# `python -m vcb.run` flags

Every command-line flag, where it is defined, and what it actually does in this
repo. Several are inherited from vendored `boostedhh` and are inert here — those
are marked. Written 2026-07-26.

Flags come from four places, in this order:

| Source | Flags |
|---|---|
| [`run_utils.parse_common_run_args`](../src/boostedhh/run_utils.py#L78) | `--starti --endi --executor --files --files-name --batch-size --yaml --file-tag` |
| [`run_utils.parse_common_hh_args`](../src/boostedhh/run_utils.py#L107) | `--year --samples --subsamples --maxchunks --chunksize --save-systematics --save-root` |
| [`vcb_utils.parse_common_run_args`](../src/vcb/vcb_utils.py#L47) | `--processor --region --nano-version --prescale-factor` |
| [`vcb/run.py`](../src/vcb/run.py) | `--skimmer --kinematic-variation --muon-pt-variation --naming-tag --outdir --root-only --output-root-location` |

Boolean flags are mutually exclusive pairs: `add_bool_arg` generates a `--no-<name>`
alongside each of `--save-root` and `--save-systematics`. `--root-only` is a plain
`store_true` with no negation.

`finalWeight` has no flag at all: the skimmer never writes it. It is appended in a
second pass by [condor/scripts/normalize.py](../condor/scripts/normalize.py), which
needs the whole sample to know the denominator.

## What each one does

### Input

| Flag | Default | Effect |
|---|---|---|
| `--year` | *required* | `2018 / 2022 / 2022EE / 2023 / 2023BPix / 2024`. Selects LUMI, JEC/JER, pile-up and jet-veto payloads. `nargs="+"`, but more than one value raises. |
| `--files` | `[]` | Explicit list of input NanoAOD paths. **The only working input path in this repo** — see *Inert* below. |
| `--files-name` | *required with `--files`* | Dataset label. The fileset key is `<year>_<files-name>`, and the skimmer splits it back apart to look up the cross section. No default — see below. |
| `--samples` `--subsamples` `--yaml` `--starti` `--endi` | — | Index-JSON workflow. Inert here. |

### Chunking

| Flag | Default | Effect |
|---|---|---|
| `--chunksize` | `10000` | Events per coffea chunk. |
| `--maxchunks` | `0` | Cap on chunks processed; `0` = no limit. Useful for quick tests. |
| `--batch-size` | `20` | How many intermediate parquet pieces get merged into one output file. Condor keeps this at `9999` so one job yields exactly one ROOT. |

These three are easy to confuse: `chunksize` is how much is read at a time,
`maxchunks` is how much is read in total, `batch-size` is how the results are
grouped on the way out.

### Output

| Flag | Default | Effect |
|---|---|---|
| `--outdir` | `outputs/<timestamp>/` | Directory for all of this run's outputs. `outputs/latest` is re-pointed here either way. |
| `--output-root-location` | `--outdir` | Directory for the skim ROOT file(s) only. Created if missing. |
| `--save-root` / `--no-save-root` | off | Write the ROOT skim alongside the parquet. |
| `--root-only` | off | Write *only* the ROOT skim: no parquet, no `num_batches_<tag>.txt`, and the `outparquet/` scratch is deleted afterwards. `outfiles/<tag>.pkl` is still written. |
| `--naming-tag` | first 32 chars of the input stem | Output file tag: `nano_skim_<tag>_batch_N.root`, `outfiles/<tag>.pkl`. |
| `--file-tag` | `None` | Same thing, lower precedence. |
| `--save-systematics` / `--no-save-systematics` | off | Also write `weight_<syst>Up/Down` branches and `np_<syst>Up/Down` totals. Off is why the baseline schema has `single_weight_pileup` but no pile-up variation branches. |

### Processor

| Flag | Default | Effect |
|---|---|---|
| `--skimmer` | `vcbSkimmer` | Module under `src/vcb/processors/` to run. Accepts `vcbSkimmer`, `vcbSkimmer.py`, or a path. |
| `--muon-pt-variation` | `nominal` | Active 2024 MC momentum pass. `all` runs nominal plus four total scale/resolution shifts from the original NanoAOD, each in its own subdirectory; see below. |
| `--kinematic-variation` | `nominal` | One 2024 MC object shift or a group (`all`, `jets`, `jes`, `jer`, `electron`, `muon`). Each pass reruns the complete skim; see below. |
| `--processor` | `skimmer` | Only choice is `skimmer`. |
| `--executor` | `iterative` | Only `dask` vs. not-`dask` is honoured — see *Inert*. |
| `--region` | `signal` | Only choice is `signal`; indexes a one-entry HLT dict. |
| `--nano-version` | `v12_private` | Only choice. Reaches `get_jec_jets`, where the gate is `"v12" not in nano_version` — always false, so a no-op. |
| `--prescale-factor` | `None` | Keep only events with `event % N == 0` ([vcbSkimmer.py:600](../src/vcb/processors/vcbSkimmer.py#L600)). Adds a `prescale` row to the cutflow. Useful for a fast, statistically valid pass over 1/N of a sample. **Note:** `np_nominal` still counts every event read, so a prescaled run's `finalWeight` over-predicts yields by roughly N — prescale for timing and shape checks, not for yields. |

## Kinematic variation passes

To produce nominal plus the full 27-source JES basis and global JER up/down:

```bash
micromamba run -n ttbar python -m vcb.run \
  --skimmer vcbSkimmer --year 2024 \
  --files tests/data/test-input.root --files-name TTtoLNuCB \
  --root-only --outdir outputs/jet_variations --kinematic-variation jets
```

Each pass starts from NanoAOD. It recalculates object selection, the trigger
lepton and its efficiency weights, jet cleaning/veto, sorting, counts, HT,
tag eligibility and parton assignments. Jet shifts also rebuild Type-1 MET
from the complete regular and auxiliary jet collections with correlated
per-jet factors. Electron shifts can therefore retain entering events.

| Group | Contents | Passes including nominal |
| --- | --- | ---: |
| `jes` | 27 signed JES source pairs | 55 |
| `jer` | Global JER up/down | 3 |
| `jets` | Full JES + global JER | 57 |
| `electron` | Electron scale/smearing up/down | 5 |
| `muon` | Muon total scale/resolution up/down | 5 |
| `all` | All of the above | 65 |

For a single pass use `jes_<Source>Up/Down`, `jerUp/Down`,
`electron_{scale,smear}Up/Down`, or `muon_{scale,resolution}Up/Down`.
For example, `--kinematic-variation jes_RelativeBalDown` selects one signed
source; the [manifest](jes-2024-full-source-manifest.json) lists all 27.
The previous muon component shifts remain available as
`muon_{scale,resolution}{Stat,Syst}Up/Down`. Components and totals are alternative
models. `Total`, reduced JES and regional JER are not additional independent
nuisances in the default model.

Groups write one subdirectory per pass under `--outdir` and, if supplied,
`--output-root-location`. Shifted filenames append `__<pass>` to the tag.
The `KinematicVariation` integer branch identifies each pass; IDs are fixed in
[`kinematic_variations.py`](../src/vcb/processors/kinematic_variations.py).
`outfiles/<tag>.kinematics.json` records its name, ID, jet options, input files
and jet-payload paths/hashes, including for a pass with no selected events.

Normalize and merge each pass separately. Each is a copy of the same MC
sample with the same all-input denominator; summing denominators across
passes would dilute the yield. `--save-systematics` independently adds
weight-only branches to each pass. All nonnominal passes require 2024 MC and
the local runner. Explicitly requested missing payloads or unsupported
configurations raise. Optional lepton-to-MET and unclustered-energy terms
are outside this implementation. Global JER and any later reduced model
still require nuisance-constraint checks in the final fit.

Condor supports the same single-pass names through
`condor/submit_batches.py --kinematic-variation <pass>`; generate a separate
campaign/tag per pass. Do not combine `--kinematic-variation` with an active
legacy `--muon-pt-variation`.

## Muon momentum passes

Nominal 2024 scale and resolution corrections run automatically. To produce
the nominal skim and all four total shifts with complete event reselection:

```bash
micromamba run -n ttbar python -m vcb.run \
  --processor skimmer --year 2024 \
  --files tests/data/test-input.root --files-name TTtoLNuCB \
  --root-only --outdir outputs/muon_variations --muon-pt-variation all
```

This writes subdirectories `nominal`, `scaleUp`, `scaleDown`, `resolutionUp`
and `resolutionDown`. An explicit `--output-root-location` gets the same
subdirectories. Non-nominal filenames include `__muon_<variation>` so separate
single-pass jobs can also share an output directory safely. `outputs/latest`
points to the last completed pass.

Each pass starts from the input events, replaces the active muon pT before
selection, and recalculates trigger-lepton choice, jet cleaning, generator
matching and efficiency weights. Thus it retains events entering under a shift.
Normalize each pass as a separate copy of the same sample using its all-input
denominator; never sum denominators across the five copies or normalize to
each pass's selected yield. Condor defaults to nominal; use its single-pass
`--kinematic-variation muon_<variation>` option for additional campaigns.

Individual choices are `nominal`, `scaleUp`, `scaleDown`, `resolutionUp`,
`resolutionDown`, or the eight component choices
`{scale,resolution}{Stat,Syst}{Up,Down}`. Total shifts combine statistical and
systematic errors in quadrature within each of the two sources. Use either
the total-source model or an explicitly defined component model in a fit;
do not count both as independent uncertainties. `MuonMomentumVariation` stores
the pass ID listed in [the implementation record](muon-momentum-2024-plan.md).

`--save-systematics` controls weight variations independently; combine it with
this option if those branches are needed. Stored varied muon-pT columns on a
nominal skim alone cannot recover events that failed its selection. Only
2024 MC supports shifted passes, using the local runner. Outside the validated
26–200 GeV range momenta stay unchanged and carry a coverage flag; these passes
do not supply the unresolved high-pT uncertainty treatment.

## Overlaps

**`--naming-tag` overrides `--file-tag`.** Both set the output tag. Precedence
([run.py:212](../src/vcb/run.py#L212)): `--naming-tag`, then `--file-tag`, then the
first 32 characters of the first input filename's stem. Since 2026-07-27 a
warning is printed when both are given.

**`--output-root-location` overrides `--outdir` for the ROOT only.** Not a
conflict — nested scopes. The pickle, parquet and `num_batches` file stay in
`--outdir` regardless.

**`--root-only` implies `--save-root`.** Set in the `__main__` block, so
`--root-only --no-save-root` silently resolves to ROOT output on.

**`--files` beats `--samples` / `--subsamples` / `--yaml` / `--starti` / `--endi`.**
If `--files` is non-empty the whole index-JSON branch is skipped and those five
are ignored silently. Within the other branch, `--yaml` beats
`--samples`/`--subsamples`.

**`--files` also flips `skipbadfiles` to `False`** ([run.py:284](../src/vcb/run.py#L284)).
A hidden side effect worth knowing: with `--files`, an unreadable input raises
instead of being skipped. This is why a NanoAOD with no `Events` tree kills the
whole job rather than being dropped.

**`--files-name` controls normalization, so it is mandatory.** The skimmer
reconstructs the dataset name from the fileset key and looks it up in `xsecs`
([SkimmerABC:73](../src/boostedhh/processors/SkimmerABC.py#L73)); the same label
also gates `gen_selection_dict` and the top-pT columns. Pass the sample name:

```bash
--files <batch files> --files-name TTtoLNu2Q
```

Two failure modes, one loud and one quiet:

- **Omitted entirely** — `vcb.run` exits non-zero before reading a file
  (`_require_files_name`). It defaulted to `TTtoLNuCB` until 2026-08-15, which
  made pointing `--files` at any other sample a silent ~1190× normalization
  error (`weight_norm` 4.28e4 instead of 5.09e7 for TTtoLNu2Q) — the
  cross-section warning below never fires, because `TTtoLNuCB` *is* in `xsecs`.
- **Present but unknown to `xsecs`** — logs `Weight not normalized to cross
  section` and falls back to `weight_norm = 1`. The run succeeds with unscaled
  weights. This is deliberate: it is how you skim a sample with no cross section
  on file.

## Inert flags

Accepted by the parser, no effect on the output:

| Flag | Why |
|---|---|
| `--executor futures` | [run.py](../src/vcb/run.py) never forwards `executor=` to `run_utils.run`, so anything other than `dask` runs **iteratively**. `--executor futures` is silently a no-op. |
| `--executor dask` | [`run_dask`](../src/boostedhh/run_utils.py#L154) hardcodes an LPC `LPCCondorCluster` with `transfer_input_files="src/HH4b"`. Not usable here; use `condor/` instead. |
| `--samples` `--subsamples` `--yaml` `--starti` `--endi` | All feed `get_fileset("data/index_<year>.json", ...)`. That file does not exist in this repo, so these only work via `--files`. (`--starti`/`--endi` also appear in the naming-tag fallback, but only when no input filename can be found.) |
| `--nano-version`, `--region`, `--processor` | Single-choice enums. |

## Worked examples

```bash
# local single file, everything on
python -m vcb.run --year 2024 --files /path/to/file.root --files-name TTtoLNuCB \
  --save-root --chunksize 100000 --maxchunks 0

# ROOT only, sent somewhere specific
python -m vcb.run --year 2024 --files /path/to/file.root --files-name TTtoLNuCB \
  --root-only --output-root-location /where/the/roots/go \
  --chunksize 100000 --maxchunks 0

# what condor runs per batch
python -m vcb.run --processor skimmer --skimmer vcbSkimmer --year 2024 \
  --files <batch files> --files-name TTtoLNuCB --naming-tag batch_000 \
  --save-root --chunksize 1000000 --maxchunks 0 --batch-size 9999 \
  --outdir <work>
```
