#!/usr/bin/env python3
"""Generate Condor jobs for local batch_* input directories."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

BATCH_RE = re.compile(r"^batch_(\d+)$")
THIS_FILE = Path(os.path.abspath(__file__))
CONDOR_DIR = THIS_FILE.parent
REPO_ROOT = CONDOR_DIR.parent
TEMPLATE_DIR = CONDOR_DIR / "templates"
EXEC_TEMPLATE = TEMPLATE_DIR / "calib_batch_exec.sh"
JOB_TEMPLATE = TEMPLATE_DIR / "calib_batch.job"


def make_abs(path: str | Path) -> Path:
    """Return an absolute path without resolving symlinks."""
    return Path(os.path.abspath(os.path.expandvars(os.path.expanduser(str(path)))))


def git_provenance(repo: Path) -> dict[str, object]:
    """
    Which code this campaign ran, as `{commit, branch, dirty, dirty_files}`.

    Worth recording because the workers do **not** get a copy of the repo: the
    generated script puts `$CALIB_REPO/src` on `PYTHONPATH` and imports from the
    live checkout. Nothing else in the campaign says what that checkout
    contained, so without this a finished skim cannot be tied back to a version
    of the skimmer.

    `dirty` is the field that actually matters. A commit hash recorded against a
    modified working tree is worse than no hash at all -- it names code that is
    not what ran. And because jobs start over a span of hours while importing
    from that same live tree, an edit made mid-queue splits the campaign across
    two versions with nothing to mark the boundary; `dirty: true` is the only
    warning the output will ever carry.

    Any git failure (not a repo, git missing) degrades to `available: false`
    rather than blocking submission -- provenance is worth recording, not worth
    refusing to run over.
    """

    def run(*cmd: str) -> str | None:
        try:
            out = subprocess.run(
                ["git", "-C", str(repo), *cmd],
                capture_output=True,
                text=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
        return out.stdout.strip()

    commit = run("rev-parse", "HEAD")
    if commit is None:
        return {"available": False}

    # `--porcelain` lines are "XY path", but `run` has already stripped the
    # output, which removes the leading space of the *first* line only. Splitting
    # on whitespace is immune to that, where a fixed `line[3:]` slice is not (it
    # ate the R of README.md). maxsplit=1 keeps rename arrows and git's own
    # quoting of paths-with-spaces intact.
    status = run("status", "--porcelain") or ""
    dirty_files = []
    for line in status.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2:
            dirty_files.append(parts[1])
    return {
        "available": True,
        "commit": commit,
        "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(dirty_files),
        "dirty_files": dirty_files,
    }


def render_template(template_path: Path, replacements: dict[str, str]) -> str:
    """Replace @@KEY@@ tokens in a template file."""
    text = template_path.read_text()
    for key, value in replacements.items():
        text = text.replace(f"@@{key}@@", str(value))

    leftovers = sorted(set(re.findall(r"@@[A-Z0-9_]+@@", text)))
    if leftovers:
        raise ValueError(f"Unreplaced placeholders in {template_path}: {leftovers}")

    return text


def batch_number(batch_name: str) -> int:
    """Extract the numeric suffix from a batch directory name."""
    match = BATCH_RE.fullmatch(batch_name)
    if match is None:
        raise ValueError(f"Invalid batch directory name: {batch_name}")
    return int(match.group(1))


def discover_batches(input_root: Path) -> list[Path]:
    """Return batch_* directories sorted by numeric suffix."""
    batches = [
        path for path in input_root.iterdir() if path.is_dir() and BATCH_RE.fullmatch(path.name)
    ]
    return sorted(batches, key=lambda path: batch_number(path.name))


def select_batches(all_batches: list[Path], args: argparse.Namespace) -> list[Path]:
    """Apply CLI filters to the discovered batch directories."""
    selected = list(all_batches)

    if args.batch_names:
        wanted = set(args.batch_names)
        selected = [path for path in selected if path.name in wanted]
        found = {path.name for path in selected}
        missing = sorted(wanted - found)
        if missing:
            raise ValueError(f"Requested batch directories not found: {missing}")

    if args.batch_start is not None:
        selected = [path for path in selected if batch_number(path.name) >= args.batch_start]

    if args.batch_end is not None:
        selected = [path for path in selected if batch_number(path.name) <= args.batch_end]

    if args.max_batches is not None:
        selected = selected[: args.max_batches]

    if args.test:
        selected = selected[:2]

    if not selected:
        raise ValueError("No batch directories selected.")

    return selected


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Generate one Condor job per batch_* directory.",
    )
    parser.add_argument(
        "--input-root",
        required=True,
        type=Path,
        help="Directory containing batch_000, batch_001, ... with input ROOT files.",
    )
    parser.add_argument(
        "--tag",
        default=datetime.now().strftime("%Y%m%d_%H%M%S"),
        help="Campaign tag used for condor/runs/<tag> and processed outputs.",
    )
    parser.add_argument(
        "--calib-repo",
        type=Path,
        default=REPO_ROOT,
        help="Path to the Calib_ChargeTagger_JH checkout visible to Condor workers.",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Directory for generated JDLs, input lists, and worker scripts.",
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=None,
        help="Directory for final batch ROOT and pickle outputs.",
    )
    parser.add_argument(
        "--submitter-home",
        type=Path,
        default=Path.home(),
        help="Home directory used when probing worker-side micromamba locations.",
    )
    parser.add_argument(
        "--micromamba-bin",
        default="",
        help="Explicit worker-side micromamba binary path.",
    )
    parser.add_argument(
        "--mamba-env",
        default="ttbar",
        help="Micromamba environment name used on Condor workers.",
    )
    parser.add_argument("--year", default="2024", help="Year passed to vcb.run.")
    parser.add_argument(
        "--files-name",
        required=True,
        help=(
            "Dataset name passed through to `vcb.run --files-name`. Required, and with "
            "no default on purpose: it selects the cross section, the gen selection and "
            "the top-pT columns, so the wrong label rescales a whole campaign silently. "
            "e.g. TTtoLNuCB, TTtoLNu2Q."
        ),
    )
    parser.add_argument("--skimmer", default="vcbSkimmer", help="Skimmer module to run.")
    parser.add_argument(
        "--chunksize",
        type=int,
        default=1_000_000,
        help="Chunk size passed through to vcb.run.",
    )
    parser.add_argument(
        "--maxchunks",
        type=int,
        default=0,
        help="Max chunks passed through to vcb.run. 0 means no limit.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=9999,
        help="run.py batch size; keep this large so one Condor job yields one ROOT file.",
    )
    # Defaults sized from a measured 5-file batch (208,780 events, 2026-07-26):
    # 104% of one core, 1.29 GB peak RSS, 129 MB of transient files, ~60 s wall.
    parser.add_argument(
        "--request-cpus",
        type=int,
        default=2,
        help="Condor CPU request. The skim is single-threaded (measured 104%% of "
        "one core); 2 is headroom for the uproot/ROOT I/O threads.",
    )
    parser.add_argument(
        "--request-memory",
        default="4G",
        help="Condor memory request. Measured peak RSS 1.29 GB on a 5-file batch; "
        "the peak is the end-of-job concatenation, so it scales with selected events.",
    )
    parser.add_argument(
        "--request-disk",
        default="2G",
        help="Condor disk request. Nearly irrelevant here (measured 5 KB of condor "
        "scratch) because the job writes to the shared filesystem, not the sandbox.",
    )
    parser.add_argument(
        "--keep-intermediate",
        action="store_true",
        help="Keep per-job parquet and helper files in the worker work directory.",
    )
    parser.add_argument(
        "--save-systematics",
        action="store_true",
        help=(
            "Pass --save-systematics to vcb.run, adding 18 weight_*Up/Down columns "
            "(pileup, ISR/FSR parton shower, and the six lepton SFs) plus their np_* "
            "denominators in the totals pickle. Strongly recommended: the raw PSWeight "
            "array is NOT written to the skim, so ISR/FSR variations cannot be rebuilt "
            "afterwards and recovering them costs a second full production. Pileup and "
            "lepton SFs are re-derivable from nTrueInt / TriggerLeptonPt+Eta, and the "
            "mu_R/mu_F scale weights are written either way."
        ),
    )
    parser.add_argument(
        "--batch-names",
        nargs="*",
        default=None,
        help="Explicit batch directory names, e.g. batch_000 batch_001.",
    )
    parser.add_argument(
        "--batch-start",
        type=int,
        default=None,
        help="Inclusive numeric lower bound on selected batch indices.",
    )
    parser.add_argument(
        "--batch-end",
        type=int,
        default=None,
        help="Inclusive numeric upper bound on selected batch indices.",
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=None,
        help="Take only the first N selected batches after filtering.",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Generate only the first two selected batches.",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Submit each generated job with condor_submit.",
    )
    return parser.parse_args()


def main() -> None:
    """Generate the Condor campaign."""
    args = parse_args()

    if (
        args.batch_start is not None
        and args.batch_end is not None
        and args.batch_start > args.batch_end
    ):
        raise ValueError("--batch-start cannot be larger than --batch-end.")
    if args.chunksize <= 0:
        raise ValueError("--chunksize must be positive.")
    if args.batch_size <= 0:
        raise ValueError("--batch-size must be positive.")
    if args.request_cpus <= 0:
        raise ValueError("--request-cpus must be positive.")

    input_root = make_abs(args.input_root)
    calib_repo = make_abs(args.calib_repo)
    submitter_home = make_abs(args.submitter_home)

    run_dir = make_abs(args.run_dir) if args.run_dir else make_abs(CONDOR_DIR / "runs" / args.tag)
    processed_dir = (
        make_abs(args.processed_dir)
        if args.processed_dir
        else make_abs(input_root / "processed-nano" / args.tag)
    )
    roots_dir = processed_dir / "roots"
    pickles_dir = processed_dir / "pickles"
    metadata_dir = processed_dir / "metadata"

    if not input_root.is_dir():
        raise FileNotFoundError(f"Input root directory not found: {input_root}")
    if not calib_repo.is_dir():
        raise FileNotFoundError(f"Calib_ChargeTagger_JH checkout not found: {calib_repo}")
    if not (calib_repo / "src" / "vcb" / "run.py").is_file():
        raise FileNotFoundError(
            f"run.py not found under repo: {calib_repo / 'src' / 'vcb' / 'run.py'}"
        )

    if run_dir.exists():
        raise FileExistsError(f"Run directory already exists: {run_dir}")
    if processed_dir.exists():
        raise FileExistsError(f"Processed output directory already exists: {processed_dir}")

    all_batches = discover_batches(input_root)
    selected_batches = select_batches(all_batches, args)

    run_dir.mkdir(parents=True, exist_ok=False)
    roots_dir.mkdir(parents=True, exist_ok=False)
    pickles_dir.mkdir(parents=True, exist_ok=False)
    metadata_dir.mkdir(parents=True, exist_ok=False)

    submit_commands: list[str] = []
    batch_summaries: list[dict[str, object]] = []

    for batch_dir in selected_batches:
        input_files = sorted(path for path in batch_dir.glob("*.root") if path.is_file())
        if not input_files:
            raise FileNotFoundError(f"No ROOT files found in {batch_dir}")

        job_dir = run_dir / batch_dir.name
        work_dir = job_dir / "work"
        job_dir.mkdir(parents=True, exist_ok=False)

        input_list_path = job_dir / "input_list.txt"
        input_list_path.write_text("\n".join(str(path) for path in input_files) + "\n")

        exec_path = job_dir / "run_batch.sh"
        job_path = job_dir / "calib_batch.job"

        exec_contents = render_template(
            EXEC_TEMPLATE,
            {
                "CALIB_REPO": str(calib_repo),
                "SUBMITTER_HOME": str(submitter_home),
                "MICROMAMBA_BIN_HINT": args.micromamba_bin,
                "BATCH_ID": batch_dir.name,
                "INPUT_LIST": str(input_list_path),
                "OUTPUT_ROOTS_DIR": str(roots_dir),
                "OUTPUT_PICKLES_DIR": str(pickles_dir),
                "WORK_DIR": str(work_dir),
                "YEAR": args.year,
                "FILES_NAME": args.files_name,
                "SKIMMER": args.skimmer,
                "CHUNKSIZE": str(args.chunksize),
                "MAXCHUNKS": str(args.maxchunks),
                "BATCH_SIZE": str(args.batch_size),
                "MAMBA_ENV": args.mamba_env,
                "KEEP_INTERMEDIATE": "1" if args.keep_intermediate else "0",
                # Spelled out either way -- `vcb.run` takes both spellings
                # (boostedhh.utils.add_bool_arg), so the worker script records the
                # choice instead of leaving it to the default.
                "SAVE_SYSTEMATICS_FLAG": (
                    "--save-systematics" if args.save_systematics else "--no-save-systematics"
                ),
            },
        )
        exec_path.write_text(exec_contents)
        exec_path.chmod(0o755)

        job_contents = render_template(
            JOB_TEMPLATE,
            {
                "EXECUTABLE": str(exec_path),
                "INITIALDIR": str(job_dir),
                "LOG": str(job_dir / "$(Cluster).$(Process).log"),
                "STDOUT": str(job_dir / "$(Cluster).$(Process).out"),
                "STDERR": str(job_dir / "$(Cluster).$(Process).err"),
                "REQUEST_CPUS": str(args.request_cpus),
                "REQUEST_MEMORY": args.request_memory,
                "REQUEST_DISK": args.request_disk,
            },
        )
        job_path.write_text(job_contents)

        submit_commands.append(f'condor_submit "{job_path}"')
        batch_summaries.append(
            {
                "batch": batch_dir.name,
                "n_input_files": len(input_files),
                "job_dir": str(job_dir),
                "job_file": str(job_path),
                "worker_script": str(exec_path),
            }
        )

    submit_all_path = run_dir / "submit_all.sh"
    submit_all_lines = ["#!/bin/bash", "set -euo pipefail", ""]
    submit_all_lines.extend(submit_commands)
    submit_all_lines.append("")
    submit_all_path.write_text("\n".join(submit_all_lines))
    submit_all_path.chmod(0o755)

    provenance = git_provenance(calib_repo)

    campaign_config = {
        "tag": args.tag,
        "submitted_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "calib_repo_git": provenance,
        "input_root": str(input_root),
        "calib_repo": str(calib_repo),
        "run_dir": str(run_dir),
        "processed_dir": str(processed_dir),
        "roots_dir": str(roots_dir),
        "pickles_dir": str(pickles_dir),
        "metadata_dir": str(metadata_dir),
        "submitter_home": str(submitter_home),
        "micromamba_bin_hint": args.micromamba_bin,
        "mamba_env": args.mamba_env,
        "year": args.year,
        "files_name": args.files_name,
        "skimmer": args.skimmer,
        "chunksize": args.chunksize,
        "maxchunks": args.maxchunks,
        "batch_size": args.batch_size,
        "request_cpus": args.request_cpus,
        "request_memory": args.request_memory,
        "request_disk": args.request_disk,
        "keep_intermediate": args.keep_intermediate,
        "save_systematics": args.save_systematics,
        "selected_batches": [summary["batch"] for summary in batch_summaries],
        "jobs": batch_summaries,
    }
    (run_dir / "campaign.json").write_text(json.dumps(campaign_config, indent=2) + "\n")

    if args.submit:
        for summary in batch_summaries:
            subprocess.run(["condor_submit", str(summary["job_file"])], check=True)

    print(f"Generated {len(batch_summaries)} Condor job(s).")
    print(f"Run directory: {run_dir}")
    print(f"Processed outputs: {processed_dir}")
    print(f"Submit helper: {submit_all_path}")
    print(f"Systematics: {'ON' if args.save_systematics else 'OFF'}")

    # Both warnings below are printed, not enforced: there are legitimate reasons
    # to run either way, and a submitter that refuses is a submitter people work
    # around. They are loud because both are silent in the output otherwise.
    if not args.save_systematics:
        print(
            "  WARNING: no weight_*Up/Down columns. ISR/FSR cannot be recovered from the\n"
            "           skim afterwards (raw PSWeight is not saved) -- getting them later\n"
            "           means re-running this whole campaign. Pass --save-systematics."
        )

    if provenance.get("available"):
        print(f"Code: {provenance['commit'][:12]} on {provenance['branch']}")
        if provenance["dirty"]:
            n = len(provenance["dirty_files"])
            print(
                f"  WARNING: {n} uncommitted file(s) -- the recorded commit is NOT what will\n"
                "           run. Workers import from the live tree, so editing it while jobs\n"
                "           are queued splits the campaign across code versions. Commit first."
            )
    else:
        print("Code: git provenance unavailable (not a git repo?)")

    if not args.submit:
        print("Jobs were not submitted. Use submit_all.sh or rerun with --submit.")


if __name__ == "__main__":
    main()
