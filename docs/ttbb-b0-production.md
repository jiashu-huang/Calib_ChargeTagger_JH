# 2024 TTBB B0 production

The production reads the certified CMSSW_CHARGE NanoAODs from EOS and writes
processed ROOT skims, normalization totals and metadata on BRUX. It uses the
frozen B0 selection and truth definitions: ten accepted jets, pT > 25 GeV,
|eta| < 2.4, at least four accepted jets, greedy distinct matching at ΔR < 0.4,
and independent W-decay/extra-b-quark labels. Unmatched events are retained.

## Weight fix and scope

The dataset-name check for six saved scale weights previously accepted
`TTto...` and `TTTo...` but omitted `TTBB-TTtoLNu2Q`. The new release also
accepts the `TTBB-` prefix. Both selected-event scale weights and their
signed all-input normalization sums are now retained. The existing scale
member mapping and clipping convention are unchanged. This does not change
nominal weights, event selection, matching or model inputs.

The campaign enables `--save-systematics` while keeping nominal kinematics.
It adds the eighteen existing pileup, ISR/FSR, and lepton-efficiency variations.
PDF/alphaS output and shifted kinematic passes remain separate work.
The approved provisional rate remains 16.011655167690346 pb; no additional
branching fraction or TT2Q/TTBB source stitching is applied here.

## Frozen campaign and pilot

[ttbb_b0_campaign.py](../condor/scripts/ttbb_b0_campaign.py) provides `prepare`,
`pilot`, `authorize`, `worker` and `finalize`. Preparation requires a clean
commit, a complete truth certificate, matching inventories and unchanged
truth payload checksums. It copies the processor, correction payloads and
required helper scripts into the campaign's `code/` directory. Every job
verifies those hashes and its pinned truth manifest before starting.

Preparation does not submit jobs. It writes `pilot.sub`; the pilot must pass
before `authorize` can write the full `production.dag`. The pilot uses one
complete certified TTBB input that also has an earlier validated nominal skim.
Every existing output branch and both original `Norm` branches must agree
exactly. The only additions are six scale branches and eighteen variations.
The pilot also checks raw jet-tagger correspondence, B0 features/truth/matching,
independent scale/shower weight arithmetic, signed all-input sums, output
schema, and nominal second-pass normalization. The production gate pins the
configuration, schema and pilot result.

One input file is processed per Condor job. This keeps source coverage and
retries unambiguous; five-file groups are not required. The campaign uses
40 simultaneous jobs, one CPU and 4 GB memory per job, and 10,000-event
processor chunks. Use the generated `worker.sh` so its environment, proxy,
source path and cache settings remain consistent between pilot and production.

```bash
# After prepare has frozen the campaign:
condor_submit /path/to/campaign/pilot.sub

# After pilot-passed.json exists and has been checked:
/path/to/campaign/worker.sh authorize
condor_submit_dag -maxjobs 40 /path/to/campaign/production.dag
```

## Worker and completion checks

Each job stages one EOS file into temporary storage, verifies its size and
Adler-32 against the conversion inventory, and processes the complete file.
Original NanoAOD UUID/entry identities remain unchanged by staging. The worker
validates the complete input count, saved source identities, truth labels,
features, one-to-one matching, exact pilot schema, eighteen weight variations,
six scale weights and all-input normalization sums. Artifacts are moved into
the output directories and a success record is written last. Failures retain
logs and are retried at most twice. A repeated successful job checks its
existing output hashes instead of adding a duplicate output.

The final job starts only after all workers succeed. It checks exact inventory
coverage, output membership and hashes before allowing normalization. It then:

1. Sums and saves all nominal, scale, pileup and shower normalization totals.
2. Appends nominal `finalWeight` with the existing second-pass normalizer.
3. Runs the campaign validator against the pilot's exact schema.
4. Runs the [optional matching report](matching-report.md) on every output.
5. Records final artifact checksums and writes `completion.json` last.

Only nominal `finalWeight` is appended. Variation branches are pre-normalization
numerators; their corresponding full-source sums are in
`processed/metadata/weight-totals.json` for downstream template construction.
The inherited `nevents` total is a signed generator-weight sum, not a raw event
count. The campaign inventory and per-file validation supply raw input counts.

## Output layout

```text
campaign.json, inventory.json, truth-manifest.json, truth-certificate.json
code/                           frozen processor and helpers
pilot/                          separate validation outputs, excluded from production
pilot-passed.json                final-configuration gate
schema.json, schema.csv          exact validated output schema
processed/roots/                one skim ROOT per original NanoAOD
processed/pickles/              per-file cutflows and all-input weight sums
processed/metadata/             profile, payload and truth provenance; global totals
status/                         one validated success record per input
attempts/, logs/                processing and retry evidence
matching-report/                raw matching counts and W/top mass plots
publication.json                checksums after normalization
completion.json                 complete only after every final check passes
```

The input EOS files and complete-truth sidecars are preserved. The production
does not merge samples, freeze training splits or bins, or start training.

## Software validation before the Condor pilot

On 3 November 2026 the full suite passed 324 tests and 22 subtests, with
repository lint passing. The full 208,780-input-event TTCB calibration
regression retained 59,713 events and 747 branches. Its schema and first-event
values were unchanged, and the jet-tagger report passed with no differences.
The only report-text difference was the absolute location of the shared
fixture; the portable tracked path was retained.

The new weight tests exercise TT2Q, TTCB, legacy ttbar and dedicated TTBB
names with optional variations both enabled and disabled, signed generator
weights, non-unit central scale members, and all-input normalization sums.
Campaign tests cover changed source/schema detection, incorrect input
checksums, incomplete-campaign rejection, idempotent retries, and final-job
dependencies. Real-input pilot results are recorded in the frozen campaign,
and passing software tests alone never releases its production gate.
