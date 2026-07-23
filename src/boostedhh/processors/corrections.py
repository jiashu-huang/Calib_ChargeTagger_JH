"""
Collection of utilities for corrections and systematics in processors.

Loosely based on https://github.com/jennetd/hbb-coffea/blob/master/boostedhiggs/corrections.py

Most corrections retrieved from the cms-nanoAOD repo:
See https://cms-nanoaod-integration.web.cern.ch/commonJSONSFs/

Authors: Raghav Kansal, Cristina Suarez
"""

from __future__ import annotations

import gzip
import pathlib
import pickle
import random
import sys

import awkward as ak
import correctionlib
import numpy as np
import uproot
from coffea.analysis_tools import Weights
from coffea.nanoevents.methods import vector
from coffea.nanoevents.methods.base import NanoEventsArray
from coffea.nanoevents.methods.nanoaod import FatJetArray, JetArray

from .utils import pad_val

ak.behavior.update(vector.behavior)
package_path = str(pathlib.Path(__file__).parent.parent.resolve())

# Important Run3 start of Run
FirstRun_2022C = 355794
FirstRun_2022D = 357487
LastRun_2022D = 359021
FirstRun_2022E = 359022
LastRun_2022F = 362180

"""
CorrectionLib files are available from: /cvmfs/cms.cern.ch/rsync/cms-nanoAOD/jsonpog-integration - synced daily
"""
pog_correction_path = "/cvmfs/cms.cern.ch/rsync/cms-nanoAOD/jsonpog-integration/"
pog_jsons = {
    "muon": ["MUO", "muon_Z.json.gz"],
    "electron": ["EGM", "electron.json.gz"],
    "pileup": ["LUM", "puWeights.json.gz"],
    "fatjet_jec": ["JME", "fatJet_jerc.json.gz"],
    "jet_jec": ["JME", "jet_jerc.json.gz"],
    "jetveto": ["JME", "jetvetomaps.json.gz"],
    "btagging": ["BTV", "btagging.json.gz"],
}


def get_UL_year(year: str) -> str:
    return f"{year}_UL"


def get_pog_json(obj: str, year: str) -> str:
    try:
        pog_json = pog_jsons[obj]
    except:
        print(f"No json for {obj}")

    year = get_UL_year(year) if year == "2018" else year
    if "2022" in year or "2023" in year or "2024" in year:
        year = {
            "2022": "2022_Summer22",
            "2022EE": "2022_Summer22EE",
            "2023": "2023_Summer23",
            "2023BPix": "2023_Summer23BPix",
            "2024": "2024_Summer24",
        }[year]
    return f"{pog_correction_path}/POG/{pog_json[0]}/{year}/{pog_json[1]}"


