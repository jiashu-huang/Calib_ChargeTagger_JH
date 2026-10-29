"""Physics counterexamples and source-safe joins for the two event truth labels."""

from __future__ import annotations

import importlib.util
import io
import json
import shlex
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import awkward as ak
import numpy as np
import pytest

from vcb.processors.GenSelection import _event_w_decay_labels
from vcb.processors.truth_labels import extra_b_labels, read_truth_manifest
from vcb.truth import (
    FIRST_COPY,
    FROM_HARD_PROCESS,
    HARD_PROCESS,
    LAST_COPY,
    TRUTH_LABEL_VERSION,
    CountStatus,
    count_extra_b_quarks,
)

HARD = HARD_PROCESS | FROM_HARD_PROCESS


def record(signal=False):
    # Two tops, their primary b lines, and the hadronic W.
    return [
        (6, 62, HARD | FIRST_COPY | LAST_COPY, []),
        (-6, 62, HARD | FIRST_COPY | LAST_COPY, []),
        (5, 23, HARD | FIRST_COPY, [0]),
        (-5, 23, HARD | FIRST_COPY, [1]),
        (24, 22, HARD | FIRST_COPY | LAST_COPY, [0]),
        (5, 71, FROM_HARD_PROCESS | LAST_COPY, [2]),
        (-5, 71, FROM_HARD_PROCESS | LAST_COPY, [3]),
    ] + ([(-5, 23, HARD | FIRST_COPY, [4]),
          (-5, 71, FROM_HARD_PROCESS | LAST_COPY, [7])] if signal else [])


def count(particles, complete=True):
    return count_extra_b_quarks(*zip(*particles, strict=True), complete_record=complete)


@pytest.mark.parametrize("signal", [False, True])
def test_primary_top_and_w_b_lines_are_not_extra(signal):
    assert count(record(signal)) == (0, CountStatus.VALID)


@pytest.mark.parametrize("signal", [False, True])
@pytest.mark.parametrize("parent", [0, 2, 4])
def test_gluon_splitting_in_top_b_or_w_radiation_counts_both_quarks(signal, parent):
    particles = record(signal)
    gluon = len(particles)
    particles += [(21, 51, FIRST_COPY | LAST_COPY, [parent]),
                  (5, 71, FIRST_COPY | LAST_COPY, [gluon]),
                  (-5, 71, FIRST_COPY | LAST_COPY, [gluon])]
    assert count(particles) == (2, CountStatus.VALID)


def test_pruned_gluon_does_not_merge_new_b_with_primary_same_sign_ancestor():
    particles = record() + [(5, 71, FIRST_COPY | LAST_COPY, [2])]
    assert count(particles) == (1, CountStatus.VALID)


@pytest.mark.parametrize("status", [21, 31, 34, 41, 42, 45, 46, 53, 54, 61])
def test_incoming_b_is_not_an_extra_outgoing_quark(status):
    assert count(record() + [(5, status, FIRST_COPY | LAST_COPY, [])])[0] == 0


def test_status_73_can_reference_two_copies_of_one_line():
    # Observed in the 2024 TTBB pilot: both paths end at root 7. Counting the
    # two mother references as separate quarks, or rejecting them, is wrong.
    particles = record() + [(5, 23, HARD | FIRST_COPY, []),
                            (5, 51, FROM_HARD_PROCESS, [7]),
                            (5, 73, FROM_HARD_PROCESS, [7, 8]),
                            (5, 71, FROM_HARD_PROCESS | LAST_COPY, [9])]
    assert count(particles) == (1, CountStatus.VALID)
    # The same terminal particle cannot be assigned to two DIFFERENT roots.
    particles[8] = (5, 51, FIRST_COPY, [])
    assert count(particles) == (-1, CountStatus.AMBIGUOUS_COPY_CHAIN)


def test_copies_do_not_inflate_count_and_hadrons_are_not_quarks():
    particles = record() + [(5, 23, HARD | FIRST_COPY, []),
                            (5, 51, FROM_HARD_PROCESS, [7]),
                            (5, 71, FROM_HARD_PROCESS | LAST_COPY, [8]),
                            (511, 2, FIRST_COPY | LAST_COPY, [9])]
    assert count(particles) == (1, CountStatus.VALID)


def test_indices_need_not_be_in_ancestry_order():
    original = record(True)
    order = list(reversed(range(len(original))))
    mapping = {old: new for new, old in enumerate(order)}
    shuffled = [(original[i][0], original[i][1], original[i][2],
                 [mapping[p] for p in original[i][3]]) for i in order]
    assert count(shuffled) == (0, CountStatus.VALID)


