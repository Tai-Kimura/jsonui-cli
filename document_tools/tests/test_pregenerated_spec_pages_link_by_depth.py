"""The FOURTH `generate_spec_html` call site — `_pre_generate_spec_docs`.

Reported 2026-09-08 by a face whose specs include a nested one. That face's
site had exactly one dangling link out of six, and the shape separated
cleanly:

    pages directly in screens/html/   18 → all resolved
    pages in a subdirectory           1 → dangling

🚨 Why the v1.8.53 fix did not reach it: that fix wired `component_links` at
three of the four call sites of `generate_spec_html`, and this one passed
nothing — so the emitter fell back to its legacy `../../components/html/<name>`
template, which is right only for a page sitting directly in `screens/html/`.
`_component_page_rel`'s docstring said "both callers now read this"; there
were four. **Wiring one place and counting the places that need it are
different acts** — the same shape the release lane hit three times the same
day with `~/.jsonui-cli`-resident CLIs.

⚠️ Why a face with no nested spec could never catch it: `../../` happens to
be correct at depth 0. One face reported `link 13 / DANGLING 0` through this
very call site. A single-layout corpus keeps this call site green forever.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.test_doc.generator import _pre_generate_spec_docs


#: ⚠️ A REAL spec, not a stub. The first cut of this file omitted
#: `displayName`, `structure.layout` and `structure.components`; every page
#: failed validation, no HTML was written, and all four arms failed for a
#: reason that had nothing to do with the defect. A fixture simpler than the
#: report is a different specimen.
SPEC = {
    "type": "screen_spec",
    "version": "1.0",
    "metadata": {"name": "Pricing", "displayName": "Pricing",
                 "description": "d"},
    "structure": {
        "components": [{"type": "View", "id": "root", "description": "root"}],
        "layout": {"root": "root", "children": []},
        "customComponents": [
            {"name": "RangePicker",
             "specFile": "rangepicker.component.json",
             "description": "d"}],
    },
}
COMPONENT = {
    "type": "component_spec",
    "version": "1.0",
    "metadata": {"name": "RangePicker", "displayName": "Range Picker",
                 "description": "d", "category": "input"},
    "structure": {
        "components": [{"type": "View", "id": "root", "description": "root"}],
        "layout": {"root": "root", "children": []},
    },
}


class PreGeneratedPagesLinkByDepth(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.docs = Path(self._tmp.name).resolve() / "docs"
        (self.docs / "screens" / "json" / "catalog").mkdir(parents=True)
        (self.docs / "components" / "json").mkdir(parents=True)
        (self.docs / "components" / "json" / "rangepicker.component.json"
         ).write_text(json.dumps(COMPONENT), encoding="utf-8")
        # depth 0 and depth 1, in one corpus: a fix that only counts `../`
        # cannot satisfy both.
        (self.docs / "screens" / "json" / "listing.spec.json"
         ).write_text(json.dumps(SPEC), encoding="utf-8")
        (self.docs / "screens" / "json" / "catalog"
         / "catalog-pricing.spec.json"
         ).write_text(json.dumps(SPEC), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _href(self, page: Path) -> str | None:
        text = page.read_text(encoding="utf-8")
        for part in text.split('href="')[1:]:
            href = part.split('"')[0]
            if href.endswith("rangepicker.html"):
                return href
        return None

    def test_the_nested_page_gets_one_more_dot_dot(self):
        """The defect, at the depth that exposes it."""
        _pre_generate_spec_docs(self.docs)
        page = (self.docs / "screens" / "html" / "catalog"
                / "catalog-pricing.html")
        href = self._href(page)
        self.assertEqual("../../../components/html/rangepicker.html", href,
                         "a page one directory deep needs three `../`; the "
                         "legacy template hard-codes two")

    def test_the_top_level_page_is_unchanged(self):
        """The control. The old template was RIGHT at depth 0, and a fix that
        breaks it would trade one face's dangling link for every other
        face's."""
        _pre_generate_spec_docs(self.docs)
        page = self.docs / "screens" / "html" / "listing.html"
        self.assertEqual("../../components/html/rangepicker.html",
                         self._href(page))

    def test_every_link_resolves_on_disk(self):
        """⚠️ The arms above compare strings. This one RESOLVES them, which is
        the property the reporting face actually measured — their check
        counted links rather than resolving them, and that is why the dangling
        one survived a release."""
        _pre_generate_spec_docs(self.docs)
        pages = sorted((self.docs / "screens" / "html").rglob("*.html"))
        self.assertEqual(2, len(pages), pages)
        for page in pages:
            href = self._href(page)
            self.assertIsNotNone(href, f"{page} has no component link")
            self.assertTrue((page.parent / href).resolve().is_file(),
                            f"{page.name}: {href} resolves to "
                            f"{(page.parent / href).resolve()}, which does not exist")

    def test_no_link_escapes_the_docs_tree(self):
        """The leak shape, asserted here too: these pages are written INTO the
        source tree, so a link that climbs out of it names the checkout."""
        _pre_generate_spec_docs(self.docs)
        for page in sorted((self.docs / "screens" / "html").rglob("*.html")):
            href = self._href(page)
            resolved = (page.parent / href).resolve()
            self.assertTrue(str(resolved).startswith(str(self.docs)),
                            f"{page.name}: {href} -> {resolved} leaves {self.docs}")


if __name__ == "__main__":
    unittest.main()
