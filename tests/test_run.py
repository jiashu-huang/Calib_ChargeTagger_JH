"""
Run Calib_ChargeTagger_JH on a single .root file and produce:
  1. tests/outfile/test-output.root          — skimmed ROOT output (git-ignored)
  2. tests/outfile/test-output-0th-event.txt — 0th event dump      (committed baseline)
  3. tests/outfile/test-output-schema.csv    — variable name + type (committed baseline)
  4. tests/outfile/test-output_jet_pt.pdf    — unweighted AK4 jet pT plot (git-ignored)

Usage:
    micromamba run -n ttbar python tests/test_run.py [path-to-input.root] [--year YEAR]

Defaults: input = tests/data/test-input.root, year = 2024.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import uproot

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTFILE_DIR = PROJECT_ROOT / "tests" / "outfile"
DEFAULT_INPUT = PROJECT_ROOT / "tests" / "data" / "test-input.root"
DEFAULT_YEAR = "2024"

# numpy dtype -> ROOT typedef
DTYPE_TO_ROOT = {
    "float64": "Double_t",
    "float32": "Float_t",
    "int32": "Int_t",
    "int64": "Long64_t",
    "uint32": "UInt_t",
    "uint64": "ULong64_t",
    "uint8": "UChar_t",
    "bool": "Bool_t",
    "int8": "Char_t",
    "int16": "Short_t",
    "uint16": "UShort_t",
}


FILETAG = "test-output"


def run_skimmer(input_file: Path, year: str) -> None:
    """Step 1: run the vcb skimmer with the prescribed parameters."""
    cmd = [
        sys.executable,
        "-m",
        "vcb.run",
        "--processor",
        "skimmer",
        "--skimmer",
        "vcbSkimmer",
        "--year",
        year,
        "--files",
        str(input_file),
        "--save-root",
        "--chunksize",
        "100000",
        "--maxchunks",
        "0",
        "--naming-tag",
        FILETAG,
        "--outdir",
        str(PROJECT_ROOT),
    ]

    print(f"Running skimmer:\n  {' '.join(cmd)}\n")
    subprocess.run(cmd, check=True, cwd=str(PROJECT_ROOT))

    # Collect output ROOT batches (written to PROJECT_ROOT by run_utils)
    root_files = sorted(PROJECT_ROOT.glob(f"nano_skim_{FILETAG}_batch_*.root"))
    if not root_files:
        sys.exit("ERROR: no output ROOT files found in " + str(PROJECT_ROOT))

    final_root = OUTFILE_DIR / "test-output.root"

    if len(root_files) == 1:
        shutil.move(str(root_files[0]), str(final_root))
    else:
        # Multiple batches — concatenate with awkward/uproot
        import awkward as ak

        all_arrays = []
        for rf in root_files:
            with uproot.open(rf) as f:
                all_arrays.append(f["Events"].arrays())
        merged = ak.concatenate(all_arrays)
        with uproot.recreate(str(final_root), compression=uproot.LZ4(4)) as f:
            f["Events"] = merged
        for rf in root_files:
            rf.unlink()

    # Clean up intermediate files left in PROJECT_ROOT
    for pattern in [
        f"out_{FILETAG}_batch_*.parquet",
        f"num_batches_{FILETAG}.txt",
    ]:
        for p in PROJECT_ROOT.glob(pattern):
            p.unlink()
    pkl = PROJECT_ROOT / "outfiles" / f"{FILETAG}.pkl"
    if pkl.exists():
        pkl.unlink()

    print(f"Output ROOT file: {final_root}")


def dump_0th_event() -> None:
    """Step 2: read test-output.root and dump the 0th event to a text file."""
    root_path = OUTFILE_DIR / "test-output.root"
    txt_path = OUTFILE_DIR / "test-output-0th-event.txt"

    with uproot.open(str(root_path)) as f:
        tree = f["Events"]
        arrays = tree.arrays(library="np", entry_start=0, entry_stop=1)

    lines = ["Tree: Events", "Entry: 0"]
    for name in sorted(arrays.keys()):
        val = arrays[name][0]
        dtype_str = str(np.asarray(val).dtype)
        root_type = DTYPE_TO_ROOT.get(dtype_str, dtype_str)
        lines.append(f"{name} ({root_type}) = {val}")

    txt_path.write_text("\n".join(lines) + "\n")
    print(f"0th event dumped to: {txt_path}")


def make_schema_csv() -> None:
    """Step 3: parse the text dump and produce a two-column CSV (name, type)."""
    txt_path = OUTFILE_DIR / "test-output-0th-event.txt"
    csv_path = OUTFILE_DIR / "test-output-schema.csv"

    pattern = re.compile(r"^(\S+)\s+\((\S+)\)\s+=")

    with txt_path.open() as fin, csv_path.open("w", newline="") as fout:
        writer = csv.writer(fout)
        writer.writerow(["variable_name", "variable_type"])
        for line in fin:
            m = pattern.match(line)
            if m:
                writer.writerow([m.group(1), m.group(2)])

    print(f"Schema CSV: {csv_path}")


def make_jet_pt_plot() -> None:
    """Step 4: plot all saved AK4 jet pT values without event weights."""
    sys.path.insert(0, str(PROJECT_ROOT / "diagnostics"))
    from plot_jet_pt import plot_jet_pt

    root_path = OUTFILE_DIR / "test-output.root"
    pdf_path = OUTFILE_DIR / "test-output_jet_pt.pdf"

    result = plot_jet_pt(root_path, pdf_path)
    print(f"Unweighted AK4 jet pT plot: {result['output_pdf']}")
    print(f"  Jets used: {result['n_jets']}")
    print(f"  Minimum jet pT: {result['min_pt']:.3f} GeV")
    print(f"  Maximum jet pT: {result['max_pt']:.3f} GeV")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input_file",
        nargs="?",
        default=str(DEFAULT_INPUT),
        help=f"Input NanoAOD ROOT file (default: {DEFAULT_INPUT})",
    )
    parser.add_argument("--year", default=DEFAULT_YEAR, help="Data-taking year")
    args = parser.parse_args()

    input_file = Path(args.input_file).resolve()
    if not input_file.exists():
        sys.exit(
            f"Input file not found: {input_file}\n"
            "Copy the fixture first, e.g.:\n"
            "  cp /isilon/export/home/jhuan166/Vcb/Calib_ChargeTagger/tests/data/test-input.root "
            "tests/data/"
        )

    OUTFILE_DIR.mkdir(parents=True, exist_ok=True)

    run_skimmer(input_file, args.year)
    dump_0th_event()
    make_schema_csv()
    make_jet_pt_plot()

    print("\nDone. Files in tests/outfile/:")
    for p in sorted(OUTFILE_DIR.iterdir()):
        if p.name.startswith("test-output"):
            print(f"  {p.name}")


if __name__ == "__main__":
    main()
