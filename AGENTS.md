# AGENTS.md

Operating notes for agents working in `Calib_ChargeTagger_JH`. Run all
commands from the repository root unless stated otherwise.

## Environment & setup

- **Python / Coffea (the skimmer):** the `ttbar` micromamba environment.
  Prefix commands with `micromamba run -n ttbar ...`, or
  `micromamba activate ttbar` for an interactive shell. One editable install:

  ```bash
  micromamba env create -f environment.yaml   # once per machine
  micromamba run -n ttbar pip install -e ".[diagnostics,test]"
  ```

  This installs both `vcb` and the vendored `boostedhh` (single source tree
  under `src/`). Do **not** pip-install `bbtautau` or the upstream
  `boostedhh` — they would shadow this repo's code.

- **`hadd` (merge step):** the ROOT bundled in the `ttbar` env works
  (`micromamba run -n ttbar hadd ...`, verified). A CMSSW runtime
  (`../CMSSW_15_1_0_patch4/src` + `scramv1 runtime`) also works if preferred.

## Ground rules

- **`src/boostedhh/` is vendored upstream code — do not auto-format or lint
  it.** ruff and the pre-commit hooks exclude it; keep it that way so
  `diff -r` against LPC-HH/boostedhh @ `71bd456` stays trivial. Sync by diff,
  not by rewrite. Record any deliberate local change in
  [src/boostedhh/VENDORED.md](src/boostedhh/VENDORED.md).
- **`diagnostics/` are standalone scripts copied as-is** from the old repo;
  also excluded from lint.
- Placeholder 2024 inputs (lumi, xsec, pileup, JER) are tracked in
  [SHOPPING-LIST.md](SHOPPING-LIST.md) — update it if you resolve or add one.
- Committed regression baselines live in `tests/outfile/`
  (`test-output-schema.csv`, `test-output-0th-event.txt`). If a change is
  *supposed* to alter the skim output, regenerate them with
  `micromamba run -n ttbar python tests/test_run.py` and commit the diff;
  unexplained baseline diffs are bugs.

## Orientation

- [README.md](README.md) — purpose, setup, how to run.
- [docs/processor.md](docs/processor.md) — how the skimmer works internally.
- [condor/README.md](condor/README.md) — batch production on HTCondor.
- [docs/history.md](docs/history.md) — lineage back to the old
  `Calib_ChargeTagger` repo and its logs.

## Checks before committing

```bash
micromamba run -n ttbar ruff check src/vcb tests   # lint (excludes vendored code)
micromamba run -n ttbar python -m pytest tests/ -q # unit tests, no data needed
micromamba run -n ttbar pre-commit run --all-files # what the hooks will enforce
```

The integration run (`tests/test_run.py`) needs the ~1 GB fixture at
`tests/data/test-input.root` (copy from the old repo, see README) and takes a
few minutes.
