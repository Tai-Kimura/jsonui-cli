"""A parent's page says it is an index, and says where each section lives.

Reported 2026-09-04 by a lane that read four missing sections off a parent's
page as a defect and filed it: `dataFlow`, `stateManagement`, `userActions`
and `validation` appear on the sub-spec pages and nowhere on the parent's.

Measured cause: `document_tools` never imports `ParentSpecMerger` (0 hits;
control — jui_tools build/verify/generate and test_tools do import it). So
`jsonui-doc generate spec <parent>` renders the parent's own document plus an
index of its sub-specs. That is the intended shape, ruled (a) by both the
lane that filed it and the docsite lane that owns page conventions.

Neither chose a merged view, for the same reason: a parent page showing Data
Flow and Validation teaches a shape the tools REFUSE — the parent may not
declare those sections — and a second copy of each drifts from the first.

So the defect was never the missing sections. It was that nothing on the page
distinguished "these live elsewhere by design" from "these are missing", which
is the documentation form of the silence this whole cycle has been about.
Absence is only legible where the absence is.

Two conditions came with the ruling, and both are asserted here:
  1. the page states that behaviour lives in the sub-specs;
  2. the index says WHICH sections each sub-spec declares — without it the
     index cannot answer "which page is validation on?", which is the only
     question it exists to answer.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "document_tools"))

from jsonui_doc_cli.spec_doc.html_generator import generate_spec_html  # noqa: E402
from jsonui_doc_cli.spec_doc.markdown_generator import (  # noqa: E402
    generate_spec_markdown,
)

PARENT = {
    "type": "screen_parent_spec", "version": "1.0",
    "metadata": {"name": "P", "displayName": "P", "description": "d"},
    "subSpecs": [{"file": "p/basic.spec.json", "name": "Basic",
                  "description": "the basics"}],
    "structure": {"components": [], "layout": {}},
}
SUB = {
    "type": "screen_sub_spec", "metadata": {"name": "Basic"},
    "dataFlow": {}, "stateManagement": {}, "userActions": [], "validation": {},
    # bookkeeping — every spec has these, so they say nothing about what this
    # sub-spec contributes and must not crowd out the ones that do
    "notes": "n", "relatedFiles": ["a.swift"],
}


class ParentPageNamesItsShape(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "p").mkdir()
        (self.root / "p" / "basic.spec.json").write_text(
            json.dumps(SUB), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _pages(self):
        return {
            "html": generate_spec_html(PARENT, spec_dir=self.root),
            "markdown": generate_spec_markdown(PARENT, spec_dir=self.root),
        }

    def test_both_pages_say_behaviour_lives_in_the_sub_specs(self):
        for kind, page in self._pages().items():
            with self.subTest(kind):
                self.assertIn("split across the sub-specs", page)
                self.assertIn("may not declare those sections", page)

    def test_both_pages_list_the_sections_each_sub_spec_declares(self):
        for kind, page in self._pages().items():
            with self.subTest(kind):
                self.assertIn("Declares", page)
                for section in ("dataFlow", "stateManagement", "userActions",
                                "validation"):
                    self.assertIn(section, page, f"{kind} omits {section}")

    def test_bookkeeping_keys_are_not_listed_as_contributions(self):
        """`notes` and `relatedFiles` are on every spec.

        Listing them would pad the answer to "which page is validation on?"
        with keys that never distinguish one sub-spec from another.
        """
        for kind, page in self._pages().items():
            with self.subTest(kind):
                cell = page.split("Declares")[1]
                self.assertNotIn("relatedFiles", cell)

    def test_a_page_without_the_sub_spec_directory_still_renders(self):
        """`spec_dir` is optional and several callers do not have it.

        Degrading to an empty cell is deliberate: a WRONG list is worse than
        none when the cell's whole job is telling a reader where to look.
        """
        html = generate_spec_html(PARENT)
        md = generate_spec_markdown(PARENT)
        for page in (html, md):
            # The notice still stands — it needs no file access.
            self.assertIn("split across the sub-specs", page)
            # The COLUMN is gone, not blank. An empty cell under a `Declares`
            # heading asserts "this sub-spec declares nothing", which is a
            # wrong answer to the only question the index answers. Raised by
            # the docsite lane, which also measured that all four CLI call
            # sites do pass `spec_dir`, so this is reachable only from library
            # callers.
            self.assertNotIn("Declares", page)
            self.assertIn("Basic", page)

    def test_an_unsplit_screen_gets_no_index_and_no_notice(self):
        """Control. The notice must not appear on a screen that has no parts —
        it would tell the reader to look somewhere that does not exist."""
        plain = {"type": "screen_spec", "version": "1.0",
                 "metadata": {"name": "S", "displayName": "S", "description": "d"},
                 "structure": {"components": [], "layout": {}}}
        for page in (generate_spec_html(plain), generate_spec_markdown(plain)):
            self.assertNotIn("split across the sub-specs", page)
            self.assertNotIn("Sub Specifications", page)


if __name__ == "__main__":
    unittest.main()
