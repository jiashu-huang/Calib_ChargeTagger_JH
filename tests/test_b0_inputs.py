"""B0 acceptance, missing measurements, supervision and source identity."""

from __future__ import annotations

from uuid import UUID

import awkward as ak
import numpy as np
import pytest

from vcb.processors import b0_inputs as b0
from vcb.processors.objects import attach_jet_charge
from vcb.run import get_processor


def jet(index, pt=50.0, eta=0.0, **changes):
    return {"pt": pt, "mass": 5.0, "eta": eta, "phi": 0.1,
            "nanoIdx": index, "QkCharge05": 0.2, "QkCharge10": -0.1,
            **dict.fromkeys(b0.TAG_FIELDS.values(), 0.3), **changes}


def context(size):
    lepton = {f"TriggerLepton{k}": np.full(size, v) for k, v in
              {"Pt": 40.0, "Eta": 0.2, "Phi": 0.3, "Charge": -1, "Flav": 13}.items()}
    met = {"METPt": np.full(size, 50.0), "METPhi": np.full(size, -0.1)}
    gen = {name: np.full(size, i, dtype=np.int32)
           for i, name in enumerate(b0.ASSIGNMENT_FIELDS)}
    gen["GenWDecayValid"] = np.ones(size, dtype=bool)
    gen["GenNExtraBQuarksValid"] = np.zeros(size, dtype=bool)
    return lepton, met, gen


def test_acceptance_precedes_cap_and_equal_pt_uses_source_index():
    # Ten harder forward jets must not evict the four central reconstruction jets.
    jets = ak.Array([[jet(i, 100.0, 3.0) for i in range(10)]
                     + [jet(i) for i in (13, 11, 12, 10)]
                     + [jet(14, 25.0), jet(15, eta=2.4), jet(16, pt=np.nan)]])
    selected = b0.select_jets(jets)
    assert ak.to_list(selected.nanoIdx) == [[10, 11, 12, 13]]
    out = b0.build_columns(selected, *context(1))
    assert out["B0AssignmentMask"].tolist() == [True]
    assert out["B0Event_n_selected_jets"].tolist() == [4]
    assert out["B0JetMask"].sum() == 4


def test_qk_numerical_zero_is_valid_but_failures_and_padding_are_not():
    raw = np.array([[-997.0, -999.0, -998.0, np.nan, 0.0, -0.4, -99999.0]])
    value, valid = b0.decode_qk(raw, np.array([[True] * 6 + [False]]))
    assert valid.tolist() == [[True, False, False, False, True, True, False]]
    np.testing.assert_allclose(value, [[0, 0, 0, 0, 0, -0.4, 0]])
    assert raw[0, 0] == -997.0


def test_feature_masks_do_not_remove_jets_and_propagate_to_products():
    jets = ak.Array([[jet(0, QkCharge05=-997.0), jet(1, QkCharge05=-999.0),
                      jet(2, ParTPosvsAll=-1.0), jet(3, btagPNetB=np.nan)]])
    out = b0.build_columns(jets, *context(1))
    assert out["B0JetMask"].sum() == 4
    assert out["B0AssignmentMask"].tolist() == [True]  # Unknown extra-b truth is independent.
    assert out["B0Jet_Qk05_valid_"][0, 0]
    assert out["B0Jet_Qk05_"][0, 0] == 0
    assert not out["B0Jet_lepton_charge_times_Qk05_valid_"][0, 1]
    assert not out["B0Jet_lepton_charge_times_ParTPositiveMinusNegative_valid_"][0, 2]
    assert not out["B0Jet_PNetB_valid_"][0, 3]
    assert out["B0Jet_lepton_charge_times_Qk10_"][0, 0] == pytest.approx(0.1)
    assert ak.to_list(jets.QkCharge05)[0][0] == -997.0
    for name, values in out.items():
        assert np.all(np.isfinite(values)), name
    for feature in b0.JET_FEATURES:
        assert not out[f"B0Jet_{feature}_valid_"][0, 4:].any()
        assert not out[f"B0Jet_{feature}_"][0, 4:].any()


