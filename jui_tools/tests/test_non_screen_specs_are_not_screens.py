"""A spec that describes no screen is not read as one — by any command.

1.8.52 added `app_contracts_spec` (a home for unit contracts no single screen
owns) and fixed ONE loop that read it as a screen, `jui verify`'s spec-
coverage check. The same question was asked — or not — in every loop that
walks `*.spec.json`, and two did not ask it:

- `jui verify`'s main loop counted it in `verified N of M` and listed
  "Layouts not found on disk: app_contracts.spec" (a consumer, 2026-09-25);
- `jui generate project` built a screen from it, named from the app's
  display name — `ios/ViewModel/My AppViewModel.swift`, a file name with a
  space that is no Swift type (measured on 3676bb4b).

Classified, the other loops that walk specs: `jui build`'s spec loader asked
already; verify's coverage check asked already; lint-strings reads only specs
that carry `branchContracts` (an app spec has none); the build's cell-layout
walk reads contents, not types — its defect was reading only the top level,
so a Collection cell declared in a sub-spec was not seen.

The question lives in one place, `jui_cli/core/spec_kind.py`, over the table
in `shared/core/spec_types.py`; the commands had two copies of the wrapper.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

JUI_TOOLS = Path(__file__).resolve().parents[1]

APP_SPEC = {"type": "app_contracts_spec", "metadata": {"name": "My App", "description": "d"},
            "unitContracts": [{"target": "ApiClient", "cases": [{"name": "x"}]}]}
UNKNOWN_SPEC = {"type": "weird_spec", "metadata": {"name": "Mystery"}}


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class VerifyCountsOnlyScreens(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _write(self.root / "jui.config.json", {
            "spec_directory": "docs/screens/json", "layouts_directory": "layouts",
            "platforms": {"web": {"root": ".", "layoutsDir": "layouts"}}})
        specs = self.root / "docs/screens/json"
        _write(specs / "home.spec.json",
               {"type": "screen_spec", "metadata": {"name": "home", "layoutFile": "home"}})
        _write(self.root / "layouts/home.json", {"type": "View", "id": "root"})
        _write(specs / "app_contracts.spec.json", APP_SPEC)
        _write(specs / "mystery.spec.json", UNKNOWN_SPEC)

    def tearDown(self):
        self._tmp.cleanup()

    def _verify(self, *extra):
        return subprocess.run(
            [sys.executable, "-m", "jui_cli.cli", "verify", "--platform", "web", *extra],
            cwd=self.root, capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(JUI_TOOLS)})

    def test_the_denominator_holds_screens_only(self):
        run = self._verify()
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("verified 0 of 1 screen(s)", run.stdout)
        # Before: "verified 0 of 3", and both non-screens under this heading.
        self.assertNotIn("Layouts not found on disk", run.stdout)
        self.assertNotIn("app_contracts.spec", run.stdout)

    def test_an_unknown_type_is_named_once(self):
        run = self._verify()
        self.assertEqual(run.stdout.count("mystery.spec.json (type: weird_spec)"), 1, run.stdout)

    def test_naming_a_non_screen_with_file_says_so(self):
        run = self._verify("--file", "app_contracts.spec.json")
        self.assertEqual(run.returncode, 1, run.stdout)
        self.assertIn("app_contracts.spec.json is not a screen spec", run.stdout)


class GenerateProjectBuildsOnlyScreens(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _write(self.root / "jui.config.json", {
            "spec_directory": "docs/screens/json", "layouts_directory": "docs/screens/layouts",
            "platforms": {"ios": {"root": "ios", "layoutsDir": "Layouts"}}})
        specs = self.root / "docs/screens/json"
        (self.root / "docs/screens/layouts").mkdir(parents=True)
        _write(specs / "home.spec.json", {
            "type": "screen_spec", "version": "1.0",
            "metadata": {"name": "Home", "displayName": "Home", "description": "d"},
            "structure": {"layout": {"root": "root", "children": []},
                          "components": [{"id": "root", "type": "View", "description": "r"}]},
            "dataFlow": {"repositories": [{"name": "ItemRepository",
                                           "methods": [{"name": "getItems", "returnType": "Bool"}]}],
                         "viewModel": {"methods": [], "vars": []}},
            "stateManagement": {"uiVariables": []}})
        _write(specs / "app_contracts.spec.json", APP_SPEC)
        _write(specs / "mystery.spec.json", UNKNOWN_SPEC)
        self._cwd = os.getcwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _generate(self):
        from jui_cli.commands.generate_cmd import _cmd_generate_project
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = _cmd_generate_project(argparse.Namespace(
                file=None, force=False, skip_layout=True, dry_run=False, ios_only=True,
                android_only=False, web_only=False, type_map=None))
        generated = sorted(p.name for p in (self.root / "ios").rglob("*") if p.is_file())
        return rc, generated, out.getvalue()

    def test_no_screen_is_made_from_a_non_screen_or_an_unknown_type(self):
        rc, generated, out = self._generate()
        self.assertEqual(rc, 0, out)
        # Before: "My AppViewModel.swift" and "MysteryViewModel.swift".
        self.assertFalse([n for n in generated if "My App" in n or "Mystery" in n], generated)
        self.assertIn("mystery.spec.json has type 'weird_spec'", out)
        self.assertNotIn("app_contracts.spec.json has type", out)   # a known non-screen, silently

    def test_the_screen_is_still_made(self):
        # The control: the loop still builds what it should.
        rc, generated, out = self._generate()
        self.assertIn("HomeViewModel.swift", generated, out)


class CellLayoutsInSubSpecs(unittest.TestCase):
    def test_a_cell_declared_in_a_sub_spec_is_a_cell(self):
        from jui_cli.commands.build_cmd import _spec_cell_layout_stems
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            specs = root / "docs/screens/json"
            _write(specs / "list.spec.json", {"type": "screen_parent_spec",
                                              "subSpecs": [{"file": "list/list-rows.spec.json"}]})
            _write(specs / "list/list-rows.spec.json", {"type": "screen_sub_spec", "structure": {
                "components": [{"id": "rows", "type": "Collection", "cell": {"layoutFile": "row_cell"}}]}})

            class Cfg:
                spec_directory = specs
            self.assertIn("row_cell", _spec_cell_layout_stems(Cfg()))


class OneWrapper(unittest.TestCase):
    def test_every_command_asks_the_same_function(self):
        from jui_cli.commands import build_cmd, verify_cmd
        from jui_cli.core import spec_kind
        self.assertIs(build_cmd._describes_a_screen, spec_kind.describes_a_screen)
        self.assertIs(verify_cmd._describes_a_screen, spec_kind.describes_a_screen)
        source = (JUI_TOOLS / "jui_cli/commands/generate_cmd.py").read_text(encoding="utf-8")
        self.assertIn("from ..core.spec_kind import describes_a_screen", source)

    def test_no_command_defines_its_own(self):
        commands = JUI_TOOLS / "jui_cli/commands"
        own = [p.name for p in commands.glob("*.py")
               if "def _describes_a_screen" in p.read_text(encoding="utf-8")]
        self.assertEqual(own, [])


if __name__ == "__main__":
    unittest.main()
