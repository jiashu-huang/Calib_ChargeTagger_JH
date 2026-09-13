# 2024 jet, MET and electron variations — implementation and validation

Finding 3 of the [2024 MC audit](audit-2024-mc-2026-09-11.md) is implemented
for 2024 MC on 13 September 2026: full 27-source JES, global JER up/down,
correlated Type-1 MET, and complete entering-electron passes. The unified
runner also includes the existing muon passes. See [CLI usage](cli.md#kinematic-variation-passes).
The research below used base commit `8cc5a818ce2fe28f0c34ca4c3370746422c1d20e`;
its numerical probes and source hashes remain in
[the research evidence](jet-met-electron-variations-2024-evidence.json).
Production-code validation is recorded separately below. Regional JER,
reduced JES, cross-year correlations and final-fit nuisance constraints are
separate analysis choices.

## Reference implementations and their scope

The strongest new implementation reference is [CMSJMECalculators](https://gitlab.cern.ch/cms-analysis/general/CMSJMECalculators), explicitly cited by [AN-25-050](/isilon/export/home/jhuan166/Vcb/References/AN-25-050.pdf), §4.4, PDF page 27. Its public source was read at revision `32e8eb7af6a06466b811656f7f99e20170b6a0e1`, committed 1 September 2026:

- [JetVariationsCalculator.cc](https://gitlab.cern.ch/cms-analysis/general/CMSJMECalculators/-/blob/32e8eb7af6a06466b811656f7f99e20170b6a0e1/src/JetVariationsCalculator.cc#L131): nominal/up/down JER, optional six-region splitting, and JES variations of jet pT and mass.
- [JetMETVariationsCalculatorBase.cc](https://gitlab.cern.ch/cms-analysis/general/CMSJMECalculators/-/blob/32e8eb7af6a06466b811656f7f99e20170b6a0e1/src/JetMETVariationsCalculatorBase.cc#L198): hybrid matching and the current relative `SFUncertainty` prescription.
- [Type1METVariationsCalculator.cc](https://gitlab.cern.ch/cms-analysis/general/CMSJMECalculators/-/blob/32e8eb7af6a06466b811656f7f99e20170b6a0e1/src/Type1METVariationsCalculator.cc#L168): regular and auxiliary jets, Cartesian MET variations, and correlated JER regions.
- [2024 test configuration](https://gitlab.cern.ch/cms-analysis/general/CMSJMECalculators/-/blob/32e8eb7af6a06466b811656f7f99e20170b6a0e1/tests/test_jmesystcalc.py#L186): explicitly selects Summer24 V5 JEC and JRV2 JER. This is source inspection; this research did not compile or execute the external framework.

The framework is a C++/ROOT implementation useful as a reference for this Coffea processor; its event-selection graph belongs to the calling analysis. Merely obtaining its varied jet arrays would not fix this skimmer's event migrations.

| Analysis note | Relevant treatment | Limit on copying it |
| --- | --- | --- |
| [AN-25-214](/isilon/export/home/jhuan166/Vcb/References/AN-25-214.pdf), §6, PDF page 61 | Re-analyzes events under each JES/JER shift. Describes the reduced JES basis and omits EC2/HF because the analysis does not use forward jets. | This skim retains jets to `abs(eta) < 4.7`, and Type-1 MET includes additional forward activity. Retain EC2/HF. Its page-16 V2 / Summer23BPix JER tag table predates the current 2024 release. No analysis-specific jet implementation repository was identified in the supplied note's links. |
| AN-25-050, §4.4, PDF page 27; §7.1, PDF page 43 | Uses CMSJMECalculators; describes six JER sources, a detailed JES source list, and separate electron scale/smearing uncertainties. | The analysis covers 2022–2023. Its older campaign tags and special regional smearing choices do not establish a 2024 prescription. Its detailed flavor-source treatment is an alternative to the regrouped JES basis, not an extra independent set to add on top of it. |

The supplied [JERC application tutorial](https://gitlab.cern.ch/cms-analysis/jme/jerc-application-tutorial/-/blob/master/JecApplication.cpp), available locally as [JecApplication.cpp](/isilon/export/home/jhuan166/.codex/attachments/cb9cb167-46e5-43ac-b16c-23cc837cb4bf/JecApplication.cpp), independently confirms multiplicative JES uncertainties and `SF * (1 +/- SFUncertainty)` for JER. The supplied [JMAR MET corrections](</isilon/export/home/jhuan166/.codex/attachments/e50840f5-9698-459d-ac2c-eca516d8eeb0/Corrections - CMS JME JMAR.pdf>), PDF pages 6–7, establish mandatory JEC-to-MET propagation with one shared nuisance parameter per source. JER-to-MET propagation is optional in general; this processor already propagates nominal JER, so the proposed varied passes propagate its corresponding JER variations too.

## Supplied JES/JER recommendations: confirmed scope

The user subsequently supplied the current [JES recommendations](</isilon/export/home/jhuan166/.codex/attachments/679bfed6-892d-4188-b26a-dc3c6fe6c02b/Jet Energy Scale - CMS JME JERC.pdf>) (12 pages) and [JER recommendations](</isilon/export/home/jhuan166/.codex/attachments/679bfed6-892d-4188-b26a-dc3c6fe6c02b/Jet Energy Resolution - CMS JME JERC.pdf>) (7 pages), printed 13 September 2026. All pages were read; the general guidance and 2024 tables were also checked as rendered pages. These close the requests for those two pages.

| Confirmed point | Consequence for this plan |
| --- | --- |
| JES PDF page 4 specifies `Summer24Prompt24_V5`; JER PDF page 3 specifies `Summer24Prompt24_JRV2_MC`. | Keep the already bundled V5/JRV2 corrections for 2024 data comparisons. The separate 2025/2026 tags also use Summer24 MC, but target different data-taking years. The MC campaign name alone does not determine the appropriate data/MC correction. |
| JER PDF page 1 requires nominal JEC first, followed by nominal or up/down JER smearing, only on MC. | Confirms the planned JER variation order. It does not establish simultaneous JES and JER variations or replace the relative-SF formula verified in the source code. |
| Neither PDF specifies eleven regrouped JES nuisances, six regional JER nuisances, their correlation matrix, or the choice of JES-to-MET implementation convention. | Those PDFs alone do not establish the nuisance configuration. The later search-index follow-up below supplies the uncertainty policy and qualifies the earlier analysis/code-based proposal. |

**The `2.5 < abs(eta) < 3.0` JER exception is conditional.** Page 1 discusses poor agreement in that region and examples of a higher pT threshold or scaling-only smearing. It explicitly limits the latter to analysis-specific use with JME/JERC approval. The proposed standard implementation therefore retains the stochastic component for unmatched jets in this region. AN-25-050's regional exception must not be copied as an automatic 2024 fix. A request to adopt scaling-only smearing would need the stated scientific approval and an analysis-specific closure study; no such exception is being adopted here.

**The rare JES pathology is also conditional.** JES page 1 describes abnormally large forward-jet momenta from L2Relative and recommends rejecting `Jet_rawFactor > 0.9` only for affected production samples. A new check of all 1,531,251 input `Jet` entries in the fixture found zero above that rawFactor threshold and zero above 10 TeV; the maxima were 0.75 and 1,889 GeV respectively. This used the original NanoAOD values, before the processor replaces `rawFactor`. It does not certify every production file or substitute for the affected-sample list in [coordination issue 153](https://gitlab.cern.ch/cms-jetmet/coordination/coordination/-/issues/153#note_9486099), which redirects to login. No blanket jet rejection is proposed from this fixture result.

JES page 1 also confirms run-dependent residuals for data and the same-campaign AK4 fallback when AK8 JECs are unavailable. Those statements do not require changing the nominal 2024 MC AK4 path addressed by this finding.

The subsequently supplied [JER application screenshot](</isilon/export/home/jhuan166/.codex/attachments/5c180d11-8c3a-4c5a-b153-3bdfecc4b51c/Screenshot 2026-09-13 at 12.39.57 PM.png>) confirms the hybrid method, use of nominally JEC-corrected pT, scaling of the complete four-momentum, and **truncation of a negative JER multiplier to zero in both matched and stochastic cases**. This settles the discrepancy with the tutorial's fallback-to-one behavior in favor of the processor's existing zero clamp. The screenshot stops at the start of generator-level matching; it does not show the full matching, stochastic-smearing or implementation subsections. Its navigation identifies **Application Methods → Uncertainty Sources** as the current source to inspect for uncertainty treatment. The user also reports that the old uncertainty Twiki directs readers to the current JERC site; the legacy page is no longer the preferred outstanding-document request.

## Search-index follow-up: application rules and uncertainty policy

The user supplied the site's [search_index.json](/isilon/export/home/jhuan166/.codex/attachments/0a1e63d8-78f3-42cf-9719-d5850b40dbd9/search_index.json) on 13 September 2026. It contains 94 indexed entries across 15 page paths, including the application formulas, uncertainty recommendations and FAQ. This is a supplied snapshot of the current website, not a live authenticated read or a Git repository checkout. The relevant entries were read directly; their locations now give exact page URLs. The file has no hyperlink targets or image elements, and does not include the externally linked full-source/grouping tables or correlation slides. Its content hash and the scope of the read are recorded in the evidence file.

The [uncertainty recommendations](https://cms-jme-jerc.docs.cern.ch/recommendations/uncertainties/) and [uncertainty FAQ](https://cms-jme-jerc.docs.cern.ch/faq/#uncertainties-and-correlations) materially qualify the earlier proposed configuration:

| Recovered guidance | Consequence for this analysis |
| --- | --- |
| Precision measurements and analyses that can constrain JES nuisances should use the full 27-source set. The default reduced 11-source treatment is for mild sensitivity and requires demonstrating that the fit does not over-constrain the nuisances. A single Total nuisance requires JME approval. | Because this skim feeds a precision Vcb measurement, prepare full-source production as the preferred target. The earlier reduced-set proposal is a conditional alternative, not an established adequate final model. The subsequently supplied Case I workbook resolves the exact source list below. The payload contains both independent sources and aggregate/alternative entries, so selecting every available entry is incorrect. |
| Different JES sources are independent; a given source is correlated across its phase space and may change sign. JES and standalone JER are independent. `RelativeJER*` JES sources describe the effect of JER on calibration derivation and must be retained alongside standalone JER. | Preserve the signed payload output and use one coefficient per source across jets and its MET response. Do not take absolute values, drop `RelativeJER*`, or fit Total together with its components. |
| Build varied jet four-momenta before repeating pT-dependent selection, overlap removal and derived observables. Standard JES uncertainties are applied to MC, not simultaneously to data and MC. | The full-pass design has direct current JERC support in addition to the analysis-note precedent. This index supplies no new electron prescription; the electron migration fix still follows the supplied EGM guidance and the measured migrations. |
| The six-region JER split is explicitly introduced as a preliminary recipe for full Run 2 analyses with JER sensitivity. A single JER nuisance is acceptable if the fit does not constrain it beyond its assigned uncertainty. | A global JER pair is the initial validation configuration, subject to the stated fit check. Keep the six-region implementation precedent as an option to assess for 2024, not a universal Run-3 requirement. The page does not establish a final 2024 regional correlation prescription. |
| The reduced-set six-global/five-period-specific correlation example covers four Run-2 UL periods; the six-region JER cross-year statement also explicitly covers Run 2. Run-2/Run-3 JES correlations are delegated to provisional slides. | Preserve the 2024 source labels but do not extrapolate a final multi-year correlation model from those examples. The slides are relevant only if a combination is intended. |

The complete [JER application page](https://cms-jme-jerc.docs.cern.ch/application/jer/#generator-level-matching) now verifies both AK4 matching requirements (`deltaR < 0.2` and `abs(pt_JEC - pt_gen) < 3 * resolution * pt_JEC`), the matched/stochastic formulas, zero clipping, and reuse of identical hash inputs for nominal/up/down. The [JER FAQ](https://cms-jme-jerc.docs.cern.ch/faq/#jet-energy-resolution) explicitly confirms the fractional `SFUncertainty` formula for the 2024 payload. These agree with the existing nominal implementation and the proposed variation mechanics. No additional PDF of that application page is needed for these questions.

The [Run-3 veto-map recommendations](https://cms-jme-jerc.docs.cern.ch/recommendations/jet-veto-maps/#application) confirm mandatory event rejection using corrected AK4 jets with pT > 15 GeV, TightLepVeto ID and charged-plus-neutral EM fraction < 0.9, consistently in data and MC. They list the 2024 V1 map. This closes the audit's current-wording access gap for the veto selection. It does not settle the separate Tight-versus-TightLepVeto exception for lepton-cleaned analysis jets, or replace occupancy and analysis-impact validation. The [JEC FAQ](https://cms-jme-jerc.docs.cern.ch/faq/#jet-energy-corrections) also confirms the complete `L1L2L3Res` compound for MC, retaining identity levels, and that rescaling jet momenta must not rescale stored constituent energy fractions.

## Case I workbook: full source list resolved

The supplied [JEC Uncertainty Correlation 2017 and 2016.xlsx](</isilon/export/home/jhuan166/.codex/attachments/581cac15-d3f4-47ed-b165-30c4f7e3e784/JEC Uncertainty Correlation 2017 and 2016.xlsx>) is the table the user identifies as linked by Case I. Its visible **Simple** worksheet contains exactly 27 source names in **A2:A28**, with **Correlation (Ideal)** in column B and **Correlation (Simple)** in column C. All 27 names have exact matches of the form `Summer24Prompt24_V5_MC_<source>_AK4PFPuppi` in the bundled 2024 V5 payload, all taking `(JetEta, JetPt)`. The [full-source manifest](jes-2024-full-source-manifest.json) records those mappings, workbook cells, historical correlation values and both file hashes. This resolves the outstanding source-list request and supplies the explicit basis for 54 JES up/down passes.

**The workbook's percentages describe historical correlations between 2016 and 2017.** The visible Ideal column contains six fully correlated, eleven 50%-correlated and ten uncorrelated sources. Those entries are not multipliers of the 2024 uncertainties and do not specify correlations between jets within 2024. For this single-year model, keep each named source at its full signed value, share its nuisance coefficient across its affected jets/events and corresponding MET response, and treat different sources as independent. Do not remove a source whose historical row says “no correlation.” A combined Run-3 or Run-2/Run-3 fit would require its own current correlation guidance; no such combination is needed to implement the 2024-only passes.

Both workbook sheets were inspected. The hidden **Sheet1** has the same source names but discussion comments and five different correlation recommendations (`RelativeJEREC1`, `RelativeJEREC2`, `RelativePtEC1`, `RelativePtEC2`, `RelativeSample`). The manifest transcribes the visible **Simple** sheet rather than silently reading the first, hidden sheet. Its 2016–2017 labels are preserved as historical metadata, not promoted to a new 2024 correlation model. Together with the current JERC full-set policy and the exact 2024 payload matches, the workbook establishes the source basis; the numerical uncertainty values continue to come from the 2024 payload.

## Recommended variation model

Use separate full processing passes, starting from the input NanoAOD for each nuisance direction. Extend the existing [muon pass mechanism](cli.md#muon-momentum-passes) to one general kinematic-variation selector. This preserves events and objects that enter under a shift, and avoids repeated correction of an already modified input collection.

Vary one nuisance at a time, keeping every other correction nominal. The implemented `all` mode enumerates these passes, with one active nuisance at a time. Preserve compatibility with the existing muon option, but reject combinations that accidentally activate two kinematic nuisances. Each output needs a distinct name and recorded variation identity. Weight-systematic output remains a separate option; requesting weight systematics must not be mistaken for running object variations.

### JES

Use the [27-source manifest](jes-2024-full-source-manifest.json) for the full JES model in this precision-measurement workflow. Its source names are now checked against both the supplied Case I table and the 2024 payload. The implementation should accept an explicit manifest and fail clearly if a requested correction is unavailable. The mechanism for running a source must not depend on whether the eventual manifest is full or reduced. The runtime registry contains this exact source list; a unit test checks its correspondence to the manifest so installed code need not load documentation files.

For the conditional reduced alternative, the bundled [2024 jet payload](../src/boostedhh/corrections/2024_jet_jerc.json.gz) already contains all eleven regrouped components:

```
Absolute, Absolute_2024, BBEC1, BBEC1_2024,
EC2, EC2_2024, FlavorQCD, HF, HF_2024,
RelativeBal, RelativeSample_2024
```

Their correction names are `Summer24Prompt24_V5_MC_Regrouped_<source>_AK4PFPuppi`, with inputs `(JetEta, JetPt)`. Retain the era suffixes for the eventual multi-year nuisance model without assuming the Run-2 correlation example settles a 2024 combination. The separately available `Regrouped_Total` is useful for a diagnostic comparison; do not fit it as an additional independent uncertainty together with its components. Using these eleven sources for the final fit requires the sensitivity/constraint validation stated above.

Following the reference jet calculator, first obtain nominal JEC+JER jets, evaluate each JES source on their nominal eta/pT, and form `p4_up/down = p4_nominal * (1 +/- delta_source)`. Preserve eta, phi, input jet identity, tagger values and charge associations; update mass and `rawFactor` consistently. Keep the nominal JER realization fixed for these JES variations. Re-running the stochastic smearing helper with JES-shifted pT changes its hash input and would inject a fresh random draw into a JES comparison.

`delta_source` is signed. A source's up direction may lower one jet's pT and raise another's; replacing it with `abs(delta_source)` destroys those correlations. The new payload grid check finds negative values even in `Regrouped_EC2`, `Regrouped_FlavorQCD`, `Regrouped_RelativeBal` and `Regrouped_RelativeSample_2024`. Add a mixed-sign, same-source check to the jet/MET implementation validation.

### JER

Retain the current payload keys:

```
Summer24Prompt24_JRV2_MC_PtResolution_AK4PFPuppi
Summer24Prompt24_JRV2_MC_ScaleFactor_AK4PFPuppi
Summer24Prompt24_JRV2_MC_SFUncertainty_AK4PFPuppi
```

Evaluate these on the nominal JEC-corrected, unsmeared jet. For the relative uncertainty `u`, use `SF_up = SF_nominal * (1 + u)` and `SF_down = SF_nominal * (1 - u)`. Calling the scale-factor correction with an extra `up/down` string is incompatible with this payload's two-input signature. Adding `u` directly to `SF` is also a different prescription.

Evaluate `JERSmear` at the same corrected pT, eta, rho, event identity, nominal resolution and accepted generator match for nominal/up/down, changing only the scale factor. For AK4 require both `deltaR < 0.2` and `abs(pt - genPt) < 3 * resolution * pt` using unsmeared JEC pT; a failed condition selects the stochastic branch. These fixed inputs give the same stochastic variate in all three cases. For a matched jet, the factor is `1 + (SF - 1) * (pt - genPt) / pt`; for an unmatched jet, it is `1 + z * resolution * sqrt(max(SF**2 - 1, 0))`. Truncate negative factors to zero before rescaling, as confirmed by the complete supplied application text, and test those rare cases. Construct each varied jet from the unsmeared corrected jet, avoiding division by a possibly zero nominal smear factor.

Start validation with a global JER up/down pair. Its suitability for the final fit depends on the nuisance-constraint check. If assessing the six-region option used by AN-25-050 and implemented in the reference, the reference fixes region assignment from nominal smeared pT and eta:

| Region | Nominal coordinates |
| --- | --- |
| 0 | `abs(eta) < 1.93` |
| 1 | `1.93 <= abs(eta) < 2.5` |
| 2 / 3 | `2.5 <= abs(eta) < 3.0`, pT below / at least 50 GeV |
| 4 / 5 | `abs(eta) >= 3.0`, pT below / at least 50 GeV |

For a regional variation, use the varied factor inside that region and the nominal factor elsewhere, with the same region identity propagated to MET. Do not add global JER independently to the regional sources or split events into disjoint samples. The recovered recommendation gives the same internal boundaries for its **Run-2** recipe, but bounds its last interval at `abs(eta) < 5`, whereas the reference helper extends it to all `abs(eta) >= 3`. Analysis jets stop at 4.7, but Type-1 jets can reach 5.2; do not silently extend that recipe to this MET acceptance or claim the reference's nominal-smeared-pT bin assignment is specified by the recommendation. A final regional scheme for 2024 requires explicit validation and confirmation of its applicability, including that forward tail.

### Type-1 MET

Extend the existing 2024 calculation instead of replacing its NanoAODv15 handling with an older example. For every jet variation, rebuild MET in Cartesian coordinates from `RawPuppiMET`, using the complete regular `Jet` and disjoint `CorrT1METJet` collections before analysis cuts, lepton cleaning, sorting or ten-slot output truncation.

The recovered JERC FAQ directly asks for opposite-vector propagation of nominal JER and its variations with the Type-1 selection. The supplied JMAR table labels JER-to-MET propagation optional in general. The implementation propagates it, satisfying the more specific JERC application wording and the processor's existing nominal choice. This does not turn the unrelated optional lepton/unclustered terms into universal requirements. Both sources require coherent JES-to-MET propagation.

Retain muon-subtracted raw pT and the stored angular offsets, the full released JEC compound, and the selected jet's JER factor. For JES, carry the corresponding per-jet JES multiplier into its Type-1 contribution with nominal JER; for JER, use that jet's varied smear factor and its fixed regional assignment. Apply the corresponding treatment to auxiliary jets as well. The implemented adaptation uses the same source, direction and per-jet variation in the jet and MET paths, as required by JMAR.

Recompute contribution eligibility using the active muon-subtracted corrected pT > 15 GeV, EM fraction < 0.9, and explicitly enforce `abs(eta) < 5.2`. The supplied worked example supports this corrected-pT selection. Rebuild the full sum for each pass so changes of membership at 15 GeV are retained. The L1 reference remains unchanged by the uncertainty multiplier. In vector notation:

```
MET_variation = RawPuppiMET
              - sum(contributing jets,
                    corrected_muon_subtracted_pT_variation - pT_L1)
```

Each term uses its muon-subtracted transverse direction. Increasing a jet contribution must decrease MET along that direction. Save the resulting `METPt` and `METPhi` as the active values in that pass. A JES source and its MET response are one nuisance, not two independently fitted uncertainties.

The optional unclustered variation has an established additive prescription in the supplied `Type1METUnc.pdf`: add `stored_shifted_PuppiMET_xy - stored_nominal_PuppiMET_xy` to the rebuilt nominal MET. It can be implemented separately. Electron/muon-to-MET propagation is also optional according to the supplied JMAR table; it is not needed to fix entering-electron events. Any chosen lepton propagation must avoid double counting leptons through jets or unclustered energy.

### Electron passes and downstream reconstruction

The current [electron helper](../src/vcb/processors/electron_ss.py) already computes `pt_scaleUp`, `pt_scaleDown`, `pt_smearUp` and `pt_smearDown` on the complete input collection using one stable Gaussian per electron. Select the requested field as active pT **before** `objects.good_electrons` and trigger matching, while preserving nominal and raw pT and the electron's input identity. Keep the current 2024 EGM formulas; the references do not justify replacing them with fixed percentage shifts or an older year's helper signature.

Every full pass must redo trigger-lepton eligibility and choice, lepton selection, jet overlap removal, jet-veto candidate selection and event veto, analysis-jet pT cuts and sorting, `nJets`, `ht`, `BTaggable`, generator-parton assignments, saved object slots and efficiency weights evaluated on the active selected lepton. Downstream fits/reconstruction must use that pass's objects and MET. Keep all-input generator/pileup normalization totals the same across kinematic passes; changed acceptance is the effect being measured, not a change to the normalization denominator.

Pass counts depend on the validated nuisance model. With four electron shifts and the existing four muon shifts, the illustrative totals including nominal are:

| JES model | One global JER source | Six regional JER sources |
| --- | ---: | ---: |
| Full 27-source model | 65 | 75 |
| Reduced 11-source model | 33 | 43 |

The full-source manifest is now resolved. The implemented default is the **65-pass** full-JES/global-JER model; the suitability of global JER for the final fit and any choice of reduced JES still need the stated fit checks. The earlier 43-pass count is a conditional configuration, not the recommended default for every 2024 analysis. Optional unclustered shifts add two. The full-JES/global-JER configuration is now the implemented `all` group. Reduced JES and regional JER configurations remain conditional alternatives and are not implemented CLI groups.

## Reference differences that must remain explicit

CMSJMECalculators resolves the central JER formula and demonstrates useful variation bookkeeping, but its checked Type-1 implementation is not a drop-in replacement for this processor:

- It does not accept the NanoAODv15 `muonSubtrDeltaEta/Phi` inputs. Its scalar muon add-back and JEC evaluation differ from the explicit three-vector subtraction supported by this processor's tests and the supplied guidance.
- It fixes the Type-1 contribution mask using the unsmeared nominal muon-subtracted corrected pT. The supplied tutorial applies its cut after the active correction. The implementation recomputes this mask under the active correction; the tests cover both directions across the threshold.
- Its MET JES code evaluates the uncertainty on an unsmeared intermediate momentum and applies an additive JES response around smeared nominal MET, whereas its analysis-jet JES code varies nominal smeared pT. The tutorial orders JES before another JER evaluation. Therefore use these sources to establish formulas and correlations, but document the project's coherent shared-factor adaptation instead of claiming bit-for-bit agreement among these different paths.
- The tutorial's JER fallback replaces nonpositive factors with one. The supplied current application screenshot explicitly prescribes truncation of negative factors to zero; retain the processor's existing zero clamp. The tutorial fallback is not the reference for this edge case.

The [CMSSW Type-1 producer](https://github.com/cms-sw/cmssw/blob/CMSSW_15_1_0_patch4/JetMETCorrections/Type1MET/interface/PFJetMETcorrInputProducerT.h#L175), also inspected on CVMFS, supports muon four-vector subtraction, reuse of additional jet scales, corrected-pT eligibility, and the negative transverse update. An exact MiniAOD comparison remains useful validation; it was not performed here.

## Completed checks and implementation acceptance criteria

The Case I follow-up verifies all **27/27** source keys and their two-input signatures against the current payload. All source evaluations are finite on the 152-point eta/pT grid; 17 of the selected sources take negative values somewhere on that grid. Their quadrature is not numerically identical to the independently tabulated `Total`: the largest grid difference is `0.00153046` in fractional uncertainty, at eta = -2.9 and pT = 15.1 GeV. At that point, `0.00147742` is explained by taking quadrature after linearly interpolating the sources versus interpolating their endpoint quadratures; the remaining endpoint discrepancy is `0.00005304`. A check at 2,000 native pT knots across all 40 eta bins finds a maximum absolute discrepancy of `0.00011035`. These are payload diagnostics, not an event-yield uncertainty. Preserve the released source values; do not renormalize them to Total or add Total as an extra independent source. No exact numerical Total closure or new full-production run is claimed.

The search-index follow-up inventories **64** AK4 uncertainty-related correction entries in the bundled V5 MC payload and evaluates each on **152** eta/pT grid points (eta from -5.1 to 5.1, pT from 15.1 to 1,000 GeV). All evaluations are finite; **28** entries have negative values somewhere on the grid, including the four regrouped entries listed above. The 64 include subtotals, totals, alternative flavor descriptions and correlation groups, so this inventory is not an independent nuisance manifest. These grid evaluations add a signed-source check; they are not new full-fixture varied skims, a proof of the 27-source mapping, or a fit sensitivity study.

The earlier full-fixture diagnostic processed all **208,780 events and 1,531,251 regular jets**, using the current nominal muon correction. It reproduces **59,537** selected events. All eleven regrouped JES evaluations are finite for regular jets above 15 GeV. Of the 254,816 jets with pT > 15 GeV and `2.4 < abs(eta) < 4.7`, 159,516 have nonzero EC2 uncertainty and 95,300 have nonzero HF uncertainty. These jet counts precede jet ID, lepton cleaning and event selection; they establish that the forward sources are active, not their effect on the final calibration. This fixture processing was not repeated for the search-index follow-up.

All JER nominal/up/down factors are finite. The matched-jet formula agrees exactly with the released helper in the probe; stochastic draws recovered from the three factors agree within `4.8e-14`. This checks the relative-SF prescription with the bundled payload, not full varied production output.

Re-evaluating electron acceptance with nominal jets, quality requirements and jet veto fixed gives:

| Electron shift | Entering nominal selection | Leaving nominal selection |
| --- | ---: | ---: |
| Scale up | 21 | 0 |
| Scale down | 0 | 15 |
| Smearing up | 18 | 25 |
| Smearing down | 22 | 15 |

The complete varied-output checks below cover these electron migrations, active-pT lepton SFs, jet identity and charge associations after sorting, entering/leaving events and objects, and identical all-input normalization totals. Acceptance checks cover Type-1 vector balance and 15-GeV crossings in both jet collections, correlated jet/MET factors, stable random draws across chunks and event ordering, zero-smear jets and clear failure for missing requested uncertainty payloads. The required unit and full integration results and nominal-baseline comparison are recorded below.

## Access status

The public CMSJMECalculators API supplied the source without credentials. The earlier HTTP 401 responses for the JES/JER recommendation pages are access history; the user's PDFs now close those requests. The supplied MET corrections PDF and C++ tutorial likewise cover their stated source questions.

Unauthenticated checks on 13 September 2026 returned **HTTP 401** for the JER application page, historical uncertainty Twiki and website search index. The private [JERC source project](https://gitlab.cern.ch/cms-jetmet/docs/jerc) redirects to sign-in. The user's downloaded search index now supplies the relevant text and exact locations of [Uncertainty Sources](https://cms-jme-jerc.docs.cern.ch/application/jec_uncertainty_sources/), [JER application methods](https://cms-jme-jerc.docs.cern.ch/application/jer/) and [Uncertainties and Correlations](https://cms-jme-jerc.docs.cern.ch/recommendations/uncertainties/). Those webpage-text access requests are closed; their historical authentication failures do not make the supplied text unread.

The **Case I full JES table request is closed** by the supplied workbook and verified source manifest. No additional source-table upload or repository access is needed for the implemented 2024-only full-JES/global-JER model. The separately linked grouping table and Run-2/Run-3 correlation slides are supplementary if choosing a reduced model or combining periods. Confirming a six-region JER alternative for 2024 remains separate from implementing the global pair. The implementation and its event-migration/MET checks are recorded below. Final-fit validation remains an analysis step.

The affected-sample [JES anomaly issue](https://gitlab.cern.ch/cms-jetmet/coordination/coordination/-/issues/153#note_9486099) redirects to GitLab sign-in. This sample-specific check is separate from implementing the missing variation passes. No repeat upload of the JES, JER or MET recommendation PDFs is needed.

## Implementation validation, 13 September 2026

The [machine-readable validation record](jet-met-electron-variations-2024-validation.json)
records the fixture hash, pass-by-pass comparisons and test scope.

- **227 unit tests and 18 subtests passed.** After the final CLI cleanup, all
  19 kinematic-dispatch/selection tests passed again. Ruff passed for
  `src/vcb`, `tests` and `condor`; the worker template passed shell syntax checking.
- **Nominal full integration passed:** 208,780 input events, 59,537 selected,
  and 741 output columns. Comparing to the prechange ROOT gives identical
  values in every one of its 734 columns. Seven columns were added:
  `KinematicVariation`, three `ElectronNanoIdx` slots and three
  `ElectronPtNominal` slots. The nominal jet/charge round-trip report is
  unchanged. The explicit Type-1 |eta| < 5.2 guard changes no fixture values.
- **All 65 complete passes passed a bounded output check:** one Coffea chunk
  of 2,008 input events, with weight systematics enabled and 759 columns per
  output. The nominal pass selects 519 events. All input normalization totals,
  including weight-variation totals, are identical across these copies.
  Signed JES pT/mass factors, active lepton pT, efficiency weights, sorting,
  tag eligibility and shared jet/charge identities were checked.
- **Eight shifted passes ran over the full fixture:** four electron shifts,
  global JER up/down and signed JES `RelativeBal` up/down. Their output checks
  passed, with the results below. Every pass has
  `np_nominal = 69805971.43478915` and identical all-input pickle totals.

| Full-fixture pass | Selected | Entering nominal | Leaving nominal |
| --- | ---: | ---: | ---: |
| Nominal | 59,537 | — | — |
| Electron scale up | 59,558 | 21 | 0 |
| Electron scale down | 59,522 | 0 | 15 |
| Electron smearing up | 59,530 | 18 | 25 |
| Electron smearing down | 59,544 | 22 | 15 |
| JER up | 59,604 | 74 | 7 |
| JER down | 59,440 | 34 | 131 |
| JES RelativeBal up | 59,570 | 34 | 1 |
| JES RelativeBal down | 59,514 | 2 | 25 |

The electron counts reproduce the independent preimplementation migration
study exactly. SF checks use each output's active trigger-lepton pT and the
input electron's supercluster eta. Common-event lepton weights stay unchanged
under jet-only shifts. Jet/MET outputs, jet counts and slot ordering change
under the relevant shifts; lepton-only passes retain the same full-jet MET.

The full input/output jet round-trip diagnostic passed for nominal,
`jerUp`, `electron_scaleUp` and `jes_RelativeBalDown`, respectively checking
**5,420,807**, **5,392,162**, **5,422,762** and **5,430,871** tagger/charge
values. Each had zero differing values, wrong input indices, pT mismatches,
misordered slots or unexplained dropped jets. Unit tests separately verify
Type-1 vector balance, correlated regular/auxiliary JES and JER factors,
active 15-GeV membership, muon-subtracted direction/eta acceptance, shared
stochastic draws, strict hybrid matching, typed empty jets and zero-smear
recovery. A requested missing source raises instead of producing nominal.

The implementation resolves audit finding 3 within the stated 2024 MC scope.
Global-JER nuisance constraints in the final fit, collision-data closure and
any regional/reduced/cross-year alternative remain analysis validation.
Optional lepton/unclustered MET terms were not enabled. The reference-code
differences above remain explicit; these checks do not claim a bit-for-bit
MiniAOD or compiled CMSJMECalculators comparison.
