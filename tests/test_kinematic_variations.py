"""Full-source provenance, independent passes, and electron acceptance migration."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import awkward as ak
import numpy as np
import pytest
from coffea.nanoevents.methods import candidate

from boostedhh.processors.corrections import JECs
from vcb import run
from vcb.processors import electron_ss, objects
from vcb.processors.kinematic_variations import (
    ALL_PASSES,
    GROUPS,
    JES_SOURCES,
    Variation,
    resolve_variation,
    variation_from_id,
)

REPO = Path(__file__).resolve().parents[1]


def test_full_jes_basis_matches_supplied_case_i_and_evaluable_2024_payload():
    manifest = json.loads((REPO / "docs/jes-2024-full-source-manifest.json").read_text())
    assert tuple(row["source"] for row in manifest["sources"]) == JES_SOURCES
    assert len(JES_SOURCES) == 27
    cset = JECs("2024").correctionlib_cset
    eta, pt = np.meshgrid(np.linspace(-4.6, 4.6, 19), [16., 30., 100., 500., 2000.])
    signed = []
    for row in manifest["sources"]:
        correction = cset[row["correction_key"]]
        assert [v.name for v in correction.inputs] == ["JetEta", "JetPt"]
        values = correction.evaluate(eta.ravel(), pt.ravel())
        assert np.all(np.isfinite(values))
        if np.any(values < 0):
            signed.append(row["source"])
    assert "RelativeBal" in signed
    assert not any("Total" in name or "Regrouped" in name for name in JES_SOURCES)


@pytest.mark.parametrize("group", list(GROUPS))
def test_cli_groups_are_independent_passes_with_separate_outputs(monkeypatch, tmp_path, group):
    args = SimpleNamespace(
        kinematic_variation=group, muon_pt_variation="nominal", year="2024",
        executor="iterative", outdir=str(tmp_path / "out"),
        output_root_location=str(tmp_path / "roots"), naming_tag="sample",
        files=["raw.root"], save_systematics=True,
    )
    calls = []
    monkeypatch.setattr(run, "_run_single", calls.append)
    run.main(args)
    assert [a.kinematic_variation for a in calls] == list(GROUPS[group])
    assert len({a.outdir for a in calls}) == len(calls)
    assert len({a.output_root_location for a in calls}) == len(calls)
    assert all(a.files == ["raw.root"] and a.save_systematics for a in calls)
    assert args.kinematic_variation == group
    assert len(ALL_PASSES) == 65
    assert len(GROUPS["jets"]) == 57


@pytest.mark.parametrize("options", [
    {"year": "2023"}, {"executor": "dask"}, {"muon_pt_variation": "scaleUp"},
])
def test_invalid_group_configuration_rejected_before_starting(monkeypatch, options):
    args = {"kinematic_variation": "jets", "muon_pt_variation": "nominal",
            "year": "2024", "executor": "iterative"}
    args.update(options)
    monkeypatch.setattr(run, "_run_single", lambda _: pytest.fail("Must not start a partial run"))
    with pytest.raises(ValueError, match=r"2024 MC|Use only one"):
        run.main(SimpleNamespace(**args))


def test_standalone_ids_and_legacy_muon_alias_are_unambiguous():
    # Persisted identifiers: pin the boundaries so reordering the schema fails.
    for name, identifier in (("nominal", 0), ("jes_AbsoluteMPFBiasUp", 1),
                             ("jerUp", 55), ("electron_scaleUp", 57), ("muon_scaleUp", 61)):
        assert Variation(name).identifier == identifier
        assert variation_from_id(identifier).name == name
    assert resolve_variation(muon="scaleUp") == Variation("muon_scaleUp")
    assert Variation("jes_RelativeBalDown").jet_options == {
        "jes_source": "RelativeBal", "jes_direction": -1,
    }
    with pytest.raises(ValueError, match="2024 MC"):
        Variation("jerUp").validate_sample("2024", is_data=True)
    with pytest.raises(ValueError, match="Unknown"):
        variation_from_id(1000)


def _electrons_near_plateau():
    pt = np.linspace(31.0, 33.0, 2000)
    n = len(pt)
    electrons = ak.zip({name: ak.unflatten(value, np.ones(n, int)) for name, value in {
        "pt": pt, "eta": np.full(n, 0.5), "phi": np.zeros(n), "mass": np.zeros(n),
        "charge": np.ones(n, int), "superclusterEta": np.full(n, 0.5),
        "r9": np.full(n, 0.95), "seedGain": np.full(n, 12.0),
        "mvaIso_WP90": np.ones(n, bool),
    }.items()}, with_name="PtEtaPhiMCandidate", behavior=candidate.behavior)
    trig = ak.with_field(electrons, ak.ones_like(electrons.pt, dtype=int) * 11, "id")
    trig = ak.with_field(trig, ak.ones_like(trig.pt, dtype=int) * (1 << 18), "filterBits")
    events = ak.Array({"run": np.full(n, 382000), "luminosityBlock": np.ones(n, int),
                       "event": np.arange(n) + 1000,
                       "HLT": {"Ele30_WPTight_Gsf": np.ones(n, bool)}})
    return ak.with_field(events, trig, "TrigObj"), electrons


@pytest.mark.parametrize("variation", ["scaleUp", "scaleDown", "smearUp", "smearDown"])
def test_electron_shift_changes_real_trigger_acceptance_from_raw_input(variation):
    events, electrons = _electrons_near_plateau()
    nominal = electron_ss.apply_electron_scale_smearing(events, electrons, "2024", False)
    shifted = electron_ss.apply_electron_scale_smearing(events, electrons, "2024", False,
                                                       variation)
    np.testing.assert_array_equal(ak.flatten(shifted.pt), ak.flatten(nominal[f"pt_{variation}"]))
    np.testing.assert_array_equal(ak.flatten(shifted.pt_nominal), ak.flatten(nominal.pt))
    np.testing.assert_array_equal(ak.flatten(shifted.pt_raw), ak.flatten(electrons.pt))
    accepted = []
    for corrected in (nominal, shifted):
        _, matches = objects.good_electrons(events, corrected, "2024")
        accepted.append(ak.to_numpy(ak.any(matches["ElectronTrigMatchEGamma"], axis=1)))
    assert np.any(accepted[0] != accepted[1])
    if variation != "scaleDown":
        assert np.any(accepted[1] & ~accepted[0])
    if variation != "scaleUp":
        assert np.any(accepted[0] & ~accepted[1])


def test_requested_electron_shift_requires_payload(monkeypatch):
    events, electrons = _electrons_near_plateau()
    monkeypatch.setattr(electron_ss, "get_electron_ss_correctionset", lambda _: None)
    with pytest.raises(FileNotFoundError, match="EGM payload"):
        electron_ss.apply_electron_scale_smearing(events, electrons, "2024", False, "scaleUp")


@pytest.mark.parametrize("variation", ["nominal", "jes_RelativeBalDown", "jerUp"])
def test_condor_generation_preserves_pass_and_matching_output_names(tmp_path, monkeypatch, variation):
    script = REPO / "condor/submit_batches.py"
    spec = importlib.util.spec_from_file_location("submit_batches", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    batch = tmp_path / "input/batch_000"
    batch.mkdir(parents=True)
    (batch / "input.root").touch()
    monkeypatch.setattr(sys, "argv", [str(script), "--input-root", str(batch.parent),
                                    "--files-name", "TTtoLNuCB", "--tag", "test",
                                    "--run-dir", str(tmp_path / "jobs"),
                                    "--processed-dir", str(tmp_path / "processed"),
                                    "--kinematic-variation", variation])
    module.main()  # Generates files only; never submits jobs.
    campaign = json.loads((tmp_path / "jobs/campaign.json").read_text())
    assert campaign["kinematic_variation"] == variation
    assert campaign["kinematic_variation_id"] == Variation(variation).identifier
    worker = next((tmp_path / "jobs").glob("*/run_batch.sh")).read_text()
    assert f'KINEMATIC_VARIATION="{variation}"' in worker
    assert '--kinematic-variation "$KINEMATIC_VARIATION"' in worker
    assert 'outfiles/$FILETAG.pkl' in worker
    assert '.kinematics.json' in worker
    assert "@@" not in worker
