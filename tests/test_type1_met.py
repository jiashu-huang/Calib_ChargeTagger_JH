"""Check Type-1 MET against explicit jet-minus-muon three-vectors."""

from __future__ import annotations

import awkward as ak
import correctionlib
import numpy as np
import pytest

from boostedhh.processors.corrections import (
    JEC_2024_MC_COMPOUND,
    JEC_2024_MC_L1,
    JER_2024_MC_RESO,
    JER_2024_MC_SF,
    JER_2024_MC_SF_UNCERTAINTY,
    JER_2024_SMEAR,
    JERSMEAR_2024_BUNDLED,
    JECs,
)


class _L1Correction:
    def evaluate(self, area, eta, pt, rho):  # noqa: ARG002
        return 1.0 + 0.02 * eta


class _FullCorrection:
    def evaluate(self, area, eta, pt, rho, phi):  # noqa: ARG002
        assert np.all((phi >= -np.pi) & (phi < np.pi))
        return 2.0 + 0.1 * eta + 0.05 * phi


class _ConstantCorrection:
    def __init__(self, value):
        self.value = value

    def evaluate(self, first, *rest):  # noqa: ARG002
        return np.full_like(first, self.value, dtype=float)


class _RecordingSmear:
    def __init__(self, factor=1.2):
        self.factor = factor
        self.gen_pt = None

    def evaluate(self, pt, eta, gen_pt, rho, event, resolution, sf):  # noqa: ARG002
        self.gen_pt = gen_pt.copy()
        return np.full_like(pt, self.factor)


class _Corrections(dict):
    def __init__(self):
        super().__init__({
            JEC_2024_MC_L1: _L1Correction(),
            JER_2024_MC_RESO: _ConstantCorrection(0.1),
            JER_2024_MC_SF: _ConstantCorrection(1.2),
        })
        self.compound = {JEC_2024_MC_COMPOUND: _FullCorrection()}


def _loader(smear=None):
    loader = JECs.__new__(JECs)
    loader.correctionlib_cset = _Corrections()
    loader.jersmear_cset = {JER_2024_SMEAR: smear or _RecordingSmear()}
    return loader


def _correctable_jet(pt=40.0, eta=0.5, phi=0.0, gen_pt=0.0, dr_gen=999.0):
    """Raw inputs with no muon subtraction; JEC and JER are applied by the test."""
    jet = _jet((pt * np.cos(phi), pt * np.sin(phi), pt * np.sinh(eta)), (0.0, 0.0, 0.0))
    return {**jet, "pt": pt, "mass": 2.0, "mass_raw": 2.0,
            "pt_gen": gen_pt, "dr_gen": dr_gen}


class _SignedSource:
    def __init__(self):
        self.pt = None

    def evaluate(self, eta, pt):
        self.pt = pt.copy()
        return np.where(eta >= 0.0, 0.1, -0.1)


@pytest.mark.parametrize("direction", [1, -1])
def test_signed_jes_uses_nominal_smeared_pt_and_preserves_mass_and_raw_factor(direction):
    loader = _loader()
    loader.jes_source, loader.jes_direction = "RelativeBal", direction
    source = _SignedSource()
    loader.correctionlib_cset[loader.jes_correction_key] = source
    loader.correctionlib_cset.compound[JEC_2024_MC_COMPOUND] = _ConstantCorrection(2.0)
    jets = ak.Array([[_correctable_jet(40.0, 0.5), _correctable_jet(40.0, -0.5)]])
    result, _ = loader._apply_correctionlib_jec_2024(jets, False, False, ak.Array([100]))
    np.testing.assert_allclose(source.pt, [96.0, 96.0], rtol=1e-7)
    factors = 1 + direction * np.array([0.1, -0.1])
    np.testing.assert_allclose(ak.flatten(result.pt), 96.0 * factors, rtol=1e-7)
    np.testing.assert_allclose(ak.flatten(result.mass), 4.8 * factors, rtol=1e-7)
    np.testing.assert_allclose(ak.flatten(result.pt * (1 - result.rawFactor)), [40, 40])
    np.testing.assert_allclose(ak.flatten(result.jer_smear), [1.2, 1.2])


