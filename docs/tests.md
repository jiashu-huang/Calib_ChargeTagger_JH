# Tests & regression baselines

Two layers: fast pytest units that need no input data, and a standalone
integration run that regenerates the committed regression baselines from the
~1 GB test fixture.

## Unit tests

```bash
pytest tests/          # 102 tests, ~10 s, no input data needed
```

| File | What it does |
|---|---|
| [tests/test_package.py](../tests/test_package.py) | One smoke test: the installed distribution's version matches `vcb.__version__`. Fails if `vcb` isn't importable or the editable install is stale/missing — i.e. it catches a broken **Setup** before anything else does. |
| [tests/test_vcb_gen_truth.py](../tests/test_vcb_gen_truth.py) | Six unit tests for the gen-truth helpers in [src/vcb/processors/GenSelection.py](../src/vcb/processors/GenSelection.py), run on hand-built awkward arrays (no NanoAOD file). Covers: **(1)** W decay-mode masks split hadronic vs. leptonic with τ counted as *leptonic*; **(2)** the `GenWto{UD,US,CD,CS,UB,BC}` flavor tags are unordered (q1/q2 swap-invariant) and mutually exclusive — exactly one fires per W; **(3)** gen quarks stored with mass 0 get the PDG mass back from their flavor (c → 1.27, b → 4.18 GeV; light quarks stay 0, already-non-zero masses untouched); **(4)–(6)** lepton mass, charge, and flavor come from the PDG id with the right sign convention (`11` → −1, `-11` → +1) and flavor stored as \|pdgId\|; and throughout, missing entries stay `PAD_VAL` rather than silently becoming 0. |
| [tests/test_objects.py](../tests/test_objects.py) | 29 unit tests for the helpers in [src/vcb/processors/objects.py](../src/vcb/processors/objects.py), on hand-built awkward arrays. **Electrons:** **(1)** supercluster eta prefers the stored `superclusterEta` branch and falls back to `eta + deltaEtaSC`; **(2)** the ECAL crack veto fires inside the transition and nowhere else, is symmetric in sign (a slip would leave the whole −1.5 side unvetoed), is half-open `[1.444, 1.566)` to match the correctionlib bin exactly, and survives jagged input; and **(3)** — the load-bearing pair — a scan against the *bundled EGM payload* asserting in both directions that the veto region is precisely the region where the ID SF is unmeasured (`sf == sfup == sfdown == 1`). That last check is what stops a future edit to either edge from silently reopening the hole the veto exists to close, or from throwing away electrons that are perfectly well measured. **Jets:** the AK4 PUPPI jet ID, both by hand (one test per η region, plus the half-open edges, η-sign symmetry, and where TightLepVeto does and does not add its lepton cuts) and against JME's own payload — the `jetid.json.gz` decision tree is walked in plain Python and `ak4_jet_id` must reproduce it on 20 000 random jets per era per working point, for all five Run-3 eras, which are separately asserted to be byte-identical. Those cvmfs-backed tests skip when it is not mounted. Plus `jetveto_candidate_jets`, the JERC "minimal selection" the jet-veto map is evaluated on: one assertion per bullet of the recipe (pT > 15 strictly, TightLepVeto rather than Tight, `chEmEF + neEmEF < 0.9` on the *sum*), since each is a deviation from the analysis jet definition that a future edit could quietly undo -- dropping the ID alone would cost ~3 percentage points of acceptance. |
| [tests/test_lepton_sf.py](../tests/test_lepton_sf.py) | Fifteen unit tests for the 2024 lepton scale factors in [src/vcb/processors/lepton_sf.py](../src/vcb/processors/lepton_sf.py), on hand-built leptons — no NanoAOD file, since the correction payloads are bundled in the repo. Covers: **(1)** the `"inf"`→`Infinity` edge shim rewrites only inside `edges` arrays, leaving names and category keys alone; **(2)** all three 2024 payloads load and really contain the working points pinned in `LEPTON_SF_KEYS` — a typo there would otherwise surface only mid-production; **(3)** an unsupported year is a clean no-op rather than a crash; **(4)** flavors do not leak (each weight is exactly 1 outside its own flavor) and an event with no trigger lepton is unweighted; **(5)** every SF sits within a few percent of 1 and its up/down bracket the nominal — a mis-ordered `evaluate()` argument lands far outside; **(6)** the clips hold at the binning edges the payloads declare `flow="error"` on (muon \|eta\| = 2.4, muon pT below the IsoMu24 floor), which would *raise*, not fail; and **(7)** the three EGM reco pT pieces are each picked up and stitched, with sub-10 GeV electrons keeping 1.0 rather than raising. |
| [tests/test_electron_ss.py](../tests/test_electron_ss.py) | Twenty-six unit tests for the 2024 electron energy scale & smearing in [src/vcb/processors/electron_ss.py](../src/vcb/processors/electron_ss.py), on hand-built electrons — the EGM payload is bundled, so no NanoAOD file. The three that earn their keep guard the ways this correction is silently misapplied: **(1)** the corrections really are named `Scale` / `SmearAndSyst` in the CAT tree and *not* the `EGMScale_Compound_Ele_2024` / `EGMSmearAndSyst_ElePTsplit_2024` every EGM document calls them, and `Scale` is reachable only through `.compound`; **(2)** the compound is genuinely Et-dependent — evaluating its six members at the raw pT gives a *different* answer, so nobody can "simplify" the compound away unnoticed; and **(3)** the scale sits within 10% of 1, the smearing width is a plausible resolution, and the endcap resolves worse than the barrel — bounds a shifted argument list lands far outside, which matters because the 2024 payload dropped the `AbsScEta` argument the 2022/2023 ones took and every axis is `flow="clamp"`, so a wrong call returns nonsense instead of raising. The rest cover: the deterministic RNG really is a standard normal with per-electron streams that decorrelate; smearing is reproducible and **independent of chunk size** (the draw decides which electrons pass the pT cut, so a chunk-dependent seed would make the event list itself irreproducible); the up/down variations bracket the nominal in the right quantity — width for `smear_*`, mean for `scale_*` — which a fresh Gaussian per variation would wash out; data gets a deterministic scale and *no* variation fields while MC gets smearing and all four; `pt_raw` survives everywhere, including the unsupported-year no-op, so the output schema never becomes year-dependent; and the skimmer's `ElectronEnergyMC` columns stay in step with `PT_VARIATIONS`. |
| [tests/test_met_filters.py](../tests/test_met_filters.py) | Seven unit tests for the event-quality (MET) filters in [src/vcb/processors/vcbSkimmer.py](../src/vcb/processors/vcbSkimmer.py), on hand-built `Flag` records. Pins **(1)** the *contents* of `RUN3_MET_FILTERS` against the JME Run-3 recommendation, with a dedicated assertion that the Run-2-only `HBHENoiseFilter`/`HBHENoiseIsoFilter` are absent — their branches still exist in the private Summer24 NanoAOD, so any "apply whatever is in the file" logic would quietly reintroduce them; and **(2)** the *failure mode* of `met_filter_mask`, which must raise on a missing branch rather than skip it, since a skipped filter leaves a `met_filters` cutflow stage that looks applied but is looser than it claims. Plus the AND semantics: one failing flag vetoes the event, and a set of flags each vetoing a different event leaves nothing. |
| [tests/test_top_pt.py](../tests/test_top_pt.py) | Eighteen unit tests for the ttbar top-pT reweighting in [src/vcb/processors/top_pt.py](../src/vcb/processors/top_pt.py), on hand-built gen particles carrying the real NanoAOD `GenParticle` behavior — the coefficients are hardcoded fits, so no payload, no fixture, no cvmfs. In rough order of how badly a slip would hurt: **(1) transcription** — the fit coefficients were copied off a twiki by eye, so each of the three functions is pinned at several pT against arithmetic written out longhand, and the *sign* is pinned separately by requiring the SF fall monotonically and cross 1 between soft and hard tops (a flipped exponent still looks like a smooth curve near 1 while correcting the spectrum the wrong way); **(2) the wrong tops** — the twiki says anything but the `isLastCopy` parton-level top gives "an invalid reweighting", so intermediate hard-process copies at a wildly different pT must be ignored, as must b quarks and Ws sharing the same flags, and the statusFlags bit pattern is derived from coffea's own `GenParticle.FLAGS` rather than hardcoded so a coffea reordering fails here instead of silently emptying the selection in production; **(3) the combination** — `sqrt(SF·SF)` is pinned against the explicit geometric mean at *well-separated* pT, where it measurably differs from the arithmetic mean, plus swap-invariance of the two top slots; and **(4) the gate** — a non-ttbar dataset gets `{}` and not columns of 1.0, since these weights are explicitly invalid for single top and ttX and an all-ones column invites somebody to apply them anyway. Plus the clamping rules (data-based flat above 500 GeV per the twiki, `NNLONLO` above 2000 GeV by our own choice) and that a negative gen pT cannot run the exponent up. |
| [tests/test_run.py](../tests/test_run.py) | **Not a pytest test** — a standalone end-to-end script (pytest collects no tests from it). Runs the real skimmer on one NanoAOD file and regenerates the regression artifacts in `tests/outfile/`. Needs the fixture and takes a few minutes. |

