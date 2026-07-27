# Calib_ChargeTagger_JH

Standalone Vcb skimmer for the jet-charge-tagger calibration, targeting the
**2024 (Summer24)** private NanoAOD production. This is a clean-room port of
the Vcb pipeline from `Vcb/Calib_ChargeTagger` (an LPC-HH/bbtautau fork) with
the `boostedhh` framework **vendored** under [src/boostedhh](src/boostedhh)
(see [src/boostedhh/VENDORED.md](src/boostedhh/VENDORED.md)) and the analysis
code renamed `bbtautau` → `vcb`. Lineage: [docs/history.md](docs/history.md).

## State of the repo (2026-07-27)

**Feature-complete and production-validated on 2024 MC.** The full 2024
TTtoLNuCB campaign (93 `batch_*` dirs) has been skimmed via HTCondor and
normalized. All four calibration inputs are real Summer24 values — luminosity
124 fb⁻¹, σ(TTtoLNuCB) ≈ 0.345 pb, `Collisions24_CDEFGHI_goldenJSON` pile-up
weights, and Summer24 V5 JEC + JRV2 JER — with no placeholders left
([docs/2024-inputs.md](docs/2024-inputs.md)).

Normalization is deliberately a **second pass**: the skimmer writes `weight`
and never `finalWeight`; each batch ROOT carries its own `np_nominal` in a
single-entry `Norm` tree, and
[condor/scripts/normalize.py](condor/scripts/normalize.py) appends the
`finalWeight` branch in place afterwards. Why it is built this way:
[docs/normalization.md](docs/normalization.md).

Known gaps:

- **No jet-energy variations.** JER up/down and JES systematics aren't wired —
  the Vcb skimmer consumes none (`jec_shifted_jetvars` unused). Nominal only.
- **2024 data L2L3Residual JEC and AK8 jets are no-ops** — this production is
  MC AK4 only.

## What the pipeline does

NanoAOD → `vcb.processors.vcbSkimmer` (object selection: tight leptons with
trigger matching, AK4 jets with JEC + jet-veto map + lepton cleaning;
gen-truth Vcb branches via `gen_selection_Vcb`; custom charge branches
`JetQk_QkCharge05/10`, `Jet_PflavCharge` pass through) → per-event weights
(genWeight, pileup, PS ISR/FSR, xsec×lumi normalization) → parquet/ROOT skim +
pickle totals → `finalWeight = weight / np_nominal` appended in a second pass
by `condor/scripts/normalize.py` (the skimmer itself never writes it — the
denominator sums over every batch of a campaign).

## Documentation map

| Document | What it covers |
|---|---|
| [docs/processor.md](docs/processor.md) | How the skimmer works internally: object selection, the per-event trigger lepton, JEC/JER, jet-veto map, gen truth, cutflow, weights, pile-up |
| [docs/cli.md](docs/cli.md) | Every `python -m vcb.run` flag — defaults, overlaps, and the inert ones inherited from `boostedhh` |
| [condor/README.md](condor/README.md) | Batch production on HTCondor: submit, normalize, validate, merge |
| [docs/normalization.md](docs/normalization.md) | Design record: why `finalWeight` is a second pass, the failure mode it closes |
| [docs/2024-inputs.md](docs/2024-inputs.md) | Provenance of the four 2024 calibration inputs (lumi, σ, pile-up, JEC/JER) |
| [docs/tests.md](docs/tests.md) | Test suite details and the jet-tagger round-trip check |
| [docs/history.md](docs/history.md) | Lineage back to the old `Calib_ChargeTagger` repo |
| [src/boostedhh/corrections/README.md](src/boostedhh/corrections/README.md) | Bundled correction payloads: origin, snapshot pins, md5s |
| [src/boostedhh/VENDORED.md](src/boostedhh/VENDORED.md) | What "vendored" means here and the local deltas vs upstream |
| [AGENTS.md](AGENTS.md) | Operating notes: environment, ground rules, pre-commit checks |

## Setup

**One-time, per machine / per environment**:

```bash
micromamba create -f environment.yaml    # only if the `ttbar` env doesn't exist yet
micromamba run -n ttbar pip install -e ".[diagnostics,test]"
```

The install is **editable**: `vcb` and the vendored `boostedhh` are linked
straight to `src/` in this repo, so edits to the source take effect on the next
run with no reinstall. Re-run `pip install -e ...` only when:

- the `ttbar` environment is recreated or you move to another machine,
- the dependency lists in [pyproject.toml](pyproject.toml) change (`dependencies`
  or the `diagnostics` / `test` extras),
- `git pull` brings in such a change.

Renaming or adding *files* under `src/` does **not** need a reinstall.

**For every shell session**: you need the `ttbar` environment active before you
run the code. There are two equivalent ways to get it:

