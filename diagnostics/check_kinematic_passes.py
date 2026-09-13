"""Validate complete variation outputs against nominal and their source NanoAOD.

Run after vcb.run --kinematic-variation all (or a collection of single passes).
Checks all-input totals, event migrations, signed JES, jet identity, lepton SFs,
active lepton pT, sorting and tag eligibility. Does not replace MET physics unit
tests or check_jet_tagger_roundtrip.py's comparison to input jet/charge fields.
"""

from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

import awkward as ak
import numpy as np
import uproot
from coffea.analysis_tools import Weights

from boostedhh.processors.corrections import JECs
from vcb.processors import lepton_sf
from vcb.processors.kinematic_variations import GROUPS, variation_from_id


def event_keys(arrays):
    return np.rec.fromarrays([arrays[key] for key in ("run", "luminosityBlock", "event")],
                             names="run,lumi,event")


def slots(arrays, prefix, count=10):
    return np.column_stack([arrays[f"{prefix}{i}"] for i in range(count)])


def read_output(path):
    with uproot.open(path) as handle:
        arr = handle["Events"].arrays(library="np")
        norm = handle["Norm"].arrays(library="np")
    keys = event_keys(arr)
    assert len(np.unique(keys)) == len(keys), f"Duplicate events: {path}"
    assert len(keys), f"This diagnostic needs a nonempty pass: {path}"
    identifiers = np.unique(arr["KinematicVariation"])
    assert len(identifiers) == 1, f"Mixed kinematic passes: {path}"
    variation = variation_from_id(int(identifiers[0]))
    tag = path.stem.removeprefix("nano_skim_").rsplit("_batch_", 1)[0]
    sidecar = path.parent / "outfiles" / f"{tag}.kinematics.json"
    totals_path = path.parent / "outfiles" / f"{tag}.pkl"
    totals = None
    if sidecar.exists():
        metadata = json.loads(sidecar.read_text())
        assert metadata["identifier"] == variation.identifier
        assert metadata["variation"] == variation.name
        with totals_path.open("rb") as handle:
            totals = next(iter(pickle.load(handle)["2024"].values()))["totals"]
    return arr, norm, keys, variation, totals


def check_object_outputs(arr, variation):
    assert np.all(np.isin(arr["TriggerLeptonFlav"], [11, 13]))
    assert np.all(arr["TriggerLeptonPt"] >= np.where(arr["TriggerLeptonFlav"] == 13, 26, 32))
    pt = slots(arr, "ak4JetPt")
    eta = slots(arr, "ak4JetEta")
    occupied = slots(arr, "ak4JetNanoIdx") >= 0
    assert np.all(pt[occupied] > 15)
    assert np.all(pt[:, :-1] >= pt[:, 1:])
    np.testing.assert_array_equal(occupied.sum(axis=1), np.minimum(arr["nJets"], 10))
    np.testing.assert_array_equal(slots(arr, "ak4JetBTaggable")[occupied],
                                  ((pt >= 20) & (abs(eta) <= 2.5))[occupied])
    untruncated = arr["nJets"] <= 10
    np.testing.assert_allclose(arr["ht"][untruncated],
                               np.where(occupied, pt, 0).sum(axis=1)[untruncated], rtol=2e-6)
    for kind, shift in (("Electron", variation.electron), ("Muon", variation.muon)):
        active = slots(arr, f"{kind}Pt", 3)
        target = "Nominal" if shift == "nominal" else shift[0].upper() + shift[1:]
        np.testing.assert_array_equal(active, slots(arr, f"{kind}Pt{target}", 3))
    for name in ("METPt", "METPhi", "weight", "weight_noxsec"):
        assert np.all(np.isfinite(arr[name])), name


def check_lepton_weights(arr, input_arrays, input_keys, keys):
    # Locate the chosen electron's *input* supercluster eta. This is distinct
    # from the track eta saved on TriggerLepton and is required by the EGM SFs.
    _, output_index, input_index = np.intersect1d(keys, input_keys, return_indices=True)
    assert len(output_index) == len(keys)
    order = input_index[np.argsort(output_index)]
    electron = arr["TriggerLeptonFlav"] == 11
    muon = arr["TriggerLeptonFlav"] == 13
    raw_eta = input_arrays["Electron_eta"][order]
    raw_phi = input_arrays["Electron_phi"][order]
    match = (raw_eta == arr["TriggerLeptonEta"]) & (raw_phi == arr["TriggerLeptonPhi"])
    assert ak.all(ak.sum(match, axis=1)[electron] == 1)
    sceta = ak.fill_none(ak.firsts(input_arrays["Electron_superclusterEta"][order][match]), 0)
    selected_electron = ak.mask(ak.zip({"pt": arr["TriggerLeptonPt"],
                                       "superclusterEta": sceta}), electron)
    selected_muon = ak.mask(ak.zip({"pt": arr["TriggerLeptonPt"],
                                   "eta": arr["TriggerLeptonEta"]}), muon)
    weights = Weights(len(keys), storeIndividual=True)
    lepton_sf.add_lepton_weights(weights, "2024", selected_electron, electron, selected_muon, muon)
    valid = arr["weight_noxsec"] != 0
    normalization = np.median(arr["weight"][valid] / arr["weight_noxsec"][valid])
    for name in ("electron_reco", "electron_id", "electron_trigger",
                 "muon_id", "muon_iso", "muon_trigger"):
        np.testing.assert_allclose(arr[f"single_weight_{name}"] / normalization,
                                   weights.partial_weight([name]), rtol=1e-12, atol=1e-12)


