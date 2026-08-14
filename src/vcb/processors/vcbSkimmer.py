"""
Skimmer for Vcb analysis, based on ttSkimmer.py.
Vcb analysis:
    p p > t t~, (t > b W, W > c b~), (t~ > b~ W~, W~ > l- nu~)

Event acceptance in this processor:
- Keep events that pass at least one single-lepton trigger path:
  `HLT_IsoMu24 OR <year's single-electron path>`, resolved from bbtautau/HLTs.py
  (Ele32_WPTight_Gsf for 2022/2023, Ele30_WPTight_Gsf for 2024). A missing
  single-lepton HLT branch raises rather than silently dropping that channel.
- Require the JME Run-3 recommended MET (event-quality) filters and the Run-3
  AK4 jet-veto map event selection. A missing MET filter branch raises rather
  than being skipped, for the same reason as the HLT branches above.
- Require a resolved *trigger lepton*, not merely a good-lepton count: the
  event must contain the electron or muon that the fired single-lepton path is
  matched to, above that path's offline plateau threshold. This is the object
  the `TriggerLepton*` branches, the lepton scale factors and the AK4 jet
  cleaning all key off, so requiring it is what keeps those three consistent
  with the events actually written (`trigger_lepton` in the cutflow; the loose
  `nMuons + nElectrons >= 1` stage is retained above it for bookkeeping only).
- Good electrons and muons are saved with their trigger-match flags. A single
  trigger lepton is chosen for `TriggerLepton*` output and AK4 jet cleaning.
- Correct the electron energy scale (data) / resolution (MC) with the EGM
  `electronSS_EtDependent` payload before any electron selection, since the
  correction is what decides which electrons clear the pT thresholds
  (`electron_ss.py`). The uncorrected pT is kept as `ElectronPtRaw`, and MC
  additionally carries the four scale/smearing shifted pTs.

Jet handling in this processor:
- Build AK4 jets from NanoAOD `events.Jet` and apply year-dependent JECs.
- Keep AK4 jets with corrected `pt > 15 GeV` and `|eta| < 4.7`; a jet at
  exactly 15 GeV is not selected.
- Require the Run-3 AK4 PUPPI *Tight* jet ID, recomputed from the PF energy
  fractions and multiplicities by `objects.ak4_jet_id` because our NanoAOD
  ships no `Jet_jetId` branch. TightLepVeto is deliberately not used *for the
  analysis jets*: the DeltaR cleaning below already removes lepton-fake jets,
  while the extra `muEF`/`chEmEF` cuts would eat real semileptonic
  heavy-flavour jets. The jet-veto map is a separate question and does use
  TightLepVeto, per JERC (`objects.jetveto_candidate_jets`).
- Remove jets within `DeltaR < 0.4` of the selected trigger lepton used for
  the single-lepton path, so the overlap veto is applied only against the
  prompt electron / muon rather than all reconstructed leptons.
- Rebuild MET from the corrected AK4 jets so it stays consistent with them:
  2022/2023 via the coffea MET factory, 2024 via an explicit Type-1 recompute
  from raw MET (`JECs.type1_met_2024`). Data keeps the input MET, since 2024
  data jets are not recorrected either.
- Do not apply any b-tag working point at skimmer level and do not use AK8 jets
  or JMSR in this processor.
- Sort the selected jets into descending *corrected* pT before saving them.
  NanoAOD's own ordering does not survive the JEC re-derivation and the
  (partly stochastic) JER smear, so without this the saved slots are neither
  pT-ordered nor even the ten hardest jets -- the 10-slot truncation keeps the
  first ten in the permuted order. See the comment at the `ak.argsort` call for
  why it has to sit exactly where it does.
- Save up to 10 selected AK4 jets to the parquet output, including kinematics,
  `rawFactor`, flavor labels, UnifiedParT / ParticleNet / RobustParT /
  charge-tagger observables, the Qk jet charges, and matched gen-jet `pt` for
  MC. UParT and PNet are both kept: only UParT is calibrated for 2024, but the
  two are independent networks and either may end up feeding the ML step.
- Each saved jet also carries `ak4JetNanoIdx`, its index in the input NanoAOD
  `Jet` collection, captured before any reordering or filtering. It is the only
  link from an output slot back to the input file once the sort has permuted
  them, it indexes `JetQk` as well, and it identifies which jets the 10-slot
  truncation dropped.
- Save the generator-level AK4 jets whole for MC (`GenJet*`, 25 slots), not just
  the matched `MatchedGenJetPt` of the jets that survived selection, so the reco
  collection can be sanity-checked against the truth-level one it came from.
  Each reco jet points into that collection with `ak4JetGenJetIdx`, and
  `nGenJets` records how many gen jets the event actually had.
- Save the event pile-up energy density as `Rho`. This is the input JER needs
  and the per-jet columns cannot supply, so writing it is what makes the JES/JER
  variations derivable from the skim without a reprocessing pass.
- The Qk charges come from the fork's separate `JetQk` collection, which is
  indexed over the *unfiltered* jets; `objects.attach_jet_charge` handles the
  match and guards the assumption it rests on.
- Derive event-level jet quantities such as `ht` and `nJets`, and apply the
  AK4 jet-veto map event selection. The map is evaluated on JERC's "minimal
  selection" taken off the *uncleaned* corrected collection (pT > 15,
  TightLepVeto ID, `chEmEF + neEmEF < 0.9`), not on the analysis jets, because
  a lepton-overlapping jet still contributes to the Type-1 MET this repo
  rebuilds -- and spurious MET is what the veto exists to prevent.

MC weights in this processor:
- `genWeight`, pile-up, and ISR/FSR parton-shower weights, plus the
  cross-section x luminosity normalization (see `docs/normalization.md`).
- Lepton reco / ID / isolation / trigger scale factors for the event's trigger
  lepton, as six separately named weights (`lepton_sf.py`). Data is unweighted.

Author: Jiashu Huang (Brown U)

This is a Coffea processor that reads NanoAOD events, builds physics objects,
applies selections, computes weights, and writes a skimmed Parquet table.
"""

# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

from __future__ import annotations  # Allow forward references in type hints.

import logging  # Standard library logging for structured runtime messages.
import pathlib  # Path utilities used to build package-relative paths.
import time  # Simple wall-clock timing for debug prints.
from collections import OrderedDict  # Stable ordering for cutflow bookkeeping.

import awkward as ak  # Jagged-array operations for NanoAOD event data.
import numpy as np
from coffea import processor  # Coffea processor accumulator utilities.
from coffea.analysis_tools import PackedSelection, Weights  # Selection masks + weights.