```bash
# (a) activate once per terminal, then run as many commands as you like
micromamba activate ttbar
python -m vcb.run ...
pytest tests/

# (b) don't activate at all — prefix each command (what condor/ and AGENTS.md use)
micromamba run -n ttbar python -m vcb.run ...
micromamba run -n ttbar pytest tests/
```

Activation does not persist across terminals, reconnects, or condor jobs — those
start a fresh shell, so they need (a) again or (b). Every command in this README
assumes one of the two; they are written in the bare form for readability.

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
per-batch parquet + ROOT skims and `outfiles/<tag>.pkl` totals. The ROOT also
carries a single-entry `Norm` tree holding this run's `np_nominal`, making it
self-describing for normalization. No `finalWeight` is written — append it
afterwards with [condor/scripts/normalize.py](condor/scripts/normalize.py),
which must see the whole sample to know the denominator.

When only the ROOT skim is wanted:

```bash
python -m vcb.run \
  --year 2024 \
  --files /path/to/<file>_CMSSW_15_CHARGE_NanoAOD.root \
  --root-only --output-root-location /where/the/roots/go \
  --chunksize 100000 --maxchunks 0
```

| Flag | Effect |
|---|---|
| `--root-only` | Write only the skim ROOT: no parquet, no `num_batches_<tag>.txt`, and the `outparquet/` scratch is deleted after the batches are assembled. Implies `--save-root`. `outfiles/<tag>.pkl` is still written — it carries `np_nominal`, without which the run cannot be normalized. |
| `--output-root-location <dir>` | Send the skim ROOT file(s) to `<dir>` instead of the run output directory. Created if missing. Works with or without `--root-only`. |

Every other flag — including the overlapping tag flags and the inert ones
inherited from `boostedhh` — is catalogued in [docs/cli.md](docs/cli.md).

Full 2024 production (93 `batch_*` dirs under
`Vcb/MC/TTtoLNuCB_Summer24MiniAODv6/NanoAOD-cmssw-charge/charge_Run3_2024_150X_v1/`)
via HTCondor: see [condor/README.md](condor/README.md).

## Tests

```bash
# unit tests (7 tests, ~10 s, no input data needed)
pytest tests/

# integration run: skims the ~1 GB fixture, regenerates the committed baselines
# in tests/outfile/, and runs the jet-tagger round-trip check (~ minutes)
python tests/test_run.py
```

Three files in `tests/outfile/` are **committed baselines**
(`test-output-schema.csv`, `test-output-0th-event.txt`,
`test-jet-tagger-roundtrip.txt`): an unexplained diff in any of them is a bug;
an expected diff should be reviewed and committed with the change that caused
it. What each artifact catches, the fixture location, and how the round-trip
check works: [docs/tests.md](docs/tests.md).

## 2024 calibration inputs

| Input | Value in place | Where |
|---|---|---|
| 2024 luminosity | 124,000 pb⁻¹ (124 fb⁻¹), CMS DP-2026/003 | `LUMI["2024"]` in [src/boostedhh/hh_vars.py](src/boostedhh/hh_vars.py) |
| σ(TTtoLNuCB) | ≈0.345 pb = σ_tt(923.6, NNLO+NNLL) × 2 × BR(W→ℓν) × BR(W→cb) | [src/boostedhh/xsecs.py](src/boostedhh/xsecs.py) |
| 2024 pileup weights | real Summer24 `Collisions24_CDEFGHI_goldenJSON` (eras C–I, no commissioning era B) | bundled `corrections/2024_puWeights.json.gz` |
| 2024 JEC + JER | compound `Summer24Prompt24_V5_MC_L1L2L3Res_AK4PFPuppi` on raw pT, then nominal JRV2 smearing on the corrected pT | bundled `corrections/2024_jet_jerc.json.gz` + `jer_smear.json.gz` |

Provenance for every number — which source it came from and why:
[docs/2024-inputs.md](docs/2024-inputs.md) and
[src/boostedhh/corrections/README.md](src/boostedhh/corrections/README.md).

> ⚠️ Do **not** substitute the gridpack/GenXsecAnalyzer cross section: the
> private POWHEG sample forces W→cb, so its generated xsec carries no `|Vcb|²`
> and would overcount the signal by ~2200×. Details in
> [docs/2024-inputs.md](docs/2024-inputs.md) item 2.

## Repo layout

```
src/vcb/                 analysis package (run.py, HLTs.py, processors/)
src/boostedhh/           vendored framework (do not auto-format; see VENDORED.md)
condor/                  batch submission + post-processing scripts
tests/                   pytest units + integration script + committed baselines
diagnostics/             plotting / checking helper scripts (not part of the package)
docs/                    processor, CLI, normalization, tests, history + archive/
```
