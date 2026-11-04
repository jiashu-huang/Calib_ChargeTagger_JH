"""C1 cannot close on a missing, altered or incompatible source population."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import numpy as np
import pytest
import uproot


@pytest.fixture
def helper(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "condor/scripts"))
    return importlib.import_module("c1_input_readiness")


def source_campaign(path, sample, helper, monkeypatch):
    path.mkdir()
    counts = {"selected": 10, "fully_matched": 3, "hadronic_top_matched": 4,
              "assignment_eligible": 3, "W_label_valid": 10, "extra_b_label_valid": 9,
              "reco_b_jets_count_valid": 10, "gen_b_jets_count_valid": 10}
    audit = {"schema_sha256": "schema2", "counts": counts,
             "histograms": {"extra_b_quarks": {"0": 8, "2": 1, "-1": 1}}}
    config = {"sample": sample, "dataset": helper.SAMPLE_DATASETS[sample],
              "processor_commit": "commit", "files": 2, "input_events": 100,
              "truth_certificate": "truth-certificate.json", "truth_certificate_sha256": "certificate"}
    for name, value in {"input-audit.json": audit, "publication.json": {},
                        "pilot-result.json": {"b0": {"schema_sha256": "schema2"}},
                        "truth-certificate.json": {"summary": {
                            sample: {"verified_files": 2, "verified_events": 100}}}}.items():
        (path / name).write_text(json.dumps(value))
    (path / "input-audit.txt").write_text("population")
    completion = {"state": "complete", "training_started": False,
                  "processor_commit": "commit", "files": 2, "input_events": 100,
                  "selected_events": 10,
                  "matching_counts": {"fully_matched": 3, "hadronic_top_matched": 4,
                                      "b0_assignment_eligible": 3},
                  "matching_artifacts": {}, "matching_summary": "matching.txt"}
    reports = ["matching_summary.txt", "matching_summary.json"]
    reports += [f"{population}_masses.{extension}"
                for population in ("fully_matched", "hadronic_top_matched")
                for extension in ("png", "pdf")]
    (path / "matching-report").mkdir()
    for name in reports:
        report = path / "matching-report" / name
        report.write_text("unit fixture")
        completion["matching_artifacts"][f"matching-report/{name}"] = helper.sha(report)
    for name, key in (("publication.json", "publication_sha256"),
                      ("input-audit.json", "input_audit_sha256"),
                      ("input-audit.txt", "input_audit_text_sha256")):
        completion[key] = helper.sha(path / name)
    (path / "completion.json").write_text(json.dumps(completion))
    monkeypatch.setattr(helper, "read_config", lambda _: config)
    monkeypatch.setattr(helper, "check_gate", lambda _: {})
    return completion


def test_source_gate_checks_coverage_reports_and_labels(helper, tmp_path, monkeypatch):
    path = tmp_path / "TT2Q"
    source_campaign(path, "TT2Q", helper, monkeypatch)
    result = helper.check_source("TT2Q", path)
    assert result["input_events"] == 100
    assert result["counts"]["extra_b_label_valid"] == 9
    (path / "input-audit.txt").write_text("changed")
    with pytest.raises(ValueError, match="artifact changed"):
        helper.check_source("TT2Q", path)


@pytest.mark.parametrize(("field", "value"), [("state", "running"), ("files", 1),
                                               ("input_events", 99), ("training_started", True)])
def test_source_gate_rejects_incomplete_coverage(helper, tmp_path, monkeypatch, field, value):
    path = tmp_path / "TTBB"
    completion = source_campaign(path, "TTBB", helper, monkeypatch)
    completion[field] = value
    (path / "completion.json").write_text(json.dumps(completion))
    with pytest.raises(ValueError, match="incomplete or inconsistent"):
        helper.check_source("TTBB", path)


def test_all_sources_need_the_same_schema_and_remain_separate(helper, tmp_path, monkeypatch):
    sources = {sample: {"processor_commit": "commit", "truth_certificate_sha256": "certificate",
                        "schema_sha256": "schema2", "input_files": 2, "input_events": 100,
                        "counts": {"selected": 10}, "population_report": "audit.txt",
                        "matching_report": "matching.txt",
                        "histograms": {"extra_b_quarks": {"0": 9, "2": 1}}}
               for sample in helper.SAMPLE_DATASETS}
    monkeypatch.setattr(helper, "check_source", lambda sample, _: sources[sample])
    campaigns = {sample: tmp_path / sample for sample in sources}
    result = helper.collect(campaigns)
    assert result["state"] == "complete"
    assert set(result["sources"]) == {"TT2Q", "TTCB", "TTBB"}
    assert not result["training_started"]
    assert "not a combined physics yield" in helper.render(result)
    with pytest.raises(ValueError, match="exactly TT2Q"):
        helper.collect({"TTBB": campaigns["TTBB"]})
    sources["TTCB"]["schema_sha256"] = "schema1"
    with pytest.raises(ValueError, match="disagree on schema"):
        helper.collect(campaigns)


def test_zero_selected_events_have_valid_matching_accounting(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "diagnostics"))
    matching = importlib.import_module("validate_ttbb_matching")
    fields = {f"ak4Jet{component}{slot}": np.array([], dtype=np.float64)
              for component in ("Pt", "Eta", "Phi") for slot in range(10)}
    fields.update({f"{parton}{component}": np.array([], dtype=np.float64)
                   for parton in matching.PARTONS for component in ("Pt", "Eta", "Phi")})
    fields.update({f"Gen{role}JetIdx": np.array([], dtype=np.int32) for role in matching.ROLES})
    path = tmp_path / "empty.root"
    with uproot.recreate(path) as output:
        output["Events"] = fields
    result = matching.audit(path)
    assert result["passed"]
    assert result["selected_events"] == 0
    assert result["greedy_fully_matched"] == 0
    assert result["greedy_fully_matched_fraction"] is None
    json.dumps(result, allow_nan=False)
