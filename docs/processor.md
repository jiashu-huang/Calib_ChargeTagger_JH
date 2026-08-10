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
| \|η\| | < 2.5 (track η) |
| ECAL crack veto | **not** 1.444 ≤ \|η_SC\| < 1.566 |
| \|dz\| | < 0.2 cm |
| \|dxy\| | < 0.045 cm |

Trigger matching against EGamma trigger objects: filter bit 1 (the generic
single-electron WPTight bit, valid for both Ele32 and Ele30), ΔR < 0.2, and a
year-dependent offline pT cut above the HLT turn-on — 35 GeV for 2022/2023
(`HLT_Ele32_WPTight_Gsf`), 32 GeV for 2024 (`HLT_Ele30_WPTight_Gsf`).

**The crack veto** (`objects.in_ecal_crack`) removes electrons landing in the
ECAL barrel/endcap transition, where a shower leaks into uninstrumented
material. Two things make it necessary rather than cosmetic: reconstruction is
degraded there, and **EGM does not measure the electron ID scale factor in that
region at all** — it fills the bin with exactly 1.0 and *zero* uncertainty, so a
surviving crack electron would carry an uncorrected efficiency with no
systematic attached (§7).

It is applied in **supercluster** η (`objects.electron_supercluster_eta` —
`superclusterEta` in NanoAODv15, else `eta + deltaEtaSC`), because that is where
the energy actually landed and the coordinate the crack and every EGM binning
are defined in; the outer \|η\| < 2.5 acceptance bound is left on track η. The
edges are the **SF bin edges** 1.444 / 1.566 rather than EGM's usual quoted
1.4442 / 1.5660 — a 0.0002 difference, irrelevant for acceptance, but it makes
it exact that nothing surviving can land in the unmeasured bin.
[`tests/test_objects.py`](../tests/test_objects.py) asserts that correspondence
against the bundled payload in both directions.

Cost on the test fixture: 575 of 62 158 events (0.93%) — 549 electron-channel
events plus 26 that had no other lepton. The muon channel is untouched.

### Electron energy scale and smearing — `electron_ss.py`

Applied to the **whole** `events.Electron` collection **before**
`good_electrons`, and it has to be: the correction is what decides which
electrons clear the pT > 20 baseline cut and the 32 GeV Ele30 offline
threshold. Running it afterwards would erase exactly the migration it exists to
describe. Everything downstream — selection, jet cleaning, the trigger-lepton
choice, the lepton SFs, `GenSelection` — therefore sees the corrected pT.

ECAL measures electron energy from scintillation light in PbWO₄ crystals, and
two things simulation does not model spoil that:

| | Problem | EGM's fix | Applied to |
|---|---|---|---|
| **Scale** | crystals darken under irradiation through the year; laser monitoring doesn't fully undo it | `pt *= Scale("scale", run, ScEta, r9, pt, seedGain)` | **data only** |
| **Resolution** | simulated showers are cleaner than real ones, so the MC peak is too narrow | `pt *= Normal(1, ρ)`, `ρ = SmearAndSyst("smear", pt, r9, ScEta)` | **MC only** |

These are not two halves of one correction applied everywhere. The scale's
*uncertainty* does go on MC, through `SmearAndSyst`'s own `scale_up` /
`scale_down` keys; data is never varied.

Payload: `2024_electronSS_EtDependent.json.gz`, EGM snapshot `2025-12-15` from
the same CAT tree as the lepton SFs — provenance and the pin in
[`src/vcb/corrections/README.md`](../src/vcb/corrections/README.md), the
recommendation trail in [`2024-inputs.md`](2024-inputs.md) §5b.

**Three ways to get this wrong**, all asserted in
[`tests/test_electron_ss.py`](../tests/test_electron_ss.py):

1. **The names.** Every EGM document, the jsonpog payload and the public
   examples call these `EGMScale_Compound_Ele_2024` and
   `EGMSmearAndSyst_ElePTsplit_2024`. The CAT tree renamed them to `Scale` and
   `SmearAndSyst` — same objects, verified by hashing both payloads' correction
   data against each other, but not findable under the documented names. The
   four other `EGMSmearAndSyst_Ele*` corrections in the file are intermediate
   derivation steps, not the recommended smearing.
