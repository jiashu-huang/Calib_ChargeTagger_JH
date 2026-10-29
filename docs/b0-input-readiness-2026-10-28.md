# B0 processor checkpoint: validated input preparation

Recorded 2026-10-28. The requested checkpoint is a processor that can prepare
the first native SPANet joint reconstruction/classification baseline (B0).
It is not the full analysis release. Development and validation stay on BRUX;
Oscar is reserved for training. The processor is ready under the explicit
`--input-profile b0` mode. Its release tag is **`b0-processor-20261028-v1`** on
branch `codex/b0-input-preparation`. The [profile guide](b0-input-profile.md)
defines the frozen processor feature schema, masks and source identity.
Full-population C1 validation and the C2 training dataset remain pending.

## Jet cap and leptonic W decays

The user selected **ten jets** on October 28. The processor already saves ten
slots, so retain that capacity and matching coverage. B0 now applies central-jet
acceptance before the cap and records uncapped multiplicity and overflow.
Twelve was a draft
engineering choice, not a SPANet/CMS requirement; comparing against twelve is
no longer a freeze prerequisite. C1 still measures truncation and matching under
the common selection using NanoAOD. A ten-slot skim cannot recover a central
jet discarded before the B0 acceptance cuts or measure what lies beyond the cap.

Retain selected events where a W decays through a tau to an electron or muon.
The existing `GenWLeptonFlavor` branch already stores the absolute PDG ID of the
**direct** leptonic W daughter: `11`, `13`, or `15`; `0` means unavailable truth.
It is `UInt_t`, not a string. A subsequent tau-to-electron/muon decay stays `15`.
`TriggerLeptonFlav` separately describes the observed trigger lepton. Do not
add a duplicate truth branch or expose the generator flavor as a model input.

The existing 59,713-event signal-fixture output contains 23,971 electron-mode,
32,406 muon-mode and 3,336 tau-mode W decays. These are skim counts, not an
efficiency measurement or the full-matched training population. AN-25-214,
section 3.2 (printed p. 12; PDF p. 14), also includes tau-fed electron/muon events.

## Reconstruction truth matching

Retain the existing deterministic greedy one-to-one matcher with strict
`DeltaR < 0.4`, applied to the retained candidate jets. Both objects are removed
after choosing the closest feasible pair. Record the parton order, jet ordering
and tie rule. All four distinct matched jets are required for assignment
supervision; valid classification targets remain usable in unmatched events.

