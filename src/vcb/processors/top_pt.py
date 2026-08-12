"""
Top-pT reweighting for ttbar MC -- TOP PAG parameterisations, stored as
standalone branches rather than folded into ``weight``.

The problem it corrects
-----------------------
The pT spectrum of top quarks measured in data is *softer* than the one
POWHEG+Pythia8 predicts: simulation makes too many hard tops. The effect was
found in Run 1, confirmed in Run 2, and seen by ATLAS too. It is understood to
be at least partly an artefact of the generator stopping at NLO in QCD -- the
NNLO QCD corrections and the (negative, pT-growing) NLO electroweak Sudakov
logarithms both soften the spectrum in the direction the data wants.

The fix is a per-event weight built from the two generated top quarks:

    w = sqrt( SF(pT_t) * SF(pT_tbar) )

with ``SF`` a smooth function of a *single* top's pT.

The four parameterisations
--------------------------
Four columns are written, and they are not interchangeable:

``dataNLO``          ratio of unfolded data (parton level) to POWHEG+Pythia8.
                     Recommended when ttbar MC models the *detector response*
                     -- trigger, ID, b-tag, reconstruction efficiencies (use
                     case 1). **Run 2 only.**

``dataNNLO``         ratio of unfolded data to the "NNLO QCD + NLO EW"
                     prediction. A *cross-check* tool, not a default
                     correction. **Run 2 only.**

``NNLONLO``          ratio of "NNLO QCD + NLO EW" to POWHEG+Pythia8 (CP5).
                     Pure theory -- no dataset enters. Prescribed for NLO-QCD
                     *signal* samples in analyses where SM ttbar is both
                     signal and background (use case 3.2). **13 TeV.**

``NNLONLO_13p6TeV``  ``NNLONLO`` times the 13 -> 13.6 TeV extrapolation.
                     **The Run 3 column, and the one to use on these
                     samples.**

For this repo both TOP PAG use cases apply: the SPANet reconstruction
efficiency is an MC-derived efficiency (case 1, which points at ``dataNLO``),
while W->cb signal sitting inside the same ttbar production is case 3.2 (which
points at ``NNLONLO``). That is why nothing here is applied centrally; see "Why
branches, not a weight" below.

In practice ``NNLONLO_13p6TeV`` serves both on Summer24, since it is the only
column carried to 13.6 TeV -- the case-1 route would need a ``dataNLO`` that
nobody has derived at this beam energy. If that gap matters for a result, the
honest fix is a self-derived control-region reweighting (TOP PAG case 3.1),
not stretching a 2015 fit.

The 13.6 TeV extrapolation
--------------------------
The ``NNLONLO`` fit was derived at 13 TeV. AN-25-050 (v11), the analysis note
for TOP-25-018, extrapolates it to 13.6 TeV by fitting the ratio of the
generator-level top pT spectrum between the two beam energies (their eq. 3),
and applies it *on top of* the 13 TeV weight (their eq. 2). The procedure is
taken from the 13.6 TeV tW measurement, TOP-23-008 / JHEP 01 (2025) 107.

So the per-top scale factor for Run 3 is the product

    SF_13.6(pT) = SF_NNLONLO(pT) * SF_extrap(pT)

and the event weight is the usual geometric mean over the two tops. The
extrapolation *rises* with pT (0.991 at pT = 0, crossing 1 near 120 GeV),
partly counteracting the fall of the 13 TeV term -- the spectrum is slightly
harder at the higher beam energy.

The extrapolation is defined only as an add-on to ``NNLONLO``; AN-25-050 does
not apply it to the data-based fits, and neither do we. Inventing a
``dataNLO_13p6TeV`` would be our extrapolation, not anybody's recommendation.

.. warning::

   **The two ``data*`` columns remain Run 2 (13 TeV) numbers with no Run 3
   counterpart.**

   The source twiki is frozen at revision r31, 2020-09-24, and those functions
   are fitted to 2.2-2.3 fb-1 of *2015* 13 TeV data (TOP-16-011, TOP-16-008);
   the page's own promise of a full-Run-2 update "soon (08/2020)" never
   landed. No 13.6 TeV differential ttbar cross section unfolded to
   parton-level top pT exists anywhere, so the TOP PAG cannot derive Run 3
   versions of them until somebody measures the input.

   That asymmetry is not an accident of bookkeeping. ``NNLONLO`` could be
   carried to 13.6 TeV precisely because it is a ratio of two *calculations*,
   both evaluable at any sqrt(s); the ``data*`` functions have a 2015 dataset,
   a Run 2 tune and a Run 2 PDF baked in, and no principled claim on Summer24
   samples. Use ``NNLONLO_13p6TeV`` unless you have a specific reason not to.

Which tops
----------
``SF`` must be evaluated on the **parton-level top after radiation and before
decay** -- the ``isLastCopy`` definition. The twiki is explicit that a reco-
or particle-level proxy "will result in an invalid reweighting". This module
imports ``TOP_PDGID`` and ``GEN_FLAGS`` from the same places
``GenSelection.gen_selection_Vcb`` does, so the two can never drift apart.

AN-25-050 phrases the same selection differently -- it fits the extrapolation
"looking only at top particles with status 62", the Pythia8 code for an
outgoing hard-process parton after radiation. On the 2024 fixture the two
definitions are not merely equivalent in spirit but identical particle for
particle: over 200 000 events, ``|pdgId| == 6 & fromHardProcess & isLastCopy``
and ``|pdgId| == 6 & status == 62`` select exactly the same GenParticles, both
giving two tops in every event. So eq. 3 is being applied to the objects it
was fitted on.

Not for single top or ttX
-------------------------
The TOP PAG weights are derived on inclusive ttbar and are explicitly *not*
to be used for single top or ttX (X = V, H, bb/cc): top production may look
similar, but there is no evidence the same mismodelling applies, and those
processes need their own differential measurements. ``TTBAR_DATASETS`` below
is the gate; keep it ttbar-only.

Why branches, not a weight
--------------------------
Nothing here enters the coffea ``Weights`` container, so nothing here reaches
``weight``, ``finalWeight`` or the ``np_nominal`` denominator. Each function
is written as its own output column carrying the *raw* SF -- no sigma*L, in
deliberate contrast to the ``single_weight_*`` diagnostics, which do carry it
(see docs/normalization.md). Downstream multiplies in whichever column it
wants, or none.

Three reasons that is the right shape:

* The recommended systematic is **on/off**, not up/down. The twiki says in as
  many words that deriving it by applying the reweighting twice, or in
  opposite directions, is *not* recommended. Separate columns give "without"
  by not multiplying and "with" by multiplying -- no division, no inverse.
* The choice between ``dataNLO`` and ``NNLONLO`` is still open, and so is the
  question of whether TOP-PAG's answer changes it.
* Folding a factor into ``weight`` entangles it with ``finalWeight = weight /
  np_nominal``, and whether top-pT belongs in that denominator is an
  unresolved normalization question. Note the denominator sums over *all*
  events read, before cuts -- so it cannot be reconstructed from the skim
  afterwards. Keeping these columns out of ``weight`` leaves that decision
  open instead of silently making it.

Sources
-------
* TOP PAG twiki (CERN SSO), r31 2020-09-24 -- all four base functions:
  https://twiki.cern.ch/twiki/bin/view/CMS/TopPtReweighting
* AN-25-050 (v11), the analysis note for **TOP-25-018**, section 4.7 -- the
  13 -> 13.6 TeV extrapolation, its eq. 3; the 13 TeV function is its eq. 2.
* Czakon et al., "Top-pair production at the LHC through NNLO QCD and NLO EW",
  JHEP 10 (2017) 186, arXiv:1705.04105 -- theory behind NNLONLO.
* CMS, tW at 13.6 TeV, JHEP 01 (2025) 107, arXiv:2409.06444 (TOP-23-008) --
  where AN-25-050 took the extrapolation procedure from.

Author: Jiashu Huang (Brown U)
"""

