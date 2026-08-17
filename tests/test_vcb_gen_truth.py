"""
TODO: write opening docstring
"""

from __future__ import annotations

import unittest

import awkward as ak
import numpy as np

from boostedhh.processors.utils import PAD_VAL
from vcb.processors.GenSelection import (
    _greedy_jet_parton_assignment,
    _pdg_lepton_charges,
    _pdg_lepton_flavors,
    _pdg_lepton_masses,
    _split_w_quarks_by_type,
    _supplement_zero_quark_masses,
    _top_w_decay_mode_masks,
    _w_flavor_tag_arrays,
)


class TestVcbGenTruth(unittest.TestCase):
    def test_top_w_decay_mode_masks_keep_tau_channel_leptonic(self):
        w_child_pdg_ids = ak.Array(
            [
                [[-15, 16], [3, -4]],
                [[-11, 12], [1, -2]],
                [[-13, 14], [-5, 4]],
            ]
        )

        hadronic_mask, leptonic_mask = _top_w_decay_mode_masks(w_child_pdg_ids)

        self.assertEqual(
            ak.to_list(hadronic_mask),
            [[False, True], [False, True], [False, True]],
        )
        self.assertEqual(
            ak.to_list(leptonic_mask),
            [[True, False], [True, False], [True, False]],
        )

    def test_w_flavor_tags_are_unordered_and_exclusive(self):
        q1_pdg_ids = ak.Array([-2, 2, -4, 4, -5, 5])
        q2_pdg_ids = ak.Array([1, 3, 1, 3, 2, -4])
        expected_tags = [
            "GenWtoUD",
            "GenWtoUS",
            "GenWtoCD",
            "GenWtoCS",
            "GenWtoUB",
            "GenWtoBC",
        ]

        tags = _w_flavor_tag_arrays(q1_pdg_ids, q2_pdg_ids)

        for i, expected_tag in enumerate(expected_tags):
            active_tags = [name for name, values in tags.items() if bool(values[i])]
            self.assertEqual(active_tags, [expected_tag])

    def test_zero_quark_masses_are_supplemented_from_flavor(self):
        quark_masses = ak.Array([0.0, 0.0, 0.0, 4.7, None])
        quark_pdg_ids = ak.Array([1, 4, -5, 5, None])

        supplemented = _supplement_zero_quark_masses(quark_masses, quark_pdg_ids)
        supplemented = ak.to_list(ak.fill_none(supplemented, PAD_VAL))

        self.assertAlmostEqual(supplemented[0], 0.0)
        self.assertAlmostEqual(supplemented[1], 1.27)
        self.assertAlmostEqual(supplemented[2], 4.18)
        self.assertAlmostEqual(supplemented[3], 4.7)
        self.assertEqual(supplemented[4], PAD_VAL)

    def test_lepton_masses_are_taken_from_pdg_flavor(self):
        lepton_pdg_ids = ak.Array([11, -13, 15, None])

        masses = _pdg_lepton_masses(lepton_pdg_ids)
        masses = ak.to_list(ak.fill_none(masses, PAD_VAL))

        self.assertAlmostEqual(masses[0], 0.00051099895)
        self.assertAlmostEqual(masses[1], 0.1056583755)
        self.assertAlmostEqual(masses[2], 1.77686)
        self.assertEqual(masses[3], PAD_VAL)

    def test_lepton_charges_follow_pdg_sign_convention(self):
        lepton_pdg_ids = ak.Array([11, -11, 13, -15, None])

        charges = _pdg_lepton_charges(lepton_pdg_ids)
        charges = ak.to_list(ak.fill_none(charges, PAD_VAL))

        self.assertEqual(charges[0], -1)
        self.assertEqual(charges[1], 1)
        self.assertEqual(charges[2], -1)
        self.assertEqual(charges[3], 1)
        self.assertEqual(charges[4], PAD_VAL)

    def test_lepton_flavors_are_stored_as_absolute_pdg_ids(self):
        lepton_pdg_ids = ak.Array([11, -13, 15, None])

        flavors = _pdg_lepton_flavors(lepton_pdg_ids)
        flavors = ak.to_list(ak.fill_none(flavors, 0))

        self.assertEqual(flavors[0], 11)
        self.assertEqual(flavors[1], 13)
        self.assertEqual(flavors[2], 15)
        self.assertEqual(flavors[3], 0)


