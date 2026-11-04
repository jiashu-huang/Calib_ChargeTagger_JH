"""Close C1 only after all three frozen B0 source campaigns pass finalization.

This collects input-readiness evidence. It neither mixes physics yields nor
creates training splits, fits feature normalization or starts training.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ttbb_b0_campaign import SAMPLE_DATASETS, check_gate, now, read_config, sha, write_json


def check_source(sample, campaign):
    config = read_config(campaign)
    check_gate(campaign)
    if config.get("sample") != sample or config["dataset"] != SAMPLE_DATASETS[sample]:
        raise ValueError("Source label does not match its frozen campaign")
    completion = json.loads((campaign / "completion.json").read_text())
    if (completion["state"] != "complete" or completion.get("training_started") is not False
            or completion["processor_commit"] != config["processor_commit"]
            or completion["files"] != config["files"]
            or completion["input_events"] != config["input_events"]):
        raise ValueError("Source campaign has incomplete or inconsistent coverage")
    certificate = json.loads((campaign / config["truth_certificate"]).read_text())
    certified = certificate["summary"][sample]
    if (certified["verified_files"] != completion["files"]
            or certified["verified_events"] != completion["input_events"]):
        raise ValueError("B0 population differs from certified C1 truth coverage")
    for name, key in (("publication.json", "publication_sha256"),
                      ("input-audit.json", "input_audit_sha256"),
                      ("input-audit.txt", "input_audit_text_sha256")):
        if sha(campaign / name) != completion[key]:
            raise ValueError(f"Completed source artifact changed: {name}")
    expected_reports = {"matching-report/matching_summary.txt", "matching-report/matching_summary.json"}
    expected_reports |= {f"matching-report/{population}_masses.{extension}"
                         for population in ("fully_matched", "hadronic_top_matched")
                         for extension in ("png", "pdf")}
    if set(completion["matching_artifacts"]) != expected_reports:
        raise ValueError("Completed matching report is incomplete")
    for name, digest in completion["matching_artifacts"].items():
        if sha(campaign / name) != digest:
            raise ValueError("Completed matching report changed")
    audit = json.loads((campaign / "input-audit.json").read_text())
    pilot = json.loads((campaign / "pilot-result.json").read_text())
    if audit["schema_sha256"] != pilot["b0"]["schema_sha256"]:
        raise ValueError("Population feature/truth schema differs from its pilot")
    counts = audit["counts"]
    matching = completion["matching_counts"]
    if (counts["selected"] != completion["selected_events"]
            or counts["fully_matched"] != matching["fully_matched"]
            or counts["hadronic_top_matched"] != matching["hadronic_top_matched"]
            or counts["assignment_eligible"] != matching["b0_assignment_eligible"]):
        raise ValueError("Population and matching report counts disagree")
    required = ("W_label_valid", "extra_b_label_valid", "assignment_eligible",
                "reco_b_jets_count_valid", "gen_b_jets_count_valid")
    if any(counts.get(name, 0) <= 0 for name in required):
        raise ValueError("A required C1 supervision or b-jet population has no usable events")
    return {"campaign": str(campaign), "dataset": config["dataset"],
            "processor_commit": config["processor_commit"],
            "truth_certificate_sha256": config["truth_certificate_sha256"],
            "completion_sha256": sha(campaign / "completion.json"),
            "input_audit_sha256": completion["input_audit_sha256"],
            "publication_sha256": completion["publication_sha256"],
            "schema_sha256": audit["schema_sha256"],
            "input_files": completion["files"], "input_events": completion["input_events"],
            "counts": counts, "histograms": audit["histograms"],
            "population_report": str(campaign / "input-audit.txt"),
            "matching_report": completion["matching_summary"]}


def collect(campaigns):
    if set(campaigns) != set(SAMPLE_DATASETS):
        raise ValueError("C1 needs exactly TT2Q, TTCB and TTBB")
    if len({Path(path).resolve() for path in campaigns.values()}) != 3:
        raise ValueError("Source campaigns must be distinct")
    sources = {sample: check_source(sample, Path(campaigns[sample]).resolve())
               for sample in ("TT2Q", "TTCB", "TTBB")}
    for key in ("processor_commit", "truth_certificate_sha256", "schema_sha256"):
        if len({source[key] for source in sources.values()}) != 1:
            raise ValueError(f"C1 source campaigns disagree on {key}")
    first = sources["TT2Q"]
    return {"state": "complete", "checkpoint": "C1 input readiness",
            "completed_utc": now(), "processor_commit": first["processor_commit"],
            "schema_sha256": first["schema_sha256"], "sources": sources,
            "scope": "Separate source populations; no inclusive/dedicated yield combination",
            "truth": "W decay, exact extra-b quarks, total reco/gen b jets and per-reco-jet hadron flavour",
            "deferred": ["Additional-b-jet origin categories and physics-yield source partition",
                         "Protected lineage splits, HDF5 assembly and train-only normalization (C2)",
                         "Training and model performance validation"],
            "training_started": False}


def render(result):
    lines = ["C1 input readiness: COMPLETE", "All counts below are unweighted.",
             "MC sources remain separate; this is not a combined physics yield.", ""]
    for sample, source in result["sources"].items():
        lines += [sample, f"  Input files: {source['input_files']:,}",
                  f"  Input events: {source['input_events']:,}"]
        lines += [f"  {key}: {value:,}" for key, value in source["counts"].items()]
        bins = source["histograms"]["extra_b_quarks"]
        lines += ["  Exact extra-b-quark support: "
                  + ", ".join(f"{key}={value:,}" for key, value in sorted(bins.items(), key=lambda p: int(p[0]))),
                  f"  Population audit: {source['population_report']}",
                  f"  Matching report: {source['matching_report']}", ""]
    lines += ["Deferred:", *["  " + item for item in result["deferred"]]]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", nargs=2, action="append", required=True,
                        metavar=("SAMPLE", "DIRECTORY"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if len(args.campaign) != 3:
        parser.error("Supply exactly one --campaign for TT2Q, TTCB and TTBB")
    result = collect(dict(args.campaign))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    text = args.output_dir / "c1-input-readiness.txt"
    text.write_text(render(result))
    result["text_sha256"] = sha(text)
    write_json(args.output_dir / "c1-input-readiness.json", result)
    print(text.read_text())


if __name__ == "__main__":
    main()
