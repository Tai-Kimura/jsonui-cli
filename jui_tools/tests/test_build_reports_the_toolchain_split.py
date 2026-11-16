"""`jui build` says when the project's vendored tools are not this version.

The rule already existed and had exactly ONE production caller — `jsonui-test`
(`test_tools/jsonui_test_cli/cli.py:201`); references from `jui_tools`: 0. So
the command that runs FIRST in the delivery script was the one that could not
see a split, and a face measured `jui build` EXIT 0 / warnings 0 while its
stamp said 1.8.54 and the running CLI was 1.8.55.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "jui_tools"))

from jui_cli.commands import build_cmd  # noqa: E402
from jui_cli.core import shared_core  # noqa: E402


class _Cfg:
    def __init__(self, root):
        self.project_root = Path(root)


def _stamp(root: Path, version: str, tool: str = "sjui_tools") -> None:
    meta = root / ".jsonui-cli"
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "sync-meta.json").write_text(json.dumps(
        {"platforms": {"ios": {"tool": tool, "version": version}}}),
        encoding="utf-8")


class TestTheSplitIsReported:
    def test_a_stale_stamp_is_named_on_stderr(self, tmp_path, capsys):
        _stamp(tmp_path, "1.8.54")
        build_cmd._report_toolchain_sync(_Cfg(tmp_path))
        err = capsys.readouterr().err
        assert "WARNING [toolchain]" in err, err
        assert "1.8.54" in err and "sjui_tools" in err, err
        assert "jui sync_tool" in err, "the warning must name the remedy"

    def test_it_goes_to_stderr_not_stdout(self, tmp_path, capsys):
        """A face may diff `jui build` stdout. Warnings already go to stderr,
        so adding this one cannot change a stdout comparison."""
        _stamp(tmp_path, "1.8.54")
        build_cmd._report_toolchain_sync(_Cfg(tmp_path))
        cap = capsys.readouterr()
        assert "WARNING [toolchain]" in cap.err
        assert "toolchain" not in cap.out, cap.out

    def test_the_control_a_matching_stamp_says_nothing(self, tmp_path, capsys):
        """🚨 The arm that would have caught the version-source defect.

        The first draft read `jui_cli.__version__`, which is the package
        literal "0.1.0" and never moves — so a stamp of the CURRENT version
        still mismatched, and the check would have warned on every project on
        every build. Stamping with what `jui --version` answers and asserting
        SILENCE is what distinguishes "reads the toolchain version" from
        "reads some version".
        """
        from jui_cli.version import toolchain_version
        _stamp(tmp_path, toolchain_version())
        build_cmd._report_toolchain_sync(_Cfg(tmp_path))
        assert capsys.readouterr().err == ""

    def test_no_stamp_is_silent(self, tmp_path, capsys):
        build_cmd._report_toolchain_sync(_Cfg(tmp_path))
        assert capsys.readouterr().err == ""


class TestOneRuleNotTwo:
    def test_the_rule_lives_in_shared_core(self):
        assert shared_core.load("toolchain_sync") is not None

    def test_jsonui_test_reads_the_same_module(self):
        """⚠️ The pairing arm. Both commands must resolve to ONE module
        object; two copies of this rule is how `jui build` and `jsonui-test`
        came to disagree about whether a project was in step."""
        sys.path.insert(0, str(REPO / "test_tools"))
        from jsonui_test_cli.validation import toolchain as adapter
        assert adapter.rule_is_available()
        assert adapter._rule() is shared_core.load("toolchain_sync")

    def test_the_adapter_holds_no_second_copy_of_the_comparison(self):
        """The adapter must DELEGATE, not re-implement. A second copy would
        pass its own tests while drifting from the one `jui build` reads."""
        src = (REPO / "test_tools" / "jsonui_test_cli" / "validation"
               / "toolchain.py").read_text(encoding="utf-8")
        assert "was synced from" not in src, (
            "the message text is back in the adapter — that is the rule "
            "being re-implemented rather than delegated")


class TestTheCheckIsActuallyWired:
    """🚨 Added because the arms above all passed with the call REMOVED.

    Every test in this file drives `_report_toolchain_sync` directly, so they
    say the function behaves — not that `jui build` runs it. Deleting the one
    line in `cmd_build` left 7/7 green. A helper nobody calls prints nothing,
    and the defect being fixed here IS "nobody called it".
    """

    def test_cmd_build_calls_it(self):
        import inspect
        src = inspect.getsource(build_cmd.cmd_build)
        assert "_report_toolchain_sync(" in src, (
            "cmd_build no longer calls the toolchain check — the rule is "
            "reachable but unreached, which is the exact shape of the defect "
            "this file was written for")

    def test_it_runs_before_any_generation(self):
        """Position matters: the operator must learn the tools are stale
        BEFORE the build writes anything with them, not in a summary after."""
        import inspect
        src = inspect.getsource(build_cmd.cmd_build)
        call = src.index("_report_toolchain_sync(")
        for later in ("_distribute_layouts", "_record_generation"):
            if later in src:
                assert call < src.index(later), (
                    f"the toolchain warning is emitted after {later}")


class TestAnUnstampedPlatformSaysItWasSkipped:
    """🚨 Silence had two causes and one spelling.

    `sync_meta_mismatches` skips a platform whose stamp carries no version —
    correctly, because comparing against `unknown` would fire on every run of
    a project stamped before versioned stamping. But the skip printed nothing,
    and "no line for android" reads as "android is in step". Reported by a
    consumer lane that decomposed the three ways the check goes quiet.
    """

    def _stamp(self, root, platforms):
        meta = root / ".jsonui-cli"
        meta.mkdir(parents=True, exist_ok=True)
        (meta / "sync-meta.json").write_text(json.dumps({"platforms": platforms}),
                                             encoding="utf-8")

    def test_a_platform_with_no_version_is_named_as_skipped(self, tmp_path, capsys):
        self._stamp(tmp_path, {"android": {"tool": "kjui_tools"},
                               "web": {"tool": "rjui_tools", "version": "1.8.54"}})
        build_cmd._report_toolchain_sync(_Cfg(tmp_path))
        err = capsys.readouterr().err
        assert "NOTE [toolchain]" in err, err
        assert "kjui_tools" in err, err
        assert "SKIPPED" in err, err

    def test_unknown_counts_as_unstamped(self, tmp_path, capsys):
        self._stamp(tmp_path, {"ios": {"tool": "sjui_tools", "version": "unknown"}})
        build_cmd._report_toolchain_sync(_Cfg(tmp_path))
        assert "sjui_tools" in capsys.readouterr().err

    def test_the_control_every_platform_stamped_prints_no_note(self, tmp_path, capsys):
        """The arm that separates "skipped" from "in step". Without it the fix
        could print the NOTE unconditionally and still pass everything else."""
        from jui_cli.version import toolchain_version
        v = toolchain_version()
        self._stamp(tmp_path, {"android": {"tool": "kjui_tools", "version": v},
                               "web": {"tool": "rjui_tools", "version": v}})
        build_cmd._report_toolchain_sync(_Cfg(tmp_path))
        err = capsys.readouterr().err
        assert "NOTE [toolchain]" not in err, err
        assert err == ""

    def test_a_mismatch_still_reports_when_another_platform_is_unstamped(
            self, tmp_path, capsys):
        """⚠️ Regression arm: adding the NOTE must not swallow the WARNING."""
        self._stamp(tmp_path, {"android": {"tool": "kjui_tools"},
                               "web": {"tool": "rjui_tools", "version": "1.8.54"}})
        build_cmd._report_toolchain_sync(_Cfg(tmp_path))
        err = capsys.readouterr().err
        assert "WARNING [toolchain]" in err and "rjui_tools" in err, err

    def test_the_note_does_not_change_the_exit_path(self, tmp_path, capsys):
        """A missing stamp is a gap in the record, not a failure."""
        self._stamp(tmp_path, {"ios": {"tool": "sjui_tools"}})
        assert build_cmd._report_toolchain_sync(_Cfg(tmp_path)) is None
