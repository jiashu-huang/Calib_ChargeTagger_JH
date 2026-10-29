#!/usr/bin/env python3
"""Prepare, run and certify C1 complete-truth sidecars, without making B0 skims.

The worker uses CMSSW Python 3.9. The frozen builder owns every physics label;
this module supplies coverage, immutable inputs, retries and atomic publication.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import zlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
from vcb.truth import TRUTH_LABEL_VERSION, UNKNOWN, CountStatus  # noqa: E402

CODE_FILES = (
    "condor/scripts/c1_truth_campaign.py", "condor/scripts/c1_truth_worker.sh",
    "condor/scripts/build_truth_labels.py", "condor/scripts/c1_inventory.py",
    "src/vcb/truth.py", "src/vcb/__init__.py",
)
NATIVE_REDIRECTORS = (
    "root://cms-xrd-global.cern.ch/", "root://cmsxrootd.fnal.gov/",
    "root://xrootd-cms.infn.it/",
)


def now():
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 -- CMSSW Python 3.9


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def read_pinned(campaign):
    config = json.loads((campaign / "campaign.json").read_text())
    if sha(campaign / "inventory.json") != config["inventory_sha256"]:
        raise ValueError("Inventory changed after campaign preparation")
    for relative, expected in config["code_sha256"].items():
        if sha(campaign / "code" / relative) != expected:
            raise ValueError(f"Pinned campaign code changed: {relative}")
    return config


def validate_pair(directory, expected, config):
    """Read back all columns and hashes; a marker file alone is never success."""
    manifest = json.loads((directory / "manifest.json").read_text())
    pins = config["code_sha256"]
    if (manifest.get("schema_version") != TRUTH_LABEL_VERSION
            or manifest.get("producer_sha256") != pins["condor/scripts/build_truth_labels.py"]
            or manifest.get("definition_sha256") != pins["src/vcb/truth.py"]
            or len(manifest["files"]) != 1):
        raise ValueError("Sidecar producer, definition or schema does not match campaign")
    row = manifest["files"][0]
    if row["nano_uuid"] != expected["nano_uuid"] or row["entries"] != expected["entries"]:
        raise ValueError("Sidecar source UUID or event count differs from inventory")
    if row.get("source_lfn", expected["source_lfn"]) != expected["source_lfn"]:
        raise ValueError("Sidecar original MiniAOD provenance differs from inventory")
    label_path = directory / row["labels"]
    if label_path.resolve().parent != directory.resolve() or sha(label_path) != row["sha256"]:
        raise ValueError("Sidecar label location or checksum is invalid")
    with np.load(label_path, allow_pickle=False) as data:
        if (data["nano_uuid"].item() != expected["nano_uuid"]
                or data["schema_version"].item() != TRUTH_LABEL_VERSION):
            raise ValueError("Label payload UUID or schema mismatch")
        for key in ("run", "luminosityBlock", "event", "count", "status"):
            if data[key].shape != (expected["entries"],) or data[key].dtype.kind not in "iu":
                raise ValueError(f"Malformed label column: {key}")
        counts, statuses = data["count"], data["status"]
        valid = statuses == CountStatus.VALID
        if (not np.isin(statuses, [int(s) for s in CountStatus]).all()
                or np.any(valid & (counts < 0)) or np.any(~valid & (counts != UNKNOWN))):
            raise ValueError("Invalid count/status relationship")
        # The builder certifies source content and within-file identities. Recheck
        # payload uniqueness so later copying/truncation cannot hide behind totals.
        identities = np.rec.fromarrays([data[k] for k in ("run", "luminosityBlock", "event")])
        if len(np.unique(identities)) != expected["entries"]:
            raise ValueError("Duplicate identities in sidecar payload")
        for name, column in (("counts", counts), ("statuses", statuses)):
            values, numbers = np.unique(column, return_counts=True)
            actual = {str(int(k)): int(numbers[i]) for i, k in enumerate(values)}
            if row[name] != actual:
                raise ValueError(f"Sidecar {name} summary differs from payload")
    if not row.get("pair_validation"):
        raise ValueError("Missing native/NanoAOD content certification")
    return row


def command(argv, log, *, timeout):
    with log.open("a") as output:
        output.write("COMMAND " + json.dumps([str(x) for x in argv]) + "\n")
        output.flush()
        subprocess.run([str(x) for x in argv], stdout=output, stderr=subprocess.STDOUT,
                       check=True, timeout=timeout)


def stage_eos(url, path, expected_bytes, expected_adler32, log):
    command(["xrdcp", "--nopbar", "--cksum", "adler32", url, path], log, timeout=600)
    checksum = 1
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            checksum = zlib.adler32(chunk, checksum)
    if path.stat().st_size != expected_bytes or f"{checksum:08x}" != expected_adler32.lower():
        raise ValueError("Staged EOS file differs from verified conversion catalog")
    return str(path)


def run_pair(campaign, record, config):
    parent = campaign / "pairs" / record["sample"]
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / record["id"]
    # Keep the lock inode stable across attempts and processes.
    with (parent / (record["id"] + ".lock")).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if destination.exists():
            return validate_pair(destination, record, config)
        started = time.monotonic()
        prior_attempts = len(list((campaign / "attempts").glob(record["id"] + ".*")))
        attempt = Path(tempfile.mkdtemp(prefix=record["id"] + ".", dir=campaign / "attempts"))
        log = attempt / "build.log"
        write_json(attempt / "source.json", record)
        try:
            with tempfile.TemporaryDirectory(
                    prefix="vcb_c1_", dir=os.environ.get("_CONDOR_SCRATCH_DIR", "/tmp")) as temp:
                scratch = Path(temp)
                nano, native = record["nano_file"], record["native_truth"]
                if record["native_kind"] == "remote MiniAOD":
                    redirectors = config["native_redirectors"]
                    native = redirectors[prior_attempts % len(redirectors)] + record["source_lfn"]
                if record["native_kind"] == "EOS complete GenTruth":
                    nano = stage_eos(nano, scratch / "nano.root", record["nano_bytes"],
                                     record["nano_adler32"], log)
                    native = stage_eos(native, scratch / "truth.root", record["native_bytes"],
                                       record["native_adler32"], log)
                elif not nano.startswith("root://"):
                    stat = Path(nano).stat()
                    if (stat.st_size, stat.st_mtime_ns) != (record["nano_bytes"], record["nano_mtime_ns"]):
                        raise ValueError("Local NanoAOD changed after inventory")
                command([sys.executable, campaign / "code/condor/scripts/build_truth_labels.py",
                         "--pair", nano, native, "--output-dir", attempt / "labels"], log,
                        timeout=config["pair_timeout_seconds"])
            labels = attempt / "labels"
            validate_pair(labels, record, config)
            manifest = json.loads((labels / "manifest.json").read_text())
            row = manifest["files"][0]
            actual_read_paths = {key: row[key] for key in ("nano_file", "native_truth")}
            row.update(nano_file=record["nano_file"], native_truth=record["native_truth"],
                       source_lfn=record["source_lfn"], sample=record["sample"],
                       dataset=record["dataset"], inventory_sha256=config["inventory_sha256"])
            write_json(labels / "manifest.json", manifest)
            write_json(labels / "completion.json", {
                "id": record["id"], "state": "complete", "completed_utc": now(),
                "wall_seconds": time.monotonic() - started, "host": socket.gethostname(),
                "attempt": str(attempt), "manifest_sha256": sha(labels / "manifest.json"),
                "inventory_sha256": config["inventory_sha256"],
                "actual_read_paths": actual_read_paths,
                "eos_catalog_checksums_checked": record["native_kind"] == "EOS complete GenTruth",
            })
            validate_pair(labels, record, config)
            labels.rename(destination)
            return row
        except Exception as error:
            write_json(attempt / "failure.json", {
                "id": record["id"], "failed_utc": now(), "error": repr(error),
                "traceback": traceback.format_exc(), "wall_seconds": time.monotonic() - started,
            })
            raise


def worker(campaign, batch):
    config = read_pinned(campaign)
    path = campaign / "batches" / (batch + ".json")
    if sha(path) != config["batch_sha256"][batch]:
        raise ValueError("Batch changed after preparation")
    records = json.loads(path.read_text())["files"]
    complete, failures = [], []
    for record in records:
        try:
            row = run_pair(campaign, record, config)
            complete.append({"id": record["id"], "entries": row["entries"]})
        except Exception as error:
            failures.append({"id": record["id"], "error": repr(error)})
            traceback.print_exc()
        write_json(campaign / "batch-status" / (batch + ".json"), {
            "batch": batch, "updated_utc": now(), "expected": len(records),
            "completed": complete, "failures": failures,
        })
    if failures:
        raise RuntimeError(f"{len(failures)} pairs failed; verified completed pairs will be reused")


def collect(campaign):
    config = read_pinned(campaign)
    inventory = json.loads((campaign / "inventory.json").read_text())
    failures, manifests, summary = [], {}, {}
    seen = set()
    for record in inventory["files"]:
        sample = record["sample"]
        entry = summary.setdefault(sample, {"expected_files": 0, "expected_events": 0,
            "verified_files": 0, "verified_events": 0, "counts": Counter(),
            "statuses": Counter(), "native_entries_reordered": 0})
        entry["expected_files"] += 1
        entry["expected_events"] += record["entries"]
        directory = campaign / "pairs" / sample / record["id"]
        try:
            row = validate_pair(directory, record, config)
            if row["nano_uuid"] in seen:
                raise ValueError("Duplicate source UUID across campaign outputs")
            seen.add(row["nano_uuid"])
            entry["verified_files"] += 1
            entry["verified_events"] += row["entries"]
            entry["counts"].update(row["counts"])
            entry["statuses"].update(row["statuses"])
            entry["native_entries_reordered"] += row["native_entries_reordered"]
            relative = (directory / row["labels"]).relative_to(campaign)
            manifests.setdefault(sample, []).append({**row, "labels": str(relative)})
        except Exception as error:
            failures.append({"id": record["id"], "error": repr(error)})
    report = {"state": "complete" if not failures else "incomplete", "checked_utc": now(),
              "inventory_sha256": config["inventory_sha256"], "summary": summary,
              "failed_or_missing_pairs": failures, "b0_skims_started": False}
    write_json(campaign / "truth-status.json", report)
    if failures:
        raise RuntimeError(f"Truth coverage incomplete: {len(failures)} unverified pairs")
    common = {"schema_version": TRUTH_LABEL_VERSION,
              "source": "Pythia8 MiniAOD prunedGenParticles; all b quarks retained",
              "producer_sha256": config["code_sha256"]["condor/scripts/build_truth_labels.py"],
              "definition_sha256": config["code_sha256"]["src/vcb/truth.py"],
              "inventory_sha256": config["inventory_sha256"]}
    for sample, rows in manifests.items():
        target = campaign / (sample + "-truth-manifest.json")
        contents = json.dumps({**common, "files": rows}, indent=2) + "\n"
        if target.exists() and target.read_text() != contents:
            raise ValueError(f"Refusing to replace a different published manifest: {target}")
        if not target.exists():
            target.write_text(contents)
    report["manifests"] = {sample: {"path": str(campaign / (sample + "-truth-manifest.json")),
        "sha256": sha(campaign / (sample + "-truth-manifest.json"))} for sample in manifests}
    write_json(campaign / "completion.json", report)
    print(json.dumps(report, indent=2))


def prepare(campaign, args):
    if (campaign / "campaign.json").exists():
        raise FileExistsError("Campaign already prepared; use its pinned worker or a new directory")
    inventory = json.loads((campaign / "inventory.json").read_text())
    if len(inventory["files"]) == 0:
        raise ValueError("Empty input inventory")
    for field in ("id", "nano_uuid", "source_lfn"):
        if len({r[field] for r in inventory["files"]}) != len(inventory["files"]):
            raise ValueError(f"Duplicate inventory {field}")
    if min(args.files_per_job, args.max_jobs, args.pair_timeout) <= 0:
        raise ValueError("Job limits must be positive")
    for name in ("attempts", "batches", "batch-status", "logs", "pairs"):
        (campaign / name).mkdir(exist_ok=True)
    for relative in CODE_FILES:
        target = campaign / "code" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, target)
    wrapper = campaign / "code/condor/scripts/c1_truth_worker.sh"
    wrapper.chmod(0o755)
    config = {"schema_version": 1, "prepared_utc": now(),
              "scope": "C1 tasks 1 and 2 only; no skims or training",
              "inventory_sha256": sha(campaign / "inventory.json"),
              "code_sha256": {r: sha(campaign / "code" / r) for r in CODE_FILES},
              "cmssw": str(args.cmssw.resolve()), "proxy": str(args.proxy.resolve()),
              "files_per_job": args.files_per_job, "max_jobs": args.max_jobs,
              "pair_timeout_seconds": args.pair_timeout, "batch_sha256": {}}
    config["native_redirectors"] = list(NATIVE_REDIRECTORS)
    # Gate the campaign on one real worker job per source. Each remaining job
    # handles up to five pairs; the first three jobs are also production outputs.
    groups = {}
    for sample in sorted({r["sample"] for r in inventory["files"]}):
        rows = [r for r in inventory["files"] if r["sample"] == sample]
        groups[sample] = [rows[:1]] + [rows[i:i+args.files_per_job]
                                      for i in range(1, len(rows), args.files_per_job)]
    pilots = [sample + "_0000" for sample in groups]
    config["pilot_batches"] = pilots
    dag = []
    for index in range(max(len(g) for g in groups.values())):
        for sample, batches in groups.items():
            if index >= len(batches):
                continue
            batch = f"{sample}_{index:04d}"
            path = campaign / "batches" / (batch + ".json")
            write_json(path, {"batch": batch, "files": batches[index]})
            config["batch_sha256"][batch] = sha(path)
            dag.extend([f"JOB {batch} {campaign}/worker.sub",
                        f'VARS {batch} batch="{batch}"', f"RETRY {batch} 2"])
            if batch not in pilots:
                dag.append("PARENT " + " ".join(pilots) + " CHILD " + batch)
    write_json(campaign / "campaign.json", config)
    common = f'''universe = vanilla
getenv = false
should_transfer_files = NO
use_x509userproxy = true
x509userproxy = {args.proxy.resolve()}
request_cpus = 1
request_memory = 4G
request_disk = 4G
notification = never
+JobBatchName = "VCB_C1_TRUTH_20261028"
+VCBC1Truth = true
executable = {wrapper}
initialdir = {campaign}
log = {campaign}/logs/$(Cluster).log
'''
    (campaign / "worker.sub").write_text(common + f'''arguments = {campaign} worker $(batch)
output = {campaign}/logs/$(batch).$(Cluster).out
error = {campaign}/logs/$(batch).$(Cluster).err
queue 1
''')
    (campaign / "finalize.sub").write_text(common + f'''arguments = {campaign} collect
output = {campaign}/logs/finalize.$(Cluster).out
error = {campaign}/logs/finalize.$(Cluster).err
queue 1
''')
    # A final node also writes an explicit incomplete report after exhausted
    # worker retries. It publishes usable manifests only at complete coverage.
    dag.append(f"FINAL certify {campaign}/finalize.sub")
    (campaign / "production.dag").write_text("\n".join(dag) + "\n")
    print(json.dumps({"campaign": str(campaign), "jobs": len(config["batch_sha256"]),
                      "max_jobs": args.max_jobs, "state": "prepared, not submitted"}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "worker", "collect"))
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--batch")
    parser.add_argument("--cmssw", type=Path)
    parser.add_argument("--proxy", type=Path)
    parser.add_argument("--files-per-job", type=int, default=5)
    parser.add_argument("--max-jobs", type=int, default=40)
    parser.add_argument("--pair-timeout", type=int, default=7200)
    args = parser.parse_args()
    campaign = args.campaign.resolve()
    if args.command == "prepare":
        if args.cmssw is None or args.proxy is None:
            parser.error("prepare requires --cmssw and --proxy")
        prepare(campaign, args)
    elif args.command == "worker":
        if args.batch is None:
            parser.error("worker requires --batch")
        worker(campaign, args.batch)
    else:
        collect(campaign)


if __name__ == "__main__":
    main()
