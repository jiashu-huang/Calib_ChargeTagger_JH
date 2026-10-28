"""Carry each chunk's all-input totals into its output ROOT batch."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

from vcb.processors.pdf_weights import pdf_metadata_fields
from vcb.processors.weight_prescription import weight_metadata_fields


def save_chunk_metadata(filename, year, dataset, totals, pdf_layout=None, weight_prescription=None):
    directory = Path(os.environ.get("BOOSTEDHH_OUTPARQUET_DIR", "outparquet"))
    record = {
        "year": year, "dataset": dataset, "pdf_layout": pdf_layout,
        "weight_prescription": weight_prescription,
        "totals": {key: np.asarray(value).tolist() for key, value in totals.items()},
    }
    (directory / f"{filename}.norm.json").write_text(json.dumps(record, allow_nan=False))


def write_root_metadata(handle, parquet_paths):
    """Each input chunk contributes once, including chunks with no saved events."""
    records = [json.loads(Path(f"{p}.norm.json").read_text()) for p in parquet_paths]
    reference = records[0]
    totals = {k: np.asarray(v, dtype=np.float64) for k, v in reference["totals"].items()}
    for record in records[1:]:
        if any(record[k] != reference[k] for k in (
            "year", "dataset", "pdf_layout", "weight_prescription",
        )):
            raise ValueError("Cannot combine different datasets, PDF mappings or weight prescriptions")
        if record["totals"].keys() != totals.keys():
            raise ValueError("Inconsistent normalization fields across chunks")
        for key, value in record["totals"].items():
            array = np.asarray(value, dtype=np.float64)
            if array.shape != totals[key].shape:
                raise ValueError(f"Inconsistent normalization shape for {key}")
            totals[key] = totals[key] + array
    if "np_nominal" in totals:
        handle["Norm"] = {key: value[None] for key, value in totals.items()}
    if reference["pdf_layout"] is not None:
        handle["PdfMetadata"] = pdf_metadata_fields(reference["pdf_layout"])
    if reference["weight_prescription"] is not None:
        handle["WeightMetadata"] = weight_metadata_fields(reference["weight_prescription"])
