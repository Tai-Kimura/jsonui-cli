"""Regression: the mock gate not running has to look different from it passing.

Two reports, one shape. A docsite lane found `Orphan mocks: 0` printed by a
project with no mocks at all — the count comes from a path that returns 0
instead of None, so "did not look" printed the sentence "looked and found
none" prints. A second lane found the other half: 152 mock files carried for
six weeks with no `mock.swagger` declared, so the contract check never
started, and every gate stayed green.

Fixing only the count turns the false reassurance into silence, which is not
better — the 152 files are still unchecked and now nothing says so. Fixing
only the warning leaves the misleading zero in place for projects that lose
their mockDir. They are one defect seen from two sides.

`mock generate --check` cannot report either: it cannot start without the
declaration. The absence of a check is not detectable by that check, so it is
asked on `validate`, which runs either way.
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
    "metadata": {"name": "Fixture", "description": "Fixture screen test.",
                 "screen": "fixture"},
    "platform": "web",
    "cases": [{"name": "renders", "description": "Root visible.",
               "steps": [{"assert": "visible", "id": "fixture_root"}]}],
}

SWAGGER = {
    "openapi": "3.0.3",
    "paths": {"/api/items/{item_id}": {"get": {"responses": {"200": {
        "content": {"application/json": {"schema": {
            "type": "object", "properties": {"id": {"type": "string"}}}}}}}}}},
}


def _mock(path: str) -> dict:
    return {
        "source": {"operationId": "get_items", "method": "GET", "path": path},
        "activeScenario": "default",
        "scenarios": {"default": {"status": 200, "body": {"id": "string"}}},
    }


class MockGateAbsenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "tests").mkdir()
        (self.root / "tests" / "smoke.test.json").write_text(
            json.dumps(TEST_DOC), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def write_config(self, mock_section: dict | None):
        cfg: dict = {}
        if mock_section is not None:
            cfg["mock"] = mock_section
        (self.root / "jui.config.json").write_text(json.dumps(cfg),
                                                   encoding="utf-8")

    def add_mocks(self, n: int, path: str = "/api/items/{id}"):
        d = self.root / "tests" / "mocks"
        d.mkdir(exist_ok=True)
        for i in range(n):
            (d / f"m{i}.mock.json").write_text(json.dumps(_mock(path)),
                                               encoding="utf-8")

    def add_swagger(self):
        p = self.root / "swagger.json"
        p.write_text(json.dumps(SWAGGER), encoding="utf-8")
        return p

    def validate(self):
        proc = subprocess.run(
            [sys.executable, "-m", "jsonui_test_cli.cli", "validate", "tests"],
            cwd=self.root, capture_output=True, text=True,
            env={"PYTHONPATH": str(REPO_TOOL), "PATH": "/usr/bin:/bin"})
        return proc.returncode, proc.stdout + proc.stderr

    # ---- the count must not claim a clean result ---------------------- #

    def test_a_project_with_no_mocks_prints_no_orphan_count(self):
        self.write_config(None)
        rc, out = self.validate()
        self.assertEqual(rc, 0, out)
        self.assertIn("Result: PASSED", out)
        self.assertNotIn("Orphan mocks", out)

    def test_a_run_that_checked_still_prints_the_count(self):
        swagger = self.add_swagger()
        self.add_mocks(1)
        self.write_config({"swagger": [str(swagger)], "mockDir": "tests/mocks"})
        rc, out = self.validate()
        self.assertIn("Orphan mocks: 0", out)
        self.assertEqual(rc, 0, out)

    # ---- and silence must not be the whole answer --------------------- #

    def test_no_mock_block_at_all_is_the_reported_case(self):
        """The exact shape that prompted the ticket: 152 mocks, no `mock` block.

        The first draft counted through `mockDir`, so this — the one
        configuration the report was about — was the single case it stayed
        quiet for.
        """
        self.add_mocks(3)
        self.write_config(None)
        rc, out = self.validate()
        self.assertIn("3 mock file(s) were validated", out)
        self.assertIn("did not run", out)
        # Asked, not decided: serving mocks with no contract is a real setup.
        self.assertEqual(rc, 0, out)
        self.assertIn("Result: PASSED", out)

    def test_a_mockdir_without_a_swagger_is_reported(self):
        self.add_mocks(3)
        self.write_config({"mockDir": "tests/mocks"})
        rc, out = self.validate()
        self.assertIn("3 mock file(s) were validated", out)
        self.assertEqual(rc, 0, out)

    def test_an_unresolvable_swagger_is_reported_too(self):
        """Declared but pointing nowhere is the same blindness as undeclared."""
        self.add_mocks(2)
        self.write_config({"swagger": ["does/not/exist.json"],
                           "mockDir": "tests/mocks"})
        rc, out = self.validate()
        self.assertIn("2 mock file(s) were validated", out)
        self.assertIn("could be resolved", out)
        self.assertEqual(rc, 0, out)

    def test_a_project_with_no_mocks_says_nothing(self):
        """The false-positive boundary: no mocks, no config, no noise."""
        self.write_config(None)
        rc, out = self.validate()
        self.assertNotIn("mock file(s)", out)
        self.assertEqual(rc, 0, out)

    def test_a_configured_project_says_nothing(self):
        swagger = self.add_swagger()
        self.add_mocks(1)
        self.write_config({"swagger": [str(swagger)], "mockDir": "tests/mocks"})
        _rc, out = self.validate()
        self.assertNotIn("mock file(s)", out)


if __name__ == "__main__":
    unittest.main()
