#!/usr/bin/env python3
"""
Second pass: append finalWeight = weight / global_np_nominal to skim ROOTs.

The skimmer never writes finalWeight -- it cannot know the denominator, which
sums np_nominal over every batch of the campaign. This script computes that
global denominator and appends the finalWeight branch to each ROOT **in
place** with PyROOT (only the new baskets are written, ~3 B/event; the
existing branches are untouched).

Per-file denominators are read from the ROOT's own single-entry "Norm" tree
(written by the skimmer since the second-pass overhaul), falling back to the
paired pickle in pickles/<stem>.pkl. A ROOT with neither is a hard error: its
events would enter the numerator with no matching denominator contribution,
silently inflating every yield.

Provenance is written next to the branch (TParameter finalWeight_np_nominal +
TNamed finalWeight_provenance carrying a fingerprint of the batch list) and to
metadata/normalization.json, so a stale finalWeight -- one computed from a
batch list that no longer matches the files on disk -- is detectable instead
of silent.

Usage:
    micromamba run -n ttbar python condor/scripts/normalize.py \
        --processed-dir <input-root>/processed-nano/<tag> [--target merged]

Idempotent: files that already carry finalWeight are skipped. --force
recomputes and rewrites them (a full uproot rewrite of those files, since ROOT
cannot cleanly drop an existing branch in place).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import uproot

REL_TOL = 1e-9  # Norm tree vs pickle cross-check


def make_abs(path: str | Path) -> Path:
    """Return an absolute path without resolving symlinks."""
    return Path(os.path.abspath(os.path.expandvars(os.path.expanduser(str(path)))))


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Append a globally normalized finalWeight branch to skim ROOTs in place.",
    )
    parser.add_argument(
        "--processed-dir",
        required=True,
        type=Path,
        help="Processed output directory containing roots/, pickles/, and metadata/.",
    )
    parser.add_argument(
        "--target",
        choices=["batches", "merged"],
        default="batches",
        help=(
            "batches: normalize every ROOT in roots/ (denominator = their sum). "
            "merged: normalize merged/total.root (denominator = its own Norm-tree sum; "
            "hadd concatenated one Norm entry per batch)."
        ),
    )
    parser.add_argument("--year", default="2024", help="Year key expected inside each pickle.")
    parser.add_argument(
        "--dataset",
        default=None,
        help="Dataset key expected inside each pickle. Defaults to inferring a single dataset.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Recompute finalWeight in files that already have it "
            "(full rewrite of those files, not an in-place append)."
        ),
    )
    return parser.parse_args()


def read_norm_tree(root_path: Path) -> tuple[float, float] | None:
    """(np_nominal, nevents) summed over the file's Norm tree, or None if absent."""
    with uproot.open(root_path) as handle:
        if "Norm" not in handle:
            return None
        norm = handle["Norm"]
        return (
            float(np.sum(norm["np_nominal"].array(library="np"))),
            float(np.sum(norm["nevents"].array(library="np"))),
        )


def read_pickle_totals(
    pickle_path: Path, year: str, dataset: str | None
) -> tuple[str, float, float]:
    """(dataset, np_nominal, nevents) from one batch pickle."""
    with pickle_path.open("rb") as handle:
        payload = pickle.load(handle)

    if year not in payload:
        raise KeyError(f"Year {year} not found in {pickle_path}")

    year_block = payload[year]
    resolved = dataset
    if resolved is None:
        if len(year_block) != 1:
            raise ValueError(
                f"Expected exactly one dataset in {pickle_path}, found {list(year_block.keys())}"
            )
        resolved = next(iter(year_block))

    if resolved not in year_block:
        raise KeyError(
            f"Dataset {resolved} not found in {pickle_path}. Available: {list(year_block.keys())}"
        )

    totals = year_block[resolved].get("totals", {})
    if "np_nominal" not in totals:
        raise KeyError(f"totals['np_nominal'] missing in {pickle_path} (data, not MC?)")

    return resolved, float(totals["np_nominal"]), float(totals.get("nevents", 0.0))


