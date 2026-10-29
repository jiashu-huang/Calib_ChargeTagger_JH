"""Audit saved TTBB assignments against geometry, a reference greedy, and a global match.

Run in the ttbar environment. This checks the processor's ten saved slots;
it does not certify the later common B0 selection or generator ancestry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import awkward as ak
import numpy as np
import uproot
from scipy.optimize import linear_sum_assignment

from boostedhh.processors.utils import PAD_VAL
from vcb.processors.GenSelection import _greedy_jet_parton_assignment


ROLES = ("HadB", "LepB", "HadQ1", "HadQ2")
PARTONS = ("GenHadTopB", "GenLepTopB", "GenQ1", "GenQ2")


def audit(source: Path) -> dict:
    fields = [f"ak4Jet{v}{j}" for v in ("Pt", "Eta", "Phi") for j in range(10)]
    fields += [f"{p}{v}" for p in PARTONS for v in ("Pt", "Eta", "Phi")]
    fields += [f"Gen{r}JetIdx" for r in ROLES]
    with uproot.open(source) as f:
        a = f["Events"].arrays(fields, library="np")
    jets = {v.lower(): np.column_stack([a[f"ak4Jet{v}{j}"] for j in range(10)])
            for v in ("Pt", "Eta", "Phi")}
    partons = [{v.lower(): a[f"{p}{v}"] for v in ("Pt", "Eta", "Phi")}
               for p in PARTONS]
    saved = np.column_stack([a[f"Gen{r}JetIdx"] for r in ROLES])
    replay = _greedy_jet_parton_assignment(
        [ak.Array(p) for p in partons], ak.Array(jets), 10, dr_max=0.4
    )
    reference = np.full_like(saved, -1)
    optimal = np.full_like(saved, -1)
    bad_index = int(np.sum((saved < -1) | (saved >= 10)))
    duplicate_events = bad_geometry = 0
    for event in range(len(saved)):
        edges = []
        costs = np.full((4, 14), 1e6)
        costs[:, 10:] = 10.0  # Prioritize match cardinality, then total DeltaR.
        for role, p in enumerate(partons):
            if p["eta"][event] == PAD_VAL:
                continue
            for jet in range(10):
                if jets["pt"][event, jet] == PAD_VAL:
                    continue
                dphi = ((float(p["phi"][event]) - jets["phi"][event, jet]
                         + math.pi) % (2 * math.pi)) - math.pi
                dr = math.hypot(float(p["eta"][event]) - jets["eta"][event, jet], dphi)
                if math.isfinite(dr) and dr < 0.4:
                    edges.append((dr, role, jet))
                    costs[role, jet] = dr
        used_roles, used_jets = set(), set()
        for _, role, jet in sorted(edges):
            if role not in used_roles and jet not in used_jets:
                reference[event, role] = jet
                used_roles.add(role)
                used_jets.add(jet)
        row, col = linear_sum_assignment(costs)
        for role, jet in zip(row, col):
            if jet < 10 and costs[role, jet] < 0.4:
                optimal[event, role] = jet
        assigned = saved[event][saved[event] >= 0]
        duplicate_events += len(assigned) != len(set(assigned.tolist()))
        for role, jet in enumerate(saved[event]):
            if jet >= 0 and (jet >= 10 or costs[role, jet] >= 0.4):
                bad_geometry += 1
    full = np.all(saved >= 0, axis=1)
    opt_full = np.all(optimal >= 0, axis=1)
    result = {
        "source": str(source.resolve()),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "scope": "unweighted selected pilot; current processor's ten saved jets",
        "role_order": list(ROLES),
        "cap": 10, "delta_r_strict_max": 0.4,
        "selected_events": len(saved),
        "invalid_indices": bad_index,
        "duplicate_jet_events": int(duplicate_events),
        "invalid_geometric_matches": int(bad_geometry),
        "saved_vs_production_replay_events": int(np.any(saved != replay, axis=1).sum()),
        "saved_vs_independent_greedy_events": int(np.any(saved != reference, axis=1).sum()),
        "greedy_fully_matched": int(full.sum()),
        "greedy_fully_matched_fraction": float(full.mean()),
        "greedy_matched_by_role": dict(zip(ROLES, (saved >= 0).sum(axis=0).tolist())),
        "global_cardinality_then_distance_fully_matched": int(opt_full.sum()),
        "global_fully_matched_fraction": float(opt_full.mean()),
        "global_full_matching_gain_percentage_points": float(100 * (opt_full.mean() - full.mean())),
        "global_assignment_different_events": int(np.any(saved != optimal, axis=1).sum()),
        "greedy_full_global_not_full": int((full & ~opt_full).sum()),
        "global_full_greedy_not_full": int((opt_full & ~full).sum()),
        "full_C1_audit_complete": False,
    }
    failures = (bad_index, duplicate_events, bad_geometry,
                result["saved_vs_production_replay_events"],
                result["saved_vs_independent_greedy_events"],
                result["greedy_full_global_not_full"])
    result["passed"] = not any(failures)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = audit(args.input)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