@pytest.mark.parametrize("direction", [1, -1])
def test_jes_propagates_to_regular_and_auxiliary_met_with_active_threshold(direction):
    loader = _loader()
    loader.jes_source, loader.jes_direction = "AbsoluteScale", direction
    loader.correctionlib_cset[loader.jes_correction_key] = _ConstantCorrection(0.1)
    loader.correctionlib_cset.compound[JEC_2024_MC_COMPOUND] = _ConstantCorrection(2.0)
    loader.correctionlib_cset[JEC_2024_MC_L1] = _ConstantCorrection(1.0)
    # The regular jet contains a muon pointing along y. Its residual is (30,-10).
    regular = {**_jet((40.0, 0.0, 20.0), (10.0, 10.0, 0.0)),
               "pt": 40.0, "mass": 2.0, "mass_raw": 2.0, "pt_gen": 0.0, "dr_gen": 999.0}
    jets, _ = loader._apply_correctionlib_jec_2024(
        ak.Array([[regular]]), False, False, ak.Array([100]),
    )
    # 6.2 * 2 * 1.2 = 14.88: only JES up includes this disjoint low-pT jet.
    events = _events([[_low_jet((0.0, 6.2, 0.0))]])
    factor = 2.0 * 1.2 * (1.0 + direction * 0.1)
    expected = np.array([25.0, -10.0]) - (factor - 1.0) * np.array([30.0, -10.0])
    if direction == 1:
        expected -= (factor - 1.0) * np.array([0.0, 6.2])
    np.testing.assert_allclose(_met(jets, [[25.0, -10.0]], events=events, loader=loader)[0],
                               expected, atol=1e-5)


def _jer_loader(direction):
    loader = _loader()
    loader.jer_direction = direction
    loader.correctionlib_cset.compound[JEC_2024_MC_COMPOUND] = _ConstantCorrection(1.0)
    loader.correctionlib_cset[JER_2024_MC_SF_UNCERTAINTY] = _ConstantCorrection(0.2)
    loader.jersmear_cset = correctionlib.CorrectionSet.from_file(JERSMEAR_2024_BUNDLED)
    return loader


def test_jer_fractional_sf_uncertainty_and_shared_random_draw():
    raw = ak.Array([[_correctable_jet(100, gen_pt=90, dr_gen=0.1),
                     _correctable_jet(100)]] * 10)
    events = ak.Array(np.arange(100, 110))
    results = {}
    for direction in (0, 1, -1):
        result, _ = _jer_loader(direction)._apply_correctionlib_jec_2024(
            ak.copy(raw), False, False, events,
        )
        results[direction] = result
        sf = 1.2 * (1 + direction * 0.2)
        # Matched scaling works even for SF < 1 and uses unsmeared reco pT.
        np.testing.assert_allclose(result.pt[:, 0], 90.0 + sf * 10.0, rtol=1e-7)
    # The stochastic standardized Gaussian is identical for nominal and up.
    z_nominal = (ak.to_numpy(results[0].jer_smear[:, 1]) - 1) / (0.1 * np.sqrt(1.2**2 - 1))
    z_up = (ak.to_numpy(results[1].jer_smear[:, 1]) - 1) / (0.1 * np.sqrt(1.44**2 - 1))
    np.testing.assert_allclose(z_nominal, z_up, atol=1e-6)
    np.testing.assert_array_equal(results[-1].jer_smear[:, 1], np.ones(10))
    # Reordering the events / splitting the chunk cannot change the draw.
    for direction in (0, 1, -1):
        chunks = []
        for selection in (slice(9, 4, -1), slice(4, None, -1)):
            chunk, _ = _jer_loader(direction)._apply_correctionlib_jec_2024(
                ak.copy(raw[selection]), False, False, events[selection],
            )
            chunks.append(chunk)
        np.testing.assert_array_equal(ak.flatten(ak.concatenate(chunks)[::-1].pt),
                                      ak.flatten(results[direction].pt))