## The integration run

```bash
# fixture is git-ignored — copy it in once
cp /isilon/export/home/jhuan166/Vcb/Calib_ChargeTagger/tests/data/test-input.root tests/data/

python tests/test_run.py            # defaults: tests/data/test-input.root, --year 2024
```

It produces six files in `tests/outfile/`, three of which are **committed
baselines** — an unexplained diff in any of them is a bug, an expected diff
should be reviewed and committed with the change that caused it:

| Artifact | Committed? | Purpose |
|---|---|---|
| `test-output-schema.csv` | **yes** | every output branch name + ROOT type — catches accidentally added/dropped/retyped branches |
| `test-output-0th-event.txt` | **yes** | full value dump of event 0 — catches value-level changes (e.g. the JEC V1→V5 + JER shift moved jet pT) |
| `test-jet-tagger-roundtrip.txt` | **yes** | per-jet input↔output tagger check over *every* event, via `diagnostics/check_jet_tagger_roundtrip.py` — see below. A `FAIL` exits `tests/test_run.py` non-zero |
| `test-output.root` | no (git-ignored) | the skim itself |
| `test-output_jet_pt.pdf` | no (git-ignored) | unweighted AK4 jet pT plot, via `diagnostics/plot_jet_pt.py` — an eyeball check |
| `test-output_trigger_lepton_pt_flavor.pdf` | no (git-ignored) | trigger lepton pT split by `TriggerLeptonFlav`, via `diagnostics/plot_trigger_lepton_pt_flavor.py`. Weighted by `finalWeight` when the branch exists, else 1.0/event. The turn-ons should land exactly on the offline cuts in [objects.py](../src/vcb/processors/objects.py) — 26 GeV for muons (IsoMu24), 32 GeV for 2024 electrons (Ele30). This step also **asserts** that no written event has `TriggerLeptonFlav == PAD_VAL`, i.e. that the `trigger_lepton` cut is doing its job; a non-zero count exits `tests/test_run.py` non-zero |

