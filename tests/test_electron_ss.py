"""
Unit tests for the 2024 electron energy scale & smearing
(`vcb.processors.electron_ss`).

No data fixture needed: the EGM payload is bundled in the repo, so these run
anywhere `pytest tests/` runs. Electrons are hand-built awkward records.
"""

from __future__ import annotations

import unittest

import awkward as ak
import numpy as np

from vcb.processors import electron_ss
from vcb.processors.vcbSkimmer import vcbSkimmer

YEAR = "2024"


def make_events(counts, pt=45.0, r9=0.95, sceta=0.5, gain=12.0, first_event=1000):
    """
    (events, electrons) with `counts[i]` electrons in event i.

    Only the fields the correction reads are filled: the module never touches
    anything else on the record.
    """
    n = int(np.sum(counts))
    flat = ak.zip(
        {
            "pt": np.full(n, pt, dtype=np.float32),
            "r9": np.full(n, r9, dtype=np.float32),
            "seedGain": np.full(n, gain, dtype=np.float32),
            "superclusterEta": np.full(n, sceta, dtype=np.float32),
        }
    )
    electrons = ak.unflatten(flat, counts)
    events = ak.zip(
        {
            "run": np.full(len(counts), 382000, dtype=np.int64),
            "luminosityBlock": np.arange(len(counts), dtype=np.int64) // 10 + 1,
            "event": np.arange(len(counts), dtype=np.int64) + first_event,
        }
    )
    return events, electrons


def ratio(electrons, field="pt"):
    """Corrected / raw pT, flat."""
    return ak.to_numpy(ak.flatten(electrons[field]) / ak.flatten(electrons.pt_raw))


class TestPayload(unittest.TestCase):
    """The payload is present and holds the corrections under the names this
    module actually asks for."""

    @classmethod
    def setUpClass(cls):
        cls.cset = electron_ss.get_electron_ss_correctionset(YEAR)

    def test_payload_loads(self):
        self.assertIsNotNone(self.cset, "bundled 2024 electronSS payload failed to load")

    def test_cat_names_not_egm_names(self):
        """
        The naming trap. EGM docs, jsonpog and every public example call these
        `EGMScale_Compound_Ele_2024` / `EGMSmearAndSyst_ElePTsplit_2024`; the
        CAT tree renamed them. If a future payload renames them back, this
        fails here rather than at 3 a.m. in a condor job.
        """
        self.assertIn(electron_ss.SCALE_COMPOUND, self.cset.compound)
        self.assertIn(electron_ss.SMEAR_CORRECTION, list(self.cset))

    def test_scale_is_compound_only(self):
        """`Scale` must be reached through .compound -- it is not a plain
        correction, and looking for it in the simple set silently misses it."""
        self.assertNotIn(electron_ss.SCALE_COMPOUND, list(self.cset))

    def test_compound_is_et_dependent(self):
        """
        The compound feeds the running-corrected pT back through the chain.
        Multiplying the six members at the raw pT is *not* the same thing, and
        this asserts the difference is real -- i.e. that nobody can "simplify"
        the compound away without a test noticing.
        """
        members = [
            "EGMScaleVsRun_2024",
            "EGMScale_EleEtaR9_2024",
            "EGMScale_EleFineEtaR9_2024",
            "EGMScale_ElePT_2024",
            "EGMScale_EleGain_2024",
            "EGMScale_ElePTsplit_2024",
        ]
        args = {"run": 382000.0, "ScEta": 2.3, "r9": 0.95, "pt": 72.0, "seedGain": 12.0}
        static = 1.0
        for name in members:
            corr = self.cset[name]
            inputs = {**args, "syst": "scale"}
            static *= corr.evaluate(*[inputs[i.name] for i in corr.inputs])

        compound = self.cset.compound[electron_ss.SCALE_COMPOUND].evaluate(
            "scale", args["run"], args["ScEta"], args["r9"], args["pt"], args["seedGain"]
        )
        self.assertGreater(abs(compound - static), 1e-3)


