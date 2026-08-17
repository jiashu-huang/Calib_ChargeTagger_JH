# Project History

> **Provenance of `Calib_ChargeTagger_JH` (this repo).** Created 2026-07-14 as
> a standalone port of the Vcb pipeline from the old
> `Vcb/Calib_ChargeTagger` repo at commit `a763acb` **plus its uncommitted
> 2026-07-14 working tree** (which already carried the 2024 trigger wiring).
> The `boostedhh` submodule was vendored into `src/boostedhh/` from its
> patched working tree at upstream commit `71bd456` + the outdir patch
> (archived at [`archive/boostedhh-outdir.patch`](archive/boostedhh-outdir.patch);
> details in [`../src/boostedhh/VENDORED.md`](../src/boostedhh/VENDORED.md)).
> `bbtautau` was renamed to `vcb`; only the Vcb skimmer path was ported.
> The old repo is untouched and remains the reference for pre-2026-07 history.

Consolidated, chronological history of `Calib_ChargeTagger` (JH fork). This
distills the four original logs — `LOG.md`, `BRANCH_LOG.md`, `AI_LOG.md`, and
`STATE.md` — which are preserved verbatim in the **old repo** under
`docs/archive/` (not carried over here; only the boostedhh outdir patch is).

- **Purpose & how to run:** see the top-level [`README.md`](../README.md).
- **How the processor works internally:** see [`docs/processor.md`](processor.md).
- **Condor batch production:** see [`condor/README.md`](../condor/README.md).

