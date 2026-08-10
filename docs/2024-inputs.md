# 2024 calibration inputs — provenance

Last update: **2026-08-05**

This repo is copied from Calib_ChargeTagger, which could only process files up
to 2023. This document records, for each 2024 calibration input, what was
needed, what is in place, and **exactly where it lives** — plus a note on
input-file health (item 7). **All are filled in** with real 2024 values. The
pipeline worked on placeholders throughout — these only ever affected
calibration-grade correctness.

Items 1–4 were the original set; item 5 (lepton scale factors) was added on
2026-08-04 and item 6 (AK4 jet ID) on 2026-08-05.

---

## 1. Certified 2024 luminosity  (done)

- **Get:** the certified 2024 golden-JSON integrated luminosity in pb⁻¹
  (BRIL / `brilcalc` with the 2024 Collisions golden JSON, or the
  LumiPOG TWiki "LumiRecommendationsRun3" page).
- **Set (2026-07-23):** `LUMI["2024"] = 124000.0` pb⁻¹ (124 fb⁻¹), from
  CMS DP-2026/003 (<https://cds.cern.ch/record/2952191>).
- **Location:** [src/boostedhh/hh_vars.py](../src/boostedhh/hh_vars.py) — the
  `LUMI["2024"]` entry at the top of the `LUMI` dict.
- **Impact:** pure overall scale of `weight`/`finalWeight`.

## 2. σ(TTtoLNuCB) cross section  (done)

- **Done (2026-07-23):** kept `923.6 * 2 * 0.333 * (0.667 * 0.0410**2 / 2)`
  ≈ 0.345 pb in [src/boostedhh/xsecs.py](../src/boostedhh/xsecs.py); removed the
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
  [src/boostedhh/processors/corrections.py](../src/boostedhh/processors/corrections.py)
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
  [src/boostedhh/corrections/README.md](../src/boostedhh/corrections/README.md).
- **Impact:** nPU-dependent event weights (shape only); normalization unaffected
  (pileup is norm-preserving).

## 4. Summer24 JER (jet energy resolution)  (done)

- **Done (2026-07-23):** 2024 MC jets now get nominal **JRV2** JER smearing
  (PtResolution + ScaleFactor + the generic `JERSmear` hybrid formula) on the
  JEC-corrected pT, applied via correctionlib in `JECs._jer_smear_2024` /
  `JECs._apply_correctionlib_jec_2024`
  ([src/boostedhh/processors/corrections.py](../src/boostedhh/processors/corrections.py)).
  The old "no JER" warning is gone.
- **JEC bumped V1 → V5** at the same time, to match the JRV2 JER (both are
  co-derived in the CAT Summer24 bundle). jsonpog-integration is no longer used
  for 2024 jets — its snapshot ships only a V1 JEC and a Summer23BPix JRV1
  stand-in.
- **Inputs:** bundled in `src/boostedhh/corrections/` — `2024_jet_jerc.json.gz`
  (V5 JEC + JRV2 JER, CAT 2026-07-16 snapshot) and `jer_smear.json.gz`
  (`JERSmear`, 2025-11-03); loaded bundled-first with a CAT cvmfs fallback.
  Provenance in
  [src/boostedhh/corrections/README.md](../src/boostedhh/corrections/README.md).
- **Not wired (future):** JER up/down + JES variations (`…_SFUncertainty`) — the
  Vcb skimmer consumes no jet-energy variations (`jec_shifted_jetvars` unused);
  2024 **data** L2L3Residual JEC and AK8 remain no-ops.
- **Impact:** MC jet pT resolution (shape) plus a JES shift from V1→V5. Jet-pT
  baselines move — refresh with `tests/test_run.py`.

## 5. 2024 lepton scale factors  (done)

- **Get:** the EGM / MUO Summer24 tag-and-probe scale factors for every step of
  the single-lepton selection — electron reco + ID + Ele30 trigger, muon ID +
  PF isolation + IsoMu24 trigger — so MC lepton efficiencies match data.
- **Done (2026-08-04):** implemented in
  [src/vcb/processors/lepton_sf.py](../src/vcb/processors/lepton_sf.py) and
  called from `vcbSkimmer.add_weights`. Six separately named weights
  (`electron_reco`, `electron_id`, `electron_trigger`, `muon_id`, `muon_iso`,
  `muon_trigger`), evaluated on the event's **trigger lepton** — the same
  object that drives `TriggerLepton*` and AK4 jet cleaning — and 1.0 outside
  their own flavor. Full walkthrough in
  [docs/processor.md](processor.md) §7 "Lepton scale factors".
- **Source:** the CAT metadata tree
  `/cvmfs/cms-griddata.cern.ch/cat/metadata/{EGM,MUO}/Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15/latest/`
  — the same campaign as the pile-up (item 3) and JEC/JER (item 4) payloads —
  bundled byte-identically in
  [src/vcb/corrections/](../src/vcb/corrections/) (pinned to the EGM
  `2025-12-15` and MUO `2026-06-18` snapshots) with a cvmfs fallback.
  **jsonpog-integration is unusable here**: its 2024 snapshot ships no lepton
  trigger SFs for either POG, and a single-lepton analysis cannot go without
  them. Provenance and working-point rationale in
  [src/vcb/corrections/README.md](../src/vcb/corrections/README.md).
- **One packaging wrinkle:** these payloads spell infinite binning edges as the
  string `"inf"`, which the pinned `correctionlib==2.5.0` rejects (it only
  parses the bare `Infinity` literal). `lepton_sf._canonicalize_infinities`
  rewrites them on load, inside `edges` arrays only; the bundled files stay
  byte-identical to cvmfs.
- **ECAL crack veto (2026-08-04):** EGM leaves the electron ID SF unmeasured in
  the barrel/endcap transition, `1.444 ≤ |η_SC| < 1.566`, filling it with
  exactly 1.0 and **zero** uncertainty. `objects.good_electrons` therefore
  vetoes that region (`objects.in_ecal_crack`), in supercluster eta and on the
  SF bin edges themselves, so nothing surviving can land in the unmeasured bin —
  asserted against the payload in both directions by
  [tests/test_objects.py](../tests/test_objects.py). Cost: 575 / 62,158 fixture
  events (0.93%), all electron-channel; the muon channel is untouched.
- **Remaining gap, upstream:** no muon reco SF exists for this campaign
  (tracking efficiency ~1 above 10 GeV).
- **Impact:** a real yield shift — mean SF 0.916 (electron channel) / 0.959
  (muon channel) on the test fixture, on top of the 0.93% acceptance loss from
  the crack veto. The SFs are *not* norm-preserving, by design: they correct
  efficiencies. Weight baselines move; jet-pT baselines do not, though the
  event count does.

## 5b. 2024 electron energy scale & smearing  (done)

- **Get:** the EGM `electronSS_EtDependent` correction for Summer24 — the
  energy *scale* for data and the resolution *smearing* for MC. Distinct from
  item 5: those are efficiency weights, this rewrites the electron's pT, so it
  moves the acceptance rather than the weight.
- **Why it matters here:** ECAL crystals lose transparency under irradiation
  through the year and the laser-monitoring corrections do not fully undo it,
  so data electrons carry a mismeasured energy that depends on run, |η_SC|, r9
  and seed gain. Simulated showers are also cleaner than real ones, so the MC
  peak is too narrow. Both move electrons across the 20 GeV baseline cut and
  the 32 GeV Ele30 offline threshold.
- **Done (2026-08-07):** implemented in
  [src/vcb/processors/electron_ss.py](../src/vcb/processors/electron_ss.py) and
  called from `vcbSkimmer.process` **before** `objects.good_electrons`, since
  the correction is what decides which electrons clear those thresholds.
  Walkthrough in [docs/processor.md](processor.md) §2 "Electron energy scale
  and smearing".
- **Source:** the same CAT tree, era and pin as item 5 —
  `EGM/Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15/latest/electronSS_EtDependent.json.gz`,
  snapshot **`2025-12-15`**, bundled byte-identically as
  `src/vcb/corrections/2024_electronSS_EtDependent.json.gz` (md5
  `322c7dda7024a866c3b471d1e4779e94`). The 2024 TWiki section says explicitly
  that the CAT tree is where to fetch these from. Unchanged upstream since the
  `2025-10-22` release. Unlike item 5's payloads this one needs no `"inf"`
  shim — it spells its open edges as `9999.0` sentinels.
- **Naming trap:** every EGM document, the jsonpog-integration payload and all
  the public examples call the two corrections `EGMScale_Compound_Ele_2024` and
  `EGMSmearAndSyst_ElePTsplit_2024`. The CAT tree renamed them to **`Scale`**
  and **`SmearAndSyst`**. They are the same objects — verified by hashing the
  `data` block of all eleven corrections in both payloads against each other —
  but code written from the EGM docs will not find them.
- **Two things that bite:** the scale *must* be reached through
  `CorrectionSet.compound[...]`, because the compound feeds the running
  corrected pT back through its six-step chain (that is what "Et-dependent"
  means) — multiplying the members by hand differs by 0.7% at pT = 72 GeV,
  |η_SC| = 2.3. And the 2024 argument list **dropped `AbsScEta`**, which the
  2022/2023 payloads took between `r9` and `pt`, so a snippet copied from a
  2022 analysis silently shifts every argument by one. Both are asserted in
  [tests/test_electron_ss.py](../tests/test_electron_ss.py).
- **Randomness:** the MC smearing is seeded from `(run, luminosityBlock,
  event, electron index)`, not from a counter, so it is reproducible under any
  chunk size or worker count. This is not cosmetic — the draw decides whether
  an electron clears the pT cut, so a chunk-dependent seed would make the skim's
  *event list* irreproducible.
- **Impact on the test fixture:** the MC smearing is nearly yield-neutral —
  −0.03% on electron-channel events (29,658 → 29,649), −0.06% on good
  electrons, muon channel untouched. The threshold sits on the rising side of
  the W → eν Jacobian peak (~40 GeV), so up- and down-migrations cancel. The
  *data* scale is the larger effect and is not visible on an MC fixture: mean
  1.005 in the barrel and up to 1.027 in the endcap, growing through the year,
  worth +0.5% to +1.1% on the count above 32 GeV. Systematics are sub-percent
  (`escale` ≈ 0.06–0.6%, resolution negligible).
- **Not propagated to MET.** Shifting electron pT ought in principle to
  propagate into the Type-1 PUPPI MET (§ "MET"), which the semileptonic leg
  uses for the ν p_z solution. It is not, matching common practice at this
  size of shift — but it is a deliberate omission, not an oversight.

## 6. AK4 jet ID  (done)

- **Get:** the Run-3 AK4 PUPPI jet ID, which rejects calorimeter-noise and
  beam-halo fakes. Mandatory for every Run-3 analysis.
- **Why it needed doing at all:** our NanoAOD has **no `Jet_jetId` branch**, by
  upstream design — JME states it outright: *"Starting from NanoV15, the
  `Jet_jetId` is not available anymore and analyzers **must** compute the jetId
  from the following branches"* (the seven we use).
  Consistent with that, CMSSW_15_1_X's `jetsAK4_Puppi_cff.py` writes no `jetId`
  variable — checked in both the vanilla release on cvmfs and the
  [CMSSW-CHARGE](https://github.com/jose8af/cmssw/tree/CMSSW_15_CHARGE) fork,
  whose diff to that file only adds charge-tagger discriminators and comments
  out `puIdDisc`. Confirmed on the produced files: `315d7993_fields.csv` has no
  `Jet_jetId`. NanoAOD ships exactly the inputs instead (`chHEF`, `neHEF`,
  `chEmEF`, `neEmEF`, `muEF`, `chMultiplicity`, `neMultiplicity`).
- **Done (2026-08-05):** `objects.ak4_jet_id` in
  [src/vcb/processors/objects.py](../src/vcb/processors/objects.py), applied at
  the **Tight** working point inside `good_ak4jets`. Full threshold table and
  the Tight-vs-TightLepVeto argument:
  [docs/processor.md](processor.md#jet-id--objectsak4_jet_id).
- **Source of the numbers:** `POG/JME/2024_Summer24/jetid.json.gz`, correction
  `AK4PUPPI_Tight`, whose `description` names
  [JetID13p6TeV rev 18](https://twiki.cern.ch/twiki/bin/view/CMS/JetID13p6TeV?rev=18)
  as its upstream. **There is only one Run-3 file:** in jsonpog-integration
  every Run-3 era's `jetid.json.gz` is a *symlink* to
  `2022_Summer22/jetid.json.gz` — 2022EE, 2023, 2023BPix, Winter24 and
  Summer24 alike.
- **Cross-checked against CAT, and it is not a stale-snapshot artifact.**
  jsonpog's 2024 snapshot is untrustworthy for jets (item 4: it ships only a V1
  JEC), so the same doubt applied here. It survives:
  `JME/Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15/latest/jetid.json.gz`
  in the CAT tree — the actively-maintained source this repo already uses for
  the V5 JEC + JRV2 JER, refreshed 2026-07-16 — decompresses to a JSON that
  compares **equal** to the jsonpog one, `AK4PUPPI_Tight` data tree included.
  Two independently-maintained sources shipping the same criteria for Summer24
  is what makes the shared 2022 lineage deliberate rather than an oversight.
- **Nothing new to bundle.** The thresholds are hard-coded, not read at
  runtime, so no extra cvmfs dependency on the workers. (jsonpog-integration is
  needed only by the unit tests, which skip without it.) That is not just
  convenience: correctionlib 2.5.0 **cannot evaluate this payload** — it bins
  on `int`-typed multiplicity inputs and raises `std::get: wrong index for
  variant`, so only the two η slices without multiplicity cuts return anything.
- **Verified against the twiki, rev 24 (2026-06-13):** every threshold agrees
  with the *"2022 re-reco CDE, 2022 FG, 2023 BCD, and 2024 FG"* section and its
  NanoV15 pseudocode. Two conventions differ on an exact float equality only
  (twiki `chHEF > 0.01` vs payload `≥ 0.01`; twiki closes η bins above, payload
  half-open); we follow the payload. Details in
  [docs/processor.md](processor.md#jet-id--objectsak4_jet_id).
- **⚠️ Preliminary, revisit later.** The twiki flags the 2024 numbers as coming
  from a JMAR presentation on prompt-reco 2024 F/G, *"To be tested when the
  re-reco 2024 CDE will be available"*. Our campaign is
  `24CDEReprocessingFGHIPrompt-Summer24`, so a re-reco CDE update could revise
  them. Re-check before the calibration is finalised.
- **Impact:** 3.1% of otherwise-selected jets are removed (9,824 on the test
  fixture), so `nJets` / `ht` / the saved jet slots all move. Jet and event
  baselines both need refreshing with `tests/test_run.py`.
- **Jet ID before or after the veto map? — settled 2026-08-10.** The JERC
  recommendations page (<https://cms-jerc.web.cern.ch/Recommendations/>, Jet
  Veto Maps → Run 3) prescribes its own candidate list for the map: pT > 15,
  **TightLepVeto** ID, `chEmEF + neEmEF < 0.9`, off the uncleaned collection.
  The veto now uses exactly that (`objects.jetveto_candidate_jets`) rather than
  the analysis jets, so the ordering is no longer our choice to make. The ID is
  required, and it matters: without it the veto costs ~3 pp more acceptance.
  See [docs/processor.md](processor.md#4-jet-veto-map) and [JERC.md](../JERC.md).

## 7. (Bonus) corrupt production files  (resolved)

**Resolved 2026-07-26:** the ten dead files listed below were regenerated, and
a rescan of the full input set found **465 files, 0 bad, 0 missing branches,
19,823,340 events** — see the input-health note in
[condor/README.md](../condor/README.md). The record of what was found is kept
below because the failure mode (a file that opens but has no `Events` tree,
which kills its whole condor job since `--files` sets `skipbadfiles=False`)
is worth re-checking after any future regeneration.

Original scan, 2026-07-26: all 447 files under `charge_Run3_2024_150X_v1`
(open + check for an `Events` tree). **437 were good, 10 dead** — they opened
but contained no `Events` tree. Every readable file had all the branches the
skimmer needs (`Pileup_nTrueInt`, `Pileup_nPU`, `JetQk_QkCharge05/10`,
`Jet_PflavCharge`): **0 files missing branches**. Total readable at the time:
**18,823,970 events**.

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

All ten were regenerated on 2026-07-26 and the rescan came back clean. While
they were dead, those ten condor jobs failed outright: the worker only checks
that inputs *exist*
([calib_batch_exec.sh:77-82](../condor/templates/calib_batch_exec.sh#L77)), and
`--files` sets `skipbadfiles=False`, so one unreadable file kills the whole
job. (At the time, **batch_082's only file was the dead one**, so that batch
could produce nothing at all.)

> The file named here previously,
> `batch_001/d33939a7-a4df-4985-ba24-d69f5c18125d`, was regenerated on
> 2026-07-24 and now skims cleanly (43,800 events, verified). It is no longer a
> problem.

---

### Quick-check after filling things in

```bash
# items 3 (pileup), 4 (JER) and 5 (lepton SFs) no longer warn; instead item 3 prints
# "Pileup 2024: using bundled .../2024_puWeights.json.gz (correction 'Collisions24_CDEFGHI_goldenJSON')"
# and item 5 logs "Lepton SF 2024 <payload>: using bundled ...":
micromamba run -n ttbar python -m vcb.run --year 2024 \
  --files <one production file> --maxchunks 1 --naming-tag check --outdir /tmp/check

# baselines: items 4 (JER + V5 JEC) and 6 (jet ID) move jet pT / nJets — item 6 also
# shifts the event count via the jet-veto map; items 1–3 and 5 change weights only
# (item 5 also adds six single_weight_* columns to the schema); item 5b moves the
# electron pT and event count, and adds 15 Electron{PtRaw,PtScale*,PtSmear*} columns:
micromamba run -n ttbar python tests/test_run.py
```
