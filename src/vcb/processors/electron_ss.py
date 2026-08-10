"""
Electron energy scale and smearing (EGM ``electronSS_EtDependent``) for 2024.

Unlike the lepton efficiency scale factors in ``lepton_sf.py``, this is not a
weight -- it rewrites the electron's ``pt``. ECAL measures electron energy from
scintillation light in PbWO4 crystals, and two things simulation does not know
about spoil that measurement:

  * **Scale.** The crystals lose transparency under irradiation over the year,
    and the laser-monitoring corrections do not fully undo it. Real electrons
    therefore come out with a slightly wrong energy, depending on run, where in
    ECAL the shower landed (supercluster eta), how much of the energy arrived
    as bremsstrahlung (r9) and the readout gain of the seed crystal.
  * **Resolution.** Simulated showers are cleaner than real ones, so the MC
    peak is too narrow.

EGM's prescription, and what this module does:

    data:  pt *= Scale("scale", run, ScEta, r9, pt, seedGain)
    MC:    pt *= Normal(1, rho),  rho = SmearAndSyst("smear", pt, r9, ScEta)

The scale is applied to **data only** and the smearing to **MC only** -- they
are not two halves of one correction applied everywhere. The scale's
*uncertainty* does go on MC, through ``SmearAndSyst``'s own ``scale_up`` /
``scale_down`` keys (see ``PT_VARIATIONS``); data is never varied.

Ordering. This must run *before* ``objects.good_electrons``, because the
correction moves electrons across that function's pT > 20 threshold and across
the 32 GeV trigger-matching threshold in ``objects.trig_match_sel``. Applying
it afterwards would corrupt exactly the migration it exists to describe.

"Et-dependent" and why ``compound()`` is mandatory. The scale is a chain of six
corrections, and the compound feeds the *running corrected* pT back into each
step rather than evaluating them all at the raw pT. Multiplying the six pieces
by hand is not equivalent: at pT = 72 GeV, |ScEta| = 2.3 it differs by 0.7%.
correctionlib does this internally as long as the compound is reached through
``CorrectionSet.compound[...]``.

A naming trap. Every EGM document, the jsonpog-integration payload and the
public examples call these two corrections ``EGMScale_Compound_Ele_2024`` and
``EGMSmearAndSyst_ElePTsplit_2024``. The CAT tree renamed them to ``Scale`` and
``SmearAndSyst``. They are the same objects -- verified by hashing the
correction ``data`` blocks of both payloads against each other, all eleven
match -- but code written from the EGM docs will not find them under those
names. The other four ``EGMSmearAndSyst_Ele*`` corrections in the payload are
intermediate steps of the derivation and are not the recommended smearing.

Also note the 2024 argument list dropped ``AbsScEta``, which the 2022/2023
payloads took between ``r9`` and ``pt``. A snippet copied from a 2022 analysis
silently shifts every argument by one.

Coverage. EGM states the corrections should not be used below ~20 GeV and may
be ineffective at very high pT. Every binning in the payload declares
``flow="clamp"``, so out-of-range inputs return the edge bin rather than
raising -- including run numbers before 379416 (early 2024B/C) and after
386951. Nothing is clipped here; clamping is EGM's own choice and this module
does not second-guess it.

Author: Jiashu Huang (Brown U)
"""

from __future__ import annotations

import logging
from pathlib import Path

import awkward as ak
import numpy as np

# The bundled-first loader, and the "inf"-edge shim it wraps, are shared with
# the lepton scale factors: same CAT tree, same correctionlib 2.5.0 pin, same
# need to work on a condor worker with no cvmfs. Imported rather than copied so
# the shim has one implementation. (This payload happens to spell its infinite
# edges as 9999.0 sentinels, so the shim is a no-op here -- but that is a fact
# about today's file, not a guarantee about the next release.)
from .lepton_sf import _load_correctionset
from .objects import electron_supercluster_eta

logger = logging.getLogger(__name__)

package_path = Path(__file__).parent.parent.resolve()  # src/vcb

_CAT_METADATA = "/cvmfs/cms-griddata.cern.ch/cat/metadata"
_CAMPAIGN_2024 = "Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15"

