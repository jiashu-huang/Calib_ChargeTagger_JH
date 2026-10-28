"""Preserve rejected-event denominators, generator alternatives and veto inputs."""

from __future__ import annotations

import awkward as ak
import numpy as np
import pytest
import uproot

from boostedhh.run_utils import flatten_dict
from vcb.processors.lepton_veto import extra_lepton_fields
from vcb.processors.met_variations import unclustered_met_fields
from vcb.processors.pdf_weights import (
    layout_from_title,
    member_weights,
    pdf_metadata_fields,
    read_saved_layout,
    validate_pdf_merge,
)
from vcb.processors.skim_metadata import save_chunk_metadata, write_root_metadata


def _leptons(entries):
    defaults = {"pt": 30., "eta": 0., "phi": 0., "charge": -1, "nanoIdx": 0, "jetIdx": -1,
                "mvaIso_WP90": True, "tightId": True, "pfRelIso03_all": 0.1,
                "pfRelIso04_all": 0.1, "genPartFlav": 1}
    return ak.Array([[{**defaults, "nanoIdx": i, **entry} for i, entry in enumerate(row)]
                     for row in entries])


def test_heavy_flavour_muon_counts_by_isolation_not_by_truth_origin():
    electrons = _leptons([[{}]])
    muons = _leptons([[{"pt": 40.}, {"pt": 25., "genPartFlav": 5},
                       {"pt": 45., "genPartFlav": 5, "pfRelIso04_all": 0.4}]])
    result = extra_lepton_fields(electrons, muons, electrons[:, :0], muons[:, :1])
    assert result["nExtraLooseElectrons"].tolist() == [1]
    assert result["nExtraLooseMuons"].tolist() == [1]
    assert result["PassExtraLeptonVeto"].tolist() == [False]
    assert result["ExtraLooseMuonPt"][0, 0] == 25
    assert result["ExtraLooseMuonGenPartFlav"][0, 0] == 5


def test_veto_thresholds_primary_identity_truncation_and_shift_migration():
    electrons = _leptons([[{"eta": 2.45}, {"pt": 15.}, {"eta": 2.4},
                           {"pt": 18.}, {"pt": 19.}, {"pt": 20.}, {"pt": 21.}]])
    muons = _leptons([[{"pfRelIso04_all": 0.25}, {"tightId": False}]])
    result = extra_lepton_fields(electrons, muons, electrons[:, :1], muons[:, :0])
    assert result["nExtraLooseElectrons"].tolist() == [4]
    assert result["nExtraLooseMuons"].tolist() == [0]
    assert result["ExtraLooseElectronPt"].tolist() == [[21., 20., 19.]]
    assert result["ExtraLooseElectronNanoIdx"].tolist() == [[6, 5, 4]]
    # Trigger can be outside the loose acceptance: do not blindly subtract one.
    one = electrons[:, :1]
    nominal = muons[:, :1]
    nominal = ak.with_field(nominal, [[0.1]], "pfRelIso04_all")
    nominal = ak.with_field(nominal, [[14.9]], "pt")
    shifted = ak.with_field(nominal, [[15.1]], "pt")
    assert extra_lepton_fields(one, nominal, one, nominal[:, :0])["PassExtraLeptonVeto"][0]
    assert not extra_lepton_fields(one, shifted, one, shifted[:, :0])["PassExtraLeptonVeto"][0]


def test_unclustered_shifts_are_rebased_vectors_not_nano_absolute_met():
    nano = ak.Array([{"pt": 10., "phi": 0., "ptUnclusteredUp": 13., "phiUnclusteredUp": 0.,
                      "ptUnclusteredDown": 10., "phiUnclusteredDown": np.pi}])
    rebuilt = ak.Array([{"pt": 20., "phi": np.pi / 2}])
    fields = unclustered_met_fields(nano, rebuilt)
    np.testing.assert_allclose(fields["METUnclusteredDeltaXUp"], [3.])
    np.testing.assert_allclose(fields["METPtUnclusteredUp"], [np.hypot(3, 20)])
    np.testing.assert_allclose(fields["METPhiUnclusteredUp"], [np.arctan2(20, 3)])
    np.testing.assert_allclose(fields["METPtUnclusteredDown"], [np.hypot(-20, 20)])
    with pytest.raises(ValueError, match="Missing required"):
        unclustered_met_fields(nano[[f for f in nano.fields if f != "phiUnclusteredDown"]], rebuilt)


def _layout(first=325300, last=325402):
    return layout_from_title(
        f"LHE pdf variation weights (w_var / w_nominal) for LHA IDs {first} - {last}"
    )