class TestWQuarkTypeSplit(unittest.TestCase):
    """
    `GenQ1` is the down-type W daughter and `GenQ2` the up-type one, in every
    event. This was true of all 9.8M events the repo had processed before it was
    enforced, but only because of the order the generator wrote the W's children
    in -- these tests pin it to the PDG numbering instead.
    """

    def _split(self, pdg_id_pairs):
        quarks = ak.Array([[{"pdgId": a}, {"pdgId": b}] for a, b in pdg_id_pairs])
        down, up = _split_w_quarks_by_type(quarks)
        return ak.to_list(down.pdgId), ak.to_list(up.pdgId)

    def test_down_type_is_first_regardless_of_generator_order(self):
        # Same decay, both child orderings: the split must give the same answer.
        down, up = self._split([(-3, 4), (4, -3)])

        self.assertEqual(down, [-3, -3])
        self.assertEqual(up, [4, 4])

    def test_split_is_by_type_not_by_abs_pdg_id(self):
        # W -> u s-bar: |pdgId| ordering would put u (2) first, but u is up-type.
        # This combination really occurs -- 248 459 times in TTtoLNu2Q.
        down, up = self._split([(2, -3), (-3, 2)])

        self.assertEqual(down, [-3, -3])
        self.assertEqual(up, [2, 2])

    def test_all_six_w_decay_modes_split_correctly(self):
        # ud, us, cd, cs, ub, cb -- both W charges, with the daughters written in
        # whichever order. Down-type is odd |pdgId|, up-type even.
        pairs = [(2, -1), (-1, 2), (2, -3), (4, -1), (-3, 4), (5, -2), (-5, 4)]
        down, up = self._split(pairs)

        self.assertTrue(all(abs(q) % 2 == 1 for q in down), down)
        self.assertTrue(all(abs(q) % 2 == 0 for q in up), up)

    def test_charge_conserving_pairs_are_always_one_of_each(self):
        # A W cannot decay to two same-type quarks, so neither side is ever empty.
        down, up = self._split([(1, -2), (3, -4), (5, -4), (-1, 2)])

        self.assertNotIn(None, down)
        self.assertNotIn(None, up)

    def test_same_type_pair_leaves_the_missing_side_none(self):
        # Physically impossible, so it must surface as PAD_VAL downstream rather
        # than quietly slotting some other quark into GenQ2.
        down, up = self._split([(1, -3)])

        self.assertEqual(down, [1])
        self.assertEqual(up, [None])


NUM_JETS = 10


def _make_jets(per_event_eta_phi):
    """Minimal jets: the assignment only reads pt (validity), eta and phi."""

    return ak.Array(
        [
            [{"pt": 30.0, "eta": eta, "phi": phi} for eta, phi in event]
            for event in per_event_eta_phi
        ]
    )


def _make_parton(eta_phi_per_event):
    """
    One gen parton per event; None marks a parton absent from the event.

    Masked rather than built from a list with None holes, so the result is an
    option-type *record* array with real fields -- what ``ak.firsts`` hands the
    assignment in production. A plain list of Nones types as ``?unknown`` and has
    no ``eta`` at all.
    """

    present = np.array([ep is not None for ep in eta_phi_per_event])
    eta = np.array([0.0 if ep is None else ep[0] for ep in eta_phi_per_event], dtype=np.float64)
    phi = np.array([0.0 if ep is None else ep[1] for ep in eta_phi_per_event], dtype=np.float64)
    return ak.mask(ak.zip({"eta": eta, "phi": phi}), present)


