# C1: recovery of four TT2Q files

The four TT2Q failures came from **four rejected events**, one per input file.
Each has `RawPuppiMET_pt = infinity` in its source NanoAOD. The stored
`PuppiMET_pt` is finite, which is why checking that branch alone missed the
problem. Rebuilding Type-1 MET uses the raw branch and propagates the infinity.

The processor formerly validated unclustered-MET fields before event selection.
One rejected event therefore stopped its entire input chunk. The failure was
repeatable; all four files exhausted their two automatic retries.

| Input UUID | Source entry | Existing cut that rejects the event | Selected events recovered |
| --- | ---: | --- | ---: |
| `4c82b44a-583a-415c-8759-b965cd436cb0` | 9065 | Single-lepton trigger | 6,625 |
| `62ff5ebe-5072-4f97-9b95-f8edf3d14f34` | 7298 | Single-lepton trigger; also fails lepton and jet cuts | 6,543 |
| `b8dc7d58-d41c-4e70-9de3-161353aeacff` | 10347 | Fewer than four selected jets in B0 | 6,592 |
| `d06d0183-00f1-4cdf-9cb9-509ee1f21479` | 4230 | Single-lepton trigger | 6,509 |

## Fix

Build and validate the saved unclustered-MET fields **after the existing event
selection**. Selected events still require finite MET. All-input generator
weights and normalization totals are computed before selection, as before.
The event cuts, observable definitions, truth labels and B0 schema are unchanged.

This recovery applies to the production's **B0 selection**. In another profile,
an event that passes selection with invalid MET must still fail validation.

## Validation

- All four complete files pass B0 and weight validation: **176,880 input
  events and 26,269 selected events**. The four nonfinite entries are absent
  from the selected outputs and remain represented in all-input totals.
- The healthy TT2Q pilot agrees with its original output for all **1,373
  branches** and normalization values. The existing allowance for rounding in
  twelve muon component-weight products remains unchanged; the maximum
  observed relative difference is `5.12e-16`.
- Injecting infinite raw MET into a known selected event still stops the skim.
- **489 tests and 22 subtests pass**, and lint passes.
- The standard **208,780-event calibration regression** passes with no changes
  to its three tracked baselines.

The [validation record](c1-met-recovery-2026-11-06-validation.json) pins the
source fingerprints, event identities, recovered output hashes and evidence.

## Production provenance and continuation

The original frozen processor is
`0fc83d74807c89d18e0f63df3a0cddbf9ea6cbdf`. Keep that snapshot and successful
outputs intact. A separate recovery snapshot and `TT2Q/recovery.json` identify
the replacement processor for the four recovered files. Each recovered worker
record names that revision and the recovery manifest hash.

Finalization verifies the source-code differences, recovery evidence, exact
file coverage and worker receipts. It records the original and recovery
versions in the completion record. The combined C1 gate verifies that record;
it cannot treat an undeclared recovery as an ordinary completed campaign.

Finalization commands allow up to 24 hours each to accommodate TT2Q's 11,014
files. TT2Q normalization and matching reports must finish before the combined
C1 audit can pass. C2 dataset assembly and training remain separate work.
