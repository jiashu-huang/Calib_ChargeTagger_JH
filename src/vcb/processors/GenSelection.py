"""
Gen selection functions for skimmer.

Author(s): Raghav Kansal

Ported for Calib_ChargeTagger_JH: only the Vcb path (helpers +
``gen_selection_Vcb``) is kept. The unused ``gen_selection_Top*`` /
``gen_selection_HH*`` functions from the old repo are dropped.
"""

from __future__ import annotations

import awkward as ak
import numpy as np
from coffea.nanoevents.methods.base import NanoEventsArray
from coffea.nanoevents.methods.nanoaod import (
    ElectronArray,
    JetArray,
    MuonArray,
)

from boostedhh.processors.utils import (
    GEN_FLAGS,
    PAD_VAL,
    PDGID,
    pad_val,
)

TOP_PDGID = 6
W_PDGID = 24
LepArray = ElectronArray | MuonArray
W_TO_QUARK_PAIR_TAGS = {
    "GenWtoUD": (PDGID.d, PDGID.u),
    "GenWtoUS": (PDGID.u, PDGID.s),
    "GenWtoCD": (PDGID.d, PDGID.c),
    "GenWtoCS": (PDGID.s, PDGID.c),
    "GenWtoUB": (PDGID.u, PDGID.b),
    "GenWtoBC": (PDGID.c, PDGID.b),
}


def _single_particle_vars(
    prefix: str,
    particles: ak.Array,
    skim_vars: dict,
    overrides: dict | None = None,
):
    """Convert a per-event single-particle record array into flat skim branches."""

    overrides = overrides or {}

    return {
        f"{prefix}{key}": ak.fill_none(overrides.get(var, particles[var]), np.float32(PAD_VAL))
        .to_numpy()
        .astype(np.float32, copy=False)
        for (var, key) in skim_vars.items()
    }


def _single_value_to_numpy(values: ak.Array, dtype=None, pad_value=PAD_VAL):
    """Convert a per-event scalar awkward array to numpy with explicit padding."""

    arr = ak.fill_none(values, pad_value).to_numpy()
    return arr.astype(dtype) if dtype is not None else arr


def _top_decay_products(tops: ak.Array):
    """
    Keep the top -> W/b hierarchy intact for semi-leptonic ttbar truth bookkeeping.
    """

    top_children = tops.distinctChildren
    top_children = top_children[top_children.hasFlags(GEN_FLAGS)]
    top_children_abs_pdgid = abs(top_children.pdgId)

    top_direct_children = tops.children
    top_direct_children = top_direct_children[top_direct_children.hasFlags(["fromHardProcess"])]
    top_direct_children_abs_pdgid = abs(top_direct_children.pdgId)

    top_direct_wbosons = ak.firsts(
        top_direct_children[top_direct_children_abs_pdgid == W_PDGID], axis=2
    )
    top_wbosons = ak.firsts(top_children[top_children_abs_pdgid == W_PDGID], axis=2)
    top_bquarks = ak.firsts(top_direct_children[top_direct_children_abs_pdgid == PDGID.b], axis=2)
    top_bquarks_lastcopy = ak.firsts(top_children[top_children_abs_pdgid == PDGID.b], axis=2)

    # For W decay products we need the immediate daughters, not the later same-flavor descendants.
    top_w_children = top_wbosons.children
    top_w_children = top_w_children[top_w_children.hasFlags(["fromHardProcess"])]

    return top_direct_wbosons, top_wbosons, top_bquarks, top_bquarks_lastcopy, top_w_children


def _top_w_decay_mode_masks(w_child_pdg_ids: ak.Array):
    """
    Classify each top-decay W by the flavors of its direct children.
    """

    w_child_abs_pdgid = abs(w_child_pdg_ids)
    has_two_children = ak.num(w_child_pdg_ids, axis=2) == 2
    has_lepton = ak.any(
        (w_child_abs_pdgid == PDGID.e)
        | (w_child_abs_pdgid == PDGID.mu)
        | (w_child_abs_pdgid == PDGID.tau),
        axis=2,
    )
    has_neutrino = ak.any(
        (w_child_abs_pdgid == PDGID.ve)
        | (w_child_abs_pdgid == PDGID.vmu)
        | (w_child_abs_pdgid == PDGID.vtau),
        axis=2,
    )
    is_hadronic_w = has_two_children & ak.all(w_child_abs_pdgid <= PDGID.b, axis=2)
    is_leptonic_w = has_two_children & has_lepton & has_neutrino

    return is_hadronic_w, is_leptonic_w


