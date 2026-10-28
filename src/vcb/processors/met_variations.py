"""Transport NanoAOD unclustered-energy shifts to the rebuilt MET vector."""
from __future__ import annotations

import numpy as np


def unclustered_met_fields(nano_met, corrected_met):
    """Keep both signed shifts separately; neither is a variation of the JEC."""
    required = [f"{component}Unclustered{direction}"
                for component in ("pt", "phi") for direction in ("Up", "Down")]
    missing = [name for name in required if name not in nano_met.fields]
    if missing:
        raise ValueError(f"Missing required PUPPI unclustered-MET inputs: {missing}")
    px = np.asarray(corrected_met.pt) * np.cos(np.asarray(corrected_met.phi))
    py = np.asarray(corrected_met.pt) * np.sin(np.asarray(corrected_met.phi))
    nano_px = np.asarray(nano_met.pt) * np.cos(np.asarray(nano_met.phi))
    nano_py = np.asarray(nano_met.pt) * np.sin(np.asarray(nano_met.phi))
    result = {}
    for direction in ("Up", "Down"):
        pt = np.asarray(nano_met[f"ptUnclustered{direction}"])
        phi = np.asarray(nano_met[f"phiUnclustered{direction}"])
        dx, dy = pt * np.cos(phi) - nano_px, pt * np.sin(phi) - nano_py
        result[f"METUnclusteredDeltaX{direction}"] = dx
        result[f"METUnclusteredDeltaY{direction}"] = dy
        result[f"METPtUnclustered{direction}"] = np.hypot(px + dx, py + dy)
        result[f"METPhiUnclustered{direction}"] = np.arctan2(py + dy, px + dx)
    if not all(np.all(np.isfinite(value)) for value in result.values()):
        raise ValueError("Nonfinite PUPPI unclustered-MET inputs")
    return result
