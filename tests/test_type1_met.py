"""Check Type-1 MET against explicit jet-minus-muon three-vectors."""

from __future__ import annotations

import awkward as ak
import numpy as np
import pytest

from boostedhh.processors.corrections import (
    JEC_2024_MC_COMPOUND,
    JEC_2024_MC_L1,
    JER_2024_MC_RESO,
    JER_2024_MC_SF,
    JER_2024_SMEAR,
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
