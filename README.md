# Calib_ChargeTagger_JH

**Turn 2024 MC NanoAODs into smaller ROOT files for the |Vcb| analysis.**

This repo is a vendored version of 
[Clara Ramon Alvarez's processor](https://github.com/cramonal/Calib_ChargeTagger).

The `Calib_ChargeTagger_JH` processor corrects and selects objects, labels events, 
matches jets to top-decay quarks, and saves features and weights. 
It handles [CMSSW_CHARGE](https://github.com/jiashu-huang/cmssw-charge-setup) 
NanoAODs for **2024 TT2Q, TTCB and TTBB** samples.

For the |Vcb| analysis, we aim to build a “Grand Network” based on 
[SPANet](https://github.com/Alexanders101/SPANet), combining event classification
and semi-leptonic ttbar reconstruction. 
**B0** is the input-preparation mode for our first SPANet baseline. 
Dataset assembly and network training come later.

**Jump to:** [Run one file](#run-one-file) · [Outputs](#what-you-get) ·
[Matching counts and plots](#check-the-matching) · [Full TTBB production](#run-the-full-ttbb-sample)

## How it works

![B0 flow: CMSSW_CHARGE NanoAOD and complete generator truth enter corrections, selection, feature preparation and matching. ROOT skims retain incomplete matches and all-input normalization totals. Separate steps produce matching reports and normalized weights.](docs/images/readme-b0-flow.svg)

MiniAOD → NanoAOD conversion happens **before** this repository runs through CMSSW_CHARGE.
Separate **C1** jobs read MiniAOD generator truth and write the extra-b-quark
labels. Jet-flavour truth already comes from NanoAOD. See the
[detailed B0 flow](docs/b0-input-profile.md#processing-flow).

## Choose a mode

| You want to… | Use | Jet selection |
| --- | --- | --- |
| Prepare Grand Network inputs | `--input-profile b0` | Corrected pT > 25 GeV, \|η\| < 2.4; require ≥4 jets; save the leading 10 |
| Study tagger calibration | `--input-profile calibration` (default) | Analysis jets above 15 GeV; no minimum jet count; save up to 10 |

Both use the same object corrections, triggers and event-quality requirements.
B0 applies jet acceptance **before** the ten-jet limit and records overflow.
Neither mode requires a b-tag count or a fully matched event.

## Run one file

### Setup

Run commands from this repository's root. If `ttbar` is already installed,
skip environment creation.

```bash
micromamba create -f environment.yaml
micromamba run -n ttbar pip install -e ".[diagnostics,test]"
```

Use the bundled `boostedhh`; installing a separate `boostedhh` or `bbtautau`
would conflict with it. `PYTHONPATH` below selects this checkout when several
worktrees share the environment.

### Process a TTBB NanoAOD

Replace the two `/path/to/…` entries with your input and its matching
[C1 truth manifest](docs/event-truth-labels.md#preparing-and-using-counts).
Choose a fresh output directory.

```bash
PYTHONPATH="$PWD/src" micromamba run -n ttbar python -m vcb.run \
  --year 2024 --input-profile b0 \
  --files /path/to/TTBB_NanoAOD.root \
  --files-name TTBB-TTtoLNu2Q \
  --truth-label-manifest /path/to/truth-labels/manifest.json \
  --root-only --save-systematics \
  --chunksize 10000 --maxchunks 0 --batch-size 9999 \
  --naming-tag ttbb-check --outdir outputs/b0-ttbb-check
```

This processes the **whole file**, with nominal object kinematics and saved
weight variations. For a short check, use `--maxchunks 1`.

| Input sample | Required `--files-name` |
| --- | --- |
| Inclusive TT2Q | `TTtoLNu2Q` |
| TTCB signal | `TTtoLNuCB` |
| Dedicated TTBB | `TTBB-TTtoLNu2Q` |

The sample name selects normalization; it does **not** assign an event's truth
class. Without a truth manifest, the extra-b count is **unknown, not zero**.
See the [CLI reference](docs/cli.md) for all flags and systematic object passes.

## What you get

For the command above:

```text
outputs/b0-ttbb-check/
├── nano_skim_ttbb-check_batch_0.root   Selected events + normalization totals
└── outfiles/
    ├── ttbb-check.pkl                Cutflow + normalization totals
    └── ttbb-check.kinematics.json     Feature definitions + input provenance
```

The ROOT `Events` tree holds selected events. `Norm` holds totals from **all
input events**, including rejected ones. Weight/PDF metadata describe the saved
alternatives. `--root-only` keeps these outputs without retaining Parquet.

<details>
<summary><strong>How to read the truth labels and matching targets</strong></summary>

A **validity mask** is a yes/no flag: can this value or target be used?

| Saved information | Meaning |
| --- | --- |
| `GenWDecay` | `0` = TT2Q (non-b W daughters, including charm); `1` = TTCB (W → cb); `-1` = unknown/outside these modes |
| `GenNExtraBQuarks` | Exact extra b/anti-b **quark** count, not a jet count; `-1` = unknown |
| `RecoNBJets`, `GenNBJets` | Total reco/gen b-jet counts from `hadronFlavour == 5`, before output limits; pT > 25 GeV, \|η\| < 2.4 |
| `B0JetIsB0..9` | Whether each retained reco jet has b hadron flavour; use its `B0JetIsBValid` flag |
| `GenWLeptonFlavor` | Direct leptonic W daughter: `11` = e, `13` = μ, `15` = τ; `0` = unavailable |
| Four `Gen*JetIdx` fields | Jet slots for hadronic-top b, leptonic-top b and the two W daughters; `-1` = unmatched |
| `B0AssignmentMask` | All four roles matched to distinct jets **and** a valid W-decay topology |

The matcher is greedy with **ΔR < 0.4**. The W pair is unordered and allows
W → cb. A TTCB event with extra b quarks retains its TTCB label.
The two b-jet counts **include top, W and radiation jets**; they are not
additional-b-jet counts. Reco jets also pass the usual ID and lepton cleaning.

**Incomplete matches stay in the skim.** Use `B0AssignmentMask` for reconstruction
training and each truth label's own `Valid` flag for classification. Use the
documented [observable feature list](docs/b0-input-profile.md#observable-features-and-masks)
as network inputs; generator truth is a target, never an input feature.

Read the [truth definitions](docs/event-truth-labels.md) and
[object fields](docs/object-synopsis.md) for the complete contract.

</details>

## Check the matching

Run this **after processing**. It reads saved jet assignments and leaves the
ROOT files unchanged. Use a new or empty report directory.

```bash
PYTHONPATH="$PWD/src" micromamba run -n ttbar python -m vcb.postprocessing.matching \
  --files 'outputs/b0-ttbb-check/nano_skim_*.root' \
  --label TTBB --outdir outputs/ttbb-matching-report
```

You get `matching_summary.txt`, `matching_summary.json`, and **W/top mass plots
in PNG and PDF**, for both full and hadronic-top matching.

| Count | What matched? |
| --- | --- |
| Fully matched | Both top b quarks + both hadronic W daughters |
| Hadronic-top matched | Hadronic-top b + both W daughters; includes fully matched events |
| Hadronic-top only | Hadronic top matched, leptonic-top b unmatched |

These are **unweighted counts within the supplied skims**. The plots compare
mass shapes, not predicted yields. The [report guide](docs/matching-report.md)
also shows how to compare TT2Q and TTBB on the same plots.

## Run the full TTBB sample

Use the [B0 production guide](docs/ttbb-b0-production.md). Its helper freezes
the code and checks a complete one-file pilot before production:

**Prepare → pass pilot → submit full sample → validate coverage → normalize → report.**

It reads TTBB NanoAODs from **EOS**, or TT2Q/TTCB NanoAODs already on BRUX, and
writes processed skims on **BRUX**. Select the source with `--sample`. The integrated
workflow uses **one input file per job**. Finalization adds `finalWeight` using
the complete dataset's all-input denominator; do not normalize each job alone.
The [general Condor guide](condor/README.md) covers other campaigns.

**Current checkpoint:** B0 schema 2 adds the agreed b-jet truth labels.
Full TT2Q, TTCB and TTBB processing was submitted after all three pilots passed.
See the [C1 readiness record](docs/c1-input-readiness-2026-11-04.md) for validation
and the production checkpoint. The [November 3 pilot](docs/ttbb-helper-integration-2026-11-03.md)
remains the historical schema-1 checkpoint.

**Scope:** 2024 MC. Collision-data processing is rejected. Combining inclusive
TT2Q and dedicated TTBB yields still requires an overlap prescription; the
processor does not perform that combination. See [CMS readiness](docs/cms-readiness-2026-10-27.md)
and [B0 dataset requirements](docs/b0-input-profile.md#release-validation-2026-10-28).

## Documentation

| Need | Start here |
| --- | --- |
| Selection and event weights | [Event synopsis](docs/event-synopsis.md) |
| Corrections and saved object fields | [Object synopsis](docs/object-synopsis.md) |
| B0 features, masks and jet-charge decoding | [B0 input profile](docs/b0-input-profile.md) |
| Truth labels and complete-truth files | [Event truth labels](docs/event-truth-labels.md) · [C1 campaign](docs/c1-truth-campaign.md) |
| Current C1 definitions, validation and production | [C1 input readiness](docs/c1-input-readiness-2026-11-04.md) |
| Commands and production | [CLI](docs/cli.md) · [TTBB workflow](docs/ttbb-b0-production.md) · [Condor](condor/README.md) |
| Matching counts and mass plots | [Matching report](docs/matching-report.md) |
| Development checks | [Tests and fixtures](docs/tests.md) · [Repository instructions](AGENTS.md) |

<details>
<summary><strong>Full reference map: validation, systematics and project history</strong></summary>

| Document | Contents |
| --- | --- |
| [CMS/C1 integration](docs/cms-c1-integration-2026-11-03.md) | Combined realignment and B0/C1 scope, merge validation and production boundaries |
| [TTBB helper integration](docs/ttbb-helper-integration-2026-11-03.md) | Passed Condor pilot, matching counts, source freeze and validation evidence |
| [CMS readiness](docs/cms-readiness-2026-10-27.md) | 2024 MC coverage, payload pins and remaining limits |
| [Top-pT normalization](docs/top-pt-normalization-2026-10-27.md) | Optional top-pT factors, all-input sums and downstream formulas; not applied to nominal weights |
| [Normalization integrity](docs/normalization-integrity-2026-10-27.md) | Signed/zero weights, reruns and stale-output checks |
| [B0 input preparation](docs/b0-input-readiness-2026-10-28.md) | Original processor freeze, ten-jet cap, W-lepton flag and provisional normalization sources |
| [B0 matched-jet mass check](docs/b0-mass-sanity-2026-11-03.md) | Bounded TT2Q/TTBB comparison before full production |
| [Nominal calibration schema](tests/outfile/test-output-schema.csv) | Test-skim branches before `finalWeight`; B0 needs its own validated schema |
| [2024 inputs](docs/2024-inputs.md) | Calibration and cross-section sources |
| [2024 muon momentum](docs/muon-momentum-2024-plan.md) | Corrections, uncertainty model and high-pT limits |
| [Jet/MET/electron variations](docs/jet-met-electron-variations-2024-plan.md) | Full object passes and [27-source JES mapping](docs/jes-2024-full-source-manifest.json) |
| [October skim realignment](docs/skim-realignment-2026-10-27.md) | Extra-lepton records, trigger matching, unclustered MET and PDF preservation |
| [October weight realignment](docs/weight-realignment-2026-10-27.md) | Uncapped pileup, signed scale weights and shower definitions |
| [2024 ttbar PDF/alpha-S](docs/pdf-alphas-2024-plan.md) | Member normalization and remaining fit choices |
| [MC audit cross-check](docs/audit-crosscheck-2026-09-23.md) | Independent review of the [2024 MC audit](docs/audit-2024-mc-2026-09-11.md) |
| [Processor walkthrough](docs/processor.md) | Longer implementation notes; use the synopses for the current sequence |
| [Normalization design](docs/normalization.md) | Second-pass design history |
| [Project history](docs/history.md) | Origins and earlier changes |
| [Jet/PU payloads](src/boostedhh/corrections/README.md) · [Lepton payloads](src/vcb/corrections/README.md) | Bundled corrections and sources |
| [Bundled framework](src/boostedhh/VENDORED.md) | Upstream version and deliberate local changes |

</details>
