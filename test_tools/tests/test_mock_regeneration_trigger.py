"""Regression: jui-mock-regeneration-trigger-is-swagger-mtime-only.

Originally: `generated/` was a function of the swagger AND of which
operations a hand-written mock had taken over, and the rebuild trigger only
watched the swagger's mtime — so adopting an operation by hand left its
generated copy behind until the schema next changed, and `Files:` moved for
a reason unrelated to the edit.

Since the overlay model (1.7.22) the second input is gone: a hand-written
mock overlays its generated counterpart instead of retiring it, so
`generated/` is a pure function of the swagger alone. The trigger itself
still matters — a stale or partial generated tree must be rebuilt when the
swagger is newer — and the hand-written-mtime input is kept because
adoption still changes what `validate` must re-examine (the overlay union).
"""

from __future__ import annotations

import json
import os
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jsonui_test_cli.cli import _regenerate_stale_mocks  # noqa: E402
from jsonui_test_cli.mock.generate import GENERATED_DIR, generate  # noqa: E402

SPEC = {
    "openapi": "3.0.3",
    "paths": {
        "/api/items": {"get": {"responses": {"200": {"content": {
            "application/json": {"schema": {"type": "array", "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}}}}}}}}}},
        "/api/items/{item_id}": {"get": {"responses": {"200": {"content": {
            "application/json": {"schema": {
                "type": "object",
                "properties": {"id": {"type": "string"}}}}}}}}},
    },
}


class RegenerationTriggerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.spec = self.root / "swagger.json"
        self.spec.write_text(json.dumps(SPEC), encoding="utf-8")
        self.mocks = self.root / "tests" / "mocks"
        self.mocks.mkdir(parents=True)
        (self.root / "jui.config.json").write_text(json.dumps(
            {"mock": {"swagger": [str(self.spec)], "mockDir": "tests/mocks"}}),
            encoding="utf-8")
        self.config = self.root / "jui.config.json"
        generate([str(self.spec)], self.mocks)

    def tearDown(self):
        self._tmp.cleanup()

    def generated(self) -> list[str]:
        root = self.mocks / GENERATED_DIR
        return sorted(p.name for p in root.rglob("*.mock.json"))

    def adopt_one(self) -> str:
        """Move one generated mock out to the hand-written tree."""
        src = sorted((self.mocks / GENERATED_DIR).rglob("*.mock.json"))[0]
        dst = self.mocks / src.name
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        # mtime resolution: make the adoption unambiguously newer.
        future = time.time() + 2
        os.utime(dst, (future, future))
        return src.name

    def test_adopting_an_operation_keeps_its_generated_copy(self):
        """RULING CHANGE (1.7.22). This test pinned retirement: adopting an
        operation removed its generated copy, making generated/ a function
        of the swagger AND the hand-written tree. Under the overlay model
        the hand-written file overlays the generated one per scenario, so
        the generated copy is the supply of routine scenarios and must
        STAY. generated/ is a pure function of the swagger alone again —
        the simpler contract the module docstring originally wanted.
        """
        before = self.generated()
        self.assertEqual(len(before), 2, before)
        name = self.adopt_one()
        self.assertEqual(_regenerate_stale_mocks(str(self.config)), 0)
        after = self.generated()
        self.assertIn(name, after)
        self.assertEqual(len(after), 2, after)

    def test_an_untouched_tree_does_not_rebuild(self):
        """Normal work must stay quiet, or every run pays for a rebuild."""
        root = self.mocks / GENERATED_DIR
        stamps = {p: p.stat().st_mtime_ns for p in root.rglob("*.mock.json")}
        self.assertEqual(_regenerate_stale_mocks(str(self.config)), 0)
        for p, was in stamps.items():
            self.assertEqual(p.stat().st_mtime_ns, was, p)

    def test_a_newer_swagger_still_triggers(self):
        """The original trigger must keep working. (Reworked for the
        overlay model: adoption no longer removes anything, so the missing
        file is made by hand — a partial tree is still what a stale
        checkout looks like.)"""
        name = self.generated()[0]
        removed = next((self.mocks / GENERATED_DIR).rglob(name))
        removed.unlink()
        future = time.time() + 4
        os.utime(self.spec, (future, future))
        self.assertEqual(_regenerate_stale_mocks(str(self.config)), 0)
        self.assertIn(name, self.generated())


if __name__ == "__main__":
    unittest.main()