# year -> (file bundled under corrections/, cvmfs fallback path)
ELECTRON_SS_SOURCES = {
    "2024": (
        "2024_electronSS_EtDependent.json.gz",
        f"{_CAT_METADATA}/EGM/{_CAMPAIGN_2024}/latest/electronSS_EtDependent.json.gz",
    ),
}

# CAT names. See the naming trap in the module docstring before changing these.
SCALE_COMPOUND = "Scale"
SMEAR_CORRECTION = "SmearAndSyst"

# Extra per-electron fields written by `apply_electron_scale_smearing`, mapping
# field name -> the `SmearAndSyst` syst key it is built from. All four are MC
# only: `scale_up`/`scale_down` are ready-to-multiply factors carrying the
# *scale* uncertainty onto simulation, while `smear_up`/`smear_down` are
# widened resolutions that get re-drawn with the same Gaussian as the nominal,
# so the variation reflects the uncertainty rather than fresh random noise.
PT_VARIATIONS = {
    "pt_scaleUp": "scale_up",
    "pt_scaleDown": "scale_down",
    "pt_smearUp": "smear_up",
    "pt_smearDown": "smear_down",
}

_unsupported_year_warned = set()

# splitmix64 constants (Steele, Lea & Flood 2014), used to turn event
# coordinates into random numbers.
_SPLITMIX_GAMMA = np.uint64(0x9E3779B97F4A7C15)
_SPLITMIX_MIX1 = np.uint64(0xBF58476D1CE4E5B9)
_SPLITMIX_MIX2 = np.uint64(0x94D049BB133111EB)

# Offsets separating the two independent uniform streams Box-Muller needs.
# Any two distinct constants work; these are the leading hex digits of pi,
# used here for the usual nothing-up-my-sleeve reason. Written as literals
# rather than computed, so no scalar uint64 arithmetic can overflow-warn.
_STREAM_1 = np.uint64(0x243F6A8885A308D3)
_STREAM_2 = np.uint64(0x13198A2E03707344)


def get_electron_ss_correctionset(year: str):
    """The scale/smearing CorrectionSet for `year`, or None if unavailable."""
    source = ELECTRON_SS_SOURCES.get(year)
    if source is None:
        return None
    bundled, cvmfs = source
    return _load_correctionset(
        str(package_path / "corrections" / bundled), cvmfs, f"Electron S&S {year}"
    )


# -----------------------------------------------------------------------------
# Deterministic randomness
# -----------------------------------------------------------------------------


def _splitmix64(x: np.ndarray) -> np.ndarray:
    """One splitmix64 round: scramble a uint64 into a well-distributed uint64."""
    z = x + _SPLITMIX_GAMMA
    z = (z ^ (z >> np.uint64(30))) * _SPLITMIX_MIX1
    z = (z ^ (z >> np.uint64(27))) * _SPLITMIX_MIX2
    return z ^ (z >> np.uint64(31))


def _uniform(key: np.ndarray, stream: np.uint64) -> np.ndarray:
    """Uniform floats strictly inside (0, 1), one per `key`, for one stream."""
    bits = _splitmix64(key + stream)
    # Top 53 bits give a double with full mantissa precision; the +0.5 keeps the
    # result off both endpoints, so the log() in Box-Muller can never blow up.
    return ((bits >> np.uint64(11)).astype(np.float64) + 0.5) * 2.0**-53


def gaussian_from_event(
    run: np.ndarray, lumi: np.ndarray, event: np.ndarray, index: np.ndarray
) -> np.ndarray:
    """
    Standard normals keyed on (run, lumi, event, electron index).

    Seeded from the event's own coordinates rather than from a counter, so the
    smearing an electron receives is a property of that electron and nothing
    else. Re-running the skim with a different chunk size, file split or worker
    count reproduces it exactly, which a shared ``default_rng(42)`` would not --
    and which matters here because the smearing decides whether an electron
    lands above or below the pT cut, i.e. whether its event is in the skim at
    all.

    Box-Muller on two independent splitmix64 streams; pure numpy, vectorized,
    no per-object Python.
    """
    key = (
        (np.asarray(run, dtype=np.uint64) * np.uint64(0x100000000))
        ^ (np.asarray(lumi, dtype=np.uint64) * np.uint64(0x10000))
        ^ np.asarray(event, dtype=np.uint64)
        ^ (np.asarray(index, dtype=np.uint64) * np.uint64(0x9E3779B1))
    )
    u1 = _uniform(key, _STREAM_1)
    u2 = _uniform(key, _STREAM_2)
    return np.sqrt(-2.0 * np.log(u1)) * np.cos(2.0 * np.pi * u2)


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------


