"""
Round-trip check: every saved AK4 jet must carry its input jet's tagger scores.

For each event in a skim output file this locates the same event in the source
NanoAOD (by run / luminosityBlock / event) and, for every saved jet, compares
the charge- and flavor-tagger branches against the input jet they came from.
Output slots are matched to input jets by eta/phi, which JECs leave untouched,
so the match is exact rather than nearest-neighbour.

Input jets that never reach the output are classified rather than ignored. The
skimmer drops a jet for exactly four reasons -- it sits within dR <= 0.4 of the
trigger lepton used for cleaning, it fails corrected pT > 15 GeV or
|eta| < 4.7, or it fell past the 8 saved slots -- so anything left over is a
real finding.

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
NUM_AK4_SLOTS = 8
# Mirrors objects.good_ak4jets: kept if pt > 15, |eta| < 4.7 and every cleaning
# lepton is farther than dR 0.4. A jet exactly on a boundary is dropped.
JET_CLEANING_DR = 0.4
JET_ETA_MAX = 4.7
JET_PT_MIN = 15.0
# Output eta/phi are float32 input values widened to float64, so the match is
# exact; the tolerance only exists so a future eta-changing correction degrades
# to a nearest-jet match with a reported dR instead of a silent failure.
MATCH_DR_TOL = 1e-6

# Compared fields: "<output branch suffix>": "<input Jet_ branch suffix>".
TAGGER_FIELD_MAP = {
    "ParTNegvsAll": "ParTNegvsAll",
    "ParTPosvsAll": "ParTPosvsAll",
    "ParTPosvsNeg": "ParTPosvsNeg",
    "btagPNetB": "btagPNetB",
    "btagPNetCvB": "btagPNetCvB",
    "btagPNetCvNotB": "btagPNetCvNotB",
}

# Why an input jet can be absent from the output, in the order tested. A jet may
# fail several cuts at once; it is counted under the first that applies, and
# lepton cleaning leads because that is the reason this check exists to confirm.
MISSING_REASONS = (
    "lepton_cleaned",
    "pt_below_threshold",
    "eta_out_of_range",
    "truncated_beyond_8_slots",
    "UNEXPLAINED",
)
REASON_NOTES = {
    "lepton_cleaned": f"dR <= {JET_CLEANING_DR} of the trigger lepton",
    "pt_below_threshold": f"corrected pT <= {JET_PT_MIN} GeV",
    "eta_out_of_range": f"|eta| >= {JET_ETA_MAX}",
    "truncated_beyond_8_slots": f"passed selection, event had > {NUM_AK4_SLOTS} selected jets",
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
        for field in ("Pt", "Eta", "Phi", *TAGGER_FIELD_MAP)
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

    with uproot.open(output_file) as root_file:
        out_tree = root_file[tree_name]
        missing = [name for name in event_branches + slot_branches if name not in out_tree.keys()]
        if missing:
            raise KeyError(
                f"Missing required branch(es) in {output_file}: {', '.join(sorted(missing))}"
            )
        out = out_tree.arrays(event_branches + slot_branches, library="np")
        n_out_events = out_tree.num_entries

    if n_out_events <= 0:
        raise ValueError(f"{output_file} has no events.")

    input_jet_branches = ["Jet_pt", "Jet_eta", "Jet_phi"] + [
        f"Jet_{name}" for name in TAGGER_FIELD_MAP.values()
    ]
    # A Condor job skims several input files into one output, so the index and
    # the jet arrays span every input file, concatenated in the given order.
    entry_of: dict[tuple[int, int, int], int] = {}
    file_event_starts = [0]
    per_file_jets = []
    for path in input_files:
        with uproot.open(path) as root_file:
            in_tree = root_file[tree_name]
            missing = [name for name in input_jet_branches if name not in in_tree.keys()]
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
            per_file_jets.append(in_tree.arrays(input_jet_branches, library="ak"))

    n_in_events = file_event_starts[-1]
    jets = per_file_jets[0] if len(per_file_jets) == 1 else ak.concatenate(per_file_jets)
    del per_file_jets

    in_flat = {}
    offsets = None
    for name in input_jet_branches:
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
    out_tagger = {field: slot_block(field) for field in TAGGER_FIELD_MAP}

    n_jets_branch = np.asarray(out["nJets"], dtype=np.int64)
    trig_flav = np.asarray(out["TriggerLeptonFlav"], dtype=np.int64)
    trig_eta = np.asarray(out["TriggerLeptonEta"], dtype=np.float64)
    trig_phi = np.asarray(out["TriggerLeptonPhi"], dtype=np.float64)

    stats = {
        "events_checked": 0,
        "events_missing_from_input": 0,
        "events_without_trigger_lepton": 0,
        "events_njets_disagree": 0,
        "slots_filled": 0,
        "slots_matched": 0,
        "slots_unmatched": 0,
        "slots_pt_disagree": 0,
        "comparisons": 0,
        "comparisons_differing": 0,
    }
    missing_counts = dict.fromkeys(MISSING_REASONS, 0)
    max_match_dr = 0.0
    anomalies: dict[str, list[str]] = {
        "missing_events": [],
        "unmatched_slots": [],
        "pt_disagree": [],
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
        last_matched = -1

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
            last_matched = max(last_matched, j)

            if corrected_pt is not None and corrected_pt[start + j] != out_pt[i, slot]:
                stats["slots_pt_disagree"] += 1
                record(
                    "pt_disagree",
                    f"{tag} slot={slot} input jet {j}: saved pT={out_pt[i, slot]!r} "
                    f"recomputed pT={corrected_pt[start + j]!r}",
                )

            for field, input_name in TAGGER_FIELD_MAP.items():
                stats["comparisons"] += 1
                output_value = out_tagger[field][i, slot]
                input_value = in_flat[f"Jet_{input_name}"][start + j]
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
            elif n_jets_branch[i] > NUM_AK4_SLOTS and j > last_matched:
                reason = "truncated_beyond_8_slots"
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
        passed=passed,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)

    return {
        "report": str(report_path),
        "passed": passed,
        "verify_jec": corrected_pt is not None,
        **stats,
        "missing_counts": missing_counts,
    }


def _format_report(**ctx) -> str:
    stats = ctx["stats"]
    missing_counts = ctx["missing_counts"]
    verify_jec = ctx["verify_jec"]
    rule = "-" * 78

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
        "fields      : " + ", ".join(f"ak4Jet{field}" for field in TAGGER_FIELD_MAP),
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
        "",
        "Saved jet slots",
        rule,
        f"  filled slots checked               : {stats['slots_filled']}",
        f"  matched to an input jet            : {stats['slots_matched']}"
        f"   (max dR {ctx['max_match_dr']:g})",
        f"  with NO input jet match            : {stats['slots_unmatched']}",
        f"  saved pT != recomputed pT          : {stats['slots_pt_disagree']}"
        + ("" if verify_jec else "   (not checked without the recomputed pT)"),
        "",
        f"Tagger value comparisons ({len(TAGGER_FIELD_MAP)} fields x matched slot)",
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
