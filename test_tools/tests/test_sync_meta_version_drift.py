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


class TestTheUnstampedNoteOnThisSide:
    """🚨 The same rule has TWO mouths in v1.8.58, and this one had no arms.

    `unstamped_platforms` is called from `jui build` (5 arms, with controls)
    and from `jsonui-test validate` (`cli.py:209`) — and `grep -rn unstamped
    test_tools/tests/` answered 0. The sibling rule right beside it,
    `sync_meta_mismatches`, has ten. Reported by the triage lane before the
    tag.

    ⚠️ Worse than uncovered: `unstamped_platforms` returns [] when there is no
    sync-meta file, so nothing in this suite reaches the NOTE branch even by
    accident, and all seven consumer faces currently stamp every platform.
    Without these arms the line would ship having never executed anywhere.

    📌 One rule with two mouths needs arms counted PER MOUTH. The version that
    added the second mouth is the version that must add its arms.
    """

    def _stamp(self, root, platforms):
        meta = root / ".jsonui-cli"
        meta.mkdir(parents=True, exist_ok=True)
        (meta / "sync-meta.json").write_text(
            json.dumps({"platforms": platforms}), encoding="utf-8")

    def test_a_platform_with_no_version_is_reported_here_too(self, tmp_path):
        from jsonui_test_cli.validation.toolchain import unstamped_platforms
        self._stamp(tmp_path, {"android": {"tool": "kjui_tools"},
                               "web": {"tool": "rjui_tools", "version": "1.7.41"}})
        assert unstamped_platforms(tmp_path) == ["kjui_tools"]

    def test_unknown_counts_as_unstamped_here_too(self, tmp_path):
        from jsonui_test_cli.validation.toolchain import unstamped_platforms
        self._stamp(tmp_path, {"ios": {"tool": "sjui_tools", "version": "unknown"}})
        assert unstamped_platforms(tmp_path) == ["sjui_tools"]

    def test_the_control_every_platform_stamped_reports_none(self, tmp_path):
        from jsonui_test_cli.validation.toolchain import unstamped_platforms
        self._stamp(tmp_path, {"android": {"tool": "kjui_tools", "version": "1.7.41"},
                               "web": {"tool": "rjui_tools", "version": "1.7.41"}})
        assert unstamped_platforms(tmp_path) == []

    def test_no_stamp_file_reports_none(self, tmp_path):
        from jsonui_test_cli.validation.toolchain import unstamped_platforms
        assert unstamped_platforms(tmp_path) == []

    def test_both_mouths_resolve_to_the_same_module(self):
        """⚠️ The pairing arm. Two callers of one rule must not drift onto two
        copies — the reason the rule was MOVED to shared/core rather than
        duplicated."""
        from jsonui_test_cli.validation import toolchain as adapter
        rule = adapter._rule()
        assert rule is not None
        assert adapter.unstamped_platforms.__module__ != rule.__name__
        assert hasattr(rule, "unstamped_platforms")

    # --- the NOTE the mouth prints, not merely the call it makes -----------
    #
    # 🚨 THE ARM BELOW USED TO BE THE ONLY ONE HERE, AND IT COVERED THE CALL
    # ONLY. Fired 2026-09-08, before the tag: a mutation that KEPT the call
    # and disabled the `if` left this file green — the NOTE became
    # unreachable and no arm noticed. "Calls it" and "says it" are two
    # claims. The three arms that follow drive the text itself, through the
    # helper the print was extracted into for exactly that reason.

    def test_the_note_names_the_platforms_and_the_remedy(self, tmp_path):
        from jsonui_test_cli.cli import unstamped_note
        self._stamp(tmp_path, {"android": {"tool": "kjui_tools"},
                               "ios": {"tool": "sjui_tools", "version": "unknown"}})
        note = unstamped_note(tmp_path)
        assert note is not None
        assert "kjui_tools" in note and "sjui_tools" in note
        assert "2 platform(s)" in note
        # ⚠️ The half that makes it actionable. A line that says a check was
        # skipped, without saying it is not a clean bill of health, is the
        # silence this exists to replace.
        assert "SKIPPED" in note
        assert "not a statement that they are in step" in note
        assert "jui sync_tool" in note

    def test_the_control_a_fully_stamped_project_gets_no_note(self, tmp_path):
        from jsonui_test_cli.cli import unstamped_note
        self._stamp(tmp_path, {"android": {"tool": "kjui_tools", "version": "1.7.41"}})
        assert unstamped_note(tmp_path) is None

    def test_the_control_no_stamp_file_gets_no_note(self, tmp_path):
        """A project that vendors no tools has nothing to be out of step
        with; a NOTE on every such run is the constant line a real one hides
        behind."""
        from jsonui_test_cli.cli import unstamped_note
        assert unstamped_note(tmp_path) is None

    def test_the_cli_actually_prints_it(self):
        """The remaining inch: the helper is pure, so only the source says
        the command emits what it returns.

        ⚠️ Do not write the searched-for spellings into prose anywhere in
        `cli.py`. The first draft of this fix explained itself in a docstring
        that quoted the call, and this arm went green against a source that
        had stopped making it — matching the comment, not the code. That is
        v1.8.58's own finding ①, reproduced while fixing something else.
        """
        from pathlib import Path as _P
        src = (_P(__file__).resolve().parents[1] / "jsonui_test_cli"
               / "cli.py").read_text(encoding="utf-8")
        # ⚠️ Pinned as ONE CONTIGUOUS BLOCK, not as two independent
        # substrings. Two `in src` checks both survive `if False and _note:`
        # — the guard is a third claim, and a mutation that kills only the
        # guard leaves every spelling in place. Three lines whose exact shape
        # IS the contract are worth pinning exactly; the cost is that a
        # reformat of these three lines must update this arm, which is the
        # intended cost.
        block = ("    _note = unstamped" + "_note(_root)\n"
                 "    if _note:\n"
                 "        print(_note)\n")
        assert block in src, (
            "the three lines that compute, guard and emit the NOTE are not "
            "in `cli.py` in that shape — one of the three claims (asks for "
            "it / only when there is one / says it) has been dropped")


