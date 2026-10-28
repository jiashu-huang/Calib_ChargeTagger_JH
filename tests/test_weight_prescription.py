"""Signed generator alternatives, released PU factors and campaign compatibility."""

from __future__ import annotations

from types import SimpleNamespace

import awkward as ak
import correctionlib
import numpy as np
import pytest
import uproot
from coffea.analysis_tools import Weights

from boostedhh.processors import corrections
from vcb.processors import lepton_sf
from vcb.processors.skim_metadata import save_chunk_metadata, write_root_metadata
from vcb.processors.top_pt import SF_FUNCTIONS
from vcb.processors.weight_prescription import (
    WEIGHT_PRESCRIPTION_VERSION,
    prescription_from_titles,
    read_saved_prescription,
    read_top_pt_normalization,
    require_supported_sample,
    validate_scale_members,
    validate_weight_fileset,
    validate_weight_merge,
    weight_metadata_fields,
)

PS_TITLE = ("PS weights (w_var / w_nominal) [0] isr.murfac=2.0; [1] fsr.murfac=2.0; "
            "[2] isr.murfac=0.5; [3] fsr.murfac=0.5; ")


def scale_title(count=9):
    pairs = [(r, f) for r in (.5, 1, 2) for f in (.5, 1, 2)]
    if count == 8:
        pairs.pop(4)
    return "LHE scale variation weights (w_var / w_nominal); " + "; ".join(
        f"[{i}] is renscfact={r}d0 facscfact={f}d0" for i, (r, f) in enumerate(pairs)
    )


def test_pileup_preserves_released_tail_and_payload_flow():
    interactions = np.array([-1., 40., 74., 99.5, 120.])
    weights = Weights(len(interactions), storeIndividual=True)
    corrections.add_pileup_weight(weights, "2024", interactions)
    cset = correctionlib.CorrectionSet.from_file(
        corrections.package_path + "/corrections/2024_puWeights.json.gz"
    )
    corr = cset[next(iter(cset))]
    for direction, modifier in [("nominal", None), ("up", "pileupUp"), ("down", "pileupDown")]:
        np.testing.assert_allclose(weights.weight(modifier), corr.evaluate(interactions, direction))
    assert weights.weight()[2] > 10
    assert weights.weight("pileupUp")[2] > 100
    np.testing.assert_array_equal(interactions, [-1., 40., 74., 99.5, 120.])
    with pytest.raises(ValueError, match="finite value per event"):
        corrections.add_pileup_weight(weights, "2024", np.full(len(interactions), np.nan))


def test_ps_scale_direction_signed_values_and_input_immutability():
    ratios = np.array([[2., 3., -4., 0.], [5., -6., 0., 8.]])
    source = ak.Array(ratios.copy())
    weights = Weights(2)
    weights.add("generator", np.array([-2., 3.]))
    corrections.add_ps_weight(weights, source)
    for name, index in [("ISRPartonShowerUp", 0), ("FSRPartonShowerUp", 1),
                        ("ISRPartonShowerDown", 2), ("FSRPartonShowerDown", 3)]:
        np.testing.assert_array_equal(weights.weight(name), [-2., 3.] * ratios[:, index])
    np.testing.assert_array_equal(ak.to_numpy(source), ratios)


@pytest.mark.parametrize("values", [[[1.]], [[1., 1., 1., 1.], []], [[np.nan, 1., 1., 1.]]])
def test_invalid_ps_weights_never_become_unity(values):
    with pytest.raises(ValueError, match="PSWeight"):
        corrections.add_ps_weight(Weights(len(values)), ak.Array(values))


@pytest.mark.parametrize("count", [8, 9])
def test_scale_ratios_keep_sign_zero_and_tail_with_correct_central(count):
    # Same physical alternatives with/without an explicit nonunit central member.
    ratios = np.array([[-2., 0., 3., 5., 2., 14., 7., 18., 20.]], dtype=np.float32)
    if count == 8:
        ratios = np.delete(ratios / 2, 4, axis=1)
    source = ak.Array(ratios.copy())
    result = corrections.get_scale_weights(SimpleNamespace(LHEScaleWeight=source))
    np.testing.assert_array_equal(result, [[-1., 0., 2.5, 7., 9., 10.]])
    np.testing.assert_array_equal(ak.to_numpy(source), ratios)
    validate_scale_members(source, prescription_from_titles(PS_TITLE, scale_title(count)))


@pytest.mark.parametrize(("values", "match"), [
    ([[1.] * 7], "eight or nine"),
    ([[1.] * 9, [1.] * 8], "eight or nine"),
    ([[1.] * 9, []], "eight or nine"),
    ([[1.] * 4 + [0.] + [1.] * 4], "zero central"),
    ([[np.inf] + [1.] * 8], "Nonfinite"),
])
def test_invalid_scale_ratios_fail(values, match):
    with pytest.raises(ValueError, match=match):
        corrections.get_scale_weights(SimpleNamespace(LHEScaleWeight=ak.Array(values)))


