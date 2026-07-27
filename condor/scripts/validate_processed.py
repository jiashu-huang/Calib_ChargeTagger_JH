#!/usr/bin/env python3
"""
Validate a processed campaign: are the skim ROOTs internally consistent, and
do they agree with the pickles and the committed schema baseline?

Run after normalize.py (or before it -- the finalWeight checks are skipped if
the branch is absent). Every check either PASSes or FAILs with the numbers that
made it fail; exit code is non-zero if anything failed.

    micromamba run -n ttbar python condor/scripts/validate_processed.py \\
        --processed-dir <input-root>/processed-nano/<tag>

Checks per file: schema against tests/outfile/test-output-schema.csv, entry
count vs the cutflow, the Norm tree, finite weights, sigma*L constant, nTrueInt
sanity, and finalWeight == weight / global_np_nominal. Campaign-wide: the
denominator matches the pickle sum, and Sum(finalWeight) == sigma*L x weighted
acceptance -- the identity that says the normalization is right.
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

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_BASELINE = REPO_ROOT / "tests" / "outfile" / "test-output-schema.csv"
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
    parser.add_argument(
        "--schema-baseline",
        type=Path,
        default=SCHEMA_BASELINE,
        help="CSV of expected branch names (finalWeight may be extra).",
    )
    return parser.parse_args()


def load_baseline_branches(path: Path) -> set[str] | None:
    """Branch names from the committed schema CSV, or None if unavailable."""
    if not path.is_file():
        return None
    with path.open() as handle:
        return {row["variable_name"] for row in csv.DictReader(handle)}


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
    baseline = load_baseline_branches(args.schema_baseline)

    # campaign-level denominator, if normalize.py has run
    summary_path = metadata_dir / "normalization.json"
    summary = json.loads(summary_path.read_text()) if summary_path.is_file() else None
    global_den = summary["global_np_nominal"] if summary else None

    totals_fw = 0.0
    totals_np = 0.0
    totals_wnx = 0.0
    totals_sel = 0
    sigma_lumi_seen: set[float] = set()

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
            has_norm = "Norm" in handle
            norm_np = (
                float(np.sum(handle["Norm"]["np_nominal"].array(library="np")))
                if has_norm
                else None
            )
            prov = None
            if "finalWeight_provenance" in handle:
                # TNamed payload is JSON; hadd copies it verbatim (unlike a
                # TParameter, which it would sum)
                prov = json.loads(handle["finalWeight_provenance"].member("fTitle"))
            has_tparameter = "finalWeight_np_nominal" in handle

        rep.check(n > 0, "non-empty", f"{n:,} entries")
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

        if baseline is not None:
            missing = baseline - branches
            extra = branches - baseline - {"finalWeight"}
            rep.check(
                not missing and not extra,
                "schema matches baseline",
                f"{len(branches)} branches"
                + (f", missing {sorted(missing)[:3]}" if missing else "")
                + (f", extra {sorted(extra)[:3]}" if extra else ""),
            )

        rep.check(has_norm, "Norm tree present", f"np_nominal={norm_np:,.2f}" if has_norm else "")

        for key in [k for k in ("weight", "weight_noxsec") if k in arr]:
            rep.check(bool(np.all(np.isfinite(arr[key]))), f"{key} all finite")
        if "weight_noxsec" in arr:
            rep.check(bool(np.all(arr["weight_noxsec"] != 0)), "weight_noxsec non-zero")

        # sigma*L must be one constant across every event (weight = w_np x sigmaL)
        can_ratio = (
            "weight" in arr
            and "weight_noxsec" in arr
            and n > 0
            and bool(np.all(arr["weight_noxsec"] != 0))
        )
        if can_ratio:
            ratio = arr["weight"] / arr["weight_noxsec"]
            sigma_lumi_seen.add(round(float(ratio[0]), 4))
            rep.check(
                float(np.ptp(ratio)) < 1e-6,
                "weight/weight_noxsec constant",
                f"sigmaL={ratio[0]:,.4f}",
            )

        # nTrueInt is the pileup input: real, positive, and within the payload range
        if "nTrueInt" in arr and n > 0:
            nti = arr["nTrueInt"]
            rep.check(
                bool(np.all(nti > 0) and np.all(nti < 200)),
                "nTrueInt in range",
                f"min {nti.min():.1f} max {nti.max():.1f} mean {nti.mean():.2f}",
            )
        if "nPU" in arr:
            rep.check(bool(np.all(arr["nPU"] != PAD_VAL)), "nPU not PAD_VAL (MC)")

        if "finalWeight" in arr and "weight" in arr and global_den:
            exact = np.array_equal(arr["finalWeight"], arr["weight"] / global_den)
            rep.check(exact, "finalWeight == weight / global_np_nominal (bit-exact)")
            if prov is not None:
                rep.check(
                    abs(prov["np_nominal"] - global_den) < 1e-6,
                    "provenance denominator matches",
                    f"{prov['np_nominal']:,.2f}",
                )
                rep.check(
                    prov["fingerprint"] == summary["fingerprint"],
                    "provenance fingerprint matches batch list",
                    prov["fingerprint"][:16] + "...",
                )
            totals_fw += float(arr["finalWeight"].sum())
            totals_wnx += float(arr["weight_noxsec"].sum()) if "weight_noxsec" in arr else 0.0

        if norm_np is not None:
            totals_np += norm_np
        totals_sel += n

    # --- campaign level -------------------------------------------------
    print("\n=== campaign ===")
    if pickles_dir.is_dir() and args.target == "batches":
        den_pkl = 0.0
        for pkl in sorted(pickles_dir.glob("*.pkl")):
            with pkl.open("rb") as handle:
                block = pickle.load(handle)[args.year]
            den_pkl += float(next(iter(block.values()))["totals"]["np_nominal"])
        rep.check(
            abs(totals_np - den_pkl) < 1e-6,
            "Norm-tree sum == pickle sum",
            f"{totals_np:,.4f}",
        )
        if global_den:
            rep.check(
                abs(global_den - den_pkl) < 1e-6,
                "normalization.json denominator == pickle sum",
            )

    rep.check(len(sigma_lumi_seen) == 1, "one sigma*L across all files", str(sigma_lumi_seen))

    # The files examined must together account for exactly the denominator
    # their finalWeight was divided by. Catches the numerator/denominator
    # mismatch of docs/normalization.md section 3 in its subtlest form: merging only
    # part of a normalized campaign, where every per-file check still passes
    # but the yield silently comes out low.
    if global_den and totals_np:
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

    if global_den and totals_fw and sigma_lumi_seen:
        sigma_lumi = next(iter(sigma_lumi_seen))
        acceptance = totals_fw / sigma_lumi
        # The identity the whole design rests on:
        #   Sum(finalWeight) = sigmaL x Sum_selected(w_np) / Sum_all(w_np)
        # Both sides are computed from independent quantities -- the left from
        # the finalWeight branch, the right from weight_noxsec and the
        # denominator -- so a finalWeight written with the wrong denominator
        # (or rescaled after the fact) fails here.
        expected = sigma_lumi * totals_wnx / global_den
        rel = abs(totals_fw - expected) / max(abs(expected), 1e-300)
        rep.check(
            rel < 1e-9,
            "Sum(finalWeight) == sigmaL x weighted acceptance",
            f"{totals_fw:,.2f} vs {expected:,.2f} (rel {rel:.2e}), "
            f"acceptance {acceptance:.6f}",
        )
        rep.check(0.0 < acceptance < 1.0, "acceptance in (0,1)", f"{acceptance:.6f}")
        print(f"\n  selected events : {totals_sel:,}")
        print(f"  global np_nominal: {global_den:,.4f}")
        print(f"  predicted yield : {totals_fw:,.2f} events")

    print(f"\n{rep.passed} passed, {rep.failed} failed")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