@pytest.mark.parametrize("direction", [0, 1, -1])
def test_jer_met_reuses_regular_and_auxiliary_factors_and_reselects_threshold(direction):
    loader = _jer_loader(direction)
    loader.correctionlib_cset[JEC_2024_MC_L1] = _ConstantCorrection(1.0)
    jets, _ = loader._apply_correctionlib_jec_2024(
        ak.Array([[_correctable_jet(100, eta=0, gen_pt=90, dr_gen=0.1)]]),
        False, False, ak.Array([100]),
    )
    events = _events([[_low_jet((0, 14.9, 0))]],
                     [[{"pt": 14.0, "eta": 0.0, "phi": np.pi / 2}]])
    sf = 1.2 * (1 + direction * 0.2)
    auxiliary_pt = 14.0 + sf * 0.9
    expected = [50.0 - (90.0 + sf * 10.0 - 100.0),
                30.0 - (auxiliary_pt - 14.9 if auxiliary_pt > 15.0 else 0.0)]
    np.testing.assert_allclose(_met(jets, [[50, 30]], events=events, loader=loader)[0],
                               expected, atol=1e-5)


@pytest.mark.parametrize("direction", [0, 1, -1])
def test_jer_match_requires_both_strict_cuts_for_every_direction(direction):
    recorder = _RecordingSmear()
    loader = _jer_loader(direction)
    loader.jersmear_cset = {JER_2024_SMEAR: recorder}
    # Binary-exact width: 3 * 0.125 * 100 = 37.5, without decimal roundoff.
    loader.correctionlib_cset[JER_2024_MC_RESO] = _ConstantCorrection(0.125)
    jets = ak.Array([[
        _correctable_jet(100, gen_pt=90, dr_gen=0.199),
        _correctable_jet(100, gen_pt=90, dr_gen=0.2),
        _correctable_jet(100, gen_pt=62.5, dr_gen=0.1),
        _correctable_jet(100, gen_pt=0, dr_gen=0.1),
    ]])
    loader._apply_correctionlib_jec_2024(jets, False, False, ak.Array([100]))
    np.testing.assert_array_equal(recorder.gen_pt, [90, -1, -1, -1])


class _ZeroNominalSmear:
    def evaluate(self, pt, eta, gen_pt, rho, event, resolution, sf):  # noqa: ARG002
        return sf - 1.3


def test_negative_nominal_smear_clamps_to_zero_but_varied_jet_can_recover():
    loader = _jer_loader(1)
    loader.jersmear_cset = {JER_2024_SMEAR: _ZeroNominalSmear()}
    result, _ = loader._apply_correctionlib_jec_2024(
        ak.Array([[_correctable_jet(200)]]), False, False, ak.Array([100]),
    )
    assert result.pt_nominal[0, 0] == 0
    assert result.pt[0, 0] == pytest.approx(28.0, rel=1e-7)
    assert np.isfinite(result.rawFactor[0, 0])


def test_type1_eta_acceptance_uses_muon_subtracted_direction():
    jet = _jet((40, 0, 20), (0, 0, 0))
    jet["muonSubtrDeltaEta"] = 5.2 - jet["eta"]
    np.testing.assert_allclose(_met([[jet]], [[20.0, 10.0]]), [[20.0, 10.0]], atol=1e-12)


@pytest.mark.parametrize("options", [{}, {"jer_direction": 1},
                                     {"jes_source": "RelativeBal", "jes_direction": -1}])
def test_typed_empty_regular_jets_keep_correction_fields(options):
    loader = JECs("2024", **options)
    jets = ak.Array([[_correctable_jet()]])[:, :0]
    corrected, _ = loader._apply_correctionlib_jec_2024(jets, False, False, ak.Array([100]))
    assert ak.to_list(corrected.pt) == [[]]
    assert {"jer_smear", "jes_shift", "pt_nominal"} <= set(corrected.fields)


def test_requested_jet_variation_does_not_silently_fall_back():
    with pytest.raises(KeyError, match="Required 2024 jet correction"):
        JECs("2024", jes_source="NotARealSource", jes_direction=1)
    with pytest.raises(ValueError, match="one JES"):
        JECs("2024", jes_source="AbsoluteScale", jes_direction=1, jer_direction=1)
    with pytest.raises(ValueError, match="2024 MC"):
        JECs("2023", jer_direction=1)


def _coordinates(vector):
    x, y, z = vector
    pt = np.hypot(x, y)
    return pt, np.arcsinh(z / pt), np.arctan2(y, x)


