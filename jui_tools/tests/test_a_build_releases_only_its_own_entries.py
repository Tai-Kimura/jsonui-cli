"""`jui build` releases only the entries `jui build` recorded.

Reported 2026-09-29 (jui-build-releases-doc-run-entries-from-shared-manifest):
on a face that runs `jsonui-doc generate html` inside its own root, the doc
run recorded 238 pages in `files`, and the next `jui build` released all 238
as "left the tracked set" — their files still there — because the build's
`present` is the build's scan and never contains the doc run's pages. The next
doc run put them back. The face tracks its manifest, so ~1200 lines flipped
on every alternation, and each build printed 238 releases of nothing.

`summary.scan` / `summary.run.scan` were split per producer on 2026-09-11;
`files` is one table, and the prune now asks who wrote each entry.
Kill condition: the 1.9.4 prune (`files = {k: v … if k in present}`) fails the
first arm — the alternation moves the file.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "jui_tools"))

from jui_cli.core import generation_manifest as gm  # noqa: E402

DOC = "jsonui-doc generate html"


class TestTheBuildReleasesOnlyItsOwnEntries(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.gen = self.root / "app" / "Generated"
        self.gen.mkdir(parents=True)
        for i in range(3):
            (self.gen / f"A{i}.swift").write_text("a\n")
        self.pages = self.root / "docs" / "html"
        self.pages.mkdir(parents=True)
        for i in range(5):
            (self.pages / f"p{i}.html").write_text("<p/>\n")
        # A pinned clock: the arm measures the table, not the stamp.
        self.env = mock.patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "1790000000"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def _build(self):
        run = gm.GenerationRun(project_root=self.root, version="b")
        files = sorted(self.gen.iterdir())
        run.observe(files, roots=[self.gen])
        run.written(files)
        gm.save(run, generated_by="jui build")
        return run

    def _doc(self):
        run = gm.GenerationRun(project_root=self.root, version="d")
        run.observe_written(sorted(f"docs/html/{p.name}" for p in self.pages.iterdir()),
                            roots=(self.root, self.root / "docs"))
        run.record_time("2026-09-29T00:00:00Z")
        gm.save(run, generated_by=DOC)
        return run

    def _text(self):
        return gm.manifest_path(self.root).read_text(encoding="utf-8")

    def _saved(self):
        return json.loads(self._text())

    def test_alternating_producers_leave_the_file_unchanged(self):
        self._build()
        self._doc()
        after_doc = self._text()
        self.assertEqual(len(self._saved()["files"]), 8)   # the premise: both recorded
        run = self._build()
        self.assertEqual(run.untracked, [], "the build released the doc run's pages")
        self.assertEqual(self._text(), after_doc, "a build after a doc run moved the file")
        self._doc()
        self.assertEqual(self._text(), after_doc, "a doc run after a build moved the file")

    def test_the_doc_run_s_entries_count_in_the_build_s_tracked(self):
        self._doc()
        self._build()
        s = self._saved()["summary"]
        # Not 3: `tracked` would otherwise flip 3 ↔ 8 between the producers.
        self.assertEqual(s["tracked"], 8)
        self.assertEqual(s["recorded"], 8)
        self.assertEqual(s["untracked"], 0)
        self.assertEqual(s["trackedByDirectory"], {"docs": 5, "app": 3})

    def test_a_doc_page_whose_file_is_gone_is_still_dropped_by_the_build(self):
        """The boundary on the other side: ownership keeps an entry only while
        its file exists. The doc run has no `present` and never prunes, so a
        deleted page would otherwise stay in the record forever."""
        self._doc()
        (self.pages / "p0.html").unlink()
        run = self._build()
        self.assertEqual(run.dropped, ["docs/html/p0.html"])
        self.assertNotIn("docs/html/p0.html", self._saved()["files"])
        self.assertIn("docs/html/p1.html", self._saved()["files"])

    def test_the_build_still_releases_its_own_entries_that_left_its_scan(self):
        """The control: the prune still works for the producer that owns the
        entry — a constant "keep everything" would pass the arms above."""
        (self.gen / "Old.swift").write_text("x\n")
        self._build()                                # Old.swift recorded by the build
        self.assertIn("app/Generated/Old.swift", self._saved()["files"])
        # …and the next build's scan no longer lists it; the file stays.
        run2 = gm.GenerationRun(project_root=self.root, version="b")
        files = [p for p in sorted(self.gen.iterdir()) if p.name != "Old.swift"]
        run2.observe(files, roots=[self.gen])
        run2.written(files)
        gm.save(run2, generated_by="jui build")
        self.assertEqual(run2.untracked, ["app/Generated/Old.swift"])
        self.assertNotIn("app/Generated/Old.swift", self._saved()["files"])

    def test_an_unstamped_entry_is_the_build_s(self):
        """Entries written before `generatedBy` existed were the build's."""
        self._build()
        data = self._saved()
        # Outside the build's scan (so it leaves the tracked set) with its file
        # still there: unstamped, it must be released like the build's own.
        data["files"]["app/Legacy/L.swift"] = {"version": "1.8.0"}
        (self.root / "app" / "Legacy").mkdir()
        (self.root / "app" / "Legacy" / "L.swift").write_text("l\n")
        gm.manifest_path(self.root).write_text(json.dumps(data), encoding="utf-8")
        run = self._build()
        self.assertEqual(run.untracked, ["app/Legacy/L.swift"])


if __name__ == "__main__":
    unittest.main()
