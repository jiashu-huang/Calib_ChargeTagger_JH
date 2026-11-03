# Event truth labels

The ttbar processor writes two separate labels. MC sample names select the
processing path and normalization; they do not determine either truth label.
No new event cut or reconstruction-matching requirement is applied.

| Branch | ROOT type | Meaning |
| --- | --- | --- |
| `GenWDecay` | `Int_t` | `0`: TT2Q; `1`: TTCB; `-1`: unknown or outside these W modes |
| `GenWDecayValid` | `Bool_t` | W-decay label is usable |
| `GenNExtraBQuarks` | `Int_t` | Exact additional b plus anti-b quark count; `-1` means unknown |
| `GenNExtraBQuarksValid` | `Bool_t` | Extra-quark count is usable |
| `GenNExtraBQuarksStatus` | `Int_t` | Count status, defined below |
| `GenTruthLabelVersion` | `Int_t` | Definition and sidecar schema version, currently `1` |

TT2Q comprises W -> ud, us, cd, cs and charge conjugates; charm is included.
TTCB comprises W -> cb and its charge conjugate. W -> ub is outside these two
categories. The processor requires one hadronic and one leptonic W from the
two hard-process top decays; tau counts as leptonic. Missing or ambiguous
topology does not become TT2Q. The existing six `GenWto*` flags remain available.

Both W categories receive the extra-quark label when it is known. A TTCB event
with extra radiation stays TTCB. The two validity flags are independent, and
neither depends on the four `Gen*JetIdx` reconstruction assignments.

## Extra-quark definition and input requirement

Count outgoing last-copy b and anti-b lines before hadronization, without pT,
eta or jet requirements. Follow same-sign b copies back to their first copy.
Exclude the primary hard-process b lines directly from the top decays and
from their W decays. A new first-copy b starts a new line, including when a
removed gluon makes its stored mother another b. Radiation such as
top -> Wb(g -> bb) therefore contributes two extra quarks. Incoming beam and
initiator entries, B hadrons and repeated shower copies are not extra quarks.
This is a Pythia8 record convention, not an accepted extra-b-jet count.

The implementation requires two resolved hard-process tops and one primary b
line per top. Broken references, cycles, missing copy endpoints, multiple
endpoints for one line or unresolved top decays give an unknown count.
Several mother references are allowed when every same-sign copy path resolves
to the same first-copy quark. This handles status-73 combinations in the 2024
Pythia record without counting earlier copies again. Different resolved roots
remain ambiguous. Incoming recoiler copies are excluded as incoming entries.

**Ordinary NanoAOD is insufficient for the unrestricted count.** In the
CMSSW_CHARGE conversion, `finalGenParticles` retains pre-hadronization shower
partons above 15 GeV, plus other selected particles. It does not retain every
soft b line. The standard MiniAOD `prunedGenParticles` selection explicitly
keeps all b quarks. The TTBB native `GenTruth` files retain that collection and
its mother references. The reader accepts MiniAOD itself as the same source.
These rules can be inspected in the installed CMSSW
`PhysicsTools/NanoAOD/python/genparticles_cff.py` and
`PhysicsTools/PatAlgos/python/slimming/prunedGenParticles_cfi.py`.

The default NanoAOD-only run writes `GenNExtraBQuarks=-1`, validity false and
status 1. It still computes the W label. It never substitutes the number of
retained b entries, tagged jets, B hadrons or a dataset-name assumption for the
complete quark count. Signal and inclusive samples also need their original
MiniAOD or retained complete truth to obtain usable counts.

| Count status | Meaning |
| --- | --- |
| 0 | Valid count, including zero |
| 1 | Complete generator record not supplied |
| 2 | Invalid mother reference or ancestry cycle |
| 3 | Ambiguous or incomplete copy chain |
| 4 | Unresolved primary top decay |
| 5 | Unsupported outgoing generator status |

## Preparing and using counts

In a CMSSW runtime, build a small label file for each corresponding NanoAOD and
native truth input. This reads existing files; it does not rerun reconstruction.
Use a new output directory. Repeat `--pair` to build one manifest for several
input files. Each pair must cover exactly the same events with unique identities
within the pair. MiniAOD and NanoAOD may differ in event order: the builder aligns
them within that pair and writes labels in NanoAOD entry order. Duplicate or
missing identities are errors. The builder also checks that every retained NanoAOD generator particle appears
in order in the native record, with matching PDG ID, status, copy/hard-process
flags and pt/eta/phi within NanoAOD's 8-bit mantissa precision. This rejects
unrelated MC with reused event numbers. It allows particles removed by NanoAOD
pruning, including soft b quarks. Missing generator branches or a content
mismatch abort the pair before a label file is written. Keep the original
conversion provenance: this content check cannot distinguish native records
that differ only in information absent from NanoAOD.

```bash
python3 condor/scripts/build_truth_labels.py \
  --pair /path/sample_NanoAOD.root /path/sample_GenTruth.root \
  --output-dir /path/truth-labels
```

Then run the processor in the `ttbar` environment:

