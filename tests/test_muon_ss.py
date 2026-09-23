"""Momentum calibration, source-reference values and acceptance boundaries."""

from __future__ import annotations

import gzip
from types import SimpleNamespace

import awkward as ak
import numpy as np
import pytest
from coffea.nanoevents.methods import candidate

from vcb import run
from vcb.processors import muon_ss, objects
from vcb.processors.muon_ss import MomentumStatus as Status


def make_muons(pt=(50.0, 70.0, 120.0, 180.0), counts=None, **overrides):
    pt = np.asarray(pt, dtype=float)
    n = len(pt)
    counts = [n] if counts is None else counts
    fields = {
        "pt": pt,
        "eta": np.resize([0.3, 1.0, 1.5, 2.2], n),
        "phi": np.resize([0.2, -0.6, 1.0, -2.0], n),
        "charge": np.resize([1, -1, 1, -1], n),
        "tightId": np.ones(n, dtype=bool),
        "pfRelIso04_all": np.full(n, 0.1),
        "nTrackerLayers": np.full(n, 12),
        "mass": np.full(n, 0.105658),
    }
    fields.update(overrides)
    muons = ak.zip(
        {k: ak.unflatten(v, counts) for k, v in fields.items()},
        with_name="PtEtaPhiMCandidate",
        behavior=candidate.behavior,
    )
    events = ak.Array(
        {"event": np.arange(len(counts)) + 12345, "luminosityBlock": np.ones(len(counts), int)}
    )
    return events, muons


def corrected(events, muons, **kwargs):
    return muon_ss.apply_muon_scale_smearing(events, muons, "2024", False, **kwargs)


def flat(array):
    return ak.to_numpy(ak.flatten(array))


def test_matches_pinned_nominal_and_cpp_resolution_reference():
    """Numbers from independently run public helpers, recorded in the audit."""
    events, muons = make_muons()
    result = corrected(events, muons)
    np.testing.assert_allclose(
        flat(result.pt),
        [49.87233370462797, 69.28582465190077, 120.9520221056571, 177.12587373266544],
        rtol=0,
        atol=1e-10,
    )
    np.testing.assert_allclose(
        flat(result.pt_resolutionStatUp),
        [49.858880497106334, 69.26741690272611, 120.97007696081758, 177.11938752518307],
        rtol=0,
        atol=1e-10,
    )
    np.testing.assert_array_equal(flat(result.pt_raw), flat(muons.pt))
    np.testing.assert_array_equal(flat(result.charge), flat(muons.charge))
    assert ak.all(result.momentumStatus == Status.CALIBRATED)


def test_data_gets_scale_without_smearing_or_variations():
    events, muons = make_muons()
    result = muon_ss.apply_muon_scale_smearing(events, muons, "2024", True)
    cset = muon_ss.get_muon_correctionset()
    pt, eta, phi, charge = (flat(muons[k]) for k in ("pt", "eta", "phi", "charge"))
    expected = 1 / (
        cset["m_data"].evaluate(eta, phi, "nom") / pt
        + charge * cset["a_data"].evaluate(eta, phi, "nom")
    )
    np.testing.assert_array_equal(flat(result.pt), expected)
    np.testing.assert_array_equal(flat(result.pt_scale), expected)
    assert not set(muon_ss.PT_VARIATIONS.values()) & set(result.fields)


def test_crystal_ball_core_tails_and_tracker_layer_edges_match_reference():
    """Pinned public helper values span eta/layer bins and both power-law tails."""
    cset = muon_ss.get_muon_correctionset()
    eta = np.array([0.0, 0.399, 0.401, 0.8, 1.201, 1.6, 2.0, 2.399])
    layers = np.array([0.0, 5.0, 7.0, 9.0, 12.0, 15.0, 18.0, 30.0])
    uniform = np.array([1e-6, 0.001, 0.01, 0.25, 0.5, 0.99, 0.999, 1 - 1e-6])
    mean, width, power, alpha = [cset["cb_params"].evaluate(eta, layers, i) for i in range(4)]
    expected = [
        -13.809288111118978,
        -15.031595817980643,
        -3.268846198095792,
        -0.6316732439376496,
        -0.00168825923017056,
        2.523108424532561,
        4.172196324917764,
        10.056013778615357,
    ]
    actual = muon_ss._crystal_ball_draw(uniform, mean, width, alpha, power)
    np.testing.assert_allclose(actual, expected, rtol=1e-10, atol=1e-10)


