"""
Unit tests for the ttbar top-pT reweighting in
[src/vcb/processors/top_pt.py](../src/vcb/processors/top_pt.py).

No NanoAOD file and no cvmfs: the parameterisations are hardcoded fit
coefficients, so everything here runs on hand-built gen particles.

What these are actually guarding, in rough order of how badly a slip would
hurt:

1. **Transcription.** The coefficients were copied off a twiki by eye. A digit
   dropped in an exponent is invisible in a plot and fatal in a yield, so the
   values are pinned at specific pT against independently written-out
   arithmetic, and the *sign* is pinned separately -- a flipped exponent still
   looks like a smooth curve near 1, but corrects the spectrum the wrong way.
2. **The wrong tops.** The twiki is explicit that anything other than the
   ``isLastCopy`` parton-level top gives "an invalid reweighting". A selection
   that quietly picked up intermediate copies would double-count tops and land
   in the ``!= 2`` branch, or worse, silently pick two of the wrong ones.
3. **The combination.** ``sqrt(SF(t) * SF(tbar))`` is a geometric mean; a
   product or an arithmetic mean is a plausible typo that survives casual
   inspection because it is still ~1.
4. **The gate.** These weights are not valid for single top or ttX, so a
   non-ttbar dataset must come back with nothing at all.
"""

from __future__ import annotations

import math
import unittest

import awkward as ak
import numpy as np
from coffea.nanoevents.methods import nanoaod

from boostedhh.processors.utils import GEN_FLAGS
from vcb.processors.top_pt import (
    DATA_PT_CLAMP,
    NNLO_PT_CLAMP,
    SF_FUNCTIONS,
    _sf_data_nlo,
    _sf_data_nnlo,
    _sf_nnlo_nlo,
    top_pt_weights,
)

TOP_PDGID = 6

# Derive the statusFlags bit pattern from coffea's own flag list rather than
# hardcoding 8448, so a coffea reordering shows up as a failure here instead of
# as a silently empty top selection in production.
_FLAG_NAMES = nanoaod.GenParticle.FLAGS
GOOD_FLAGS = sum(1 << _FLAG_NAMES.index(flag) for flag in GEN_FLAGS)
# Hard-process but *not* last copy: the intermediate radiating copy.
INTERMEDIATE_FLAGS = 1 << _FLAG_NAMES.index("fromHardProcess")


class _Events:
    """Minimal stand-in: `top_pt_weights` only ever touches `events.GenPart`."""

    def __init__(self, genpart):
        self.GenPart = genpart


def make_events(events_particles: list[list[tuple[int, float, int]]]) -> _Events:
    """
    Build gen particles from ``(pdgId, pt, statusFlags)`` triples, one list per
    event, with the real NanoAOD ``GenParticle`` behavior so ``hasFlags`` is
    the same code path production uses.
    """
    genpart = ak.zip(
        {
            "pdgId": ak.Array([[p[0] for p in ev] for ev in events_particles]),
            "pt": ak.Array([[p[1] for p in ev] for ev in events_particles]),
            "statusFlags": ak.Array([[p[2] for p in ev] for ev in events_particles]),
            "eta": ak.Array([[0.0 for _ in ev] for ev in events_particles]),
            "phi": ak.Array([[0.0 for _ in ev] for ev in events_particles]),
            "mass": ak.Array([[172.5 for _ in ev] for ev in events_particles]),
        },
        with_name="GenParticle",
        behavior=nanoaod.behavior,
    )
    return _Events(genpart)


def ttbar_event(pt_top: float, pt_atop: float) -> list[tuple[int, float, int]]:
    """One well-formed ttbar event: a last-copy t and tbar."""
    return [(TOP_PDGID, pt_top, GOOD_FLAGS), (-TOP_PDGID, pt_atop, GOOD_FLAGS)]


