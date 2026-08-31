"""The `!` warning must reach the build's warning stream, not just exist.

`WebGenerator.warnings` being populated is not the same claim as a consumer
seeing it: a list nothing drains is a registry nobody is tied to, and the
whole design of the `!` branch rests on it never going out silently. So this
drives the real `jui build` protocol-sync path end to end and reads stderr.
"""
from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from jui_cli.commands.build_cmd import _sync_viewmodel_protocols
from jui_cli.core.config_manager import ConfigManager

SPEC = {
    "metadata": {
        "name": "AccountSetup",
        "displayName": "Account Setup",
        "layoutFile": "account_setup",
    },
    "dataFlow": {
        "viewModel": {
            "vars": [
                # No defaultValue anywhere for UserProfile -> the `!` branch.
                {"name": "profile", "type": "UserProfile",
                 "optional": False, "observable": False},
                # Resolvable -> must not add noise to the stream.
                {"name": "isSubmitting", "type": "Bool",
                 "optional": False, "observable": False},
            ]
        }
    },
}


class TheWarningReachesTheBuild(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        (self.root / "docs" / "screens" / "json").mkdir(parents=True)
        (self.root / "docs" / "screens" / "json"
         / "account_setup.spec.json").write_text(
            json.dumps(SPEC), encoding="utf-8")
        (self.root / "Layouts").mkdir()
        (self.root / "web").mkdir()
        (self.root / "jui.config.json").write_text(json.dumps({
            "layouts_directory": "Layouts",
            "specs_directory": "docs/screens/json",
            "platforms": {"web": {"root": "web"}},
        }), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _build(self):
        cwd = Path.cwd()
        import os
        os.chdir(self.root)
        try:
            mgr = ConfigManager()
            config = mgr.load()
            args = SimpleNamespace(ios_only=False, android_only=False,
                                   web_only=True, clean=False)
            err, out = io.StringIO(), io.StringIO()
            with redirect_stderr(err), redirect_stdout(out):
                ok = _sync_viewmodel_protocols(
                    mgr, config, config["platforms"], args)
            return ok, err.getvalue()
        finally:
            os.chdir(cwd)

    def test_the_unsynthesizable_var_is_reported_on_the_warning_stream(self):
        ok, stderr = self._build()
        self.assertTrue(ok)
        self.assertIn("profile", stderr)
        self.assertIn("AccountSetup", stderr)
        self.assertIn('"optional": true', stderr)
        self.assertIn(".jsonui-type-map.json", stderr)

    def test_a_var_that_can_be_initialized_adds_nothing_to_the_stream(self):
        """The stream is a gate, so it must stay quiet when nothing is wrong."""
        _, stderr = self._build()
        self.assertNotIn("isSubmitting", stderr)

    def test_the_emitted_base_carries_the_bang_the_warning_describes(self):
        """The warning and the emit are two statements about one decision."""
        self._build()
        base = (self.root / "web" / "src" / "generated" / "viewmodels"
                / "AccountSetupViewModelBase.ts").read_text()
        self.assertIn("public profile!: UserProfile;", base)
        self.assertIn("public isSubmitting: boolean = false;", base)


if __name__ == "__main__":
    unittest.main()
