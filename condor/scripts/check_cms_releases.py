#!/usr/bin/env python3
"""
Check the bundled CMS correction files against the official releases on CVMFS.

The skimmer reads committed copies of the POG correction files, so nothing
tells us when CMS publishes a newer one. Run this before every production, and
about monthly otherwise:

    micromamba run -n ttbar python condor/scripts/check_cms_releases.py

It answers two questions from `cms_releases.json`, next to this script:

1. Does each bundled file still have the content of its official `latest/`
   copy? The same test covers "tracked" official files that we do not bundle
   but depend on, such as the certified-luminosity list.
2. Has a group published a dated release newer than the one last acknowledged?
   This includes groups whose files are not bundled (b-tagging, certification).

Content is compared by SHA-256 of the *decompressed* bytes: two gzip files of
the same payload can differ in their headers.

Exit code: 0 up to date, 1 action needed, 2 not checked (CVMFS unavailable).
A release is acknowledged by raising `acknowledged` in the manifest after its
`changes.md` has been read and the decision recorded; see condor/README.md.
This checks published files only. It cannot check the written POG
recommendations, which need a CERN login.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = Path(__file__).with_name("cms_releases.json")
RELEASE_NAME = re.compile(r"\d{4}-\d{2}-\d{2}")
HEADLINE = re.compile(r"Changes:\s*\S+\s*\((.*)\)\s*$")
EXIT_UP_TO_DATE, EXIT_ACTION_NEEDED, EXIT_NOT_CHECKED = 0, 1, 2


def content_sha256(path: Path) -> str:
    """SHA-256 of the decompressed content, so gzip headers do not matter."""
    raw = path.read_bytes()
    return hashlib.sha256(gzip.decompress(raw) if path.suffix == ".gz" else raw).hexdigest()


def release_names(group_dir: Path) -> list[str]:
    """Dated release folders, oldest first; `latest/` and side folders are ignored."""
    return sorted(p.name for p in group_dir.iterdir() if RELEASE_NAME.fullmatch(p.name))


def release_headline(release_dir: Path) -> str:
    """First line of the release's `changes.md`, without the date it repeats."""
    notes = release_dir / "changes.md"
    if not notes.is_file():
        return "(no changes.md)"
    for line in notes.read_text(errors="replace").splitlines():
        text = line.strip().lstrip("#").strip()
        if text:
            match = HEADLINE.match(text)
            return match.group(1) if match else text
    return "(empty changes.md)"


def compare_file(label: str, expected_sha256: str, official: Path) -> dict:
    if not official.is_file():
        status = "MISSING"
    elif content_sha256(official) == expected_sha256:
        status = "MATCH"
    else:
        status = "DIFFERS"
    return {"file": label, "official": str(official), "status": status}


def check_group(entry: dict, cat_root: Path) -> dict:
    group_dir = cat_root / entry["dir"]
    result = {"dir": entry["dir"], "acknowledged": entry["acknowledged"], "newest": None, "new": []}
    if not group_dir.is_dir():
        return {**result, "status": "MISSING"}
    names = release_names(group_dir)
    result["newest"] = names[-1] if names else None
    if entry["acknowledged"] not in names:
        # A mistyped date would otherwise silence every later release.
        return {**result, "status": "UNKNOWN"}
    result["new"] = [
        {"release": name, "headline": release_headline(group_dir / name)}
        for name in names
        if name > entry["acknowledged"]
    ]
    return {**result, "status": "NEW" if result["new"] else "OK"}


def check(manifest: dict, cat_root: Path, repo_root: Path = REPO_ROOT) -> dict:
    files = [
        compare_file(
            entry["path"], content_sha256(repo_root / entry["path"]), cat_root / entry["source"]
        )
        for entry in manifest["bundled"]
    ]
    files += [
        compare_file(entry["source"], entry["sha256"], cat_root / entry["source"])
        for entry in manifest.get("tracked", [])
    ]
    groups = [check_group(entry, cat_root) for entry in manifest["groups"]]
    return {
        "checked_utc": datetime.now(UTC).strftime("%Y-%m-%d %H:%M"),
        "cat_root": str(cat_root),
        "files": files,
        "groups": groups,
        "unchecked": manifest.get("unchecked", []),
        "action_needed": any(f["status"] != "MATCH" for f in files)
        or any(g["status"] != "OK" for g in groups),
    }


def render(report: dict) -> str:
    lines = [
        f"CMS release check, {report['checked_utc']} UTC",
        f"Official tree: {report['cat_root']}",
        "",
        "Bundled and tracked files against the official copy",
    ]
    lines += [f"  {f['status']:<8} {f['file']}" for f in report["files"]]
    lines += [f"  {'SKIPPED':<8} {u['path']}: {u['why']}" for u in report["unchecked"]]
    lines += ["", "Releases newer than the last acknowledged one"]
    for group in report["groups"]:
        lines.append(
            f"  {group['status']:<8} {group['dir']}: "
            f"acknowledged {group['acknowledged']}, newest {group['newest']}"
        )
        lines += [f"{'':11}{new['release']}  {new['headline']}" for new in group["new"]]
    changed = sum(f["status"] != "MATCH" for f in report["files"])
    pending = sum(len(g["new"]) for g in report["groups"])
    broken = sum(g["status"] in ("MISSING", "UNKNOWN") for g in report["groups"])
    if report["action_needed"]:
        verdict = (
            f"ACTION NEEDED ({changed} file(s) not matching, {pending} release(s) to review, "
            f"{broken} group(s) unreadable)"
        )
    else:
        verdict = "UP TO DATE"
    return "\n".join([*lines, "", f"VERDICT: {verdict}"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check bundled CMS correction files against the official CVMFS releases."
    )
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--cat-root", type=Path, help="override the manifest's CVMFS root")
    parser.add_argument("--json", type=Path, help="also write the report as JSON")
    args = parser.parse_args(argv)

    manifest = json.loads(args.manifest.read_text())
    cat_root = args.cat_root or Path(manifest["cat_root"])
    if not cat_root.is_dir():
        # Never report "up to date" for a check that could not run.
        print(f"VERDICT: NOT CHECKED ({cat_root} is not available)")
        return EXIT_NOT_CHECKED
    report = check(manifest, cat_root)
    print(render(report))
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n")
    return EXIT_ACTION_NEEDED if report["action_needed"] else EXIT_UP_TO_DATE


if __name__ == "__main__":
    raise SystemExit(main())