def add_pileup_weight(weights: Weights, year: str, nPU: np.ndarray, dataset: str | None = None):
    # clip nPU from 0 to 100
    nPU = np.clip(nPU, 0, 99)
    # print(list(nPU))

    if "Pu60" in dataset or "Pu70" in dataset:
        # pileup profile from data
        path_pileup = package_path + "/corrections/data/MyDataPileupHistogram2022FG.root"
        pileup_profile = uproot.open(path_pileup)["pileup"]
        pileup_profile = pileup_profile.to_numpy()[0]
        # normalise
        pileup_profile /= pileup_profile.sum()

        # https://indico.cern.ch/event/695872/contributions/2877123/attachments/1593469/2522749/pileup_ppd_feb_2018.pdf
        # pileup profile from MC
        pu_name = "Pu60" if "Pu60" in dataset else "Pu70"
        path_pileup_dataset = package_path + f"/corrections/data/pileup/{pu_name}.npy"
        pileup_MC = np.load(path_pileup_dataset)

        # avoid division by 0 (?)
        pileup_MC[pileup_MC == 0.0] = 1
        pileup_correction = pileup_profile / pileup_MC
        # remove large MC reweighting factors to prevent artifacts
        pileup_correction[pileup_correction > 10] = 10
        sf = pileup_correction[nPU]
        # no uncertainties
        weights.add("pileup", sf)

    else:
        # https://twiki.cern.ch/twiki/bin/view/CMS/LumiRecommendationsRun3
        values = {}

        if year == "2024":
            # No POG/LUM/2024_Summer24 on this cvmfs jsonpog-integration snapshot.
            # Preferred: a user-supplied 2024 puWeights bundled in the repo
            # (see SHOPPING-LIST.md). Fallback: 2023 (Summer23) weights as a
            # PLACEHOLDER -- pileup is a norm-preserving weight, so this only
            # reshapes distributions, not the normalization.
            bundled_2024 = package_path + "/corrections/2024_puWeights.json.gz"
            if pathlib.Path(bundled_2024).is_file():
                cset = correctionlib.CorrectionSet.from_file(bundled_2024)
                corr = list(cset.keys())[0]
                print(f"Pileup 2024: using bundled {bundled_2024} (correction '{corr}')")
            else:
                print(
                    "WARNING: 2024 pileup weights not available -- using 2023 (Summer23) "
                    "puWeights as a PLACEHOLDER. Drop the real 2024 file in "
                    "src/boostedhh/corrections/2024_puWeights.json.gz (see SHOPPING-LIST.md)."
                )
                cset = correctionlib.CorrectionSet.from_file(get_pog_json("pileup", "2023"))
                corr = "Collisions2023_366403_369802_eraBC_GoldenJson"
        else:
            cset = correctionlib.CorrectionSet.from_file(get_pog_json("pileup", year))
            corr = {
                "2018": "Collisions18_UltraLegacy_goldenJSON",
                "2022": "Collisions2022_355100_357900_eraBCD_GoldenJson",
                "2022EE": "Collisions2022_359022_362760_eraEFG_GoldenJson",
                "2023": "Collisions2023_366403_369802_eraBC_GoldenJson",
                "2023BPix": "Collisions2023_369803_370790_eraD_GoldenJson",
            }[year]
        # evaluate and clip up to 10 to avoid large weights
        values["nominal"] = np.clip(cset[corr].evaluate(nPU, "nominal"), 0, 10)
        values["up"] = np.clip(cset[corr].evaluate(nPU, "up"), 0, 10)
        values["down"] = np.clip(cset[corr].evaluate(nPU, "down"), 0, 10)

        weights.add("pileup", values["nominal"], values["up"], values["down"])


def get_vpt(genpart, check_offshell=False):
    """Only the leptonic samples have no resonance in the decay tree, and only
    when M is beyond the configured Breit-Wigner cutoff (usually 15*width)
    """
    boson = ak.firsts(
        genpart[
            ((genpart.pdgId == 23) | (abs(genpart.pdgId) == 24))
            & genpart.hasFlags(["fromHardProcess", "isLastCopy"])
        ]
    )
    if check_offshell:
        offshell = genpart[
            genpart.hasFlags(["fromHardProcess", "isLastCopy"])
            & ak.is_none(boson)
            & (abs(genpart.pdgId) >= 11)
            & (abs(genpart.pdgId) <= 16)
        ].sum()
        return ak.where(ak.is_none(boson.pt), offshell.pt, boson.pt)
    return np.array(ak.fill_none(boson.pt, 0.0))


def add_ps_weight(weights, ps_weights):
    """
    Parton Shower Weights (FSR and ISR)
    """

    nweights = len(weights.weight())
    nom = np.ones(nweights)

    up_isr = np.ones(nweights)
    down_isr = np.ones(nweights)
    up_fsr = np.ones(nweights)
    down_fsr = np.ones(nweights)

    if len(ps_weights[0]) == 4:
        up_isr = ps_weights[:, 0]  # ISR=2, FSR=1
        down_isr = ps_weights[:, 2]  # ISR=0.5, FSR=1

        up_fsr = ps_weights[:, 1]  # ISR=1, FSR=2
        down_fsr = ps_weights[:, 3]  # ISR=1, FSR=0.5

    elif len(ps_weights[0]) > 1:
        print("PS weight vector has length ", len(ps_weights[0]))

    weights.add("ISRPartonShower", nom, up_isr, down_isr)
    weights.add("FSRPartonShower", nom, up_fsr, down_fsr)


