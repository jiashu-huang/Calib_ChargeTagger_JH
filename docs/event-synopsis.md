# Event processing synopsis

This follows the current **2024 MC** path for `TTtoLNu2Q` and `TTtoLNuCB`, from
input NanoAOD to the skim and its second-pass `finalWeight`. Object corrections,
cuts, ordering, matching, and output fields are in
[object-synopsis.md](object-synopsis.md).

2024 collision-data input is rejected before processing: the certified-lumi
mask, run-dependent data JEC and rebuilt data MET are not implemented.

## Event sequence

1. Read a chunk of the input `Events` tree. Take the year and dataset name from
   the fileset metadata; the presence of input `genWeight` identifies MC.
   The dataset name selects the cross section and generator-truth routines.
   Direct-file runs therefore require an explicit `--files-name`.
2. Correct and select [electrons](object-synopsis.md#electrons) and
   [muons](object-synopsis.md#muons). Resolve one trigger lepton: the highest-pT
   eligible muon takes priority; otherwise use the highest-pT eligible electron.
3. Correct [jets](object-synopsis.md#jets), rebuild
   [MET](object-synopsis.md#met), clean jets against the chosen trigger lepton,
   and sort the selected jets. Keep the separate uncleaned jet collection for
   the event veto map.
4. Derive generator-level top/W decay information and reconstructed-object
   matching. These routines label events without imposing a generator-level
   veto. The normalization mask, `gen_selected`, is therefore true for every
   input event in the chunk, before the following event selections.
   The [two event truth labels](event-truth-labels.md) have separate validity
   masks; neither requires full reconstruction matching.
5. **Trigger veto — `single_lep_trigger`:** reject events unless
   `HLT_IsoMu24 OR HLT_Ele30_WPTight_Gsf` fired. Both paths may fire.
6. **Event-quality veto — `met_filters`:** reject events failing any of the
   eight quality flags listed in the [MET section](object-synopsis.md#met).
   A missing required flag or single-lepton HLT branch stops processing with
   an error; it is not treated as an ordinary rejected event.
7. **Detector-region veto — `ak4_jetveto`:** reject events with any jet in a
   vetoed map region, using the uncleaned candidate jets defined in the
   [jet section](object-synopsis.md#jets).
8. **Lepton-count veto — `1lep`:** require at least one good electron or muon.
   This is an at-least-one requirement; additional leptons are allowed.
9. **Trigger-lepton veto — `trigger_lepton`:** require the resolved trigger
   lepton from step 2. It must match its fired trigger and satisfy the offline
   threshold: electron pT >= 32 GeV or muon pT >= 26 GeV. This requirement
   implies `1lep`; both stages remain in the cutflow.
   Additional loose leptons are counted separately. `PassExtraLeptonVeto` is
   recorded for downstream selection, never added to this skim's cutflow.
   See the [object synopsis](object-synopsis.md) for its exact versioned definition.
10. **Optional prescale veto — `prescale`:** if `--prescale-factor N` is set,
    keep only events with `event % N == 0`. The processor does not multiply
    their weights by N, and the normalization denominator remains unprescaled.
11. Calculate weights and normalization totals for **all input events in the
    chunk**, including events failing the selections above. The selections
    have only registered masks at this point. The formulas and factors are
    listed below.
12. Apply the combined selection mask once, then write only passing events.
    Chunk tables are assembled into the skim ROOT `Events` tree. Save the
    accumulated cutflow and normalization totals in the accompanying pickle.
    Each ROOT's `Norm` tree contains the all-input totals for exactly the chunks
    combined into that file, including chunks with zero selected events.
    Requested PDF member sums and their metadata are retained in ROOT too.
13. Run the second pass over the completed output files for this dataset.
    Sum their normalization contributions and append `finalWeight` to each
    saved event, as described below.

There is no event cut on jet multiplicity, b-tag multiplicity, MET magnitude,
W-decay flavour, or completeness of the four parton-to-jet matches. MC cutflow
entries, including `all`, are cumulative **sums of input `genWeight`**, not
raw event counts or fully corrected yields. For MC, the metadata names
`nevents` and `total_nevents` also mean sums of generator weights.

For kinematic uncertainties, [`--kinematic-variation all`](cli.md#kinematic-variation-passes)
repeats this sequence from NanoAOD for nominal, 27 JES pairs, global JER
up/down, four electron shifts and four muon shifts. Jet passes rebuild MET
with correlated per-jet factors; lepton passes select using active pT and
recalculate the chosen lepton's SFs. Each pass retains its entering events.
The all-input normalization denominator is unchanged: normalize and merge
each pass separately. The legacy `--muon-pt-variation all` remains available.

## Nominal weight in the first pass

Define `C = cross section × luminosity`, `g = input genWeight`, and `PU` as
the nominal pileup factor. Let `SF_lepton` be the product of the six registered
lepton factors below; the three belonging to the unchosen flavour equal one.
The nominal ISR and FSR factors also equal one.

```text
w_np          = g × PU × ISR_nominal × FSR_nominal = g × PU
weight_noxsec = w_np × SF_lepton
weight        = C × weight_noxsec
np_nominal    = sum(w_np over every input event processed by the job)
```

`weight` is the first-pass numerator. It is not yet normalized by the amount
of MC processed. Signed generator weights are retained; neither absolute
weights nor event counts replace them in the denominator.

The configured luminosity is `LUMI["2024"] = 109820 pb^-1` (109.82 fb^-1),
the documented C–I analysis reference. Its sources and the treatment of older
outputs are recorded in [2024-inputs.md](2024-inputs.md).
The current cross sections and resulting constants are:

| Dataset | Cross section in pb | `C = sigma × L` |
| --- | ---: | ---: |
| `TTtoLNu2Q` | 410.2834392 | 45057327.292944 |
| `TTtoLNuCB` | 0.3448432306476 | 37870.6835897 |

The signal cross section already includes the configured `|Vcb| = 0.0410`:
`923.6 × 2 × 0.333 × (0.667 × 0.0410^2 / 2)` pb. There is no additional
per-event Vcb factor. These constants come from
[`xsecs.py`](../src/boostedhh/xsecs.py) and
[`hh_vars.py`](../src/boostedhh/hh_vars.py). An unknown dataset label causes
the cross-section lookup to warn and use `C = 1`.

**Applied factors and their output fields**

Every `single_weight_<term>` below stores **`C × that individual nominal
factor`**. To recover the bare factor, divide by C. Multiplying these diagnostic
branches together would incorrectly multiply C repeatedly. The constant can
also be recovered as `weight / weight_noxsec` where the latter is nonzero.

| Term in the weight container | Factor or input | Output diagnostic branch | Included in `np_nominal`? |
| --- | --- | --- | --- |
| `genweight` | Input `genWeight`, including its sign and magnitude | `single_weight_genweight` | Yes |
| `pileup` | Data/MC pileup-profile correction evaluated on input `Pileup.nTrueInt` | `single_weight_pileup` | Yes |
| `ISRPartonShower` | Nominal factor 1; ISR variations from `PSWeight` | `single_weight_ISRPartonShower` | Yes |
| `FSRPartonShower` | Nominal factor 1; FSR variations from `PSWeight` | `single_weight_FSRPartonShower` | Yes |
| `electron_reco` | EGM reconstruction efficiency, using the selected pT range (`Reco20to75` or `RecoAbove75` for the trigger electron) | `single_weight_electron_reco` | No |
| `electron_id` | EGM `wp90iso` identification efficiency | `single_weight_electron_id` | No |
| `electron_trigger` | EGM `HLT_SF_Ele30_MVAiso90ID` trigger efficiency | `single_weight_electron_trigger` | No |
| `muon_id` | MUO `NUM_TightID_DEN_TrackerMuons` efficiency | `single_weight_muon_id` | No |
| `muon_iso` | MUO `NUM_TightPFIso_DEN_TightID` efficiency | `single_weight_muon_iso` | No |
| `muon_trigger` | MUO `NUM_IsoMu24_DEN_CutBasedIdTight_and_PFIsoTight` efficiency | `single_weight_muon_trigger` | No |

PU uses the bundled 2024 `Collisions24_CDEFGHI_goldenJSON` correction without
capping its nominal/up/down factors. Its own `flow="clamp"` handles inputs
outside its [0, 100) binning; nonfinite inputs fail. Output `nTrueInt` retains the input value. Output
`nPU` is the sampled pileup count and `nPV` the reconstructed vertex count;
neither is the PU-weight input. `Rho` is used for jet corrections, not PU weights.

Lepton SFs apply only to the event's chosen `TriggerLepton*`, not to every saved
lepton. Electron SFs use corrected pT and supercluster eta; muon SFs use active corrected pT and
signed eta. The bundled payloads are `2024_electron.json.gz`,
`2024_electronHlt.json.gz`, and `2024_muon_Z.json.gz`. If a lepton payload is
unavailable both locally and at its fallback path, processing fails. The 2024
runner checks the required payloads before starting the event loop.

2024 MC carries `WeightPrescriptionVersion=3` in Events and a `WeightMetadata`
tree containing the input PS/scale titles and the applied convention. These
identify the uncapped weights, signed scale ratios, shower-label meanings and
the muon efficiency uncertainty convention. Version 3 adds the top-pT formulas,
sample routing, validity rule and all-input/joint normalization contract.
Versions 1 and 2 remain readable separately; mixing versions is rejected.
The record survives empty selections, merging and forced normalization.
Merge and normalization reject a mixture with legacy output lacking this
record. Old and new output need separate denominators; regenerate from NanoAOD
to adopt the new convention. See [the weight realignment record](weight-realignment-2026-10-27.md)
and the [muon-uncertainty](cms-readiness-2026-10-27.md) and
[top-pT normalization](top-pt-normalization-2026-10-27.md) follow-ups.

## Second pass: `finalWeight`

1. [`condor/scripts/normalize.py`](../condor/scripts/normalize.py) gathers the
   ROOT files for one dataset's processed sample. It reads each file's
   `Norm/np_nominal`, using the matching batch pickle as a fallback. When both
   exist, their denominators must agree. A ROOT with neither source is an
   error; a pickle without a corresponding ROOT contributes nothing.
2. Sum these contributions into `global_np_nominal`, denoted D below. This
   denominator covers all processed input events represented by those files,
   including the events rejected before output.
3. Append the nominal `finalWeight` branch to each `Events` tree:

   ```text
   D = sum_jobs(np_nominal)
     = sum_all_processed_events(genWeight × PU)

   finalWeight = weight / D
               = C × genWeight × PU × SF_lepton / D

   predicted yield after any further analysis cuts
       = sum(finalWeight over events passing those cuts)
   ```

   Lepton SFs remain in the numerator because they correct selection
   efficiencies. They are excluded from D, so their yield correction is not
   divided away. Further analysis cuts do not redefine D.
4. Record D and a fingerprint of the contributing batch list in the ROOT
   `finalWeight_provenance` object and in `metadata/normalization.json`
   (`global_np_nominal`, `sigma_x_lumi`, `batches`, and `fingerprint`).

The second pass adds no further SF, top-pT factor, or luminosity factor.
It appends only nominal `finalWeight`; all first-pass weight branches retain
their original values. Every input weight and inferred sample scale is checked
before writing. Existing `finalWeight` branches are skipped only after their
values and provenance agree with the current D and batch fingerprint. If the
contributing files change, use `--force` to recompute all affected files;
an ordinary rerun rejects stale results. Signed and zero event weights are
retained; D must be finite and nonzero. The weighted selection fraction need
not lie between zero and one. See the
[normalization integrity record](normalization-integrity-2026-10-27.md).
Normalize `TTtoLNu2Q` and `TTtoLNuCB` separately, each with its own denominator.

## Other weight terms and saved alternatives

**PU, shower, and lepton SF variations**

With `--save-systematics`, the following complete first-pass alternative
weights are written. `{Up,Down}` means two branches. Each replaces one nominal
factor with its shifted value and already includes C and the other nominal
factors; it is not a bare up/down SF.

| Source | Output branches | Input variation | Denominator total saved in the pickle |
| --- | --- | --- | --- |
| Pileup | `weight_pileup{Up,Down}` | PU payload `up` / `down` | `np_pileup{Up,Down}` |
| ISR | `weight_ISRPartonShower{Up,Down}` | Four-entry `PSWeight`: indices 0 / 2 | `np_ISRPartonShower{Up,Down}` |
| FSR | `weight_FSRPartonShower{Up,Down}` | Four-entry `PSWeight`: indices 1 / 3 | `np_FSRPartonShower{Up,Down}` |
| Electron reconstruction | `weight_electron_reco{Up,Down}` | EGM `sfup` / `sfdown` | No separate total; use nominal D |
| Electron ID | `weight_electron_id{Up,Down}` | EGM `sfup` / `sfdown` | No separate total; use nominal D |
| Electron trigger | `weight_electron_trigger{Up,Down}` | EGM `sfup` / `sfdown` | No separate total; use nominal D |
| Muon ID | `weight_muon_id{Up,Down}` | MUO nominal ± sqrt(stat² + syst²) | No separate total; use nominal D |
| Muon isolation | `weight_muon_iso{Up,Down}` | MUO nominal ± sqrt(stat² + syst²) | No separate total; use nominal D |
| Muon trigger | `weight_muon_trigger{Up,Down}` | MUO nominal ± sqrt(stat² + syst²) | No separate total; use nominal D |

Versions 2 and 3 also save twelve complete event weights:
`weight_muon_{id,iso,trigger}_{stat,syst}{Up,Down}`. Each replaces that step's
nominal SF by nominal ± the named absolute error and uses nominal D. These
components are alternatives to the total uncertainty for that step; do not
count both models in the same fit. Correlations between bins remain a
downstream statistical-model decision. The June 2026 MUO payload includes
statistical uncertainty in ID/ISO `systup/down`, but omits it for IsoMu24.
Explicit `stat` and `syst` evaluation gives a consistent total for all three.
The dated payload and its decompressed SHA-256 are checked at load time.

For PU and shower variations, the corresponding `np_*` total sums the varied
`w_np` over all processed events. These totals must be combined across jobs
before normalizing those alternatives. `normalize.py` does not perform this
variation normalization. With `--no-save-systematics`, the nominal corrections
and `single_weight_*` fields still exist, but the branches in this table do not.
For the supported 2024 inputs, shower `Up` means muR multiplied by 2 and
`Down` means muR multiplied by 0.5. These names describe the scale, not the
amount of radiation. The runner verifies that interpretation against every
input branch title. An unknown layout, wrong per-event length or nonfinite
member stops processing; signed and zero ratios are retained.

**Renormalization/factorization scales and PDFs**

The 2024 ttbar skimmer requires `LHEScaleWeight` and writes `scale_weights0`
through `scale_weights5`, even with `--no-save-systematics`. Their
(muR, muF) multipliers are, in output order:
`(0.5, 0.5)`, `(0.5, 1)`, `(1, 0.5)`, `(1, 2)`, `(2, 1)`, `(2, 2)`.
For a nine-entry input, these use indices `[0, 1, 3, 5, 7, 8]` divided by
the central entry 4. For the eight-entry layout, they use indices
`[0, 1, 3, 4, 6, 7]`. Ratios retain their sign and magnitude without clipping.
Every file's title must identify the supported grid, and every event must
have the advertised number of finite members. A zero central member fails
instead of inventing a ratio.

Each saved `scale_weights{k}` equals the corresponding ratio times `weight`,
including C. The six matching denominator totals are stored as the array
`totals["np_scale_weights"]` in the pickle and `Norm/np_scale_weights` in ROOT. They are excluded from nominal
`weight` and `finalWeight`, and the second pass leaves these alternatives
unnormalized. Their normalization uses the matching global denominator total.

With `--save-systematics`, ttbar inputs retain `LHEPdfWeight` as raw ratios
`PDFWeight0`, `PDFWeight1`, ...; these are **not** multiplied by C or by nominal
event weights. Zero and negative members survive. Input branch titles identify
the LHA IDs and are checked against registered set metadata; every event's
length is checked. `PdfMetadata` records the mapping as UTF-8 JSON bytes in
`layout_utf8`. The signal fixture has 103 members (Hessian plus alpha-S), while
the measured TTBB pilot has a different 101-member Hessian set with no alpha-S
endpoints. Different sets must not be correlated by member index alone.

For member i, `Norm/np_pdf_weights[i]` and the corresponding pickle total store
`sum_all_input(genWeight * nominal_pileup * PDFWeight_i)`. Sum these over the
dataset and use `weight * PDFWeight_i / global_np_pdf_weights[i]` downstream.
The second pass still writes only nominal `finalWeight`; it does not normalize
the alternatives. Normalize templates before reducing Hessian directions.
Fit correlations and the alpha-S prior remain separate analysis choices.

**Top-pT reweighting**

All four `topPtWeight_*` branches are bare event factors. They are saved for
ttbar independently of `--save-systematics`, after the C multiplication, and
enter neither `weight`, `weight_noxsec`, `np_nominal`, nor `finalWeight`.
For each prescription, the event factor is `sqrt(f(pT_top) × f(pT_antitop))`,
using one hard-process, last-copy top and one antitop, with finite nonnegative
pT. `TopPtWeightValid` records that condition. Invalid pairs receive a factor
of 1 and remain in the all-input normalization, with separate validity counts.
This flag describes the generator pair, not the physics applicability of a fit.

| Output branch | Implemented per-top function f(pT), pT in GeV |
| --- | --- |
| `topPtWeight_dataNLO` | `exp(0.0615 - 0.0005 × pT)`; pT clipped to [0, 500] |
| `topPtWeight_dataNNLO` | `exp(0.0416 - 0.0003 × pT)`; pT clipped to [0, 500] |
| `topPtWeight_NNLONLO` | `0.103 × exp(-0.0118 × pT) - 0.000134 × pT + 0.973`; pT clipped to [0, 2000] |
| `topPtWeight_NNLONLO_13p6TeV` | The preceding function times `(0.991 + 0.000075 × pT)`, with the same clipping |

`topPtWeight_NNLONLO_13p6TeV` is the stored Run 3 extrapolation; the other
columns retain 13 TeV prescriptions for comparison. Their application remains
an analysis choice, including for dedicated TTBB samples. The associated saved
top momenta are `GenTopPt0` and `GenTopPt1`.

Version 3 saves `Norm/np_topPtWeight_<model> = sum_all_input(genWeight × PU × T)`
for each factor T, without lepton efficiencies or C. To preserve the inclusive
normalization when adopting T, use `weight × T / D_T`, where D_T is that sum
across every input batch. Equivalently, use `finalWeight × T × D / D_T`.
Multiplying only `finalWeight × T` changes the inclusive normalization.
The processor leaves nominal `weight` and `finalWeight` unchanged.

Joint sums also cover the six LHE scales and, under `--save-systematics`,
PU, shower and PDF alternatives. They retain signed and zero members. Each
joint numerator must use its matching global denominator; lepton efficiency
alternatives use D_T. `normalize.py` reports all these sums in
`metadata/normalization.json/global_top_pt_sums`, while appending only nominal
`finalWeight`. Exact names and formulas are in the
[top-pT record](top-pt-normalization-2026-10-27.md).

**Terms not implemented as event-weight factors**

There are no b-tag/c-tag/charge-tag SFs, pileup-jet-ID SFs, separate muon
reconstruction SFs, prefiring weights, or luminosity uncertainty branches in
this ttbar path. Electron and muon momentum corrections, nominal jet JEC/JER, MET
rebuilding, jet-veto maps, trigger requirements, and object cuts can change
acceptance or the kinematics used to evaluate SFs; they add no independent
multiplicative event factor. Electron pT alternatives are listed in
[object-synopsis.md](object-synopsis.md#electrons).

Implementation references:
[`vcbSkimmer.py`](../src/vcb/processors/vcbSkimmer.py),
[`lepton_sf.py`](../src/vcb/processors/lepton_sf.py),
[`corrections.py`](../src/boostedhh/processors/corrections.py),
[`top_pt.py`](../src/vcb/processors/top_pt.py), and
[`run_utils.py`](../src/boostedhh/run_utils.py).
