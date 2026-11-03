"""Observable B0 inputs, masks and provenance for the 2024 ten-jet profile.

These columns are not standardized. Fit normalization on valid training entries
only, then set invalid standardized entries to zero using the saved masks.
Generator labels and source identity are metadata, never inference features.
"""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

import awkward as ak
import numpy as np

from boostedhh.processors.utils import PAD_VAL

from .GenSelection import NUM_JET_SLOTS
from .objects import QK_SENTINEL_MAX

SCHEMA_VERSION = 1
MAX_JETS = NUM_JET_SLOTS
MIN_JETS = 4
JET_PT_MIN = 25.0
JET_ABS_ETA_MAX = 2.4

TAG_FIELDS = {
    "PNetB": "btagPNetB",
    "ParTPosvsNeg": "ParTPosvsNeg",
    "UParTB": "btagUParTAK4B",
    "UParTCvL": "btagUParTAK4CvL",
    "UParTCvB": "btagUParTAK4CvB",
    "ParTPositive": "ParTPosvsAll",
    "ParTNegative": "ParTNegvsAll",
    "ParTZero": "ParTZerovsAll",
}
JET_FEATURES = (
    "log1p_pt", "log1p_mass", "eta", "sin_phi", "cos_phi",
    *TAG_FIELDS, "Qk05", "Qk10", "lepton_charge_times_Qk05",
    "lepton_charge_times_Qk10", "lepton_charge_times_ParTPositiveMinusNegative",
)
EVENT_FEATURES = (
    "lepton_log1p_pt", "lepton_eta", "lepton_sin_phi", "lepton_cos_phi",
    "lepton_charge", "lepton_is_electron", "lepton_is_muon",
    "MET_log1p_pt", "MET_sin_phi", "MET_cos_phi", "n_selected_jets",
    "selected_HT", "n_overflow", "overflow_sum_pt", "overflow_max_valid_UParTB",
)
ASSIGNMENT_FIELDS = ("GenHadBJetIdx", "GenLepBJetIdx", "GenHadQ1JetIdx", "GenHadQ2JetIdx")