def get_pdf_weights(events):
    """
    For the PDF acceptance uncertainty:
        - store 103 variations. 0-100 PDF values
        - The last two values: alpha_s variations.
        - you just sum the yield difference from the nominal in quadrature to get the total uncertainty.
        e.g. https://github.com/LPC-HH/HHLooper/blob/master/python/prepare_card_SR_final.py#L258
        and https://github.com/LPC-HH/HHLooper/blob/master/app/HHLooper.cc#L1488

    Some references:
    Scale/PDF weights in MC https://twiki.cern.ch/twiki/bin/view/CMS/HowToPDF
    https://twiki.cern.ch/twiki/bin/viewauth/CMS/TopSystematics#PDF
    """
    return events.LHEPdfWeight.to_numpy()


def get_scale_weights(events):
    """
    QCD Scale variations, best explanation I found is here:
    https://twiki.cern.ch/twiki/bin/viewauth/CMS/TopSystematics#Factorization_and_renormalizatio

    TLDR: we want to vary the renormalization and factorization scales by a factor of 0.5 and 2,
    and then take the envelope of the variations on our final observation as the up/down uncertainties.

    Importantly, we need to keep track of the normalization for each variation,
    so that this uncertainty takes into account the acceptance effects of our selections.

    LHE scale variation weights (w_var / w_nominal) (from https://cms-nanoaod-integration.web.cern.ch/autoDoc/NanoAODv9/2018UL/doc_TTToSemiLeptonic_TuneCP5_13TeV-powheg-pythia8_RunIISummer20UL18NanoAODv9-106X_upgrade2018_realistic_v16_L1v1-v1.html#LHEScaleWeight)
    [0] is renscfact=0.5d0 facscfact=0.5d0 ; <=
    [1] is renscfact=0.5d0 facscfact=1d0 ; <=
    [2] is renscfact=0.5d0 facscfact=2d0 ;
    [3] is renscfact=1d0 facscfact=0.5d0 ; <=
    [4] is renscfact=1d0 facscfact=1d0 ;
    [5] is renscfact=1d0 facscfact=2d0 ; <=
    [6] is renscfact=2d0 facscfact=0.5d0 ;
    [7] is renscfact=2d0 facscfact=1d0 ; <=
    [8] is renscfact=2d0 facscfact=2d0 ; <=

    See also https://git.rwth-aachen.de/3pia/cms_analyses/common/-/blob/11e0c5225416a580d27718997a11dc3f1ec1e8d1/processor/generator.py#L93 for an example.
    """
    if len(events[0].LHEScaleWeight) > 0:
        if len(events[0].LHEScaleWeight) == 9:
            variations = events.LHEScaleWeight[:, [0, 1, 3, 5, 7, 8]].to_numpy()
            nominal = events.LHEScaleWeight[:, 4].to_numpy()[:, np.newaxis]
            variations /= nominal
        else:
            variations = events.LHEScaleWeight[:, [0, 1, 3, 4, 6, 7]].to_numpy()
        return np.clip(variations, 0.0, 4.0)
    else:
        return None


