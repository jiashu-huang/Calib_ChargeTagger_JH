"""Dedicated TTBB must retain scale variations and their all-input sums."""

from __future__ import annotations

from importlib import import_module
from types import SimpleNamespace

import awkward as ak
import numpy as np
import pytest

skimmer = import_module("vcb.processors.vcbSkimmer")


@pytest.mark.parametrize("dataset", ["TTtoLNu2Q", "TTtoLNuCB", "TTToSemiLeptonic",
                                     "TTBB-TTtoLNu2Q", "TTBB-TTtoLNu2Q_TuneCP5"])
@pytest.mark.parametrize("save_systematics", [False, True])
def test_ttbar_scale_numerators_and_signed_denominators(monkeypatch, dataset, save_systematics):
    # Different central LHE weights guard normalization by the central member.
    lhe = np.array([[2.4, 2.2, 2.6, 1.8, 2, 2.1, 1.4, 1.6, 1.5],
                    [1.6, 1.4, 1.8, 1.1, 1, .9, .8, .7, .6],
                    [.5, .6, .7, .8, 1, 1.1, 1.2, 1.3, 1.4]])
    events = ak.Array({"Pileup": {"nTrueInt": [20., 30., 40.]},
                       "PSWeight": np.ones((3, 4)), "LHEScaleWeight": lhe})
    gen = np.array([3., -2., 4.])
    pileup = np.array([1.1, .9, 1.2])

    def add_pileup(weights, _year, _ntrue):
        weights.add("pileup", pileup, pileup * 1.1, pileup * .9)

    monkeypatch.setattr(skimmer, "add_pileup_weight", add_pileup)
    monkeypatch.setattr(skimmer, "top_pt_weights", lambda _events, _dataset: {})
    processor = SimpleNamespace(_systematics=save_systematics,
                                get_dataset_norm=lambda _year, _dataset: 123.)
    weights, totals = skimmer.vcbSkimmer.add_weights(
        processor, events, "2024", dataset, gen, np.ones(3, dtype=bool))
    nominal = gen * pileup
    expected = lhe[:, [0, 1, 3, 5, 7, 8]] / lhe[:, 4, None]
    np.testing.assert_allclose(weights["weight"], 123 * nominal)
    np.testing.assert_allclose(weights["scale_weights"], 123 * nominal[:, None] * expected)
    np.testing.assert_allclose(totals["np_scale_weights"], (nominal[:, None] * expected).sum(axis=0))
    assert totals["np_nominal"] == pytest.approx(nominal.sum())
    assert "pdf_weights" not in weights  # No change to the separate PDF scope.
