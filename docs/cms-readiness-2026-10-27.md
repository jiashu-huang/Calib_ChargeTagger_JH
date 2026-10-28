# 2024 CMS readiness — 27 October 2026

**Status: substantial 2024 MC coverage, with identified physics limitations.
Do not describe this processor as fully validated against CMS recommendations.**
The supported scope is Summer24 MC, AK4 PUPPI jets and the single-lepton skim.
The [normalization integrity follow-up](normalization-integrity-2026-10-27.md)
corrects signed/zero-weight validation and stale-output handling without
changing event selection, physics weights or prescription version 3.
The latest [top-pT follow-up](top-pt-normalization-2026-10-27.md) introduces
weight prescription version 3, preserving all-input and joint normalization
sums plus explicit validity/event counts. The muon/payload implementation and
validation below record the preceding version-2 stage.
This record is the current follow-up to the [September audit](audit-2024-mc-2026-09-11.md),
[cross-check](audit-crosscheck-2026-09-23.md), [information-preservation changes](skim-realignment-2026-10-27.md)
and [weight prescription version 1](weight-realignment-2026-10-27.md).

All changes and validation outputs are in the isolated BRUX copy
`Calib_ChargeTagger_JH-realignment-20261027`. The live checkout and production
outputs are unchanged. `realignment.patch` contains the cumulative changes;
`snapshot-provenance.json` identifies the source snapshot. Python checks in
this copy require `PYTHONPATH="$PWD/src"` with the `ttbar` environment because
the shared editable installation still points to the live checkout.

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

`WeightPrescriptionVersion=2` and ROOT/pickle metadata identify this change.
The validator requires the twelve components in version-2 systematic output.
Version 1 remains readable as its own campaign; merge and normalization
reject mixtures. Nominal event weights are unchanged by this follow-up.
Adopting it requires regenerating systematic outputs, then consistently
rebuilding their downstream products.

The MUO fallback is fixed to the dated June release and the loader checks
SHA-256 of decompressed content for both bundled and fallback inputs.
A changed or missing payload stops the run. Detailed provenance is in the
[lepton-payload README](../src/vcb/corrections/README.md).

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
the [jet-payload README](../src/boostedhh/corrections/README.md).

## Validation

The [machine-readable record](cms-readiness-2026-10-27-validation.json)
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

The TTBB pilot uses the existing `weight_norm=1` fallback. Its normalized
test yield is an arithmetic check, not a physical yield prediction.
This follow-up reruns nominal kinematics with weight systematics; the full
JES/JER/lepton momentum pass validation remains the evidence recorded in
[the existing kinematic validation](jet-met-electron-variations-2024-validation.json).

## Remaining work before a physics-ready claim

| Item | Current limit and required closure |
| --- | --- |
| High-pT muons | Ordinary-momentum corrections cover 26–200 GeV. The signal test has 330 trigger muons above 200 GeV, including 3 above 500 GeV; TTBB has 31 and 1. Resolve the TuneP/GE application and uncertainty model, plus boundary migration treatment. Supplied GE tables alone do not establish how to correct ordinary MC momenta. |
| Muon efficiency closure | Study impact-parameter efficiency versus pileup and isolation efficiency in high-jet/heavy-flavour environments. Z-based SF arithmetic is not a substitute for these checks. |
| Physical normalization | Fix and document the TTBB cross section/filter convention and overlap treatment with inclusive ttbar. Resolve the W branching-fraction and reference-Vcb conventions identified by the cross-check. |
| Top-pT and nuisance model | Version 3 now preserves all-input and joint normalization sums. Choose and validate the nominal top-pT model, then complete correlations and the final PDF/alpha-S/theory model downstream. Tagger SFs need assessment if downstream selections or categories use them. |
| Jet charge association | Guarantee JetQk-to-Jet identity upstream or supply a verifiable mapping. The current length guard and statistical checks do not provide that guarantee for every production. |
| Collision data and closure | Implement the certified-lumi mask, run-dependent data JEC/MET and the intended data workflow, then validate corrected simulation against collision data. 2024 data is currently blocked explicitly. |

Public CMS guidance, the official CVMFS release contents and previously
supplied POG documents were used. Some current CERN-protected recommendation
pages could not be read in this session. No blanket claim is made that every
current POG requirement has been independently verified. Payload agreement
and successful regression tests establish implementation evidence within the
stated scope; they do not close the analysis studies above.