@pytest.mark.parametrize("source", ["scale", "resolution"])
def test_total_uncertainties_include_stat_and_syst(source):
    events, muons = make_muons()
    result = corrected(events, muons)
    nominal = flat(result.pt)
    total = flat(result[f"pt_{source}Up"]) - nominal
    stat = flat(result[f"pt_{source}StatUp"]) - nominal
    syst = flat(result[f"pt_{source}SystUp"]) - nominal
    np.testing.assert_allclose(total**2, stat**2 + syst**2, rtol=1e-10, atol=1e-15)
    assert np.all(np.abs(total) > np.abs(stat))
    np.testing.assert_allclose(flat(result[f"pt_{source}Down"]) - nominal, -total, atol=1e-12)


@pytest.mark.parametrize("variation", tuple(muon_ss.PT_VARIATIONS))
def test_selected_variation_replaces_active_pt(variation):
    events, muons = make_muons()
    nominal = corrected(events, muons)
    result = corrected(events, muons, variation=variation)
    np.testing.assert_array_equal(flat(result.pt), flat(nominal[muon_ss.PT_VARIATIONS[variation]]))
    np.testing.assert_array_equal(flat(result.pt_nominal), flat(nominal.pt))


def test_chunk_event_and_muon_order_do_not_change_smearing():
    events, muons = make_muons(np.linspace(30, 195, 20), counts=[2, 0, 4, 8, 6])
    result = corrected(events, muons)
    split = ak.concatenate([corrected(events[:3], muons[:3]), corrected(events[3:], muons[3:])])
    reversed_events = corrected(events[::-1], muons[::-1])[::-1]
    reversed_muons = corrected(events, muons[:, ::-1])[:, ::-1]
    for field in ("pt", *muon_ss.PT_VARIATIONS.values()):
        for other in (split, reversed_events, reversed_muons):
            np.testing.assert_array_equal(flat(result[field]), flat(other[field]))


def test_reapplication_uses_preserved_raw_momentum():
    events, muons = make_muons()
    first = corrected(events, muons)
    second = corrected(events, first)
    for field in ("pt", "pt_raw", *muon_ss.PT_VARIATIONS.values()):
        np.testing.assert_array_equal(flat(first[field]), flat(second[field]))


def test_validity_bounds_and_high_pt_are_explicit():
    pt = [25.999, 26.0, 26.001, 199.999, 200.0, 200.001, 656.0]
    events, muons = make_muons(pt)
    result = corrected(events, muons)
    assert flat(result.momentumStatus)[[0, 5, 6]].tolist() == [2, 3, 3]
    assert not np.any(np.isin(flat(result.momentumStatus)[1:5], [0, 2, 3, 6]))
    for field in ("pt", *muon_ss.PT_VARIATIONS.values()):
        np.testing.assert_array_equal(flat(result[field])[[0, 5, 6]], np.asarray(pt)[[0, 5, 6]])


def test_wrong_id_isolation_or_eta_is_not_calibrated():
    events, muons = make_muons(
        tightId=np.array([False, True, True, True]),
        pfRelIso04_all=np.array([0.1, 0.15, 0.1, 0.1]),
        eta=np.array([0.3, 0.3, 2.4, np.nan]),
    )
    result = corrected(events, muons)
    assert ak.all(result.momentumStatus == Status.INELIGIBLE)
    np.testing.assert_array_equal(flat(result.pt), flat(muons.pt))


@pytest.mark.parametrize("is_data", [False, True])
def test_empty_typed_collections(is_data):
    events, muons = make_muons([], counts=[0, 0])
    result = muon_ss.apply_muon_scale_smearing(events, muons, "2024", is_data)
    assert ak.to_list(ak.num(result)) == [0, 0]
    assert "momentumStatus" in result.fields
    assert "pt_nominal" in result.fields


def test_missing_required_inputs_raise():
    events, muons = make_muons()
    with pytest.raises(KeyError, match="nTrackerLayers"):
        corrected(events, muons[[f for f in muons.fields if f != "nTrackerLayers"]])
    with pytest.raises(KeyError, match="luminosityBlock"):
        corrected(events[[f for f in events.fields if f != "luminosityBlock"]], muons)


def test_payload_missing_or_wrong_hash_is_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(muon_ss, "PAYLOAD_PATH", tmp_path / "bundled.gz")
    monkeypatch.setattr(muon_ss, "CVMFS_PATH", tmp_path / "cvmfs.gz")
    muon_ss.get_muon_correctionset.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="missing"):
            muon_ss.get_muon_correctionset()
        muon_ss.PAYLOAD_PATH.write_bytes(gzip.compress(b"{}"))
        with pytest.raises(RuntimeError, match="checksum"):
            muon_ss.get_muon_correctionset()
    finally:
        muon_ss.get_muon_correctionset.cache_clear()


