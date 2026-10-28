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
                     The stored Run 3 extrapolation; adoption requires an
                     analysis-specific modelling choice.

For this repo both TOP PAG use cases apply: the SPANet reconstruction
efficiency is an MC-derived efficiency (case 1, which points at ``dataNLO``),
while W->cb signal sitting inside the same ttbar production is case 3.2 (which
points at ``NNLONLO``). That is why nothing here is applied centrally; see "Why
branches, not a weight" below.

``NNLONLO_13p6TeV`` is the only column here carried to 13.6 TeV. This
processor does not implement a measured 13.6 TeV data/NLO correction.
The choice for an efficiency or spectrum study therefore requires a separate
analysis decision; storing the theory extrapolation does not settle it.

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
   a full-Run-2 update is not implemented here. These stored data fits have
   not been replaced by a measured 13.6 TeV correction in this processor.

   That asymmetry is not an accident of bookkeeping. ``NNLONLO`` could be
   carried to 13.6 TeV precisely because it is a ratio of two *calculations*,
   both evaluable at any sqrt(s); the ``data*`` functions have a 2015 dataset,
   a Run 2 tune and a Run 2 PDF baked in, and no principled claim on Summer24
   samples. ``NNLONLO_13p6TeV`` is the available theory extrapolation here;
   retaining it does not establish its validity for every generator or use.

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

Sample scope
------------
The saved factors cover the named ttbar samples, including TTBB-TTtoLNu2Q.
This is not a universal prescription to apply them to every generator. CMS
TOP-22-009 section 7.2 applies a top-pT modelling treatment to its ttbar
components, including ttbb, while excluding single top and ttV/ttH. The
Summer24 analysis must choose and validate its own nominal model. The
``is_ttbar`` name match is also used for truth and generator-weight handling;
it must not be confused with physics approval of a correction.

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
* The optional normalization is now preserved over all input events, including
  rejected events: ``Norm/np_topPtWeight_*`` and its joint PU/shower/scale/PDF
  alternatives. This enables an inclusive-normalization-preserving choice
  downstream without changing the nominal model here. Lepton SFs and sigma*L
  do not enter these sums. Invalid top pairs retain unity factors and carry
  ``TopPtWeightValid=False``; their contributions are not discarded.

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
# (it would cross zero around 7.3 TeV).
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

    AN-25-050 eq. 2 x eq. 3 -- the stored Run 3 extrapolation.
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
    """Recognize supported ttbar sample names, including dedicated TTBB names.

    This is a routing predicate, not a physics-applicability statement.
    """
    return any(name in dataset for name in TTBAR_DATASETS)


def gen_top_pt(events: NanoEventsArray) -> tuple[np.ndarray, np.ndarray]:
    """
    The two gen top pT values per event, and a mask of events that really have
    one top and one antitop with finite, nonnegative pT.

    Returns ``(pt, has_two)`` where ``pt`` is ``(n_events, 2)``. Events without
    exactly two hard-process last-copy tops are padded with 0.0 and flagged
    ``False`` in ``has_two`` -- the caller unweights them rather than feeding
    a made-up pT into the fit.
    """
    tops = events.GenPart[
        (abs(events.GenPart.pdgId) == TOP_PDGID) * events.GenPart.hasFlags(GEN_FLAGS)
    ]
    has_two = ak.to_numpy((ak.num(tops, axis=1) == 2) & (ak.sum(tops.pdgId, axis=1) == 0))
    # Pad/clip to exactly two so the result is rectangular; the fill value is
    # irrelevant because `has_two` masks those rows out downstream.
    padded = ak.fill_none(ak.pad_none(tops.pt, 2, axis=1, clip=True), 0.0)
    pt = ak.to_numpy(padded).astype(np.float64)
    valid = has_two & np.all(np.isfinite(pt) & (pt >= 0), axis=1)
    return np.where(valid[:, None], pt, 0.), valid


