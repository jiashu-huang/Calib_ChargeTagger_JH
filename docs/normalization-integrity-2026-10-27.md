# Signed-weight normalization checks — 27 October 2026

The second pass and campaign validator now handle signed and zero MC weights
consistently. They check every event before normalization writes begin, and
verify existing `finalWeight` values before treating a rerun as complete.
The skim's event selection, weight formulas, output schema and prescription
version 3 are unchanged. This work is in the isolated BRUX realignment copy.

## Failures corrected

- A zero `weight_noxsec` previously failed validation, even when the corresponding
  `weight` was also zero. Such events are retained and checked without division.
- The validator required a weighted selection fraction strictly between zero
  and one. That restriction is not valid for signed MC weights. The numerator
  also includes lepton-efficiency factors that are absent from the denominator.
- Checks guarded by the truth value of a sum could disappear when positive and
  negative contributions canceled exactly. The checks now run for zero sums.
- The normalizer inferred its scale from at most the first 1,000 entries in a
  file and stopped at the first usable ratio. A later incompatible scale could
  escape detection. It now scans every file in bounded chunks.
- The validator rounded inferred scales to four decimal places when comparing
  files. It now compares all nonzero-event ratios with relative tolerance
  1e-10, without that rounding.
- Nonfinite denominators could pass the old `D != 0` check. Nonfinite inputs,
  overflowed sums, zero global denominators and nonfinite quotients now fail.
- A normalizer rerun could skip stale `finalWeight` branches while writing a
  fresh summary. It now requires the branch, denominator and batch fingerprint
  to agree before skipping the file.
- The validator imposed an independent pileup-input cut of `0 < nTrueInt < 200`.
  It now checks finite, nonnegative inputs and leaves flow handling to the
  correction payload used by the processor.

## Arithmetic contract

Let g be the signed generator weight, P the pileup factor, L the lepton
efficiency factor, and C the sample's stored cross-section-times-luminosity
factor. The existing definitions remain:

```text
D               = sum_all_input(g × P)
weight_noxsec[i] = g[i] × P[i] × L[i]
weight[i]       = C × weight_noxsec[i]
finalWeight[i]  = weight[i] / D
```

D must be finite and nonzero. Individual batch sums and selected-event sums
may be zero. Signed denominators are retained; the checks do not take an
absolute value or clip a weight. A negative or strongly canceled denominator
still needs a statistical interpretation before a physics result is quoted.

The campaign identity is

```text
sum_selected(finalWeight) = C × sum_selected(weight_noxsec) / D
```

The right-hand fraction is a weighted selection fraction, not a probability.
The validator checks this identity even when the result is zero, negative,
or the fraction exceeds one. Each stored `finalWeight` must also equal its
individual quotient. The aggregate comparison allows relative tolerance 1e-9
and an absolute rounding allowance of 1e-12 times the sum of absolute
`finalWeight` values, so cancellation does not create a false failure.

C is inferred only where `weight_noxsec != 0`. Every such event must give
the same finite positive factor. At zero `weight_noxsec`, `weight` must also
be zero. An empty or entirely zero-weight output cannot determine C; its
summary records `sigma_x_lumi: null` unless another included file determines it.

The inferred factor verifies arithmetic only. It does not establish that the
cross section, W branching fractions, reference Vcb or sample-overlap treatment
is correct. In particular, the existing TTBB factor of 1 remains a placeholder.
The validator reports a **normalized weighted sum**, and the summary records
this limitation in `scale_interpretation`.

## Reruns and compatibility

Before writing any output, `normalize.py` checks all weights, the common
sample factor, the usable global denominator and the finiteness of every
resulting quotient. An existing branch is skipped only after its values and
`finalWeight_provenance` agree with the current denominator and fingerprint.
Invalid later files therefore cannot cause earlier files to be normalized
before that input error is discovered. This preflight does not make a
multi-file run transactional against an interruption or filesystem failure.

If the included batches change, or a previous branch/receipt is missing or
stale, rerun the same normalization command with `--force`. The forced path
recomputes from `weight`; it does not divide an existing `finalWeight` again.
It preserves the complete `Norm`, `PdfMetadata` and `WeightMetadata` trees.
The campaign validator rejects a mixture of normalized and unnormalized files.

Both supported workflows remain available: normalize all batches and then
merge, or merge raw batches and normalize the merged file. A later normalizer
invocation using a different target can change the fingerprint and therefore
require `--force`. Retain the summary belonging to the chosen workflow.

No NanoAOD reprocessing is needed for these checks. Existing prescription
versions 1, 2 and 3 remain readable separately. No new event fields or physics
corrections are introduced.

## Validation

The [validation record](normalization-integrity-2026-10-27-validation.json)
contains the unit, integration and real-sample pipeline results. Tests include
signed/zero entries, exact cancellations, invalid denominators, late scale
mismatches, corrupted receipts and branches, unchanged files after failed
preflight, empty selections, verified reruns and forced normalization.

| Check | Result |
| --- | --- |
| Unit suite and lint | 364 tests and 22 subtests passed; lint passed |
| Nominal integration | 208,780 input events; 59,712 selected; all three regression baselines byte-identical |
| Jet-tagger round trip | 5,435,070 comparisons; PASS |
| TTBB systematic campaign | 2,709 selected events; 137 batch checks and 65 merged checks passed |
| Signal systematic campaign | 59,712 selected events; 99 batch checks and 65 merged checks passed |
| Normalizer reruns | Both campaigns' ROOT files byte-identical after verified reruns |
| Forced rewrite | Both campaigns passed all 65 merged checks again; event values and all normalization/weight/PDF metadata preserved |
| Older prescription | Existing version-2 TTBB campaign passed all 25 current checks |

The high-pT muon prescription, TTBB physical normalization and overlap,
upstream jet-charge association and collision-data closure remain the physics
limitations listed in the [readiness record](cms-readiness-2026-10-27.md).