## The jet tagger round-trip check

`diagnostics/check_jet_tagger_roundtrip.py` answers one question: **did the skim
keep each jet's tagger scores attached to the right jet?** For every output
event it finds the same event in the source NanoAOD by `(run, luminosityBlock,
event)`, matches each saved jet slot to an input jet by eta/phi — which JECs
leave untouched, so the match is exact — and compares
every tagger discriminant the skimmer saves against the input value — the four
charge-tagger heads (`ak4JetParT{Pos,Neg,Zero}vsAll`, `ak4JetParTPosvsNeg`), the
five UnifiedParT scores (`ak4JetbtagUParTAK4{B,CvB,CvL,CvNotB,QvG}`), the five
ParticleNet scores (`ak4JetbtagPNet{B,CvB,CvL,CvNotB,QvG}`) and
`ak4JetbtagRobustParTAK4B`, plus the two Qk jet charges
(`ak4JetQkCharge05_`, `ak4JetQkCharge10_` — the trailing underscore separates
the name from the slot index, since these are the only saved fields whose name
ends in a digit). `COMPARED_FIELDS` in the script and
`skim_vars["Jet"]` in the skimmer are meant to stay in step: a score that is
written but not round-tripped is one nothing would catch being attached to the
wrong jet.

The Qk charges are a special case worth knowing about. The fork writes them to
a separate `JetQk` flat table built from `slimmedJetsPuppi` — the *unfiltered*
collection — while `Jet` comes from `finalJetsPuppi` (`pt > 15`). So
`nJetQk >= nJet`, with equality in only ~16 % of events, and `JetQk` carries no
kinematics to match on. Both the skimmer
([`objects.attach_jet_charge`](../src/vcb/processors/objects.py)) and this check
take the first `nJet` entries, which is right because the CMSSW chain preserves
order end to end. The round-trip therefore verifies the *plumbing* — that a
charge survived JEC, selection, cleaning and slot padding still on its own jet —
but does not independently re-prove the prefix itself, since both sides assume
it. That was validated separately against `Jet_PflavCharge`: sign agreement is
0.6081 ± 0.0018 on events where `nJet == nJetQk` (alignment exact by
construction) and 0.6074 ± 0.0008 where the prefix is assumed, a 0.4 σ
difference, while deliberately shifted controls sit at ~0.47.

