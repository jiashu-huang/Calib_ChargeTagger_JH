"""2024 selection payloads must remain reproducible without mutable CVMFS paths."""

from __future__ import annotations

import gzip
import re
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


def test_run_metadata_records_the_applied_veto_map_tag_and_key():
    # JERC FAQ: outputs should store "the jet veto map tag and key".
    from vcb import run

    record = run._jet_payload_metadata("2024")
    assert record["jet_veto_tag"] == "Summer24Prompt24_RunBCDEFGHI_V1"
    assert record["jet_veto_key"] == "jetvetomap"
    # They are the names the selection evaluates, and they exist in the file
    # whose path and hash the same record carries.
    assert record["jet_veto_tag"] == corrections.JETVETO_TAGS["2024"]
    assert record["jet_veto_key"] == corrections.JETVETO_KEY
    assert Path(record["jet_veto"]["path"]) == Path(corrections.JETVETO_2024_BUNDLED)
    assert record["jet_veto"]["sha256"] == corrections.JETVETO_2024_SHA256
    cset = correctionlib.CorrectionSet.from_file(record["jet_veto"]["path"])
    assert cset[record["jet_veto_tag"]].evaluate(record["jet_veto_key"], 0.0, 0.0) >= 0
    assert run._jet_payload_metadata("2023") == {}


def _fallback_pairs() -> dict[str, tuple[Path, Path]]:
    """Every 2024 (bundled copy, cvmfs fallback) pair the loaders know."""
    from vcb.processors import electron_ss, lepton_sf, muon_ss

    boostedhh_dir = Path(corrections.package_path) / "corrections"
    vcb_dir = Path(lepton_sf.package_path) / "corrections"
    pairs = {
        "jet_jerc": (corrections.JEC_JER_2024_BUNDLED, corrections.JEC_JER_2024_CVMFS),
        "jer_smear": (corrections.JERSMEAR_2024_BUNDLED, corrections.JERSMEAR_2024_CVMFS),
        "jet_veto": (corrections.JETVETO_2024_BUNDLED, corrections.JETVETO_2024_CVMFS),
        "pileup": (boostedhh_dir / "2024_puWeights.json.gz", corrections.pileup_cvmfs_path("2024")),
        "muon_scalesmearing": (muon_ss.PAYLOAD_PATH, muon_ss.CVMFS_PATH),
        "electron_ss": (
            vcb_dir / electron_ss.ELECTRON_SS_SOURCES["2024"][0],
            electron_ss.ELECTRON_SS_SOURCES["2024"][1],
        ),
    }
    for name, (bundled, fallback) in lepton_sf.LEPTON_SF_SOURCES["2024"].items():
        pairs[name] = (vcb_dir / bundled, fallback)
    return {name: (Path(bundled), Path(fallback)) for name, (bundled, fallback) in pairs.items()}


def test_every_2024_fallback_names_a_dated_release():
    # JERC FAQ: an unversioned CVMFS path "can be replaced when a new release
    # is deployed", so `latest/` is not a reproducible fallback.
    pairs = _fallback_pairs()
    assert len(pairs) == 9
    for name, (bundled, fallback) in pairs.items():
        assert bundled.is_file(), name
        assert "latest" not in fallback.parts, name
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", fallback.parent.name), name


def test_dated_fallbacks_hold_the_bundled_content():
    # Adopting a newer release must move the bundled file and its date together.
    pairs = _fallback_pairs()
    if not all(fallback.is_file() for _, fallback in pairs.values()):
        pytest.skip("CAT metadata tree on CVMFS is not available here")
    for name, (bundled, fallback) in pairs.items():
        assert gzip.decompress(fallback.read_bytes()) == gzip.decompress(bundled.read_bytes()), name
