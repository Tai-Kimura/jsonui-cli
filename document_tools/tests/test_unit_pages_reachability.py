"""Each spec page links to the target IT declares, and pages are counted.

Two defects found by A/B against a real corpus rather than by the unit tests
that existed at the time — which is why these assertions are about the
generated TREE, not about any function's return value.

1. A split screen's pages linked to the wrong target, or to none. Three keys
   were tried, and all three are one-to-many:

     by SCREEN     a split screen's cases are read through the merged parent,
                   so every target under it is recorded against the PARENT's
                   screen name — two targets, one key;
     by SPEC PATH  `UnitCase.spec_file` is the parent's path for every
                   sub-spec, measured — so again two targets, one key;
     by DIRECTORY  one directory holding two targets sends every page under
                   it to whichever was seen first. This one shipped: nine
                   pages pointed at a single arbitrary target, and the other
                   target was reachable from no spec at all.

   A file's own `unitContracts` block names its own target, and a sub-spec
   carries its block in its own file — so the page reads its own declaration
   and needs no map. The fixture therefore holds TWO targets in one directory
   plus a sibling declaring none; a fixture with one sub-spec is green under
   every one of the three broken keys.

2. Unit pages were written and not counted. `Generated N HTML files` answers
   "did everything come out?", and a page added through a different door makes
   the printed number smaller than the tree — the defect that counter exists
   to prevent.

Links are resolved against the filesystem rather than string-matched: a wrong
relative depth and a missing link are different bugs, and only resolution
tells them apart.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.test_doc.generator import (
    generate_html_directory,
    get_pages_written,
)


def _screen_spec(name: str, target: str | None) -> dict:
    spec = {
        "type": "screen_spec",
        "version": "1.0",
        "metadata": {"screenName": name, "name": "Scr", "displayName": "Scr",
                     "description": "A screen."},
        "structure": {"components": [{"type": "View", "id": "root", "description": "r"}],
                      "layout": {"root": "root", "children": []}},
    }
    if target:
        spec["unitContracts"] = {
            "target": target,
            "cases": [{"name": f"case_{target}", "intent": "does", "platforms": ["ios"]}],
        }
    return spec


class _Site(unittest.TestCase):
    #: sub-spec name -> the target it declares (None = declares none)
    SPLIT = {"chat-core": "ChatUserActionHandler",
             "chat-recommendation": "ChatRecommendationHandler",
             "chat-plain": None}

    def build(self, *, split: bool, flat_target: str | None) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        specs = root / "docs" / "screens" / "json"
        specs.mkdir(parents=True)
        (root / "tests" / "screens").mkdir(parents=True)
        tests_dir = root / "ios" / "Tests"
        tests_dir.mkdir(parents=True)
        (root / "jui.config.json").write_text(json.dumps({
            "spec_directory": "docs/screens/json",
            "platforms": {"ios": {"root": "ios", "unitTestsDir": "Tests",
                                  "testModule": "App"}},
        }), encoding="utf-8")
        (root / "tests" / "screens" / "s.test.json").write_text(json.dumps({
            "type": "screen", "platform": "ios", "source": {"layout": "s"},
            "metadata": {"name": "s", "description": "d"},
            "cases": [{"name": "opens", "description": "opens",
                       "steps": [{"action": "tap", "id": "x"}]}],
        }), encoding="utf-8")

        targets: list[str] = []
        if flat_target:
            (specs / "flat.spec.json").write_text(
                json.dumps(_screen_spec("flat", flat_target)), encoding="utf-8")
            targets.append(flat_target)
        if split:
            (specs / "chat.spec.json").write_text(json.dumps({
                "type": "screen_parent_spec", "version": "1.0",
                "metadata": {"screenName": "chat", "name": "Chat",
                             "displayName": "Chat", "description": "Parent."},
                "subSpecs": [{"name": n, "file": f"chat/{n}.spec.json",
                              "description": n} for n in sorted(self.SPLIT)],
            }), encoding="utf-8")
            (specs / "chat").mkdir()
            for name, target in self.SPLIT.items():
                (specs / "chat" / f"{name}.spec.json").write_text(
                    json.dumps(_screen_spec(name, target)), encoding="utf-8")
                if target:
                    targets.append(target)

        for t in targets:
            (tests_dir / f"{t}ContractTests.swift").write_text(
                "import XCTest\n@testable import App\n"
                f"final class {t}ContractTests: XCTestCase "
                f"{{ func test_case_{t}() throws {{}} }}\n", encoding="utf-8")

        out = root / "out"
        out.mkdir()
        generate_html_directory(root / "tests", out, "T", project_root=root)
        return out

    def links_of(self, page: Path) -> list[str]:
        """Target names this page links to, each proven to resolve on disk."""
        self.assertTrue(page.is_file(), f"{page} was not generated")
        found = []
        for href, target in re.findall(
                r'href="([^"]*unit/([A-Za-z0-9_]+)\.html)"',
                page.read_text(encoding="utf-8")):
            resolved = Path(os.path.normpath(page.parent / href))
            self.assertTrue(resolved.is_file(),
                            f"{page.name} links to {href}, resolving to "
                            f"{resolved} — no such file (wrong relative depth)")
            found.append(target)
        return found


class SplitScreenReachability(_Site):
    def test_each_sub_spec_links_to_the_target_it_declares(self):
        out = self.build(split=True, flat_target=None)
        self.assertEqual(self.links_of(out / "specs" / "chat" / "chat-core.html"),
                         ["ChatUserActionHandler"])
        self.assertEqual(
            self.links_of(out / "specs" / "chat" / "chat-recommendation.html"),
            ["ChatRecommendationHandler"])

    def test_two_targets_in_one_directory_do_not_share_a_link(self):
        # The defect that shipped: a directory-wide key gave every page under
        # chat/ the same target. Comparing the two pages catches it even if
        # both happen to resolve.
        out = self.build(split=True, flat_target=None)
        core = self.links_of(out / "specs" / "chat" / "chat-core.html")
        rec = self.links_of(out / "specs" / "chat" / "chat-recommendation.html")
        self.assertNotEqual(core, rec)

    def test_every_generated_target_is_reachable_from_some_spec(self):
        # The other half of the same defect: one target was linked from nine
        # pages while the other was linked from none.
        out = self.build(split=True, flat_target="FlatHandler")
        linked = set()
        for page in (out / "specs").rglob("*.html"):
            linked.update(self.links_of(page))
        have_pages = {p.stem for p in (out / "unit").glob("*.html")}
        self.assertEqual(have_pages - linked, set(),
                         f"targets with a page but no spec linking to it: "
                         f"{sorted(have_pages - linked)}")

    def test_the_parent_of_a_split_screen_declares_nothing_and_links_nothing(self):
        # The merger forbids the parent its own block, so the parent page has
        # no declaration to point at.
        out = self.build(split=True, flat_target=None)
        self.assertEqual(self.links_of(out / "specs" / "chat.html"), [])

    def test_a_sibling_declaring_no_contracts_gets_no_link(self):
        out = self.build(split=True, flat_target=None)
        self.assertEqual(self.links_of(out / "specs" / "chat" / "chat-plain.html"), [])

    def test_a_flat_spec_links_to_its_own_target(self):
        # Control: the flat case worked throughout, so a regression here is
        # distinguishable from the nested defect.
        out = self.build(split=False, flat_target="FlatHandler")
        self.assertEqual(self.links_of(out / "specs" / "flat.html"), ["FlatHandler"])

    def test_a_project_with_no_contracts_has_no_unit_links_anywhere(self):
        out = self.build(split=False, flat_target=None)
        for page in (out / "specs").rglob("*.html"):
            self.assertNotIn("unit-contract-link", page.read_text(encoding="utf-8"))


class PagesWrittenCount(_Site):
    def test_the_count_includes_the_unit_pages(self):
        out = self.build(split=True, flat_target="FlatHandler")
        on_disk = sorted(out.rglob("*.html"))
        self.assertTrue(any(p.parent.name == "unit" for p in on_disk),
                        "fixture wrote no unit pages, so this proves nothing")
        self.assertEqual(get_pages_written(), len(on_disk),
                         f"counter {get_pages_written()} vs {len(on_disk)} files: "
                         + ", ".join(p.name for p in on_disk))

    def test_the_count_matches_when_there_are_no_unit_pages(self):
        # Control: the equality is not an artefact of the unit pages, so a
        # future page written outside the counter fails here too.
        out = self.build(split=False, flat_target=None)
        self.assertEqual(get_pages_written(), len(list(out.rglob("*.html"))))


if __name__ == "__main__":
    unittest.main()
