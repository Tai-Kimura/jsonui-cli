"""The vendored toolchain and the running one are compared by the tool.

`jui sync_tool` stamps the version it copied into
`<project>/.jsonui-cli/sync-meta.json`; the CLI running the gate knows its
own. A disagreement means the distribution arrived and the sync was never
run — the project builds with one toolchain and is validated by another.

Seven consumer faces were about to add `sync-meta.version !=
$(jsonui-test --version)` to their pretests, which is what a missing tool
feature looks like from outside: the same shell line in N projects, over
two values that both already live inside the tool.

BOTH DIRECTIONS ARE TESTED, and that is the requirement rather than a
courtesy. "Matching versions produce no warning" is equally true of a check
that has been deleted, so the silent arm proves nothing on its own.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.validation.toolchain import (
    SYNC_META_RELPATH, sync_meta_mismatches,
)


def _stamp(root: Path, platforms: dict) -> Path:
    path = root / SYNC_META_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"platforms": platforms}), encoding="utf-8")
    return path


def _web(version, tool="rjui_tools"):
    return {"web": {"tool": tool, "version": version,
                    "sourceSha": "abc", "sourceRoot": "~/.jsonui-cli"}}


class TestTheTwoArms:
    def test_a_stale_stamp_warns(self, tmp_path):
        _stamp(tmp_path, _web("1.7.38"))

        [message] = sync_meta_mismatches(tmp_path, "1.7.41")

        assert "1.7.38" in message and "1.7.41" in message
        assert "jui sync_tool" in message

    def test_a_matching_stamp_is_silent(self, tmp_path):
        """The other arm. On its own it is also satisfied by a deleted
        check, which is why it is never the only one here."""
        _stamp(tmp_path, _web("1.7.41"))

        assert sync_meta_mismatches(tmp_path, "1.7.41") == []

    def test_a_stamp_ahead_of_the_running_cli_also_warns(self, tmp_path):
        """The disagreement is what matters, not its direction — a project
        synced from a newer source than the CLI on PATH is the same split,
        reached from the other side."""
        _stamp(tmp_path, _web("1.7.41"))

        assert sync_meta_mismatches(tmp_path, "1.7.38")


class TestWhatItDoesNotReportOn:
    def test_a_project_with_no_stamp_is_silent(self, tmp_path):
        """Most projects do not vendor the tools. A gate firing on an
        optional file's absence would be reporting on all of them."""
        assert sync_meta_mismatches(tmp_path, "1.7.41") == []

    def test_an_unreadable_stamp_is_silent(self, tmp_path):
        path = tmp_path / SYNC_META_RELPATH
        path.parent.mkdir(parents=True)
        path.write_text("{ not json", encoding="utf-8")

        assert sync_meta_mismatches(tmp_path, "1.7.41") == []

    def test_an_unknown_version_is_not_a_mismatch(self, tmp_path):
        """`jui sync_tool` writes `unknown` when it cannot name a version.
        Comparing against it would warn on every run of a project whose
        stamp predates versioned stamping — a different state, and not one
        `jui sync_tool` clears."""
        _stamp(tmp_path, _web("unknown"))

        assert sync_meta_mismatches(tmp_path, "1.7.41") == []

    def test_no_project_root_is_silent(self, tmp_path):
        assert sync_meta_mismatches(None, "1.7.41") == []


class TestEveryPlatformIsChecked:
    def test_each_stale_platform_is_named(self, tmp_path):
        _stamp(tmp_path, {
            "web": {"tool": "rjui_tools", "version": "1.7.38"},
            "ios": {"tool": "sjui_tools", "version": "1.7.41"},
            "android": {"tool": "kjui_tools", "version": "1.7.39"},
        })

        messages = sync_meta_mismatches(tmp_path, "1.7.41")

        assert len(messages) == 2
        assert any("rjui_tools" in m for m in messages)
        assert any("kjui_tools" in m for m in messages)
        assert not any("sjui_tools" in m for m in messages)

    def test_the_tool_is_named_so_the_reader_knows_which_to_sync(self, tmp_path):
        """A project syncs per platform, so "the toolchain is stale" without
        naming which one leaves the reader to run all three or guess."""
        _stamp(tmp_path, _web("1.7.38", tool="rjui_tools"))

        assert "rjui_tools" in sync_meta_mismatches(tmp_path, "1.7.41")[0]


class TestThroughTheGate:
    """End to end, because the count is part of the claim: this warning is
    actionable in one command, so unlike the notice a declined check prints
    it belongs in `Warnings:`."""

    def _project(self, tmp_path, stamped):
        (tmp_path / "jui.config.json").write_text("{}", encoding="utf-8")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "s.test.json").write_text(json.dumps({
            "type": "screen",
            "source": {"layout": "s.json"},
            "metadata": {"name": "s", "description": "d"},
            "cases": [{"name": "c", "description": "d",
                       "steps": [{"action": "wait", "ms": 10}]}],
        }), encoding="utf-8")
        _stamp(tmp_path, _web(stamped))
        return tmp_path

    def _run(self, project):
        import os
        import subprocess
        proc = subprocess.run(
            [sys.executable, "-m", "jsonui_test_cli.cli", "validate",
             "tests"],
            cwd=project, capture_output=True, text=True,
            env={**os.environ,
                 "PYTHONPATH": str(Path(__file__).parent.parent)})
        return proc.returncode, proc.stdout + proc.stderr

    def test_a_stale_stamp_reaches_the_summary(self, tmp_path):
        from jsonui_test_cli import __version__

        rc, out = self._run(self._project(tmp_path, "0.0.1"))

        assert "0.0.1" in out
        assert __version__ in out
        assert "Warnings: 0" not in out
        assert rc == 0, "a stale sync is a warning, not a failure"

    def test_a_matching_stamp_leaves_the_count_alone(self, tmp_path):
        from jsonui_test_cli import __version__

        rc, out = self._run(self._project(tmp_path, __version__))

        assert "sync_tool" not in out
        assert rc == 0
