# AGENTS.md

`Calib_ChargeTagger_JH` is the NanoAOD skimmer for the |Vcb| analysis and
jet-charge-tagger calibration. Command examples assume the repository root.

Complete requested changes, including relevant validation and fixes for
failures they introduce. Routine local edits and checks within that scope
need no separate approval at each step.

## Environment

- Use `micromamba run -n ttbar ...` for Python/Coffea commands, or activate
  `ttbar` in an interactive shell. See [setup](README.md#setup) when creating
  the environment or changing dependencies. The editable install supplies
  both `vcb` and vendored `boostedhh` from `src/`; do not install `bbtautau`
  or upstream `boostedhh`, which would shadow this code.
- For merging, use `micromamba run -n ttbar hadd ...`. The CMSSW runtime in
  `../CMSSW_15_1_0_patch4/src` is also an option.

## Repository constraints

- `src/boostedhh/` is vendored from LPC-HH/boostedhh @ `71bd456`. Do not
  auto-format or lint it; preserve its exclusion in `pyproject.toml`. Sync
  by diff and record deliberate local changes in
  [VENDORED.md](src/boostedhh/VENDORED.md).
- `diagnostics/` is excluded from lint by policy. Its
  `check_jet_tagger_roundtrip.py` and `plot_trigger_lepton_pt_flavor.py` are
  maintained parts of `tests/test_run.py`, despite that exclusion.
- Keep the documentation map in `README.md` and durable details in `docs/`.
  Move superseded notes to `docs/archive/` with a header naming their
  replacement. Root `PLAN.md` is ignored scratch; promote durable content
  before finishing.
- Condor workers use the live checkout. Keep its source fixed while a
  production is running; use an isolated checkout for concurrent edits.

## Documentation by task

Read the guides relevant to the task; [README.md](README.md) has the full map.

- Event selection and weights: [event synopsis](docs/event-synopsis.md).
- Object corrections and output fields: [object synopsis](docs/object-synopsis.md).
- CLI behavior: [CLI reference](docs/cli.md).
- Batch production, normalization, and merging: [Condor guide](condor/README.md).
- Test selection and fixture setup: [tests](docs/tests.md).

## Validation

For documentation-only edits, review the diff and links. For Python changes,
lint affected paths within `src/vcb`, `tests`, and `condor`, and run relevant
unit tests. Use the full checks below when changes span modules or focused
checks leave uncertainty. There are no pre-commit hooks to run them for you.

```bash
micromamba run -n ttbar ruff check src/vcb tests condor
micromamba run -n ttbar python -m pytest tests/ -q  # no NanoAOD fixture needed
```

For changes affecting skim output or integration behavior, run
`micromamba run -n ttbar python tests/test_run.py`. It needs the ~1 GB
`tests/data/test-input.root` fixture and takes a few minutes. It regenerates
three tracked baselines in `tests/outfile/`: `test-output-schema.csv`,
`test-output-0th-event.txt`, and `test-jet-tagger-roundtrip.txt`. Review each
diff and include intentional updates with the change; unexplained differences
are bugs. The round-trip report must end in `VERDICT: PASS`; the script also
fails if an output event lacks a trigger lepton.

If a needed dependency or fixture is unavailable, complete feasible checks
and report what remains unverified. Once relevant checks pass, broaden or
repeat them only for new changes, failures, or unresolved concerns.
