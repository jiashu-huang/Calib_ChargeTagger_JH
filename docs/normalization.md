# Normalization: where `finalWeight` should be computed

**Status: implemented on `second-pass-finalWeight` (2026-07-26).** The analysis
below (written 2026-07-24, when `fix_final_weight.py` still existed) led to a
design combining Option D's pairing checks with an in-place branch append and
recommendation #3 (self-describing batches): the skimmer never writes
`finalWeight`; each batch ROOT carries its own `np_nominal` in a single-entry
`Norm` tree; and [`condor/scripts/normalize.py`](../condor/scripts/normalize.py)
sums the denominator, **appends** the `finalWeight` branch in place (~3 B/event
written, existing branches untouched), and records provenance in each file and
in `metadata/normalization.json`. Sections below are kept as the design record;
references to `fix_final_weight.py` describe the retired implementation.

## The question

`finalWeight` is what turns a skimmed MC event into a predicted number of real
collisions. Today it is computed by a second pass over the condor outputs
(`condor/scripts/fix_final_weight.py`, since retired)
which rewrites all 93 batch ROOT files in place. That pass is a global
dependency across otherwise-independent jobs, and it has a silent failure mode.
This document works out what the alternatives are.

---

## 1. The principle: it is a ratio estimator

The physical quantity is

```
predicted yield = σ × L × (weighted events passing cuts) / (weighted events processed)
                              ^ numerator                    ^ denominator
```

In this code:

| Piece | Where it lives | Depends on how much you process? |
|---|---|---|
| `σ × L` = 42,760.56 | `xsecs.py` × `hh_vars.LUMI["2024"]`, a constant | **no** |
| `weight` (per event) | branch in each batch ROOT; already includes σ×L | **no** |
| `np_nominal` | `totals` in each batch pickle; Σ of `genweight × pileup × ISR × FSR` over **all** events read, before cuts | **yes** |
| `finalWeight` = `weight / np_nominal` | currently written by the rewrite pass | yes, via the denominator |

**The correctness requirement is that the numerator and the denominator describe
the same population of events.** Get that right and

```
Σ finalWeight  =  σL × acceptance
```

which is independent of how many MC events you happened to process. Verified on
a 20k-event chunk: 6,279 events passed, weighted acceptance 0.29886,
Σ `finalWeight` = 12,779 = 42,760.56 × 0.29886.

This is why processing a subset is *safe*: the acceptance measured from part of
the sample is an unbiased estimate of the acceptance of the whole sample. Losing
batches costs statistical precision, not accuracy — **provided the denominator
is recomputed over the batches you actually have.**

## 2. The worked example

Three batches. Pretend every MC event has weight 1 (really ~349, from
`genWeight`; it changes nothing structurally). σL = 42,760.

| Batch | events processed → `np_nominal` | passing cuts | `weight` written per event |
|---|---|---|---|
| A | 1,000 | 300 | 42,760 |
| B | 1,000 | 300 | 42,760 |
| C | 1,000 | 290 | 42,760 |

All three present: denominator 3,000 → `finalWeight` = 42,760/3,000 = 14.25,
total yield 14.25 × 890 = **12,687**.

Note `weight` is identical in every batch. It is a *per-event* quantity and knows
nothing about how many batches exist. Only the denominator is *global*. The
current design fuses the two together at write time, which is the root of the
problem.

### Now batch C fails

| | denominator used | result | |
|---|---|---|---|
| Correct | 2,000 (A+B) | 21.38 × 600 = **12,828** | unbiased; differs from 12,687 only by statistical wobble in the acceptance |
| Stale baked-in `finalWeight` | 3,000 | 14.25 × 600 = **8,552** | 33% low |
| Denominator passed in up front | 3,000 | 14.25 × 600 = **8,552** | identical failure |

8,552 is exactly ⅔ of the right answer — the fraction of the sample that
survived. That is the signature of a denominator that does not match its
numerator.

**Corollary: do not pass a pre-computed total-generated-events number into the
jobs.** It reproduces the stale-rewrite bug by construction, converting a benign
failure mode (fewer events → more noise) into a malignant one (missing events →
silent multiplicative bias). The generated total is still worth recording, but as
a *QA check* ("we successfully processed 94.6% of the sample"), never as an input
to the weight.

## 3. The concrete hole in the current implementation

`fix_final_weight.py` globs the two directories **independently** and never
checks that they correspond:

```python
pickle_paths = sorted(pickles_dir.glob("*.pkl"))
root_paths   = sorted(roots_dir.glob("*.root"))
```

It records `num_pickles` and `num_roots` in `metadata/global_final_weight.json`
but does not compare them. Meanwhile the worker
([`condor/templates/calib_batch_exec.sh`](../condor/templates/calib_batch_exec.sh))
moves its two outputs non-atomically, **ROOT first**:

```bash
mv -f "${ROOT_OUTPUTS[0]}" "$OUTPUT_ROOTS_DIR/$BATCH_ID.root"
mv -f "$PICKLE_OUTPUT"     "$OUTPUT_PICKLES_DIR/$BATCH_ID.pkl"
```

A job killed between those two lines — or hitting a quota on the second — leaves
a ROOT with no pickle. Its events enter the numerator while its `np_nominal` is
absent from the denominator, so the yield comes out **too high**, silently.