def test_titles_and_lengths_must_agree_not_just_vector_sizes():
    record = prescription_from_titles(PS_TITLE, scale_title())
    assert record["ps"]["Up"] == "muR x2"
    assert record["scale"]["saved_muR_muF"] == [[.5, .5], [.5, 1.], [1., .5],
                                               [1., 2.], [2., 1.], [2., 2.]]
    for title in ["four weights", PS_TITLE.replace("[0] isr.murfac=2.0", "[0] isr.murfac=0.5")]:
        with pytest.raises(ValueError, match="PSWeight"):
            prescription_from_titles(title, scale_title())
    with pytest.raises(ValueError, match="LHEScaleWeight"):
        prescription_from_titles(PS_TITLE, scale_title().replace("[0]", "[8]"))
    for members in [[], [1.] * 8]:
        with pytest.raises(ValueError, match="length disagrees"):
            validate_scale_members(ak.Array([members]), record)


def _root(path, record, rows=1, marker=True):
    with uproot.recreate(path) as handle:
        fields = {"weight": np.ones(rows)}
        if marker:
            version = record["version"] if record is not None else WEIGHT_PRESCRIPTION_VERSION
            fields["WeightPrescriptionVersion"] = np.full(rows, version, dtype=np.uint8)
        fields.update({f"scale_weights{i}": np.ones(rows) for i in range(6)})
        handle["Events"] = fields
        handle["Norm"] = {"np_nominal": np.array([2.]), "np_scale_weights": np.ones((1, 6))}
        if record is not None:
            handle["WeightMetadata"] = weight_metadata_fields(record)


def test_merge_rejects_legacy_mixtures_missing_metadata_and_changed_prescriptions(tmp_path):
    record = prescription_from_titles(PS_TITLE, scale_title())
    a, b = tmp_path / "a.root", tmp_path / "b.root"
    _root(a, record)
    _root(b, record, rows=0)
    assert validate_weight_merge([a, b]) == record
    _root(b, None, marker=False)
    with pytest.raises(ValueError, match="Incompatible weight prescriptions"):
        validate_weight_merge([a, b])
    assert validate_weight_merge([b]) is None
    _root(b, None, rows=0)
    with pytest.raises(ValueError, match="has no WeightMetadata"):
        validate_weight_merge([a, b])
    _root(b, {**record, "pileup": {"clip": 10}})
    with pytest.raises(ValueError, match="Unrecognized"):
        validate_weight_merge([a, b])


def test_all_merged_metadata_rows_are_checked(tmp_path):
    record = prescription_from_titles(PS_TITLE, scale_title())
    path = tmp_path / "merged.root"
    _root(path, record)
    a = weight_metadata_fields(record)["prescription_utf8"]
    b = weight_metadata_fields({**record, "version": 1})["prescription_utf8"]
    with uproot.update(path) as handle:
        handle["WeightMetadata"] = {"prescription_utf8": np.concatenate([a, b])}
    with pytest.raises(ValueError, match="incompatible rows"):
        validate_weight_merge([path])


