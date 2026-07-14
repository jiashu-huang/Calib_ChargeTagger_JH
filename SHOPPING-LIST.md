# SHOPPING LIST — 2024 inputs to fill in

Everything below is running on a **placeholder** right now (the pipeline works
and is safe to run — these only affect calibration-grade correctness). For
each item: what to get, what's in place now, and **exactly where to put it**.

Status as of 2026-07-14.

---

## 1. Certified 2024 luminosity  ⭐ trivial to fill

- **Get:** the certified 2024 golden-JSON integrated luminosity in pb⁻¹
  (BRIL / `brilcalc` with the 2024 Collisions golden JSON, or the
  LumiPOG TWiki "LumiRecommendationsRun3" page).
- **Now:** placeholder `109_080.0` pb⁻¹ (~109.08 fb⁻¹, the commonly quoted
  2024 recorded number — close, but not the certified value).
- **Fill in:** [src/boostedhh/hh_vars.py](src/boostedhh/hh_vars.py) — the
  `LUMI["2024"]` entry at the top of the `LUMI` dict (marked `TODO(user)`).
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

## 4. Summer24 JER (jet energy resolution)  ⏳ blocked on JME POG

- **Get:** nothing to do until JME publishes Summer24 `JRV*` for AK4PFPuppi.
  Watch `POG/JME/2024_Summer24/jet_jerc.json.gz` on cvmfs — note it currently
  ships **Summer23BPixPrompt23_RunD_JRV1** PtResolution/ScaleFactor entries,
  which could be used as a 2023 stand-in if you want smearing sooner.
- **Now:** 2024 MC jets get the compound **Summer24Prompt24_V1_MC_L1L2L3Res**
  JEC (verified, applied via correctionlib on raw pT) but **no JER smearing**;
  a loud warning is printed at JEC-loader construction. 2022/2023 keep the
  bundled pickle factories (with smearing).
- **Fill in (when available):** either implement correctionlib JER smearing in
  `JECs._apply_correctionlib_jec_2024` in
  [src/boostedhh/processors/corrections.py](src/boostedhh/processors/corrections.py),
  or rebuild the JEC pickle with
  [src/boostedhh/corrections/build_jec.py](src/boostedhh/corrections/build_jec.py)
  (needs internet access to JECDatabase text files).
- **Impact:** MC jet pT resolution; no JES/JER *variations* are consumed by
  the Vcb skimmer anyway (`jec_shifted_jetvars` is unused).

## 5. (Bonus) corrupt production file

- `…/charge_Run3_2024_150X_v1/batch_001/d33939a7-a4df-4985-ba24-d69f5c18125d_CMSSW_15_CHARGE_NanoAOD.root`
  has **no `Events` tree** (dead 119 MB file). The batch_001 condor job will
  fail on it. Regenerate the file, or delete the line from the generated
  `condor/runs/<tag>/batch_001/input_list.txt` before submitting.

---

### Quick-check after filling things in

```bash
# should show no WARNING lines about pileup/JER any more (items 3–4):
micromamba run -n ttbar python -m vcb.run --year 2024 \
  --files <one production file> --maxchunks 1 --naming-tag check --outdir /tmp/check

# baselines: rerun and commit if values moved (items 1–3 change weights only):
micromamba run -n ttbar python tests/test_run.py
```