There is direct CMS precedent: CMSSW `CMSSW_15_1_0_patch4`
[TtSemiLepJetPartonMatch_cfi.py](https://github.com/cms-sw/cmssw/blob/CMSSW_15_1_0_patch4/TopQuarkAnalysis/TopTools/python/TtSemiLepJetPartonMatch_cfi.py)
selects `totalMinDist`. Its
[implementation](https://github.com/cms-sw/cmssw/blob/CMSSW_15_1_0_patch4/TopQuarkAnalysis/TopTools/src/JetPartonMatching.cc)
is nearest-pair-first greedy matching, despite the potentially misleading name.
`minSumDist` is a separate global-sum algorithm. The CMS example has different
distance-cut and jet-count settings; it does not establish our 0.4 cut or cap.
Neither local AN specifies this reconstruction truth matcher. Their ME/PS
matching and ghost-hadron matching address different problems.

The historical signal-fixture comparison in [processor.md](processor.md#jetparton-assignment)
favored retaining greedy: 41 of 59,575 events differed from the global method,
with a 0.037 percentage-point gain in full matching for the latter. This is
not a TTBB validation. The new TTBB check below covers the current saved slots;
C1 must still audit the common selection across sources. The native
SPANet prediction decoder is another separate algorithm; it does not define
generator truth.

The 10,000-event TTBB pilot in the default calibration profile has 2,709
selected events. All saved assignments
agree exactly with the production matcher and an independent edge-sorting
greedy reference. There are no invalid indices, duplicate assigned jets, or
matches outside strict DeltaR < 0.4. Greedy fully matches **1,144 events
(42.2296%)**; global maximum-cardinality, then minimum-distance assignment
matches **1,146 (42.3034%)**. Only two events differ, both recovered by the
global method, for a gain of **0.0738 percentage points**. Retain greedy as
directed. This is a bounded pilot, not production-wide efficiency or full C1.
The reproducible check is
[validate_ttbb_matching.py](../diagnostics/validate_ttbb_matching.py).

## TTBB normalization and overlap

The primary analysis reference is
[AN-25-214 v5](../../References/AN-25-214.pdf), Table 2 and sections 2.2.2–2.2.5
(printed pp. 8–11; PDF pp. 10–13). Table 2 lists **15.84 pb** for the 2024
semileptonic TTBB sample, with the mean `genWeight` as its source. It lists
**2.896 pb** separately for semileptonic TTBB double-parton scattering (DPS).
The AN uses an NLO four-flavor TTBB calculation for the additional-b component.
Its main ttbar flavor-category rates float independently in the fit; the
tabulated rates are pre-fit normalizations. It assigns a 50% normalization
uncertainty to the separate DPS contribution (printed pp. 55–59).
Its abbreviated dataset name differs from our exact primary-dataset name;
15.84 pb must not be installed solely from a name resemblance.

Our exact source is:

```
/TTBB-TTtoLNu2Q_TuneCP5_13p6TeV_powheg-pythia8/RunIII2024Summer24MiniAODv6-150X_mcRun3_2024_realistic_v2-v2/MINIAODSIM
```

The completed conversion catalog records all 44,323,128 input events and
`sumw = 709686641.4894006`. Therefore its sample-wide signed mean is
**16.01165517**. Following the user's instruction, use **16.01165517 pb**
(16.0117 pb rounded) provisionally under the AN's mean-weight prescription.
It is 1.0837% above the AN value and is a generator normalization, not a new
measurement. It is now registered as `TTBB-TTtoLNu2Q` in the processor.
This effective semileptonic rate includes the decay convention; do not apply
another W branching fraction. The rate alone does not remove source overlap.
The accompanying [evidence record](b0-input-readiness-2026-10-28.json) separates
the full-catalog mean from the single-file generator metadata checks.

On one original MiniAOD, `GenXSecAnalyzer` returns about 36.52 pb and a filter
efficiency of one; the LHE run header also contains 36.52171015 pb (`IDWTUP=-4`).
The same source's `GenRunInfoProduct` reports 15.55938923 pb. These metadata
quantities are not interchangeable with the sample-wide effective semileptonic
rate. The analyzer output alone does not settle the decay-normalization
convention. Keep these checks alongside the adopted provisional mean-weight
normalization for later physics review.

The AN combines samples using **additional accepted generator b jets**, with
ghost-associated B hadrons, `pT > 20 GeV`, `|eta| < 2.4`, and top/W decay
origins treated by the CMS heavy-flavor categorizer. Its prescription is:

- take the additional-b-jet component from dedicated TTBB;
- take the additional-c and light-flavor components from inclusive ttbar;
- account separately for the DPS contribution described in the note.

Apply complementary source selections when forming physical yields. An
inclusive TT2Q extra-b event and a dedicated TTBB event can be distinct MC
events representing overlapping phase space. Adding their complete yields
double counts that region. Conversely, TTBB events with no accepted extra b jet
do not automatically belong in the dedicated contribution under this rule.

For a source with an approved effective cross section, the usual event weight
is `L * sigma_eff * genWeight / sumw_all_input`, times the event corrections and
the source/category selection. Keep the denominator before the category cut;
renormalizing each selected category to the entire source cross section would
inflate it. Specify whether branching/filter factors are already in `sigma_eff`
and never apply them twice.

CMS [HIG-19-011, section 7](https://arxiv.org/html/2407.10896v2#S7) uses the same
source-replacement principle, but takes its pre-fit flavor fractions from
inclusive ttbar and normalizes to the inclusive rate. Its Run-2 numbers do not
apply to 2024. This demonstrates why an overlap prescription alone does not
settle the normalization convention. AN-25-050 was also checked; it does not
supply a more applicable dedicated-TTBB stitching prescription.

Your exact extra-b-quark count has no acceptance cut and remains label 2.
It must not substitute for the CMS b-jet category: two quarks may merge into one
jet or leave acceptance. Preserve separate CMS-category metadata at the AN's
20 GeV threshold for the provisionally adopted prescription. The design's existing
25 GeV diagnostic and reconstructed-jet threshold are different definitions.
TTCB events with extra radiation retain their TTCB label. Source-balanced B0
training can use both background samples; its sampling fractions are not
physical yields. Keep evaluation per source until the combination is fixed.

## Implementation and validation

The three reviewed truth-label integrity fixes were integrated into the live
processor after an unrestricted BRUX queue query returned no jobs. All seven
changed code/test hashes match the prior validated patch. Integration validation:
278 tests plus 22 subtests and repository lint pass. The earlier full-fixture
and TTBB-pilot checks apply to the same code hashes; see the
[review validation](event-truth-labels-review-validation.json).

After registering the approved TTBB rate, a fresh 10,000-input-event pilot
produced the same 2,709 selected events and 741 branches. Only the eleven
luminosity/cross-section-normalized weight branches changed, by the expected
factor `16.011655167690346 * 109820 = 1758399.9705157538`; all other branches,
including truth labels, assignments and `weight_noxsec`, and the `Norm` tree
were unchanged. This factor is the processor's pre-merge numerator;
physical yields still require the full-source sum-of-weights denominator.
The signal integration run also passed: 59,713 events, 747 branches, all three
tracked reports unchanged, and 5,435,189 jet-tagger comparisons with no differences.
All 19 focused generator-truth tests passed. Decision-specific reports are in
`outputs/b0-decisions-20261028/`, with hashes in the evidence record.

The October 28 entry in the
[October logbook](https://docs.google.com/document/d/1NwUY5wwjr5CxWxebIAsU3Z-z0Ks8qU-ugVzSVnjCENQ)
records these decisions and the TTBB pilot, quotes AN-25-214 v5 section 2.2.4,
identifies the 15.84 pb table row, and shows the full-catalog division yielding
16.01165517 pb. The appended text and preservation of the existing logbook were
verified by reading the document back.

The subsequent B0 implementation has passed 289 unit tests plus 22 subtests,
repository lint, the full calibration integration regression, and source-to-skim
checks on each of the three intended sources. Its ten slots are shared by
features and matching. It saves 18 jet and 15 event observables with validity
masks, source UUID/entry identity, both truth axes, independent classification
masks and one full-match mask for both assignment branches. The user-approved
Qk decoding maps `-997` to valid zero; raw values remain in the skim and
`-999`/`-998` remain invalid. Neither missing features nor failed matching
rejects an otherwise selected event.

| Source | Input events | B0 selected | Fully matched | Valid classification, unmatched |
| --- | ---: | ---: | ---: | ---: |
| TTtoLNuCB | 33,580 | 4,703 | 1,705 | 2,998 |
| TTtoLNu2Q | 27,269 | 4,050 | 1,595 | 2,455 |
| TTBB | 10,000 | 1,748 | 613 | 1,135 |

Every selected event in these bounded pilots has both classification labels.
The independent greedy replay agrees exactly. The global comparison recovers
one additional TTBB full match and none in the other two sources. There are
no duplicate assigned jets or matches outside the cone. The three raw-tagger
checks compare 840,242 values with no differences or unexplained dropped jets.
These B0 counts differ from the calibration pilot above because the event and
jet acceptance differ; they do not measure full-sample efficiencies.

The truth builder now aligns unique event identities within each declared
MiniAOD/NanoAOD file pair, checks complete coverage and retained generator
content, and writes labels in NanoAOD order. Signal and inclusive files required
27 and 35 reordered entries; TTBB required none. Five ambiguous native
extra-quark counts remain unknown (two signal, two inclusive, one TTBB).
None of those events survives these B0 pilots. The truth definition is unchanged.

Exact validation results, code hashes and artifact checksums are in
[the release validation record](b0-processor-validation-2026-10-28.json).
The live calibration schema and first-event baseline remain identical to the
pre-B0 snapshot. Its tagger report differs only in the resolved fixture path
inside the isolated checkout; the portable tracked report is preserved.

The remaining gates are the full-population C1 audit and C2 construction of
the SPANet dataset: count-bin support, protected MiniAOD-lineage splits,
train-only normalization, and the explicit HDF5 input/target mapping. The
CMS additional-b-jet source partition and DPS treatment remain physics-yield
work. This checkpoint did not submit a production campaign or train a model.

## Questions for Greg on October 29

1. The user has approved the sample mean-weight normalization provisionally.
   For the later physics release, confirm this convention and whether to follow
   the AN's independently floating ttbar flavor-category rates.
2. Should that first validation include the separate 2024 semileptonic DPS
   sample (the AN lists 2.896 pb), or is it acceptable to defer DPS until the
   full analysis release while B0 is established on TT2Q, TTCB and TTBB?

Take these questions to Greg with the AN table and the full-sample weight sum.
