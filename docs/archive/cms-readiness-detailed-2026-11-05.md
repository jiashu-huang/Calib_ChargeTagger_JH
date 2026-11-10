> Archived on 5 November 2026. Replaced by the shorter [current CMS readiness report](../cms-readiness-2026-10-27.md). This preserves the detailed review and historical validation; its production status is a dated snapshot.

# 2024 CMS readiness

**Reviewed: 5 November 2026. Status: the supported MC implementation and
three-source pilots are validated; full-population C1 validation and physics
closure remain incomplete.** This is not a claim of full validation against
all CMS recommendations. The original filename is retained for existing links.

The supported scope is Summer24 TT2Q, TTCB and TTBB MC with AK4 PUPPI jets,
using either the calibration or B0 profile. Collision-data processing is
explicitly rejected. B0 input readiness, a complete experimental uncertainty
model and validation against collision data are separate requirements.

## Current release

Work in `/isilon/export/home/jhuan166/Vcb/worktrees/calib-cms-c1-integration-20261103`,
on `codex/cms-c1-integration-20261103`. The reviewed HEAD is `1a56399`; changes
since the production commit `0fc83d7` are documentation only. The current
processor uses **weight prescription 3** and **B0 schema 2**.

The integrated release includes the CMS trigger and weight corrections,
muon total/component uncertainties, PDF-member preservation, all-input and
joint top-pT normalization sums, and the signed/zero-weight normalization
checks. It also includes the frozen production helper, matching reports,
certified C1 truth and the November 4 hadron-flavour b-jet labels. See
[CMS/C1 integration](../cms-c1-integration-2026-11-03.md),
[normalization integrity](../normalization-integrity-2026-10-27.md),
[top-pT normalization](../top-pt-normalization-2026-10-27.md) and
[C1 schema-2 readiness](../c1-input-readiness-2026-11-04.md).

The additional lepton impact-parameter cuts were also removed, following
AN-25-214. The older audit's concern about applying standard SFs with those
extra cuts is closed; efficiency studies for the actual selected lepton
population remain separate analysis work.

The November 4 production was prepared from this checkout at `0fc83d7`.
Workers execute each campaign's frozen `code/` copy. Its output location under
`Calib_ChargeTagger_JH/outputs/` does not make the older checkout its source.
This readiness review changes documentation only, including the evidence record;
it does not change frozen production code or outputs.

Use `PYTHONPATH="$PWD/src"` with `micromamba run -n ttbar` when checking this
worktree. The shared environment's editable install otherwise imports the
older `Calib_ChargeTagger_JH` checkout.

## Validation checked on November 5

The [review evidence](../cms-readiness-2026-11-05-validation.json) records the
checkout, commands, content hashes and production receipts. The checks below
were run for this review; the later table preserves historical October results.

| Check | Result and scope |
| --- | --- |
| Unit tests | 474 passed and 22 subtests passed; three dependency deprecation warnings. The tested import path is this checkout's `src/`. |
| Lint | `ruff check src/vcb tests condor` passes. Vendored code remains excluded. |
| Official payload comparison | All nine reviewed bundles have the same decompressed SHA-256 as their CAT `latest/` counterparts visible on BRUX: electron reco/ID, trigger and scale/smearing; muon efficiency and momentum; JEC/JER, veto map and Jet-ID; and C–I pileup. This verifies content, not analysis closure or every protected POG recommendation. |
| Frozen production identity | All 60 pinned files match both this checkout and the frozen copy for each of TT2Q, TTCB and TTBB. Results and hashes are in the review evidence. |
| TTCB completion validation | The read-only C1 source check passed: completion receipt, certified coverage, pilot gate, publication, matching-report hashes, population counts and common schema. This does not rerun every source event. |
| Real-file and kinematic evidence | The November 3 integration and November 4 schema-2 pilot records remain the real-file evidence. No new full-fixture or 65-pass kinematic production was run for this documentation review. The active production uses nominal kinematics with weight variations. |