from __future__ import annotations

import logging

import awkward as ak
import numpy as np
from coffea.nanoevents.methods.base import NanoEventsArray

from boostedhh.processors.utils import GEN_FLAGS

from .GenSelection import TOP_PDGID

logger = logging.getLogger(__name__)

# Datasets these weights may be applied to. ttbar only -- see the module
# docstring on single top / ttX. Matched as substrings of the dataset name,
# the same convention `vcbSkimmer.process` uses for `gen_selection_dict`.
TTBAR_DATASETS = (
    "TTtoLNuCB",  # 2024 Summer24 private production, W->cb forced
    "TT1L2Q",  # legacy 2022 private sample naming
    "TTtoLNu2Q",  # central semileptonic ttbar
)

# Fit coefficients, transcribed from the twiki (r31, 2020-09-24).
#   data-NLO   SF(pT) = exp(a + b * pT)                 [data / POWHEG+Pythia8]
#   data-NNLO  SF(pT) = exp(a + b * pT)                 [data / NNLO]
#   NNLO-NLO   SF(pT) = A * exp(-B * pT) - C * pT + D   [(NNLO QCD + NLO EW) / POWHEG+Pythia8 CP5]
DATA_NLO_A, DATA_NLO_B = 0.0615, -0.0005
DATA_NNLO_A, DATA_NNLO_B = 0.0416, -0.0003
NNLO_NLO_A, NNLO_NLO_B, NNLO_NLO_C, NNLO_NLO_D = 0.103, 0.0118, 0.000134, 0.973

