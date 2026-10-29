#!/usr/bin/env python3
"""Inventory the existing nominal 2024 conversions for C1 tasks 1 and 2.

No event selection or skim production runs here. Original conversion input
lists and the completed TTBB EOS catalog define coverage, never old HDF5 counts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from multiprocessing import get_context
from pathlib import Path

PRODUCTION = "charge_Run3_2024_150X_v1"
NANO_SUFFIX = "_CMSSW_15_CHARGE_NanoAOD.root"
REDIRECTOR = "root://cms-xrd-global.cern.ch/"
SAMPLES = {"TTCB": "TTtoLNuCB_Summer24MiniAODv6", "TT2Q": "TTtoLNu2Q_Summer24MiniAODv6"}
REQUIRED_BRANCHES = {
    "run", "luminosityBlock", "event", "genWeight", "Jet_pt", "Jet_eta", "Jet_phi",
    "Jet_mass", "GenPart_pdgId", "GenPart_status", "GenPart_statusFlags", "GenPart_pt",
    "GenPart_eta", "GenPart_phi", "GenPart_mass", "GenPart_genPartIdxMother",
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    """Atomic replacement is for resumable reports, not existing label files."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def unique_sources(lfns):
    mapping = {}
    for lfn in lfns:
        if not lfn.startswith("/store/mc/RunIII2024Summer24MiniAODv6/"):
            raise ValueError(f"Input is outside the declared 2024 campaign: {lfn}")
        stem = Path(lfn).stem
        if stem in mapping:
            raise ValueError(f"Duplicate or ambiguous MiniAOD basename: {stem}")
        mapping[stem] = lfn
    return mapping


def local_records(workspace, sample, directory):
    base = workspace / "MC" / directory
    inputs = base / "productions" / PRODUCTION / "cmssw/input-lists" / PRODUCTION
    input_list = inputs / "files_all.txt"
    lfns = [s.strip() for s in input_list.read_text().splitlines()
            if s.strip() and not s.startswith("#")]
    expected = unique_sources(lfns)
    dataset = (inputs / "dataset.txt").read_text().strip()
    found, records = set(), []
    for nano in sorted((base / "NanoAOD-cmssw-charge" / PRODUCTION).glob("batch_*/*.root")):
        if not nano.name.endswith(NANO_SUFFIX):
            raise ValueError(f"Unexpected ROOT file in the canonical collection: {nano}")
        stem = nano.name.removesuffix(NANO_SUFFIX)
        if stem not in expected or stem in found:
            raise ValueError(f"Unexpected or duplicated conversion: {nano}")
        found.add(stem)
        lfn = expected[stem]
        local = base / "MiniAOD" / (stem + ".root")
        stat = nano.stat()
        records.append({
            "id": sample + "_" + stem, "sample": sample, "dataset": dataset,
            "source_lfn": lfn, "source_entry_range": "complete original file",
            "nano_file": str(nano), "nano_bytes": stat.st_size,
            "nano_mtime_ns": stat.st_mtime_ns,
            "native_truth": str(local) if local.is_file() else REDIRECTOR + lfn,
            "native_kind": "local MiniAOD" if local.is_file() else "remote MiniAOD",
            "conversion_input_list": str(input_list),
        })
    missing = sorted(set(expected) - found)
    if missing:
        raise ValueError(f"{sample}: {len(missing)} declared conversions are missing: {missing[:5]}")
    return records, {"path": str(input_list), "sha256": digest(input_list),
                     "dataset": dataset, "declared_files": len(expected)}


