# HTCondor batch processing

One Condor job per `batch_*` input directory. Each job runs the `vcb` skimmer
on all ROOT files in its batch and writes one skimmed ROOT + one totals pickle.
`finalWeight` is **not** written per-job (`--no-write-final-weight`); it is
computed globally afterwards with `scripts/fix_final_weight.py`.

## Worked example: 2024 production

Input: 93 `batch_*` dirs (445 files, ~62 GB) under

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

> Known data issue (2026-07-14): `batch_001/d33939a7-...root` in the 2024
> production has no `Events` tree (empty file); its job will fail. Either
> regenerate that file or drop it from `input_list.txt`.

### 2. Global finalWeight

After **all** jobs finish (the normalization must see every batch pickle):

```bash
python condor/scripts/fix_final_weight.py \
  --processed-dir "$INPUT/processed-nano/<tag>"
```

This sums `np_nominal` over all pickles and rewrites each
`roots/batch_*.root` with `finalWeight = weight / global_np_nominal`
(summary in `metadata/global_final_weight.json`).

### 3. Merge

```bash
# hadd comes with the ROOT install in the ttbar env (or activate CMSSW)
python condor/scripts/merge_processed.py \
  --processed-dir "$INPUT/processed-nano/<tag>"
# -> <processed-dir>/merged/total.root
```

## Notes

- Workers only need the shared filesystem: the repo checkout, the `ttbar`
  micromamba env, and the input files. Nothing is transferred.
- `--batch-size` stays at 9999 so one job folds into exactly one ROOT file
  (the worker script asserts this).
- Resource knobs: `--request-cpus 2 --request-memory 8G --request-disk 4G`.
- Filters: `--batch-names batch_007 ...`, `--batch-start/--batch-end`,
  `--max-batches`, `--test` (first two).
