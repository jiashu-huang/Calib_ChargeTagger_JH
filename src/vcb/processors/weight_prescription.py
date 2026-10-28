"""Identify the 2024 weight convention and reject incompatible output batches."""

from __future__ import annotations

import json
import re
from functools import lru_cache

import awkward as ak
import numpy as np
import uproot

from vcb.processors.lepton_sf import (
    MUON_COMPONENT_WEIGHT_BRANCHES,
    MUON_SF_2024_SHA256,
    get_lepton_correctionsets,
)
from vcb.processors.top_pt import SF_FUNCTIONS, is_ttbar, top_pt_prescription

WEIGHT_PRESCRIPTION_VERSION = 3
_PS_PREFIX = "PS weights (w_var / w_nominal)"
_SCALE_PREFIX = "LHE scale variation weights (w_var / w_nominal);"
_SCALE_GRID = [(r, f) for r in (0.5, 1.0, 2.0) for f in (0.5, 1.0, 2.0)]


def require_supported_sample(year: str, is_data: bool) -> None:
    """Do not write data output through the known incomplete 2024 path."""
    if year == "2024" and is_data:
        raise NotImplementedError(
            "2024 collision-data processing is not implemented: it requires a golden-JSON "
            "lumi mask, run-dependent data JEC and rebuilt data MET. This path supports MC only."
        )


def uses_scale_weights(dataset: str) -> bool:
    return is_ttbar(dataset) or "HHTobbbb" in dataset or "HHto4B" in dataset


def prescription_from_titles(
    ps_title: str, scale_title: str | None, version: int = WEIGHT_PRESCRIPTION_VERSION,
    top_pt_enabled: bool = False,
) -> dict:
    """Lengths alone cannot identify either weight ordering. Check every label."""
    if version not in (1, 2, 3):
        raise ValueError(f"Unrecognized weight prescription version: {version}")
    ps_title = " ".join(ps_title.split()).rstrip(" ;")
    if not ps_title.startswith(_PS_PREFIX):
        raise ValueError(f"Unverified PSWeight metadata: {ps_title!r}")
    entries = ps_title[len(_PS_PREFIX):].strip().split(";")
    ps_labels = []
    for entry in entries:
        match = re.fullmatch(r"\s*\[(\d+)\]\s+(isr|fsr)\.murfac=(0\.5|2(?:\.0)?)\s*", entry)
        if match is None:
            raise ValueError(f"Unverified PSWeight metadata: {ps_title!r}")
        index, shower, scale = match.groups()
        ps_labels.append((int(index), shower, float(scale)))
    if ps_labels != [(0, "isr", 2.), (1, "fsr", 2.), (2, "isr", .5), (3, "fsr", .5)]:
        raise ValueError("PSWeight metadata disagrees with the supported muR ordering")

    scale_layout = None
    if scale_title is not None:
        scale_title = " ".join(scale_title.split()).rstrip(" ;")
        if not scale_title.startswith(_SCALE_PREFIX):
            raise ValueError(f"Unverified LHEScaleWeight metadata: {scale_title!r}")
        entries = scale_title[len(_SCALE_PREFIX):].strip().split(";")
        labels = []
        for index, entry in enumerate(entries):
            match = re.fullmatch(
                r"\s*\[(\d+)\] is renscfact=(0\.5|1(?:\.0)?|2(?:\.0)?)(?:d0)? "
                r"facscfact=(0\.5|1(?:\.0)?|2(?:\.0)?)(?:d0)?\s*", entry,
            )
            if match is None or int(match[1]) != index:
                raise ValueError(f"Unverified LHEScaleWeight metadata: {scale_title!r}")
            labels.append((float(match[2]), float(match[3])))
        if labels not in (_SCALE_GRID, _SCALE_GRID[:4] + _SCALE_GRID[5:]):
            raise ValueError("LHEScaleWeight metadata disagrees with the supported scale grid")
        indices = [0, 1, 3, 5, 7, 8] if len(labels) == 9 else [0, 1, 3, 4, 6, 7]
        scale_layout = {
            "input_members": len(labels), "central_index": 4 if len(labels) == 9 else None,
            "saved_indices": indices, "saved_muR_muF": [list(labels[i]) for i in indices],
            "clip": None,
        }
    record = {
        "version": version, "year": "2024",
        "pileup": {"input": "Pileup_nTrueInt", "flow": "payload", "clip": None},
        "ps": {"Up": "muR x2", "Down": "muR x0.5", "ISR_indices": [0, 2],
               "FSR_indices": [1, 3], "clip": None},
        "scale": scale_layout, "required_lepton_sf": True,
        "ps_input_title": ps_title, "scale_input_title": scale_title,
        "normalization": "Signed all-input genWeight * pileup sums; no lepton SF in denominator",
    }
    if version >= 2:
        record["muon_efficiency_uncertainties"] = {
            "total": "nominal +/- hypot(stat, syst) for ID, isolation and trigger",
            "component_branches": sorted(MUON_COMPONENT_WEIGHT_BRANCHES),
            "normalization": "Nominal denominator; total and components are alternative models",
            "payload_content_sha256": MUON_SF_2024_SHA256,
        }
    if version >= 3:
        record["top_pt"] = top_pt_prescription(top_pt_enabled)
    return record


