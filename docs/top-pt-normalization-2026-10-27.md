# Top-pT normalization preservation — 27 October 2026

Weight prescription version 3 preserves the information needed to evaluate an
optional top-pT correction with consistent inclusive normalization. It changes
neither the nominal event weight nor event selection. This work is in the
isolated BRUX realignment copy; the live checkout and production are unchanged.

Previously, the skim saved four per-event top-pT factors but discarded their
contributions from rejected events. A mean computed on selected events cannot
recover the all-input denominator. Version 3 saves those sums and their joint
PU, shower, scale and PDF alternatives before reconstructed selection.

## Output contract

The existing four `topPtWeight_*` columns remain raw factors. No cross-section,
luminosity or lepton-efficiency factor is included in them. Their numerical
formulas, limits and combination are recorded in `WeightMetadata`; coefficient
changes cannot silently share this prescription.

`TopPtWeightValid` is true only when the generator record contains exactly one
hard-process, last-copy top and one antitop with finite, nonnegative pT.
Otherwise every factor is 1 and the flag is false. Such events remain in every
normalization sum; they are not removed by a generator-level cut.
The flag checks generator inputs; it does not certify sample applicability
or that the top pT lies inside an unclamped fit range.

The ROOT `Norm` tree and accumulator pickle carry:

| Field | Meaning |
| --- | --- |
| `n_input_events` | Literal number of input events, including rejected events |
| `n_top_pt_valid`, `n_top_pt_invalid` | Counts satisfying/failing the top-pair rule; their sum equals `n_input_events` |
| `np_topPtWeight_<model>` | Signed sum of `genWeight × nominal_PU × T` over all input events |
| `np_topPtWeight_<model>_pileup{Up,Down}` | Same sum with varied PU, under `--save-systematics` |
| `np_topPtWeight_<model>_{ISR,FSR}PartonShower{Up,Down}` | Same nominal-PU sum times the shower ratio, under `--save-systematics` |
| `np_topPtWeight_<model>_scale_weights` | Six-member vector of joint top-pT/LHE-scale sums; always saved for supported ttbar |
| `np_topPtWeight_<model>_pdf_weights` | Vector of joint top-pT/PDF-member sums, using the verified PDF layout, under `--save-systematics` |

Here `<model>` is `dataNLO`, `dataNNLO`, `NNLONLO` or `NNLONLO_13p6TeV`, and
T denotes that model's factor. Every sum excludes lepton efficiencies and
cross section × luminosity. Signed, zero and large generator ratios are
preserved. A nominal run adds eight sums and three counters; a systematic
run adds 36 sums/vectors and three counters. Empty selections retain all of
them. No additional joint sums are needed for lepton efficiency variations,
because those efficiencies do not enter the normalization denominator.

**Legacy naming:** `Norm/nevents`, the pickle's `nevents`, and the existing
normalization summary's `total_nevents` store the signed generator-weight sum
for MC. They are not literal event counts. Their values remain unchanged for
compatibility. Use `n_input_events` and the new summary's `total_input_events`
for event accounting in these version-3 ttbar outputs.

## Downstream use

Let D be the global `np_nominal` sum over every included batch, and D_T the
matching global `np_topPtWeight_<model>` sum. The existing nominal weight is
`finalWeight = weight / D`. If the analysis adopts T while preserving the
inclusive normalization, use:

```text
weight_with_T = weight × T / D_T
              = finalWeight × T × D / D_T
```

Multiplying only `finalWeight × T` also changes the inclusive normalization.
Normalizing T to its selected-event mean instead removes its effect on the
selected yield and is a different prescription.

The joint sums support consistent variations around that optional model:

| Numerator | Denominator |
| --- | --- |
| `weight × T` | D_T |
| `weight_muon_idUp × T`, or another lepton alternative | D_T |
| `weight_pileupUp × T` | Global `np_topPtWeight_<model>_pileupUp` |
| `weight_ISRPartonShowerUp × T` | Global `np_topPtWeight_<model>_ISRPartonShowerUp` |
| `scale_weights<i> × T` | Member i of the global joint scale sum |
| `weight × PDFWeight<i> × T` | Member i of the global joint PDF sum |

Sum denominators across the same input batches as the numerator. Never
redefine them after reconstructed selections. Signed sums may be negative or
zero; a zero denominator cannot be used for division and requires investigation.
The saved sums make this optional normalization available; they do not choose
the final analysis model or correlation scheme.