# 2024 (Summer24) jet corrections applied via correctionlib -- the bundled
# pickle factories only cover 2022/2023 and rebuilding them needs internet
# access to JECDatabase. Source is the CAT Summer24 bundle (V5 compound JEC +
# JRV2 JER), bundled in corrections/ with a cvmfs fallback; see
# corrections/README.md. jsonpog-integration is NOT used for 2024: its snapshot
# ships only a V1 JEC and a Summer23BPix JRV1 JER stand-in.
JEC_2024_MC_COMPOUND = "Summer24Prompt24_V5_MC_L1L2L3Res_AK4PFPuppi"
JER_2024_MC_RESO = "Summer24Prompt24_JRV2_MC_PtResolution_AK4PFPuppi"
JER_2024_MC_SF = "Summer24Prompt24_JRV2_MC_ScaleFactor_AK4PFPuppi"
JER_2024_SMEAR = "JERSmear"

# Bundled-first, cvmfs-fallback sources for the 2024 jet corrections.
JEC_JER_2024_BUNDLED = package_path + "/corrections/2024_jet_jerc.json.gz"
JERSMEAR_2024_BUNDLED = package_path + "/corrections/jer_smear.json.gz"
# CAT metadata tree (has the real Summer24 V5 JEC + JRV2 JER; jsonpog does not).
_CAT_JME = "/cvmfs/cms-griddata.cern.ch/cat/metadata/JME"
JEC_JER_2024_CVMFS = (
    f"{_CAT_JME}/Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15/latest/jet_jerc.json.gz"
)
JERSMEAR_2024_CVMFS = f"{_CAT_JME}/JER-Smearing/latest/jer_smear.json.gz"


def _load_correctionset_bundled_first(bundled: str, cvmfs: str, what: str):
    """Load a correctionlib CorrectionSet, preferring the bundled repo copy and
    falling back to the cvmfs (CAT) path. Returns None (with a warning) if
    neither exists, so JEC/JER degrade gracefully rather than crashing."""
    for path, tag in ((bundled, "bundled"), (cvmfs, "cvmfs")):
        if pathlib.Path(path).is_file():
            print(f"{what}: using {tag} {path}")
            return correctionlib.CorrectionSet.from_file(path)
    print(f"WARNING: {what} not found (bundled or cvmfs); 2024 JER disabled.")
    return None