@pytest.mark.parametrize(("extra", "reason"), [
    ([(5, 71, LAST_COPY, [999])], CountStatus.INVALID_ANCESTRY),
    ([(5, 71, LAST_COPY, [-1])], CountStatus.INVALID_ANCESTRY),
    ([(5, 71, LAST_COPY, [8]), (5, 51, 0, [7])], CountStatus.INVALID_ANCESTRY),
    ([(5, 71, FIRST_COPY | LAST_COPY, [8]), (21, 51, FIRST_COPY, [7])],
     CountStatus.INVALID_ANCESTRY),
    ([(5, 71, FIRST_COPY | LAST_COPY, [8]), (21, 51, FIRST_COPY, [999])],
     CountStatus.INVALID_ANCESTRY),
    ([(5, 71, LAST_COPY, [])], CountStatus.AMBIGUOUS_COPY_CHAIN),
    ([(5, 71, LAST_COPY, [2])], CountStatus.AMBIGUOUS_COPY_CHAIN),
    ([(5, 23, FIRST_COPY, [])], CountStatus.AMBIGUOUS_COPY_CHAIN),
    ([(5, 91, FIRST_COPY | LAST_COPY, [])], CountStatus.UNSUPPORTED_STATUS),
])
def test_incomplete_or_ambiguous_graphs_are_unknown(extra, reason):
    assert count(record() + extra) == (-1, reason)


def test_nanoaod_is_not_certified_by_finding_two_primary_b_quarks():
    assert count(record(), complete=False) == (-1, CountStatus.INCOMPLETE_RECORD)
    particles = record()
    particles[2] = (5, 23, FIRST_COPY, [0])
    assert count(particles) == (-1, CountStatus.UNRESOLVED_TOP_DECAY)


def test_w_modes_charge_conjugates_and_unknowns():
    labels = _event_w_decay_labels(
        ak.Array([1, -3, -5, 4, 5, None, 1, 4]),
        ak.Array([-2, 4, 4, -5, -2, None, 2, -5]),
        ak.Array([True, True, True, True, True, True, True, False]),
    )
    assert labels["GenWDecay"].tolist() == [0, 0, 1, 1, -1, -1, -1, -1]
    assert labels["GenWDecayValid"].tolist() == [True] * 4 + [False] * 4


class Events:
    def __init__(self, uuid="source-a", start=0, stop=2):
        self.metadata = {"fileuuid": uuid, "entrystart": start, "entrystop": stop}
        self.ids = {"run": ak.Array([1, 1][start:stop]),
                    "luminosityBlock": ak.Array([2, 2][start:stop]),
                    "event": ak.Array([100, 101][start:stop])}

    def __len__(self):
        return len(self.ids["event"])

    def __getitem__(self, key):
        return self.ids[key]


@pytest.fixture
def sidecar(tmp_path):
    path = tmp_path / "counts.npz"
    np.savez(path, schema_version=np.array(TRUTH_LABEL_VERSION), nano_uuid=np.array("source-a"),
             run=np.array([1, 1]), luminosityBlock=np.array([2, 2]), event=np.array([100, 101]),
             count=np.array([2, -1]), status=np.array([0, CountStatus.INVALID_ANCESTRY]))
    manifest = tmp_path / "manifest.json"
    data = {"schema_version": TRUTH_LABEL_VERSION, "files": [{
        "nano_uuid": "source-a", "entries": 2, "labels": path.name,
        "sha256": sha256(path.read_bytes()).hexdigest(),
    }]}
    manifest.write_text(json.dumps(data))
    return SimpleNamespace(records=read_truth_manifest(manifest), path=path,
                           manifest=manifest, data=data)


def test_source_join_chunking_and_independent_unknown_mask(sidecar):
    labels = extra_b_labels(Events(), sidecar.records)
    assert labels["GenNExtraBQuarks"].tolist() == [2, -1]
    assert labels["GenNExtraBQuarksValid"].tolist() == [True, False]
    for key, values in labels.items():
        pieces = [extra_b_labels(Events(start=i, stop=i + 1), sidecar.records)[key]
                  for i in range(2)]
        np.testing.assert_array_equal(values, np.concatenate(pieces))
    assert extra_b_labels(Events())["GenNExtraBQuarks"].tolist() == [-1, -1]


