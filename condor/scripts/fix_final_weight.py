#!/usr/bin/env python3
"""Recompute finalWeight using the global np_nominal across all batch pickles."""

from __future__ import annotations

import argparse
import json
import os
import pickle
from pathlib import Path

import numpy as np
import uproot


def make_abs(path: str | Path) -> Path:
    """Return an absolute path without resolving symlinks."""
    return Path(os.path.abspath(os.path.expandvars(os.path.expanduser(str(path)))))


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Rewrite per-batch ROOT outputs with a globally normalized finalWeight branch.",
    )
    parser.add_argument(
        "--processed-dir",
        required=True,
        type=Path,
        help="Processed output directory containing roots/, pickles/, and metadata/.",
    )
    parser.add_argument("--year", default="2022", help="Year key expected inside each pickle.")
    parser.add_argument(
        "--dataset",
        default=None,
        help="Dataset key expected inside each pickle. Defaults to inferring a single dataset.",
    )
    parser.add_argument(
        "--pickle-glob",
        default="*.pkl",
        help="Glob used inside pickles/ to find batch pickle files.",
    )
    parser.add_argument(
        "--root-glob",
        default="*.root",
        help="Glob used inside roots/ to find batch ROOT files.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing finalWeight branch if present.",
    )
    return parser.parse_args()


def load_global_norm(
    pickle_paths: list[Path], year: str, dataset: str | None
) -> tuple[str, float, float]:
    """Sum np_nominal and nevents across all batch pickle files."""
    resolved_dataset = dataset
    total_np_nominal = 0.0
    total_nevents = 0.0

    for pickle_path in pickle_paths:
        with pickle_path.open("rb") as handle:
            payload = pickle.load(handle)

        if year not in payload:
            raise KeyError(f"Year {year} not found in {pickle_path}")

        year_block = payload[year]
        if resolved_dataset is None:
            if len(year_block) != 1:
                raise ValueError(
                    f"Expected exactly one dataset in {pickle_path}, found {list(year_block.keys())}"
                )
            resolved_dataset = next(iter(year_block))

        if resolved_dataset not in year_block:
            raise KeyError(
                f"Dataset {resolved_dataset} not found in {pickle_path}. "
                f"Available: {list(year_block.keys())}"
            )

        totals = year_block[resolved_dataset].get("totals", {})
        if "np_nominal" not in totals:
            raise KeyError(f"totals['np_nominal'] missing in {pickle_path}")

        total_np_nominal += float(totals["np_nominal"])
        total_nevents += float(totals.get("nevents", 0.0))

    if resolved_dataset is None:
        raise ValueError("No dataset could be inferred from the batch pickles.")

    if total_np_nominal == 0.0:
        raise ValueError("Global np_nominal is 0. Cannot compute finalWeight.")

    return resolved_dataset, total_np_nominal, total_nevents


def rewrite_root(root_path: Path, global_np_nominal: float, force: bool) -> bool:
    """Rewrite one ROOT file with finalWeight = weight / global_np_nominal."""
    with uproot.open(root_path) as handle:
        arrays = handle["Events"].arrays(library="np")

    if "weight" not in arrays:
        raise KeyError(f"'weight' branch missing in {root_path}")

    if "finalWeight" in arrays and not force:
        return False

    arrays["finalWeight"] = np.asarray(arrays["weight"], dtype=np.float64) / global_np_nominal

    temp_path = root_path.with_suffix(".tmp.root")
    if temp_path.exists():
        temp_path.unlink()

    with uproot.recreate(temp_path, compression=uproot.LZ4(4)) as handle:
        handle["Events"] = arrays

    temp_path.replace(root_path)
    return True


def main() -> None:
    """Entry point."""
    args = parse_args()
    processed_dir = make_abs(args.processed_dir)
    pickles_dir = processed_dir / "pickles"
    roots_dir = processed_dir / "roots"
    metadata_dir = processed_dir / "metadata"

    if not pickles_dir.is_dir():
        raise FileNotFoundError(f"Pickle directory not found: {pickles_dir}")
    if not roots_dir.is_dir():
        raise FileNotFoundError(f"ROOT directory not found: {roots_dir}")

    pickle_paths = sorted(path for path in pickles_dir.glob(args.pickle_glob) if path.is_file())
    root_paths = sorted(path for path in roots_dir.glob(args.root_glob) if path.is_file())

    if not pickle_paths:
        raise FileNotFoundError(f"No pickles found in {pickles_dir} with glob {args.pickle_glob}")
    if not root_paths:
        raise FileNotFoundError(f"No ROOT files found in {roots_dir} with glob {args.root_glob}")

    dataset, global_np_nominal, total_nevents = load_global_norm(
        pickle_paths, args.year, args.dataset
    )

    updated = 0
    skipped = 0
    for root_path in root_paths:
        if rewrite_root(root_path, global_np_nominal, args.force):
            updated += 1
        else:
            skipped += 1

    metadata_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "year": args.year,
        "dataset": dataset,
        "global_np_nominal": global_np_nominal,
        "total_nevents": total_nevents,
        "num_pickles": len(pickle_paths),
        "num_roots": len(root_paths),
        "roots_updated": updated,
        "roots_skipped": skipped,
    }
    summary_path = metadata_dir / "global_final_weight.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")

    print(
        f"Computed global np_nominal={global_np_nominal} from {len(pickle_paths)} pickle file(s)."
    )
    print(f"Updated {updated} ROOT file(s); skipped {skipped}.")
    print(f"Summary written to: {summary_path}")


if __name__ == "__main__":
    main()
