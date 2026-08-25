"""Regression: the project boundary has to be asked, not waited for.

1.6.52 bounded the unconfigured-mock search with `stop_at`, implemented as
"break when the walk reaches this directory". That does nothing whenever the
boundary is not on the walk's path — and a project whose tests live in a
different tree from its config is exactly that shape:

    tests/<app>/screens/*.test.json     <- validated path
    <app>/jui.config.json               <- boundary
    <app>/tests/mocks/                  <- the real mocks

Walking up from the test file never passes through `<app>/`, so the break
never fired and the walk ran to the filesystem root. Measured on that layout
with a decoy `mocks/` two levels up: it reported nine mock files belonging to
no project at all — the exact false positive the boundary was added to
prevent, reintroduced for the one layout the feature was written for.

A consumer lane predicted the missing detection from its own silence and
said so as an untested hypothesis. The unbounded walk was found by measuring
it.
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

MOCK = {
    "source": {"operationId": "get_items", "method": "GET", "path": "/api/x"},
    "activeScenario": "default",
    "scenarios": {"default": {"status": 200, "body": {}}},
}


class SplitTreeBoundaryTests(unittest.TestCase):
    """Tests in one tree, config and mocks in another."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.tests = self.root / "tests" / "admin" / "screens"
        self.tests.mkdir(parents=True)
        (self.tests / "s.test.json").write_text(json.dumps(TEST_DOC),
                                                encoding="utf-8")
        self.app = self.root / "admin"
        (self.app / "tests" / "mocks").mkdir(parents=True)
        (self.app / "jui.config.json").write_text("{}", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def put_mocks(self, directory: Path, n: int):
        directory.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            (directory / f"m{i}.mock.json").write_text(json.dumps(MOCK),
                                                       encoding="utf-8")

    def validate(self):
        proc = subprocess.run(
            [sys.executable, "-m", "jsonui_test_cli.cli", "validate",
             "../tests/admin"],
            cwd=self.app, capture_output=True, text=True,
            env={"PYTHONPATH": str(REPO_TOOL), "PATH": "/usr/bin:/bin"})
        return proc.returncode, proc.stdout + proc.stderr

    def test_it_does_not_reach_out_of_the_project(self):
        """The bug: a decoy outside the boundary was reported as this
        project's unchecked mocks."""
        self.put_mocks(self.app / "tests" / "mocks", 3)   # in bounds
        self.put_mocks(self.root / "mocks", 9)            # OUT of bounds
        rc, out = self.validate()
        self.assertNotIn("Unchecked mocks", out)
        self.assertNotIn("9 mock file(s)", out)
        self.assertEqual(rc, 0, out)

    def test_a_decoy_alone_is_not_reported_either(self):
        self.put_mocks(self.root / "mocks", 4)
        _rc, out = self.validate()
        self.assertNotIn("Unchecked mocks", out)

    def test_the_silence_is_a_known_limit_not_a_claim(self):
        """Mocks inside the boundary but off the test file's ancestry are
        still not found. Documented, and silent — never `Unchecked mocks: 0`,
        which would turn "did not find" into "counted none"."""
        self.put_mocks(self.app / "tests" / "mocks", 3)
        _rc, out = self.validate()
        self.assertNotIn("Unchecked mocks: 0", out)
        self.assertIn("Result: PASSED", out)


class SameTreeStillWorksTests(unittest.TestCase):
    """The layout the feature was written for must keep firing."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "tests" / "mocks").mkdir(parents=True)
        (self.root / "tests" / "s.test.json").write_text(json.dumps(TEST_DOC),
                                                         encoding="utf-8")
        for i in range(2):
            (self.root / "tests" / "mocks" / f"m{i}.mock.json").write_text(
                json.dumps(MOCK), encoding="utf-8")
        (self.root / "jui.config.json").write_text("{}", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_mocks_on_the_ancestry_inside_the_boundary_are_found(self):
        proc = subprocess.run(
            [sys.executable, "-m", "jsonui_test_cli.cli", "validate", "tests"],
            cwd=self.root, capture_output=True, text=True,
            env={"PYTHONPATH": str(REPO_TOOL), "PATH": "/usr/bin:/bin"})
        out = proc.stdout + proc.stderr
        self.assertIn("Unchecked mocks: 2", out)
        self.assertEqual(proc.returncode, 0, out)


if __name__ == "__main__":
    unittest.main()
