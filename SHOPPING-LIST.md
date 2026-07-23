# SHOPPING LIST — 2024 inputs to fill in

Everything below is running on a **placeholder** right now (the pipeline works
and is safe to run — these only affect calibration-grade correctness). For
each item: what to get, what's in place now, and **exactly where to put it**.

Status as of 2026-07-23.

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

## 2. σ(TTtoLNuCB) cross section  ⭐ trivial to fill

- **Get:** the cross section (pb) you want to normalize the private
  `TTtoLNuCB` sample to. Suggested: σ_tt(NNLO, 13.6 TeV) = 923.6 pb ×
  2 × BR(W→ℓν) × BR(W→cb̄), or take the effective xsec straight from the
  gridpack/GenXsecAnalyzer of the production.
- **Now:** placeholder `923.6 * 2 * 0.333 * (0.667 * 0.0410**2 / 2)` ≈ 0.345 pb
  (|Vcb| = 0.0410).
- **Fill in:** [src/boostedhh/xsecs.py](src/boostedhh/xsecs.py) — the
  `xsecs["TTtoLNuCB"]` line right after `xsecs["TTtoLNu2Q"]`
  (marked `TODO(user)`).
- **Impact:** pure overall scale under the `finalWeight = weight / np_nominal`
  scheme.

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

## 5. (Bonus) corrupt production file

- `…/charge_Run3_2024_150X_v1/batch_001/d33939a7-a4df-4985-ba24-d69f5c18125d_CMSSW_15_CHARGE_NanoAOD.root`
  has **no `Events` tree** (dead 119 MB file). The batch_001 condor job will
  fail on it. Regenerate the file, or delete the line from the generated
  `condor/runs/<tag>/batch_001/input_list.txt` before submitting.

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