def _sorted_quark_flavors(q1_pdgid: ak.Array, q2_pdgid: ak.Array):
    """Return the unordered absolute flavor pair for two W-daughter quarks."""

    q1_abs = ak.fill_none(abs(q1_pdgid), 0)
    q2_abs = ak.fill_none(abs(q2_pdgid), 0)
    q_lo = ak.where(q1_abs <= q2_abs, q1_abs, q2_abs)
    q_hi = ak.where(q1_abs <= q2_abs, q2_abs, q1_abs)

    return q_lo, q_hi


def _w_flavor_tag_arrays(q1_pdgid: ak.Array, q2_pdgid: ak.Array):
    """Build the six exclusive hadronic-W flavor tags from GenQ1/GenQ2 PDG IDs."""

    q_lo, q_hi = _sorted_quark_flavors(q1_pdgid, q2_pdgid)

    return {
        branch: ((q_lo == lo) & (q_hi == hi)).to_numpy()
        for branch, (lo, hi) in W_TO_QUARK_PAIR_TAGS.items()
    }


def _supplement_zero_quark_masses(quark_masses: ak.Array, quark_pdg_ids: ak.Array):
    """Overwrite zero quark masses with the requested PDG-based flavor masses."""

    quark_abs_pdgid = ak.fill_none(abs(quark_pdg_ids), 0)
    pdg_masses = ak.where(
        quark_abs_pdgid == PDGID.b,
        4.18,
        ak.where(quark_abs_pdgid == PDGID.c, 1.27, 0.0),
    )
    zero_mass = ak.fill_none(quark_masses == 0, False)

    return ak.where(zero_mass, pdg_masses, quark_masses)


def _pdg_lepton_masses(lepton_pdg_ids: ak.Array):
    """Map charged-lepton PDG IDs to their PDG masses in GeV."""

    lepton_abs_pdgid = ak.fill_none(abs(lepton_pdg_ids), 0)
    is_charged_lepton = (
        (lepton_abs_pdgid == PDGID.e)
        | (lepton_abs_pdgid == PDGID.mu)
        | (lepton_abs_pdgid == PDGID.tau)
    )
    masses = ak.where(
        lepton_abs_pdgid == PDGID.e,
        0.00051099895,
        ak.where(
            lepton_abs_pdgid == PDGID.mu,
            0.1056583755,
            ak.where(lepton_abs_pdgid == PDGID.tau, 1.77686, 0.0),
        ),
    )

    return ak.mask(masses, is_charged_lepton)


def _pdg_lepton_charges(lepton_pdg_ids: ak.Array):
    """Convert charged-lepton PDG IDs to reconstructed charges (+1/-1)."""

    lepton_abs_pdgid = ak.fill_none(abs(lepton_pdg_ids), 0)
    is_charged_lepton = (
        (lepton_abs_pdgid == PDGID.e)
        | (lepton_abs_pdgid == PDGID.mu)
        | (lepton_abs_pdgid == PDGID.tau)
    )
    charges = ak.where(lepton_pdg_ids < 0, 1, -1)

    return ak.mask(charges, is_charged_lepton)


def _pdg_lepton_flavors(lepton_pdg_ids: ak.Array):
    """Return the absolute charged-lepton PDG ID as a flavor code."""

    lepton_abs_pdgid = ak.fill_none(abs(lepton_pdg_ids), 0)
    is_charged_lepton = (
        (lepton_abs_pdgid == PDGID.e)
        | (lepton_abs_pdgid == PDGID.mu)
        | (lepton_abs_pdgid == PDGID.tau)
    )

    return ak.mask(lepton_abs_pdgid, is_charged_lepton)


def _direct_w_decay_products(wboson: ak.Array):
    """Return the direct charged-lepton and neutrino daughters of a terminal W."""

    w_children = wboson.children
    w_children = w_children[w_children.hasFlags(["fromHardProcess"])]
    w_child_abs_pdgid = abs(w_children.pdgId)
    charged_lepton = ak.firsts(
        w_children[
            (w_child_abs_pdgid == PDGID.e)
            | (w_child_abs_pdgid == PDGID.mu)
            | (w_child_abs_pdgid == PDGID.tau)
        ],
        axis=1,
    )
    neutrino = ak.firsts(
        w_children[
            (w_child_abs_pdgid == PDGID.ve)
            | (w_child_abs_pdgid == PDGID.vmu)
            | (w_child_abs_pdgid == PDGID.vtau)
        ],
        axis=1,
    )

    return w_children, charged_lepton, neutrino


