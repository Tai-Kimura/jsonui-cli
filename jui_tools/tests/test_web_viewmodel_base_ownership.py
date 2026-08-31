"""jui_tools does not write the web `<Name>ViewModelBase.ts`. rjui_tools does.

Two generators wrote that path. `rjui build` regenerates it from the Layout
and runs after protocol sync inside `jui build`, so everything jui_tools wrote
was overwritten before the build finished. The symptoms were a build that
reported `updated N protocol(s)` on an unchanged tree — work it had not
durably done — and, once var declarations were added, a warning naming a
declaration that did not survive into the artifact.

The two tools do not merely duplicate: rjui_tools emits no var declarations at
all, because in the rjui contract an `observable: false` var is Impl-private
state. A consumer's hand-written Impl declares those names as `private`, so a
`public` field on the Base is a TS2415. That contract is why this is an
ownership question and not a merge.

The condition is the project's existing `platforms.web` declaration, not a new
flag: both commands only visit platforms the project declared, so reaching a
`"web"` iteration is that declaration.
"""
from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from jui_cli.commands.build_cmd import _sync_viewmodel_protocols
from jui_cli.core.config_manager import ConfigManager
from jui_cli.generators.web_generator import WebGenerator, owns_viewmodel_base

SPEC = {
    "metadata": {"name": "AccountSetup", "displayName": "Account Setup",
                 "layoutFile": "account_setup"},
    "dataFlow": {"viewModel": {"vars": [
        # The shape that used to emit `public profile!: UserProfile;` and warn.
        {"name": "profile", "type": "UserProfile",
         "optional": False, "observable": False},
        {"name": "isSubmitting", "type": "Bool",
         "optional": False, "observable": False},
    ]}},
}


class TheRuleIsStatedOnce(unittest.TestCase):
    def test_web_is_not_ours_and_the_native_platforms_are(self):
        self.assertFalse(owns_viewmodel_base("web"))
        self.assertTrue(owns_viewmodel_base("ios"))
        self.assertTrue(owns_viewmodel_base("android"))

    def test_the_generator_no_longer_offers_to_write_one(self):
        """Deleted rather than left unreachable.

        An unreachable emitter is an asset no gate covers: it keeps its own
        idea of what belongs in the file, and the next person to find it has
        no way to tell "deliberately not called" from "call site lost".
        """
        self.assertFalse(hasattr(WebGenerator, "generate_viewmodel_protocol"))
        self.assertFalse(hasattr(WebGenerator, "viewmodel_protocol_path"))

    def test_the_impl_scaffold_is_still_ours(self):
        """Scope: only the Base moved. The Impl is written once, never
        overwritten, and is not part of the round-trip."""
        self.assertTrue(hasattr(WebGenerator, "generate_viewmodel_impl"))
        self.assertTrue(hasattr(WebGenerator, "viewmodel_impl_path"))