class TestScaleFactorValues(unittest.TestCase):
    """The fit coefficients, pinned against arithmetic written out by hand."""

    def test_data_nlo_matches_twiki_at_reference_points(self):
        # SF(pT) = exp(0.0615 - 0.0005 * pT)
        for pt, expected in [
            (0.0, math.exp(0.0615)),
            (100.0, math.exp(0.0615 - 0.05)),
            (200.0, math.exp(0.0615 - 0.10)),
            (500.0, math.exp(0.0615 - 0.25)),
        ]:
            self.assertAlmostEqual(float(_sf_data_nlo(np.array([pt]))[0]), expected, places=12)

    def test_data_nnlo_matches_twiki_at_reference_points(self):
        # SF(pT) = exp(0.0416 - 0.0003 * pT)
        for pt, expected in [
            (0.0, math.exp(0.0416)),
            (200.0, math.exp(0.0416 - 0.06)),
            (500.0, math.exp(0.0416 - 0.15)),
        ]:
            self.assertAlmostEqual(float(_sf_data_nnlo(np.array([pt]))[0]), expected, places=12)

    def test_nnlo_nlo_matches_twiki_at_reference_points(self):
        # SF(pT) = 0.103 * exp(-0.0118 * pT) - 0.000134 * pT + 0.973
        for pt in (0.0, 100.0, 500.0, 1000.0, 2000.0):
            expected = 0.103 * math.exp(-0.0118 * pt) - 0.000134 * pt + 0.973
            self.assertAlmostEqual(float(_sf_nnlo_nlo(np.array([pt]))[0]), expected, places=12)

    def test_all_scale_factors_fall_with_pt(self):
        """
        The whole point of the correction: simulation makes too many hard tops,
        so SF must *decrease*. A sign slip in the exponent leaves a smooth curve
        near 1 that corrects in the wrong direction -- this is what catches it.
        """
        pt = np.array([0.0, 50.0, 100.0, 200.0, 300.0, 400.0, 500.0])
        for name, sf in SF_FUNCTIONS.items():
            values = sf(pt)
            self.assertTrue(
                np.all(np.diff(values) < 0.0),
                f"{name} is not monotonically falling in pT: {values}",
            )

    def test_scale_factors_cross_unity_between_soft_and_hard(self):
        """Above 1 for soft tops, below 1 for hard ones -- an overall offset slip."""
        for name, sf in SF_FUNCTIONS.items():
            self.assertGreater(float(sf(np.array([0.0]))[0]), 1.0, name)
            self.assertLess(float(sf(np.array([400.0]))[0]), 1.0, name)

    def test_scale_factors_stay_physical(self):
        """Positive and within a sane band over the whole clamped range."""
        pt = np.linspace(0.0, 3000.0, 301)
        for name, sf in SF_FUNCTIONS.items():
            values = sf(pt)
            self.assertTrue(np.all(values > 0.0), f"{name} went non-positive")
            self.assertTrue(np.all(values < 1.2), f"{name} exceeded 1.2")


class TestClamping(unittest.TestCase):
    def test_data_functions_hold_flat_above_500(self):
        """The twiki's rule: beyond 500 GeV use the value at 500 GeV."""
        at_clamp = np.array([DATA_PT_CLAMP])
        beyond = np.array([600.0, 1000.0, 5000.0])
        for sf in (_sf_data_nlo, _sf_data_nnlo):
            expected = float(sf(at_clamp)[0])
            for value in sf(beyond):
                self.assertAlmostEqual(float(value), expected, places=12)

    def test_nnlo_nlo_holds_flat_above_fit_range(self):
        """Our own guard rail at the edge of the published fit, not twiki text."""
        expected = float(_sf_nnlo_nlo(np.array([NNLO_PT_CLAMP]))[0])
        for value in _sf_nnlo_nlo(np.array([2500.0, 8000.0])):
            self.assertAlmostEqual(float(value), expected, places=12)

    def test_negative_pt_cannot_inflate_the_weight(self):
        """Clipping at zero: a pathological gen pT must not run the exponent up."""
        for sf in (_sf_data_nlo, _sf_data_nnlo, _sf_nnlo_nlo):
            self.assertAlmostEqual(
                float(sf(np.array([-50.0]))[0]), float(sf(np.array([0.0]))[0]), places=12
            )


class TestEventWeights(unittest.TestCase):
    def test_equal_top_pts_give_back_the_single_top_scale_factor(self):
        """sqrt(SF * SF) == SF -- the cleanest statement of the geometric mean."""
        events = make_events([ttbar_event(150.0, 150.0)])
        weights = top_pt_weights(events, "TTtoLNu2Q")

        for name, sf in SF_FUNCTIONS.items():
            self.assertAlmostEqual(
                float(weights[name][0]), float(sf(np.array([150.0]))[0]), places=12
            )

    def test_weight_is_the_geometric_not_arithmetic_mean(self):
        """
        Pinned against the explicit sqrt-of-product. Chosen with well-separated
        pT so the geometric and arithmetic means actually differ -- at equal pT
        the two agree and the test would prove nothing.
        """
        events = make_events([ttbar_event(50.0, 450.0)])
        weights = top_pt_weights(events, "TTtoLNuCB")

        for name, sf in SF_FUNCTIONS.items():
            low = float(sf(np.array([50.0]))[0])
            high = float(sf(np.array([450.0]))[0])
            geometric = math.sqrt(low * high)
            arithmetic = 0.5 * (low + high)

            self.assertAlmostEqual(float(weights[name][0]), geometric, places=12)
            self.assertNotAlmostEqual(geometric, arithmetic, places=6)

    def test_weight_is_invariant_under_swapping_the_two_tops(self):
        """t and tbar enter symmetrically; slot order must not matter."""
        forward = top_pt_weights(make_events([ttbar_event(80.0, 320.0)]), "TTtoLNu2Q")
        reversed_ = top_pt_weights(make_events([ttbar_event(320.0, 80.0)]), "TTtoLNu2Q")

        for name in SF_FUNCTIONS:
            self.assertAlmostEqual(float(forward[name][0]), float(reversed_[name][0]), places=12)


