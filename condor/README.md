# HTCondor batch processing

Last update: **2026-09-13**

One Condor job per `batch_*` input directory. Each job runs the `vcb` skimmer
on all ROOT files in its batch and writes one skimmed ROOT + one totals pickle.
The skimmer never writes `finalWeight` — its denominator sums over every batch,
which no single job can know. It is appended afterwards, in place, by
`scripts/normalize.py`.

Run the submitter from the `ttbar` environment (activate it or prefix the
commands below with `micromamba run -n ttbar`). The worker's environment
selection remains controlled independently by `--mamba-env`.

## Worked example: 2024 production

Input: 93 `batch_*` dirs (465 files, 5 per batch, ~65 GB, 19,823,340 events;
Σ genWeight = 6.627e9) under

```
/isilon/export/home/jhuan166/Vcb/MC/TTtoLNuCB_Summer24MiniAODv6/NanoAOD-cmssw-charge/charge_Run3_2024_150X_v1/
```

### 1. Generate (and optionally submit) the campaign

```bash
INPUT=/isilon/export/home/jhuan166/Vcb/MC/TTtoLNuCB_Summer24MiniAODv6/NanoAOD-cmssw-charge/charge_Run3_2024_150X_v1

# dry run on the first two batches first:
python condor/submit_batches.py --input-root "$INPUT" --files-name TTtoLNuCB \
  --tag test_$(date +%Y%m%d) --test

# full campaign, submitting directly:
python condor/submit_batches.py --input-root "$INPUT" --files-name TTtoLNuCB \
  --tag prod_$(date +%Y%m%d) --submit
```

`--files-name` is **required** and has no default — it picks the cross section,
the gen selection and the top-pT columns, so the wrong label rescales the whole
campaign with nothing to catch it. Other defaults: `--year 2024`,
`--skimmer vcbSkimmer`, `--mamba-env ttbar`. Generated JDLs/worker scripts land in
`condor/runs/<tag>/` (git-ignored); outputs in
`<input-root>/processed-nano/<tag>/{roots,pickles,metadata}/` by default, or
wherever `--processed-dir <dir>` points (the 2026-07-26 production wrote to
`MC/TTtoLNuCB_Summer24MiniAODv6/NanoAOD-processed/prod_20260726/`, keeping
skims out of the input tree).

Without `--submit`, submit later with `condor/runs/<tag>/submit_all.sh`, or
debug a single job locally with `bash condor/runs/<tag>/batch_000/run_batch.sh`.

> Input health (scanned 2026-07-26): all 465 files open, carry an `Events`
> tree, and have the branches the skimmer needs — **0 bad, 0 missing
> branches**. Worth re-checking after any regeneration: `--files` sets
> `skipbadfiles=False`, so a single unreadable file aborts its whole job.
>
> Keep merged/derived copies **out of** the `batch_*` directories. A hadd of
> batch_000 (`merged/batch_000.root`, 208,780 events) briefly sat inside
> `batch_000/`, which would have made that job skim the same events twice —
> harmless to the yield (numerator and denominator both double-count) but it
> corrupts the statistics and doubles the runtime. `submit_batches.py` only
> descends into directories matching `batch_<digits>`, so a sibling `merged/`
> is safely ignored.

### What each job runs

`submit_batches.py` renders one worker script per batch from
[templates/calib_batch_exec.sh](templates/calib_batch_exec.sh). With the
defaults above, every job executes:

```bash
micromamba run -n ttbar python -u -m vcb.run \
  --processor skimmer --skimmer vcbSkimmer \
  --year 2024 \
  --files <this batch's *.root>  --files-name TTtoLNuCB \
  --naming-tag batch_NNN \
  --save-root \
  --save-systematics|--no-save-systematics \
  --chunksize 1000000 --maxchunks 0 --batch-size 9999 \
  --outdir condor/runs/<tag>/batch_NNN/work
```

