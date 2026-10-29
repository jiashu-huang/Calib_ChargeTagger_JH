"""Load per-source truth counts with UUID, checksum and event-identity checks."""

from __future__ import annotations

import json
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import awkward as ak
import numpy as np

from vcb.truth import TRUTH_LABEL_VERSION, UNKNOWN, CountStatus


def unknown_count_labels(size):
    return {
        "GenNExtraBQuarks": np.full(size, UNKNOWN, dtype=np.int32),
        "GenNExtraBQuarksValid": np.zeros(size, dtype=np.bool_),
        "GenNExtraBQuarksStatus": np.full(size, CountStatus.INCOMPLETE_RECORD, dtype=np.int32),
        "GenTruthLabelVersion": np.full(size, TRUTH_LABEL_VERSION, dtype=np.int32),
    }


def read_truth_manifest(path, *, expected_sha256=None):
    """Resolve one immutable manifest when constructing the processor."""
    path = Path(path).resolve()
    contents = path.read_bytes()
    if expected_sha256 is not None and sha256(contents).hexdigest() != expected_sha256:
        raise ValueError(f"Truth-label manifest checksum mismatch: {path}")
    manifest = json.loads(contents)
    if manifest.get("schema_version") != TRUTH_LABEL_VERSION:
        raise ValueError("Unsupported truth-label manifest version")
    records = {}
    for record in manifest["files"]:
        uuid = record["nano_uuid"]
        if uuid in records:
            raise ValueError(f"Duplicate NanoAOD UUID in truth manifest: {uuid}")
        records[uuid] = {**record, "labels": str((path.parent / record["labels"]).resolve())}
    if not records:
        raise ValueError("Empty truth-label manifest")
    return records


@lru_cache(maxsize=8)
def _load_counts(path, digest, uuid):
    path = Path(path)
    contents = path.read_bytes()
    if sha256(contents).hexdigest() != digest:
        raise ValueError(f"Truth-label checksum mismatch: {path}")
    with np.load(BytesIO(contents), allow_pickle=False) as data:
        values = {key: data[key] for key in data.files}
    if (values["schema_version"].item() != TRUTH_LABEL_VERSION
            or values["nano_uuid"].item() != uuid):
        raise ValueError("Truth-label version or source UUID mismatch")
    columns = ("run", "luminosityBlock", "event", "count", "status")
    size = len(values["event"])
    if any(values[key].shape != (size,) or values[key].dtype.kind not in "iu"
           for key in columns):
        raise ValueError("Malformed truth-label columns")
    valid = values["status"] == CountStatus.VALID
    if (not np.isin(values["status"], [int(s) for s in CountStatus]).all()
            or np.any(valid & (values["count"] < 0))
            or np.any(~valid & (values["count"] != UNKNOWN))):
        raise ValueError("Invalid truth-count sentinel or status")
    return values


def extra_b_labels(events, records=None):
    """No sidecar means unknown. An explicitly requested but bad join is fatal."""
    result = unknown_count_labels(len(events))
    if records is None:
        return result
    metadata = events.metadata
    uuid = metadata.get("fileuuid")
    if uuid not in records:
        raise ValueError(f"No truth-label sidecar for NanoAOD UUID {uuid!r}")
    record = records[uuid]
    data = _load_counts(record["labels"], record["sha256"], uuid)
    start, stop = metadata["entrystart"], metadata["entrystop"]
    if (len(data["event"]) != record["entries"] or not 0 <= start <= stop <= record["entries"]
            or stop - start != len(events)):
        raise ValueError("Truth-label entry range mismatch")
    for key in ("run", "luminosityBlock", "event"):
        if not np.array_equal(data[key][start:stop], ak.to_numpy(events[key])):
            raise ValueError(f"Truth-label event identity mismatch: {key}")
    result["GenNExtraBQuarks"] = data["count"][start:stop].astype(np.int32)
    result["GenNExtraBQuarksStatus"] = data["status"][start:stop].astype(np.int32)
    result["GenNExtraBQuarksValid"] = result["GenNExtraBQuarksStatus"] == CountStatus.VALID
    return result
