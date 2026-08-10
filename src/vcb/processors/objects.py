"""
Object definitions.

Author(s): Cristina Suarez, Raghav Kansal

Ported for Calib_ChargeTagger_JH: only the helpers used by vcbSkimmer are
kept (trig_match_sel, single_ele_lepton_pt, good_electrons, good_muons,
good_ak4jets, delta_r). AK8/tau/VBF/CA-mass helpers from the old repo are
dropped. Added here: electron_supercluster_eta / in_ecal_crack, backing the
ECAL crack veto in good_electrons (also reused by lepton_sf.py, so the veto
and the scale factors share one eta convention), ak4_jet_id, which recomputes
the Run-3 AK4 PUPPI jet ID that our NanoAOD does not ship, and
jetveto_candidate_jets, which builds the jet list JERC's jet-veto map is
evaluated on (deliberately not the analysis jets).
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
HLT_ELE32_LEPTON_PT = 35.0  # 2022 / 2023: HLT_Ele32_WPTight_Gsf
HLT_ELE30_LEPTON_PT = 32.0  # 2024:        HLT_Ele30_WPTight_Gsf
HLT_ISOMU24_LEPTON_PT = 26.0

# ECAL barrel/endcap transition, the "crack": a module gap where an electron
# shower leaks into uninstrumented material. Reconstruction is degraded there
# and EGM does not measure the ID scale factor at all -- it fills the bin with
# exactly 1.0 and *zero* uncertainty, so a crack electron would silently carry
# an unmeasured efficiency correction with no systematic attached. Vetoing is
# the standard fix and costs ~2% of the electron channel.
#
# These are the SF binning edges rather than EGM's usual 1.4442 / 1.5660
# quotation. The two differ by 0.0002 in eta -- irrelevant for acceptance, but
# using the bin edges makes it exact that no surviving electron can land in the
# unmeasured bin, which is the entire point of the veto.
ECAL_CRACK_ETA_LOW = 1.444
ECAL_CRACK_ETA_HIGH = 1.566

# ---------------------------------------------------------------------------
# Run-3 AK4 PUPPI jet ID
# ---------------------------------------------------------------------------
# Jet ID rejects fake jets: calorimeter noise, beam halo, and cosmics that the
# clustering turns into something that looks like a jet. A real jet deposits
# energy across many particles and (inside the tracker) leaves tracks; noise
# does not. So the ID is a set of cuts on the *particle-flow composition* of
# the jet -- the fraction of its energy carried by each PF candidate type, and
# how many candidates there are.
#
# Our NanoAOD has NO `Jet_jetId` branch: CMSSW_15_1_X's `jetsAK4_Puppi_cff.py`
# does not write one (verified in both the vanilla release and the CMSSW-CHARGE
# fork), so the ID *must* be recomputed here. This is by design, and JME says so
# outright -- "Starting from NanoV15, the Jet_jetId is not available anymore and
# analyzers must compute the jetId from the following branches", listing exactly
# what we use below. The twiki offers a correctionlib payload *or* a direct
# implementation in analysis code; this is the latter. Payload:
#   POG/JME/<era>/jetid.json.gz -> corrections "AK4PUPPI_Tight" /
#   "AK4PUPPI_TightLeptonVeto"
# built from https://twiki.cern.ch/twiki/bin/view/CMS/JetID13p6TeV?rev=18
#
# The thresholds below are read straight out of that payload's decision tree
# for 2024_Summer24, and tests/test_objects.py re-walks the JSON and asserts
# this function agrees with it jet by jet. They are byte-identical across
# 2024_Summer24, 2024_Winter24, 2023_Summer23(BPix) and 2022_Summer22(EE), so
# a single Run-3 definition covers every year this skimmer supports and the
# function takes no `year` argument.
#
# Why not just call correctionlib on the JSON at runtime? Because it does not
# work: the payload bins on `chMultiplicity` / `neMultiplicity` / `multiplicity`,
# which are declared as *int* inputs, and correctionlib 2.5.0 (our pinned
# version) raises "std::get: wrong index for variant" on an int-typed Binning
# node. Only the two eta slices with no multiplicity cut evaluate at all.
# Explicit cuts also vectorise over the jagged array instead of forcing a
# flatten/evaluate/unflatten round trip per event.
#
# One subtlety on the *raw* energy: pat::Jet's fraction accessors divide by
# `jecFactor(0) * energy()`, i.e. the UNCORRECTED jet energy (see
# DataFormats/PatCandidates/interface/Jet.h). The fractions are therefore
# invariant under JEC, and it makes no difference whether the ID is applied
# before or after get_jec_jets(). We apply it after, alongside the other
# selections.
#
# Eta boundaries of the four regions. They track detector transitions:
#   |eta| < 2.6      tracker coverage, so charged-hadron and track-multiplicity
#                    cuts are meaningful and the ID is at its most powerful
#   2.6 - 2.7        tracking is gone but the cut set is still ECAL/HCAL-based
#   2.7 - 3.0        HE/HF transition: no tracks at all, so only neHEF survives
#   > 3.0            HF, a Cherenkov calorimeter with no tracking and coarse
#                    granularity; a different pair of cuts applies
JET_ID_ETA_TRACKER = 2.6
JET_ID_ETA_TRANSITION = 2.7
JET_ID_ETA_HF = 3.0

# EM-fraction ceiling on the jets the jet-veto map is evaluated on, from JERC's
# "minimal selection" (see jetveto_candidate_jets). Numerically the same as
# `corrections.TYPE1_MET_MAX_EMEF`, and for the same reason -- JERC motivates
# the cut from the Type-1 MET correction -- but kept separate so a change to one
# recipe cannot silently move the other.
JETVETO_MAX_EMEF = 0.9

# Jet charge Qk, from the CMSSW_15_CHARGE fork's JetChargeTableProducer. The
# producer's own sentinels, which are NOT the skimmer's PAD_VAL: a jet with no
# constituent above the 0.95 GeV candidate cut is -999, zero jet pT is -998,
# and a numerically zero numerator ("neutral jet") is -997. The last is common
# -- about 21% of jets on the 2024 fixture -- so anything averaging Qk must mask
# on `> QK_SENTINEL_MAX` rather than assume every entry is a charge.
QK_FIELDS = ("QkCharge05", "QkCharge10")
QK_SENTINEL_MAX = -900.0


def attach_jet_charge(jets: JetArray, events) -> JetArray:
    """
    Copy the `JetQk` charge columns onto the matching `Jet` records.

    The fork writes jet charge to its own flat table rather than extending
    `Jet`, and it builds that table from `slimmedJetsPuppi` -- the raw MiniAOD
    collection -- while the `Jet` table comes from `finalJetsPuppi`, which is
    `slimmedJetsPuppi` filtered to `pt > 15`. So `nJetQk >= nJet`, with equality
    in only ~16% of events, and there is no pT/eta/phi in `JetQk` to match on.

    What makes the positional match `JetQk[i] <-> Jet[i]` correct is that the
    whole chain preserves order: `updatedPatJets` recomputes JECs without
    sorting and `PATJetRefSelector` only filters, so `Jet` is `JetQk` with a
    suffix of sub-threshold jets removed. Checked against the data as well --
    on events where `nJet == nJetQk` the match is exact by construction, and
    the sign agreement between Qk05 and `Jet_PflavCharge` there (0.6081 +-
    0.0018) is 0.4 sigma from the same quantity on events where the prefix is
    assumed (0.6074 +- 0.0008). A broken prefix would pull the second toward
    0.5, and does for deliberately shifted controls (~0.47).

    That argument is an inference about the producer, not something the file
    asserts, so the length guard below is a hard error rather than a warning:
    if a future production ever makes `JetQk` shorter than `Jet`, the prefix
    is meaningless and silently attaching the wrong charge to a jet would
    corrupt exactly the observable this analysis calibrates.

    The right upstream fix is to point the producer's `src` at
    `finalJetsPuppi`, which would make the alignment exact by construction and
    shrink the branch; until then this is the only match available.
    """
    if "JetQk" not in events.fields:
        raise KeyError(
            "No `JetQk` collection in this NanoAOD -- the jet charge branches "
            "require the CMSSW_15_CHARGE fork. Available: "
            f"{sorted(f for f in events.fields if 'Jet' in f)}"
        )

    n_jets, n_qk = ak.num(jets), ak.num(events.JetQk)
    if ak.any(n_qk < n_jets):
        n_bad = int(ak.sum(n_qk < n_jets))
        raise ValueError(
            f"`JetQk` is shorter than `Jet` in {n_bad} event(s); the positional "
            "prefix match this relies on does not hold. See attach_jet_charge()."
        )

    for field in QK_FIELDS:
        # Keep the first n_jets entries of each event -- the extra JetQk rows
        # are the sub-threshold jets that never made it into the Jet table.
        column = events.JetQk[field]
        jets = ak.with_field(jets, column[ak.local_index(column) < n_jets], field)
    return jets


def ak4_jet_id(jets: JetArray, wp: str = "tight") -> ak.Array:
    """
    Run-3 AK4 PUPPI jet ID, as a jagged boolean with the shape of ``jets``.

    ``wp`` is either ``"tight"`` (the default, and what this analysis uses) or
    ``"tightlepveto"``, which adds ``chEmEF < 0.8`` and ``muEF < 0.8`` in the
    two eta regions where those fractions are measurable.

    Note that JME's *default* is TightLepVeto, so "tight" here is a deliberate
    exercise of the exception the twiki grants: "For analyses that perform any
    special cleaning or selections between jets and leptons, the jet ID can also
    be applied without the vetoing on leptons to avoid possible biases."
    good_ak4jets() does exactly that special cleaning (DeltaR > 0.4 against the
    trigger lepton), so the lepton-fake jets TightLepVeto targets are already
    gone geometrically. What the extra cuts would still remove is genuine
    semileptonic heavy-flavour jets (b -> mu + X inside the cone) -- precisely
    the jets whose soft lepton carries the charge information this analysis is
    calibrating a tagger on. That is the "possible bias" in our case.

    That exception is about which jets the analysis *keeps*. The jet-veto map
    decides which events to *drop*, and there JERC names TightLepVeto outright,
    so jetveto_candidate_jets() calls this with wp="tightlepveto".
    """
    if wp not in ("tight", "tightlepveto"):
        raise ValueError(f"unknown AK4 jet ID working point {wp!r}; use 'tight' or 'tightlepveto'")

    abs_eta = np.abs(jets.eta)

    # NanoAOD stores both multiplicities as UChar_t. Widen before summing so
    # the total cannot wrap around 255 (it peaks around 70 in practice, but a
    # silent uint8 overflow would turn a busy jet into a failing one).
    ch_mult = ak.values_astype(jets.chMultiplicity, np.int32)
    ne_mult = ak.values_astype(jets.neMultiplicity, np.int32)
    # The payload's `multiplicity` input is defined as chMultiplicity +
    # neMultiplicity, NOT `nConstituents`. They are not the same branch: on
    # tests/data/test-input.root the sum falls below nConstituents for ~5% of
    # jets (by up to 8), because the multiplicities are PUPPI-weighted counts
    # while nConstituents is a plain numberOfDaughters().
    mult = ch_mult + ne_mult

    # Bins are half-open [lo, hi) exactly as in the JSON. Checked against
    # JetID13p6TeV rev 24 (2026-06-13), NanoV15 section: the twiki writes
    # `chHEF > 0.01` where the payload has `>= 0.01`, and closes its eta bins on
    # the upper edge (`abs(eta) <= 2.6`) where the payload leaves them open.
    # Both differ only on an exact float equality; we follow the payload, since
    # that is what tests/test_objects.py validates against.
    tracker = (
        (jets.chHEF >= 0.01)  # some charged-hadron energy: a real jet has tracks
        & (jets.neHEF < 0.99)  # not pure neutral-hadron energy -> HCAL noise
        & (jets.neEmEF < 0.90)  # not pure ECAL energy -> photon/ECAL noise
        & (ch_mult >= 1)  # at least one charged PF candidate
        & (mult >= 2)  # at least two PF candidates total
    )
    transition = (jets.neHEF < 0.90) & (jets.neEmEF < 0.99)
    hetohf = jets.neHEF < 0.99
    forward = (jets.neEmEF < 0.40) & (ne_mult >= 2)

    if wp == "tightlepveto":
        # Only where the tracker/ECAL make chEmEF and muEF meaningful; the JSON
        # leaves the two |eta| > 2.7 regions untouched.
        lepton_veto = (jets.chEmEF < 0.80) & (jets.muEF < 0.80)
        tracker = tracker & lepton_veto
        transition = transition & lepton_veto

    # Jets past the payload's last eta edge (5.2) fall in its overflow, which
    # is declared "clamp" -- i.e. they take the forward branch, same as here.
    return ak.where(
        abs_eta < JET_ID_ETA_TRACKER,
        tracker,
        ak.where(
            abs_eta < JET_ID_ETA_TRANSITION,
            transition,
            ak.where(abs_eta < JET_ID_ETA_HF, hetohf, forward),
        ),
    )


def jetveto_candidate_jets(jets: JetArray) -> JetArray:
    """
    The jets the Run-3 jet-veto map is evaluated on, per JERC's "minimal
    selection" (<https://cms-jerc.web.cern.ch/Recommendations/>, Jet Veto Maps
    -> Run 3): ``pT > 15 GeV``, the *TightLepVeto* jet ID, and
    ``chEmEF + neEmEF < 0.9``.

    This is deliberately **not** the analysis jet collection, and the three
    differences all follow from what the veto is for. JERC's stated purpose is
    to reject events where a jet in a dead/noisy region injects spurious MET,
    so the candidate list must be the jets that can put energy into MET:

    - **No lepton cleaning.** ``good_ak4jets`` drops jets within ΔR < 0.4 of the
      trigger lepton, but this analysis rebuilds MET as PUPPI Type-1 over
      *every* jet in the event (``JECs.type1_met_2024``), so a jet removed from
      the analysis collection still contributes its mismeasured energy to MET.
      The veto has to see it.
    - **TightLepVeto, not Tight.** ``ak4_jet_id``'s docstring explains why the
      *analysis* jets use Tight: TightLepVeto would eat genuine semileptonic
      heavy-flavour jets, whose soft lepton carries the charge information this
      analysis calibrates. That argument is about which jets we *keep*; here we
      are only deciding which jets may *throw the event away*, and JERC names
      TightLepVeto. The jet ID is not a detail -- dropping it entirely costs
      ~3 percentage points of acceptance, because fake jets are exactly what the
      vetoed hot/cold regions produce.
    - **EM-fraction cut.** JERC motivates it from the Type-1 MET correction, and
      it is the same ``TYPE1_MET_MAX_EMEF = 0.9`` this repo already applies when
      rebuilding MET: a jet that is mostly EM energy is not propagated into MET,
      so it cannot inject the spurious MET the veto exists to prevent.

    Net effect versus feeding the analysis jets in (measured on
    ``tests/data/test-input.root``, after every other cut): 15.85 % event loss
    instead of 15.77 %. The two nearly coincide because ΔR > 0.4 cleaning plus
    Tight ID removes almost the same jets as TightLepVeto -- but that agreement
    is a coincidence of this lepton selection, not something the code enforces,
    which is why the recipe is now applied literally. See ``JERC.md``.
    """
    minimal = (
        (jets.pt > 15.0)
        & ak4_jet_id(jets, wp="tightlepveto")
        & ((jets.chEmEF + jets.neEmEF) < JETVETO_MAX_EMEF)
    )
    return jets[minimal]


def single_ele_lepton_pt(year: str) -> float:
    """Offline pT cut for the trigger-matched electron, matching that year's single-e HLT."""
    return HLT_ELE30_LEPTON_PT if year in years_2024 else HLT_ELE32_LEPTON_PT


