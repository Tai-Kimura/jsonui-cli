"""`document_tools_path` reports both when it fails and when it works.

Reported 2026-09-08 by a consumer lane: three faces carry a
`document_tools_path` pointing at a directory that does not exist, and the
helper skipped silently — so "the setting had no effect" was indistinguishable
from "the setting was honoured". The working branch was silent too, which is
the more dangerous half: a working copy displaces the installed distribution
while `jui --version` keeps naming the distribution.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "jui_tools"))

from jui_cli.core.config_manager import ConfigManager  # noqa: E402


def _project(tmp_path, dtp):
    cfg = {"project_name": "P", "platforms": {}}
    if dtp is not None:
        cfg["document_tools_path"] = str(dtp)
    (tmp_path / "jui.config.json").write_text(json.dumps(cfg), encoding="utf-8")
    import os
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        mgr = ConfigManager()
        mgr.load()
        return mgr
    finally:
        os.chdir(cwd)


class TestBothOutcomesAreReported:
    def test_set_but_missing_says_the_setting_had_no_effect(self, tmp_path):
        mgr = _project(tmp_path, tmp_path / "nope")
        notes = mgr.document_tools_path_notes()
        assert len(notes) == 1
        assert "does not exist" in notes[0]
        assert "had no effect" in notes[0]

    def test_set_and_present_says_the_distribution_was_displaced(self, tmp_path):
        """⚠️ The half a lane called the dangerous one: it WORKS, and the
        working copy silently replaces the installed distribution."""
        real = tmp_path / "document_tools"
        real.mkdir()
        mgr = _project(tmp_path, real)
        notes = mgr.document_tools_path_notes()
        assert len(notes) == 1
        assert "prepended to sys.path" in notes[0]
        assert "not the" in notes[0] and "installed distribution" in notes[0]

    def test_the_control_unset_says_nothing(self, tmp_path):
        mgr = _project(tmp_path, None)
        assert mgr.document_tools_path_notes() == []

    def test_the_two_branches_do_not_print_the_same_thing(self, tmp_path):
        """🚨 The arm that makes the fix mean something. Reporting BOTH with
        one message would restore the confusion: the point is that the reader
        can tell which branch ran."""
        (tmp_path / "a").mkdir()
        missing = _project(tmp_path / "a", (tmp_path / "a" / "nope"))
        (tmp_path / "b" / "document_tools").mkdir(parents=True)
        present = _project(tmp_path / "b", tmp_path / "b" / "document_tools")
        m = missing.document_tools_path_notes()[0]
        p = present.document_tools_path_notes()[0]
        assert m != p

    def test_it_writes_to_stderr_and_returns_none(self, tmp_path, capsys):
        mgr = _project(tmp_path, tmp_path / "nope")
        assert mgr.ensure_document_tools_importable() is None
        cap = capsys.readouterr()
        assert "NOTE [tools]" in cap.err
        assert "NOTE [tools]" not in cap.out

    def test_the_helper_still_inserts_the_path_when_it_exists(self, tmp_path):
        """⚠️ Regression arm: adding the report must not change the behaviour."""
        real = tmp_path / "document_tools"
        real.mkdir()
        mgr = _project(tmp_path, real)
        before = list(sys.path)
        try:
            mgr.ensure_document_tools_importable()
            assert str(real) == sys.path[0]
        finally:
            sys.path[:] = before