# The following imports are from the boostedhh submodule.
from boostedhh import hh_vars  # Definitions for weight categories/normalization.
from boostedhh.processors import SkimmerABC, utils  # Base skimmer + common helpers.
from boostedhh.processors.corrections import (
    JECs,  # Jet energy corrections factory/loader.
    add_pileup_weight,  # Pileup reweighting for MC.
    add_ps_weight,  # Parton shower weights for MC variations.
    get_jetveto_event,  # Jet veto map selection per event.
    get_pdf_weights,  # PDF variation weights.
    get_scale_weights,  # Renormalization/factorization scale variations.
)
from boostedhh.processors.utils import (
    P4,  # Canonical 4-vector field mapping used in skim_vars.
    PAD_VAL,  # Padding sentinel value for missing entries.
    add_selection,  # Helper to register selections + update cutflow.
    pad_val,  # Helper to pad jagged arrays to fixed length.
)
from vcb.HLTs import HLTs  # Trigger lists grouped by year/region.

from . import GenSelection, objects  # Local gen selection and object definitions.
from .electron_ss import apply_electron_scale_smearing  # 2024 EGM electron energy scale/smearing.
from .lepton_sf import add_lepton_weights  # 2024 lepton reco/ID/iso/trigger SFs.
from .top_pt import top_pt_weights  # ttbar top-pT reweighting SFs (standalone columns).

# -----------------------------------------------------------------------------
# End Imports
# -----------------------------------------------------------------------------

# mapping samples to the appropriate function for doing gen-level selections
gen_selection_dict = {
    "TTtoLNuCB": GenSelection.gen_selection_Vcb,  # 2024 Summer24 private production
    "TT1L2Q": GenSelection.gen_selection_Vcb,  # legacy 2022 private sample naming
    "TTtoLNu2Q": GenSelection.gen_selection_Vcb,
}

# Event-quality ("MET") filters: the JME/JetMET POG **Run-3** recommended set,
# which covers every year this repo can process (2022, 2022EE, 2023, 2023BPix,
# 2024). Source of truth, CERN SSO:
#   https://twiki.cern.ch/twiki/bin/viewauth/CMS/MissingETOptionalFiltersRun2#Run_3_recommendations
#
# Deliberately absent (removed 2026-08-09) and not to be re-added for Run 3:
# `HBHENoiseFilter` and `HBHENoiseIsoFilter`. They target HPD / ion-feedback
# noise topologies of the pre-Phase-1 HB/HE readout, are not part of the Run-3
# recommendation, and are not validated for Run-3 conditions. CMSSW still *runs*
# those paths (`PhysicsTools/PatAlgos/.../metFilterPaths_cff.py` has no Run-3
# removal), so the branches do exist in our private Summer24 NanoAOD — presence
# in the file is not a POG endorsement. On tests/data/test-input.root both are
# true for all 208,780 events, so dropping them is a numerical no-op there.
#
# If this repo is ever pointed at 2022/2023: the stored `Flag_ecalBadCalibFilter`
# was known to over-veto in those eras and JME published a recomputation recipe.
# Check the TWiki before trusting the branch as-is for those years; it is fine
# as stored for 2024.
#
# Kept here rather than in boostedhh (`processors/utils.py::met_filters`, which
# is unused) so the vendored dependency stays untouched.
RUN3_MET_FILTERS = [
    "goodVertices",
    "globalSuperTightHalo2016Filter",
    "EcalDeadCellTriggerPrimitiveFilter",
    "BadPFMuonFilter",
    "BadPFMuonDzFilter",
    "eeBadScFilter",
    "ecalBadCalibFilter",
    "hfNoisyHitsFilter",
]

# MET collection written to the skim, and the raw collection the 2024 Type-1
# rebuild starts from. These must be the same flavour as the jets: raw PF MET
# sums unweighted PF candidates while a PUPPI jet is built from pileup-weighted
# ones, so crossing them subtracts energy that was never in the total.
#
# PUPPI is not a preference here, it is what `events.Jet` is. Measured on
# tests/data/test-input.root: rebuilding the Type-1 shift from events.Jet with
# NanoAOD's own jet pT reproduces NanoAOD's PuppiMET shift exactly (corr 1.000,
# rms 0.17 GeV) but its PFMET shift only loosely (corr 0.74). PFMET is built
# from a different jet collection, so propagating our PUPPI jets onto it is not
# a valid correction. This changed from PFMET on 2026-07-29.
MET_COLLECTION = "PuppiMET"
RAW_MET_COLLECTION = "RawPuppiMET"

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

package_path = str(pathlib.Path(__file__).parent.parent.resolve())


def met_filter_mask(events, year: str) -> np.ndarray:
    """Per-event AND of the Run-3 recommended event-quality flags.

    Every flag in `RUN3_MET_FILTERS` is required to be present in the input.
    A missing branch raises rather than being skipped: silently dropping a
    filter loosens the selection in a way nothing downstream can see — the
    cutflow still reports a `met_filters` stage that passed.
    """
    missing = [mf for mf in RUN3_MET_FILTERS if mf not in events.Flag.fields]
    if missing:
        raise KeyError(
            f"MET filter branches {missing} required for year {year} are not present "
            f"in the input NanoAOD (found {sorted(events.Flag.fields)}). Skipping them "
            f"would silently loosen the event selection. Check the NanoAOD version of "
            f"this sample against RUN3_MET_FILTERS in vcb/processors/vcbSkimmer.py."
        )

    mask = np.ones(len(events), dtype="bool")
    for mf in RUN3_MET_FILTERS:
        mask = mask & events.Flag[mf].to_numpy().astype(bool)
    return mask


# -----------------------------------------------------------------------------
# Class definition:
# -----------------------------------------------------------------------------


