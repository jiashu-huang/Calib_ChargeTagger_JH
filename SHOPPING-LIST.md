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

## 3. 2024 pileup weights (`puWeights.json.gz`)  ⚠️ currently 2023 copy-paste

- **Get:** `POG/LUM/2024_Summer24/puWeights.json.gz` from the CERN GitLab
  **jsonpog-integration** repo
  (<https://gitlab.cern.ch/cms-nanoAOD/jsonpog-integration>, master branch —
  it is NOT on this machine's cvmfs snapshot, which only has LUM up to
  2023_Summer23BPix). Alternatively derive one with
  `src/boostedhh/corrections/makePUReWeightJSON.py`.
- **Now:** the skimmer **uses the 2023 (Summer23, eraBC golden-JSON) pileup
  weights as a stand-in** and prints a loud `WARNING` on every chunk. Pileup
  is a norm-preserving weight, so this only reshapes distributions — the
  normalization is unaffected.
- **Fill in:** drop the file at
  `src/boostedhh/corrections/2024_puWeights.json.gz` — **no code change
  needed**; `add_pileup_weight` in
  [src/boostedhh/processors/corrections.py](src/boostedhh/processors/corrections.py)
  picks it up automatically (it uses the first correction key in the file) and
  the warning disappears. Then re-run the skims.
- **Impact:** nPU-dependent event weights (shape only).

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
# item 4 (JER) no longer warns; item 3 (pileup) still prints its stand-in WARNING:
micromamba run -n ttbar python -m vcb.run --year 2024 \
  --files <one production file> --maxchunks 1 --naming-tag check --outdir /tmp/check

# baselines: item 4 (JER + V5 JEC) moves jet pT; items 1–3 change weights only:
micromamba run -n ttbar python tests/test_run.py
```
