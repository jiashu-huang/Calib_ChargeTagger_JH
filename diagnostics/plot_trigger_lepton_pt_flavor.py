"""
Plot the trigger lepton's pT split by trigger lepton flavor.

Events are weighted by `finalWeight` when the branch is present (i.e. the file
has been through the normalization pass, see docs/normalization.md); otherwise every
event counts as 1.0. Events with no resolved trigger lepton carry
`TriggerLeptonFlav == PAD_VAL` and are counted but not plotted.
"""

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
WEIGHT_BRANCH = "finalWeight"
REQUIRED_BRANCHES = (
    "TriggerLeptonPt",
    "TriggerLeptonFlav",
)
# (flavor code, legend label, color)
FLAVORS = (
    (11, "electron", "tab:blue"),
    (13, "muon", "tab:red"),
)


def plot_trigger_lepton_pt_flavor(
    input_file: str | Path,
    output_pdf: str | Path | None = None,
    tree_name: str = DEFAULT_TREE,
) -> dict:
    """
    Plot TriggerLeptonPt for electrons and muons on the same axes.

    Uses `finalWeight` as the per-event weight if that branch exists, else 1.0
    per event.
    """

    input_path = Path(input_file).expanduser().resolve()
    if output_pdf is None:
        output_path = input_path.with_name(f"{input_path.stem}_trigger_lepton_pt_flavor.pdf")
    else:
        output_path = Path(output_pdf).expanduser().resolve()

    with uproot.open(input_path) as root_file:
        tree = root_file[tree_name]
        branches = tree.keys()
        missing = [branch for branch in REQUIRED_BRANCHES if branch not in branches]
        if missing:
            raise KeyError(
                f"Missing required branch(es) in {input_path}: {', '.join(sorted(missing))}"
            )

        weighted = WEIGHT_BRANCH in branches
        arrays = tree.arrays(
            [*REQUIRED_BRANCHES, *([WEIGHT_BRANCH] if weighted else [])],
            library="np",
        )
        n_events = tree.num_entries

    if n_events <= 0:
        raise ValueError("Input tree has no events.")

    pt = np.asarray(arrays["TriggerLeptonPt"], dtype=np.float64)
    flav = np.asarray(arrays["TriggerLeptonFlav"], dtype=np.int64)
    weights = (
        np.asarray(arrays[WEIGHT_BRANCH], dtype=np.float64)
        if weighted
        else np.ones(n_events, dtype=np.float64)
    )

    has_trigger_lepton = flav != int(PAD_VAL)
    valid = has_trigger_lepton & np.isfinite(pt) & (pt != PAD_VAL)

    bin_edges = np.arange(PT_RANGE[0], PT_RANGE[1] + BIN_WIDTH_GEV, BIN_WIDTH_GEV)

    hep.style.use("CMS")
    fig, ax = plt.subplots(figsize=(8.0, 6.0))

    per_flavor = {}
    tallest_bin = 0.0
    for code, label, color in FLAVORS:
        mask = valid & (flav == code)
        counts, _, _ = ax.hist(
            pt[mask],
            bins=bin_edges,
            weights=weights[mask],
            histtype="step",
            linewidth=1.8,
            color=color,
            label=rf"$\mathrm{{TriggerLeptonFlav}}={code}$ ({label})",
        )
        tallest_bin = max(tallest_bin, float(np.max(counts)) if len(counts) else 0.0)
        per_flavor[label] = {
            "n_events": int(np.count_nonzero(mask)),
            "sum_weights": float(np.sum(weights[mask])),
        }

    # The y axis states the weight, so the legend stays narrow enough to sit
    # beside the sharp trigger turn-on peak rather than on top of it.
    weight_note = rf"$\sum$ {WEIGHT_BRANCH}" if weighted else "Events"
    ax.set_xlim(*PT_RANGE)
    if tallest_bin > 0.0:
        ax.set_ylim(0.0, 1.45 * tallest_bin)
    ax.set_xlabel(r"Trigger lepton $p_{\mathrm{T}}$ [GeV]")
    ax.set_ylabel(f"{weight_note} / {BIN_WIDTH_GEV:g} GeV")
    ax.set_title(r"Trigger lepton $p_{\mathrm{T}}$ split by flavor")
    ax.legend(loc="upper right", frameon=True, fontsize=15)
    ax.grid(True, alpha=0.25)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)

    return {
        "output_pdf": str(output_path),
        "n_events": int(n_events),
        "weight_branch": WEIGHT_BRANCH if weighted else None,
        "n_no_trigger_lepton": int(np.count_nonzero(~has_trigger_lepton)),
        "per_flavor": per_flavor,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot TriggerLeptonPt for electrons and muons on the same axes, "
            f"weighted by {WEIGHT_BRANCH} when available."
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
    result = plot_trigger_lepton_pt_flavor(
        input_file=args.input_file,
        output_pdf=args.output_pdf,
        tree_name=args.tree_name,
    )
    print(f"Saved plot to: {result['output_pdf']}")
    print(f"Events: {result['n_events']}")
    print(f"Weight: {result['weight_branch'] or 'unweighted (1.0 / event)'}")
    for label, stats in result["per_flavor"].items():
        print(f"{label}: {stats['n_events']} events, sum of weights {stats['sum_weights']:.6g}")
    print(f"No trigger lepton (PAD_VAL flavor): {result['n_no_trigger_lepton']}")
