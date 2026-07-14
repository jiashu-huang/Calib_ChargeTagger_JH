#!/usr/bin/env python3
"""Merge processed batch ROOT files with hadd."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


def make_abs(path: str | Path) -> Path:
    """Return an absolute path without resolving symlinks."""
    return Path(os.path.abspath(os.path.expandvars(os.path.expanduser(str(path)))))


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Merge per-batch ROOT files under processed-nano/<tag>/roots.",
    )
    parser.add_argument(
        "--processed-dir",
        required=True,
        type=Path,
        help="Processed output directory containing roots/.",
    )
    parser.add_argument(
        "--root-glob",
        default="batch_*.root",
        help="Glob used inside roots/ to select input ROOT files.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Merged ROOT output path. Defaults to <processed-dir>/merged/total.root.",
    )
    parser.add_argument(
        "--hadd-bin",
        default="hadd",
        help="hadd executable to use. Activate CMSSW first if needed.",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=None,
        help="Optional hadd -j value.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing output ROOT file.",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = parse_args()
    processed_dir = make_abs(args.processed_dir)
    roots_dir = processed_dir / "roots"
    output_root = (
        make_abs(args.output_root)
        if args.output_root is not None
        else make_abs(processed_dir / "merged" / "total.root")
    )

    if not roots_dir.is_dir():
        raise FileNotFoundError(f"ROOT directory not found: {roots_dir}")

    input_roots = sorted(path for path in roots_dir.glob(args.root_glob) if path.is_file())
    if not input_roots:
        raise FileNotFoundError(f"No ROOT files found in {roots_dir} with glob {args.root_glob}")

    if output_root.exists() and not args.force:
        raise FileExistsError(f"Output ROOT already exists: {output_root}")

    hadd_bin = shutil.which(args.hadd_bin) if os.path.sep not in args.hadd_bin else args.hadd_bin
    if hadd_bin is None or not Path(hadd_bin).exists():
        raise FileNotFoundError(
            f"hadd executable not found: {args.hadd_bin}. Activate CMSSW or pass --hadd-bin."
        )

    output_root.parent.mkdir(parents=True, exist_ok=True)

    command = [str(hadd_bin), "-f"]
    if args.jobs is not None:
        if args.jobs <= 0:
            raise ValueError("--jobs must be positive when provided.")
        command.extend(["-j", str(args.jobs)])
    command.append(str(output_root))
    command.extend(str(path) for path in input_roots)

    subprocess.run(command, check=True)

    print(f"Merged {len(input_roots)} ROOT file(s) into {output_root}")


if __name__ == "__main__":
    main()
