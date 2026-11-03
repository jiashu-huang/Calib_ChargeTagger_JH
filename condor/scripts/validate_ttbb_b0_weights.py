"""Validate retained TTBB weights against a complete, staged input NanoAOD."""

from __future__ import annotations

import pickle
from pathlib import Path

import awkward as ak
import numpy as np
import uproot
from coffea.analysis_tools import Weights

from boostedhh.processors.corrections import add_pileup_weight

DATASET = "TTBB-TTtoLNu2Q"
SIGMA_LUMI = 16.011655167690346 * 109820.0
SYSTEMATIC_BRANCHES = {
    f"weight_{source}{direction}"
    for source in ("pileup", "ISRPartonShower", "FSRPartonShower", "electron_reco",
                   "electron_id", "electron_trigger", "muon_id", "muon_iso", "muon_trigger")
    for direction in ("Up", "Down")
}
SCALE_BRANCHES = {f"scale_weights{i}" for i in range(6)}


def expected_variations(lhe, shower):
    """Use the measured 2024 TTBB nine-member scale and four-member PS ordering."""
    if lhe.ndim != 2 or lhe.shape[1] != 9 or shower.shape != (len(lhe), 4):
        raise ValueError("Unexpected TTBB scale/shower weight layout")
    if not np.isfinite(lhe).all() or not np.isfinite(shower).all() or np.any(lhe[:, 4] == 0):
        raise ValueError("Invalid TTBB theory weights or zero central scale member")
    # Preserve the existing processor convention; this release does not change its clipping.
    scales = np.clip(lhe[:, [0, 1, 3, 5, 7, 8]] / lhe[:, 4, None], 0, 4)
    ps = {"ISRPartonShowerUp": shower[:, 0], "ISRPartonShowerDown": shower[:, 2],
          "FSRPartonShowerUp": shower[:, 1], "FSRPartonShowerDown": shower[:, 3]}
    return scales, ps


def validate(nano, skim, pickle_path):
    with uproot.open(nano) as source:
        raw = source["Events"].arrays(
            ["genWeight", "Pileup_nTrueInt", "LHEScaleWeight", "PSWeight"], library="ak")
    gen = ak.to_numpy(raw.genWeight).astype(np.float64)
    scales, shower = expected_variations(ak.to_numpy(raw.LHEScaleWeight), ak.to_numpy(raw.PSWeight))
    pu_weights = Weights(len(gen), storeIndividual=True)
    add_pileup_weight(pu_weights, "2024", ak.to_numpy(raw.Pileup_nTrueInt))
    pu = pu_weights.weight()
    nominal = gen * pu
    expected_sums = {"nevents": gen.sum(), "np_nominal": nominal.sum(),
                     "np_scale_weights": (nominal[:, None] * scales).sum(axis=0)}
    for direction in ("Up", "Down"):
        expected_sums[f"np_pileup{direction}"] = (
            gen * pu_weights.weight(modifier=f"pileup{direction}")).sum()
    for name, ratio in shower.items():
        expected_sums[f"np_{name}"] = (nominal * ratio).sum()
    with Path(pickle_path).open("rb") as stream:
        payload = pickle.load(stream)
    if set(payload) != {"2024"} or set(payload["2024"]) != {DATASET}:
        raise ValueError("Unexpected year/dataset in TTBB totals")
    totals = payload["2024"][DATASET]["totals"]
    if set(totals) != set(expected_sums):
        raise ValueError(f"Unexpected normalization-total keys: {sorted(totals)}")
    for name, expected in expected_sums.items():
        if not np.isfinite(totals[name]).all():
            raise ValueError(f"Nonfinite total: {name}")
        # nevents is inherited float32 chunk summation. Weight sums use float64.
        np.testing.assert_allclose(totals[name], expected,
                                   rtol=1e-6 if name == "nevents" else 1e-8,
                                   atol=1e-6, err_msg=f"All-input total {name}")
    with uproot.open(skim) as source:
        tree = source["Events"]
        required = SYSTEMATIC_BRANCHES | SCALE_BRANCHES
        if missing := required - set(tree.keys()):
            raise ValueError(f"Missing requested TTBB weights: {sorted(missing)}")
        fields = sorted(required | {"weight", "weight_noxsec", "single_weight_genweight",
                                     "single_weight_pileup", "B0SourceEntry"})
        a = tree.arrays(fields, library="np")
        schema = tree.typenames()
        norm = source["Norm"].arrays(library="np")
    for name in fields:
        if not np.isfinite(a[name]).all():
            raise ValueError(f"Nonfinite saved values: {name}")
    entries = a["B0SourceEntry"]
    np.testing.assert_allclose(a["weight"], a["weight_noxsec"] * SIGMA_LUMI, rtol=1e-12)
    np.testing.assert_allclose(a["single_weight_genweight"], gen[entries] * SIGMA_LUMI, rtol=1e-12)
    np.testing.assert_allclose(a["single_weight_pileup"], pu[entries] * SIGMA_LUMI, rtol=1e-12)
    for i in range(6):
        np.testing.assert_allclose(a[f"scale_weights{i}"], a["weight"] * scales[entries, i],
                                   rtol=1e-12, atol=1e-6)
    for name, ratio in shower.items():
        np.testing.assert_allclose(a[f"weight_{name}"], a["weight"] * ratio[entries],
                                   rtol=1e-12, atol=1e-6)
    np.testing.assert_allclose(norm["np_nominal"].sum(), totals["np_nominal"], rtol=1e-12)
    return {"passed": True, "input_events": len(gen), "selected_events": len(entries),
            "negative_genweights_input": int((gen < 0).sum()),
            "negative_weights_selected": int((a["weight"] < 0).sum()),
            "scale_branches": sorted(SCALE_BRANCHES),
            "systematic_branches": sorted(SYSTEMATIC_BRANCHES),
            "schema": schema,
            "all_input_totals": {name: np.asarray(value).tolist() for name, value in totals.items()}}