def _jet(raw, muon, smear=1.1):
    raw = np.asarray(raw, dtype=float)
    residual = raw - muon
    pt, eta, phi = _coordinates(raw)
    sub_pt, sub_eta, sub_phi = _coordinates(residual)
    return {
        "pt_raw": pt,
        "eta": eta,
        "phi": phi,
        "muonSubtrFactor": 1.0 - sub_pt / pt,
        "muonSubtrDeltaEta": sub_eta - eta,
        "muonSubtrDeltaPhi": sub_phi - phi,
        "area": 0.5,
        "event_rho": 20.0,
        "jer_smear": smear,
        "neEmEF": 0.1,
        "chEmEF": 0.1,
    }


def _low_jet(raw, muon=(0.0, 0.0, 0.0), em_fraction=0.2):
    jet = _jet(raw, muon)
    return {
        **{name: jet[name] for name in (
            "eta", "phi", "area", "muonSubtrFactor", "muonSubtrDeltaEta", "muonSubtrDeltaPhi",
        )},
        "rawPt": jet["pt_raw"],
        "rawMass": 0.0,
        "EmEF": em_fraction,
    }


def _events(low_jets, gen_jets=None):
    if gen_jets is None:
        gen_jets = [[] for _ in low_jets]
    # Keep the GenJet schema when every event has zero gen jets, as NanoAOD does.
    gen_flat = [jet for event in gen_jets for jet in event]
    gen_array = ak.unflatten(
        ak.zip({name: np.array([j[name] for j in gen_flat], dtype=float)
                for name in ("pt", "eta", "phi")}),
        [len(event) for event in gen_jets],
    )
    return ak.zip({
        "CorrT1METJet": ak.Array(low_jets),
        "GenJet": gen_array,
        "Rho": ak.zip({"fixedGridRhoFastjetAll": np.full(len(low_jets), 20.0)}),
        "event": np.arange(len(low_jets), dtype=np.int64) + 100,
    }, depth_limit=1)


def _met(jets, raw_xy, *, events=None, loader=None):
    raw_xy = np.asarray(raw_xy, dtype=float)
    raw_met = ak.zip({
        "pt": np.hypot(raw_xy[:, 0], raw_xy[:, 1]),
        "phi": np.arctan2(raw_xy[:, 1], raw_xy[:, 0]),
    })
    if loader is None:
        loader = _loader()
    if events is None:
        events = _events([[] for _ in jets])
    met = loader.type1_met_2024(raw_met, ak.Array(jets), events)
    return np.column_stack((met.pt * np.cos(met.phi), met.pt * np.sin(met.phi)))


@pytest.mark.parametrize(
    ("raw", "muon"),
    [
        ((40.0, 0.0, 30.0), (10.0, 10.0, 5.0)),
        ((-40.0, 0.1, 30.0), (0.0, 2.0, 5.0)),  # cross the phi boundary
        ((40.0, 10.0, 30.0), (0.0, 0.0, 0.0)),  # no muon: unchanged jet
    ],
)
def test_met_balances_muon_subtracted_jet(raw, muon):
    residual = np.asarray(raw) - muon
    _, eta, phi = _coordinates(residual)
    # Compute the expected transverse balance directly from the residual vector.
    # Direction-dependent factors expose using the original eta/phi for the JEC.
    correction = (2.0 + 0.1 * eta + 0.05 * phi) * 1.1 - (1.0 + 0.02 * eta)
    raw_xy = np.array([25.0, -10.0])
    expected = raw_xy - correction * residual[:2]
    np.testing.assert_allclose(_met([[_jet(raw, muon)]], [raw_xy])[0], expected, atol=1e-12)


def test_phi_offset_can_differ_by_a_full_turn():
    jet = _jet((-40.0, 0.1, 30.0), (0.0, 2.0, 5.0))
    equivalent = {**jet, "muonSubtrDeltaPhi": jet["muonSubtrDeltaPhi"] + 2.0 * np.pi}
    result = _met([[jet], [equivalent]], [(10.0, 5.0), (10.0, 5.0)])
    np.testing.assert_allclose(result[0], result[1], atol=1e-12)