def ttbb_records(workspace):
    production = workspace / "cmssw-charge-run/productions/ttbb_eos_20261024"
    catalog_path, completion_path = production / "catalog.json", production / "completion.json"
    catalog, completion = json.loads(catalog_path.read_text()), json.loads(completion_path.read_text())
    manifest_path = production / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if completion["state"] != "completed" or digest(manifest_path) != completion["manifest_sha256"]:
        raise ValueError("TTBB completion record does not bind the production manifest")
    expected = unique_sources([r["lfn"] for r in manifest["input_files"]])
    actual = unique_sources([r["lfn"] for r in catalog["files"]])
    if actual != expected or len(actual) != completion["input_files"]:
        raise ValueError("TTBB catalog coverage differs from the completed manifest")
    if sum(r["source_file_events"] for r in catalog["files"]) != completion["events"]:
        raise ValueError("TTBB input event total differs from completion")
    records = []
    for row in catalog["files"]:
        if row["skip_events"] != 0 or row["max_events"] != row["source_file_events"]:
            raise ValueError("Partial TTBB source range cannot replace a complete conversion")
        records.append({
            "id": "TTBB_" + Path(row["lfn"]).stem, "sample": "TTBB", "dataset": catalog["dataset"],
            "source_lfn": row["lfn"], "source_entry_range": "complete original file",
            "source_bytes": row["source_file_bytes"], "source_adler32": row["source_adler32"],
            "nano_file": row["nano"]["url"], "nano_bytes": row["nano"]["bytes"],
            "nano_adler32": row["nano"]["adler32"], "expected_events": row["source_file_events"],
            "native_truth": row["truth"]["url"], "native_kind": "EOS complete GenTruth",
            "native_bytes": row["truth"]["bytes"], "native_adler32": row["truth"]["adler32"],
            "conversion_catalog": str(catalog_path), "conversion_batch": row["batch"],
        })
    provenance = [{"path": str(p), "sha256": digest(p)}
                  for p in (catalog_path, manifest_path, completion_path)]
    return records, provenance


def inspect_nano(record):
    import numpy as np
    import uproot

    with uproot.open(record["nano_file"], object_cache=None, array_cache=None, timeout=90) as handle:
        tree = handle["Events"]
        schema = tree.typenames()
        missing = REQUIRED_BRANCHES - schema.keys()
        if missing:
            raise ValueError(f"Missing required branches: {sorted(missing)}")
        entries = tree.num_entries
        if entries <= 0 or entries != record.get("expected_events", entries):
            raise ValueError(f"Unexpected NanoAOD entry count: {entries}")
        runs = handle["Runs"].arrays(
            ["genEventCount", "genEventSumw", "genEventSumw2"], library="np")
        run_count = int(runs["genEventCount"].sum(dtype=np.int64))
        return {
            **record, "nano_uuid": str(handle.file.uuid), "entries": entries,
            "runs_genEventCount": run_count, "runs_count_matches_events": run_count == entries,
            "sumw": float(runs["genEventSumw"].sum(dtype=np.float64)),
            "sumw2": float(runs["genEventSumw2"].sum(dtype=np.float64)),
            "branch_count": len(schema),
            "schema_sha256": hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest(),
        }


def inspect_nano_root(record):
    """Use ROOT's compiled header reader; never loop over the Events tree."""
    import ROOT

    ROOT.gROOT.SetBatch(True)
    handle = ROOT.TFile.Open(record["nano_file"])
    if not handle or handle.IsZombie():
        raise ValueError("Cannot open NanoAOD")
    try:
        tree, runs = handle.Get("Events"), handle.Get("Runs")
        if not tree or not runs:
            raise ValueError("Missing Events or Runs tree")
        schema = {b.GetName(): {"title": b.GetTitle(), "class": b.GetClassName()}
                  for b in tree.GetListOfBranches()}
        missing = REQUIRED_BRANCHES - schema.keys()
        if missing:
            raise ValueError(f"Missing required branches: {sorted(missing)}")
        entries = int(tree.GetEntries())
        if entries <= 0 or entries != record.get("expected_events", entries):
            raise ValueError(f"Unexpected NanoAOD entry count: {entries}")
        for name in ("genEventCount", "genEventSumw", "genEventSumw2"):
            if not runs.GetBranch(name):
                raise ValueError(f"Missing Runs metadata: {name}")
        weights = [(int(r.genEventCount), float(r.genEventSumw), float(r.genEventSumw2)) for r in runs]
        run_count = sum(w[0] for w in weights)
        return {
            **record, "nano_uuid": str(handle.GetUUID().AsString()), "entries": entries,
            "runs_genEventCount": run_count, "runs_count_matches_events": run_count == entries,
            "sumw": sum(w[1] for w in weights), "sumw2": sum(w[2] for w in weights),
            "branch_count": len(schema), "schema_format": "ROOT branch title and class",
            "schema_sha256": hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest(),
            "_schema": schema,
        }
    finally:
        handle.Close()


