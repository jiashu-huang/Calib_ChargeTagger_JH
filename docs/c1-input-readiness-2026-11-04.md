# C1 input readiness: b-jet truth and common processing

Decision record: `c1-bjet-truth-20261104-v1`. B0 output schema: **2**.

The user settled the b-jet label choice on November 4: save total reconstructed
and generator b-jet counts from `Jet_hadronFlavour == 5` and
`GenJet_hadronFlavour == 5`, and use the reco jet's hadron flavour for its
individual b label. This extends the existing W-decay and exact extra-quark
labels. It does not add a model classification head.

## Definitions fixed for this production

| Quantity | Definition |
| --- | --- |
| W decay | Existing independent TT2Q/TTCB label. TTCB with extra radiation remains TTCB. |
| Extra b quarks | Existing complete-generator outgoing-line count, excluding primary top/W b lines; exact integer and independent validity. |
| Reco b jets | `RecoNBJets`: corrected, ID-selected and lepton-cleaned B0 jets with pT > 25 GeV and abs(eta) < 2.4, counted before the ten-jet limit. |
| Gen b jets | `GenNBJets`: all AK4 generator jets with pT > 25 GeV and abs(eta) < 2.4, counted before the 25 saved slots. No detector ID or cleaning. |
| Individual reco jet | `B0JetIsB0..9`, equivalent to valid `ak4JetHadronFlavour == 5`; `B0JetIsBValid0..9` masks padding and unknowns. |
| Reconstruction | Existing four distinct jet assignments, greedy strict DeltaR < 0.4; unordered W pair, including b daughters. |

Both jet counts include **all origins**: top, W and radiation. Two b hadrons in
one jet count once. Flavours 0 and 4 are valid non-b labels. Unsupported or
missing flavour is unknown; count unknowns are `-1` with validity=false.
None of these labels enters the observable feature allowlist.

Generator acceptance follows the existing C0 25 GeV diagnostic definition.
It is not AN-25-214's separate 20 GeV additional-heavy-flavour prescription.
Additional-b-jet origin categories, inclusive/dedicated yield partition and DPS
treatment remain later analysis decisions. A total b-jet count does not resolve
those choices. C1 audits the agreed total jet counts and original labels; it
does not claim a completed additional-b-jet origin classification.

The hadron-flavour decision supersedes quark-cone matching as the proposed
*per-jet b-flavour definition*. The four-role reconstruction matcher remains.

## Certified inputs

No CMSSW_CHARGE rerun or sidecar rebuild is required. NanoAOD already contains
the jet hadron-flavour branches. The existing sidecars still supply the
unrestricted extra-quark count, for which NanoAOD loses some soft quark lines.

The completed native-truth campaign is on BRUX at
`/isilon/export/home/jhuan166/Vcb/Calib_ChargeTagger_JH/outputs/c1-truth-20261103`.

| Source | Certified files | Input events |
| --- | ---: | ---: |
| TT2Q | 11,014 | 484,298,177 |
| TTCB | 465 | 19,823,340 |
| TTBB | 2,258 | 44,323,128 |

These are separate MC populations, not a combined physics prediction.

## Bounded validation

Full NanoAOD files from all three sources passed schema-2 processing with
nominal kinematics, registered weight variations and certified truth.

| Source | Input events | Selected | Fully matched | Hadronic top matched |
| --- | ---: | ---: | ---: | ---: |
| TT2Q | 27,269 | 4,050 | 1,595 | 1,926 |
| TTCB | 33,580 | 4,703 | 1,705 | 2,063 |
| TTBB | 22,176 | 4,055 | 1,438 | 1,794 |

All selected pilot events have valid reco/gen b counts. One selected TTBB event
has unknown extra-quark truth; its b-jet labels remain valid. TT2Q/TTCB outputs
have 1,373 columns and TTBB has 1,371 before `finalWeight`; their PDF member
counts account for the difference.

Compared with the independent schema-1 references, only `B0SchemaVersion`
changes, and 24 truth columns are added. All 49 normalization fields are
identical. The twelve muon component alternatives retain the established
16-float64-epsilon tolerance for multiplication order; other existing columns
agree exactly. The calibration integration fixture's three tracked baselines
are unchanged.

Independent checks read original NanoAOD flavours, replay the corrected reco
selection before truncation, count the full accepted GenJet collection, and
verify matching and feature masks. Synthetic tests cover b jets beyond both
output limits, merged b hadrons, acceptance edges, unknowns, padding, empty
selections and truth-feature separation.

Full logs and outputs are in this checkout's
`outputs/c1-bjet-validation-20261104/`. The
[machine-readable record](c1-input-readiness-2026-11-04-validation.json) pins
the evidence. The common B0 schema SHA-256 is
`417966e8868f7d7e060b554fa3900d89e511c1ffc89c9cc4205dee1674277d54`.

## Full-production checkpoint

The [production helper](ttbb-b0-production.md) now accepts
`--sample TT2Q`, `TTCB` or `TTBB`; TTBB remains its default. Local inputs are
checked against certified size, modification time and event/UUID identity.
EOS inputs retain size and Adler-32 checks. Source normalization and PDF
layouts remain distinct. Every source must pass a new frozen Condor pilot.

Workers write additive feature, truth, matching and truncation audits.
Finalization writes `input-audit.json` and `input-audit.txt` beside the matching
report, using the full selected population. Finalizers request 12 GB for the
larger TT2Q inventory; workers use one CPU and 4 GB.

`condor/scripts/c1_input_readiness.py` closes C1 only after all three source
finalizers pass, full input coverage matches the truth certificate, reports
remain intact, and code and common schemas agree. It reports actual support
of exact extra-quark multiplicities. Missing sources or failed jobs leave C1
open. Sources remain separate; the audit does not combine physics yields.

**Production submitted: 2026-11-04, 17:39 UTC.** Frozen processor commit
`0fc83d74807c89d18e0f63df3a0cddbf9ea6cbdf` passed 474 unit tests, 22 subtests,
lint and the unchanged calibration regression. All three new Condor pilots
passed 149 campaign checks each, plus normalization rerun and matching-report
checks. Their clusters were TT2Q `7651228`, TTCB `7651226` and TTBB `7651227`.

One master DAG, cluster **7651230**, covers 13,737 inputs and 548,444,645 raw
events with a shared maximum of 40 active processing/finalization jobs. It
interleaves sources and runs the overall C1 audit after all three finalizers.
The campaign root is
`/isilon/export/home/jhuan166/Vcb/Calib_ChargeTagger_JH/outputs/c1-b0-20261104`.
The [submission record](c1-b0-production-2026-11-04.json) pins source snapshots,
pilot gates, workflow hashes and queue identifiers.

Pilot scaling estimates about 204 GB of skim ROOTs, plus metadata and logs;
the shared filesystem had about 18 TB available at submission. This is an
estimate, not a quota measurement or a production size result.

Full-population processing and its final audit are **not yet complete** at
submission. Protected lineage splits, HDF5 assembly and train-only normalization
are C2 work; training has not started.

**November 6 recovery:** TTCB and TTBB finalized successfully. Four TT2Q files
failed because the pre-selection MET check encountered rejected events with
infinite raw MET. The [recovery record](c1-met-recovery-2026-11-06.md) documents
the selection-preserving fix, complete-file validation and separate processor
provenance. C1 remains open until TT2Q finalization and the combined audit pass.
