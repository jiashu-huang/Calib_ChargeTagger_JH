"""
Round-trip check: every saved AK4 jet must carry its input jet's tagger scores.

For each event in a skim output file this locates the same event in the source
NanoAOD (by run / luminosityBlock / event) and, for every saved jet, compares
the charge- and flavor-tagger branches against the input jet they came from.
Output slots are matched to input jets by eta/phi, which JECs leave untouched,
so the match is exact rather than nearest-neighbour.

The skimmer also *saves* that correspondence, as `ak4JetNanoIdx`. This script
deliberately does not use it to do the matching -- the whole point is to
re-derive the correspondence from the NanoAOD rather than trust it -- but it
does compare the two afterwards, which turns the eta/phi match into an
independent check that the saved index is right. Output files written before
that column existed simply skip the comparison.

Input jets that never reach the output are classified rather than ignored. The
skimmer drops a jet for exactly five reasons -- it sits within dR <= 0.4 of the
trigger lepton used for cleaning, it fails corrected pT > 15 GeV or
|eta| < 4.7, it fails the Run-3 AK4 PUPPI Tight jet ID, or, in an event with
more than ten selected jets, it did not rank among the ten highest corrected
pT -- so anything left over is a real finding.

The saved slots are additionally required to be in descending corrected pT,
which is what makes the last of those reasons well defined.

The corrected pT is not stored for dropped jets, so by default this recomputes
it with the same JEC/JER machinery the skimmer used (deterministic, and
verified here to reproduce the saved pT bit for bit). That makes every reason
exact; `--no-jec` skips it and leaves the pT cut unverified.

Everything lands in a single .txt report.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import awkward as ak
import numpy as np
import uproot

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTFILE_DIR = PROJECT_ROOT / "tests" / "outfile"
DEFAULT_OUTPUT_FILE = OUTFILE_DIR / "test-output.root"
DEFAULT_INPUT_FILE = PROJECT_ROOT / "tests" / "data" / "test-input.root"
DEFAULT_REPORT = OUTFILE_DIR / "test-jet-tagger-roundtrip.txt"
DEFAULT_TREE = "Events"
DEFAULT_YEAR = "2024"
DEFAULT_CHUNK_SIZE = 50000

PAD_VAL = -99999.0
NUM_AK4_SLOTS = 10
# Mirrors objects.good_ak4jets: kept if pt > 15, |eta| < 4.7 and every cleaning
# lepton is farther than dR 0.4. A jet exactly on a boundary is dropped.
JET_CLEANING_DR = 0.4
JET_ETA_MAX = 4.7
JET_PT_MIN = 15.0
# Output eta/phi are float32 input values widened to float64, so the match is
# exact; the tolerance only exists so a future eta-changing correction degrades
# to a nearest-jet match with a reported dR instead of a silent failure.
MATCH_DR_TOL = 1e-6
# Provenance column written by the skimmer: the slot's index in the input
# `Jet` collection. Optional here so this script still runs against output
# produced before it was added.
NANO_IDX_FIELD = "NanoIdx"

# Inputs to the Run-3 AK4 PUPPI Tight jet ID, reimplemented in _passes_jet_id
# below. Deliberately a second, independent transcription of the thresholds
# rather than an import of objects.ak4_jet_id -- the whole point of this script
# is to re-derive the skimmer's selection from the NanoAOD, not to trust it.
# (objects.ak4_jet_id is separately checked against JME's jetid.json payload in
# tests/test_objects.py; these two agreeing is what makes the count exact.)
JET_ID_BRANCHES = (
    "Jet_chHEF",
    "Jet_neHEF",
    "Jet_neEmEF",
    "Jet_chMultiplicity",
    "Jet_neMultiplicity",
)

# Compared fields: "<output branch suffix>": "<input Jet_ branch suffix>".
# Every tagger discriminant `vcbSkimmer.skim_vars["Jet"]` saves appears here --
# a score that is written but never round-tripped is a score nothing would catch
# being attached to the wrong jet, which is the one failure this script exists
# to find. Keep the two lists in step when either changes.
TAGGER_FIELD_MAP = {
    # Charge-tagger heads (CMSSW_15_CHARGE) -- the calibration target.
    "ParTNegvsAll": "ParTNegvsAll",
    "ParTPosvsAll": "ParTPosvsAll",
    "ParTPosvsNeg": "ParTPosvsNeg",
    "ParTZerovsAll": "ParTZerovsAll",
    # UnifiedParT -- the tagger BTV calibrates for 2024.
    "btagUParTAK4B": "btagUParTAK4B",
    "btagUParTAK4CvB": "btagUParTAK4CvB",
    "btagUParTAK4CvL": "btagUParTAK4CvL",
    "btagUParTAK4CvNotB": "btagUParTAK4CvNotB",
    "btagUParTAK4QvG": "btagUParTAK4QvG",
    # ParticleNet + RobustParT -- uncalibrated for 2024, kept as ML inputs.
    "btagPNetB": "btagPNetB",
    "btagPNetCvB": "btagPNetCvB",
    "btagPNetCvL": "btagPNetCvL",
    "btagPNetCvNotB": "btagPNetCvNotB",
    "btagPNetQvG": "btagPNetQvG",
    "btagRobustParTAK4B": "btagRobustParTAK4B",
}

# The Qk jet charges live in the separate `JetQk` flat table, which the fork
# builds from the *unfiltered* jet collection -- so it is a superset of `Jet`,
# and the skimmer relies on `JetQk[i] <-> Jet[i]` holding over the first nJet
# entries (see objects.attach_jet_charge for why that is sound). Comparing them
# here re-derives that same slice straight from the NanoAOD, so it verifies the
# skimmer's plumbing -- that the charge rode through JEC, selection, cleaning
# and slot padding still attached to its own jet. It does not independently
# re-prove the prefix assumption itself; both sides make it.
#
# The output suffixes carry a trailing underscore that the input branches do not
# -- these are the only saved fields whose name ends in a digit, so the skimmer
# separates them from the slot index to keep `ak4JetQkCharge05_7` unambiguous.
# This is the one place in this file where the output and input names differ.
JET_CHARGE_FIELD_MAP = {
    "QkCharge05_": "QkCharge05",
    "QkCharge10_": "QkCharge10",
}

# Everything compared per matched slot, whichever collection it came from.
COMPARED_FIELDS = {**TAGGER_FIELD_MAP, **JET_CHARGE_FIELD_MAP}
# Once sliced to the Jet prefix, the JetQk columns are relabelled into the Jet_
# namespace under their *input* name, so the comparison loop's generic
# `Jet_{COMPARED_FIELDS[field]}` lookup reads them exactly like a tagger branch.
CHARGE_AS_JET_BRANCHES = [f"Jet_{name}" for name in JET_CHARGE_FIELD_MAP.values()]

# Why an input jet can be absent from the output, in the order tested. A jet may
# fail several cuts at once; it is counted under the first that applies, and
# lepton cleaning leads because that is the reason this check exists to confirm.
MISSING_REASONS = (
    "lepton_cleaned",
    "pt_below_threshold",
    "eta_out_of_range",
    "failed_jet_id",
    "truncated_beyond_slots",
    "UNEXPLAINED",
)
REASON_NOTES = {
    "lepton_cleaned": f"dR <= {JET_CLEANING_DR} of the trigger lepton",
    "pt_below_threshold": f"corrected pT <= {JET_PT_MIN} GeV",
    "eta_out_of_range": f"|eta| >= {JET_ETA_MAX}",
    "failed_jet_id": "fails the Run-3 AK4 PUPPI Tight jet ID",
    "truncated_beyond_slots": (
        f"passed selection, but was not among the {NUM_AK4_SLOTS} highest "
        f"corrected pT of an event with > {NUM_AK4_SLOTS} selected jets"
    ),
    "UNEXPLAINED": "no known reason -- investigate",
}
PT_UNVERIFIED_NOTE = "not verified (--no-jec): assumed to fail the corrected-pT cut"


def _display_path(path: Path) -> str:
    """Repo-relative when possible, so the report is comparable across machines."""
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _delta_r(eta1, phi1, eta2, phi2):
    deta = eta1 - eta2
    dphi = (phi1 - phi2 + np.pi) % (2 * np.pi) - np.pi
    return np.hypot(deta, dphi)


def _passes_jet_id(fractions: dict[str, np.ndarray], start: int, stop: int) -> np.ndarray:
    """
    Run-3 AK4 PUPPI Tight jet ID for one event's slice of the flat jet arrays.

    Four |eta| regions, tracking the detector: inside the tracker (< 2.6) the
    charged-hadron and multiplicity cuts apply; 2.6-2.7 and 2.7-3.0 progressively
    drop them as tracking runs out; beyond 3.0 the HF gets its own pair of cuts.
    Bins are half-open, matching JME's payload (chHEF exactly 0.01 passes).
    """
    eta = np.abs(fractions["Jet_eta"][start:stop])
    ch_hef = fractions["Jet_chHEF"][start:stop]
    ne_hef = fractions["Jet_neHEF"][start:stop]
    ne_em_ef = fractions["Jet_neEmEF"][start:stop]
    # uint8 in NanoAOD; widen before summing so the total cannot wrap at 255.
    ch_mult = fractions["Jet_chMultiplicity"][start:stop].astype(np.int32)
    ne_mult = fractions["Jet_neMultiplicity"][start:stop].astype(np.int32)

    tracker = (
        (ch_hef >= 0.01)
        & (ne_hef < 0.99)
        & (ne_em_ef < 0.90)
        & (ch_mult >= 1)
        & (ch_mult + ne_mult >= 2)
    )
    transition = (ne_hef < 0.90) & (ne_em_ef < 0.99)
    hetohf = ne_hef < 0.99
    forward = (ne_em_ef < 0.40) & (ne_mult >= 2)

    return np.where(
        eta < 2.6, tracker, np.where(eta < 2.7, transition, np.where(eta < 3.0, hetohf, forward))
    )


def resolve_input_files(paths: list[Path]) -> list[Path]:
    """
    Expand the --input-file arguments into a sorted list of ROOT files.

    A Condor job skims a whole `batch_*` directory, so accepting a directory
    (or several files) is what makes this runnable against real batch output
    rather than only the single-file test fixture.
    """
    resolved: list[Path] = []
    for path in paths:
        path = Path(path).expanduser().resolve()
        if path.is_dir():
            found = sorted(path.glob("*.root"))
            if not found:
                raise FileNotFoundError(f"No .root files in {path}")
            resolved.extend(found)
        else:
            resolved.append(path)
    if not resolved:
        raise FileNotFoundError("No input files given.")
    return resolved


def _build_input_index(tree, entry_offset: int = 0) -> dict[tuple[int, int, int], int]:
    """Map (run, luminosityBlock, event) -> global input entry number."""
    ids = tree.arrays(["run", "luminosityBlock", "event"], library="np")
    index = {
        (int(run), int(lumi), int(event)): entry_offset + entry
        for entry, (run, lumi, event) in enumerate(
            zip(ids["run"], ids["luminosityBlock"], ids["event"])
        )
    }
    if len(index) != tree.num_entries:
        raise RuntimeError(
            f"Input tree has {tree.num_entries} entries but only {len(index)} unique "
            "(run, luminosityBlock, event) keys; cannot match events unambiguously."
        )
    return index


def _flatten_jagged(array: ak.Array) -> tuple[np.ndarray, np.ndarray]:
    """Return (flat values, offsets) so per-event slices are plain numpy views."""
    counts = ak.to_numpy(ak.num(array))
    offsets = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)
    return ak.to_numpy(ak.flatten(array)).astype(np.float64), offsets


def recompute_corrected_pt(
    input_files: list[Path],
    tree_name: str,
    year: str,
    offsets: np.ndarray,
    file_event_starts: list[int],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> np.ndarray:
    """
    Re-apply the skimmer's JEC/JER to every input jet and return the corrected
    pT flattened onto the same offsets as the raw input jet arrays.

    The corrections are deterministic (the JER smearing is seeded from the event
    content, not from a global RNG), so this reproduces the pT the skimmer saved
    exactly -- which the caller then asserts on the matched jets.
    """
    from coffea.nanoevents import NanoAODSchema, NanoEventsFactory

    from boostedhh.processors import utils
    from boostedhh.processors.corrections import JECs

    NanoAODSchema.warn_missing_crossrefs = False

    corrected = np.empty(offsets[-1], dtype=np.float64)
    jec_loader = JECs(year)

    for file_index, input_file in enumerate(input_files):
        base = file_event_starts[file_index]
        n_file_events = file_event_starts[file_index + 1] - base
        with uproot.open(input_file) as root_file:
            is_data = "genWeight" not in root_file[tree_name].keys()

        for local_start in range(0, n_file_events, chunk_size):
            local_stop = min(local_start + chunk_size, n_file_events)
            events = NanoEventsFactory.from_root(
                str(input_file),
                treepath=tree_name,
                schemaclass=NanoAODSchema,
                entry_start=local_start,
                entry_stop=local_stop,
                metadata={"dataset": f"{year}_TTtoLNuCB"},
            ).events()
            jets, _ = jec_loader.get_jec_jets(
                events,
                events.Jet,
                year,
                is_data,
                jecs=utils.jecs,
                fatjets=False,
                applyData=True,
                dataset="TTtoLNuCB",
                nano_version="v12_private",
            )
            start, stop = base + local_start, base + local_stop
            chunk_counts = ak.to_numpy(ak.num(jets.pt))
            expected = np.diff(offsets[start : stop + 1])
            if not np.array_equal(chunk_counts, expected):
                raise RuntimeError(
                    f"Jet counts disagree between the uproot and coffea reads over "
                    f"{input_file} entries [{local_start}, {local_stop}); "
                    "cannot align the recomputed pT."
                )
            corrected[offsets[start] : offsets[stop]] = ak.to_numpy(ak.flatten(jets.pt))

    return corrected


def _values_agree(output_value: float, input_value: float) -> bool:
    if np.isnan(output_value) and np.isnan(input_value):
        return True
    return bool(output_value == input_value)


def check_jet_tagger_roundtrip(
    output_file: Path = DEFAULT_OUTPUT_FILE,
    input_file: Path | list[Path] = DEFAULT_INPUT_FILE,
    report_path: Path = DEFAULT_REPORT,
    tree_name: str = DEFAULT_TREE,
    year: str = DEFAULT_YEAR,
    verify_jec: bool = True,
    max_anomalies: int = 200,
) -> dict:
    output_file = Path(output_file).expanduser().resolve()
    input_files = resolve_input_files(
        input_file if isinstance(input_file, (list, tuple)) else [input_file]
    )
    report_path = Path(report_path).expanduser().resolve()

    slot_branches = [
        f"ak4Jet{field}{slot}"
        for field in ("Pt", "Eta", "Phi", *COMPARED_FIELDS)
        for slot in range(NUM_AK4_SLOTS)
    ]
    event_branches = [
        "run",
        "luminosityBlock",
        "event",
        "nJets",
        "TriggerLeptonFlav",
        "TriggerLeptonEta",
        "TriggerLeptonPhi",
    ]

    index_branches = [f"ak4Jet{NANO_IDX_FIELD}{slot}" for slot in range(NUM_AK4_SLOTS)]

    with uproot.open(output_file) as root_file:
        out_tree = root_file[tree_name]
        out_branches = set(out_tree.keys())
        missing = [name for name in event_branches + slot_branches if name not in out_branches]
        if missing:
            raise KeyError(
                f"Missing required branch(es) in {output_file}: {', '.join(sorted(missing))}"
            )
        # All-or-nothing: a file carrying only some of the ten slot columns is
        # malformed, not merely old, so say which ones are missing.
        present_index = [name for name in index_branches if name in out_branches]
        if present_index and len(present_index) != len(index_branches):
            raise KeyError(
                f"{output_file} has only {len(present_index)}/{len(index_branches)} "
                f"ak4Jet{NANO_IDX_FIELD} slot branches; missing "
                f"{', '.join(sorted(set(index_branches) - set(present_index)))}"
            )
        has_index = bool(present_index)
        out = out_tree.arrays(
            event_branches + slot_branches + (index_branches if has_index else []), library="np"
        )
        n_out_events = out_tree.num_entries

    if n_out_events <= 0:
        raise ValueError(f"{output_file} has no events.")

    input_jet_branches = (
        ["Jet_pt", "Jet_eta", "Jet_phi"]
        + list(JET_ID_BRANCHES)
        + [f"Jet_{name}" for name in TAGGER_FIELD_MAP.values()]
    )
    input_charge_branches = [f"JetQk_{name}" for name in JET_CHARGE_FIELD_MAP.values()]
    # A Condor job skims several input files into one output, so the index and
    # the jet arrays span every input file, concatenated in the given order.
    entry_of: dict[tuple[int, int, int], int] = {}
    file_event_starts = [0]
    per_file_jets = []
    for path in input_files:
        with uproot.open(path) as root_file:
            in_tree = root_file[tree_name]
            missing = [
                name
                for name in input_jet_branches + input_charge_branches
                if name not in in_tree.keys()
            ]
            if missing:
                raise KeyError(
                    f"Missing required branch(es) in {path}: {', '.join(sorted(missing))}"
                )
            file_index = _build_input_index(in_tree, entry_offset=file_event_starts[-1])
            overlap = entry_of.keys() & file_index.keys()
            if overlap:
                raise RuntimeError(
                    f"{path} repeats {len(overlap)} (run, luminosityBlock, event) key(s) "
                    "already seen in an earlier input file. Overlapping inputs would make "
                    "the skimmer process the same events twice; check for a merged copy "
                    "sitting inside the batch directory."
                )
            entry_of.update(file_index)
            file_event_starts.append(file_event_starts[-1] + in_tree.num_entries)
            chunk = in_tree.arrays(input_jet_branches + input_charge_branches, library="ak")
            # Cut `JetQk` down to the `Jet` prefix so it shares Jet's offsets,
            # then rename it into the Jet_ namespace the comparison loop reads.
            n_jet = ak.num(chunk["Jet_pt"])
            if ak.any(ak.num(chunk[input_charge_branches[0]]) < n_jet):
                raise RuntimeError(
                    f"{path}: JetQk is shorter than Jet in some events; the positional "
                    "prefix match the skimmer relies on does not hold there."
                )
            for in_name in JET_CHARGE_FIELD_MAP.values():
                column = chunk[f"JetQk_{in_name}"]
                chunk[f"Jet_{in_name}"] = column[ak.local_index(column) < n_jet]
            per_file_jets.append(chunk[input_jet_branches + CHARGE_AS_JET_BRANCHES])

    n_in_events = file_event_starts[-1]
    jets = per_file_jets[0] if len(per_file_jets) == 1 else ak.concatenate(per_file_jets)
    del per_file_jets

    in_flat = {}
    offsets = None
    for name in input_jet_branches + CHARGE_AS_JET_BRANCHES:
        in_flat[name], offsets = _flatten_jagged(jets[name])
    del jets

    corrected_pt = (
        recompute_corrected_pt(input_files, tree_name, year, offsets, file_event_starts)
        if verify_jec
        else None
    )

    # Stack the per-slot output columns into (n_events, NUM_AK4_SLOTS) blocks.
    def slot_block(field: str) -> np.ndarray:
        return np.stack(
            [np.asarray(out[f"ak4Jet{field}{s}"], dtype=np.float64) for s in range(NUM_AK4_SLOTS)],
            axis=1,
        )

    out_pt = slot_block("Pt")
    out_eta = slot_block("Eta")
    out_phi = slot_block("Phi")
    out_tagger = {field: slot_block(field) for field in COMPARED_FIELDS}
    out_nano_idx = slot_block(NANO_IDX_FIELD) if has_index else None

    n_jets_branch = np.asarray(out["nJets"], dtype=np.int64)
    trig_flav = np.asarray(out["TriggerLeptonFlav"], dtype=np.int64)
    trig_eta = np.asarray(out["TriggerLeptonEta"], dtype=np.float64)
    trig_phi = np.asarray(out["TriggerLeptonPhi"], dtype=np.float64)

    stats = {
        "events_checked": 0,
        "events_missing_from_input": 0,
        "events_without_trigger_lepton": 0,
        "events_njets_disagree": 0,
        "events_slots_out_of_order": 0,
        "slots_filled": 0,
        "slots_matched": 0,
        "slots_unmatched": 0,
        "slots_pt_disagree": 0,
        "slots_index_disagree": 0,
        "comparisons": 0,
        "comparisons_differing": 0,
    }
    missing_counts = dict.fromkeys(MISSING_REASONS, 0)
    max_match_dr = 0.0
    anomalies: dict[str, list[str]] = {
        "missing_events": [],
        "unmatched_slots": [],
        "pt_disagree": [],
        "index_disagree": [],
        "slots_out_of_order": [],
        "njets_disagree": [],
        "value_mismatches": [],
        "unexplained": [],
    }

    def record(bucket: str, message: str) -> None:
        if len(anomalies[bucket]) < max_anomalies:
            anomalies[bucket].append(message)

    for i in range(n_out_events):
        key = (int(out["run"][i]), int(out["luminosityBlock"][i]), int(out["event"][i]))
        entry = entry_of.get(key)
        tag = f"run={key[0]} lumi={key[1]} event={key[2]}"
        if entry is None:
            stats["events_missing_from_input"] += 1
            record("missing_events", f"{tag}: not present in the input file")
            continue
        stats["events_checked"] += 1

        start, stop = offsets[entry], offsets[entry + 1]
        in_eta = in_flat["Jet_eta"][start:stop]
        in_phi = in_flat["Jet_phi"][start:stop]
        in_pt = in_flat["Jet_pt"][start:stop]
        in_jet_id = _passes_jet_id(in_flat, start, stop)
        n_in_jets = stop - start

        has_trig_lepton = trig_flav[i] != int(PAD_VAL)
        if not has_trig_lepton:
            stats["events_without_trigger_lepton"] += 1

        dr_lepton = (
            _delta_r(in_eta, in_phi, trig_eta[i], trig_phi[i])
            if has_trig_lepton
            else np.full(n_in_jets, np.inf)
        )

        matched_input = np.zeros(n_in_jets, dtype=bool)

        # The saved slots must be in descending corrected pT. Checked from the
        # output alone -- it is a property of the file, independent of whether
        # the input can be matched -- and it is also what makes
        # `truncated_beyond_slots` below a statement rather than a guess.
        filled_pt = out_pt[i][out_pt[i] != PAD_VAL]
        if filled_pt.size > 1 and np.any(np.diff(filled_pt) > 0):
            stats["events_slots_out_of_order"] += 1
            record(
                "slots_out_of_order",
                f"{tag}: saved slot pT is not descending: "
                + ", ".join(f"{v:.4f}" for v in filled_pt),
            )
        # Every filled slot is at or above this, so an input jet that passes the
        # selection and sits below it is one the truncation dropped.
        min_saved_pt = float(filled_pt.min()) if filled_pt.size else np.inf

        for slot in range(NUM_AK4_SLOTS):
            if out_pt[i, slot] == PAD_VAL:
                continue
            stats["slots_filled"] += 1

            if n_in_jets == 0:
                stats["slots_unmatched"] += 1
                record("unmatched_slots", f"{tag} slot={slot}: input event has no jets")
                continue

            dr = _delta_r(in_eta, in_phi, out_eta[i, slot], out_phi[i, slot])
            j = int(np.argmin(dr))
            if dr[j] > MATCH_DR_TOL:
                stats["slots_unmatched"] += 1
                record(
                    "unmatched_slots",
                    f"{tag} slot={slot}: no input jet within dR {MATCH_DR_TOL:g} "
                    f"(closest input jet {j}, dR={dr[j]:.6g}, output eta/phi="
                    f"{out_eta[i, slot]:.6g}/{out_phi[i, slot]:.6g})",
                )
                continue

            stats["slots_matched"] += 1
            max_match_dr = max(max_match_dr, float(dr[j]))
            matched_input[j] = True

            # The saved provenance index must name the same input jet that the
            # eta/phi match just found. The two are derived independently -- the
            # skimmer captures the index before any reordering, this script
            # re-derives the correspondence from the geometry -- so agreement is
            # a real check on the column rather than a tautology.
            if out_nano_idx is not None and int(out_nano_idx[i, slot]) != j:
                stats["slots_index_disagree"] += 1
                record(
                    "index_disagree",
                    f"{tag} slot={slot}: saved ak4Jet{NANO_IDX_FIELD}="
                    f"{int(out_nano_idx[i, slot])} but eta/phi matches input jet {j}",
                )

            if corrected_pt is not None and corrected_pt[start + j] != out_pt[i, slot]:
                stats["slots_pt_disagree"] += 1
                record(
                    "pt_disagree",
                    f"{tag} slot={slot} input jet {j}: saved pT={out_pt[i, slot]!r} "
                    f"recomputed pT={corrected_pt[start + j]!r}",
                )

            for field in COMPARED_FIELDS:
                stats["comparisons"] += 1
                output_value = out_tagger[field][i, slot]
                # Charge columns were relabelled into the Jet_ namespace above,
                # so both kinds of field are read the same way here.
                input_value = in_flat[f"Jet_{COMPARED_FIELDS[field]}"][start + j]
                if not _values_agree(output_value, input_value):
                    stats["comparisons_differing"] += 1
                    record(
                        "value_mismatches",
                        f"{tag} slot={slot} input jet {j} {field}: "
                        f"output={output_value!r} input={input_value!r} "
                        f"diff={output_value - input_value!r}",
                    )

        for j in np.flatnonzero(~matched_input):
            if dr_lepton[j] <= JET_CLEANING_DR:
                reason = "lepton_cleaned"
            elif corrected_pt is None or corrected_pt[start + j] <= JET_PT_MIN:
                # Without the recomputed pT this is an assumption, not a result;
                # the report says so and the verdict is downgraded accordingly.
                reason = "pt_below_threshold"
            elif abs(in_eta[j]) >= JET_ETA_MAX:
                reason = "eta_out_of_range"
            elif not in_jet_id[j]:
                reason = "failed_jet_id"
            elif n_jets_branch[i] > NUM_AK4_SLOTS and corrected_pt[start + j] <= min_saved_pt:
                # Slots are pT-sorted, so a selected jet the output does not
                # carry is the truncation's doing exactly when it is no harder
                # than the softest jet that was kept. (This branch is only
                # reachable with the recomputed pT -- without it the elif above
                # has already claimed every unmatched jet.)
                reason = "truncated_beyond_slots"
            else:
                reason = "UNEXPLAINED"
                dr_text = "no trigger lepton" if not has_trig_lepton else f"{dr_lepton[j]:.4f}"
                pt_text = (
                    "" if corrected_pt is None else f" corrected pt={corrected_pt[start + j]:.4f}"
                )
                record(
                    "unexplained",
                    f"{tag} input jet {j}: raw pt={in_pt[j]:.4f}{pt_text} "
                    f"eta={in_eta[j]:.4f} phi={in_phi[j]:.4f} "
                    f"dR(trigger lepton)={dr_text} nJets={n_jets_branch[i]}",
                )
            missing_counts[reason] += 1

        # Independent cross-check of the saved nJets against the selection the
        # skimmer says it applied. Only meaningful with the recomputed pT.
        if corrected_pt is not None:
            selected = (
                (corrected_pt[start:stop] > JET_PT_MIN)
                & (np.abs(in_eta) < JET_ETA_MAX)
                & (dr_lepton > JET_CLEANING_DR)
                & in_jet_id
            )
            if int(np.count_nonzero(selected)) != int(n_jets_branch[i]):
                stats["events_njets_disagree"] += 1
                record(
                    "njets_disagree",
                    f"{tag}: saved nJets={n_jets_branch[i]} but "
                    f"{int(np.count_nonzero(selected))} input jets pass the selection",
                )

    if stats["slots_matched"] == 0:
        raise RuntimeError("No output jet slot could be matched to an input jet.")

    passed = (
        stats["events_missing_from_input"] == 0
        and stats["slots_unmatched"] == 0
        and stats["slots_pt_disagree"] == 0
        and stats["slots_index_disagree"] == 0
        and stats["events_slots_out_of_order"] == 0
        and stats["events_njets_disagree"] == 0
        and stats["comparisons_differing"] == 0
        and missing_counts["UNEXPLAINED"] == 0
    )

    report = _format_report(
        output_file=output_file,
        input_files=input_files,
        tree_name=tree_name,
        year=year,
        verify_jec=corrected_pt is not None,
        n_out_events=n_out_events,
        n_in_events=n_in_events,
        stats=stats,
        max_match_dr=max_match_dr,
        missing_counts=missing_counts,
        anomalies=anomalies,
        max_anomalies=max_anomalies,
        has_index=has_index,
        passed=passed,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)

    return {
        "report": str(report_path),
        "passed": passed,
        "verify_jec": corrected_pt is not None,
        "has_index": has_index,
        **stats,
        "missing_counts": missing_counts,
    }


def _format_report(**ctx) -> str:
    stats = ctx["stats"]
    missing_counts = ctx["missing_counts"]
    verify_jec = ctx["verify_jec"]
    has_index = ctx["has_index"]
    rule = "-" * 78
    no_index_note = f"   (no ak4Jet{NANO_IDX_FIELD} in this file)"

    jec_line = (
        f"JEC/JER recomputed for year {ctx['year']} -- dropped jets get an exact reason"
        if verify_jec
        else "JEC/JER NOT recomputed (--no-jec) -- the corrected-pT cut is assumed, not checked"
    )

    lines = [
        "AK4 jet tagger round-trip check: skim output vs. NanoAOD input",
        "=" * 78,
        f"output file : {_display_path(ctx['output_file'])}",
        "input files : "
        + f"{len(ctx['input_files'])} file(s)\n"
        + "\n".join(f"              {_display_path(p)}" for p in ctx["input_files"]),
        f"tree        : {ctx['tree_name']}",
        "fields      : " + ", ".join(f"ak4Jet{field}" for field in COMPARED_FIELDS),
        f"mode        : {jec_line}",
        "",
        "Events",
        rule,
        f"  in the output file                 : {ctx['n_out_events']}",
        f"  in the input file                  : {ctx['n_in_events']}",
        f"  matched to an input event          : {stats['events_checked']}",
        f"  NOT found in the input file        : {stats['events_missing_from_input']}",
        f"  with no trigger lepton (PAD_VAL)   : {stats['events_without_trigger_lepton']}"
        "   (no jet cleaning applied)",
        f"  saved nJets != jets passing the cuts: {stats['events_njets_disagree']}"
        + ("" if verify_jec else "   (not checked without the recomputed pT)"),
        f"  saved slots NOT in descending pT   : {stats['events_slots_out_of_order']}",
        "",
        "Saved jet slots",
        rule,
        f"  filled slots checked               : {stats['slots_filled']}",
        f"  matched to an input jet            : {stats['slots_matched']}"
        f"   (max dR {ctx['max_match_dr']:g})",
        f"  with NO input jet match            : {stats['slots_unmatched']}",
        f"  saved pT != recomputed pT          : {stats['slots_pt_disagree']}"
        + ("" if verify_jec else "   (not checked without the recomputed pT)"),
        f"  saved NanoIdx != eta/phi match     : {stats['slots_index_disagree']}"
        + ("" if has_index else no_index_note),
        "",
        f"Tagger + jet-charge comparisons ({len(COMPARED_FIELDS)} fields x matched slot)",
        rule,
        f"  comparisons made                   : {stats['comparisons']}",
        "  identical                          : "
        f"{stats['comparisons'] - stats['comparisons_differing']}",
        f"  DIFFERING                          : {stats['comparisons_differing']}",
        "",
        "Input jets absent from the output",
        rule,
        f"  total                              : {sum(missing_counts.values())}",
    ]
    for reason in MISSING_REASONS:
        note = REASON_NOTES[reason]
        if reason == "pt_below_threshold" and not verify_jec:
            note = PT_UNVERIFIED_NOTE
        lines.append(f"    {reason:<33}: {missing_counts[reason]}   ({note})")
    lines += [
        "",
        "  A jet can fail several cuts at once; it is counted under the first",
        "  reason in the list above that applies to it.",
        "",
    ]

    sections = (
        ("Events not found in the input file", "missing_events", stats["events_missing_from_input"]),
        ("Output jet slots with no input match", "unmatched_slots", stats["slots_unmatched"]),
        ("Saved pT disagreeing with the recomputed pT", "pt_disagree", stats["slots_pt_disagree"]),
        (
            f"Saved ak4Jet{NANO_IDX_FIELD} disagreeing with the eta/phi match",
            "index_disagree",
            stats["slots_index_disagree"],
        ),
        (
            "Events whose saved slots are not in descending pT",
            "slots_out_of_order",
            stats["events_slots_out_of_order"],
        ),
        ("Events where nJets disagrees with the selection", "njets_disagree", stats["events_njets_disagree"]),
        ("Tagger value mismatches", "value_mismatches", stats["comparisons_differing"]),
        ("Absent input jets with no known reason", "unexplained", missing_counts["UNEXPLAINED"]),
    )
    for title, bucket, total in sections:
        if total == 0:
            continue
        entries = ctx["anomalies"][bucket]
        lines += [title, rule]
        lines += [f"  {entry}" for entry in entries]
        if total > len(entries):
            lines.append(f"  ... {total - len(entries)} more (raise --max-anomalies to see them)")
        lines.append("")

    lines += ["=" * 78, f"VERDICT: {'PASS' if ctx['passed'] else 'FAIL'}"]
    return "\n".join(lines) + "\n"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check that every saved AK4 jet carries the tagger scores of the input "
            "jet it came from, and that every dropped input jet has a known reason."
        )
    )
    parser.add_argument("--output-file", type=Path, default=DEFAULT_OUTPUT_FILE)
    parser.add_argument(
        "--input-file",
        type=Path,
        nargs="+",
        default=[DEFAULT_INPUT_FILE],
        help="Source NanoAOD file(s), or a directory of them. Pass every input file "
        "that fed the output: a Condor job skims a whole batch_* directory.",
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--tree-name", default=DEFAULT_TREE)
    parser.add_argument(
        "--year",
        default=DEFAULT_YEAR,
        help=f"Data-taking year, for the JEC/JER recompute. Default: {DEFAULT_YEAR}",
    )
    parser.add_argument(
        "--no-jec",
        dest="verify_jec",
        action="store_false",
        help="Skip the JEC/JER recompute. Faster, but the corrected-pT cut is then "
        "assumed rather than verified, and nJets is not cross-checked.",
    )
    parser.add_argument(
        "--max-anomalies",
        type=int,
        default=200,
        help="Maximum number of entries to list per anomaly section. Default: 200",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    result = check_jet_tagger_roundtrip(
        output_file=args.output_file,
        input_file=args.input_file,
        report_path=args.report,
        tree_name=args.tree_name,
        year=args.year,
        verify_jec=args.verify_jec,
        max_anomalies=args.max_anomalies,
    )
    print(f"Report: {result['report']}")
    print(f"Events checked: {result['events_checked']}")
    print(f"Jet slots matched: {result['slots_matched']} / {result['slots_filled']}")
    print(
        f"Tagger comparisons: {result['comparisons']}, "
        f"differing: {result['comparisons_differing']}"
    )
    print(f"Unexplained absent input jets: {result['missing_counts']['UNEXPLAINED']}")
    print(f"VERDICT: {'PASS' if result['passed'] else 'FAIL'}")
    raise SystemExit(0 if result["passed"] else 1)