class JECs:
    def __init__(self, year):
        self.year = year
        if year in ["2022", "2022EE", "2023", "2023BPix"]:
            if sys.version_info[1] < 11:  # noqa: YTT203
                jec_compiled = package_path + "/corrections/jec_compiled.pkl.gz"
            else:
                # need new version for python 3.11
                jec_compiled = package_path + "/corrections/jec_compiled_py311.pkl.gz"

        elif year in ["2016", "2016APV", "2017", "2018"]:
            jec_compiled = package_path + "/corrections/jec_compiled_run2.pkl.gz"
        else:
            jec_compiled = None

        self.jet_factory = {}
        self.met_factory = None
        self.correctionlib_cset = None
        self.jersmear_cset = None

        if year == "2024":
            # 2024 uses correctionlib (no pickle factories). Load the compound
            # JEC + JRV2 JER (one file) and the generic JERSmear formula,
            # preferring the bundled repo copies over the cvmfs CAT path.
            self.correctionlib_cset = _load_correctionset_bundled_first(
                JEC_JER_2024_BUNDLED, JEC_JER_2024_CVMFS, "JEC/JER 2024 (V5 + JRV2)"
            )
            self.jersmear_cset = _load_correctionset_bundled_first(
                JERSMEAR_2024_BUNDLED, JERSMEAR_2024_CVMFS, "JERSmear 2024"
            )
            print(
                f"JECs 2024: compound {JEC_2024_MC_COMPOUND}; "
                f"JER {JER_2024_MC_RESO} (nominal smearing)"
            )

        print(jec_compiled)
        if jec_compiled is not None:
            with gzip.open(jec_compiled, "rb") as filehandler:
                jmestuff = pickle.load(filehandler)

            self.jet_factory["ak4"] = jmestuff["jet_factory"]
            self.jet_factory["ak8"] = jmestuff["fatjet_factory"]
            self.met_factory = jmestuff["met_factory"]

    def _apply_correctionlib_jec_2024(
        self, jets: JetArray, isData: bool, fatjets: bool, event: ak.Array | None = None
    ):
        """
        Apply the Summer24 compound JEC (V5 L1L2L3Res) on raw jet pT/mass via
        correctionlib, then nominal JRV2 JER smearing on the corrected pT.
        MC + AK4 only. No JES/JER variations (jec_shifted_vars is not consumed
        by the Vcb skimmer).
        """
        if isData:
            print("WARNING: 2024 data JECs not implemented; keeping NanoAOD jet energies.")
            return jets, None
        if fatjets:
            print("WARNING: 2024 AK8 JECs not implemented; keeping NanoAOD fatjet energies.")
            return jets, None

        corr = self.correctionlib_cset.compound[JEC_2024_MC_COMPOUND]
        j, nj = ak.flatten(jets), ak.num(jets)
        factor = corr.evaluate(
            np.array(j.area, dtype=np.float64),
            np.array(j.eta, dtype=np.float64),
            np.array(j.pt_raw, dtype=np.float64),
            np.array(j.event_rho, dtype=np.float64),
            np.array(j.phi, dtype=np.float64),
        )
        # float32 keeps jet pt/mass dtypes identical to the 2022/2023 pickle
        # factories (e.g. the summed `ht` branch stays Float_t)
        factor = ak.unflatten(ak.values_astype(factor, np.float32), nj)

        jets["pt"] = jets.pt_raw * factor
        jets["mass"] = jets.mass_raw * factor

        # JER smearing (nominal) on the JEC-corrected pT; fold into `factor` so
        # rawFactor stays consistent with the final energies.
        smear = self._jer_smear_2024(jets, event)
        if smear is not None:
            jets["pt"] = jets.pt * smear
            jets["mass"] = jets.mass * smear
            factor = factor * smear

        # rawFactor must be consistent with the recorrected energies. Guard the
        # division: a jet whose (rare) stochastic JER smear clamps to 0 has
        # factor == 0 and is dropped by the pt > 15 selection, but must stay
        # finite here; all realistic jets take the plain 1 - 1/factor branch.
        safe = factor > 0
        jets["rawFactor"] = ak.where(safe, 1 - 1 / ak.where(safe, factor, 1.0), 0.0)

        return jets, None

    def _jer_smear_2024(self, jets: JetArray, event: ak.Array | None):
        """
        Nominal Summer24 JRV2 JER smear factor per jet (jagged float32), applied
        on the JEC-corrected pT, or None if inputs are unavailable (smearing
        skipped). Hybrid method: the JERSmear correction branches on GenPt
        (>= 0 -> scaling, -1 -> stochastic with a deterministic hashprng seed);
        the gen match (dR < 0.2 and the 3-sigma window) is decided here.
        """
        if self.correctionlib_cset is None or self.jersmear_cset is None or event is None:
            return None

        nj = ak.num(jets)
        j = ak.flatten(jets)
        eta = np.array(j.eta, dtype=np.float64)
        pt = np.array(j.pt, dtype=np.float64)  # JEC-corrected
        rho = np.array(j.event_rho, dtype=np.float64)

        reso = self.correctionlib_cset[JER_2024_MC_RESO].evaluate(eta, pt, rho)
        sf = self.correctionlib_cset[JER_2024_MC_SF].evaluate(eta, pt)

        # hybrid gen match: pt_gen (0 if unmatched) and dr_gen were stored in
        # _add_jec_variables. Pass the matched gen pT only inside dR < 0.2 and the
        # 3-sigma window; otherwise the -1 sentinel selects stochastic smearing.
        genpt = ak.values_astype(jets.pt_gen, np.float64)
        reso_j = ak.unflatten(reso, nj)
        matched = (
            (genpt > 0)
            & (jets.dr_gen < 0.2)
            & (np.abs(jets.pt - genpt) < 3.0 * reso_j * jets.pt)
        )
        genpt_in = np.array(ak.flatten(ak.where(matched, genpt, -1.0)), dtype=np.float64)

        # deterministic entropy source: event number broadcast to each jet
        evid = np.array(
            ak.flatten(ak.broadcast_arrays(ak.values_astype(event, np.int64), jets.pt)[0]),
            dtype=np.int64,
        )

        smear = self.jersmear_cset[JER_2024_SMEAR].evaluate(
            pt, eta, genpt_in, rho, evid, reso, sf
        )
        smear = np.maximum(smear, 0.0)
        return ak.unflatten(ak.values_astype(smear, np.float32), nj)

    def _add_jec_variables(self, jets: JetArray, event_rho: ak.Array, isData: bool) -> JetArray:
        """add variables needed for JECs"""
        jets["pt_raw"] = (1 - jets.rawFactor) * jets.pt
        jets["mass_raw"] = (1 - jets.rawFactor) * jets.mass
        jets["event_rho"] = ak.broadcast_arrays(event_rho, jets.pt)[0]
        if not isData:
            # gen pT needed for smearing
            gen = jets.matched_gen
            jets["pt_gen"] = ak.values_astype(ak.fill_none(gen.pt, 0), np.float32)
            if self.year == "2024":
                # reco-gen dR for the 2024 JER hybrid match. Captured here (before
                # JEC modifies pt/mass) while matched_gen resolves cleanly; JEC
                # leaves the jet direction unchanged, so dR is JEC-invariant.
                jets["dr_gen"] = ak.values_astype(
                    ak.fill_none(jets.delta_r(gen), 999.0), np.float32
                )
        return jets

    def get_jec_jets(
        self,
        events: NanoEventsArray,
        jets: FatJetArray,
        year: str,
        isData: bool = False,
        jecs: dict[str, str] | None = None,
        fatjets: bool = True,
        applyData: bool = False,
        dataset: str | None = None,
        nano_version: str = "v12",
    ) -> FatJetArray:
        """
        If ``jecs`` is not None, returns the shifted values of variables are affected by JECs.
        """

        rho = (
            events.Rho.fixedGridRhoFastjetAll
            if "Rho" in events.fields
            else events.fixedGridRhoFastjetAll
        )
        jets = self._add_jec_variables(jets, rho, isData)

        apply_jecs = ak.any(jets.pt) if (applyData or not isData) else False
        if "v12" not in nano_version:
            apply_jecs = False
        if not apply_jecs:
            return jets, None

        # 2024: no pickle factories; apply the Summer24 JEC + JER via correctionlib.
        if self.correctionlib_cset is not None:
            return self._apply_correctionlib_jec_2024(jets, isData, fatjets, event=events.event)

        jec_vars = ["pt"]  # variables we are saving that are affected by JECs
        jet_factory_str = "ak4"
        if fatjets:
            jet_factory_str = "ak8"

        if self.jet_factory[jet_factory_str] is None:
            print("No factory available")
            return jets, None

        import cachetools

        jec_cache = cachetools.Cache(np.inf)

        if isData:
            if year == "2022":
                corr_key = f"{year}_runCD"
            elif year == "2022EE" and "Run2022E" in dataset:
                corr_key = f"{year}_runE"
            elif year == "2022EE" and "Run2022F" in dataset:
                corr_key = f"{year}_runF"
            elif year == "2022EE" and "Run2022G" in dataset:
                corr_key = f"{year}_runG"
            elif year == "2023":
                corr_key = "2023_runCv4" if "Run2023Cv4" in dataset else "2023_runCv123"
            elif year == "2023BPix":
                corr_key = "2023BPix_runD"
            else:
                print(dataset, year)
                print("warning, no valid dataset, JECs won't be applied to data")
                applyData = False
        else:
            corr_key = f"{year}mc"

        # fatjet_factory.build gives an error if there are no jets in event
        if apply_jecs:
            jets = self.jet_factory[jet_factory_str][corr_key].build(jets, jec_cache)

        # return only jets if no variations are given
        if jecs is None or isData:
            return jets, None

        jec_shifted_vars = {}
        for jec_var in jec_vars:
            tdict = {"": jets[jec_var]}
            if apply_jecs:
                for key, shift in jecs.items():
                    for var in ["up", "down"]:
                        if shift in ak.fields(jets):
                            tdict[f"{key}_{var}"] = jets[shift][var][jec_var]
            jec_shifted_vars[jec_var] = tdict

        return jets, jec_shifted_vars