def schema_metadata() -> dict:
    """Self-contained feature allowlist and interpretation, with a stable hash."""
    schema = {
        "schema_version": SCHEMA_VERSION,
        "profile": "b0",
        "era": "2024",
        "max_jets": MAX_JETS,
        "min_jets": MIN_JETS,
        "jet_pt_strict_min_GeV": JET_PT_MIN,
        "jet_abs_eta_strict_max": JET_ABS_ETA_MAX,
        "jet_order": "corrected pt descending; NanoAOD source index for exact ties",
        "jet_features": list(JET_FEATURES),
        "event_features": list(EVENT_FEATURES),
        "jet_value_pattern": "B0Jet_{feature}_{slot}",
        "jet_validity_pattern": "B0Jet_{feature}_valid_{slot}",
        "real_jet_pattern": "B0JetMask{slot}",
        "event_value_pattern": "B0Event_{feature}",
        "event_validity_pattern": "B0Event_{feature}_valid",
        "invalid_placeholder": 0.0,
        "normalization": "Fit on valid train entries only; mask to zero after standardizing.",
        "tag_validity": "finite and in [0,1]; absent, negative or nonfinite values are missing",
        "Qk_validity": "finite above -900, or -997 decoded to valid zero; raw fields unchanged",
        "Qk_zero_decision": "User approved 2026-10-28 after checking CMSSW_CHARGE producer.",
        "source_uuid": "B0SourceUUID0..3: four unsigned 32-bit words, most significant first",
        "source_entry": "B0SourceEntry: zero-based entry in the original input NanoAOD",
        "source_to_jet_mapping": "ak4JetNanoIdx{slot}; metadata only",
        "assignment_mask": "B0AssignmentMask shared by had_top and lep_top; four distinct real matches and valid W topology",
        "classification_masks": ["GenWDecayValid", "GenNExtraBQuarksValid"],
        "source_identity_weights_truth_are_features": False,
    }
    schema["schema_sha256"] = hashlib.sha256(
        json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return schema


def select_jets(jets: ak.Array) -> ak.Array:
    """Apply B0 acceptance to corrected, ID-selected and lepton-cleaned jets.

    Keep the full accepted collection until features and overflow summaries are
    computed. Both the feature writer and truth matcher subsequently use ten.
    """
    accepted = (
        np.isfinite(jets.pt) & np.isfinite(jets.eta)
        & (jets.pt > JET_PT_MIN) & (abs(jets.eta) < JET_ABS_ETA_MAX)
    )
    jets = jets[accepted]
    jets = jets[ak.argsort(jets.nanoIdx, axis=1, stable=True)]
    return jets[ak.argsort(jets.pt, axis=1, ascending=False, stable=True)]


def _slots(jets: ak.Array, field: str) -> np.ndarray:
    values = jets[field] if field in jets.fields else ak.full_like(jets.pt, np.nan)
    return ak.to_numpy(ak.fill_none(ak.pad_none(values, MAX_JETS, clip=True), np.nan))


def decode_qk(values: np.ndarray, real: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Decode the producer's numerical-zero sentinel; retain failures as missing."""
    valid = real & np.isfinite(values) & ((values > QK_SENTINEL_MAX) | (values == -997))
    return np.where(valid & (values != -997), values, 0.0), valid


def _observable(values: np.ndarray) -> np.ndarray:
    return np.isfinite(values) & (values != PAD_VAL)


def source_columns(metadata: dict, size: int) -> dict:
    """Preserve exact file/entry identity; event numbers alone are not unique MC IDs."""
    uuid = UUID(str(metadata["fileuuid"]))
    start, stop = metadata["entrystart"], metadata["entrystop"]
    if start < 0 or stop - start != size:
        raise ValueError("B0 source entry range does not match the event chunk")
    words = np.array([(uuid.int >> shift) & 0xFFFFFFFF for shift in (96, 64, 32, 0)],
                     dtype=np.uint32)
    return {
        "B0SourceUUID": np.broadcast_to(words, (size, 4)).copy(),
        "B0SourceEntry": np.arange(start, stop, dtype=np.uint64),
        "B0SchemaVersion": np.full(size, SCHEMA_VERSION, dtype=np.int32),
    }


def build_columns(jets: ak.Array, lepton: dict, met: dict, gen: dict) -> dict:
    """Build only the declared observables and separate supervision metadata."""
    count = ak.to_numpy(ak.num(jets))
    real = np.arange(MAX_JETS)[None, :] < count[:, None]
    out = {"B0JetMask": real}
    jet_values, jet_valid = {}, {}

    def jet_feature(name, values, valid):
        valid = valid & real & np.isfinite(values)
        values = np.where(valid, values, 0.0).astype(np.float32)
        jet_values[name], jet_valid[name] = values, valid
        out[f"B0Jet_{name}_"] = values
        out[f"B0Jet_{name}_valid_"] = valid

    def event_feature(name, values, valid):
        valid = np.asarray(valid, dtype=bool) & np.isfinite(values)
        out[f"B0Event_{name}"] = np.where(valid, values, 0.0).astype(np.float32)
        out[f"B0Event_{name}_valid"] = valid

    pt, mass, eta, phi = (_slots(jets, field) for field in ("pt", "mass", "eta", "phi"))
    for name, values in (("log1p_pt", pt), ("log1p_mass", mass)):
        valid = _observable(values) & (values >= 0)
        jet_feature(name, np.log1p(np.where(valid, values, 0.0)), valid)
    jet_feature("eta", eta, _observable(eta))
    jet_feature("sin_phi", np.sin(phi), _observable(phi))
    jet_feature("cos_phi", np.cos(phi), _observable(phi))
    for name, field in TAG_FIELDS.items():
        values = _slots(jets, field)
        jet_feature(name, values, (values >= 0) & (values <= 1))
    for name, field in (("Qk05", "QkCharge05"), ("Qk10", "QkCharge10")):
        values, valid = decode_qk(_slots(jets, field), real)
        jet_feature(name, values, valid)

    charge = lepton["TriggerLeptonCharge"]
    charge_valid = _observable(charge) & (abs(charge) == 1)
    for name in ("Qk05", "Qk10"):
        jet_feature(f"lepton_charge_times_{name}", charge[:, None] * jet_values[name],
                    charge_valid[:, None] & jet_valid[name])
    jet_feature("lepton_charge_times_ParTPositiveMinusNegative",
                charge[:, None] * (jet_values["ParTPositive"] - jet_values["ParTNegative"]),
                charge_valid[:, None] & jet_valid["ParTPositive"] & jet_valid["ParTNegative"])

    lpt, leta, lphi, flavor = (lepton[f"TriggerLepton{x}"] for x in ("Pt", "Eta", "Phi", "Flav"))
    valid = _observable(lpt) & (lpt > 0)
    event_feature("lepton_log1p_pt", np.log1p(np.where(valid, lpt, 0.0)), valid)
    event_feature("lepton_eta", leta, _observable(leta))
    event_feature("lepton_sin_phi", np.sin(lphi), _observable(lphi))
    event_feature("lepton_cos_phi", np.cos(lphi), _observable(lphi))
    event_feature("lepton_charge", charge, charge_valid)
    flavor_valid = (flavor == 11) | (flavor == 13)
    event_feature("lepton_is_electron", flavor == 11, flavor_valid)
    event_feature("lepton_is_muon", flavor == 13, flavor_valid)
    mpt, mphi = met["METPt"], met["METPhi"]
    valid = _observable(mpt) & (mpt >= 0)
    event_feature("MET_log1p_pt", np.log1p(np.where(valid, mpt, 0.0)), valid)
    event_feature("MET_sin_phi", np.sin(mphi), _observable(mphi))
    event_feature("MET_cos_phi", np.cos(mphi), _observable(mphi))

    always_valid = np.ones(len(jets), dtype=bool)
    overflow = jets[:, MAX_JETS:]
    event_feature("n_selected_jets", count, always_valid)
    event_feature("selected_HT", ak.to_numpy(ak.sum(jets.pt, axis=1)), always_valid)
    event_feature("n_overflow", np.maximum(count - MAX_JETS, 0), always_valid)
    event_feature("overflow_sum_pt", ak.to_numpy(ak.sum(overflow.pt, axis=1)), always_valid)
    b = overflow.btagUParTAK4B if "btagUParTAK4B" in jets.fields else ak.full_like(overflow.pt, np.nan)
    b_valid = np.isfinite(b) & (b >= 0) & (b <= 1)
    max_b = ak.max(b[b_valid], axis=1, mask_identity=True)
    event_feature("overflow_max_valid_UParTB", ak.to_numpy(ak.fill_none(max_b, 0.0)),
                  ak.to_numpy(ak.any(b_valid, axis=1)))

    assignment = np.column_stack([gen[field] for field in ASSIGNMENT_FIELDS])
    full = np.all((assignment >= 0) & (assignment < np.minimum(count, MAX_JETS)[:, None]), axis=1)
    full &= np.all(np.diff(np.sort(assignment, axis=1), axis=1) != 0, axis=1)
    out["B0AssignmentMask"] = full & gen["GenWDecayValid"].astype(bool)
    assert set(jet_values) == set(JET_FEATURES)
    return out