class BuildDoesNotTouchTheWebBase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        (self.root / "docs" / "screens" / "json").mkdir(parents=True)
        (self.root / "docs" / "screens" / "json" / "account_setup.spec.json"
         ).write_text(json.dumps(SPEC), encoding="utf-8")
        (self.root / "Layouts").mkdir()
        self.base = (self.root / "web" / "src" / "generated" / "viewmodels"
                     / "AccountSetupViewModelBase.ts")
        self.base.parent.mkdir(parents=True)
        # Stand in for what `rjui build` leaves on disk: no var declarations.
        self.base.write_text(
            "export class AccountSetupViewModelBase {\n}\n", encoding="utf-8")
        (self.root / "jui.config.json").write_text(json.dumps({
            "layouts_directory": "Layouts",
            "specs_directory": "docs/screens/json",
            "platforms": {"web": {"root": "web"}},
        }), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _sync(self):
        cwd = Path.cwd()
        os.chdir(self.root)
        try:
            mgr = ConfigManager()
            config = mgr.load()
            args = SimpleNamespace(ios_only=False, android_only=False,
                                   web_only=False, clean=False)
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                ok = _sync_viewmodel_protocols(
                    mgr, config, config["platforms"], args)
            return ok, out.getvalue(), err.getvalue()
        finally:
            os.chdir(cwd)

    def test_the_rjui_artifact_is_left_exactly_as_found(self):
        before = self.base.read_text()
        ok, _, _ = self._sync()
        self.assertTrue(ok)
        self.assertEqual(self.base.read_text(), before)

    def test_nothing_is_reported_as_updated(self):
        """The churn was a false report of work, not only wasted writes.

        `atomic_write_text` skips unchanged content, so `updated N` on an
        unchanged tree could only mean the file had been rewritten to
        something else and back.
        """
        _, stdout, _ = self._sync()
        self.assertNotIn("Protocol sync:", stdout)

    def test_no_warning_is_raised_about_a_declaration_that_never_ships(self):
        """`profile` would have warned under the previous behaviour."""
        _, stdout, stderr = self._sync()
        self.assertNotIn("profile", stdout + stderr)
        self.assertNotIn("definite assignment", stdout + stderr)

    def test_a_second_run_is_identical(self):
        """The reported symptom was per-build, so it is checked per-build."""
        self._sync()
        after_first = self.base.read_text()
        _, stdout, _ = self._sync()
        self.assertEqual(self.base.read_text(), after_first)
        self.assertNotIn("Protocol sync:", stdout)



class GenerateProjectDoesNotSeedTheWebBase(unittest.TestCase):
    """The scaffolding side of the same rule.

    Closing protocol sync alone would have left `jui generate project`
    planting the file the round-trip fed on — the same path, written by the
    other command. Both commands ask `owns_viewmodel_base`, so there is one
    statement of who owns the file rather than two that can drift apart.
    """

    SPEC = {
        "type": "screen_spec",
        "version": "1.0",
        "metadata": {"name": "Home", "displayName": "Home",
                     "description": "ownership fixture"},
        "structure": {"layout": {"root": "root", "children": []},
                      "components": [{"id": "root", "type": "View",
                                      "description": "root container"}]},
        "dataFlow": {
            "repositories": [{"name": "ItemRepository",
                              "methods": [{"name": "getItems",
                                           "returnType": "Bool"}]}],
            "viewModel": {"methods": [], "vars": [
                {"name": "profile", "type": "UserProfile",
                 "optional": False, "observable": False}]},
        },
        "stateManagement": {"uiVariables": []},
    }

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        (self.root / "jui.config.json").write_text(json.dumps({
            "spec_directory": "docs/screens/json",
            "layouts_directory": "docs/screens/layouts",
            "platforms": {"web": {"root": "web"}},
        }), encoding="utf-8")
        (self.root / "docs/screens/json").mkdir(parents=True)
        (self.root / "docs/screens/layouts").mkdir(parents=True)
        (self.root / "docs/screens/json/home.spec.json").write_text(
            json.dumps(self.SPEC), encoding="utf-8")
        self._cwd = os.getcwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _generate(self):
        from jui_cli.commands.generate_cmd import _cmd_generate_project
        args = SimpleNamespace(file=None, force=False, skip_layout=True,
                               dry_run=False, ios_only=False,
                               android_only=False, web_only=True,
                               type_map=None)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = _cmd_generate_project(args)
        return code, out.getvalue() + err.getvalue()

    def test_no_viewmodel_base_is_written(self):
        code, _ = self._generate()
        self.assertEqual(code, 0)
        self.assertEqual(
            list(self.root.rglob("*ViewModelBase.ts")), [],
            "generate project must not plant the file rjui_tools owns")

    def test_the_impl_scaffold_is_still_written(self):
        """Scope check: only the Base moved, not the whole web generator."""
        self._generate()
        self.assertTrue(list(self.root.rglob("HomeViewModel.ts")),
                        "the Impl scaffold is still ours to write")

    def test_no_warning_about_an_unshippable_declaration(self):
        _, output = self._generate()
        self.assertNotIn("definite assignment", output)


if __name__ == "__main__":
    unittest.main()