def electron_supercluster_eta(electrons: ElectronArray) -> ak.Array:
    """
    Supercluster eta -- where the electron's energy actually landed in ECAL,
    as opposed to `eta`, which is the track's direction at the vertex.

    The two differ by up to ~0.03 for a bremsstrahlung-heavy electron. That is
    enough to move it across the crack boundary, and it is the coordinate every
    EGM binning (and the crack itself) is defined in, so it is what both the
    veto and the scale factors must use. NanoAODv15 ships `superclusterEta`
    directly; older versions only carry the offset from the track.
    """
    if "superclusterEta" in ak.fields(electrons):
        return electrons.superclusterEta
    return electrons.eta + electrons.deltaEtaSC


def in_ecal_crack(supercluster_eta: ak.Array) -> ak.Array:
    """True for electrons inside the ECAL barrel/endcap transition."""
    abs_eta = abs(supercluster_eta)
    return (abs_eta >= ECAL_CRACK_ETA_LOW) & (abs_eta < ECAL_CRACK_ETA_HIGH)


def trig_match_sel(events, leptons, trig_leptons, year, trigger, filterbit, ptcut, trig_dR=0.2):
    """
    Returns selection for leptons which are trigger matched to the specified trigger.
    """
    trigger = HLTs.hlts_by_type(year, trigger, hlt_prefix=False)[0]  # picking first trigger in list
    trig_fired = events.HLT[trigger]
    # print(f"{trigger} rate: {ak.mean(trig_fired)}")

    filterbit = 2**filterbit

    pass_trig = (trig_leptons.filterBits & filterbit) == filterbit
    trig_l = trig_leptons[pass_trig]
    trig_l_matched = ak.any(leptons.metric_table(trig_l) < trig_dR, axis=2)
    trig_l_sel = trig_fired & trig_l_matched & (leptons.pt >= ptcut)
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
    jet_id: str | None = "tight",
):
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

    # Baseline kinematics + lepton-jet overlap removal using deltaR.
    # metric_table builds pairwise deltaR between each jet and each lepton.
    # ak.all(..., axis=2) requires every lepton to be farther than dr_leptons.
    jet_sel = (
        (jets.pt > 15)
        & (np.abs(jets.eta) < 4.7)
        & ak.all(jets.metric_table(electrons) > dr_leptons, axis=2)
        & ak.all(jets.metric_table(muons) > dr_leptons, axis=2)
    )

    # Jet ID (see ak4_jet_id). `None` disables it, which is only meant for
    # studies of what the ID removes -- the analysis selection always applies
    # it, and JME treats it as mandatory for every Run-3 analysis.
    if jet_id is not None:
        jet_sel = jet_sel & ak4_jet_id(jets, wp=jet_id)

    return jets[jet_sel]


