"""Production gates prevent incomplete normalization and duplicate publication."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "condor/scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


campaign = load("ttbb_b0_campaign")
weights = load("validate_ttbb_b0_weights")


def test_theory_layout_and_scale_mapping():
    lhe = np.array([[2.4, 2.2, 9, 1.8, 2, 2.1, 9, 1.6, 1.5]])
    shower = np.array([[1.1, 1.2, .9, .8]])
    scales, ps = weights.expected_variations(lhe, shower)
    np.testing.assert_allclose(scales, [[1.2, 1.1, .9, 1.05, .8, .75]])
    assert {name: value[0] for name, value in ps.items()} == {
        "ISRPartonShowerUp": 1.1, "ISRPartonShowerDown": .9,
        "FSRPartonShowerUp": 1.2, "FSRPartonShowerDown": .8}
    with pytest.raises(ValueError, match="layout"):
        weights.expected_variations(lhe[:, :8], shower)
    lhe[:, 4] = 0
    with pytest.raises(ValueError, match="zero central"):
        weights.expected_variations(lhe, shower)


def test_pinned_configuration_rejects_changed_code(tmp_path):
    (tmp_path / "code").mkdir()
    code = tmp_path / "code/worker.py"
    code.write_text("version = 1\n")
    for name in ("inventory.json", "truth-manifest.json"):
        (tmp_path / name).write_text("{}\n")
    config = {"code_sha256": {"worker.py": campaign.sha(code)},
              "inventory": "inventory.json", "inventory_sha256": campaign.sha(tmp_path / "inventory.json"),
              "truth_manifest": "truth-manifest.json",
              "truth_manifest_sha256": campaign.sha(tmp_path / "truth-manifest.json")}
    campaign.write_json(tmp_path / "campaign.json", config)
    assert campaign.read_config(tmp_path) == config
    code.write_text("version = 2\n")
    with pytest.raises(ValueError, match="Frozen production code changed"):
        campaign.read_config(tmp_path)


def test_pilot_gate_pins_schema_and_result(tmp_path):
    gate = {"state": "passed"}
    for name, key in [("campaign.json", "campaign_sha256"), ("schema.json", "schema_sha256"),
                      ("schema.csv", "schema_csv_sha256"), ("pilot-result.json", "pilot_result_sha256")]:
        (tmp_path / name).write_text("{}\n")
        gate[key] = campaign.sha(tmp_path / name)
    campaign.write_json(tmp_path / "pilot-passed.json", gate)
    assert campaign.check_gate(tmp_path) == gate
    (tmp_path / "schema.json").write_text('{"unexpected": "branch"}\n')
    with pytest.raises(ValueError, match="pilot/configuration changed"):
        campaign.check_gate(tmp_path)


def test_staged_input_checksum_failure(monkeypatch, tmp_path):
    path = tmp_path / "nano.root"

    def fake_copy(_argv, _log, **_kwargs):
        path.write_bytes(b"wrong bytes")

    monkeypatch.setattr(campaign, "command", fake_copy)
    record = {"nano_file": "root://example.test/input.root", "nano_bytes": 11,
              "nano_adler32": "00000000"}
    with pytest.raises(ValueError, match="Adler-32"):
        campaign.staged_input(record, path, tmp_path / "log")


def test_incomplete_campaign_cannot_normalize(monkeypatch, tmp_path):
    (tmp_path / "status").mkdir()
    campaign.write_json(tmp_path / "status/one.json", {"id": "one"})
    monkeypatch.setattr(campaign, "read_config", lambda _path: {})
    monkeypatch.setattr(campaign, "check_gate", lambda _path: {})
    monkeypatch.setattr(campaign, "records_for", lambda _path: [{"id": "one"}, {"id": "two"}])
    calls = []
    monkeypatch.setattr(campaign, "command", lambda *args, **kwargs: calls.append((args, kwargs)))
    with pytest.raises(ValueError, match="Missing or extra production statuses"):
        campaign.finalize(SimpleNamespace(campaign=tmp_path))
    assert calls == []
    assert not (tmp_path / "pre-normalization.json").exists()


def test_worker_retry_checks_outputs_without_processing_again(monkeypatch, tmp_path):
    for directory in ("locks", "status"):
        (tmp_path / directory).mkdir()
    artifact = tmp_path / "output.root"
    artifact.write_bytes(b"validated output")
    result = {"state": "complete", "artifacts": {
        "root": {"path": str(artifact), "sha256": campaign.sha(artifact)}}}
    campaign.write_json(tmp_path / "status/one.json", result)
    monkeypatch.setattr(campaign, "read_config", lambda _path: {})
    monkeypatch.setattr(campaign, "check_gate", lambda _path: {})
    monkeypatch.setattr(campaign, "records_for", lambda _path: [{"id": "one"}])
    calls = []
    monkeypatch.setattr(campaign, "run_one", lambda *args, **kwargs: calls.append((args, kwargs)))
    campaign.worker(SimpleNamespace(campaign=tmp_path, id="one"))
    assert calls == []
    artifact.write_bytes(b"changed output")
    with pytest.raises(ValueError, match="Previously published worker output changed"):
        campaign.worker(SimpleNamespace(campaign=tmp_path, id="one"))
    assert calls == []


def test_dag_contains_every_input_and_only_then_finalizes(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign, "read_config", lambda _path: {"max_jobs": 40})
    monkeypatch.setattr(campaign, "check_gate", lambda _path: {})
    monkeypatch.setattr(campaign, "records_for", lambda _path: [{"id": "one"}, {"id": "two"}])
    campaign.authorize(SimpleNamespace(campaign=tmp_path))
    dag = (tmp_path / "production.dag").read_text()
    assert "PARENT one CHILD FINALIZE" in dag
    assert "PARENT two CHILD FINALIZE" in dag
    assert "RETRY one 2" in dag
    assert "RETRY two 2" in dag
    assert sum(line.startswith("JOB ") for line in dag.splitlines()) == 3
    with pytest.raises(FileExistsError):
        campaign.authorize(SimpleNamespace(campaign=tmp_path))
