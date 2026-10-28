"""Lossless ttbar PDF members and their signed, all-input normalization sums.

Layouts are identified by NanoAOD's LHA-ID title, never by vector length.
The registered identities were checked against LHAPDF's official set metadata
on CVMFS on 2026-10-27. No Hessian reduction or alpha-S prior is applied here.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache

import awkward as ak
import numpy as np
import uproot

from vcb.processors.top_pt import is_ttbar

PDF_SETS = {
    (325300, 325402): {
        "name": "NNPDF31_nnlo_as_0118_mc_hessian_pdfas",
        "error_type": "symmhessian+as",
        "alpha_s_members": {"101": 0.116, "102": 0.120},
        "flavours": 5,
        "alpha_s_metadata": {"Q": 91.2, "value": 0.118},
    },
    (325500, 325600): {
        "name": "NNPDF31_nnlo_as_0118_nf_4_mc_hessian",
        "error_type": "symmhessian",
        "alpha_s_members": {},
        "flavours": 4,
        "alpha_s_metadata": {"Q": 4.91999, "value": 0.2134902},
    },
}


def layout_from_title(title: str) -> dict:
    """Reject missing, ambiguous or unverified metadata before saving weights."""
    match = re.fullmatch(
        r"LHE pdf variation weights \(w_var / w_nominal\) for LHA IDs\s+(\d+)\s*-\s*(\d+)",
        " ".join(title.split()),
    )
    if match is None:
        raise ValueError(f"Unsupported LHEPdfWeight metadata: {title!r}")
    first, last = map(int, match.groups())
    if (first, last) not in PDF_SETS:
        raise ValueError(f"Unverified PDF LHA IDs {first}-{last}; register the actual set first")
    identity = PDF_SETS[first, last]
    return {
        "schema_version": 1,
        "lha_ids": list(range(first, last + 1)),
        "central_member": 0,
        "hessian_members": list(range(1, 101)),
        **identity,
        "input_title": " ".join(title.split()),
        "source": f"https://lhapdfsets.web.cern.ch/current/{identity['name']}/{identity['name']}.info",
        "event_branches": "PDFWeight{index}: unmodified w_var / w_nominal",
        "normalization": "Norm/np_pdf_weights[index] = sum_all_input(genWeight * nominal_pileup * ratio)",
    }


@lru_cache(maxsize=256)
def read_pdf_layout(filename: str) -> dict:
    with uproot.open(filename) as handle:
        tree = handle["Events"]
        if "LHEPdfWeight" not in tree:
            raise ValueError(f"Requested ttbar PDF weights are absent in {filename}")
        return layout_from_title(tree["LHEPdfWeight"].title)


def validate_pdf_fileset(fileset: dict) -> None:
    """Check all file identities within each dataset before starting a job."""
    for key, files in fileset.items():
        if not is_ttbar(key.split("_", 1)[-1]):
            continue
        expected = None
        for filename in files:
            layout = read_pdf_layout(str(filename))
            if expected is not None and layout != expected:
                raise ValueError(f"Incompatible PDF member mappings in dataset {key}: {filename}")
            expected = layout


def member_weights(values, layout: dict, normalization_weights) -> tuple[np.ndarray, np.ndarray]:
    """Preserve zero/negative members; sum before any reconstructed selection."""
    count = len(layout["lha_ids"])
    if not bool(ak.all(ak.num(values, axis=1) == count)):
        raise ValueError(f"LHEPdfWeight length disagrees with the {count} metadata members")
    ratios = ak.to_numpy(values)
    if ratios.shape != (len(normalization_weights), count) or not np.all(np.isfinite(ratios)):
        raise ValueError("LHEPdfWeight must be a finite rectangular member array")
    base = np.asarray(normalization_weights, dtype=np.float64)
    if not np.all(np.isfinite(base)):
        raise ValueError("Nonfinite PDF normalization weight")
    return ratios, np.sum(base[:, None] * ratios, axis=0, dtype=np.float64)


def pdf_metadata_fields(layout: dict) -> dict:
    """UTF-8 bytes avoid unsupported string-TTree writing in pinned uproot 4."""
    encoded = json.dumps(layout, sort_keys=True).encode("utf-8")
    return {"layout_utf8": np.frombuffer(encoded, dtype=np.uint8)[None]}


def read_saved_layout(handle) -> dict | None:
    """Validate every metadata row, including rows concatenated by hadd."""
    branches = set(handle["Events"].keys())
    has_members = any(re.fullmatch(r"PDFWeight\d+", b) for b in branches)
    if "PdfMetadata" not in handle:
        if has_members:
            raise ValueError("PDFWeight branches have no PdfMetadata")
        return None
    rows = [row.tobytes().decode("utf-8") for row in
            handle["PdfMetadata"]["layout_utf8"].array(library="np")]
    if not rows or len(set(rows)) != 1:
        raise ValueError("Missing or incompatible PDF member mappings in PdfMetadata")
    layout = json.loads(rows[0])
    if layout != layout_from_title(layout["input_title"]):
        raise ValueError("PDF metadata disagrees with the registered member mapping")
    count = len(layout["lha_ids"])
    expected = {f"PDFWeight{i}" for i in range(count)}
    actual = {b for b in branches if b.startswith("PDFWeight")}
    if actual != expected:
        raise ValueError("PDFWeight columns disagree with the recorded member mapping")
    if "Norm" not in handle or "np_pdf_weights" not in handle["Norm"]:
        raise ValueError("PDF members have no all-input normalization sums")
    sums = handle["Norm"]["np_pdf_weights"].array(library="np")
    if sums.ndim != 2 or sums.shape[1] != count or not np.all(np.isfinite(sums)):
        raise ValueError("Invalid PDF all-input normalization sums")
    return layout


def validate_pdf_merge(paths) -> dict | None:
    """Do not merge or jointly normalize different bases or missing members."""
    expected = None
    first = True
    for path in paths:
        with uproot.open(path) as handle:
            layout = read_saved_layout(handle)
        if not first and layout != expected:
            raise ValueError(f"Incompatible PDF member mappings before merge/normalization: {path}")
        expected, first = layout, False
    return expected
