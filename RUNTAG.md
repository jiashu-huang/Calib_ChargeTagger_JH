# `python -m vcb.run` flags

Every command-line flag, where it is defined, and what it actually does in this
repo. Several are inherited from vendored `boostedhh` and are inert here — those
are marked. Written 2026-07-26.

Flags come from four places, in this order:

| Source | Flags |
|---|---|
| [`run_utils.parse_common_run_args`](src/boostedhh/run_utils.py#L78) | `--starti --endi --executor --files --files-name --batch-size --yaml --file-tag` |
| [`run_utils.parse_common_hh_args`](src/boostedhh/run_utils.py#L107) | `--year --samples --subsamples --maxchunks --chunksize --save-systematics --save-root` |
| [`vcb_utils.parse_common_run_args`](src/vcb/vcb_utils.py#L47) | `--processor --region --nano-version --prescale-factor` |
| [`vcb/run.py`](src/vcb/run.py) | `--skimmer --naming-tag --outdir --root-only --output-root-location` |

Boolean flags are mutually exclusive pairs: `add_bool_arg` generates a `--no-<name>`
alongside each of `--save-root` and `--save-systematics`. `--root-only` is a plain
`store_true` with no negation.

`finalWeight` has no flag at all: the skimmer never writes it. It is appended in a
second pass by [condor/scripts/normalize.py](condor/scripts/normalize.py), which
needs the whole sample to know the denominator.

## What each one does

### Input

| Flag | Default | Effect |
|---|---|---|
| `--year` | *required* | `2018 / 2022 / 2022EE / 2023 / 2023BPix / 2024`. Selects LUMI, JEC/JER, pile-up and jet-veto payloads. `nargs="+"`, but more than one value raises. |
| `--files` | `[]` | Explicit list of input NanoAOD paths. **The only working input path in this repo** — see *Inert* below. |
| `--files-name` | `TTtoLNuCB` | Dataset label. The fileset key is `<year>_<files-name>`, and the skimmer splits it back apart to look up the cross section. |
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
| `--processor` | `skimmer` | Only choice is `skimmer`. |
| `--executor` | `iterative` | Only `dask` vs. not-`dask` is honoured — see *Inert*. |
| `--region` | `signal` | Only choice is `signal`; indexes a one-entry HLT dict. |
| `--nano-version` | `v12_private` | Only choice. Reaches `get_jec_jets`, where the gate is `"v12" not in nano_version` — always false, so a no-op. |
| `--prescale-factor` | `None` | Keep only events with `event % N == 0` ([vcbSkimmer.py:600](src/vcb/processors/vcbSkimmer.py#L600)). Adds a `prescale` row to the cutflow. Useful for a fast, statistically valid pass over 1/N of a sample. **Note:** `np_nominal` still counts every event read, so a prescaled run's `finalWeight` over-predicts yields by roughly N — prescale for timing and shape checks, not for yields. |

## Overlaps

**`--naming-tag` overrides `--file-tag`.** Both set the output tag. Precedence
([run.py:328](src/vcb/run.py#L328)): `--naming-tag`, then `--file-tag`, then the
first 32 characters of the first input filename's stem. No warning if both are
given.

**`--output-root-location` overrides `--outdir` for the ROOT only.** Not a
conflict — nested scopes. The pickle, parquet and `num_batches` file stay in
`--outdir` regardless.

**`--root-only` implies `--save-root`.** Set in the `__main__` block, so
`--root-only --no-save-root` silently resolves to ROOT output on.

**`--files` beats `--samples` / `--subsamples` / `--yaml` / `--starti` / `--endi`.**
If `--files` is non-empty the whole index-JSON branch is skipped and those five
are ignored silently. Within the other branch, `--yaml` beats
`--samples`/`--subsamples`.

**`--files` also flips `skipbadfiles` to `False`** ([run.py:284](src/vcb/run.py#L284)).
A hidden side effect worth knowing: with `--files`, an unreadable input raises
instead of being skipped. This is why a NanoAOD with no `Events` tree kills the
whole job rather than being dropped.

**`--files-name` silently controls normalization.** The skimmer reconstructs the
dataset name from the fileset key and looks it up in `xsecs`
([SkimmerABC:73](src/boostedhh/processors/SkimmerABC.py#L73)). A name with no
matching entry logs `Weight not normalized to cross section` and falls back to
`weight_norm = 1` — the run succeeds with wrong weights. Keep it `TTtoLNuCB`.

## Inert flags

Accepted by the parser, no effect on the output:

| Flag | Why |
|---|---|
| `--executor futures` | [run.py](src/vcb/run.py) never forwards `executor=` to `run_utils.run`, so anything other than `dask` runs **iteratively**. `--executor futures` is silently a no-op. |
| `--executor dask` | [`run_dask`](src/boostedhh/run_utils.py#L154) hardcodes an LPC `LPCCondorCluster` with `transfer_input_files="src/HH4b"`. Not usable here; use `condor/` instead. |
| `--samples` `--subsamples` `--yaml` `--starti` `--endi` | All feed `get_fileset("data/index_<year>.json", ...)`. That file does not exist in this repo, so these only work via `--files`. (`--starti`/`--endi` also appear in the naming-tag fallback, but only when no input filename can be found.) |
| `--nano-version`, `--region`, `--processor` | Single-choice enums. |

## Worked examples

```bash
# local single file, everything on
python -m vcb.run --year 2024 --files /path/to/file.root \
  --save-root --chunksize 100000 --maxchunks 0

# ROOT only, sent somewhere specific
python -m vcb.run --year 2024 --files /path/to/file.root \
  --root-only --output-root-location /where/the/roots/go \
  --chunksize 100000 --maxchunks 0

# what condor runs per batch
python -m vcb.run --processor skimmer --skimmer vcbSkimmer --year 2024 \
  --files <batch files> --files-name TTtoLNuCB --naming-tag batch_000 \
  --save-root --chunksize 1000000 --maxchunks 0 --batch-size 9999 \
  --outdir <work>
```
