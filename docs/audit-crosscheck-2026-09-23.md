# Cross-check of the 2024 MC audit — 23 September 2026

**27 October follow-up:** the isolated implementation described in
[the realignment record](skim-realignment-2026-10-27.md) closes PDF information
loss (finding 6), electron trigger matching (7), extra-lepton information (N1,
by recording rather than applying the veto), and unclustered-MET output (N5).
The [weight follow-up](weight-realignment-2026-10-27.md) removes PU/LHE clipping
and resolves N3 by recording and checking the shower muR convention.
The [current readiness record](cms-readiness-2026-10-27.md) covers the MUO
uncertainty correction and pinned selection payloads. N7's ordering explanation
is corrected: equal Jet/JetQk lengths do not guarantee correspondence, and the
runtime mapping still relies on a production-specific assumption. Unsupported
2024 collision-data input now fails explicitly. Historical evidence below is
retained; current limitations are listed in the readiness record.
The [top-pT follow-up](top-pt-normalization-2026-10-27.md) closes the missing
normalization-information item and distinguishes raw input counts from the
legacy generator-weight sum named `nevents`.

This checks the claims in [the 2024 MC audit](audit-2024-mc-2026-09-11.md)
against the code at `1e1b0d8`, the CVMFS payloads, the test fixture, both local
analysis notes, and the supplied POG material. The reference throughout is CMS
convention: POG recommendations first, then the directly relevant analysis
[AN-25-214](/isilon/export/home/jhuan166/Vcb/References/AN-25-214.pdf)
(2024 |Vcb|, v5), then [AN-25-050](/isilon/export/home/jhuan166/Vcb/References/AN-25-050.pdf)
(TOP-25-018, Run 3). The working tree also contained uncommitted edits to
documentation only. This review did not change any code.

## Bottom line

- **The audit's nine findings hold up.** Every number I re-derived matched
  exactly. The luminosity, muon, JES/JER/electron and eta-guard
  implementations match the POG recipes.
- **The audit missed four real issues.**
  - The skim has no second-lepton veto and does not save the loose leptons
    needed to apply one later.
  - The PS-weight "Up" label means *less* ISR/FSR in this NanoAOD.
  - The ttbar W branching fractions follow neither PDG nor AN-25-214.
  - The unclustered-MET variation used by both reference notes cannot be
    rebuilt from the skim.
- **The audit's cross-section and JetQk statements need correction.** It
  misstated how the signal normalization differs from AN-25-214. JetQk
  alignment is now verified per jet, but the code's explanation for why it
  holds is wrong.
- **Collision data cannot be processed yet.** There is no golden-JSON lumi
  mask and no 2024 data JEC. The audit scoped this out as MC-only.
- **Part of the audit's failure-handling row is out of date.** Missing 2024
  JEC/JER payloads now raise an error instead of being silently skipped.

## What was re-run

