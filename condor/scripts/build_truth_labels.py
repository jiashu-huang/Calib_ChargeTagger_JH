#!/usr/bin/env python3
"""Build small extra-b label sidecars from native MiniAOD/GenTruth, using FWLite.

Run in a CMSSW runtime. Supply one or more --pair NANO EDM pairs. No CMSSW
conversion is run. Within each declared source pair, require a one-to-one event
identity mapping and matching retained generator content before publishing.
Output labels follow NanoAOD entry order. Existing outputs are never overwritten.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from hashlib import sha256
from math import isclose
from pathlib import Path

import numpy as np

# CMSSW uses its own Python; importing vcb.processors would import Coffea too.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from vcb.truth import (
    FIRST_COPY,
    FROM_HARD_PROCESS,
    HARD_PROCESS,
    LAST_COPY,
    TRUTH_LABEL_VERSION,
    count_extra_b_quarks,
)

GENERATOR_FIELDS = ("pdgId", "status", "statusFlags", "pt", "eta", "phi")
COPY_FLAGS = FIRST_COPY | LAST_COPY | HARD_PROCESS | FROM_HARD_PROCESS


def nano_identity_index(identities):
    """Index one source file only; reject ambiguous or malformed event identities."""
    fields = ("run", "luminosityBlock", "event")
    size = len(identities["event"])
    if any(identities[key].shape != (size,) or identities[key].dtype.kind not in "iu"
           for key in fields):
        raise ValueError("Malformed NanoAOD event identity columns")
    lookup = {}
    for index in range(size):
        identity = tuple(int(identities[key][index]) for key in fields)
        if identity in lookup:
            raise ValueError(f"Duplicate NanoAOD event identity in one source file: {identity}")
        lookup[identity] = index
    return lookup


def aligned_nano_entry(identity, lookup, seen):
    """Resolve a unique native event within the same declared file pair."""
    if identity not in lookup:
        raise ValueError(f"Native event identity absent from its paired NanoAOD: {identity}")
    index = lookup[identity]
    if seen[index]:
        raise ValueError(f"Duplicate native event identity in one source file: {identity}")
    seen[index] = True
    return index


def check_generator_particles(nano_particles, native_particles):
    """Check the retained NanoAOD particles against the native ordered record.

    Event numbers can repeat in independent MC samples. Check generator content
    before binding native labels to a NanoAOD UUID. The NanoAOD pruner preserves
    input order but removes particles; its pt/eta/phi retain 8 mantissa bits.
    This is a consistency check, not a replacement for conversion provenance.
    """
    native = iter(native_particles)
    seen = False
    for index, expected in enumerate(nano_particles):
        seen = True
        for actual in native:
            if (expected[0] == actual[0] and expected[1] == actual[1]
                    and (int(expected[2]) & COPY_FLAGS) == (int(actual[2]) & COPY_FLAGS)
                    and all(isclose(expected[k], actual[k], rel_tol=2**-8, abs_tol=1e-7)
                            for k in (3, 4, 5))):
                break
        else:
            raise ValueError(f"Native/NanoAOD generator content mismatch at particle {index}")
    if not seen:
        raise ValueError("Empty NanoAOD generator record cannot certify a native pair")


def build_pair(nano_path, edm_path, output_dir):
    import ROOT

    ROOT.gROOT.SetBatch(True)
    print(f"Reading NanoAOD identity: {nano_path}", flush=True)
    nano = ROOT.TFile.Open(nano_path)
    if not nano or nano.IsZombie() or not nano.Get("Events"):
        raise ValueError(f"Cannot read NanoAOD Events tree: {nano_path}")
    try:
        uuid = str(nano.GetUUID().AsString())
        size = int(nano.Get("Events").GetEntries())
        identities = {key: np.asarray(value).copy() for key, value in
                      ROOT.RDataFrame(nano.Get("Events")).AsNumpy(
                          ["run", "luminosityBlock", "event"]).items()}
    except Exception:
        nano.Close()
        raise
    try:
        return _build_pair(nano_path, edm_path, output_dir, nano, uuid, size, identities)
    finally:
        nano.Close()


def _build_pair(nano_path, edm_path, output_dir, nano, uuid, size, identities):
    import ROOT
    from DataFormats.FWLite import Events, Handle

    tree = nano.Get("Events")
    branches = [f"GenPart_{field}" for field in GENERATOR_FIELDS]
    if any(not tree.GetBranch(branch) for branch in branches):
        raise ValueError("Missing NanoAOD generator branches needed to verify the native pair")
    tree.SetBranchStatus("*", False)
    for branch in branches:
        tree.SetBranchStatus(branch, True)
        # ROOT leaf arrays need their count leaf enabled as well.
        leaf = tree.GetBranch(branch).GetListOfLeaves().At(0)
        if leaf.GetLeafCount():
            tree.SetBranchStatus(leaf.GetLeafCount().GetName(), True)
    output = output_dir / f"{uuid}.npz"
    if output.exists():
        raise FileExistsError(output)
    count = np.full(size, -1, dtype=np.int32)
    status = np.full(size, -1, dtype=np.int32)
    lookup = nano_identity_index(identities)
    seen = np.zeros(size, dtype=bool)
    handle = Handle("std::vector<reco::GenParticle>")
    read = 0
    reordered = 0
    print(f"Reading native generator truth: {edm_path}", flush=True)
    for native_index, event in enumerate(Events(edm_path)):
        if native_index >= size:
            raise ValueError("Native truth has more entries than NanoAOD")
        aux = event.eventAuxiliary()
        identity = (int(aux.run()), int(aux.luminosityBlock()), int(aux.event()))
        index = aligned_nano_entry(identity, lookup, seen)
        reordered += index != native_index
        event.getByLabel("prunedGenParticles", handle)
        if not handle.isValid():
            raise ValueError("Missing prunedGenParticles in native truth")
        particles = handle.product()
        pdg, states, flags, mothers, native_particles = [], [], [], [], []
        for particle in particles:
            pdg.append(int(particle.pdgId()))
            states.append(int(particle.status()))
            f = particle.statusFlags()
            flags.append((int(f.isFirstCopy()) << 12) | (int(f.isLastCopy()) << 13)
                         | (int(f.isHardProcess()) << 7) | (int(f.fromHardProcess()) << 8))
            native_particles.append((pdg[-1], states[-1], flags[-1],
                                     float(particle.pt()), float(particle.eta()),
                                     float(particle.phi())))
            refs = [particle.motherRef(j) for j in range(particle.numberOfMothers())]
            # References must target this collection, not just an in-range key.
            mothers.append([
                int(ref.key()) if ref.isAvailable() and 0 <= int(ref.key()) < len(particles)
                and ROOT.addressof(ref.get()) == ROOT.addressof(particles[int(ref.key())])
                else -1 for ref in refs
            ])
        if tree.GetEntry(index) <= 0:
            raise ValueError(f"Cannot read NanoAOD generator record at entry {index}")
        columns = [getattr(tree, branch) for branch in branches]
        if any(len(column) != len(columns[0]) for column in columns):
            raise ValueError(f"Malformed NanoAOD generator columns at entry {index}")
        try:
            check_generator_particles(
                (tuple(column[j] for column in columns) for j in range(len(columns[0]))),
                native_particles,
            )
        except ValueError as error:
            raise ValueError(f"{error}; entry {index}, event {identity}") from error
        count[index], status[index] = count_extra_b_quarks(
            pdg, states, flags, mothers, complete_record=True,
        )
        read += 1
    if read != size or not seen.all():
        raise ValueError(f"Native/NanoAOD entry count mismatch: {read} != {size}")
    # Exclusive creation also guards concurrent builders targeting the same UUID.
    with output.open("xb") as stream:
        np.savez_compressed(stream, **identities, count=count, status=status,
                            nano_uuid=np.array(uuid), schema_version=np.array(TRUTH_LABEL_VERSION))
    return {
        "nano_file": nano_path, "native_truth": edm_path, "nano_uuid": uuid,
        "entries": size, "labels": output.name,
        "sha256": sha256(output.read_bytes()).hexdigest(),
        "pair_validation": "unique within-file event identity alignment and ordered retained GenPart content (8-bit precision)",
        "native_entries_reordered": reordered,
        "counts": {str(k): v for k, v in sorted(Counter(count.tolist()).items())},
        "statuses": {str(k): v for k, v in sorted(Counter(status.tolist()).items())},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", nargs=2, action="append", required=True, metavar=("NANO", "EDM"))
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = args.output_dir / "manifest.json"
    if manifest.exists():
        raise FileExistsError(manifest)
    records = [build_pair(nano, edm, args.output_dir) for nano, edm in args.pair]
    if len({r["nano_uuid"] for r in records}) != len(records):
        raise ValueError("Duplicate NanoAOD source in requested pairs")
    with manifest.open("x") as stream:
        json.dump({
            "schema_version": TRUTH_LABEL_VERSION,
            "source": "Pythia8 MiniAOD prunedGenParticles; all b quarks retained",
            "producer_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "definition_sha256": sha256(
                (Path(__file__).resolve().parents[2] / "src/vcb/truth.py").read_bytes()
            ).hexdigest(),
            "files": records,
        }, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"manifest": str(manifest), "files": records}, indent=2))


if __name__ == "__main__":
    main()
