"""Frozen, checksum-validated 2024 TTBB B0 production from the certified EOS inventory.

prepare -> Condor pilot -> authorize -> Condor DAG (workers -> finalize).
Preparation and authorization write job descriptions; neither submits jobs.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import zlib
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import uproot

REPO = Path(__file__).resolve().parents[2]
DATASET = "TTBB-TTtoLNu2Q"
DEFAULT_ENV = Path("/isilon/export/home/jhuan166/micromamba/envs/ttbar")
DEFAULT_MAMBA = Path("/isilon/export/home/jhuan166/.local/bin/micromamba")


def now():
    return datetime.now(UTC).isoformat()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def command(argv, log, *, cwd=None, timeout=3600):
    with Path(log).open("a") as output:
        output.write("COMMAND " + json.dumps([str(arg) for arg in argv]) + "\n")
        output.flush()
        subprocess.run([str(arg) for arg in argv], stdout=output, stderr=subprocess.STDOUT,
                       cwd=cwd, timeout=timeout, check=True)


def read_config(campaign):
    config = json.loads((campaign / "campaign.json").read_text())
    for name, digest in config["code_sha256"].items():
        if sha(campaign / "code" / name) != digest:
            raise ValueError(f"Frozen production code changed: {name}")
    for name in ("inventory", "truth_manifest"):
        if sha(campaign / config[name]) != config[f"{name}_sha256"]:
            raise ValueError(f"Pinned {name} changed")
    return config


def records_for(campaign):
    return json.loads((campaign / "inventory.json").read_text())["files"]


def write_job(campaign, name, arguments, config):
    (campaign / f"{name}.sub").write_text("\n".join([
        "universe = vanilla", "getenv = false", "should_transfer_files = NO",
        "use_x509userproxy = true", f"x509userproxy = {config['proxy']}",
        "request_cpus = 1", "request_memory = 4G", "request_disk = 2G",
        f'+JobBatchName = "{config["batch_name"]}_{name}"',
        f"initialdir = {campaign}", f"executable = {campaign}/worker.sh",
        f"arguments = {arguments}", f"log = {campaign}/logs/jobs.log",
        f"output = {campaign}/logs/{name}_$(Cluster)_$(Process).out",
        f"error = {campaign}/logs/{name}_$(Cluster)_$(Process).err", "queue 1", "",
    ]))


def prepare(args):
    if args.max_jobs < 1 or not args.proxy.is_file():
        raise ValueError("A positive concurrency limit and an existing CMS proxy are required")
    source = args.truth_campaign.resolve()
    certificate = json.loads((source / "completion.json").read_text())
    if certificate["state"] != "complete" or certificate["failed_or_missing_pairs"]:
        raise ValueError("Truth campaign is not complete")
    inventory = source / "inventory.json"
    manifest = source / "TTBB-truth-manifest.json"
    if (sha(inventory) != certificate["inventory_sha256"]
            or sha(manifest) != certificate["manifests"]["TTBB"]["sha256"]):
        raise ValueError("Certified truth inventory or manifest changed")
    records = [r for r in json.loads(inventory.read_text())["files"] if r["sample"] == "TTBB"]
    truth = json.loads(manifest.read_text())
    expected = {r["nano_uuid"]: r for r in records}
    if len(expected) != len(records) or len(records) != len(truth["files"]):
        raise ValueError("Duplicate input UUID or manifest coverage mismatch")
    for row in truth["files"]:
        item = expected[row["nano_uuid"]]
        if (row["entries"] != item["entries"] or row["source_lfn"] != item["source_lfn"]
                or row["nano_file"] != item["nano_file"]):
            raise ValueError("Truth manifest and NanoAOD inventory disagree")
        labels = (manifest.parent / row["labels"]).resolve()
        if sha(labels) != row["sha256"]:
            raise ValueError(f"Changed truth payload: {labels}")
        row["labels"] = str(labels)
    summary = certificate["summary"]["TTBB"]
    if (len(records) != summary["verified_files"]
            or sum(r["entries"] for r in records) != summary["verified_events"]):
        raise ValueError("TTBB population differs from its certificate")
    if args.pilot_id not in {r["id"] for r in records}:
        raise ValueError("Pilot input is not part of the certified TTBB inventory")
    dirty = subprocess.check_output(["git", "-C", str(REPO), "status", "--porcelain"], text=True)
    if dirty:
        raise ValueError("Commit production code before freezing the campaign")
    campaign = args.campaign.resolve()
    campaign.mkdir(parents=True, exist_ok=False)
    for directory in ("logs", "attempts", "status", "locks", "processed/roots",
                      "processed/pickles", "processed/metadata", "pilot/roots",
                      "pilot/pickles", "pilot/metadata"):
        (campaign / directory).mkdir(parents=True)
    code = campaign / "code"
    shutil.copytree(REPO / "src", code / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    code_files = ["condor/scripts/ttbb_b0_campaign.py", "condor/scripts/validate_ttbb_b0_weights.py",
                  "condor/scripts/normalize.py", "condor/scripts/validate_processed.py",
                  "diagnostics/validate_b0_inputs.py", "diagnostics/validate_ttbb_matching.py",
                  "diagnostics/check_jet_tagger_roundtrip.py", "environment.yaml", "pyproject.toml"]
    for name in code_files:
        destination = code / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / name, destination)
    write_json(campaign / "inventory.json", {"source_inventory": str(inventory),
        "source_inventory_sha256": sha(inventory), "files": sorted(records, key=lambda r: r["id"])})
    write_json(campaign / "truth-manifest.json", truth)
    shutil.copy2(source / "completion.json", campaign / "truth-certificate.json")
    config = {"schema_version": 1, "created_utc": now(), "dataset": DATASET,
        "processor_commit": subprocess.check_output(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip(),
        "processor_checkout": str(REPO), "code_sha256": {
            str(p.relative_to(code)): sha(p) for p in sorted(code.rglob("*")) if p.is_file()},
        "inventory": "inventory.json", "inventory_sha256": sha(campaign / "inventory.json"),
        "truth_manifest": "truth-manifest.json", "truth_manifest_sha256": sha(campaign / "truth-manifest.json"),
        "source_truth_manifest": str(manifest), "source_truth_manifest_sha256": sha(manifest),
        "files": len(records), "input_events": sum(r["entries"] for r in records),
        "input_profile": "b0", "kinematic_variation": "nominal", "save_systematics": True,
        "chunksize": 10000, "files_per_job": 1, "max_jobs": args.max_jobs,
        "pilot_id": args.pilot_id, "pilot_reference": str(args.reference_skim.resolve()),
        "pilot_reference_sha256": sha(args.reference_skim), "proxy": str(args.proxy.resolve()),
        "environment": str(DEFAULT_ENV), "batch_name": "VCB_B0_TTBB_20261103",
        "outputs": "BRUX processed/{roots,pickles,metadata}; EOS is the preserved input source",
        "normalization": "Nominal finalWeight after complete coverage; all-input variation sums retained",
        "scope": "TTBB-only B0 preparation; no sample stitching, PDF/alphaS output or training"}
    write_json(campaign / "campaign.json", config)
    wrapper = campaign / "worker.sh"
    wrapper.write_text("\n".join([
        "#!/bin/bash", "set -euo pipefail", "export PATH=/usr/local/bin:/usr/bin:/bin",
        f"export X509_USER_PROXY={shlex.quote(config['proxy'])}",
        "export XrdSecPROTOCOL=gsi,unix XRD_NETWORKSTACK=IPv4",
        "export XRD_CONNECTIONWINDOW=30 XRD_REQUESTTIMEOUT=120",
        "export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1",
        'export XDG_CACHE_HOME="${_CONDOR_SCRATCH_DIR:-/tmp}/vcb-ttbb-$$-cache"',
        'export MPLCONFIGDIR="$XDG_CACHE_HOME/matplotlib"',
        f"export PYTHONPATH={shlex.quote(str(code / 'src'))}",
        f"exec {DEFAULT_MAMBA} run -p {DEFAULT_ENV} python -u "
        f"{shlex.quote(str(code / 'condor/scripts/ttbb_b0_campaign.py'))} "
        f'"$@" --campaign {shlex.quote(str(campaign))}', "",
    ]))
    wrapper.chmod(0o755)
    write_job(campaign, "pilot", "pilot", config)
    write_job(campaign, "worker", "worker --id $(pair)", config)
    write_job(campaign, "finalize", "finalize", config)
    print(json.dumps({"campaign": str(campaign), "files": len(records),
                      "input_events": config["input_events"], "next": "Submit pilot.sub"}, indent=2))


def staged_input(record, path, log):
    command(["/usr/bin/xrdcp", "--nopbar", "--cksum", "adler32", record["nano_file"], path],
            log, timeout=900)
    checksum = 1
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum = zlib.adler32(block, checksum)
    if (path.stat().st_size != record["nano_bytes"]
            or f"{checksum:08x}" != record["nano_adler32"].lower()):
        raise ValueError("EOS input size or Adler-32 differs from the certified inventory")


def compare_reference(skim, config):
    from validate_ttbb_b0_weights import SCALE_BRANCHES, SYSTEMATIC_BRANCHES

    if sha(config["pilot_reference"]) != config["pilot_reference_sha256"]:
        raise ValueError("Pilot reference changed")
    with uproot.open(config["pilot_reference"]) as old, uproot.open(skim) as new:
        before, after = old["Events"].arrays(library="np"), new["Events"].arrays(library="np")
        if set(after) - set(before) != SCALE_BRANCHES | SYSTEMATIC_BRANCHES or set(before) - set(after):
            raise ValueError("Unexpected branch change in TTBB pilot")
        for name in before:
            np.testing.assert_array_equal(before[name], after[name], err_msg=name)
        for name, branch in old["Norm"].items():
            np.testing.assert_array_equal(branch.array(library="np"),
                                          new["Norm"][name].array(library="np"), err_msg=name)
    return {"unchanged_branches": len(before), "new_branches": 24,
            "nominal_values_and_normalization_unchanged": True}


def run_one(campaign, config, record, *, pilot=False):
    sys.path.insert(0, str(REPO / "diagnostics"))
    from validate_b0_inputs import validate as validate_b0
    from validate_ttbb_b0_weights import validate as validate_weights

    identity = record["id"]
    destination = campaign / ("pilot" if pilot else "processed")
    attempt = Path(tempfile.mkdtemp(prefix=identity + ".", dir=campaign / "attempts"))
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="vcb_ttbb_", dir=os.environ.get("_CONDOR_SCRATCH_DIR")) as scratch:
            nano = Path(scratch) / "nano.root"
            staged_input(record, nano, attempt / "stage.log")
            manifest = campaign / config["truth_manifest"]
            argv = [sys.executable, "-u", "-m", "vcb.run", "--year", "2024",
                    "--files", str(nano), "--files-name", DATASET, "--input-profile", "b0",
                    "--kinematic-variation", "nominal", "--save-systematics", "--root-only",
                    "--truth-label-manifest", str(manifest), "--truth-label-manifest-sha256",
                    config["truth_manifest_sha256"], "--chunksize", str(config["chunksize"]),
                    "--maxchunks", "0", "--batch-size", "9999", "--naming-tag", identity,
                    "--outdir", str(attempt)]
            command(argv, attempt / "skim.log", cwd=attempt)
            roots = list(attempt.glob("nano_skim_*_batch_*.root"))
            if len(roots) != 1:
                raise ValueError(f"Expected one skim, found {len(roots)}")
            skim = roots[0]
            metadata = attempt / "outfiles" / f"{identity}.kinematics.json"
            totals = attempt / "outfiles" / f"{identity}.pkl"
            b0 = validate_b0(nano, skim, metadata, manifest)
            weights = validate_weights(nano, skim, totals)
            if (b0["input_events"] != record["entries"] or b0["input_uuid"] != record["nano_uuid"]
                    or not b0["passed"] or not weights["passed"]):
                raise ValueError("Unexpected input identity, event coverage or failed validation")
            schema = weights.pop("schema")
            if pilot:
                reference = compare_reference(skim, config)
                command([sys.executable, REPO / "diagnostics/check_jet_tagger_roundtrip.py",
                         "--input-file", nano, "--output-file", skim, "--input-profile", "b0",
                         "--report", campaign / "pilot-roundtrip.txt"], attempt / "roundtrip.log")
                write_json(campaign / "schema.json", schema)
                with (campaign / "schema.csv").open("w") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(["variable_name", "variable_type"])
                    writer.writerows(sorted(schema.items()))
            else:
                reference = None
                if schema != json.loads((campaign / "schema.json").read_text()):
                    raise ValueError("Output schema differs from the validated pilot")
            artifacts = {}
            for kind, original, target in [
                ("root", skim, destination / "roots" / f"{identity}.root"),
                ("pickle", totals, destination / "pickles" / f"{identity}.pkl"),
                ("metadata", metadata, destination / "metadata" / f"{identity}.kinematics.json"),
            ]:
                original.replace(target)
                artifacts[kind] = {"path": str(target), "sha256": sha(target), "bytes": target.stat().st_size}
            b0["skim"] = artifacts["root"]["path"]
            b0["matching"]["source"] = artifacts["root"]["path"]
            return {"state": "complete", "id": identity, "sample": "TTBB", "completed_utc": now(),
                    "elapsed_seconds": time.monotonic() - started, "command": argv,
                    "source": record, "b0": b0, "weights": weights, "reference": reference,
                    "artifacts": artifacts, "attempt": str(attempt), "pilot": pilot}
    except Exception:
        write_json(attempt / "failure.json", {"id": identity, "failed_utc": now(),
                                              "error": traceback.format_exc()})
        raise


def pilot(args):
    campaign = args.campaign.resolve()
    config = read_config(campaign)
    if (campaign / "pilot-passed.json").exists():
        raise ValueError("Pilot already passed; use its recorded result")
    record = next(r for r in records_for(campaign) if r["id"] == config["pilot_id"])
    result = run_one(campaign, config, record, pilot=True)
    write_json(campaign / "pilot-result.json", result)
    command([sys.executable, REPO / "condor/scripts/normalize.py", "--processed-dir", campaign / "pilot"],
            campaign / "logs/pilot-normalization.log")
    command([sys.executable, REPO / "condor/scripts/validate_processed.py", "--processed-dir",
             campaign / "pilot", "--schema-baseline", campaign / "schema.csv"],
            campaign / "logs/pilot-validation.log")
    write_json(campaign / "pilot-passed.json", {"state": "passed", "completed_utc": now(),
        "campaign_sha256": sha(campaign / "campaign.json"), "schema_sha256": sha(campaign / "schema.json"),
        "schema_csv_sha256": sha(campaign / "schema.csv"), "pilot_result_sha256": sha(campaign / "pilot-result.json"),
        "normalized_root_sha256": sha(result["artifacts"]["root"]["path"]),
        "input_events": record["entries"], "selected_events": result["b0"]["selected_events"],
        "fully_matched": result["b0"]["fully_matched"],
        "branches_before_finalWeight": result["b0"]["branches"]})
    print((campaign / "pilot-passed.json").read_text())


def check_gate(campaign):
    gate = json.loads((campaign / "pilot-passed.json").read_text())
    for name, key in [("campaign.json", "campaign_sha256"), ("schema.json", "schema_sha256"),
                      ("schema.csv", "schema_csv_sha256"), ("pilot-result.json", "pilot_result_sha256")]:
        if gate["state"] != "passed" or sha(campaign / name) != gate[key]:
            raise ValueError("Validated pilot/configuration changed")
    return gate


def authorize(args):
    campaign = args.campaign.resolve()
    config = read_config(campaign)
    check_gate(campaign)
    records = records_for(campaign)
    dag = []
    for record in records:
        identity = record["id"]
        dag += [f"JOB {identity} {campaign}/worker.sub", f'VARS {identity} pair="{identity}"',
                f"RETRY {identity} 2"]
    dag += [f"JOB FINALIZE {campaign}/finalize.sub", "RETRY FINALIZE 1"]
    dag += [f"PARENT {r['id']} CHILD FINALIZE" for r in records]
    with (campaign / "production.dag").open("x") as output:
        output.write("\n".join(dag) + "\n")
    print(f"Ready: {len(records)} workers; condor_submit_dag -maxjobs {config['max_jobs']} "
          f"{campaign}/production.dag")


def worker(args):
    campaign = args.campaign.resolve()
    config = read_config(campaign)
    check_gate(campaign)
    record = next(r for r in records_for(campaign) if r["id"] == args.id)
    status = campaign / "status" / f"{args.id}.json"
    with (campaign / "locks" / args.id).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if status.exists():
            result = json.loads(status.read_text())
            for artifact in result["artifacts"].values():
                if sha(artifact["path"]) != artifact["sha256"]:
                    raise ValueError("Previously published worker output changed")
            print(f"Already complete and verified: {args.id}")
            return
        if (campaign / "pre-normalization.json").exists():
            raise ValueError("Campaign normalization already started")
        result = run_one(campaign, config, record)
        write_json(status, result)
        print(json.dumps({"id": args.id, "state": result["state"],
                          "selected_events": result["b0"]["selected_events"]}))


def finalize(args):
    campaign = args.campaign.resolve()
    config = read_config(campaign)
    check_gate(campaign)
    records = records_for(campaign)
    expected = {r["id"] for r in records}
    statuses = list((campaign / "status").glob("*.json"))
    if {p.stem for p in statuses} != expected:
        raise ValueError("Missing or extra production statuses; normalization is forbidden")
    output = campaign / "processed"
    for directory, suffix in [("roots", ".root"), ("pickles", ".pkl")]:
        if {p.name.removesuffix(suffix) for p in (output / directory).glob(f"*{suffix}")} != expected:
            raise ValueError(f"Missing or extra {directory}; normalization is forbidden")
    results = [json.loads(path.read_text()) for path in sorted(statuses)]
    by_id = {record["id"]: record for record in records}
    for path, result in zip(sorted(statuses), results, strict=True):
        expected_record = by_id[path.stem]
        if (result["id"] != path.stem or result["source"] != expected_record
                or result["b0"]["input_uuid"] != expected_record["nano_uuid"]
                or result["b0"]["input_events"] != expected_record["entries"]):
            raise ValueError("Published worker record does not match the pinned input inventory")
    if (any(r["state"] != "complete" or not r["b0"]["passed"] or not r["weights"]["passed"]
            or r["pilot"] for r in results)
            or sum(r["b0"]["input_events"] for r in results) != config["input_events"]):
        raise ValueError("Incomplete validated TTBB input coverage")
    status_hashes = {p.name: sha(p) for p in statuses}
    marker = campaign / "pre-normalization.json"
    if marker.exists():
        if json.loads(marker.read_text())["status_sha256"] != status_hashes:
            raise ValueError("Worker records changed during finalization")
    else:
        for result in results:
            for artifact in result["artifacts"].values():
                if sha(artifact["path"]) != artifact["sha256"]:
                    raise ValueError("Worker artifact changed before normalization")
        write_json(marker, {"verified_utc": now(), "status_sha256": status_hashes,
                            "files": len(results), "input_events": config["input_events"]})
    totals = {}
    for result in results:
        for name, values in result["weights"]["all_input_totals"].items():
            totals[name] = totals.get(name, 0) + np.asarray(values, dtype=np.float64)
    write_json(output / "metadata/weight-totals.json", {
        "scope": "Complete TTBB source before reco selection; signed sums, not raw counts",
        "input_events": config["input_events"], "input_files": len(results),
        "all_input_totals": {name: np.asarray(values).tolist() for name, values in totals.items()},
        "usage": "Only nominal finalWeight is appended; use the corresponding sums for variation templates"})
    command([sys.executable, REPO / "condor/scripts/normalize.py", "--processed-dir", output],
            campaign / "logs/normalization.log", timeout=14400)
    command([sys.executable, REPO / "condor/scripts/validate_processed.py", "--processed-dir", output,
             "--schema-baseline", campaign / "schema.csv"], campaign / "logs/validation.log", timeout=14400)
    report_dir = campaign / "matching-report"
    if not (report_dir / "matching_summary.json").exists():
        if report_dir.exists():
            report_dir.rename(campaign / f"matching-report-incomplete-{time.time_ns()}")
        command([sys.executable, "-m", "vcb.postprocessing.matching", "--files", output / "roots",
                 "--label", "TTBB", "--outdir", report_dir], campaign / "logs/matching.log", timeout=14400)
    matching = json.loads((report_dir / "matching_summary.json").read_text())["samples"]["TTBB"]
    selected = sum(r["b0"]["selected_events"] for r in results)
    if matching["counts"]["events_in_processed_files"] != selected:
        raise ValueError("Matching report event accounting differs from worker validation")
    publication = {name: {"path": str(path), "sha256": sha(path), "bytes": path.stat().st_size}
                   for name, path in ((str(p.relative_to(output)), p)
                                      for p in sorted(output.rglob("*")) if p.is_file())}
    write_json(campaign / "publication.json", publication)
    write_json(campaign / "completion.json", {"state": "complete", "completed_utc": now(),
        "processor_commit": config["processor_commit"], "files": len(results),
        "input_events": config["input_events"], "selected_events": selected,
        "matching_counts": matching["counts"], "publication_sha256": sha(campaign / "publication.json"),
        "matching_summary": str(report_dir / "matching_summary.txt"),
        "normalization": str(output / "metadata/normalization.json"), "training_started": False})
    print((campaign / "completion.json").read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("prepare", "pilot", "authorize", "worker", "finalize"):
        item = sub.add_parser(action)
        item.add_argument("--campaign", type=Path, required=True)
        if action == "prepare":
            item.add_argument("--truth-campaign", type=Path, required=True)
            item.add_argument("--pilot-id", required=True)
            item.add_argument("--reference-skim", type=Path, required=True)
            item.add_argument("--proxy", type=Path, required=True)
            item.add_argument("--max-jobs", type=int, default=40)
        if action == "worker":
            item.add_argument("--id", required=True)
    args = parser.parse_args()
    {"prepare": prepare, "pilot": pilot, "authorize": authorize, "worker": worker,
     "finalize": finalize}[args.action](args)


if __name__ == "__main__":
    main()
