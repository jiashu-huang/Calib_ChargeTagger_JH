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
import vector

try:
    from scipy.optimize import curve_fit
except ImportError:  # pragma: no cover - optional dependency fallback
    curve_fit = None


HIST_RANGE = (30.0, 130.0)
BIN_WIDTH_GEV = 1.0
DEFAULT_TREE = "Events"
REQUIRED_BRANCHES = (
    "GenWLeptonPt",
    "GenWLeptonEta",
    "GenWLeptonPhi",
    "GenWLeptonMass",
    "GenWNeutrinoPt",
    "GenWNeutrinoEta",
    "GenWNeutrinoPhi",
    "GenWNeutrinoMass",
)


def _gaussian(x: np.ndarray, amplitude: float, mean: float, sigma: float) -> np.ndarray:
    return amplitude * np.exp(-0.5 * ((x - mean) / sigma) ** 2)


def _grid_search_gaussian_fit(
    bin_centers: np.ndarray,
    bin_values: np.ndarray,
    fit_mask: np.ndarray,
) -> tuple[float, float, float]:
    """
    Numpy-only Gaussian fit fallback for environments without scipy.

    For fixed mean and sigma, the least-squares best-fit amplitude is analytic.
    We search over (mean, sigma) on a coarse-to-fine grid around the peak bin.
    """

    x_fit = bin_centers[fit_mask]
    y_fit = bin_values[fit_mask]
    peak_center = float(x_fit[np.argmax(y_fit)])

    best = None
    mu_min = max(HIST_RANGE[0], peak_center - 15.0)
    mu_max = min(HIST_RANGE[1], peak_center + 15.0)

    for mu_step, sigma_step, sigma_span in (
        (0.5, 0.5, (2.0, 20.0)),
        (0.1, 0.1, None),
        (0.02, 0.02, None),
    ):
        if best is None:
            mu_values = np.arange(mu_min, mu_max + mu_step, mu_step)
            sigma_values = np.arange(sigma_span[0], sigma_span[1] + sigma_step, sigma_step)
        else:
            best_amp, best_mu, best_sigma, _ = best
            mu_values = np.arange(best_mu - 2.0, best_mu + 2.0 + mu_step, mu_step)
            sigma_values = np.arange(
                max(0.5, best_sigma - 2.0),
                best_sigma + 2.0 + sigma_step,
                sigma_step,
            )

        for mean in mu_values:
            for sigma in sigma_values:
                if sigma <= 0:
                    continue

                shape = np.exp(-0.5 * ((x_fit - mean) / sigma) ** 2)
                denom = np.dot(shape, shape)
                if denom <= 0:
                    continue

                amplitude = float(np.dot(y_fit, shape) / denom)
                model = amplitude * shape
                chi2 = float(np.sum((y_fit - model) ** 2))

                if best is None or chi2 < best[3]:
                    best = (amplitude, float(mean), float(sigma), chi2)

    if best is None:
        raise RuntimeError("Gaussian fit failed in grid-search fallback.")

    return best[0], best[1], best[2]


def _fit_gaussian_to_histogram(
    bin_centers: np.ndarray,
    bin_values: np.ndarray,
) -> tuple[float, float, float]:
    """
    Fit a Gaussian to the central W-mass peak in the normalized histogram.

    The fit window is centered on the peak bin and spans +/- 15 GeV.
    """

    if not np.any(bin_values > 0):
        raise ValueError("Histogram has no positive bins; cannot fit a Gaussian.")

    peak_center = float(bin_centers[np.argmax(bin_values)])
    fit_mask = (bin_centers >= peak_center - 15.0) & (bin_centers <= peak_center + 15.0)
    fit_mask &= np.isfinite(bin_values)

    if np.count_nonzero(fit_mask) < 5:
        raise ValueError("Not enough populated bins in the fit window to fit a Gaussian.")

    amplitude0 = float(np.max(bin_values[fit_mask]))
    mean0 = peak_center
    sigma0 = 8.0

    if curve_fit is not None:
        params, _ = curve_fit(
            _gaussian,
            bin_centers[fit_mask],
            bin_values[fit_mask],
            p0=(amplitude0, mean0, sigma0),
            bounds=([0.0, HIST_RANGE[0], 0.5], [np.inf, HIST_RANGE[1], 30.0]),
            maxfev=20000,
        )
        amplitude, mean, sigma = map(float, params)
        return amplitude, mean, sigma

    return _grid_search_gaussian_fit(bin_centers, bin_values, fit_mask)


