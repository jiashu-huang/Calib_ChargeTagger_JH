# CMS readiness: quick guide

**Reviewed: 5 November 2026.** Applies to our 2024 TT2Q, TTCB and TTBB simulation.

**The tested simulation workflow works. A final physics measurement still needs more work.**

Three terms used below:

- **MC** = simulated collisions. **Data** = collisions recorded by CMS.
- **Jet** = a spray of particles. **pT** = momentum perpendicular to the beams.
- **Weight** = how much a simulated event contributes when we count events.

**✅ Checked** means the code matches the reviewed recipe within the stated scope.
**🟡 Incomplete** means a calculation, decision or validation is still needed.
**❌ Missing** means the required capability is absent. These are our review
judgments, not official CMS approval.

## ✅ Implemented and checked

Read each row as: **the CMS recipe → what this code does → where to check it.**

| Part | CMS recipe, in plain English | What works here | Sources |
| --- | --- | --- | --- |
| **Jet momentum** | Correct the jet energy and simulated resolution. Repeat event selection when testing a correction's uncertainty. | The 2024 corrections and separate uncertainty runs are implemented. The current production uses the default, unshifted corrections. | [CMS jet-resolution guide](https://cms-jme-jerc.docs.cern.ch/application/jer/) · [our checks](jet-met-electron-variations-2024-plan.md) |
| **Bad detector regions** | Reject events containing jets in the recommended problem regions, using the prescribed jet selection. | The veto map and its event rejection are implemented. Jet-quality definitions match the official correction file. | [CMS veto-map guide](https://cms-jme-jerc.docs.cern.ch/recommendations/jet-veto-maps/#application) · [our checks](../src/boostedhh/corrections/README.md) |
| **Missing momentum, or MET** | Update MET when jet corrections change. Apply the recommended detector-noise filters. | Jet-based MET corrections and the eight required filters are implemented. A separate comparison with real data remains open. | [CMS MET corrections](https://cms-jme-jmar.docs.cern.ch/recommendations/met/corrections/) and [filters](https://cms-jme-jmar.docs.cern.ch/recommendations/met/noise_filters/) · [our checks](jet-met-electron-variations-2024-plan.md) |
| **Electron energy** | Use the released 2024 electron corrections, including smearing to model detector resolution. | Corrections are implemented; the bundled file matches the official release checked on BRUX. | [Official electron correction file](/cvmfs/cms-griddata.cern.ch/cat/metadata/EGM/Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15/latest/electronSS_EtDependent.json.gz) · [our checks](../src/vcb/corrections/README.md) |
| **Muon momentum: 26–200 GeV** | Correct the selected muons before making momentum-dependent event cuts. | Corrected momenta and their uncertainty runs are implemented in this range. | [CMS muon-momentum guide](https://muon-wiki.docs.cern.ch/code/ptcorr/) · [our checks](muon-momentum-2024-plan.md) |
| **Electron and muon detection efficiencies** | Apply correction factors for how often a lepton is reconstructed, identified and triggers the detector. Include the measured uncertainties. | Released factors are applied. Muon statistical and systematic errors are included, including the previously missing trigger term. | [Official electron/muon files and definitions](../src/vcb/corrections/README.md) · [CMS muon guidance](https://muon-wiki.docs.cern.ch/guidelines/corrections/) · [our checks](archive/cms-readiness-detailed-2026-11-05.md#muon-efficiency-uncertainties) |
| **Pileup: extra collisions in the same crossing** | Use the released 2024 C–I correction factors. | The code uses the full factors; the old artificial cap has been removed. | [Official CMS pileup file](/cvmfs/cms-griddata.cern.ch/cat/metadata/LUM/Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15/latest/puWeights_CDEFGHI.json.gz) · [our checks](weight-realignment-2026-10-27.md) |
| **Generator uncertainty information** | Identify the weights that describe alternative collision simulations and proton structures. | Their identities and values are preserved, including negative weights and totals needed to scale event counts. The final uncertainty calculation is still separate. | [CMS NanoAOD weight definitions](https://twiki.cern.ch/twiki/bin/view/CMSPublic/WorkBookNanoAOD#Weights) · [our checks](skim-realignment-2026-10-27.md) |

## 🟡 / ❌ Still needs work

These rows explain **why we cannot call the whole analysis CMS-ready yet**.
An unfinished analysis choice is different from a known coding error.

| Status | Item | What is missing | Source of the requirement or decision |
| --- | --- | --- | --- |
| 🟡 Incomplete | **Muons outside 26–200 GeV** | Especially above 200 GeV, we still need an appropriate momentum definition, correction and uncertainty treatment. Copying a correction measured for a different momentum definition is not sufficient. | [CMS muon guidance](https://muon-wiki.docs.cern.ch/guidelines/corrections/) · [remaining application questions](muon-momentum-2024-plan.md) |
| 🟡 Incomplete | **Efficiencies in our actual events** | Check that the lepton corrections work in events with many jets and heavy-flavour decays. Confirm the electron-trigger angle convention and efficiency near its threshold. | [CMS muon guidance](https://muon-wiki.docs.cern.ch/guidelines/corrections/) · [electron/trigger audit](audit-2024-mc-2026-09-11.md) |
| 🟡 Incomplete | **Jet cleaning and MET validation** | Show that our lepton removal, detector-region veto and MET treatment behave correctly in this analysis. Tests of the formulas alone do not establish that. | [CMS Jet-ID guidance](https://twiki.cern.ch/twiki/bin/view/CMSPublic/PhysicsResultsDP24028) allows an analysis-dependent cleaning choice; [CMS MET guide](https://cms-jme-jmar.docs.cern.ch/recommendations/met/corrections/) · [our remaining checks](jet-met-electron-variations-2024-plan.md) |
| 🟡 Decision needed | **Combining TT2Q and TTBB** | Define which sample supplies each background category, so overlapping physics is not counted twice. The provisional TTBB rate, **16.0117 pb**, is already implemented; it does not solve overlap. | [CMS HIG-19-011, §7](https://arxiv.org/html/2407.10896v2#S7) is an analysis example, not a universal 2024 recipe. See [our adopted convention and open choices](b0-input-readiness-2026-10-28.md#ttbb-normalization-and-overlap). |
| 🟡 Decision needed | **Predicted event rates** | Settle the W-decay probabilities and reference Vcb value used to predict how many events we expect. | [AN-25-214](/isilon/export/home/jhuan166/Vcb/References/AN-25-214.pdf) is our reference analysis, not a universal selection rule. See the [rate comparison](audit-crosscheck-2026-09-23.md). |
| 🟡 Decision needed | **The final uncertainty model** | Choose the top-pT treatment and shared uncertainties; jet-tagging corrections are the next row. TTBB has no separate weights for varying the strong-force coupling, alpha-S; its uncertainty still needs a prescription. **Reviewed 10 November** against the CMS top-quark group's two general pages, which are still Run 2 documents: the top-pT recipe has no Run 3 update and says not to use it on a dedicated ttbb sample such as TTBB. Several listed uncertainties need extra simulated samples we do not have (matching scale, underlying event, colour reconnection, top mass), and CMS currently advises against its own b-fragmentation weights. | [CMS jet-uncertainty guidance](https://cms-jme-jerc.docs.cern.ch/recommendations/uncertainties/) · [CMS generator guidance](https://cms-pdmv.gitbook.io/project/mccontact/info-for-mc-production-for-run3-campaigns) · [CMS top-quark uncertainty list](https://twiki.cern.ch/twiki/bin/view/CMS/TopSystematics) and [top-pT page](https://twiki.cern.ch/twiki/bin/view/CMS/TopPtReweighting) · [our PDF/alpha-S review](pdf-alphas-2024-plan.md) · [our check of the list](2024-inputs.md#top-pag-uncertainty-list-checked-against-the-skim-2026-11-10) |
| 🟡 Decision needed | **Flavour-tagger calibration** (added 10 November) | A tagger scores how b-like or c-like a jet is. For 2024, CMS has released corrections only for fixed score thresholds ("working points"), and its b-tagging and c-tagging corrections cannot be used together. Our B0 network inputs use the raw scores, which have no official 2024 correction. Choose threshold-binned inputs, a future CMS correction of the score shape, or our own factors. The skim applies no tagging cut, so its output is unaffected. | [CMS 2024 tagging campaign](https://btv-wiki.docs.cern.ch/ScaleFactors/Run3Summer24/), [working-point recipe](https://btv-wiki.docs.cern.ch/PerformanceCalibration/fixedWPSFRecommendations/) and [uncertainties](https://btv-wiki.docs.cern.ch/PerformanceCalibration/SFUncertaintiesAndCorrelations/) · [our B0 inputs](b0-input-profile.md) |
| ❌ Missing guarantee | **Jet charge attached to the correct jet** | The code assumes two jet lists have matching order. We need an explicit mapping or a shared source collection to guarantee that. | [CMS jet-updater code](https://github.com/cms-sw/cmssw/blob/CMSSW_15_1_0_patch4/PhysicsTools/PatAlgos/python/producersLayer1/jetUpdater_cfi.py) sorts jets. This is a **software-correctness issue**, documented in [our round-trip checks](tests.md#the-jet-tagger-round-trip-check). |
| ❌ Not implemented | **Real collision data** | Add the approved good-data mask and corrections that depend on the data-taking run. Then compare corrected simulation with data. The code currently refuses 2024 data. | [CMS luminosity guidance, pp. 3–4](/isilon/export/home/jhuan166/.codex/attachments/da14dc9c-6865-46a8-b359-245635000e10/CMS_LumiRecommendationsRun3.pdf) · [CMS JEC guidance](https://cms-jme-jerc.docs.cern.ch/faq/#jet-energy-corrections) · [data-path audit](audit-crosscheck-2026-09-23.md) |

**One issue already closed:** extra lepton impact-parameter cuts were removed.
That resolves the concern about applying standard efficiency corrections after
adding those extra cuts. This follows our reference analysis,
[AN-25-214, §§3.2 and 4.2](/isilon/export/home/jhuan166/Vcb/References/AN-25-214.pdf);
it is an analysis choice, not a universal CMS selection rule.

## Evidence behind the colors

The November 5 review found:

- **474 tests + 22 subtests passed**, and the code-quality check passed.
- **All nine reviewed correction files matched** the official CMS files visible on BRUX.
- **All 60 pinned production files matched** this checkout and each frozen campaign copy.

Those checks support the implementation claims. Real-data validation and the
unfinished physics decisions above still need their own evidence.

**Production snapshot — November 5, about noon Eastern:** TTCB was complete;
TTBB was finalizing; TT2Q still had queued jobs. The overall **C1 check**—our
check that all three complete datasets agree with their required input and
output definitions—had not finished. This is a project milestone, not a CMS
standard. See the [timestamped review record](cms-readiness-2026-11-05-validation.json).

## Reading the sources

A **CMS guide or official correction file** supplies the recipe. An **“our checks”**
link shows how this repository tested it. An **analysis example** shows one
choice made in a CMS analysis; it does not make that choice mandatory everywhere.

Some CMS web guides require CERN access and could not be reopened during this
review. Their previously reviewed copies and conclusions are identified in the
linked technical records. CVMFS file links refer to the official files on BRUX.

For formulas, release identifiers, historical results and detailed limitations,
use the [archived detailed report](archive/cms-readiness-detailed-2026-11-05.md).
