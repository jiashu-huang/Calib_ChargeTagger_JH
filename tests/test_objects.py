"""
Unit tests for the object-selection helpers in `vcb.processors.objects`.

The electron supercluster-eta helper and the ECAL crack veto, on hand-built
awkward arrays (no NanoAOD file); one test reaches into the bundled EGM payload
to check the veto edges against the scale factor binning they exist to protect.

Then the AK4 PUPPI jet ID, which is validated against JME's own
`jetid.json.gz` on cvmfs: the JSON's decision tree is walked here in plain
Python and `objects.ak4_jet_id` has to reproduce it jet by jet, for every
Run-3 era. Those tests skip when cvmfs is not mounted.
"""

from __future__ import annotations

import gzip
import json
import unittest
from pathlib import Path

import awkward as ak
import numpy as np
import pytest

from vcb.processors import lepton_sf
from vcb.processors.objects import (
    ECAL_CRACK_ETA_HIGH,
    ECAL_CRACK_ETA_LOW,
    ak4_jet_id,
    attach_jet_charge,
    electron_supercluster_eta,
    in_ecal_crack,
)

JSONPOG_JME = Path("/cvmfs/cms.cern.ch/rsync/cms-nanoAOD/jsonpog-integration/POG/JME")
# Every era this skimmer can be pointed at. The Run-3 AK4 PUPPI ID is supposed
# to be one definition for all of them, which is why ak4_jet_id takes no year;
# checking all four is what makes that an assertion rather than an assumption.
JETID_ERAS = [
    "2022_Summer22",
    "2022_Summer22EE",
    "2023_Summer23",
    "2023_Summer23BPix",
    "2024_Summer24",
]


class TestSuperclusterEta(unittest.TestCase):
    def test_prefers_the_stored_branch(self):
        electrons = ak.Array([{"eta": 1.0, "deltaEtaSC": 0.02, "superclusterEta": 1.03}])
        self.assertAlmostEqual(electron_supercluster_eta(electrons)[0], 1.03)

    def test_falls_back_to_the_offset(self):
        electrons = ak.Array([{"eta": 1.0, "deltaEtaSC": 0.02}])
        self.assertAlmostEqual(electron_supercluster_eta(electrons)[0], 1.02)


class TestEcalCrackVeto(unittest.TestCase):
    def test_inside_and_outside(self):
        eta = ak.Array([0.0, 1.2, 1.5, 1.7, 2.4])
        self.assertEqual(ak.to_list(in_ecal_crack(eta)), [False, False, True, False, False])

    def test_symmetric_in_sign(self):
        """The crack is a barrel/endcap gap at both ends, so the veto has to be
        on |scEta| -- a sign slip would leave the whole -1.5 side unvetoed."""
        eta = ak.Array([1.5, -1.5, 1.2, -1.2])
        self.assertEqual(ak.to_list(in_ecal_crack(eta)), [True, True, False, False])

    def test_boundaries_are_half_open(self):
        """Closed below, open above -- matching the correctionlib bin the veto
        is aligned to, so the two agree exactly at the edges."""
        just_below = np.nextafter(ECAL_CRACK_ETA_LOW, 0.0)
        just_above = np.nextafter(ECAL_CRACK_ETA_HIGH, 2.0)
        eta = ak.Array([just_below, ECAL_CRACK_ETA_LOW, ECAL_CRACK_ETA_HIGH, just_above])
        self.assertEqual(ak.to_list(in_ecal_crack(eta)), [False, True, False, False])

    def test_preserves_jagged_structure(self):
        """good_electrons ANDs this into a per-event, per-lepton mask, so the
        jaggedness has to survive."""
        eta = ak.Array([[0.3, 1.5], [], [-1.5]])
        self.assertEqual(ak.to_list(in_ecal_crack(eta)), [[False, True], [], [True]])