class TestGreedyJetPartonAssignment(unittest.TestCase):
    """
    The gen match used to be 40 per-slot ``ak4Matched*_`` booleans from four
    independent dR < 0.4 cuts, which is not an assignment at all: on the test
    fixture 7.1% of events had one jet carrying two parton labels and 5.0% had one
    parton spread over two jets, so the SPANet target format -- one parton per jet,
    one jet per parton -- could not be built from them. They are now four
    ``Gen*JetIdx`` integers holding this function's output. These tests pin the
    greedy nearest-first rule, including the case where it is knowingly sub-optimal.
    """

    def _assign(self, jets, partons):
        return _greedy_jet_parton_assignment(partons, jets, NUM_JETS)

    def test_contested_jet_goes_to_the_nearer_parton(self):
        # Both b partons sit inside the same jet's cone; only the closer may have it,
        # and the loser must not fall back onto a jet outside its own cone.
        jets = _make_jets([[(0.0, 0.0), (1.0, 0.0)]])
        partons = [
            _make_parton([(0.05, 0.0)]),  # HadB, dR = 0.05
            _make_parton([(0.15, 0.0)]),  # LepB, dR = 0.15 to the same jet
            _make_parton([None]),
            _make_parton([None]),
        ]

        assign = self._assign(jets, partons)

        self.assertEqual(assign[0, 0], 0)
        self.assertEqual(assign[0, 1], -1)

    def test_each_parton_takes_its_own_jet_when_both_fit(self):
        jets = _make_jets([[(0.0, 0.0), (0.35, 0.0)]])
        partons = [
            _make_parton([(0.02, 0.0)]),
            _make_parton([(0.33, 0.0)]),
            _make_parton([None]),
            _make_parton([None]),
        ]

        assign = self._assign(jets, partons)

        self.assertEqual(assign[0, 0], 0)
        self.assertEqual(assign[0, 1], 1)

    def test_assignment_is_one_to_one(self):
        # Four partons crowded around three jets: whatever comes out, no jet may be
        # used twice. This is the property the old independent flags violated.
        jets = _make_jets([[(0.0, 0.0), (0.1, 0.0), (0.2, 0.0)]])
        partons = [
            _make_parton([(0.02, 0.0)]),
            _make_parton([(0.05, 0.0)]),
            _make_parton([(0.12, 0.0)]),
            _make_parton([(0.18, 0.0)]),
        ]

        assign = self._assign(jets, partons)

        used = [j for j in assign[0] if j >= 0]
        self.assertEqual(len(used), len(set(used)))
        self.assertEqual(len(used), 3)  # three jets, so exactly one parton misses out

    def test_pairs_outside_the_cone_are_never_assigned(self):
        # dR exactly 0.4 must fail: the cut is strict, as it was before.
        jets = _make_jets([[(0.0, 0.0)], [(0.0, 0.0)]])
        partons = [
            _make_parton([(0.4, 0.0), (0.39, 0.0)]),
            _make_parton([None, None]),
            _make_parton([None, None]),
            _make_parton([None, None]),
        ]

        assign = self._assign(jets, partons)

        self.assertEqual(assign[0, 0], -1)
        self.assertEqual(assign[1, 0], 0)

    def test_exact_ties_break_to_the_earlier_parton_deterministically(self):
        # Bit-identical dR happens in ~0.02% of fixture events. The rule only has to
        # be fixed, not physical: argmin over the row-major (parton, jet) block
        # takes the earlier entry in the parton list.
        jets = _make_jets([[(0.0, 0.0), (5.0, 0.0)]])
        partons = [
            _make_parton([(0.1, 0.0)]),
            _make_parton([(-0.1, 0.0)]),  # identical dR to the same jet
            _make_parton([None]),
            _make_parton([None]),
        ]

        first = self._assign(jets, partons)
        again = self._assign(jets, partons)

        self.assertEqual(first[0, 0], 0)
        self.assertEqual(first[0, 1], -1)
        np.testing.assert_array_equal(first, again)

    def test_absent_parton_is_unmatched_and_frees_its_jet(self):
        # An absent parton sits at PAD_VAL. So does an empty jet slot -- their dR
        # would be exactly 0 and read as the tightest match in the event if the
        # validity masks were dropped.
        jets = _make_jets([[(0.0, 0.0)]])
        partons = [
            _make_parton([None]),
            _make_parton([(0.05, 0.0)]),
            _make_parton([None]),
            _make_parton([None]),
        ]

        assign = self._assign(jets, partons)

        self.assertEqual(assign[0, 0], -1)
        self.assertEqual(assign[0, 1], 0)

    def test_padded_jet_slots_are_never_assigned(self):
        # One real jet the parton cannot reach, nine padded slots. The index must be
        # -1 and never a padded slot: those sit at PAD_VAL in eta/phi, so an absent
        # parton would land on one at dR exactly 0 without the validity masks.
        jets = _make_jets([[(0.0, 0.0)]])
        partons = [
            _make_parton([(3.0, 0.0)]),
            _make_parton([None]),
            _make_parton([None]),
            _make_parton([None]),
        ]

        assign = self._assign(jets, partons)

        self.assertEqual(assign[0].tolist(), [-1, -1, -1, -1])

    def test_greedy_leaves_the_documented_gap_to_the_optimal_assignment(self):
        # The case where nearest-first is knowingly sub-optimal: HadB's tightest jet
        # is the only jet LepB can reach, and HadB has a second option it never
        # takes. Greedy matches one parton, the minimum-total-dR (Hungarian)
        # assignment would match two. Worth +0.037 pp over the fixture, which is why
        # this behaviour is pinned rather than fixed.
        jets = _make_jets([[(0.0, 0.0), (0.0, 0.35)]])
        partons = [
            _make_parton([(0.0, 0.02)]),  # dR 0.02 to jet 0, 0.33 to jet 1
            _make_parton([(0.0, -0.10)]),  # dR 0.10 to jet 0, 0.45 to jet 1
            _make_parton([None]),
            _make_parton([None]),
        ]

        assign = self._assign(jets, partons)

        self.assertEqual(assign[0, 0], 0)
        self.assertEqual(assign[0, 1], -1)


if __name__ == "__main__":
    unittest.main()
