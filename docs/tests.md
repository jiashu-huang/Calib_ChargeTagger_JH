# Tests & regression baselines

Two layers: fast pytest units that need no input data, and a standalone
integration run that regenerates the committed regression baselines from the
~1 GB test fixture.

## Unit tests

```bash
pytest tests/          # 7 tests, ~10 s, no input data needed
```

| File | What it does |
|---|---|
| [tests/test_package.py](../tests/test_package.py) | One smoke test: the installed distribution's version matches `vcb.__version__`. Fails if `vcb` isn't importable or the editable install is stale/missing — i.e. it catches a broken **Setup** before anything else does. |
| [tests/test_vcb_gen_truth.py](../tests/test_vcb_gen_truth.py) | Six unit tests for the gen-truth helpers in [src/vcb/processors/GenSelection.py](../src/vcb/processors/GenSelection.py), run on hand-built awkward arrays (no NanoAOD file). Covers: **(1)** W decay-mode masks split hadronic vs. leptonic with τ counted as *leptonic*; **(2)** the `GenWto{UD,US,CD,CS,UB,BC}` flavor tags are unordered (q1/q2 swap-invariant) and mutually exclusive — exactly one fires per W; **(3)** gen quarks stored with mass 0 get the PDG mass back from their flavor (c → 1.27, b → 4.18 GeV; light quarks stay 0, already-non-zero masses untouched); **(4)–(6)** lepton mass, charge, and flavor come from the PDG id with the right sign convention (`11` → −1, `-11` → +1) and flavor stored as \|pdgId\|; and throughout, missing entries stay `PAD_VAL` rather than silently becoming 0. |
| [tests/test_run.py](../tests/test_run.py) | **Not a pytest test** — a standalone end-to-end script (pytest collects no tests from it). Runs the real skimmer on one NanoAOD file and regenerates the regression artifacts in `tests/outfile/`. Needs the fixture and takes a few minutes. |

## The integration run

```bash
# fixture is git-ignored — copy it in once
cp /isilon/export/home/jhuan166/Vcb/Calib_ChargeTagger/tests/data/test-input.root tests/data/

python tests/test_run.py            # defaults: tests/data/test-input.root, --year 2024
```

It produces six files in `tests/outfile/`, three of which are **committed
baselines** — an unexplained diff in any of them is a bug, an expected diff
should be reviewed and committed with the change that caused it:

| Artifact | Committed? | Purpose |
|---|---|---|
| `test-output-schema.csv` | **yes** | every output branch name + ROOT type — catches accidentally added/dropped/retyped branches |
| `test-output-0th-event.txt` | **yes** | full value dump of event 0 — catches value-level changes (e.g. the JEC V1→V5 + JER shift moved jet pT) |
| `test-jet-tagger-roundtrip.txt` | **yes** | per-jet input↔output tagger check over *every* event, via `diagnostics/check_jet_tagger_roundtrip.py` — see below. A `FAIL` exits `tests/test_run.py` non-zero |
| `test-output.root` | no (git-ignored) | the skim itself |
| `test-output_jet_pt.pdf` | no (git-ignored) | unweighted AK4 jet pT plot, via `diagnostics/plot_jet_pt.py` — an eyeball check |
| `test-output_trigger_lepton_pt_flavor.pdf` | no (git-ignored) | trigger lepton pT split by `TriggerLeptonFlav`, via `diagnostics/plot_trigger_lepton_pt_flavor.py`. Weighted by `finalWeight` when the branch exists, else 1.0/event. The turn-ons should land exactly on the offline cuts in [objects.py](../src/vcb/processors/objects.py) — 26 GeV for muons (IsoMu24), 32 GeV for 2024 electrons (Ele30) |

## The jet tagger round-trip check

`diagnostics/check_jet_tagger_roundtrip.py` answers one question: **did the skim
keep each jet's tagger scores attached to the right jet?** For every output
event it finds the same event in the source NanoAOD by `(run, luminosityBlock,
event)`, matches each saved jet slot to an input jet by eta/phi — which JECs
leave untouched, so the match is exact — and compares
`ak4JetParTNegvsAll`, `ak4JetParTPosvsAll`, `ak4JetParTPosvsNeg`,
`ak4JetbtagPNetB`, `ak4JetbtagPNetCvB` and `ak4JetbtagPNetCvNotB` against the
input values.

Input jets that never reach the output are classified, not ignored. The skimmer
drops a jet for exactly four reasons — it sits within `dR <= 0.4` of the trigger
lepton used for cleaning, it fails corrected `pT > 15 GeV` or `|eta| < 4.7`, or
it fell past the 8 saved slots — so anything left over lands in `UNEXPLAINED`
and fails the check.

The corrected pT is not stored for dropped jets, so by default the script
re-applies the same JEC/JER the skimmer used. Those corrections are
deterministic, and the script asserts that they reproduce every saved
`ak4JetPt` bit for bit; that also lets it cross-check the saved `nJets` against
the jets that actually pass the selection. `--no-jec` skips the recompute (~28 s
→ ~12 s on the test fixture) at the cost of leaving the pT cut assumed rather
than verified.

```bash
# the test fixture
micromamba run -n ttbar python diagnostics/check_jet_tagger_roundtrip.py

# a real Condor batch — pass the whole input directory, since one job skims 5 files
micromamba run -n ttbar python diagnostics/check_jet_tagger_roundtrip.py \
  --output-file "$INPUT/processed-nano/<tag>/roots/batch_000.root" \
  --input-file  "$INPUT/batch_000" \
  --report      batch_000-roundtrip.txt
```

`--input-file` takes any number of files or a directory; every input that fed
the output must be listed, and the script errors out if two of them repeat a
`(run, luminosityBlock, event)` key — which is exactly the "merged copy left
inside a `batch_*` dir" hazard described in
[condor/README.md](../condor/README.md).

On the frozen 2024 fixture all 2,032,902 tagger comparisons across 338,817 saved
jets are identical, and all 121,726 dropped input jets are accounted for
(60,016 lepton-cleaned, 52,664 below the pT cut, 2,223 out of eta range, 6,823
truncated past 8 slots).
