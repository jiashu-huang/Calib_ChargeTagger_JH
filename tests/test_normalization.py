"""Exercise normalization preflight and actual ROOT rewriting on small campaigns."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import uproot

from vcb.normalization import infer_sample_scale, normalized_weights

SCRIPT = Path(__file__).resolve().parents[1] / "condor/scripts/normalize.py"


@pytest.fixture
def normalizer():
    spec = importlib.util.spec_from_file_location("normalize_campaign", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _root(path, base, *, scale=10., denominator=10., weights=None, final=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    base = np.asarray(base, dtype=float)
    arrays = {"weight_noxsec": base, "weight": scale * base if weights is None else np.asarray(weights)}
    if final is not None:
        arrays["finalWeight"] = np.asarray(final)
    with uproot.recreate(path) as handle:
        handle["Events"] = arrays
        handle["Norm"] = {"np_nominal": np.array([denominator]), "nevents": np.array([len(base)])}
    return path


def _run(module, monkeypatch, campaign, *extra):
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--processed-dir", str(campaign), *extra])
    module.main()


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_signed_weights_and_zero_sf_are_not_divided_or_dropped():
    base = np.array([0., -2., 3.])
    assert infer_sample_scale(7 * base, base) == 7
    np.testing.assert_array_equal(normalized_weights(7 * base, -2), [0., 7., -10.5])
    assert infer_sample_scale([0.], [0.]) is None


@pytest.mark.parametrize(("weights", "base", "message"), [
    ([1.], [0.], "Zero weight_noxsec"),
    ([np.nan], [1.], "must be finite"),
    ([1.], [np.inf], "must be finite"),
    ([-1.], [1.], "sample scale"),
    ([1., 2.], [1., 1.], "sample scale"),
])
def test_invalid_event_weights_or_scale_fail(weights, base, message):
    with pytest.raises(ValueError, match=message):
        infer_sample_scale(weights, base)


def test_normalized_overflow_is_rejected():
    with pytest.raises(ValueError, match="nonfinite"):
        normalized_weights([1e308], 1e-308)


def test_inference_scans_past_the_first_thousand_events(normalizer, tmp_path):
    root = _root(tmp_path / "later.root", [0.] * 1001 + [2.], scale=7.)
    assert normalizer.derive_sigma_lumi([root]) == 7


@pytest.mark.parametrize("problem", ["late_scale", "later_file_scale", "zero_mismatch", "nonfinite", "overflow"])
def test_bad_later_input_never_partially_normalizes_campaign(normalizer, tmp_path, monkeypatch, problem):
    campaign = tmp_path / "campaign"
    first = _root(campaign / "roots/batch_000.root", [1., -1., 0.], scale=1.)
    options = {
        "late_scale": {"weights": [1.] * 1001 + [1.1], "scale": 1.},
        "later_file_scale": {"scale": 1.00001},
        "zero_mismatch": {"weights": [1.], "base": [0.]},
        "nonfinite": {"weights": [np.nan]},
        "overflow": {"weights": [1e308], "base": [1e308], "denominator": -10. + 1e-14},
    }[problem]
    base = options.pop("base", [1.] * (1002 if problem == "late_scale" else 1))
    second = _root(campaign / "roots/batch_001.root", base, **options)
    before = {path: _digest(path) for path in (first, second)}
    message = {
        "late_scale": "sample scale", "later_file_scale": "sample scale",
        "zero_mismatch": "Zero weight_noxsec", "nonfinite": "must be finite",
        "overflow": "Normalizing event weights produces nonfinite",
    }[problem]
    with pytest.raises(ValueError, match=message):
        _run(normalizer, monkeypatch, campaign)
    assert {path: _digest(path) for path in before} == before
    assert not (campaign / "metadata/normalization.json").exists()


@pytest.mark.parametrize("denominator", [0., np.nan, np.inf, -np.inf])
def test_bad_denominator_never_modifies_root(normalizer, tmp_path, monkeypatch, denominator):
    campaign = tmp_path / "campaign"
    path = _root(campaign / "roots/batch_000.root", [1.], denominator=denominator)
    before = _digest(path)
    with pytest.raises(ValueError, match="finite"):
        _run(normalizer, monkeypatch, campaign)
    assert _digest(path) == before


@pytest.mark.parametrize("base", [[0., 1., -1.], [0., 0.], []])
def test_normalization_and_verified_rerun_preserve_signed_and_empty_inputs(
    normalizer, tmp_path, monkeypatch, base,
):
    campaign = tmp_path / "campaign"
    path = _root(campaign / "roots/batch_000.root", base)
    _run(normalizer, monkeypatch, campaign)
    with uproot.open(path) as handle:
        np.testing.assert_array_equal(handle["Events/finalWeight"].array(library="np"), base)
        assert handle["Norm/np_nominal"].array(library="np")[0] == 10.
    before = _digest(path)
    _run(normalizer, monkeypatch, campaign)
    assert _digest(path) == before
    summary = json.loads((campaign / "metadata/normalization.json").read_text())
    assert summary["sigma_x_lumi"] == (10. if any(base) else None)


def test_stale_normalization_requires_force_and_preserves_norm(normalizer, tmp_path, monkeypatch):
    campaign = tmp_path / "campaign"
    first = _root(campaign / "roots/batch_000.root", [1., -1.])
    _run(normalizer, monkeypatch, campaign)
    second = _root(campaign / "roots/batch_001.root", [2., 0.])
    before = {path: _digest(path) for path in (first, second)}
    summary = campaign / "metadata/normalization.json"
    summary_before = summary.read_bytes()
    with pytest.raises(ValueError, match="--force"):
        _run(normalizer, monkeypatch, campaign)
    assert {path: _digest(path) for path in before} == before
    assert summary.read_bytes() == summary_before
    _run(normalizer, monkeypatch, campaign, "--force")
    for path in (first, second):
        with uproot.open(path) as handle:
            arrays = handle["Events"].arrays(library="np")
            np.testing.assert_array_equal(arrays["finalWeight"], arrays["weight"] / 20.)
            assert handle["Norm/np_nominal"].array(library="np")[0] == 10.


def test_corrupt_existing_weight_is_not_skipped(normalizer, tmp_path, monkeypatch):
    campaign = tmp_path / "campaign"
    path = _root(campaign / "roots/batch_000.root", [1., -1.])
    _run(normalizer, monkeypatch, campaign)
    with uproot.open(path) as handle:
        receipt = handle["finalWeight_provenance"]
    _root(path, [1., -1.], final=[2., -2.])
    with uproot.update(path) as handle:
        handle["finalWeight_provenance"] = receipt
    before = _digest(path)
    with pytest.raises(ValueError, match=r"finalWeight.*--force"):
        _run(normalizer, monkeypatch, campaign)
    assert _digest(path) == before
