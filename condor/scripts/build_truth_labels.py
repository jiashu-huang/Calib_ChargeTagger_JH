#!/usr/bin/env python3
"""Build small extra-b label sidecars from native MiniAOD/GenTruth, using FWLite.

Run in a CMSSW runtime. Supply one or more --pair NANO EDM pairs. No CMSSW
conversion is run. Every source entry and event identity must match before a
manifest is published. Existing outputs are never overwritten.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from hashlib import sha256
from pathlib import Path

import numpy as np

# CMSSW uses its own Python; importing vcb.processors would import Coffea too.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from vcb.truth import TRUTH_LABEL_VERSION, count_extra_b_quarks


def build_pair(nano_path, edm_path, output_dir):
    import ROOT
    from DataFormats.FWLite import Events, Handle

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
    finally:
        nano.Close()
    output = output_dir / f"{uuid}.npz"
    if output.exists():
        raise FileExistsError(output)
    count = np.full(size, -1, dtype=np.int32)
    status = np.full(size, -1, dtype=np.int32)
    handle = Handle("std::vector<reco::GenParticle>")
    read = 0
    print(f"Reading native generator truth: {edm_path}", flush=True)
    for index, event in enumerate(Events(edm_path)):
        if index >= size:
            raise ValueError("Native truth has more entries than NanoAOD")
        aux = event.eventAuxiliary()
        identity = (int(aux.run()), int(aux.luminosityBlock()), int(aux.event()))
        expected = tuple(int(identities[k][index]) for k in ("run", "luminosityBlock", "event"))
        if identity != expected:
            raise ValueError(f"Native/NanoAOD identity mismatch at entry {index}")
        event.getByLabel("prunedGenParticles", handle)
        if not handle.isValid():
            raise ValueError("Missing prunedGenParticles in native truth")
        particles = handle.product()
        pdg, states, flags, mothers = [], [], [], []
        for particle in particles:
            pdg.append(int(particle.pdgId()))
            states.append(int(particle.status()))
            f = particle.statusFlags()
            flags.append((int(f.isFirstCopy()) << 12) | (int(f.isLastCopy()) << 13)
                         | (int(f.isHardProcess()) << 7) | (int(f.fromHardProcess()) << 8))
            refs = [particle.motherRef(j) for j in range(particle.numberOfMothers())]
            # References must target this collection, not just an in-range key.
            mothers.append([
                int(ref.key()) if ref.isAvailable() and 0 <= int(ref.key()) < len(particles)
                and ROOT.addressof(ref.get()) == ROOT.addressof(particles[int(ref.key())])
                else -1 for ref in refs
            ])
        count[index], status[index] = count_extra_b_quarks(
            pdg, states, flags, mothers, complete_record=True,
        )
        read += 1
    if read != size:
        raise ValueError(f"Native/NanoAOD entry count mismatch: {read} != {size}")
    # Exclusive creation also guards concurrent builders targeting the same UUID.
    with output.open("xb") as stream:
        np.savez_compressed(stream, **identities, count=count, status=status,
                            nano_uuid=np.array(uuid), schema_version=np.array(TRUTH_LABEL_VERSION))
    return {
        "nano_file": nano_path, "native_truth": edm_path, "nano_uuid": uuid,
        "entries": size, "labels": output.name,
        "sha256": sha256(output.read_bytes()).hexdigest(),
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
