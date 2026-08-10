# Jet veto map — findings and deferred work

**Status:** investigation complete, no code changed. Written 2026-08-05.

The jet-veto-map implementation was reviewed against the pinned CAT payload in
`~/cat-snapshot` and against JERC's own recommendations. **The current
implementation is correct and needs no fix.** What follows is (a) the evidence
that settles the event-vs-jet-level question that `PROVENANCE.md` and
[docs/processor.md](docs/processor.md#4-jet-veto-map) both record as open, (b)
the measured cost of the veto, and (c) a deferred proposal plus the exact steps
for the study JERC asks for before that cost can be reduced.

---

## 1. Verdict

`get_jetveto_event` ([src/boostedhh/processors/corrections.py:649](src/boostedhh/processors/corrections.py#L649))
rejects the **event** when any selected jet lands in a vetoed region. That is
JERC's recommendation, not — as the docs currently claim — a stricter reading
inherited from `boostedhh`.

From the JERC recommendations page, Jet Veto Maps section
(<https://cms-jerc.web.cern.ch/Recommendations/>, CERN SSO):

> These maps should be applied similarly both on Data and MC, to keep the
> phase-spaces equal.
>
> As a general guideline for Run3, **we recommend rejecting events** (read the
> reason here) that contain jets within the vetoed regions to prevent the
> introduction of spurious MET in the event. We encourage you to include a
> detailed description in your AN outlining how this vetoing procedure is
> implemented.
>
> *Reminder: Jet veto maps are mandatory for Run 3 analyses.*

The reason, from M. Voutilainen on cms-talk
([140517/4](https://cms-talk.web.cern.ch/t/using-jet-map-veto-in-analysis-without-jets-or-met/140517/4)):
the vetoed regions hold dead ECAL crystals, bad tracker pixels or strips and
noisy HCAL cells, and there

> you cannot assume that JEC, JER SF, isolation efficiencies, reconstruction
> efficiencies, trigger efficiencies or any other analysis variable is correct
> within quoted uncertainties, and no estimates are given to how much you would
> need to increase your systematics to have data and MC agree within
> uncertainties.

That argument bites harder on a calibration than on a search: an unquantifiable
reconstruction-efficiency distortion inside the veto regions is a systematic on
the very scale factor being extracted, and JERC declines to size it.

**Both of JERC's relaxation options are gated on a condition we fail.** From
their reply to the ~15 % event-loss inquiry (Ilias, Ravindra, Fikri, Matteo for
JERC/JME):

> If your analysis does not rely on MET, and you can demonstrate that JES
> effects are small compared to other systematics […] then it may be reasonable
> to relax the veto recommendation. Options for doing so include:
> - Moving from an event-level veto to a jet-level veto (**recommended only if
>   MET and jet multiplicity are not used**).
> - Restricting your preselected jets to better match your analysis phase space
>   (e.g., pT > 40 GeV & |η| < 2.5 instead of pT > 15 GeV) […]

This analysis uses MET (the ν p_z solution on the semileptonic leg) *and* jet
multiplicity (the χ² jet-to-parton assignment). Option A is ruled out
explicitly. Option B is gated on the same MET condition and cannot be taken
without the studies in §5.

A second, independent argument against Option A specific to this repo: MET is
rebuilt as PUPPI Type-1 summing over **every** jet in the event
([vcbSkimmer.py:411](src/vcb/processors/vcbSkimmer.py#L411)), so dropping a jet
from the analysis collection would leave its mismeasured energy in MET
regardless. Object-level veto would pay the full price JERC's rationale warns
about while additionally punching a hole in the χ² fit.

### Payload checks (all pass)

| Check | Result |
|---|---|
| Correction `Summer24Prompt24_RunBCDEFGHI_V1` | present; also verified for all four 2022/2023 entries in the year map |
| Key `jetvetomap` | matches the payload's own "recommended map for analyses" |
| `evaluate("jetvetomap", eta, phi)` | matches declared inputs `(type, eta, phi)` |
| Applied to data and MC alike | yes, no `isData` branch |
| `> 0` test | map values are exactly `{0, 100}` |
| η/φ clipping | harmless: node `flow` is `0.0`, and no vetoed cell exists above \|η\| = 4.45, so clipping to 4.7 cannot fabricate a veto |
| jsonpog copy vs CAT pin | **byte-identical** decompressed, sha256 `61a5b389…873a2` |

Geometry: 82 η × 72 φ bins, 164 non-zero cells, 140 of them at |η| < 2.5;
3.68 % of the η–φ area inside |η| < 2.5, 2.28 % overall. Strict subset of
`jetvetomap_hotandcold` (259 = hot 62 + cold 197), with **zero** overlap with
`bpix` (72) or `fpix` (8). `jetvetomap_all` (260) = hotandcold ∪ bpix ∪ fpix
exactly. `jetvetomap_eep` exists only in `2022_Summer22EE` — confirming it was
a 2022 artifact.

---

## 2. Measured cost

All numbers from `tests/data/test-input.root` (TTtoLNuCB, 208 780 events),
reproducing `good_ak4jets` + `ak4_jet_id`. **Caveat:** raw NanoAOD pT (no
JEC/JER) and all leptons above 26/32 GeV as a proxy for the resolved trigger
lepton, so each figure carries a few tenths of a percent of slop. Unweighted —
redo with `finalWeight` before quoting anywhere external.

```
A repo as-is (pt>15, |eta|<4.7, tightID, dR>0.4 lep)   vetoed jets  2.95%   events lost 16.81%
B same, without jet ID                                 vetoed jets  2.85%   events lost 17.40%
C repo + EMfrac<0.9                                    vetoed jets  2.95%   events lost 16.73%
D JERC-style (+EMfrac<0.9, PF-muon dR<0.2 removal)     vetoed jets  2.90%   events lost 15.74%
E kinematics only, no ID no cleaning                   vetoed jets  2.89%   events lost 19.19%
```

Map-key choice, same selection: `jetvetomap` 16.81 %, `jetvetomap_hotandcold`
26.39 %, `jetvetomap_all` 26.51 %. Using `jetvetomap` is worth ~10 percentage
points of acceptance over the alternatives, confirming the `PROVENANCE.md`
warning not to substitute `_all`.

Event loss attributable to each jet-pT slice: 2.35 pp from 15–20 GeV jets,
3.34 pp from 20–30, 4.58 pp from 30–50, 7.56 pp above 50.

### The loss is pure multiplicity multiplication

Voutilainen's footnote — *"3.3 % assumes single objects, but with multi-prong
final states this inefficiency can indeed multiply and in that case it may be
warranted to revisit the event vs object veto"* — describes us exactly:

```
per-jet veto probability p     =  2.954%
mean selected jet multiplicity =  6.177
independent-jet prediction     = 16.75%     1 - sum_k N(k)*(1-p)^k / N
measured event loss            = 16.81%
```

Agreement to 0.06 pp, holding bin by bin in multiplicity:

```
njet= 3  N= 12414  lost= 9.15%   [1-(1-p)^3  =  8.60%]
njet= 5  N= 40314  lost=14.55%   [1-(1-p)^5  = 13.92%]
njet= 6  N= 41124  lost=16.71%   [1-(1-p)^6  = 16.46%]
njet= 8  N= 22548  lost=21.00%   [1-(1-p)^8  = 21.33%]
njet=10  N=  7337  lost=24.23%   [1-(1-p)^10 = 25.91%]
```

So the 16.8 % is not a hot spot or a correlation with the tt̄ topology — it is
3 % per jet raised to the power of a six-jet final state. **92 % of vetoed
events contain exactly one vetoed jet** (7.7 % two, 0.4 % three): in the
overwhelming majority of the loss we discard five good jets to remove one bad
one.

### Option B, priced

Event loss when the veto's preselected jets are restricted (JERC's example is
the pT > 40, |η| < 2.5 row):

```
preselection for the veto              <njet>  event loss   recovered
  pT > 15 GeV, |eta| < 4.7  (current)    6.18      16.81%     0.00 pp
  pT > 15 GeV, |eta| < 2.5               4.75      15.85%     0.97 pp
  pT > 20 GeV, |eta| < 2.5               4.14      13.96%     2.85 pp
  pT > 25 GeV, |eta| < 2.5               3.69      12.56%     4.26 pp
  pT > 30 GeV, |eta| < 2.5               3.30      11.29%     5.52 pp
  pT > 40 GeV, |eta| < 2.5               2.64       9.10%     7.72 pp
  pT > 30 GeV, |eta| < 4.7               3.83      11.81%     5.00 pp
  pT > 40 GeV, |eta| < 4.7               2.97       9.47%     7.34 pp
```

A realistic phase space for this analysis — charm and charge tagging need
tracks, so |η| < 2.5, and `PROVENANCE.md` cites the pT > 20, |η| < 2.5 taggable
jet definition from CMS-DP-2024-024 — sits in the **2.9–5.5 pp** range. JERC's
own example recovers 7.7 pp, nearly half the loss.

The MET gate is graded rather than binary, which is what makes Option B worth
studying: a vetoed 18 GeV jet contaminates MET far less than a vetoed 80 GeV
one, and the pT-slice breakdown above shows 5.7 pp of the loss comes from jets
below 30 GeV.

---

## 3. Deferred proposal — save the decision, don't bake in the cut

[vcbSkimmer.py:643](src/vcb/processors/vcbSkimmer.py#L643) applies the veto as a
hard cut at the loosest preselection, i.e. the most expensive row of the table
above, and writes nothing that would let anyone revisit it. Everywhere else the
skimmer defers analysis choices on purpose (no b-tag cut — "deferred to analysis
time"); the veto is the one place it commits.

**Proposal.** Save two scalars per event instead of only cutting:

- `vetoJetMaxPtEta2p5` — max pT among vetoed jets with |η| < 2.5, `-1` if none
- `vetoJetMaxPtEta4p7` — same for |η| < 4.7, `-1` if none

Every row of the Option B table then becomes a one-line cut at analysis time.
Current behaviour is reproduced exactly by `vetoJetMaxPtEta4p7 < 15`. Scalars
rather than per-jet flags because a vetoed jet can fall outside the 10 saved jet
slots; the max-pT scalar handles that correctly.

Keep applying the event cut as now — this is not a physics change, it is
preserving the option.

**Cost of not doing it:** the 16.8 % is already baked into `prod_20260726` and
`prod_lnu2q_20260728`. Any relaxation, or even the study in §5 done properly on
production statistics, currently needs a re-skim of all 465 files. If a re-skim
happens for any other reason, fold this in then.

---

## 4. Still open

1. **Candidate-jet definition.** The standard JERC recipe adds
   `chEmEF + neEmEF < 0.9` and removal of jets overlapping a PF muon within
   ΔR < 0.2. Neither is applied; the repo's cleaning is ΔR > 0.4 against the
   single resolved trigger lepton only, so a jet overlapping any other muon can
   still veto the event. Together worth 1.1 pp (row A → row D). **Unconfirmed** —
   the wording lives behind the collapsed "Click for recommendations …" panel on
   the JERC page, which has not been read. Read it before acting.
2. **[cms-talk 57850/3](https://cms-talk.web.cern.ch/t/jet-veto-maps-for-run3/57850/3)**
   (rverma), cited as reference [4] in the JERC reply as the detailed
   discussion. Not read.
3. **Payload sourcing.** [corrections.py:49](src/boostedhh/processors/corrections.py#L49)
   reads `jetvetomaps.json.gz` from jsonpog-integration — the only 2024
   correction still doing so, and from a tree
   [docs/2024-inputs.md:165](docs/2024-inputs.md#L165) already calls
   "untrustworthy for jets". Content is identical today (hashed), so this is a
   supply-chain concern, not a physics one: bundle the 313 kB payload alongside
   the others in `src/boostedhh/corrections/`, or route it through `CAT_BASE`
   the way `add_pileup_weight` does.
4. **Doc corrections.** Three places record this as unresolved and lean the
   wrong way: [docs/processor.md:291](docs/processor.md#L291) ("the stricter
   reading, inherited from `boostedhh`"),
   [docs/2024-inputs.md:195](docs/2024-inputs.md#L195) ("Open question"), and the
   `PROVENANCE.md` open item in `~/cat-snapshot`. Also stale line references in
   `docs/processor.md`: `get_jetveto_event` is at
   [corrections.py:649](src/boostedhh/processors/corrections.py#L649)–673, not
   573–599; the year map at 664–670, not 588–594; `get_pog_json` at 58–73.
5. **JERC offered a meeting slot** to discuss this in detail. For a calibration
   analysis eating a 16.8 % hit, worth taking.

Minor: the `pt > 15` inside `get_jetveto_event` duplicates `good_ak4jets`;
`CorrectionSet.from_file` is re-read every chunk; JER smearing makes the
15 GeV threshold crossing seed-dependent at the sub-permille level.

---

## 5. The JERC study — exact steps

JERC specifies two studies, in order. Study 2 runs **only** if study 1 passes.
Adapted to a calibration measurement, where "expected limit or pseudo-significance"
has no direct analogue.

> 1. **Kinematic comparison:** Compare distributions of key analysis observables
>    between (a) events passing the JVM requirement and (b) events failing it.
>    If the distributions agree within uncertainties, this indicates that
>    relaxing the JVM may be acceptable. Otherwise, relaxing the JVM would
>    introduce biased events.
> 2. **Sensitivity study:** Only after confirming the distributions in 1) are
>    consistent, compare the expected sensitivity between (a) applying the full
>    veto and (b) omitting the JVM entirely.

### Step 0 — get both samples without a re-skim

The skim discards failing events, so they cannot be recovered from
`prod_20260726`. Two options:

- **Preferred:** implement §3, re-skim, split on `vetoJetMaxPtEta4p7`.
- **Cheap first pass:** a new `diagnostics/compare_jetveto_split.py` reading
  NanoAOD directly and reproducing the object selection, in the style of
  `diagnostics/check_jet_tagger_roundtrip.py`. Working starting point:
  `vetostudy.py` / `phasespace.py` from the session that produced this document.
  Good enough to decide whether the full study is worth a re-skim.

Either way the split is on the **same** event sample with the **same** selection
otherwise applied — trigger, MET filters, `trigger_lepton` — so the only difference
between (a) and (b) is the veto.

### Step 1 — kinematic comparison

Observables, weighted by `finalWeight` (not raw counts):

| Group | Branches |
|---|---|
| Jets | `ak4JetPt` / `Eta` / `Phi` (all 10 slots), `nJets`, `ht` |
| MET | `METPt`, `METPhi` — **the load-bearing pair**, since MET is what JERC's rationale is about |
| Lepton | trigger-lepton pT, η, flavor fraction |
| Taggers | `ak4JetbtagUParTAK4B`, `btagUParTAK4CvB`, `btagUParTAK4CvL`, `ParTPosvsNeg`, `ParTPosvsAll`, `ParTNegvsAll` — **the calibration observables themselves; if anything must agree, it is these.** UParT rather than PNet: it is the only 2024-calibrated tagger and the same network family as the charge-tagger heads. The PNet equivalents are saved too and worth overlaying as a cross-check |
| Truth | `FlavSplit`, `HadronFlavour` composition, to check the veto is not flavor-selective |
| χ² fit | reconstructed W and top masses, ν p_z discriminant — add once the fit exists |

For each: overlay (a) and (b) normalized to unit area, plot the ratio with
statistical errors, and quote a χ²/ndf. "Agree within uncertainties" is JERC's
bar; with 16.8 % of events in the failing sample the statistical power is
adequate, so a real disagreement will show.

Two things to watch that a generic version of this study would miss:

- **The tagger distributions matter more than the kinematics.** A shift in
  `ParTPosvsNeg` or `btagPNetCvL` between (a) and (b) is a direct bias on the
  extracted scale factor, whereas a mild HT shift is not.
- **Check flavor composition explicitly.** The concern is not only that the
  vetoed events differ kinematically, but that they differ in the b/c/light mix
  the calibration is measuring.

Run on MC now; repeat on data once `Collisions24` is pinned and data processing
starts, since data/MC disagreement inside the veto regions is the actual worry.

### Step 2 — sensitivity, only if step 1 passes

For a calibration the analogue of "expected limit" is the **total uncertainty on
the extracted charm-tagger and charge-tagger scale factors**. Extract the SFs
under each configuration and compare stat, syst, and total:

- (a) full veto as now — pT > 15, |η| < 4.7
- (b) Option B at the analysis phase space — pT > 20 or 30, |η| < 2.5
- (c) no veto at all — the bound, for reference

Note the adaptation: JERC frames (b) as "omitting the JVM entirely", but the
decision we actually face is (a) vs Option B, not (a) vs nothing. Configuration
(c) is worth computing anyway as the scale of the effect.

Decision rule, following JERC: if the SF central values agree and the total
uncertainty barely improves, keep the full veto — the 16.8 % is buying
robustness cheaply. If the uncertainty improves materially **and** step 1 showed
no bias, take Option B, document it in the AN, and carry the difference between
(a) and (b) as a systematic.

### Step 3 — regardless of outcome

The JERC page requires it:

> it is imperative to assess this impact rigorously by creating jet eta-phi
> maps, before and after applying the veto maps […] We encourage you to include
> a detailed description in your AN outlining how this vetoing procedure is
> implemented.

So: produce `finalWeight`-weighted jet η–φ occupancy maps before and after the
veto, confirm the vetoed cells are actually depopulated, and write the procedure
up for the AN. Compare against JERC's own published map,
<https://cms-jerc.web.cern.ch/figures/jetVetoMap/jetvetomap_Summer24Prompt24_2024BCDEFGHI.png>.

---

## References

- JERC recommendations, Jet Veto Maps — <https://cms-jerc.web.cern.ch/Recommendations/> (CERN SSO)
- Voutilainen, on why the regions are untrustworthy and the multi-prong footnote — [cms-talk 140517/4](https://cms-talk.web.cern.ch/t/using-jet-map-veto-in-analysis-without-jets-or-met/140517/4)
- JERC/JME reply on ~15 % event loss from the 2024 maps — cms-talk, "Inquiry regarding significant event loss (~15%) from 2024 Jet Veto Maps"
- Detailed discussion, cited as [4] in that reply, **unread** — [cms-talk 57850/3](https://cms-talk.web.cern.ch/t/jet-veto-maps-for-run3/57850/3)
- Run-3 map announcement — [cms-talk 18444](https://cms-talk.web.cern.ch/t/jet-veto-maps-for-run3-data/18444)
- 2024 map figure — <https://cms-jerc.web.cern.ch/figures/jetVetoMap/jetvetomap_Summer24Prompt24_2024BCDEFGHI.png>
- Payload provenance and pin policy — `~/cat-snapshot/PROVENANCE.md`
