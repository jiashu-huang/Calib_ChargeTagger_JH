# Project History

Consolidated, chronological history of `Calib_ChargeTagger` (JH fork). This
distills the four original logs — `LOG.md`, `BRANCH_LOG.md`, `AI_LOG.md`, and
`STATE.md` — which are preserved verbatim under [`docs/archive/`](archive/).

- **Purpose & how to run:** see the top-level [`README.md`](../README.md).
- **How the processor works internally:** see [`docs/processor.md`](processor.md).
- **Condor batch production:** see [`condor/README.md`](../condor/README.md).

> This fork descends from Clara Ramon Alvarez's
> [`cramonal/Calib_ChargeTagger`](https://github.com/cramonal/Calib_ChargeTagger),
> re-purposed for the Vcb charge-tagger calibration study of semileptonic
> `ttbar`: **pp → tt̄, (t → bW, W → cb̄), (t̄ → b̄W, W → ℓν)**.

---

## ⚠️ Known discrepancies / pending 2024 work

As of **2026-07-14**, the committed and working-tree code targets **2022** MC.
Before running on the new 2024 samples under `Vcb/MC/`, the following gaps must
be resolved (discovered during a pre-run review, not yet fixed):

1. **Electron trigger is 2022-only.** `vcbSkimmer.py` hard-codes
   `HLT_Ele32_WPTight_Gsf` and `objects.HLT_ELE32_LEPTON_PT = 35.0`. The intended
   2024 single-electron trigger is **`HLT_Ele30_WPTight_Gsf`**. Measured on the
   2024 test fixture (`tests/data/test-input.root`, 208,780 events): `IsoMu24`
   fires 22.0%, `Ele30` 16.1%, `Ele32` 15.5% — so **both electron branches exist
   and fire** in this file; the Ele32 path is not silently empty here, and the
   Ele30↔Ele32 difference is only ~0.6 pp. The switch to Ele30 is still required
   to match the stated analysis trigger, and matters more because the code guards
   with `if "Ele32_WPTight_Gsf" in events.HLT.fields` → on any sample where Ele32
   is absent, the electron path would silently become all-`False` and, combined
   with `single_lep_trigger = IsoMu24 | Ele32`, drop the electron channel
   entirely. Fix: switch to Ele30 (branch name, the `HLT_ELE30_LEPTON_PT` pT
   threshold ~31 GeV, and the trigger-matching filter bit).

2. **`--year 2024` is not a valid option.** The `--year` choices in
   `boostedhh/run_utils.py` are `2018, 2022, 2022EE, 2023, 2023BPix` — no 2024.
   `JECs(year)`, the jet-veto map (`2022_jetvetomaps.json`), and pileup/PS
   corrections are all year-keyed, so 2024 support must be wired in before the
   skimmer produces correct output on the 2024 era (`Run3_2024`, global tag
   `150X_mcRun3_2024_realistic_v2`).

3. **Integration test still points at the 2022 file.** `AGENTS.md`'s test file is
   the 2022 `MINIAODSIM`-derived NanoAOD. A 2024 test fixture under
   `Vcb/MC/TTtoLNuCB_Summer24MiniAODv6/NanoAOD-cmssw-charge/` should be added when
   2024 support lands.

The 2024 input data is staged and ready:
`MC/TTtoLNuCB_Summer24MiniAODv6/NanoAOD-cmssw-charge/charge_Run3_2024_150X_v1/`
holds 93 `batch_*` dirs (445 ROOT files, ~62 GB), which maps cleanly onto the
`condor/submit_batches.py` one-job-per-`batch_*` workflow.

---

## Timeline

### 2025-01 — Setup and first runs

- **01-08 to 01-13:** Environment setup. The `boostedhh` submodule initially
  failed `pip install -e .` because it was empty; fixed with
  `git submodule update --init --recursive` before installing.
- **01-14 to 01-17:** First skimmer runs. Hit `NameError: name 'bcut' is not
  defined` in `ttSkimmer.py`; patched the b-jet count to use
  `self.ak4_bjet_selection["bcut"]`. Established that the private local NanoAOD is
  run with `--files` and the dataset key `TT1L2Q` to enable gen-level branches.
- **01-21:** For the standard test file, use `--year 2022` (not `2022EE`).
  Noticed selection efficiency was low (~7%), prompting the debugging below.

### 2026-01 to 2026-02 — Skimmer rewrite and weights

- **01-20 (`1f01963`):** Added generator-level information to the Vcb flow.
- **01-25 (`7644a0d`):** Began a careful rewrite of `vcbSkimmer.py`; kept
  `vcbSkimmer_old.py` temporarily for comparison.
- **01-26 (`a977d18`, `9bc367b`, `f23121c`):** Added dedicated
  `GenSelection.py`; marked the rewritten `vcbSkimmer.py` as the working version;
  enforced chunk-size handling in `run.py`.
- **02-09 (`8269cc3`):** Large `run.py` update plus a `vcbSkimmer.py` adjustment.
  Flagged a suspected **weight normalization off by ~1000×** to investigate.
- **02-27:** Adopted **`finalWeight`** as the per-event MC weight. It normalizes
  by `np_nominal` under the assumption that the input represents the entire
  dataset, so a 10%-of-dataset input yields ~10× per-event weights (correct once
  re-normalized to the full dataset).

### 2026-02-27 — Processors package cleanup (from AI_LOG)

- Deleted the dead `vcbSkimmer_old.py`; exported `vcbSkimmer` from
  `src/processors/__init__.py`.
- Removed orphan `skim_vars["HLT"]`/`["TriggerObject"]` entries and dead
  commented-out b-jet code; fixed a `print(print(...))` double-print bug in both
  `vcbSkimmer.py` and `ttSkimmer.py`.
- Renamed `ak4_jet_lepton_selection` → `ak4_bjet_lepton_selection` to match
  `ttSkimmer`. Cutflow after cleanup: `all → met_filters → ak4_jetveto → 1lep`.

### 2026-02-27 — Validation test runs (from AI_LOG)

- **Smoke** (`batch_000.root`, ~1/1250 of the sample): 2 chunks, ~218k events,
  ~38 s, ~40% efficiency after the 1-lepton cut.
- **10% run** (`all_merged_000_024.root`): 56 chunks, ~5.6M events, ~16 min;
  weighted cutflow `2.89B → 2.89B → 2.70B → 1.16B`; `np_nominal = 2.76B`.

### 2026-03 — `lep-overlap` branch

The `lep-overlap` branch changed jet–lepton overlap removal. Previously
`good_ak4jets` removed any jet within ΔR < 0.4 of **any** electron > 5 GeV or
muon > 7 GeV, which discarded ~22% of jets and the b-jet from the leptonic-side
top in most semileptonic events (see [`docs/processor.md`](processor.md) for the
quantitative study). The branch replaced this with cleaning against **only the
prompt, trigger-matched analysis lepton**, and added an explicit single-lepton
trigger requirement.

- **03-04 (`402cac9`):** Branch-local cleanup (`initial commit`); removed
  `vcbSkimmer_old.py` and old branch baggage.
- **03-04 (`0b66516`):** Implemented the branch goal — overlap removal uses only
  trigger-matched prompt leptons (`prompt_electrons`, `prompt_muons` passed to
  `good_ak4jets`), and events must pass `HLT_IsoMu24 | HLT_Ele32_WPTight_Gsf`.
  This does **not** affect `finalWeight` normalization, since `np_nominal` is
  computed over all input events before selection cuts.
- **03-04:** Designated primary-analysis output for this branch:
  `nano_skim_all_merged_000_024_lep-overlap_uptodate_20260304_lz4.root`
  (~10% of input; effective ~10× per-event weight).
- **03-12 (`5dfef5b`):** Added integration-test assets `tests/test_run.py`,
  `tests/outfile/test-output-0th-event.txt`, `test-output-schema.csv`.
- **03-12 (`a763acb`, current HEAD):** Expanded `README.md` to document the
  skimmer, output branches, and test procedure.

### 2026-04 — Condor production and `--outdir` plumbing (uncommitted)

The following are in the working tree but **not yet committed**:

- **04-06/04-07:** New repo-root `condor/` workflow (separate from legacy
  `src/condor/`): one job per `batch_*` dir, `--no-write-final-weight` during the
  skim, then `condor/scripts/fix_final_weight.py` to recompute `finalWeight` from
  the global `np_nominal`, and `merge_processed.py` to produce
  `processed-nano/<tag>/merged/total.root`. See [`condor/README.md`](../condor/README.md).
- **04-06/04-07:** `run.py` gained `--outdir`, timestamped `outputs/YYYYMMDD_HHMM/`
  outputs, and an `outputs/latest` symlink. The `boostedhh` submodule was modified
  to thread `outdir` through `run_utils.run()` and `SkimmerABC.dump_table()`
  (via `BOOSTEDHH_OUTPARQUET_DIR`) — note this conflicts with `AGENTS.md`'s
  "do not modify the submodule" rule and needs a deliberate decision.
- **04-08/04-10:** `good_ak4jets` made `muon_pt`/`electron_pt` optional when
  explicit cleaning collections are passed; `vcbSkimmer.py` removed the old
  hard-coded lepton-pT cleaning config.

#### 2026-04-07 — Full Condor run over `batch_000`–`batch_249` (from AI_LOG)

- Fixed early failures: workers needed `outputs/` created under their `cwd`; and
  parallel `micromamba` jobs raced on the shared cache lock, fixed with per-job
  `XDG_CACHE_HOME` / `CONDA_PKGS_DIRS` / `MAMBA_PKGS_DIRS`.
- `fix_final_weight.py`: `Computed global np_nominal = 29747137451.0 from 250
  pickle files; updated 250 ROOT files`.
- `merge_processed.py` requires a live CMSSW runtime so `hadd` finds
  `libtbb.so.12`. Final: `Merged 250 ROOT files into .../merged/total.root`.
- **Validation of `merged/total.root`:** 18,408,611 entries;
  `sum(finalWeight) = 1,002,344.14`; mean `0.0544`; min/max `∓1.466`.
- **10% vs full cross-check:** the 10% file has ~9.46× fewer entries but
  `sum(finalWeight)` agrees (999,080 vs 1,002,344); per-event weights are ~10×
  larger in the 10% file because it is self-normalized. Confirms the split-Condor
  `finalWeight` matches a single manual run.

### 2026-04-30 to 2026-05-27 — Gen-truth expansion (uncommitted)

Working-tree changes extending generator-truth bookkeeping beyond the March HEAD:

- New explicit branches: `GenHadW*`/`GenLepW*`, `GenHadTopB*`/`GenLepTopB*`,
  `GenHadTopIdx`/`GenLepTopIdx`, `GenHadTopDecayW*`/`GenLepTopDecayW*`.
- Six exclusive hadronic-W flavor tags: `GenWtoUD/US/CD/CS/UB/BC`.
- Quark masses supplemented from PDG values where NanoAOD stores zero.
- Retired old top-slot aliases `GenTopW0/1*`, `GenTopDecayW0/1*`, `GenTopB0/1*`.
- New tests/diagnostics: `tests/test_vcb_gen_truth.py`, `plot_gen*.py`,
  `dump_matching_input_event.py`, regenerated `tests/outfile/` fixtures.

### 2026-05-08 — Working-tree snapshot (from STATE)

Branch `lep-overlap` at `a763acb`; working tree dirty. Latest committed change
`2026-03-12`; latest local file edits `2026-05-27`. The committed state is a
working, documented skimmer; the newest operational (Condor, `--outdir`) and
truth-level improvements sit uncommitted in the working tree.
