"""A build whose output dirs do not exist yet: a new worktree with gitignored outputs.

Reported on a real face: 342 gitignored layout copies, `outsideDeclaredRoots` 342 on the first build and 0 on the
second, every entry stamped again. Two things with two answers:

- The count was wrong. The first scan cannot name a directory the run has yet to create, so files under declared
  roots read as outside them. The roots are read again after the run.
- The stamps are right, and these arms hold them. The file was absent when the run began, so this run wrote it; the
  entry has no hash that could say the bytes are an older version's.

🔻 THE CONTROL: the same run without the roots from the scan after the build counts every file outside.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "jui_tools"))

from jui_cli.commands import build_cmd  # noqa: E402
from jui_cli.core import generation_manifest as gm  # noqa: E402
from jui_cli.core.config_manager import ConfigManager  # noqa: E402

LAYOUT = "web/src/Layouts/home.json"
GENERATED = "web/src/generated/Home.js"


def _project(root: Path) -> Path:
    """A project as a new worktree has it: the sources and the record, none of the gitignored outputs."""
    (root / "docs" / "screens" / "layouts").mkdir(parents=True)
    (root / "docs" / "screens" / "layouts" / "home.json").write_text('{"type": "View"}\n', encoding="utf-8")
    (root / "web").mkdir()
    (root / "jui.config.json").write_text(json.dumps({
        "layouts_directory": "docs/screens/layouts",
        "platforms": {"web": {"root": "web", "layoutsDir": "src/Layouts"}},
    }), encoding="utf-8")
    return root


def _manifest(root: Path) -> dict:
    return json.loads((root / ".jsonui-cli" / "generation-manifest.json").read_text(encoding="utf-8"))


def _write_old_record(root: Path) -> None:
    (root / ".jsonui-cli").mkdir()
    entry = {"version": "0.0.1", "generatedAt": "2020-01-01T00:00:00Z", "generatedBy": "jui build"}
    (root / ".jsonui-cli" / "generation-manifest.json").write_text(json.dumps({
        "schemaVersion": 1, "files": {LAYOUT: dict(entry), GENERATED: dict(entry)}}), encoding="utf-8")


@pytest.fixture
def build(monkeypatch, tmp_path):
    """The real cmd_build; only the platform tool is a stand-in, which writes its output as rjui does."""
    root = _project(tmp_path)
    monkeypatch.chdir(root)
    tool = {"ok": True}

    def run_tool(_cmd, cwd):
        out = Path(cwd) / "src" / "generated"
        out.mkdir(parents=True, exist_ok=True)
        (out / "Home.js").write_text("// @generated\n", encoding="utf-8")
        return tool["ok"]

    monkeypatch.setattr(build_cmd, "_run_tool", run_tool)

    def run(ok=True):
        tool["ok"] = ok
        with contextlib.redirect_stdout(io.StringIO()):
            return build_cmd.cmd_build(argparse.Namespace(
                clean=False, ios_only=False, android_only=False, web_only=False, platform=None,
                lint_strings=False, normalize_layouts=None))

    return root, run


class TestTheScanRoots:
    def test_nothing_is_outside_on_the_first_build(self, build):
        root, run = build
        assert run() == 0
        made = _manifest(root)
        assert LAYOUT in made["files"] and GENERATED in made["files"]
        assert made["summary"]["scan"]["outsideDeclaredRoots"] == 0

    def test_the_first_build_declares_what_the_second_does(self, build):
        root, run = build
        assert run() == 0
        first = _manifest(root)["summary"]["scan"]["roots"]
        assert run() == 0
        assert first == _manifest(root)["summary"]["scan"]["roots"]
        assert "web/src/Layouts" in first and "web/src/generated" in first

    def test_a_build_that_stops_says_the_same(self, build):
        root, run = build
        assert run(ok=False) == 1
        assert _manifest(root)["summary"]["scan"]["outsideDeclaredRoots"] == 0

    def test_the_control_without_the_second_scan_counts_them_outside(self, tmp_path):
        root = _project(tmp_path)
        cfg = ConfigManager(root / "jui.config.json")
        run = gm.GenerationRun(project_root=root, version="t")
        before, before_roots = build_cmd._generated_scan(cfg)
        run.observe(before, roots=before_roots)
        layout = root / LAYOUT
        layout.parent.mkdir(parents=True)
        layout.write_text('{"type": "View"}\n', encoding="utf-8")
        paths, roots = build_cmd._generated_scan(cfg)
        run.written(paths)
        assert len(run.outside_roots) == 1
        run.add_roots(roots)
        run.written(paths)
        assert run.outside_roots == []

    def test_a_file_under_no_root_is_still_outside(self, tmp_path):
        """The count keeps its job: it says a file came from a source the config does not declare."""
        root = _project(tmp_path)
        cfg = ConfigManager(root / "jui.config.json")
        run = gm.GenerationRun(project_root=root, version="t")
        before, before_roots = build_cmd._generated_scan(cfg)
        run.observe(before, roots=before_roots)
        stray = root / "elsewhere" / "Stray.js"
        stray.parent.mkdir()
        stray.write_text("// @generated\n", encoding="utf-8")
        build_cmd._record_generation(cfg, run, [stray], roots=[root / "web" / "src" / "generated"])
        assert run.outside_roots == ["elsewhere/Stray.js"]

    def test_a_root_gone_after_the_run_stays_declared(self, tmp_path):
        run = gm.GenerationRun(project_root=tmp_path, version="t")
        run.observe([], roots=[tmp_path / "a"])
        run.add_roots([tmp_path / "b"])
        assert run.roots == ("a", "b")


class TestTheStampsAreTheContract:
    """Not an accident to fix: what the record says of a file this run wrote."""

    def test_an_absent_file_is_stamped_with_the_version_that_wrote_it(self, build):
        root, run = build
        _write_old_record(root)
        assert run() == 0
        files = _manifest(root)["files"]
        for key in (LAYOUT, GENERATED):
            assert files[key]["version"] != "0.0.1"
            assert files[key]["generatedAt"] != "2020-01-01T00:00:00Z"

    def test_the_second_build_moves_nothing(self, build):
        root, run = build
        _write_old_record(root)
        assert run() == 0
        first = _manifest(root)["files"]
        assert run() == 0
        assert _manifest(root)["files"] == first

    def test_a_file_that_was_there_keeps_its_entry(self, build):
        root, run = build
        assert run() == 0
        entries = _manifest(root)
        entries["files"][LAYOUT]["version"] = "0.0.1"
        (root / ".jsonui-cli" / "generation-manifest.json").write_text(json.dumps(entries), encoding="utf-8")
        assert run() == 0
        assert _manifest(root)["files"][LAYOUT]["version"] == "0.0.1"

    def test_a_pinned_clock_leaves_the_record_alone_at_the_same_version(self, build, monkeypatch):
        root, run = build
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "1790000000")
        assert run() == 0
        first = _manifest(root)["files"]
        os.remove(root / LAYOUT)
        os.remove(root / GENERATED)
        assert run() == 0
        assert _manifest(root)["files"] == first
