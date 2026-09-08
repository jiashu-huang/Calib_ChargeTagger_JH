# Calib_ChargeTagger_JH

NanoAOD skimmer for the |Vcb| analysis and jet-charge-tagger calibration.
It processes the private 2024 Summer24 `TTtoLNu2Q` and `TTtoLNuCB` MC samples
into ROOT files containing selected events, calibrated objects, generator
labels, and weights for analysis and SPANet input preparation.

Start with these two guides:

- [Event synopsis](docs/event-synopsis.md): processing order, event vetoes,
  weight factors, and second-pass normalization.
- [Object synopsis](docs/object-synopsis.md): electron, muon, jet, and MET
  processing, followed by their output fields.

## Processing and output

1. Correct and select leptons and AK4 jets, choose a trigger lepton, and
   calculate PUPPI MET.
2. Apply trigger, event-quality, jet-veto-map, and lepton requirements. Save
   passing events with generator labels and first-pass weights.
3. Normalize the completed outputs for each dataset in a second pass to
   obtain `finalWeight`.
4. Apply analysis selections and prepare training inputs downstream.

The ROOT `Events` tree has fixed slots for up to three electrons, three muons,
10 reconstructed jets, and 25 generator jets, plus a chosen trigger lepton,
MET, and event quantities. The processor keeps analysis jets above 15 GeV;
the later 20 GeV cut belongs downstream. It imposes no minimum jet count,
b-tag count, or MET magnitude.

`GenQ1` is the down-type W daughter and `GenQ2` the up-type daughter. For
W → cb, Q1 is b and Q2 is c. The four `Gen*JetIdx` labels identify distinct
saved jet slots, with `-1` for an unmatched parton. Field names and padding
conventions are in the [object synopsis](docs/object-synopsis.md).

## Current scope

- The supported production target is 2024 MC with AK4 PUPPI jets. Nominal
  electron smearing, JEC/JER, pileup weights, and trigger-lepton efficiency
  scale factors are applied. The 2024 data JEC and AK8 paths are incomplete.
- `--save-systematics` writes PU, shower, and lepton-SF weight alternatives.
  JES/JER variations and ttbar PDF-weight output are not implemented. The six
  renormalization/factorization-scale alternatives are saved independently of
  this flag when available in the input.
