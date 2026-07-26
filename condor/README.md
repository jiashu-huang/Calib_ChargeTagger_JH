# HTCondor batch processing

Last update: **2026-07-26**

One Condor job per `batch_*` input directory. Each job runs the `vcb` skimmer
on all ROOT files in its batch and writes one skimmed ROOT + one totals pickle.
The skimmer never writes `finalWeight` — its denominator sums over every batch,
which no single job can know. It is appended afterwards, in place, by
`scripts/normalize.py`.

## Worked example: 2024 production

Input: 93 `batch_*` dirs (465 files, 5 per batch, ~65 GB, 19,823,340 events;
Σ genWeight = 6.627e9) under

```
/isilon/export/home/jhuan166/Vcb/MC/TTtoLNuCB_Summer24MiniAODv6/NanoAOD-cmssw-charge/charge_Run3_2024_150X_v1/
```

### 1. Generate (and optionally submit) the campaign

```bash
INPUT=/isilon/export/home/jhuan166/Vcb/MC/TTtoLNuCB_Summer24MiniAODv6/NanoAOD-cmssw-charge/charge_Run3_2024_150X_v1

# dry run on the first two batches first:
python condor/submit_batches.py --input-root "$INPUT" --tag test_$(date +%Y%m%d) --test

# full campaign, submitting directly:
python condor/submit_batches.py --input-root "$INPUT" --tag prod_$(date +%Y%m%d) --submit
```

Defaults: `--year 2024`, `--files-name TTtoLNuCB`, `--skimmer vcbSkimmer`,
`--mamba-env ttbar`. Generated JDLs/worker scripts land in
`condor/runs/<tag>/` (git-ignored); outputs in
`<input-root>/processed-nano/<tag>/{roots,pickles,metadata}/`.

Without `--submit`, submit later with `condor/runs/<tag>/submit_all.sh`, or
debug a single job locally with `bash condor/runs/<tag>/batch_000/run_batch.sh`.

> Input health (scanned 2026-07-26): all 465 files open, carry an `Events`
> tree, and have the branches the skimmer needs — **0 bad, 0 missing
> branches**. Worth re-checking after any regeneration: `--files` sets
> `skipbadfiles=False`, so a single unreadable file aborts its whole job.
>
> Keep merged/derived copies **out of** the `batch_*` directories. A hadd of
> batch_000 (`merged/batch_000.root`, 208,780 events) briefly sat inside
> `batch_000/`, which would have made that job skim the same events twice —
> harmless to the yield (numerator and denominator both double-count) but it
> corrupts the statistics and doubles the runtime. `submit_batches.py` only
> descends into directories matching `batch_<digits>`, so a sibling `merged/`
> is safely ignored.

### What each job runs

`submit_batches.py` renders one worker script per batch from
[templates/calib_batch_exec.sh](templates/calib_batch_exec.sh). With the
defaults above, every job executes:

```bash
micromamba run -n ttbar python -u -m vcb.run \
  --processor skimmer --skimmer vcbSkimmer \
  --year 2024 \
  --files <this batch's *.root>  --files-name TTtoLNuCB \
  --naming-tag batch_NNN \
  --save-root \
  --chunksize 1000000 --maxchunks 0 --batch-size 9999 \
  --outdir condor/runs/<tag>/batch_NNN/work
```

| Where it comes from | Value | Why |
|---|---|---|
| `--naming-tag` | `batch_NNN` | names the outputs; the worker renames them to `<tag>/roots/batch_NNN.root` and `<tag>/pickles/batch_NNN.pkl`, which is the pairing `normalize.py` relies on |
| `--files-name` | `TTtoLNuCB` | must match a key in `xsecs`, else the run silently normalizes to `weight_norm = 1` |
| `--batch-size` | `9999` | forces one ROOT per job; the worker asserts exactly one and fails otherwise |
| `--maxchunks` | `0` | no cap — process the whole batch |
| `--chunksize` | `1000000` | events per coffea chunk |
| no `finalWeight` flag | — | the skimmer cannot write it; see step 2 |

Condor resources come from the JDL: `request_cpus = 2`,
`request_memory = 8G`, `request_disk = 4G`, `getenv = true`, `universe =
vanilla`. Nothing is transferred — workers read the shared filesystem
directly.

The campaign `--tag` is the only identifier you choose. It names both
`condor/runs/<tag>/` (JDLs, worker scripts, logs, `campaign.json`) and
`<input-root>/processed-nano/<tag>/`. Both must not already exist, so a tag is
single-use.

### 2. Global finalWeight

After **all** jobs finish (the denominator must see every batch):

```bash
micromamba run -n ttbar python condor/scripts/normalize.py \
  --processed-dir "$INPUT/processed-nano/<tag>"
```

This sums `np_nominal` over the batches (from each ROOT's own `Norm` tree,
pickles as fallback) and **appends** `finalWeight = weight / global_np_nominal`
to each `roots/batch_*.root` in place — existing branches untouched, ~3 bytes
per event written, seconds not minutes. Provenance (denominator + a fingerprint
of the batch list) lands in each file and in `metadata/normalization.json`.

A ROOT without a Norm tree or pickle is a hard error; already-normalized files
are skipped (`--force` recomputes them via a full rewrite). To normalize after
merging instead, run with `--target merged` — hadd concatenates the per-batch
`Norm` entries, so the merged file carries its own denominator.

### 3. Merge (optional)

```bash
# hadd comes with the ROOT install in the ttbar env (or activate CMSSW)
python condor/scripts/merge_processed.py \
  --processed-dir "$INPUT/processed-nano/<tag>"
# -> <processed-dir>/merged/total.root
```

**This step is convenience, not correctness.** After step 2 every batch ROOT
already carries a `finalWeight` computed with the *global* denominator, so the
93 files are immediately usable as they are — `TChain` them, or hand the
directory to uproot, and the yields come out right. `hadd` preserves
`finalWeight`, the `Norm` tree (one entry per batch, so the merged file's sum
is the global denominator) and the provenance objects, so merging after
normalizing is safe and self-consistent.

One thing to keep straight: `finalWeight` is normalized to the **whole
campaign**, not to the file it lives in. Summing it over all 93 batches gives
the predicted yield; summing over one batch gives *that batch's share* of the
yield, not a full-sample estimate. Analyse a subset only if you mean to.

If you would rather merge first and normalize once, swap the order and run
`normalize.py --target merged`. Do not do both — the second pass skips files
that already have `finalWeight` rather than dividing twice.

## Notes

- Workers only need the shared filesystem: the repo checkout, the `ttbar`
  micromamba env, and the input files. Nothing is transferred.
- `--batch-size` stays at 9999 so one job folds into exactly one ROOT file
  (the worker script asserts this).
- Resource knobs: `--request-cpus 2 --request-memory 8G --request-disk 4G`.
- Filters: `--batch-names batch_007 ...`, `--batch-start/--batch-end`,
  `--max-batches`, `--test` (first two).
