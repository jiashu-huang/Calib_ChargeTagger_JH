# Processor Walkthrough: `vcbSkimmer`

How `src/vcb/processors/vcbSkimmer.py` turns a NanoAOD file into a skimmed output,
step by step. For the output-branch dictionary see the top-level
[`README.md`](../README.md); for run history see [`docs/history.md`](history.md).

> **Note on provenance.** This document supersedes the archived
> `Vcb_OVERVIEW.md` (kept verbatim in [`docs/archive/`](archive/)). The archived
> version described the pre-`lep-overlap` behavior — cleaning jets against *all*
> soft leptons and applying *no* trigger requirement. The `lep-overlap` branch
> replaced that with a per-event "trigger lepton" used for cleaning; that layer
> has since been removed in favor of deferring the lepton selection entirely (see
> [§2.3](#23-what-the-skimmer-deliberately-does-not-do)). The old cleaning
> behavior survives only in the clearly-labeled
> [historical b-jet-loss study](#historical-study-why-lepton-cleaning-was-changed).

> **Design rule.** The skimmer records *facts* and makes only the coarsest
> acceptance decision. Every finer cut — which lepton triggered, offline
> activation thresholds, lepton multiplicity, jet–lepton overlap removal — is
> applied by a separate selection script that runs on this skim. Cuts made here
> are irreversible; cuts made downstream can be retuned without re-skimming.

The processor targets **pp → tt̄, (t → bW, W → cb̄), (t̄ → b̄W, W → ℓν)**.

---

## 1. Entry point: `run.py`

| Step | What happens |
|------|--------------|
| Parse CLI | `--skimmer vcbSkimmer` (default) is resolved to the processor class. |
| Build fileset | `{"{year}_{files_name}": [file_path]}`, e.g. `{"2022_TT1L2Q": [...]}`. |
| Run | `run_utils.run()` calls `vcbSkimmer.process()` per chunk (iterative executor locally). |
| Post-process | `finalWeight = weight / np_nominal` appended to parquet/ROOT, unless `--no-write-final-weight`. |

Year and dataset name are recovered inside `process()` from
`events.metadata["dataset"].split("_")` — so `--year` drives the JEC, jet-veto,
pileup, and cross-section lookups.

---

## 2. Object selection

### 2.1 Electrons — `objects.good_electrons`

| Cut | Threshold |
|-----|-----------|
| MVA Iso WP90 | `mvaIso_WP90 == True` |
| pT | > 20 GeV |
| \|η\| | < 2.5 |
| \|dz\| | < 0.2 cm |
| \|dxy\| | < 0.045 cm |

Saved as `ElectronTrigMatchEGamma`: the year's single-electron path fired **and**
the electron is within ΔR < 0.2 of a `TrigObj` carrying filter bit 1
(`1e WPTight`). **No pT threshold is folded in** — see
[§2.3](#23-what-the-skimmer-deliberately-does-not-do).

### 2.2 Muons — `objects.good_muons`

| Cut | Threshold |
|-----|-----------|
| Tight ID | `tightId == True` |
| PF rel. iso (ΔR 0.4) | `pfRelIso04_all < 0.15` |
| pT | > 20 GeV |
| \|η\| | < 2.4 |
| \|dz\| | < 0.2 cm |
| \|dxy\| | < 0.045 cm |

Saved as `MuonTrigMatchMuon`: `HLT_IsoMu24` fired **and** the muon is within
ΔR < 0.2 of a `TrigObj` carrying filter bit 3 (`1mu`). **No pT threshold is
folded in.**

### 2.3 What the skimmer deliberately does *not* do

There is **no per-event "trigger lepton"**. The skimmer does not pick one, does
not apply the offline activation thresholds, and does not clean jets against a
lepton. All of that is the selection script's job.

The reason is that these cuts are lossy in one direction only. A trigger-match
flag defined as *fired AND matched AND pT ≥ 32* cannot be loosened afterwards —
the sub-threshold matches are simply gone. A jet dropped for overlapping a
lepton cannot be put back. So the skimmer stores the ingredients instead:

| Saved | Branches |
|-------|----------|
| All good electrons / muons (up to 3 each) | `Electron*`, `Muon*` — pT, η, φ, mass, charge, `ElectronMvaIsoWP90`, `ElectronPfRelIso03All`, `MuonPfRelIso04All` |
| Per-lepton trigger match (no pT cut) | `ElectronTrigMatchEGamma`, `MuonTrigMatchMuon` |
| Per-event HLT decisions | `HLT_IsoMu24`, `HLT_Ele30_WPTight_Gsf`, … |
| Lepton counts | `nElectrons`, `nMuons` |
| Uncleaned jets | `ak4JetEta`, `ak4JetPhi`, … |

**Checklist for the downstream selection script.** The thresholds it should
apply live in `objects.py` as the single source of truth:

| Constant | Value | Applies to |
|----------|-------|------------|
| `HLT_ELE30_LEPTON_PT` | 32 GeV | 2024, `HLT_Ele30_WPTight_Gsf` |
| `HLT_ELE32_LEPTON_PT` | 35 GeV | 2022/2023, `HLT_Ele32_WPTight_Gsf` |
| `HLT_ISOMU24_LEPTON_PT` | 26 GeV | all years, `HLT_IsoMu24` |

Use `objects.single_ele_lepton_pt(year)` to get the right electron value. Beyond
the thresholds, the script still needs to decide:

1. **Trigger-lepton choice** when both paths fire, and what to do with events
   that fire a path but yield no matched, above-threshold lepton (~10% of
   triggered events on the 2024 fixture — mostly non-prompt muons failing the
   offline `pfRelIso04_all < 0.15`, plus genuine turn-on events at 29–32 GeV
   (e) and 24–26 GeV (µ)).
2. **Jet–lepton overlap removal** at ΔR < 0.4, recomputed from the saved η/φ.
3. **Electron η**, which the skimmer only cuts at \|η\| < 2.5 on the *track*
   η. Neither the supercluster η (`eta + deltaEtaSC`, what the HLT filters on)
   nor an EB–EE gap veto (1.444 < \|η_SC\| < 1.566, ~2.2% of trigger electrons)
   is applied here. `deltaEtaSC` is **not** currently saved — add it to
   `skim_vars["ElectronDebug"]` if the script needs it.

### 2.4 AK4 jets — `objects.good_ak4jets`

JECs are applied first (`JEC_loader.get_jec_jets`), then:

| Cut | Threshold |
|-----|-----------|
| pT | > 15 GeV |
| \|η\| | < 4.7 |

**No lepton overlap removal** — `good_ak4jets` is called with
`apply_lepton_cleaning=False`. On the 2024 fixture ~99.9% of events with a good
muon contain a jet within ΔR < 0.4 of it, so `nJets` and `ht` here include the
lepton-overlapping jets by construction. The selection script must do its own
cleaning before using either.

### 2.5 MET

`events.PFMET` for MC (JEC-corrected MET factory used for data when available).

---

## 3. Generator-level info — `GenSelection.gen_selection_Vcb`

Runs only when the dataset name is a key in `gen_selection_dict` (`TT1L2Q` or
`TTtoLNu2Q`). It **saves** gen-truth branches but registers **no** event-level
cuts. It finds the hard-process tops, splits the hadronic/leptonic branches,
saves W/b/quark kinematics and the six exclusive `GenWto*` flavor tags, and
computes ΔR reco↔gen matching (jets↔b/quarks at ΔR < 0.4, leptons↔gen-lepton at
ΔR < 0.2). See the [`README.md`](../README.md) branch dictionary for the full
list.

---

## 4. Event-level selection (current cutflow)

| # | Cut | Condition |
|---|-----|-----------|
| 1 | `single_lep_trigger` | the year's single-µ **or** single-e path fired |
| 2 | `met_filters` | all configured `Flag.*` branches present in the input pass |
| 3 | `ak4_jetveto` | no good jet falls in the Run-3 jet-veto map |
| 4 | `prescale` *(optional)* | only if `--prescale-factor` is set |

Cut 1 is the **only** lepton-level requirement, and it is a plain OR of the two
per-event HLT bits — firing both is fine and no flavor is assigned. The paths are
resolved per year from [`HLTs.py`](../src/vcb/HLTs.py), which is the single source
of truth; `vcbSkimmer` and `objects.trig_match_sel` use the same lookup, so the
path an event is selected on always matches the path its leptons are matched to:

| Year | Electron path | Muon path |
|------|---------------|-----------|
| 2022, 2022EE, 2023, 2023BPix | `HLT_Ele32_WPTight_Gsf` | `HLT_IsoMu24` |
| **2024** | **`HLT_Ele30_WPTight_Gsf`** | **`HLT_IsoMu24`** |

A missing single-lepton HLT branch **raises** rather than silently dropping that
lepton channel.

Cuts 2–3 are detector-quality cuts, not physics selection, which is why they stay
here. **There is no `1lep` cut** — lepton multiplicity is deferred with the rest
of the lepton selection. On the 2024 fixture this keeps ~7% more events than the
old skim; those are events that fired a lepton path with no good offline lepton,
which also leaves the fake / non-prompt sideband intact for downstream study.
**No b-jet multiplicity cut** is applied (unlike `ttSkimmer`) — b-tag
requirements are deferred to analysis time.

The final mask is `selection.all(*names)`; only events passing all registered
cuts are written.

---

## 5. Weights

For MC: `genWeight × pileup SF × ISR/FSR PS weights × (σ × L)` normalization
(`add_weights`). `np_nominal = Σ weight` over selected events is stored per file;
`run.py` then writes `finalWeight = weight / np_nominal`. In the Condor workflow
the per-batch skim runs with `--no-write-final-weight` and `finalWeight` is
recomputed globally afterward — see [`condor/README.md`](../condor/README.md).

---

## Historical study: why lepton cleaning was changed

> **This section documents the OLD (pre-`lep-overlap`) behavior** and the study
> that motivated changing it. The numbers below were produced with the old
> cleaning (ΔR < 0.4 against **all** electrons > 5 GeV / muons > 7 GeV) and with
> **no** trigger requirement. They do **not** describe the current processor.

On 5.6M `TTtoLplusNu2Q` events, the old event-level cutflow
(`met_filters → jet_veto → ≥1 lepton`) kept ~43%:

| Stage | Remaining | % of total |
|-------|-----------|-----------|
| Input | 5,645,931 | 100% |
| + MET filters | 5,643,311 | 99.95% |
| + Jet veto | 5,271,502 | 93.4% |
| + ≥1 lepton | 2,432,138 | 43.1% |

But the dominant *physics* distortion was at **jet** level: the old cleaning
removed **~22.4% of all jets** (8.8M), of which ~33% were b-tagged at the medium
working point. In semileptonic `ttbar` the leptonic-side b-jet
(`t → bW → b ℓν`) sits close to the lepton, so a soft/fake lepton within ΔR < 0.4
would silently delete a genuine b-jet — migrating events from "2 b-jets" to
"1 b-jet" ~67% of the time (medium WP).

**Conclusion that drove the branch:** cleaning against every soft lepton removes
real signal b-jets. The `lep-overlap` fix was to clean only against the prompt,
trigger-matched analysis lepton, and to require the single-lepton trigger
explicitly. The trigger requirement stayed; the cleaning has since moved
downstream entirely (see [§2.3](#23-what-the-skimmer-deliberately-does-not-do)),
so the conclusion now applies to the **selection script** — it must clean against
the prompt trigger lepton, not against every soft lepton. The full set of
diagnostic plots referenced by the original study lived under the git-ignored
`diagnostics/` directory.
