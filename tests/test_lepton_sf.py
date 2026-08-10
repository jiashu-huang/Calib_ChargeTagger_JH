"""
Unit tests for the 2024 lepton scale factors (`vcb.processors.lepton_sf`).

No data fixture needed: the correction payloads are bundled in the repo, so
these run anywhere `pytest tests/` runs.
"""

from __future__ import annotations

import math
import unittest

import awkward as ak
import numpy as np
from coffea.analysis_tools import Weights

from vcb.processors import lepton_sf

ELECTRON_WEIGHTS = ("electron_reco", "electron_id", "electron_trigger")
MUON_WEIGHTS = ("muon_id", "muon_iso", "muon_trigger")
ALL_WEIGHTS = ELECTRON_WEIGHTS + MUON_WEIGHTS

ELECTRON_FIELDS = ("pt", "superclusterEta")
MUON_FIELDS = ("pt", "eta")


def trigger_leptons(items, fields):
    """
    Per-event optional lepton record, shaped like `ak.firsts` output.

    `None` entries stand for events with no trigger lepton of that flavor. They
    are masked rather than dropped so the array keeps its record type even when
    every entry is None -- which is exactly what the skimmer hands in for a
    chunk of pure muon events.
    """
    placeholder = dict.fromkeys(fields, 0.0)
    records = ak.Array([placeholder if item is None else item for item in items])
    return ak.mask(records, np.array([item is not None for item in items]))


def build_weights(electrons, use_electron, muons, use_muon, year="2024"):
    """Run add_lepton_weights on hand-built leptons and return the container."""
    weights = Weights(len(use_electron), storeIndividual=True)
    weights.add("genweight", np.ones(len(use_electron)))
    lepton_sf.add_lepton_weights(
        weights,
        year,
        trigger_leptons(electrons, ELECTRON_FIELDS),
        np.asarray(use_electron, dtype=bool),
        trigger_leptons(muons, MUON_FIELDS),
        np.asarray(use_muon, dtype=bool),
    )
    return weights


class TestInfinityCanonicalization(unittest.TestCase):
    """correctionlib 2.5.0 only parses the bare `Infinity` literal, so the
    quoted "inf" spelling the CAT payloads use has to be rewritten on load."""

    def test_edges_strings_become_floats(self):
        payload = {"edges": ["-inf", -2.0, 0.0, 2.0, "inf"]}
        self.assertEqual(
            lepton_sf._canonicalize_infinities(payload)["edges"],
            [-math.inf, -2.0, 0.0, 2.0, math.inf],
        )

    def test_only_edges_are_rewritten(self):
        payload = {"name": "inf", "description": "-inf", "content": ["inf"]}
        self.assertEqual(lepton_sf._canonicalize_infinities(payload), payload)

    def test_nested_edges_and_existing_floats_survive(self):
        payload = {"data": [{"edges": [[10.0, "inf"], ["-inf", 1.0]]}, {"edges": [0.0, math.inf]}]}
        result = lepton_sf._canonicalize_infinities(payload)
        self.assertEqual(result["data"][0]["edges"], [[10.0, math.inf], [-math.inf, 1.0]])
        self.assertEqual(result["data"][1]["edges"], [0.0, math.inf])


class TestPayloadsLoad(unittest.TestCase):
    def test_all_2024_payloads_available(self):
        csets = lepton_sf.get_lepton_correctionsets("2024")
        self.assertEqual(set(csets), {"electron", "electron_hlt", "muon"})
        for name, cset in csets.items():
            self.assertIsNotNone(cset, f"{name} payload failed to load")

    def test_configured_corrections_exist_in_payloads(self):
        """The working points pinned in LEPTON_SF_KEYS must really be there --
        a typo would otherwise only surface mid-production."""
        csets = lepton_sf.get_lepton_correctionsets("2024")
        keys = lepton_sf.LEPTON_SF_KEYS["2024"]

        self.assertIn(lepton_sf.EGM_ID_CORRECTION, csets["electron"])
        self.assertIn(lepton_sf.EGM_HLT_CORRECTION, csets["electron_hlt"])
        for key in ("muon_id", "muon_iso", "muon_hlt"):
            self.assertIn(keys[key], csets["muon"])

    def test_unsupported_year_is_a_no_op(self):
        weights = build_weights(
            [{"pt": 45.0, "superclusterEta": 0.4}], [True], [None], [False], year="2022"
        )
        self.assertEqual(list(weights._weights), ["genweight"])


