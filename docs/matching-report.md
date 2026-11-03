# Optional matching report and mass plots

After `Calib_ChargeTagger_JH` finishes, run this separate module on its
processed ROOT skims. It counts the saved jet–parton assignments and plots
the reconstructed hadronic W and top masses. It does not run the processor,
redo matching, change jet corrections, or impose additional selection cuts.
It works for TT2Q, TTCB and TTBB with the same saved-branch schema.

## Run

From the repository root, with the package and diagnostics dependencies
installed as described in the main README:

```bash
micromamba run -n ttbar python -m vcb.postprocessing.matching \
  --files '/path/to/processed/roots/*.root' \
  --label TTBB --outdir outputs/ttbb-matching-report
```

To compare two samples on the same plots:

```bash
micromamba run -n ttbar python -m vcb.postprocessing.matching \
  --sample 'TT2Q=/path/to/tt2q/nano_skim_*.root' \
  --sample 'TTBB=/path/to/ttbb/nano_skim_*.root' \
  --outdir outputs/tt2q-ttbb-matching-report
```

Quote globs when using `--sample`. Repeat a sample label to add another
directory or file to that sample. `--files` also accepts explicit files,
local directories (their immediate `*.root` files), and local globs. Remote
`root://` inputs must name individual files and need working read credentials.
Use nominal skims from one selection profile; do not mix systematic passes.

The output directory must be new or empty. Reading is streamed in chunks of
50,000 events; `--step-size` changes this without changing the result.
Only the columns needed for the report are read. The ROOT files remain unchanged.
For an isolated checkout, set `PYTHONPATH="$PWD/src"` before the command so
the editable installation cannot select a different checkout.

## Counts and denominator

The four saved indices are `GenHadBJetIdx`, `GenLepBJetIdx`,
`GenHadQ1JetIdx`, and `GenHadQ2JetIdx`. An index of `-1` means unmatched;
nonnegative indices refer to distinct real saved reconstructed jets.

| Report item | Requirement |
|---|---|
| Fully matched | HadB, LepB, HadQ1 and HadQ2 matched |
| Hadronic-top matched, inclusive | HadB, HadQ1 and HadQ2 matched, irrespective of LepB |
| Hadronic-top only | Hadronic-top matched and LepB unmatched |
| W-pair matched, inclusive | HadQ1 and HadQ2 matched, irrespective of both b assignments |
| B0 assignment eligible | Saved `B0AssignmentMask`, if available: fully matched **and** `GenWDecayValid` |

Every count is an **unweighted number of processed `Events` rows**. Fractions
use all rows supplied for that sample, including unmatched events. They are
not efficiencies relative to the original NanoAOD before the skim cuts.
Neither the weighted MC cutflow nor the `Norm` tree supplies this denominator.
The report also gives counts by role, by number of matched partons, and by file.

Fully matched and hadronic-top matched are inclusive geometric assignment
counts; neither requires a valid W-decay classification label or a known
extra-b count. In particular, fully matched is not simply a sum of
`B0AssignmentMask`. If only some input files have that mask, its count is
explicitly accompanied by the number of rows on which it was available.

## Masses and output files

The module sums the saved corrected reconstructed jet four-vectors:

- `mW = M(jHadQ1 + jHadQ2)`;
- `mTop = M(jHadB + jHadQ1 + jHadQ2)`.

The W pair is unordered. No b-tag cut or requirement that either W daughter
be light-flavored is added. It therefore accepts W → cb with the same logic.

| Output | Contents |
|---|---|
| `matching_summary.txt` | Readable counts, percentages, per-file counts and plot overflows |
| `matching_summary.json` | Same accounting, input paths/ROOT UUIDs, validation coverage, and exact histogram bins |
| `hadronic_top_matched_masses.png` / `.pdf` | W and top masses for the inclusive hadronic-top matched population |
| `fully_matched_masses.png` / `.pdf` | W and top masses requiring all four assignments |

Plots compare **unweighted shapes**, each sample normalized by its matched
event count including overflow. Error bars are square roots of bin counts
with the same normalization. Display ranges are 0–200 GeV for W and
50–350 GeV for top, in 5 GeV bins. Values outside those ranges remain in
the count and are recorded as underflow/overflow; the last bin includes its
upper edge. The dashed 80.4 and 172.5 GeV lines are approximate references,
not fitted peaks or mass constraints. These plots do not predict event
yields, apply cross sections, or combine overlapping TT2Q/TTBB production.

## Integrity checks and limits

The module rejects invalid indices, duplicate assigned jets, padded matched
slots and nonfinite or unphysical matched-jet four-vectors. It checks `nJets`
and `B0JetMask` when present. Saved generator directions, when present, must
satisfy ΔR < 0.4; a 10⁻⁶ allowance covers coordinate rounding and any use of
that allowance is reported. Partial generator-direction or B0-mask schemas
are errors. With generator directions absent the geometry check is marked
unavailable. This checks the saved assignments; it does not independently
replay the greedy algorithm or establish that a different pairing is impossible.

Duplicate paths and ROOT UUIDs are rejected, including identical file copies.
Event overlap between independently written files is not checked. Supply
either merged files or their constituent chunks, never both. The report
describes only the supplied files; it does not certify campaign completeness.
An empty tree or an empty matched population is valid and yields zero counts.

The mass calculation follows the existing local
`NanoAOD-calib-studies/studies/hadronic-masses.py` utility. That older script
reads a `MatchFilter` output which is already fully matched. This module
reads processor skims directly, so it can retain and count events whose
hadronic system is matched while the leptonic b is not.

## Validation on 3 November 2026

The module was run on all 15 completed nominal skims from the
[bounded mass sanity check](b0-mass-sanity-2026-11-03.md), without processing
the original NanoAOD again:

| Sample | Processed events | Fully matched | Hadronic-top matched, inclusive | Hadronic-top only |
|---|---:|---:|---:|---:|
| TT2Q | 32,826 | 13,187 | 16,052 | 2,865 |
| TTBB | 37,164 | 13,064 | 16,450 | 3,386 |

All 223,974 saved assignments passed the index, uniqueness, padding and
geometry checks. No ΔR rounding allowance was needed. Full-match histogram
bins and flows agree exactly with the earlier independent vector-library
calculation. Both samples' inclusive hadronic-top populations peak in the
80–85 GeV W bin and 170–175 GeV top bin.

The [text report](../../../Calib_ChargeTagger_JH/outputs/matching-report-20261103/matching_summary.txt),
[JSON report](../../../Calib_ChargeTagger_JH/outputs/matching-report-20261103/matching_summary.json),
and [inclusive hadronic-top mass plots](../../../Calib_ChargeTagger_JH/outputs/matching-report-20261103/hadronic_top_matched_masses.pdf)
are stored on BRUX. These are results for that bounded subset, not the full
TT2Q or TTBB campaigns.

Eighteen focused tests cover the population definitions, analytic masses,
unordered W pair, malformed assignments, non-B0 skims, chunking, duplicate
files, empty inputs, overflows and output creation. The full repository suite
passed: 307 tests and 22 subtests. Repository lint passed. The main processor
and its ROOT output schema were not changed.
