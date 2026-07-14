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

PT_RANGE = (0.0, 50.0)
BIN_WIDTH_GEV = 1.0
DEFAULT_TREE = "Events"
REQUIRED_BRANCHES = (
    "GenWLeptonPt",
    "GenWLeptonFlavor",
    "HLT_IsoMu24",
)
MUON_FLAVOR = 13


def plot_genwleptonpt_isomu24_ratio(
    input_file: str | Path,
    output_pdf: str | Path | None = None,
    tree_name: str = DEFAULT_TREE,
) -> dict[str, str | int]:
    """
    Plot the IsoMu24 trigger ratio versus GenWLeptonPt for generator-level muons.

    The denominator is all events with GenWLeptonFlavor == 13, binned in GenWLeptonPt.
    The numerator additionally requires HLT_IsoMu24 to be true.
    """

    input_path = Path(input_file).expanduser().resolve()
    if output_pdf is None:
        output_path = input_path.with_name(f"{input_path.stem}_genwleptonpt_isomu24_ratio.pdf")
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

    genwlepton_pt = np.asarray(arrays["GenWLeptonPt"], dtype=np.float64)
    genwlepton_flavor = np.asarray(arrays["GenWLeptonFlavor"], dtype=np.uint32)
    hlt_isomu24 = np.asarray(arrays["HLT_IsoMu24"], dtype=bool)

    flavor_mask = genwlepton_flavor == MUON_FLAVOR
    valid_mask = np.isfinite(genwlepton_pt) & flavor_mask
    triggered_mask = valid_mask & hlt_isomu24

    bin_edges = np.arange(PT_RANGE[0], PT_RANGE[1] + BIN_WIDTH_GEV, BIN_WIDTH_GEV)
    bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])

    all_counts, _ = np.histogram(genwlepton_pt[valid_mask], bins=bin_edges)
    triggered_counts, _ = np.histogram(genwlepton_pt[triggered_mask], bins=bin_edges)

    ratio = np.divide(
        triggered_counts,
        all_counts,
        out=np.full_like(triggered_counts, np.nan, dtype=np.float64),
        where=all_counts > 0,
    )

    hep.style.use("CMS")
    fig, (ax_top, ax_ratio) = plt.subplots(
        2,
        1,
        figsize=(8.0, 8.0),
        sharex=True,
        gridspec_kw={"height_ratios": [3.0, 1.5], "hspace": 0.06},
    )

    ax_top.hist(
        genwlepton_pt[valid_mask],
        bins=bin_edges,
        histtype="step",
        linewidth=1.8,
        color="black",
        label=r"All events with $\mathrm{GenWLeptonFlavor}=13$",
    )
    ax_top.hist(
        genwlepton_pt[triggered_mask],
        bins=bin_edges,
        histtype="step",
        linewidth=1.8,
        color="tab:red",
        label=r"Subset with $\mathrm{HLT\_IsoMu24}=1$",
    )
    ax_top.set_ylabel("Events / GeV")
    ax_top.set_title(r"$\mathrm{IsoMu24}$ ratio vs. $\mathrm{GenWLeptonPt}$")
    ax_top.legend(loc="upper left", frameon=True)
    ax_top.grid(True, alpha=0.25)

    ratio_mask = np.isfinite(ratio)
    ax_ratio.step(bin_edges[:-1], ratio, where="post", color="tab:blue", linewidth=1.8)
    ax_ratio.scatter(bin_centers[ratio_mask], ratio[ratio_mask], color="tab:blue", s=16)
    ax_ratio.set_xlim(*PT_RANGE)
    ax_ratio.set_ylim(0.0, 1.1)
    ax_ratio.set_xlabel(r"$\mathrm{GenWLeptonPt}$ [GeV]")
    ax_ratio.set_ylabel("HLT ratio")
    ax_ratio.grid(True, alpha=0.25)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)

    return {
        "output_pdf": str(output_path),
        "n_all_events": int(np.sum(all_counts)),
        "n_triggered_events": int(np.sum(triggered_counts)),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot the IsoMu24 trigger ratio versus GenWLeptonPt for "
            "GenWLeptonFlavor == 13 events."
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
    result = plot_genwleptonpt_isomu24_ratio(
        input_file=args.input_file,
        output_pdf=args.output_pdf,
        tree_name=args.tree_name,
    )
    print(f"Saved plot to: {result['output_pdf']}")
    print(f"Events in denominator histograms: {result['n_all_events']}")
    print(f"Events in numerator histogram: {result['n_triggered_events']}")
