# 2024 muon momentum corrections — implementation and remaining validation

Implemented on 12 September 2026 for `Calib_ChargeTagger_JH`, building on the audit of `d212f09313e4418bd8b14d96bfa61356b3ee9c9d` and preserving the separate luminosity fix. **The ordinary-momentum 26–200 GeV correction and its complete processing passes are implemented; high-pT treatment and collision-data closure remain open.** Numerical checks, source hashes and implementation results are recorded under `muon_momentum_implementation` in [the audit metrics](audit-2024-mc-2026-09-11-metrics.json). The earlier research sections remain as provenance.

**Implemented behavior**

[`muon_ss.py`](../src/vcb/processors/muon_ss.py) applies Run-3 MuonScaReKIT scale correction followed by MC resolution smearing before muon selection, using the corrected 2024 ordinary-momentum payload. Separate scale and resolution variations include statistical and systematic components; [`--muon-pt-variation all`](cli.md#muon-momentum-passes) retains entering events by processing the raw NanoAOD independently for each shift. Before correction, 34,321 of the fixture's 34,651 selected trigger muons (99.05%) had input pT in this range. The dedicated treatment of the 330 muons above 200 GeV now has the 2024 GE tables available. Their demonstrated use is a correction to **data TuneP momentum**; they do not establish a nominal GE correction to ordinary MC `Muon_pt`.

This is a correction to muon kinematics, separate from the existing identification, isolation and trigger efficiency weights. The public [NanoAOD workbook's muon description](https://twiki.cern.ch/twiki/bin/view/CMSPublic/WorkBookNanoAOD#Muons) states that residual momentum corrections are not applied in NanoAOD. The processor now corrects ordinary `events.Muon` before [good-muon selection](../src/vcb/processors/vcbSkimmer.py); it does not consume the separate beam-spot-constrained momentum.

**What the analysis notes establish**

| Source | Useful precedent | Limit on reuse |
| --- | --- | --- |
| [AN-25-214](/isilon/export/home/jhuan166/Vcb/References/AN-25-214.pdf), §3.2.2, PDF page 15 | The relevant 2024 Vcb analysis applies muon scale and resolution corrections, with charge, eta, phi and tracker-layer inputs as appropriate. | Its cited `2025-10-17` correction version predates the April 2026 bug fix. Its prompt-MVA selection also differs from this processor's PF-isolated tight muons. |
| AN-25-214, §6, PDF page 61 | It evaluates lepton momentum uncertainties in the final analysis. | Its small observed impact does not establish a negligible effect on this calibration or justify omitting the variations. |
| [AN-25-050](/isilon/export/home/jhuan166/Vcb/References/AN-25-050.pdf), §4.2, PDF page 21 | Explicit use of MuonScaReKIT and a dimuon Z-peak validation. | It covers 2022–2023. Its short description of data scales and MC resolution is not a complete MC application recipe; the current official example applies MC scale first. |
| AN-25-050, §7.1, PDF page 43 | Separate muon scale and resolution nuisance sources, each including statistical and systematic contributions. | Cross-period correlations in that analysis are a precedent, not a newly verified all-year POG prescription. |

Use these notes for analysis choices and validation examples. Use the current MUO payload and application guidance for the correction itself; do not introduce Run-2 Rochester parameters for Summer24.

**Pin the payload and application source**

The ordinary-momentum payload is [muon_scalesmearing.json.gz](/cvmfs/cms-griddata.cern.ch/cat/metadata/MUO/Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15/2026-04-28/muon_scalesmearing.json.gz). Its campaign is `Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15`; the [release notes](/cvmfs/cms-griddata.cern.ch/cat/metadata/MUO/Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15/2026-04-28/changes.md) explicitly identify a bug fix and addition of the separate VXBS payload. The April payload is content-identical to the currently accessible `latest` file. Its decompressed SHA-256 is:

```text
4d3137a34fd6cba316d9fd3b2f9f5f7df8aaac8f8f878e283d0f5ff89053589f
```

This payload is bundled as `src/vcb/corrections/2024_muon_scalesmearing.json.gz`. The loader verifies the decompressed hash, with only the same dated CVMFS file as fallback. Missing inputs or unavailable/mismatched payloads raise. Use the VXBS variant only if the analysis deliberately switches to the corresponding beam-spot-constrained momentum and validates that change.

The [MuonScaReKIT repository](https://gitlab.cern.ch/cms-muonPOG/muonscarekit) is publicly readable. The reviewed revision is `1c7426b5e1d808110e8f4fbfef27e71071ea3c26`, committed 22 June 2026. References below are pinned to that revision:

- [Coffea application example](https://gitlab.cern.ch/cms-muonPOG/muonscarekit/-/blob/1c7426b5e1d808110e8f4fbfef27e71071ea3c26/scripts/apply_corrections_coffea.py).
- [Python helper](https://gitlab.cern.ch/cms-muonPOG/muonscarekit/-/blob/1c7426b5e1d808110e8f4fbfef27e71071ea3c26/scripts/MuonScaRe.py) and [C++ helper](https://gitlab.cern.ch/cms-muonPOG/muonscarekit/-/blob/1c7426b5e1d808110e8f4fbfef27e71071ea3c26/scripts/MuonScaRe.cc).
- [Uncertainty derivation](https://gitlab.cern.ch/cms-muonPOG/muonscarekit/-/blob/1c7426b5e1d808110e8f4fbfef27e71071ea3c26/code/python/corrections/uncertainties.py) and [payload export](https://gitlab.cern.ch/cms-muonPOG/muonscarekit/-/blob/1c7426b5e1d808110e8f4fbfef27e71071ea3c26/code/python/tools/convert2json.py).

The helper examples require the uncertainty adaptations described below. The C++ implementation is a cross-check of formulas within the validated domain, not an oracle for every boundary: for example, its scale helper lacks the Python helper's explicit 200-GeV upper guard.

**Nominal correction in the medium-pT range**

The supplied [MUO momentum guide](/isilon/export/home/jhuan166/.codex/attachments/60aed387-817d-491a-9706-d09a9579a130/muon-momentum-scale-and-reso-corrections.pdf), PDF pages 1–2, specifies tight, isolated muons in **26–200 GeV** and prefers correcting both data and MC to the generator reference. The current processor's tight ID and PF isolation are compatible with this stated selection. Its additional impact-parameter efficiency questions remain a separate audit finding.

For MC, preserve `pt_raw`, then evaluate the scale using signed eta and phi and the original physical charge q:

\[
p_{T,\mathrm{scale}}=\frac{1}{M_{\mathrm{mc}}/p_{T,\mathrm{raw}}+qA_{\mathrm{mc}}}.
\]

Next smear MC using the released resolution model:

\[
p_{T,\mathrm{nom}}=p_{T,\mathrm{scale}}\left[1+K\,\sigma(p_{T,\mathrm{scale}},|\eta|,n_{\mathrm{layers}})R_{\mathrm{CB}}\right],
\qquad K=\sqrt{\max(0,k_{\mathrm{data}}^2-k_{\mathrm{mc}}^2)}.
\]

Here `poly_params` supplies the fractional-resolution polynomial and `cb_params` supplies the double-sided Crystal Ball distribution. Reuse the current helper's `RandomSmearing` payload evaluation, seeded by event number, luminosity block and phi, followed by its inverse CDF. Do not replace that distribution with an arbitrary Gaussian or draw independent noise for each variation. The required `pt`, `eta`, `phi`, `charge`, `nTrackerLayers`, `event` and `luminosityBlock` inputs exist in the fixture.

For data, use the corresponding `M_data` and `A_data` scale correction without MC resolution smearing. This choice requires data and MC to be processed consistently. The guide also describes leaving data unchanged and correcting MC to data; adopting that alternative would require a deliberate, consistent implementation rather than mixing the two conventions.

Respect the nominal helper's domain and pathological-output guards. Its scale guard uses the incoming pT; resolution is subsequently evaluated on the scaled pT. Test the composition explicitly near 26 and 200 GeV. In particular, the offline trigger-muon threshold is 26 GeV: allowing a helper argument below 26 does not establish calibrated validity below 26. Any proposed treatment that requires extrapolation there needs MUO guidance or an explicit validation; do not silently treat it as established by the note's lower baseline cut.

**Complete uncertainty treatment, including the helper discrepancy**

The published payload has nonzero `stat` and `syst` uncertainties. Both reviewed helper examples currently read only `stat` for their scale and resolution variations. Calling these functions unchanged would omit the payload's systematic component.

For each component u = `stat` or `syst`, evaluate the scale error with that component's M–A correlation. The helper's linearized expression around nominal corrected MC pT p is:

\[
(\Delta p_u)^2=p^4\left[\frac{\sigma_{M,u}^2}{p^2}+\sigma_{A,u}^2+
\frac{2q\rho_u\sigma_{M,u}\sigma_{A,u}}{p}\right].
\]

Obtain the errors from `m_mc` and `a_mc`, and the corresponding `rho_stat` or `rho_syst` from `m_mc`. The public derivation forms the joint data/MC scale parameters `M_SIG/M_DATA` and `(A_SIG-A_DATA)/M_DATA`; the exporter puts their uncertainties into the `_mc` entries. Thus those uncertainty entries already include data and MC contributions. Adding independent data parameter errors on top would double-count them. Keep the scale and resolution sources independent as specified in the supplied guide.

The resolution uncertainty in `k_mc` also has a particular meaning: its `stat`/`syst` entries describe the uncertainty **on residual K**, obtained from joint data/MC variations. They are not errors to add to nominal `k_mc` and then propagate through the square root a second time. With the same resolution draw as nominal, use:

\[
p_{T,\mathrm{res},u}^{\pm}=p_{T,\mathrm{scale}}
\left[1+(K\pm\delta K_u)\sigma R_{\mathrm{CB}}\right].
\]

The C++ variation uses residual K, consistent with the derivation. The Python `pt_resol_var` instead divides the nominal smearing displacement by `k_mc(nom)` and varies that coefficient. Algebraically its displacement is smaller than the residual-K expression by `K/k_mc(nom)`. In a four-muon synthetic check at 50, 70, 120 and 180 GeV, the Python statistical-variation displacements are only **0.297, 0.357, 0.407 and 0.440** times the C++-formula displacements. This is a helper-consistency finding, not an estimate of the analysis uncertainty. Nominal repeated evaluations were exactly reproducible.

The implementation uses residual K and includes `syst`; it retains the resolution draw explicitly so K = 0 needs no division. Shifted widths use `max(0, K ± deltaK)`; this floor is inactive for the released 2024 nominal bins. The reference smearing guard falls back to scaled pT when the smeared/scaled ratio leaves [0.1, 2] or is nonfinite, and records that fallback. Statistical and systematic components are saved separately. The default two-source model follows the analysis-note precedent: combine independent stat/syst components in quadrature within scale and within resolution, keeping scale and resolution independent. A fit can instead use the saved components with an explicit correlation model; counting the total and component shifts as independent would double-count errors. No cross-year correlation prescription is implied.

**Processor integration and acceptance**

| Location | Implementation |
| --- | --- |
| [`muon_ss.py`](../src/vcb/processors/muon_ss.py) | Pinned payload; deterministic nominal and varied momenta; raw pT, NanoAOD index, charge and coverage retained. Required payload/input failures raise. |
| [`vcbSkimmer.py`](../src/vcb/processors/vcbSkimmer.py) | Calls the helper before `good_muons`; the chosen active pT flows through trigger selection, SFs, jet cleaning and generator matching. Writes momentum fields and the pass ID. |
| [`run.py`](../src/vcb/run.py) | Nominal remains the default. `--muon-pt-variation all` runs nominal plus four independent full input passes into separate directories. Individual total or component shifts can also be selected. |
| [`tests/test_muon_ss.py`](../tests/test_muon_ss.py) | Numerical references, domain/fallback behavior, reproducibility and a real trigger-selection entering-event check, plus CLI dispatch checks. |

The input-pT scale guard and scaled-pT resolution guard are composed explicitly.
Below 26 GeV and above 200 GeV, momenta and all shifts retain the input value.
An in-range scale correction that moves MC outside the resolution domain is
marked scale-only. This means the physical below-26 migration problem is not
solved by extrapolation; applicability near that threshold still needs the
analysis validation discussed below.

All selected good muons carry `MuonPtRaw`, `MuonPtNominal`, `MuonPtScale`,
`MuonNanoIdx` and `MuonMomentumStatus`, with the usual slot suffix 0, 1 or 2.
MC also saves `MuonPt{Scale,Resolution}{Up,Down}` and
`MuonPt{Scale,Resolution}{Stat,Syst}{Up,Down}`. `MuonPt` always equals the active
pass's momentum. These fields are written independently of weight-systematics
settings; the baseline grows from 681 to **734 columns**.

| `MuonMomentumStatus` | Meaning |
| ---: | --- |
| 0 | Ineligible: outside tight ID, PF isolation or eta requirements, or nonfinite/invalid inputs |
| 1 | Calibration applied within the supported regime |
| 2 | Eligible quality, input pT below 26 GeV; unchanged |
| 3 | Eligible quality, input pT above 200 GeV; unchanged; high-pT prescription open |
| 4 | Invalid scale/resolution parameters or nominal/varied smearing fallback |
| 5 | MC scale applied, but scaled pT outside the 26–200 GeV resolution domain |
| 6 | Unsupported year; input pT retained |

`TriggerMuonMomentumStatus` records the chosen muon's status, or `PAD_VAL`
for an electron. Empty muon slots use `PAD_VAL` as usual.

| `MuonMomentumVariation` | Pass |
| ---: | --- |
| 0 | nominal |
| 1 / 2 | scaleUp / scaleDown |
| 3 / 4 | resolutionUp / resolutionDown |
| 5 / 6 | scaleStatUp / scaleStatDown |
| 7 / 8 | scaleSystUp / scaleSystDown |
| 9 / 10 | resolutionStatUp / resolutionStatDown |
| 11 / 12 | resolutionSystUp / resolutionSystDown |

Each pass has its own skim and totals pickle. Normalize each copy of the sample
using the all-input denominator, which is independent of the muon shift.
Do not concatenate the five copies or sum their repeated denominators.
Existing Condor templates still submit nominal; use the documented CLI options
when producing varied samples. Full processing passes are needed to preserve
entering events; stored shifts on the nominal skim alone cannot do so.

The processor gives muons priority when choosing the trigger lepton. A shifted muon can therefore change lepton flavor as well as pT ordering, jet cleaning and reconstruction. Recompute affected SFs and observables consistently; storing varied pT for the original leading muon alone is insufficient.

Propagation of lepton corrections to MET is **optional in the supplied JMAR prescription** and is not applied in this implementation. PF relative isolation and physical charge also retain their NanoAOD definitions. If MET propagation is adopted for this analysis's W/neutrino reconstruction, apply the opposite vector change to MET once, relative to the documented muon reference, with the same muon variation and a muon set consistent with the PUPPI MET definition. Do not double-count it through Type-1 jet muon subtraction. Record the choice and its validation.

**High-pT correction and the supplied 2024 tables**

The earlier audit incorrectly carried over the generic paragraph saying to leave nominal high-pT muons uncorrected. The supplied [MUO guide's explicit Run-3 section](/isilon/export/home/jhuan166/.codex/attachments/3c9a6841-eca9-4a35-8cca-93ee9459f8b6/corrections.md:386), reinforced by its Run-2 exception at line 345, recommends applying the **GE bias correction** for Run 3. That era-specific recommendation supersedes the generic paragraph for this audit.

The supplied [high-pT presentation](/isilon/export/home/jhuan166/.codex/attachments/87295dc4-2e4c-41fb-99e0-81bb14c406a3/highptmuons.pdf), L. Thomas for EXO-25-021, 22 March 2026, closes the missing-table request. All 24 pages were read, with the formulas and tables inspected as rendered pages. **The GE tables are on PDF pages 11 and 16. Page 12 shows medium-pT additive biases for comparison**, so the original `#page=12` link should not be interpreted as identifying the GE table itself.

| Part of the presentation | What it establishes |
| --- | --- |
| Page 9 | All momenta in the GE study are TuneP. The illustrated bias convention is `q/pT -> q/pT + kappa_b`. The revised measurement has a phi-dependent first stage followed by an eta-dependent residual stage. |
| Pages 10–11 | The first stage uses single-muon data versus a data template averaged over phi and mirrored eta. Its selection includes `HLT_Mu50`, high-pT ID, `pfIsoId >= 5`, and TuneP pT above 200 GeV. The 2024 map has six phi rows and ten signed-eta columns. Fit axes on page 10 identify inverse TeV as the bias unit. |
| Pages 14–16 | The second stage compares dimuon data with a DY/diboson/ttbar MC template after the first correction. Its 2024 result consists of ten eta parameters, repeated across phi in the plot. These repeated cells are not 60 independent measurements. |
| Pages 17–20 | The demonstrated correction is **stage 1 applied to data**, compared with the original TuneP value, with boosted-Z and dimuon-spectrum checks. These figures do not validate applying the same bias to ordinary MC `Muon_pt`. |
| Page 24 and the supplied MUO guide | The March talk proposes using the measured bias as a correction. The guide's explicit Run-3 recommendation is the stronger recommendation-level evidence; the talk alone is not the final complete application specification. |

The [2024 table transcription](/isilon/export/home/jhuan166/Vcb/Calib_ChargeTagger_JH/docs/muon-ge-2024-tables.json) records all 60 first-stage values/errors and all ten second-stage values/errors with the PDF hash, units, axis order and precision limits. Each of the 120 plotted cell assignments was checked against PDF coordinates; all six copies of the second-stage eta vector agree. The signed-eta edges read from the plots are `[-2.4, -2.1, -1.6, -1.2, -0.8, 0, 0.8, 1.2, 1.6, 2.1, 2.4]`, and the phi edges are `[-pi, -2*pi/3, -pi/3, 0, pi/3, 2*pi/3, pi]`. First-stage values span **−0.173 to +0.153 TeV⁻¹**; second-stage values span **−0.051 to +0.037 TeV⁻¹**. This documentary transcription preserves the slides' three-decimal precision; it is not a production correctionlib payload.

**Sign and units.** Taking the stated convention to mean `(q/pT)_biased = (q/pT)_reference + kappa_b`, removing that bias from data is the algebraic inverse:

\[
p_{T,\mathrm{data,corr}}=\frac{p_{T,\mathrm{TuneP}}}{1-q\,p_{T,\mathrm{TuneP}}\,\kappa_b/1000},
\]

where pT is in GeV and the tabulated bias is in TeV⁻¹. This formula is a derivation from the displayed convention, not a supplied executable helper. Check that any eventual map/helper uses the same bias convention. If both stages are adopted as biases to remove, sequential curvature subtraction is equivalent to using their sum; this algebra does not establish whether the final prescribed nominal correction should use both stages. Page 17 explicitly demonstrates only stage 1.

**Consequence for this processor.** A data-corrected high-pT convention calls for a consistent TuneP definition in data and MC, data-side bias removal, and MC resolution/uncertainty treatment appropriate to that reference. The deck does not support adding the nominal data bias to MC in that convention. In the fixture all 330 selected high-pT muons have `highPtId == 2`, but **27 have `tunepRelPt != 1`** (minimum 0.9921875). Thus the available TuneP pT can be formed from raw `Muon_pt * Muon_tunepRelPt`, but its use changes the momentum definition for those muons and requires selection, PF isolation/MET and charge-sensitive validation. The efficiency-regime guidance does not mandate switching SF sets event by event. Record and validate the high-pT momentum choice before integrating a GE branch.

**What the tables do not settle.** They print fit uncertainties but do not give a full statistical/systematic decomposition, inter-bin or inter-stage covariance, a final nuisance implementation, or an explicit production choice between stage 1 alone and both stages. The first stage shares a data template across bins, and the second follows the first, so treating every entry and both stages as independent is not established. Obtain the final application prescription or maintainer clarification for these choices; no repeat upload of this deck is needed. The page-14 tracker-isolation inequality is also inconsistent with the earlier isolation description and should not be copied into this processor's selection.

**High-pT resolution.** Page 7 adds a useful 2024 precedent: EXO-25-021 reports extra **15% MC smearing** motivated by boosted-Z widths and describes the strategy as blessed by MUO POG for 2024. It supplies neither a standalone `sigma(pT, eta)` parameterization nor validation for this processor's ordinary-momentum, PF-isolated selection. The broader [2024 high-pT resolution guidance](/isilon/export/home/jhuan166/.codex/attachments/3c9a6841-eca9-4a35-8cca-93ee9459f8b6/corrections.md:581) remains preliminary and asks for closure in the analysis phase space before choosing extra smearing or non-closure uncertainty. Treat the 15% as an analysis precedent to test, not a universal replacement for that guidance. If interpreted as a 15% increase of resolution width implemented with independent Gaussian noise, the extra width is `sqrt(1.15**2 - 1) * sigma_MC`, about `0.568 * sigma_MC`; it is not a 15% shift of each pT. The guide's separate 10% uncertainty proxy also concerns resolution width. Do not import 2022/2023 polynomial coefficients as a 2024 result. Three fixture muons exceed 500 GeV, reaching 656.26 GeV; the additional scale-bias impact check still applies.

GE bias removal itself reduces the high-eta Z-peak width in the presentation (page 19). Therefore determine the residual data/MC resolution difference **after the chosen GE treatment**, before adopting the 15% smearing benchmark. Combining an unchanged smearing amount with a newly narrowed data reference could oversmear MC; the appropriate amount requires that closure comparison.

**Validation and remaining work before closing the full finding**

1. **Implemented and checked:** 191 unit tests and 18 subtests pass, including the pinned nominal and residual-K reference, both Crystal Ball tails and tracker-layer edges, statistical/systematic combination, data behavior, empty/missing inputs, domain boundaries, fallback visibility, chunk/event/object ordering and entering events through the real trigger selection. Changed implementation/test files pass lint; repository-wide lint still reports two pre-existing `B905` errors in `tests/test_objects.py`.
2. **Full integration completed:** all 208,780 fixture events were processed in nominal and four total shifted passes with weight systematics enabled. The nominal skim retains 59,537 events (24,925 electron and 34,612 muon), versus 59,575 before correction; 38 events leave and one common event changes from a muon to an electron trigger. Each pass retains entering events and recalculates weights. Normalization totals are identical across all five passes. The nominal baseline was regenerated through `tests/test_run.py`, with 734 columns and 5,420,807 jet-tagger/charge comparisons passing. The systematics-enabled passes each have 752 columns.
3. Validate the dimuon Z-peak mean and width in data versus corrected DY MC, including charge, eta, phi and pT dependence, following the notes' control-region approach. Study any high-pT non-closure in suitable data and MC. A single signal fixture cannot supply these data/MC checks.
4. Record the adopted TuneP/data-correction convention, which GE stages are applied, any boundary treatment and the final nuisance model before calling the full momentum issue resolved. Existing skims require reprocessing for corrected acceptance; an event-weight rescaling cannot supply the missing kinematics or recover lost events.

| Muon pass | Selected events | Entering versus corrected nominal | Leaving versus corrected nominal |
| --- | ---: | ---: | ---: |
| nominal | 59,537 | — | — |
| scaleUp | 59,538 | 1 | 0 |
| scaleDown | 59,537 | 0 | 0 |
| resolutionUp | 59,533 | 0 | 4 |
| resolutionDown | 59,541 | 4 | 0 |

All 34,836 saved nominal muons match the raw pT and physical charge of their
input NanoAOD index. Coverage counts are 34,423 calibrated, 83 below range and
330 above range, with no saved numerical fallback or scale-only cases. Of the
trigger muons, 34,282 are calibrated and 330 are above range. High-pT momenta
and shifts remain equal to input in every pass. Detailed reference/SF checks
and migration metrics are in `muon_momentum_implementation` in the audit metrics.
These signal-fixture results do not supply collision-data closure.

An independent application of the pinned public nominal helper agrees for all
34,423 calibrated saved muons, with maximum absolute pT difference
`1.38e-11 GeV`. Across the five passes, 519,183 muon SF evaluations agree with
the official efficiency payload evaluated at the chosen active pT. Matching
events by `(run, luminosityBlock, event)`, every one of the 734 nominal columns
is identical with weight systematics enabled or disabled; file row order can
differ between runner invocations.

**Access status and material still needed**

| Link | Observed access on 12 September 2026 | Need |
| --- | --- | --- |
| [MUO momentum-correction guide](https://muon-wiki.docs.cern.ch/code/ptcorr/) | HTTP 401 | The supplied PDF already covers the main prescription. A newer copy is useful only if its guidance has changed. |
| [MUO correction recommendations](https://muon-wiki.docs.cern.ch/guidelines/corrections/) | HTTP 401 | The supplied markdown already covers the medium/high-pT guidance discussed above. |
| [High-pT presentation with 2024 GE tables](https://indico.cern.ch/event/1665380/contributions/7001589/attachments/3243397/5786110/highptmuons.pdf) | Historical CERN SSO redirect; **the supplied PDF has now been read** | Table-access request closed. The GE maps are on pages 11 and 16; remaining application/correlation questions are described above. |
| [Earlier GE-method presentation](https://indico.cern.ch/event/1648086/contributions/6926843/attachments/3216713/5734489/muonpogtalk.pdf) | CERN SSO redirect in the earlier access check; the web reader remains unable to open it | Supplementary source that may help with the remaining application/uncertainty details; its content has not been read. |
| [MuonScaReKIT](https://gitlab.cern.ch/cms-muonPOG/muonscarekit) | HTTP 200; source files readable | No upload needed. |

The 26–200 GeV processor implementation, pinned payload, separate variation passes and regression baselines are now supplied. Existing production files were not rewritten. High-pT prescription, the below-range acceptance limit and data/MC closure remain explicit analysis work; the GE tables remain a documentary transcription, not an applied MC correction.