class TestArgumentOrder(unittest.TestCase):
    """
    The 2024 payload dropped the `AbsScEta` argument the 2022/2023 ones took,
    so a snippet copied from a 2022 analysis shifts every argument by one.
    A shifted call still evaluates -- every axis declares flow="clamp" -- it
    just returns nonsense, which is what these bounds catch.
    """

    @classmethod
    def setUpClass(cls):
        cls.cset = electron_ss.get_electron_ss_correctionset(YEAR)

    def test_scale_is_near_unity(self):
        scale = self.cset.compound[electron_ss.SCALE_COMPOUND]
        for sceta in (-2.3, -1.2, -0.3, 0.3, 1.2, 2.3):
            for pt in (25.0, 45.0, 120.0):
                value = scale.evaluate("scale", 382000.0, sceta, 0.95, pt, 12.0)
                self.assertTrue(
                    0.9 < value < 1.1, f"scale {value} out of range at ScEta={sceta}, pt={pt}"
                )

    def test_smear_is_a_plausible_resolution(self):
        smear = self.cset[electron_ss.SMEAR_CORRECTION]
        for sceta in (0.3, 1.2, 2.3):
            for pt in (25.0, 45.0, 120.0):
                rho = smear.evaluate("smear", pt, 0.95, sceta)
                self.assertTrue(0.0 < rho < 0.15, f"rho {rho} implausible at ScEta={sceta}")

    def test_resolution_degrades_toward_the_endcap(self):
        """Physics sanity: the endcap resolves electrons worse than the barrel.
        A swapped (pt, ScEta) pair breaks this ordering."""
        smear = self.cset[electron_ss.SMEAR_CORRECTION]
        barrel = smear.evaluate("smear", 45.0, 0.95, 0.3)
        endcap = smear.evaluate("smear", 45.0, 0.95, 2.3)
        self.assertGreater(endcap, barrel)


class TestGaussian(unittest.TestCase):
    """The deterministic RNG has to actually be a standard normal, and its
    per-electron streams have to be independent."""

    @classmethod
    def setUpClass(cls):
        n = 300_000
        cls.n = n
        cls.g = electron_ss.gaussian_from_event(
            np.full(n, 382000), np.arange(n) // 100, np.arange(n), np.zeros(n)
        )

    def test_standard_normal(self):
        self.assertAlmostEqual(self.g.mean(), 0.0, delta=5.0 / np.sqrt(self.n))
        self.assertAlmostEqual(self.g.std(), 1.0, delta=0.01)
        self.assertAlmostEqual(np.mean(np.abs(self.g) < 1.0), 0.6827, delta=0.01)
        self.assertAlmostEqual(np.mean(np.abs(self.g) < 2.0), 0.9545, delta=0.01)

    def test_finite(self):
        """Box-Muller blows up if the uniform can hit exactly 0."""
        self.assertTrue(np.all(np.isfinite(self.g)))

    def test_electron_index_decorrelates(self):
        """Two electrons in the same event must not get the same draw."""
        other = electron_ss.gaussian_from_event(
            np.full(self.n, 382000), np.arange(self.n) // 100, np.arange(self.n), np.ones(self.n)
        )
        self.assertLess(abs(np.corrcoef(self.g, other)[0, 1]), 0.01)


