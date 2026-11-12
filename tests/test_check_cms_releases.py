"""Exercise the CMS release check on small fake release trees; CVMFS is not needed."""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "condor/scripts/check_cms_releases.py"
GROUP = "POG/Campaign"
SOURCE = f"{GROUP}/latest/sf.json.gz"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("check_cms_releases", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _gz(path, payload, mtime=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=mtime) as handle:
        handle.write(payload)
    return path


def _release(cat, name, payload):
    _gz(cat / GROUP / name / "sf.json.gz", payload)
    (cat / GROUP / name / "changes.md").write_text(
        f"## Changes: {name} (Release {name})\n\nDetails.\n"
    )


def _setup(tmp_path, *, latest=b"v1"):
    """One bundled file, one acknowledged release, and a `latest/` copy."""
    cat, repo = tmp_path / "cat", tmp_path / "repo"
    _release(cat, "2026-01-01", b"v1")
    # A different gzip header from the bundled copy, as on CVMFS.
    _gz(cat / SOURCE, latest, mtime=12345)
    _gz(repo / "sf.json.gz", b"v1")
    manifest = {
        "cat_root": str(cat),
        "bundled": [{"path": "sf.json.gz", "source": SOURCE}],
        "groups": [{"dir": GROUP, "acknowledged": "2026-01-01"}],
    }
    return manifest, cat, repo


def test_same_content_in_different_gzip_bytes_is_up_to_date(tool, tmp_path):
    manifest, cat, repo = _setup(tmp_path)
    assert (repo / "sf.json.gz").read_bytes() != (cat / SOURCE).read_bytes()

    report = tool.check(manifest, cat, repo)

    assert [f["status"] for f in report["files"]] == ["MATCH"]
    assert [g["status"] for g in report["groups"]] == ["OK"]
    assert not report["action_needed"]
    assert tool.render(report).endswith("VERDICT: UP TO DATE")


def test_changed_official_content_is_reported(tool, tmp_path):
    manifest, cat, repo = _setup(tmp_path, latest=b"v2")

    report = tool.check(manifest, cat, repo)

    assert report["files"][0]["status"] == "DIFFERS"
    assert report["action_needed"]


def test_removed_official_file_is_reported(tool, tmp_path):
    manifest, cat, repo = _setup(tmp_path)
    (cat / SOURCE).unlink()

    report = tool.check(manifest, cat, repo)

    assert report["files"][0]["status"] == "MISSING"
    assert report["action_needed"]


def test_new_release_is_listed_with_its_headline(tool, tmp_path):
    manifest, cat, repo = _setup(tmp_path)
    # `latest/` still holds the old content: only the release list reveals it.
    _release(cat, "2026-02-01", b"v2")

    report = tool.check(manifest, cat, repo)
    group = report["groups"][0]

    assert report["files"][0]["status"] == "MATCH"
    assert group["status"] == "NEW"
    assert group["newest"] == "2026-02-01"
    assert group["new"] == [{"release": "2026-02-01", "headline": "Release 2026-02-01"}]
    assert report["action_needed"]
    assert "1 release(s) to review" in tool.render(report)


def test_side_folders_are_not_releases(tool, tmp_path):
    manifest, cat, repo = _setup(tmp_path)
    (cat / GROUP / "newFormats").mkdir()
    (cat / GROUP / "2026-03-01-draft").mkdir()

    report = tool.check(manifest, cat, repo)

    assert report["groups"][0]["status"] == "OK"
    assert not report["action_needed"]


def test_release_without_notes_still_counts(tool, tmp_path):
    manifest, cat, repo = _setup(tmp_path)
    (cat / GROUP / "2026-02-01").mkdir()

    report = tool.check(manifest, cat, repo)

    assert report["groups"][0]["new"] == [
        {"release": "2026-02-01", "headline": "(no changes.md)"}
    ]


@pytest.mark.parametrize("acknowledged", ["2026-13-01", "2025-01-01"])
def test_acknowledged_release_must_exist(tool, tmp_path, acknowledged):
    # A mistyped later date would otherwise hide every future release.
    manifest, cat, repo = _setup(tmp_path)
    manifest["groups"][0]["acknowledged"] = acknowledged

    report = tool.check(manifest, cat, repo)

    assert report["groups"][0]["status"] == "UNKNOWN"
    assert report["action_needed"]


def test_missing_group_is_reported(tool, tmp_path):
    manifest, cat, repo = _setup(tmp_path)
    manifest["groups"].append({"dir": "POG/Gone", "acknowledged": "2026-01-01"})

    report = tool.check(manifest, cat, repo)

    assert report["groups"][1]["status"] == "MISSING"
    assert report["action_needed"]


def test_tracked_file_is_compared_with_its_recorded_hash(tool, tmp_path):
    manifest, cat, repo = _setup(tmp_path)
    golden = cat / "DC/latest/golden.json"
    golden.parent.mkdir(parents=True)
    golden.write_text('{"1": [[1, 10]]}')
    manifest["tracked"] = [
        {"source": "DC/latest/golden.json", "sha256": hashlib.sha256(golden.read_bytes()).hexdigest()}
    ]
    assert tool.check(manifest, cat, repo)["files"][1]["status"] == "MATCH"

    golden.write_text('{"1": [[1, 9]]}')

    report = tool.check(manifest, cat, repo)
    assert report["files"][1]["status"] == "DIFFERS"
    assert report["action_needed"]


def test_cli_exit_codes_and_json_report(tool, tmp_path, capsys):
    manifest, cat, repo = _setup(tmp_path)
    # An absolute bundled path keeps the CLI independent of the real checkout.
    manifest["bundled"][0]["path"] = str(repo / "sf.json.gz")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    saved = tmp_path / "report.json"

    assert tool.main(["--manifest", str(manifest_path), "--json", str(saved)]) == 0
    assert "VERDICT: UP TO DATE" in capsys.readouterr().out
    assert json.loads(saved.read_text())["action_needed"] is False

    _release(cat, "2026-02-01", b"v2")
    assert tool.main(["--manifest", str(manifest_path)]) == 1
    assert "VERDICT: ACTION NEEDED" in capsys.readouterr().out


def test_unavailable_tree_is_not_reported_as_up_to_date(tool, tmp_path, capsys):
    manifest, _, _ = _setup(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    code = tool.main(["--manifest", str(manifest_path), "--cat-root", str(tmp_path / "absent")])

    assert code == 2
    assert "VERDICT: NOT CHECKED" in capsys.readouterr().out


def test_manifest_covers_every_bundled_payload(tool):
    manifest = json.loads(tool.MANIFEST.read_text())
    bundled = {entry["path"] for entry in manifest["bundled"]}
    unchecked = {entry["path"] for entry in manifest["unchecked"]}
    on_disk = {
        str(path.relative_to(REPO))
        for folder in ("src/vcb/corrections", "src/boostedhh/corrections")
        for path in (REPO / folder).glob("*.gz")
    }

    # A newly bundled payload must be either checked or deliberately excluded.
    assert bundled | unchecked == on_disk
    assert not bundled & unchecked

    # Every bundled file's release folder is watched for newer releases.
    watched = {group["dir"] for group in manifest["groups"]}
    for entry in manifest["bundled"]:
        group, marker, _ = entry["source"].partition("/latest/")
        assert marker, entry["source"]
        assert group in watched, entry["source"]
    assert all(tool.RELEASE_NAME.fullmatch(group["acknowledged"]) for group in manifest["groups"])
