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
    "source": {"layout": "test.json"},
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
        # The layout the fixture's `source` names. Declared paths are
        # resolved now, so a fixture that names a file it does not create
        # earns an unrelated warning and this file's assertions about the
        # summary line stop measuring the summary line.
        layouts = self.root / "docs" / "screens" / "layouts"
        layouts.mkdir(parents=True)
        (layouts / "test.json").write_text("{}", encoding="utf-8")

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

    def test_the_summary_line_alone_distinguishes_the_two_states(self):
        """A reader of the last line has to be able to tell them apart.

        `[WARN]` above the summary is not enough: `Warnings:` counts per-file
        findings, this one is project-level, so the summary printed
        `Files: N, Errors: 0, Warnings: 0` either way — byte-identical to a
        healthy project, and invisible to anyone grepping the last line. It
        gets its own field rather than joining `Warnings:`, which a project
        may be gating on.
        """
        self.add_mocks(2)
        self.write_config(None)
        _rc, out = self.validate()
        line = [l for l in out.splitlines() if l.startswith("Files:")][0]
        self.assertIn("Unchecked mocks: 2", line)
        self.assertIn("Warnings: 0", line)  # per-file count is untouched

        clean = MockGateAbsenceTests("test_a_project_with_no_mocks_says_nothing")
        clean.setUp()
        try:
            clean.write_config(None)
            _rc2, out2 = clean.validate()
            line2 = [l for l in out2.splitlines() if l.startswith("Files:")][0]
            self.assertNotIn("Unchecked mocks", line2)
        finally:
            clean.tearDown()

    def test_the_unchecked_count_does_not_gate(self):
        self.add_mocks(2)
        self.write_config(None)
        rc, out = self.validate()
        self.assertEqual(rc, 0, out)
        self.assertIn("Result: PASSED", out)

    def test_a_mockdir_without_a_swagger_is_reported(self):
        self.add_mocks(3)
        self.write_config({"mockDir": "tests/mocks"})
        rc, out = self.validate()
        self.assertIn("3 mock file(s) were validated", out)
        self.assertEqual(rc, 0, out)

    def test_an_unresolvable_mockdir_is_reported_without_a_count(self):
        """The rename case, and the one that actually happens.

        A lane moved its mocks between trees and rewrote `mockDir` the same
        day; one wrong character and the contract check for 190 files stops
        with every gate still green. `mockDir` declared and not resolving
        needs no discovery to detect — the project said where its mocks are.
        There is nothing to count, because they are wherever they were moved
        to, so the slot says so rather than staying empty.
        """
        self.add_mocks(2, )
        # Move them out of the validated path so nothing else can find them.
        moved = self.root / "elsewhere"
        (self.root / "tests" / "mocks").rename(moved)
        self.write_config({"mockDir": "tests/mocks"})
        rc, out = self.validate()
        self.assertIn("does not exist", out)
        line = [l for l in out.splitlines() if l.startswith("Files:")][0]
        self.assertIn("Unchecked mocks: unknown", line)
        self.assertEqual(rc, 0, out)
        self.assertIn("Result: PASSED", out)
        # Nothing was collected here, so there is no second sentence to add.
        self.assertNotIn("were collected", out)

    def test_an_unresolvable_mockdir_still_reports_what_it_did_collect(self):
        """When the mocks happen to sit under the validated path.

        The run collected and validated them, so their number is a fact it
        already has — an earlier version threw it away behind a comment
        claiming there was nothing to count. A lane whose mocks live under
        `tests/` measured `Files: 154` (2 tests + 152 mocks) against a warning
        that admitted to knowing nothing.

        Reported as a separate sentence, never as the count: the collected
        set is not known to be the set `mockDir` meant, and putting 152 in the
        slot would claim it is.
        """
        self.add_mocks(3)               # under tests/, i.e. inside the path
        self.write_config({"mockDir": "somewhere/else"})
        rc, out = self.validate()
        self.assertIn("does not exist", out)
        self.assertIn("3 .mock.json file(s) were collected", out)
        line = [l for l in out.splitlines() if l.startswith("Files:")][0]
        self.assertIn("Unchecked mocks: unknown", line)
        self.assertNotIn("Unchecked mocks: 3", line)
        self.assertEqual(rc, 0, out)

    def test_a_resolvable_mockdir_says_nothing_about_resolution(self):
        """The false-positive boundary for the check above."""
        swagger = self.add_swagger()
        self.add_mocks(1)
        self.write_config({"swagger": [str(swagger)], "mockDir": "tests/mocks"})
        _rc, out = self.validate()
        self.assertNotIn("does not exist", out)

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
        # "Nothing" means steady state. A hand-written mock's route now gets
        # a generated counterpart too (the overlay model — 1.7.22), so the
        # FIRST run after adding one legitimately reports a regeneration;
        # quiet is the property of the run after that.
        swagger = self.add_swagger()
        self.add_mocks(1)
        self.write_config({"swagger": [str(swagger)], "mockDir": "tests/mocks"})
        self.validate()
        _rc, out = self.validate()
        self.assertNotIn("mock file(s)", out)


