"""The platform declaration comes from the config the run read, end to end.

Driven through the real CLI rather than the validator, because the part worth
pinning is where the declaration is resolved from. Every previous version of
this idea in this tool searched upward from a file and was defeated by the
same layout — tests in a parent repository, config in the app directory — so
the test that matters is the one that runs from a directory whose config is
NOT on the ancestor path of the tests it validates.

Also pins the note for the opposite case: a run that produces platform
warnings while finding no declaration says so once, and only then.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_TOOL = Path(__file__).resolve().parents[1]

NOTE = "No 'platforms' declaration was found"
TYPE_W = "has an unsupported type"


def doc(step):
    return {
        "type": "screen",
        "source": {"layout": "test.json"},
        "metadata": {"name": "Fixture", "description": "Fixture screen test.",
                     "screen": "fixture"},
        "platform": "web",
        "cases": [{"name": "c", "description": "Case.", "steps": [step]}],
    }


PDF_STEP = {"action": "addMedia", "id": "u", "paths": ["files/report.pdf"]}
CLEAN_STEP = {"assert": "visible", "id": "fixture_root"}


class _Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "tests").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def write_test(self, step):
        (self.root / "tests" / "f.test.json").write_text(
            json.dumps(doc(step)), encoding="utf-8")

    def write_config(self, platforms, where=None):
        body = {} if platforms is None else {"platforms": platforms}
        target = (where or self.root) / "jui.config.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(body), encoding="utf-8")

    def validate(self, cwd=None, args=()):
        proc = subprocess.run(
            [sys.executable, "-m", "jsonui_test_cli.cli", "validate",
             *(args or [str(self.root / "tests")])],
            cwd=cwd or self.root, capture_output=True, text=True,
            env={"PYTHONPATH": str(REPO_TOOL), "PATH": "/usr/bin:/bin"})
        return proc.returncode, proc.stdout + proc.stderr


class DeclarationSilencesWarnings(_Fixture):
    def test_a_web_only_declaration_silences_the_warning(self):
        self.write_test(PDF_STEP)
        self.write_config({"web": {"root": "."}})
        rc, out = self.validate()
        self.assertEqual(rc, 0, out)
        self.assertNotIn(TYPE_W, out)
        self.assertIn("Warnings: 0", out)

    def test_a_list_spelling_works_too(self):
        """`platforms` is a map in the corpus; a list is the obvious variant."""
        self.write_test(PDF_STEP)
        self.write_config(["web"])
        rc, out = self.validate()
        self.assertNotIn(TYPE_W, out)

    def test_declaring_every_platform_changes_nothing(self):
        self.write_test(PDF_STEP)
        self.write_config({"ios": {}, "android": {}, "web": {}})
        rc, out = self.validate()
        self.assertIn(TYPE_W, out)

    def test_no_config_at_all_warns_as_before(self):
        self.write_test(PDF_STEP)
        rc, out = self.validate()
        self.assertIn(TYPE_W, out)


class TheNoteIsConditional(_Fixture):
    def test_it_appears_when_warnings_had_no_declaration_to_consult(self):
        self.write_test(PDF_STEP)
        self.write_config(None)
        rc, out = self.validate()
        self.assertIn(NOTE, out)

    def test_it_stays_quiet_when_there_is_nothing_to_suppress(self):
        """A project with no platform warnings has nothing to explain.

        The whole point of the feature is holding a suite at zero warnings; a
        line printed on every clean run would be the constant a new warning
        hides behind.
        """
        self.write_test(CLEAN_STEP)
        self.write_config(None)
        rc, out = self.validate()
        self.assertNotIn(NOTE, out)

    def test_it_stays_quiet_once_the_declaration_is_found(self):
        self.write_test(PDF_STEP)
        self.write_config({"web": {}})
        rc, out = self.validate()
        self.assertNotIn(NOTE, out)

    def test_quiet_suppresses_it(self):
        self.write_test(PDF_STEP)
        self.write_config(None)
        rc, out = self.validate(args=[str(self.root / "tests"), "-q"])
        self.assertNotIn(NOTE, out)


class TheConfigIsTheOneTheRunRead(_Fixture):
    """The layout every previous version of this idea got wrong."""

    def setUp(self):
        super().setUp()
        # Tests in the parent tree, the app (and its config) in a subdirectory:
        # `app/jui.config.json` is NOT an ancestor of `tests/`.
        self.app = self.root / "app"
        self.app.mkdir()
        self.write_test(PDF_STEP)

    def test_running_from_the_app_finds_its_declaration(self):
        self.write_config({"web": {}}, where=self.app)
        rc, out = self.validate(cwd=self.app)
        self.assertNotIn(TYPE_W, out)

    def test_an_explicit_config_path_finds_it_from_anywhere(self):
        self.write_config({"web": {}}, where=self.app)
        rc, out = self.validate(args=[
            str(self.root / "tests"), "--config",
            str(self.app / "jui.config.json")])
        self.assertNotIn(TYPE_W, out)

    def test_running_from_the_parent_does_not_borrow_the_apps_declaration(self):
        """Not a defect to route around — the run was pointed elsewhere.

        Searching upward from the test file would not find it either (the app
        directory is not an ancestor). Guessing which of several app configs
        applies is what this deliberately does not do; the note below tells the
        reader why nothing was suppressed.
        """
        self.write_config({"web": {}}, where=self.app)
        rc, out = self.validate(cwd=self.root)
        self.assertIn(TYPE_W, out)
        self.assertIn(NOTE, out)


if __name__ == "__main__":
    unittest.main()
