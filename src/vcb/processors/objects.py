"""
Object definitions.

Author(s): Cristina Suarez, Raghav Kansal

Ported for Calib_ChargeTagger_JH: only the helpers used by vcbSkimmer are
kept (trig_match_sel, single_ele_lepton_pt, good_electrons, good_muons,
good_ak4jets, delta_r). AK8/tau/VBF/CA-mass helpers from the old repo are
dropped.
"""

from __future__ import annotations

import awkward as ak
import numpy as np
from coffea.nanoevents.methods.nanoaod import (
    ElectronArray,
    JetArray,
    MuonArray,
)

from boostedhh.processors.utils import PDGID
from vcb.HLTs import HLTs, years_2024

# Offline pT cuts for the trigger-matched lepton, placed above the HLT turn-on.
#
# The skimmer no longer applies these: it only requires that one of the single-lepton
# paths fired, and leaves the activation-threshold cut to the downstream selection
# script. They stay here as the single source of truth for that script.
HLT_ELE32_LEPTON_PT = 35.0  # 2022 / 2023: HLT_Ele32_WPTight_Gsf
HLT_ELE30_LEPTON_PT = 32.0  # 2024:        HLT_Ele30_WPTight_Gsf
HLT_ISOMU24_LEPTON_PT = 26.0


def single_ele_lepton_pt(year: str) -> float:
    """Offline pT cut for the trigger-matched electron, matching that year's single-e HLT."""
    return HLT_ELE30_LEPTON_PT if year in years_2024 else HLT_ELE32_LEPTON_PT


def trig_match_sel(
    events, leptons, trig_leptons, year, trigger, filterbit, ptcut=None, trig_dR=0.2
):
    """
    Returns selection for leptons which are trigger matched to the specified trigger.

    ``ptcut`` is optional and defaults to no offline pT requirement, so the saved flag
    is the bare fact "this path fired and this lepton is matched to one of its trigger
    objects". Folding a threshold in here would make it impossible for a downstream
    script to *loosen* it later, since the sub-threshold matches would already be gone.
    Lepton pT is saved alongside the flag, so any threshold can be applied afterwards.
    """
    trigger = HLTs.hlts_by_type(year, trigger, hlt_prefix=False)[0]  # picking first trigger in list
    trig_fired = events.HLT[trigger]
    # print(f"{trigger} rate: {ak.mean(trig_fired)}")

    filterbit = 2**filterbit

    pass_trig = (trig_leptons.filterBits & filterbit) == filterbit
    trig_l = trig_leptons[pass_trig]
    trig_l_matched = ak.any(leptons.metric_table(trig_l) < trig_dR, axis=2)
    trig_l_sel = trig_fired & trig_l_matched
    if ptcut is not None:
        trig_l_sel = trig_l_sel & (leptons.pt >= ptcut)
    return trig_l_sel


def good_ak4jets(
    jets: JetArray,
    nano_version: str,  # noqa: ARG001
    events,
    muon_pt: float | None = None,
    electron_pt: float | None = None,
    dr_leptons: float = 0.4,
    cleaning_electrons=None,
    cleaning_muons=None,
    apply_lepton_cleaning: bool = True,
):
    # Baseline kinematics. Overlap removal, if requested, is added below.
    jet_sel = (jets.pt > 15) & (np.abs(jets.eta) < 4.7)

    if not apply_lepton_cleaning:
        # Overlap removal is deferred to the downstream selection script, which can
        # redo it from the saved jet and lepton eta/phi. Dropping jets here would bake
        # a lepton choice into the output that is supposed to stay deferred, and a
        # removed jet cannot be recovered.
        return jets[jet_sel]

    # If explicit lepton collections are provided, use them for overlap removal.
    # Otherwise fall back to the default: all NanoAOD leptons above pT thresholds.
    if cleaning_electrons is None:
        if electron_pt is None:
            raise ValueError("electron_pt is required when cleaning_electrons is not provided")
        electrons = events.Electron
        electrons = electrons[electrons.pt > electron_pt]
    else:
        electrons = cleaning_electrons

    if cleaning_muons is None:
        if muon_pt is None:
            raise ValueError("muon_pt is required when cleaning_muons is not provided")
        muons = events.Muon
        muons = muons[muons.pt > muon_pt]
    else:
        muons = cleaning_muons

    # Lepton-jet overlap removal using deltaR.
    # metric_table builds pairwise deltaR between each jet and each lepton.
    # ak.all(..., axis=2) requires every lepton to be farther than dr_leptons.
    jet_sel = (
        jet_sel
        & ak.all(jets.metric_table(electrons) > dr_leptons, axis=2)
        & ak.all(jets.metric_table(muons) > dr_leptons, axis=2)
    )
    return jets[jet_sel]