# 13 -> 13.6 TeV extrapolation of the NNLO-NLO weight, from AN-25-050 (v11)
# section 4.7 eq. 3 -- the analysis note for TOP-25-018:
#
#   SF(t) = 0.991 + 0.000075 * pT
#
# Fitted to the ratio of the generator-level top pT spectrum between 13 TeV and
# 13.6 TeV, on tops with Pythia8 status 62. AN-25-050 applies it multiplicatively
# on top of its eq. 2 (our NNLO_NLO_*), and took the procedure from the 13.6 TeV
# tW measurement, TOP-23-008 / JHEP 01 (2025) 107.
#
# Only defined as an add-on to NNLO-NLO. The AN does not extrapolate the
# data-based fits and neither do we.
RUN3_EXTRAP_A, RUN3_EXTRAP_B = 0.991, 0.000075

# Above 500 GeV the twiki says to hold the data-based weight at its 500 GeV
# value -- the measurements it is fitted to do not extend further.
DATA_PT_CLAMP = 500.0

# The twiki gives no equivalent rule for NNLO-NLO. Its figure is drawn to
# 2000 GeV, so that is where we clamp: **our choice, not twiki text**, made so
# a pathological gen pT cannot walk the linear term down to a negative weight
# (it would cross zero around 7.3 TeV). No top in 124 fb-1 comes close, so
# this is a guard rail rather than a physics statement.
NNLO_PT_CLAMP = 2000.0

# Emit the Run 2 provenance warning once per process, not once per chunk.
_WARNED = False


def _sf_data_nlo(pt: np.ndarray) -> np.ndarray:
    """data / POWHEG+Pythia8, per top. Clamped above 500 GeV per the twiki."""
    pt = np.clip(pt, 0.0, DATA_PT_CLAMP)
    return np.exp(DATA_NLO_A + DATA_NLO_B * pt)


def _sf_data_nnlo(pt: np.ndarray) -> np.ndarray:
    """data / NNLO, per top. Clamped above 500 GeV per the twiki."""
    pt = np.clip(pt, 0.0, DATA_PT_CLAMP)
    return np.exp(DATA_NNLO_A + DATA_NNLO_B * pt)


def _sf_nnlo_nlo(pt: np.ndarray) -> np.ndarray:
    """
    (NNLO QCD + NLO EW) / POWHEG+Pythia8 CP5, per top, **at 13 TeV**.
    AN-25-050 eq. 2. Clamped at the fit range.
    """
    pt = np.clip(pt, 0.0, NNLO_PT_CLAMP)
    return NNLO_NLO_A * np.exp(-NNLO_NLO_B * pt) - NNLO_NLO_C * pt + NNLO_NLO_D


def _sf_run3_extrapolation(pt: np.ndarray) -> np.ndarray:
    """
    13 -> 13.6 TeV extrapolation factor, per top. AN-25-050 eq. 3.

    Rises with pT (0.991 at pT = 0, crossing 1 near 120 GeV): the spectrum is
    slightly harder at the higher beam energy, so this partly counteracts the
    fall of the 13 TeV term. Never used alone -- only as a multiplier on
    ``_sf_nnlo_nlo``. Shares that function's clamp so the product is flat above
    the fit range rather than continuing to rise.
    """
    pt = np.clip(pt, 0.0, NNLO_PT_CLAMP)
    return RUN3_EXTRAP_A + RUN3_EXTRAP_B * pt