class TestVetoMatchesScaleFactorBinning(unittest.TestCase):
    """
    The reason the veto exists: EGM leaves the electron ID SF unmeasured in the
    crack, filling it with exactly 1.0 and *zero* uncertainty. These tests tie
    `objects.in_ecal_crack` to the bundled payload, so a future edit to either
    edge that reopens the hole fails here instead of silently shipping events
    with an uncorrected, un-systematiced efficiency.
    """

    @classmethod
    def setUpClass(cls):
        cls.corr = lepton_sf.get_lepton_correctionsets("2024")["electron"][
            lepton_sf.EGM_ID_CORRECTION
        ]

    def id_sf(self, eta, pt):
        return tuple(
            self.corr.evaluate("2024Prompt", val, "wp90iso", float(eta), float(pt))
            for val in lepton_sf.EGM_VALTYPES
        )

    def test_surviving_electrons_have_a_measured_id_sf(self):
        for eta in np.linspace(-2.49, 2.49, 499):
            if in_ecal_crack(eta):
                continue
            for pt in (25.0, 45.0, 150.0, 600.0):
                _sf, up, down = self.id_sf(eta, pt)
                self.assertNotEqual(up, down, f"unmeasured ID SF survived at eta={eta}, pt={pt}")

    def test_vetoed_electrons_are_exactly_the_unmeasured_ones(self):
        """Nothing measured is thrown away either -- the veto is not wider than
        the hole it closes."""
        for eta in np.linspace(-2.49, 2.49, 499):
            if not in_ecal_crack(eta):
                continue
            for pt in (25.0, 45.0, 150.0, 600.0):
                self.assertEqual(self.id_sf(eta, pt), (1.0, 1.0, 1.0))


def evaluate_jetid_json(node: dict | float, jet: dict) -> float:
    """
    Evaluate one JME `jetid.json` correction tree for a single jet.

    This is a deliberately dumb reimplementation of the three correctionlib
    node types the payload uses, and it exists because correctionlib itself
    cannot evaluate this file: the multiplicity inputs are declared `int`, and
    correctionlib 2.5.0 throws "std::get: wrong index for variant" on an
    int-typed Binning node. Walking the JSON by hand is what lets the test
    cover the tracker and forward regions, which are exactly the ones with
    multiplicity cuts.
    """
    if not isinstance(node, dict):
        return float(node)

    kind = node["nodetype"]
    if kind == "transform":
        # The only transform in this payload is eta -> abs(eta).
        assert node["rule"]["expression"] == "abs(x)", node["rule"]
        jet = {**jet, node["input"]: abs(jet[node["input"]])}
        return evaluate_jetid_json(node["content"], jet)

    if kind == "binning":
        value = jet[node["input"]]
        edges, content = node["edges"], node["content"]
        if value < edges[0] or value >= edges[-1]:
            # "clamp" sends out-of-range values to the nearest bin; "error"
            # bins in this payload are only ever entered from inside.
            assert node["flow"] == "clamp", node["flow"]
            return evaluate_jetid_json(content[0 if value < edges[0] else -1], jet)
        index = int(np.searchsorted(edges, value, side="right")) - 1
        return evaluate_jetid_json(content[index], jet)

    raise AssertionError(f"unexpected nodetype {kind}")


def load_jetid_correction(era: str, name: str) -> dict:
    with gzip.open(JSONPOG_JME / era / "jetid.json.gz") as payload_file:
        payload = json.load(payload_file)
    return next(c for c in payload["corrections"] if c["name"] == name)["data"]


def random_jets(n: int, seed: int) -> dict[str, np.ndarray]:
    """
    Jets scattered over the whole input space, not a physical sample.

    The fractions are drawn on [0, 1] and the multiplicities on [0, 4] so that
    every threshold in the payload gets straddled from both sides -- a physical
    sample would leave most of the cuts untested because almost nothing sits
    near them.
    """
    rng = np.random.default_rng(seed)
    return {
        "eta": rng.uniform(-5.5, 5.5, n),
        "chHEF": rng.uniform(0.0, 1.0, n),
        "neHEF": rng.uniform(0.0, 1.0, n),
        "chEmEF": rng.uniform(0.0, 1.0, n),
        "neEmEF": rng.uniform(0.0, 1.0, n),
        "muEF": rng.uniform(0.0, 1.0, n),
        "chMultiplicity": rng.integers(0, 5, n),
        "neMultiplicity": rng.integers(0, 5, n),
    }


def as_jet_array(fields: dict[str, np.ndarray]) -> ak.Array:
    """One jet per event, so the helper sees the jagged layout it gets in the skimmer."""
    return ak.Array(
        {
            key: ak.unflatten(
                ak.values_astype(value, np.uint8 if "Multiplicity" in key else np.float32),
                np.ones(len(value), dtype=int),
            )
            for key, value in fields.items()
        }
    )