def test_pdf_metadata_distinguishes_actual_ttbb_hessian_without_alphas():
    signal, ttbb = _layout(), _layout(325500, 325600)
    assert signal["error_type"] == "symmhessian+as"
    assert signal["alpha_s_members"] == {"101": 0.116, "102": 0.120}
    assert ttbb["error_type"] == "symmhessian"
    assert ttbb["alpha_s_members"] == {}
    assert len(ttbb["lha_ids"]) == 101
    with pytest.raises(ValueError, match="Unverified"):
        _layout(123, 225)
    with pytest.raises(ValueError, match="Unsupported"):
        layout_from_title("103 weights")


def test_pdf_ratios_survive_zero_nominal_weights_and_signed_members():
    ratios = np.ones((3, 103), dtype=np.float32)
    ratios[:, 3] = [-4, 0, 10]
    saved, totals = member_weights(ak.Array(ratios), _layout(), np.array([2., -3., 0.]))
    np.testing.assert_array_equal(saved, ratios)
    assert saved.dtype == ratios.dtype
    assert totals[3] == -8
    assert totals[0] == -1
    with pytest.raises(ValueError, match="length"):
        member_weights(ak.Array([[1.], [2.]]), _layout(), [1., 1.])
    ratios[0, 1] = np.nan
    with pytest.raises(ValueError, match="finite"):
        member_weights(ak.Array(ratios), _layout(), [1., 1., 1.])


def _root(path, layout, sums, *, rows=1, metadata=True):
    with uproot.recreate(path) as handle:
        handle["Events"] = {
            f"PDFWeight{i}": np.ones(rows, dtype=np.float32)
            for i in range(len(layout["lha_ids"]))
        }
        handle["Norm"] = {"np_nominal": np.array([sums[0]]),
                          "np_pdf_weights": np.array([sums])}
        if metadata:
            handle["PdfMetadata"] = pdf_metadata_fields(layout)


def test_pdf_merge_checks_metadata_and_keeps_empty_selection_sums(tmp_path):
    signal, ttbb = _layout(), _layout(325500, 325600)
    paths = [tmp_path / f"{i}.root" for i in range(3)]
    _root(paths[0], signal, np.full(103, 20.))
    _root(paths[1], signal, np.full(103, -3.), rows=0)
    _root(paths[2], ttbb, np.ones(101))
    assert validate_pdf_merge(paths[:2]) == signal
    with pytest.raises(ValueError, match="Incompatible"):
        validate_pdf_merge(paths)
    _root(paths[2], signal, np.ones(103), metadata=False)
    with pytest.raises(ValueError, match="no PdfMetadata"):
        validate_pdf_merge(paths)


def test_chunk_records_preserve_empty_selections_and_distribute_totals_once(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOSTEDHH_OUTPARQUET_DIR", str(tmp_path))
    paths = [tmp_path / f"{i}.parquet" for i in range(3)]
    for index, path in enumerate(paths):
        save_chunk_metadata(path.name, "2024", "TTtoLNuCB", {
            "np_nominal": index + 1., "nevents": 100.,
            "np_pdf_weights": np.full(103, index + 1.),
        }, _layout())
    # The middle chunk has no selected events. It still belongs to its batch.
    totals = []
    for index, batch in enumerate([paths[:2], paths[2:]]):
        target = tmp_path / f"batch{index}.root"
        with uproot.recreate(target) as handle:
            handle["Events"] = {f"PDFWeight{i}": np.ones(1) for i in range(103)}
            write_root_metadata(handle, batch)
        with uproot.open(target) as handle:
            assert read_saved_layout(handle) == _layout()
            totals.append(handle["Norm"]["np_nominal"].array(library="np")[0])
    assert totals == [3., 3.]
    save_chunk_metadata(paths[2].name, "2024", "TTBB-TTtoLNu2Q", {
        "np_nominal": 1., "nevents": 1., "np_pdf_weights": np.ones(101),
    }, _layout(325500, 325600))
    with (
        uproot.recreate(tmp_path / "bad.root") as handle,
        pytest.raises(ValueError, match="different datasets"),
    ):
        write_root_metadata(handle, paths)


@pytest.mark.parametrize("rows", [0, 1, 2])
def test_root_flattening_preserves_event_axis_for_singletons_and_empty_chunks(rows):
    output = flatten_dict({"weight": np.ones(rows), "PDFWeight": np.ones((rows, 103))})
    assert len(output) == 104
    assert all(value.shape == (rows,) for value in output.values())
