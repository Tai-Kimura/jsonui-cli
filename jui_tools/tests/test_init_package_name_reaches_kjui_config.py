"""`jui init --package-name` reaches android/kjui.config.json.

`jui init` wrote the package into jui.config.json only and ran `kjui init`
without it. kjui detects the package from AndroidManifest.xml / build.gradle,
and the empty platform root `jui init` starts from has neither, so
kjui.config.json fell back to com.example.app and `jui g converter` wrote the
Android files under com/example/app while jui.config.json named another package.

Two arms: the command `jui init` runs carries the package, and the flag it uses
is one `kjui init` actually declares (read from the Ruby source, so the two
spellings cannot drift apart without a red). The Ruby side's behaviour with the
flag is armed in kjui_tools/spec/cli/commands/init_spec.rb.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jui_cli.commands import init_cmd

KJUI_INIT_RB = Path(__file__).resolve().parents[2] / "kjui_tools" / "lib" / "cli" / "commands" / "init.rb"


def _args(**overrides):
    base = dict(project_name="sample", ios=None, ios_mode="swiftui",
                android=None, android_mode="compose", package_name=None,
                web=None, no_sync_tools=True)
    base.update(overrides)
    return argparse.Namespace(**base)


class InitPassesThePackage(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._old = os.getcwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self._old)
        self._tmp.cleanup()

    def _kjui_commands(self, **overrides):
        seen = []
        with mock.patch.object(init_cmd, "_run_tool", side_effect=lambda cmd, cwd: seen.append(cmd)), \
                contextlib.redirect_stdout(io.StringIO()):
            init_cmd.cmd_init(_args(android="android", **overrides))
        return [c for c in seen if c[:2] == ["kjui", "init"]]

    def test_the_package_is_passed_to_kjui_init(self):
        (cmd,) = self._kjui_commands(package_name="com.example.myapp")
        self.assertIn("--package-name", cmd)
        self.assertEqual(cmd[cmd.index("--package-name") + 1], "com.example.myapp")

    def test_no_package_no_flag(self):
        (cmd,) = self._kjui_commands()
        self.assertNotIn("--package-name", cmd)

    def test_kjui_init_declares_the_flag_jui_init_passes(self):
        (cmd,) = self._kjui_commands(package_name="com.example.myapp")
        flag = next(a for a in cmd if a.startswith("--package"))
        declared = re.findall(r"opts\.on\('(--[a-z-]+)", KJUI_INIT_RB.read_text(encoding="utf-8"))
        self.assertIn(flag, declared)


if __name__ == "__main__":
    unittest.main()