Note the sentinels: `-999` (no constituent above the 0.95 GeV cut), `-998`
(zero jet pT) and `-997` (neutral jet, ~21 % of jets) are the producer's, not
`PAD_VAL`. Mask on `> -900` before averaging.

Input jets that never reach the output are classified, not ignored. The skimmer
drops a jet for exactly five reasons — it sits within `dR <= 0.4` of the trigger
lepton used for cleaning, it fails corrected `pT > 15 GeV` or `|eta| < 4.7`, it
fails the Run-3 AK4 PUPPI Tight jet ID, or it fell past the 10 saved slots — so
anything left over lands in `UNEXPLAINED` and fails the check.

The jet ID is re-transcribed inside the script (`_passes_jet_id`) rather than
imported from `objects.ak4_jet_id`, on purpose: the check exists to re-derive
the skimmer's selection from the NanoAOD, so importing the thing under test
would make it circular. The two transcriptions agreeing is what drives both
`UNEXPLAINED` and `saved nJets != jets passing the cuts` to zero over all
208 780 events of the fixture.

The corrected pT is not stored for dropped jets, so by default the script
re-applies the same JEC/JER the skimmer used. Those corrections are
deterministic, and the script asserts that they reproduce every saved
`ak4JetPt` bit for bit; that also lets it cross-check the saved `nJets` against
the jets that actually pass the selection. `--no-jec` skips the recompute (~28 s
→ ~12 s on the test fixture) at the cost of leaving the pT cut assumed rather
than verified.

```bash
# the test fixture
micromamba run -n ttbar python diagnostics/check_jet_tagger_roundtrip.py

# a real Condor batch — pass the whole input directory, since one job skims 5 files
micromamba run -n ttbar python diagnostics/check_jet_tagger_roundtrip.py \
  --output-file "$INPUT/processed-nano/<tag>/roots/batch_000.root" \
  --input-file  "$INPUT/batch_000" \
  --report      batch_000-roundtrip.txt
```

`--input-file` takes any number of files or a directory; every input that fed
the output must be listed, and the script errors out if two of them repeat a
`(run, luminosityBlock, event)` key — which is exactly the "merged copy left
inside a `batch_*` dir" hazard described in
[condor/README.md](../condor/README.md).

On the frozen 2024 fixture all 5,651,004 comparisons (17 fields × 332,412 saved
jets) are identical, and all 125,465 dropped input jets are accounted for
(59,639 lepton-cleaned, 52,337 below the pT cut, 2,206 out of eta range, 10,523
failing the jet ID, 760 truncated past 10 slots). Going from 8 slots to 10 is
what took the truncation count from 5,297 to 760.
