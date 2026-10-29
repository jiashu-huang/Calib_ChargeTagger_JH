"""Production failure cases: a readable NPZ or success marker is not certification."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location(
    "c1_campaign", Path(__file__).parents[1] / "condor/scripts/c1_truth_campaign.py")
campaign = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(campaign)


@pytest.fixture
def example(tmp_path):
    root = tmp_path / "campaign"
    directory = root / "pairs/TTCB/TTCB_source"
    directory.mkdir(parents=True)
    record = {"id": "TTCB_source", "sample": "TTCB", "nano_uuid": "source-uuid",
              "entries": 3, "source_lfn": "/store/source.root"}
    pins = {}
    for name in ("condor/scripts/build_truth_labels.py", "src/vcb/truth.py"):
        target = root / "code" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(name)
        pins[name] = campaign.sha(target)
    config = {"code_sha256": pins, "inventory_sha256": "pending"}
    values = {"run": np.array([1, 1, 1]), "luminosityBlock": np.array([2, 2, 2]),
              "event": np.array([100, 101, 102]), "count": np.array([0, 2, -1]),
              "status": np.array([0, 0, 3]), "nano_uuid": np.array("source-uuid"),
              "schema_version": np.array(1)}
    np.savez_compressed(directory / "labels.npz", **values)
    row = {"nano_uuid": record["nano_uuid"], "entries": 3, "labels": "labels.npz",
           "sha256": campaign.sha(directory / "labels.npz"), "native_entries_reordered": 0,
           "counts": {"-1": 1, "0": 1, "2": 1}, "statuses": {"0": 2, "3": 1},
           "pair_validation": "content and identity checked"}
    manifest = {"schema_version": 1, "producer_sha256": pins["condor/scripts/build_truth_labels.py"],
                "definition_sha256": pins["src/vcb/truth.py"], "files": [row]}
    campaign.write_json(directory / "manifest.json", manifest)
    campaign.write_json(root / "inventory.json", {"files": [record]})
    config["inventory_sha256"] = campaign.sha(root / "inventory.json")
    campaign.write_json(root / "campaign.json", config)
    return root, directory, record, config, values, manifest


@pytest.mark.parametrize(("field", "replacement", "error"), [
    ("count", np.array([0, 2, 0]), "count/status"),
    ("status", np.array([0, 0, 99]), "count/status"),
    ("event", np.array([100, 101, 100]), "Duplicate identities"),
    ("event", np.array([100, 101]), "Malformed"),
    ("nano_uuid", np.array("another-source"), "UUID"),
    ("count", np.array([1, 2, -1]), "summary differs"),
])
def test_semantic_corruption_is_rejected_even_with_updated_hash(example, field, replacement, error):
    _, directory, record, config, values, manifest = example
    values[field] = replacement
    np.savez_compressed(directory / "labels.npz", **values)
    manifest["files"][0]["sha256"] = campaign.sha(directory / "labels.npz")
    campaign.write_json(directory / "manifest.json", manifest)
    with pytest.raises(ValueError, match=error):
        campaign.validate_pair(directory, record, config)


def test_unexpected_source_producer_or_bytes_are_rejected(example):
    _, directory, record, config, _, manifest = example
    with pytest.raises(ValueError, match="source UUID"):
        campaign.validate_pair(directory, {**record, "nano_uuid": "different"}, config)
    manifest["definition_sha256"] = "different truth convention"
    campaign.write_json(directory / "manifest.json", manifest)
    with pytest.raises(ValueError, match="definition"):
        campaign.validate_pair(directory, record, config)
    manifest["definition_sha256"] = config["code_sha256"]["src/vcb/truth.py"]
    campaign.write_json(directory / "manifest.json", manifest)
    (directory / "labels.npz").write_bytes(b"truncated")
    with pytest.raises(ValueError, match="checksum"):
        campaign.validate_pair(directory, record, config)


def test_incomplete_coverage_never_publishes_usable_manifest(example):
    root, _, record, config, _, _ = example
    second = {**record, "id": "TTCB_missing", "nano_uuid": "missing", "source_lfn": "missing"}
    campaign.write_json(root / "inventory.json", {"files": [record, second]})
    config["inventory_sha256"] = campaign.sha(root / "inventory.json")
    campaign.write_json(root / "campaign.json", config)
    with pytest.raises(RuntimeError, match="coverage incomplete"):
        campaign.collect(root)
    status = json.loads((root / "truth-status.json").read_text())
    assert status["summary"]["TTCB"]["verified_events"] == 3
    assert status["summary"]["TTCB"]["expected_events"] == 6
    assert status["state"] == "incomplete"
    assert not (root / "TTCB-truth-manifest.json").exists()
    assert not (root / "completion.json").exists()


def test_complete_manifest_preserves_unknowns_and_resolves_label_paths(example):
    root, directory, _, _, _, _ = example
    campaign.collect(root)
    manifest = json.loads((root / "TTCB-truth-manifest.json").read_text())
    assert root / manifest["files"][0]["labels"] == directory / "labels.npz"
    report = json.loads((root / "completion.json").read_text())
    assert report["state"] == "complete"
    assert report["summary"]["TTCB"]["counts"]["-1"] == 1
    assert report["summary"]["TTCB"]["statuses"]["3"] == 1
    assert not report["b0_skims_started"]
    campaign.collect(root)  # Idempotent certification of identical immutable outputs.


def test_resume_validates_outputs_and_never_rebuilds_them(example, monkeypatch):
    root, directory, record, config, _, _ = example

    def unexpected_command(*_args, **_kwargs):
        pytest.fail("An already verified sidecar must not be regenerated")

    monkeypatch.setattr(campaign, "command", unexpected_command)
    assert campaign.run_pair(root, record, config)["entries"] == 3
    (directory / "labels.npz").write_bytes(b"corruption after success")
    with pytest.raises(ValueError, match="checksum"):
        campaign.run_pair(root, record, config)


def test_failed_builder_never_publishes_a_pair(example, monkeypatch):
    root, _, record, config, _, _ = example
    record = {**record, "id": "TTCB_new", "native_kind": "remote MiniAOD",
              "nano_file": "root://example/nano", "native_truth": "root://example/mini"}
    (root / "attempts").mkdir()
    config["pair_timeout_seconds"] = 1

    def fail_after_partial_output(argv, _log, **_kwargs):
        output = Path(argv[-1])
        output.mkdir()
        (output / "labels.npz").write_bytes(b"partial")
        raise RuntimeError("interrupted builder")

    monkeypatch.setattr(campaign, "command", fail_after_partial_output)
    with pytest.raises(RuntimeError, match="interrupted"):
        campaign.run_pair(root, record, config)
    assert not (root / "pairs/TTCB/TTCB_new").exists()
    assert len(list((root / "attempts").glob("*/failure.json"))) == 1


def test_pinned_inventory_and_worker_code_are_enforced(example):
    root, _, _, _, _, _ = example
    campaign.read_pinned(root)
    (root / "code/src/vcb/truth.py").write_text("unreviewed convention change")
    with pytest.raises(ValueError, match="Pinned campaign code changed"):
        campaign.read_pinned(root)


def test_campaign_partitions_sources_and_gates_bulk_jobs_on_worker_pilots(tmp_path):
    records = [{"id": f"{s}_{i}", "nano_uuid": f"uuid_{s}_{i}", "source_lfn": f"lfn_{s}_{i}",
                "sample": s} for s in ("TT2Q", "TTCB", "TTBB") for i in range(7)]
    campaign.write_json(tmp_path / "inventory.json", {"files": records})
    args = SimpleNamespace(files_per_job=5, max_jobs=40, pair_timeout=7200,
                           cmssw=tmp_path / "cmssw", proxy=tmp_path / "proxy")
    campaign.prepare(tmp_path, args)
    config = campaign.read_pinned(tmp_path)
    dag = (tmp_path / "production.dag").read_text()
    assert len(config["pilot_batches"]) == 3
    assigned = []
    for batch, digest in config["batch_sha256"].items():
        path = tmp_path / "batches" / (batch + ".json")
        assert campaign.sha(path) == digest
        rows = json.loads(path.read_text())["files"]
        assigned.extend(r["id"] for r in rows)
        if batch in config["pilot_batches"]:
            assert len(rows) == 1
        else:
            assert len(rows) <= 5
            assert ("PARENT " + " ".join(config["pilot_batches"]) + " CHILD " + batch) in dag
    assert sorted(assigned) == sorted(r["id"] for r in records)
    assert "FINAL certify" in dag
