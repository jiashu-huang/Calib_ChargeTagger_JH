"""
Lepton (electron / muon) scale factors for the Vcb single-lepton skim.

A scale factor is the ratio ``eff_data / eff_MC`` of a selection efficiency
measured in data to the same efficiency measured in simulation, published by
the POGs from tag-and-probe fits on Z -> ll events. Simulation does not
reproduce reconstruction, identification, isolation or trigger efficiencies
perfectly, so every MC event is reweighted by the product of the SFs of the
lepton it was selected on. Data is untouched.

This skim selects events on a single-lepton trigger and designates exactly one
"trigger lepton" per event (see ``vcbSkimmer.process``); the SFs therefore
apply to that lepton and factorize into the steps of its selection:

    electron:  reco x ID(mvaIso_WP90) x HLT(Ele30)
    muon:      ID(tight) x PFIso(tight) x HLT(IsoMu24)

Each step enters the coffea ``Weights`` container under its own name, so the
uncertainties stay separable per flavour and per step downstream. Events with
no trigger lepton, and every event of the other flavour, get exactly 1.0.

The muon reco SF is not applied: MUO publishes none for Summer24 in this
campaign (their tracking efficiency is ~1 above 10 GeV). The electron energy
scale/smearing correction (EGM ``electronSS_EtDependent``) is a *correction to
the lepton*, not a weight, and is out of scope here.

On the ECAL crack. EGM did not measure the electron *ID* SF for
1.444 < |scEta| < 1.566 and fills those bins with exactly 1.0 and **zero**
uncertainty (reco and HLT are measured there normally). ``good_electrons``
therefore vetoes the crack outright -- ``objects.in_ecal_crack``, using the
same ``electron_supercluster_eta`` imported here and the SF bin edges
themselves -- so no electron reaching this module can land in an unmeasured
bin. If that veto is ever relaxed, this caveat comes back with it.

Analysis-local by design -- the working points below must track
``objects.good_electrons`` / ``objects.good_muons``, which are Vcb choices, so
this lives in ``vcb`` rather than in the vendored ``boostedhh``.

Author: Jiashu Huang (Brown U)
"""

from __future__ import annotations

import gzip
import json
import logging
import math
from functools import cache
from pathlib import Path

import awkward as ak
import correctionlib
import numpy as np
from coffea.analysis_tools import Weights

# Same helper the crack veto uses, so the SF and the selection can never end up
# binned in two different eta conventions.
from .objects import electron_supercluster_eta

logger = logging.getLogger(__name__)

package_path = Path(__file__).parent.parent.resolve()  # src/vcb

# -----------------------------------------------------------------------------
# Where the payloads come from
# -----------------------------------------------------------------------------
# The CAT metadata tree, same source (and same campaign) as the 2024 pile-up
# weights and jet JEC/JER this repo already bundles. It is used instead of
# jsonpog-integration because the jsonpog 2024 snapshot ships *no* lepton
# trigger SFs at all, and its electron payload is missing the RecoBelow20
# piece -- see src/vcb/corrections/README.md.
_CAT_METADATA = "/cvmfs/cms-griddata.cern.ch/cat/metadata"
_CAMPAIGN_2024 = "Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15"

# payload -> (file bundled under corrections/, cvmfs fallback path)
LEPTON_SF_SOURCES = {
    "2024": {
        "electron": (
            "2024_electron.json.gz",
            f"{_CAT_METADATA}/EGM/{_CAMPAIGN_2024}/latest/electron.json.gz",
        ),
        "electron_hlt": (
            "2024_electronHlt.json.gz",
            f"{_CAT_METADATA}/EGM/{_CAMPAIGN_2024}/latest/electronHlt.json.gz",
        ),
        "muon": (
            "2024_muon_Z.json.gz",
            f"{_CAT_METADATA}/MUO/{_CAMPAIGN_2024}/latest/muon_Z.json.gz",
        ),
    },
}

