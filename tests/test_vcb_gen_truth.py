from __future__ import annotations

import unittest

import awkward as ak

from boostedhh.processors.utils import PAD_VAL
from vcb.processors.GenSelection import (
    _pdg_lepton_charges,
    _pdg_lepton_flavors,
    _pdg_lepton_masses,
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


if __name__ == "__main__":
    unittest.main()