The rewrite pass is also destructive and non-resumable: it reads and overwrites
each file via `temp_path.replace(root_path)`. Interrupt it and the directory
holds a mix of normalized and unnormalized files with no record of which is
which (`finalWeight` present is the only clue, and `--force` erases even that
distinction).

## 4. Options

### Option A — normalize at merge time  ← recommended

Batch ROOTs stay raw (`weight`, no `finalWeight`).
[`merge_processed.py`](../condor/scripts/merge_processed.py) computes the
denominator from exactly the batches it is merging and writes `finalWeight` into
`merged/total.root` as it goes. `fix_final_weight.py` is retired.

- Merging *is* the moment you commit to "these batches are my sample," so the
  decision and the arithmetic happen in one place, in one function, at one time.
  The two can no longer drift apart.
- One write of a new file instead of 93 destructive in-place rewrites.
- Re-running after a batch is reprocessed is just re-merging.
- Cost: essentially zero — the merge already reads and writes every byte.
- Downside: individual batch files are no longer directly usable for physics
  without the merged file or a manual denominator.

### Option B — normalize at read time (purist)

Nothing on disk ever carries `finalWeight`. Analysis code loads the batches it
wants, sums their `np_nominal`, divides.

- Maximum flexibility; correct for any subset by construction.
- Downside: every consumer must remember to normalize. For a single-sample
  calibration this is a worse trade than A.

### Option C — store only the scalar

Recognize that `finalWeight = weight × (1 / np_nominal_global)` is a *single
number* applied uniformly. Writing a per-event column to encode one scalar is
redundant. Write `metadata/normalization.json` with the global denominator, the
list of batches that produced it, and σL — then divide on the fly wherever
needed (`RDataFrame::Define`, uproot, `TTree::Draw` with a weight expression).

- Cheapest possible: no event data is touched at all.
- Downside: least convenient downstream; easy to forget.

### Option D — keep the current flow, close the hole

If the rewrite pass is retained, two small changes make arbitrary job failures
safe:

1. In the worker, move the **pickle first, ROOT second**. Then "a ROOT exists"
   implies "its pickle exists."
2. In `fix_final_weight.py`, sum `np_nominal` over exactly the pickles that have
   a matching ROOT stem, and **raise** if any ROOT lacks a pickle. Orphan pickles
   are skipped (consistent); orphan ROOTs become a loud error. Record the actual
   batch list in the summary JSON, not just counts.

~10 lines. Strictly an improvement over today regardless of which option is
chosen, and worth doing even as an interim step.

## 5. On writing a separate (C++?) post-processing script

The idea of a standalone pass that walks the outputs and writes `finalWeight` is
reasonable, but two things are worth knowing before reaching for C++ for speed.

**Scale of the job.** Measured from the committed baseline: 859 bytes/event,
346 branches. Projected full production ≈ 12.3M input events → ~3.7M selected →
**~3.2 GB** of skim across 93 files. That is a few minutes of I/O, not hours.

**The work is I/O-bound, not CPU-bound.** The arithmetic is one division per
event — microseconds in total. Everything else is decompressing and recompressing
ROOT baskets. A C++/`RDataFrame` implementation would not beat `uproot` by a
meaningful factor here, because both spend their time in the same compression
libraries. Language choice is not the lever.

**The lever is avoiding the pass entirely.** Ranked by actual cost:

| Approach | Bytes touched | Notes |
|---|---|---|
| Option C (scalar in JSON) | ~0 | one number |
| Friend tree | ~30 MB | one float branch per event, attached via `TTree::AddFriend`; original files untouched |
| Option A (fold into merge) | 3.2 GB, already being paid | free — the merge reads and writes everything anyway |
| Standalone rewrite pass | 6.4 GB | doubles the I/O to add one column |

If a standalone script is still wanted (e.g. to keep merging optional), the
friend-tree variant is the one to build: it is ~30 MB of output, it never
rewrites the skims, and it is trivially re-runnable and reversible. `RDataFrame`
with implicit multithreading is a fine choice for it — just choose it for
convenience and ROOT-native integration, not for speed over the alternatives.

## 6. Recommendation

1. **Do Option D now** regardless — it is small and removes a silent-corruption
   mode from the pipeline that exists today.
2. **Adopt Option A** as the target design: normalize inside
   `merge_processed.py`, retire `fix_final_weight.py`.
3. **Additionally**, write each batch's own `np_nominal` into its ROOT file (a
   single-valued branch or file metadata) so a batch file is self-describing and
   the ROOT↔pickle pairing-by-filename stops being load-bearing.
4. **Record, don't use**, the total generated events: compare Σ `nevents` across
   pickles against the production's known total and put the fraction in the
   summary JSON as a campaign-health number.

## 7. Caveat on "failures are harmless"

The claim that lost batches cost only precision assumes failures are unrelated to
the physics — true for node deaths, quota, timeouts. If jobs fail *because of*
their content (e.g. the highest-pileup files are slowest and time out), the
surviving sample is biased and no normalization scheme can repair it. Worth a
glance at *which* batches failed rather than only *how many*.

## 8. Related

- [`condor/README.md`](../condor/README.md) — current workflow
- [`processor.md`](processor.md) — the weights and pile-up sections, for the
  weight chain `genweight × pileup × ISR × FSR × σL`
- Known issue: `single_weight_*` diagnostic branches also carry the σ×L factor
  (an ordering accident in `add_weights` step 11); unrelated to this decision but
  in the same code path.
