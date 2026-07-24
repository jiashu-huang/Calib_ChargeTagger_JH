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

### Trigger lepton selection

Relevant files: 
- leptons in [src/vcb/processors/objects.py](src/vcb/processors/objects.py),
- HLTs in [src/vcb/HLTs.py](src/vcb/HLTs.py),
- Reconciling two single-lepton HLTS: [src/vcb/processors/vcbSkimmer.py](src/vcb/processors/vcbSkimmer.py), 
  done through the main processing method for each chunk.

Each retained event is assigned one leading trigger lepton.  The lepton must
pass the offline selection, be matched to the object for the HLT path that
fired, and lie above that path's activation threshold. 

For 2024, `HLT_Ele30_WPTight_Gsf` selects an electron with pT ≥ 32 GeV and
|η| < 2.5, while `HLT_IsoMu24` selects a muon with pT ≥ 26 GeV and |η| < 2.4.
If both single-lepton paths fire, a trigger-ready muon is preferred; otherwise
use a trigger-ready electron; otherwise discard the event. 

This single per-event lepton is used for the trigger-lepton output branches and
AK4 jet cleaning.

### Jet energy correction (JEC)

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

**For every shell session**L You need the `ttbar` environment active befor you 
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
per-batch parquet + ROOT skims, `outfiles/<tag>.pkl` totals, and a
`finalWeight` column/branch (disable with `--no-write-final-weight` — condor
jobs do, then normalize globally).

Full 2024 production (93 `batch_*` dirs under
`Vcb/MC/TTtoLNuCB_Summer24MiniAODv6/NanoAOD-cmssw-charge/charge_Run3_2024_150X_v1/`)
via HTCondor: see [condor/README.md](condor/README.md).

## Tests

```bash
# unit tests (7 tests, ~10 s, no input data needed)
pytest tests/
```

| File | What it does |
|---|---|
| [tests/test_package.py](tests/test_package.py) | One smoke test: the installed distribution's version matches `vcb.__version__`. Fails if `vcb` isn't importable or the editable install is stale/missing — i.e. it catches a broken **Setup** before anything else does. |
| [tests/test_vcb_gen_truth.py](tests/test_vcb_gen_truth.py) | Six unit tests for the gen-truth helpers in [src/vcb/processors/GenSelection.py](src/vcb/processors/GenSelection.py), run on hand-built awkward arrays (no NanoAOD file). Covers: **(1)** W decay-mode masks split hadronic vs. leptonic with τ counted as *leptonic*; **(2)** the `GenWto{UD,US,CD,CS,UB,BC}` flavor tags are unordered (q1/q2 swap-invariant) and mutually exclusive — exactly one fires per W; **(3)** gen quarks stored with mass 0 get the PDG mass back from their flavor (c → 1.27, b → 4.18 GeV; light quarks stay 0, already-non-zero masses untouched); **(4)–(6)** lepton mass, charge, and flavor come from the PDG id with the right sign convention (`11` → −1, `-11` → +1) and flavor stored as \|pdgId\|; and throughout, missing entries stay `PAD_VAL` rather than silently becoming 0. |
| [tests/test_run.py](tests/test_run.py) | **Not a pytest test** — a standalone end-to-end script (pytest collects no tests from it). Runs the real skimmer on one NanoAOD file and regenerates the regression artifacts in `tests/outfile/`. Needs the ~1 GB fixture and takes a few minutes. |

The integration run: 

```bash
# fixture is git-ignored — copy it in once
cp /isilon/export/home/jhuan166/Vcb/Calib_ChargeTagger/tests/data/test-input.root tests/data/

python tests/test_run.py            # defaults: tests/data/test-input.root, --year 2024
```

It produces four files in `tests/outfile/`, two of which are **committed
baselines** — an unexplained diff in either is a bug, an expected diff should be
reviewed and committed with the change that caused it:

| Artifact | Committed? | Purpose |
|---|---|---|
| `test-output-schema.csv` | **yes** | every output branch name + ROOT type — catches accidentally added/dropped/retyped branches |
| `test-output-0th-event.txt` | **yes** | full value dump of event 0 — catches value-level changes (e.g. the JEC V1→V5 + JER shift moved jet pT) |
| `test-output.root` | no (git-ignored) | the skim itself |
| `test-output_jet_pt.pdf` | no (git-ignored) | unweighted AK4 jet pT plot, via `diagnostics/plot_jet_pt.py` — an eyeball check |

## 2024 calibration inputs

Calib_ChargeTagger is only up-to-date to 2023. We brought in 2024 inputs.
Provenance for every number, including which source it came from and why: 
[docs/2024-inputs.md](docs/2024-inputs.md).

| Input | Value in place | Where |
|---|---|---|
| 2024 luminosity | 124,000 pb⁻¹ (124 fb⁻¹), CMS DP-2026/003 | `LUMI["2024"]` in [src/boostedhh/hh_vars.py](src/boostedhh/hh_vars.py) |
| σ(TTtoLNuCB) | ≈0.345 pb = σ_tt(923.6, NNLO+NNLL) × 2 × BR(W→ℓν) × BR(W→cb) | [src/boostedhh/xsecs.py](src/boostedhh/xsecs.py) |
| 2024 pileup weights | real Summer24 `Collisions24_CDEFGHI_goldenJSON` (eras C–I, no commissioning era B) | bundled `corrections/2024_puWeights.json.gz` |
| 2024 JEC + JER | compound `Summer24Prompt24_V5_MC_L1L2L3Res_AK4PFPuppi` on raw pT, then nominal JRV2 smearing on the corrected pT | bundled `corrections/2024_jet_jerc.json.gz` + `jer_smear.json.gz` |

Both jet files are CAT Summer24 snapshots, loaded bundled-first with a CAT cvmfs
fallback; the pileup file comes from the LUM sibling of the same campaign
(jsonpog-integration has no `2024_Summer24` LUM entry). Details in
[src/boostedhh/corrections/README.md](src/boostedhh/corrections/README.md).
2022/2023 keep the bundled pickle JEC factories.

Two σ values are defensible for the cross section — theory σ_tt = 923.6 pb (used
here, matching the sibling `TTto*` entries and the CMS convention of normalizing
tt̄ MC to theory) or the measured 881 ± 30 pb; they agree within uncertainty and
it's a pure overall scale, so swapping is a one-number edit. Do *not* substitute
the gridpack/GenXsecAnalyzer xsec: the private POWHEG sample forces W→cb, so its
generated xsec carries no `|Vcb|²` and would overcount the signal by ~2200×.

### Known gaps (as of 2026-07-24)

- **No jet-energy variations.** JER up/down and JES systematics aren't wired —
  the Vcb skimmer consumes none (`jec_shifted_jetvars` unused). Nominal only.
- **2024 data L2L3Residual JEC and AK8 jets are no-ops** — this production is MC
  AK4 only.

## Repo layout

```
src/vcb/                 analysis package (run.py, HLTs.py, processors/)
src/boostedhh/           vendored framework (do not auto-format; see VENDORED.md)
condor/                  batch submission + post-processing scripts
tests/                   pytest units + integration script + committed baselines
diagnostics/             plotting / event-dump helper scripts (not part of the package)
docs/                    processor description, lineage, archived patch
```