The [November 4 production record](../c1-b0-production-2026-11-04.json) documents
three complete-file Condor pilots, each passing 149 campaign checks,
normalization rerun and matching-report checks. Schema-2 B0 outputs have
1,373 columns for TT2Q/TTCB and 1,371 for TTBB before `finalWeight`; the
source-specific PDF member counts explain the difference. The 808-column
version-2 results below are historical calibration results, not this schema.

## Production snapshot on November 5

The submitted workflow is DAG **7651230**, rooted at
`/isilon/export/home/jhuan166/Vcb/Calib_ChargeTagger_JH/outputs/c1-b0-20261104`.
It covers 13,737 files and 548,444,645 input events. Queue and receipt observations
are timestamped in the review evidence; they are a snapshot, not a live monitor.

| Source | Current evidence |
| --- | --- |
| TTCB | Completion receipt dated November 5, 14:20 UTC: all 465 files and 19,823,340 input events; 2,779,586 selected events. The source's population and matching artifacts are checked. |
| TTBB | Finalizer running; a population audit exists, but no completion receipt was present. Do not count an intermediate audit as finalized output. |
| TT2Q | Worker jobs remain queued; no completion receipt or population audit was present. |
| Overall C1 | `c1-input-readiness.json` is absent. All three finalizations and the common-input audit must pass before declaring C1 complete. |

