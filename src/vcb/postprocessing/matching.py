"""Count saved truth matches and plot reconstructed hadronic W/top masses.

Run with ``python -m vcb.postprocessing.matching --help``. This reads completed
Calib_ChargeTagger_JH ROOT skims; it never rematches or changes their selection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import uproot

ROLES = ("HadB", "LepB", "HadQ1", "HadQ2")
PARTONS = ("GenHadTopB", "GenLepTopB", "GenQ1", "GenQ2")
INDEX_FIELDS = tuple(f"Gen{role}JetIdx" for role in ROLES)
GEOMETRY_FIELDS = tuple(f"{parton}{coord}" for parton in PARTONS for coord in ("Eta", "Phi"))
POPULATIONS = {
    "hadronic_top_matched": "Hadronic top matched (includes fully matched events)",
    "fully_matched": "All four top-decay partons matched",
}
MASS_EDGES = {"W": np.arange(0.0, 205.0, 5.0), "top": np.arange(50.0, 355.0, 5.0)}
DR_LIMIT = 0.4
DR_TOLERANCE = 1e-6  # Saved coordinates can have less precision than matching inputs.


def resolve_inputs(patterns):
    """Expand local paths/globs; remote ROOT URLs must name individual files."""
    paths = []
    for pattern in patterns:
        if "://" in pattern:
            if any(char in pattern for char in "*?["):
                raise ValueError("Remote globs are unsupported; supply individual ROOT URLs")
            paths.append(pattern)
            continue
        path = Path(pattern).expanduser()
        if path.is_dir():
            matches = sorted(path.glob("*.root"))
        else:
            root = Path(path.anchor) if path.is_absolute() else Path()
            matches = sorted(root.glob(str(path)[len(path.anchor):]))
        if not matches:
            raise ValueError(f"No input files match {pattern!r}")
        for match in matches:
            resolved = Path(match).resolve()
            if not resolved.is_file():
                raise ValueError(f"Not an input file: {resolved}")
            paths.append(str(resolved))
    if len(paths) != len(set(paths)):
        raise ValueError("Duplicate input path: do not combine overlapping globs or symlinks")
    return paths


def inspect_schema(tree):
    fields = set(tree.keys())
    slots = sorted(int(m[1]) for name in fields if (m := re.fullmatch(r"ak4JetPt(\d+)", name)))
    if not slots or slots != list(range(len(slots))):
        raise ValueError("Expected contiguous ak4JetPt0, ak4JetPt1, ... in a processed skim")
    required = set(INDEX_FIELDS)
    required.update(f"ak4Jet{coord}{slot}" for coord in ("Pt", "Eta", "Phi", "Mass")
                    for slot in slots)
    if missing := required - fields:
        raise ValueError(f"Missing processed-skim branches: {sorted(missing)}")
    geometry = fields.intersection(GEOMETRY_FIELDS)
    if geometry and geometry != set(GEOMETRY_FIELDS):
        raise ValueError("Incomplete saved generator directions for the four matched partons")
    masks = {f"B0JetMask{slot}" for slot in slots}
    if fields.intersection(masks) and not masks.issubset(fields):
        raise ValueError("Incomplete B0JetMask slots")
    if "B0AssignmentMask" in fields and "GenWDecayValid" not in fields:
        raise ValueError("B0AssignmentMask requires GenWDecayValid for validation")
    optional = fields.intersection({"nJets", "B0AssignmentMask", "GenWDecayValid"})
    optional.update(geometry)
    optional.update(fields.intersection(masks))
    return len(slots), sorted(required | optional)


def boolean_column(values, name):
    if not np.isin(values, [0, 1]).all():
        raise ValueError(f"Invalid boolean values in {name}")
    return values.astype(bool)


def invariant_mass(pt, eta, phi, mass, indices):
    """Sum reconstructed jet four-vectors in float64, preserving the W symmetry."""
    rows = np.arange(len(indices))[:, None]
    p, e, f, m = [values[rows, indices] for values in (pt, eta, phi, mass)]
    energy = np.sqrt((p * np.cosh(e)) ** 2 + m ** 2).sum(axis=1)
    px = (p * np.cos(f)).sum(axis=1)
    py = (p * np.sin(f)).sum(axis=1)
    pz = (p * np.sinh(e)).sum(axis=1)
    squared = energy ** 2 - px ** 2 - py ** 2 - pz ** 2
    if not np.isfinite(squared).all() or np.any(squared < -1e-9 * energy ** 2):
        raise ValueError("Invalid invariant mass from saved matched-jet four-vectors")
    return np.sqrt(np.maximum(squared, 0))


def analyze_chunk(arrays, slots):
    """Validate assignments, then return disjoint/inclusive masks and hadronic masses."""
    columns = [arrays[field] for field in INDEX_FIELDS]
    if any(column.dtype.kind not in "iu" or column.ndim != 1 for column in columns):
        raise ValueError("Saved match indices must be scalar integer branches")
    indices = np.column_stack(columns)
    if np.any((indices < -1) | (indices >= slots)):
        raise ValueError("Saved match index outside [-1, number of saved slots)")
    matched = indices >= 0
    ordered = np.sort(indices, axis=1)
    if np.any((ordered[:, 1:] == ordered[:, :-1]) & (ordered[:, 1:] >= 0)):
        raise ValueError("Duplicate assigned jet: saved matching must be one-to-one")
    if "nJets" in arrays:
        n_jets = arrays["nJets"]
        if np.any(~np.isfinite(n_jets) | (n_jets < 0) | (n_jets != np.floor(n_jets))):
            raise ValueError("Invalid nJets")
        if np.any(matched & (indices >= n_jets[:, None])):
            raise ValueError("Saved match index points beyond nJets (padding)")
    pt, eta, phi, mass = [np.column_stack([arrays[f"ak4Jet{coord}{i}"]
                                         for i in range(slots)]).astype(np.float64)
                         for coord in ("Pt", "Eta", "Phi", "Mass")]
    rows = np.arange(len(indices))[:, None]
    safe_indices = np.maximum(indices, 0)
    assigned = [values[rows, safe_indices][matched] for values in (pt, eta, phi, mass)]
    if (not all(np.isfinite(values).all() for values in assigned)
            or np.any(assigned[0] <= 0) or np.any(assigned[3] < 0)):
        raise ValueError("Invalid matched-jet four-vector or padded jet")
    if "B0JetMask0" in arrays:
        masks = np.column_stack([boolean_column(arrays[f"B0JetMask{i}"], f"B0JetMask{i}")
                                 for i in range(slots)])
        if np.any(matched & ~masks[rows, safe_indices]):
            raise ValueError("Saved match index points to a false B0JetMask slot")
    checks = {"delta_r_checked_assignments": 0, "delta_r_roundoff_assignments": 0,
              "maximum_delta_r": None}
    if GEOMETRY_FIELDS[0] in arrays:
        parton_eta, parton_phi = [np.column_stack([arrays[f"{parton}{coord}"]
                                                  for parton in PARTONS])
                                 for coord in ("Eta", "Phi")]
        dphi = (phi[rows, safe_indices] - parton_phi + np.pi) % (2 * np.pi) - np.pi
        delta_r = np.hypot(eta[rows, safe_indices] - parton_eta, dphi)[matched]
        if not np.isfinite(delta_r).all() or np.any(delta_r >= DR_LIMIT + DR_TOLERANCE):
            raise ValueError("Saved matched jet violates DeltaR < 0.4 (including roundoff tolerance)")
        checks.update(delta_r_checked_assignments=len(delta_r),
                      delta_r_roundoff_assignments=int(np.sum(delta_r >= DR_LIMIT)),
                      maximum_delta_r=float(delta_r.max()) if len(delta_r) else None)
    full = matched.all(axis=1)
    hadronic = matched[:, [0, 2, 3]].all(axis=1)
    selections = {"fully_matched": full, "hadronic_top_matched": hadronic,
                  "hadronic_top_only": hadronic & ~full,
                  "w_pair_matched": matched[:, [2, 3]].all(axis=1)}
    counts = {name: int(mask.sum()) for name, mask in selections.items()}
    counts.update(events_in_processed_files=len(indices), b0_mask_checked_events=0,
                  b0_assignment_eligible=0)
    if "B0AssignmentMask" in arrays:
        b0_mask = boolean_column(arrays["B0AssignmentMask"], "B0AssignmentMask")
        w_valid = boolean_column(arrays["GenWDecayValid"], "GenWDecayValid")
        if not np.array_equal(b0_mask, full & w_valid):
            raise ValueError("B0AssignmentMask differs from full matching AND GenWDecayValid")
        counts.update(b0_mask_checked_events=len(indices), b0_assignment_eligible=int(b0_mask.sum()))
    masses = {"W": invariant_mass(pt[hadronic], eta[hadronic], phi[hadronic], mass[hadronic],
                                  indices[hadronic][:, [2, 3]]),
              "top": invariant_mass(pt[hadronic], eta[hadronic], phi[hadronic], mass[hadronic],
                                    indices[hadronic][:, [0, 2, 3]])}
    return counts, matched.sum(axis=0), np.bincount(matched.sum(axis=1), minlength=5), checks, {
        "hadronic_top_matched": masses,
        "fully_matched": {name: values[full[hadronic]] for name, values in masses.items()},
    }


def empty_result():
    count_names = ("events_in_processed_files", "fully_matched", "hadronic_top_matched",
                   "hadronic_top_only", "w_pair_matched", "b0_mask_checked_events",
                   "b0_assignment_eligible")
    return {"counts": dict.fromkeys(count_names, 0), "matched_by_role": dict.fromkeys(ROLES, 0),
            "events_by_number_of_matched_partons": [0] * 5,
            "checks": {"delta_r_checked_assignments": 0, "delta_r_roundoff_assignments": 0,
                       "maximum_delta_r": None},
            "histograms": {selection: {mass: {"edges_GeV": edges.tolist(),
                "counts": [0] * (len(edges) - 1), "underflow": 0, "overflow": 0}
                for mass, edges in MASS_EDGES.items()} for selection in POPULATIONS}, "files": []}


def accumulate(result, chunk):
    counts, roles, multiplicity, checks, masses = chunk
    for key, value in counts.items():
        result["counts"][key] += value
    for role, value in zip(ROLES, roles, strict=True):
        result["matched_by_role"][role] += int(value)
    result["events_by_number_of_matched_partons"] = [int(a + b) for a, b in
        zip(result["events_by_number_of_matched_partons"], multiplicity, strict=True)]
    for key in ("delta_r_checked_assignments", "delta_r_roundoff_assignments"):
        result["checks"][key] += checks[key]
    maximum = checks["maximum_delta_r"]
    if maximum is not None:
        result["checks"]["maximum_delta_r"] = max(
            maximum, result["checks"]["maximum_delta_r"] or 0)
    for selection, distributions in masses.items():
        for name, values in distributions.items():
            hist = result["histograms"][selection][name]
            edges = MASS_EDGES[name]
            counts, _ = np.histogram(values, edges)
            hist["counts"] = [int(a + b) for a, b in zip(hist["counts"], counts, strict=True)]
            hist["underflow"] += int(np.sum(values < edges[0]))
            hist["overflow"] += int(np.sum(values > edges[-1]))


def summarize(samples, step_size=50_000):
    """Read only requested columns in bounded chunks; retain exact unweighted counts."""
    if step_size < 1:
        raise ValueError("step_size must be positive")
    report = {"schema_version": 1, "created_utc": datetime.now(UTC).isoformat(),
              "module_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "definitions": {
                  "denominator": "All Events rows in the supplied processed skims; not original NanoAOD",
                  "fully_matched": "HadB, LepB, HadQ1 and HadQ2 each have a distinct valid saved jet",
                  "hadronic_top_matched": "HadB, HadQ1 and HadQ2 matched; includes fully_matched",
                  "hadronic_top_only": "hadronic_top_matched AND NOT fully_matched",
                  "w_pair_matched": "HadQ1 and HadQ2 matched, regardless of either b assignment",
                  "b0_assignment_eligible": "Saved B0AssignmentMask, if present; full AND GenWDecayValid",
                  "masses": "M(jHadQ1+jHadQ2), M(jHadB+jHadQ1+jHadQ2); saved corrected jets",
                  "weights": "Unweighted integer event counts; each plotted sample normalized separately",
                  "selection": "No new selection, matching, corrections or mass-window cut",
                  "delta_r_validation": {"limit": DR_LIMIT, "roundoff_tolerance": DR_TOLERANCE},
                  "duplicates": "Duplicate paths/ROOT UUIDs rejected; merged/component event overlap not checked",
              }, "samples": {}}
    seen_paths, seen_uuids = set(), set()
    for label, patterns in samples.items():
        paths = resolve_inputs(patterns)
        if not paths:
            raise ValueError(f"No input files for {label}")
        result = empty_result()
        for path in paths:
            if path in seen_paths:
                raise ValueError(f"Duplicate input path across samples: {path}")
            seen_paths.add(path)
            with uproot.open(path) as source:
                uuid = str(source.file.uuid)
                if uuid in seen_uuids:
                    raise ValueError(f"Duplicate ROOT UUID (copied input): {path}")
                seen_uuids.add(uuid)
                if "Events" not in source:
                    raise ValueError(f"Missing Events tree in {path}")
                tree = source["Events"]
                slots, fields = inspect_schema(tree)
                per_file = empty_result()
                try:
                    for arrays in tree.iterate(fields, step_size=step_size, library="np"):
                        chunk = analyze_chunk(arrays, slots)
                        accumulate(result, chunk)
                        accumulate(per_file, chunk)
                except ValueError as error:
                    raise ValueError(f"{path}: {error}") from error
                if per_file["counts"]["events_in_processed_files"] != tree.num_entries:
                    raise ValueError(f"Entry accounting mismatch in {path}")
                result["files"].append({"path": path, "root_uuid": uuid, "jet_slots": slots,
                    "counts": per_file["counts"], "checks": per_file["checks"],
                    "generator_directions_available": GEOMETRY_FIELDS[0] in fields,
                    "b0_assignment_mask_available": "B0AssignmentMask" in fields})
        total = result["counts"]["events_in_processed_files"]
        result["fractions_of_processed_events"] = {name: value / total if total else None
            for name, value in result["counts"].items()
            if name not in ("events_in_processed_files", "b0_mask_checked_events", "b0_assignment_eligible")}
        report["samples"][label] = result
    return report


def summary_text(report):
    lines = ["SAVED TRUTH-MATCHING REPORT", "",
             "Counts are unweighted Events rows in the supplied processed skims.",
             "Percentages use all supplied processed events, not pre-skim NanoAOD events.",
             "Hadronic-top matched includes fully matched; hadronic-top only excludes them.",
             "No additional selection, rematching or mass-window cut is applied.", ""]
    labels = {"fully_matched": "Fully matched (all four)",
              "hadronic_top_matched": "Hadronic-top matched (inclusive)",
              "hadronic_top_only": "Hadronic-top only (LepB unmatched)",
              "w_pair_matched": "W-pair matched (inclusive)"}
    for sample, data in report["samples"].items():
        counts = data["counts"]
        lines.extend([f"Sample: {sample}", f"Input files: {len(data['files'])}",
                      f"Processed events: {counts['events_in_processed_files']:,}"])
        for key, label in labels.items():
            fraction = data["fractions_of_processed_events"][key]
            percent = f"{fraction:.4%}" if fraction is not None else "N/A"
            lines.append(f"  {label}: {counts[key]:,} ({percent})")
        lines.append(f"  B0AssignmentMask true: {counts['b0_assignment_eligible']:,} "
                     f"of {counts['b0_mask_checked_events']:,} rows with the mask available")
        lines.append("  Matched by role: " + ", ".join(
            f"{role}={value:,}" for role, value in data["matched_by_role"].items()))
        lines.append("  Events with 0/1/2/3/4 matched partons: " + "/".join(
            f"{value:,}" for value in data["events_by_number_of_matched_partons"]))
        lines.append(f"  Checked DeltaR assignments: {data['checks']['delta_r_checked_assignments']:,}")
        for population, hists in data["histograms"].items():
            for mass, hist in hists.items():
                lines.append(f"  {population} {mass} mass: underflow={hist['underflow']:,}, "
                             f"overflow={hist['overflow']:,}")
        lines.append("  Files (processed / full / hadronic-top matched):")
        for file in data["files"]:
            c = file["counts"]
            lines.append(f"    {c['events_in_processed_files']:,} / {c['fully_matched']:,} / "
                         f"{c['hadronic_top_matched']:,} : {file['path']}")
        lines.append("")
    lines.extend(["Integrity checks passed for the supplied saved assignments.",
                  "DeltaR is checked when saved generator directions are available (see JSON).",
                  "Distinct files can still overlap: do not include both merged files and their inputs."])
    return "\n".join(lines) + "\n"


def draw(report, outdir):
    # Plotting is optional at import time; analysis and tests can use only NumPy/Uproot.
    import matplotlib as mpl

    mpl.use("Agg")
    import matplotlib.pyplot as plt

    with plt.rc_context({"font.size": 11, "axes.spines.top": False,
                         "axes.spines.right": False, "savefig.dpi": 180}):
        for population, title in POPULATIONS.items():
            fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.5))
            specs = [("W", 80.4, r"$m(j_{q_1}+j_{q_2})$ [GeV]"),
                     ("top", 172.5, r"$m(j_{b_{had}}+j_{q_1}+j_{q_2})$ [GeV]")]
            for ax, (mass, reference, xlabel) in zip(axes, specs, strict=True):
                for index, (sample, data) in enumerate(report["samples"].items()):
                    hist = data["histograms"][population][mass]
                    edges, counts = np.array(hist["edges_GeV"]), np.array(hist["counts"])
                    total = data["counts"][population]
                    # Normalize including under/overflow, without cutting events to the plot range.
                    denominator = max(total, 1) * np.diff(edges)
                    density = counts / denominator
                    color = f"C{index % 10}"
                    ax.stairs(density, edges, color=color, linewidth=1.8,
                              label=f"{sample} (N={total:,})")
                    ax.errorbar((edges[:-1] + edges[1:]) / 2, density,
                                yerr=np.sqrt(counts) / denominator, fmt="none",
                                color=color, alpha=.55, elinewidth=.7)
                ax.axvline(reference, color=".4", linestyle="--", linewidth=1,
                           label=f"{reference:g} GeV reference")
                ax.set(xlabel=xlabel, ylabel="Normalized events / GeV", title=f"Hadronic {mass}",
                       xlim=(MASS_EDGES[mass][0], MASS_EDGES[mass][-1]), ylim=(0, None))
                ax.grid(axis="y", alpha=.15)
                ax.legend(frameon=False, fontsize=9)
            fig.suptitle("Masses from truth-matched reconstructed jets", fontsize=15, y=.98)
            fig.text(.5, .89, title, ha="center")
            fig.text(.5, .035, "Unweighted; each sample normalized separately; no new selection. "
                     "Error bars: statistical.", ha="center", fontsize=10)
            fig.subplots_adjust(left=.075, right=.985, top=.80, bottom=.16, wspace=.26)
            for extension in ("png", "pdf"):
                fig.savefig(outdir / f"{population}_masses.{extension}")
            plt.close(fig)


def write_report(report, outdir):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    if any(outdir.iterdir()):
        raise ValueError(f"Output directory must be empty: {outdir}")
    draw(report, outdir)
    (outdir / "matching_summary.txt").write_text(summary_text(report))
    (outdir / "matching_summary.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--files", nargs="+", help="Processed ROOT files, local globs or directories")
    source.add_argument("--sample", action="append", metavar="LABEL=PATH_OR_GLOB",
                        help="Repeat to compare samples; repeat a label to add files to it")
    parser.add_argument("--label", help="Sample label for --files (default: sample)")
    parser.add_argument("--outdir", type=Path, required=True, help="New or empty report directory")
    parser.add_argument("--step-size", type=int, default=50_000, help="Events read per chunk")
    args = parser.parse_args(argv)
    if args.step_size < 1:
        parser.error("--step-size must be positive")
    if args.sample and args.label:
        parser.error("--label is only used with --files")
    samples = {}
    if args.files:
        samples[args.label or "sample"] = args.files
    else:
        for item in args.sample:
            label, separator, pattern = item.partition("=")
            if not separator or not label.strip() or not pattern:
                parser.error("--sample requires LABEL=PATH_OR_GLOB")
            samples.setdefault(label.strip(), []).append(pattern)
    if args.outdir.exists() and (not args.outdir.is_dir() or any(args.outdir.iterdir())):
        parser.error("--outdir must be a new or empty directory")
    try:
        report = summarize(samples, args.step_size)
        write_report(report, args.outdir)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Matching report failed: {error}\n")
    print(summary_text(report))
    print(f"Report and plots: {args.outdir.resolve()}")


if __name__ == "__main__":
    main()
