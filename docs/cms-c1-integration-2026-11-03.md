# CMS realignment and C1/B0 integration

This branch combines the corrected 2024 MC processing and weight prescription
from CMS realignment with B0 feature preparation and the C1 truth-production
workflow. It is an integration checkpoint; production has not been restarted.

## Parents and preserved behavior

| Role | Branch | Commit |
|---|---|---|
| Base | `codex/cms-2024-realignment-20261027` | `c19bbb77c3e39a84c767e5cf9d2a17cdaea03d4c` |
| Merged | `codex/c1-truth-preparation` | `64160b016c7268d7edd5eafbdddd95d64f8ef0c2` |
| Included through C1 | `second-pass-corrections-and-selection` | `e5cd178e88cce734f1474755417f3b918dd5beb6` |

The integration branch is `codex/cms-c1-integration-20261103`. Its isolated BRUX
checkout is `/isilon/export/home/jhuan166/Vcb/worktrees/calib-cms-c1-integration-20261103`.
Use `PYTHONPATH="$PWD/src"` for commands in this checkout so the shared editable
installation cannot select another branch. Generated Condor workers already
set their source path to the campaign's selected repository.

The combined processor retains:

- **CMS realignment:** Ele30 filter bit 18, additional-lepton records without
  applying their veto, unclustered-MET fields, uncapped pileup and signed scale
  ratios, PDF/alpha-S member preservation, muon total/component uncertainties,
  top-pT all-input and joint sums, and weight prescription version 3.
- **Normalization integrity:** signed/zero-weight support, complete preflight,
  metadata consistency, and verified normalization reruns. Top-pT factors
  remain optional downstream quantities and are absent from nominal weights.
- **B0:** central jets with pT > 25 GeV and |eta| < 2.4 before the ten-slot cap,
  at least four accepted jets, observable features and masks, exact source
  identity, and greedy distinct assignments at DeltaR < 0.4. Unmatched events
  remain available for classification. Qk sentinel -997 remains valid zero.
- **C1:** complete generator-truth production, unique event alignment within
  each declared native/NanoAOD pair, retained-generator content checks,
  checksum-pinned manifests and payloads, and resumable campaign collection.
- **TTBB rate:** the already approved provisional effective semileptonic cross
  section, 16.011655167690346 pb. Its evidence and limitations remain in
  [B0 readiness](b0-input-readiness-2026-10-28.md#ttbb-normalization-and-overlap).

B0 feature definitions, their schema hash, and both physical truth definitions
remain unchanged. The exact processor commit and weight prescription identify
the changed trigger and weight behavior. Normalization totals still cover all
input events, including events rejected by the additional B0 jet requirement.

## Merge resolution

Twelve files required conflict resolution. The processor and runner combine
both sets of options and checks; the truth builder, loader and tests retain
C1's later safeguards. Documentation preserves the CMS weight contract and
adds the B0/C1 instructions. A duplicated `--truth-label-manifest` declaration
introduced by Git's automatic merge was removed from the Condor CLI.

Fourteen correction, weighting, metadata and normalization implementation files
are byte-identical to CMS realignment. Seven B0/truth/campaign implementation
files are byte-identical to C1. The generator extra-b counting module is
identical in both parents. The three committed calibration regression baselines
remain byte-identical to the realignment parent.

## Validation

Validation passed. The [machine-readable record](cms-c1-integration-2026-11-03-validation.json)
pins the source files, input identities, manifest checksums, commands and results.
Full logs and pilot outputs remain in `outputs/cms-c1-validation/` in the
integration checkout.

- Repository lint passes; 405 unit tests and 22 subtests pass.
- The complete 208,780-event signal calibration fixture retains 59,712 events.
  Every value in all 809 event columns agrees exactly with the saved
  realignment reference: 48,307,008 compared values.
- The calibration jet-tagger check passes all 5,435,070 comparisons with zero
  differences and zero unexplained missing jets.

One complete NanoAOD file from each source was processed in both profiles with
weight systematics enabled and certified C1 truth manifests:

| Source | Input events | Calibration selected | B0 selected | Fully matched, valid W topology |
|---|---:|---:|---:|---:|
| TT2Q | 27,269 | 7,832 | 4,050 | 1,595 |
| TTCB | 33,580 | 9,593 | 4,703 | 1,705 |
| TTBB | 22,176 | 6,292 | 4,055 | 1,438 |

All 49 all-input normalization fields agree between the two profiles for each
source. Independent evaluation from the original input verifies nominal,
scale, shower and PDF sums, including negative and above-four scale ratios.
The selected-event weight, PDF, top-pT and trigger-lepton columns also agree
between profiles. All feature masks, charge sentinel conversions, source
identities, classification labels and greedy assignments pass their checks.
Each source passes the jet-tagger round trip, 149 campaign validation checks,
and a normalization rerun that leaves the ROOT file byte-identical.

PDF layouts remain source-specific: these TT2Q and TTCB inputs contain 103
members and TTBB contains 101. Their systematic B0 skims therefore contain
1,349 and 1,347 columns respectively before `finalWeight`. Freeze the output
schema for each source and weight mode; the B0 feature schema is common.

The independent TTBB check initially divided float32 scale members after
promoting them to float64, producing a relative sum difference below 1e-9.
Using the stored input precision reproduces the inherited realignment behavior
and passes the original tolerances. This correction affected only the validation
script; no processor or weighting code was changed for it.

## Production boundary

The earlier TTBB campaign used `d580296` on
`codex/ttbb-b0-production-20261103`, with the previous trigger/weight behavior.
Its outputs remain comparison material. This merge neither changes those files
nor submits new jobs. To adopt the integrated prescription, process the original
CMSSW_CHARGE NanoAODs again; renormalizing selected legacy skims cannot recover
the revised rejected-event totals, unclipped ratios or missing PDF members.
The completed NanoAOD conversion and certified C1 truth payloads can be reused
with their identity and checksum checks.

At this checkpoint the separate frozen-TTBB production helper and optional
matching-report module were outside both merged parents. Their subsequent
integration is recorded in [TTBB helper integration](ttbb-helper-integration-2026-11-03.md).
The November 3 C1 repair
validator and recovery notes are also uncommitted work in the original C1
checkout; this merge preserves them there without silently adding them.

Before further production, freeze the combined release and pass a final campaign
pilot using its exact source, schema and weight mode. The additional-b-jet
source partition, DPS treatment, high-pT muon prescription, upstream charge
association guarantee and collision-data closure remain the separate physics
limitations recorded in [CMS readiness](cms-readiness-2026-10-27.md).