def test_empty_events_and_excluded_jets_do_not_shift_met():
    low_pt = _jet((4.0, 0.0, 3.0), (1.0, 1.0, 0.0))
    electromagnetic = {
        **_jet((40.0, 0.0, 30.0), (10.0, 10.0, 5.0)),
        "neEmEF": 0.85,
    }
    raw_xy = [(10.0, 5.0), (20.0, -3.0)]
    result = _met([[], [low_pt, electromagnetic]], raw_xy)
    np.testing.assert_allclose(result, raw_xy, atol=1e-12)


def test_auxiliary_jet_crossing_threshold_after_jer_contributes_once():
    low = _low_jet((0.0, 7.0, 0.0))
    # JEC alone gives 14.55 GeV; JER moves it above the 15 GeV MET threshold,
    # while it stays below the downstream 20 GeV analysis threshold.
    full_factor = 2.0 + 0.05 * np.pi / 2
    corrected_pt = 7.0 * full_factor * np.float32(1.2)
    assert 7.0 * full_factor < 15.0 < corrected_pt < 20.0
    events = _events([[low]], [[{"pt": 14.0, "eta": 0.0, "phi": np.pi / 2}]])
    smear = _RecordingSmear()
    jets = [[_jet((30.0, 0.0, 0.0), (0.0, 0.0, 0.0), smear=1.0)]]
    before = ak.to_list(events)
    result = _met(jets, [(100.0, 0.0)], events=events, loader=_loader(smear))
    np.testing.assert_allclose(result[0], [70.0, -(corrected_pt - 7.0)], atol=1e-12)
    np.testing.assert_array_equal(smear.gen_pt, [14.0])
    assert ak.to_list(events) == before  # auxiliary inputs and analysis jets stay separate


def test_auxiliary_jet_uses_muon_subtracted_direction_and_em_fraction():
    raw = np.array([10.0, 5.0, 3.0])
    muon = np.array([0.0, 2.0, 1.0])
    low = _low_jet(raw, muon)
    blocked = _low_jet((13.0, 0.0, 0.0), em_fraction=0.95)
    below_threshold = _low_jet((2.0, 0.0, 0.0))
    events = _events([[low, blocked, below_threshold], []])
    residual = raw - muon
    _, eta, phi = _coordinates(residual)
    factor = (2.0 + 0.1 * eta + 0.05 * phi) * np.float32(1.2) - (1.0 + 0.02 * eta)
    # No regular jets: the auxiliary collection must still correct MET.
    result = _met([[], []], [(0.0, 0.0), (10.0, 5.0)], events=events)
    np.testing.assert_allclose(result[0], -factor * residual[:2], atol=1e-12)
    np.testing.assert_allclose(result[1], [10.0, 5.0], atol=1e-12)


def test_auxiliary_gen_match_requires_distance_and_resolution_window():
    low = _low_jet((10.0, 0.0, 0.0))
    events = _events([[low], [low], [low]], [
        # Closest gen jet fails the pT window; the next closest is valid.
        [{"pt": 100.0, "eta": 0.0, "phi": 0.0},
         {"pt": 19.0, "eta": 0.0, "phi": 0.1}],
        [{"pt": 20.0, "eta": 0.0, "phi": 0.3}],  # outside dR < 0.2
        [],
    ])
    smear = _RecordingSmear()
    _met([[], [], []], [(0.0, 0.0)] * 3, events=events, loader=_loader(smear))
    np.testing.assert_array_equal(smear.gen_pt, [19.0, -1.0, -1.0])


def test_missing_auxiliary_collection_raises():
    events = ak.Array([{"event": 1}])
    with pytest.raises(KeyError, match="CorrT1METJet"):
        _met([[]], [(0.0, 0.0)], events=events)


def test_bundled_auxiliary_smearing_is_independent_of_chunk_boundaries():
    events = _events([
        [_low_jet((12.0, 1.0, 2.0))],
        [],
        [_low_jet((2.0, 13.0, -4.0)), _low_jet((3.0, 8.0, 1.0))],
    ])
    raw_xy = [(25.0, -5.0), (0.0, 10.0), (-5.0, 30.0)]
    loader = JECs("2024")
    together = _met([[], [], []], raw_xy, events=events, loader=loader)
    separately = np.concatenate([
        _met([[]], [raw_xy[i]], events=events[i:i + 1], loader=loader)
        for i in range(len(events))
    ])
    assert np.all(np.isfinite(together))
    np.testing.assert_array_equal(together, separately)