def test_empty_chunk_persists_prescription_and_normalization(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOSTEDHH_OUTPARQUET_DIR", str(tmp_path))
    record = prescription_from_titles(PS_TITLE, scale_title())
    path = tmp_path / "chunk.parquet"
    save_chunk_metadata(path.name, "2024", "TTtoLNuCB", {
        "np_nominal": -2., "np_scale_weights": [-3., 0., 1., 5., -4., 8.],
    }, weight_prescription=record)
    root = tmp_path / "empty.root"
    _root(root, None, rows=0)
    with uproot.update(root) as handle:
        write_root_metadata(handle, [path])
    with uproot.open(root) as handle:
        assert read_saved_prescription(handle) == record
        assert handle["Norm"]["np_nominal"].array(library="np")[0] == -2.


def test_missing_required_lepton_payload_fails_preflight(tmp_path, monkeypatch):
    from vcb.processors import weight_prescription

    record = prescription_from_titles(PS_TITLE, scale_title())
    monkeypatch.setattr(weight_prescription, "read_weight_prescription", lambda *_: record)
    monkeypatch.setitem(lepton_sf.LEPTON_SF_SOURCES, "2024", {
        "muon": (str(tmp_path / "missing-bundled.gz"), str(tmp_path / "missing-fallback.gz")),
    })
    with pytest.raises(FileNotFoundError, match="Required Lepton SF 2024 muon"):
        validate_weight_fileset({"2024_TTtoLNuCB": ["input.root"]}, "2024")


def test_lepton_payload_fallback_still_works(tmp_path):
    cset = lepton_sf._load_correctionset(
        str(tmp_path / "missing.gz"),
        str(lepton_sf.package_path / "corrections/2024_electron.json.gz"), "test electron SF",
    )
    assert lepton_sf.EGM_ID_CORRECTION in cset


def test_v1_remains_readable_but_cannot_mix_with_new_muon_uncertainties(tmp_path):
    v1 = prescription_from_titles(PS_TITLE, scale_title(), version=1)
    v2 = prescription_from_titles(PS_TITLE, scale_title())
    a, b = tmp_path / "v1.root", tmp_path / "v2.root"
    _root(a, v1)
    _root(b, v2)
    assert validate_weight_merge([a]) == v1
    assert validate_weight_merge([b]) == v2
    with pytest.raises(ValueError, match="Incompatible weight prescriptions"):
        validate_weight_merge([a, b])


def test_v2_remains_readable_but_cannot_mix_with_top_pt_preservation(tmp_path):
    a, b = tmp_path / "v2.root", tmp_path / "v3.root"
    v2 = prescription_from_titles(PS_TITLE, scale_title(), version=2)
    v3 = prescription_from_titles(PS_TITLE, scale_title())
    _root(a, v2)
    _root(b, v3)
    assert validate_weight_merge([a]) == v2
    with pytest.raises(ValueError, match="Incompatible weight prescriptions"):
        validate_weight_merge([a, b])


def _top_pt_root(path, *, mutation=None, empty=False):
    record = prescription_from_titles(PS_TITLE, scale_title(), top_pt_enabled=True)
    fields = {"weight": np.ones(2), "WeightPrescriptionVersion": np.full(2, 3, dtype=np.uint8),
              "TopPtWeightValid": np.array([True, False])}
    fields.update({name: np.array([.5, 1.]) for name in SF_FUNCTIONS})
    fields.update({f"scale_weights{i}": np.ones(2) for i in range(6)})
    norm = {"np_nominal": np.array([-2.]), "np_scale_weights": np.ones((1, 6)),
            "nevents": np.array([-2.5]), "n_input_events": np.array([3.]),
            "n_top_pt_valid": np.array([2.]), "n_top_pt_invalid": np.array([1.])}
    for name in SF_FUNCTIONS:
        norm[f"np_{name}"] = np.array([-3.])
        norm[f"np_{name}_scale_weights"] = np.full((1, 6), -4.)
    if mutation:
        mutation(fields, norm)
    if empty:
        fields = {key: value[:0] for key, value in fields.items()}
    with uproot.recreate(path) as handle:
        handle["Events"] = fields
        handle["Norm"] = norm
        handle["WeightMetadata"] = weight_metadata_fields(record)
    return record


@pytest.mark.parametrize("empty", [False, True])
def test_top_pt_metadata_preserves_signed_sums_and_empty_selection(tmp_path, empty):
    path = tmp_path / "top.root"
    record = _top_pt_root(path, empty=empty)
    with uproot.open(path) as handle:
        assert read_saved_prescription(handle) == record
        sums = read_top_pt_normalization(handle)
    assert sums["np_topPtWeight_NNLONLO_13p6TeV"] == -3.
    assert sums["n_top_pt_valid"] == 2.
    assert sums["n_input_events"] == 3.  # Legacy nevents is a signed generator-weight sum.
    np.testing.assert_array_equal(sums["np_topPtWeight_NNLONLO_13p6TeV_scale_weights"], np.full(6, -4.))


@pytest.mark.parametrize(("mutation", "match"), [
    (lambda fields, _norm: fields.pop("TopPtWeightValid"), "Incomplete top-pT"),
    (lambda fields, _norm: fields.update(TopPtWeightValid=np.array([1., 0.])), "boolean"),
    (lambda fields, _norm: fields.update(topPtWeight_dataNLO=np.array([.5, .7])), "fallback"),
    (lambda _fields, norm: norm.pop("np_topPtWeight_dataNLO_scale_weights"), "joint top-pT"),
    (lambda _fields, norm: norm.update(np_topPtWeight_dataNLO=np.array([np.inf])), "Invalid top-pT"),
    (lambda _fields, norm: norm.update(np_topPtWeight_dataNLO_scale_weights=np.ones((1, 5))), "shape"),
    (lambda _fields, norm: norm.update(n_top_pt_invalid=np.array([0.])), "cover every input"),
])
def test_incomplete_or_corrupt_top_pt_records_fail(tmp_path, mutation, match):
    path = tmp_path / "bad.root"
    _top_pt_root(path, mutation=mutation)
    with pytest.raises(ValueError, match=match):
        validate_weight_merge([path])


def test_new_systematic_output_requires_all_muon_components(tmp_path):
    record = prescription_from_titles(PS_TITLE, scale_title())
    path = tmp_path / "incomplete.root"
    _root(path, record)
    with uproot.open(path) as handle:
        fields = handle["Events"].arrays(library="np")
    fields["weight_pileupUp"] = np.ones(1)
    with uproot.update(path) as handle:
        handle["Events"] = fields
    with pytest.raises(ValueError, match="component variations missing"):
        validate_weight_merge([path])


def test_incomplete_2024_data_path_is_rejected_before_processing(monkeypatch):
    from vcb.processors import weight_prescription

    require_supported_sample("2024", False)
    with pytest.raises(NotImplementedError, match=r"golden-JSON.*data JEC.*data MET"):
        require_supported_sample("2024", True)
    monkeypatch.setattr(weight_prescription, "read_weight_prescription", lambda *_: None)
    with pytest.raises(NotImplementedError, match="supports MC only"):
        validate_weight_fileset({"2024_Muon": ["data.root"]}, "2024")
