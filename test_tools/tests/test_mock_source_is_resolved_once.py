"""Regression: the walk's bound must not be something a caller can forget.

v1.6.55 made a declared mockDir outrank the convention walk, which closed the
reported case — a project that declares where its mocks are. It left the other
half open. The bound on the walk was an optional argument, passed by the
unchecked-mock warning and by nothing else, so the three validators that run
the *reference* check (`screen`, `flow`, `step`) walked up from each test file
with no bound at all. A project that declares no mockDir therefore still had
that walk run to the filesystem root.

Measured before the fix, on a project with a `jui.config.json` and no `mock`
block, with one decoy `*.mock.json` one level above the project root:

    [ERROR] unknown mock operationId 'get_items' (not in .../outer/mocks)
    Result: FAILED

Same mechanism as the blocker v1.6.55 was written for, in the case v1.6.55 did
not cover. Six releases went into that argument's meaning (arrival vs
containment) and into how many places the walk should start; the defect was
the optionality, so the argument is gone. One `MockSource` is resolved once
per run and carries the directory, how it was chosen, and the bound — every
caller gets the bound because there is nowhere to not pass it.

Found by measurement rather than by a consumer report: the fourth occurrence
that `docs/plans/2026-08-28-mock-source-resolution-design.md` was written to
predict.
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
    "mocks": {"get_items": "default"},
    "cases": [{"name": "renders", "description": "Root visible.",
               "steps": [{"assert": "visible", "id": "fixture_root"}]}],
}


def _mock(op_id: str) -> dict:
    return {"source": {"operationId": op_id, "method": "GET",
                       "path": "/api/items"},
            "activeScenario": "default",
            "scenarios": {"default": {"status": 200, "body": {}}}}


class UndeclaredWalkStaysInTheProjectTests(unittest.TestCase):
    """No `mock` block at all — the case a declaration cannot bound."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.outer = Path(self._tmp.name)
        self.proj = self.outer / "proj"
        (self.proj / "tests").mkdir(parents=True)
        (self.proj / "tests" / "s.test.json").write_text(
            json.dumps(TEST_DOC), encoding="utf-8")
        (self.proj / "jui.config.json").write_text("{}", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def put(self, where: Path, op_id: str):
        where.mkdir(parents=True, exist_ok=True)
        (where / f"{op_id}.mock.json").write_text(json.dumps(_mock(op_id)),
                                                  encoding="utf-8")

    def validate(self):
        proc = subprocess.run(
            [sys.executable, "-m", "jsonui_test_cli.cli", "validate", "tests",
             "--no-install"],
            cwd=self.proj, capture_output=True, text=True,
            env={"PYTHONPATH": str(REPO_TOOL), "PATH": "/usr/bin:/bin"})
        return proc.returncode, proc.stdout + proc.stderr

    def test_a_decoy_above_the_project_root_does_not_supply_the_index(self):
        """The measured failure. `outer/` is not this project."""
        self.put(self.outer / "mocks", "zzz_decoy")
        rc, out = self.validate()
        self.assertNotIn("unknown mock operationId", out)
        self.assertNotIn(str(self.outer / "mocks"), out)
        self.assertEqual(rc, 0, out)

    def test_the_projects_own_mocks_are_still_found(self):
        """The bound must not cost the convention its reach."""
        self.put(self.proj / "mocks", "get_items")
        rc, out = self.validate()
        self.assertNotIn("unknown mock operationId", out)
        self.assertEqual(rc, 0, out)

    def test_an_in_project_dir_wins_over_a_decoy_above_it(self):
        self.put(self.proj / "mocks", "get_items")
        self.put(self.outer / "mocks", "zzz_decoy")
        rc, out = self.validate()
        self.assertNotIn("unknown mock operationId", out)
        self.assertEqual(rc, 0, out)

    def test_a_genuinely_unknown_id_is_still_an_error(self):
        """Bounding the walk must not turn the check off."""
        self.put(self.proj / "mocks", "get_something_else")
        rc, out = self.validate()
        self.assertIn("unknown mock operationId 'get_items'", out)
        self.assertEqual(rc, 1, out)


class ProvenanceIsInTheMessageTests(unittest.TestCase):
    """A wrong `mockDir` and a wrong guess print the same path.

    They are not the same thing to go and fix, so the message says which one
    answered — the same reason v1.6.55 put the resolved absolute path there
    instead of the literal `tests/mocks`.
    """

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "tests").mkdir()
        (self.root / "tests" / "s.test.json").write_text(
            json.dumps(TEST_DOC), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def put(self, where: Path, op_id: str):
        where.mkdir(parents=True, exist_ok=True)
        (where / f"{op_id}.mock.json").write_text(json.dumps(_mock(op_id)),
                                                  encoding="utf-8")

    def validate(self):
        proc = subprocess.run(
            [sys.executable, "-m", "jsonui_test_cli.cli", "validate", "tests",
             "--no-install"],
            cwd=self.root, capture_output=True, text=True,
            env={"PYTHONPATH": str(REPO_TOOL), "PATH": "/usr/bin:/bin"})
        return proc.stdout + proc.stderr

    def test_a_declared_directory_says_so(self):
        (self.root / "jui.config.json").write_text(
            json.dumps({"mock": {"mockDir": "api-mocks"}}), encoding="utf-8")
        self.put(self.root / "api-mocks", "get_something_else")
        out = self.validate()
        self.assertIn("declared by mock.mockDir", out)

    def test_a_discovered_directory_says_so(self):
        (self.root / "jui.config.json").write_text("{}", encoding="utf-8")
        self.put(self.root / "tests" / "mocks", "get_something_else")
        out = self.validate()
        self.assertIn("found by convention", out)

    def test_a_declared_dir_that_does_not_resolve_is_not_called_declared(self):
        """The run declared one and was answered by the other.

        Naming the declaration here would send the reader to a directory that
        did not supply the index.
        """
        (self.root / "jui.config.json").write_text(
            json.dumps({"mock": {"mockDir": "gone"}}), encoding="utf-8")
        self.put(self.root / "tests" / "mocks", "get_something_else")
        out = self.validate()
        self.assertIn("found by convention", out)
        self.assertNotIn("declared by mock.mockDir", out)


if __name__ == "__main__":
    unittest.main()
