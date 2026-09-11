"""`summary.scan` is the build's; a doc run's scan goes in `summary.run.scan`.

Reported 2026-09-11 from a three-face `--app` run: after each doc run exactly
one face's manifest showed a real build scan (29 roots / 1464 observed) and
the other two showed `[".", "docs"] / 0` — and which face it was changed
between runs. The doc producer wrote ITS scan (pages written under the face
root: none, `-o` was elsewhere) into the same slot the build uses, so a face
kept its build scan only if `jui build` had run after the last doc run. A
reader took `observed 0` as "scanned, nothing there" on a face with 677
tracked files.

The slot now belongs to the producer. Kill condition: the old `save` wrote
`claims["scan"]` unconditionally — the first arm's `summary.scan` would then
be the doc's.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
import tempfile

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "jui_tools"))

from jui_cli.core import generation_manifest as gm  # noqa: E402


class TestTheScanSlot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "app" / "Generated").mkdir(parents=True)
        (self.root / "app" / "Generated" / "A.swift").write_text("a\n")
        (self.root / "docs" / "x.html").parent.mkdir(parents=True, exist_ok=True)
        (self.root / "docs" / "x.html").write_text("<p>x</p>\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _build(self):
        run = gm.GenerationRun(project_root=self.root, version="b")
        run.observe([self.root / "app" / "Generated" / "A.swift"],
                    roots=[self.root / "app" / "Generated"])
        run.written([self.root / "app" / "Generated" / "A.swift"])
        return gm.save(run, generated_by="jui build")

    def _doc(self):
        run = gm.GenerationRun(project_root=self.root, version="d")
        run.observe_written(["docs/x.html"], roots=(self.root, self.root / "docs"))
        run.record_time("2026-09-11T00:00:00Z")
        return gm.save(run, generated_by="jsonui-doc generate html")

    def _saved(self):
        return json.loads(gm.manifest_path(self.root).read_text(encoding="utf-8"))

    def test_a_doc_run_after_a_build_keeps_the_builds_scan(self):
        self._build()
        build_scan = dict(self._saved()["summary"]["scan"])
        self.assertEqual(build_scan["roots"], ["app/Generated"])
        self._doc()
        s = self._saved()["summary"]
        self.assertEqual(s["scan"], build_scan, "the doc run overwrote the build's scan")
        self.assertEqual(s["run"]["scan"]["observed"], 1)
        self.assertEqual(s["run"]["scan"]["outsideDeclaredRoots"], 0)
        self.assertEqual(s["run"]["recordedBy"], "jsonui-doc generate html")

    def test_a_doc_run_with_no_prior_scan_writes_none_in_the_builds_slot(self):
        self._doc()
        s = self._saved()["summary"]
        self.assertNotIn("scan", s)
        self.assertIn("scan", s["run"])

    def test_a_build_after_a_doc_run_writes_its_own_and_carries_the_docs_block(self):
        self._doc()
        self._build()
        s = self._saved()["summary"]
        self.assertEqual(s["scan"]["roots"], ["app/Generated"])
        self.assertEqual(s["run"]["scan"]["observed"], 1)   # carried, untouched


if __name__ == "__main__":
    unittest.main()
