"""Check version-3 TTBB weights against every event in a staged input NanoAOD."""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import awkward as ak
import correctionlib
import numpy as np
import uproot

from vcb.processors.lepton_sf import MUON_COMPONENT_WEIGHT_BRANCHES
from vcb.processors.pdf_weights import read_pdf_layout, read_saved_layout
from vcb.processors.top_pt import SF_FUNCTIONS
from vcb.processors.weight_prescription import read_saved_prescription, read_weight_prescription

DATASET = "TTBB-TTtoLNu2Q"
SIGMA_LUMI = 16.011655167690346 * 109820.0
LEPTON_FACTORS = ("electron_reco", "electron_id", "electron_trigger",
                  "muon_id", "muon_iso", "muon_trigger")
SYSTEMATIC_BRANCHES = {
    f"weight_{source}{direction}"
    for source in ("pileup", "ISRPartonShower", "FSRPartonShower", *LEPTON_FACTORS)
    for direction in ("Up", "Down")
} | MUON_COMPONENT_WEIGHT_BRANCHES
SCALE_BRANCHES = {f"scale_weights{i}" for i in range(6)}


def expected_variations(lhe, shower):
    """Nine-member TTBB scale grid and four-member shower grid, without clipping."""
    if lhe.ndim != 2 or lhe.shape[1] != 9 or shower.shape != (len(lhe), 4):
        raise ValueError("Unexpected TTBB scale/shower weight layout")
    if not np.isfinite(lhe).all() or not np.isfinite(shower).all() or np.any(lhe[:, 4] == 0):
        raise ValueError("Invalid TTBB theory weights or zero central scale member")
    # Divide at the stored input precision, as in the version-3 prescription.
    scales = lhe[:, [0, 1, 3, 5, 7, 8]] / lhe[:, 4, None]
    if not np.isfinite(scales).all():
        raise ValueError("Nonfinite normalized scale ratio")
    ps = {"ISRPartonShowerUp": shower[:, 0], "ISRPartonShowerDown": shower[:, 2],
          "FSRPartonShowerUp": shower[:, 1], "FSRPartonShowerDown": shower[:, 3]}
    return scales, ps


def source_top_factors(raw):
    """Select the two tops directly from NanoAOD, using the stored SF definitions."""
    flags, pdg = raw.GenPart_statusFlags, raw.GenPart_pdgId
    selected = (abs(pdg) == 6) & ((flags & (1 << 8)) != 0) & ((flags & (1 << 13)) != 0)
    top_pt, top_id = raw.GenPart_pt[selected], pdg[selected]
    pair = ak.to_numpy((ak.num(top_pt) == 2) & (ak.sum(top_id, axis=1) == 0))
    pt = ak.to_numpy(ak.fill_none(ak.pad_none(top_pt, 2, clip=True), 0.)).astype(float)
    valid = pair & np.all(np.isfinite(pt) & (pt >= 0), axis=1)
    pt = np.where(valid[:, None], pt, 0.)
    return {name: np.where(valid, np.sqrt(function(pt).prod(axis=1)), 1.)
            for name, function in SF_FUNCTIONS.items()}, valid


def source_expectations(nano):
    prescription = read_weight_prescription(str(nano), require_scale=True, top_pt_enabled=True)
    layout = read_pdf_layout(str(nano))
    if prescription["version"] != 3 or prescription["scale"]["input_members"] != 9:
        raise ValueError("This TTBB campaign requires the version-3 nine-member scale prescription")
    with uproot.open(nano) as source:
        raw = source["Events"].arrays([
            "genWeight", "Pileup_nTrueInt", "LHEScaleWeight", "PSWeight", "LHEPdfWeight",
            "GenPart_pdgId", "GenPart_statusFlags", "GenPart_pt",
        ], library="ak")
    gen = ak.to_numpy(raw.genWeight).astype(float)
    scales, shower = expected_variations(ak.to_numpy(raw.LHEScaleWeight), ak.to_numpy(raw.PSWeight))
    pdf = ak.to_numpy(raw.LHEPdfWeight)
    if pdf.shape != (len(gen), len(layout["lha_ids"])) or not np.isfinite(pdf).all():
        raise ValueError("PDF members disagree with the input metadata or contain nonfinite values")
    # Evaluate the payload independently of the processor's weight builder.
    payload = correctionlib.CorrectionSet.from_file(str(
        Path(__file__).resolve().parents[2] / "src/boostedhh/corrections/2024_puWeights.json.gz"))
    correction = payload[next(iter(payload))]
    interactions = ak.to_numpy(raw.Pileup_nTrueInt).astype(float)
    pu = {name: correction.evaluate(interactions, name) for name in ("nominal", "up", "down")}
    nominal = gen * pu["nominal"]
    tops, top_valid = source_top_factors(raw)
    per_event = {"nominal": nominal, "pileupUp": gen * pu["up"], "pileupDown": gen * pu["down"]}
    per_event.update({name: nominal * ratio for name, ratio in shower.items()})
    per_event.update(scale_weights=nominal[:, None] * scales, pdf_weights=nominal[:, None] * pdf)
    sums = {"nevents": gen.sum(), "n_input_events": len(gen),
            "n_top_pt_valid": int(top_valid.sum()), "n_top_pt_invalid": int((~top_valid).sum())}
    for name, values in per_event.items():
        sums[f"np_{name}"] = values.sum(axis=0)
        for column, factor in tops.items():
            suffix = "" if name == "nominal" else "_" + name
            sums[f"np_{column}{suffix}"] = (
                values * (factor[:, None] if values.ndim == 2 else factor)).sum(axis=0)
    return {"prescription": prescription, "layout": layout, "gen": gen, "pu": pu,
            "scales": scales, "shower": shower, "pdf": pdf, "tops": tops,
            "top_valid": top_valid, "sums": sums}