@lru_cache(maxsize=256)
def read_weight_prescription(
    filename: str, require_scale: bool, top_pt_enabled: bool = False,
) -> dict | None:
    with uproot.open(filename) as handle:
        tree = handle["Events"]
        if "genWeight" not in tree:  # Data has no generator-weight prescription.
            return None
        required = ["PSWeight"] + (["LHEScaleWeight"] if require_scale else [])
        missing = [name for name in required if name not in tree]
        if missing:
            raise ValueError(f"Missing required generator weights {missing} in {filename}")
        return prescription_from_titles(
            tree["PSWeight"].title, tree["LHEScaleWeight"].title if require_scale else None,
            top_pt_enabled=top_pt_enabled,
        )


def validate_weight_fileset(fileset: dict, year: str) -> None:
    if year != "2024":
        return
    for key, filenames in fileset.items():
        dataset = key.split("_", 1)[-1]
        reference = None
        first = True
        for filename in filenames:
            record = read_weight_prescription(str(filename), uses_scale_weights(dataset), is_ttbar(dataset))
            require_supported_sample(year, record is None)
            if not first and record != reference:
                raise ValueError(f"Inconsistent weight prescriptions in dataset {key}: {filename}")
            if record is not None:
                get_lepton_correctionsets(year)  # Fail before any output when a payload is missing.
            reference, first = record, False


def validate_scale_members(values, prescription: dict) -> None:
    """Reject empty, truncated or mixed event vectors even when the title is valid."""
    count = prescription["scale"]["input_members"]
    if not bool(ak.all(ak.num(values, axis=1) == count)):
        raise ValueError(f"LHEScaleWeight length disagrees with the {count}-member input title")


def weight_metadata_fields(prescription: dict) -> dict:
    encoded = json.dumps(prescription, sort_keys=True).encode("utf-8")
    return {"prescription_utf8": np.frombuffer(encoded, dtype=np.uint8)[None]}


def read_saved_prescription(handle) -> dict | None:
    tree = handle["Events"]
    marker = "WeightPrescriptionVersion"
    if "WeightMetadata" not in handle:
        if marker in tree:
            raise ValueError("WeightPrescriptionVersion has no WeightMetadata")
        return None  # Legacy-only campaigns remain readable, never mixed with this convention.
    rows = [row.tobytes().decode("utf-8") for row in
            handle["WeightMetadata"]["prescription_utf8"].array(library="np")]
    if not rows or len(set(rows)) != 1:
        raise ValueError("Missing or incompatible rows in WeightMetadata")
    record = json.loads(rows[0])
    if record != prescription_from_titles(
        record["ps_input_title"], record["scale_input_title"], record["version"],
        top_pt_enabled=record.get("top_pt", {}).get("enabled", False),
    ):
        raise ValueError("Unrecognized weight prescription")
    if marker not in tree or not np.all(tree[marker].array(library="np") == record["version"]):
        raise ValueError("Event weight version disagrees with WeightMetadata")
    if "Norm" not in handle or "np_nominal" not in handle["Norm"]:
        raise ValueError("Weight prescription has no all-input normalization")
    branches = set(tree.keys())  # Iterating a TTree itself yields TBranch objects.
    has_variations = any(name.startswith("weight_") and name != "weight_noxsec" for name in branches)
    if record["version"] >= 2 and has_variations:
        missing = MUON_COMPONENT_WEIGHT_BRANCHES - branches
        if missing:
            raise ValueError(f"Muon efficiency component variations missing: {sorted(missing)}")
    if record["scale"] is not None:
        if any(f"scale_weights{i}" not in tree for i in range(6)):
            raise ValueError("Scale columns missing from recorded weight prescription")
        if "np_scale_weights" not in handle["Norm"]:
            raise ValueError("Scale weights have no all-input normalization")
        sums = handle["Norm"]["np_scale_weights"].array(library="np")
        if sums.ndim != 2 or sums.shape[1] != 6 or not np.all(np.isfinite(sums)):
            raise ValueError("Invalid scale-weight normalization sums")
    if record["version"] >= 3:
        present = bool(branches & (set(SF_FUNCTIONS) | {"TopPtWeightValid"}))
        if present != record["top_pt"]["enabled"]:
            raise ValueError("Top-pT factor presence disagrees with the recorded sample policy")
        read_top_pt_normalization(handle)
    return record


