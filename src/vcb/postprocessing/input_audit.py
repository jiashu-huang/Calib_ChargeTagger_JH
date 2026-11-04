"""Additive population accounting for C1; never a training normalization fit."""

from __future__ import annotations

from collections import Counter

import numpy as np


def histogram(values):
    keys, counts = np.unique(values, return_counts=True)
    return {str(int(key)): int(count) for key, count in zip(keys, counts, strict=True)}


def feature_summary(values, valid, eligible):
    if not np.isfinite(values).all() or np.any(valid & ~eligible):
        raise ValueError("Invalid feature values or validity on padding")
    if np.any(values[~valid] != 0):
        raise ValueError("Invalid features must have zero placeholders")
    usable = values[valid]
    return {"eligible": int(eligible.sum()), "valid": int(valid.sum()),
            "missing": int((eligible & ~valid).sum()), "valid_zero": int((usable == 0).sum()),
            "minimum": float(usable.min()) if usable.size else None,
            "maximum": float(usable.max()) if usable.size else None}


def summarize_rows(arrays, schema):
    """Summarize already validated B0 rows, retaining independent truth masks."""
    def flag(name):
        value = arrays[name]
        if not np.isin(value, [0, 1]).all():
            raise ValueError(f"Invalid boolean flag: {name}")
        return value.astype(bool)

    def slots(prefix):
        return np.column_stack([arrays[f"{prefix}{i}"] for i in range(schema["max_jets"])])

    real = np.column_stack([flag(f"B0JetMask{i}") for i in range(schema["max_jets"])])
    w, extra = arrays["GenWDecay"], arrays["GenNExtraBQuarks"]
    w_valid, extra_valid = flag("GenWDecayValid"), flag("GenNExtraBQuarksValid")
    assignment = flag("B0AssignmentMask")
    if (np.any(w[~w_valid] != -1) or np.any(extra[~extra_valid] != -1)
            or not np.isin(w[w_valid], [0, 1]).all() or np.any(extra[extra_valid] < 0)):
        raise ValueError("Truth labels disagree with their independent validity flags")
    indices = np.column_stack([arrays[f"Gen{role}JetIdx"]
                               for role in ("HadB", "LepB", "HadQ1", "HadQ2")])
    matched = indices >= 0
    full, hadronic = matched.all(axis=1), matched[:, [0, 2, 3]].all(axis=1)
    if not np.array_equal(assignment, full & w_valid):
        raise ValueError("Assignment mask disagrees with full matching and valid W topology")
    n_jets = arrays["nJets"]
    overflow = n_jets > schema["max_jets"]
    if not np.array_equal(real.sum(axis=1), np.minimum(n_jets, schema["max_jets"])):
        raise ValueError("Jet padding disagrees with the accepted multiplicity")
    populations = {
        "selected": np.ones(len(w), dtype=bool), "W_label_valid": w_valid,
        "extra_b_label_valid": extra_valid, "both_labels_valid": w_valid & extra_valid,
        "fully_matched": full, "hadronic_top_matched": hadronic,
        "assignment_eligible": assignment, "overflow": overflow,
        "unmatched_with_W_label": ~assignment & w_valid,
        "unmatched_with_extra_b_label": ~assignment & extra_valid,
        "fully_matched_with_overflow": full & overflow,
        "fully_matched_without_overflow": full & ~overflow,
    }
    counts = {name: int(mask.sum()) for name, mask in populations.items()}
    counts.update(accepted_jets=int(n_jets.sum()), retained_jets=int(real.sum()),
                  overflow_jets=int(np.maximum(n_jets - schema["max_jets"], 0).sum()))
    b_histograms = {}
    if schema.get("schema_version", 1) >= 2:
        is_b = np.column_stack([flag(f"B0JetIsB{i}") for i in range(schema["max_jets"])])
        b_valid = np.column_stack([flag(f"B0JetIsBValid{i}") for i in range(schema["max_jets"])])
        if np.any(b_valid & ~real) or np.any(is_b & ~b_valid):
            raise ValueError("Invalid per-jet b truth or labelled padding")
        retained = is_b.sum(axis=1)
        for field, key in (("RecoNBJets", "reco_b_jets"), ("GenNBJets", "gen_b_jets")):
            number, valid = arrays[field], flag(field + "Valid")
            if np.any(number[~valid] != -1) or np.any(number[valid] < 0):
                raise ValueError("B-jet counts disagree with their validity flags")
            counts[key + "_count_valid"] = int(valid.sum())
            b_histograms[key] = histogram(number)
        reco, reco_valid = arrays["RecoNBJets"], flag("RecoNBJetsValid")
        if (np.any(reco[reco_valid] > n_jets[reco_valid])
                or np.any(reco[reco_valid] < retained[reco_valid])
                or np.any((reco - retained)[reco_valid] >
                          np.maximum(n_jets - schema["max_jets"], 0)[reco_valid])
                or np.any(reco_valid & np.any(real & ~b_valid, axis=1))):
            raise ValueError("Reco b-jet counts disagree with retained jets or overflow")
        if not np.array_equal(reco_valid[~overflow], np.all(~real | b_valid, axis=1)[~overflow]):
            raise ValueError("Reco b-jet count validity disagrees with complete retained truth")
        counts["retained_b_jets"] = int(retained.sum())
        counts["retained_jets_with_unknown_b_truth"] = int((real & ~b_valid).sum())
        counts["overflow_b_jets_in_valid_events"] = int((reco - retained)[reco_valid].sum())
        pairs = np.column_stack([reco, arrays["GenNBJets"]])
        b_histograms["reco_vs_gen_b_jets"] = {
            f"reco={int(r)},gen={int(g)}": int(((pairs[:, 0] == r) & (pairs[:, 1] == g)).sum())
            for r, g in np.unique(pairs, axis=0)}
    features = {}
    for feature in schema["jet_features"]:
        valid = np.column_stack([flag(f"B0Jet_{feature}_valid_{i}")
                                 for i in range(schema["max_jets"])])
        features[f"jet/{feature}"] = feature_summary(slots(f"B0Jet_{feature}_"), valid, real)
    for feature in schema["event_features"]:
        features[f"event/{feature}"] = feature_summary(
            arrays[f"B0Event_{feature}"], flag(f"B0Event_{feature}_valid"), populations["selected"])
    joint = {}
    for w_label, n_extra in np.unique(np.column_stack([w, extra]), axis=0):
        subset = (w == w_label) & (extra == n_extra)
        joint[f"W={int(w_label)},extra_b={int(n_extra)}"] = {
            key: int((subset & mask).sum()) for key, mask in populations.items()}
    sentinels = {}
    for name in ("QkCharge05_", "QkCharge10_"):
        values = slots(f"ak4Jet{name}")[real]
        sentinels[name.rstrip("_")] = {str(value): int((values == value).sum())
                                       for value in (-997, -998, -999)}
    return {"version": 1, "schema_sha256": schema["schema_sha256"], "counts": counts,
            "features": features, "joint_truth": joint, "charge_sentinels": sentinels,
            "histograms": {"n_jets": histogram(n_jets), "W_decay": histogram(w),
                           "extra_b_quarks": histogram(extra),
                           "extra_b_status": histogram(arrays["GenNExtraBQuarksStatus"]),
                           "W_lepton_flavor": histogram(arrays["GenWLeptonFlavor"]),
                           **b_histograms}}


