# Bundled lepton corrections — provenance

Correction inputs **committed to the repo** so that skim jobs (including condor
workers) do not depend on network access or on a particular cvmfs snapshot being
mounted. Same policy as
[`src/boostedhh/corrections/README.md`](../../boostedhh/corrections/README.md),
which covers the jet and pile-up payloads; these live under `src/vcb/` instead
because the code that reads them
([`../processors/lepton_sf.py`](../processors/lepton_sf.py),
[`../processors/electron_ss.py`](../processors/electron_ss.py)) is
analysis-local — its working points track the Vcb object selection, so it does
not belong in the vendored `boostedhh` tree.

All four files are **byte-identical copies** of their cvmfs source (md5 below).

| File | Content date | Retrieved | Used by |
|---|---|---|---|
| `2024_electron.json.gz` | 2025-12-15 snapshot | 2026-08-04 | 2024 electron reco + ID SFs |
| `2024_electronHlt.json.gz` | 2025-12-15 snapshot | 2026-08-04 | 2024 electron trigger (Ele30) SFs |
| `2024_electronSS_EtDependent.json.gz` | 2025-12-15 snapshot | 2026-08-07 | 2024 electron energy scale (data) + smearing (MC) |
| `2024_muon_Z.json.gz` | 2026-06-18 snapshot | 2026-08-04 | 2024 muon ID + PF-isolation + trigger (IsoMu24) SFs |

Three of the four are *scale factors* — event weights, applied in
`lepton_sf.py`. `electronSS_EtDependent` is not: it rewrites the electron's pT
and so moves the acceptance, which is why it lives in its own module and runs
before the object selection rather than in `add_weights`.

---

## Why the CAT tree and not jsonpog-integration

Same reason as the 2024 pile-up and JEC/JER payloads, only sharper: the
`jsonpog-integration` snapshot on this machine (Sep 2025) is **missing the
trigger scale factors entirely** for both POGs in 2024, and its electron
payload is incomplete besides.

| | jsonpog `POG/EGM/2024_Summer24` + `POG/MUO/2024_Summer24` | CAT `Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15` |
|---|---|---|
| electron reco | `Reco20to75`, `RecoAbove75` only | + `RecoBelow20` |
| electron ID | cut-based + MVA WPs | same, + `PromptMVA-*`, finer syst/stat split |
| electron trigger | **absent** | `electronHlt.json.gz`, 5 paths |
| electron scale & smearing | `electronSS_EtDependent_v1.json.gz` — the Aug 2025 first release | superseded payload from `2025-10-22` on |
| muon ID / iso | 28 corrections | same |
| muon trigger | **absent** | 10 HLT corrections incl. `IsoMu24` |

A single-lepton analysis cannot leave the trigger SF out, so the CAT tree is the
only usable local source. It is also the tree the rest of the 2024 chain already
reads, and the 2024 section of EGM's own `EgammSFandSSRun3` TWiki says outright
that the corrections it describes "are also available under
`/cvmfs/cms-griddata.cern.ch/cat/metadata/EGM/`. It is recommended to fetch the
latest versions from there."

---

## `2024_electron.json.gz`

**What it is.** The EGM `electron` correctionlib payload for Summer24: one
correction, `Electron-ID-SF`, categorised as
`(year, ValType, WorkingPoint, eta, pt)` — `year` is the campaign label
`"2024Prompt"` (not the calendar year), `ValType ∈ {sf, sfup, sfdown, effMC,
effData, err_statMC, err_statData, err_stat, err_syst}`, and `WorkingPoint`
covers **both** the three reconstruction pieces (`RecoBelow20`, `Reco20to75`,
`RecoAbove75`) and every ID working point (`Veto`/`Loose`/`Medium`/`Tight`,
`wp80iso`/`wp90iso`/`wp80noiso`/`wp90noiso`, `PromptMVA-Medium`/`-Tight`).

`eta` is **supercluster** eta, not track eta.

**Origin.**
`/cvmfs/cms-griddata.cern.ch/cat/metadata/EGM/Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15/latest/electron.json.gz`.
At retrieval, `latest/` was byte-identical to the dated snapshot folder
**`2025-12-15`** (verified by md5), so the bundled copy is pinned to that
snapshot. That snapshot's `changes.md`: "added promptMVA ID electron SF, added
SingleEle trigger SF, updated syst/stat splitting".