def compare_common(arr, nominal, vi, ni, variation, cset):
    varied = {key: value[vi] for key, value in arr.items()}
    central = {key: value[ni] for key, value in nominal.items()}
    is_jet = bool(variation.jet_options)
    if is_jet:
        for name in ("TriggerLeptonPt", "TriggerLeptonFlav", "weight", "weight_noxsec"):
            np.testing.assert_array_equal(varied[name], central[name])
    else:
        # Optional lepton-to-MET terms are not enabled. Cleaning must not alter
        # the full jet collection used for the common-event MET sum.
        for name in ("METPt", "METPhi"):
            np.testing.assert_array_equal(varied[name], central[name])
    v_idx, n_idx = slots(varied, "ak4JetNanoIdx"), slots(central, "ak4JetNanoIdx")
    event, vslot, nslot = np.nonzero((v_idx[:, :, None] == n_idx[:, None, :])
                                    & (v_idx[:, :, None] >= 0))
    for field in ("Eta", "Phi", "ParTPosvsAll", "ParTNegvsAll", "ParTZerovsAll",
                  "ParTPosvsNeg", "btagUParTAK4B", "btagPNetB", "QkCharge05_", "QkCharge10_"):
        np.testing.assert_array_equal(slots(varied, f"ak4Jet{field}")[event, vslot],
                                       slots(central, f"ak4Jet{field}")[event, nslot])
    if variation.name.startswith("jes_"):
        options = variation.jet_options
        key = f"Summer24Prompt24_V5_MC_{options['jes_source']}_AK4PFPuppi"
        pt = slots(central, "ak4JetPt")[event, nslot]
        eta = slots(central, "ak4JetEta")[event, nslot]
        delta = cset[key].evaluate(eta.astype(float), pt.astype(float))
        factor = (1 + options["jes_direction"] * delta).astype(np.float32)
        for field in ("Pt", "Mass"):
            # Padding promotes saved float32 jet momenta to float64. The
            # correction itself multiplies two float32 arrays before padding.
            expected = slots(central, f"ak4Jet{field}")[event, nslot].astype(np.float32) * factor
            np.testing.assert_array_equal(slots(varied, f"ak4Jet{field}")[event, vslot],
                                           expected)
    return {
        "common": len(vi),
        "changed_nJets": int(np.count_nonzero(varied["nJets"] != central["nJets"])),
        "changed_jet_slots": int(np.count_nonzero(np.any(v_idx != n_idx, axis=1))),
        "changed_met": int(np.count_nonzero((varied["METPt"] != central["METPt"])
                                            | (varied["METPhi"] != central["METPhi"]))),
        "changed_trigger_pt": int(np.count_nonzero(varied["TriggerLeptonPt"] != central["TriggerLeptonPt"])),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--reference-root", type=Path)
    parser.add_argument("--expect-group", choices=GROUPS)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    paths = sorted(args.directory.glob("*/nano_skim_*_batch_*.root"))
    reference = args.reference_root or next(p for p in paths if p.parent.name == "nominal")
    nominal, norm, nominal_keys, nominal_variation, totals = read_output(reference)
    assert nominal_variation.name == "nominal"
    with uproot.open(args.input) as handle:
        raw = handle["Events"].arrays(["run", "luminosityBlock", "event", "Electron_eta",
                                        "Electron_phi", "Electron_superclusterEta"], library="ak")
        input_count = handle["Events"].num_entries
    input_keys = event_keys(raw)
    cset = JECs("2024").correctionlib_cset
    results = {}
    for path in paths:
        arr, this_norm, keys, variation, this_totals = read_output(path)
        assert set(arr) == set(nominal), f"Schema mismatch: {path}"
        for name, value in norm.items():
            np.testing.assert_array_equal(this_norm[name], value)
        if totals is not None and this_totals is not None:
            assert this_totals.keys() == totals.keys()
            for name in totals:
                np.testing.assert_array_equal(this_totals[name], totals[name])
        check_object_outputs(arr, variation)
        check_lepton_weights(arr, raw, input_keys, keys)
        _, vi, ni = np.intersect1d(keys, nominal_keys, return_indices=True)
        row = compare_common(arr, nominal, vi, ni, variation, cset)
        row.update(selected=len(keys), entering=len(keys) - len(vi), leaving=len(nominal_keys) - len(ni))
        assert variation.name not in results, f"Repeated pass: {variation.name}"
        results[variation.name] = row
        print(f"PASS {variation.name}: {row}", flush=True)
    if args.expect_group:
        assert set(results) == set(GROUPS[args.expect_group])
    report = {"input": str(args.input), "input_file_entries": input_count,
              "directory": str(args.directory), "reference": str(reference),
              "normalization": {name: value.tolist() for name, value in norm.items()},
              "results": results, "verdict": "PASS"}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
