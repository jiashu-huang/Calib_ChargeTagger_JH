# 2024 ttbar PDF and alpha-S weights: research and proposed treatment

Research completed on 13 September 2026 against processor commit `1e1b0d8`.
The information-preservation part of audit finding 6 was implemented on
27 October 2026; see [the implementation record](skim-realignment-2026-10-27.md).
The following research and fit prescription are retained as historical context.
The [fixture evidence](pdf-alphas-2024-evidence.json) records the numerical
checks and analysis-note hashes from the original research-only follow-up.

**Priority: P2**, reprioritized at the user's request for the immediate nominal
SPANet/ML-training workflow. The generated events already embody the central
PDF and alpha-S choices. Discarding their uncertainty weights changes neither
nominal features and truth labels nor nominal event selection and weights.
Ordinary nominal training can proceed without this fix. The missing weights
are needed for theory-uncertainty evaluation or training that explicitly uses
PDF/alpha-S variations. Preserve the source NanoAOD and its provenance so the
member weights and all-input normalization sums can be recovered later.

## What is missing

Historical status as of 13 September; the October implementation now retains
the members, metadata and all-input sums. Histogram reduction and fit choices
remain downstream. In particular, our measured TTBB pilot uses a **Hessian**
4FS set, unlike the replica example discussed in AN-25-214.

`vcbSkimmer.add_weights` saves `pdf_weights` and `np_pdf_weights` only for
HH dataset names. Both `TTtoLNuCB` and `TTtoLNu2Q` bypass that branch, even
with `--save-systematics`. The helper simply returns `LHEPdfWeight`.
The existing second-pass normalizer only creates nominal `finalWeight`;
it does not normalize PDF or other alternative weights.