`normalize.py` still appends only nominal `finalWeight`. It exports the global
top-pT sums/counters in `metadata/normalization.json/global_top_pt_sums` and
the literal input count in `total_input_events`. Merge, normalization and the
campaign validator check the recorded prescription. The validator also checks
joint-sum completeness/shapes, finite values, unity fallback for invalid
selected pairs, all-input counts and agreement with pickle/summary totals.
Forced normalization preserves the full Norm and metadata trees.

## Sample scope and compatibility

Top-pT factors remain available for supported ttbar names, including
`TTBB-TTtoLNu2Q`. The former comment excluding ttbb as a matter of general CMS
policy was too strong: [CMS TOP-22-009, section 7.2](https://cds.cern.ch/record/2872305/files/CMS-TOP-22-009-arXiv.pdf?version=1)
applies a top-pT modeling treatment to its ttbar components, including its ttbb
signal, and excludes single top and ttV/ttH. This is a documented analysis
precedent at 13 TeV, not universal approval of a Summer24 prescription. The
stored 13.6 TeV extrapolation remains the one already transcribed from
AN-25-050; it is not newly applied to any sample here. The two `data*` fits
remain historical 13 TeV comparisons.

`WeightPrescriptionVersion=3` records whether top-pT information is enabled
for the sample. Removing all factor fields therefore fails validation rather
than appearing to disable the feature. Versions 1 and 2 remain readable as
separate campaigns. They cannot be mixed with version 3. Reprocessing from
NanoAOD is required to obtain rejected events' contributions; selected skims
alone cannot reconstruct the missing sums.

## Stored Run 3 factor

`topPtWeight_NNLONLO_13p6TeV` is the optional top-pT weight already stored by
the processor. For each valid generator top, let x be its pT in GeV, capped
at 2,000 GeV. The implementation evaluates

```text
f(x) = [0.103 exp(-0.0118 x) - 0.000134 x + 0.973]
       × [0.991 + 0.000075 x]
T    = sqrt(f(x_top) × f(x_antitop))
```

The first bracket is the stored 13 TeV NNLO/NLO model. The second is the
13-to-13.6 TeV extrapolation transcribed from AN-25-050. The 2,000 GeV cap
is an implementation choice, not a CMS recommendation. This factor changes
the relative contributions of different top-pT configurations if an analysis
adopts it. It is saved separately and is absent from nominal `weight` and
`finalWeight`. The new all-input sums allow its adoption with consistent
inclusive normalization, as described above.

## Validation and remaining limits

Measured results are recorded in
[the validation JSON](top-pt-normalization-2026-10-27-validation.json).
Tests cover signed/zero ratios, invalid/missing top pairs, finite-value and
shape failures, rejected-only output and incompatible prescriptions. Full
signal and TTBB source comparisons independently evaluate the formulas and
all-input sums from NanoAOD. The pipeline check includes actual merging,
normalization and forced rewriting.

| Check | Result |
| --- | --- |
| Unit suite and lint | 320 tests and 22 subtests passed; lint passed |
| Nominal signal integration | 208,780 input events; 59,712 selected; 809 columns; all 11 new normalization fields checked against input NanoAOD |
| Signal with systematics | Same input and selected events; 942 columns; all 39 new normalization fields checked against input NanoAOD |
| TTBB with systematics | 10,000 input events; 2,709 selected; 940 columns; all 39 new normalization fields checked against input NanoAOD |
| Jet-tagger round trip | 5,435,070 comparisons; PASS; existing report unchanged |
| TTBB production tools | 136 batch checks; 63 merged checks; 63 checks after forced normalization; all passed |
| Version-2 compatibility | Existing campaign passed all 23 validator checks; mixed-version merges remain rejected |

Selection, kinematics, truth labels and nominal event weights are bitwise
unchanged. Twelve existing muon-component alternatives differ only by
floating-point multiplication order in Coffea's `partial_weight`, which
iterates over a Python set. Their largest relative difference from the
previous run is below 6e-16. All twelve also agree with independent evaluation
of the pinned CMS muon payload. No muon prescription changed in this stage.

As a diagnostic, adopting the stored Run 3 factor with its all-input
normalization would change the selected weighted yield by -0.2324% in the
signal fixture and -0.2157% in the TTBB fixture. These are fixture-specific
relative effects, not a selected nominal correction. The TTBB check still
uses the existing sigma-times-luminosity placeholder of 1; it does not
establish a physical TTBB event yield.

This closes the missing top-pT normalization-information item in the
[readiness record](cms-readiness-2026-10-27.md). It does not settle the nominal
top-pT model, TTBB physical normalization or sample overlap. High-pT muon
treatment, guaranteed upstream jet-charge association and validation against
collision data remain open.
