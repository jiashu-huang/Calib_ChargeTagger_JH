# C1 tasks 1 and 2: source inventory and complete truth

The authorized work is to inventory the nominal 2024 inputs and produce complete
extra-b-quark truth sidecars. B0 skim production, selection/matching audits,
training-file conversion and training are later steps. All work here runs on
BRUX. The frozen B0 processor and its truth definition are unchanged.

The [October 28 launch record](c1-truth-campaign-2026-10-28.json) pins the
inventory, code snapshot, validation evidence and Condor submission. Task 1
completed with **13,737 files and 548,403,125 raw events**. Task 2 was submitted
as DAG **7642817**, with 2,751 worker batches and an automatic final certification
job. The launch record is not a completion certificate; the runtime campaign's
`completion.json` is the final gate.

## Inputs and coverage

The canonical conversion is `charge_Run3_2024_150X_v1`:

| Source | NanoAOD files | Raw events | Complete generator record |
| --- | ---: | ---: | --- |
| TTtoLNuCB | 465 | 19,823,340 | Original 2024 MiniAODs; three already local, the rest through CMS XRootD |
| TTtoLNu2Q | 11,014 | 484,256,657 | Original 2024 MiniAODs through CMS XRootD |
| TTBB-TTtoLNu2Q | 2,258 | 44,323,128 | Paired complete GenTruth files in the verified EOS production of October 24 |

These are counts before event selection and matching, not the usable
reconstruction-training populations.

The original conversion input lists define the first two populations. The
completed TTBB catalog and its bound production manifest define the third.
Each original MiniAOD appears once. The older ten local TTBB pilot files are
partial conversions and are excluded. Historical selected ROOT/HDF5 counts do
not define the new campaign population.

`condor/scripts/c1_inventory.py` checks every NanoAOD header, required basic
branches, UUID, event count and Runs weight sums. It rejects missing declared
files, duplicated sources/UUIDs, invalid headers and partial TTBB ranges. It
records branch names, titles and ROOT classes, source locations and local file sizes/timestamps or EOS
catalog checksums. A Runs/Events count difference is reported explicitly.
The complete truth builder subsequently requires complete native event coverage.

All three sources have the same 2,019 branch names. Their recorded branch
metadata differ only in the `LHEPdfWeight` documentation: TTBB identifies LHA
IDs `325500–325600`, while TTCB/TT2Q identify `325300–325402`. These PDF metadata
remain separate by source. The complete feature/type audit remains later C1 work.

ROOT's compiled header reader is the production reader. Independent Uproot
measurements check its UUID, counts and weight sums. The ROOT and Uproot readers
also have a common synthetic-file test. No Events-tree selection is performed
during inventory. Per-file metadata caching permits interrupted scans to resume.

## Execution and checkpoints

1. **Inventory checkpoint:** `inventory.json` is published only after all
   declared headers pass. `inventory-failures.json` reports any unsuccessful
   reads; rerunning the scan retries them using the verified cache.
2. **Code checkpoint:** `c1_truth_campaign.py prepare` copies the worker,
   existing `build_truth_labels.py` and truth definition into the campaign.
   Their hashes, the inventory hash and every batch manifest hash are pinned
   in `campaign.json`. Later edits to a checkout cannot alter running jobs.
3. **Worker checkpoint:** the first job for each sample processes one complete
   file. All three must succeed before the remaining jobs can start. Later
   jobs process up to five file pairs. The production limit is 40 concurrent
   jobs, one CPU and 4 GB memory per job.
4. **Per-file checkpoint:** the frozen builder aligns unique run/lumi/event
   identities, verifies retained GenPart content, requires complete native/NanoAOD
   coverage and writes exact extra-b counts in NanoAOD order. The wrapper reads
   back the NPZ, verifies its checksum, UUID, schema, count/status consistency,
   identities and summary counts, then atomically publishes that pair.
5. **Truth checkpoint:** the final job independently reads every published pair.
   Only complete, unique, verified coverage produces the three source manifests
   and `completion.json`. Missing or failed pairs produce `truth-status.json`
   with state `incomplete`; they do not produce a usable final manifest.

TTBB NanoAOD/GenTruth pairs are staged one at a time on each worker. Both sizes
and Adler-32 checksums must match the conversion catalog. Scratch files are
removed after the pair. Remote MiniAOD truth is streamed; the campaign does not
download a second full MiniAOD collection or write new ROOT files to EOS.

Successful pairs are retained across retries. Every reused sidecar is checked
again. Unfinished attempts remain outside the published pair directory, with
their logs and failure record. The DAG retries failed jobs twice; a retry skips
verified completed pairs. A CMS proxy with at least three hours remaining is
required at worker start. Expiration requires renewal, never an interactive
passphrase prompt in a batch job.

For failed remote MiniAOD reads, subsequent attempts use the CMS global,
Fermilab and INFN redirectors in turn. The original MiniAOD LFN remains fixed;
every attempt must pass the same identity/content checks. The successful read
path is retained in the pair completion record.

## Meaning of the labels

The sidecar stores the exact unrestricted count and its validity status. Primary
top/W decay b lines are excluded under the frozen convention; genuinely new
shower b lines remain included. Ambiguous ancestry remains `count=-1` with its
failure status. It is never converted to zero or used to reject an event.

The sidecar does not define a visible extra-b-jet category, a physical-yield
stitching rule, a reconstruction assignment or a W-decay label inferred from
the dataset name. `Calib_ChargeTagger_JH` supplies W-decay labels and reconstruction
targets during the later B0 skim step. Full matching remains the condition for
assignment supervision. Valid classification labels have independent masks.

## Reproduction and recovery

Run the inventory with the CMSSW runtime and the CMS proxy configured:

```bash
python3 condor/scripts/c1_inventory.py \
  --workspace /isilon/export/home/jhuan166/Vcb \
  --output-dir /isilon/export/home/jhuan166/Vcb/Calib_ChargeTagger_JH/outputs/c1-truth-20261028 \
  --reader root --workers 8
```

Preparation requires a completed inventory in that directory. `prepare` refuses
to replace an existing campaign. The frozen worker can run one batch or repeat
the final certification without regenerating successful outputs:

```bash
python3 condor/scripts/c1_truth_campaign.py prepare --campaign CAMPAIGN \
  --cmssw /isilon/export/home/jhuan166/Vcb/CMSSW_15_1_0_patch4 \
  --proxy /isilon/export/home/jhuan166/Vcb/cmssw-charge-run/x509up_u140430215 \
  --files-per-job 5 --max-jobs 40
condor_submit_dag -maxjobs 40 CAMPAIGN/production.dag
bash CAMPAIGN/code/condor/scripts/c1_truth_worker.sh CAMPAIGN collect
```

Use the DAG's rescue state after exhausted retries. Preserve its inventory,
code snapshot and verified pair directories. A change in scope or truth
definition requires a new campaign. The later skim must pin the SHA-256 of
its source's `TTCB-truth-manifest.json`, `TT2Q-truth-manifest.json` or
`TTBB-truth-manifest.json`.

Tests cover missing and duplicated inputs, independent metadata readers,
partial TTBB ranges, corrupt payloads, source/definition mismatches, unknown
truth, interrupted publication, complete coverage, retry reuse and the three
sample worker gate. Full C1 is not complete when tasks 1 and 2 finish; the common
skim and its feature/matching audit still have to run.
