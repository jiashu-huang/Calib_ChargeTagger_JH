"""Numerical checks for signed MC normalization; no sample cross-section choice."""

from __future__ import annotations

import json

import numpy as np


def finite_sum(values, label: str) -> float:
    """Sum a finite one-dimensional array, retaining signs and zero entries."""
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise ValueError(f"{label} must contain finite one-dimensional values")
    with np.errstate(over="ignore", invalid="ignore"):
        total = float(np.sum(values))
    if not np.isfinite(total):
        raise ValueError(f"{label} has a nonfinite sum")
    return total


def require_denominator(value) -> float:
    """A signed denominator is usable only if finite and nonzero."""
    denominator = float(value)
    if not np.isfinite(denominator) or denominator == 0:
        raise ValueError("Global np_nominal must be finite and nonzero")
    return denominator


def normalized_weights(weights, denominator) -> np.ndarray:
    """Compute the exact stored quotient; reject nonfinite inputs or results."""
    denominator = require_denominator(denominator)
    weights = np.asarray(weights, dtype=np.float64)
    if weights.ndim != 1 or not np.all(np.isfinite(weights)):
        raise ValueError("Event weights must be finite and one-dimensional")
    with np.errstate(over="ignore", invalid="ignore"):
        result = weights / denominator
    if not np.all(np.isfinite(result)):
        raise ValueError("Normalizing event weights produces nonfinite values")
    return result


def infer_sample_scale(weights, weights_noxsec, reference: float | None = None) -> float | None:
    """Check weight = scale * weight_noxsec, including signed/zero entries.

    Return a common positive factor when inferable. Empty or all-zero arrays
    carry no scale information and retain the incoming reference. A consistent
    factor is an arithmetic check, not proof of a physical cross section.
    """
    weights, base = (np.asarray(value, dtype=np.float64) for value in (weights, weights_noxsec))
    if weights.ndim != 1 or weights.shape != base.shape:
        raise ValueError("weight and weight_noxsec must have matching one-dimensional shapes")
    if not np.all(np.isfinite(weights)) or not np.all(np.isfinite(base)):
        raise ValueError("weight and weight_noxsec must be finite")
    nonzero = base != 0
    if np.any(weights[~nonzero] != 0):
        raise ValueError("Zero weight_noxsec must have zero weight")
    if not np.any(nonzero):
        return reference
    with np.errstate(over="ignore", invalid="ignore"):
        ratios = weights[nonzero] / base[nonzero]
    candidate = float(ratios[0]) if reference is None else reference
    if (not np.isfinite(candidate) or candidate <= 0 or not np.all(np.isfinite(ratios))
            or not np.allclose(ratios, candidate, rtol=1e-10, atol=0)):
        raise ValueError("Inconsistent or invalid sample scale in weight / weight_noxsec")
    return candidate


def read_normalization_provenance(handle) -> dict | None:
    """Read a valid, hadd-safe TNamed normalization receipt when present."""
    if "finalWeight_provenance" not in handle:
        return None
    try:
        record = json.loads(handle["finalWeight_provenance"].member("fTitle"))
        require_denominator(record["np_nominal"])
        if not isinstance(record["fingerprint"], str) or not record["fingerprint"]:
            raise ValueError("Missing normalization fingerprint")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid finalWeight provenance: {exc}") from exc
    return record