def collect_denominators(
    root_paths: list[Path], pickles_dir: Path, year: str, dataset: str | None
) -> tuple[str | None, dict[str, float], float]:
    """
    Per-ROOT np_nominal, keyed by file stem: Norm tree preferred, paired pickle
    as fallback, cross-checked when both exist. Raises on a ROOT with neither
    (orphan ROOT = silent yield inflation). Orphan pickles are only warned
    about: their events are not in the numerator, so skipping them is
    consistent.
    """
    resolved_dataset = dataset
    per_file: dict[str, float] = {}
    total_nevents = 0.0

    for root_path in root_paths:
        stem = root_path.stem
        from_norm = read_norm_tree(root_path)

        pickle_path = pickles_dir / f"{stem}.pkl"
        from_pickle = None
        if pickle_path.is_file():
            resolved_dataset, np_nom, nevents = read_pickle_totals(
                pickle_path, year, resolved_dataset
            )
            from_pickle = (np_nom, nevents)

        if from_norm is None and from_pickle is None:
            raise FileNotFoundError(
                f"{root_path.name}: no Norm tree in the ROOT and no pickle at "
                f"{pickle_path}. Cannot include this file's events in the "
                "numerator without its denominator contribution -- fix or remove it."
            )

        if from_norm is not None and from_pickle is not None:
            rel = abs(from_norm[0] - from_pickle[0]) / max(abs(from_pickle[0]), 1e-300)
            if rel > REL_TOL:
                raise ValueError(
                    f"{root_path.name}: Norm tree np_nominal ({from_norm[0]}) disagrees "
                    f"with pickle ({from_pickle[0]}, rel {rel:.2e}). The ROOT and pickle "
                    "are from different skims -- re-run the batch or remove the stale file."
                )

        np_nom, nevents = from_norm if from_norm is not None else from_pickle
        per_file[stem] = np_nom
        total_nevents += nevents

    orphan_pickles = sorted(
        p.stem for p in pickles_dir.glob("*.pkl") if p.stem not in per_file
    ) if pickles_dir.is_dir() else []
    if orphan_pickles:
        print(
            f"WARNING: {len(orphan_pickles)} pickle(s) without a matching ROOT "
            f"(skipped, consistent): {orphan_pickles}"
        )

    return resolved_dataset, per_file, total_nevents


def derive_sigma_lumi(root_paths: list[Path]) -> float | None:
    """sigma x L = weight / weight_noxsec, constant per construction; None if underivable."""
    for root_path in root_paths:
        with uproot.open(root_path) as handle:
            tree = handle["Events"]
            if tree.num_entries == 0:
                continue
            arr = tree.arrays(["weight", "weight_noxsec"], entry_stop=1000, library="np")
            nonzero = arr["weight_noxsec"] != 0
            if np.any(nonzero):
                return float((arr["weight"][nonzero] / arr["weight_noxsec"][nonzero])[0])
    return None


def has_final_weight(root_path: Path) -> bool:
    """True if the Events tree already carries a finalWeight branch."""
    with uproot.open(root_path) as handle:
        return "finalWeight" in handle["Events"]


def append_final_weight(root_path: Path, global_np_nominal: float, fingerprint: str) -> int:
    """
    Append finalWeight = weight / global_np_nominal to the Events tree in
    place, plus provenance objects. Only the new baskets and the updated tree
    header are written; every existing branch is untouched. Returns the number
    of entries filled.
    """
    from array import array

    import ROOT

    ROOT.gROOT.SetBatch(True)

    # read the weight column once, vectorized (much faster than GetEntry)
    weights = uproot.open(root_path)["Events"]["weight"].array(library="np")

    fout = ROOT.TFile.Open(str(root_path), "UPDATE")
    tree = fout.Get("Events")
    val = array("d", [0.0])
    branch = tree.Branch("finalWeight", val, "finalWeight/D")
    for w in weights:
        val[0] = w / global_np_nominal
        branch.Fill()
    tree.Write("", ROOT.TObject.kOverwrite)

    write_provenance(fout, global_np_nominal, fingerprint)
    fout.Close()
    return len(weights)