def read_top_pt_normalization(handle) -> dict:
    """Validate version-3 top-pT factors/counts and every joint denominator.

    Return all-input sums over the ROOT's Norm rows, including after hadd.
    No positive-sum requirement is imposed on signed generator weights.
    """
    tree, norm = handle["Events"], handle["Norm"]
    branches, norm_names = set(tree.keys()), set(norm.keys())
    columns = set(SF_FUNCTIONS)
    count_names = {"n_top_pt_valid", "n_top_pt_invalid"}
    stored_sums = {name for name in norm_names if name.startswith("np_topPtWeight_")}
    if not branches & (columns | {"TopPtWeightValid"}):
        if stored_sums or norm_names & count_names:
            raise ValueError("Top-pT normalization has no event factors")
        return {}
    if not columns | {"TopPtWeightValid"} <= branches:
        raise ValueError("Incomplete top-pT factors or validity flag")
    if not count_names | {"n_input_events"} <= norm_names:
        raise ValueError("Missing all-input top-pT validity counts")
    expected = {}
    for name in norm_names - stored_sums:
        if not name.startswith("np_"):
            continue
        suffix = "" if name == "np_nominal" else "_" + name.removeprefix("np_")
        for column in columns:
            expected[f"np_{column}{suffix}"] = name
    if stored_sums != expected.keys():
        raise ValueError("Incomplete or unexpected joint top-pT normalization fields")
    result = {}
    for name, base in expected.items():
        values = norm[name].array(library="np")
        if values.shape != norm[base].array(library="np").shape or not np.all(np.isfinite(values)):
            raise ValueError(f"Invalid top-pT normalization shape or values: {name}")
        result[name] = np.sum(values, axis=0)
    counts = {name: norm[name].array(library="np") for name in count_names | {"n_input_events"}}
    if any(value.ndim != 1 or not np.all(np.isfinite(value) & (value >= 0) & (value == np.rint(value)))
           for value in counts.values()):
        raise ValueError("Invalid all-input top-pT event counts")
    if not np.array_equal(counts["n_top_pt_valid"] + counts["n_top_pt_invalid"], counts["n_input_events"]):
        raise ValueError("Top-pT counts do not cover every input event")
    valid = tree["TopPtWeightValid"].array(library="np")
    if valid.dtype != np.dtype(bool):
        raise ValueError("TopPtWeightValid must be a boolean flag")
    for column in columns:
        factors = tree[column].array(library="np")
        if not np.all(np.isfinite(factors)) or not np.all(factors[~valid] == 1.):
            raise ValueError(f"Invalid top-pT factors or fallback: {column}")
    if (np.sum(valid) > np.sum(counts["n_top_pt_valid"])
            or np.sum(~valid) > np.sum(counts["n_top_pt_invalid"])):
        raise ValueError("Selected top-pT validity counts exceed all-input counts")
    result.update({name: float(np.sum(value)) for name, value in counts.items()})
    if any(not np.all(np.isfinite(value)) for value in result.values()):
        raise ValueError("Nonfinite summed top-pT normalization")
    return result


def validate_weight_merge(paths) -> dict | None:
    reference = None
    first = True
    for path in paths:
        with uproot.open(path) as handle:
            record = read_saved_prescription(handle)
        if not first and record != reference:
            raise ValueError(f"Incompatible weight prescriptions before merge/normalization: {path}")
        reference, first = record, False
    return reference