def _sf_nnlo_nlo_13p6tev(pt: np.ndarray) -> np.ndarray:
    """
    (NNLO QCD + NLO EW) / POWHEG+Pythia8 CP5 **at 13.6 TeV**, per top.

    AN-25-050 eq. 2 x eq. 3 -- the Run 3 prescription, and the right column for
    Summer24 samples.
    """
    return _sf_nnlo_nlo(pt) * _sf_run3_extrapolation(pt)


# Column name -> per-top scale factor. The names follow the twiki's own
# vocabulary (data-NLO, data-NNLO, NNLO-NLO) so there is no translation step
# between what the recommendation says and what the branch is called;
# `_13p6TeV` marks the one carrying AN-25-050's beam-energy extrapolation.
SF_FUNCTIONS = {
    "topPtWeight_dataNLO": _sf_data_nlo,
    "topPtWeight_dataNNLO": _sf_data_nnlo,
    "topPtWeight_NNLONLO": _sf_nnlo_nlo,
    "topPtWeight_NNLONLO_13p6TeV": _sf_nnlo_nlo_13p6tev,
}

# The column to reach for on Run 3 samples, named once so docs and downstream
# code can refer to it without re-deriving the argument for it.
RECOMMENDED_COLUMN = "topPtWeight_NNLONLO_13p6TeV"


def is_ttbar(dataset: str) -> bool:
    """True if `dataset` is one of the ttbar samples these weights are valid for."""
    return any(name in dataset for name in TTBAR_DATASETS)


def gen_top_pt(events: NanoEventsArray) -> tuple[np.ndarray, np.ndarray]:
    """
    The two gen top pT values per event, and a mask of events that really have
    two.

    Returns ``(pt, has_two)`` where ``pt`` is ``(n_events, 2)``. Events without
    exactly two hard-process last-copy tops are padded with 0.0 and flagged
    ``False`` in ``has_two`` -- the caller unweights them rather than feeding
    a made-up pT into the fit.
    """
    tops = events.GenPart[
        (abs(events.GenPart.pdgId) == TOP_PDGID) * events.GenPart.hasFlags(GEN_FLAGS)
    ]
    has_two = ak.to_numpy(ak.num(tops, axis=1) == 2)
    # Pad/clip to exactly two so the result is rectangular; the fill value is
    # irrelevant because `has_two` masks those rows out downstream.
    padded = ak.fill_none(ak.pad_none(tops.pt, 2, axis=1, clip=True), 0.0)
    return ak.to_numpy(padded).astype(np.float64), has_two


def top_pt_weights(events: NanoEventsArray, dataset: str) -> dict[str, np.ndarray]:
    """
    Per-event top-pT reweighting factors for ttbar MC.

    Returns one array per parameterisation, keyed by output branch name, or an
    empty dict for a non-ttbar dataset (so a caller can ``.update()`` the
    result unconditionally). Events without exactly two gen tops get 1.0.

    These are **raw scale factors**: not applied to ``weight``, not scaled by
    sigma*L. Applying them -- or not -- is a downstream decision. On Run 3
    samples the column to use is ``RECOMMENDED_COLUMN``; see the module
    docstring for why the ``data*`` ones do not qualify.
    """
    global _WARNED

    if not is_ttbar(dataset):
        return {}

    if not _WARNED:
        logger.warning(
            "top-pT reweighting: writing %s. None is applied -- raw SFs only, not in "
            "`weight`. On Run 3 samples use %s (AN-25-050 eq. 2 x eq. 3, i.e. the "
            "13 TeV NNLO-NLO fit carried to 13.6 TeV). The two topPtWeight_data* "
            "columns are 13 TeV fits with no Run 3 counterpart and do not apply to "
            "Summer24. See src/vcb/processors/top_pt.py.",
            ", ".join(SF_FUNCTIONS),
            RECOMMENDED_COLUMN,
        )
        _WARNED = True

    pt, has_two = gen_top_pt(events)

    weights = {}
    for name, sf in SF_FUNCTIONS.items():
        # w = sqrt(SF(t) * SF(tbar)) -- the geometric mean over the two tops.
        per_top = sf(pt)
        weights[name] = np.where(has_two, np.sqrt(per_top[:, 0] * per_top[:, 1]), 1.0)

    return weights