def inspect_cached(record, cache, reader="root"):
    cache_key = hashlib.sha256(json.dumps({"record": record, "reader": reader}, sort_keys=True).encode()).hexdigest()
    path = cache / (record["id"] + ".json")
    if path.exists():
        data = json.loads(path.read_text())
        if data.get("cache_key") == cache_key:
            return data["record"]
    enriched = inspect_nano_root(record) if reader == "root" else inspect_nano(record)
    schema = enriched.pop("_schema", None)
    if schema is not None:
        target = cache.parent / "schemas" / (enriched["schema_sha256"] + ".json")
        # Concurrent writers may have the same schema; unique temporary names
        # and identical content make publication safe.
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(f".{os.getpid()}.tmp")
            temporary.write_text(json.dumps(schema, sort_keys=True, indent=2) + "\n")
            temporary.replace(target)
    write_json(path, {"cache_key": cache_key, "record": enriched})
    return enriched


def validate_uniqueness(records):
    for field in ("id", "nano_uuid", "source_lfn", "nano_file"):
        counts = Counter(r[field] for r in records)
        duplicates = [key for key, count in counts.items() if count > 1]
        if duplicates:
            raise ValueError(f"Duplicated {field}: {duplicates[:5]}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--reader", choices=("root", "uproot"), default="root")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if (args.output_dir / "inventory.json").exists():
        raise FileExistsError("Final inventory exists; use a new campaign directory")
    records, sources = [], []
    for sample, directory in SAMPLES.items():
        rows, source = local_records(args.workspace.resolve(), sample, directory)
        records.extend(rows)
        sources.append(source)
    rows, source = ttbb_records(args.workspace.resolve())
    records.extend(rows)
    sources.extend(source)
    write_json(args.output_dir / "discovered-inputs.json", {"sources": sources, "files": records})
    cache = args.output_dir / "inventory-cache"
    cache.mkdir(exist_ok=True)
    inspected, failures = [], []
    # ROOT-header decoding holds Python's GIL; isolated workers also avoid
    # sharing XRootD connection state between concurrent inspections.
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=get_context("spawn")) as pool:
        futures = {pool.submit(inspect_cached, r, cache, args.reader): r for r in records}
        for index, future in enumerate(as_completed(futures), 1):
            record = futures[future]
            try:
                inspected.append(future.result())
            except Exception as error:
                failures.append({"id": record["id"], "error": repr(error)})
            if index % 100 == 0 or index == len(records):
                progress = {"checked": index, "total": len(records), "failures": len(failures)}
                write_json(args.output_dir / "inventory-progress.json", progress)
                print(json.dumps(progress), flush=True)
    write_json(args.output_dir / "inventory-failures.json", failures)
    if failures:
        raise RuntimeError(f"{len(failures)} inputs failed inspection; rerun to retry them")
    inspected.sort(key=lambda r: r["id"])
    validate_uniqueness(inspected)
    summary = {}
    for sample in (*SAMPLES, "TTBB"):
        selected = [r for r in inspected if r["sample"] == sample]
        summary[sample] = {
            "files": len(selected), "events": sum(r["entries"] for r in selected),
            "nano_bytes": sum(r["nano_bytes"] for r in selected),
            "sumw": sum(r["sumw"] for r in selected), "sumw2": sum(r["sumw2"] for r in selected),
            "native_sources": dict(Counter(r["native_kind"] for r in selected)),
            "schema_counts": dict(Counter(r["schema_sha256"] for r in selected)),
            "run_event_count_mismatches": sum(not r["runs_count_matches_events"] for r in selected),
        }
    inventory = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),  # noqa: UP017 -- CMSSW Python 3.9
        "reader": args.reader,
        "inventory_script_sha256": digest(__file__),
        "scope": "Existing complete nominal 2024 conversions; C1 tasks 1 and 2 only",
        "sources": sources, "summary": summary, "files": inspected,
        "excluded": [
            "Legacy processed NanoAOD/HDF5 collections: different selections and extraction units",
            "Local ten-file TTBB pilots: partial original-file ranges; complete EOS production selected",
            "Manual/alternate NanoAOD conversions outside the canonical production directories",
        ],
        "native_pair_content_verified": False,
        "task2_requirement": "Every pair must pass the pinned complete-truth builder before use",
    }
    write_json(args.output_dir / "inventory.json", inventory)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