# -----------------------------------------------------------------------------
# Which correction / working point inside each payload
# -----------------------------------------------------------------------------
# Every entry here is pinned to an object-selection choice made elsewhere; a
# change on either side must be mirrored, or the SF stops describing the
# selection it is meant to correct:
#
#   electron_id_wp     <- objects.good_electrons: `mvaIso_WP90`
#   electron_hlt_path  <- HLTs.py single-e path (Ele30) x the ID above
#   muon_id            <- objects.good_muons: `tightId`
#   muon_iso           <- objects.good_muons: `pfRelIso04_all < 0.15`
#   muon_hlt           <- HLTs.py single-mu path (IsoMu24) x the two above
#
# `egm_campaign` is EGM's own label for the measurement, not the calendar year.
LEPTON_SF_KEYS = {
    "2024": {
        "egm_campaign": "2024Prompt",
        "electron_id_wp": "wp90iso",
        "electron_hlt_path": "HLT_SF_Ele30_MVAiso90ID",
        "muon_id": "NUM_TightID_DEN_TrackerMuons",
        "muon_iso": "NUM_TightPFIso_DEN_TightID",
        "muon_hlt": "NUM_IsoMu24_DEN_CutBasedIdTight_and_PFIsoTight",
    },
}

EGM_ID_CORRECTION = "Electron-ID-SF"  # holds reco *and* every ID working point
EGM_HLT_CORRECTION = "Electron-HLT-SF"

# EGM splits the reconstruction SF into three disjoint pT pieces, each its own
# "working point"; the caller picks by pT. (name, pT low, pT high)
ELECTRON_RECO_WPS = (
    ("RecoBelow20", 10.0, 20.0),
    ("Reco20to75", 20.0, 75.0),
    ("RecoAbove75", 75.0, np.inf),
)

# Binning limits. Every one of these payloads declares flow="error", so an
# input outside the covered range raises instead of extrapolating; clip to the
# edge, which is the POG-recommended treatment. All are below the analysis
# thresholds in objects.py (electron pT > 20 / >= 32 when trigger-matched, muon
# pT > 20 / >= 26, |eta| < 2.5 / 2.4), so in practice the clips never bite --
# they are guards against a future loosening of those cuts, not corrections.
ELECTRON_ID_PT_MIN = 10.0
ELECTRON_HLT_PT_MIN = 25.0
MUON_PT_MIN = 10.0
MUON_HLT_PT_MIN = 26.0
MUON_ETA_MAX = 2.4  # upper edge is exclusive, hence the nextafter() below

# Uncertainty labels: EGM varies through a `ValType` category, MUO through a
# `scale_factors` one. Both up/down are absolute SF values (nominal +- total
# uncertainty), not multiplicative shifts.
EGM_VALTYPES = ("sf", "sfup", "sfdown")
MUO_VALTYPES = ("nominal", "systup", "systdown")

_unsupported_year_warned = set()


# -----------------------------------------------------------------------------
# Loading
# -----------------------------------------------------------------------------


def _canonicalize_infinities(node, in_edges: bool = False):
    """
    Rewrite the string edge encoding ``"inf"`` / ``"-inf"`` to real floats.

    correctionlib is pinned to 2.5.0 (pyproject.toml), which only understands
    the bare JSON ``Infinity`` literal in a binning `edges` array. The CAT
    payloads switched to the quoted spelling -- MUO on 2026-06-18, "Was using
    Infinity, but correct one is 'inf'" -- and 2.5.0 rejects those files
    outright ("Invalid edges array type"). Converting back to floats lets
    ``json.dumps`` emit ``Infinity`` again on the way into correctionlib.

    Only strings *inside* an ``edges`` value are touched, so correction names
    and category keys are left alone. A payload that already uses ``Infinity``
    passes through unchanged.
    """
    if isinstance(node, str):
        if in_edges:
            if node == "inf":
                return math.inf
            if node == "-inf":
                return -math.inf
        return node
    if isinstance(node, list):
        return [_canonicalize_infinities(item, in_edges) for item in node]
    if isinstance(node, dict):
        return {key: _canonicalize_infinities(val, key == "edges") for key, val in node.items()}
    return node


