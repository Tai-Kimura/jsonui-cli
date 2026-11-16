"""Regression: doc-generate-html-strips-the-producer-mark-it-never-writes.

Two commands write these files. `jsonui-doc generate spec` / `generate
component` stamp what they write, so a reader can ask "is this my own
output?". `generate html` regenerates the SAME files in the source tree,
for the root scope and for every ``--app`` — and had never stamped. Any
`generate html` run therefore stripped the marks the other command had put
there.

Measured on a consumer face 2026-09-09 after another lane's verification run
reached its tree: five html and one md lost their marks, and four newly
written md files carried none. `generator.py` contained `stamp_producer`
zero times, in v1.8.58 where the mark shipped and ever since; `cli.py`
contained it five times.

⚠️ NOT a regression of the release that exposed it — the state since the
mark was introduced, first seen the day a `generate html` run reached a tree
whose pages had been marked.

🔻 The arms are on THIS path specifically, not on "a mark exists somewhere".
An existence arm is satisfied by `generate spec`'s own output and stays green
while this path is broken, which is exactly how the defect survived two
releases.
"""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonui_doc_cli.cli import producer_mark, read_producer
from jsonui_doc_cli.test_doc import generate_html_directory
from test_document_page_links_and_writes_outside_output import (
    COMPONENT_FILE, _component_spec, _screen_spec,
)


class GenerateHtmlStampsItsSourceTreeWrites(unittest.TestCase):

    APP = "client"
    SCREEN = "settings"

    def _build(self) -> Path:
        """Run `generate html` over one app; return the app's docs root."""
        self._tmp = TemporaryDirectory()
        root = Path(self._tmp.name)
        tests_dir = root / "tests"
        (tests_dir / "screens").mkdir(parents=True)
        (tests_dir / "screens" / "s.test.json").write_text(json.dumps({
            "type": "screen", "version": "1.0",
            "source": {"layout": "s"},
            "metadata": {"name": "s", "description": "d"},
            "cases": [{"name": "opens", "description": "opens",
                       "steps": [{"action": "tap", "id": "x"}]}],
        }), encoding="utf-8")
        docs = root / "docs" / self.APP
        (docs / "screens" / "json").mkdir(parents=True)
        (docs / "components" / "json").mkdir(parents=True)
        (docs / "screens" / "json" / f"{self.SCREEN}.spec.json").write_text(
            json.dumps(_screen_spec(self.SCREEN, COMPONENT_FILE)), encoding="utf-8")
        (docs / "components" / "json" / COMPONENT_FILE).write_text(
            json.dumps(_component_spec()), encoding="utf-8")
        out = root / "out"
        out.mkdir()
        with redirect_stdout(io.StringIO()):
            generate_html_directory(
                tests_dir, out, "T",
                apps=[{"name": self.APP, "docs_path": str(docs)}])
        return docs

    def tearDown(self):
        tmp = getattr(self, "_tmp", None)
        if tmp is not None:
            tmp.cleanup()

    def test_the_pages_it_writes_outside_output_carry_the_mark(self):
        docs = self._build()
        pages = {
            "spec html": docs / "screens" / "html" / f"{self.SCREEN}.html",
            "spec md": docs / "screens" / "md" / f"{self.SCREEN}.md",
            "component html": docs / "components" / "html" / "picker.html",
            "component md": docs / "components" / "md" / "picker.md",
        }
        unmarked = []
        for label, page in pages.items():
            self.assertTrue(page.is_file(), f"{label} was not written: {page}")
            if read_producer(page) is None:
                unmarked.append(f"{label} ({page.name})")
        self.assertEqual([], unmarked, f"written by generate html, unmarked: {unmarked}")

    def test_the_mark_survives_a_run_over_an_already_marked_tree(self):
        """The property is that the mark is not REMOVED, not that one exists.

        ⚠️ A pre-marked file is what the reporting face had: pages written by
        `generate component`, then overwritten by a `generate html` run. If
        this path stops stamping, the overwrite silently drops the mark and
        nothing fails — the file is still valid, still current, and now
        answers "who wrote this?" with "no idea".
        """
        docs = self._build()
        page = docs / "components" / "html" / "picker.html"
        self.assertIsNotNone(read_producer(page))
        # Overwrite the way the other command would have, then run again.
        marked = producer_mark("component", ".html")
        page.write_text(f"<html><head>\n    {marked}</head><body>old</body></html>",
                        encoding="utf-8")
        self.assertIsNotNone(read_producer(page))
        with redirect_stdout(io.StringIO()):
            generate_html_directory(
                Path(self._tmp.name) / "tests", Path(self._tmp.name) / "out", "T",
                apps=[{"name": self.APP, "docs_path": str(docs)}])
        self.assertIsNotNone(
            read_producer(page),
            "a generate html run over a marked tree removed the mark")

    def test_the_family_matches_the_other_command_so_it_is_not_a_collision(self):
        """A second spelling would read as ANOTHER producer's output.

        The check reads the first mark it finds and compares by FAMILY, so a
        mark naming this path rather than the family would turn every page
        this writes into a false collision — the one v1.8.59 removed.
        """
        docs = self._build()
        self.assertEqual(
            read_producer(docs / "components" / "html" / "picker.html"),
            "jsonui-doc:component")
        self.assertEqual(
            read_producer(docs / "screens" / "html" / f"{self.SCREEN}.html"),
            "jsonui-doc:spec")


if __name__ == "__main__":
    unittest.main()