def gen_selection_Vcb(
    events: NanoEventsArray,
    jets: JetArray,
    electrons: LepArray,
    muons: LepArray,
    selection_args: list,  # noqa: ARG001
    skim_vars: dict,
):
    """
    Get gen variables for Vcb analysis.
    """

    # Find generator-level top quarks from the hard process (last copy) and
    # save their kinematic variables for downstream skims.
    tops = events.GenPart[
        (abs(events.GenPart.pdgId) == TOP_PDGID) * events.GenPart.hasFlags(GEN_FLAGS)
    ]
    GenTopVars = {f"GenTop{key}": tops[var].to_numpy() for (var, key) in skim_vars.items()}

    # Keep the top->W/b hierarchy intact so hadronic/leptonic roles are assigned by construction.
    (
        top_direct_wbosons,
        top_wbosons,
        top_bquarks,
        _top_bquarks_lastcopy,
        top_w_children,
    ) = _top_decay_products(tops)

    # Legacy top-slot aliases (GenTopW0/1, GenTopDecayW0/1) are retired.
    GenTopVars = {
        **GenTopVars,
    }

    # Identify the hadronic and leptonic W explicitly from their direct children.
    hadronic_w_mask, leptonic_w_mask = _top_w_decay_mode_masks(top_w_children.pdgId)
    hadronic_w = ak.firsts(top_wbosons[hadronic_w_mask], axis=1)
    leptonic_w = ak.firsts(top_wbosons[leptonic_w_mask], axis=1)
    hadronic_top_decay_w = ak.firsts(top_direct_wbosons[hadronic_w_mask], axis=1)
    leptonic_top_decay_w = ak.firsts(top_direct_wbosons[leptonic_w_mask], axis=1)
    hadronic_top_b = ak.firsts(top_bquarks[hadronic_w_mask], axis=1)
    leptonic_top_b = ak.firsts(top_bquarks[leptonic_w_mask], axis=1)
    top_indices = ak.local_index(top_wbosons, axis=1)
    hadronic_top_idx = ak.firsts(top_indices[hadronic_w_mask], axis=1)
    leptonic_top_idx = ak.firsts(top_indices[leptonic_w_mask], axis=1)

    # Direct children of the identified hadronic and leptonic W bosons.
    hadronic_w_children, _, _ = _direct_w_decay_products(hadronic_w)
    hadronic_quarks = hadronic_w_children[abs(hadronic_w_children.pdgId) <= PDGID.b]
    _, leptonic_w_lepton, leptonic_w_neutrino = _direct_w_decay_products(leptonic_w)
    leptonic_w_lepton_mass = _pdg_lepton_masses(leptonic_w_lepton.pdgId)
    leptonic_w_lepton_charge = _pdg_lepton_charges(leptonic_w_lepton.pdgId)
    leptonic_w_lepton_flavor = _pdg_lepton_flavors(leptonic_w_lepton.pdgId)
    leptonic_w_neutrino_mass = leptonic_w_neutrino.pt * 0.0

    # GenQ1/GenQ2 are now the two direct quark daughters of the hadronic W by construction.
    qs_2 = ak.firsts(hadronic_quarks[:, 0:1], axis=1)
    qs_3 = ak.firsts(hadronic_quarks[:, 1:2], axis=1)
    q1_mass = _supplement_zero_quark_masses(qs_2.mass, qs_2.pdgId)
    q2_mass = _supplement_zero_quark_masses(qs_3.mass, qs_3.pdgId)

    # Keep the explicit hadronic/leptonic top-b aliases for analysis and matching.
    ls_0 = leptonic_w_lepton
    hadronic_top_b_mass = _supplement_zero_quark_masses(hadronic_top_b.mass, hadronic_top_b.pdgId)
    leptonic_top_b_mass = _supplement_zero_quark_masses(leptonic_top_b.mass, leptonic_top_b.pdgId)

    # Save explicit hadronic/leptonic gen-level decay products.
    # Legacy top-slot aliases (GenTopB0/1) are retired.
    GenTopBVars = {
        **_single_particle_vars("GenHadW", hadronic_w, skim_vars),
        **_single_particle_vars("GenLepW", leptonic_w, skim_vars),
        **_single_particle_vars(
            "GenWLepton", leptonic_w_lepton, skim_vars, overrides={"mass": leptonic_w_lepton_mass}
        ),
        **_single_particle_vars(
            "GenWNeutrino",
            leptonic_w_neutrino,
            skim_vars,
            overrides={"mass": leptonic_w_neutrino_mass},
        ),
        **_single_particle_vars("GenHadTopDecayW", hadronic_top_decay_w, skim_vars),
        **_single_particle_vars("GenLepTopDecayW", leptonic_top_decay_w, skim_vars),
        **_single_particle_vars(
            "GenHadTopB", hadronic_top_b, skim_vars, overrides={"mass": hadronic_top_b_mass}
        ),
        **_single_particle_vars(
            "GenLepTopB", leptonic_top_b, skim_vars, overrides={"mass": leptonic_top_b_mass}
        ),
        "GenWLeptonCharge": _single_value_to_numpy(leptonic_w_lepton_charge, dtype=np.int32),
        "GenWLeptonFlavor": _single_value_to_numpy(
            leptonic_w_lepton_flavor, dtype=np.uint32, pad_value=0
        ),
        # Original top-slot indices (0/1) retained for cross-referencing hadronic/leptonic branches.
        "GenHadTopIdx": _single_value_to_numpy(hadronic_top_idx, dtype=np.int32),
        "GenLepTopIdx": _single_value_to_numpy(leptonic_top_idx, dtype=np.int32),
    }

    # Six exclusive hadronic-W flavor tags are derived from the unordered |GenQ1PdgId|/|GenQ2PdgId| pair.
    q1_flavor, q2_flavor = _sorted_quark_flavors(qs_2.pdgId, qs_3.pdgId)
    w_to_bc_mask = (q1_flavor == PDGID.c) & (q2_flavor == PDGID.b)
    w_bc_b = ak.firsts(hadronic_quarks[abs(hadronic_quarks.pdgId) == PDGID.b], axis=1)
    w_bc_b = ak.mask(w_bc_b, w_to_bc_mask)
    w_bc_b_mass = _supplement_zero_quark_masses(w_bc_b.mass, w_bc_b.pdgId)
    GenWbcVars = {
        **_single_particle_vars("GenWb", w_bc_b, skim_vars, overrides={"mass": w_bc_b_mass}),
        **_w_flavor_tag_arrays(qs_2.pdgId, qs_3.pdgId),
    }

    # Save the two hadronic-W quark daughters with flavor-supplemented masses.
    GenQVars = {
        **_single_particle_vars("GenQ1", qs_2, skim_vars, overrides={"mass": q1_mass}),
        **_single_particle_vars("GenQ2", qs_3, skim_vars, overrides={"mass": q2_mass}),
        "GenQ1PdgId": _single_value_to_numpy(qs_2.pdgId, dtype=np.int32),
        "GenQ2PdgId": _single_value_to_numpy(qs_3.pdgId, dtype=np.int32),
    }

    # Tag reconstructed objects by proximity to the explicit gen objects saved above.
    jets["MatchedHadB"] = ak.values_astype(jets.delta_r(hadronic_top_b) < 0.4, np.int32)
    jets["MatchedLepB"] = ak.values_astype(jets.delta_r(leptonic_top_b) < 0.4, np.int32)
    electrons["NumlMatchedTop1"] = ak.values_astype(electrons.delta_r(ls_0) < 0.2, np.int32)
    muons["NumlMatchedTop1"] = ak.values_astype(muons.delta_r(ls_0) < 0.2, np.int32)
    jets["MatchedHadQ1"] = ak.values_astype(jets.delta_r(qs_2) < 0.4, np.int32)
    jets["MatchedHadQ2"] = ak.values_astype(jets.delta_r(qs_3) < 0.4, np.int32)

    # Pad per-jet/per-lepton match info to fixed sizes for the output format.
    num_jets = 8
    JetVars = {
        f"ak4{var}_": pad_val(jets[var], num_jets, axis=1)
        for var in [
            # "TopMatch",
            # "TopMatchIndex",
            "MatchedHadB",
            "MatchedLepB",
            "MatchedHadQ1",
            "MatchedHadQ2",
        ]
    }
    num_lep = 3
    EleVars = {
        f"electrons{var}": pad_val(electrons[var], num_lep, axis=1)
        for var in [
            "NumlMatchedTop1",
        ]
    }

    # Same lepton matching info for muons (kept for consistency, even if unused elsewhere).
    MuonVars = {
        f"muons{var}": pad_val(muons[var], num_lep, axis=1)
        for var in [
            "NumlMatchedTop1",
        ]
    }

    # Return all gen-level and matching-related variables for the Vcb analysis.
    return {**GenTopVars, **JetVars, **EleVars, **MuonVars, **GenTopBVars, **GenWbcVars, **GenQVars}