@unittest.skipUnless(JSONPOG_JME.is_dir(), "jsonpog-integration not mounted (needs cvmfs)")
class TestAK4JetIDMatchesJME(unittest.TestCase):
    """
    `ak4_jet_id` hard-codes thresholds transcribed out of JME's payload. These
    tests are what keeps that transcription honest: if a threshold was copied
    wrong, or JME changes one in a future era, the comparison fails here rather
    than quietly shifting the jet multiplicity of every skim.
    """

    def assert_matches(self, era: str, wp: str, correction: str, n: int = 20000):
        tree = load_jetid_correction(era, correction)
        fields = random_jets(n, seed=hash(era + wp) % (2**32))
        ours = ak.to_numpy(ak.flatten(ak4_jet_id(as_jet_array(fields), wp=wp)))

        theirs = np.empty(n, dtype=bool)
        for i in range(n):
            jet = {key: value[i] for key, value in fields.items()}
            jet["multiplicity"] = jet["chMultiplicity"] + jet["neMultiplicity"]
            theirs[i] = evaluate_jetid_json(tree, jet) == 1.0

        mismatch = np.flatnonzero(ours != theirs)
        self.assertEqual(
            len(mismatch),
            0,
            f"{era} {correction}: {len(mismatch)} disagreements, first at "
            f"{ {k: v[mismatch[0]] for k, v in fields.items()} if len(mismatch) else None }",
        )

    def test_tight_matches_every_run3_era(self):
        for era in JETID_ERAS:
            with self.subTest(era=era):
                self.assert_matches(era, "tight", "AK4PUPPI_Tight")

    def test_tightlepveto_matches_every_run3_era(self):
        for era in JETID_ERAS:
            with self.subTest(era=era):
                self.assert_matches(era, "tightlepveto", "AK4PUPPI_TightLeptonVeto")

    def test_all_run3_eras_ship_the_same_definition(self):
        """
        ak4_jet_id takes no `year`. That is only legitimate because JME ships
        one Run-3 definition; assert it directly instead of trusting it.
        """
        for correction in ("AK4PUPPI_Tight", "AK4PUPPI_TightLeptonVeto"):
            reference = load_jetid_correction(JETID_ERAS[0], correction)
            for era in JETID_ERAS[1:]:
                with self.subTest(era=era, correction=correction):
                    self.assertEqual(load_jetid_correction(era, correction), reference)


class TestAK4JetIDBehaviour(unittest.TestCase):
    """Thresholds spelled out by hand, so the numbers are readable in one place."""

    # A comfortably-passing central jet; individual tests spoil one field each.
    GOOD = {
        "eta": 1.0,
        "chHEF": 0.5,
        "neHEF": 0.3,
        "chEmEF": 0.1,
        "neEmEF": 0.1,
        "muEF": 0.05,
        "chMultiplicity": 10,
        "neMultiplicity": 8,
    }

    def passes(self, wp: str = "tight", **overrides) -> bool:
        fields = {**self.GOOD, **overrides}
        array = as_jet_array({k: np.array([v]) for k, v in fields.items()})
        return bool(ak.flatten(ak4_jet_id(array, wp=wp))[0])

    def test_good_central_jet_passes(self):
        self.assertTrue(self.passes())

    def test_tracker_region_thresholds(self):
        self.assertFalse(self.passes(chHEF=0.005))  # needs chHEF >= 0.01
        self.assertTrue(self.passes(chHEF=0.01))  # bins are half-open [lo, hi)
        self.assertFalse(self.passes(neHEF=0.995))  # needs neHEF < 0.99
        self.assertFalse(self.passes(neEmEF=0.95))  # needs neEmEF < 0.90
        self.assertFalse(self.passes(chMultiplicity=0))  # needs chMultiplicity >= 1
        self.assertFalse(self.passes(chMultiplicity=1, neMultiplicity=0))  # needs sum >= 2
        self.assertTrue(self.passes(chMultiplicity=1, neMultiplicity=1))

    def test_transition_and_hf_regions_drop_the_track_cuts(self):
        """Beyond |eta| = 2.6 there is no tracking, so a jet with no charged
        energy at all must still be able to pass."""
        naked = {"chHEF": 0.0, "chEmEF": 0.0, "chMultiplicity": 0}
        self.assertTrue(self.passes(eta=2.65, neHEF=0.5, neEmEF=0.5, **naked))
        self.assertFalse(self.passes(eta=2.65, neHEF=0.95, neEmEF=0.5, **naked))  # neHEF < 0.90
        self.assertTrue(self.passes(eta=2.8, neHEF=0.95, neEmEF=0.95, **naked))  # only neHEF < 0.99
        self.assertFalse(self.passes(eta=2.8, neHEF=0.995, neEmEF=0.1, **naked))
        self.assertTrue(self.passes(eta=3.5, neEmEF=0.3, neMultiplicity=2, **naked))
        self.assertFalse(self.passes(eta=3.5, neEmEF=0.5, neMultiplicity=2, **naked))  # < 0.40
        self.assertFalse(self.passes(eta=3.5, neEmEF=0.3, neMultiplicity=1, **naked))  # >= 2

    def test_symmetric_in_eta_sign(self):
        """The regions are defined in |eta|; a sign slip would apply the
        tracker cuts to the whole negative endcap."""
        for eta in (2.65, 2.8, 3.5):
            self.assertEqual(
                self.passes(eta=eta, neHEF=0.95, chHEF=0.0, chMultiplicity=0),
                self.passes(eta=-eta, neHEF=0.95, chHEF=0.0, chMultiplicity=0),
            )

    def test_tightlepveto_adds_the_lepton_cuts_only_where_jme_does(self):
        self.assertTrue(self.passes(muEF=0.9))  # Tight has no muEF cut
        self.assertFalse(self.passes("tightlepveto", muEF=0.9))
        self.assertTrue(self.passes("tightlepveto", muEF=0.7))
        self.assertFalse(self.passes("tightlepveto", chEmEF=0.9))
        # ... but not beyond |eta| = 2.7, where the payload leaves them out.
        naked = {"chHEF": 0.0, "chMultiplicity": 0}
        self.assertTrue(self.passes("tightlepveto", eta=2.8, chEmEF=0.9, muEF=0.9, **naked))

    def test_rejects_an_unknown_working_point(self):
        with pytest.raises(ValueError, match="unknown AK4 jet ID working point"):
            self.passes("loose")

    def test_preserves_jagged_structure(self):
        """good_ak4jets ANDs this into a per-event, per-jet mask."""
        jets = ak.Array(
            [
                [{**self.GOOD}, {**self.GOOD, "neHEF": 0.995}],
                [],
                [{**self.GOOD, "chMultiplicity": 0}],
            ]
        )
        self.assertEqual(ak.to_list(ak4_jet_id(jets)), [[True, False], [], [False]])


