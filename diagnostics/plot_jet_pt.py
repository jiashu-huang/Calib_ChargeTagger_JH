from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-calib_chargetagger")

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import mplhep as hep
import numpy as np
import uproot

PT_RANGE = (0.0, 200.0)
BIN_WIDTH_GEV = 1.0
DEFAULT_TREE = "Events"
PAD_VAL = -99999.0
JET_PT_PATTERN = re.compile(r"^ak4JetPt(\d+)$")


def _sorted_jet_pt_branches(branches: list[str]) -> list[str]:
    matched = []
    for branch in branches:
        match = JET_PT_PATTERN.match(branch)
        if match:
            matched.append((int(match.group(1)), branch))
    return [branch for _, branch in sorted(matched)]


def _extract_valid_jet_pts(arrays: dict[str, np.ndarray], jet_pt_branches: list[str]) -> np.ndarray:
    pts = np.stack(
        [np.asarray(arrays[name], dtype=np.float64) for name in jet_pt_branches],
        axis=1,
    )
    pts = pts.reshape(-1)
    valid = np.isfinite(pts) & (pts != PAD_VAL) & (pts > 0.0)
    return pts[valid]


def plot_jet_pt(
    input_file: str | Path,
    output_pdf: str | Path | None = None,
    tree_name: str = DEFAULT_TREE,
) -> dict[str, float | str | int]:
    """
    Plot all saved AK4 jet pT values as an unweighted raw-count histogram.
    """

    input_path = Path(input_file).expanduser().resolve()
    if output_pdf is None:
        output_path = input_path.with_name(f"{input_path.stem}_jet_pt.pdf")
    else:
        output_path = Path(output_pdf).expanduser().resolve()

    with uproot.open(input_path) as root_file:
        tree = root_file[tree_name]
        jet_pt_branches = _sorted_jet_pt_branches(tree.keys())
        if not jet_pt_branches:
            raise KeyError(f"No ak4JetPt<i> branches found in {input_path}")

        arrays = tree.arrays(jet_pt_branches, library="np")
        n_events = tree.num_entries

    if n_events <= 0:
        raise ValueError("Input tree has no events.")

    jet_pts = _extract_valid_jet_pts(arrays, jet_pt_branches)
    if len(jet_pts) == 0:
        raise ValueError("No valid AK4 jet pT values found after removing padded slots.")

    min_pt = float(np.min(jet_pts))
    max_pt = float(np.max(jet_pts))
    bin_edges = np.arange(PT_RANGE[0], PT_RANGE[1] + BIN_WIDTH_GEV, BIN_WIDTH_GEV)

    hep.style.use("CMS")
    fig, ax = plt.subplots(figsize=(8.0, 6.0))

    ax.hist(
        jet_pts,
        bins=bin_edges,
        histtype="step",
        linewidth=1.8,
        color="black",
        label="AK4 jets",
    )
    ax.axvline(
        min_pt,
        color="tab:red",
        linestyle="--",
        linewidth=1.5,
        label=rf"min $p_{{\mathrm{{T}}}}$ = {min_pt:.2f} GeV",
    )

    ax.set_xlim(*PT_RANGE)
    ax.set_xlabel(r"AK4 jet $p_{\mathrm{T}}$ [GeV]")
    ax.set_ylabel("Jets / bin")
    ax.set_title(r"Unweighted AK4 jet $p_{\mathrm{T}}$ distribution")
    ax.legend(loc="upper right", frameon=True)
    ax.grid(True, alpha=0.25)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)

    return {
        "output_pdf": str(output_path),
        "n_events": int(n_events),
        "n_jets": int(len(jet_pts)),
        "min_pt": min_pt,
        "max_pt": max_pt,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot all saved AK4 jet pT values as an unweighted histogram."
    )
    parser.add_argument("input_file", help="Path to a Calib_ChargeTagger output ROOT file.")
    parser.add_argument(
        "-o",
        "--output-pdf",
        default=None,
        help="Optional output PDF path. Defaults next to the input file.",
    )
    parser.add_argument(
        "--tree-name",
        default=DEFAULT_TREE,
        help=f"ROOT tree name to read. Default: {DEFAULT_TREE}",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    result = plot_jet_pt(
        input_file=args.input_file,
        output_pdf=args.output_pdf,
        tree_name=args.tree_name,
    )
    print(f"Saved plot to: {result['output_pdf']}")
    print(f"Events: {result['n_events']}")
    print(f"Jets used: {result['n_jets']}")
    print(f"Minimum jet pT: {result['min_pt']:.3f} GeV")
    print(f"Maximum jet pT: {result['max_pt']:.3f} GeV")
