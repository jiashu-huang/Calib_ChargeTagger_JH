"""One-at-a-time 2024 object variations and their stable output identifiers.

The full JES basis is transcribed from Case I, Simple!A2:A28; its mapping to
Summer24 V5 is recorded in docs/jes-2024-full-source-manifest.json. Historical
2016/2017 correlation percentages do not scale these single-year variations.
"""

from __future__ import annotations

from dataclasses import dataclass

from .muon_ss import TOTAL_VARIATIONS
from .muon_ss import VARIATION_IDS as MUON_VARIATION_IDS

# This ordering defines persisted IDs; changing it requires a schema migration.
JES_SOURCES = (
    "AbsoluteMPFBias", "AbsoluteScale", "AbsoluteStat", "FlavorQCD", "Fragmentation",
    "PileUpDataMC", "PileUpPtBB", "PileUpPtEC1", "PileUpPtEC2", "PileUpPtHF", "PileUpPtRef",
    "RelativeFSR", "RelativeJEREC1", "RelativeJEREC2", "RelativeJERHF", "RelativePtBB",
    "RelativePtEC1", "RelativePtEC2", "RelativePtHF", "RelativeBal", "RelativeSample",
    "RelativeStatEC", "RelativeStatFSR", "RelativeStatHF", "SinglePionECAL",
    "SinglePionHCAL", "TimePtEta",
)
JES_VARIATIONS = tuple(f"jes_{source}{direction}" for source in JES_SOURCES
                       for direction in ("Up", "Down"))
JER_VARIATIONS = ("jerUp", "jerDown")
ELECTRON_VARIATIONS = tuple(f"electron_{source}{direction}" for source in ("scale", "smear")
                            for direction in ("Up", "Down"))
MUON_VARIATIONS = tuple(f"muon_{name}" for name in TOTAL_VARIATIONS)
ALL_PASSES = ("nominal", *JES_VARIATIONS, *JER_VARIATIONS, *ELECTRON_VARIATIONS, *MUON_VARIATIONS)
COMPONENT_PASSES = tuple(f"muon_{name}" for name in MUON_VARIATION_IDS
                        if name != "nominal" and name not in TOTAL_VARIATIONS)
VARIATION_IDS = {name: index for index, name in enumerate((*ALL_PASSES, *COMPONENT_PASSES))}
GROUPS = {
    "all": ALL_PASSES,
    "jets": ("nominal", *JES_VARIATIONS, *JER_VARIATIONS),
    "jes": ("nominal", *JES_VARIATIONS),
    "jer": ("nominal", *JER_VARIATIONS),
    "electron": ("nominal", *ELECTRON_VARIATIONS),
    "muon": ("nominal", *MUON_VARIATIONS),
}


@dataclass(frozen=True)
class Variation:
    name: str

    def __post_init__(self):
        if self.name not in VARIATION_IDS:
            raise ValueError(f"Unknown kinematic variation {self.name!r}")

    @property
    def identifier(self) -> int:
        return VARIATION_IDS[self.name]

    @property
    def muon(self) -> str:
        return self.name.removeprefix("muon_") if self.name.startswith("muon_") else "nominal"

    @property
    def electron(self) -> str:
        return self.name.removeprefix("electron_") if self.name.startswith("electron_") else "nominal"

    @property
    def jet_options(self) -> dict:
        if self.name.startswith("jes_"):
            direction = 1 if self.name.endswith("Up") else -1
            suffix = "Up" if direction == 1 else "Down"
            return {"jes_source": self.name[4:-len(suffix)], "jes_direction": direction}
        if self.name in JER_VARIATIONS:
            return {"jer_direction": 1 if self.name.endswith("Up") else -1}
        return {}

    def validate_sample(self, year: str, is_data: bool = False) -> None:
        if self.name != "nominal" and (year != "2024" or is_data):
            raise ValueError("Kinematic variations require 2024 MC")


def resolve_variation(kinematic: str = "nominal", muon: str = "nominal") -> Variation:
    """Keep the legacy muon option, while rejecting simultaneous nuisances."""
    if muon not in MUON_VARIATION_IDS:
        raise ValueError(f"Unknown muon pT variation {muon!r}")
    if kinematic != "nominal" and muon != "nominal":
        raise ValueError("Use only one of --kinematic-variation and --muon-pt-variation")
    return Variation(f"muon_{muon}" if muon != "nominal" else kinematic)


def variation_from_id(identifier: int) -> Variation:
    for name, value in VARIATION_IDS.items():
        if value == identifier:
            return Variation(name)
    raise ValueError(f"Unknown KinematicVariation identifier {identifier}")
