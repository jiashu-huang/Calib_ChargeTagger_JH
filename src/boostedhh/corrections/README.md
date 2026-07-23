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
| `2024_jet_jerc.json.gz` | 2026-07-16 snapshot | 2026-07-23 | 2024 JEC (V5) + JER (JRV2) — *wiring pending* |
| `jer_smear.json.gz` | 2025-11-03 | 2026-07-23 | 2024 JER stochastic-smear formula — *wiring pending* |

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

## `2024_jet_jerc.json.gz`  *(new — Step 1 of the JER plan)*

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

**Status.** Bundled, but not yet consumed by the code — `corrections.py` still
applies the V1 compound from jsonpog and no smearing. Wiring it in (loader,
`_apply_jer_2024`, V1→V5 swap) is Steps 2–5 of the JER plan.

**Runtime fallback (planned).** When wired, the loader will prefer this bundled
file and fall back to the CAT `latest/` path, which tracks the newest snapshot
rather than the pinned 2026-07-16 one.

---

## `jer_smear.json.gz`  *(new — Step 1 of the JER plan)*

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

**Status.** Bundled, wiring pending (same Steps 2–5). This formula is not tied to
2024 — the same file applies to any campaign's resolution/SF inputs.

---

## Related (not in this directory yet)

- `2024_puWeights.json.gz` — planned bundle for 2024 pileup weights (SHOPPING-LIST
  item 3). Until present, `add_pileup_weight` falls back to the 2023 Summer23
  weights as a stand-in with a loud warning.

[cloudpickle]: https://github.com/cloudpipe/cloudpickle
[coffea]: https://github.com/scikit-hep/coffea
