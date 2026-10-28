# 2024 MC weight realignment — 27 October 2026

This records weight prescription version 1. The later
[MUO uncertainty/readiness follow-up](cms-readiness-2026-10-27.md) defines
version 2 and the current output schema. Counts and validation below describe
the version-1 stage; they are retained as its evidence.

This follows the [skim information realignment](skim-realignment-2026-10-27.md)
in the same isolated BRUX working copy. It removes two analysis-imposed caps
that changed the released weight prescriptions. Event selection, truth labels,
object corrections and the decision to retain extra-lepton events are unchanged.
The live checkout and production output have not been modified.

## Applied prescription

- **Pileup:** evaluate the released nominal/up/down factors without capping
  them at 10. The payload's `flow="clamp"` handles its input limits; the extra
  `[0,99]` input clamp is removed. Nonfinite inputs or returned factors fail.
  The bundled 2024 payload matches the official dated CVMFS release in
  decompressed content. Its largest nominal/up factors are about 73.45/489.94;
  these were previously suppressed.
- **LHE scales:** preserve signed, zero and large ratios. The six saved
  `(muR,muF)` pairs remain `(0.5,0.5)`, `(0.5,1)`, `(1,0.5)`, `(1,2)`, `(2,1)`,
  `(2,2)`. Nine-member inputs are divided by central member 4; eight-member
  inputs omit that member. Every event must have the declared length, every
  member must be finite, and a zero central member fails. These alternatives
  remain available without `--save-systematics`.
- **Parton shower:** preserve the existing branch names and values.
  `ISRPartonShowerUp`/`FSRPartonShowerUp` mean muR x2; `Down` means muR x0.5.
  They describe scale changes, not a radiation-up/down convention. Four finite
  members are required for each event; malformed vectors no longer silently
  produce unity alternatives. Zero and negative ratios remain valid.
- **Input identification:** before processing, every 2024 MC file's PS title
  and every relevant ttbar/HH scale title must identify the supported order.
  Unknown orderings or mixed file layouts fail. Vector lengths alone do not
  establish the meaning of the weights.
- **Required lepton corrections:** missing bundled and fallback payloads now
  raise an error. The 2024 runner checks them before the event loop. The
  bundled-first/fallback loading order is retained.

The pileup convention follows the released LUM payload. The scale mapping and
shower interpretation follow the actual NanoAOD branch titles in the signal
fixture and TTBB pilot. The reasons for removing the caps, including the
supplied luminosity guidance and AN-25-214 normalization prescription, were
recorded in the [September audit](audit-2024-mc-2026-09-11.md) and
[cross-check](audit-crosscheck-2026-09-23.md). This change introduces no new
cross-section, branching-fraction or nominal top-pT convention.

## Output and compatibility

`Events/WeightPrescriptionVersion=1` identifies the new convention. A
`WeightMetadata` tree stores a UTF-8 JSON record with the PS/scale input titles,
member mapping, scale-label meaning and uncapped-weight rules. The accumulator
pickle carries the same record in `weight_prescriptions`. Empty selections
retain the ROOT record and all-input normalization sums.

The metadata writer checks every chunk. Merge and normalization check every
ROOT file and every metadata row, including rows concatenated by `hadd`.
The campaign validator checks the ROOT record against the accumulator pickle
and normalization summary, and checks that all saved weight alternatives are
finite. A forced normalization rewrite preserves both `WeightMetadata` and
`PdfMetadata`.

A campaign made entirely under the old convention remains readable by merge
and normalization. Combining old output with version 1 is rejected. Adoption
requires fresh processing from NanoAOD and fresh all-input denominators;
selected events alone do not reconstruct the lost scale ratios or rejected
events' revised pileup contributions. The default schema now describes version 1.
2024 processing uses `skipbadfiles=False`; the unsupported Dask path fails
because it cannot persist this metadata. Local and Condor processing use the
same supported writer.

Normalization continues to use signed sums over all processed input events.
Lepton efficiency factors stay outside these denominators. Changing pileup
can change the selected yield through acceptance, despite preserving inclusive
normalization. `normalize.py` still adds only nominal `finalWeight`; systematic
alternatives require their respective global denominators downstream.

## Validation

Measured results and the official payload hash are in the
[machine-readable record](weight-realignment-2026-10-27-validation.json).

| Check | Result |
| --- | --- |
| Unit tests and lint | 296 tests and 22 subtests pass; lint passes. Three existing dependency deprecation warnings. |
| Full nominal integration | 208,780 signal inputs; the same 59,712 selected events and 1,108 recorded veto failures as before this weight change. Jet-tagger round trip passes. |
| Event contents | All 798 pre-existing fields outside the nine affected weight columns are bitwise unchanged. Nominal weight and its PU diagnostic change for three selected events. |
| Signal weight validation | Full 208,780-event fixture with systematics. Nominal, PU, four PS and six scale alternatives agree with direct source/payload calculations; all 103 raw PDF members match input exactly. All-input sums agree within floating-point accumulation precision. |
| Removed signal clipping | 12 nominal PU factors and 935 upward factors exceeded 10. Scale clipping altered 536 input events, including 173 selected events; 852 negative and 91 above-four scale-ratio entries are now preserved. |
| TTBB validation | Full 10,000-event pilot; 2,709 selected events in three ROOT outputs. All weights and sums pass the same independent checks, including all 101 PDF members. |
| Campaign pipeline | 58 batch checks pass; actual merging and nominal normalization pass. Merged validation passes 23 checks, and passes all 23 again after forced normalization. |
| Failure paths | Tests reject missing lepton payloads, nonfinite/malformed weights, unverified titles, zero scale central values, missing metadata and mixed old/new conventions; empty-output metadata is retained. |

The nominal schema now has 808 columns. Systematic signal and TTBB outputs
have 929 and 927 columns respectively. The first-event/schema baselines gain
only the version field; the jet round-trip report is unchanged. The complete
event comparison identifies only the expected weight differences.

The TTBB pilot still uses the documented `weight_norm=1` fallback. These tests
validate arithmetic and information flow, not its physical cross section or
overlap treatment with inclusive ttbar. Branching-fraction choices, high-pT
muon treatment, remaining closure/jet-ID questions and collision-data support
remain separate audit work.
