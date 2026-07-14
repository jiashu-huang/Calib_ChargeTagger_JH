from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import uproot

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTFILE_DIR = PROJECT_ROOT / "tests" / "outfile"
# Default raw-NanoAOD input used for input-vs-output cross-checks.
# This is the same file the integration test (tests/test_run.py) skims; keep the
# two in sync. Currently the frozen 2024 TTtoLNuCB test fixture.
DEFAULT_INPUT_FILE = PROJECT_ROOT / "tests" / "data" / "test-input.root"
DEFAULT_SKIM_DUMP = OUTFILE_DIR / "test-output-0th-event.txt"
DEFAULT_INPUT_DUMP = OUTFILE_DIR / "test-input-matching-event.txt"
DEFAULT_COMPARISON = OUTFILE_DIR / "test-input-vs-output-jet-charge.txt"
DEFAULT_TREE = "Events"
PAD_VAL = -99999

OUTPUT_VALUE_PATTERN = re.compile(r"^(\S+)\s+\((\S+)\)\s+=\s+(.+)$")
OUTPUT_JET_PATTERN = re.compile(r"^ak4Jet(.+?)(\d+)$")

JET_CHARGE_FIELD_MAP = {
    "ParTNegvsAll": "ParTNegvsAll",
    "ParTPosvsAll": "ParTPosvsAll",
    "ParTZerovsAll": "ParTZerovsAll",
    "ParTPosvsNeg": "ParTPosvsNeg",
    "PflavCharge": "PflavCharge",
    "FlavSplit": "FlavSplit",
}
MATCH_FIELDS = ("Eta", "Phi")


def _parse_scalar(text: str) -> int | float | str:
    text = text.strip()
    if text in {"True", "False"}:
        return int(text == "True")
    try:
        value = int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text
    return value


def read_skim_dump(path: Path) -> dict[str, int | float | str]:
    values = {}
    for line in path.read_text().splitlines():
        match = OUTPUT_VALUE_PATTERN.match(line)
        if match:
            values[match.group(1)] = _parse_scalar(match.group(3))
    return values


def find_input_entry(
    tree,
    run: int,
    luminosity_block: int,
    event: int,
) -> int:
    ids = tree.arrays(["run", "luminosityBlock", "event"], library="np")
    mask = (
        (ids["run"] == run) & (ids["luminosityBlock"] == luminosity_block) & (ids["event"] == event)
    )
    matches = np.flatnonzero(mask)
    if len(matches) != 1:
        raise RuntimeError(
            "Expected exactly one matching input event for "
            f"run={run}, luminosityBlock={luminosity_block}, event={event}; "
            f"found {len(matches)}."
        )
    return int(matches[0])


def _format_value(value) -> str:
    value = np.asarray(value)
    if value.ndim == 0:
        return str(value.item())
    return np.array2string(value, separator=", ", threshold=100000, max_line_width=120)


def dump_input_event(tree, entry: int, output_path: Path) -> None:
    arrays = tree.arrays(library="np", entry_start=entry, entry_stop=entry + 1)

    lines = ["Tree: Events", f"Entry: {entry}"]
    for name in sorted(arrays.keys()):
        branch_type = tree[name].typename
        lines.append(f"{name} ({branch_type}) = {_format_value(arrays[name][0])}")

    output_path.write_text("\n".join(lines) + "\n")


def _output_slots(skim_values: dict[str, int | float | str]) -> list[int]:
    slots = set()
    for name in skim_values:
        match = OUTPUT_JET_PATTERN.match(name)
        if match:
            slots.add(int(match.group(2)))
    return sorted(slots)


def _skim_value(
    skim_values: dict[str, int | float | str],
    output_field: str,
    slot: int,
) -> int | float | str | None:
    return skim_values.get(f"ak4Jet{output_field}{slot}")


def _is_padded(value: int | float | str | None) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return False
    return bool(np.isclose(float(value), PAD_VAL))


def _delta_phi(phi1: float, phi2: float) -> float:
    return float(np.arctan2(np.sin(phi1 - phi2), np.cos(phi1 - phi2)))


def _best_input_jet_match(skim_values, input_event, slot: int) -> tuple[int | None, float | None]:
    eta = _skim_value(skim_values, "Eta", slot)
    phi = _skim_value(skim_values, "Phi", slot)
    if _is_padded(eta) or _is_padded(phi):
        return None, None

    input_eta = np.asarray(input_event["Jet_eta"], dtype=np.float64)
    input_phi = np.asarray(input_event["Jet_phi"], dtype=np.float64)
    dr2 = (input_eta - float(eta)) ** 2 + np.array(
        [_delta_phi(float(phi), value) ** 2 for value in input_phi],
        dtype=np.float64,
    )
    index = int(np.argmin(dr2))
    return index, float(np.sqrt(dr2[index]))


def _format_comparison_value(value) -> str:
    if value is None:
        return "None"
    if isinstance(value, float):
        return f"{value:.12g}"
    return str(value)