@cache
def _load_correctionset(bundled: str, cvmfs: str, what: str):
    """
    Load a CorrectionSet, preferring the bundled repo copy over cvmfs.

    Bundled-first matches the JEC/JER and pile-up loaders: condor workers then
    need neither network nor a particular cvmfs snapshot. Returns None (with a
    warning) if neither path exists, so a missing payload costs those SFs
    rather than killing the job.

    Cached: the muon payload is ~750 kB of JSON and would otherwise be parsed
    once per chunk.
    """
    for path, tag in ((bundled, "bundled"), (cvmfs, "cvmfs")):
        if Path(path).is_file():
            with gzip.open(path, "rt") as fh:
                payload = json.load(fh)
            logger.info(f"{what}: using {tag} {path}")
            return correctionlib.CorrectionSet.from_string(
                json.dumps(_canonicalize_infinities(payload))
            )
    logger.warning(f"{what} not found (bundled or cvmfs); those scale factors are skipped.")
    return None


def get_lepton_correctionsets(year: str) -> dict | None:
    """CorrectionSets for `year` keyed as in LEPTON_SF_SOURCES, or None if the
    year has no lepton SFs wired up."""
    sources = LEPTON_SF_SOURCES.get(year)
    if sources is None:
        return None
    return {
        name: _load_correctionset(
            str(package_path / "corrections" / bundled), cvmfs, f"Lepton SF {year} {name}"
        )
        for name, (bundled, cvmfs) in sources.items()
    }


# -----------------------------------------------------------------------------
# Per-lepton kinematics
# -----------------------------------------------------------------------------


def _flat(values, mask: np.ndarray, default: float) -> np.ndarray:
    """
    Per-event float array, with `default` wherever the lepton is absent.

    Masked-out entries are still handed to correctionlib (evaluating the whole
    array is far cheaper than compacting it), so the default must sit inside
    every binning -- an out-of-range value there would raise for events the
    result is then thrown away for.
    """
    flat = ak.fill_none(values, default).to_numpy().astype(np.float64)
    return np.where(mask, flat, default)


# -----------------------------------------------------------------------------
# Scale factor evaluation
# -----------------------------------------------------------------------------


def _electron_reco_sf(corr, campaign: str, valtype: str, eta, pt) -> np.ndarray:
    """
    Reco SF, stitched from EGM's three disjoint pT pieces.

    Each piece is evaluated over the full array with pT parked at its own lower
    edge outside the piece's range -- an in-range dummy whose result is then
    discarded by the np.where. Electrons below 10 GeV fall in no piece and keep
    1.0; the analysis cut is 20 GeV, so that never happens here.
    """
    sf = np.ones_like(pt)
    for wp, low, high in ELECTRON_RECO_WPS:
        in_piece = (pt >= low) & (pt < high)
        if not in_piece.any():
            continue
        safe_pt = np.where(in_piece, pt, low)
        sf = np.where(in_piece, corr.evaluate(campaign, valtype, wp, eta, safe_pt), sf)
    return sf


def electron_scale_factors(csets: dict, year: str, eta: np.ndarray, pt: np.ndarray) -> dict:
    """
    ``{step: (nominal, up, down)}`` for the reco / ID / trigger steps.

    `eta` must be supercluster eta and `pt` the electron pT, both per-event and
    already defaulted for events without a trigger electron.
    """
    keys = LEPTON_SF_KEYS[year]
    campaign = keys["egm_campaign"]
    out = {}

    id_cset = csets.get("electron")
    if id_cset is not None:
        corr = id_cset[EGM_ID_CORRECTION]
        id_pt = np.clip(pt, ELECTRON_ID_PT_MIN, None)
        out["electron_reco"] = tuple(
            _electron_reco_sf(corr, campaign, val, eta, pt) for val in EGM_VALTYPES
        )
        out["electron_id"] = tuple(
            corr.evaluate(campaign, val, keys["electron_id_wp"], eta, id_pt)
            for val in EGM_VALTYPES
        )

    hlt_cset = csets.get("electron_hlt")
    if hlt_cset is not None:
        corr = hlt_cset[EGM_HLT_CORRECTION]
        hlt_pt = np.clip(pt, ELECTRON_HLT_PT_MIN, None)
        out["electron_trigger"] = tuple(
            corr.evaluate(campaign, val, keys["electron_hlt_path"], eta, hlt_pt)
            for val in EGM_VALTYPES
        )

    return out