- content date: **2025-12-15** (cvmfs snapshot)
- retrieved: **2026-08-04**
- size: 71732 bytes
- md5: `756b0cf9e3351b9bc82ee95a58a7267e`

**Which working points and why.** `wp90iso`, because
[`objects.good_electrons`](../processors/objects.py) selects on
`Electron_mvaIso_WP90`. Reco is taken from all three pT pieces, stitched by
`lepton_sf._electron_reco_sf`.

---

## `2024_electronHlt.json.gz`

**What it is.** The EGM single-electron trigger payload for Summer24: three
corrections — `Electron-HLT-SF`, `Electron-HLT-DataEff`, `Electron-HLT-McEff` —
each categorised as `(year, ValType, Path, eta, pt)`. `Path` covers
`HLT_SF_Ele30_{Loose,Medium,Tight}ID` and `HLT_SF_Ele30_MVAiso{90,80}ID`.
Only `Electron-HLT-SF` is used; the two efficiency corrections are shipped for
analyses that need to build their own trigger-OR efficiency.

**Origin.** Same directory and snapshot as `2024_electron.json.gz`.

- content date: **2025-12-15** (cvmfs snapshot)
- retrieved: **2026-08-04**
- size: 50303 bytes
- md5: `023173744449bf070c7958f661ede061`

**Which path and why.** `HLT_SF_Ele30_MVAiso90ID` — 2024 runs
`HLT_Ele30_WPTight_Gsf` ([`HLTs.py`](../HLTs.py), and
`objects.HLT_ELE30_LEPTON_PT = 32` sits above its turn-on), and the SF must be
the one measured with the same offline ID the analysis applies, hence the
`MVAiso90` denominator.

---

## `2024_electronSS_EtDependent.json.gz`

**What it is.** The EGM electron energy **scale and smearing** payload for
Summer24 — not a scale factor. It rewrites the electron's pT, so it changes the
acceptance rather than the weight, and is read by
[`../processors/electron_ss.py`](../processors/electron_ss.py) *before* the
object selection instead of in `add_weights`.

Eleven simple corrections plus one compound. Only two are used:

| Used | What it does | Signature |
|---|---|---|
| **`Scale`** (compound) | data energy scale | `("scale", run, ScEta, r9, pt, seedGain)` |
| **`SmearAndSyst`** | MC resolution smearing + all four systematics | `(syst, pt, r9, ScEta)` |

`syst` keys on `SmearAndSyst`: `smear` (the resolution ρ), `esmear`,
`smear_up`, `smear_down`, plus `escale`, `scale_up`, `scale_down` — the last
three carry the *scale* uncertainty onto MC. Data gets the nominal scale and is
never varied.

**Origin.**
`/cvmfs/cms-griddata.cern.ch/cat/metadata/EGM/Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15/latest/electronSS_EtDependent.json.gz`.
At retrieval `latest/` was byte-identical to the dated snapshot **`2025-12-15`**
(verified by `cmp`), so the bundled copy is pinned to that snapshot. Its
decompressed content is in fact unchanged across every release from
`2025-10-22` onward — sha256 `9678dbc2…` on all of them.

- content date: **2025-12-15** (cvmfs snapshot)
- retrieved: **2026-08-07**
- size: 72891 bytes
- md5: `322c7dda7024a866c3b471d1e4779e94`
- sha256 (decompressed): `9678dbc2ce8cb93fe257867e90bd150a924121985108b24f634ca63c269bf0c7`

**The names are not EGM's names.** Every EGM document, the jsonpog payload and
all the public examples call these two `EGMScale_Compound_Ele_2024` and
`EGMSmearAndSyst_ElePTsplit_2024`. The CAT tree renamed them to `Scale` and
`SmearAndSyst`. They are the same objects — checked by hashing the `data` block
of all eleven corrections in the CAT payload against the jsonpog one, all
eleven match, and the compound's stack, inputs and operators are identical too
— but code written from the EGM docs will not find them. The other four
`EGMSmearAndSyst_Ele*` corrections are intermediate steps of the derivation
chain and are **not** the recommended smearing.

**Why `SmearAndSyst` and not one of the others.** It is the final
`ElePTsplit` step, binned identically to `EGMScale_ElePTsplit_2024`, the last
member of the scale chain — and it is the one both EGM's examples and the
bamboo recipe reach for.