class TestTheNoteIsActuallyREACHED:
    """🚨 THE THIRD CLAIM. Reported by the triage lane against the arms above.

    "Calls it" and "says it" are two claims — that was the finding that moved
    this release's candidate. There is a third: **is reached**. A source arm
    pins spelling, shape and relative order; it cannot pin reachability.

        MUT F  move the three lines VERBATIM to after `cmd_validate`'s
               `return 0` — block still in src, order still correct,
               index 9943 -> 19575
        result 20 passed. Every arm above stays green.

    ⚠️ The reason given for not driving `cmd_validate` — "it needs a whole
    project on disk" — was wrong: SIX files in this suite already drive it,
    and the project is `jui.config.json` = `{}` plus one test file. The
    argument that justified stopping at a source read did not survive being
    checked.

    📌 Same family, third instance: v1.8.56 (an arm read a comment),
    v1.8.57 (an arm read spelling, not order), and now an arm that reads
    everything about the line except whether control gets there.
    """

    def _project(self, tmp_path, platforms):
        (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
        (tmp_path / "jui.config.json").write_text("{}", encoding="utf-8")
        if platforms is not None:
            meta = tmp_path / ".jsonui-cli"
            meta.mkdir(parents=True, exist_ok=True)
            (meta / "sync-meta.json").write_text(
                json.dumps({"platforms": platforms}), encoding="utf-8")
        (tmp_path / "tests" / "s.test.json").write_text(json.dumps({
            "type": "screen", "source": {},
            "metadata": {"name": "s", "description": "d"},
            "cases": [{"name": "c", "description": "d",
                       "steps": [{"assert": "visible", "id": "root"}]}],
        }), encoding="utf-8")
        return tmp_path

    def _run(self, tmp_path, monkeypatch, capsys, platforms):
        import argparse
        from jsonui_test_cli import cli
        monkeypatch.chdir(self._project(tmp_path, platforms))
        cli.cmd_validate(argparse.Namespace(
            files=["tests"], verbose=False, quiet=False, config=None,
            no_mock_check=True, no_install=True, strict=False))
        out = capsys.readouterr().out
        return [l for l in out.splitlines()
                if "carry no stamped version" in l]

    def test_the_command_emits_the_note(self, tmp_path, monkeypatch, capsys):
        lines = self._run(tmp_path, monkeypatch, capsys, {
            "android": {"tool": "kjui_tools"},
            "ios": {"tool": "sjui_tools", "version": "unknown"}})

        assert len(lines) == 1, lines
        assert "2 platform(s)" in lines[0]
        assert "kjui_tools" in lines[0] and "sjui_tools" in lines[0]

    def test_the_control_a_fully_stamped_project_emits_nothing(
            self, tmp_path, monkeypatch, capsys):
        """⚠️ Without this, the arm above passes over a command that prints
        the NOTE unconditionally — which is the shape a reader mistakes for
        a working guard."""
        lines = self._run(tmp_path, monkeypatch, capsys, {
            "android": {"tool": "kjui_tools", "version": "1.8.58"}})

        assert lines == []

    def test_the_control_no_stamp_file_emits_nothing(
            self, tmp_path, monkeypatch, capsys):
        assert self._run(tmp_path, monkeypatch, capsys, None) == []