def rewrite_final_weight(root_path: Path, global_np_nominal: float, fingerprint: str) -> int:
    """
    --force path: full uproot rewrite (ROOT cannot cleanly drop an existing
    branch in place). Preserves the Norm tree; provenance is re-written via a
    PyROOT UPDATE afterwards.
    """
    import ROOT

    ROOT.gROOT.SetBatch(True)

    with uproot.open(root_path) as handle:
        arrays = handle["Events"].arrays(library="np")
        norm = (
            handle["Norm"].arrays(library="np") if "Norm" in handle else None
        )

    arrays["finalWeight"] = np.asarray(arrays["weight"], dtype=np.float64) / global_np_nominal

    temp_path = root_path.with_suffix(".tmp.root")
    if temp_path.exists():
        temp_path.unlink()
    with uproot.recreate(temp_path, compression=uproot.LZ4(4)) as handle:
        handle["Events"] = arrays
        if norm is not None:
            handle["Norm"] = norm
    temp_path.replace(root_path)

    fout = ROOT.TFile.Open(str(root_path), "UPDATE")
    write_provenance(fout, global_np_nominal, fingerprint)
    fout.Close()
    return len(arrays["finalWeight"])


def write_provenance(fout, global_np_nominal: float, fingerprint: str) -> None:
    """TParameter + TNamed next to Events: which denominator, from which batch list."""
    import ROOT

    fout.cd()  # make sure the provenance objects land in this file
    param = ROOT.TParameter("double")("finalWeight_np_nominal", global_np_nominal)
    param.Write("", ROOT.TObject.kOverwrite)
    named = ROOT.TNamed("finalWeight_provenance", fingerprint)
    named.Write("", ROOT.TObject.kOverwrite)


def main() -> None:
    """Entry point."""
    args = parse_args()
    processed_dir = make_abs(args.processed_dir)
    roots_dir = processed_dir / "roots"
    pickles_dir = processed_dir / "pickles"
    metadata_dir = processed_dir / "metadata"

    if args.target == "merged":
        merged = processed_dir / "merged" / "total.root"
        if not merged.is_file():
            raise FileNotFoundError(f"Merged ROOT not found: {merged}")
        root_paths = [merged]
    else:
        if not roots_dir.is_dir():
            raise FileNotFoundError(f"ROOT directory not found: {roots_dir}")
        root_paths = sorted(p for p in roots_dir.glob("*.root") if p.is_file())
        if not root_paths:
            raise FileNotFoundError(f"No ROOT files found in {roots_dir}")

    dataset, per_file, total_nevents = collect_denominators(
        root_paths, pickles_dir, args.year, args.dataset
    )
    global_np_nominal = sum(per_file.values())
    if global_np_nominal == 0.0:
        raise ValueError("Global np_nominal is 0. Cannot compute finalWeight.")

    sigma_x_lumi = derive_sigma_lumi(root_paths)

    # fingerprint of exactly which files fed the denominator, so a stale
    # finalWeight (batch list changed since) is detectable, not silent
    fingerprint_src = "\n".join(f"{stem}:{per_file[stem]!r}" for stem in sorted(per_file))
    fingerprint = hashlib.sha1(fingerprint_src.encode()).hexdigest()

    updated, skipped = [], []
    for root_path in root_paths:
        if has_final_weight(root_path):
            if args.force:
                n = rewrite_final_weight(root_path, global_np_nominal, fingerprint)
                updated.append(root_path.stem)
                print(f"  rewrote  {root_path.name} ({n:,} entries, --force)")
            else:
                skipped.append(root_path.stem)
                print(f"  skipped  {root_path.name} (finalWeight present; use --force)")
        else:
            n = append_final_weight(root_path, global_np_nominal, fingerprint)
            updated.append(root_path.stem)
            print(f"  appended {root_path.name} ({n:,} entries)")

    metadata_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "target": args.target,
        "year": args.year,
        "dataset": dataset,
        "global_np_nominal": global_np_nominal,
        "sigma_x_lumi": sigma_x_lumi,
        "total_nevents": total_nevents,
        "batches": sorted(per_file),
        "n_batches": len(per_file),
        "fingerprint": fingerprint,
        "updated": updated,
        "skipped": skipped,
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    summary_path = metadata_dir / "normalization.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")

    print(
        f"Global np_nominal = {global_np_nominal} over {len(per_file)} file(s); "
        f"finalWeight appended to {len(updated)}, skipped {len(skipped)}."
    )
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