- Four top-pT factors are saved separately. They are not applied to `weight`
  or `finalWeight`; the
  [event synopsis](docs/event-synopsis.md#other-weight-terms-and-saved-alternatives)
  describes their use and normalization.

Type-1 MET uses the jet direction after muon subtraction and includes the
auxiliary `CorrT1METJet` collection after nominal JEC/JER. These auxiliary jets
contribute to MET only. Existing August 2026 skims predate both updates and
need reprocessing to include them.

The 2026-09-07 audit checked the headers and required branches of all 465
signal and 11,014 inclusive-sample input files; every file passed. Fresh
processing of eight complete files passed the event-selection, truth-matching,
jet-tagger, and second-pass weight checks. The audit did not read every event
in the full input set.

## Setup

Run commands from this repository's root directory. Create the `ttbar`
environment if it does not already exist, then install the package:

```bash
micromamba create -f environment.yaml
micromamba run -n ttbar pip install -e ".[diagnostics,test]"
```

This editable install uses `src/vcb` and the bundled `src/boostedhh` directly.
Source edits take effect on the next run. Reinstall when dependencies change.
Do not install a separate `bbtautau` or upstream `boostedhh` into this environment;
it would conflict with the bundled framework.

The commands below use `micromamba run -n ttbar`. Alternatively, activate
`ttbar` once in your shell and omit that prefix.

## Run locally

Process one input file with nominal weights:

```bash
micromamba run -n ttbar python -m vcb.run \
  --year 2024 \
  --files /path/to/input_CMSSW_15_CHARGE_NanoAOD.root \
  --files-name TTtoLNuCB \
  --root-only --no-save-systematics \
  --chunksize 100000 --maxchunks 0 --batch-size 9999
```

Use `--files-name TTtoLNu2Q` for the inclusive semileptonic sample. The label
is required with `--files` and determines the cross section and truth routines.
`--maxchunks 0` processes the whole input; use `--maxchunks 1` for a short check.

Outputs go to `outputs/<timestamp>/`, linked by `outputs/latest`:

- `nano_skim_<tag>_batch_0.root`: selected events and a `Norm` tree with the
  run's normalization totals when the run produces one ROOT file.
- `outfiles/<tag>.pkl`: cutflow and normalization totals, including totals
  for requested weight variations.

`--root-only` retains the ROOT and pickle outputs. Replace it with
`--save-root` to retain a Parquet copy as well. Use `--outdir` to choose the
run directory or `--output-root-location` to send ROOT files elsewhere.
Replace `--no-save-systematics` with `--save-systematics` to save the weight
alternatives. See the [CLI reference](docs/cli.md) for all options.

## Batch production and normalization

The [Condor guide](condor/README.md) covers submission and output collection.
Its processed directory contains `roots/`, `pickles/`, and `metadata/`.
After the jobs finish, normalize and validate that dataset's outputs:

```bash
micromamba run -n ttbar python condor/scripts/normalize.py \
  --processed-dir /path/to/processed-nano/production_tag

micromamba run -n ttbar python condor/scripts/validate_processed.py \
  --processed-dir /path/to/processed-nano/production_tag
```

The validator's default schema covers the 681 first-pass branches from a
nominal run and also allows `finalWeight`. For a run with `--save-systematics`,
use `--schema-baseline /path/to/systematics-schema.csv` with the matching
699-branch schema. Otherwise the validator reports the 18 expected up/down
weight branches as unexpected extras. This is a schema-check limitation;
the audit passed all remaining checks and passed schema validation with the
matching baseline. See the
[weight-variation list](docs/event-synopsis.md#other-weight-terms-and-saved-alternatives).

The skimmer writes `weight`, which already includes cross section × luminosity.
The second pass appends:

```text
finalWeight = weight / global_np_nominal

global_np_nominal = sum(genWeight × pileup weight over all processed input events)
```

Rejected events contribute to the denominator. Lepton SFs appear only in the
numerator. Normalize each dataset separately, and use `finalWeight` for
analysis yields. Existing `finalWeight` branches are skipped; use `--force`
to recompute them if the contributing batch set changes. Details are in the
[event synopsis](docs/event-synopsis.md#second-pass-finalweight).

An optional final merge is handled by `condor/scripts/merge_processed.py`;
see the [Condor guide](condor/README.md). Workers use the live checkout, so
keep the source fixed while a production is running. `campaign.json` records
the commit, branch, and working-tree status at submission.

## Checks

```bash
micromamba run -n ttbar ruff check src/vcb tests condor
micromamba run -n ttbar python -m pytest tests/ -q
```

The integration check needs `tests/data/test-input.root`:

```bash
micromamba run -n ttbar python tests/test_run.py
```

It regenerates the tracked schema, example-event, and jet-tagger round-trip
baselines in `tests/outfile/`. Review any changes; the round-trip report must
end in `VERDICT: PASS`. Fixture setup and check details are in
[docs/tests.md](docs/tests.md).

## Documentation

| Document | Contents |
| --- | --- |
| [Event synopsis](docs/event-synopsis.md) | Event selection, all weight terms, and second-pass normalization |
| [Object synopsis](docs/object-synopsis.md) | Object processing and output fields |
| [Output schema](tests/outfile/test-output-schema.csv) | Branch names and types for the nominal test skim, before `finalWeight` |
| [CLI reference](docs/cli.md) | Run options and defaults |
| [Condor guide](condor/README.md) | Submit, normalize, validate, and merge |
| [2024 inputs](docs/2024-inputs.md) | Calibration and cross-section sources |
| [Tests](docs/tests.md) | Unit tests, integration fixture, and baselines |
| [Processor walkthrough](docs/processor.md) | Longer implementation notes; use the synopses for the current processing sequence |
| [Normalization design](docs/normalization.md) | Design history of the second pass |
| [Project history](docs/history.md) | Origins in `Calib_ChargeTagger` and earlier changes |
| [Jet and PU payloads](src/boostedhh/corrections/README.md) | Bundled corrections and their sources |
| [Lepton payloads](src/vcb/corrections/README.md) | Bundled electron and muon corrections |
| [Bundled framework](src/boostedhh/VENDORED.md) | Upstream version and local changes to `boostedhh` |
| [Agent instructions](AGENTS.md) | Repository conventions and required checks |

## Repository layout

```text
src/vcb/        analysis code and lepton corrections
src/boostedhh/  bundled framework and jet/pileup corrections
condor/        production and post-processing scripts
tests/         unit tests, integration check, and regression baselines
diagnostics/   analysis and validation scripts
docs/          synopses, references, and historical notes
```