| Check | Result |
| --- | --- |
| Unit tests and lint | 227 passed, 18 subtests; `ruff` clean. The two `B905` errors the audit reported are gone. |
| Fresh nominal skim of the fixture | 59,537 events, 741 columns. After matching on (run, lumi, event), every value equals the existing baseline output: 24,925 electron and 34,612 muon events. Source files edited after the baselines were written did not change the output. |
| `electron_scaleUp` pass | 59,558 events: **21 enter, 0 leave**, exactly the audit's table |
| `jes_FlavorQCDUp` pass | 59,502 events: 0 enter, 35 leave (extra jets crossing the veto map). Leading-jet pT +0.76% on average; median \|ΔMET\| 0.63 GeV |
| Payload identity | JEC/JER, PU, muon S&S and veto map are identical to CAT `latest`. The jsonpog and CAT veto maps are identical. All 26 CAT-snapshot payloads show no drift today. |
| Public pages | [DP-2026/003](https://twiki.cern.ch/twiki/bin/view/CMSPublic/LumiCalibration2024pp): 124.0 fb⁻¹ *delivered*, 1.6%. [DP-2026-101 r5](https://twiki.cern.ch/twiki/bin/view/CMSPublic/DP2026101): 109.82 fb⁻¹ for C–I. [TOPLHCWG](https://twiki.cern.ch/twiki/bin/view/LHCPhysics/TtbarNNLO): 923.6 +22.6/−33.4 ±22.8 pb (PDF4LHC21). [PDG W](https://pdglive.lbl.gov/Particle.action?init=0&node=S043&home=sumtabG): e/μ/τ 10.71/10.63/11.38%, hadrons 67.41%. PDG 2025 CKM review: \|Vcb\| = (41.1 ± 1.2)×10⁻³. |

## Verdict on each audit finding

| # | Audit claim | Verdict | Independent evidence |
| --- | --- | --- | --- |
| 1 | Use 109.82 fb⁻¹ for C–I, not 124.0 | **Confirmed** | AN-25-214 Table 1 matches. The CVMFS pileup JSONs, masked with the latest golden JSON, sum to **109.81 fb⁻¹**, era by era within 0.01 fb⁻¹ (C 7.252 … I 11.558). This is independent corroboration. The 102 missing lumisections are reproduced. Era B contributes only 0.132 fb⁻¹, so it does *not* explain the LumiPOG example's 110.11. |
| 2 | Muon scale/resolution for 26–200 GeV | **Confirmed** | Formulas match the MUO text and the CVMFS helpers. The Python `pt_resol_var` uses nominal `k_mc`, the C++ helper uses residual K, and both read only `stat`. The payload equals the bug-fixed 2026-04-28 release, which is also `latest`. AN-25-214 still uses the pre-fix 2025-10-17 release, worth telling its authors. Saved-muon statuses 34,423/83/330 are reproduced, as are 3 muons above 500 GeV (maximum 656.26 GeV). High-pT GE and closure remain open. |
| 3 | Full JES/JER passes, correlated MET, entering electrons | **Confirmed** | The 27 sources in quadrature reproduce the V5 `Total` to ≤2.3×10⁻⁴ on a 165-point grid; `AbsoluteSample` and `AbsoluteFlavMap` are zero. The JERC FAQ confirms fractional `SFUncertainty` and full reselection per variation. See N5 and N8 for gaps in the nuisance model. |
| 4 | PU weights capped at 10 | **Confirmed** | The payload maximum is 73.45 (nominal) and 489.9 (up), both at nTrueInt 74. On the fixture, 12 nominal and 935 up weights are capped; the denominators move by −0.031% and −1.90%. The effect on nominal yields is negligible, but the PU-up template changes. |
| 5 | LHE scale ratios clipped to [0, 4] | **Confirmed** | 536 events, 852 negative entries and 91 entries above 4. The index choice matches the branch documentation. |
| 6 | ttbar PDF/αS discarded | **Confirmed** | Only HH datasets save PDF weights. LHAPDF metadata confirms `symmhessian+as` with members 101/102 at αS = 0.116/0.120. AN-25-214's Hessian paragraph is blue (PDF p. 58), which the note defines as not yet implemented. The 5% cap would alter 27,380 entries in 2,377 events, reproduced. |
| 7 | Electron match should use bit 18 | **Confirmed; low impact** | Exactly 1 of 24,925 electron-channel events lacks a bit-18 match. The fix is correct, but by impact this is P3. |
| 8 | MUO impact-parameter and isolation-environment studies | **Confirmed; understated** | The quoted MUO text is verbatim. The audit does not say where the cuts came from; see N2. |
| 9 | Type-1 \|η\| < 5.2 guard | **Confirmed** | The mask is at [corrections.py:613](../src/boostedhh/processors/corrections.py:613). The fixture's maximum \|η\| is 5.10059 (`Jet`) and 5.10254 (`CorrT1METJet`). |

Coverage-table rows also confirmed: exactly the eight MET filters, identical to
both analysis notes (208,677 of 208,780 pass). The jet-veto recipe matches the
JERC Run-3 text: pT > 15, `tightLepVeto`, EM fraction < 0.9, event rejection.
The EGM S&S formulas match the June 2026 page, including the ~10 GeV validity
caution. The JEC compound's input order is `JetA, JetEta, JetPt, Rho, JetPhi`,
as called. The lepton-SF keys exist in the bundled payloads.

## Corrections to the audit text

- **Cross sections.** The audit says exact note normalization would multiply
  the signal by `(0.0411/0.0410)² ≈ 1.0049`. That goes the wrong way.
  AN-25-214 Table 2 lists **0.342 pb** for `TTtoLNuCB` and **407.4 pb** for
  `TTtoLNu2Q`; the processor uses 0.3448 and 410.28 pb, which are 0.8% and
  0.7% higher. The audit's factor would widen the signal gap to 1.3%. The
  difference comes mainly from the W branching fractions; see N4.
- **JetQk alignment.** The alignment is now verified per jet; see N7. The
  docstring's explanation for it is incorrect.
- **Failure handling is partly out of date.** Since `1e1b0d8`, a missing 2024
  JEC/JER payload or a non-`v12` label raises an error. Two things still
  apply: missing lepton-SF payloads are skipped with only a warning, and the
  veto map reads the mutable jsonpog path.
- **ISR/FSR.** The audit says the labels "agree with the implemented indices".
  The indices do, but the up/down meaning is inverted; see N3.

## New findings

**N1 (P2): no second-lepton veto, and the needed leptons are not saved.**
AN-25-214 §4.2 requires exactly one tight lepton and vetoes additional loose
leptons with pT > 15 GeV and |η| < 2.4. The loose definition is WP90 for
electrons and `tightId`+`pfRelIso04_all < 0.25` for muons. The note's Table 9
gives a promptMVA variant. AN-25-050 applies the same kind of veto. The skim
allows extra leptons and saves only its own good leptons (pT > 20 GeV,
muon isolation < 0.15). On the fixture, **1,104 of 59,537 selected events (1.85%,
or 1.93% weighted)** contain an extra AN-style loose lepton. **659** of them
cannot be identified from any saved field. The fraction will be much larger in
dileptonic ttbar. Either apply the veto, or save veto-lepton counts and
kinematics.

**N2 (resolved 2026-09-23): lepton impact-parameter cuts came from H→ττ
conventions.** Both explicit cuts were removed in `30745a5`, following
AN-25-214; see the
[history entry](history.md#2026-09-23--lepton-impact-parameter-cuts-removed).
The original finding follows.
Both flavors use `|dxy| < 0.045` and `|dz| < 0.2` cm
([objects.py:418](../src/vcb/processors/objects.py:418),
[objects.py:465](../src/vcb/processors/objects.py:465)). These are the
H→ττ values ([CMS H→ττ observation](https://arxiv.org/pdf/1708.00373)),
inherited from the bbττ code this repo descends from. EGM does not recommend
them, and its SF guide says special IP thresholds call for re-measuring SFs.
MUO says IP cuts tighter than the Tight ID's own `|dxy| < 0.2`, `|dz| < 0.5` cm
need a dedicated study (audit finding 8). AN-25-214 applies no extra IP cut beyond its IDs. AN-25-050 uses
0.05/0.1 cm plus `sip3d < 8`. Choose one reference convention; aligning with
AN-25-214 also removes the need for the extra muon IP study. A smaller
difference: the electron acceptance is track |η| < 2.5, while AN-25-214 uses
|η_SC| < 2.4.

**N3 (P3): the PS-weight "Up" label means less radiation here.** Both the
fixture and a `TTtoLNu2Q` production file document `PSWeight` as
`[0] isr.murfac=2.0; [1] fsr.murfac=2.0; [2] isr.murfac=0.5; [3] fsr.murfac=0.5`.
The fixture confirms the physics:

- Index 0 lowers ⟨nGenJet(pT > 30 GeV, |η| < 2.4)⟩ from 3.9560 to 3.9445, and
  ⟨pT(tt̄)⟩ from 68.10 to 67.84 GeV.
- Index 2 raises them to 3.9706 and 68.43 GeV.

The code's comment "ISR=2" comes from Run-2 NanoAOD. There, slot 0 held
`isrDefHi` (μR × 0.5, more radiation). CMSSW's name parser
([GenWeightsTableProducer.cc:1030](/isilon/export/home/jhuan166/Vcb/CMSSW_15_1_0_patch4/src/PhysicsTools/NanoAOD/plugins/GenWeightsTableProducer.cc:1030))
now puts `2.0` into that same slot. So `ISRPartonShowerUp` and
`FSRPartonShowerUp` here mean μR × 2. Nominal results are unaffected. Before
correlating with other samples or years, or comparing pulls, rename by μR
factor or swap the labels.

**N4 (P3): the ttbar W branching fractions follow neither PDG nor AN-25-214.**
[xsecs.py:89](../src/boostedhh/xsecs.py:89) uses 1/3 for leptonic and 2/3 for
hadronic W decays. This ignores the file's own `BR_WLNU = 0.324` and
`BR_WQQ = 0.676`. AN-25-214 uses the PDG 2025 values, which the numbers below
reproduce exactly.

| Sample | Processor | PDG 2025 | AN-25-214 |
| --- | ---: | ---: | ---: |
| `TTtoLNu2Q` | 410.28 pb | 407.43 pb | 407.4 pb |
| `TTto2L2Nu` | 102.4 pb | 98.88 pb | 98.88 pb |
| `TTtoLNuCB` | 0.3448 pb | 0.3441 pb | 0.342 pb |

The PDG 2025 column uses BR(ℓν) = 0.3272 (the sum over e, μ, τ) and
BR(had) = 0.6741; its `TTtoLNuCB` value also uses \|Vcb\| = 0.0411. AN-25-214's
own 0.342 pb matches \|Vcb\| = 0.0410, not the 0.0411 stated in its text. Use
the PDG values and \|Vcb\| = 0.0411, and record which convention was chosen.

**N5 (P2, before the next reprocessing): the unclustered-MET variation cannot
be rebuilt from the skim.** JMAR calls this term optional. Both reference notes
nevertheless include it: AN-25-214 Table 15 and AN-25-050 §7.1. The recipe
needs `PuppiMET_{pt,phi}Unclustered{Up,Down}`, and the skim does not save them.
Saving those four fields costs almost nothing. The skim has no MET cut, so a
downstream MET > 20 GeV cut can then be varied.

**N6 (P1 before any collision data): the data path is incomplete.** Three pieces
are missing:

- There is no golden-JSON lumi mask.
- 2024 data jets keep their NanoAOD JEC.
  [corrections.py:369](../src/boostedhh/processors/corrections.py:369) says so
  explicitly, even though the bundled payload already contains
  `Summer24Prompt24_V5_DATA_L1L2L3Res_AK4PFPuppi` with a `run` input.
- Data MET is not rebuilt.

Data and MC jets would therefore carry different JEC versions. The calibration
needs data, so this blocks it.

**N7 (information): JetQk alignment is verified, but the stated reason is
wrong.** The docstring of `attach_jet_charge` says `updatedPatJets` recomputes
the JEC without sorting. In CMSSW, however, `updatedPatJets` defaults to
`sort = True` (`jetUpdater_cfi.py:30`), and NanoAOD's `updatedJetsPuppi` does
not override that setting. `JetQk`, by contrast, reads `slimmedJetsPuppi` in
MiniAOD order. The positional match therefore holds only if the NanoAOD JEC
leaves the jet order unchanged. Direct per-jet tests show that it does:

- In the fixture, **0 of 73,775** jets with \|η\| > 3.5 carry a real charge.
  These jets have no tracks, so a correct match must give a sentinel.
- In the fixture, **3 of 1,013,729** jets with more than 10 GeV of
  charged-hadron energy carry a sentinel.
- In the `TTtoLNu2Q` file, the second test gives **1 of 134,661**.
- `nJetQk == nJet + nCorrT1METJet` holds in every event of both files.

Correct the docstring and add the second test as a guard in
`validate_processed`. The upstream fix is still to use `src=finalJetsPuppi`.

**N8 (recommendation): flavour-dependent JES.** For a b/c and charge-tagger
calibration, consider the TOP practice in AN-25-050 §7.1. It replaces
`FlavorQCD` with `FlavorPure{Bottom,Charm,Quark,Gluon}`, applied by jet
flavour. The V5 payload provides all four. At 30 GeV in the central detector,
`FlavorQCD` is 1.6%, compared with −0.5% for b jets and −0.2% for c jets.

## Minor drift

- [electron_ss.py:52](../src/vcb/processors/electron_ss.py:52) says ~20 GeV;
  EGM now says ~10 GeV.
- The "NanoAOD v12" trigger-bit comments in
  [objects.py:387](../src/vcb/processors/objects.py:387) are stale for v15.
- The audit's line references to `vcbSkimmer.py` have drifted.
- `~/cat-snapshot/check-drift.sh` also scans `.git/`, which produces harmless
  "GONE" lines.

## Suggested order

1. **Before any data:** complete N6.
2. **In one MC reprocessing, to avoid a second:**
   - Save the PDF/αS members and their all-event sums (finding 6).
   - Remove or explicitly justify the PU and LHE clipping (4, 5).
   - Apply the second-lepton veto or save the veto leptons (N1).
   - ~~Settle the IP cuts (N2).~~ Done: no cut beyond the IDs, as in AN-25-214.
   - Switch the electron match to bit 18 (7).
   - Save the unclustered-MET vectors (N5).
   - Decide on flavour-dependent JES passes (N8).
3. **Cheap, no reprocessing needed:** N3 labels, N4 branching fractions, and
   the N7 docstring and guard.

## Not verified

- Pages behind CERN SSO: JetID13p6TeV, TopPtReweighting/TopSystematics, BTV 2024
  SFs and the MUO wiki.
- The GE-table transcription.
- The remaining 62 variation passes.
- The audit's muon impact-parameter counts and electron energy-error ratios.
- Any production output beyond the fixture and one `TTtoLNu2Q` file.