def test_overflow_uses_uncapped_selection_and_masks_missing_maximum():
    jets = ak.Array([[jet(i, 100.0-i, btagUParTAK4B=0.8 if i == 11 else -1.0)
                      for i in range(12)], [jet(i) for i in range(4)]])
    out = b0.build_columns(jets, *context(2))
    np.testing.assert_array_equal(out["B0Event_n_selected_jets"], [12, 4])
    np.testing.assert_array_equal(out["B0Event_n_overflow"], [2, 0])
    np.testing.assert_array_equal(out["B0Event_overflow_sum_pt"], [179, 0])
    np.testing.assert_allclose(out["B0Event_overflow_max_valid_UParTB"], [0.8, 0])
    np.testing.assert_array_equal(out["B0Event_overflow_max_valid_UParTB_valid"], [True, False])
    assert out["B0JetMask"].sum(axis=1).tolist() == [10, 4]
    assert out["B0Event_selected_HT"][0] == 1134


def test_assignment_mask_rejects_collision_padding_and_unknown_topology():
    jets = ak.Array([[jet(i) for i in range(4)] for _ in range(4)])
    lepton, met, gen = context(4)
    gen["GenHadQ2JetIdx"][:] = [3, 2, 4, 3]
    gen["GenWDecayValid"][3] = False
    out = b0.build_columns(jets, lepton, met, gen)
    assert out["B0AssignmentMask"].tolist() == [True, False, False, False]
    assert gen["GenWDecayValid"].tolist() == [True, True, True, False]


def test_absent_tag_or_charge_is_masked_without_changing_real_jet_count():
    jets = ak.Array([[jet(i) for i in range(4)]])
    jets = jets[[field for field in jets.fields if field not in ("btagPNetB", "QkCharge05")]]
    out = b0.build_columns(jets, *context(1))
    assert out["B0JetMask"].sum() == 4
    assert not out["B0Jet_PNetB_valid_"].any()
    assert not out["B0Jet_Qk05_valid_"].any()
    absent_events = ak.Array([{"other": 1}])
    with pytest.raises(KeyError, match="No `JetQk`"):
        attach_jet_charge(jets, absent_events)
    missing = attach_jet_charge(jets, absent_events, allow_missing=True)
    assert ak.to_list(ak.num(missing)) == [4]
    assert np.isnan(ak.to_numpy(ak.flatten(missing.QkCharge05))).all()


def test_empty_accepted_collection_is_all_padding_before_event_selection():
    jets = b0.select_jets(ak.Array([[jet(0, eta=4.0)]]))
    out = b0.build_columns(jets, *context(1))
    assert not out["B0JetMask"].any()
    assert out["B0Event_n_selected_jets"].tolist() == [0]
    assert not out["B0AssignmentMask"].any()
    assert not out["B0Event_overflow_max_valid_UParTB_valid"].any()


def test_source_uuid_and_entry_are_exact_and_profile_is_explicit():
    uuid = UUID("12345678-abcd-4321-8765-0123456789ab")
    meta = {"fileuuid": str(uuid), "entrystart": 110, "entrystop": 112}
    out = b0.source_columns(meta, 2)
    recovered = sum(int(word) << shift for word, shift in
                    zip(out["B0SourceUUID"][0], (96, 64, 32, 0), strict=True))
    assert recovered == uuid.int
    assert out["B0SourceEntry"].tolist() == [110, 111]
    with pytest.raises(ValueError, match="entry range"):
        b0.source_columns(meta, 3)
    processor = get_processor("skimmer", region="signal", input_profile="b0")
    assert processor._input_profile == "b0"
    assert get_processor("skimmer", region="signal")._input_profile == "calibration"
    schema = b0.schema_metadata()
    assert len(schema["jet_features"]) == 18
    assert len(schema["event_features"]) == 15
    assert not schema["source_identity_weights_truth_are_features"]
