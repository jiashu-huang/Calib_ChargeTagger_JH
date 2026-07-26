# Processor Walkthrough: `vcbSkimmer`

How `src/vcb/processors/vcbSkimmer.py` turns a NanoAOD file into a skimmed output,
step by step. For the output-branch dictionary see the top-level
[`README.md`](../README.md); for run history see [`docs/history.md`](history.md).

> **Note on provenance.** This document supersedes the archived
> `Vcb_OVERVIEW.md` (kept verbatim in [`docs/archive/`](archive/)). The archived
> version described the pre-`lep-overlap` behavior — cleaning jets against *all*
> soft leptons and applying *no* trigger requirement. Both were changed on the
> `lep-overlap` branch; the current behavior is documented below, and the old
> behavior is preserved only in the clearly-labeled
> [historical b-jet-loss study](#historical-study-why-lepton-cleaning-was-changed).

The processor targets **pp → tt̄, (t → bW, W → cb̄), (t̄ → b̄W, W → ℓν)**.

---

## 1. Entry point: `run.py`

| Step | What happens |
|------|--------------|
| Parse CLI | `--skimmer vcbSkimmer` (default) is resolved to the processor class. |
| Build fileset | `{"{year}_{files_name}": [file_path]}`, e.g. `{"2022_TT1L2Q": [...]}`. |
| Run | `run_utils.run()` calls `vcbSkimmer.process()` per chunk (iterative executor locally). |
| Post-process | none in the skim: `finalWeight` is appended later, in place, by `condor/scripts/normalize.py` (its denominator sums over the whole sample). |

Year and dataset name are recovered inside `process()` from
`events.metadata["dataset"].split("_")` — so `--year` drives the JEC, jet-veto,
pileup, and cross-section lookups.

---

## 2. Object selection

### Electrons — `objects.good_electrons`

| Cut | Threshold |
|-----|-----------|
| MVA Iso WP90 | `mvaIso_WP90 == True` |
| pT | > 20 GeV |
| \|η\| | < 2.5 |
| \|dz\| | < 0.2 cm |
| \|dxy\| | < 0.045 cm |

Trigger matching against EGamma triggers (filter bit 1, lepton pT > 31 GeV).

### Muons — `objects.good_muons`

| Cut | Threshold |
|-----|-----------|
| Tight ID | `tightId == True` |
| PF rel. iso (ΔR 0.4) | `pfRelIso04_all < 0.15` |
| pT | > 20 GeV |
| \|η\| | < 2.4 |
| \|dz\| | < 0.2 cm |
| \|dxy\| | < 0.045 cm |

Trigger matching against single-muon triggers (filter bit 3, lepton pT > 26 GeV).

### The prompt "trigger lepton" (current behavior)

The `lep-overlap` branch introduced a single, per-event **trigger lepton** that
is the only object used for AK4 jet cleaning. It is chosen as follows
(`vcbSkimmer.py` ~L281–347):

1. Build `prompt_electrons` / `prompt_muons` = good leptons that are
   trigger-matched (`ElectronTrigMatchEGamma`, `MuonTrigMatchMuon`).
2. If only `HLT_IsoMu24` fired → use the leading prompt muon passing the IsoMu24
   activation threshold (`HLT_ISOMU24_LEPTON_PT = 26 GeV`).
3. If only the single-electron HLT fired → use the leading prompt electron
   passing the electron activation threshold (`HLT_ELE32_LEPTON_PT = 35 GeV`).
4. If **both** fired → prefer a trigger-ready muon; otherwise fall back to the
   leading selected electron.

> ⚠️ Steps 3–4 hard-code `HLT_Ele32_WPTight_Gsf` / 35 GeV, which is **2022-only**.
> Run3 2023/2024 use `HLT_Ele30_WPTight_Gsf`. See the pending-work note in
> [`docs/history.md`](history.md#-known-discrepancies--pending-2024-work) before
> running on the 2024 samples.

### AK4 jets — `objects.good_ak4jets`

JECs are applied first (`JEC_loader.get_jec_jets`), then:

| Cut | Threshold |
|-----|-----------|
| pT | > 15 GeV |
| \|η\| | < 4.7 |
| ΔR from the **prompt trigger lepton only** | > 0.4 |

This is the key change from the archived overview: overlap removal is done
against the single prompt, trigger-matched analysis lepton passed as
`cleaning_electrons` / `cleaning_muons`, **not** against every soft electron
> 5 GeV or muon > 7 GeV.

### MET

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

Registered in this order (`vcbSkimmer.py` ~L561–585):

| # | Cut | Condition |
|---|-----|-----------|
| 1 | `single_lep_trigger` | `HLT_IsoMu24 \| HLT_Ele32_WPTight_Gsf` fired |
| 2 | `met_filters` | all configured `Flag.*` branches present in the input pass |
| 3 | `ak4_jetveto` | no good jet falls in the Run-3 jet-veto map |
| 4 | `1lep` | `nMuons + nElectrons ≥ 1` |
| 5 | `prescale` *(optional)* | only if `--prescale-factor` is set |

The final mask is `selection.all(*names)`; only events passing all registered
cuts are written. **No b-jet multiplicity cut** is applied (unlike `ttSkimmer`) —
b-tag requirements are deferred to analysis time.

---

## 5. Weights

For MC: `genWeight × pileup SF × ISR/FSR PS weights × (σ × L)` normalization
(`add_weights`). `np_nominal` = Σ of the no-σL partial weight over **every
event read, before any cut** — the denominator of the finalWeight ratio
estimator. It is stored in the totals pickle and in a single-entry `Norm` tree
inside the skim ROOT. The skimmer never writes `finalWeight`; it is appended
globally afterward by
[`condor/scripts/normalize.py`](../condor/scripts/normalize.py) — see
[`condor/README.md`](../condor/README.md).

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
real signal b-jets. The fix (current behavior) is to clean only against the
prompt, trigger-matched analysis lepton, and to require the single-lepton
trigger explicitly. The full set of diagnostic plots referenced by the original
study lived under the git-ignored `diagnostics/` directory.