2. **`compound()` is mandatory.** `Scale` is a chain of six corrections and the
   compound feeds the *running corrected* pT back into each step — that is what
   "Et-dependent" means. Multiplying the six by hand differs by 0.7% at
   pT = 72 GeV, |η_SC| = 2.3.
3. **The 2024 argument list dropped `AbsScEta`**, which the 2022/2023 payloads
   took between `r9` and `pt`. A snippet copied from a 2022 analysis still
   evaluates — every axis declares `flow="clamp"` — it just returns nonsense.

**The random draw is seeded from `(run, luminosityBlock, event, electron
index)`**, via splitmix64 + Box–Muller, not from a shared counter. That makes
the smearing a property of the electron rather than of the processing order, so
it reproduces under any chunk size, file split or worker count. Not cosmetic:
the draw decides whether an electron clears the pT cut, so a chunk-dependent
seed would make the skim's *event list* irreproducible. The same draw is reused
for the `smear_up` / `smear_down` variations, so those differ by the
uncertainty rather than by fresh noise.

**Output.** `ElectronPtRaw*` keeps the uncorrected value, so the correction
stays auditable and reversible. MC additionally carries
`ElectronPt{ScaleUp,ScaleDown,SmearUp,SmearDown}*` — the shifted pTs are saved
per electron rather than as a weight because a pT shift changes *which*
electrons pass the selection, which cannot be recovered downstream from the
nominal column alone.

**Coverage and limits.** EGM says not to use these below ~20 GeV (the baseline
cut sits exactly on that boundary) and that they may be ineffective at very
high pT. Every binning declares `flow="clamp"`, so out-of-range inputs return
the edge bin rather than raising — including runs before 379416 and after
386951. Nothing is clipped in our code; clamping is EGM's own choice.

Cost on the test fixture (MC, so smearing only): −0.03% on electron-channel
events (29 658 → 29 649), −0.06% on good electrons, muon channel untouched.
Near-neutral because the 32 GeV threshold sits on the *rising* side of the
W → eν Jacobian peak, so up- and down-migrations cancel. The data scale is the
larger effect and cannot be seen on an MC fixture — mean 1.005 in the barrel
and up to 1.027 in the endcap, growing through the year.

