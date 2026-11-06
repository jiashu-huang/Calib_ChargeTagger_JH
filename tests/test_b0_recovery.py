"""A recovery must carry immutable code, evidence and per-input provenance."""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def recovery(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "condor/scripts"))
    helper = importlib.import_module("ttbb_b0_campaign")
    source = "src/vcb/processors/vcbSkimmer.py"
    code = tmp_path / "code" / source
    code.parent.mkdir(parents=True)
    code.write_text("selected MET validation")
    config = {"processor_commit": "base", "code_sha256": {source: "old-source-hash"}}
    evidence = dict.fromkeys(("healthy_reference_unchanged", "calibration_baselines_unchanged",
                             "selected_nonfinite_control_rejected", "unit_tests_passed"), True)
    evidence["processing_source_sha256"] = {source: helper.sha(code)}
    evidence["recovered"] = {"input": {"nonfinite_met_selected": 0,
                                       "input_events": 20, "selected_events": 3,
                                       "artifacts": {k: {"sha256": k} for k in ("root", "pickle", "metadata")}}}
    manifest = {"version": 1, "kind": "selected-event-met-validation",
                "base_processor_commit": "base", "processor_commit": "fixed",
                "files": {"input": "uuid"}, "code_directory": str(tmp_path / "code"),
                "code_sha256": {source: helper.sha(code)}}
    result = {"id": "input", "state": "complete", "source": {"nano_uuid": "uuid"},
              "b0": {"passed": True, "input_events": 20, "selected_events": 3},
              "weights": {"passed": True},
              "artifacts": {k: {"sha256": k} for k in ("root", "pickle", "metadata")}}

    def pin():
        helper.write_json(tmp_path / "evidence.json", evidence)
        manifest["validation"] = {"path": str(tmp_path / "evidence.json"),
                                  "sha256": helper.sha(tmp_path / "evidence.json")}
        helper.write_json(tmp_path / "recovery.json", manifest)
        result["recovery"] = {"processor_commit": manifest["processor_commit"],
                              "manifest_sha256": helper.sha(tmp_path / "recovery.json")}
        helper.write_json(tmp_path / "status/input.json", result)

    pin()
    return helper, tmp_path, config, manifest, evidence, result, pin


def test_recovery_receipt_survives_finalization_and_reinspection(recovery):
    helper, path, config, _, _, result, _ = recovery
    checked = helper.check_recovery(path, config, [result])
    assert checked == helper.check_recovery(path, config)
    assert checked["processor_commit"] == "fixed"
    assert checked["base_processor_commit"] == "base"
    assert checked["files"] == ["input"]


@pytest.mark.parametrize("change", ["code", "evidence", "base", "source", "selected", "coverage",
                                    "tested_source", "artifact"])
def test_incompatible_or_changed_recovery_is_rejected(recovery, change):
    helper, path, config, manifest, evidence, result, pin = recovery
    if change == "code":
        (path / "code/src/vcb/processors/vcbSkimmer.py").write_text("changed")
    elif change == "evidence":
        (path / "evidence.json").write_text("changed")
    elif change == "base":
        manifest["base_processor_commit"] = "unrelated"
        pin()
    elif change == "source":
        manifest["code_sha256"]["src/other.py"] = "unaudited"
        pin()
    elif change == "selected":
        evidence["recovered"]["input"]["nonfinite_met_selected"] = 1
        pin()
    elif change == "coverage":
        result = {**result, "id": "other-input"}
    elif change == "tested_source":
        evidence["processing_source_sha256"] = {}
        pin()
    elif change == "artifact":
        result["artifacts"]["root"]["sha256"] = "different-output"
        pin()
    with pytest.raises(ValueError, match=r"changed|Invalid recovery|unaudited|inconsistent|differs"):
        helper.check_recovery(path, config, [result])


def test_unrecorded_recovery_cannot_enter_an_ordinary_campaign(recovery):
    helper, path, config, _, _, result, _ = recovery
    (path / "recovery.json").unlink()
    with pytest.raises(ValueError, match="no pinned recovery"):
        helper.check_recovery(path, config, [result])
    assert helper.check_recovery(path, config, []) is None


def test_completion_cannot_hide_recovery_provenance(recovery, monkeypatch):
    helper, path, config, _, _, _, _ = recovery
    gate = importlib.import_module("c1_input_readiness")
    monkeypatch.setattr(gate, "read_config", lambda _: {**config, "sample": "TT2Q",
                                                       "dataset": "TTtoLNu2Q"})
    monkeypatch.setattr(gate, "check_gate", lambda _: {})
    helper.write_json(path / "completion.json", {"state": "complete"})
    with pytest.raises(ValueError, match="recovery provenance"):
        gate.check_source("TT2Q", path)