def apply_electron_scale_smearing(events, electrons, year: str, isData: bool):
    """
    Return `electrons` with EGM-corrected ``pt``.

    Applied to the *whole* input collection, before any selection, because the
    correction is what decides which electrons pass the pT cuts downstream.
    The original value is preserved as ``pt_raw`` so the output stays auditable
    and the correction stays reversible; on MC the four ``PT_VARIATIONS``
    fields are attached as well.

    On a missing payload, or a year with no corrections wired up, the
    collection is returned untouched (with ``pt_raw`` still set, so downstream
    field access does not depend on whether the correction ran) and a warning
    is logged -- the same failure mode as the lepton SFs: lose the correction,
    not the job.
    """
    electrons = ak.with_field(electrons, electrons.pt, "pt_raw")

    if year not in ELECTRON_SS_SOURCES:
        if year not in _unsupported_year_warned:
            _unsupported_year_warned.add(year)
            logger.warning(
                f"No electron scale/smearing wired up for year {year}; electron energies "
                "are left uncorrected. Add the campaign to ELECTRON_SS_SOURCES in "
                "vcb/processors/electron_ss.py to enable it."
            )
        return electrons

    cset = get_electron_ss_correctionset(year)
    if cset is None:
        return electrons

    counts = ak.num(electrons)
    if ak.sum(counts) == 0:
        return electrons

    flat = ak.flatten(electrons)
    pt = np.asarray(flat.pt, dtype=np.float64)
    r9 = np.asarray(flat.r9, dtype=np.float64)
    sceta = np.asarray(electron_supercluster_eta(flat), dtype=np.float64)

    if isData:
        # Data: the multiplicative scale, no smearing and no variation. `run` is
        # per-event, so it has to be broadcast down to per-electron first.
        run = np.asarray(ak.flatten(ak.broadcast_arrays(events.run, electrons.pt)[0]), np.float64)
        gain = np.asarray(flat.seedGain, dtype=np.float64)
        scale = cset.compound[SCALE_COMPOUND].evaluate("scale", run, sceta, r9, pt, gain)
        return ak.with_field(electrons, ak.unflatten(pt * scale, counts), "pt")

    # MC: smear only. One Gaussian draw per electron, reused across the
    # variations so they differ by the correction and not by the dice.
    corr = cset[SMEAR_CORRECTION]

    def per_electron(field):
        return np.asarray(ak.flatten(ak.broadcast_arrays(field, electrons.pt)[0]))

    gauss = gaussian_from_event(
        per_electron(events.run),
        per_electron(events.luminosityBlock),
        per_electron(events.event),
        np.asarray(ak.flatten(ak.local_index(electrons, axis=1)), dtype=np.int64),
    )

    rho = corr.evaluate("smear", pt, r9, sceta)
    pt_nominal = pt * (1.0 + gauss * rho)
    electrons = ak.with_field(electrons, ak.unflatten(pt_nominal, counts), "pt")

    for field, syst in PT_VARIATIONS.items():
        value = corr.evaluate(syst, pt, r9, sceta)
        # `smear_*` are widened resolutions, so they re-smear the *raw* pT with
        # the same Gaussian. `scale_*` are ready-to-multiply factors carrying an
        # uncertainty that is independent of resolution, so they ride on top of
        # the nominal smeared pT rather than replacing the smearing.
        shifted = pt * (1.0 + gauss * value) if syst.startswith("smear") else pt_nominal * value
        electrons = ak.with_field(electrons, ak.unflatten(shifted, counts), field)

    return electrons
