# Jet energy resolution (JER)

Date: 2026-07-23

In this `.md` file we list sources of JER information.

## JME POG (Jet and Missing Energy)

```bash
ls /cvmfs/cms-griddata.cern.ch/cat/metadata/JME/
```
yields
```
JER-Smearing                    Run2-2018-UL-NanoAODv9
Run2-2016-EOY17-NanoAODv6       Run3-22CDSep23-Summer22-NanoAODv12
Run2-2016postVFP-UL-NanoAODv15  Run3-22EFGSep23-Summer22EE-NanoAODv12
Run2-2016postVFP-UL-NanoAODv9   Run3-22Prompt-Winter22-NanoAODv12
Run2-2016preVFP-UL-NanoAODv15   Run3-23CSep23-Summer23-NanoAODv12
Run2-2016preVFP-UL-NanoAODv9    Run3-23DSep23-Summer23BPix-NanoAODv12
Run2-2017-EOY17-NanoAODv6       Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15
Run2-2017-UL-NanoAODv15         Run3-24Prompt-Winter24-NanoAODv14
Run2-2017-UL-NanoAODv9          Run3-25Prompt-Summer24-NanoAODv15
Run2-2018-EOY17-NanoAODv6       Run3-25Prompt-Winter25-NanoAODv15
Run2-2018-UL-NanoAODv15         Run3-26Prompt-Summer24-NanoAODv15
```
For our 2024 MC, `JER-Smearing` and `Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15`
are of interest.

### JER-Smearing

```bash
ls /cvmfs/cms-griddata.cern.ch/cat/metadata/JME/JER-Smearing/latest
```
yields
```
changes.md  jer_smear.json.gz
```

### Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15

Folder content:
```bash
ls /cvmfs/cms-griddata.cern.ch/cat/metadata/JME/Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15/latest/
```
yields
```
changes.md  fatJet_jerc.json.gz  jetid.json.gz  jet_jerc.json.gz  jetvetomaps.json.gz
```

`jet_jerc.json.gz` content:
```bash
D=/cvmfs/cms-griddata.cern.ch/cat/metadata/JME/Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15
python3 - "$D/2026-07-16/jet_jerc.json.gz" <<'EOF'
import gzip, json, sys
d = json.load(gzip.open(sys.argv[1], 'rt'))
for c in d.get("corrections", []):
    print("simple  ", c["name"])
for c in d.get("compound_corrections", []):
    print("compound", c["name"])
EOF
```
yields
```
simple   Summer24Prompt24_V5_MC_L1FastJet_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_L2Relative_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_L3Absolute_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_L2L3Residual_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_Regrouped_FlavorQCD_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_Regrouped_RelativeBal_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_Regrouped_HF_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_Regrouped_BBEC1_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_Regrouped_EC2_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_Regrouped_Absolute_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_Regrouped_Absolute_2024_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_Regrouped_HF_2024_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_Regrouped_EC2_2024_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_Regrouped_RelativeSample_2024_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_Regrouped_BBEC1_2024_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_Regrouped_Total_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_AbsoluteStat_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_AbsoluteScale_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_AbsoluteSample_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_AbsoluteFlavMap_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_AbsoluteMPFBias_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_Fragmentation_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_SinglePionECAL_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_SinglePionHCAL_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_FlavorQCD_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_TimePtEta_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_RelativeJEREC1_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_RelativeJEREC2_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_RelativeJERHF_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_RelativePtBB_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_RelativePtEC1_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_RelativePtEC2_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_RelativePtHF_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_RelativeBal_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_RelativeSample_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_RelativeFSR_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_RelativeStatFSR_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_RelativeStatEC_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_RelativeStatHF_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_PileUpDataMC_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_PileUpPtRef_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_PileUpPtBB_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_PileUpPtEC1_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_PileUpPtEC2_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_PileUpPtHF_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_PileUpMuZero_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_PileUpEnvelope_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_SubTotalPileUp_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_SubTotalRelative_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_SubTotalPt_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_SubTotalScale_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_SubTotalAbsolute_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_SubTotalMC_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_Total_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_TotalNoFlavor_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_TotalNoTime_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_TotalNoFlavorNoTime_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_FlavorZJet_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_FlavorPhotonJet_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_FlavorPureGluon_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_FlavorPureQuark_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_FlavorPureCharm_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_FlavorPureBottom_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_CorrelationGroupMPFInSitu_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_CorrelationGroupIntercalibration_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_CorrelationGroupbJES_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_CorrelationGroupFlavor_AK4PFPuppi
simple   Summer24Prompt24_V5_MC_CorrelationGroupUncorrelated_AK4PFPuppi
simple   Summer24Prompt24_V5_DATA_L1FastJet_AK4PFPuppi
simple   Summer24Prompt24_V5_DATA_L2Relative_AK4PFPuppi
simple   Summer24Prompt24_V5_DATA_L3Absolute_AK4PFPuppi
simple   Summer24Prompt24_V5_DATA_L2L3Residual_AK4PFPuppi
simple   Summer24Prompt24_JRV2_MC_PtResolution_AK4PFPuppi
simple   Summer24Prompt24_JRV2_MC_ScaleFactor_AK4PFPuppi
simple   Summer24Prompt24_JRV2_MC_SFUncertainty_AK4PFPuppi
compound Summer24Prompt24_V5_MC_L1L2L3Res_AK4PFPuppi
compound Summer24Prompt24_V5_DATA_L1L2L3Res_AK4PFPuppi
```
Not sure what these are.
