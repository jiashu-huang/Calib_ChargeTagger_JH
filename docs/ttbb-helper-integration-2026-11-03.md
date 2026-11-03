# TTBB production and matching-report integration

**Passed:** software validation and the complete Condor pilot. The frozen
processor/helper commit is `47c4169`. Full production has not been submitted.

This follow-up merges the separate TTBB production/report work at `d580296`
into `codex/cms-c1-integration-20261103`, whose prior checkpoint is `8bf0156`.
The processor, object corrections, truth definitions and normalization library
remain byte-identical to that integration checkpoint. The optional matching
module is retained from the TTBB branch without changing its definitions.

## Changes

- Replace the legacy clipped-weight checker with source-based validation of
  the version-3 prescription: all 49 normalization fields, PDF member values,
  top-pT factors and joint sums, signed scale/shower weights, uncapped PU, and
  required total/component lepton alternatives.
- Require a systematic B0 reference from the integrated processor. Compare
  every column and normalization field and check weight/PDF metadata.
- Pin the pilot's output schema, weight prescription and PDF layout for
  production workers. Use a new campaign format and destination.
- Generate the matching counts and all six report/plot files during the pilot
  as well as finalization. Pin these artifacts and the normalized pilot ROOT
  in the success record. A normalization rerun must preserve the ROOT bytes.
- Archive incomplete pilot output before a retry. Preserve all prior campaigns
  and input products.

The earlier TTBB campaign has completed using its frozen `d580296` code:
2,258 files, 44,323,128 input events and 8,013,107 selected events. Its output
is preserved as a legacy comparison; no jobs need stopping for this merge.

## Validation checkpoint

The updated weight checker passes on the integrated TTBB reference: 22,176
input events and 4,055 selected events. It verifies 6,712 negative scale ratios,
1,369 ratios above four, and one nominal pileup factor above ten. These values
would expose the legacy clipping assumptions. All 49 input totals pass,
including every PDF and joint top-pT total.

Repository lint and all 445 tests plus 22 subtests pass. The complete
208,780-event calibration fixture retains 59,712 events, with the same 809
columns and all three committed baselines unchanged. The jet-tagger check
passes 5,435,070 comparisons with no differences or unexplained missing jets.
All 49 existing files under `src/` and the normalization/validation entrypoints
remain byte-identical to `8bf0156`.

The unchanged report module also passes on the three integrated systematic
B0 pilot skims. Histogram counts, including underflow/overflow, account for
every event in each matched population:

| Source | Selected | Fully matched | Hadronic-top matched | Hadronic-top only |
|---|---:|---:|---:|---:|
| TT2Q | 4,050 | 1,595 | 1,926 | 331 |
| TTCB | 4,703 | 1,705 | 2,063 | 358 |
| TTBB | 4,055 | 1,438 | 1,794 | 356 |

The first frozen Condor pilot, job 7651193.0 at `002ee54`, reached the reference
comparison but failed its bitwise check on the twelve muon component weights.
A complete column audit found no other event-column differences and identical
normalization fields. The largest relative discrepancy was 5.16e-16. Coffea's
`Weights.partial_weight` iterates a Python set, so multiplication order can
change between processes. The reference check now allows 16 float64 epsilons
relatively, with zero absolute tolerance, for these twelve products only.
Tests require exact PDF values and reject larger component differences. The
processor itself is unchanged; the failed campaign is preserved.

## Passed Condor pilot

Job **7651194.0** ran the newly frozen `47c4169` source on one complete EOS
input and exited with code 0. The campaign is stored at
`/isilon/export/home/jhuan166/Vcb/Calib_ChargeTagger_JH/outputs/b0-ttbb-cms-c1-pilot-20261103-r2`.

| Check | Result |
|---|---|
| Input coverage | 22,176 events; certified source size, checksum and UUID verified |
| Selection | 4,055 events; 1,347 columns before `finalWeight` |
| Reference comparison | All columns agree; only the twelve component products use the documented rounding tolerance |
| Normalization | All 49 fields agree exactly with the reference and pass input-based arithmetic checks |
| Output validation | 149 passed, zero failed |
| Normalization rerun | ROOT bytes unchanged |
| Fully matched | 1,438 |
| Hadronic-top matched, inclusive | 1,794 |
| Hadronic-top only | 356 |
| W-pair matched | 2,243 |
| Report artifacts | Text, JSON and both W/top plot selections in PNG and PDF |

All matching counts and mass-histogram bins agree exactly with the independent
integrated reference report. Frozen source, configuration, schema, metadata,
normalized ROOT and report hashes were rechecked after completion. The final
software suite passes 445 tests plus 22 subtests; lint passes. Only the pilot
was submitted, and no full `production.dag` was generated.

The [machine-readable record](ttbb-helper-integration-2026-11-03-validation.json)
contains the source hashes, both pilot attempts, Condor exit status, input and
output identities, arithmetic checks, population counts, report paths and logs.
The next production step is an explicit launch using this passed frozen
campaign; the original EOS NanoAODs and certified C1 truth remain reusable.

See [TTBB production](ttbb-b0-production.md) for the execution and retry
contract, and [matching reports](matching-report.md) for population definitions.