def plot_genlv_invariant_mass(
    input_file: str | Path,
    output_pdf: str | Path | None = None,
    tree_name: str = DEFAULT_TREE,
) -> dict[str, float | str]:
    """
    Plot m(GenWLepton + GenWNeutrino) from a Calib_ChargeTagger skimmed ROOT file.

    The histogram uses 1 GeV bins over [30, 130] GeV, is normalized to unit area
    over the plotted range, and is fit with a Gaussian around the central peak.
    """

    input_path = Path(input_file).expanduser().resolve()
    if output_pdf is None:
        output_path = input_path.with_name(f"{input_path.stem}_genlv_mass.pdf")
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

    genwlepton = vector.array(
        {
            "pt": arrays["GenWLeptonPt"],
            "eta": arrays["GenWLeptonEta"],
            "phi": arrays["GenWLeptonPhi"],
            "mass": arrays["GenWLeptonMass"],
        }
    )
    genwneutrino = vector.array(
        {
            "pt": arrays["GenWNeutrinoPt"],
            "eta": arrays["GenWNeutrinoEta"],
            "phi": arrays["GenWNeutrinoPhi"],
            "mass": arrays["GenWNeutrinoMass"],
        }
    )

    masses = np.asarray((genwlepton + genwneutrino).mass, dtype=np.float64)

    valid = np.isfinite(masses)
    masses = masses[valid]

    bin_edges = np.arange(HIST_RANGE[0], HIST_RANGE[1] + BIN_WIDTH_GEV, BIN_WIDTH_GEV)
    bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
    counts, _ = np.histogram(masses, bins=bin_edges)

    normalization = float(np.sum(counts) * BIN_WIDTH_GEV)
    if normalization <= 0:
        raise ValueError(
            "Histogram integral in the plotting range is not positive; cannot "
            "normalize the histogram."
        )

    normalized_counts = counts / normalization
    amplitude, mean, sigma = _fit_gaussian_to_histogram(bin_centers, normalized_counts)

    print(f"Gaussian mean: {mean:.3f} GeV")
    print(f"Gaussian sigma: {sigma:.3f} GeV")

    hep.style.use("CMS")
    fig, ax = plt.subplots(figsize=(8.0, 6.0))

    ax.hist(
        masses,
        bins=bin_edges,
        weights=np.full(len(masses), 1.0 / normalization),
        histtype="step",
        linewidth=1.8,
        color="black",
        label="Normalized histogram",
    )

    fit_x = np.linspace(HIST_RANGE[0], HIST_RANGE[1], 800)
    ax.plot(
        fit_x,
        _gaussian(fit_x, amplitude, mean, sigma),
        color="tab:red",
        linewidth=2.0,
        label=rf"Gaussian fit: $\mu={mean:.2f}$ GeV, $\sigma={sigma:.2f}$ GeV",
    )

    ax.set_xlim(*HIST_RANGE)
    ax.set_xlabel(r"$m(\mathrm{GenWLepton}+\mathrm{GenWNeutrino})$ [GeV]")
    ax.set_ylabel("Normalized events / GeV")
    ax.set_title("Invariant mass of GenWLepton + GenWNeutrino")
    ax.legend(loc="upper right", frameon=True)
    ax.grid(True, alpha=0.25)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)

    return {
        "output_pdf": str(output_path),
        "gaussian_mean_gev": mean,
        "gaussian_sigma_gev": sigma,
        "n_events_used": int(len(masses)),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot the normalized invariant-mass distribution of GenWLepton + "
            "GenWNeutrino from a Calib_ChargeTagger skim ROOT file."
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
    result = plot_genlv_invariant_mass(
        input_file=args.input_file,
        output_pdf=args.output_pdf,
        tree_name=args.tree_name,
    )
    print(f"Saved plot to: {result['output_pdf']}")
