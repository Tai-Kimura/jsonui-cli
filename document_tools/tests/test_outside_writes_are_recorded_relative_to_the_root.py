"""Regression: manifest-outside-output-directories-are-absolute-so-a-tracked-file-becomes-machine-specific.

`summary.run.outsideOutput.directories` holds absolute paths, and the manifest
is a tracked file on some faces: a clone at another path rewrites every line
on its first run, so a face could not keep the doc run's record in history.
`directoriesRelative` names the same directories relative to the manifest's
root — `../docs/<face>/…` on a split tree, which is the record's point, not a
defect — and is byte-identical across clones. A directory outside the
repository that holds the root has no relative form and is None.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "document_tools"))

from jsonui_doc_cli.test_doc import generator as gen  # noqa: E402


def _manifest(root: Path) -> dict:
    return json.loads((root / ".jsonui-cli" / "generation-manifest.json").read_text(encoding="utf-8"))


def _site(base: Path) -> Path:
    """A split tree inside its own git repository: docs under the parent."""
    site = base / "site"
    for name in ("a", "b"):
        (site / name).mkdir(parents=True)
        (site / "docs" / name / "screens" / "html").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(site)], check=True)
    return site


def _record(site: Path, monkeypatch, extra_outside: list | None = None) -> None:
    out = site / "out"
    out.mkdir(exist_ok=True)
    monkeypatch.setattr(gen, "get_written_pages", lambda: set())
    wa = str((site / "docs" / "a" / "screens" / "html").resolve())
    wb = str((site / "docs" / "b" / "screens" / "html").resolve())
    outside = {"directories": [wa, wb] + (extra_outside or []), "gitTrackedDirectories": {}, "uncheckable": []}
    gen._record_generation_manifest(
        out, [{"app": "a", "root": site / "a", "docs": site / "docs" / "a"},
              {"app": "b", "root": site / "b", "docs": site / "docs" / "b"}], [], outside)


def test_the_relative_form_walks_up_out_of_the_root_on_a_split_tree(tmp_path, monkeypatch):
    site = _site(tmp_path)
    _record(site, monkeypatch)
    a = _manifest(site / "a")["summary"]["run"]["outsideOutput"]
    b = _manifest(site / "b")["summary"]["run"]["outsideOutput"]
    assert a["directoriesRelative"] == ["../docs/a/screens/html"]
    assert b["directoriesRelative"] == ["../docs/b/screens/html"]
    # The scope has its relative twin: the root itself, then the --app docs.
    assert a["scopeRelative"] == [".", "../docs/a"]
    assert b["scopeRelative"] == [".", "../docs/b"]
    # The absolute form stays, so nothing that reads it today breaks.
    assert a["directories"] == [str((site / "docs" / "a" / "screens" / "html").resolve())]


def test_two_clones_at_different_paths_write_the_same_relative_list(tmp_path, monkeypatch):
    """The arm this ticket exists for: the absolute lists differ, the relative lists do not."""
    first = _site(tmp_path / "one")
    _record(first, monkeypatch)
    second_base = tmp_path / "elsewhere" / "deeper"
    second_base.mkdir(parents=True)
    shutil.copytree(first, second_base / "site", symlinks=True)
    second = second_base / "site"
    for name in ("a", "b"):
        shutil.rmtree(second / name / ".jsonui-cli")
    _record(second, monkeypatch)
    for name in ("a", "b"):
        o1 = _manifest(first / name)["summary"]["run"]["outsideOutput"]
        o2 = _manifest(second / name)["summary"]["run"]["outsideOutput"]
        assert o1["directories"] != o2["directories"]
        assert json.dumps(o1["directoriesRelative"]) == json.dumps(o2["directoriesRelative"])
        assert o1["scopeRelative"] == o2["scopeRelative"] and o1["scope"] != o2["scope"]


def test_a_directory_outside_the_repository_has_no_relative_form(tmp_path, monkeypatch):
    """A face whose --app docs live in ANOTHER repository: the directory is in
    scope, keeps its absolute form, and the relative slot says None because
    no path relative to this root can name a file outside this repository."""
    site = _site(tmp_path)
    elsewhere = tmp_path / "other-repo" / "docs" / "a"
    (elsewhere / "screens" / "html").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(tmp_path / "other-repo")], check=True)
    out = site / "out"; out.mkdir()
    monkeypatch.setattr(gen, "get_written_pages", lambda: set())
    inside = str((site / "docs" / "a" / "screens" / "html").resolve())
    far = str((elsewhere / "screens" / "html").resolve())
    gen._record_generation_manifest(
        out, [{"app": "a", "root": site / "a", "docs": elsewhere}], [],
        {"directories": [inside, far], "gitTrackedDirectories": {}, "uncheckable": []})
    block = _manifest(site / "a")["summary"]["run"]["outsideOutput"]
    # `inside` is under neither the root nor the (foreign) docs: out of scope.
    assert block["directories"] == [far]
    assert block["directoriesRelative"] == [None]
    assert block["scopeRelative"] == [".", None]


def test_the_relative_form_round_trips_through_json_with_the_parent_segments(tmp_path, monkeypatch):
    site = _site(tmp_path)
    _record(site, monkeypatch)
    raw = (site / "a" / ".jsonui-cli" / "generation-manifest.json").read_text(encoding="utf-8")
    assert '"../docs/a/screens/html"' in raw