def get_jmsr(
    fatjets: FatJetArray,
    num_jets: int,
    jmsr_vars: list[str],
    jms_values: dict,
    jmr_values: dict,
    isData: bool = False,
    seed: int = 42,
) -> dict:
    """Calculates post JMS/R masses and shifts"""

    jmsr_shifted_vars = {}

    for mkey in jmsr_vars:
        tdict = {}

        mass = pad_val(fatjets[mkey], num_jets, axis=1)
        jms = jms_values[mkey]
        jmr = jmr_values[mkey]

        if isData:
            tdict[""] = mass
        else:
            rng = np.random.default_rng(seed)
            smearing = rng.normal(size=mass.shape)
            # scale to JMR nom, down, up (minimum at 0)
            jmr_nom, jmr_down, jmr_up = ((smearing * max(jmr[i] - 1, 0) + 1) for i in range(3))
            jms_nom, jms_down, jms_up = jms

            corr_mass_JMRUp = random.gauss(0.0, jmr[2] - 1.0)
            corr_mass = max(jmr[0] - 1.0, 0.0) / (jmr[2] - 1.0) * corr_mass_JMRUp

            mass_jms = mass * jms_nom
            mass_jmr = mass * jmr_nom

            tdict[""] = mass * jms_nom * (1.0 + corr_mass)
            tdict["JMS_down"] = mass_jmr * jms_down
            tdict["JMS_up"] = mass_jmr * jms_up
            tdict["JMR_down"] = mass_jms * jmr_down
            tdict["JMR_up"] = mass_jms * jmr_up

        jmsr_shifted_vars[mkey] = tdict

    return jmsr_shifted_vars


