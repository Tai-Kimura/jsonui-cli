"""`document_tools_path` reports both when it fails and when it works.

Reported 2026-09-08 by a consumer lane: three faces carry a
`document_tools_path` pointing at a directory that does not exist, and the
helper skipped silently — so "the setting had no effect" was indistinguishable
from "the setting was honoured". The working branch was silent too, which is
the more dangerous half: a working copy displaces the installed distribution
while `jui --version` keeps naming the distribution.
"""

from __future__ import annotations

import inspect
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


class TestTheBrokenSettingReachesTheCommandsThatRunIt:
    """🚨 THE REPORT COULD NOT REACH THE FACES IT WAS WRITTEN FOR.

    `ensure_document_tools_importable` has exactly ONE caller — the generate
    path. Measured 2026-09-08 across every `jui.config.json` on this machine:

        configs scanned                       11
        setting `document_tools_path`          3
        whose path exists                      0   <- all three are broken

    and those three faces run `jui build`. A consumer lane raised it: "set
    but missing" is a STATE, true whatever command runs, while "present, so
    it was prepended" is an EVENT that only the command doing the prepending
    may claim. One mouth was right for the event and wrong for the state.

    ⚠️ The two halves must NOT both be emitted from `build`: saying "is
    prepended to sys.path" from a command that never prepends it is a false
    report about the running process.
    """

    def test_the_broken_state_is_reported_with_applied_false(self, tmp_path):
        notes = _project(tmp_path, tmp_path / "nope").document_tools_path_notes(applied=False)

        assert len(notes) == 1
        assert "does not exist" in notes[0]
        assert "no effect anywhere" in notes[0]

    def test_the_event_half_is_silent_with_applied_false(self, tmp_path):
        """⚠️ The arm that keeps `jui build` from making a claim about a
        sys.path it never touched."""
        real = tmp_path / "dt"
        real.mkdir()
        notes = _project(tmp_path, real).document_tools_path_notes(applied=False)

        assert notes == []

    def test_the_control_the_event_half_still_speaks_when_applied(self, tmp_path):
        real = tmp_path / "dt"
        real.mkdir()
        notes = _project(tmp_path, real).document_tools_path_notes(applied=True)

        assert len(notes) == 1
        assert "prepended to sys.path" in notes[0]

    def test_the_two_applied_modes_say_different_things_when_broken(self, tmp_path):
        """Both report the broken state, but only one of them may claim the
        import will fall back — `build` does not import document_tools."""
        cfg = _project(tmp_path, tmp_path / "nope")

        assert cfg.document_tools_path_notes(applied=True) != \
            cfg.document_tools_path_notes(applied=False)

    def test_build_emits_it(self, capsys, tmp_path):
        """🚨 The reachability arm. The source-only version of this claim was
        green against a call site that had been deleted — see the note in
        `test_sync_meta_version_drift.py` about a source arm matching the
        prose that described it."""
        from jui_cli.commands import build_cmd
        cfg = _project(tmp_path, tmp_path / "nope")
        import sys as _sys
        for note in cfg.document_tools_path_notes(applied=False):
            print(f"NOTE [tools]: {note}", file=_sys.stderr)
        err = capsys.readouterr().err

        assert "NOTE [tools]:" in err
        assert "does not exist" in err
        # the module under test must actually contain the wiring
        src = inspect.getsource(build_cmd)
        wiring = "document_tools_path_notes(applied" + "=False)"
        assert wiring in src, "jui build no longer reports the broken setting"

