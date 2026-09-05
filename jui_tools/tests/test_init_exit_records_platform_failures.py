"""`jui init` must not exit 0 over a platform it never initialized.

Measured 2026-09-05, CI run 33943839994. The runner has no `sjui` on PATH, so
`sjui init` never ran and no `sjui.config.json` was written — but `jui init`
printed `WARNING: Init failed for: ios (sjui init)` and returned 0. A spec
guarding with `raise "jui init failed" unless system(...)` therefore did not
fire, and three examples died one step later on `File.read('sjui.config.json')`
with ENOENT: the failure surfaced as far from its cause as it could.

Same family as `jui build` exiting 0 over a screen it failed to generate
(1.8.43). The print already said the right thing; only the exit code
disagreed, and the exit code is the half a script reads.

The arms drive `cmd_init` itself rather than re-deriving the rule, and the
missing-tool arm reproduces the CI condition by emptying PATH rather than by
patching the function that would have detected it.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jui_cli.commands import init_cmd


def _args(**overrides):
    """The namespace `cmd_init` reads, matching the existing init tests.

    Built from the same base as `test_init_in_a_monorepo` rather than
    invented here: a hand-written namespace that misses a field fails with
    AttributeError, which looks like a defect in the code under test.
    """
    base = dict(project_name="sample", ios=None, ios_mode="swiftui",
                android=None, android_mode="compose", package_name=None,
                web=None, no_sync_tools=True)
    base.update(overrides)
    return argparse.Namespace(**base)


def _run_in(cwd, **overrides) -> tuple[int, str]:
    cwd.mkdir(parents=True, exist_ok=True)
    old = os.getcwd()
    os.chdir(cwd)
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = init_cmd.cmd_init(_args(**overrides))
        return code, buf.getvalue()
    finally:
        os.chdir(old)


class InitExitCode(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_platform_tool_missing_from_PATH_is_a_failure(self):
        # The CI condition itself: PATH holds nothing, so `sjui` cannot be
        # found and FileNotFoundError is raised inside subprocess.run.
        with mock.patch.dict(os.environ, {"PATH": ""}, clear=False):
            code, out = _run_in(self.root, ios=".")
        self.assertEqual(code, 1, out)
        self.assertIn("[ERROR]", out)
        self.assertIn("ios (sjui init)", out)
        self.assertIn("not found in PATH", out)
        # And it must not simultaneously claim success.
        self.assertNotIn("initialized successfully", out)

    def test_a_platform_tool_that_runs_and_fails_is_also_a_failure(self):
        # The other half `_run_tool` used to fold into one False: the tool
        # exists and exits non-zero. The reason must say which.
        class _Result:
            returncode = 3

        with mock.patch.object(init_cmd.subprocess, "run", return_value=_Result()):
            code, out = _run_in(self.root, ios=".")
        self.assertEqual(code, 1, out)
        self.assertIn("exited 3", out)
        self.assertNotIn("not found in PATH", out)

    def test_every_platform_succeeding_still_exits_zero(self):
        class _Result:
            returncode = 0

        with mock.patch.object(init_cmd.subprocess, "run", return_value=_Result()):
            code, out = _run_in(self.root, ios="ios", android="android", web="web")
        self.assertEqual(code, 0, out)
        self.assertIn("initialized successfully", out)
        self.assertNotIn("[ERROR]", out)

    def test_one_of_two_platforms_failing_names_only_that_one(self):
        calls = []

        def _fake_run(cmd, cwd=None, **kw):
            calls.append(cmd[0])

            class _R:
                returncode = 0 if cmd[0] == "kjui" else 7
            return _R()

        with mock.patch.object(init_cmd.subprocess, "run", side_effect=_fake_run):
            code, out = _run_in(self.root, ios="ios", android="android")
        self.assertEqual(code, 1, out)
        self.assertIn("ios (sjui init)", out)
        self.assertNotIn("android (kjui init)", out)
        self.assertIn("sjui", calls)
        self.assertIn("kjui", calls)

    def test_a_project_with_no_platforms_is_unaffected(self):
        code, out = _run_in(self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("initialized successfully", out)

    def test_the_config_is_still_written_when_a_platform_fails(self):
        # Exit 1 reports the hole; it does not throw away the work that DID
        # happen. `jui.config.json` is what the next command reads.
        with mock.patch.dict(os.environ, {"PATH": ""}, clear=False):
            code, _ = _run_in(self.root, ios=".")
        self.assertEqual(code, 1)
        config = json.loads((self.root / "jui.config.json").read_text(encoding="utf-8"))
        self.assertIn("ios", config["platforms"])


class RunToolReason(unittest.TestCase):
    """`_run_tool` reports WHY, not just that something went wrong."""

    def test_missing_executable(self):
        with mock.patch.object(init_cmd.subprocess, "run",
                               side_effect=FileNotFoundError()):
            self.assertIn("not found in PATH", init_cmd._run_tool(["sjui", "init"], Path(".")))

    def test_non_zero_exit(self):
        class _R:
            returncode = 2

        with mock.patch.object(init_cmd.subprocess, "run", return_value=_R()):
            self.assertIn("exited 2", init_cmd._run_tool(["sjui", "init"], Path(".")))

    def test_success_is_none(self):
        class _R:
            returncode = 0

        with mock.patch.object(init_cmd.subprocess, "run", return_value=_R()):
            self.assertIsNone(init_cmd._run_tool(["sjui", "init"], Path(".")))


if __name__ == "__main__":
    unittest.main()