**Why the compound must go through `compound()`.** `Scale` stacks six
corrections with `inputs_update: ["pt"]`, so correctionlib feeds the *running
corrected* pT into each successive step. That iteration is what "Et-dependent"
means. Multiplying the six members yourself at the raw pT gives 1.0409 where
the compound gives 1.0341 (pT = 72 GeV, |ScEta| = 2.3) — 0.7% off, and worse
near a pT bin edge.

**Argument order changed for 2024.** The 2022/2023 payloads took
`(scale, run, ScEta, r9, AbsScEta, pt, gain)`. 2024 **dropped `AbsScEta`**. A
snippet copied from a 2022 analysis still runs — every axis declares
`flow="clamp"`, so nothing raises — it just silently shifts every argument by
one and returns nonsense.

**No `"inf"` shim needed.** Unlike the three SF payloads above, this one spells
its open edges as `9999.0` sentinels, so `correctionlib==2.5.0` reads it
directly. `_canonicalize_infinities` still runs on it (the loader is shared)
and is simply a no-op — which is a fact about today's file, not a guarantee
about the next release.

**Coverage.** EGM states these should not be used below ~20 GeV and may be
ineffective at very high pT. Every binning is `flow="clamp"`, so out-of-range
inputs return the edge bin: run numbers below 379416 (early 2024B/C) and above
386951 clamp to the first and last time bin. Nothing is clipped in our code —
clamping is EGM's own choice.

---

## `2024_muon_Z.json.gz`

**What it is.** The MUO `muon_Z` correctionlib payload for Summer24: 38
corrections named `NUM_<numerator>_DEN_<denominator>`, each binned in
`(eta, pt)` with a `scale_factors` category (`nominal`, `systup`, `systdown`,
plus the `stat` / `syst` / `AltBkg` / `AltSig` / `massBin` / `massRange` /
`tagIso` components). Covers ID, isolation, and — unlike jsonpog — the trigger.

`eta` is **signed** probe eta. This changed on 2026-06-18: the earlier HLT SFs
were measured against |eta|.

**Origin.**
`/cvmfs/cms-griddata.cern.ch/cat/metadata/MUO/Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15/latest/muon_Z.json.gz`.
At retrieval, `latest/` was byte-identical to the dated snapshot folder
**`2026-06-18`** (verified by md5), so the bundled copy is pinned to that
snapshot.

- content date: **2026-06-18** (cvmfs snapshot)
- retrieved: **2026-08-04**
- size: 751485 bytes
- md5: `25da71350bced1317b0c9b2e0f074824`

**Which corrections and why**, matching
[`objects.good_muons`](../processors/objects.py) (`tightId`,
`pfRelIso04_all < 0.15`) and the IsoMu24 path in [`HLTs.py`](../HLTs.py):

| Step | Correction |
|---|---|
| ID | `NUM_TightID_DEN_TrackerMuons` |
| Isolation | `NUM_TightPFIso_DEN_TightID` |
| Trigger | `NUM_IsoMu24_DEN_CutBasedIdTight_and_PFIsoTight` |

The denominators chain correctly: the isolation SF is conditional on the tight
ID already being applied, and the trigger SF on both, so the product is the
efficiency ratio for the full selection.

No muon **reco** SF is applied — this campaign publishes none (`muon_Z` has no
`Reco`/`Tracking` correction), tracking efficiency being ~1 above 10 GeV.

---

## A packaging note: `"inf"` vs `Infinity`

These payloads spell an infinite binning edge as the JSON **string** `"inf"`.
`correctionlib` is pinned to **2.5.0** (`pyproject.toml`), which only accepts
the bare `Infinity` literal and rejects the string form outright
(`RuntimeError: Invalid edges array type` for MUO,
`binning edges are not monotone increasing` for EGM). The MUO `changes.md` for
2026-06-18 records the switch: *"Fixed the infinite treatment. (Was using
Infinity, but correct one is 'inf')"*.

`lepton_sf._canonicalize_infinities` converts those strings back to floats on
load — only inside `edges` arrays, so names and category keys are untouched —
and hands the re-serialised payload to correctionlib. The **bundled files are
left byte-identical to cvmfs**, so the md5s above stay verifiable and the same
loader works against either source. Upgrading correctionlib past 2.6 would make
the shim a no-op, but it is not needed and the pin is deliberate.
