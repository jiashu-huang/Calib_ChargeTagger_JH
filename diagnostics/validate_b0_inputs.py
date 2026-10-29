"""Check a B0 skim against its input file, raw observables and truth sidecar."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID

import numpy as np
import uproot

from validate_ttbb_matching import audit as matching_audit


def validate(nano: Path, skim: Path, metadata: Path, manifest: Path | None = None) -> dict:
    run_metadata = json.loads(metadata.read_text())
    assert run_metadata["input_profile"] == "b0"
    schema = run_metadata["b0_schema"]
    claimed_schema_hash = schema.pop("schema_sha256")
    assert hashlib.sha256(json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()).hexdigest() == claimed_schema_hash
    schema["schema_sha256"] = claimed_schema_hash
    with uproot.open(skim) as source:
        a = source["Events"].arrays(library="np")
        norm = source["Norm"].arrays(library="np")
    size = len(a["event"])
    entries = a["B0SourceEntry"]
    assert entries.dtype == np.dtype("uint64") and len(np.unique(entries)) == size
    with uproot.open(nano) as source:
        uuid = UUID(str(source.file.uuid))
        source_size = source["Events"].num_entries
        ids = source["Events"].arrays(["run", "luminosityBlock", "event"], library="np")
        input_sumw = source["Events"]["genWeight"].array(library="np").sum(dtype=np.float64)
        for field in ids:
            np.testing.assert_array_equal(a[field], ids[field][entries])
    # The inherited MC Norm.nevents name stores signed genWeight, not raw count.
    np.testing.assert_allclose(norm["nevents"].sum(), input_sumw, rtol=1e-6)
    for slot, shift in enumerate((96, 64, 32, 0)):
        assert a[f"B0SourceUUID{slot}"].dtype == np.dtype("uint32")
        assert np.all(a[f"B0SourceUUID{slot}"] == ((uuid.int >> shift) & 0xFFFFFFFF))
    assert np.all(a["B0SchemaVersion"] == schema["schema_version"])

    def slots(prefix):
        return np.column_stack([a[f"{prefix}{i}"] for i in range(10)])

    real = slots("B0JetMask").astype(bool)
    pt, eta, phi, mass = [slots(f"ak4Jet{x}") for x in ("Pt", "Eta", "Phi", "Mass")]
    assert np.all(real.sum(axis=1) >= 4)
    assert np.all(pt[real] > 25) and np.all(abs(eta[real]) < 2.4)
    assert np.all(np.diff(np.where(real, pt, -1e10), axis=1)[real[:, 1:]] <= 0)
    np.testing.assert_array_equal(real.sum(axis=1), np.minimum(a["nJets"], 10))
    np.testing.assert_array_equal(a["B0Event_n_selected_jets"], a["nJets"])
    np.testing.assert_allclose(a["B0Event_selected_HT"], a["ht"], rtol=1e-6)
    np.testing.assert_array_equal(a["B0Event_n_overflow"], np.maximum(a["nJets"] - 10, 0))

    missing = {}
    for feature in schema["jet_features"]:
        value, valid = slots(f"B0Jet_{feature}_"), slots(f"B0Jet_{feature}_valid_").astype(bool)
        assert np.isfinite(value).all(), feature
        assert not valid[~real].any(), feature
        assert np.all(value[~valid] == 0), feature
        missing[feature] = int((real & ~valid).sum())
    for feature in schema["event_features"]:
        value, valid = a[f"B0Event_{feature}"], a[f"B0Event_{feature}_valid"].astype(bool)
        assert np.isfinite(value).all() and np.all(value[~valid] == 0), feature

    for feature, expected in {
        "log1p_pt": np.log1p(np.maximum(pt, 0)),
        "log1p_mass": np.log1p(np.maximum(mass, 0)),
        "eta": eta, "sin_phi": np.sin(phi), "cos_phi": np.cos(phi),
    }.items():
        valid = slots(f"B0Jet_{feature}_valid_").astype(bool)
        np.testing.assert_allclose(slots(f"B0Jet_{feature}_")[valid], expected[valid], rtol=1e-6,
                                   atol=1e-7)

    zero_counts = {}
    for feature, raw_field in (("Qk05", "QkCharge05_"), ("Qk10", "QkCharge10_")):
        raw = slots(f"ak4Jet{raw_field}")
        expected_valid = real & np.isfinite(raw) & ((raw > -900) | (raw == -997))
        expected = np.where(expected_valid & (raw != -997), raw, 0.0)
        np.testing.assert_array_equal(slots(f"B0Jet_{feature}_valid_"), expected_valid)
        np.testing.assert_allclose(slots(f"B0Jet_{feature}_"), expected, rtol=1e-6)
        zero_counts[feature] = int((real & (raw == -997)).sum())

    assignments = np.column_stack([a[f"Gen{role}JetIdx"]
                                  for role in ("HadB", "LepB", "HadQ1", "HadQ2")])
    full = np.all((assignments >= 0) & (assignments < real.sum(axis=1)[:, None]), axis=1)
    full &= np.all(np.diff(np.sort(assignments, axis=1), axis=1) != 0, axis=1)
    np.testing.assert_array_equal(a["B0AssignmentMask"], full & a["GenWDecayValid"])
    for value, valid in (("GenWDecay", "GenWDecayValid"),
                         ("GenNExtraBQuarks", "GenNExtraBQuarksValid")):
        assert np.all(a[value][~a[valid]] == -1)
    sidecar_checked = False
    if manifest is not None:
        assert run_metadata["truth_label_manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
        records = json.loads(manifest.read_text())["files"]
        record = next(x for x in records if x["nano_uuid"] == str(uuid))
        path = manifest.parent / record["labels"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
        with np.load(path, allow_pickle=False) as labels:
            np.testing.assert_array_equal(a["GenNExtraBQuarks"], labels["count"][entries])
            np.testing.assert_array_equal(a["GenNExtraBQuarksStatus"], labels["status"][entries])
        sidecar_checked = True

    matching = matching_audit(skim)
    assert matching["passed"]
    def counts(field):
        values, numbers = np.unique(a[field], return_counts=True)
        return dict(zip((str(x) for x in values), numbers.tolist()))
    return {
        "passed": True, "input": str(nano.resolve()), "skim": str(skim.resolve()),
        "input_events": source_size, "selected_events": size, "branches": len(a),
        "input_signed_genweight_sum": float(input_sumw),
        "input_uuid": str(uuid), "schema_sha256": schema["schema_sha256"],
        "sidecar_checked": sidecar_checked,
        "fully_matched": int(a["B0AssignmentMask"].sum()),
        "unmatched_with_W_label": int((~a["B0AssignmentMask"] & a["GenWDecayValid"]).sum()),
        "unmatched_with_quark_count": int((~a["B0AssignmentMask"] & a["GenNExtraBQuarksValid"]).sum()),
        "W_labels": counts("GenWDecay"), "extra_b_counts": counts("GenNExtraBQuarks"),
        "W_lepton_flavors": counts("GenWLeptonFlavor"),
        "valid_zero_Qk_from_sentinel": zero_counts, "missing_features": missing,
        "overflow_events": int((a["nJets"] > 10).sum()), "matching": matching,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("nano", "skim", "metadata", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--truth-manifest", type=Path)
    args = parser.parse_args()
    result = validate(args.nano, args.skim, args.metadata, args.truth_manifest)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