class TestMonteCarlo(unittest.TestCase):
    """MC gets smearing and the four variations, never the data scale."""

    @classmethod
    def setUpClass(cls):
        events, electrons = make_events([1, 2, 0, 1, 3] * 400)
        cls.events, cls.raw = events, electrons
        cls.corrected = electron_ss.apply_electron_scale_smearing(
            events, electrons, YEAR, isData=False
        )

    def test_raw_pt_preserved(self):
        self.assertTrue(
            ak.all(ak.flatten(self.corrected.pt_raw) == ak.flatten(self.raw.pt)),
            "pt_raw must keep the uncorrected value so the correction is reversible",
        )

    def test_pt_is_smeared(self):
        r = ratio(self.corrected)
        # Smearing is norm-preserving in the mean but not per electron.
        self.assertAlmostEqual(r.mean(), 1.0, delta=0.01)
        self.assertGreater(r.std(), 0.005)

    def test_all_variations_present(self):
        for field in electron_ss.PT_VARIATIONS:
            self.assertIn(field, self.corrected.fields)

    def test_smear_variations_bracket_the_nominal_width(self):
        """smear_up/down widen/narrow the resolution; using a *fresh* Gaussian
        for each would leave the widths indistinguishable."""
        nominal = ratio(self.corrected).std()
        up = ratio(self.corrected, "pt_smearUp").std()
        down = ratio(self.corrected, "pt_smearDown").std()
        self.assertGreater(up, nominal)
        self.assertLess(down, nominal)

    def test_scale_variations_bracket_the_nominal_mean(self):
        nominal = ratio(self.corrected).mean()
        self.assertGreater(ratio(self.corrected, "pt_scaleUp").mean(), nominal)
        self.assertLess(ratio(self.corrected, "pt_scaleDown").mean(), nominal)

    def test_scale_variation_is_small(self):
        """EGM's MC scale uncertainty is sub-percent; a much larger shift means
        the wrong syst key or the wrong correction."""
        shift = abs(ratio(self.corrected, "pt_scaleUp") / ratio(self.corrected) - 1.0)
        self.assertLess(shift.max(), 0.02)

    def test_deterministic(self):
        again = electron_ss.apply_electron_scale_smearing(self.events, self.raw, YEAR, isData=False)
        self.assertTrue(ak.all(ak.flatten(self.corrected.pt) == ak.flatten(again.pt)))

    def test_independent_of_chunking(self):
        """
        The load-bearing property. The skim is written in chunks and re-run with
        different chunk sizes and worker counts; because the smearing decides
        which electrons clear the pT cut, a chunk-dependent seed would make the
        *event list* itself irreproducible.
        """
        half = len(self.events) // 2
        first = electron_ss.apply_electron_scale_smearing(
            self.events[:half], self.raw[:half], YEAR, isData=False
        )
        self.assertTrue(
            ak.all(ak.flatten(first.pt) == ak.flatten(self.corrected.pt[:half])),
            "smearing changed when the events were processed in a smaller chunk",
        )


class TestData(unittest.TestCase):
    """Data gets the scale, and is never smeared or varied."""

    @classmethod
    def setUpClass(cls):
        events, electrons = make_events([1, 2, 0, 1] * 400)
        cls.corrected = electron_ss.apply_electron_scale_smearing(
            events, electrons, YEAR, isData=True
        )

    def test_scale_applied(self):
        r = ratio(self.corrected)
        self.assertTrue(np.all(r != 1.0))
        self.assertTrue(np.all((r > 0.9) & (r < 1.1)))

    def test_scale_is_deterministic_not_random(self):
        """Identical electrons in different events must get the identical
        scale -- data carries no stochastic component."""
        self.assertEqual(len(np.unique(np.round(ratio(self.corrected), 12))), 1)

    def test_no_variation_fields(self):
        for field in electron_ss.PT_VARIATIONS:
            self.assertNotIn(field, self.corrected.fields)


class TestGracefulDegradation(unittest.TestCase):
    """A year with no payload, or an empty chunk, must cost the correction --
    not the job."""

    def test_unsupported_year_is_a_noop(self):
        events, electrons = make_events([1, 2, 1] * 10)
        out = electron_ss.apply_electron_scale_smearing(events, electrons, "2019", isData=False)
        self.assertTrue(ak.all(ak.flatten(out.pt) == ak.flatten(electrons.pt)))

    def test_unsupported_year_still_sets_pt_raw(self):
        """Downstream field access must not depend on whether the correction
        ran, or the skim output schema becomes year-dependent."""
        events, electrons = make_events([1, 2, 1] * 10)
        out = electron_ss.apply_electron_scale_smearing(events, electrons, "2019", isData=False)
        self.assertIn("pt_raw", out.fields)

    def test_empty_collection(self):
        events, electrons = make_events([0, 0, 0])
        out = electron_ss.apply_electron_scale_smearing(events, electrons, YEAR, isData=False)
        self.assertEqual(ak.sum(ak.num(out)), 0)


class TestSkimmerWiring(unittest.TestCase):
    """The skimmer's output columns and the module's variations must not
    drift apart."""

    def test_skim_vars_match_pt_variations(self):
        self.assertEqual(
            set(vcbSkimmer.skim_vars["ElectronEnergyMC"]),
            set(electron_ss.PT_VARIATIONS),
        )

    def test_pt_raw_is_saved(self):
        self.assertIn("pt_raw", vcbSkimmer.skim_vars["ElectronEnergy"])


if __name__ == "__main__":
    unittest.main()
