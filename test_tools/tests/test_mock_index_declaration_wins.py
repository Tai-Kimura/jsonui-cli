"""Regression: jui-stray-mock-file-outside-mockdir-hijacks-operationid-index.

The reference check ("does this test's `mocks` block name real operationIds?")
located its index by walking up from the test file and taking the first
`tests/mocks` or `mocks` directory it met. That walk cannot see a config which
is not an ancestor of the test file, and in a split tree — tests in one tree,
app and config in another — it never is.

So one stray `*.mock.json` in an ancestor directory replaced the entire index.
A consumer with a correct declared mockDir and 151 real mocks got 357 errors
from a single decoy file, with no way to switch it off: the reference check is
not the drift gate, so `--no-mock-check` does not reach it, and the `npm test`
that runs validate first stopped running any tests at all.

Two lanes hit it within an hour on the same shared checkout — one of them
reported it as a release regression, because the decoy appeared between two
runs that differed by a version. Measured against v1.6.51 and v1.6.53: the
behaviour is identical there. It predates the release it was blamed on.

A declaration outranks a search. The project said where its mocks are; a
directory found by convention is a guess about the same question.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_TOOL = Path(__file__).resolve().parents[1]

TEST_DOC = {
    "type": "screen",
    "source": {"layout": "test.json"},
    "metadata": {"name": "Fixture", "description": "Fixture screen test.",
                 "screen": "fixture"},
    "platform": "web",
    "mocks": {"get_items": "default"},
    "cases": [{"name": "renders", "description": "Root visible.",
               "steps": [{"assert": "visible", "id": "fixture_root"}]}],
}

SWAGGER = {
    "openapi": "3.0.3",
    "paths": {"/api/items": {"get": {"responses": {"200": {"content": {
        "application/json": {"schema": {"type": "object", "properties": {
            "id": {"type": "string"}}}}}}}}}},
}


def _mock(op_id: str) -> dict:
    return {"source": {"operationId": op_id, "method": "GET",
                       "path": "/api/items"},
            "activeScenario": "default",
            "scenarios": {"default": {"status": 200, "body": {"id": "x"}}}}


class DeclarationBeatsDiscoveryTests(unittest.TestCase):
    """Split tree: tests beside the repo root, app (config + mocks) elsewhere."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "tests" / "app").mkdir(parents=True)
        (self.root / "tests" / "app" / "s.test.json").write_text(
            json.dumps(TEST_DOC), encoding="utf-8")
        self.app = self.root / "app"
        (self.app / "tests" / "mocks").mkdir(parents=True)
        (self.app / "tests" / "mocks" / "get_items.mock.json").write_text(
            json.dumps(_mock("get_items")), encoding="utf-8")
        swagger = self.app / "swagger.json"
        swagger.write_text(json.dumps(SWAGGER), encoding="utf-8")
        (self.app / "jui.config.json").write_text(json.dumps(
            {"mock": {"swagger": [str(swagger)], "mockDir": "tests/mocks"}}),
            encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def put_decoy(self, where: Path):
        where.mkdir(parents=True, exist_ok=True)
        (where / "decoy.mock.json").write_text(json.dumps(_mock("zzz_decoy")),
                                               encoding="utf-8")

    def validate(self):
        proc = subprocess.run(
            [sys.executable, "-m", "jsonui_test_cli.cli", "validate",
             "../tests/app", "--no-install"],
            cwd=self.app, capture_output=True, text=True,
            env={"PYTHONPATH": str(REPO_TOOL), "PATH": "/usr/bin:/bin"})
        return proc.returncode, proc.stdout + proc.stderr

    def test_a_stray_mock_on_the_ancestry_does_not_hijack_the_index(self):
        """One decoy used to replace the whole index."""
        self.put_decoy(self.root / "mocks")
        rc, out = self.validate()
        self.assertNotIn("unknown mock operationId", out)
        self.assertIn("Result: PASSED", out)
        self.assertEqual(rc, 0, out)

    def test_the_same_holds_for_a_decoy_named_tests_mocks(self):
        self.put_decoy(self.root / "tests" / "mocks")
        rc, out = self.validate()
        self.assertNotIn("unknown mock operationId", out)
        self.assertEqual(rc, 0, out)

    def test_a_genuinely_unknown_operation_id_is_still_an_error(self):
        """The check has to keep working, not just stop complaining."""
        doc = dict(TEST_DOC, mocks={"get_nothing": "default"})
        (self.root / "tests" / "app" / "s.test.json").write_text(
            json.dumps(doc), encoding="utf-8")
        rc, out = self.validate()
        self.assertIn("unknown mock operationId 'get_nothing'", out)
        self.assertEqual(rc, 1, out)

    def test_an_unknown_scenario_is_still_an_error(self):
        doc = dict(TEST_DOC, mocks={"get_items": "no_such_scenario"})
        (self.root / "tests" / "app" / "s.test.json").write_text(
            json.dumps(doc), encoding="utf-8")
        rc, out = self.validate()
        self.assertIn("no scenario 'no_such_scenario'", out)
        self.assertEqual(rc, 1, out)


class NoDeclarationStillDiscoversTests(unittest.TestCase):
    """With nothing declared, the convention is all there is — keep it."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "tests" / "mocks").mkdir(parents=True)
        (self.root / "tests" / "mocks" / "get_items.mock.json").write_text(
            json.dumps(_mock("get_items")), encoding="utf-8")
        (self.root / "tests" / "s.test.json").write_text(
            json.dumps(TEST_DOC), encoding="utf-8")
        (self.root / "jui.config.json").write_text("{}", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_discovery_still_resolves_when_nothing_is_declared(self):
        proc = subprocess.run(
            [sys.executable, "-m", "jsonui_test_cli.cli", "validate", "tests",
             "--no-install"],
            cwd=self.root, capture_output=True, text=True,
            env={"PYTHONPATH": str(REPO_TOOL), "PATH": "/usr/bin:/bin"})
        out = proc.stdout + proc.stderr
        self.assertNotIn("unknown mock operationId", out)
        self.assertEqual(proc.returncode, 0, out)


class NormalLayoutAlsoLosesTests(unittest.TestCase):
    """Not a split-tree problem. A convention directory closer to the tests
    than the config beat the declaration in the ordinary layout too.

    The walk asks each level for a config first and a convention directory
    second, but `proj/tests/` has no config — so `proj/tests/mocks` was
    decided before `proj/jui.config.json` was ever read. Reported by the lane
    that measured five releases looking for a regression and found the
    behaviour identical in all of them.
    """

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "tests").mkdir()
        (self.root / "tests" / "s.test.json").write_text(
            json.dumps(TEST_DOC), encoding="utf-8")
        (self.root / "api-mocks").mkdir()
        (self.root / "api-mocks" / "get_items.mock.json").write_text(
            json.dumps(_mock("get_items")), encoding="utf-8")
        swagger = self.root / "swagger.json"
        swagger.write_text(json.dumps(SWAGGER), encoding="utf-8")
        (self.root / "jui.config.json").write_text(json.dumps(
            {"mock": {"swagger": [str(swagger)], "mockDir": "api-mocks"}}),
            encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_convention_dir_closer_than_the_config_does_not_win(self):
        (self.root / "tests" / "mocks").mkdir()
        (self.root / "tests" / "mocks" / "decoy.mock.json").write_text(
            json.dumps(_mock("zzz_decoy")), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-m", "jsonui_test_cli.cli", "validate", "tests",
             "--no-install"],
            cwd=self.root, capture_output=True, text=True,
            env={"PYTHONPATH": str(REPO_TOOL), "PATH": "/usr/bin:/bin"})
        out = proc.stdout + proc.stderr
        self.assertNotIn("unknown mock operationId", out)
        self.assertEqual(proc.returncode, 0, out)

    def test_the_error_names_the_directory_that_answered(self):
        """Which directory supplied the index is the whole question when the
        answer is wrong; the reporting lane needed four A/B runs to find it."""
        doc = dict(TEST_DOC, mocks={"get_nothing": "default"})
        (self.root / "tests" / "s.test.json").write_text(json.dumps(doc),
                                                          encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-m", "jsonui_test_cli.cli", "validate", "tests",
             "--no-install"],
            cwd=self.root, capture_output=True, text=True,
            env={"PYTHONPATH": str(REPO_TOOL), "PATH": "/usr/bin:/bin"})
        out = proc.stdout + proc.stderr
        self.assertIn("unknown mock operationId 'get_nothing'", out)
        self.assertIn(str((self.root / "api-mocks").resolve()), out)


if __name__ == "__main__":
    unittest.main()