"""
Electron TrigObj_filterBits, read off the 2024 NanoAOD in tests/data/test-input.root.
(The older v12 listing this comment used to carry was off by one from bit 5 onwards.)

0 => CaloIdL_TrackIdL_IsoVL,
1 => 1e (WPTight, with possible contribution from Xtriggers besides singleElectron),
2 => 1e (WPLoose),
3 => OverlapFilter PFTau,
4 => 2e (Leg 1),
5 => 2e (Leg 2),
6 => 1e-1mu,
7 => 1e-1tau,
8 => 3e,
9 => 2e-1mu,
10 => 1e-2mu,
11 => 1e (32_L1DoubleEG_AND_L1SingleEGOr),
12 => 1e (CaloIdVT_GsfTrkIdT),
13 => 1e (PFJet),
14 => 1e (Photon175_OR_Photon200),
15 => 2e (CaloIdL_MW seeded),
16 => 2e (CaloIdL_MW unseeded),
17 => 1e-1tau PNet,
18 => 1e (HLT30WPTightGsfTrackIso),
19 => WPTightGsfTrackIso for VBF, for Electron;

Bit 18 is Ele30-specific where bit 1 is generic. Measured on the 2024 fixture, the two
agree to 1 event in 30,362 once the path-fired and dR-match requirements are also
applied, so bit 1 is kept for cross-year validity.
"""


def good_electrons(events, leptons: ElectronArray, year: str):
    trigobj = events.TrigObj

    # baseline kinematic selection
    # https://twiki.cern.ch/twiki/bin/view/CMS/MultivariateElectronIdentificationRun3
    lsel = (
        leptons.mvaIso_WP90
        & (leptons.pt > 20)
        & (abs(leptons.eta) < 2.5)
        & (abs(leptons.dz) < 0.2)
        & (abs(leptons.dxy) < 0.045)
    )
    leptons = leptons[lsel]

    # Trigger matching: {trigger type: TrigObj filter bit}.
    # filterbit 1 = "1e (WPTight)" is the generic single-electron WPTight bit, so it is
    # valid for both Ele32 (2022/2023) and Ele30 (2024).
    # No offline pT threshold is folded in -- see trig_match_sel.
    triggers = {"EGamma": 1}
    trig_leptons = trigobj[trigobj.id == PDGID.e]

    TrigMatchDict = {
        f"ElectronTrigMatch{trigger}": trig_match_sel(
            events, leptons, trig_leptons, year, trigger, filterbit
        )
        for trigger, filterbit in triggers.items()
    }

    return leptons, TrigMatchDict


"""
Trigger quality bits in NanoAOD v12
0 => TrkIsoVVL,
1 => Iso,
2 => OverlapFilter PFTau,
3 => 1mu,
4 => 2mu,
5 => 1mu-1e,
6 => 1mu-1tau,
7 => 3mu,
8 => 2mu-1e,
9 => 1mu-2e,
10 => 1mu (Mu50),
11 => 1mu (Mu100),
12 => 1mu-1photon for Muon;
"""


def good_muons(events, leptons: MuonArray, year: str):
    trigobj = events.TrigObj

    lsel = (
        leptons.tightId
        & (leptons.pfRelIso04_all < 0.15)
        & (leptons.pt > 20)
        & (abs(leptons.eta) < 2.4)
        & (abs(leptons.dz) < 0.2)
        & (abs(leptons.dxy) < 0.045)
    )
    leptons = leptons[lsel]

    # Trigger matching: {trigger type: TrigObj filter bit}.
    # filterbit 3 = "1mu". Requiring bit 1 ("Iso") in addition gives an identical result
    # on the 2024 fixture (41,175 events either way), so the generic bit is kept.
    # No offline pT threshold is folded in -- see trig_match_sel.
    triggers = {"Muon": 3}
    trig_leptons = trigobj[trigobj.id == PDGID.mu]

    TrigMatchDict = {
        f"MuonTrigMatch{trigger}": trig_match_sel(
            events, leptons, trig_leptons, year, trigger, filterbit
        )
        for trigger, filterbit in triggers.items()
    }

    return leptons, TrigMatchDict


# adopted from https://github.com/scikit-hep/coffea/blob/a315da1fa307f1ec0d21c29e908e5b733603d7c0/src/coffea/nanoevents/methods/vector.py#L106
def delta_r(eta1, phi1, eta2, phi2):
    deta = eta1 - eta2
    dphi = (phi1 - phi2 + np.pi) % (2 * np.pi) - np.pi
    return np.hypot(deta, dphi)