def test_variations_reject_data_and_other_years():
    events, muons = make_muons()
    for year, data in [("2024", True), ("2023", False)]:
        with pytest.raises(ValueError, match="2024 MC"):
            muon_ss.apply_muon_scale_smearing(events, muons, year, data, "scaleUp")
    result = muon_ss.apply_muon_scale_smearing(events, muons, "2023", False)
    assert ak.all(result.momentumStatus == Status.UNSUPPORTED_YEAR)
    np.testing.assert_array_equal(flat(result.pt), flat(muons.pt))
    with pytest.raises(ValueError, match="Unknown"):
        corrected(events, muons, variation="typo")


def test_resolution_fallback_is_visible(monkeypatch):
    events, muons = make_muons()
    monkeypatch.setattr(
        muon_ss,
        "_resolution_inputs",
        lambda *_: (np.ones(4), np.zeros(4), np.zeros(4, dtype=bool)),
    )
    result = corrected(events, muons)
    assert ak.all(result.momentumStatus == Status.FALLBACK)
    np.testing.assert_array_equal(flat(result.pt), flat(result.pt_scale))
    np.testing.assert_array_equal(flat(result.pt_resolutionUp), flat(result.pt_scale))


def test_zero_residual_width_has_finite_variations(monkeypatch):
    events, muons = make_muons()
    monkeypatch.setattr(
        muon_ss,
        "_resolution_inputs",
        lambda *_: (np.zeros(4), np.full(4, 0.01), np.ones(4, dtype=bool)),
    )
    result = corrected(events, muons)
    assert np.all(np.isfinite(flat(result.pt_resolutionUp)))
    assert ak.all(result.pt_resolutionUp > result.pt)
    np.testing.assert_array_equal(flat(result.pt_resolutionDown), flat(result.pt))


def test_variation_can_enter_the_real_trigger_selection():
    """Start from raw objects; a nominally rejected muon can enter a shift."""
    pts = np.linspace(26.01, 27.0, 2000)
    events, muons = make_muons(pts, counts=np.ones(len(pts), dtype=int))
    trig = ak.with_field(muons, ak.ones_like(muons.pt, dtype=int) * 13, "id")
    trig = ak.with_field(trig, ak.ones_like(muons.pt, dtype=int) * 8, "filterBits")
    events = ak.with_field(events, trig, "TrigObj")
    events = ak.with_field(events, ak.Array({"IsoMu24": np.ones(len(pts), dtype=bool)}), "HLT")
    nominal = corrected(events, muons)
    shifted = corrected(events, muons, variation="resolutionDown")
    _, nom_matches = objects.good_muons(events, nominal, "2024")
    _, var_matches = objects.good_muons(events, shifted, "2024")
    nom_pass = ak.to_numpy(ak.any(nom_matches["MuonTrigMatchMuon"], axis=1))
    var_pass = ak.to_numpy(ak.any(var_matches["MuonTrigMatchMuon"], axis=1))
    assert np.any(var_pass & ~nom_pass)


def test_all_cli_passes_have_separate_directories_and_preserve_arguments(monkeypatch, tmp_path):
    args = SimpleNamespace(
        muon_pt_variation="all",
        year="2024",
        executor="iterative",
        outdir=str(tmp_path / "out"),
        output_root_location=str(tmp_path / "roots"),
        naming_tag="sample",
    )
    calls = []
    monkeypatch.setattr(run, "_run_single", calls.append)
    run.main(args)
    assert [a.muon_pt_variation for a in calls] == ["nominal", *muon_ss.TOTAL_VARIATIONS]
    assert len({a.outdir for a in calls}) == 5
    assert len({a.output_root_location for a in calls}) == 5
    assert args.muon_pt_variation == "all"
    assert all(a.naming_tag == "sample" for a in calls)


@pytest.mark.parametrize("variation", ["all", "scaleUp"])
def test_cli_passes_reject_unsupported_year(monkeypatch, variation):
    args = SimpleNamespace(muon_pt_variation=variation, year="2023", executor="iterative")
    monkeypatch.setattr(run, "_run_single", lambda _: pytest.fail("Must not start a partial run"))
    with pytest.raises(ValueError, match="2024 MC"):
        run.main(args)


@pytest.mark.parametrize("variation", ["all", "scaleUp"])
def test_cli_passes_reject_unsupported_runner(monkeypatch, variation):
    args = SimpleNamespace(muon_pt_variation=variation, year="2024", executor="dask")
    monkeypatch.setattr(run, "_run_single", lambda _: pytest.fail("Must not start a partial run"))
    with pytest.raises(ValueError, match="local runner"):
        run.main(args)