**Not propagated to MET.** See [§ MET](#met): shifting electron pT ought in
principle to propagate into the Type-1 PUPPI MET the ν p_z solution uses. It is
not, matching common practice at this size of shift, but the omission is
deliberate.

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

**Trigger matching** means: NanoAOD stores the objects the HLT actually
reconstructed and cut on, in the `TrigObj` collection, together with
`filterBits` recording which filters each one passed. `objects.trig_match_sel`
keeps the `TrigObj` entries carrying the single-lepton WPTight bit and asks
whether an offline lepton sits within **ΔR < 0.2** of one. That is what makes
the offline lepton *the reason this event was recorded*, rather than a
bystander in an event some other object triggered. The same function also
applies the offline plateau cut, so "prompt"/"trigger-matched" in this codebase
always means **matched *and* above threshold**:

```python
trig_l_sel = trig_fired & trig_l_matched & (leptons.pt >= ptcut)
```

For 2024, `HLT_Ele30_WPTight_Gsf` selects an electron with pT ≥ 32 GeV and
|η| < 2.5, while `HLT_IsoMu24` selects a muon with pT ≥ 26 GeV and |η| < 2.4.
(For 2022/2023 the electron path is `HLT_Ele32_WPTight_Gsf` with pT ≥ 35 GeV.)
The offline cut sits **above** the HLT threshold on purpose: online
reconstruction is fast and coarse, so efficiency ramps rather than steps at the
nominal value. Cutting on the plateau is what makes the POG's tag-and-probe
trigger scale factor applicable.

The rule is then one line per flavour, with no looser branch for either:

```python
use_trigger_muon     = hlt_single_mu  & trigger_muon_ready
use_trigger_electron = hlt_single_ele & trigger_electron_ready & ~use_trigger_muon
```

i.e. a trigger-matched muon if there is one, else a trigger-matched electron,
else the event has no trigger lepton and is discarded. `*_ready` reads as "a
trigger-matched candidate of this flavour exists" — the pT comparison in the
code is not a second cut but the idiom that collapses `ak.firsts`' option type
to a boolean.

Muon-over-electron only ever has to be decided in the **0.2 %** of events where
both single-lepton paths fire (95 / 59 630 on the fixture: 52 → muon,
43 → electron).

This single per-event lepton is used for the trigger-lepton output branches,
for AK4 jet cleaning (next), and for the lepton scale factors
([section 7](#lepton-scale-factors)) — three things that all silently degrade
if the event has no trigger lepton. "Otherwise discard the event" is therefore
load-bearing, and is enforced by the `trigger_lepton` cut in
[section 6](#6-event-level-selection-cutflow). Until 2026-08-09 it was **not**
enforced: the cutflow only required `nMuons + nElectrons ≥ 1`, so 3.5 % of
written events carried `TriggerLeptonFlav = PAD_VAL`. See
[`docs/history.md`](history.md).

### AK4 jets — `objects.good_ak4jets`

JECs are applied first ([section 3](#3-jet-energy-corrections-jec--jer)), then:

| Cut | Threshold |
|-----|-----------|
| pT (corrected) | > 15 GeV |
| \|η\| | < 4.7 |
| ΔR from the **trigger lepton only** | > 0.4 |
| Jet ID | Run-3 AK4 PUPPI **Tight** (`objects.ak4_jet_id`) |

Jet cleaning uses *only* the selected per-event trigger lepton, not every
reconstructed lepton — the key change from the archived overview, motivated by
the [historical study](#historical-study-why-lepton-cleaning-was-changed)
below. `vcbSkimmer` passes that one lepton as the cleaning electron or muon
collection; `good_ak4jets` retains jets only when their ΔR from every supplied
cleaning lepton is greater than 0.4.

#### Jet ID — `objects.ak4_jet_id`

**Our NanoAOD has no `Jet_jetId` branch, so the ID is recomputed here.** This
is deliberate upstream policy, stated on the JME twiki:

> Starting from NanoV15, the `Jet_jetId` is not available anymore and analyzers
> **must** compute the jetId from the following branches […]

— listing exactly the branches used below. Consistent with that,
CMSSW_15_1_X's `PhysicsTools/NanoAOD/python/jetsAK4_Puppi_cff.py` writes no
`jetId` variable, in the vanilla release *and* in the
[CMSSW-CHARGE](https://github.com/jose8af/cmssw/tree/CMSSW_15_CHARGE) fork
(whose only edits to that file are the charge-tagger discriminators and a
commented-out `puIdDisc`). JME offers two routes — a correctionlib payload, or
a direct implementation in analysis code — and this is the latter. Payload:
`POG/JME/<era>/jetid.json.gz`, corrections `AK4PUPPI_Tight` /
`AK4PUPPI_TightLeptonVeto`, generated from
[JetID13p6TeV](https://twiki.cern.ch/twiki/bin/view/CMS/JetID13p6TeV) rev 18.

Thresholds, transcribed from that payload (bins are half-open `[lo, hi)`, and
`multiplicity` ≡ `chMultiplicity + neMultiplicity`, *not* `nConstituents`):

| \|η\| | Tight | TightLepVeto adds |
|-------|-------|-------------------|
| < 2.6 | `chHEF ≥ 0.01`, `neHEF < 0.99`, `neEmEF < 0.90`, `chMultiplicity ≥ 1`, `multiplicity ≥ 2` | `chEmEF < 0.80`, `muEF < 0.80` |
| 2.6 – 2.7 | `neHEF < 0.90`, `neEmEF < 0.99` | `chEmEF < 0.80`, `muEF < 0.80` |
| 2.7 – 3.0 | `neHEF < 0.99` | — |
| > 3.0 | `neEmEF < 0.40`, `neMultiplicity ≥ 2` | — |

The regions track the detector: inside the tracker the charged-hadron and
track-multiplicity cuts are what separate a real jet from calorimeter noise;
past \|η\| = 2.6 tracking runs out and they are dropped one by one; beyond 3.0
the HF gets its own pair of cuts.

There is **one Run-3 payload, not one per era**: in jsonpog-integration every
Run-3 `jetid.json.gz` (2022EE, 2023, 2023BPix, Winter24, Summer24) is a symlink
to `2022_Summer22/jetid.json.gz`. That is deliberate, not a stale mount — the
CAT tree's `Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15/latest/jetid.json.gz`
(refreshed 2026-07-16, the same source as our V5 JEC) decompresses to an equal
JSON. Hence `ak4_jet_id` takes no `year` argument;
`tests/test_objects.py` asserts the era-equality and re-walks the JSON to
confirm the transcription jet by jet.

**Verified against the twiki, rev 24 (2026-06-13)** — the section for *"runs
2022 re-reco CDE, 2022 FG, 2023 BCD, and 2024 FG"* and its NanoV15
implementation pseudocode. Every threshold above agrees, including the forward
`neMultiplicity ≥ 2` (the `> 2` form belongs to the older *2022 prompt reco
CDE* section, which does not apply to us). Two conventions differ, both only on
an exact float equality, and we follow the payload since that is what the test
validates against:

| | twiki | payload / this code |
|---|---|---|
| charged hadron fraction | `chHEF > 0.01` | `chHEF ≥ 0.01` |
| η bin edges | closed above (`abs(eta) <= 2.6`) | half-open (`< 2.6`) |

⚠️ **The 2024 criteria are preliminary.** The twiki states they come from a
JMAR presentation on prompt-reco 2024 F and G data, *"To be tested when the
re-reco 2024 CDE will be available."* Our production is the
`24CDEReprocessingFGHIPrompt-Summer24` campaign, so a re-reco CDE update could
revise these numbers — worth re-checking before the calibration is finalised.

Design notes:

- **Tight, not TightLepVeto — a deliberate exception, not the default.** JME's
  general recommendation *is* TightLepVeto. The twiki grants an explicit
  carve-out we fall under: *"For analyses that perform any special cleaning or
  selections between jets and leptons, the jet ID can also be applied without
  the vetoing on leptons to avoid possible biases."* The ΔR > 0.4 cleaning
  above is that special cleaning, so the lepton-fake jets TightLepVeto targets
  are already gone geometrically. What its `muEF < 0.8` / `chEmEF < 0.8` cuts
  would still remove is genuine semileptonic heavy-flavour jets (b → μ + X
  inside the cone) — precisely the jets whose soft lepton carries the charge
  information this analysis calibrates a tagger on. That is the "possible
  bias" in our case. Measured cost on `tests/data/test-input.root`: 0.4 % of
  b-jets and 1.0 % of c-jets (pT > 20, \|η\| < 2.5).
  The exception applies to the *analysis* jets only. The jet-veto map decides
  which events to discard, not which jets to keep, and JERC names TightLepVeto
  there outright — so `jetveto_candidate_jets` uses it
  ([section 4](#4-jet-veto-map)). Both working points are implemented by the
  same `ak4_jet_id` and both are validated against JME's payload in
  `tests/test_objects.py`.
- **Explicit cuts, not a correctionlib call.** The payload bins on `int`-typed
  multiplicity inputs, and correctionlib 2.5.0 (the pinned version) raises
  `std::get: wrong index for variant` on an `int` `Binning` node — only the two
  η slices without multiplicity cuts evaluate at all. Explicit cuts also
  vectorise over the jagged array with no flatten/evaluate/unflatten round trip.
- **JEC order does not matter.** `pat::Jet`'s fraction accessors divide by
  `jecFactor(0) * energy()`, i.e. the *uncorrected* energy
  ([`DataFormats/PatCandidates/interface/Jet.h`](https://github.com/cms-sw/cmssw/blob/master/DataFormats/PatCandidates/interface/Jet.h)),
  so the fractions are invariant under JEC. The ID is applied after
  `get_jec_jets` alongside the other cuts.

Effect on `tests/data/test-input.root` (208 780 events): 9 824 jets that pass
pT / η / cleaning fail the ID, ≈ 3.1 % of the otherwise-selected jets. The
jet-veto map applies this same helper at its TightLepVeto working point, to its
own candidate list — see [section 4](#4-jet-veto-map).

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
- [`src/vcb/processors/objects.py`](../src/vcb/processors/objects.py) —
  `jetveto_candidate_jets` defines which jets reach the veto: JERC's "minimal
  selection" of `pt > 15`, the **TightLepVeto** jet ID and
  `chEmEF + neEmEF < 0.9`, applied to the *uncleaned* corrected collection.
  These are not the analysis jets `good_ak4jets` returns.
- [`src/boostedhh/processors/corrections.py`](../src/boostedhh/processors/corrections.py#L649-L675)
  (lines 649–675) implements `get_jetveto_event`; the year → correction-name
  map is at [lines 664–671](../src/boostedhh/processors/corrections.py#L664-L671),
  and the CVMFS path is built by `get_pog_json`
  ([lines 58–73](../src/boostedhh/processors/corrections.py#L58-L73)).
- The map payload is the campaign-specific correctionlib
  `jetvetomaps.json.gz` read from the CMS JSON POG CVMFS tree
  (`/cvmfs/cms.cern.ch/rsync/cms-nanoAOD/jsonpog-integration/POG/JME/`). It is
  **not bundled** in this repository, so CVMFS must be reachable from wherever
  the skimmer runs (including condor workers).

After JEC, the skimmer evaluates the year-specific Run-3 jet-veto map at the eta
and phi of every candidate jet. A nonzero map value marks a vetoed detector
region. The event fails `ak4_jetveto` if any candidate jet lies in such a
region; otherwise it passes. This selection is applied to both data and MC. Eta
and phi are clipped to the map range before evaluation.

For 2024 the resolved payload is `POG/JME/2024_Summer24/jetvetomaps.json.gz`,
correction `Summer24Prompt24_RunBCDEFGHI_V1`, map type `jetvetomap` — the
campaign matching the `Summer24MiniAODv6` MC and the `Summer24Prompt24_V5` JEC
above.

### Candidate jets — JERC's "minimal selection"

The map is evaluated on the jets JERC prescribes, not on the analysis
collection. From the JERC recommendations page (Jet Veto Maps → Run 3), the
*safest procedure* is to "veto events if **ANY** jet with a minimal selection
lies in the veto regions", where the minimal selection is

- jet pT > 15 GeV,
- the `tightLepVeto` jet ID (which our NanoAOD has no branch for, hence
  `objects.ak4_jet_id(wp="tightlepveto")` — see
  [section 2](#jet-id--objectsak4_jet_id)),
- `chEmEF + neEmEF < 0.9`, motivated by the Type-1 MET correction.

Three consequences worth spelling out, because each differs from the analysis
jet definition:

- **Event level, not jet level — and that is now confirmed.** Earlier revisions
  of this document flagged the event-level veto as a stricter reading inherited
  from `boostedhh`, on the strength of the Run-3 release post
  ([cms-talk 18444](https://cms-talk.web.cern.ch/t/jet-veto-maps-for-run3-data/18444))
  saying "reject **jets**". The recommendations page supersedes it: rejecting
  the event is the recommendation, to prevent spurious MET. JERC allows a
  jet-level veto only for analyses that use neither MET nor jet multiplicity —
  we use both. See [`JERC.md`](../JERC.md).
- **No lepton cleaning.** The candidates come off the uncleaned collection, so a
  jet within ΔR < 0.4 of the trigger lepton still vetoes. It has to: MET is
  rebuilt as PUPPI Type-1 over *every* jet in the event, so a jet dropped from
  the analysis collection still puts its mismeasured energy into MET, which is
  exactly the failure mode the veto exists to prevent.
- **TightLepVeto here, Tight for the analysis jets.** The exception this
  analysis takes for `good_ak4jets` (section 2 — TightLepVeto would eat genuine
  semileptonic heavy-flavour jets, whose soft lepton carries the charge
  information being calibrated) is about which jets to *keep*. Which jets may
  *throw the event away* is a separate question, and JERC names TightLepVeto.

Measured on `tests/data/test-input.root`, on events passing every other cut
(unweighted; genWeight-weighted moves each number by ≤ 0.01 pp):

| Jets fed to the map | Event loss |
|---|---|
| JERC minimal selection (**current code**) | **15.85 %** |
| previous code: cleaned analysis jets, Tight ID | 15.77 % |
| minimal selection without the EM-fraction cut | 15.86 % |
| minimal selection without the jet ID | 18.81 % |

So switching to the recipe costs 0.08 pp: 79 events that used to pass now fail,
24 that used to fail now pass, out of 70 797. The old and new definitions nearly
coincide because ΔR > 0.4 cleaning plus Tight ID happens to remove almost the
same jets as TightLepVeto — but that is a coincidence of the current lepton
selection, not something the code enforced. The jet ID is the load-bearing part
of the recipe: dropping it costs ~3 pp, because fake jets are precisely what the
vetoed hot and cold regions produce.

Remaining caveat: the pT > 15 GeV requirement inside `get_jetveto_event`
duplicates the one in `jetveto_candidate_jets`. Harmless — it is the same
threshold, and it keeps `get_jetveto_event` correct if ever called with a
looser collection.

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
| 2 | `met_filters` | every flag in `RUN3_MET_FILTERS` passes (see below) |
| 3 | `ak4_jetveto` | no good jet falls in the Run-3 jet-veto map |
| 4 | `1lep` | `nMuons + nElectrons ≥ 1` — bookkeeping only, implied by 5 |
| 5 | `trigger_lepton` | a trigger lepton was resolved ([section 2](#the-per-event-trigger-lepton)) |
| 6 | `prescale` *(optional)* | only if `--prescale-factor` is set |

The final mask is `selection.all(*names)`; only events passing all registered
cuts are written. **No b-jet multiplicity cut** is applied (unlike `ttSkimmer`)
— b-tag requirements are deferred to analysis time.

### Why `1lep` and `trigger_lepton` are both registered

Cut 1 asks *did a single-lepton path fire*; cut 5 asks *is the offline lepton
that fired it in this event*. They are not the same question, and cut 4 answers
neither: it counts good leptons, which need be neither trigger-matched nor above
the path's offline plateau threshold.

Requiring only cut 4 wrote events with no trigger lepton at all — 2 144 / 61 774
= **3.5 %** on `tests/data/test-input.root`. Broken down:

| Why no trigger lepton | Events | Fraction of the 2 144 |
|---|---|---|
| only good lepton is **below** the offline plateau cut (µ < 26, e < 32 GeV) | 2 075 | 96.8 % |
| **no** good lepton of the flavour whose HLT fired | 47 | 2.2 % |
| good lepton above threshold but **not** matched to an HLT object | 21 | 1.0 % |

Every one of those is an event where the trigger and the offline selection
disagree about what fired the path, and each was written with

- `TriggerLepton*` = `PAD_VAL` — no lepton to build W → ℓν from,
- lepton SFs of 1.0, applied silently ([section 7](#lepton-scale-factors)) — and
  the dominant category sits *on the turn-on*, precisely where the tag-and-probe
  trigger SF is not the measured quantity,
- AK4 jets never cleaned against the lepton, so an electron faking a jet still
  counts in `nJets` and `ht`.

Cut 5 removes them. Cut 4 is kept above it purely so the cutflow shows the
difference between the two, which is the number in this table; it can never
remove an event on its own, since a trigger lepton is by construction a good
lepton. On one 40 k-event chunk of the fixture (weighted, as the cutflow always
is) the last two rows are exactly that measurement:

```
all                13 957 788
single_lep_trigger  5 293 659
met_filters         5 292 311
ak4_jetveto         4 461 828
1lep                4 139 273
trigger_lepton      3 991 984      <- -3.6 %
```

Two consequences worth knowing:

- **`np_nominal` is unchanged.** It is evaluated from `gen_selected` *before*
  the first `add_selection` call (see the ORDERING MATTERS comment in
  `vcbSkimmer.py`), so tightening the selection moves the numerator of the
  `finalWeight` ratio estimator and not its denominator. Normalization
  ([`docs/normalization.md`](normalization.md)) is unaffected.
- **Skims produced before 2026-08-09 still contain the 3.5 %.** Cut them at
  analysis time with `TriggerLeptonFlav > 0`, or re-skim.

### MET (event-quality) filters

`vcbSkimmer.RUN3_MET_FILTERS`, applied by `met_filter_mask` as a plain AND of
`events.Flag.*`. These are *event-quality* filters, not a cut on MET: each one
tags a detector or reconstruction pathology (beam halo, dead ECAL cells, HF
noise, mis-measured muons) whose signature is fake missing energy. They are the
JME/JetMET POG **Run-3** set, valid for every year this repo processes
(2022 → 2024):

| Flag | What it removes |
|---|---|
| `goodVertices` | events with no good reconstructed primary vertex |
| `globalSuperTightHalo2016Filter` | beam-halo muons faking calorimeter deposits |
| `EcalDeadCellTriggerPrimitiveFilter` | energy lost to masked/dead ECAL channels |
| `BadPFMuonFilter` | badly reconstructed PF muons |
| `BadPFMuonDzFilter` | the Run-3 addition: bad PF muons flagged via track `dz` |
| `eeBadScFilter` | anomalous EE superclusters |
| `ecalBadCalibFilter` | jets pointing at known mis-calibrated ECAL crystals |
| `hfNoisyHitsFilter` | HF noise hits faking forward energy |

Two Run-2-only filters, `HBHENoiseFilter` and `HBHENoiseIsoFilter`, were applied
until 2026-08-09 and have been **removed**. They target HPD / ion-feedback noise
of the pre-Phase-1 HB/HE readout and are not part of the Run-3 recommendation.
CMSSW still runs those paths, so the branches *do* exist in the private Summer24
NanoAOD — presence in the file is not a POG endorsement. On
`tests/data/test-input.root` both are true for all 208,780 events, so the removal
is a numerical no-op on 2024 MC; the point is that the selection now says what it
means.

A filter named in `RUN3_MET_FILTERS` but missing from the input **raises**, it is
not skipped. The previous "apply whatever is present" logic could silently drop
filters while the cutflow still reported a `met_filters` stage. Unit tests:
[`tests/test_met_filters.py`](../tests/test_met_filters.py).

If this repo is ever pointed at 2022/2023, re-check `ecalBadCalibFilter`: the
stored branch was known to over-veto in those eras and JME published a
recomputation recipe. The stored branch is fine for 2024. Authoritative source
(CERN SSO): [MissingETOptionalFiltersRun2 § Run 3
recommendations](https://twiki.cern.ch/twiki/bin/viewauth/CMS/MissingETOptionalFiltersRun2#Run_3_recommendations).

---

## 7. Weights

For MC: `genWeight × pileup SF × ISR/FSR PS weights × lepton SFs × (σ × L)`
normalization (`add_weights`). `np_nominal` = Σ of the no-σL **norm-preserving**
partial weight over **every event read, before any cut** — the denominator of
the `finalWeight` ratio estimator. It is stored in the totals pickle and in a
single-entry `Norm` tree inside the skim ROOT. The skimmer never writes
`finalWeight`; it is appended globally afterward by
[`condor/scripts/normalize.py`](../condor/scripts/normalize.py) — see
[`condor/README.md`](../condor/README.md) for the workflow and
[`normalization.md`](normalization.md) for the design record.

Only `genweight`, `pileup` and the two PS weights are in
`norm_preserving_weights`, so they cancel in `weight / np_nominal`. The lepton
SFs deliberately are not: they correct an efficiency, and are meant to move the
yield.

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
`weight_norm` to recover the actual scale factor. The same caveat applies to
every `single_weight_*` below.

### Lepton scale factors

A scale factor is `eff_data / eff_MC` for one step of the lepton selection,
measured by the POGs with tag-and-probe on Z → ℓℓ. Simulation does not
reproduce reconstruction, identification, isolation or trigger efficiencies
exactly, so each MC event is reweighted by the SFs of **the lepton it was
selected on** — the per-event trigger lepton from §2, the same object that
drives `TriggerLepton*` and AK4 jet cleaning. Data is untouched.

Implemented in [`src/vcb/processors/lepton_sf.py`](../src/vcb/processors/lepton_sf.py)
(analysis-local, not in the vendored `boostedhh`, because the working points
have to track `objects.good_electrons` / `good_muons`), called from
`vcbSkimmer.add_weights`. Six weights, one per selection step per flavor, each
exactly 1.0 outside its own flavor:

| Weight | Correction | Pinned to |
|---|---|---|
| `electron_reco` | `Electron-ID-SF` / `RecoBelow20` + `Reco20to75` + `RecoAbove75` | — (stitched by pT) |
| `electron_id` | `Electron-ID-SF` / `wp90iso` | `good_electrons`: `mvaIso_WP90` |
| `electron_trigger` | `Electron-HLT-SF` / `HLT_SF_Ele30_MVAiso90ID` | `HLTs.py`: `Ele30_WPTight_Gsf` × the ID above |
| `muon_id` | `NUM_TightID_DEN_TrackerMuons` | `good_muons`: `tightId` |
| `muon_iso` | `NUM_TightPFIso_DEN_TightID` | `good_muons`: `pfRelIso04_all < 0.15` |
| `muon_trigger` | `NUM_IsoMu24_DEN_CutBasedIdTight_and_PFIsoTight` | `HLTs.py`: `IsoMu24` × the two above |

They are kept apart rather than merged into one lepton SF so the electron and
muon channels can carry independent nuisance parameters downstream; `up`/`down`
variations exist in the `Weights` container and are written only under
`--save-systematics`, exactly like pile-up.

`add_lepton_weights` still assigns 1.0 to an event with no trigger lepton —
weights are computed for every event read and masked only at the very end — but
no such event survives to the output, because the `trigger_lepton` cut
([section 6](#6-event-level-selection-cutflow)) removes them. **A written event
whose lepton SFs are all exactly 1.0 is a bug, not a convention.** Before
2026-08-09 it was the convention, and it covered ≈3.5 % of the fixture.

Measured on the 2024 fixture (`tests/data/test-input.root`, mean SF per event):

| Channel | reco | ID | iso | trigger | product |
|---|---|---|---|---|---|
| electron (24 887 ev) | 0.983 | 0.959 | — | 0.971 | **0.916** |
| muon (34 573 ev) | — | 0.986 | 0.993 | 0.979 | **0.959** |

Payloads are bundled in [`src/vcb/corrections/`](../src/vcb/corrections/) —
provenance, working-point rationale, and the `"inf"`-vs-`Infinity`
correctionlib shim are in
[that directory's README](../src/vcb/corrections/README.md). They come from the
CAT metadata tree rather than `jsonpog-integration` for a blunt reason: the
jsonpog 2024 snapshot ships **no lepton trigger SFs at all**.

Two things to be aware of:

* **No muon reco SF** — MUO publishes none for this Summer24 campaign (muon
  tracking efficiency is ~1 above 10 GeV).
* **The ECAL crack is unmeasured for electron ID**, so `good_electrons` vetoes
  it (§2). EGM fills 1.444 ≤ |η_SC| < 1.566 with exactly 1.0 and *zero*
  uncertainty; reco and HLT are measured there normally, but the ID hole is the
  one that matters, and an SF of 1 with no error is indistinguishable from "no
  correction needed" once it is in the weight. With the veto in place **zero**
  electron-channel events in the fixture take an unmeasured SF (verified in
  [`tests/test_objects.py`](../tests/test_objects.py)); relaxing the veto brings
  the problem straight back.

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
