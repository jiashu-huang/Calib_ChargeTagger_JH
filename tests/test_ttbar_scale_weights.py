"""Dedicated TTBB must retain scale variations and their all-input sums."""

from __future__ import annotations

from importlib import import_module
from types import SimpleNamespace

import awkward as ak
import numpy as np
import pytest

skimmer = import_module("vcb.processors.vcbSkimmer")


@pytest.mark.parametrize("dataset", ["TTtoLNu2Q", "TTtoLNuCB", "TT1L2Q",
                                     "TTBB-TTtoLNu2Q", "TTBB-TTtoLNu2Q_TuneCP5"])
@pytest.mark.parametrize("save_systematics", [False, True])
def test_ttbar_scale_numerators_and_signed_denominators(monkeypatch, dataset, save_systematics):
    # Different central LHE weights guard normalization by the central member.
    lhe = np.array([[2.4, 2.2, 2.6, 1.8, 2, 2.1, 1.4, 1.6, 1.5],
                    [1.6, 1.4, 1.8, 1.1, 1, .9, .8, .7, .6],
                    [.5, .6, .7, .8, 1, 1.1, 1.2, 1.3, 1.4]])
    pdf = np.array([[1., -2., 0.], [1., 3., 4.], [1., 2., 5.]])

    class Events:
        metadata = {"filename": "toy-input.root"}
        Pileup = SimpleNamespace(nTrueInt=ak.Array([20., 30., 40.]))
        PSWeight = ak.Array(np.ones((3, 4)))
        LHEScaleWeight = ak.Array(lhe)
        LHEPdfWeight = ak.Array(pdf)

        def __len__(self):
            return 3

    events = Events()
    gen = np.array([3., -2., 4.])
    pileup = np.array([1.1, .9, 1.2])

    def add_pileup(weights, _year, _ntrue):
        weights.add("pileup", pileup, pileup * 1.1, pileup * .9)

    monkeypatch.setattr(skimmer, "add_pileup_weight", add_pileup)
    monkeypatch.setattr(skimmer, "read_weight_prescription", lambda *_args: {
        "scale": {"input_members": 9}})
    monkeypatch.setattr(skimmer, "read_pdf_layout", lambda _name: {"lha_ids": [1, 2, 3]})
    monkeypatch.setattr(skimmer, "top_pt_weights_and_validity", lambda _events, _dataset: ({}, None))
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
    if save_systematics:
        np.testing.assert_array_equal(weights["PDFWeight"], pdf)
        np.testing.assert_allclose(totals["np_pdf_weights"], (nominal[:, None] * pdf).sum(axis=0))
    else:
        assert "PDFWeight" not in weights
