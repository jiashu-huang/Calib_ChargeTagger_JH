#!/usr/bin/env python3
"""
Validate a processed campaign: are the skim ROOTs internally consistent, and
do they agree with the pickles and the committed schema baseline?

Run after normalize.py (or before it -- the finalWeight checks are skipped if
the branch is absent). Every check either PASSes or FAILs with the numbers that
made it fail; exit code is non-zero if anything failed.

    micromamba run -n ttbar python condor/scripts/validate_processed.py \\
        --processed-dir <input-root>/processed-nano/<tag>

Checks per file: nominal or systematic schema based on the committed CSV, entry
count vs the cutflow, the Norm tree, finite weights, sigma*L constant, nTrueInt
sanity, and finalWeight == weight / global_np_nominal. Campaign-wide: the
denominator matches the pickle sum, and the normalized weighted sum obeys
the signed-weight identity. It need not be a probability between zero and one.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import pickle
import sys
from pathlib import Path

import numpy as np
import uproot

from vcb.normalization import (
    finite_sum,
    infer_sample_scale,
    normalized_weights,
    read_normalization_provenance,
    require_denominator,
)
from vcb.processors.lepton_sf import MUON_COMPONENT_WEIGHT_BRANCHES
from vcb.processors.pdf_weights import read_saved_layout
from vcb.processors.weight_prescription import read_saved_prescription, read_top_pt_normalization

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_BASELINE = REPO_ROOT / "tests" / "outfile" / "test-output-schema.csv"
# Complete set written by the supported 2024 MC --save-systematics path.
# Keep this explicit: accepting arbitrary weight_* names would hide typos.
SYSTEMATIC_WEIGHT_BRANCHES = {
    f"weight_{source}{direction}"
    for source in (
        "pileup", "ISRPartonShower", "FSRPartonShower",
        "electron_reco", "electron_id", "electron_trigger",
        "muon_id", "muon_iso", "muon_trigger",
    )
    for direction in ("Up", "Down")
}
PAD_VAL = -99999


class Report:
    """Collects PASS/FAIL lines and tracks whether anything failed."""

    def __init__(self) -> None:
        self.failed = 0
        self.passed = 0

    def check(self, ok: bool, label: str, detail: str = "") -> bool:
        if ok:
            self.passed += 1
            print(f"  PASS  {label}" + (f"  ({detail})" if detail else ""))
        else:
            self.failed += 1
            print(f"  FAIL  {label}" + (f"  ({detail})" if detail else ""))
        return ok


def make_abs(path: str | Path) -> Path:
    """Return an absolute path without resolving symlinks."""
    return Path(os.path.abspath(os.path.expandvars(os.path.expanduser(str(path)))))


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Validate skim ROOTs in a processed campaign directory.",
    )
    parser.add_argument("--processed-dir", required=True, type=Path)
    parser.add_argument("--year", default="2024")
    parser.add_argument(
        "--target", choices=["batches", "merged"], default="batches", help="Which ROOTs to check."
    )
    schema = parser.add_mutually_exclusive_group()
    schema.add_argument(
        "--schema-mode",
        choices=["auto", "nominal", "systematics"],
        default="auto",
        help=(
            "Expected output mode for the committed nominal baseline. Auto detects "
            "the mode from the first ROOT and requires it for all files."
        ),
    )
    schema.add_argument(
        "--schema-baseline",
        type=Path,
        help="Custom CSV of exact expected branch names (only finalWeight may be extra).",
    )
    return parser.parse_args()


def load_baseline_branches(path: Path) -> set[str]:
    """Read expected branch names; an unavailable or empty schema is an error."""
    with path.open() as handle:
        branches = {row["variable_name"] for row in csv.DictReader(handle)}
    if not branches or any(not name for name in branches):
        raise ValueError("schema must contain non-empty variable_name entries")
    return branches


def main() -> int:
    """Entry point. Returns a process exit code."""
    args = parse_args()
    processed_dir = make_abs(args.processed_dir)
    pickles_dir = processed_dir / "pickles"
    metadata_dir = processed_dir / "metadata"

    if args.target == "merged":
        root_paths = [processed_dir / "merged" / "total.root"]
    else:
        root_paths = sorted((processed_dir / "roots").glob("*.root"))
    if not root_paths or not root_paths[0].is_file():
        print(f"ERROR: no ROOT files found for --target {args.target}", file=sys.stderr)
        return 2

    rep = Report()
    baseline_path = args.schema_baseline or SCHEMA_BASELINE
    try:
        baseline = load_baseline_branches(baseline_path)
    except (OSError, ValueError, KeyError, csv.Error) as exc:
        print(f"ERROR: cannot load schema {baseline_path}: {exc}", file=sys.stderr)
        return 2
    schema_mode = "custom" if args.schema_baseline is not None else args.schema_mode

    # campaign-level denominator, if normalize.py has run
    summary_path = metadata_dir / "normalization.json"
    try:
        summary = json.loads(summary_path.read_text()) if summary_path.is_file() else None
        global_den = require_denominator(summary["global_np_nominal"]) if summary is not None else None
    except (ValueError, TypeError, KeyError) as exc:
        rep.check(False, "valid normalization summary", str(exc))
        return 1

    totals_fw = 0.0
    totals_np = 0.0
    totals_wnx = 0.0
    totals_abs_fw = 0.0
    totals_sel = 0
    sigma_lumi = None
    normalized_mode_seen = None
    pdf_layout_seen = None
    pdf_mode_seen = None
    totals_pdf = None
    totals_top_pt = {}
    weight_prescription_seen = None
    weight_prescription_first = True

    for root_path in root_paths:
        print(f"\n=== {root_path.name} ===")
        with uproot.open(root_path) as handle:
            tree = handle["Events"]
            branches = set(tree.keys())
            n = tree.num_entries
            required = ["weight", "weight_noxsec", "nTrueInt", "nPU"]
            missing_required = [b for b in required if b not in branches]
            # read only what is actually there: a missing branch must be a
            # reported FAIL, not a traceback that skips every later check
            want = [b for b in required if b in branches]
            if "finalWeight" in branches:
                want.append("finalWeight")
            arr = tree.arrays(want, library="np") if want else {}
            weight_prescription = None
            try:
                weight_prescription = read_saved_prescription(handle)
                rep.check(True, "weight metadata and normalization consistent")
                if weight_prescription is not None and weight_prescription["version"] >= 3:
                    for key, value in read_top_pt_normalization(handle).items():
                        totals_top_pt[key] = totals_top_pt.get(key, 0.) + value
                if not weight_prescription_first:
                    rep.check(weight_prescription == weight_prescription_seen,
                              "one weight prescription across campaign")
                weight_prescription_seen, weight_prescription_first = weight_prescription, False
                if summary is not None and "weight_prescription" in summary:
                    rep.check(weight_prescription == summary["weight_prescription"],
                              "normalization used this weight prescription")
            except (ValueError, KeyError) as exc:
                rep.check(False, "weight metadata and normalization consistent", str(exc))
            variation_names = [b for b in branches if b.startswith(("weight_", "scale_weights"))]
            variation_arrays = tree.arrays(variation_names, library="np")
            rep.check(all(np.all(np.isfinite(a)) for a in variation_arrays.values()),
                      "all weight alternatives finite")
            has_norm = "Norm" in handle
            norm_np = None
            if has_norm:
                try:
                    norm_np = finite_sum(handle["Norm"]["np_nominal"].array(library="np"), "Norm np_nominal")
                    rep.check(True, "finite all-input nominal sum")
                except (ValueError, KeyError) as exc:
                    rep.check(False, "finite all-input nominal sum", str(exc))
            prov = None
            try:
                prov = read_normalization_provenance(handle)
            except ValueError as exc:
                rep.check(False, "valid normalization provenance", str(exc))
            has_tparameter = "finalWeight_np_nominal" in handle
            pdf_layout = None
            try:
                pdf_layout = read_saved_layout(handle)
                rep.check(True, "PDF metadata and normalization consistent")
            except (ValueError, KeyError) as exc:
                rep.check(False, "PDF metadata and normalization consistent", str(exc))
            if pdf_layout is not None:
                member_sum = np.sum(handle["Norm"]["np_pdf_weights"].array(library="np"), axis=0)
                if pdf_layout_seen is None:
                    pdf_layout_seen = pdf_layout
                    totals_pdf = member_sum
                elif rep.check(pdf_layout == pdf_layout_seen, "one PDF mapping across campaign"):
                    totals_pdf += member_sum
                for member in range(len(pdf_layout["lha_ids"])):
                    if not np.all(np.isfinite(tree[f"PDFWeight{member}"].array(library="np"))):
                        rep.check(False, "PDF member values finite", f"member {member}")
            pdf_mode = pdf_layout is not None
            if pdf_mode_seen is not None:
                rep.check(pdf_mode == pdf_mode_seen, "consistent PDF presence across campaign")
            pdf_mode_seen = pdf_mode

        rep.check(n > 0 or has_norm, "events or preserved empty-selection normalization", f"{n:,} entries")
        rep.check(
            not missing_required,
            "required branches present",
            f"missing {missing_required}" if missing_required else "",
        )
        rep.check(
            not has_tparameter,
            "no TParameter provenance",
            "hadd sums TParameter, so it must not carry the denominator",
        )

        if schema_mode == "auto":
            # Pin one mode for the entire campaign. Even a partial set selects
            # systematics, so missing variations cannot pass as nominal output.
            varied = SYSTEMATIC_WEIGHT_BRANCHES | MUON_COMPONENT_WEIGHT_BRANCHES
            schema_mode = "systematics" if branches & varied else "nominal"
        expected = baseline
        if schema_mode != "custom" and (
            weight_prescription is None or weight_prescription["version"] < 3
        ):
            expected = expected - {"TopPtWeightValid"}
        if schema_mode == "systematics":
            expected = expected | SYSTEMATIC_WEIGHT_BRANCHES
            if weight_prescription is not None and weight_prescription["version"] >= 2:
                expected = expected | MUON_COMPONENT_WEIGHT_BRANCHES
            if "GenWDecay" in baseline:
                rep.check(pdf_layout is not None, "requested ttbar PDF members present")
        if pdf_layout is not None and schema_mode != "custom":
            expected = expected | {f"PDFWeight{i}" for i in range(len(pdf_layout["lha_ids"]))}
        missing = expected - branches
        extra = branches - expected - {"finalWeight"}
        rep.check(
            not missing and not extra,
            "schema matches baseline",
            f"{schema_mode}, {len(branches)} branches"
            + (f", missing {sorted(missing)[:3]}" if missing else "")
            + (f", extra {sorted(extra)[:3]}" if extra else ""),
        )

        rep.check(has_norm, "Norm tree present", f"np_nominal={norm_np:,.2f}" if norm_np is not None else "")

        for key in [k for k in ("weight", "weight_noxsec") if k in arr]:
            rep.check(bool(np.all(np.isfinite(arr[key]))), f"{key} all finite")
        if "weight" in arr and "weight_noxsec" in arr:
            try:
                sigma_lumi = infer_sample_scale(arr["weight"], arr["weight_noxsec"], sigma_lumi)
                detail = f"scale={sigma_lumi:.12g}" if sigma_lumi is not None else "not inferable from zero/empty weights"
                rep.check(True, "consistent sample scale, including zero weights", detail)
            except ValueError as exc:
                rep.check(False, "consistent sample scale, including zero weights", str(exc))

        # The correction payload owns flow handling; do not invent an upper cut.
        if "nTrueInt" in arr and n > 0:
            nti = arr["nTrueInt"]
            rep.check(
                bool(np.all(np.isfinite(nti) & (nti >= 0))),
                "nTrueInt finite and nonnegative",
                f"min {nti.min():.1f} max {nti.max():.1f} mean {nti.mean():.2f}",
            )
        if "nPU" in arr:
            rep.check(bool(np.all(arr["nPU"] != PAD_VAL)), "nPU not PAD_VAL (MC)")

        normalized = "finalWeight" in arr
        if normalized_mode_seen is not None:
            rep.check(normalized == normalized_mode_seen, "consistent finalWeight presence across campaign")
        normalized_mode_seen = normalized
        if normalized:
            rep.check(np.all(np.isfinite(arr["finalWeight"])), "finalWeight all finite")
            rep.check(global_den is not None, "normalization summary present")
            rep.check(prov is not None, "normalization provenance present")
        if normalized and "weight" in arr and global_den is not None:
            try:
                expected_weights = normalized_weights(arr["weight"], global_den)
                rep.check(np.array_equal(arr["finalWeight"], expected_weights),
                          "finalWeight == weight / global_np_nominal (bit-exact)")
            except ValueError as exc:
                rep.check(False, "finite normalized weights", str(exc))
            if prov is not None and summary is not None:
                rep.check(
                    prov["np_nominal"] == global_den,
                    "provenance denominator matches",
                    f"{prov['np_nominal']:,.2f}",
                )
                rep.check(
                    prov["fingerprint"] == summary.get("fingerprint"),
                    "provenance fingerprint matches batch list",
                    prov["fingerprint"][:16] + "...",
                )
            totals_fw += float(arr["finalWeight"].sum())
            totals_abs_fw += float(np.abs(arr["finalWeight"]).sum())
            totals_wnx += float(arr["weight_noxsec"].sum()) if "weight_noxsec" in arr else 0.0

        if norm_np is not None:
            totals_np += norm_np
        totals_sel += n

    # --- campaign level -------------------------------------------------
    print("\n=== campaign ===")
    if pickles_dir.is_dir() and args.target == "batches":
        den_pkl = 0.0
        pdf_pkl = None
        top_pt_pkl = {key: np.zeros_like(value) for key, value in totals_top_pt.items()}
        for pkl in sorted(pickles_dir.glob("*.pkl")):
            with pkl.open("rb") as handle:
                block = pickle.load(handle)[args.year]
            dataset_block = next(iter(block.values()))
            try:
                den_pkl += finite_sum([dataset_block["totals"]["np_nominal"]], f"{pkl.name}: np_nominal")
            except ValueError as exc:
                rep.check(False, "finite pickle nominal sum", str(exc))
            for key, reference in totals_top_pt.items():
                value = dataset_block["totals"].get(key)
                if rep.check(value is not None and np.shape(value) == np.shape(reference)
                             and np.all(np.isfinite(value)), "pickle top-pT sum present and valid",
                             f"{pkl.name}: {key}"):
                    top_pt_pkl[key] += value
            if weight_prescription_seen is not None:
                rep.check(
                    dataset_block.get("weight_prescriptions", set())
                    == {json.dumps(weight_prescription_seen, sort_keys=True)},
                    "pickle weight prescription matches ROOT", pkl.name,
                )
            if totals_pdf is not None:
                layout_strings = dataset_block.get("pdf_layouts", set())
                matches = layout_strings == {json.dumps(pdf_layout_seen, sort_keys=True)}
                rep.check(matches, "pickle PDF mapping matches ROOT", pkl.name)
                values = dataset_block["totals"].get("np_pdf_weights")
                if rep.check(values is not None, "pickle PDF sums present", pkl.name):
                    values = np.asarray(values)
                    if rep.check(values.shape == totals_pdf.shape, "pickle PDF sums shape", pkl.name):
                        pdf_pkl = values.copy() if pdf_pkl is None else pdf_pkl + values
        for key, value in totals_top_pt.items():
            rep.check(np.allclose(value, top_pt_pkl[key], rtol=1e-10, atol=1e-6),
                      "top-pT Norm-tree sum == pickle sum", key)
        if totals_pdf is not None:
            rep.check(
                pdf_pkl is not None and np.allclose(totals_pdf, pdf_pkl, rtol=1e-10, atol=1e-6),
                "PDF Norm-tree sums == pickle sums",
            )
        rep.check(
            abs(totals_np - den_pkl) < 1e-6,
            "Norm-tree sum == pickle sum",
            f"{totals_np:,.4f}",
        )
        if global_den is not None:
            rep.check(
                abs(global_den - den_pkl) < 1e-6,
                "normalization.json denominator == pickle sum",
            )

    if summary is not None and totals_top_pt:
        saved_top_pt = summary.get("global_top_pt_sums", {})
        rep.check(saved_top_pt.keys() == totals_top_pt.keys(),
                  "normalization.json contains all top-pT sums")
        for key, value in totals_top_pt.items():
            saved = saved_top_pt.get(key)
            rep.check(saved is not None and np.shape(saved) == np.shape(value)
                      and np.allclose(saved, value, rtol=1e-10, atol=1e-6),
                      "normalization.json top-pT sum == ROOT sum", key)

    if summary is not None and "sigma_x_lumi" in summary:
        saved_scale = summary["sigma_x_lumi"]
        rep.check(saved_scale is None if sigma_lumi is None else (
            saved_scale is not None and np.isfinite(saved_scale)
            and np.isclose(saved_scale, sigma_lumi, rtol=1e-10, atol=0)
        ), "normalization.json sample scale matches ROOT")

    # The files examined must together account for exactly the denominator
    # their finalWeight was divided by. Catches the numerator/denominator
    # mismatch of docs/normalization.md section 3 in its subtlest form: merging only
    # part of a normalized campaign, where every per-file check still passes
    # but the yield silently comes out low.
    if global_den is not None:
        rel = abs(totals_np - global_den) / max(abs(global_den), 1e-300)
        rep.check(
            rel < 1e-9,
            "Norm sum over examined files == global_np_nominal",
            f"{totals_np:,.4f} vs {global_den:,.4f}"
            + (
                "  -- these files are not the set finalWeight was normalized against"
                if rel >= 1e-9
                else ""
            ),
        )

    if global_den is not None and normalized_mode_seen:
        selection_fraction = totals_wnx / global_den
        # The identity the whole design rests on:
        #   Sum(finalWeight) = scale x Sum_selected(weight_noxsec) / D
        # Both sides are computed from independent quantities -- the left from
        # the finalWeight branch, the right from weight_noxsec and the
        # denominator -- so a finalWeight written with the wrong denominator
        # (or rescaled after the fact) fails here.
        expected = sigma_lumi * selection_fraction if sigma_lumi is not None else 0.
        close = np.isfinite(totals_fw) and np.isfinite(expected) and np.isclose(
            totals_fw, expected, rtol=1e-9, atol=1e-12 * totals_abs_fw,
        )
        rep.check(
            close,
            "normalized signed-weight sum identity",
            f"{totals_fw:,.6g} vs {expected:,.6g}; weighted selection fraction {selection_fraction:.6g}",
        )
        print(f"\n  selected events : {totals_sel:,}")
        print(f"  global np_nominal: {global_den:,.4f}")
        print(f"  normalized weighted sum : {totals_fw:,.6g}")
        print("  Physical yield interpretation requires a verified sample cross section and luminosity.")

    print(f"\n{rep.passed} passed, {rep.failed} failed")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
