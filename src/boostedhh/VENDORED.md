# Vendored: `boostedhh`

This directory is a **vendored copy** of the `boostedhh` framework — it is not a
git submodule and is not pip-installed from upstream.

## Provenance

- Upstream: <https://github.com/LPC-HH/boostedhh> @ commit `71bd456`
  ("Merge pull request #19 from LPC-HH/dev-plotting-update")
- Copied from the *patched working tree* of the old repo's submodule at
  `Vcb/Calib_ChargeTagger/boostedhh/src/boostedhh/` on 2026-07-14, which
  carries one local patch on top of `71bd456`:
  - **outdir patch** (`docs/archive/boostedhh-outdir.patch` in this repo):
    `SkimmerABC.dump_table` and `run_utils.run` route intermediate parquet
    output through the `BOOSTEDHH_OUTPARQUET_DIR` environment variable instead
    of hardcoding `./outparquet`.

## Local modifications on top of that

- `hh_vars.py` — trimmed: HH sample dictionaries and SF tables dropped; only
  symbols imported by `boostedhh.utils`/`run_utils` and the `vcb` package kept.
  2024 added to `years` and `LUMI`.
- `run_utils.py` — `--year` choices extended with `"2024"`.
- `processors/corrections.py` — 2024 wiring: `get_pog_json` year→dir map,
  Summer24 jet-veto key, correctionlib-based 2024 JEC in `JECs`
  (no pickle factories exist for 2024).
- `xsecs.py` — added `xsecs["TTtoLNuCB"]`.
- **Pileup overhaul (2026-07-24)** — `add_pileup_weight` rewritten:
  - takes `Pileup_nTrueInt` (the Poisson mean the LUM weights are derived in);
    upstream fed it `Pileup_nPU`, the sampled count, which mis-weights events
    and costs effective statistics;
  - sources puWeights bundled-first (`corrections/{year}_puWeights.json.gz`)
    with a fallback to the CAT metadata LUM tree on cvmfs
    (`cat_lum_campaigns` map) — the jsonpog-integration LUM tree stops at
    `2023_Summer23BPix` and its 2022/2023 payloads are content-identical to
    CAT's anyway; the `"pileup"` entry left `pog_jsons`;
  - reads the payload's single correction key, dropping the hardcoded per-year
    correction-name map and the 2023-placeholder fallback for 2024;
  - removed with it: the dead `Pu60`/`Pu70` histogram branch (its data file
    `MyDataPileupHistogram2022FG.root` was never vendored, and
    `"Pu60" in dataset` raised `TypeError` on the `dataset=None` default),
    `SkimmerABC.pileup_cutoff` (called nonexistent `get_pileup_weight`),
    `corrections/makePUReWeightJSON.py`, `corrections/puWeightsJSON.sh`, and
    `corrections/data/pileup/`.

## What was deliberately NOT vendored

`plotting.py`, `submit_utils.py`, `log_utils.py`, `inspect_root.py`,
`check_xsecs.py`, Run-2 / py<3.11 JEC pickles (`jec_compiled.pkl.gz`,
`jec_compiled_run2.pkl.gz`), `ULvjets_corrections.json`,
`2022_puWeights.json.gz`, `corrections/data/txbb_sfs/`, and the
`pu_correction_per_file.py` / `to_zip.py` helpers.

## Keeping it diffable

The package keeps the upstream module name `boostedhh` so the ~30 import
sites in `vcb` remain untouched and `diff -r` against upstream stays trivial:

```bash
git clone https://github.com/LPC-HH/boostedhh /tmp/boostedhh
git -C /tmp/boostedhh checkout 71bd456
diff -r /tmp/boostedhh/src/boostedhh src/boostedhh
```

Do **not** auto-format or lint this directory (ruff excludes it via
`pyproject.toml` / `.pre-commit-config.yaml`).
