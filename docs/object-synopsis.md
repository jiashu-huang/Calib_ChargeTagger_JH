# Object processing synopsis

This describes the current **2024 MC** processing of `TTtoLNu2Q` and
`TTtoLNuCB` in [`vcbSkimmer.py`](../src/vcb/processors/vcbSkimmer.py), including
the current MET corrections. The output is a skimmed ROOT `Events` tree with
fixed object slots. The [complete branch list](../tests/outfile/test-output-schema.csv)
also includes event metadata, weights, and top/W truth variables.

In the field lists, braces mean alternatives: `Electron{Pt,Eta}{i}` expands to
`ElectronPt0`, `ElectronEta0`, etc. Lepton slots use `i = 0, 1, 2`, reconstructed
jet slots use `j = 0, ..., 9`, and generator jet slots use `k = 0, ..., 24`.
Empty object slots contain `-99999`, except trigger-match flags, which contain
`0`. Counts are measured before slot truncation. Momenta and masses are in GeV,
angles in radians, and impact parameters in cm.

## Electrons

1. Save the input transverse momentum as `pt_raw`. Apply the nominal 2024 EGM
   resolution smearing to every electron's pT before selection. The random draw
   is reproducible from the event identifiers and electron index. Save scale
   up/down and smearing up/down pT values; selections use nominal pT. Eta, phi,
   mass, and charge retain their input values.
2. Keep electrons with `mvaIso_WP90`, pT > 20, |eta| < 2.5, |dz| < 0.2, and
   |dxy| < 0.045. Reject the ECAL gap, 1.444 <= |supercluster eta| < 1.566;
   use `superclusterEta`, or `eta + deltaEtaSC` if that field is absent.
3. Mark an electron as trigger-matched when `HLT_Ele30_WPTight_Gsf` fired,
   pT >= 32, and a trigger electron with filter bit 1 (mask 2) lies within
   delta-R < 0.2.
4. Choose the highest-pT matched electron as the event's trigger lepton only
   if no eligible trigger muon exists. This chosen lepton defines the jet
   overlap removal and lepton scale factors. Every saved event must have a
   chosen trigger lepton; additional good leptons are allowed.
5. Label each good electron by whether it lies within delta-R < 0.2 of the
   generator-level charged lepton directly from the leptonic W decay.
6. Apply reconstruction, identification, and trigger scale factors to the
   chosen trigger electron in the event weight. Electron factors are unity
   when the chosen trigger lepton is a muon.
7. Write the first three good electrons in their surviving input order; the
   collection is not sorted again after smearing. Record the full good-electron
   count in `nElectrons`.

**Output fields**

- Kinematics and charge: `Electron{Pt,Eta,Phi,Mass,charge}{i}`.
- Energy correction records: `Electron{PtRaw,PtScaleUp,PtScaleDown,PtSmearUp,PtSmearDown}{i}`.
- Selection and matching: `ElectronMvaIsoWP90{i}`, `ElectronTrigMatchEGamma{i}`,
  `electronsNumlMatchedTop1{i}`. The last name expands to
  `electronsNumlMatchedTop10`, `electronsNumlMatchedTop11`, and `electronsNumlMatchedTop12`.
- Count: `nElectrons`.
- Chosen lepton, shared with muons:
  `TriggerLepton{Pt,Eta,Phi,Mass,Charge,Flav,Isolation}`.
  `Flav = 11` identifies an electron; its isolation is input `pfRelIso03_all`.
- W-decay lepton truth, shared with muons:
  `GenWLepton{Pt,Eta,Phi,Mass,Charge,Flavor}`.
- Weight records: `single_weight_electron_{reco,id,trigger}`.
  These branches contain the individual factor multiplied by cross section
  times luminosity, **not the bare scale factor**.
- Electron HLT decisions: `HLT_Ele30_WPTight_Gsf`,
  `HLT_Ele23_Ele12_CaloIdL_TrackIdL_IsoVL`.
- Electron-muon HLT decisions, shared with the muon section:
  `HLT_Mu12_TrkIsoVVL_Ele23_CaloIdL_TrackIdL_IsoVL_DZ`,
  `HLT_Mu23_TrkIsoVVL_Ele12_CaloIdL_TrackIdL_IsoVL`,
  `HLT_Mu8_TrkIsoVVL_Ele23_CaloIdL_TrackIdL_IsoVL_DZ`.
  Dilepton HLT decisions are recorded but do not select events; missing optional
  HLT paths are written as `0`.

