# B0 processor input profile

`--input-profile b0` prepares 2024 MC for the first native SPANet joint
reconstruction/classification baseline. The default `calibration` profile keeps
the existing skim selection and columns. Both profiles use the same corrections,
trigger lepton, event-quality filters, jet ID, cleaning and event weights.

## Selection and matching

After correction, ID and lepton cleaning, B0 selects jets with strict
`pT > 25 GeV` and `abs(eta) < 2.4`. It orders them by corrected pT, breaking exact
ties with their input NanoAOD index, and retains at most **ten**. Acceptance is
applied before the cap. Events need at least four accepted jets. There is no
b-tag or charge-validity event cut.

`nJets`, `ht` and the overflow summaries use the full accepted collection before
the cap. The existing `ak4Jet*` columns contain the ten retained slots, and
`ak4JetNanoIdx{slot}` identifies each original NanoAOD jet. The deterministic
nearest-pair greedy matcher uses these same slots and strict `DeltaR < 0.4`.
All four assignments must be distinct and real for reconstruction supervision.

`B0AssignmentMask` also requires a valid resolved W-decay topology. Use that
same mask for both native SPANet assignment branches. Keep events that fail it
for classification: `GenWDecayValid` and `GenNExtraBQuarksValid` are independent
classification masks. Exact quark counts remain unbinned in the skim.

`GenWLeptonFlavor` remains the direct W-daughter absolute PDG ID: 11, 13 or 15,
with 0 for unavailable truth. Selected tau-fed electron/muon events are retained;
their direct-W flag stays 15. This flag is metadata, not an inference input.

## Observable features and masks

The companion `outfiles/<tag>.kinematics.json` records `input_profile`, the full
`b0_schema`, its deterministic SHA-256, and the truth-manifest path/checksum.
Use its explicit feature allowlist. Do not feed every numeric ROOT branch to
the network: generator labels, source identifiers and weights are excluded.

| B0 observable | Raw source or definition |
| --- | --- |
| `log1p_pt`, `log1p_mass`, `eta`, `sin_phi`, `cos_phi` | Corrected retained-jet four-vector |
| `PNetB` | `btagPNetB` |
| `ParTPosvsNeg` | `ParTPosvsNeg` |
| `UParTB`, `UParTCvL`, `UParTCvB` | Corresponding `btagUParTAK4*` discriminators |
| `ParTPositive`, `ParTNegative`, `ParTZero` | `ParTPosvsAll`, `ParTNegvsAll`, `ParTZerovsAll` |
| `Qk05`, `Qk10` | Decoded `QkCharge05`, `QkCharge10` |
| Lepton-charge products | Charge times each Qk, and charge times `(ParTPositive - ParTNegative)` |

Each of the 18 jet observables has `B0Jet_<feature>_<slot>` and
`B0Jet_<feature>_valid_<slot>` columns. `B0JetMask<slot>` distinguishes a real
jet from padding. Missing measurements do not remove jets. Tag scores are usable
when finite and within `[0,1]`; absent, negative or nonfinite scores are masked.

There are 15 event observables, each with `B0Event_<feature>` and
`B0Event_<feature>_valid`: trigger-lepton log-pT, eta, sin/cos-phi, charge and
electron/muon indicators; MET log-pT and sin/cos-phi; full accepted multiplicity
and HT; and overflow count, summed pT and maximum valid UParT B score. The
overflow maximum is masked when there is no valid score beyond the ten slots.

Features are **not standardized by this processor**. Invalid entries contain
zero with validity=false. Fit normalization using valid training entries only,
then restore invalid entries to zero after standardization. A physical zero
with validity=true participates normally in that normalization.

## Jet-charge sentinel decision

