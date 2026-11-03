# B0 truth-matched jet masses, 3 November 2026

The bounded TT2Q and TTBB check shows the expected hadronic W and top
resonances. Both samples have their highest unweighted 5 GeV bins at
80–85 GeV for the W and 170–175 GeV for the top. No assignment-index,
matching-cone, source-identity or four-vector inconsistency was found.
This checks the nominal processor on a small population before full B0 skim
production. It does not certify the full C1 population or its sample stitching.

## Code and selection

The existing
[hadronic-mass study](../../../NanoAOD-calib-studies/studies/hadronic-masses.py)
already implements the required sums. Its input is the older match-filter
schema and selection. The new
[B0 plotter](../diagnostics/plot_matched_jet_masses.py) uses the same sums
directly on the current processor columns:

- W: `M(j[GenHadQ1JetIdx] + j[GenHadQ2JetIdx])`.
- Top: `M(j[GenHadBJetIdx] + j[GenHadQ1JetIdx] + j[GenHadQ2JetIdx])`.

The vectors use corrected reconstructed `ak4JetPt/Eta/Phi/Mass` values.
`B0AssignmentMask` requires all four ttbar partons to have distinct real
matches, including the leptonic-top b. B0 selects jets with strict
`pT > 25 GeV`, `abs(eta) < 2.4` before retaining ten slots; matching uses
the frozen nearest-pair greedy algorithm with strict `DeltaR < 0.4`.
The W pair is unordered for this calculation. There is no mass-window cut,
b-tag cut, extra-b-count cut or mass-constrained fit.

The processor is release `b0-processor-20261028-v1`, commit
`721a43947ac3f66c5d9d416f4548edcdabb47635`. Its source files were checked
against the campaign's hashes at every worker start. Only diagnostic code
and documentation were added in the isolated checkout.

## Inputs and results

Whole files were sorted by `SHA256("20261103:" + source_id)` within each
sample. Files were taken until at least 200,000 input events were covered.
The choice uses file identity only. All fully matched events in those files
are included; events were not chosen using their reconstructed masses.

| Sample | Files | Input events | B0 selected | Fully matched |
| --- | ---: | ---: | ---: | ---: |
| Inclusive TTtoLNu2Q | 5 | 221,100 | 32,826 | 13,187 |
| Dedicated TTBB-TTtoLNu2Q | 10 | 204,624 | 37,164 | 13,064 |

TTBB NanoAODs were read from the completed EOS CMSSW_CHARGE production,
staged per worker and checked against its file sizes and Adler-32 checksums.
TT2Q NanoAODs were read from the inventoried BRUX production. Every input had
an independently validated C1 truth sidecar. This bounded check did not need
the pending repair of an unrelated TT2Q file or a full-population manifest.

All selected files passed the existing B0 validator, including source/event
identity, complete input weight sums, raw features and masks, extra-b labels,
saved-slot geometry, and an independent replay of the greedy matcher.
Both samples used the same B0 feature schema and jet-correction payloads.
Every fully matched event has W-decay label TT2Q. Two fully matched TTBB
events have ambiguous extra-b counts; they remain in these plots.

Unweighted mass summaries, in GeV:

| Quantity | TT2Q median | TT2Q central 68% | TTBB median | TTBB central 68% |
| --- | ---: | --- | ---: | --- |
| W mass | 81.86 | 68.23–95.82 | 82.53 | 68.73–96.90 |
| Top mass | 168.17 | 145.07–191.55 | 169.46 | 146.40–193.32 |

These are distribution summaries, not fitted masses or precision calibration
measurements. The distributions have radiation and reconstruction tails.
The corresponding generator top medians are 172.48 and 172.50 GeV.

The main figure uses unweighted counts, normalized independently for each
source. The companion figure uses the skim's signed nominal MC weights with
the same separate shape normalization. It contains 46 negative-weight TT2Q
events and 596 negative-weight TTBB events. No inclusive/dedicated yield sum
or overlap-removal prescription enters either comparison.

Histograms show W masses from 0 to 200 GeV and top masses from 50 to 350 GeV.
Normalization includes the complete selected population, including entries
outside these display ranges. W overflow counts are 43 (TT2Q) and 71 (TTBB);
top overflow counts are 49 and 87. There are no underflows. The accompanying
NPZ files retain every plotted event and both masses without truncation.

## Artifacts and reproduction

The [campaign directory](../../../Calib_ChargeTagger_JH/outputs/b0-mass-sanity-20261103-v2/)
contains the immutable file list, code hashes, commands, worker reports,
skim ROOT files and metadata. Condor DAG 7648888 completed all 15 jobs.
The initial attempt, DAG 7648856, stopped before processing events because
its clean worker environment lacked `PATH`. The corrected wrapper exports
`PATH` and uses the absolute `ttbar` environment prefix; the file population
and physics configuration are unchanged. Both attempt records are retained.

- [Unweighted comparison, PDF](../../../Calib_ChargeTagger_JH/outputs/b0-mass-sanity-20261103-v2/plots/matched_jet_masses.pdf)
- [Weighted comparison, PDF](../../../Calib_ChargeTagger_JH/outputs/b0-mass-sanity-20261103-v2/plots/matched_jet_masses_weighted.pdf)
- [Numerical summary and provenance](../../../Calib_ChargeTagger_JH/outputs/b0-mass-sanity-20261103-v2/plots/summary.json)

PNG versions and per-event mass/provenance NPZ files are in the same `plots/`
directory. The plotter verifies skim checksums before reading them, checks
source-event uniqueness and matching eligibility, and compares the vector
library's invariant masses against an independent Cartesian calculation
for every event. Analytic four-vectors reproduce known 80 and 172.5 GeV
invariant masses. Interchanging the two W daughters leaves every W mass
unchanged. The plotter passes the repository's diagnostic lint checks.

Recreate the plots from the completed campaign in the isolated checkout:

```bash
MPLCONFIGDIR=/tmp/vcb-mass-sanity-mpl \
  micromamba run -n ttbar python diagnostics/plot_matched_jet_masses.py \
  --campaign /isilon/export/home/jhuan166/Vcb/Calib_ChargeTagger_JH/outputs/b0-mass-sanity-20261103-v2
```

[The bounded runner](../diagnostics/run_mass_sanity.py) provides `prepare` and
`worker` commands for a new campaign. Preparation requires a new output
directory and revalidates every chosen truth sidecar before writing jobs.

For routine postprocessing of completed skims, use the separate
[matching report module](matching-report.md). It adds readable text/JSON
counts and mass plots for events with the hadronic top matched even when
the leptonic b is unmatched. The original campaign plotter above remains
the reproduction tool for this bounded check, including its weighted plots.
