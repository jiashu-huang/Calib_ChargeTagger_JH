"""Record the additional-loose-lepton veto without removing training events."""

from __future__ import annotations

import awkward as ak
import numpy as np

from boostedhh.processors.utils import PAD_VAL, pad_val


def extra_lepton_fields(electrons, muons, trigger_electrons, trigger_muons, is_data=False):
    """Count before truncation and exclude the chosen trigger by NanoAOD index.

    Version 1: pT > 15 GeV, |track eta| < 2.4; electron mvaIso_WP90;
    muon tightId and pfRelIso04_all < 0.25. Use the active corrected pT.
    No additional impact-parameter or jet-overlap cut is imposed. Generator
    origin is diagnostic only and never participates in the veto decision.
    """
    output = {}
    for flavour, leptons, primary, iso_name in (
        ("Electron", electrons, trigger_electrons, "pfRelIso03_all"),
        ("Muon", muons, trigger_muons, "pfRelIso04_all"),
    ):
        chosen = ak.any(leptons.nanoIdx[:, :, None] == primary.nanoIdx[:, None, :], axis=2)
        loose = (leptons.pt > 15) & (abs(leptons.eta) < 2.4)
        if flavour == "Electron":
            loose = loose & leptons.mvaIso_WP90
        else:
            loose = loose & leptons.tightId & (leptons.pfRelIso04_all < 0.25)
        extra = leptons[loose & ~chosen]
        output[f"nExtraLoose{flavour}s"] = ak.to_numpy(ak.num(extra)).astype(np.int32)
        extra = extra[ak.argsort(extra.pt, axis=1, ascending=False)]
        for field, name in (
            ("pt", "Pt"), ("eta", "Eta"), ("phi", "Phi"), ("charge", "Charge"),
            (iso_name, "Isolation"), ("nanoIdx", "NanoIdx"), ("jetIdx", "JetIdx"),
        ):
            output[f"ExtraLoose{flavour}{name}"] = pad_val(extra[field], 3, axis=1)
        output[f"ExtraLoose{flavour}GenPartFlav"] = (
            np.full((len(leptons), 3), PAD_VAL, dtype=np.int32) if is_data
            else pad_val(extra.genPartFlav, 3, axis=1)
        )
    output["PassExtraLeptonVeto"] = (
        output["nExtraLooseElectrons"] + output["nExtraLooseMuons"] == 0
    )
    output["ExtraLeptonVetoVersion"] = np.ones(len(electrons), dtype=np.int32)
    return output
