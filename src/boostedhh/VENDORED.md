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
  2024 added to `years` and `LUMI`. On 2026-09-11 the luminosity was corrected
  from 124,000 pb^-1 (delivered) to the C-I analysis reference of 109,820 pb^-1,
  documented in AN-25-214 Table 1 and the public CMS-DP-2026-101 page. See
  `docs/2024-inputs.md` for the data definition and calculation limitations.
- `run_utils.py` — `--year` choices extended with `"2024"`; `run()` gained a
  `root_dir` argument (skim ROOT files can land outside the run output
  directory), writes `num_batches_<tag>.txt` only when parquet is kept, and
  deletes the `outparquet/` scratch when it is not. Together these back the
  `--output-root-location` / `--root-only` flags in `vcb.run`. Single-batch MC
  runs additionally write a one-entry `Norm` tree (`np_nominal`, `nevents`)
  next to `Events`, making each skim ROOT self-describing for the
  `normalize.py` second pass (hadd concatenates `Norm`, so a merged file's
  `Norm` sum is the global denominator).
- `processors/corrections.py` — 2024 wiring: `get_pog_json` year→dir map,
  Summer24 jet-veto key, correctionlib-based 2024 JEC in `JECs`
  (no pickle factories exist for 2024).
  Type-1 MET uses `muonSubtrDeltaEta/Phi` to reconstruct the muon-subtracted
  jet direction for JEC evaluation and transverse-vector propagation
  (2026-09-06). It also includes `CorrT1METJet` after nominal JEC/JER and the
  Type-1 pT/EM-fraction cuts. Auxiliary jets use geometric hybrid gen matching
  for JER because they have no `genJetIdx`; they do not enter analysis jets.
  On 2026-09-13, added single-source signed JES and global JER up/down passes
  using the fractional JRV2 `SFUncertainty`, fixed nominal hash inputs and
  hybrid matches. The corresponding per-jet factors also propagate to Type-1
  MET for both collections, with active pT acceptance and |eta| < 5.2 after
  muon subtraction. Missing mandatory 2024 payloads raise; raw NanoAOD records
  are preserved for independent passes, including typed empty collections.
- `xsecs.py` — added `xsecs["TTtoLNuCB"]`.
  On 2026-10-28, added the user-approved provisional 2024
  `TTBB-TTtoLNu2Q` rate, 16.011655167690346 pb, from the complete sample's
  signed mean generator weight under AN-25-214 v5 section 2.2.4. The source,
  AN comparison and overlap convention are recorded in
  [B0 preparation](../../docs/b0-input-readiness-2026-10-28.md). This rate is
  specific to the recorded Summer24 MiniAODv6 v2 sample.
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
`pyproject.toml`).