The provisional TTBB effective semileptonic cross section is already registered
as **16.011655167690346 pb**. The older `weight_norm=1` pilot below is not the
normalization of this production. The adopted rate includes its decay convention;
do not apply another W branching fraction. It does not resolve inclusive/dedicated
sample overlap, additional-b-jet origin categories or DPS. Total hadron-flavour
b-jet counts and the unrestricted extra-b-quark count do not supply that source
partition. See [normalization and overlap](../b0-input-readiness-2026-10-28.md#ttbb-normalization-and-overlap).

## October 27 implementation evidence

The sections through the historical validation table below describe the original
muon/payload follow-up in `Calib_ChargeTagger_JH-realignment-20261027`, at weight
prescription 2. That work was subsequently integrated into the current checkout
and prescription 3. Its [original validation record](../cms-readiness-2026-10-27-validation.json)
is preserved unchanged; its old location, counts and schema are historical.

## Changes in this follow-up

### Muon efficiency uncertainties

The official `2026-06-18/muon_Z.json.gz` payload describes `systup/down` as
combined statistical and systematic alternatives. For the Tight ID and Tight
PF-isolation corrections this is correct. For
`NUM_IsoMu24_DEN_CutBasedIdTight_and_PFIsoTight`, those categories instead
return nominal ± `syst`. The old trigger variation therefore omitted `stat`.

The processor now evaluates the released `nominal`, `stat` and `syst` fields
and forms nominal ± sqrt(stat² + syst²) for all three steps. It uses the
released aggregate `syst`; it does not invent a new combination of AltBkg,
AltSig or other subcomponents. For example, at signed eta 0.5 and pT 45 GeV,
IsoMu24 has nominal 0.9723169804, stat 0.0001169212 and syst 0.0005890280.
The total error is 0.0006005202. The supplied MUO efficiency guidance calls
for the statistical and systematic errors to be combined in quadrature.

Under `--save-systematics`, twelve new complete event weights preserve the
components:

```text
weight_muon_{id,iso,trigger}_{stat,syst}{Up,Down}
```

Each replaces one SF by nominal ± its named error, retaining all other
nominal factors and cross section × luminosity. The replacement multiplies
the other factors directly; it does not divide by that SF, so a zero nominal
SF and signed generator weights are handled. Lepton alternatives all use the
nominal all-input normalization denominator. The total and component models
are alternatives for a given step; using both together would double-count
the uncertainty. The skim does not prescribe bin-to-bin nuisance correlations.

`WeightPrescriptionVersion=2` and ROOT/pickle metadata identified this change
at the October checkpoint. Version 3 retains these components and adds the
top-pT normalization contract. The validator requires the twelve components
in version-2 and version-3 systematic output.
Version 1 remains readable as its own campaign; merge and normalization
reject mixtures. Nominal event weights are unchanged by this follow-up.
Adopting it requires regenerating systematic outputs, then consistently
rebuilding their downstream products.

The MUO fallback is fixed to the dated June release and the loader checks
SHA-256 of decompressed content for both bundled and fallback inputs.
A changed or missing payload stops the run. Detailed provenance is in the
[lepton-payload README](../../src/vcb/corrections/README.md).

### Selection and operating scope

- The 2024 jet-veto map is bundled from CAT's dated `2026-07-16` release,
  with a dated fallback and a compressed-file SHA-256 check. The content is
  identical to the former JSON POG map. No map values or selection rules change.
- The same release's Jet-ID payload is bundled as an independent test reference.
  Both Tight and TightLepVeto are checked offline against its decision tree on
  20,000 random jets per working point, including separate boundary tests.
  This verifies the implementation of the released definition, not its
  performance in this analysis.
- Public [CMS-DP-2024-028](https://twiki.cern.ch/twiki/bin/view/CMSPublic/PhysicsResultsDP24028)
  supports an analysis-dependent Tight-with-cleaning exception. Our inference
  is that trigger-lepton cleaning and the need to retain semileptonic
  heavy-flavour jets provide a documented basis for this choice. Cleaning one
  trigger lepton does not establish that all lepton-fake jets are removed.
  Veto-map candidates still use TightLepVeto as prescribed.
- The runner and direct processor reject 2024 collision-data input. That path
  is incomplete without certified-luminosity selection, run-dependent data JEC
  and rebuilt data MET. Object-level data helper tests do not establish an
  operational collision-data workflow.
- The JetQk documentation now states the actual limitation: `updatedPatJets`
  sorts by default, so a positional JetQk-to-Jet match depends on this production.
  Equal lengths alone prove nothing about order. Existing per-jet and
  statistical checks support the audited samples; a common final collection
  or explicit source index is needed upstream to guarantee association.
- The extra-lepton veto continues to be saved, not applied, as requested.
  This preserves heavy-flavour-lepton studies and downstream selection choices.

Jet payload sources and both compressed/decompressed hashes are recorded in
the [jet-payload README](../../src/boostedhh/corrections/README.md).

## October 27 validation

The [machine-readable record](../cms-readiness-2026-10-27-validation.json)
contains comparisons, source-weight checks, payload hashes and pipeline receipts.

| Check | Result |
| --- | --- |
| Unit tests | 308 passed, plus 22 subtests; three existing dependency deprecation warnings. |
| Lint | `ruff check src/vcb tests condor` passes. Vendored code is deliberately excluded. |
| Full nominal integration | 208,780 signal input events; 59,712 selected; 808 columns. The schema and jet round-trip baseline are unchanged. The first-event baseline changes only the prescription version. |
| Jet round trip | 319,710 saved jets and 5,435,070 tagger/charge comparisons; zero mismatches or unexplained missing jets. This checks preservation, not the upstream JetQk association. |
| Full signal systematics | 59,712 events, 941 columns, including 103 PDF members. All twelve component and six total muon alternatives agree with independent evaluation of the dated CMS payload. |
| TTBB systematics | All 10,000 pilot events processed; 2,709 selected in three outputs, 939 columns, including 101 PDF members. The same independent uncertainty checks pass. |
| Unchanged physics fields | Selected identities, nominal weights, kinematics, truth labels and other pre-existing fields are bitwise unchanged in both samples. Only the version field and six muon total-weight branches change. ID/ISO differences are floating-point roundoff; trigger changes restore the missing statistical term. |
| Other weights | Nominal, PU, four shower and six scale alternatives agree with direct source/payload calculations. Raw PDF members match exactly; all-input sums agree within floating-point accumulation precision. |
| Campaign pipeline | TTBB batch validator: 58 checks pass. Actual merge and normalization succeed; merged validator: 23 checks pass, and all 23 pass again after forced normalization. |
| Failure cases | Missing/corrupt pinned payloads, incomplete component sets, mixed prescriptions and unsupported data input are rejected. Zero nominal SFs and negative generator weights are covered. |

The signal skim retains 1,108 events failing the recorded extra-lepton veto.
Muon total-weight differences are checked at relative tolerance 3e-12; the
largest absolute discrepancy from independently computed weights is 5.96e-8
for signal and 2.84e-14 for TTBB, reflecting their different overall scales.

The historical TTBB pilot used the then-existing `weight_norm=1` fallback.
Its normalized test yield is an arithmetic check, not a physical yield prediction
or the normalization of the current production.
This follow-up reruns nominal kinematics with weight systematics; the full
JES/JER/lepton momentum pass validation remains the evidence recorded in
[the existing kinematic validation](../jet-met-electron-variations-2024-validation.json).

## Remaining work before a physics-ready claim

| Item | Current limit and required closure |
| --- | --- |
| High-pT muons | `muon_ss.py` still limits ordinary-momentum corrections to 26–200 GeV and records out-of-range status. Resolve the TuneP/GE application and uncertainty model and boundary migration. The October pilots had 330/31 trigger muons above 200 GeV in signal/TTBB, including 3/1 above 500 GeV; these are not full-production counts. Supplied GE tables do not by themselves define an ordinary-MC correction. |
| Lepton efficiency closure | The extra impact-parameter-cut mismatch is closed. Validate the retained ID/isolation choices in the high-jet/heavy-flavour environment, and confirm the electron-trigger SF eta convention and turn-on coverage identified by the cross-check. Correct payload arithmetic and the fixed Ele30 matching bit do not close those analysis checks. |
| Physical normalization and source partition | The provisional TTBB rate is implemented. Complete the review of its generator/filter convention, define complementary additional-b-jet selections for TT2Q/TTBB and DPS treatment, and settle the W branching-fraction/reference-Vcb conventions. The saved total b-jet counts are not additional-b-jet origin labels. |
| Top-pT and nuisance model | Version 3 preserves all-input and joint sums; top-pT factors remain absent from nominal weights. Choose and validate the nominal model, nuisance correlations and PDF/alpha-S/theory prescription downstream. TTBB's 101-member input has no separate alpha-S members. Assess tagger SFs if downstream selections or categories use them. |
| Jet charge association | `objects.attach_jet_charge` still assumes the JetQk prefix matches Jet ordering. Guarantee identity upstream or provide a verifiable source mapping. The length guard, saved source index and skim round trip do not independently prove the original association. |
| Jet/MET analysis closure | Pinned Jet-ID/veto payload tests and the public cleaning exception support the implemented definitions. Retain analysis checks of cleaning, veto-map occupancy/impact and an independent Type-1 MET comparison with the intended MiniAOD recipe. The earlier kinematic-pass evidence is not full-production or collision-data closure. |
| Collision data and closure | `require_supported_sample` still rejects 2024 data. Implement certified-lumi selection, run-dependent data JEC/MET and the intended data workflow, then validate simulation against collision data. Data support is outside the presently supported MC scope. |
| Complete input population | Finish TT2Q/TTBB finalization and the overall C1 audit. Even a complete C1 receipt will certify input populations, not the physical source combination, C2 dataset assembly or model performance. |

## Recommendation access and limits

The public [CMS-DP-2024-028](https://twiki.cern.ch/twiki/bin/view/CMSPublic/PhysicsResultsDP24028)
page was re-read on November 5 and still allows an analysis-dependent
Tight-with-cleaning choice. Its application to this analysis remains an
inference requiring the cleaning checks above. The nine official CAT payloads
were compared directly with the files visible on BRUX, without changing them.

The [MUO recommendations](https://muon-wiki.docs.cern.ch/guidelines/corrections/)
and pinned [MuonScaReKIT source](https://gitlab.cern.ch/cms-muonPOG/muonscarekit/-/tree/1c7426b5e1d808110e8f4fbfef27e71071ea3c26)
could not be retrieved through the web reader in this review. Their previously
supplied/read evidence remains in the linked momentum and payload records;
this is not a fresh verification of all protected recommendations. The remaining
items above are not closed by matching payload bytes or passing software tests.
