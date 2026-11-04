"""Production gates prevent incomplete normalization and duplicate publication."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import uproot

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


def test_scale_zero_negative_and_large_ratios_remain_unclipped():
    lhe = np.array([[-2., 0., 1., 5., 2., 14., 1., 18., 20.]], dtype=np.float32)
    scales, _ = weights.expected_variations(lhe, np.ones((1, 4), dtype=np.float32))
    np.testing.assert_array_equal(scales, [[-1., 0., 2.5, 7., 9., 10.]])
    assert scales.dtype == np.float32


def test_pinned_configuration_rejects_changed_code(tmp_path):
    (tmp_path / "code").mkdir()
    code = tmp_path / "code/worker.py"
    code.write_text("version = 1\n")
    for name in ("inventory.json", "truth-manifest.json", "truth-certificate.json"):
        (tmp_path / name).write_text("{}\n")
    config = {"schema_version": 2, "weight_prescription_version": 3,
              "code_sha256": {"worker.py": campaign.sha(code)},
              "inventory": "inventory.json", "inventory_sha256": campaign.sha(tmp_path / "inventory.json"),
              "truth_manifest": "truth-manifest.json",
              "truth_manifest_sha256": campaign.sha(tmp_path / "truth-manifest.json"),
              "truth_certificate": "truth-certificate.json",
              "truth_certificate_sha256": campaign.sha(tmp_path / "truth-certificate.json")}
    campaign.write_json(tmp_path / "campaign.json", config)
    assert campaign.read_config(tmp_path) == config
    code.write_text("version = 2\n")
    with pytest.raises(ValueError, match="Frozen production code changed"):
        campaign.read_config(tmp_path)


def test_pilot_gate_pins_schema_and_result(tmp_path):
    gate = {"state": "passed", "normalization_rerun_byte_identical": True}
    for name, key in [("campaign.json", "campaign_sha256"), ("schema.json", "schema_sha256"),
                      ("schema.csv", "schema_csv_sha256"), ("pilot-result.json", "pilot_result_sha256"),
                      ("weight-prescription.json", "weight_prescription_sha256"),
                      ("pdf-layout.json", "pdf_layout_sha256")]:
        (tmp_path / name).write_text("{}\n")
        gate[key] = campaign.sha(tmp_path / name)
    (tmp_path / "plot.png").write_bytes(b"validated plot")
    gate["pilot_artifacts"] = {"plot.png": campaign.sha(tmp_path / "plot.png")}
    campaign.write_json(tmp_path / "pilot-passed.json", gate)
    assert campaign.check_gate(tmp_path) == gate
    (tmp_path / "schema.json").write_text('{"unexpected": "branch"}\n')
    with pytest.raises(ValueError, match="pilot/configuration changed"):
        campaign.check_gate(tmp_path)
    (tmp_path / "schema.json").write_text("{}\n")
    (tmp_path / "plot.png").write_bytes(b"changed plot")
    with pytest.raises(ValueError, match="pilot artifact changed"):
        campaign.check_gate(tmp_path)


def test_old_campaign_is_rejected_before_using_legacy_assumptions(tmp_path):
    campaign.write_json(tmp_path / "campaign.json", {"schema_version": 1})
    with pytest.raises(ValueError, match="new version-3 campaign"):
        campaign.read_config(tmp_path)


def test_reference_accepts_only_equal_integrated_values_and_metadata(monkeypatch, tmp_path):
    old, new = tmp_path / "reference.root", tmp_path / "pilot.root"
    fields = {"event": np.array([1, 2]), "PDFWeight0": np.array([1., -2.]),
              "weight_muon_id_statDown": np.array([1.e8, -2.e8])}

    def write(path, columns):
        with uproot.recreate(path) as out:
            out["Events"] = columns
            out["Norm"] = {"np_nominal": np.array([-1.])}

    write(old, {**fields, "finalWeight": np.array([1., -2.])})
    write(new, fields)
    monkeypatch.setattr(campaign, "read_saved_prescription", lambda _handle: {"version": 3})
    monkeypatch.setattr(campaign, "read_saved_layout", lambda _handle: {"lha_ids": [325500]})
    config = {"pilot_reference": str(old), "pilot_reference_sha256": campaign.sha(old)}
    assert campaign.compare_reference(new, config)["compared_branches"] == 3
    rounded = {**fields, "weight_muon_id_statDown": np.nextafter(fields["weight_muon_id_statDown"], np.inf)}
    write(new, rounded)
    result = campaign.compare_reference(new, config)
    assert 0 < result["maximum_component_relative_difference"] < campaign.COMPONENT_ROUNDOFF_RTOL
    # The allowance is restricted to the component-weight products.
    write(new, {**fields, "PDFWeight0": np.nextafter(fields["PDFWeight0"], np.inf)})
    with pytest.raises(AssertionError):
        campaign.compare_reference(new, config)
    write(new, {**fields, "weight_muon_id_statDown": fields["weight_muon_id_statDown"] * (1 + 1e-10)})
    with pytest.raises(AssertionError):
        campaign.compare_reference(new, config)
    monkeypatch.setattr(campaign, "read_saved_prescription", lambda _handle: {"version": 2})
    with pytest.raises(ValueError, match="obsolete"):
        campaign.compare_reference(new, config)


@pytest.mark.parametrize("sample", ["TTBB", "TT2Q", "TTCB"])
def test_matching_report_checks_counts_and_every_artifact(monkeypatch, tmp_path, sample):
    (tmp_path / "pilot/roots").mkdir(parents=True)
    (tmp_path / "logs").mkdir()
    root = tmp_path / "pilot/roots/one.root"
    root.write_bytes(b"stand-in ROOT")
    result = {"sample": sample, "b0": {"selected_events": 5, "fully_matched": 1,
                      "matching": {"greedy_fully_matched": 2}}}
    report = {"samples": {sample: {"counts": {
        "events_in_processed_files": 5, "fully_matched": 2,
        "b0_assignment_eligible": 1, "b0_mask_checked_events": 5},
        "files": [{"path": str(root)}]}}}

    def render(_argv, _log, **_kwargs):
        directory = tmp_path / "pilot-matching-report"
        directory.mkdir()
        (directory / "matching_summary.json").write_text(json.dumps(report))
        (directory / "matching_summary.txt").write_text("report")
        for population in ("fully_matched", "hadronic_top_matched"):
            for extension in ("png", "pdf"):
                (directory / f"{population}_masses.{extension}").write_bytes(b"plot")

    monkeypatch.setattr(campaign, "command", render)
    validated = campaign.matching_report(tmp_path, tmp_path / "pilot", [result], pilot=True)
    assert len(validated["artifacts"]) == 6
    report["samples"][sample]["counts"]["fully_matched"] = 1
    with pytest.raises(ValueError, match="accounting differs"):
        campaign.matching_report(tmp_path, tmp_path / "pilot", [result], pilot=True)
    report["samples"][sample]["counts"]["fully_matched"] = 2

    def incomplete_render(*args, **kwargs):
        render(*args, **kwargs)
        (tmp_path / "pilot-matching-report/fully_matched_masses.pdf").unlink()

    monkeypatch.setattr(campaign, "command", incomplete_render)
    with pytest.raises(ValueError, match="Missing matching-report artifact"):
        campaign.matching_report(tmp_path, tmp_path / "pilot", [result], pilot=True)


def test_pilot_report_failure_never_releases_production(monkeypatch, tmp_path):
    for name in ("roots", "pickles", "metadata"):
        (tmp_path / "pilot" / name).mkdir(parents=True)
    monkeypatch.setattr(campaign, "read_config", lambda _path: {"pilot_id": "one"})
    monkeypatch.setattr(campaign, "records_for", lambda _path: [{"id": "one"}])
    monkeypatch.setattr(campaign, "command", lambda *_args, **_kwargs: None)

    def run(*_args, **_kwargs):
        root = tmp_path / "pilot/roots/one.root"
        root.write_bytes(b"validated skim")
        return {"artifacts": {"root": {"path": str(root)}}}

    def fail(*_args, **_kwargs):
        raise ValueError("Report is incomplete")

    monkeypatch.setattr(campaign, "run_one", run)
    monkeypatch.setattr(campaign, "matching_report", fail)
    with pytest.raises(ValueError, match="Report is incomplete"):
        campaign.pilot(SimpleNamespace(campaign=tmp_path))
    assert not (tmp_path / "pilot-passed.json").exists()


def test_staged_input_checksum_failure(monkeypatch, tmp_path):
    path = tmp_path / "nano.root"

    def fake_copy(_argv, _log, **_kwargs):
        path.write_bytes(b"wrong bytes")

    monkeypatch.setattr(campaign, "command", fake_copy)
    record = {"nano_file": "root://example.test/input.root", "nano_bytes": 11,
              "nano_adler32": "00000000"}
    with pytest.raises(ValueError, match="Adler-32"):
        campaign.staged_input(record, path, tmp_path / "log")


def test_local_staging_preserves_content_and_rejects_changed_source(tmp_path):
    original, staged = tmp_path / "original.root", tmp_path / "staged.root"
    original.write_bytes(b"certified NanoAOD bytes")
    record = {"nano_file": str(original), "nano_bytes": original.stat().st_size,
              "nano_mtime_ns": original.stat().st_mtime_ns}
    campaign.staged_input(record, staged, tmp_path / "log")
    assert staged.read_bytes() == original.read_bytes()
    original.write_bytes(b"changed input")
    with pytest.raises(ValueError, match="certified inventory"):
        campaign.staged_input(record, staged, tmp_path / "log")


def test_local_staging_rejects_source_change_during_copy(monkeypatch, tmp_path):
    original, staged = tmp_path / "original.root", tmp_path / "staged.root"
    original.write_bytes(b"certified bytes")
    record = {"nano_file": str(original), "nano_bytes": original.stat().st_size,
              "nano_mtime_ns": original.stat().st_mtime_ns}

    def changed_copy(source, destination):
        destination.write_bytes(source.read_bytes())
        source.write_bytes(b"changed")

    monkeypatch.setattr(campaign.shutil, "copyfile", changed_copy)
    with pytest.raises(ValueError, match="changed during staging"):
        campaign.staged_input(record, staged, tmp_path / "log")


def test_normalization_registry_and_unknown_source():
    from boostedhh.hh_vars import LUMI
    from boostedhh.xsecs import xsecs

    for dataset in campaign.SAMPLE_DATASETS.values():
        assert weights.DATASET_SIGMA_LUMI[dataset] == xsecs[dataset] * LUMI["2024"]
    with pytest.raises(ValueError, match="Unsupported normalization dataset"):
        weights.validate(None, None, None, dataset="unregistered")


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
