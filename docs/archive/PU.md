> **Archived 2026-07-27.** Exploration notes from finding the 2024 pile-up
> payload on CVMFS. Superseded by
> [`src/boostedhh/corrections/README.md`](../../src/boostedhh/corrections/README.md),
> which records the chosen file, snapshot pin, md5, and era rationale.

# Pile up (PU)

Pile up information of 2024 can be found at
```bash
ls /cvmfs/cms-griddata.cern.ch/cat/metadata/LUM/Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15/latest/
```
which yields
```text
changes.md                  puWeights_CDEFGHI.json.gz  puWeights_E.json.gz  puWeights_H.json.gz
puWeights_BCDEFGHI.json.gz  puWeights_C.json.gz        puWeights_F.json.gz  puWeights_I.json.gz
puWeights_B.json.gz         puWeights_D.json.gz        puWeights_G.json.gz
```
