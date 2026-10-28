# Skim information and selection realignment — 27 October 2026

This records the first implementation stage. The later
[CMS readiness record](cms-readiness-2026-10-27.md) is the current status;
validation counts here describe this stage only.

This change closes the information-preservation findings in the September
audit for the supported 2024 MC workflow. It was developed in an isolated
copy of the BRUX checkout, including its uncommitted truth-label additions.
The source snapshot is recorded in `snapshot-provenance.json`. Production
workers use the original checkout; no production campaign is launched here.
The existing editable Python installation still points to the original.
For commands in this isolated copy, use `PYTHONPATH="$PWD/src"` with the
`ttbar` environment; do not reinstall it over the shared environment.

## Decisions and output contract

- **Extra leptons:** retain events and record the veto for downstream use,
  as requested by the user. An isolated heavy-flavour decay lepton can fail
  this veto in a genuine signal event. The veto does not define generator
  signal/background labels and does not alter the skim cutflow.
- **Veto definition, version 1:** active corrected pT > 15 GeV and
  |track eta| < 2.4; electron `mvaIso_WP90`, or muon `tightId` with
  `pfRelIso04_all < 0.25`. Exclude the chosen trigger lepton by input index.
  No extra IP, ECAL-gap or jet-overlap cut is imposed on veto candidates.
  Exact counts precede truncation. Save the three highest-pT candidates per
  flavour with pt/eta/phi, charge, isolation, input lepton/jet indices and
  NanoAOD `genPartFlav`. Origin codes are flavour-specific and diagnostic only.
  Additional leptons below these thresholds are not retained by this record.
- **Electron trigger:** use bit 18 for the 2024 Ele30 trigger filter. Bit 1
  can also describe cross-trigger objects in the actual input branch title.
  This is the only intentional event-selection change in this update.
- **Unclustered MET:** save the input up/down vector differences relative
  to input nominal PUPPI MET, plus those differences added to rebuilt MET.
  Never substitute the old absolute NanoAOD varied MET for the rebuilt vector.
  Preserve both directions independently, even without weight systematics.
- **PDF/alpha-S:** under `--save-systematics`, save all original ratios as
  `PDFWeight{index}`, including signed and zero members. No clipping, per-event
  reduction, or multiplication by nominal event weights is applied to them.
  Nominal-only skims remain available. Every requested file's branch-title
  identity is checked before processing and every event's member length and
  finiteness are checked during processing. Missing/unverified inputs fail.
  The ttbar scale-weight gate also recognizes `TTBB-TTtoLNu2Q`, so its six
  pre-existing scale alternatives are retained rather than skipped by the name.

The actual local input layouts, checked against official LHAPDF `.info` files
under `/cvmfs/sft.cern.ch/lcg/external/lhapdfsets/current/`, are:

| Input | LHA IDs | Set | Members |
| --- | --- | --- | --- |
| Signal fixture | 325300–325402 | NNPDF31_nnlo_as_0118_mc_hessian_pdfas | Central, 100 symmetric Hessian directions, alpha-S 0.116/0.120 |
| TTBB pilot | 325500–325600 | NNPDF31_nnlo_as_0118_nf_4_mc_hessian | Central and 100 symmetric Hessian directions; no alpha-S endpoints |

The measured TTBB sample is **not** the replica example in AN-25-214. A
different file must identify its own layout; member counts alone are insufficient.
This change does not assign an alpha-S uncertainty to the 4FS sample or define
cross-sample eigenvector correlations.

## Normalization and merging

For member i, store `D_i = sum_all_input(genWeight * nominal_pileup * ratio_i)`.
The pickle retains `np_pdf_weights` and `pdf_layouts`; ROOT retains the vector
in `Norm/np_pdf_weights` and its interpretation in `PdfMetadata/layout_utf8`
(UTF-8 JSON bytes, compatible with the pinned uproot 4 writer).
An alternative normalized event weight is `weight * PDFWeight_i / global_D_i`.
Apply this normalization before histogram-level PDF reduction. Nominal
`finalWeight` alone does not normalize these alternatives.

Each chunk writes a normalization record alongside its temporary table,
including chunks with zero selected events. Each output ROOT carries only
the totals for its own chunks, so multiple output batches neither duplicate
nor omit the denominator. The table writer preserves empty and single-event
dimensions. Standard `hadd` concatenates the metadata and `Norm` rows.
The merge and normalization scripts reject incompatible PDF mappings; the
validator checks all rows and the member sums against the pickle totals.
Forced nominal re-normalization preserves PDF metadata.

## Validation

These results describe the first information-preservation iteration, before
the subsequent [weight realignment](weight-realignment-2026-10-27.md).

The [machine-readable record](skim-realignment-2026-10-27-validation.json)
contains the measured results and source-metadata hashes.

| Check | Result |
| --- | --- |
| Unit tests and lint | 278 tests and 22 subtests pass; lint passes. Three existing dependency deprecation warnings. |
| Complete signal fixture | 208,780 inputs; 59,712 selected, down from 59,713 solely because of the corrected trigger filter. All 747 old fields are bitwise unchanged on common events. |
| Extra-lepton record | 1,108 veto-failing signal events retained. Independent full-fixture checks reproduce every loose count, saved candidate index and decision. |
| MET and jet checks | All saved unclustered vectors reproduced from source; full jet-tagger round trip passes. |
| Signal systematics | 2,008 inputs, 520 outputs; all 103 member ratios match input exactly, and all-input sums agree. |
| TTBB systematics | Complete 10,000-event pilot, 2,709 outputs split across three ROOT files; all 101 ratios match exactly, with all-input sums agreeing within floating-point accumulation precision. |
| Empty selection | 2,008 inputs, zero selected; a typed ROOT with every PDF member and the full normalization sums is written. |
| Batch/merge/normalization | TTBB batch validator passes 49 checks. Actual hadd, nominal normalization and forced re-normalization retain the metadata; merged validation passes 20 checks before and after the forced rewrite. |

The nominal schema has 807 columns. Systematic signal output has 928 and the
measured TTBB output has 926; their PDF member counts account for the difference.
No systematic branch is added to the nominal event weight.

## Remaining work

The subsequent [weight realignment](weight-realignment-2026-10-27.md) closes
PU/LHE clipping, shower-label interpretation and missing lepton-SF failure handling.
This work does not close the entire CMS audit. Branching fractions, high-pT muons,
remaining closure/jet-ID questions and collision-data support remain open.
TTBB physical normalization and its overlap treatment with inclusive ttbar
remain unresolved. TTBB tests use the documented `weight_norm=1` fallback
and validate information flow, not a physical cross section.
The reference analysis's electron acceptance and final exactly-one-lepton
selection remain downstream analysis decisions. Full campaign PDF identities
and native truth coverage still need their dataset audit.
