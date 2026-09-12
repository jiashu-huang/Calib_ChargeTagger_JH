"""Run-3 MuonScaReKIT momentum calibration for tight, isolated 2024 muons.

The ordinary-momentum April 2026 payload is pinned below. Data and MC are
scaled to the generator reference; MC then receives residual resolution
smearing. Apply this to the input collection before any pT selection.

Formulas follow cms-muonPOG/muonscarekit at 1c7426b5 (22 June 2026).
Unlike its Python example, resolution variations act on residual K, and
both statistical and systematic uncertainties are included. The payload's
MC uncertainty entries already combine data and MC errors. See
docs/muon-momentum-2024-plan.md for sources and the high-pT limitation.
"""

from __future__ import annotations

import gzip
import hashlib
import logging
from enum import IntEnum
from functools import cache
from pathlib import Path

import awkward as ak
import correctionlib
import numpy as np
from scipy.special import erf, erfinv

logger = logging.getLogger(__name__)

PAYLOAD_NAME = "2024_muon_scalesmearing.json.gz"
PAYLOAD_SHA256 = "4d3137a34fd6cba316d9fd3b2f9f5f7df8aaac8f8f878e283d0f5ff89053589f"
PAYLOAD_PATH = Path(__file__).resolve().parents[1] / "corrections" / PAYLOAD_NAME
CVMFS_PATH = Path(
    "/cvmfs/cms-griddata.cern.ch/cat/metadata/MUO/"
    "Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15/"
    "2026-04-28/muon_scalesmearing.json.gz"
)
PT_MIN, PT_MAX = 26.0, 200.0

# The four total shifts define the default two-source nuisance model. The
# components are retained as well so another correlation model can be built.
TOTAL_VARIATIONS = ("scaleUp", "scaleDown", "resolutionUp", "resolutionDown")
COMPONENT_VARIATIONS = tuple(
    f"{source}{component}{direction}"
    for source in ("scale", "resolution")
    for component in ("Stat", "Syst")
    for direction in ("Up", "Down")
)
PT_VARIATIONS = {name: f"pt_{name}" for name in TOTAL_VARIATIONS + COMPONENT_VARIATIONS}
VARIATION_IDS = {name: i for i, name in enumerate(("nominal", *PT_VARIATIONS))}


class MomentumStatus(IntEnum):
    """Per-muon coverage, saved even when no correction is applicable."""

    INELIGIBLE = 0  # outside tight ID / PF isolation / eta or nonfinite inputs
    CALIBRATED = 1
    BELOW_RANGE = 2
    ABOVE_RANGE = 3  # GE/TuneP prescription is not an ordinary MC pT correction
    FALLBACK = 4  # invalid parameters or pathological nominal/varied smearing
    SCALE_ONLY = 5  # scaled MC pT left the resolution helper's 26--200 domain
    UNSUPPORTED_YEAR = 6


def validate_variation(variation: str) -> None:
    if variation not in VARIATION_IDS:
        raise ValueError(f"Unknown muon pT variation {variation!r}; choose {tuple(VARIATION_IDS)}")


@cache
def get_muon_correctionset():
    """Load only the pinned payload; unavailable or different inputs are fatal."""
    for path in (PAYLOAD_PATH, CVMFS_PATH):
        if path.is_file():
            payload = gzip.decompress(path.read_bytes())
            if hashlib.sha256(payload).hexdigest() != PAYLOAD_SHA256:
                raise RuntimeError(f"Muon momentum payload checksum mismatch: {path}")
            logger.info("Muon momentum: using %s", path)
            return correctionlib.CorrectionSet.from_string(payload.decode())
    raise RuntimeError(f"Required muon momentum payload missing: {PAYLOAD_PATH} or {CVMFS_PATH}")


def _crystal_ball_draw(uniform, mean, width, alpha, power):
    """Invert the symmetric double-sided Crystal Ball CDF, vectorized.

    Keep the reference helper's numerical pi constant for reproducibility.
    Evaluating each branch only on its domain avoids invalid intermediate
    powers and erfinv arguments in the tails.
    """
    sqrt_pi_over_two = np.sqrt(3.14159 / 2.0)
    a = np.abs(alpha)
    tail = power / a / (power - 1) * np.exp(-0.5 * a**2)
    core = 2 * sqrt_pi_over_two * erf(a / np.sqrt(2.0))
    norm = 1 / (core + 2 * tail)
    tail_probability = norm * tail
    f = 1 - a**2 / power
    g = width * power / a
    exponent = 1 / (power - 1)
    result = np.empty_like(uniform)
    left = uniform < tail_probability
    right = uniform > 1 - tail_probability
    middle = ~(left | right)
    result[left] = mean[left] + g[left] * (
        f[left] - (tail_probability[left] / uniform[left]) ** exponent[left]
    )
    result[right] = mean[right] - g[right] * (
        f[right] - ((1 - uniform[right]) / tail_probability[right]) ** -exponent[right]
    )
    argument = (core[middle] + 2 * tail[middle]) / 2 - uniform[middle] / norm[middle]
    result[middle] = mean[middle] - np.sqrt(2.0) * width[middle] * erfinv(
        argument / sqrt_pi_over_two
    )
    return result