class TestScaleFactorValues(unittest.TestCase):
    def setUp(self):
        # event 0: electron; event 1: muon; event 2: neither
        self.electrons = [{"pt": 45.0, "superclusterEta": 0.4}, None, None]
        self.muons = [None, {"pt": 30.0, "eta": 0.5}, None]
        self.weights = build_weights(
            self.electrons, [True, False, False], self.muons, [False, True, False]
        )

    def test_all_six_weights_registered(self):
        for name in ALL_WEIGHTS:
            self.assertIn(name, self.weights._weights)

    def test_flavors_do_not_leak(self):
        """Each weight is exactly 1 outside its own flavor, so the muon channel
        cannot pick up an electron SF (or vice versa)."""
        for name in ELECTRON_WEIGHTS:
            np.testing.assert_allclose(self.weights.partial_weight([name])[[1, 2]], 1.0)
        for name in MUON_WEIGHTS:
            np.testing.assert_allclose(self.weights.partial_weight([name])[[0, 2]], 1.0)

    def test_event_without_a_trigger_lepton_is_unweighted(self):
        self.assertAlmostEqual(self.weights.weight()[2], 1.0)

    def test_scale_factors_are_close_to_unity(self):
        """Loose sanity band: a real lepton SF sits within a few percent of 1.
        Catches a wrong working point or a mis-ordered evaluate() argument,
        both of which land far outside this."""
        for name in ALL_WEIGHTS:
            sf = self.weights.partial_weight([name])
            self.assertTrue(np.all((sf > 0.8) & (sf < 1.2)), f"{name} out of band: {sf}")

    def test_variations_bracket_the_nominal(self):
        for name in ALL_WEIGHTS:
            nominal = self.weights.partial_weight([name])
            up = nominal * self.weights._modifiers[f"{name}Up"]
            down = nominal * self.weights._modifiers[f"{name}Down"]
            self.assertTrue(np.all(down <= nominal + 1e-12), f"{name} down above nominal")
            self.assertTrue(np.all(up >= nominal - 1e-12), f"{name} up below nominal")


class TestBinningEdges(unittest.TestCase):
    """Every payload declares flow="error", so anything the analysis can hand
    in has to be clipped into range first. These would raise, not fail."""

    def test_muon_at_the_eta_edge(self):
        # 2.4 is the exclusive upper edge -- unclipped this raises outright.
        muons = [{"pt": 26.0, "eta": 2.4}, {"pt": 26.0, "eta": -2.4}]
        weights = build_weights([None, None], [False, False], muons, [True, True])
        for name in MUON_WEIGHTS:
            self.assertTrue(np.all(np.isfinite(weights.partial_weight([name]))))

    def test_muon_below_the_trigger_binning_floor(self):
        # ID/iso start at 10 GeV, the IsoMu24 SF only at 26.
        muons = [{"pt": 21.0, "eta": 0.0}]
        weights = build_weights([None], [False], muons, [True])
        for name in MUON_WEIGHTS:
            self.assertTrue(np.all(np.isfinite(weights.partial_weight([name]))))

    def test_electron_reco_pieces_are_stitched_by_pt(self):
        """EGM ships reco in three disjoint pT pieces; each must be picked up,
        and each must give a different (non-trivial) SF."""
        electrons = [
            {"pt": 15.0, "superclusterEta": 0.4},  # RecoBelow20
            {"pt": 45.0, "superclusterEta": 0.4},  # Reco20to75
            {"pt": 150.0, "superclusterEta": 0.4},  # RecoAbove75
        ]
        weights = build_weights(electrons, [True] * 3, [None] * 3, [False] * 3)
        reco = weights.partial_weight(["electron_reco"])
        self.assertEqual(len(set(np.round(reco, 6))), 3)
        self.assertTrue(np.all((reco > 0.8) & (reco < 1.2)))

    def test_electron_below_every_reco_piece_keeps_unity(self):
        # Below 10 GeV no piece applies; the reco SF stays 1 rather than raising.
        electrons = [{"pt": 5.0, "superclusterEta": 0.4}]
        weights = build_weights(electrons, [True], [None], [False])
        self.assertAlmostEqual(weights.partial_weight(["electron_reco"])[0], 1.0)


if __name__ == "__main__":
    unittest.main()