def top_pt_weights_and_validity(events: NanoEventsArray, dataset: str) -> tuple[dict, np.ndarray | None]:
    """
    Per-event top-pT reweighting factors for ttbar MC.

    Returns factors and a validity mask, or ({}, None) for a non-ttbar dataset.
    Invalid top pairs get 1.0, without pretending a correction was measured.

    These are **raw scale factors**: not applied to ``weight``, not scaled by
    sigma*L. Applying them -- or not -- is a downstream decision. On Run 3
    samples the column to use is ``RECOMMENDED_COLUMN``; see the module
    docstring for why the ``data*`` ones do not qualify.
    """
    global _WARNED

    if not is_ttbar(dataset):
        return {}, None

    if not _WARNED:
        logger.warning(
            "top-pT reweighting: writing %s. None is applied -- raw SFs only, not in "
            "`weight`. %s is the stored 13.6 TeV extrapolation (AN-25-050 eq. 2 x eq. 3); "
            "its adoption remains an analysis choice, including for dedicated TTBB. "
            "The two topPtWeight_data* columns are historical 13 TeV comparisons. "
            "See src/vcb/processors/top_pt.py.",
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

    return weights, has_two


def top_pt_weights(events: NanoEventsArray, dataset: str) -> dict[str, np.ndarray]:
    """Backward-compatible factor-only interface; no factors enter nominal weight."""
    return top_pt_weights_and_validity(events, dataset)[0]


def top_pt_normalization(factors: dict, base, suffix: str = "", ratios=None) -> dict:
    """Signed all-input sums, optionally with a vector of generator alternatives.

    ``base`` contains genWeight times nominal or varied pileup/shower factors,
    never lepton efficiencies or sigma*L. No selected-event average is used.
    """
    if not factors:
        return {}
    if set(factors) != set(SF_FUNCTIONS):
        raise ValueError("Incomplete top-pT factor set")
    base = np.asarray(base, dtype=np.float64)
    if base.ndim != 1 or not np.all(np.isfinite(base)):
        raise ValueError("Top-pT normalization requires finite event weights")
    if ratios is not None:
        ratios = np.asarray(ratios)
        if ratios.ndim != 2 or ratios.shape[0] != len(base) or not np.all(np.isfinite(ratios)):
            raise ValueError("Top-pT normalization requires finite rectangular ratios")
    result = {}
    for column, factor in factors.items():
        factor = np.asarray(factor, dtype=np.float64)
        if factor.shape != base.shape or not np.all(np.isfinite(factor)):
            raise ValueError(f"Invalid top-pT factors for {column}")
        values = base * factor
        total = np.sum(values) if ratios is None else np.einsum("i,ij->j", values, ratios)
        if not np.all(np.isfinite(total)):
            raise ValueError(f"Nonfinite top-pT normalization for {column}")
        result[f"np_{column}{'_' + suffix if suffix else ''}"] = total
    return result


def top_pt_prescription(enabled: bool) -> dict:
    """Record the numerical definitions; applicability remains an analysis choice."""
    return {
        "enabled": enabled,
        "columns": list(SF_FUNCTIONS),
        "validity_column": "TopPtWeightValid",
        "top_selection": "fromHardProcess and isLastCopy; one t and one tbar; finite nonnegative pT",
        "invalid_pair": "Unity factors with false validity; retain contribution in every sum",
        "input_event_count": "Norm/n_input_events; legacy nevents is sum(genWeight) for MC",
        "event_factor": "sqrt(f(pt_top) * f(pt_antitop))",
        "dataNLO": {"a": DATA_NLO_A, "b": DATA_NLO_B, "pt_clamp_GeV": DATA_PT_CLAMP},
        "dataNNLO": {"a": DATA_NNLO_A, "b": DATA_NNLO_B, "pt_clamp_GeV": DATA_PT_CLAMP},
        "NNLONLO": {"A": NNLO_NLO_A, "B": NNLO_NLO_B, "C": NNLO_NLO_C,
                    "D": NNLO_NLO_D, "pt_clamp_GeV": NNLO_PT_CLAMP},
        "NNLONLO_13p6TeV": {"multiply_NNLONLO_by": "a + b * clipped_pt",
                            "a": RUN3_EXTRAP_A, "b": RUN3_EXTRAP_B},
        "normalization": "Signed all-input genWeight * PU * factor; no lepton SF or sigma*L",
        "joint_sums": "For each saved np_* denominator, store np_topPtWeight_<model>_<suffix>; nominal has no suffix",
        "nominal_application": False,
        "scope": "Preserved diagnostics for named ttbar samples including TTBB; not approval for all generators",
    }