# Jet Veto Maps
# the JERC group recommends ALL analyses use these maps, as the JECs are derived excluding these zones.
# apply to both Data and MC
# https://cms-talk.web.cern.ch/t/jet-veto-maps-for-run3-data/18444?u=anmalara
# https://cms-talk.web.cern.ch/t/jes-for-2022-re-reco-cde-and-prompt-fg/32873
def get_jetveto_event(jets: JetArray, year: str):
    """
    Get event selection that rejects events with jets in the veto map
    """

    # correction: Non-zero value for (eta, phi) indicates that the region is vetoed
    cset = correctionlib.CorrectionSet.from_file(get_pog_json("jetveto", year))
    j, nj = ak.flatten(jets), ak.num(jets)

    def get_veto(j, nj, csetstr):
        j_phi = np.clip(np.array(j.phi), -3.1415, 3.1415)
        j_eta = np.clip(np.array(j.eta), -4.7, 4.7)
        veto = cset[csetstr].evaluate("jetvetomap", j_eta, j_phi)
        return ak.unflatten(veto, nj)

    corr_str = {
        "2022": "Summer22_23Sep2023_RunCD_V1",
        "2022EE": "Summer22EE_23Sep2023_RunEFG_V1",
        "2023": "Summer23Prompt23_RunC_V1",
        "2023BPix": "Summer23BPixPrompt23_RunD_V1",
        "2024": "Summer24Prompt24_RunBCDEFGHI_V1",  # verified on cvmfs jsonpog-integration
    }[year]

    jet_veto = get_veto(j, nj, corr_str) > 0

    event_sel = ~(ak.any((jets.pt > 15) & jet_veto, axis=1))
    return event_sel