def _safe_smearing(pt, candidate):
    valid = np.isfinite(candidate) & (candidate / pt >= 0.1) & (candidate / pt <= 2.0)
    return np.where(valid, candidate, pt), valid


def _resolution_inputs(cset, pt, eta, layers, event, lumi, phi):
    abseta = np.abs(eta)
    parameters = [cset["cb_params"].evaluate(abseta, layers, i) for i in range(4)]
    mean, width, power, alpha = parameters
    valid = np.all(np.isfinite(parameters), axis=0) & (width > 0) & (power > 1) & (alpha > 0)
    uniform = cset["RandomSmearing"].evaluate(event, lumi, phi)
    valid &= (uniform > 0) & (uniform < 1)
    draw = np.zeros(len(pt))
    draw[valid] = _crystal_ball_draw(
        uniform[valid], mean[valid], width[valid], alpha[valid], power[valid]
    )
    poly = [cset["poly_params"].evaluate(abseta, layers, i) for i in range(3)]
    sigma = np.maximum(0, poly[0] + poly[1] * pt + poly[2] * pt**2)
    k_data = cset["k_data"].evaluate(abseta, "nom")
    k_mc = cset["k_mc"].evaluate(abseta, "nom")
    k = np.sqrt(np.maximum(0, k_data**2 - k_mc**2))
    valid &= np.isfinite(sigma) & np.isfinite(k) & np.isfinite(draw)
    return k, np.where(valid, sigma * draw, 0), valid


def _scale_error(cset, pt, eta, phi, charge, component):
    m = cset["m_mc"].evaluate(eta, phi, component)
    a = cset["a_mc"].evaluate(eta, phi, component)
    rho = cset["m_mc"].evaluate(eta, phi, f"rho_{component}")
    variance = (m / pt) ** 2 + a**2 + 2 * charge * rho * m * a / pt
    if np.any(~np.isfinite(variance)) or np.any(variance < -1e-20):
        raise ValueError(f"Invalid muon {component} scale covariance in the pinned payload")
    return pt**2 * np.sqrt(np.maximum(variance, 0))


