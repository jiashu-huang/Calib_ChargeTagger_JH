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
REQUIRED_BRANCHES = (
    "GenWLeptonPt",
    "GenWLeptonFlavor",
)
ELECTRON_FLAVOR = 11
MUON_FLAVOR = 13


def plot_genwlepton_pt_flavor(
    input_file: str | Path,
    output_pdf: str | Path | None = None,
    tree_name: str = DEFAULT_TREE,
) -> dict[str, float | str | int]:
    """
    Plot GenWLeptonPt for electrons and muons on the same axes.

    Each histogram is normalized by the total number of events, so the integral
    approximates the average number of generator-level W leptons of that flavor
    per event in the plotted range.
    """

    input_path = Path(input_file).expanduser().resolve()
    if output_pdf is None:
        output_path = input_path.with_name(f"{input_path.stem}_genwlepton_pt_flavor.pdf")
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

    if n_events <= 0:
        raise ValueError("Input tree has no events.")

    genwlepton_pt = np.asarray(arrays["GenWLeptonPt"], dtype=np.float64)
    genwlepton_flavor = np.asarray(arrays["GenWLeptonFlavor"], dtype=np.uint32)

    valid_pt = np.isfinite(genwlepton_pt) & (genwlepton_pt > 0.0)
    electron_mask = valid_pt & (genwlepton_flavor == ELECTRON_FLAVOR)
    muon_mask = valid_pt & (genwlepton_flavor == MUON_FLAVOR)

    electron_pts = genwlepton_pt[electron_mask]
    muon_pts = genwlepton_pt[muon_mask]

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
        label=r"$\mathrm{GenWLeptonFlavor}=11$ (electron)",
    )
    ax.hist(
        muon_pts,
        bins=bin_edges,
        weights=muon_weights,
        histtype="step",
        linewidth=1.8,
        color="tab:red",
        label=r"$\mathrm{GenWLeptonFlavor}=13$ (muon)",
    )

    ax.set_xlim(*PT_RANGE)
    ax.set_xlabel(r"$\mathrm{GenWLeptonPt}$ [GeV]")
    ax.set_ylabel("Leptons / event / bin")
    ax.set_title(r"$\mathrm{GenWLeptonPt}$ split by flavor")
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
            "Plot GenWLeptonPt for electrons and muons on the same axes, "
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
    result = plot_genwlepton_pt_flavor(
        input_file=args.input_file,
        output_pdf=args.output_pdf,
        tree_name=args.tree_name,
    )
    print(f"Saved plot to: {result['output_pdf']}")
    print(f"Events: {result['n_events']}")
    print(f"Electrons used: {result['n_electrons']} ({result['electron_per_event']:.4f} / event)")
    print(f"Muons used: {result['n_muons']} ({result['muon_per_event']:.4f} / event)")