def test_same_event_numbers_from_another_mc_file_cannot_join(sidecar):
    with pytest.raises(ValueError, match="No truth-label sidecar"):
        extra_b_labels(Events(uuid="source-b"), sidecar.records)


def test_reordered_events_fail_instead_of_attaching_wrong_labels(sidecar):
    events = Events()
    events.ids["event"] = ak.Array([101, 100])
    with pytest.raises(ValueError, match="event identity mismatch"):
        extra_b_labels(events, sidecar.records)


def test_modified_sidecar_and_duplicate_source_fail(sidecar):
    sidecar.path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum mismatch"):
        extra_b_labels(Events(), sidecar.records)
    sidecar.data["files"] *= 2
    sidecar.manifest.write_text(json.dumps(sidecar.data))
    with pytest.raises(ValueError, match="Duplicate NanoAOD UUID"):
        read_truth_manifest(sidecar.manifest)


def test_sidecar_reader_uses_verified_bytes_when_file_is_replaced(sidecar, monkeypatch):
    original_load = np.load
    with original_load(sidecar.path, allow_pickle=False) as data:
        replacement = {key: data[key] for key in data.files}
    replacement["count"] = np.array([4, -1])
    buffer = io.BytesIO()
    np.savez(buffer, **replacement)

    def replace_before_decode(source, *args, **kwargs):
        # Simulate a file replacement between checksum verification and decode.
        sidecar.path.write_bytes(buffer.getvalue())
        return original_load(source, *args, **kwargs)

    monkeypatch.setattr(np, "load", replace_before_decode)
    labels = extra_b_labels(Events(), sidecar.records)
    assert labels["GenNExtraBQuarks"].tolist() == [2, -1]


def test_manifest_is_pinned_to_the_bytes_recorded_at_submission(sidecar):
    digest = sha256(sidecar.manifest.read_bytes()).hexdigest()
    assert read_truth_manifest(sidecar.manifest, expected_sha256=digest) == sidecar.records
    # A different, otherwise well-formed manifest must not be silently accepted
    # by workers that start later in the same campaign.
    sidecar.data["files"][0]["entries"] = 3
    sidecar.manifest.write_text(json.dumps(sidecar.data))
    with pytest.raises(ValueError, match="manifest checksum mismatch"):
        read_truth_manifest(sidecar.manifest, expected_sha256=digest)


def test_processor_factory_forwards_manifest_pin_and_rejects_pin_without_manifest(sidecar):
    from vcb.run import get_processor

    digest = sha256(sidecar.manifest.read_bytes()).hexdigest()
    processor = get_processor("skimmer", region="signal", nano_version="v12_private",
                              truth_label_manifest=str(sidecar.manifest),
                              truth_label_manifest_sha256=digest)
    assert processor._truth_labels == sidecar.records
    with pytest.raises(ValueError, match="manifest checksum mismatch"):
        get_processor("skimmer", region="signal", nano_version="v12_private",
                      truth_label_manifest=str(sidecar.manifest),
                      truth_label_manifest_sha256="0" * 64)
    with pytest.raises(ValueError, match=r"requires.*manifest"):
        get_processor("skimmer", truth_label_manifest_sha256=digest)


