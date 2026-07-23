# Calib_ChargeTagger_JH

Standalone Vcb skimmer for the jet-charge-tagger calibration, targeting the
**2024 (Summer24)** private NanoAOD production. This is a clean-room port of
the Vcb pipeline from `Vcb/Calib_ChargeTagger` (an LPC-HH/bbtautau fork) with
the `boostedhh` framework **vendored** under [src/boostedhh](src/boostedhh)
(see [src/boostedhh/VENDORED.md](src/boostedhh/VENDORED.md)) and the analysis
code renamed `bbtautau` → `vcb`. Lineage: [docs/history.md](docs/history.md).

## What the pipeline does

NanoAOD → `vcb.processors.vcbSkimmer` (object selection: tight leptons with
trigger matching, AK4 jets with JEC + jet-veto map + lepton cleaning;
gen-truth Vcb branches via `gen_selection_Vcb`; custom charge branches
`JetQk_QkCharge05/10`, `Jet_PflavCharge` pass through) → per-event weights
(genWeight, pileup, PS ISR/FSR, xsec×lumi normalization) → parquet/ROOT skim +
pickle totals → `finalWeight = weight / np_nominal` (locally in `vcb.run`, or
globally across batches via `condor/scripts/fix_final_weight.py`).
Details: [docs/processor.md](docs/processor.md).

## Setup

```bash
micromamba activate ttbar     # or: micromamba create -f environment.yaml
pip install -e ".[diagnostics,test]"
```

> The old repo's `bbtautau`/`boostedhh` editable installs have been
> uninstalled from the `ttbar` env — this repo's `vcb` + vendored `boostedhh`
> replace them. (To run the *old* repo locally now, it needs
> `PYTHONPATH=src:boostedhh/src`.)

## Run

Single file, local:

```bash
python -m vcb.run \
  --year 2024 \
  --files /path/to/<file>_CMSSW_15_CHARGE_NanoAOD.root \
  --save-root --chunksize 100000 --maxchunks 0
```

Outputs land in `outputs/<timestamp>/` (symlinked from `outputs/latest`):
per-batch parquet + ROOT skims, `outfiles/<tag>.pkl` totals, and a
`finalWeight` column/branch (disable with `--no-write-final-weight` — condor
jobs do, then normalize globally).

Full 2024 production (93 `batch_*` dirs under
`Vcb/MC/TTtoLNuCB_Summer24MiniAODv6/NanoAOD-cmssw-charge/charge_Run3_2024_150X_v1/`)
via HTCondor: see [condor/README.md](condor/README.md).

## Tests

```bash
# unit tests (fast, no data needed)
pytest tests/

# integration run: regenerates tests/outfile/ baselines (committed)
cp /isilon/export/home/jhuan166/Vcb/Calib_ChargeTagger/tests/data/test-input.root tests/data/
python tests/test_run.py            # defaults: tests/data/test-input.root, --year 2024
```

## 2024 status / user-input TODOs

Placeholders are wired in and safe to run with; fill them in when the real
numbers are available — see **[SHOPPING-LIST.md](SHOPPING-LIST.md)** for exactly
what to get and where to put it.

| Item | Interim behavior |
|---|---|
| 2024 luminosity | **set** to 124,000 pb⁻¹ (CMS DP-2026/003) in `boostedhh/hh_vars.py` (overall scale only) |
| `xsecs["TTtoLNuCB"]` | placeholder computed from σ_tt×2×BR(W→ℓν)×BR(W→cb) in `boostedhh/xsecs.py` (overall scale only) |
| 2024 pileup weights | **2023 (Summer23) puWeights used as stand-in** with a loud warning (norm-preserving) |
| 2024 JER smearing | **applied** — nominal Summer24 JRV2 smearing via correctionlib (no longer a placeholder) |

2024 jet corrections are applied via correctionlib from the bundled CAT Summer24
file `src/boostedhh/corrections/2024_jet_jerc.json.gz` — compound
`Summer24Prompt24_V5_MC_L1L2L3Res_AK4PFPuppi` on raw pT, then nominal JRV2 JER
smearing (`jer_smear.json.gz`) on the corrected pT; both loaded bundled-first
with a CAT cvmfs fallback (see
[src/boostedhh/corrections/README.md](src/boostedhh/corrections/README.md)).
2022/2023 keep the bundled pickle factories.

## Repo layout

```
src/vcb/                 analysis package (run.py, HLTs.py, processors/)
src/boostedhh/           vendored framework (do not auto-format; see VENDORED.md)
condor/                  batch submission + post-processing scripts
tests/                   pytest units + integration script + committed baselines
diagnostics/             plotting / event-dump helper scripts (not part of the package)
docs/                    processor description, lineage, archived patch
```
