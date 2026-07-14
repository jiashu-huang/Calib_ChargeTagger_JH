from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-calib_chargetagger")

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import mplhep as hep
import numpy as np
import uproot

PT_RANGE = (0.0, 100.0)
BIN_WIDTH_GEV = 1.0
DEFAULT_TREE = "Events"
PAD_VAL = -99999.0
REQUIRED_BRANCHES = (
    "ElectronPt0",
    "ElectronPt1",
    "ElectronPt2",
    "MuonPt0",
    "MuonPt1",
    "MuonPt2",
)


def _extract_valid_pts(arrays: dict[str, np.ndarray], prefixes: tuple[str, ...]) -> np.ndarray:
    pts = np.stack([np.asarray(arrays[name], dtype=np.float64) for name in prefixes], axis=1)
    pts = pts.reshape(-1)
    valid = np.isfinite(pts) & (pts != PAD_VAL) & (pts > 0.0)
    return pts[valid]


def plot_lepton_pt(
    input_file: str | Path,
    output_pdf: str | Path | None = None,
    tree_name: str = DEFAULT_TREE,
) -> dict[str, float | str | int]:
    """
    Plot ElectronPt and MuonPt on the same axes, normalized by the total event count.

    With this normalization, the histogram integrals correspond to the average
    number of reconstructed electrons or muons per event in the plotted range.
    """

    input_path = Path(input_file).expanduser().resolve()
    if output_pdf is None:
        output_path = input_path.with_name(f"{input_path.stem}_lepton_pt.pdf")
    else:
        output_path = Path(output_pdf).expanduser().resolve()

    with uproot.open(input_path) as root_file:
        tree = root_file[tree_name]
        missing = [branch for branch in REQUIRED_BRANCHES if branch not in tree.keys()]
        if missing:
            raise KeyError(
                f"Missing required branch(es) in {input_path}: {', '.join(sorted(missing))}"
            )

        arrays = tree.arrays(list(REQUIRED_BRANCHES), library="np")
        n_events = tree.num_entries

    electron_pts = _extract_valid_pts(arrays, ("ElectronPt0", "ElectronPt1", "ElectronPt2"))
    muon_pts = _extract_valid_pts(arrays, ("MuonPt0", "MuonPt1", "MuonPt2"))

    if n_events <= 0:
        raise ValueError("Input tree has no events.")

    bin_edges = np.arange(PT_RANGE[0], PT_RANGE[1] + BIN_WIDTH_GEV, BIN_WIDTH_GEV)
    electron_weights = np.full(len(electron_pts), 1.0 / n_events, dtype=np.float64)
    muon_weights = np.full(len(muon_pts), 1.0 / n_events, dtype=np.float64)

    hep.style.use("CMS")
    fig, ax = plt.subplots(figsize=(8.0, 6.0))

    ax.hist(
        electron_pts,
        bins=bin_edges,
        weights=electron_weights,
        histtype="step",
        linewidth=1.8,
        color="tab:blue",
        label="Electrons",
    )
    ax.hist(
        muon_pts,
        bins=bin_edges,
        weights=muon_weights,
        histtype="step",
        linewidth=1.8,
        color="tab:red",
        label="Muons",
    )

    ax.set_xlim(*PT_RANGE)
    ax.set_xlabel(r"Lepton $p_{\mathrm{T}}$ [GeV]")
    ax.set_ylabel("Leptons / event / bin")
    ax.set_title("ElectronPt and MuonPt distributions")
    ax.legend(loc="upper right", frameon=True)
    ax.grid(True, alpha=0.25)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)

    return {
        "output_pdf": str(output_path),
        "n_events": int(n_events),
        "n_electrons": int(len(electron_pts)),
        "n_muons": int(len(muon_pts)),
        "electron_per_event": float(len(electron_pts) / n_events),
        "muon_per_event": float(len(muon_pts) / n_events),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot ElectronPt and MuonPt distributions on the same axes, "
            "normalized by the total number of events."
        )
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
    result = plot_lepton_pt(
        input_file=args.input_file,
        output_pdf=args.output_pdf,
        tree_name=args.tree_name,
    )
    print(f"Saved plot to: {result['output_pdf']}")
    print(f"Events: {result['n_events']}")
    print(f"Electrons used: {result['n_electrons']} ({result['electron_per_event']:.4f} / event)")
    print(f"Muons used: {result['n_muons']} ({result['muon_per_event']:.4f} / event)")
