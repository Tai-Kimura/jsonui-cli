"""A spec page's component link points at the page this run writes, or at nothing.

Reported 2026-09-08 as the site's ONLY dangling link. The spec page emitted

    href="../../components/html/picker.html"

while the run wrote the page at `user/components/picker.html`.
Two spellings of one rule: the emitter reapplied the layout `generate spec`
uses (screens/html/ beside components/html/, where that path is right), and
the site generator writes `<app>/specs/` and `<app>/components/`, where it is
not.

It survived because the checks counted links. "links N" and "N links that
resolve to a real file" are different predicates, and only the second finds
this. The reporting face added the second one for the 1.8.50 unit back-links
and it came out on the first run — so these arms resolve every href against
the filesystem rather than string-matching it.

The emitter no longer knows the rule at all when the caller supplies the
pages: `_component_page_rel` is the single place that decides where a
component page goes, and the site generator hands the emitter the result. A
component with no page renders as text, because a link that resolves to
nothing claims a page exists.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.spec_doc.html_generator import generate_spec_html
from jsonui_doc_cli.test_doc.generator import (
    _component_page_rel, generate_html_directory)

HREF = re.compile(r"""href\s*=\s*(['"])(.*?)\1""", re.I | re.S)
NAV = re.compile(r"<nav\b.*?</nav>", re.I | re.S)


def body_of(html: str) -> str:
    """The page minus its shared nav.

    ⚠️ Both site arms below first scanned the WHOLE page and one of them
    passed under a deliberately broken emitter, because the shared nav
    carries a correct link to every component page. The nav is the same on
    every page and says nothing about THIS page's table. The reported defect
    is a body link, so the arms have to name that layer.
    """
    return NAV.sub("", html)

COMPONENT_FILE = "picker.component.json"


def _screen_with_component() -> dict:
    return {
        "type": "screen_spec", "version": "1.0",
        "metadata": {"screenName": "booking", "name": "Booking",
                     "displayName": "Booking", "description": "A screen."},
        "structure": {
            "components": [{"type": "View", "id": "root", "description": "r"}],
            "layout": {"root": "root", "children": []},
            "customComponents": [{
                "name": "Picker", "specFile": COMPONENT_FILE,
                "description": "Picks a range.",
            }],
        },
    }


def _component_spec() -> dict:
    return {
        "type": "component_spec", "version": "1.0",
        "metadata": {"name": "Picker", "displayName": "Picker",
                     "description": "Picks a range.", "category": "input"},
        "props": {},
        "structure": {
            "components": [{"type": "View", "id": "root", "description": "r"}],
            "layout": {"root": "root", "children": []},
        },
    }


class TheEmitterUsesThePagesItIsGiven(unittest.TestCase):
    """Unit level: what the table emits for each of the three states."""

    def _row(self, **kw) -> str:
        html = generate_spec_html(_screen_with_component(), **kw)
        m = re.search(r"<h3>Custom Components</h3>.*?</table>", html, re.S)
        self.assertIsNotNone(m, "the Custom Components table was not emitted")
        return m.group(0)

    def test_the_supplied_page_is_the_href(self):
        row = self._row(component_links={COMPONENT_FILE: "../components/picker.html"})
        self.assertIn('href="../components/picker.html"', row)

    def test_a_component_with_no_page_is_text_not_a_link(self):
        # ⚠️ The arm that separates this fix from "compute a different rule".
        # An implementation that always emits SOME href passes every other arm
        # here and fails only this one — and a link that resolves to nothing
        # is worse than no link, because it claims the page exists.
        row = self._row(component_links={})
        self.assertNotIn("<a ", row)
        self.assertIn(f"<code>{COMPONENT_FILE}</code>", row)

    def test_without_a_map_the_generate_spec_layout_is_unchanged(self):
        # The control. `generate spec` writes screens/html/ beside
        # components/html/, where the legacy relative path is correct, and the
        # docs-site face ships from that path. Changing it there would fix one
        # face by breaking another.
        row = self._row()
        self.assertIn('href="../../components/html/picker.html"', row)


class OneFunctionDecidesWhereAComponentPageGoes(unittest.TestCase):
    def test_the_app_prefix_and_the_subdirectory_both_reach_the_path(self):
        base = Path("/docs/user")
        self.assertEqual(
            _component_page_rel(base / "components/json/picker.component.json",
                                base / "components" / "json", "user"),
            "user/components/picker.html")
        self.assertEqual(
            _component_page_rel(base / "components/json/picker.component.json",
                                base / "components" / "json", None),
            "components/picker.html")
        self.assertEqual(
            _component_page_rel(base / "components/json/forms/picker.component.json",
                                base / "components" / "json", "user"),
            "user/components/forms/picker.html")


class TheSiteEmitsALinkThatResolves(unittest.TestCase):
    """End to end: the href must land on a file this run actually wrote."""

    def build(self) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "tests" / "screens").mkdir(parents=True)
        (root / "tests" / "screens" / "s.test.json").write_text(json.dumps({
            "type": "screen", "platform": "ios", "source": {"layout": "s"},
            "metadata": {"name": "s", "description": "d"},
            "cases": [{"name": "opens", "description": "opens",
                       "steps": [{"action": "tap", "id": "x"}]}],
        }), encoding="utf-8")
        (root / "jui.config.json").write_text(json.dumps({
            "spec_directory": "docs/user/screens/json",
            "platforms": {"ios": {"root": "ios", "unitTestsDir": "Tests",
                                  "testModule": "App"}},
        }), encoding="utf-8")
        user_docs = root / "docs" / "user"
        specs = user_docs / "screens" / "json"
        comps = user_docs / "components" / "json"
        specs.mkdir(parents=True)
        comps.mkdir(parents=True)
        (specs / "booking.spec.json").write_text(
            json.dumps(_screen_with_component()), encoding="utf-8")
        (comps / COMPONENT_FILE).write_text(
            json.dumps(_component_spec()), encoding="utf-8")
        out = root / "out"
        out.mkdir()
        generate_html_directory(
            root / "tests", out, "T",
            apps=[{"name": "user", "docs_path": str(user_docs)}])
        return out

    def test_the_component_link_resolves_to_a_generated_file(self):
        out = self.build()
        page = out / "user" / "specs" / "booking.html"
        self.assertTrue(page.is_file(), f"{page} was not generated")
        body = body_of(page.read_text(encoding="utf-8"))
        links = [m.group(2) for m in HREF.finditer(body)
                 if "components/" in m.group(2) and m.group(2).endswith(".html")]
        self.assertTrue(links, "the spec page emitted no component link at all")
        for h in links:
            resolved = Path(os.path.normpath(page.parent / h))
            self.assertTrue(
                resolved.is_file(),
                f"booking.html emits href={h!r} -> {resolved}, which this run "
                "never wrote. Counting the link finds nothing; resolving it "
                "is what found the reported defect.")

    def test_the_page_it_resolves_to_is_the_one_the_run_wrote(self):
        # Resolution alone would accept a link to SOME existing html file.
        out = self.build()
        page = out / "user" / "specs" / "booking.html"
        written = out / "user" / "components" / "picker.html"
        self.assertTrue(written.is_file(), "the component page itself is missing")
        resolved = {Path(os.path.normpath(page.parent / m.group(2)))
                    for m in HREF.finditer(body_of(page.read_text(encoding="utf-8")))
                    if "components/" in m.group(2) and m.group(2).endswith(".html")}
        self.assertIn(written, resolved)


if __name__ == "__main__":
    unittest.main()