@pytest.fixture
def builder():
    script = Path(__file__).resolve().parents[1] / "condor/scripts/build_truth_labels.py"
    spec = importlib.util.spec_from_file_location("build_truth_labels_review", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_native_pair_check_accepts_nanoaod_pruning_and_precision(builder):
    # Native floats have more precision; NanoAOD also drops the soft extra b.
    native = [(6, 62, HARD | LAST_COPY, 100.123, 0.12345, -2.3456),
              (5, 71, FIRST_COPY | LAST_COPY, 3.0, 1.0, 0.5),
              (-6, 62, HARD | LAST_COPY, 88.01, -1.234, 1.5)]
    nano = [(6, 62, HARD | LAST_COPY, 100.0, 0.12353515625, -2.34375),
            (-6, 62, HARD | LAST_COPY, 88.0, -1.234375, 1.5)]
    builder.check_generator_particles(nano, native)


@pytest.mark.parametrize(("column", "replacement"), [
    (0, -6), (1, 23), (2, FIRST_COPY), (3, 150.0), (4, -0.2), (5, 2.0),
])
def test_native_pair_check_rejects_different_truth_with_reused_event_numbers(
    builder, column, replacement,
):
    particle = [6, 62, HARD | LAST_COPY, 100.0, 0.2, 1.0]
    wrong = particle.copy()
    wrong[column] = replacement
    with pytest.raises(ValueError, match="generator content mismatch"):
        builder.check_generator_particles([particle], [wrong])


def test_native_pair_check_does_not_reuse_particles_or_accept_empty_truth(builder):
    particle = (6, 62, HARD | LAST_COPY, 100.0, 0.2, 1.0)
    with pytest.raises(ValueError, match="generator content mismatch"):
        builder.check_generator_particles([particle, particle], [particle])
    with pytest.raises(ValueError, match="Empty NanoAOD generator record"):
        builder.check_generator_particles([], [particle])


def test_native_pair_aligns_a_permutation_with_exact_large_event_ids(builder):
    ids = {"run": np.array([1, 1, 1], dtype=np.uint32),
           "luminosityBlock": np.array([8, 8, 8], dtype=np.uint32),
           "event": np.array([2**60 + 1, 2**60 + 2, 2**60 + 3], dtype=np.uint64)}
    lookup = builder.nano_identity_index(ids)
    seen = np.zeros(3, dtype=bool)
    native = [(1, 8, int(ids["event"][j])) for j in (2, 0, 1)]
    assert [builder.aligned_nano_entry(key, lookup, seen) for key in native] == [2, 0, 1]
    assert seen.all()
    with pytest.raises(ValueError, match="Duplicate native"):
        builder.aligned_nano_entry(native[0], lookup, seen)
    with pytest.raises(ValueError, match="absent from its paired NanoAOD"):
        builder.aligned_nano_entry((1, 8, 0), lookup, seen)


def test_native_pair_rejects_ambiguous_or_malformed_identity_columns(builder):
    ids = {key: np.array([1, 1], dtype=np.uint64)
           for key in ("run", "luminosityBlock", "event")}
    with pytest.raises(ValueError, match="Duplicate NanoAOD"):
        builder.nano_identity_index(ids)
    ids["event"] = np.array([1.0, 2.0])
    with pytest.raises(ValueError, match="Malformed NanoAOD"):
        builder.nano_identity_index(ids)


@pytest.mark.parametrize("input_profile", ["calibration", "b0"])
def test_condor_forwards_manifest_as_one_argument_and_records_provenance(sidecar, tmp_path,
                                                                       monkeypatch, input_profile):
    repo = Path(__file__).resolve().parents[1]
    script = repo / "condor/submit_batches.py"
    spec = importlib.util.spec_from_file_location("submit_truth_batches", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    batch = tmp_path / "input/batch_000"
    batch.mkdir(parents=True)
    (batch / "input.root").touch()
    # Quoting must survive spaces and shell metacharacters in a valid path.
    manifest = sidecar.manifest.with_name("truth labels $literal.json")
    manifest.write_text(sidecar.manifest.read_text())
    monkeypatch.setattr(sys, "argv", [str(script), "--input-root", str(batch.parent),
                        "--files-name", "TTtoLNu2Q", "--tag", "truth",
                        "--run-dir", str(tmp_path / "jobs"),
                        "--processed-dir", str(tmp_path / "processed"),
                        "--truth-label-manifest", str(manifest), "--input-profile", input_profile])
    module.main()  # Generate only; never submit a job.
    campaign = json.loads((tmp_path / "jobs/campaign.json").read_text())
    assert campaign["truth_label_manifest"] == str(manifest.resolve())
    assert campaign["truth_label_manifest_sha256"] == sha256(manifest.read_bytes()).hexdigest()
    assert campaign["input_profile"] == input_profile
    worker = next((tmp_path / "jobs").glob("*/run_batch.sh"))
    script_text = worker.read_text()
    assert f'INPUT_PROFILE="{input_profile}"' in script_text
    assert '--input-profile "$INPUT_PROFILE"' in script_text
    assignment = next(line for line in script_text.splitlines()
                      if line.startswith("TRUTH_LABEL_MANIFEST="))
    assert shlex.split(assignment)[0] == f"TRUTH_LABEL_MANIFEST={manifest.resolve()}"
    assert '"${TRUTH_LABEL_ARGS[@]}"' in script_text
    pin_assignment = next(line for line in script_text.splitlines()
                          if line.startswith("TRUTH_LABEL_MANIFEST_SHA256="))
    assert shlex.split(pin_assignment)[0] == (
        f"TRUTH_LABEL_MANIFEST_SHA256={campaign['truth_label_manifest_sha256']}"
    )
    assert '--truth-label-manifest-sha256 "$TRUTH_LABEL_MANIFEST_SHA256"' in script_text
    subprocess.run(["bash", "-n", str(worker)], check=True)