## Muons

1. Read the input muon four-momenta and charges. The processor applies no
   additional muon momentum scale correction or smearing.
2. Keep muons with `tightId`, `pfRelIso04_all < 0.15`, pT > 20,
   |eta| < 2.4, |dz| < 0.2, and |dxy| < 0.045.
3. Mark a muon as trigger-matched when `HLT_IsoMu24` fired, pT >= 26, and a
   trigger muon with filter bit 3 (mask 8) lies within delta-R < 0.2.
4. Choose the highest-pT matched muon as the event's trigger lepton. An
   eligible muon takes priority over an eligible electron. Use this same
   muon for jet overlap removal and lepton scale factors.
5. Label each good muon by whether it lies within delta-R < 0.2 of the
   generator-level charged lepton directly from the leptonic W decay.
6. Apply identification, isolation, and trigger scale factors to the chosen
   trigger muon in the event weight. Muon factors are unity when the chosen
   trigger lepton is an electron.
7. Write the first three good muons in their surviving input order. Record
   the full good-muon count in `nMuons`.

**Output fields**

- Kinematics and charge: `Muon{Pt,Eta,Phi,Mass,charge}{i}`.
- Isolation and matching: `MuonPfRelIso04All{i}`, `MuonTrigMatchMuon{i}`,
  `muonsNumlMatchedTop1{i}`. The last name expands to
  `muonsNumlMatchedTop10`, `muonsNumlMatchedTop11`, and `muonsNumlMatchedTop12`.
- Count: `nMuons`.
- Chosen lepton: `TriggerLepton{Pt,Eta,Phi,Mass,Charge,Flav,Isolation}`.
  `Flav = 13` identifies a muon; its isolation is input `pfRelIso04_all`.
- W-decay lepton truth: `GenWLepton{Pt,Eta,Phi,Mass,Charge,Flavor}`.
- Weight records: `single_weight_muon_{id,iso,trigger}`. As for electrons,
  these include cross section times luminosity.
- Muon HLT decisions: `HLT_IsoMu24`,
  `HLT_Mu17_TrkIsoVVL_Mu8_TrkIsoVVL_DZ_Mass3p8`, plus the three shared
  electron-muon HLT decisions listed above. The dimuon path does not select events.

## Jets

1. Start with the complete input AK4 PUPPI `Jet` collection. Recover raw pT
   and mass by multiplying the input values by `1 - rawFactor`.
2. Apply Summer24 V5 nominal jet energy corrections (JEC), followed by
   JRV2 nominal jet energy resolution (JER) smearing. JER uses a compatible
   generator jet when available and reproducible stochastic smearing otherwise.
   Update pT, mass, and `rawFactor`; retain eta and phi. Nominal JER is applied
   even when systematic variations are disabled.
3. Save each jet's original input index and attach the two jet charges from
   the corresponding `JetQk` entry. Carry through the input flavour and charge
   tagger scores without recalculating them. Use the complete corrected
   collection for the MET calculation described below.
4. Evaluate the jet-veto map on the uncleaned jets with corrected pT > 15,
   TightLepVeto ID, and `chEmEF + neEmEF < 0.9`. Reject the whole event if any
   such jet lies in a vetoed region.
5. Select analysis jets with corrected pT > 15, |eta| < 4.7, Tight ID, and
   delta-R > 0.4 from the chosen trigger lepton. Recompute jet ID from the
   input energy fractions and multiplicities. Jet overlap removal uses only
   the chosen lepton. Saved jet momenta still include constituent muons.
6. Sort the selected jets by decreasing corrected pT. Set `BTaggable` for
   pT >= 20 and |eta| <= 2.5; this flag does not remove jets. Record the full
   selected-jet count and pT sum as `nJets` and `ht`. The later 20 GeV analysis
   cut is separate; this processor imposes no minimum jet count or b-tag cut.
7. Assign the four ttbar decay partons to the first ten selected jets using
   the closest available parton-jet pair with delta-R < 0.4, without reusing
   either object. Q1 is the down-type W daughter and Q2 the up-type daughter.
   Save their jet-slot indices, with `-1` for an unmatched parton.