def merge_summaries(summaries):
    """Combine independent file populations without averaging per-file fractions."""
    if not summaries:
        raise ValueError("No input summaries")
    if len({(item["version"], item["schema_sha256"]) for item in summaries}) != 1:
        raise ValueError("Input feature schemas differ")
    first = summaries[0]
    result = {"version": first["version"], "schema_sha256": first["schema_sha256"],
              "counts": {}, "features": {}, "joint_truth": {}, "charge_sentinels": {},
              "histograms": {}}
    for item in summaries:
        if set(item["features"]) != set(first["features"]):
            raise ValueError("Feature coverage differs")
        for key, count in item["counts"].items():
            result["counts"][key] = result["counts"].get(key, 0) + count
        for category in ("joint_truth", "charge_sentinels", "histograms"):
            for key, values in item[category].items():
                counter = Counter(result[category].get(key, {}))
                counter.update(values)
                result[category][key] = dict(counter)
        for key, values in item["features"].items():
            target = result["features"].setdefault(key, {})
            for field in ("eligible", "valid", "missing", "valid_zero"):
                target[field] = target.get(field, 0) + values[field]
            for field, operation in (("minimum", min), ("maximum", max)):
                finite = [x for x in (target.get(field), values[field]) if x is not None]
                target[field] = operation(finite) if finite else None
    return result


def render_summary(summary):
    lines = ["C1 input population audit", "Counts are unweighted selected events unless stated.",
             "Feature ranges are audit diagnostics, not fitted training normalization.", ""]
    lines += [f"{key}: {value:,}" for key, value in summary["counts"].items()]
    for key, values in summary["histograms"].items():
        lines += ["", key + ":", *[f"  {label}: {count:,}" for label, count in sorted(values.items())]]
    lines += ["", "Feature availability (missing / eligible; valid zeros):"]
    for key, values in summary["features"].items():
        lines.append(f"  {key}: {values['missing']:,} / {values['eligible']:,}; "
                     f"{values['valid_zero']:,}")
    lines += ["", "Ten-jet accounting measures discarded slots and matching with/without overflow.",
              "It does not attribute unmatched events uniquely to the cap.",
              "Reco/gen b-jet counts include all origins and use hadronFlavour == 5.",
              "Extra-b-jet categories, source combination and training splits are not defined here."]
    return "\n".join(lines) + "\n"