The user approved the following interpretation on 2026-10-28 after reviewing
the [CMSSW_CHARGE producer](https://github.com/jose8af/cmssw/blob/6e413adba949c83733e56c81811b629c5a16fa0b/PhysicsTools/NanoAOD/plugins/JetChargeTableProducer.cc):

- `-997`: the weighted charge numerator is numerically zero; decode to 0 with
  validity=true for B0. It does not identify the initiating quark's charge.
- `-999`: no constituent passes the producer's pT requirement; validity=false.
- `-998`: nonpositive jet-pT denominator; validity=false.
- Padding, absent measurements and nonfinite values are also invalid.

The producer uses constituents above 0.95 GeV and computes
`sum(q_i * pT_i**kappa) / pT_jet**kappa` for kappa 0.5 and 1.0. Its zero test
is applied to the numerator, with absolute tolerance `1e-10`, after checking
the constituent count and denominator. The raw `ak4JetQkCharge*` columns retain
their original values. No event is rejected by this decoding.

## Truth and source identity

Prepare complete extra-b counts with the [truth-label builder](event-truth-labels.md).
Original MiniAOD and its NanoAOD can have different event order. The builder
requires a unique one-to-one `(run, lumi, event)` mapping **within each declared
file pair**, complete event coverage, and matching retained generator content.
It writes labels in NanoAOD entry order and records the number of reordered
entries. Duplicate identities, missing events or mismatched particle content
abort the pair. It never joins independent files using event numbers alone.

Every B0 row stores the original NanoAOD entry in `B0SourceEntry` (`uint64`)
and its UUID in `B0SourceUUID0..3` (four `uint32` words, most significant first).
Keep these with the input-to-MiniAOD conversion records and truth manifest.
Dataset construction must use the original MiniAOD lineage for protected splits.
`B0SchemaVersion` is currently 1. The two physical truth definitions and sidecar
schema remain version 1; event alignment changes their transport, not their meaning.

Without a complete-truth manifest, the extra-quark label stays unknown with
validity=false. This is useful for diagnostics and reconstruction preparation,
but does not provide count supervision. Neither a missing count nor a failed
full match is converted into a background label.

## Run and validate

```bash
micromamba run -n ttbar python -m vcb.run \
  --year 2024 --input-profile b0 \
  --files /path/sample_NanoAOD.root --files-name TTBB-TTtoLNu2Q \
  --truth-label-manifest /path/truth-labels/manifest.json \
  --root-only --outdir outputs/b0-ttbb
```

Condor accepts and records the same `--input-profile b0` option. Local and
Condor runs pin the truth manifest checksum before loading it. The B0 jet-count
cut is applied after the all-input normalization totals are accumulated.
The inherited MC `Norm.nevents` field stores the signed sum of generator
weights despite its name; it is not the raw number of events.

For a one-file pilot, run [validate_b0_inputs.py](../diagnostics/validate_b0_inputs.py)
with `--nano`, `--skim`, `--metadata`, `--truth-manifest` and `--output`. It checks
source UUID/entry identities, selection, masks, zero-charge decoding, exact
sidecar counts and matching. Also run
[check_jet_tagger_roundtrip.py](../diagnostics/check_jet_tagger_roundtrip.py)
with `--input-profile b0` to check the raw taggers, jet indices, corrected pT,
accepted multiplicity and reasons for discarded input jets against NanoAOD.

The general campaign validator defaults to the calibration schema. For B0,
use its `--schema-baseline` option with an exact schema from a validated pilot
of the same source and weight mode; do not use the 747-branch calibration
baseline or accept arbitrary additional columns. The B0 diagnostic above
additionally checks the model features and truth/source mapping.

## Release validation, 2026-10-28

The three bounded, unweighted 2024 pilots use complete native generator truth:

| Source | Input events | B0 selected | Fully matched | Unmatched with classification labels |
| --- | ---: | ---: | ---: | ---: |
| TTtoLNuCB | 33,580 | 4,703 | 1,705 | 2,998 |
| TTtoLNu2Q | 27,269 | 4,050 | 1,595 | 2,455 |
| TTBB | 10,000 | 1,748 | 613 | 1,135 |

All selected events in these pilots have both valid classification labels.
There are 333 selected TTCB events and 294 selected inclusive TT2Q events with
extra b quarks; their W-decay labels remain TTCB and TT2Q respectively.
The native files contain five ambiguous extra-quark counts in total (two,
two and one respectively), all recorded as unknown; none survives B0 selection
in these pilots. This does not guarantee zero unknowns in the full samples.

The matcher agrees with an independent greedy implementation on every selected
event, with no duplicated assigned jet or match outside the cone. A global
maximum-cardinality, then minimum-distance comparison recovers one additional
TTBB full match and none in the other two pilots. Greedy remains the baseline.
The Qk zero sentinel is decoded in three selected inclusive-source jets and two
TTBB jets for each kappa. Raw tagger round trips have no differences and no
unexplained dropped jets. The default calibration regression retains 59,713
events and the same branch schema and first-event values. Unit validation
passes 289 tests plus 22 subtests; repository lint passes.

Exact file paths, checksums, schemas and reports are recorded in
[processor readiness](b0-input-readiness-2026-10-28.json). Pilot fractions are
diagnostics of these files, not estimates for the full training population.

This processor profile is not a completed training dataset. Full-population
coverage, multiplicity-bin support, lineage splits, normalization fitting and
the HDF5 writer remain dataset gates. The CMS additional-b-jet source partition
and DPS treatment remain separate physics-yield work; a quark count must not
be used as a substitute for that generator-jet category.
