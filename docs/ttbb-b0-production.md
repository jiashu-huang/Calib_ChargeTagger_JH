# 2024 TTBB B0 production

This workflow reads certified CMSSW_CHARGE NanoAODs from EOS and writes B0
ROOT skims, normalization totals and matching reports on BRUX. It runs the
integrated CMS version-3 processor with nominal kinematics and weight
systematics enabled. The physics selection and truth definitions are those
in the [B0 guide](b0-input-profile.md).

## What is frozen

[ttbb_b0_campaign.py](../condor/scripts/ttbb_b0_campaign.py) provides `prepare`,
`pilot`, `authorize`, `worker` and `finalize`. Preparation requires a clean
commit, the complete C1 truth certificate, matching input inventories and
unchanged truth payloads. It copies the processor, correction payloads and
helpers into the campaign's `code/` directory. Every job checks those hashes,
the inventory, certificate and truth manifest before processing.

Campaign format 2 requires weight prescription 3. The integrated helper
rejects old campaign configurations; the old campaign retains its own frozen
code and outputs. Create a new directory for the integrated release.

The campaign preserves:

- Uncapped pileup factors and signed, zero or large scale/shower ratios.
- Six scale alternatives, eighteen total weight variations, and twelve muon
  efficiency component alternatives.
- The source's registered PDF member mapping and raw member values. The
  certified TTBB source has 101 members and no separate alpha-S members;
  no alpha-S uncertainty is invented.
- All 49 normalization fields, including original input counts, top-pT
  validity counts, and joint top-pT/PU/shower/scale/PDF sums. Top-pT factors
  remain separate optional quantities and are absent from nominal weights.

The approved provisional cross section remains 16.011655167690346 pb. This
workflow neither applies another branching fraction nor combines TTBB with
inclusive TT2Q yields. Source overlap removal is a separate analysis step.

## Prepare and pass the pilot

Preparation writes job descriptions but submits nothing. Supply a systematic
B0 reference from the integrated processor, independently validated on the
same complete source file. A normalized reference is accepted: its appended
`finalWeight` is excluded from the comparison before normalization. Legacy
weight metadata or missing PDF/B0 metadata is rejected.

```bash
PYTHONPATH="$PWD/src" micromamba run -n ttbar python condor/scripts/ttbb_b0_campaign.py prepare \
  --campaign /path/to/new-campaign \
  --truth-campaign /path/to/completed-c1-truth-campaign \
  --pilot-id TTBB_SOURCE_ID \
  --reference-skim /path/to/validated-integrated-b0-skim.root \
  --proxy /path/to/cms-proxy
condor_submit /path/to/new-campaign/pilot.sub
```

The single Condor pilot stages one EOS file, checks its size and Adler-32,
and runs the frozen processor. It then checks:

1. Complete input coverage and original UUID/entry identity.
2. B0 features, truth sidecars, distinct greedy matching and raw jet taggers.
3. All output columns and `Norm` values against the integrated reference,
   with identical weight prescription and PDF metadata. All values must match
   exactly except the twelve muon component alternatives: Coffea multiplies
   their factors in set order, which can change between processes. Those
   products allow at most 16 float64 epsilons relatively (about 3.6e-15),
   with zero absolute tolerance. PDF values, identities, features, assignments,
   other weights and all normalization fields still require exact equality.
4. Selected weights and all-input sums against the original NanoAOD. The
   checker evaluates the pileup payload directly, preserves the input precision
   during scale division, and uses all input events, including rejected ones.
   It evaluates the stored top-pT functions on tops selected directly from
   NanoAOD; the existing processor tests cover the function definitions.
5. The second-pass normalizer and campaign validator. A normalization rerun
   must leave the ROOT file byte-identical.
6. The [matching report](matching-report.md), including counts and all six
   text/JSON/PNG/PDF artifacts. Geometric full matching is checked separately
   from `B0AssignmentMask`, which also requires valid W topology.

`pilot-passed.json` is written only after every check succeeds. It pins the
configuration, schema, weight prescription, PDF layout, result, normalized
ROOT, normalization receipt and report files. An interrupted pilot's output
is archived before retrying so stale normalization receipts cannot be reused.

Only after reviewing that checkpoint, generate and submit the production DAG:

```bash
/path/to/new-campaign/worker.sh authorize
condor_submit_dag -maxjobs 40 /path/to/new-campaign/production.dag
```

`authorize` writes the DAG; it does not submit it. One complete input file is
processed per job, with one CPU, 4 GB memory and 10,000-event processor chunks.
Use the generated `worker.sh` so source, environment, proxy and caches agree
between pilot and production. Five-file groups are not required.

## Worker and completion checks

Each worker stages its EOS input into temporary storage and verifies the
certified size and checksum. It validates the complete input count, identities,
truth, features, matching, weight arithmetic and all-input normalization sums.
Its exact output schema, weight prescription and PDF mapping must match the
pilot. It publishes artifacts before writing its success record. Failed jobs
retain logs and may be retried twice; a repeated successful job verifies its
existing hashes instead of creating duplicate output.

The final job requires exact inventory coverage, output membership and
validated artifact hashes before normalization. It sums all 49 input totals,
appends nominal `finalWeight`, and runs the campaign validator. It generates
the same matching report used by the pilot and compares its total, geometric
full-match and B0-eligible counts with the worker records. Final report hashes
are recorded with the completion record.

Only nominal `finalWeight` is appended. Weight-variation branches retain their
pre-normalization numerators, PDF branches retain raw ratios, and the required
all-input sums are saved in `processed/metadata/weight-totals.json`. See
[normalization](event-synopsis.md) and [top-pT normalization](top-pt-normalization-2026-10-27.md)
for downstream formulas. `nevents` is a signed generator-weight sum;
`n_input_events` and the inventory give the raw event count.

## Output layout

```text
campaign.json, inventory.json, truth-manifest.json, truth-certificate.json
code/                           frozen processor, payloads and helpers
pilot/                          validation outputs, excluded from production
pilot-matching-report/          pilot matching counts and W/top mass plots
pilot-result.json               complete pilot validation details
pilot-passed.json               immutable release checks and artifact hashes
schema.json, schema.csv          exact output columns before finalWeight
weight-prescription.json        pilot's CMS version-3 metadata
pdf-layout.json                 pilot's registered member mapping
processed/roots/                one skim ROOT per original NanoAOD
processed/pickles/              per-file cutflows and all-input weight sums
processed/metadata/             provenance, normalization receipt and totals
status/                         one validated success record per input
attempts/, logs/                processing and retry evidence
matching-report/                full-campaign counts and W/top mass plots
publication.json                processed artifact checksums after normalization
completion.json                 complete only after all final checks pass
```

The NanoAODs and C1 truth sidecars are reusable input products. The older skims
from `d580296` use the previous trigger/weight prescription and are retained
for comparison. Reprocess the NanoAODs to adopt the integrated release.
This workflow does not start training or freeze training splits.

## Validation and history

The original production helper was validated and used at `d580296`, before
CMS realignment was integrated. Its 747-column calibration baseline and
capped-weight expectations are historical. The integrated helper preserves
the 809-column CMS calibration baseline and uses the source-specific B0
systematic schema (1,347 TTBB columns before `finalWeight`).

The current software tests, real-input checks, frozen source and Condor pilot
are recorded in [TTBB helper integration](ttbb-helper-integration-2026-11-03.md).
