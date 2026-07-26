# Bundled corrections — provenance

This directory holds correction inputs that are **committed to the repo** so that
skim jobs (including condor workers) do not depend on network access or on a
particular cvmfs snapshot being mounted. This file records where each bundled
artifact came from, when, and what the code does with it.

Retrieval dates below are when the file was copied into this repo; the *content*
date (the JME publication/snapshot the file represents) is listed separately
because cvmfs mtimes track the sync, not the derivation.

| File | Content date | Retrieved | Used by |
|---|---|---|---|
| `jec_compiled_py311.pkl.gz` | 2022 `22Sep2023` reReco / 2023 `Prompt` (see tags) | 2026-07-14 (repo port) | 2022 / 2023 JEC **+ JER** |
| `2024_jet_jerc.json.gz` | 2026-07-16 snapshot | 2026-07-23 | 2024 MC AK4 JEC (V5) + nominal JER (JRV2) |
| `jer_smear.json.gz` | 2025-11-03 | 2026-07-23 | 2024 MC AK4 nominal JER smearing formula |
| `2024_puWeights.json.gz` | 2026-04-15 snapshot | 2026-07-23 | 2024 pileup event weight (nominal/up/down) |

---

## `jec_compiled_py311.pkl.gz`

**What it is.** A gzip-compressed [cloudpickle] of pre-built [coffea] jet-correction
factory objects — live Python objects, not lookup tables. Unpickling yields a dict:

- `jet_factory`  — dict of `CorrectedJetsFactory` (AK4PFPuppi), keyed by era
- `fatjet_factory` — dict of `CorrectedJetsFactory` (AK8PFPuppi), keyed by era
- `met_factory` — a `CorrectedMETFactory`

Each factory bundles the compiled JERC text-file lookups, so a single
`factory.build(jets, cache)` call applies the full JEC chain **and JER smearing**
in one step.

**Origin.** Vendored from the upstream `boostedhh` / `bbtautau` framework (authors
Raghav Kansal, Cristina Suarez) during the port into this repo on **2026-07-14**.
It is produced by [`build_jec.py`](build_jec.py) from JME JECDatabase text files
(`.jec.txt` scale, `.junc.txt` uncertainty, `.jr.txt` resolution, `.jersf.txt`
resolution SF). Those source text files are **not** shipped here — `data/jecs/` is
empty — so the pickle cannot be rebuilt locally without first fetching them
(needs internet / JECDatabase).

**Correction versions baked in** (MC eras; data eras carry only L2Relative +
L2L3Residual):

| Era key | JEC | JER |
|---|---|---|
| `2022mc` | `Summer2222Sep2023_V2` | `Summer2222Sep2023_JRV1` |
| `2022EEmc` | `Summer22EE22Sep2023_V2` | `Summer22EE22Sep2023_JRV1` |
| `2023mc` | `Summer23Prompt23_V1` | `Summer23Prompt23RunCv1234_JRV1` |
| `2023BPixmc` | `Summer23BPixPrompt23_V1` | `Summer23BPixPrompt23RunD_JRV1` |

**How the code uses it.** `JECs.__init__` in
[`../processors/corrections.py`](../processors/corrections.py) loads this file for
years `2022 / 2022EE / 2023 / 2023BPix` (and would load `jec_compiled.pkl.gz` /
`jec_compiled_run2.pkl.gz` for Python < 3.11 / Run 2 — **neither of those two is
shipped here**, so only 2022–2023 on Python ≥ 3.11 is actually supported by the
pickle path). The `ttbar` env is Python 3.11.0, so the `_py311` build is the one
selected. 2024 does **not** use this pickle (see below).

The `_py311` suffix exists because pickled coffea objects are not reliably portable
across Python versions; a matching build is kept per interpreter major.minor.

---

## `2024_jet_jerc.json.gz`

**What it is.** The full JME `jet_jerc` correctionlib payload for the 2024
Summer24 campaign: the compound JEC **and** the JER pieces in one file.

- Compound JEC: `Summer24Prompt24_V5_MC_L1L2L3Res_AK4PFPuppi`
  (+ the `DATA` compound, all individual JEC levels, and the full set of
  uncertainty sources — 75 simple corrections in total, available for later use)
- JER (JRV2): `Summer24Prompt24_JRV2_MC_PtResolution_AK4PFPuppi`,
  `…_ScaleFactor_…`, `…_SFUncertainty_…`

**Origin.**
`/cvmfs/cms-griddata.cern.ch/cat/metadata/JME/Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15/latest/jet_jerc.json.gz`
(the CAT metadata tree, **not** the `jsonpog-integration` tree the older years
read). At retrieval, `latest/` was byte-identical to the dated snapshot folder
**`2026-07-16`** (verified by md5), so the bundled copy is pinned to that snapshot.

- content date: **2026-07-16** (cvmfs snapshot)
- retrieved: **2026-07-23**
- size: 625409 bytes
- md5: `ca0ea4e4cae372969a6036c53a960bb2`

**Why the CAT tree and not jsonpog.** The `jsonpog-integration` snapshot on this
machine (Sep 2025) ships only a **Summer23BPix JRV1** JER stand-in and the older
**V1** JEC for 2024. The real Summer24 **JRV2** JER — and the newer **V5** JEC it
is co-derived with — are only in the CAT tree. Bundling this file adopts the
consistent, POG-intended **V5 + JRV2** pair.

**How the code uses it.** `JECs.__init__` in
[`../processors/corrections.py`](../processors/corrections.py) loads this file for
`year == "2024"` through `correctionlib`, preferring the bundled repo copy and
falling back to the CAT `latest/` path if the bundled file is unavailable. The
2024 path does not use the coffea pickle factories above.