"""
Trigger quality bits in NanoAOD v12
0 => CaloIdL_TrackIdL_IsoVL,
1 => 1e (WPTight),
2 => 1e (WPLoose),
3 => OverlapFilter PFTau,
4 => 2e,
5 => 1e-1mu,
6 => 1e-1tau,
7 => 3e,
8 => 2e-1mu,
9 => 1e-2mu,
10 => 1e (32_L1DoubleEG_AND_L1SingleEGOr),
11 => 1e (CaloIdVT_GsfTrkIdT),
12 => 1e (PFJet),
13 => 1e (Photon175_OR_Photon200) for Electron;
"""


def good_electrons(events, leptons: ElectronArray, year: str):
    trigobj = events.TrigObj

    # baseline kinematic selection
    # https://twiki.cern.ch/twiki/bin/view/CMS/MultivariateElectronIdentificationRun3
    # The crack veto is in supercluster eta (see in_ecal_crack); the outer
    # |eta| < 2.5 acceptance bound stays on track eta, unchanged.
    lsel = (
        leptons.mvaIso_WP90
        & (leptons.pt > 20)
        & (abs(leptons.eta) < 2.5)
        & ~in_ecal_crack(electron_supercluster_eta(leptons))
        & (abs(leptons.dz) < 0.2)
        & (abs(leptons.dxy) < 0.045)
    )
    leptons = leptons[lsel]

    # Trigger: (filterbit, ptcut for matched lepton)
    # filterbit 1 = "1e (WPTight)" is the generic single-electron WPTight bit, so it is
    # valid for both Ele32 (2022/2023) and Ele30 (2024); only the pT cut is year-dependent.
    triggers = {"EGamma": (1, single_ele_lepton_pt(year))}
    trig_leptons = trigobj[trigobj.id == PDGID.e]

    TrigMatchDict = {
        f"ElectronTrigMatch{trigger}": trig_match_sel(
            events, leptons, trig_leptons, year, trigger, filterbit, ptcut
        )
        for trigger, (filterbit, ptcut) in triggers.items()
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

    # Trigger: (filterbit, ptcut for matched lepton)
    triggers = {"Muon": (3, HLT_ISOMU24_LEPTON_PT)}
    trig_leptons = trigobj[trigobj.id == PDGID.mu]

    TrigMatchDict = {
        f"MuonTrigMatch{trigger}": trig_match_sel(
            events, leptons, trig_leptons, year, trigger, filterbit, ptcut
        )
        for trigger, (filterbit, ptcut) in triggers.items()
    }

    return leptons, TrigMatchDict


# adopted from https://github.com/scikit-hep/coffea/blob/a315da1fa307f1ec0d21c29e908e5b733603d7c0/src/coffea/nanoevents/methods/vector.py#L106
def delta_r(eta1, phi1, eta2, phi2):
    deta = eta1 - eta2
    dphi = (phi1 - phi2 + np.pi) % (2 * np.pi) - np.pi
    return np.hypot(deta, dphi)
