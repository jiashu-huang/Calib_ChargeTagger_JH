"""
Common variables

Authors: Raghav Kansal, Cristina Suarez

VENDORED + TRIMMED for Calib_ChargeTagger_JH: the HH sample dictionaries
(samples_run3*, samples_2018, bbtt_sigs, sig_keys*, syst_keys, jmsr_values,
ttbarsfs/txbbsfs tables) are dropped; only the symbols imported by
boostedhh.utils / boostedhh.run_utils / vcb are kept. See VENDORED.md.
"""

from __future__ import annotations

years = ["2022", "2022EE", "2023", "2023BPix"]

# in pb^-1
LUMI = {
    "2022": 7971.4,
    "2022EE": 26337.0,
    "2022All": 34308.0,
    "2023": 17650.0,
    "2023BPix": 9451.0,
    "2023All": 27101.0,
    "2022-2023": 61409.0,
    "2018": 59830.0,
    "2017": 41480.0,
    "2016": 36330.0,
    "Run2": 137640.0,
}


DATA_SAMPLES = ["JetHT", "JetMET", "Muon", "EGamma", "Tau"]

data_key = "data"
qcd_key = "qcd"

# kept for boostedhh.utils.combine_hbb_bgs
hbb_bg_keys = ["gghtobb", "vbfhtobb", "vhtobb", "tthtobb", "novhhtobb"]

norm_preserving_weights = ["genweight", "pileup", "ISRPartonShower", "FSRPartonShower"]

jecs = {
    # "JES": "JES",
    "JER": "JER",
}

jec_shifts = []
for key in jecs:
    for shift in ["up", "down"]:
        jec_shifts.append(f"{key}_{shift}")

jmsr = {
    "JMS": "JMS",
    "JMR": "JMR",
}

jmsr_shifts = []
for key in jmsr:
    for shift in ["up", "down"]:
        jmsr_shifts.append(f"{key}_{shift}")

# variables affected by JECs
jec_vars = [
    "bbFatJetPt",
    "VBFJetPt",
    "bdt_score",
    "bdt_score_vbf",
    "HHPt",
    "HHeta",
    "HHmass",
    "H1Pt",
    "H2Pt",
    "H1Pt_HHmass",
    "H2Pt_HHmass",
    "H1Pt/H2Pt",
    "VBFjjMass",
    "VBFjjDeltaEta",
    "Category",
]

# variables affected by JMS/JMR
jmsr_vars = [
    "bbFatJetPNetMassLegacy",
    "bdt_score",
    "bdt_score_vbf",
    "HHmass",
    "H1Pt_HHmass",
    "H2Pt_HHmass",
    "H1Mass",
    "H2Mass",
    "H1PNetMass",
    "H2PNetMass",
    "Category",
]