> This fork descends from Clara Ramon Alvarez's
> [`cramonal/Calib_ChargeTagger`](https://github.com/cramonal/Calib_ChargeTagger),
> re-purposed for the Vcb charge-tagger calibration study of semileptonic
> `ttbar`: **pp → tt̄, (t → bW, W → cb̄), (t̄ → b̄W, W → ℓν)**.

---

## Known discrepancies found at port time (all since resolved)

As of **2026-07-14**, the committed and working-tree code targeted **2022** MC.
A pre-run review found the following gaps. **All three have since been fixed**
— the electron trigger is year-dependent (Ele30 for 2024), `--year 2024` is
fully wired (JEC/JER, jet-veto, pile-up, lumi), and the integration test runs
on a 2024 fixture. The list is kept as a record of what the port was missing:

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

### 2026-08-09 — `1lep` tightened to require a trigger lepton

The event selection asked for `nMuons + nElectrons ≥ 1`, but the lepton scale
factors, the `TriggerLepton*` branches and the AK4 jet ΔR cleaning all key off
the **trigger** lepton — trigger-matched and above the path's offline plateau
cut. The two are not the same requirement, so **3.5 %** of written events
(2 144 / 61 774 on `tests/data/test-input.root`) had `TriggerLeptonFlav =
PAD_VAL`: no lepton kinematics, a silent 1.0 lepton SF, and jets never cleaned
against the lepton. `docs/processor.md` §2 already claimed such events were
discarded; the cutflow never enforced it.

Fixed by adding a `trigger_lepton` cut (`use_trigger_electron |
use_trigger_muon`) after `1lep`, which is kept purely so the cutflow shows what
the tightening costs. 96.8 % of the removed events had their only good lepton
*below* the plateau cut — on the trigger turn-on, where the tag-and-probe
trigger SF is not the measured quantity — 2.2 % had no good lepton of the fired
flavour, and 1.0 % had an unmatched lepton above threshold.
`tests/test_run.py` now fails if any written event lacks a trigger lepton.

**Productions skimmed before this date** (`prod_20260726`,
`prod_lnu2q_20260728`) still contain the 3.5 %; cut them at analysis time with
`TriggerLeptonFlav > 0` or re-skim. Cutflow denominators are unaffected —
`np_nominal` is evaluated before any `add_selection` call.

### 2026-08-09 — Trigger-lepton choice made symmetric

Follow-up to the above, in the same block of `vcbSkimmer.process`. When **both**
single-lepton paths fired and no trigger-matched muon existed, the code fell
back to the leading *good* electron above 32 GeV — **not** required to be
trigger-matched — while the electron-only branch did require a match. So the
same event was judged by a different standard depending on whether `IsoMu24`
happened to also fire, and an unmatched electron could collect an
`electron_trigger` SF measured on matched ones.

The fallback now uses the trigger-matched collection like every other branch,
which collapses the four masks to two:

```python
use_trigger_muon     = hlt_single_mu  & trigger_muon_ready
use_trigger_electron = hlt_single_ele & trigger_electron_ready & ~use_trigger_muon
```

algebraically identical to the old expressions with the fallback tightened
(`use_trigger_muon`'s `both_single_lep_triggers` term was already dead:
`((mu & ~ele) | (both & ready)) & ready` reduces to `mu & ready`). Dropped with
it: `leading_electrons`, `fallback_trigger_electron_ready`,
`both_single_lep_triggers`, and the `ak.concatenate` that stitched the two
electron branches together.

**No event changed on the fixture** — both fired in only 95 / 59 630 events
(0.2 %), 43 of which took the fallback, and in all 43 the chosen electron was
trigger-matched anyway. This closed a latent inconsistency, not an observed
bias, so pre-existing skims need no reprocessing on this account.

### 2026-08-13 — Saved jets sorted by pT; `ak4JetNanoIdx` provenance added

The saved AK4 jet slots were never sorted. NanoAOD writes `Jet` in descending
pT, but under the JEC of its own era; the re-derivation in `get_jec_jets`
multiplies each jet by its own factor and then applies a partly **stochastic**
JER smear, after which only **43.8 %** of the full collection (68.5 % of the
selected one) is still pT-descending. Boolean masking in `good_ak4jets`
preserves whatever order it is given, so nothing repaired it.

Two distinct consequences, measured on `tests/data/test-input.root`
(59 575 written events):

1. **Mislabelled slots.** `ak4JetPt0` was not the leading jet in **31.5 %**
   (18 762) of events. Cosmetic in the sense that nothing was lost, but wrong
   for anything that reads slot 0 as "the leading jet".
2. **The wrong jets were dropped.** `pad_val(..., clip=True)` keeps the
   *first* ten jets, not the *hardest* ten. 455 events (0.76 %) had more than
   ten selected jets, and in **217 of them (47.7 %)** the kept set differed from
   the ten hardest: **234 jets** with mean pT 21.4 GeV (max **54.3 GeV**) were
   discarded in favour of jets averaging 18.1 GeV. This one loses information
   irreversibly, and the χ² jet–parton assignment needs exactly those hard jets.

Fixed with one `ak.argsort(jets.pt, ascending=False)` in `vcbSkimmer.process`,
placed between `attach_jet_charge` (which needs the input ordering intact, for
the positional `JetQk` match) and the `GenSelection` call (which pads its own
`ak4Matched*_` truth flags off the same array — sorting after it would desync
slot *k*'s kinematics from slot *k*'s gen match, silently). See
[`docs/processor.md` §2](processor.md#slot-ordering-and-provenance).

Added alongside it: **`ak4JetNanoIdx`**, each saved jet's index in the input
NanoAOD `Jet` collection, captured right after `get_jec_jets` — before anything
can permute or drop it. Once the sort permutes the slots this is the only column
that points back at the input file. It doubles as the `JetQk` index (same
positional-prefix argument as `attach_jet_charge`), and
`set(range(nJets)) − set(saved indices)` recovers precisely which jets the
ten-slot truncation dropped, which is otherwise unrecoverable from the output.
Ten `Long64_t` columns; negligible on disk under dictionary encoding.

`diagnostics/check_jet_tagger_roundtrip.py` was updated to match: it now
requires the saved slots to be pT-descending, classifies `truncated_beyond_slots`
by corrected pT rather than by input position (the old rule assumed input
ordering), and cross-checks `ak4JetNanoIdx` against its own independent η/φ
match. On the fixture: 319 077 filled slots, **0** index disagreements, **0**
out-of-order events, 5 424 309 tagger comparisons identical, 0 unexplained
dropped jets. Output files predating the column skip that one check rather than
failing.

**Productions skimmed before this date** (`prod_20260726`, `prod_lnu2q_20260728`)
carry both problems. Point (1) is repairable at analysis time — re-sort the ten
slots per event — but point (2) is not: the dropped jets are simply not in those
files, and without `ak4JetNanoIdx` there is no record of which they were. It
affects ~0.4 % of events, so whether that warrants a re-skim depends on how much
the jet-assignment step leans on the tail.

### 2026-08-13 — `Rho` and the full `GenJet` collection added to the output

Two additions aimed at what a 2024 analysis needs downstream, found by checking
the bundled JEC/JER payloads' input signatures against the saved columns.

**`Rho`** (`fixedGridRhoFastjetAll`, one float per event). The skimmer writes no
JES/JER variations, the intent being to derive them at analysis time. That works
for JES — `V5_MC_Total` and the eleven `V5_MC_Regrouped_*` sources take only
`(JetEta, JetPt)`, both already per-jet columns — and for the JER scale factor,
which takes the same pair. It did **not** work for JER as a whole, because
`JRV2_MC_PtResolution` takes `(JetEta, JetPt, Rho)` and rho was consumed inside
`get_jec_jets` and thrown away. Without it the JER systematic was not
reconstructible from the skim at any price. One float fixes that. The boundaries
of the offline route — exact per-jet above the threshold, approximate for
`nJets`, `ht`, Type-1 MET and the veto decision — are written up in
[`docs/processor.md` §3](processor.md#deriving-jesjer-variations-from-the-skim).

**`GenJet*`** — the whole truth-level AK4 collection (`Pt`/`Eta`/`Phi`/`Mass`,
`HadronFlavour`, `PartonFlavour`, `NBHadrons`, `NCHadrons`), 25 slots, MC only.
Previously the only truth-level jet information was `ak4JetMatchedGenJetPt`: one
number, and only for the jets that survived selection, so nothing in the output
could say what was actually there before the reco cuts.

25 slots is where truncation stops occurring — `GenJet` is a pT > 10 GeV
collection with a median multiplicity of 7, 20 at the 99.99th percentile and a
maximum of 23 over the 208 780 fixture events. The number is deliberately
generous rather than tuned, because surplus slots are pure padding and padding
compresses away: 15 slots cost 47.9 MiB and 30 slots 48.8 MiB on the full
fixture, under 2 % apart for twice the columns. `GenJet` is pT-descending as
written and nothing here touches it — no JEC applies to truth-level jets, which
is exactly why the reco collection needed sorting and this one does not — so a
truncated event would lose only its softest gen jets.

Side benefit: `GenJet` eta/phi is what makes the ΔR of the JER gen-match
recoverable downstream (`_add_jec_variables` computes `dr_gen` and does not save
it), so the two additions together close the JER gap rather than only most of it.

Cost: 201 new columns, output `test-output.root` 62.1 → 76.4 MiB (**+23 %**) for
59 575 events, ~244 B/event of it the gen jets. If that proves too expensive at
production scale, a pT cut on the saved gen jets is the lever — `pt > 20` would
drop the median multiplicity from 7 to 5 — but it was not applied here, since
the point of the collection is to see what the reco selection did *not* keep.

Verified by the usual round-trip run: every `GenJet` slot compared value by
value against the input NanoAOD (163 200 comparisons on a smoke chunk, 0
mismatches), `Rho` exact against `Rho_fixedGridRhoFastjetAll`, filled-slot counts
equal to `nGenJet`, and the full-fixture jet round-trip still PASS with 0
out-of-order events and 0 `NanoIdx` disagreements.

### 2026-08-14 — `ak4JetGenJetIdx`: point at the gen jets, don't copy them

Follow-up to the above. The obvious economy on the new `GenJet*` block is to
keep only the gen jets matched to a saved reco jet — 80 columns instead of 200,
and aligned to the reco slot so no lookup is needed. It was measured and
rejected.

**What it would have cost.** Matched-only keeps 61.9 % of the gen jets in the
written events and drops 38.1 %, and the dropped population is not soft junk:
22.6 % of it is above 50 GeV. Above the 20 GeV analysis threshold it drops
1.41 gen jets per event — but that headline is inflated, because a gen jet is
clustered from all visible particles and the trigger lepton therefore *is* one.
Decomposing:

| | per event | |
|---|---|---|
| the trigger lepton's own gen jet | 1.00 | expected, not a loss |
| a reco jet existed but the selection cut it | 0.12 | acceptance |
| no reco jet claimed it at all | 0.29 | reconstruction inefficiency |

So the real loss is **0.41 hard gen jets per event**, of which **0.169 are
b-flavour**. In a final state with three b jets (both tops plus the b̄ from
W → cb) that is the acceptance population, and it is exactly what cannot be
asked about once discarded — the parton-level `ak4Matched*_` flags already in
the output do not answer it, since they are keyed to reco jets that survived.

**What it would have saved.** 14.0 → 9.1 MiB, i.e. **4.9 MiB on a 76.4 MiB
file (6.4 %)**. Deleting 120 of 200 columns buys far less than 60 % of the bytes
because the deleted columns are mostly padding, which is the most compressible
thing in the file.

**What was done instead.** The full collection stays, and each reco jet gains
`ak4JetGenJetIdx` — NanoAOD's `Jet_genJetIdx`, clamped to the saved slots. That
recovers the only real attraction of matched-only (reco slot → gen jet in one
indexing operation) for **10 integer columns, ~0.8 MiB** — a sixth of what the
matched block cost, and additive rather than destructive. Same pattern as
`ak4JetNanoIdx`: store the pointer, not a copy. It also makes the JER gen-match
exact, closing the last approximation in the offline-variation route (previously
the gen jet had to be identified by pT-matching against the `GenJet*` slots).

Three sentinel values, deliberately distinct: `>= 0` is the slot index, `-1` is
NanoAOD's own "no gen jet matched this reco jet" (31 870 saved jets on the
fixture — a physics statement about pileup-like jets, so not folded into
`PAD_VAL`), and `PAD_VAL` means either an empty reco slot or a gen jet real but
past `num_gen_jets`. The clamp exists so the latter can never leak through as an
index pointing confidently at the wrong gen jet. **`nGenJets`** was added in the
same change so that case is detectable from the output alone; it does not arise
on the fixture, where the maximum gen-jet multiplicity is 23 against 25 slots.

Verified on a smoke chunk: 4 037 non-negative pointers all land in filled
`GenJet` slots, `GenJetPt[ptr] == MatchedGenJetPt` for every one of them (two
independently written columns), all 444 `-1` slots carry `MatchedGenJetPt == 0`,
and all 4 481 filled slots agree with the input `Jet_genJetIdx` read back through
`ak4JetNanoIdx`.

### 2026-08-15 — Jet–parton matching made a one-to-one assignment

`MatchedHadB` / `MatchedLepB` / `MatchedHadQ1` / `MatchedHadQ2` were four
*independent* ΔR < 0.4 booleans. That is not an assignment, and SPANet's target
format needs one: one parton per jet, one jet per parton. On the 59 575-event
fixture the old output had a jet carrying 2+ parton labels in **7.09 %** of
events (1.335 % of saved jets carried 2, 0.011 % carried 3) and a parton spread
over 2+ jets in **5.02 %** (per parton: HadB 1.45 %, LepB 1.54 %, HadQ1 1.03 %,
HadQ2 1.13 % — the 1.0–1.5 % figure is *per parton*, the 5.02 % is the union).
A complete unique four-parton → four-jet reading succeeded for only 33.89 % of
written events.

Replaced by a **greedy nearest-first assignment**: take the smallest
ΔR(parton, jet) still under 0.4, record it, retire both objects, repeat. The
whole gen match is now four integers — `GenHadBJetIdx` / `GenLepBJetIdx` /
`GenHadQ1JetIdx` / `GenHadQ2JetIdx`, each a saved jet slot in `0..9` or `-1`.

**The 40 `ak4Matched*_` booleans were dropped**, taking the output from 721
columns to 681. They shipped briefly as a derived per-slot view of the same
assignment before being removed in the same day's work: they held the same four
numbers, nothing in the repo, `spanet-test/` or `Vcb-analysis/` read them, and a
second representation of one fact only invites the two to drift. The disk saving
was *not* the reason and should not be quoted as one — parquet run-length-encodes
a column that is almost entirely `0`/`PAD_VAL` down to 0.24 MB of a 31.5 MB file,
0.76 %.

The parton order — which fixes both the tie-break and the branch naming — is now
declared once, as the `match_partons` mapping in `gen_selection_Vcb`, so
reordering it renames the outputs to match instead of silently filing LepB's jet
under `GenHadBJetIdx`.

**Reading older skims.** The names were deliberately *not* reused. A pre-2026-08-15
skim has `ak4Matched*_` and no `Gen*JetIdx`; the two are not interchangeable,
since the old flags are not a one-to-one assignment. Reusing `MatchedHadB` for an
index was considered and rejected: the old branch was consumed in boolean
context, where index `0` (matched to the leading jet, the commonest case) is
falsy and `-1` (unmatched) is truthy — it would invert exactly the two cases that
matter, silently. A new name makes stale code fail loudly.

**Greedy, not Hungarian.** The exact minimum-total-ΔR (Hungarian) assignment was
measured on the same fixture as the alternative — for a 4×10 cost matrix the
optimum is reachable by brute force over all P(10,4) = 5040 orderings, so the
comparison is exact and needed no solver. It differs from greedy in **41 of
59 575 events** and gains **+0.037 pp** of complete four-parton events (36.20 %
vs 36.16 %); per parton the gain is +0.007 to +0.034 pp, and it never matches
fewer. Greedy captures 2.271 pp of the 2.308 pp available over the old booleans
— 98 % of the win is having a one-to-one rule at all, not which rule — so the
simpler statement was taken. The "sacrifice a tight match to rescue a marginal
one" case that distinguishes them fires in 2 events; it is pinned as a test
(`test_greedy_leaves_the_documented_gap_to_the_optimal_assignment`) rather than
fixed.

**Ties.** Bit-identical ΔR between two feasible pairs occurs in 13 events
(0.02 %). `argmin` over the row-major (parton, jet) block breaks them to the
earlier parton in `MATCH_PARTON_LABELS`, then the harder jet — fixed, not
physically motivated, which is all it needs to be. The exact optimum had **zero**
genuinely degenerate solutions after post-filtering, so neither rule needed a
tie-break to be reproducible.

**Cost matrix spans the saved slots only.** Matching over the full jet
collection would let a parton claim a jet that the 10-slot truncation then
deletes — losing that label *and* blocking a jet another parton could have
taken. An earlier standalone Hungarian study that matched over all jets scored
35.59 %, ~0.6 pp below the 36.20 % the same rule reaches on the saved ten,
which is the size of that effect.

**Ceiling.** Both rules sit ~3.9 pp under the 40.08 % of events where all four
partons have *some* jet within 0.4: there two partons' only candidate is the
same jet and no one-to-one rule can split them. This is why `GenQ1` matches at
67.8 % against `GenHadTopB`'s 84.1 % — in this sample Q1 is the b from W→cb, a
third b crowding the cones. A cone/merging question, not an assignment one.

ΔR is rebuilt from padded η/φ rather than `jets.delta_r(parton)`: a parton
absent for an event makes the whole coffea entry `None`, which does not survive
`pad_val`'s `to_numpy`. Both validity masks in that computation are load-bearing
— an absent parton and an empty jet slot both sit at `PAD_VAL`, so their ΔR is
exactly 0 and would otherwise read as the tightest match in the event.

Verified on the regenerated fixture output, while the per-slot flags were still
being written alongside: zero jets carrying 2+ labels, zero partons on 2+ jets,
zero disagreements between the flags and the index branches (which is what
established the two were redundant), zero assigned pairs at ΔR ≥ 0.4 (max 0.3999)
or pointing at padding, and the complete-assignment and per-parton rates
reproducing the standalone study exactly (36.16 %, 79.04 % of partons). Re-checked
after the flags were dropped: every index is `-1` or a filled slot, no slot is
claimed twice, and the same rates hold. Eight unit tests in
[`tests/test_vcb_gen_truth.py`](../tests/test_vcb_gen_truth.py).

### 2026-08-15 — `GenQ1`/`GenQ2` pinned to down-type/up-type

`GenQ1` and `GenQ2` were the hadronic W's children `0` and `1` — positional, so
which one held the c in a W→cb event was whatever order the generator wrote them
in. The convention everyone was already relying on (Q1 down-type, Q2 up-type) was
real but unenforced.

**It was also, empirically, already true everywhere.** Checked before changing
anything: 9 746 741 TTtoLNu2Q events (`prod_lnu2q_20260728`, the d/s against u/c
modes) and 59 575 TTtoLNuCB fixture events (b against c) — Q1 down-type and Q2
up-type in **100 %** of both, covering all three down flavors and both up
flavors. So `_split_w_quarks_by_type` changed no output: the regenerated
regression baselines came back byte-identical, which is the point of recording
the check here.

Two details worth keeping:

- The ordering is by **type**, not by \|pdgId\|. The s-then-u combination occurs
  248 459 times in TTtoLNu2Q; a \|pdgId\| sort would put the u first there. So
  "sorted by pdgId" is *not* an equivalent description, and a future refactor
  reaching for `argsort` on \|pdgId\| would silently break the ub/us modes.
- It holds for both W charges and regardless of which daughter is the
  antiparticle — all eight signed (Q1, Q2) combinations appear in TTtoLNu2Q with
  Q1 always down-type.

Enforced anyway, because nothing *made* it true: it came from generator child
ordering by way of `distinctChildren`, and a different generator, NanoAOD version
or coffea release could reverse it for one decay mode with nothing raising — the
kind of break that would surface as a quietly mislabelled charge tagger training
set rather than as an error. Down-type is odd \|pdgId\| (d=1, s=3, b=5), up-type
even (u=2, c=4), which is PDG numbering rather than a convention of this
analysis. A same-type pair leaves the missing side `PAD_VAL`.

The six `GenWto*` flavor tags sort their pair internally and are swap-invariant,
so they are unaffected; `GenWb` is selected by flavor and unaffected too. For
W→cb, `GenQ1` and `GenWb` now necessarily refer to the same quark.

Documented in [`README.md`](../README.md) (gen-truth conventions, alongside the
one-to-one jet match) and [`docs/processor.md`](processor.md). Five unit tests
cover both child orderings, all six decay modes, the by-type-not-by-\|pdgId\|
distinction, and the impossible same-type pair.