| Where it comes from | Value | Why |
|---|---|---|
| `--naming-tag` | `batch_NNN` | names the outputs; the worker renames them to `<tag>/roots/batch_NNN.root` and `<tag>/pickles/batch_NNN.pkl`, which is the pairing `normalize.py` relies on |
| `--files-name` | *required* | whatever you passed to `submit_batches.py`. Must match a key in `xsecs`, else the run normalizes to `weight_norm = 1`; `vcb.run` refuses to start if it is missing altogether |
| `--save-systematics` | off unless passed | mirrors `submit_batches.py --save-systematics`. Always written out in full (`--save-systematics` or `--no-save-systematics`) so the worker script records which mode it ran. See below |
| `--kinematic-variation` | `nominal` | One complete 2024 MC pass, e.g. `jerUp`, `jes_RelativeBalDown` or `electron_smearUp`. See [the pass list](../docs/cli.md#kinematic-variation-passes). Use a separate campaign/tag per pass; group names are local-runner options. |
| `--batch-size` | `9999` | forces one ROOT per job; the worker asserts exactly one and fails otherwise |
| `--maxchunks` | `0` | no cap — process the whole batch |
| `--chunksize` | `1000000` | events per coffea chunk |
| no `finalWeight` flag | — | the skimmer cannot write it; see step 2 |

Condor resources come from the JDL: `request_cpus = 2`,
`request_memory = 4G`, `request_disk = 2G`, `getenv = true`, `universe =
vanilla`. Nothing is transferred — workers read the shared filesystem
directly.

The campaign `--tag` is the only identifier you choose. It names both
`condor/runs/<tag>/` (JDLs, worker scripts, logs, `campaign.json`) and the
processed-output directory. Both must not already exist, so a tag is
single-use — the tag is the one key tying scripts, logs, and outputs
together, and `campaign.json` inside the run dir records every path and
parameter it was generated with.

**Tag convention:** `test_<YYYYMMDD>[_<HHMM>]` for trial runs (delete the run
dir *and* its processed outputs once superseded), `prod_<YYYYMMDD>` for real
productions (keep both).

#### Which code ran: `calib_repo_git`

`campaign.json` also records `submitted_at` and a `calib_repo_git` block —
commit, branch, and a `dirty` flag with the list of uncommitted files.

This matters more than it looks, because **workers do not get a copy of the
repo**. The generated script puts `$CALIB_REPO/src` on `PYTHONPATH` and imports
from the live checkout, so:

- a finished skim has no other record of what produced it, and
- jobs start over a span of hours. **Editing anything under `src/` while the
  queue drains silently splits the campaign across two code versions**, with
  nothing in the output to mark where.

So: commit before submitting, and leave the tree alone until the queue is
empty. `submit_batches.py` prints a warning when the tree is dirty, but does
not refuse — a submitter that blocks is a submitter people work around.
`dirty: true` in a production's `campaign.json` means its commit hash does not
describe what ran.

#### Kinematic variations

For each desired pass, generate a campaign with a distinct tag and
`--kinematic-variation <pass>`. The worker runs the full input NanoAOD selection
and copies the corresponding ROOT, totals pickle and
`metadata/<batch>.kinematics.json` together. `campaign.json` records the pass
name/ID. The ROOT also stores `KinematicVariation` on every event. Non-nominal
temporary filenames include the pass name; the output ROOT/pickle pairing
retains the normal batch naming within its separate campaign.

Normalize and merge each campaign separately. Never mix nominal and shifted
copies in a normalization denominator or a merged event sample. Weight-only
`--save-systematics` can be enabled independently in every campaign.

#### Event truth labels

For the exact extra-b-quark label, pass `--truth-label-manifest /path/manifest.json`
to `submit_batches.py`. The worker forwards it to the processor; the campaign
records its path and checksum. Build it from the paired native generator-truth
files as described in [event truth labels](../docs/event-truth-labels.md).
Without a manifest, the count is unknown and the W-decay label is still written.

#### Systematic variations

`--save-systematics` is **off by default** and worth turning on for any real
production. Weight prescription versions 2 and 3 add 18 `weight_*Up/Down` total
alternatives — pile-up, ISR/FSR parton shower, and the six lepton scale factors —
plus 12 muon statistical/systematic component alternatives. Use either a step's
total or its components in a fit, not both. Only norm-preserving terms get
separate `np_*` denominators in the totals pickle and ROOT `Norm` tree;
lepton variations use the nominal denominator. For ttbar it also saves every PDF member
ratio, the verified LHA mapping, and all-input member sums. The signal fixture
has 103 members; the measured TTBB pilot has 101. See the
[October implementation record](../docs/skim-realignment-2026-10-27.md).

The follow-up [weight realignment](../docs/weight-realignment-2026-10-27.md)
removes PU/scale clipping and requires verified 2024 PS/scale layouts and
lepton-SF payloads. Shower Up/Down means muR x2/x0.5. `WeightMetadata` records
the convention even in nominal-only output. The merge, normalization and
validation tools reject mixing it with older capped output. Regenerate that
output from NanoAOD and compute fresh all-input denominators to adopt the fix.

The [muon follow-up](../docs/cms-readiness-2026-10-27.md) defines version 2,
including the statistical error missing from the released IsoMu24 `systup/down`
categories. Version 1 remains readable in its own campaign; mixing versions fails.
2024 collision-data production is explicitly unsupported.

The [top-pT follow-up](../docs/top-pt-normalization-2026-10-27.md) defines
version 3. It preserves all-input top-pT normalization and joint sums with
every saved norm-preserving variation, plus a validity flag/counts. These are
also retained through merge and forced normalization, checked against the
pickle, and reported in `normalization.json/global_top_pt_sums`. This does not
apply a top-pT factor to nominal `weight` or `finalWeight`. Versions 1/2 remain
readable separately; mixing them with version 3 fails.

The reason to decide *before* submitting rather than after: the raw `PSWeight`
array is not written to the skim, so **ISR/FSR variations cannot be rebuilt
from the output** — recovering them means re-running the whole campaign, and
regenerating everything downstream that was built on the first skim. Pile-up
and the lepton SFs are re-derivable (from `nTrueInt` and
`TriggerLeptonPt`/`Eta`), and the μR/μF `scale_weights0..5` are written either
way.

### 2. Global finalWeight

After **all** jobs finish (the denominator must see every batch):

```bash
micromamba run -n ttbar python condor/scripts/normalize.py \
  --processed-dir "$INPUT/processed-nano/<tag>"
```

This sums `np_nominal` over the batches (from each ROOT's own `Norm` tree,
pickles as fallback) and **appends** `finalWeight = weight / global_np_nominal`
to each `roots/batch_*.root` in place — existing branches untouched, ~3 bytes
per event written, seconds not minutes. Provenance (denominator + a fingerprint
of the batch list) lands in each file and in `metadata/normalization.json`.

A ROOT without a Norm tree or pickle is a hard error. The complete campaign
is checked before writing: weights and quotients must be finite, zero weights
must be consistent, and all nonzero-event ratios must give the same sample
factor. D must be finite and nonzero. Already-normalized files are skipped
only after their values and provenance match; stale output requires `--force`
to recompute it via a full rewrite. To normalize after
merging instead, run with `--target merged` — hadd concatenates the per-batch
`Norm` entries, so the merged file carries its own denominator.

### 2b. Validate

```bash
micromamba run -n ttbar python condor/scripts/validate_processed.py \
  --processed-dir "$INPUT/processed-nano/<tag>"     # add --target merged for the merge
```

The default `--schema-mode auto` detects nominal or systematic output from
the first ROOT file and requires that mode for every file checked. Nominal
output must match the committed `tests/outfile/test-output-schema.csv`;
systematic output must also contain all 18 total up/down weight branches and,
for prescription versions 2/3, all 12 muon component branches,
and the ttbar PDF members specified by `PdfMetadata`.
`finalWeight` is allowed in either mode. Missing columns,
unknown extras, incomplete variation sets, and mixed modes fail validation.

Use `--schema-mode systematics` for a campaign run with `--save-systematics`
to catch even the absence of all variation branches. Use `--schema-mode nominal`
to require nominal output. These modes work for both batches and merged files.
For a different schema, `--schema-baseline /path/to/schema.csv` replaces mode
detection with an exact column list, allowing only `finalWeight` as an extra.
The two options are mutually exclusive; a missing or invalid CSV is an error.

Per file: the branch-name check above,
required branches present, `Norm` tree (including empty selections), finite weights, a single
sample factor across every nonzero event, finite nonnegative `nTrueInt`, and `finalWeight == weight /
global_np_nominal` bit-exact with matching provenance. Campaign-wide: the
`Norm` sums equal the pickle sums, PDF mappings agree, the sample factor is consistent across files, and
`Σ finalWeight == σL × Σ(weight_noxsec) / global_np_nominal` — the identity
that catches a `finalWeight` written with the wrong denominator. Exit code is
non-zero if anything fails.

Signed and zero weights are retained. The weighted selection fraction is not
restricted to zero through one, and a canceled sum does not disable checks.
The inferred sample factor checks arithmetic; it does not certify a physical
cross section. See [normalization integrity](../docs/normalization-integrity-2026-10-27.md).

### 3. Merge (optional)

```bash
# hadd comes with the ROOT install in the ttbar env (or activate CMSSW)
python condor/scripts/merge_processed.py \
  --processed-dir "$INPUT/processed-nano/<tag>"
# -> <processed-dir>/merged/total.root
```

**This step is convenience, not correctness.** After step 2 every batch ROOT
already carries a `finalWeight` computed with the *global* denominator, so the
93 files are immediately usable as they are — `TChain` them, or hand the
directory to uproot, and the yields come out right. `hadd` preserves
`finalWeight`, the `Norm` tree (one entry per batch, so the merged file's sum
is the global denominator) and the provenance objects, so merging after
normalizing is safe and self-consistent.

One thing to keep straight: `finalWeight` is normalized to the **whole
campaign**, not to the file it lives in. Summing it over all 93 batches gives
the predicted yield; summing over one batch gives *that batch's share* of the
yield, not a full-sample estimate. Analyse a subset only if you mean to.

If you would rather merge first and normalize once, swap the order and run
`normalize.py --target merged`. Choose one workflow. A later invocation using
a different target may require `--force` because its batch fingerprint changes;
forced normalization always recomputes from the original `weight` branch.

## Notes

- Workers only need the shared filesystem: the repo checkout, the `ttbar`
  micromamba env, and the input files. Nothing is transferred.
- `--batch-size` stays at 9999 so one job folds into exactly one ROOT file
  (the worker script asserts this).
- Resource knobs (defaults, sized from a measured 5-file batch — 208,780
  events, 104% of one core, **1.29 GB peak RSS**, 129 MB transient, ~60 s wall):
  `--request-cpus 2 --request-memory 4G --request-disk 2G`. The skim is
  single-threaded, so the second CPU is headroom for I/O threads, not
  parallelism. Memory peaks at the end-of-job concatenation and therefore
  scales with *selected* events, not input size. Disk barely matters: the job
  writes to the shared filesystem, so condor's own accounting reported 5 KB of
  sandbox use.
- Condor's cgroup memory sampling can under-report a ~60 s job (it logged
  133 MB against a directly measured 1.29 GB peak). Size from
  `/usr/bin/time -v`, not from the job log.
- Filters: `--batch-names batch_007 ...`, `--batch-start/--batch-end`,
  `--max-batches`, `--test` (first two).