class TestAttachJetCharge(unittest.TestCase):
    """
    `JetQk` is a superset of `Jet`, matched positionally over the Jet prefix.
    These pin the slice and, more importantly, the guard: a JetQk shorter than
    Jet means the prefix is meaningless, and attaching a charge to the wrong
    jet is the one failure mode this analysis cannot afford to do quietly.
    """

    @staticmethod
    def _events(qk05, qk10=None):
        qk10 = qk10 if qk10 is not None else qk05
        return ak.Array(
            [
                {"JetQk": [{"QkCharge05": a, "QkCharge10": b} for a, b in zip(e5, e10)]}
                for e5, e10 in zip(qk05, qk10)
            ]
        )

    @staticmethod
    def _jets(pts):
        return ak.Array([[{"pt": p} for p in event] for event in pts])

    def test_takes_the_prefix_when_jetqk_is_longer(self):
        """The extra JetQk rows are sub-threshold jets absent from Jet."""
        jets = attach_jet_charge(
            self._jets([[100.0, 50.0], [80.0]]),
            self._events([[0.1, 0.2, 0.3, 0.4], [0.5, 0.6]]),
        )
        self.assertEqual(ak.to_list(jets.QkCharge05), [[0.1, 0.2], [0.5, 0.6][:1]])
        self.assertEqual(ak.to_list(jets.QkCharge10), [[0.1, 0.2], [0.5]])

    def test_equal_lengths_are_a_straight_copy(self):
        jets = attach_jet_charge(self._jets([[100.0, 50.0]]), self._events([[-0.3, 0.7]]))
        self.assertEqual(ak.to_list(jets.QkCharge05), [[-0.3, 0.7]])

    def test_empty_events_survive(self):
        jets = attach_jet_charge(self._jets([[], [30.0]]), self._events([[], [0.9]]))
        self.assertEqual(ak.to_list(jets.QkCharge05), [[], [0.9]])

    def test_raises_when_jetqk_is_shorter_than_jet(self):
        """The prefix cannot hold, so this must never degrade to a warning."""
        with pytest.raises(ValueError, match="shorter than"):
            attach_jet_charge(
                self._jets([[100.0, 50.0, 20.0]]),
                self._events([[0.1, 0.2]]),
            )

    def test_raises_when_the_collection_is_absent(self):
        """A vanilla NanoAOD has no JetQk; say so instead of KeyError-ing deep."""
        with pytest.raises(KeyError, match="CMSSW_15_CHARGE"):
            attach_jet_charge(self._jets([[100.0]]), ak.Array([{"Jet": []}]))

    def test_does_not_disturb_existing_fields(self):
        jets = attach_jet_charge(self._jets([[100.0, 50.0]]), self._events([[0.1, 0.2, 0.3]]))
        self.assertEqual(ak.to_list(jets.pt), [[100.0, 50.0]])


if __name__ == "__main__":
    unittest.main()