The complete signal fixture has 208,780 events, each with 103 entries.
Its branch title identifies LHA IDs 325300–325402 and defines the entries
as `w_var / w_nominal`. Member 0 is exactly 1 in every event. According to
the [official set metadata](https://lhapdfsets.web.cern.ch/current/NNPDF31_nnlo_as_0118_mc_hessian_pdfas/NNPDF31_nnlo_as_0118_mc_hessian_pdfas.info),
the set is `NNPDF31_nnlo_as_0118_mc_hessian_pdfas`, with error type
`symmhessian+as`:

| Input index | Meaning |
| --- | --- |
| 0 | Central PDF, alpha-S = 0.118 |
| 1–100 | 100 symmetric Hessian directions, at alpha-S = 0.118 |
| 101 | Central PDF with alpha-S = 0.116 |
| 102 | Central PDF with alpha-S = 0.120 |

The `mc` in this set's name does not make its error members Monte Carlo
replicas. The background's exact input layout was not measured in this
follow-up; check its branch metadata before assigning the same mapping.

## Comparison with the supplied analysis notes

| Source | Stated treatment | Applicability and qualification |
| --- | --- | --- |
| [AN-25-214](/isilon/export/home/jhuan166/Vcb/References/AN-25-214.pdf), section 6, PDF page 58 (printed page 56) | Each ttbar Hessian direction is an individual nuisance, correlated across processes; alpha-S is separate. Replica RMS is described for its different 4FS ttbb set. | **This paragraph is blue. The same page explicitly says blue items are not yet implemented.** This is a proposed model, not a validated implementation precedent. The earlier audit overstated its status. The note also names a different NNPDF3.1 Hessian variant, so use our measured LHA IDs. |
| AN-25-214, PDF page 60 (printed page 58) | Scale and shower variations retain inclusive normalization while allowing shape and acceptance changes; the text explicitly compares this with the PDF treatment. | Supports retaining all-input member sums. It does not prescribe this processor's exact list of normalization-preserving factors, which includes nominal pileup. |
| [AN-25-050](/isilon/export/home/jhuan166/Vcb/References/AN-25-050.pdf), section 7.2, PDF page 45 (printed page 43) | Reweights t-channel and ttbar with 100 NNPDF3.1 members, calls them replicas, correlates PDFs across periods/processes, and treats alpha-S separately for ttbar. It caps each PDF variation at 5% per event to handle outliers. | A 2022–2023 analysis precedent, not a general 2024 cap or a determination of our error type. Its omission of alpha-S for the 4FS sample is an analysis choice; current PdmV guidance discusses estimating that uncertainty from 5FS. |

The relevant pages were read as text and rendered images, including the
blue status annotation. Neither note gives an explicit numerical alpha-S
prior interval in these paragraphs. AN-25-214 cites PDF4LHC15, which helps
identify the historical prescription but does not prove its implementation.

## Public recommendations

- [CMS Run-3 generator guidance](https://cms-pdmv.gitbook.io/project/mccontact/info-for-mc-production-for-run3-campaigns)
  identifies the positive NNPDF3.1 Hessian sets and CP5, and links the NNPDF
  positivity prescription. For 4FS without alpha-S members it describes
  estimating the relative uncertainty from 5FS.
- [CMS NanoAOD documentation](https://twiki.cern.ch/twiki/bin/view/CMSPublic/WorkBookNanoAOD#Weights)
  says the stored PDF set is selected from the configured preference list
  and that the branch title records the actual LHAPDF IDs.
- [CMS DAS generator exercise](https://fnallpc.github.io/generators/03-systematic_uncertainties/index.html#estimating-systematic-uncertainties)
  distinguishes Hessian and replica reductions and warns that a non-unit
  central weight can indicate a different nominal matrix-element PDF.
  Its example describes UL; the fixture metadata supplies the 2024 mapping.
- [LHAPDF uncertainty API](https://www.lhapdf.org/classLHAPDF_1_1PDFSet.html)
  selects the formula by error type and requires correctly ordered members.
- [PDF4LHC15](https://arxiv.org/pdf/1510.03865), section 6, equations 24–30,
  gives the symmetric-Hessian master formula and a separate alpha-S term
  with delta alpha-S = 0.0015. [PDF4LHC21](https://arxiv.org/html/2203.05506v2#S6.SS3)
  repeats the Hessian formula but uses delta alpha-S = 0.0010 for its own
  combination. Neither changes the actual 0.116/0.120 members of our set.

## Proposed implementation

1. Under `--save-systematics`, retain all original member ratios for supported
   ttbar samples, with central/member IDs, PDF-set name, error type, and
   alpha-S endpoints. Keep nominal-only production available for training.
   Verify metadata and lengths per file; a vector length alone cannot identify
   a PDF set. Unsupported or missing requested inputs must be reported clearly.
2. Accumulate each member's signed all-input normalization sum before reco
   selection. Use the same processed-event scope and normalization convention
   as nominal. Preserve zero and negative ratios; report them for validation.
   Do not apply a generic positivity cut or the AN-25-050 5% cap while saving.
3. Carry the member sums through the campaign output/merge path, including
   jobs with zero selected events. Reject incompatible member mappings when
   merging. Put the sums in persistent ROOT metadata as well as the batch
   pickle, so ROOT-only workflows do not lose the required denominators.
4. Build and normalize each member's templates before any PDF reduction.
   This can be done in the histogram/template stage; nominal `finalWeight`
   alone is insufficient. Retaining the existing HH complete-weight convention
   is an alternative storage design, but the saved ratios and weight units
   must be explicit, and ratios for zero-weight events must remain recoverable
   if lossless preservation is intended.
5. Use 100 independent Hessian nuisances plus one separate alpha-S nuisance
   as the proposed full model. Correlate a given direction across categories
   and signal/background samples with a verified common eigenvector basis.
   Do not identify different sets' members solely by array index. Keep PDF
   alpha-S separate from the existing ISR/FSR shower-scale nuisances.

For the current convention, let `u_e = genWeight_e * pileup_nominal_e`,
`s_e` be the nominal lepton efficiency factor, and `r_ei` the stored member
ratio. Nominal shower factors are one. With externally assigned `sigma * L`:

```text
D_i       = sum over all processed input events of u_e * r_ei
Y_i(bin)  = sigma * L * sum over selected events in bin of u_e * s_e * r_ei / D_i
```

This retains shape and acceptance changes while fixing inclusive normalization
in the processor's existing scheme. Normalizing after selection would erase
the acceptance effect. An analysis retaining inclusive theory-rate variations
needs a different documented convention and must avoid duplicating its cross-
section uncertainty. This proposal follows the Vcb note's shape/acceptance
choice; it is not a universal normalization rule for all measurements.

For symmetric Hessian members, at the **histogram-bin level**:

```text
Delta_i(bin) = Y_i(bin) - Y_0(bin), i = 1,...,100
Y_i,up/down = Y_0 +/- Delta_i
delta_PDF(bin) = sqrt(sum_i Delta_i(bin)^2)
Cov(bin_a, bin_b) = sum_i Delta_i(bin_a) * Delta_i(bin_b)
```

There is no `1/sqrt(100)` factor. A per-event RMS followed by histogramming
loses the signed correlations and is not an equivalent reduction. The full
directions preserve cancellations between processes/categories; a single
per-bin envelope does not preserve that covariance for a fit.

For alpha-S, preserve both endpoints and make the chosen prior explicit.
Under linear error propagation, a symmetric template displacement is:

```text
delta_alphaS(bin; d) = (d / 0.002) * (Y_102(bin) - Y_101(bin)) / 2
```

Thus PDF4LHC15's `d=0.0015` gives a factor 0.75, while PDF4LHC21's `d=0.0010`
gives 0.5 relative to the stored endpoint half-difference. These are alternative
prior conventions, not extra nuisances. The unread TOP/PDF guidance should
settle the intended CMS treatment for this analysis before fixing that prior.
Saving the unmodified endpoints can proceed independently. Validate endpoint
asymmetry/nonlinearity before using a linear rescaling in the final fit.

These are event-weight alternatives: reconstructed kinematics, event membership
and fixed SPANet predictions can be reused. The histogram contents change when
the event weights change. No 103 full skimmer passes or separate model training
are needed for this reweighting prescription.

## Fixture checks and the 5% cap

The probe joins the current nominal skim back to NanoAOD using the exact
`(run, luminosityBlock, event)` key. All 59,537 output events match uniquely.
The normalization and numerator formulas above were evaluated for all members.
These results cover one signal fixture and its inclusive skim selection,
without SPANet or final-fit cuts:

| Check | Result |
| --- | ---: |
| Nonfinite member entries | 0 |
| Zero / negative member entries, including alpha-S | 79 / 121 |
| Input events with a negative nominal generator weight | 855 |
| PDF member entries outside [0.95, 1.05] | 27,380 in 2,377 input events |
| Same check among selected events | 4,835 entries in 472 events |
| PDF uncertainty on the normalized selected yield | 0.08159% |
| Same PDF calculation after a 5% per-event cap | 0.06642% |
| Alpha-S endpoint yield changes (0.116 / 0.120) | +0.07792% / -0.04334% |

The cap changes this diagnostic uncertainty by about 19% relative. This does
not determine the final Vcb uncertainty or certify the outlier weights; it
shows why the cap needs a dedicated study rather than automatic adoption.
Distinguish signed NLO event weights from physical PDF-observable positivity.
The [NNPDF positivity note](https://nnpdf.mi.infn.it/wp-content/uploads/2019/03/NNPDFfits_Positivity_PhysicalCrossSections_v2.pdf)
discusses replica predictions of physical observables; its median/quantile
prescription is not a license to discard signed NLO events or treat Hessian
directions as a replica sample. PdmV also mentions removing zero weights in
median/uncertainty calculations. Preserve the original data and clarify any
application of that instruction to this Hessian sample instead of silently
dropping events or directions.

`Runs/LHEPdfSumw` has 103 entries for each of five run records. Its title
defines a generator-weighted sum divided by `genEventSumw`, so reconstruct a
generator-only total with `sum_runs(genEventSumw * LHEPdfSumw_i)`, not an
unweighted sum of the ratios. Those totals do not include pileup and cannot
replace `D_i` in the current convention. They cover the whole file, which
also differs from a partial-chunk run. The event-derived and Runs-derived
generator sums agree here within 8.91e-6 relative; serialized event weights
have reduced precision, so bitwise equality is not expected.

## Remaining sources and implementation checks

Unauthenticated checks returned **HTTP 401** for
[CMS TopSystematics, PDF](https://twiki.cern.ch/twiki/bin/viewauth/CMS/TopSystematics#PDF)
and [CMS HowToPDF](https://twiki.cern.ch/twiki/bin/viewauth/CMS/HowToPDF).
Copies would help confirm the alpha-S interval, precise fit construction and
any TOP-specific outlier guidance. The
[event-weight guide](https://twiki.cern.ch/twiki/bin/view/CMS/ScaleAndPDFUncertaintiesFromEventWeights)
timed out; it was not observed to return 401. Public sources and the provided
notes are sufficient to establish the information-preservation fix.

When implementing, validate signed/zero weights, missing and mismatched member
metadata, all-input totals across chunks, empty selected outputs, and ROOT
merging. Check that the full Hessian template covariance matches the stored
members and that nominal branches and fixed SPANet predictions are unchanged.
Audit all production samples' PDF identities before defining correlations.
