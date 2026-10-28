"""2024 selection payloads must remain reproducible without mutable CVMFS paths."""

from __future__ import annotations

import gzip
from pathlib import Path

import awkward as ak
import correctionlib
import numpy as np
import pytest

from boostedhh.processors import corrections


def test_jetveto_bundled_map_and_dated_fallback_agree():
    pinned = corrections._load_jetveto_2024(
        corrections.JETVETO_2024_BUNDLED, "/missing/fallback",
    )
    source = Path(corrections.JETVETO_2024_CVMFS)
    if source.is_file():
        assert source.read_bytes() == Path(corrections.JETVETO_2024_BUNDLED).read_bytes()
    # Probe the whole eta/phi map independently of its binning representation.
    eta, phi = np.meshgrid(np.linspace(-4.7, 4.7, 101), np.linspace(-3.1415, 3.1415, 121))
    reference = correctionlib.CorrectionSet.from_file(corrections.JETVETO_2024_BUNDLED)
    key = "Summer24Prompt24_RunBCDEFGHI_V1"
    expected = reference[key].evaluate("jetvetomap", eta.ravel(), phi.ravel()) > 0
    assert expected.any()
    assert (~expected).any()
    np.testing.assert_array_equal(
        pinned[key].evaluate("jetvetomap", eta.ravel(), phi.ravel()) > 0, expected,
    )
    jets = ak.zip({"pt": np.full((len(expected), 1), 30.),
                   "eta": eta.reshape(-1, 1), "phi": phi.reshape(-1, 1)})
    np.testing.assert_array_equal(ak.to_numpy(corrections.get_jetveto_event(jets, "2024")), ~expected)


def test_missing_or_modified_jetveto_payload_is_fatal(tmp_path):
    a, b = tmp_path / "bundled.gz", tmp_path / "fallback.gz"
    with pytest.raises(FileNotFoundError, match="required 2024 jet-veto"):
        corrections._load_jetveto_2024(str(a), str(b))
    a.write_bytes(gzip.compress(b'{}'))
    with pytest.raises(ValueError, match="checksum"):
        corrections._load_jetveto_2024(str(a), corrections.JETVETO_2024_CVMFS)


def test_jetveto_empty_and_below_threshold_events():
    jets = ak.Array([[], [{"pt": 14., "eta": 1.3, "phi": 2.5}]])
    np.testing.assert_array_equal(ak.to_numpy(corrections.get_jetveto_event(jets, "2024")), [True, True])
