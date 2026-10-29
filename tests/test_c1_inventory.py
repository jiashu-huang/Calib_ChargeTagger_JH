"""Counterexamples for C1 source coverage and metadata accounting."""

from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path

import numpy as np
import pytest
import uproot

SPEC = importlib.util.spec_from_file_location(
    "c1_inventory", Path(__file__).parents[1] / "condor/scripts/c1_inventory.py")
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)
LFN = "/store/mc/RunIII2024Summer24MiniAODv6/TTtoLNuCB/MINIAODSIM/v1/0000/a.root"


def test_duplicate_source_or_ambiguous_basename_is_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        inventory.unique_sources([LFN, LFN])
    with pytest.raises(ValueError, match="ambiguous"):
        inventory.unique_sources([LFN, LFN.replace("0000", "0001")])
    with pytest.raises(ValueError, match="outside"):
        inventory.unique_sources([LFN.replace("2024", "2023")])


def test_duplicate_conversion_uuid_is_rejected_across_sources():
    records = [{"id": "a", "nano_uuid": "same", "source_lfn": "a", "nano_file": "a"},
               {"id": "b", "nano_uuid": "same", "source_lfn": "b", "nano_file": "b"}]
    with pytest.raises(ValueError, match="nano_uuid"):
        inventory.validate_uniqueness(records)


def test_declared_but_absent_local_conversion_is_an_error(tmp_path):
    sample = tmp_path / "MC/sample"
    inputs = sample / "productions" / inventory.PRODUCTION / "cmssw/input-lists" / inventory.PRODUCTION
    inputs.mkdir(parents=True)
    (inputs / "files_all.txt").write_text(LFN + "\n")
    (inputs / "dataset.txt").write_text("dataset\n")
    with pytest.raises(ValueError, match="missing"):
        inventory.local_records(tmp_path, "TTCB", "sample")
    folder = sample / "NanoAOD-cmssw-charge" / inventory.PRODUCTION / "batch_000"
    folder.mkdir(parents=True)
    (folder / ("a" + inventory.NANO_SUFFIX)).write_bytes(b"header checked separately")
    rows, source = inventory.local_records(tmp_path, "TTCB", "sample")
    assert rows[0]["source_lfn"] == LFN
    assert source["declared_files"] == 1
    assert rows[0]["native_truth"] == inventory.REDIRECTOR + LFN
    assert rows[0]["native_kind"] == "remote MiniAOD"


def test_header_counts_are_actual_events_and_mismatch_is_preserved(tmp_path):
    path = tmp_path / "nano.root"
    with uproot.recreate(path) as output:
        output["Events"] = {name: np.arange(3) for name in inventory.REQUIRED_BRANCHES}
        output["Runs"] = {"genEventCount": np.array([4]),
                          "genEventSumw": np.array([-2.0]), "genEventSumw2": np.array([9.0])}
    record = {"id": "source", "nano_file": str(path)}
    inspected = inventory.inspect_nano(record)
    assert inspected["entries"] == 3
    assert inspected["sumw"] == -2.0
    assert not inspected["runs_count_matches_events"]
    with pytest.raises(ValueError, match="entry count"):
        inventory.inspect_nano({**record, "expected_events": 4})


def test_root_header_reader_agrees_with_independent_uproot_reader(tmp_path):
    pytest.importorskip("ROOT")
    path = tmp_path / "nano.root"
    # CMSSW writes the same UUID in the TFile and root TDirectory headers.
    # Uproot's writer otherwise generates distinct UUIDs for those two headers.
    source_uuid = uuid.uuid4()
    with uproot.recreate(path, uuid_function=lambda: source_uuid) as output:
        output["Events"] = {name: np.arange(3) for name in inventory.REQUIRED_BRANCHES}
        output["Runs"] = {"genEventCount": np.array([4]),
                          "genEventSumw": np.array([-2.0]), "genEventSumw2": np.array([9.0])}
    record = {"id": "source", "nano_file": str(path)}
    fast, reference = inventory.inspect_nano_root(record), inventory.inspect_nano(record)
    for field in ("nano_uuid", "entries", "runs_genEventCount", "runs_count_matches_events",
                  "sumw", "sumw2", "branch_count"):
        assert fast[field] == reference[field]
    with pytest.raises(ValueError, match="entry count"):
        inventory.inspect_nano_root({**record, "expected_events": 4})


def test_partial_ttbb_catalog_cannot_replace_complete_source(tmp_path):
    p = tmp_path / "cmssw-charge-run/productions/ttbb_eos_20261024"
    p.mkdir(parents=True)
    lfn = LFN.replace("TTtoLNuCB", "TTBB-TTtoLNu2Q")
    manifest = {"input_files": [{"lfn": lfn}]}
    (p / "manifest.json").write_text(json.dumps(manifest))
    (p / "completion.json").write_text(json.dumps({
        "state": "completed", "manifest_sha256": inventory.digest(p / "manifest.json"),
        "input_files": 1, "events": 100}))
    catalog = {"dataset": "TTBB", "files": [{"lfn": lfn, "source_file_events": 100,
                                              "skip_events": 10, "max_events": 90}]}
    (p / "catalog.json").write_text(json.dumps(catalog))
    with pytest.raises(ValueError, match="Partial"):
        inventory.ttbb_records(tmp_path)