def muon_scale_factors(csets: dict, year: str, eta: np.ndarray, pt: np.ndarray) -> dict:
    """
    ``{step: (nominal, up, down)}`` for the ID / isolation / trigger steps.

    MUO bins in *signed* probe eta (the 2026-06-18 update moved off |eta|), so
    `eta` is the muon eta as-is, only clipped to the covered range.
    """
    cset = csets.get("muon")
    if cset is None:
        return {}

    keys = LEPTON_SF_KEYS[year]
    eta = np.clip(eta, -MUON_ETA_MAX, np.nextafter(MUON_ETA_MAX, 0.0))
    id_pt = np.clip(pt, MUON_PT_MIN, None)
    hlt_pt = np.clip(pt, MUON_HLT_PT_MIN, None)

    return {
        "muon_id": tuple(cset[keys["muon_id"]].evaluate(eta, id_pt, val) for val in MUO_VALTYPES),
        "muon_iso": tuple(cset[keys["muon_iso"]].evaluate(eta, id_pt, val) for val in MUO_VALTYPES),
        "muon_trigger": tuple(
            cset[keys["muon_hlt"]].evaluate(eta, hlt_pt, val) for val in MUO_VALTYPES
        ),
    }


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------


def add_lepton_weights(
    weights: Weights,
    year: str,
    trigger_electron,
    use_trigger_electron: np.ndarray,
    trigger_muon,
    use_trigger_muon: np.ndarray,
) -> None:
    """
    Add the trigger lepton's reco / ID / isolation / trigger SFs to `weights`.

    `trigger_electron` / `trigger_muon` are the per-event leading candidates
    (``ak.firsts`` output, option type), and the two boolean masks are the
    per-event flavour choice made in ``vcbSkimmer.process`` -- the same choice
    that drives ``TriggerLepton*`` and AK4 jet cleaning, so the SFs always
    describe the lepton the event was actually kept on. The masks are mutually
    exclusive and may both be False (trigger fired but no candidate above the
    offline threshold); such events get 1.0 here, but they never reach the
    output -- weights are computed for every event read and only masked at the
    end, and the skimmer's ``trigger_lepton`` cut removes exactly the events
    this branch would have left uncorrected. A 1.0 in a written event would
    therefore be a bug, not a convention.

    Six weights are registered -- ``electron_reco``, ``electron_id``,
    ``electron_trigger``, ``muon_id``, ``muon_iso``, ``muon_trigger`` -- each
    1.0 outside its own flavour. Keeping them apart (rather than one merged
    lepton SF) is what lets the electron and muon channels carry independent
    nuisance parameters in a combined fit.

    None of these are norm-preserving: they correct an efficiency, so they are
    deliberately absent from ``hh_vars.norm_preserving_weights`` and do move
    the yield.
    """
    if year not in LEPTON_SF_SOURCES:
        if year not in _unsupported_year_warned:
            _unsupported_year_warned.add(year)
            logger.warning(
                f"No lepton scale factors wired up for year {year}; MC lepton efficiencies "
                "are left uncorrected. Add the campaign to LEPTON_SF_SOURCES / "
                "LEPTON_SF_KEYS in vcb/processors/lepton_sf.py to enable them."
            )
        return

    csets = get_lepton_correctionsets(year)

    use_electron = np.asarray(use_trigger_electron, dtype=bool)
    use_muon = np.asarray(use_trigger_muon, dtype=bool)

    # Defaults are arbitrary in-range values; they only ever feed evaluations
    # whose results the masks discard.
    scale_factors = {
        **electron_scale_factors(
            csets,
            year,
            _flat(electron_supercluster_eta(trigger_electron), use_electron, 0.0),
            _flat(trigger_electron.pt, use_electron, 40.0),
        ),
        **muon_scale_factors(
            csets,
            year,
            _flat(trigger_muon.eta, use_muon, 0.0),
            _flat(trigger_muon.pt, use_muon, 40.0),
        ),
    }

    for name, (nominal, up, down) in scale_factors.items():
        mask = use_muon if name.startswith("muon") else use_electron
        weights.add(
            name,
            np.where(mask, nominal, 1.0),
            np.where(mask, up, 1.0),
            np.where(mask, down, 1.0),
        )
