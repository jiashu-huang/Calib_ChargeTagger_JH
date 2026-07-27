# AGENTS.md

Operating notes for agents working in `Calib_ChargeTagger_JH`. Run all
commands from the repository root unless stated otherwise.

## Environment & setup

- **Python / Coffea (the skimmer):** the `ttbar` micromamba environment.
  Prefix commands with `micromamba run -n ttbar ...`, or
  `micromamba activate ttbar` for an interactive shell. One editable install:

  ```bash
  micromamba create -f environment.yaml       # once per machine
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
  it.** ruff excludes it via `pyproject.toml`; keep it that way so
  `diff -r` against LPC-HH/boostedhh @ `71bd456` stays trivial. Sync by diff,
  not by rewrite. Record any deliberate local change in
  [src/boostedhh/VENDORED.md](src/boostedhh/VENDORED.md).
- **`diagnostics/` are standalone scripts, excluded from lint by policy.**
  Most were copied as-is from the old repo, but two were written fresh in
  *this* repo and are load-bearing despite living here:
  `check_jet_tagger_roundtrip.py` (invoked by `tests/test_run.py`; its report
  is a committed baseline) and `plot_trigger_lepton_pt_flavor.py` (renders the
  trigger turn-on check plot). Treat those two as real code even though the
  linter skips them.
- **Docs layout:** the root `README.md` is the front door and carries the
  documentation map; deep dives and design records live in `docs/`
  (committed); superseded notes go to `docs/archive/` with a header saying
  what supersedes them. A root `PLAN.md` is git-ignored working scratch —
  promote anything durable out of it before finishing a task.
- Committed regression baselines live in `tests/outfile/`
  (`test-output-schema.csv`, `test-output-0th-event.txt`,
  `test-jet-tagger-roundtrip.txt`). If a change is *supposed* to alter the skim
  output, regenerate them with
  `micromamba run -n ttbar python tests/test_run.py` and commit the diff;
  unexplained baseline diffs are bugs. `test-jet-tagger-roundtrip.txt` must end
  in `VERDICT: PASS` — `tests/test_run.py` exits non-zero otherwise.

## Orientation

- [README.md](README.md) — purpose, setup, how to run, and the full
  documentation map.
- [docs/processor.md](docs/processor.md) — how the skimmer works internally.
- [docs/cli.md](docs/cli.md) — every `vcb.run` flag, incl. overlaps and inert ones.
- [condor/README.md](condor/README.md) — batch production on HTCondor.
- [docs/normalization.md](docs/normalization.md) — why `finalWeight` is a
  second pass (design record).
- [docs/tests.md](docs/tests.md) — test suite details and the jet-tagger
  round-trip check.
- [docs/history.md](docs/history.md) — lineage back to the old
  `Calib_ChargeTagger` repo and its logs.

## Checks before committing

```bash
micromamba run -n ttbar ruff check src/vcb tests condor  # lint (vendored code + diagnostics excluded)
micromamba run -n ttbar python -m pytest tests/ -q       # unit tests, no data needed
```

This repo does **not** use pre-commit — there are no hooks, so run the two
commands above by hand.

The integration run (`tests/test_run.py`) needs the ~1 GB fixture at
`tests/data/test-input.root` (copy from the old repo, see README) and takes a
few minutes.