def apply_muon_scale_smearing(events, muons, year: str, isData: bool, variation="nominal"):
    """Return corrected muons with raw/nominal/varied pT and explicit coverage.

    Input pT defines scale eligibility; scaled pT defines resolution
    eligibility, matching the reference's composed guards. Values outside
    26--200 GeV are preserved, never extrapolated. Relative isolation and
    physical charge retain their NanoAOD definitions. MET propagation is not
    applied here (optional in the supplied JMAR prescription).
    """
    validate_variation(variation)
    if variation != "nominal" and (isData or year != "2024"):
        raise ValueError("Muon pT variations require 2024 MC")
    required = {"pt", "eta", "phi", "charge", "tightId", "pfRelIso04_all"}
    if year == "2024" and not isData:
        required.add("nTrackerLayers")
        missing_events = {"event", "luminosityBlock"} - set(events.fields)
        if missing_events:
            raise KeyError(f"Missing muon momentum event inputs: {sorted(missing_events)}")
    missing = required - set(muons.fields)
    if missing:
        raise KeyError(f"Missing muon momentum inputs: {sorted(missing)}")

    counts = ak.to_numpy(ak.num(muons, axis=1))
    flat = ak.flatten(muons)
    raw = np.asarray(flat.pt_raw if "pt_raw" in flat.fields else flat.pt, dtype=np.float64)
    scale, nominal = raw.copy(), raw.copy()
    shifted = {name: raw.copy() for name in PT_VARIATIONS}
    status = np.full(len(raw), MomentumStatus.UNSUPPORTED_YEAR, dtype=np.int32)

    if year == "2024":
        # Load even for an empty chunk, so a broken production fails at startup.
        cset = get_muon_correctionset()
        eta, phi = np.asarray(flat.eta, float), np.asarray(flat.phi, float)
        charge = np.asarray(flat.charge, float)
        quality = (
            np.asarray(flat.tightId, bool)
            & (np.asarray(flat.pfRelIso04_all) < 0.15)
            & (np.abs(eta) < 2.4)
            & np.isfinite(raw)
            & np.isfinite(phi)
            & np.isin(charge, (-1, 1))
        )
        status[:] = MomentumStatus.INELIGIBLE
        status[quality & (raw < PT_MIN)] = MomentumStatus.BELOW_RANGE
        status[quality & (raw > PT_MAX)] = MomentumStatus.ABOVE_RANGE
        indices = np.flatnonzero(quality & (raw >= PT_MIN) & (raw <= PT_MAX))
        if len(indices):
            pt, e, ph, q = raw[indices], eta[indices], phi[indices], charge[indices]
            sample = "data" if isData else "mc"
            m = cset[f"m_{sample}"].evaluate(e, ph, "nom")
            a = cset[f"a_{sample}"].evaluate(e, ph, "nom")
            denominator = m / pt + q * a
            valid_scale = np.isfinite(denominator) & (denominator > 0)
            scale[indices] = np.divide(1, denominator, out=pt.copy(), where=valid_scale)
            nominal[indices] = scale[indices]
            status[indices] = np.where(
                valid_scale, MomentumStatus.CALIBRATED, MomentumStatus.FALLBACK
            )
            if not isData:
                valid_indices = indices[valid_scale]
                res_indices = valid_indices[
                    (scale[valid_indices] >= PT_MIN) & (scale[valid_indices] <= PT_MAX)
                ]
                status[valid_indices] = MomentumStatus.SCALE_ONLY
                for name in shifted:
                    shifted[name][valid_indices] = scale[valid_indices]
                if len(res_indices):
                    rp = scale[res_indices]
                    layers = np.asarray(flat.nTrackerLayers, float)[res_indices]
                    ev = np.repeat(np.asarray(events.event, np.int64), counts)[res_indices]
                    ls = np.repeat(np.asarray(events.luminosityBlock, np.int64), counts)[
                        res_indices
                    ]
                    k, sigma_draw, valid_res = _resolution_inputs(
                        cset, rp, eta[res_indices], layers, ev, ls, phi[res_indices]
                    )
                    nominal[res_indices], valid_smear = _safe_smearing(
                        rp, rp * (1 + k * sigma_draw)
                    )
                    valid_res &= valid_smear
                    sigma_draw = np.where(valid_res, sigma_draw, 0)
                    status[res_indices] = np.where(
                        valid_res, MomentumStatus.CALIBRATED, MomentumStatus.FALLBACK
                    )
                    errors = {
                        part: cset["k_mc"].evaluate(np.abs(eta[res_indices]), part)
                        for part in ("stat", "syst")
                    }
                    if any(np.any(~np.isfinite(v) | (v < 0)) for v in errors.values()):
                        raise ValueError(
                            "Invalid muon resolution uncertainty in the pinned payload"
                        )
                    errors[""] = np.hypot(errors["stat"], errors["syst"])
                    for part, error in errors.items():
                        for direction, sign in (("Up", 1), ("Down", -1)):
                            name = f"resolution{part.title()}{direction}"
                            candidate = rp * (1 + np.maximum(0, k + sign * error) * sigma_draw)
                            shifted[name][res_indices], valid_var = _safe_smearing(rp, candidate)
                            status[res_indices[~valid_var]] = MomentumStatus.FALLBACK

                vi = valid_indices
                errors = {
                    part: _scale_error(cset, nominal[vi], eta[vi], phi[vi], charge[vi], part)
                    for part in ("stat", "syst")
                }
                errors[""] = np.hypot(errors["stat"], errors["syst"])
                for part, error in errors.items():
                    for direction, sign in (("Up", 1), ("Down", -1)):
                        shifted[f"scale{part.title()}{direction}"][vi] = nominal[vi] + sign * error

    fields = {"pt_raw": raw, "pt_nominal": nominal, "pt_scale": scale, "momentumStatus": status}
    if not isData:
        fields.update({PT_VARIATIONS[name]: values for name, values in shifted.items()})
    fields["pt"] = nominal if variation == "nominal" else shifted[variation]
    for field, values in fields.items():
        muons = ak.with_field(muons, ak.unflatten(values, counts), field)
    if "nanoIdx" not in muons.fields:
        muons = ak.with_field(
            muons, ak.values_astype(ak.local_index(muons, axis=1), np.int32), "nanoIdx"
        )
    return muons
