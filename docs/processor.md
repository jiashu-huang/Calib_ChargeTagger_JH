# Processor walkthrough: `vcbSkimmer`

How [`src/vcb/processors/vcbSkimmer.py`](../src/vcb/processors/vcbSkimmer.py)
turns a NanoAOD file into a skimmed output, step by step. For how to *run* it
see the top-level [`README.md`](../README.md); for every CLI flag see
[`cli.md`](cli.md); for the complete output-branch list see the committed
schema baseline
[`tests/outfile/test-output-schema.csv`](../tests/outfile/test-output-schema.csv).

> **Note on provenance.** This document supersedes the archived
> `Vcb_OVERVIEW.md` (kept in the old repo's `docs/archive/`). The archived
> version described the pre-`lep-overlap` behavior — cleaning jets against
> *all* soft leptons and applying *no* trigger requirement. The current
> behavior is documented below; the old behavior is preserved only in the
> clearly-labeled
> [historical b-jet-loss study](#historical-study-why-lepton-cleaning-was-changed).

The processor targets **pp → tt̄, (t → bW, W → cb̄), (t̄ → b̄W, W → ℓν)**.

---

## 1. Entry point: `run.py`

| Step | What happens |
|------|--------------|
| Parse CLI | `--skimmer vcbSkimmer` (default) is resolved to the processor class. Full flag reference: [`cli.md`](cli.md). |
| Build fileset | `{"{year}_{files_name}": [file_path]}`, e.g. `{"2024_TTtoLNuCB": [...]}`. |
| Run | `run_utils.run()` calls `vcbSkimmer.process()` per chunk (iterative executor locally). |
| Post-process | none in the skim: `finalWeight` is appended later, in place, by [`condor/scripts/normalize.py`](../condor/scripts/normalize.py) (its denominator sums over the whole sample — see [`normalization.md`](normalization.md)). |

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

Trigger matching against EGamma trigger objects: filter bit 1 (the generic
single-electron WPTight bit, valid for both Ele32 and Ele30), ΔR < 0.2, and a
year-dependent offline pT cut above the HLT turn-on — 35 GeV for 2022/2023
(`HLT_Ele32_WPTight_Gsf`), 32 GeV for 2024 (`HLT_Ele30_WPTight_Gsf`).

### Muons — `objects.good_muons`

| Cut | Threshold |
|-----|-----------|
| Tight ID | `tightId == True` |
| PF rel. iso (ΔR 0.4) | `pfRelIso04_all < 0.15` |
| pT | > 20 GeV |
| \|η\| | < 2.4 |
| \|dz\| | < 0.2 cm |
| \|dxy\| | < 0.045 cm |

Trigger matching against single-muon trigger objects: filter bit 3, ΔR < 0.2,
offline pT > 26 GeV (`HLT_IsoMu24`, all years).

### The per-event trigger lepton

Relevant files:

- leptons in [`src/vcb/processors/objects.py`](../src/vcb/processors/objects.py),
- HLT paths in [`src/vcb/HLTs.py`](../src/vcb/HLTs.py),
- the per-event choice in
  [`src/vcb/processors/vcbSkimmer.py`](../src/vcb/processors/vcbSkimmer.py),
  in the main processing method.

Each retained event is assigned **one** leading trigger lepton. The lepton must
pass the offline selection above, be matched to the trigger object for the HLT
path that fired, and lie above that path's activation threshold.

For 2024, `HLT_Ele30_WPTight_Gsf` selects an electron with pT ≥ 32 GeV and
|η| < 2.5, while `HLT_IsoMu24` selects a muon with pT ≥ 26 GeV and |η| < 2.4.
(For 2022/2023 the electron path is `HLT_Ele32_WPTight_Gsf` with pT ≥ 35 GeV.)
If both single-lepton paths fire, a trigger-ready muon is preferred; otherwise
use a trigger-ready electron; otherwise discard the event.

This single per-event lepton is used for the trigger-lepton output branches and
for AK4 jet cleaning (next).

### AK4 jets — `objects.good_ak4jets`

JECs are applied first ([section 3](#3-jet-energy-corrections-jec--jer)), then:

| Cut | Threshold |
|-----|-----------|
| pT (corrected) | > 15 GeV |
| \|η\| | < 4.7 |
| ΔR from the **trigger lepton only** | > 0.4 |

Jet cleaning uses *only* the selected per-event trigger lepton, not every
reconstructed lepton — the key change from the archived overview, motivated by
the [historical study](#historical-study-why-lepton-cleaning-was-changed)
below. `vcbSkimmer` passes that one lepton as the cleaning electron or muon
collection; `good_ak4jets` retains jets only when their ΔR from every supplied
cleaning lepton is greater than 0.4.

### MET

`events.PFMET` for MC (a JEC-corrected MET factory is used for data when
available).

---

## 3. Jet energy corrections (JEC + JER)

Relevant files:

- [`src/vcb/processors/vcbSkimmer.py`](../src/vcb/processors/vcbSkimmer.py)
  creates `JECs(year)` and applies it to AK4 jets before jet selection.
- [`src/boostedhh/processors/corrections.py`](../src/boostedhh/processors/corrections.py)
  implements `JECs` and its `get_jec_jets` correction path.
- [`src/boostedhh/corrections/`](../src/boostedhh/corrections/) contains the
  bundled inputs: `jec_compiled_py311.pkl.gz` for 2022–2023 and
  `2024_jet_jerc.json.gz` plus `jer_smear.json.gz` for 2024. Versions and
  provenance:
  [the corrections' README](../src/boostedhh/corrections/README.md).

For every jet, the code first derives raw pT and mass from NanoAOD `rawFactor`
and attaches event rho (and, for MC, matched-generator-jet information).
For 2024 MC AK4 jets, correctionlib evaluates the Summer24 V5 `L1L2L3Res`
compound correction on raw pT/mass, then applies nominal JRV2 hybrid JER
smearing. The resulting factors update `pt`, `mass`, and `rawFactor` before jet
cleaning and selection. The current 2024 data and AK8 paths retain NanoAOD
energies, and JES/JER variations are not written by the skimmer.

---

## 4. Jet-veto map

Relevant files (line numbers as of the current commit):

- [`src/vcb/processors/vcbSkimmer.py`](../src/vcb/processors/vcbSkimmer.py)
  applies the resulting event selection as the `ak4_jetveto` cut.
- [`src/vcb/processors/objects.py`](../src/vcb/processors/objects.py#L84-L89)
  (lines 84–89) defines which jets reach the veto: `pt > 15`, `|eta| < 4.7`,
  and ΔR > 0.4 from the selected trigger-lepton candidates.
- [`src/boostedhh/processors/corrections.py`](../src/boostedhh/processors/corrections.py#L573-L599)
  (lines 573–599) implements `get_jetveto_event`; the year → correction-name
  map is at [lines 588–594](../src/boostedhh/processors/corrections.py#L588-L594),
  and the CVMFS path is built by `get_pog_json`
  ([lines 60–75](../src/boostedhh/processors/corrections.py#L60-L75)).
- The map payload is the campaign-specific correctionlib
  `jetvetomaps.json.gz` read from the CMS JSON POG CVMFS tree
  (`/cvmfs/cms.cern.ch/rsync/cms-nanoAOD/jsonpog-integration/POG/JME/`). It is
  **not bundled** in this repository, so CVMFS must be reachable from wherever
  the skimmer runs (including condor workers).

After JEC and AK4 jet selection, the skimmer evaluates the year-specific Run-3
jet-veto map at every jet's eta and phi. A nonzero map value marks a vetoed
detector region. The event fails `ak4_jetveto` if any selected jet with
pT > 15 GeV lies in such a region; otherwise it passes. This selection is
applied to both data and MC. Eta and phi are clipped to the map range before
evaluation.

For 2024 the resolved payload is `POG/JME/2024_Summer24/jetvetomaps.json.gz`,
correction `Summer24Prompt24_RunBCDEFGHI_V1`, map type `jetvetomap` — the
campaign matching the `Summer24MiniAODv6` MC and the `Summer24Prompt24_V5` JEC
above.

Two caveats on the implementation:

- The pT > 15 GeV requirement inside `get_jetveto_event` is redundant — the
  same threshold is already applied in `good_ak4jets`.
- The jets tested are the lepton-cleaned ones, and no jet ID / EM-fraction cut
  is applied, so this is close to but not literally the JERC prescription
  (pT > 15, tight jet ID, neutral EM fraction < 0.9, no ΔR < 0.2 PF-muon
  overlap).

---

## 5. Generator-level info — `GenSelection.gen_selection_Vcb`

Runs only when the dataset name is a key in `gen_selection_dict` (`TT1L2Q`,
`TTtoLNu2Q`, `TTtoLNuCB`). It **saves** gen-truth branches but registers
**no** event-level cuts. It finds the hard-process tops, splits the
hadronic/leptonic branches, saves W/b/quark kinematics and the six exclusive
`GenWto*` flavor tags, and computes ΔR reco↔gen matching (jets↔b/quarks at
ΔR < 0.4, leptons↔gen-lepton at ΔR < 0.2). The full branch list is in
[`tests/outfile/test-output-schema.csv`](../tests/outfile/test-output-schema.csv);
unit tests for the helpers are in
[`tests/test_vcb_gen_truth.py`](../tests/test_vcb_gen_truth.py).

---

## 6. Event-level selection (cutflow)

Registered in this order in `vcbSkimmer.py`:

| # | Cut | Condition |
|---|-----|-----------|
| 1 | `single_lep_trigger` | `HLT_IsoMu24` \| the year's single-electron path (Ele32 for 2022/2023, Ele30 for 2024) fired |
| 2 | `met_filters` | all configured `Flag.*` branches present in the input pass |
| 3 | `ak4_jetveto` | no good jet falls in the Run-3 jet-veto map |
| 4 | `1lep` | `nMuons + nElectrons ≥ 1` |
| 5 | `prescale` *(optional)* | only if `--prescale-factor` is set |

The final mask is `selection.all(*names)`; only events passing all registered
cuts are written. **No b-jet multiplicity cut** is applied (unlike `ttSkimmer`)
— b-tag requirements are deferred to analysis time.

---

## 7. Weights

For MC: `genWeight × pileup SF × ISR/FSR PS weights × (σ × L)` normalization
(`add_weights`). `np_nominal` = Σ of the no-σL partial weight over **every
event read, before any cut** — the denominator of the `finalWeight` ratio
estimator. It is stored in the totals pickle and in a single-entry `Norm` tree
inside the skim ROOT. The skimmer never writes `finalWeight`; it is appended
globally afterward by
[`condor/scripts/normalize.py`](../condor/scripts/normalize.py) — see
[`condor/README.md`](../condor/README.md) for the workflow and
[`normalization.md`](normalization.md) for the design record.

### Pile-up

Relevant files (line numbers as of the current commit):

- [`src/boostedhh/corrections/2024_puWeights.json.gz`](../src/boostedhh/corrections/2024_puWeights.json.gz)
  is **the source of the pile-up information** — a bundled correctionlib
  payload holding one correction, `Collisions24_CDEFGHI_goldenJSON`, with
  inputs `(NumTrueInteractions: real, weights: string ∈ {nominal, up, down})`
  → `weight`.
- [`src/boostedhh/processors/corrections.py`](../src/boostedhh/processors/corrections.py#L101)
  (line 101) implements `add_pileup_weight`; the bundled-first / CAT-cvmfs
  lookup it uses is at
  [lines 76–98](../src/boostedhh/processors/corrections.py#L76-L98).
- [`src/vcb/processors/vcbSkimmer.py`](../src/vcb/processors/vcbSkimmer.py#L676)
  calls `add_pileup_weight` inside `add_weights` (line 676) and copies the raw
  pile-up counters into the skim (`skim_vars["Pileup"]` at lines 166–168,
  filled at lines 531–534).
- [`src/boostedhh/hh_vars.py`](../src/boostedhh/hh_vars.py#L41) (line 41)
  lists `"pileup"` in `norm_preserving_weights`, which is what keeps it
  shape-only.
- Provenance of the bundled file — era choice, snapshot pin, md5 — is in
  [the corrections' README](../src/boostedhh/corrections/README.md).

The payload is **not** taken from the `jsonpog-integration` tree used for the
jet-veto map: that tree's LUM entries stop at `2023_Summer23BPix`. It comes
from the CAT metadata tree,
`/cvmfs/cms-griddata.cern.ch/cat/metadata/LUM/Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15/latest/puWeights_CDEFGHI.json.gz`
— the LUM sibling of the same campaign as the 2024 JEC/JER file — pinned to
the `2026-04-15` snapshot and committed to the repo so condor workers need no
network access. Era set `CDEFGHI` matches the campaign name (C–E reReco + F–I
prompt, no commissioning era B). Every year resolves the same way: bundled
`corrections/<year>_puWeights.json.gz` first, else the CAT campaign directory
on cvmfs. `add_pileup_weight` reads the *first* correction key in the file, so
swapping in `puWeights_BCDEFGHI.json.gz` needs no code change.

Pile-up enters the output in two independent ways.

* **As per-event counters.** For MC the skimmer copies NanoAOD `Pileup_nPU`
  and `Pileup_nTrueInt` into the branches `nPU` and `nTrueInt`, and `PV_npvs`
  into `nPV`, for every retained event; for data both pile-up branches are
  filled with `PAD_VAL` (−99999) and only `nPV` is real. Nothing selects on
  them, so downstream code can re-derive or validate the reweighting — and
  because `nTrueInt` is stored, a future weight-file update is a
  post-processing rescale rather than a re-skim.
* **As an event weight.** `add_weights` evaluates the correction on `nTrueInt`
  (clipped to `[0, 99]`) for `nominal`, `up`, and `down`, clips each returned
  weight to `[0, 10]`, and adds all three to the coffea `Weights` container as
  `"pileup"`. It is then folded multiplicatively into `weight` (together with
  `genweight`, the ISR/FSR PS weights, and the σ×L normalization) and into
  `weight_noxsec`, and is written out on its own as `single_weight_pileup`.
  Because `"pileup"` is in `norm_preserving_weights`, it is also part of the
  partial weight summed into `totals["np_nominal"]`; since
  `finalWeight = weight / np_nominal` divides by that same sum, pile-up
  reweighting reshapes pile-up-dependent distributions without moving the
  overall normalization. The `up`/`down` variations live in the `Weights`
  object but are only written (as `weight_pileupUp`/`Down` plus
  `np_pileupUp`/`Down` totals) when the skimmer runs with
  `--save-systematics`, which is off by default — hence the committed baseline
  schema carries `single_weight_pileup` but no pile-up variation branches.

The correction is a function of `NumTrueInteractions` = `Pileup_nTrueInt`, the
*mean* μ of the Poisson each bunch crossing was sampled from — **not**
`Pileup_nPU`, the integer actually drawn from it. Upstream `boostedhh` passed
`nPU`; we pass `nTrueInt`. On the test fixture the two share a mean (45.4) but
`nPU` is broader (σ = 11.7 vs 9.5) and tracks `nTrueInt` at a correlation of
only 0.82, so the old call mis-weighted 51% of events by >25% and cost
effective statistics (N_eff/N = 0.44 → 0.74). It never errored — the payload
is 100 unit-wide bins with `flow: clamp`, so an integer input still landed in
a valid bin. Yields were unaffected either way, pile-up being norm-preserving.

One caveat on the implementation: `single_weight_pileup` is not the bare
pile-up weight. The σ×L normalization loop multiplies *every* entry of
`weights_dict`, including the `single_weight_*` diagnostics. Divide by
`weight_norm` to recover the actual scale factor.

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
study lived under the git-ignored `diagnostics/` directory of the old repo.