```bash
micromamba run -n ttbar python -m vcb.run \
  --year 2024 --files /path/sample_NanoAOD.root \
  --files-name TTBB-TTtoLNu2Q \
  --truth-label-manifest /path/truth-labels/manifest.json \
  --root-only --outdir outputs/labelled-ttbb
```

Use the intended dataset normalization label; an unregistered TTBB name still
has the processor's existing cross-section fallback. This change does not
establish TTBB normalization or inclusive/dedicated sample stitching.

`condor/submit_batches.py` accepts the same `--truth-label-manifest` option,
forwards it to each worker, and records the manifest path and checksum in
`campaign.json`. Workers require that exact checksum before loading labels;
editing or replacing the manifest after campaign creation aborts the affected
job. The checksum is checked against the same bytes that are parsed, avoiding
a separate check/read race. Local runs can request the same check with
`--truth-label-manifest-sha256 <digest>`. The manifest must cover all input files
in that campaign.

The manifest binds each label file to the NanoAOD UUID and records its checksum,
source paths, entry count, definition hash and count/status distributions. The
processor checks the UUID, checksum, entry range and every `(run, lumi, event)`
triple before attaching labels. Label arrays are decoded from the bytes whose
checksum was verified, so replacing a file during loading cannot substitute
unverified counts. A missing source in an explicitly supplied
manifest, reordered events or changed label file is an error. It does not join
independent MC files using event numbers alone. Kinematic passes use the same
truth labels for each source event, even when reconstructed selections change.

These are truth targets, not network input features. Consumers must apply each
label's own validity mask. Existing skims need reprocessing to acquire the new
branches. C1 still needs per-source coverage and multiplicity audits before
these labels are admitted to a training dataset.

The [B0 input profile](b0-input-profile.md) adds a common central-jet selection,
feature masks and source-entry metadata. It preserves both truth definitions,
independent classification masks and the direct-W lepton flavor. The builder's
within-file alignment handles the observed event-order differences in the
2024 TTCB and inclusive TT2Q pilot files; retained-particle checks remain required.

## Validation on BRUX, 2026-10-27

All 267 unit tests and the repository lint checks pass. The full integration
fixture processes 208,780 input events and writes 59,713 events with 747
branches. The 741 pre-existing branches are unchanged, and the jet-tagger
round-trip check passes. Every selected signal event has `GenWDecay=1`,
including 38,154 events without all four reconstruction matches. Without a
complete-truth sidecar, their extra-b counts correctly remain unknown.

The paired 2024 TTBB pilot has 10,000 entries. Native truth gives 9,450 events
with two extra quarks, 526 with four and 23 with six. One event remains unknown:
`(run, lumi, event) = (1, 59492, 29983698)`. Its same-sign copy paths lead to
different first-copy quarks, so the counter does not choose an origin. These
are unweighted pilot counts, not production-wide rates or accepted b-jet counts.
The first implementation unnecessarily rejected status-73 records with several
references to one physical line; the audited implementation resolves those
paths and includes a regression test for that case.

Processing the complete pilot in five chunks writes 2,709 selected events.
All have a valid TT2Q label, and every saved count and status matches its native
truth entry exactly. Their extra-quark counts are 2,566 with two, 138 with four
and five with six. The ambiguous native event does not pass the skim selection.

The validation record is [event-truth-labels-validation.json](event-truth-labels-validation.json).
No production campaign or network training was launched by this change.

## Integrity review on BRUX, 2026-10-28

The review added generator-content checks when pairing inputs, enforced the
manifest checksum recorded by Condor, and made sidecar decoding use the exact
bytes already verified. The two label definitions and version remain unchanged.

All 278 unit tests (plus 22 subtests) and lint pass. The full 208,780-event
fixture writes the same 59,713 events: every value in all 747 branches matches
the prior output. Schema and first-event baselines are unchanged. The jet-tagger
round-trip passes; its only report difference is the absolute fixture path used
by the isolated checkout.

The retained-particle check passes on all 10,000 native TTBB pilot events.
The rebuilt count sidecar is byte-for-byte identical to the previous sidecar.
The processor accepts the pinned manifest and writes 2,709 events with the same
native counts. A deliberate particle-content mismatch with unchanged event
numbers fails before any labels are written. An incorrect manifest checksum
fails before processing. A regression test also replaces a sidecar between
verification and decoding: only the verified counts may be returned.

The machine-readable record is
[event-truth-labels-review-validation.json](event-truth-labels-review-validation.json).
The review was originally performed in an isolated copy because the restricted
runtime could not query the scheduler. On 2026-10-28, an unrestricted BRUX queue
query returned no jobs, and the reviewed patch was integrated into the live
checkout. All seven code/test hashes match the recorded validation. Fresh tests
again pass (278 tests plus 22 subtests), and lint passes. The remaining
TT2Q/TTCB native-coverage and normalization work is unchanged by this review.
See [B0 input preparation](b0-input-readiness-2026-10-28.md) for the requested
processor checkpoint and its remaining gates.
