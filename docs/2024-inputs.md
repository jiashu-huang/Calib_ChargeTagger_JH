# SHOPPING LIST — 2024 inputs to fill in

Last update: **2026-07-24T13:25**

This repo is copied from Calib_ChargeTagger, which can only process files up to 
2023. As we are interested in studying Summer2024 MC, we should fill in our own
data. 

**All four calibration inputs (items 1–4) are now filled in** with real 2024
values; only the bonus data-quality note (item 5) remains. Each item below records
what was needed, what is in place, and **exactly where it lives**. The pipeline
worked on placeholders throughout — these only ever affected calibration-grade
correctness.

---

## 1. Certified 2024 luminosity  (done)

- **Get:** the certified 2024 golden-JSON integrated luminosity in pb⁻¹
  (BRIL / `brilcalc` with the 2024 Collisions golden JSON, or the
  LumiPOG TWiki "LumiRecommendationsRun3" page).
- **Set (2026-07-23):** `LUMI["2024"] = 124000.0` pb⁻¹ (124 fb⁻¹), from
  CMS DP-2026/003 (<https://cds.cern.ch/record/2952191>).
- **Location:** [src/boostedhh/hh_vars.py](src/boostedhh/hh_vars.py) — the
  `LUMI["2024"]` entry at the top of the `LUMI` dict.
- **Impact:** pure overall scale of `weight`/`finalWeight`.

## 2. σ(TTtoLNuCB) cross section  (done)

- **Done (2026-07-23):** kept `923.6 * 2 * 0.333 * (0.667 * 0.0410**2 / 2)`
  ≈ 0.345 pb in [src/boostedhh/xsecs.py](src/boostedhh/xsecs.py); removed the
  `TODO`, verified the value, and documented the reasoning inline. This is the
  **physical** σ of the `(ℓν)(cb)` final state.
- **σ_tt = 923.6 pb (NNLO+NNLL SM)**, *not* the measured 881 ± 30 pb
  (arXiv:2303.10680; agrees within uncertainty). Rationale: consistency with the
  sibling `TTto4Q/2L2Nu/LNu2Q` entries (same tt̄ split by decay), the CMS
  convention of normalizing tt̄ MC to theory, and the fact that it's a pure
  overall scale anyway. Swapping to 881 is a one-number change if preferred.
- **The `|Vcb|²` factor is mandatory — do NOT use the gridpack xsec.** The private
  POWHEG `hvq` sample (`gridpack/powheg.input`: `semileptonic 1`, `VcbOnly 1`)
  **forces** W→cb, so its generated xsec (`pwg-stat.dat` = 762 pb) has no `|Vcb|²`
  and is ~2200× the physical rate. Under `finalWeight = weight / np_nominal` that
  generated xsec is divided out and the value here is multiplied back in, so it
  must be the physical `(ℓν)(cb)` xsec. Plugging in the GenXsecAnalyzer/gridpack
  ~762 pb would overcount the signal by ~2200×.
- **Impact:** pure overall scale on the TTtoLNuCB sample under
  `finalWeight = weight / np_nominal`.

## 3. 2024 pileup weights (`puWeights.json.gz`)  (done)

- **Done (2026-07-23):** bundled the real 2024 Summer24 pileup weights at
  `src/boostedhh/corrections/2024_puWeights.json.gz`. `add_pileup_weight` in
  [src/boostedhh/processors/corrections.py](src/boostedhh/processors/corrections.py)
  now picks it up automatically (first correction key,
  `Collisions24_CDEFGHI_goldenJSON`), evaluates nominal/up/down, and the 2023
  stand-in `WARNING` is gone — **no code change was needed**.
- **Source:** `puWeights_CDEFGHI.json.gz` from the CAT metadata tree
  `/cvmfs/cms-griddata.cern.ch/cat/metadata/LUM/Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15/latest/`
  (pinned to the `2026-04-15` snapshot, md5 `05a482b9…`). This is the LUM sibling
  of the same campaign as the 2024 JEC/JER file (item 4). The
  **jsonpog-integration** snapshot on this machine has no `POG/LUM/2024_Summer24`
  (LUM stops at 2023_Summer23BPix), so the CAT tree is the only local source.
- **Era choice:** **CDEFGHI** (C–E reReco + F–I prompt; excludes commissioning
  era B) — matches the campaign name, the snapshot's `changes.md`, and the
  cms-talk request. To include era B instead, swap in `puWeights_BCDEFGHI.json.gz`
  from the same directory (no code change). Provenance in
  [src/boostedhh/corrections/README.md](src/boostedhh/corrections/README.md).
- **Impact:** nPU-dependent event weights (shape only); normalization unaffected
  (pileup is norm-preserving).

## 4. Summer24 JER (jet energy resolution)  (done)

- **Done (2026-07-23):** 2024 MC jets now get nominal **JRV2** JER smearing
  (PtResolution + ScaleFactor + the generic `JERSmear` hybrid formula) on the
  JEC-corrected pT, applied via correctionlib in `JECs._jer_smear_2024` /
  `JECs._apply_correctionlib_jec_2024`
  ([src/boostedhh/processors/corrections.py](src/boostedhh/processors/corrections.py)).
  The old "no JER" warning is gone.
- **JEC bumped V1 → V5** at the same time, to match the JRV2 JER (both are
  co-derived in the CAT Summer24 bundle). jsonpog-integration is no longer used
  for 2024 jets — its snapshot ships only a V1 JEC and a Summer23BPix JRV1
  stand-in.
- **Inputs:** bundled in `src/boostedhh/corrections/` — `2024_jet_jerc.json.gz`
  (V5 JEC + JRV2 JER, CAT 2026-07-16 snapshot) and `jer_smear.json.gz`
  (`JERSmear`, 2025-11-03); loaded bundled-first with a CAT cvmfs fallback.
  Provenance in
  [src/boostedhh/corrections/README.md](src/boostedhh/corrections/README.md).
- **Not wired (future):** JER up/down + JES variations (`…_SFUncertainty`) — the
  Vcb skimmer consumes no jet-energy variations (`jec_shifted_jetvars` unused);
  2024 **data** L2L3Residual JEC and AK8 remain no-ops.
- **Impact:** MC jet pT resolution (shape) plus a JES shift from V1→V5. Jet-pT
  baselines move — refresh with `tests/test_run.py`.

## 5. (Bonus) corrupt production files

Scanned all 447 files under `charge_Run3_2024_150X_v1` on **2026-07-26**
(open + check for an `Events` tree). **437 are good, 10 are dead** — they open
but contain no `Events` tree. Every readable file has all the branches the
skimmer needs (`Pileup_nTrueInt`, `Pileup_nPU`, `JetQk_QkCharge05/10`,
`Jet_PflavCharge`): **0 files missing branches**. Total readable: **18,823,970
events**.

| Batch | Dead file | Files in batch | Usable |
|---|---|---|---|
| batch_021 | `5e5e0349-c2f4-4d1b-a7ff-dd0e8026f620` | 3 | 2 |
| batch_036 | `e582ecfd-b9bb-4e88-a106-2094e6aeedd8` | 2 | 1 |
| batch_041 | `11283c4c-5c8e-4301-b924-c1e9bdcfcd5c` | 2 | 1 |
| batch_074 | `007b32a6-17e5-4996-bd2f-ff23f5808332` | 5 | 4 |
| batch_076 | `2affec19-d4f1-445c-a869-22d2db628f95` | 5 | 4 |
| batch_081 | `778698cf-f3ff-4d4f-9232-52cf5e78fba6` | 2 | 1 |
| **batch_082** | `37bfe028-5ad2-43ff-9901-2ab84804141f` | **1** | **0** |
| batch_086 | `8f1af746-cba8-4da2-b17a-4ebde013ce52` | 4 | 3 |
| batch_087 | `f05b3147-0f94-4796-86dd-9be2ef727213` | 5 | 4 |
| batch_091 | `8f6f2de9-5309-426e-8dbe-161db05bdf79` | 2 | 1 |

These are being regenerated (in condor production as of 2026-07-26). Until they
land, those ten condor jobs fail: the worker only checks that inputs *exist*
([calib_batch_exec.sh:77-82](../condor/templates/calib_batch_exec.sh#L77)), and
`--files` sets `skipbadfiles=False`, so one unreadable file kills the whole job.
Note **batch_082 has a single file and it is the dead one** — that batch can
produce nothing and must be dropped, not just filtered.

> The file named here previously,
> `batch_001/d33939a7-a4df-4985-ba24-d69f5c18125d`, was regenerated on
> 2026-07-24 and now skims cleanly (43,800 events, verified). It is no longer a
> problem.

---

### Quick-check after filling things in

```bash
# items 3 (pileup) and 4 (JER) no longer warn; instead item 3 prints
# "Pileup 2024: using bundled .../2024_puWeights.json.gz (correction 'Collisions24_CDEFGHI_goldenJSON')":
micromamba run -n ttbar python -m vcb.run --year 2024 \
  --files <one production file> --maxchunks 1 --naming-tag check --outdir /tmp/check

# baselines: item 4 (JER + V5 JEC) moves jet pT; items 1–3 change weights only:
micromamba run -n ttbar python tests/test_run.py
```
