"""Read-only postprocessing: population definitions, masses and malformed inputs."""

from __future__ import annotations

import hashlib
import json
import shutil

import numpy as np
import pytest
import uproot

from vcb.postprocessing.matching import (
    GEOMETRY_FIELDS,
    INDEX_FIELDS,
    analyze_chunk,
    main,
    summarize,
)


def skim_arrays():
    # Full; hadronic-only; W-only; unmatched; full with an invalid W truth label.
    indices = np.array([[0, 1, 2, 3], [0, -1, 2, 3], [-1, 1, 2, 3],
                        [-1, -1, -1, -1], [0, 1, 2, 3]], dtype=np.int32)
    out = {name: indices[:, i].copy() for i, name in enumerate(INDEX_FIELDS)}
    out.update(nJets=np.full(5, 4, dtype=np.int32),
               B0AssignmentMask=np.array([True, False, False, False, False]),
               GenWDecayValid=np.array([True, True, True, True, False]))
    pt = [(172.5 ** 2 - 80 ** 2) / 160, 30, 40, 40]
    phi = [np.pi / 2, -np.pi / 2, 0, np.pi]
    for slot in range(4):
        for name, value in {"Pt": pt[slot], "Eta": 0, "Phi": phi[slot], "Mass": 0}.items():
            out[f"ak4Jet{name}{slot}"] = np.full(5, value, dtype=np.float64)
        out[f"B0JetMask{slot}"] = np.ones(5, dtype=bool)
    for i, name in enumerate(GEOMETRY_FIELDS):
        out[name] = np.full(5, 0 if name.endswith("Eta") else phi[i // 2], dtype=float)
    return out


def write_skim(path, arrays=None):
    with uproot.recreate(path) as output:
        output["Events"] = skim_arrays() if arrays is None else arrays
    return path


def test_inclusive_and_exclusive_matching_counts_and_analytic_masses(tmp_path):
    path = write_skim(tmp_path / "skim.root")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = summarize({"TT": [str(path)]}, step_size=2)["samples"]["TT"]
    assert result["counts"] == {
        "events_in_processed_files": 5, "fully_matched": 2, "hadronic_top_matched": 3,
        "hadronic_top_only": 1, "w_pair_matched": 4, "b0_mask_checked_events": 5,
        "b0_assignment_eligible": 1,
    }
    assert result["matched_by_role"] == {"HadB": 3, "LepB": 3, "HadQ1": 4, "HadQ2": 4}
    assert result["events_by_number_of_matched_partons"] == [1, 0, 0, 2, 2]
    assert result["fractions_of_processed_events"]["hadronic_top_matched"] == .6
    assert result["checks"]["delta_r_checked_assignments"] == 14
    assert result["checks"]["maximum_delta_r"] == 0
    masses = analyze_chunk(skim_arrays(), 4)[-1]
    np.testing.assert_allclose(masses["hadronic_top_matched"]["W"], [80] * 3)
    np.testing.assert_allclose(masses["hadronic_top_matched"]["top"], [172.5] * 3)
    assert len(masses["fully_matched"]["W"]) == 2
    for population in ("fully_matched", "hadronic_top_matched"):
        for hist in result["histograms"][population].values():
            assert sum(hist["counts"]) == result["counts"][population]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_no_b0_fields_no_generator_directions_and_no_new_pt_cut(tmp_path):
    arrays = {key: value for key, value in skim_arrays().items()
              if not key.startswith("B0") and key not in GEOMETRY_FIELDS}
    arrays["ak4JetPt2"][:] = 20  # Must remain matched: no B0 pT>25 reselection here.
    path = write_skim(tmp_path / "calibration.root", arrays)
    result = summarize({"calibration": [str(path)]})["samples"]["calibration"]
    assert result["counts"]["fully_matched"] == 2
    assert result["counts"]["b0_mask_checked_events"] == 0
    assert result["checks"]["maximum_delta_r"] is None
    assert not result["files"][0]["generator_directions_available"]


def test_unordered_w_pair():
    arrays = skim_arrays()
    original = analyze_chunk(arrays, 4)[-1]
    arrays["GenHadQ1JetIdx"], arrays["GenHadQ2JetIdx"] = (
        arrays["GenHadQ2JetIdx"], arrays["GenHadQ1JetIdx"])
    for coordinate in ("Eta", "Phi"):
        arrays[f"GenQ1{coordinate}"], arrays[f"GenQ2{coordinate}"] = (
            arrays[f"GenQ2{coordinate}"], arrays[f"GenQ1{coordinate}"])
    swapped = analyze_chunk(arrays, 4)[-1]
    for population in original:
        for mass in original[population]:
            np.testing.assert_allclose(original[population][mass], swapped[population][mass])


@pytest.mark.parametrize(("branch", "value", "message"), [
    ("GenHadBJetIdx", 4, "outside"),
    ("GenHadBJetIdx", -2, "outside"),
    ("GenHadBJetIdx", 1, "Duplicate assigned jet"),
    ("nJets", 3, "beyond nJets"),
    ("ak4JetPt0", -99999, "four-vector"),
    ("ak4JetEta0", np.nan, "four-vector"),
    ("ak4JetMass0", -1, "four-vector"),
    ("B0JetMask0", False, "false B0JetMask"),
    ("B0AssignmentMask", False, "B0AssignmentMask differs"),
    ("GenHadTopBEta", .41, "DeltaR"),
])
def test_invalid_assignments_are_errors(branch, value, message):
    arrays = skim_arrays()
    arrays[branch][0] = value
    with pytest.raises(ValueError, match=message):
        analyze_chunk(arrays, 4)


def test_noninteger_indices_and_partial_schema(tmp_path):
    arrays = skim_arrays()
    arrays["GenHadBJetIdx"] = arrays["GenHadBJetIdx"].astype(float)
    with pytest.raises(ValueError, match="integer"):
        analyze_chunk(arrays, 4)
    del arrays["GenQ1Eta"]
    path = write_skim(tmp_path / "incomplete.root", arrays)
    with pytest.raises(ValueError, match="Incomplete saved generator"):
        summarize({"bad": [str(path)]})


def test_chunking_and_multiple_files_give_same_result(tmp_path):
    arrays = skim_arrays()
    whole = write_skim(tmp_path / "whole.root", arrays)
    first = write_skim(tmp_path / "first.root", {key: val[:2] for key, val in arrays.items()})
    second = write_skim(tmp_path / "second.root", {key: val[2:] for key, val in arrays.items()})
    a = summarize({"TT": [str(whole)]}, step_size=100)["samples"]["TT"]
    b = summarize({"TT": [str(first), str(second)]}, step_size=1)["samples"]["TT"]
    for key in ("counts", "matched_by_role", "events_by_number_of_matched_partons",
                "checks", "histograms", "fractions_of_processed_events"):
        assert a[key] == b[key]


def test_duplicate_paths_and_root_copies_are_rejected(tmp_path):
    path = write_skim(tmp_path / "input.root")
    with pytest.raises(ValueError, match="Duplicate input path"):
        summarize({"TT": [str(path), str(path)]})
    copy = tmp_path / "copy.root"
    shutil.copyfile(path, copy)
    with pytest.raises(ValueError, match="Duplicate ROOT UUID"):
        summarize({"TT": [str(path), str(copy)]})
    with pytest.raises(ValueError, match="Duplicate input path across samples"):
        summarize({"TT": [str(path)], "TTBB": [str(path)]})


def test_empty_and_no_matches_are_valid_and_cli_writes_all_artifacts(tmp_path):
    arrays = skim_arrays()
    empty = write_skim(tmp_path / "empty.root", {key: val[:0] for key, val in arrays.items()})
    unmatched = write_skim(tmp_path / "unmatched.root", {key: val[3:4]
                                                       for key, val in arrays.items()})
    out = tmp_path / "report"
    main(["--sample", f"empty={empty}", "--sample", f"unmatched={unmatched}", "--outdir", str(out)])
    report = json.loads((out / "matching_summary.json").read_text())
    assert report["samples"]["empty"]["counts"]["events_in_processed_files"] == 0
    assert report["samples"]["empty"]["fractions_of_processed_events"]["fully_matched"] is None
    assert report["samples"]["unmatched"]["counts"]["events_in_processed_files"] == 1
    assert "N/A" in (out / "matching_summary.txt").read_text()
    for name in ("fully_matched_masses", "hadronic_top_matched_masses"):
        for extension in ("png", "pdf"):
            assert (out / f"{name}.{extension}").stat().st_size > 100
    with pytest.raises(SystemExit):
        main(["--files", str(empty), "--outdir", str(out)])


def test_mass_overflows_are_counted_without_removing_events(tmp_path):
    arrays = skim_arrays()
    for key in arrays:
        if key.startswith("ak4JetPt"):
            arrays[key] *= 10
    path = write_skim(tmp_path / "overflow.root", arrays)
    result = summarize({"TT": [str(path)]})["samples"]["TT"]
    for population in ("fully_matched", "hadronic_top_matched"):
        for hist in result["histograms"][population].values():
            assert hist["overflow"] == result["counts"][population]
            assert sum(hist["counts"]) == 0