if __name__ == "__main__":
    unittest.main()


class TestARebuildNamesWhatItPutBack:
    """The rebuild runs before the contract check, so what it restores is
    what the check will not report.

    A consumer deleted a generated scenario, got `Regenerated N mock
    file(s)` and `PASSED`, and could not tell from that output that the
    tree had been repaired underneath the check. The `mock contract:` line
    is true of the repaired tree, so nothing in the run reads as wrong.

    File counts answer "what did this run do". They do not answer "what did
    this run hide".
    """

    def _project(self, tmp_path):
        (tmp_path / "api.json").write_text(json.dumps({
            "openapi": "3.0.0", "info": {"title": "t", "version": "1"},
            "paths": {"/api/items": {"get": {
                "operationId": "listItems",
                "responses": {"200": {"content": {"application/json": {"schema": {
                    "type": "array",
                    "items": {"type": "object", "required": ["id"],
                              "properties": {"id": {"type": "string"}}}}}}}}}}},
        }), encoding="utf-8")
        (tmp_path / "jui.config.json").write_text(json.dumps(
            {"mock": {"swagger": ["api.json"], "mockDir": "tests/mocks"}}),
            encoding="utf-8")
        (tmp_path / "tests").mkdir()
        return tmp_path

    def _run(self, tmp_path, *args):
        import os
        import subprocess
        tree = str(Path(__file__).parent.parent)
        return subprocess.run(
            [sys.executable, "-m", "jsonui_test_cli.cli", *args],
            cwd=tmp_path, capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": tree})

    def test_a_restored_scenario_is_named(self, tmp_path):
        import os
        import time
        root = self._project(tmp_path)
        self._run(root, "mock", "generate")
        gen = next((root / "tests/mocks").rglob("*.mock.json"))
        data = json.loads(gen.read_text(encoding="utf-8"))
        data["scenarios"].pop("empty")
        gen.write_text(json.dumps(data, indent=2), encoding="utf-8")
        # age it so the freshness branch of the rebuild trigger fires
        old = time.time() - 10_000
        os.utime(gen, (old, old))

        out = self._run(root, "validate", "tests").stdout
        # WORDING CHANGED, and the change is a narrowing of a claim rather
        # than a weakening of this test. This branch has two causes that the
        # rebuild cannot tell apart: a scenario really was deleted (this
        # fixture), or the swagger grew a response and generation added one
        # (measured separately). The old sentence, "restored a scenario the
        # tree was missing", asserted the first for both — so on the second
        # it described a legitimate addition as a repair.
        #
        # What this test exists to pin is unchanged: the run must NAME what
        # came back rather than leave it to a file count. The sibling case
        # the old line could not reach at all — a whole file deleted, whose
        # key is absent from `before` — is covered in
        # `test_the_rebuild_says_what_it_repaired.py`.
        assert "generation added a scenario this file did not have" in out
        assert "empty" in out

    def test_an_untouched_tree_says_nothing_about_restoring(self, tmp_path):
        # The control. Without it, "restores are named" and "the line always
        # prints" are the same observation.
        root = self._project(tmp_path)
        self._run(root, "mock", "generate")
        out = self._run(root, "validate", "tests").stdout
        assert "restored a scenario" not in out