def compare_jet_charge_fields(
    skim_values: dict[str, int | float | str],
    input_event: dict[str, np.ndarray],
    output_path: Path,
) -> None:
    lines = [
        "Jet charge tag comparison",
        ("Output AK4 slots are matched to input Jet indices by closest " "eta/phi in this event."),
        "",
    ]
    matched_input_indices = set()

    for slot in _output_slots(skim_values):
        pt = _skim_value(skim_values, "Pt", slot)
        if _is_padded(pt):
            continue

        input_index, delta_r = _best_input_jet_match(skim_values, input_event, slot)
        lines.append(f"ak4 output slot {slot}")
        lines.append(
            f"  output pt/eta/phi: {pt}, {_skim_value(skim_values, 'Eta', slot)}, "
            f"{_skim_value(skim_values, 'Phi', slot)}"
        )

        if input_index is None:
            lines.append("  no input match")
            lines.append("")
            continue

        matched_input_indices.add(input_index)
        lines.append(f"  matched input Jet index: {input_index} (deltaR={delta_r:.6g})")
        lines.append(
            "  input pt/eta/phi: "
            f"{input_event['Jet_pt'][input_index]}, "
            f"{input_event['Jet_eta'][input_index]}, "
            f"{input_event['Jet_phi'][input_index]}"
        )

        for output_field, input_field in JET_CHARGE_FIELD_MAP.items():
            output_value = _skim_value(skim_values, output_field, slot)
            input_value = input_event[f"Jet_{input_field}"][input_index]
            if isinstance(output_value, float):
                agrees = np.isclose(float(output_value), float(input_value), rtol=0.0, atol=1e-7)
            else:
                agrees = output_value == int(input_value)
            status = "OK" if agrees else "DIFF"
            lines.append(
                f"  {output_field}: output={_format_comparison_value(output_value)} "
                f"input={_format_comparison_value(input_value.item())} [{status}]"
            )
        lines.append("")

    all_input_indices = set(range(len(input_event["Jet_pt"])))
    unmatched_input_indices = sorted(all_input_indices - matched_input_indices)
    if unmatched_input_indices:
        lines.append("Input Jet indices not present in selected output AK4 slots")
        for input_index in unmatched_input_indices:
            lines.append(f"input Jet index {input_index}")
            lines.append(
                "  input pt/eta/phi: "
                f"{input_event['Jet_pt'][input_index]}, "
                f"{input_event['Jet_eta'][input_index]}, "
                f"{input_event['Jet_phi'][input_index]}"
            )
            for input_field in JET_CHARGE_FIELD_MAP.values():
                input_value = input_event[f"Jet_{input_field}"][input_index]
                formatted = _format_comparison_value(input_value.item())
                lines.append(f"  {input_field}: input={formatted}")
            lines.append("")

    output_path.write_text("\n".join(lines))


def dump_matching_input_event(
    input_file: Path = DEFAULT_INPUT_FILE,
    skim_dump: Path = DEFAULT_SKIM_DUMP,
    input_dump: Path = DEFAULT_INPUT_DUMP,
    comparison_output: Path = DEFAULT_COMPARISON,
    tree_name: str = DEFAULT_TREE,
) -> dict[str, str | int]:
    skim_values = read_skim_dump(skim_dump)
    run = int(skim_values["run"])
    luminosity_block = int(skim_values["luminosityBlock"])
    event = int(skim_values["event"])

    with uproot.open(input_file) as root_file:
        tree = root_file[tree_name]
        entry = find_input_entry(tree, run, luminosity_block, event)
        dump_input_event(tree, entry, input_dump)
        input_event = tree.arrays(library="np", entry_start=entry, entry_stop=entry + 1)
        input_event = {name: values[0] for name, values in input_event.items()}

    compare_jet_charge_fields(skim_values, input_event, comparison_output)

    return {
        "run": run,
        "luminosityBlock": luminosity_block,
        "event": event,
        "input_entry": entry,
        "input_dump": str(input_dump),
        "comparison_output": str(comparison_output),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find the input NanoAOD event corresponding to test-output-0th-event.txt "
            "and dump it with a focused jet charge comparison."
        )
    )
    parser.add_argument("--input-file", type=Path, default=DEFAULT_INPUT_FILE)
    parser.add_argument("--skim-dump", type=Path, default=DEFAULT_SKIM_DUMP)
    parser.add_argument("--input-dump", type=Path, default=DEFAULT_INPUT_DUMP)
    parser.add_argument("--comparison-output", type=Path, default=DEFAULT_COMPARISON)
    parser.add_argument("--tree-name", default=DEFAULT_TREE)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    result = dump_matching_input_event(
        input_file=args.input_file,
        skim_dump=args.skim_dump,
        input_dump=args.input_dump,
        comparison_output=args.comparison_output,
        tree_name=args.tree_name,
    )
    print(
        "Matched input event "
        f"run={result['run']} luminosityBlock={result['luminosityBlock']} "
        f"event={result['event']} at input entry {result['input_entry']}"
    )
    print(f"Input event dump: {result['input_dump']}")
    print(f"Jet charge comparison: {result['comparison_output']}")
