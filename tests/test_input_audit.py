"""C1 populations keep unmatched events, unknown truth and charge zeros distinct."""

from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest

from vcb.postprocessing.input_audit import merge_summaries, render_summary, summarize_rows


def fixture():
    schema = {"max_jets": 10, "schema_sha256": "test-schema",
              "jet_features": ["Qk05"], "event_features": ["overflow_max_valid_UParTB"]}
    rows = {"GenWDecay": np.array([0, 1, -1, 1]),
            "GenNExtraBQuarks": np.array([2, 0, -1, 2]),
            "GenWDecayValid": np.array([True, True, False, True]),
            "GenNExtraBQuarksValid": np.array([True, True, False, True]),
            "GenNExtraBQuarksStatus": np.array([0, 0, 3, 0]),
            "GenWLeptonFlavor": np.array([11, 13, 15, 13]),
            "B0AssignmentMask": np.array([True, False, False, True]),
            "nJets": np.array([4, 4, 4, 12]),
            "B0Event_overflow_max_valid_UParTB": np.array([0., 0., 0., .8]),
            "B0Event_overflow_max_valid_UParTB_valid": np.array([False, False, False, True])}
    for slot in range(10):
        real = slot < np.minimum(rows["nJets"], 10)
        rows[f"B0JetMask{slot}"] = real
        rows[f"B0Jet_Qk05_valid_{slot}"] = real.copy()
        rows[f"B0Jet_Qk05_{slot}"] = np.where(real, .5, 0.)
        rows[f"ak4JetQkCharge05_{slot}"] = np.where(real, .5, -99999.)
        rows[f"ak4JetQkCharge10_{slot}"] = np.where(real, .5, -99999.)
    rows["B0Jet_Qk05_0"][0:2] = 0.
    rows["ak4JetQkCharge05_0"][0:2] = [-997., -999.]
    rows["B0Jet_Qk05_valid_0"][1] = False
    for slot, role in enumerate(("HadB", "LepB", "HadQ1", "HadQ2")):
        rows[f"Gen{role}JetIdx"] = np.full(4, slot)
    rows["GenLepBJetIdx"][1] = -1
    return rows, schema


def test_populations_include_unknown_and_unmatched_events():
    rows, schema = fixture()
    result = summarize_rows(rows, schema)
    assert result["counts"]["selected"] == 4
    assert result["counts"]["fully_matched"] == 3
    assert result["counts"]["assignment_eligible"] == 2
    assert result["counts"]["hadronic_top_matched"] == 4
    assert result["counts"]["unmatched_with_extra_b_label"] == 1
    assert result["counts"]["overflow_jets"] == 2
    assert result["counts"]["fully_matched_with_overflow"] == 1
    assert result["histograms"]["extra_b_quarks"] == {"-1": 1, "0": 1, "2": 2}
    assert result["joint_truth"]["W=1,extra_b=2"]["assignment_eligible"] == 1
    assert result["features"]["jet/Qk05"] == {
        "eligible": 22, "valid": 21, "missing": 1, "valid_zero": 1,
        "minimum": 0., "maximum": .5}
    assert result["charge_sentinels"]["QkCharge05"] == {"-997": 1, "-998": 0, "-999": 1}


def test_event_labels_use_independent_validity():
    rows, schema = fixture()
    rows["GenNExtraBQuarks"][2] = 4
    rows["GenNExtraBQuarksValid"][2] = True
    rows["GenNExtraBQuarksStatus"][2] = 0
    result = summarize_rows(rows, schema)
    assert result["counts"]["extra_b_label_valid"] == 4
    assert result["counts"]["W_label_valid"] == 3
    assert result["counts"]["unmatched_with_extra_b_label"] == 2


@pytest.mark.parametrize(("field", "value"), [("GenNExtraBQuarks", 0), ("GenWDecay", 0),
                                              ("B0AssignmentMask", True)])
def test_invalid_truth_and_assignment_masks_fail(field, value):
    rows, schema = fixture()
    rows[field][2] = value
    with pytest.raises(ValueError, match="disagree"):
        summarize_rows(rows, schema)


def test_aggregation_preserves_counts_ranges_and_empty_populations():
    rows, schema = fixture()
    whole = summarize_rows(rows, schema)
    pieces = [summarize_rows({key: value[part] for key, value in rows.items()}, schema)
              for part in (slice(0, 1), slice(1, 4), slice(0, 0))]
    assert merge_summaries(pieces) == whole
    assert "selected: 4" in render_summary(whole)
    wrong = deepcopy(whole)
    wrong["schema_sha256"] = "other"
    with pytest.raises(ValueError, match="schemas differ"):
        merge_summaries([whole, wrong])
    with pytest.raises(ValueError, match="No input summaries"):
        merge_summaries([])


def test_missing_features_do_not_count_padding():
    rows, schema = fixture()
    rows["B0Jet_Qk05_valid_9"][0] = True
    with pytest.raises(ValueError, match="padding"):
        summarize_rows(rows, schema)


def b_jet_fixture():
    rows, schema = fixture()
    schema["schema_version"] = 2
    rows["RecoNBJets"] = np.array([2, 2, -1, 4])
    rows["RecoNBJetsValid"] = np.array([True, True, False, True])
    rows["GenNBJets"] = np.array([2, 3, 2, 4])
    rows["GenNBJetsValid"] = np.ones(4, dtype=bool)
    for slot in range(10):
        rows[f"B0JetIsBValid{slot}"] = rows[f"B0JetMask{slot}"].copy()
        rows[f"B0JetIsB{slot}"] = rows[f"B0JetMask{slot}"] & (slot < 2)
    rows["B0JetIsBValid3"][2] = False
    return rows, schema


def test_b_jet_audit_counts_overflow_and_keeps_reco_and_gen_separate():
    rows, schema = b_jet_fixture()
    result = summarize_rows(rows, schema)
    assert result["counts"]["retained_b_jets"] == 8
    assert result["counts"]["overflow_b_jets_in_valid_events"] == 2
    assert result["counts"]["retained_jets_with_unknown_b_truth"] == 1
    assert result["histograms"]["reco_b_jets"] == {"-1": 1, "2": 2, "4": 1}
    assert result["histograms"]["reco_vs_gen_b_jets"]["reco=2,gen=3"] == 1
    parts = [summarize_rows({key: value[part] for key, value in rows.items()}, schema)
             for part in (slice(0, 2), slice(2, 4), slice(0, 0))]
    assert merge_summaries(parts) == result


@pytest.mark.parametrize(("field", "index", "value"), [
    ("RecoNBJets", 0, 3),  # No overflow: cannot have more b jets than retained.
    ("RecoNBJets", 3, 5),  # Only two overflow slots exist.
    ("RecoNBJets", 2, 0),  # Unknown must not look like zero.
    ("B0JetIsBValid9", 0, True),  # Padding must be invalid.
    ("B0JetIsB3", 2, True),  # Unknown flavour cannot be labelled b.
])
def test_b_jet_audit_rejects_inconsistent_truth(field, index, value):
    rows, schema = b_jet_fixture()
    rows[field][index] = value
    with pytest.raises(ValueError, match=r"disagree|Invalid per-jet"):
        summarize_rows(rows, schema)
