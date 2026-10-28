"""Exercise campaign schema validation with small ROOT files and the real CLI."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import uproot

SCRIPT = Path(__file__).resolve().parents[1] / "condor/scripts/validate_processed.py"
NOMINAL = {"weight", "weight_noxsec", "nTrueInt", "nPU", "METPt"}
VARIATIONS = {
    f"weight_{source}{direction}"
    for source in (
        "pileup", "ISRPartonShower", "FSRPartonShower",
        "electron_reco", "electron_id", "electron_trigger",
        "muon_id", "muon_iso", "muon_trigger",
    )
    for direction in ("Up", "Down")
}


def _write_schema(path, branches):
    path.write_text("variable_name,variable_type\n" + "".join(
        f"{name},Double_t\n" for name in sorted(branches)
    ))
    return path


def _receipt(handle, denominator, fingerprint="test-campaign"):
    obj = uproot.models.TNamed.Model_TNamed.empty()
    obj._bases = [uproot.models.TObject.Model_TObject.empty()]
    obj._members = {"fName": "finalWeight_provenance", "fTitle": json.dumps({
        "np_nominal": denominator, "fingerprint": fingerprint,
    })}
    handle["finalWeight_provenance"] = obj


@pytest.fixture
def validator(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("validate_processed", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    baseline = _write_schema(tmp_path / "nominal.csv", NOMINAL)
    monkeypatch.setattr(module, "SCHEMA_BASELINE", baseline)
    return module


def _campaign(path, schemas, *, normalized=False, target="batches"):
    root_dir = path / ("merged" if target == "merged" else "roots")
    root_dir.mkdir(parents=True)
    denominator = 10.0 * len(schemas)
    for index, branches in enumerate(schemas):
        arrays = {name: np.array([1.0, 2.0]) for name in branches}
        values = {
            "weight": np.array([10.0, 20.0]),
            "weight_noxsec": np.array([1.0, 2.0]),
            "nTrueInt": np.array([20.0, 30.0]),
            "nPU": np.array([20.0, 30.0]),
        }
        arrays.update({name: value for name, value in values.items() if name in branches})
        if normalized:
            arrays["finalWeight"] = values["weight"] / denominator
        filename = "total.root" if target == "merged" else f"batch_{index:03d}.root"
        with uproot.recreate(root_dir / filename) as handle:
            handle["Events"] = arrays
            handle["Norm"] = {"np_nominal": np.array([10.0])}
            if normalized:
                _receipt(handle, denominator)
    if normalized:
        metadata = path / "metadata"
        metadata.mkdir()
        (metadata / "normalization.json").write_text(json.dumps({
            "global_np_nominal": denominator,
            "fingerprint": "test-campaign",
        }))
    return path


def _run(validator, monkeypatch, capsys, campaign, *options):
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--processed-dir", str(campaign), *options])
    result = validator.main()
    captured = capsys.readouterr()
    return result, captured.out + captured.err


@pytest.mark.parametrize("target", ["batches", "merged"])
@pytest.mark.parametrize("normalized", [False, True])
@pytest.mark.parametrize("systematics", [False, True])
def test_auto_accepts_complete_schemas(
    validator, tmp_path, monkeypatch, capsys, systematics, normalized, target,
):
    schema = NOMINAL | VARIATIONS if systematics else NOMINAL
    campaign = _campaign(tmp_path / "campaign", [schema], normalized=normalized, target=target)
    result, output = _run(validator, monkeypatch, capsys, campaign, "--target", target)
    assert result == 0, output
    assert "PASS  schema matches baseline" in output
    assert f"({'systematics' if systematics else 'nominal'}," in output
    if normalized:
        assert "PASS  finalWeight == weight / global_np_nominal" in output


@pytest.mark.parametrize("schema", [
    NOMINAL - {"METPt"},
    (NOMINAL | VARIATIONS) - {"METPt"},
    (NOMINAL | VARIATIONS) - {"weight_muon_isoDown"},
    NOMINAL | {"weight_pileupUp"},
    NOMINAL | {"weight_pileupUP"},
    NOMINAL | VARIATIONS | {"weight_typoDown"},
])
def test_auto_rejects_missing_or_unexpected_branches(
    validator, tmp_path, monkeypatch, capsys, schema,
):
    campaign = _campaign(tmp_path / "campaign", [schema])
    result, output = _run(validator, monkeypatch, capsys, campaign)
    assert result == 1
    assert "FAIL  schema matches baseline" in output
    assert "1 failed" in output  # other checks still run and pass


@pytest.mark.parametrize("schemas", [
    [NOMINAL, NOMINAL | VARIATIONS],
    [NOMINAL | VARIATIONS, NOMINAL],
])
def test_auto_rejects_mixed_campaigns(validator, tmp_path, monkeypatch, capsys, schemas):
    campaign = _campaign(tmp_path / "campaign", schemas)
    result, output = _run(validator, monkeypatch, capsys, campaign)
    assert result == 1
    assert output.count("PASS  schema matches baseline") == 1
    assert output.count("FAIL  schema matches baseline") == 1


@pytest.mark.parametrize("mode", ["nominal", "systematics"])
@pytest.mark.parametrize("systematics", [False, True])
def test_explicit_mode_enforces_requested_output(
    validator, tmp_path, monkeypatch, capsys, mode, systematics,
):
    schema = NOMINAL | VARIATIONS if systematics else NOMINAL
    campaign = _campaign(tmp_path / "campaign", [schema])
    result, output = _run(validator, monkeypatch, capsys, campaign, "--schema-mode", mode)
    assert result == (0 if systematics == (mode == "systematics") else 1), output


@pytest.mark.parametrize("custom_systematics", [False, True])
def test_custom_csv_keeps_exact_branch_contract(
    validator, tmp_path, monkeypatch, capsys, custom_systematics,
):
    custom = _write_schema(
        tmp_path / "custom.csv", NOMINAL | VARIATIONS if custom_systematics else NOMINAL,
    )
    campaign = _campaign(tmp_path / "campaign", [NOMINAL | VARIATIONS], normalized=True)
    result, output = _run(
        validator, monkeypatch, capsys, campaign, "--schema-baseline", str(custom),
    )
    assert result == (0 if custom_systematics else 1), output
    assert "(custom," in output


@pytest.mark.parametrize("contents", [None, "", "wrong_header\nweight\n"])
def test_unavailable_or_invalid_schema_fails(validator, tmp_path, monkeypatch, capsys, contents):
    custom = tmp_path / "invalid.csv"
    if contents is not None:
        custom.write_text(contents)
    campaign = _campaign(tmp_path / "campaign", [NOMINAL])
    result, output = _run(
        validator, monkeypatch, capsys, campaign, "--schema-baseline", str(custom),
    )
    assert result == 2
    assert "ERROR: cannot load schema" in output


def test_missing_default_schema_fails(validator, tmp_path, monkeypatch, capsys):
    validator.SCHEMA_BASELINE.unlink()
    campaign = _campaign(tmp_path / "campaign", [NOMINAL])
    result, output = _run(validator, monkeypatch, capsys, campaign)
    assert result == 2
    assert "ERROR: cannot load schema" in output


def _signed_campaign(path, base, denominator, *, weights=None, final=None, receipt=True):
    base = np.asarray(base, dtype=float)
    weights = 10 * base if weights is None else np.asarray(weights, dtype=float)
    arrays = {name: np.ones(len(base)) for name in NOMINAL}
    arrays.update(weight=weights, weight_noxsec=base)
    arrays["finalWeight"] = weights / denominator if final is None else np.asarray(final, dtype=float)
    (path / "roots").mkdir(parents=True)
    with uproot.recreate(path / "roots/batch_000.root") as handle:
        handle["Events"] = arrays
        handle["Norm"] = {"np_nominal": np.array([denominator])}
        if receipt:
            _receipt(handle, denominator)
    (path / "metadata").mkdir()
    (path / "metadata/normalization.json").write_text(json.dumps({
        "global_np_nominal": denominator, "fingerprint": "test-campaign",
    }))
    return path


@pytest.mark.parametrize(("base", "denominator"), [
    ([0., 1., -1.], 10.),
    ([0., 0.], 10.),
    ([2., -1.], .5),
    ([-2., 1.], 10.),
    ([2., -1.], 1.),
    ([-2., 1.], -10.),
    ([], 10.),
])
def test_signed_and_zero_weights_obey_identity_without_probability_bound(
    validator, tmp_path, monkeypatch, capsys, base, denominator,
):
    path = _signed_campaign(tmp_path / "signed", base, denominator)
    result, output = _run(validator, monkeypatch, capsys, path)
    assert result == 0, output
    assert "PASS  normalized signed-weight sum identity" in output


@pytest.mark.parametrize("problem", ["zero_mismatch", "corrupt_zero_sum", "missing_receipt", "nonfinite_final"])
def test_corrupt_signed_output_is_rejected(validator, tmp_path, monkeypatch, capsys, problem):
    options = {
        "zero_mismatch": {"weights": [1., 10., -10.]},
        "corrupt_zero_sum": {"final": [0., 2., -2.]},
        "missing_receipt": {"receipt": False},
        "nonfinite_final": {"final": [0., np.nan, -1.]},
    }
    path = _signed_campaign(tmp_path / "bad", [0., 1., -1.], 10., **options[problem])
    result, output = _run(validator, monkeypatch, capsys, path)
    assert result == 1, output


@pytest.mark.parametrize("denominator", [0., np.nan, np.inf, -np.inf])
def test_invalid_summary_denominator_fails(validator, tmp_path, monkeypatch, capsys, denominator):
    path = _signed_campaign(tmp_path / "bad", [1.], 10.)
    summary = path / "metadata/normalization.json"
    summary.write_text(json.dumps({"global_np_nominal": denominator}))
    result, output = _run(validator, monkeypatch, capsys, path)
    assert result == 1
    assert "FAIL  valid normalization summary" in output


def test_mixed_scales_below_old_rounding_precision_fail(validator, tmp_path, monkeypatch, capsys):
    path = _campaign(tmp_path / "mixed", [NOMINAL, NOMINAL])
    second = path / "roots/batch_001.root"
    with uproot.open(second) as handle:
        arrays = handle["Events"].arrays(library="np")
    arrays["weight"] = arrays["weight_noxsec"] * 10.00001
    with uproot.recreate(second) as handle:
        handle["Events"] = arrays
        handle["Norm"] = {"np_nominal": np.array([10.])}
    result, output = _run(validator, monkeypatch, capsys, path)
    assert result == 1
    assert "FAIL  consistent sample scale" in output


@pytest.mark.parametrize(("values", "success"), [([0., 200.], True), ([-1., 20.], False), ([np.nan, 20.], False)])
def test_pileup_input_uses_payload_flow_without_an_invented_upper_cut(
    validator, tmp_path, monkeypatch, capsys, values, success,
):
    path = _campaign(tmp_path / "pileup", [NOMINAL])
    filename = path / "roots/batch_000.root"
    with uproot.open(filename) as handle:
        arrays = handle["Events"].arrays(library="np")
    arrays["nTrueInt"] = np.asarray(values)
    with uproot.recreate(filename) as handle:
        handle["Events"] = arrays
        handle["Norm"] = {"np_nominal": np.array([10.])}
    result, output = _run(validator, monkeypatch, capsys, path)
    assert result == (0 if success else 1), output


@pytest.mark.parametrize("value", [0., np.nan])
def test_invalid_norm_sum_cannot_bypass_campaign_comparison(
    validator, tmp_path, monkeypatch, capsys, value,
):
    path = _signed_campaign(tmp_path / "bad-norm", [1., -1.], 10.)
    with uproot.update(path / "roots/batch_000.root") as handle:
        handle["Norm"] = {"np_nominal": np.array([value])}
    result, output = _run(validator, monkeypatch, capsys, path)
    assert result == 1
    assert "FAIL  Norm sum over examined files" in output


def test_partially_normalized_campaign_fails(validator, tmp_path, monkeypatch, capsys):
    path = _campaign(tmp_path / "partial", [NOMINAL, NOMINAL], normalized=True)
    second = path / "roots/batch_001.root"
    with uproot.open(second) as handle:
        arrays = handle["Events"].arrays(library="np")
    arrays.pop("finalWeight")
    with uproot.recreate(second) as handle:
        handle["Events"] = arrays
        handle["Norm"] = {"np_nominal": np.array([10.])}
    result, output = _run(validator, monkeypatch, capsys, path)
    assert result == 1
    assert "FAIL  consistent finalWeight presence" in output