For 2024 MC AK4 jets, `_apply_correctionlib_jec_2024` evaluates the compound
`Summer24Prompt24_V5_MC_L1L2L3Res_AK4PFPuppi` on raw jet pT/mass inputs and
updates jet `pt`, `mass`, and `rawFactor`. It then evaluates the JRV2
`PtResolution` and `ScaleFactor` corrections from this file and passes those
values to the generic `JERSmear` formula in `jer_smear.json.gz` for nominal JER
smearing.

Current limits: 2024 data JECs are not implemented; 2024 AK8 JECs/JER are not
implemented; JES/JER up/down variations are not wired into the skimmer output.

---

## `jer_smear.json.gz`

**What it is.** The generic, campaign-independent **`JERSmear`** correction: the
hybrid stochastic-smearing formula that turns a resolution + SF + (optional) matched
gen-jet pT into a per-jet multiplicative smear factor. Inputs
`(JetPt, JetEta, GenPt, Rho, EventID, JER, JERSF)`; it branches on the sign of
`GenPt` (matched → scaling method, unmatched → stochastic with a deterministic
`hashprng` seed).

**Origin.**
`/cvmfs/cms-griddata.cern.ch/cat/metadata/JME/JER-Smearing/latest/jer_smear.json.gz`.
(An identical-size copy also lives at the top of the `jsonpog-integration` JME
tree; the CAT copy was used for consistency with `2024_jet_jerc.json.gz`.)

- content date: **2025-11-03** (cvmfs mtime)
- retrieved: **2026-07-23**
- size: 462 bytes
- md5: `390e4be4be109bb1a2d3a116f2c9386a`

**How the code uses it.** `JECs.__init__` loads this file for `year == "2024"`,
again preferring the bundled copy and falling back to the CAT `latest/` path. In
`_jer_smear_2024`, the code calls `JERSmear` with the JEC-corrected jet pT, jet
eta, matched gen-jet pT or `-1` for stochastic smearing, event rho, event number,
JER resolution, and JER scale factor. The resulting non-negative smear factor is
multiplied into the corrected jet `pt` and `mass`.

The formula itself is not campaign-specific; in this repo it is currently used
only by the 2024 MC AK4 path.

---

## `2024_puWeights.json.gz`

**What it is.** The LUM `puWeights` correctionlib payload for the 2024 Summer24
campaign: the pileup event reweighting derived from the ratio of the data
`NumTrueInteractions` profile (certified golden JSON) to the Summer24 MC profile.
One correction, `Collisions24_CDEFGHI_goldenJSON`, with inputs
`(NumTrueInteractions: real, weights: string)` where `weights ∈ {nominal, up, down}`
and output `weight`.

**Origin.**
`/cvmfs/cms-griddata.cern.ch/cat/metadata/LUM/Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15/latest/puWeights_CDEFGHI.json.gz`
(the CAT metadata tree — the LUM sibling of the same
`Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15` campaign that
`2024_jet_jerc.json.gz` comes from, **not** the `jsonpog-integration` tree). At
retrieval, `latest/` was byte-identical to the dated snapshot folder
**`2026-04-15`** (verified by md5 and full `diff -qr`), so the bundled copy is
pinned to that snapshot.

- content date: **2026-04-15** (cvmfs snapshot)
- retrieved: **2026-07-23**
- size: 2737 bytes
- md5: `05a482b913a68ed10755f35341c12f57`

**Which era set and why.** The directory ships several golden-JSON variants:
per-era (`B` … `I`), the inclusive `BCDEFGHI`, and `CDEFGHI`. We bundle the
**CDEFGHI** file. It matches (a) the campaign name itself —
`24CDEReprocessingFGHIPrompt` (C–E reReco + F–I prompt, no commissioning era B),
(b) that snapshot's `changes.md` ("2026-04-15: Added weights for CDEFGHI only"),
(c) the cms-talk request that motivated it (`pileup-weights-for-2024cdefghi`), and
(d) the sibling `2024_jet_jerc.json.gz`, taken from the identically-named JME
campaign. `CDEFGHI` did not exist in the older `2025-12-02` snapshot — it was added
specifically on 2026-04-15. To include the commissioning era B instead, bundle
`puWeights_BCDEFGHI.json.gz` (correction `Collisions24_BCDEFGHI_goldenJSON`) from
the same directory; no code change is needed because `add_pileup_weight` reads the
first correction key in the file.

**Why the CAT tree and not jsonpog.** The `jsonpog-integration` snapshot on this
machine has no `POG/LUM/2024_Summer24` — its LUM tree stops at
`2023_Summer23BPix`. The 2024 pileup weights live only in the CAT tree (same
reason as `2024_jet_jerc.json.gz`).

**How the code uses it.** `add_pileup_weight` in
[`../processors/corrections.py`](../processors/corrections.py) loads this file
through `correctionlib`, preferring the bundled repo copy and otherwise falling
back to the CAT campaign directory on cvmfs. It takes the first (only) correction
key and evaluates `nominal` / `up` / `down` on the per-event `Pileup_nTrueInt`
(`NumTrueInteractions`, clipped to `[0, 99]`), clipping each resulting weight to
`[0, 10]`. Note this is `nTrueInt`, the Poisson *mean*, not the sampled count
`nPU` that upstream `boostedhh` passed. Pileup is norm-preserving, so this
reshapes pile-up-dependent distributions without changing the overall
normalization.

[cloudpickle]: https://github.com/cloudpipe/cloudpickle
[coffea]: https://github.com/scikit-hep/coffea