class vcbSkimmer(SkimmerABC):
    """
    Skims nanoaod files, saving selected branches and events passing preselection cuts
    (and triggers for data).
    """

    # skim_vars maps NanoAOD input fields to the specific output column names the skimmer will save.
    # Naming convention:
    #       "name in nano files": "name in the skimmed output"
    skim_vars = {
        "Jet": {
            **P4,
            "rawFactor": "rawFactor",
            # Provenance: this jet's index in the input NanoAOD `Jet` collection,
            # attached in process() before anything can permute or drop it. The
            # saved slots are sorted by corrected pT, which is a *different*
            # order from the file's, so this is the only column that points back
            # at the input. See the `nanoIdx` comment in process() for what it
            # buys; `-99999` in an unfilled slot, like every other padded field.
            "nanoIdx": "NanoIdx",
            "hadronFlavour": "HadronFlavour",
            "partonFlavour": "PartonFlavour",
            # UnifiedParT (UParTAK4) flavour scores. The only AK4 tagger BTV
            # calibrates for 2024: the CAT payload for
            # Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15 ships
            # `UParTAK4_comb` / `_mujets` / `_light` b-tag SFs plus the CvL/CvB
            # working points, and no ParticleNet correction of any kind — not
            # even `particleNet_wp_values`. It is also the same network family
            # as the ParT charge-tagger heads below, so the flavour split and
            # the calibration target are not drawn from unrelated trainings.
            "btagUParTAK4B": "btagUParTAK4B",
            "btagUParTAK4CvB": "btagUParTAK4CvB",
            "btagUParTAK4CvL": "btagUParTAK4CvL",
            "btagUParTAK4CvNotB": "btagUParTAK4CvNotB",
            "btagUParTAK4QvG": "btagUParTAK4QvG",
            # ParticleNet + RobustParT, kept alongside UParT. No 2024 SF exists
            # for either, so neither can carry a b-tag weight, but they are
            # independent networks and are retained as ML inputs / cross-checks.
            "btagPNetB": "btagPNetB",
            "btagPNetCvB": "btagPNetCvB",
            "btagPNetCvL": "btagPNetCvL",
            "btagRobustParTAK4B": "btagRobustParTAK4B",
            "btagPNetCvNotB": "btagPNetCvNotB",
            "btagPNetQvG": "btagPNetQvG",
            # Jet charge Qk at kappa = 0.5 and 1.0, attached from the separate
            # `JetQk` collection by objects.attach_jet_charge. Sentinels are
            # -999 / -998 / -997, not PAD_VAL — see objects.QK_SENTINEL_MAX.
            #
            # The trailing underscore is load-bearing. Slot indices are appended
            # bare, so these are the only saved fields whose *name* ends in a
            # digit: without it, `ak4JetQkCharge105` could be read as either
            # QkCharge1 slot 05 or QkCharge10 slot 5. The separator makes the
            # split unambiguous for anything that parses branch names, and
            # matches what GenSelection already does for `ak4MatchedHadB_`.
            "QkCharge05": "QkCharge05_",
            "QkCharge10": "QkCharge10_",
            # Charge-tagger heads from the CMSSW_15_CHARGE fork — what this
            # analysis exists to calibrate.
            "ParTPosvsAll": "ParTPosvsAll",
            "ParTNegvsAll": "ParTNegvsAll",
            "ParTZerovsAll": "ParTZerovsAll",
            "ParTPosvsNeg": "ParTPosvsNeg",
            "PflavCharge": "PflavCharge",
            "FlavSplit": "FlavSplit",
        },
        "MET": {
            "pt": "Pt",
            "phi": "Phi",
        },
        # Generator-level AK4 jets, saved whole (MC only). The reco jets already
        # carry `MatchedGenJetPt`, but that is one number for the jets that were
        # *kept*; this is the full truth-level collection, for sanity-checking
        # the reco selection against what was actually there.
        #
        # `pt` is included via P4 even though it duplicates `MatchedGenJetPt` for
        # matched jets -- eta/phi/mass without pt would not define a jet, and the
        # duplication is the cross-check that the matching worked.
        #
        # nBHadrons / nCHadrons are the ghost-clustered heavy-flavour hadron
        # counts. For a *charge*-tagger calibration these are worth more than
        # `hadronFlavour` alone: the latter collapses to a single label, while
        # the counts distinguish a b jet from a b jet that also contains a
        # charmed hadron -- which is exactly the W -> cb topology this analysis
        # is built around.
        "GenJet": {
            **P4,
            "hadronFlavour": "HadronFlavour",
            "partonFlavour": "PartonFlavour",
            "nBHadrons": "NBHadrons",
            "nCHadrons": "NCHadrons",
        },
        "Lepton": {
            **P4,
            "charge": "charge",
        },
        "ElectronDebug": {
            "mvaIso_WP90": "MvaIsoWP90",
        },
        # Electron energy scale / smearing (electron_ss.py). `pt_raw` is the
        # uncorrected NanoAOD pT, kept so the correction stays auditable and
        # reversible after the fact.
        "ElectronEnergy": {
            "pt_raw": "PtRaw",
        },
        # The shifted pTs for the EGM scale/smearing systematics, MC only.
        # Saved per electron rather than as a weight because a pT shift changes
        # *which* electrons pass the selection, and that cannot be recovered
        # downstream from the nominal column alone. The keys must stay in step
        # with electron_ss.PT_VARIATIONS; tests/test_electron_ss.py asserts it.
        "ElectronEnergyMC": {
            "pt_scaleUp": "PtScaleUp",
            "pt_scaleDown": "PtScaleDown",
            "pt_smearUp": "PtSmearUp",
            "pt_smearDown": "PtSmearDown",
        },
        "MuonDebug": {
            "pfRelIso04_all": "PfRelIso04All",
        },
        "Event": {
            "run": "run",
            "event": "event",
            "luminosityBlock": "luminosityBlock",
        },
        # Both the sampled count (nPU) and the Poisson mean (nTrueInt, the
        # variable the pileup weights are derived in) are stored, so future
        # weight-file updates can be applied as a post-processing rescale.
        "Pileup": {
            "nPU",
            "nTrueInt",
        },
    }

    # We will not b-tag the jets at the Coffea skimmer processing level.
    # This is because our analysis would require testing multiple working points.

    # AK4 jet cleaning in this skimmer uses only the trigger-matched prompt lepton.
    # The cleaning collections are passed explicitly in process(), so no separate
    # lepton pT threshold configuration is needed here.

    # The constructor method, which is run automatically when an instance of the class is created.
    # Keep these variables in the function signature, as they are set by run.py.
    def __init__(
        self,
        xsecs: dict = None,
        save_systematics: bool = False,
        region: str = "signal",
        nano_version: str = "v12_private",
        prescale_factor: int = None,
    ):
        # Initialize the base Processor/Skimmer state first.
        super().__init__()

        # Store per-dataset cross sections (pb), falling back to empty if not provided.
        self.XSECS = xsecs if xsecs is not None else {}  # in pb

        # HLT selection
        # Build the HLT map, then pick the list for the requested analysis region.
        self.HLTs = {"signal": HLTs.hlt_list(hlt_prefix=False)}
        self.HLTs = self.HLTs[region]
        # Persist configuration flags for later processing steps.
        self._systematics = save_systematics
        self._nano_version = nano_version
        self._region = region
        # Coffea accumulator to collect outputs from process().
        self._accumulator = processor.dict_accumulator({})
        # Optional prescale: keep only events with event % N == 0.
        self._prescale_factor = prescale_factor

        # Log the configuration for user visibility.
        logger.info(
            f"Running skimmer with:\nsystematics {self._systematics}\nregion {self._region}"
        )

    @property  # a decorator that turns a method into a read-only attribute
    def accumulator(self):
        return self._accumulator  # This is defined above in __init__

    # The main processing method, called for each chunk of events.
    def process(self, events: ak.Array):
        """
        Runs event processor for different types of jets.

        Abbreviations:
        - JEC: Jet Energy Corrections
        - JMSR: Jet Mass Scale Resolution
        - ak4: anti-kT R=0.4 jets
        """

        # Define start time for debug prints
        start = time.time()

        # Log the number of input events.
        logging.info(f"# events {len(events)}")

        # Extract year and dataset from metadata.
        year = events.metadata["dataset"].split("_")[0]
        dataset = "_".join(events.metadata["dataset"].split("_")[1:])

        # isData is defined by the absence of genWeight.
        isData = not hasattr(events, "genWeight")

        # datasets for saving jec variations
        isJECs = (  # noqa: F841
            "HHto4B" in dataset
            or "TT" in dataset
            or "Wto2Q" in dataset
            or "Zto2Q" in dataset
            or "Hto2B" in dataset
            or "WW" in dataset
            or "ZZ" in dataset
            or "WZ" in dataset
        )

        # gen-weights
        gen_weights = events["genWeight"].to_numpy() if not isData else None
        n_events = len(events) if isData else np.sum(gen_weights)

        # selection and cutflow
        selection = PackedSelection()
        cutflow = OrderedDict()
        cutflow["all"] = n_events
        selection_args = (selection, cutflow, isData, gen_weights)

        # JEC factory loader
        JEC_loader = JECs(year)

        #########################
        # Object definitions
        #########################

        print("\nStarting object selection", f"{time.time() - start:.2f}")

        # Leptons (electrons and muons)
        num_leptons = 3  # We will save up to 3 leptons

        # EGM electron energy scale (data) / resolution smearing (MC), applied
        # to the full collection BEFORE good_electrons. Ordering is not
        # cosmetic: the correction moves electrons across the pT > 20 cut in
        # good_electrons and the 32 GeV trigger-matching threshold in
        # trig_match_sel, and applying it afterwards would erase exactly the
        # migration it describes. Everything downstream -- selection, jet
        # cleaning, the trigger-lepton choice, the lepton SFs, GenSelection --
        # therefore sees the corrected pT.
        corrected_electrons = apply_electron_scale_smearing(events, events.Electron, year, isData)

        electrons, etrigvars = objects.good_electrons(events, corrected_electrons, year)
        muons, mtrigvars = objects.good_muons(events, events.Muon, year)

        # These are bools saying if the lepton is matched to a trigger object or not
        trigMatchVars = {**etrigvars, **mtrigvars}
        for key, val in trigMatchVars.items():
            trigMatchVars[key] = pad_val(val, num_leptons, False, axis=1).astype(int)

        # Resolve this year's single-lepton HLT paths from HLTs.py, which is the single
        # source of truth (Ele32 for 2022/2023, Ele30 for 2024; IsoMu24 for all years).
        # This is the same lookup objects.trig_match_sel uses, so the trigger the event
        # is selected on always matches the trigger the prompt lepton is matched to.
        single_ele_hlt = HLTs.hlts_by_type(year, "EGamma", hlt_prefix=False)[0]
        single_mu_hlt = HLTs.hlts_by_type(year, "Muon", hlt_prefix=False)[0]

        def read_single_lep_hlt(name: str) -> np.ndarray:
            # Fail loudly rather than defaulting to all-False: a missing single-lepton
            # path would silently drop that entire lepton channel from the skim.
            if name not in events.HLT.fields:
                raise KeyError(
                    f"Required single-lepton trigger 'HLT_{name}' for year {year} is not "
                    f"present in the input NanoAOD. Without it the corresponding lepton "
                    f"channel would be silently dropped. Check the HLT menu for this "
                    f"sample and the year mapping in bbtautau/HLTs.py."
                )
            return events.HLT[name].to_numpy().astype(bool)

        hlt_single_ele = read_single_lep_hlt(single_ele_hlt)
        hlt_single_mu = read_single_lep_hlt(single_mu_hlt)

        # Identify prompt leptons: good leptons that are trigger-matched and pass
        # the analysis trigger activation thresholds in objects.trig_match_sel().
        prompt_electrons = electrons[etrigvars["ElectronTrigMatchEGamma"]]
        prompt_muons = muons[mtrigvars["MuonTrigMatchMuon"]]

        def leading_lepton_collection(leptons):
            pt_order = ak.argsort(leptons.pt, axis=1, ascending=False)
            leading_collection = leptons[pt_order][:, :1]
            return leading_collection, ak.firsts(leading_collection)

        leading_prompt_electrons, trigger_electron_candidate = leading_lepton_collection(
            prompt_electrons
        )
        leading_prompt_muons, trigger_muon = leading_lepton_collection(prompt_muons)

        # "ready" means: a trigger-matched candidate of this flavour exists in this
        # event. The pT comparison is NOT an extra cut -- objects.trig_match_sel
        # already folds `pt >= ptcut` into the match, so every prompt lepton is above
        # its path's offline plateau by construction. What the comparison does is
        # collapse the option-type `ak.firsts` result to a plain per-event boolean:
        # an empty prompt collection gives None, which fill_none turns into False.
        trigger_electron_ready = ak.fill_none(
            trigger_electron_candidate.pt >= objects.single_ele_lepton_pt(year),
            False,
        ).to_numpy()
        trigger_muon_ready = ak.fill_none(
            trigger_muon.pt >= objects.HLT_ISOMU24_LEPTON_PT,
            False,
        ).to_numpy()

        # One rule for both flavours: the trigger lepton is a *trigger-matched*
        # lepton above its path's offline plateau. Muon wins when both are
        # available, which is only decidable at all in the 0.2% of events where
        # both single-lepton paths fire.
        #
        # There is deliberately no looser electron branch. Until 2026-08-09 the
        # both-fired case fell back to the leading *good* electron, matched or not,
        # which meant the same event was judged by a different standard depending on
        # whether IsoMu24 happened to also fire -- and let an unmatched electron
        # collect an `electron_trigger` scale factor measured on matched ones. It
        # never actually selected an unmatched electron on the 2024 fixture, so
        # removing it changed no event there; it was a latent inconsistency, not an
        # observed bias.
        #
        # The `hlt_single_*` terms are redundant (trig_match_sel requires the path to
        # have fired before any lepton can be prompt) and kept as belt-and-braces:
        # they keep this block correct on its own terms if that ever changes.
        use_trigger_muon = hlt_single_mu & trigger_muon_ready
        use_trigger_electron = hlt_single_ele & trigger_electron_ready & ~use_trigger_muon

        def keep_leading_when(leading_collection, event_mask):
            event_mask_broadcast = ak.broadcast_arrays(ak.Array(event_mask), leading_collection.pt)[
                0
            ]
            return leading_collection[event_mask_broadcast]

        cleaning_electrons = keep_leading_when(leading_prompt_electrons, use_trigger_electron)
        cleaning_muons = keep_leading_when(leading_prompt_muons, use_trigger_muon)
        trigger_electron = ak.firsts(cleaning_electrons)

        print("* Leptons:\t", f"{time.time() - start:.2f}")

        # The trigger lepton resolved just above is also what the lepton scale
        # factors are evaluated on, down in add_weights() -> add_lepton_weights().

        # AK4 Jets
        # 10 slots, not 8: the semileptonic tt -> b c b~ b~ l nu final state has
        # four hard jets, and the chi^2 jet-parton assignment needs the ISR/FSR
        # jets around them too. `GenSelection.num_jets` pads the gen-match flags
        # and must stay equal to this, or slots 8-9 carry jets whose truth flags
        # were silently truncated.
        num_ak4_jets = 10
        jets, _jec_shifted_jetvars = JEC_loader.get_jec_jets(
            events,
            events.Jet,
            year,
            isData,
            jecs=utils.jecs,
            fatjets=False,
            applyData=True,
            dataset=dataset,
            nano_version=self._nano_version,
        )

        # Freeze each jet's position in the input NanoAOD `Jet` collection, here,
        # while `jets` is still that collection element for element. JECs change
        # energies but neither reorder nor filter, so this is identical to taking
        # the index off `events.Jet` -- and taking it here keeps it adjacent to
        # the first step that could ever invalidate it.
        #
        # Everything downstream permutes or drops jets, and after the pT sort in
        # particular an output slot has no algebraic relation to anything in the
        # input file. This column is what survives all of it:
        #   * it names the input jet a saved slot came from, for any check that
        #     wants to go back to the NanoAOD (diagnostics/check_jet_tagger_roundtrip.py
        #     matches on eta/phi independently and then cross-checks against it);
        #   * it indexes `JetQk` too, since `Jet` is a positional prefix of it
        #     (objects.attach_jet_charge), so auditing the jet charges is a lookup
        #     rather than an excavation;
        #   * `set(range(nJets)) - set(saved indices)` is exactly the set of jets
        #     the 10-slot truncation below discarded, which is otherwise
        #     unrecoverable from the output.
        jets["nanoIdx"] = ak.values_astype(ak.local_index(jets, axis=1), np.int32)

        # MET must be rebuilt from the jets we just recorrected -- it is minus the
        # vector sum of the event, so new jet energies mean a new MET. Done here,
        # before good_ak4jets(), because Type-1 sums over every jet in the event,
        # not just the cleaned analysis ones.
        met = events[MET_COLLECTION]
        if JEC_loader.met_factory is not None:
            # 2022/2023: coffea pickle factory (unchanged behaviour).
            met = JEC_loader.met_factory.build(met, jets, {}) if isData else met
        elif not isData:
            # 2024: no pickle factory, and CorrectedMETFactory cannot be used --
            # it requires MetUnclustEnUpDeltaX/Y, which NanoAODv15 does not ship
            # (it has ptUnclusteredUp/Down instead). Rebuild Type-1 explicitly.
            if RAW_MET_COLLECTION in events.fields:
                type1_met = JEC_loader.type1_met_2024(events[RAW_MET_COLLECTION], jets)
                if type1_met is not None:
                    met = type1_met
            else:
                logger.warning(
                    f"{RAW_MET_COLLECTION} not in NanoAOD; keeping {MET_COLLECTION} "
                    "uncorrected (it will be inconsistent with the recorrected jets)."
                )

        print("* ak4 JECs:\t", f"{time.time() - start:.2f}")

        # Attach jet charge before the selection below, while `jets` is still
        # index-aligned with the input `Jet` collection that `JetQk` is a
        # superset of. JEC changes pt/mass values but neither the order nor the
        # count, so doing it here rather than pre-JEC is equivalent and keeps
        # the raw-NanoAOD dependency in one place.
        jets = objects.attach_jet_charge(jets, events)

        # The jet-veto map is evaluated on the *uncleaned* collection (see
        # `objects.jetveto_candidate_jets`), so keep a handle on it before
        # `good_ak4jets` throws the lepton-overlapping jets away.
        jetveto_jets = objects.jetveto_candidate_jets(jets)

        jets = objects.good_ak4jets(
            jets,
            self._nano_version,
            events,
            dr_leptons=0.4,
            cleaning_electrons=cleaning_electrons,
            cleaning_muons=cleaning_muons,
            jet_id="tight",
        )

        # Sort into descending *corrected* pT. Nothing upstream gives us this.
        # NanoAOD is written pT-ordered, but under the JEC of its own era; the
        # re-derivation above rescales every jet by a different factor, and the
        # JER smear on top of it is partly stochastic per jet, so adjacent jets
        # swap constantly -- only ~44% of the full collection is still ordered by
        # the time it reaches this line. Masking in good_ak4jets() preserves
        # whatever order it was handed, so it cannot fix it either.
        #
        # Two things break without the sort, and the second is the serious one:
        #   * `ak4JetPt0` is not the leading jet, so any downstream "leading jet"
        #     is wrong in ~31% of events;
        #   * `pad_val(..., num_ak4_jets, clip=True)` below keeps the *first* ten
        #     jets, not the *hardest* ten. In an event with more than ten selected
        #     jets that silently deletes hard jets while keeping soft ones -- and
        #     the chi^2 jet-parton assignment this skim feeds needs the hard ones.
        #
        # The placement is load-bearing on both sides. It must come *after*
        # attach_jet_charge(), the one step that requires the input ordering to be
        # intact, and *before* the GenSelection call below, which pads its own
        # `ak4Matched*_` truth flags from this same array: sorting after that call
        # would leave slot k's kinematics and slot k's gen match describing
        # different jets, with nothing anywhere to catch it.
        jets = jets[ak.argsort(jets.pt, axis=1, ascending=False)]

        ht = ak.sum(jets.pt, axis=1)
        print("* ak4:\t", f"{time.time() - start:.2f}")

        # We will not use ak8 jets or JMSR for this analysis.

        #########################
        # Save / derive variables
        #########################

        # Gen variables
        genVars = {}
        for d in gen_selection_dict:  # gen_selection_dict is defined in GenSelection.py
            if d in dataset:  # dataset is extracted from events metadata
                vars_dict = gen_selection_dict[d](
                    events, jets, electrons, muons, selection_args, P4
                )
                genVars = {**genVars, **vars_dict}

        # used for normalization to cross section below
        #
        # ORDERING MATTERS: this line must run BEFORE any add_selection call
        # (all currently below, in the Selection section). At this point
        # selection.names is empty, so gen_selected is all-True and np_nominal
        # sums over every event read -- the denominator of the finalWeight
        # ratio estimator. Moving any add_selection above this line silently
        # changes every normalized yield.
        gen_selected = (
            selection.all(*selection.names)
            if len(selection.names)
            else np.ones(len(events)).astype(bool)
        )
        logging.info(f"Passing gen selection: {np.sum(gen_selected)} / {len(events)}")

        # Lepton variables
        electron_skimvars = {
            **self.skim_vars["Lepton"],
            **self.skim_vars["ElectronDebug"],
            **self.skim_vars["ElectronEnergy"],
        }
        if not isData:
            # The scale/smearing variations exist on MC only -- data gets the
            # nominal scale and is never varied (see electron_ss.py).
            electron_skimvars = {**electron_skimvars, **self.skim_vars["ElectronEnergyMC"]}

        electronVars = {
            f"Electron{key}": pad_val(electrons[var], num_leptons, axis=1)
            for (var, key) in electron_skimvars.items()
        }
        muonVars = {
            f"Muon{key}": pad_val(muons[var], num_leptons, axis=1)
            for (var, key) in self.skim_vars["Lepton"].items()
        }
        muonVars.update(
            {
                f"Muon{key}": pad_val(muons[var], num_leptons, axis=1)
                for (var, key) in self.skim_vars["MuonDebug"].items()
            }
        )
        leptonVars = {**electronVars, **muonVars}

        # Trigger lepton variables use the same per-event trigger-lepton choice
        # used above for AK4 jet cleaning.

        def leading_or_pad(leptons, field: str) -> np.ndarray:
            if field not in leptons.fields:
                return np.full(len(events), PAD_VAL)
            return ak.fill_none(leptons[field], PAD_VAL).to_numpy()

        triggerLeptonVars = {
            "TriggerLeptonFlav": np.where(
                use_trigger_electron,
                11,
                np.where(use_trigger_muon, 13, PAD_VAL),
            ),
            "TriggerLeptonPt": np.where(
                use_trigger_electron,
                leading_or_pad(trigger_electron, "pt"),
                np.where(use_trigger_muon, leading_or_pad(trigger_muon, "pt"), PAD_VAL),
            ),
            "TriggerLeptonPhi": np.where(
                use_trigger_electron,
                leading_or_pad(trigger_electron, "phi"),
                np.where(use_trigger_muon, leading_or_pad(trigger_muon, "phi"), PAD_VAL),
            ),
            "TriggerLeptonEta": np.where(
                use_trigger_electron,
                leading_or_pad(trigger_electron, "eta"),
                np.where(use_trigger_muon, leading_or_pad(trigger_muon, "eta"), PAD_VAL),
            ),
            "TriggerLeptonCharge": np.where(
                use_trigger_electron,
                leading_or_pad(trigger_electron, "charge"),
                np.where(use_trigger_muon, leading_or_pad(trigger_muon, "charge"), PAD_VAL),
            ),
            "TriggerLeptonMass": np.where(
                use_trigger_electron,
                leading_or_pad(trigger_electron, "mass"),
                np.where(use_trigger_muon, leading_or_pad(trigger_muon, "mass"), PAD_VAL),
            ),
            "TriggerLeptonIsolation": np.where(
                use_trigger_electron,
                leading_or_pad(trigger_electron, "pfRelIso03_all"),
                np.where(
                    use_trigger_muon,
                    leading_or_pad(trigger_muon, "pfRelIso04_all"),
                    PAD_VAL,
                ),
            ),
        }

        # Generator-level AK4 jets (MC only), the whole collection rather than a
        # leading subset. 25 slots because that is where truncation stops
        # happening at all: the NanoAOD `GenJet` threshold is pT > 10 GeV, and on
        # tests/data/test-input.root the multiplicity is 7 at the median, 20 at
        # the 99.99th percentile and 23 at its maximum over 208 780 events.
        #
        # Being generous costs almost nothing, which is why the number is not
        # tuned tighter: the surplus slots are pure padding, and padding is the
        # most compressible thing in the file. Measured on the full fixture,
        # 15 slots cost 47.9 MiB and 30 slots cost 48.8 MiB -- under 2 % apart
        # for twice the columns. The whole block is ~244 B/event.
        #
        # `GenJet` is pT-descending as written by NanoAOD and nothing here
        # touches it (no JEC applies to truth-level jets, which is the entire
        # reason the reco collection needed sorting and this one does not), so a
        # truncated event loses its *softest* gen jets and nothing else.
        num_gen_jets = 25

        # AK4 Jet variables
        jet_skimvars = self.skim_vars["Jet"]
        jets["BTaggable"] = ak.values_astype((jets.pt >= 20.0) & (abs(jets.eta) <= 2.5), np.int32)
        jet_skimvars = {
            **jet_skimvars,
            "BTaggable": "BTaggable",
        }
        if not isData:
            # Pointer from this reco jet to its generator-level jet, as an index
            # into the `GenJet*` slots written below -- the truth-side twin of
            # `nanoIdx`. Storing the pointer rather than a copy of the gen jet is
            # what lets the full `GenJet` collection stay in the file: the jets
            # the reco selection did *not* keep (0.41 hard gen jets per event,
            # 0.169 of them b-flavour) are exactly the acceptance population, and
            # a per-reco-slot copy would bury them. See docs/history.md.
            #
            # Three values, and the distinction between them is load-bearing:
            #   >= 0      the gen jet's slot index
            #   -1        NanoAOD's own "no gen jet matched this reco jet".
            #             Kept rather than folded into PAD_VAL because it is a
            #             physics statement (an unmatched, i.e. pileup-like, reco
            #             jet) and it is NanoAOD's documented convention; 31 870
            #             of the fixture's saved jets carry it.
            #   PAD_VAL   either the slot holds no jet at all, or -- and this is
            #             why the clamp exists -- the gen jet is real but sits
            #             past `num_gen_jets` and was therefore never written.
            #             Never let that case through as an index: it would point
            #             confidently at the wrong gen jet. `nGenJets` below is
            #             what tells you whether it can have happened (it does
            #             not on the fixture: max nGenJet is 23).
            jets["genJetIdxSaved"] = ak.where(
                jets.genJetIdx < num_gen_jets, jets.genJetIdx, PAD_VAL
            )
            jet_skimvars = {
                **jet_skimvars,
                "pt_gen": "MatchedGenJetPt",
                "genJetIdxSaved": "GenJetIdx",
            }

        ak4JetVars = {
            f"ak4Jet{key}": pad_val(jets[var], num_ak4_jets, axis=1)
            for (var, key) in jet_skimvars.items()
        }

        genJetVars = (
            {}
            if isData
            else {
                f"GenJet{key}": pad_val(events.GenJet[var], num_gen_jets, axis=1)
                for (var, key) in self.skim_vars["GenJet"].items()
            }
        )

        # MET
        metVars = {f"MET{key}": met[var].to_numpy() for (var, key) in self.skim_vars["MET"].items()}

        # Event variables
        eventVars = {
            key: events[val].to_numpy()
            for key, val in self.skim_vars["Event"].items()
            if key in events.fields
        }
        eventVars["ht"] = ht.to_numpy()
        eventVars["nElectrons"] = ak.num(electrons).to_numpy()
        eventVars["nMuons"] = ak.num(muons).to_numpy()
        eventVars["nJets"] = ak.num(jets).to_numpy()
        if not isData:
            # Gen jets *in the event*, which is not the same as gen jets in the
            # file: `nGenJets > num_gen_jets` is the only way to know the
            # collection was truncated, and it is what makes a PAD_VAL in
            # `ak4JetGenJetIdx` readable as "gen jet past the slots" rather than
            # "empty reco slot". Same role `nJets` plays for the reco side.
            eventVars["nGenJets"] = ak.num(events.GenJet).to_numpy()

        # Pileup energy density, the same one JECs.get_jec_jets evaluates the
        # corrections with (`fixedGridRhoFastjetAll` -- NanoAOD ships six rho
        # flavours and they are not interchangeable). One float per event.
        #
        # Saved because it is the missing input for redoing JER downstream. The
        # JES uncertainty payloads (`V5_MC_Total`, `V5_MC_Regrouped_*`) and the
        # JER scale factor take only (JetEta, JetPt), both of which are already
        # per-jet columns -- but `JRV2_MC_PtResolution` takes (JetEta, JetPt,
        # Rho), so without this the resolution cannot be evaluated and the JER
        # systematic is not reconstructible from the skim at any price. See
        # docs/processor.md, "Deriving JES/JER variations from the skim".
        rho = (
            events.Rho.fixedGridRhoFastjetAll
            if "Rho" in events.fields
            else events.fixedGridRhoFastjetAll
        )
        eventVars["Rho"] = rho.to_numpy()

        if isData:
            pileupVars = {key: np.ones(len(events)) * PAD_VAL for key in self.skim_vars["Pileup"]}
        else:
            pileupVars = {key: events.Pileup[key].to_numpy() for key in self.skim_vars["Pileup"]}
        pileupVars = {**pileupVars, "nPV": events.PV["npvs"].to_numpy()}

        # Trigger variables
        HLTVars = {}
        zeros = np.zeros(len(events), dtype="int")
        for trigger in self.HLTs[year]:
            if trigger in events.HLT.fields:
                HLTVars[f"HLT_{trigger}"] = events.HLT[trigger].to_numpy().astype(int)
            else:
                logger.warning(f"Missing {trigger}!")
                HLTVars[f"HLT_{trigger}"] = zeros

        print("HLT vars", f"{time.time() - start:.2f}")

        # # JEC variations for VBF Jets
        # if self._region == "signal" and isJECs:
        #     for var in ["pt"]:
        #         key = self.skim_vars["Jet"][var]
        #         for label, shift in utils.jecs.items():
        #             if shift in ak.fields(vbf_jets):
        #                 for vari in ["up", "down"]:
        #                     vbfJetVars[f"VBFJet{key}_{label}_{vari}"] = pad_val(
        #                         vbf_jets[shift][vari][var], 2, axis=1
        #                     )

        skimmed_events = {
            **genVars,
            **eventVars,
            **pileupVars,
            **trigMatchVars,
            **HLTVars,
            **leptonVars,
            **triggerLeptonVars,
            **ak4JetVars,
            **genJetVars,
            **metVars,
        }

        print("Vars", f"{time.time() - start:.2f}")

        ######################
        # Selection
        ######################

        # Require at least one single-lepton trigger path: IsoMu24 OR the year's
        # single-electron path (Ele32 for 2022/2023, Ele30 for 2024). If both fire, the
        # event is retained and the trigger-lepton flavor is resolved by the per-event
        # trigger-lepton choice above.
        single_lep_trigger = hlt_single_mu | hlt_single_ele
        add_selection("single_lep_trigger", single_lep_trigger, *selection_args)

        # MET filters: require every flag in the Run-3 recommended set (see
        # RUN3_MET_FILTERS). All must be present in the input; a missing one raises.
        add_selection("met_filters", met_filter_mask(events, year), *selection_args)

        # Jet veto maps. `jetveto_jets` is JERC's minimal selection off the
        # uncleaned collection, NOT the analysis jets -- see
        # `objects.jetveto_candidate_jets` for why the two differ.
        cut_jetveto = get_jetveto_event(jetveto_jets, year)
        add_selection("ak4_jetveto", cut_jetveto, *selection_args)

        # # >=2 AK8 jets passing selections
        # add_selection("ak8_numjets", (ak.num(fatjets) >= 2), *selection_args)

        # Two lepton stages, deliberately. `1lep` is the loose good-lepton count and
        # is kept only so the cutflow shows what the tightening below costs; it is
        # implied by `trigger_lepton` and never removes an event on its own.
        add_selection("1lep", ak.num(muons) + ak.num(electrons) >= 1, *selection_args)

        # `trigger_lepton` is the cut that matters: the event must have a *resolved*
        # trigger lepton, i.e. the same object the `TriggerLepton*` branches, the
        # lepton scale factors (add_lepton_weights) and the AK4 jet DeltaR cleaning
        # all key off. A good-lepton count is not equivalent, and the gap is not
        # academic -- on tests/data/test-input.root it is 3.5% of the events that
        # would otherwise be written, of which:
        #   - 97% have their only good lepton *below* the offline plateau cut
        #     (muon < 26, electron < 32 GeV in 2024), i.e. sitting on the trigger
        #     turn-on where the tag-and-probe trigger SF is not the measured
        #     quantity;
        #   - the rest either carry no good lepton of the flavour whose HLT fired,
        #     or a lepton above threshold that no HLT object matches -- both mean
        #     the path fired on something other than the analysis lepton.
        # Keeping them would write events with PAD_VAL lepton kinematics (nothing to
        # build W -> l nu from), a silent 1.0 lepton SF, and jets that were never
        # cleaned against the lepton. See docs/processor.md section 6.
        add_selection("trigger_lepton", use_trigger_electron | use_trigger_muon, *selection_args)
        if self._prescale_factor:
            cut_prescale = events.event % self._prescale_factor == 0
            add_selection("prescale", cut_prescale, *selection_args)

        print("Selection", f"{time.time() - start:.2f}")

        # -----------------------------------------------------------------------------
        # Event Weights (per-event)
        # -----------------------------------------------------------------------------
        # Data events: weight = 1. MC events: genweight * corrections * normalization.
        totals_dict = {"nevents": n_events}  # Track totals for reporting/normalization.

        if isData:
            # Data has no MC corrections; assign unit weight per event.
            skimmed_events["weight"] = np.ones(n_events)
        else:
            # MC: compute nominal + systematic weights inside add_weights(...).
            weights_dict, totals_temp = self.add_weights(
                events,
                year,
                dataset,
                gen_weights,
                gen_selected,
                trigger_electron=trigger_electron,
                use_trigger_electron=use_trigger_electron,
                trigger_muon=trigger_muon,
                use_trigger_muon=use_trigger_muon,
            )
            # Merge the weight columns into the skim output and keep the totals metadata.
            skimmed_events = {**skimmed_events, **weights_dict}
            totals_dict = {**totals_dict, **totals_temp}

        ##############################
        # Reshape and apply selections
        ##############################

        # This is where the selection happens!
        sel_all = selection.all(*selection.names)
        skimmed_events = {
            key: value.reshape(len(skimmed_events["weight"]), -1)[sel_all]
            for (key, value) in skimmed_events.items()
        }

        dataframe = self.to_pandas(skimmed_events)
        fname = events.behavior["__events_factory__"]._partition_key.replace("/", "_") + ".parquet"
        self.dump_table(dataframe, fname)

        logger.info(f"Cutflow:\n{cutflow}")

        print("Return ", f"{time.time() - start:.2f}")
        print("Columns:", list(dataframe.columns))
        return {year: {dataset: {"totals": totals_dict, "cutflow": cutflow}}}

    def postprocess(self, accumulator):
        return accumulator

    def add_weights(
        self,
        events,
        year,
        dataset,
        gen_weights,
        gen_selected,
        trigger_electron=None,
        use_trigger_electron=None,
        trigger_muon=None,
        use_trigger_muon=None,
    ) -> tuple[dict, dict]:
        """
        Adds weights and variations, saves totals for all norm preserving weights and variations

        The four trigger-lepton arguments are the per-event leading electron /
        muon candidates and the flavor choice made in process(); they are what
        the lepton scale factors are evaluated on. Omitting them skips those
        SFs, which is only correct for a run that has no lepton selection.
        """

        # -------------------------------------------------------------------------
        # Per-event weight construction (MC only)
        # -------------------------------------------------------------------------
        # 1) Create a Coffea Weights container that can combine multiple factors.
        weights = Weights(len(events), storeIndividual=True)

        # 2) Seed the event weight with the generator weight from NanoAOD.
        weights.add("genweight", gen_weights)

        # 3) Add standard MC corrections/variations.
        # nTrueInt (the Poisson mean mu), NOT the sampled count nPU -- the
        # puWeights corrections are functions of NumTrueInteractions.
        add_pileup_weight(weights, year, events.Pileup.nTrueInt.to_numpy())
        add_ps_weight(weights, events.PSWeight)

        # Lepton reco / ID / isolation / trigger SFs for the event's trigger
        # lepton. Not norm-preserving: these correct efficiencies, so they move
        # the yield rather than just reshaping it.
        if use_trigger_electron is None or use_trigger_muon is None:
            # Say so rather than dropping ~5% of the event weight in silence.
            logger.warning(
                "add_weights called without the trigger lepton; lepton scale factors "
                "are NOT applied and MC lepton efficiencies stay uncorrected."
            )
        else:
            add_lepton_weights(
                weights,
                year,
                trigger_electron,
                use_trigger_electron,
                trigger_muon,
                use_trigger_muon,
            )

        logger.debug("weights", extra=weights._weights.keys())

        ###################### Save all the weights and variations ######################

        # 4) Identify weights that should preserve normalization across variations.
        norm_preserving_weights = hh_vars.norm_preserving_weights

        # 5) Prepare output dictionaries.
        weights_dict = {}
        totals_dict = {}

        # 6) Compute the nominal per-event combined weight.
        weights_dict["weight"] = weights.weight()

        # 7) Also compute the normalization-preserving partial weight and its total.
        weight_np = weights.partial_weight(include=norm_preserving_weights)
        totals_dict["np_nominal"] = np.sum(weight_np[gen_selected])

        # 8) If requested, compute per-event systematic variations.
        if self._systematics:
            for systematic in list(weights.variations):
                weights_dict[f"weight_{systematic}"] = weights.weight(modifier=systematic)

                if utils.remove_variation_suffix(systematic) in norm_preserving_weights:
                    var_weight = weights.partial_weight(include=norm_preserving_weights)
                    # modify manually
                    if "Down" in systematic and systematic not in weights._modifiers:
                        var_weight = (
                            var_weight / weights._modifiers[systematic.replace("Down", "Up")]
                        )
                    else:
                        var_weight = var_weight * weights._modifiers[systematic]

                    # need to save total # events for each variation for normalization in post-processing
                    totals_dict[f"np_{systematic}"] = np.sum(var_weight[gen_selected])

        # 9) Debugging aid: store each individual weight factor separately.
        for key in weights._weights:
            weights_dict[f"single_weight_{key}"] = weights.partial_weight([key])

        # 10) Add theory variations (scale/PDF) for supported datasets.
        ###################### alpha_S and PDF variations ######################

        if ("HHTobbbb" in dataset or "HHto4B" in dataset) or dataset.startswith(("TTTo", "TTto")):
            scale_weights = get_scale_weights(events)
            if scale_weights is not None:
                weights_dict["scale_weights"] = (
                    scale_weights * weights_dict["weight"][:, np.newaxis]
                )
                totals_dict["np_scale_weights"] = np.sum(
                    (scale_weights * weight_np[:, np.newaxis])[gen_selected], axis=0
                )

        if "HHTobbbb" in dataset or "HHto4B" in dataset:
            pdf_weights = get_pdf_weights(events)
            weights_dict["pdf_weights"] = pdf_weights * weights_dict["weight"][:, np.newaxis]
            totals_dict["np_pdf_weights"] = np.sum(
                (pdf_weights * weight_np[:, np.newaxis])[gen_selected], axis=0
            )

        # 11) Apply cross section * luminosity normalization to all weights.
        ###################### Normalization (Step 1) ######################

        weight_norm = self.get_dataset_norm(year, dataset)
        # normalize all the weights to xsec, needs to be divided by totals in Step 2 in post-processing
        for key, val in weights_dict.items():
            weights_dict[key] = val * weight_norm

        # 12) Also store the unnormalized nominal weight for post-processing checks.
        weights_dict["weight_noxsec"] = weights.weight()

        # 13) Top-pT reweighting factors for ttbar MC, as standalone columns.
        #
        # Deliberately *after* the sigma*L loop in step 11, and deliberately not
        # in the `Weights` container: these stay raw per-event scale factors, so
        # they reach neither `weight` nor `finalWeight` nor `np_nominal`.
        # Applying them is a downstream choice, and the recommended systematic
        # is on/off rather than up/down. They are Run 2 parameterisations on Run
        # 3 samples -- src/vcb/processors/top_pt.py carries the full caveat.
        weights_dict.update(top_pt_weights(events, dataset))

        return weights_dict, totals_dict