class TestTopSelection(unittest.TestCase):
    def test_intermediate_copies_are_ignored(self):
        """
        Only the last copy counts. Here each top also has an earlier
        hard-process copy at a very different pT: if those leaked in, the event
        would have four tops and fall through to 1.0, and if they *replaced* the
        last copies the weight would be visibly wrong.
        """
        events = make_events(
            [
                [
                    (TOP_PDGID, 900.0, INTERMEDIATE_FLAGS),
                    (-TOP_PDGID, 900.0, INTERMEDIATE_FLAGS),
                    (TOP_PDGID, 150.0, GOOD_FLAGS),
                    (-TOP_PDGID, 150.0, GOOD_FLAGS),
                ]
            ]
        )
        weights = top_pt_weights(events, "TTtoLNu2Q")

        for name, sf in SF_FUNCTIONS.items():
            self.assertAlmostEqual(
                float(weights[name][0]), float(sf(np.array([150.0]))[0]), places=12
            )

    def test_non_top_particles_are_ignored(self):
        """b quarks and W bosons sharing the flags must not be counted as tops."""
        events = make_events(
            [
                [
                    (5, 200.0, GOOD_FLAGS),
                    (24, 300.0, GOOD_FLAGS),
                    (TOP_PDGID, 150.0, GOOD_FLAGS),
                    (-TOP_PDGID, 150.0, GOOD_FLAGS),
                ]
            ]
        )
        weights = top_pt_weights(events, "TTtoLNu2Q")

        for name, sf in SF_FUNCTIONS.items():
            self.assertAlmostEqual(
                float(weights[name][0]), float(sf(np.array([150.0]))[0]), places=12
            )

    def test_events_without_exactly_two_tops_are_unweighted(self):
        """
        No tops, one top, three tops -> 1.0. Better an unweighted event than a
        weight built from a made-up pT.
        """
        events = make_events(
            [
                [],
                [(TOP_PDGID, 150.0, GOOD_FLAGS)],
                [
                    (TOP_PDGID, 150.0, GOOD_FLAGS),
                    (-TOP_PDGID, 150.0, GOOD_FLAGS),
                    (TOP_PDGID, 150.0, GOOD_FLAGS),
                ],
                ttbar_event(150.0, 150.0),
            ]
        )
        weights = top_pt_weights(events, "TTtoLNu2Q")

        for name, sf in SF_FUNCTIONS.items():
            values = weights[name]
            self.assertEqual(len(values), 4)
            for i in range(3):
                self.assertEqual(float(values[i]), 1.0, f"{name} event {i}")
            # the well-formed event still gets a real weight
            self.assertAlmostEqual(float(values[3]), float(sf(np.array([150.0]))[0]), places=12)


class TestDatasetGate(unittest.TestCase):
    def test_ttbar_datasets_get_every_column(self):
        events = make_events([ttbar_event(150.0, 150.0)])
        for dataset in ("TTtoLNuCB", "TTtoLNu2Q", "TT1L2Q"):
            weights = top_pt_weights(events, dataset)
            self.assertEqual(set(weights), set(SF_FUNCTIONS), dataset)

    def test_dataset_names_match_as_substrings(self):
        """Production passes full sample names, not the bare keys."""
        events = make_events([ttbar_event(150.0, 150.0)])
        weights = top_pt_weights(events, "TTtoLNuCB_TuneCP5_13p6TeV_powheg-pythia8")
        self.assertEqual(set(weights), set(SF_FUNCTIONS))

    def test_non_ttbar_datasets_get_nothing(self):
        """
        Not merely 1.0 -- no columns at all. The TOP PAG weights are explicitly
        invalid for single top and ttX, and an all-ones column would invite
        somebody to apply them there anyway.
        """
        events = make_events([ttbar_event(150.0, 150.0)])
        for dataset in ("TWminustoLNu2Q", "TTZToLLNuNu", "WJetsToLNu", "SingleMuon"):
            self.assertEqual(top_pt_weights(events, dataset), {}, dataset)


if __name__ == "__main__":
    unittest.main()