def validate(nano, skim, pickle_path):
    expected = source_expectations(nano)
    gen, pu, scales = expected["gen"], expected["pu"], expected["scales"]
    with Path(pickle_path).open("rb") as stream:
        payload = pickle.load(stream)
    if set(payload) != {"2024"} or set(payload["2024"]) != {DATASET}:
        raise ValueError("Unexpected year/dataset in TTBB totals")
    sample = payload["2024"][DATASET]
    totals = sample["totals"]
    for field, value in (("weight_prescriptions", expected["prescription"]),
                         ("pdf_layouts", expected["layout"])):
        if sample.get(field) != {json.dumps(value, sort_keys=True)}:
            raise ValueError(f"Missing or incompatible pickle {field}")
    if set(totals) != set(expected["sums"]):
        raise ValueError(f"Unexpected normalization-total keys: {sorted(totals)}")
    pdf_branches = {f"PDFWeight{i}" for i in range(len(expected["layout"]["lha_ids"]))}
    with uproot.open(skim) as source:
        if read_saved_prescription(source) != expected["prescription"]:
            raise ValueError("Saved weight prescription disagrees with the input")
        if read_saved_layout(source) != expected["layout"]:
            raise ValueError("Saved PDF mapping disagrees with the input")
        tree = source["Events"]
        required = SYSTEMATIC_BRANCHES | SCALE_BRANCHES | pdf_branches | set(SF_FUNCTIONS)
        required |= {f"single_weight_{name}" for name in LEPTON_FACTORS}
        required |= {"weight", "weight_noxsec", "single_weight_genweight", "single_weight_pileup",
                     "B0SourceEntry", "TopPtWeightValid", "WeightPrescriptionVersion"}
        if missing := required - set(tree.keys()):
            raise ValueError(f"Missing requested TTBB weights: {sorted(missing)}")
        a = tree.arrays(sorted(required), library="np")
        schema = tree.typenames()
        norm = source["Norm"].arrays(library="np")
    if set(norm) != set(expected["sums"]):
        raise ValueError("ROOT and pickle normalization fields disagree")
    for name, value in expected["sums"].items():
        tolerance = 1e-6 if name == "nevents" else 1e-10
        for label, actual in (("pickle", totals[name]), ("ROOT", norm[name].sum(axis=0))):
            if not np.isfinite(actual).all():
                raise ValueError(f"Nonfinite {label} total: {name}")
            np.testing.assert_allclose(actual, value, rtol=tolerance, atol=1e-6,
                                       err_msg=f"All-input {label} total {name}")
    for name, value in a.items():
        if not np.isfinite(value).all():
            raise ValueError(f"Nonfinite saved values: {name}")
    entries = a["B0SourceEntry"]
    if entries.dtype.kind != "u" or np.any(entries >= len(gen)) or len(np.unique(entries)) != len(entries):
        raise ValueError("Invalid or duplicate saved source entry")
    lepton = np.prod([a[f"single_weight_{name}"] / SIGMA_LUMI for name in LEPTON_FACTORS], axis=0)
    nominal = gen[entries] * pu["nominal"][entries] * lepton
    np.testing.assert_allclose(a["weight_noxsec"], nominal, rtol=1e-12)
    np.testing.assert_allclose(a["weight"], nominal * SIGMA_LUMI, rtol=1e-12)
    np.testing.assert_allclose(a["single_weight_genweight"], gen[entries] * SIGMA_LUMI, rtol=1e-12)
    np.testing.assert_allclose(a["single_weight_pileup"], pu["nominal"][entries] * SIGMA_LUMI, rtol=1e-12)
    for direction in ("Up", "Down"):
        value = gen[entries] * pu[direction.lower()][entries] * lepton * SIGMA_LUMI
        np.testing.assert_allclose(a[f"weight_pileup{direction}"], value, rtol=1e-12, atol=1e-6)
    for i in range(6):
        np.testing.assert_allclose(a[f"scale_weights{i}"], a["weight"] * scales[entries, i],
                                   rtol=1e-12, atol=1e-6)
    for name, ratio in expected["shower"].items():
        np.testing.assert_allclose(a[f"weight_{name}"], a["weight"] * ratio[entries],
                                   rtol=1e-12, atol=1e-6)
    for i in range(expected["pdf"].shape[1]):
        np.testing.assert_array_equal(a[f"PDFWeight{i}"], expected["pdf"][entries, i])
    np.testing.assert_array_equal(a["TopPtWeightValid"], expected["top_valid"][entries])
    for name, values in expected["tops"].items():
        np.testing.assert_allclose(a[name], values[entries], rtol=1e-12)
    return {"passed": True, "input_events": len(gen), "selected_events": len(entries),
            "negative_genweights_input": int((gen < 0).sum()),
            "negative_weights_selected": int((a["weight"] < 0).sum()),
            "negative_scale_ratios_input": int((scales < 0).sum()),
            "scale_ratios_above_four_input": int((scales > 4).sum()),
            "pileup_factors_above_ten_input": int((pu["nominal"] > 10).sum()),
            "scale_branches": sorted(SCALE_BRANCHES), "systematic_branches": sorted(SYSTEMATIC_BRANCHES),
            "weight_prescription": expected["prescription"], "pdf_layout": expected["layout"],
            "schema": schema, "all_input_totals": {
                name: np.asarray(value).tolist() for name, value in totals.items()}}
