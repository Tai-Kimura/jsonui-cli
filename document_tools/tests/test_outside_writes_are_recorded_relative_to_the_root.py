"""Regression: manifest-outside-output-directories-are-absolute-so-a-tracked-file-becomes-machine-specific.

`summary.run.outsideOutput.directories` holds absolute paths, and the manifest
is a tracked file on some faces: a clone at another path rewrites every line
on its first run, so a face could not keep the doc run's record in history.
`directoriesRelative` names the same directories relative to the manifest's
root — `../docs/<face>/…` on a split tree, which is the record's point, not a
defect — and is byte-identical across clones.

⚠️ 2026-09-10, after 1.8.68 shipped: a directory outside the REPOSITORY used
to come back None. The face that asked for the key has its root in a
submodule and its docs in the parent repository, so it got None for every
entry and the ticket's own problem was not solved for the reporter. The
relative form is emitted now; `directoriesOutsideRepo` /`scopeOutsideRepo`
carry, index-aligned, what the None used to carry. None survives only where
no relative form exists at all.
"""

from __future__ import annotations

import json
import os
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
        # ⚠️ Assert the NON-NULL COUNT before the equality. On 2026-09-10 this
        # arm was first run against copies that were not git repositories, so
        # both sides came back [None, None, …] and the equality held on two
        # empty sets. An equality between two absences is not a measurement.
        for o in (o1, o2):
            assert sum(1 for x in o["directoriesRelative"] if x is not None) == \
                len(o["directories"]), "every directory must have a relative form"
            assert all(x is not None for x in o["scopeRelative"])
        assert json.dumps(o1["directoriesRelative"]) == json.dumps(o2["directoriesRelative"])
        assert o1["scopeRelative"] == o2["scopeRelative"] and o1["scope"] != o2["scope"]


def test_a_directory_outside_the_repository_still_gets_its_relative_form(tmp_path, monkeypatch):
    """INVERTED 2026-09-10 (was: `…_has_no_relative_form`, asserting None).

    Until 1.8.68 a directory outside the repository holding the root came
    back None, so that the record would not claim a path a clone of that
    sub-repository alone could follow. Measured on the face that asked for
    the key: its root IS a submodule and its docs live in the parent, so all
    four entries were None and the ticket — a tracked manifest full of
    machine-specific absolute paths — was not solved for the reporter. The
    relative form is strictly better than the absolute one for that purpose,
    so it is emitted; `directoriesOutsideRepo` says, index-aligned, which
    entries leave the repository."""
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
    # The relative form exists and leads there: no None, and it climbs out.
    assert block["directoriesRelative"] == [
        os.path.relpath(far, str((site / "a").resolve()))]
    assert block["directoriesRelative"][0].startswith("..")
    assert block["directoriesRelative"][0] is not None
    # …and the block says the entry leaves the repository, index-aligned.
    assert block["directoriesOutsideRepo"] == [True]
    assert block["scopeRelative"][0] == "." and block["scopeRelative"][1].startswith("..")
    assert block["scopeOutsideRepo"] == [False, True]


def test_a_submodule_root_whose_docs_are_in_the_parent_gets_relative_forms(tmp_path, monkeypatch):
    """The reporting face's own shape: manifest root is its OWN repository,
    `--app` docs are in the parent's. This is the case 1.8.68 shipped as
    four Nones. The two trees must really be two repositories — a plain
    subdirectory does not reproduce it — so the arm measures that first."""
    parent = tmp_path / "parent"
    (parent / "docs" / "a" / "screens" / "html").mkdir(parents=True)
    (parent / "a").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(parent)], check=True)
    subprocess.run(["git", "init", "-q", str(parent / "a")], check=True)

    # The premise of this arm, stated where it is used: two repositories.
    def _top(d):
        return subprocess.run(["git", "-C", str(d), "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, check=True).stdout.strip()
    assert Path(_top(parent / "a")).resolve() == (parent / "a").resolve()
    assert Path(_top(parent / "docs" / "a")).resolve() == parent.resolve()
    assert _top(parent / "a") != _top(parent / "docs" / "a")

    out = parent / "out"; out.mkdir()
    monkeypatch.setattr(gen, "get_written_pages", lambda: set())
    wa = str((parent / "docs" / "a" / "screens" / "html").resolve())
    gen._record_generation_manifest(
        out, [{"app": "a", "root": parent / "a", "docs": parent / "docs" / "a"}], [],
        {"directories": [wa], "gitTrackedDirectories": {}, "uncheckable": []})
    block = _manifest(parent / "a")["summary"]["run"]["outsideOutput"]
    # 1.8.68 produced [None] here. The whole point of the ticket.
    assert block["directoriesRelative"] == ["../docs/a/screens/html"]
    assert block["scopeRelative"] == [".", "../docs/a"]
    # …and the record still says these leave the sub-repository.
    assert block["directoriesOutsideRepo"] == [True]
    assert block["scopeOutsideRepo"] == [False, True]


def test_a_single_repository_tree_reports_nothing_outside_the_repository(tmp_path, monkeypatch):
    """The control for the two arms above: same split tree, ONE repository.
    Without this, `directoriesOutsideRepo == [True]` could be a constant."""
    site = _site(tmp_path)
    _record(site, monkeypatch)
    block = _manifest(site / "a")["summary"]["run"]["outsideOutput"]
    assert block["directoriesRelative"] == ["../docs/a/screens/html"]
    assert block["directoriesOutsideRepo"] == [False]
    assert block["scopeOutsideRepo"] == [False, False]


def test_the_relative_form_round_trips_through_json_with_the_parent_segments(tmp_path, monkeypatch):
    site = _site(tmp_path)
    _record(site, monkeypatch)
    raw = (site / "a" / ".jsonui-cli" / "generation-manifest.json").read_text(encoding="utf-8")
    assert '"../docs/a/screens/html"' in raw