8. Write up to ten selected jets and the first 25 input `GenJet` entries.
   Retain each reconstructed jet's matched generator-jet pT and saved index.
   `GenJetIdx = -1` means no input match; `-99999` means an empty jet slot or
   a matched generator jet beyond the 25 saved slots. Record the full generator
   jet count in `nGenJets`.

**Output fields**

- Kinematics and input identity: `ak4Jet{Pt,Eta,Phi,Mass,rawFactor,NanoIdx}{j}`.
- Eligibility and generator matching:
  `ak4Jet{BTaggable,HadronFlavour,PartonFlavour,MatchedGenJetPt,GenJetIdx}{j}`.
- Unified Particle Transformer scores:
  `ak4JetbtagUParTAK4{B,CvB,CvL,CvNotB,QvG}{j}`.
- ParticleNet scores: `ak4JetbtagPNet{B,CvB,CvL,CvNotB,QvG}{j}`.
- Robust Particle Transformer score: `ak4JetbtagRobustParTAK4B{j}`.
- Jet charges: `ak4JetQkCharge05_{j}`, `ak4JetQkCharge10_{j}`.
  Input charge sentinels `-999`, `-998`, and `-997` are preserved.
- Charge tagger scores: `ak4Jet{ParTPosvsAll,ParTNegvsAll,ParTZerovsAll,ParTPosvsNeg}{j}`.
- Additional truth labels: `ak4Jet{PflavCharge,FlavSplit}{j}`.
- Generator jets:
  `GenJet{Pt,Eta,Phi,Mass,HadronFlavour,PartonFlavour,NBHadrons,NCHadrons}{k}`.
- Parton assignments: `Gen{HadB,LepB,HadQ1,HadQ2}JetIdx`.
- Assigned-parton truth: `Gen{HadTopB,LepTopB,Q1,Q2}{Pt,Eta,Phi,Mass}`,
  `GenQ{1,2}PdgId`.
- Counts and event quantities: `nJets`, `nGenJets`, `ht`, `Rho`.
  `Rho` is the input `fixedGridRhoFastjetAll` used for the corrections.

## MET

1. Start from `RawPuppiMET`. Rebuild Type-1 PUPPI MET using the full regular
   jet collection before lepton cleaning, analysis cuts, or output truncation.
   Include `CorrT1METJet`, the separate low-pT jet collection omitted from
   the input `Jet` table; apply the same nominal JEC/JER to these jets.
2. For each contributing collection, reconstruct the muon-subtracted raw jet:
   pT = raw pT times `1 - muonSubtrFactor`, eta = jet eta plus
   `muonSubtrDeltaEta`, and phi = jet phi plus `muonSubtrDeltaPhi`, wrapped
   into [-pi, pi). This subtraction is used only for MET.
3. Evaluate L1 and full JEC using the muon-subtracted pT and direction.
   Multiply the full-correction pT by the jet's nominal JER factor.
   Retain contributions with this corrected pT > 15 and electromagnetic
   fraction < 0.9 (`chEmEF + neEmEF` for regular jets, `EmEF` for auxiliary jets).
4. Subtract the vector sum of `(full JEC + JER pT) - (L1 pT)` from raw MET,
   using the muon-subtracted phi for each jet. Convert the resulting x/y
   components to pT and phi. Auxiliary jets affect MET only; they do not become
   saved analysis jets. Electron energy corrections are not propagated into MET.
5. Require all eight input event-quality flags: `goodVertices`,
   `globalSuperTightHalo2016Filter`, `EcalDeadCellTriggerPrimitiveFilter`,
   `BadPFMuonFilter`, `BadPFMuonDzFilter`, `eeBadScFilter`,
   `ecalBadCalibFilter`, and `hfNoisyHitsFilter`. A missing flag raises an error.
6. Save the corrected MET pT and phi. There is no MET magnitude cut in this
   processor. The raw MET, auxiliary jet collection, individual quality flags,
   and MET uncertainty variations are not written.

**Output fields**

- Reconstructed MET: `METPt`, `METPhi`.
- Associated W-decay neutrino truth: `GenWNeutrino{Pt,Eta,Phi,Mass}`.
  This is the direct W daughter, not the vector sum of all invisible particles.
