"""
Unit tests for the event-quality ("MET") filters in `vcb.processors.vcbSkimmer`.

Two things are pinned here. First the *contents* of `RUN3_MET_FILTERS`: the
Run-3 recommended set, and in particular the absence of the Run-2-only HBHE
noise filters, whose branches still exist in our private Summer24 NanoAOD and
so would be applied again by any "use whatever is in the file" logic.

Second the *failure mode*: `met_filter_mask` must raise on a missing branch
rather than skip it. A skipped filter is invisible — the cutflow still shows a
`met_filters` stage, it is just looser than it claims to be.

The mask itself is exercised on hand-built awkward records, no NanoAOD file.
"""

from __future__ import annotations

import awkward as ak
import numpy as np
import pytest

from vcb.processors.vcbSkimmer import RUN3_MET_FILTERS, met_filter_mask

# JME/JetMET POG Run-3 recommendation (TWiki MissingETOptionalFiltersRun2,
# "Run 3 recommendations"). Order-independent; the mask is an AND.
EXPECTED_RUN3_SET = {
    "goodVertices",
    "globalSuperTightHalo2016Filter",
    "EcalDeadCellTriggerPrimitiveFilter",
    "BadPFMuonFilter",
    "BadPFMuonDzFilter",
    "eeBadScFilter",
    "ecalBadCalibFilter",
    "hfNoisyHitsFilter",
}

# Run-2-only filters. Present as branches in the private Summer24 NanoAOD, but
# not part of the Run-3 recommendation and not validated for Run-3 conditions.
RUN2_ONLY = {"HBHENoiseFilter", "HBHENoiseIsoFilter"}


def _events(n: int, **overrides: np.ndarray):
    """Minimal stand-in for NanoEvents: just the `Flag` record it needs.

    All configured filters default to all-True; `overrides` sets individual
    flags, and passing `drop=` is done by the caller building its own dict.
    """
    flags = {mf: np.ones(n, dtype=bool) for mf in RUN3_MET_FILTERS}
    flags.update(overrides)
    return ak.zip({"Flag": ak.zip(flags)}, depth_limit=1)


class TestRun3FilterList:
    def test_matches_pog_recommendation(self):
        assert set(RUN3_MET_FILTERS) == EXPECTED_RUN3_SET

    def test_no_duplicates(self):
        assert len(RUN3_MET_FILTERS) == len(set(RUN3_MET_FILTERS))

    def test_excludes_run2_only_filters(self):
        assert not (set(RUN3_MET_FILTERS) & RUN2_ONLY), (
            "HBHE noise filters are Run-2 only; their branches exist in Run-3 "
            "NanoAOD but the POG does not recommend them for Run 3."
        )


class TestMask:
    def test_all_pass(self):
        mask = met_filter_mask(_events(5), "2024")
        assert mask.dtype == np.dtype(bool)
        assert mask.tolist() == [True] * 5

    def test_single_failing_flag_vetoes_event(self):
        bad = np.array([True, False, True, True, True])
        mask = met_filter_mask(_events(5, ecalBadCalibFilter=bad), "2024")
        assert mask.tolist() == [True, False, True, True, True]

    def test_and_over_all_filters(self):
        # Each filter vetoes a different event: nothing survives.
        overrides = {}
        for i, mf in enumerate(RUN3_MET_FILTERS):
            v = np.ones(len(RUN3_MET_FILTERS), dtype=bool)
            v[i] = False
            overrides[mf] = v
        mask = met_filter_mask(_events(len(RUN3_MET_FILTERS), **overrides), "2024")
        assert not mask.any()

    def test_missing_branch_raises(self):
        n = 3
        flags = {mf: np.ones(n, dtype=bool) for mf in RUN3_MET_FILTERS}
        dropped = flags.pop("hfNoisyHitsFilter")
        assert dropped is not None  # sanity: the name was really in the set
        events = ak.zip({"Flag": ak.zip(flags)}, depth_limit=1)

        with pytest.raises(KeyError, match="hfNoisyHitsFilter"):
            met_filter_mask(events, "2024")
