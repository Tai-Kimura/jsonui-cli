"""Every unit page is reachable from its specs, and counted once written.

Two defects this pins, both found by A/B against a real corpus rather than by
the unit tests that existed at the time — which is why the assertions here are
about the generated TREE, not about a function's return value.

1. A split screen's pages carried no link. The contracts are declared in the
   SUB-specs and read through the merged parent, so the target is recorded
   against the parent's screen name: the parent's own file has no
   `unitContracts` key at all, and the sub-spec's stem is not a screen
   anything was recorded against. Both pages missed, for opposite reasons,
   and a flat spec linked fine — so nothing smaller than a nested fixture
   could see it.

2. Unit pages were written and not counted. `Generated N HTML files` exists to
   answer "did everything come out?", and a page outside the counter makes the
   printed number smaller than the tree. That is the exact defect the counter
   was introduced to fix, reintroduced by adding pages through a different
   door.

The link assertions resolve the href against the filesystem rather than
matching a string: a wrong relative depth and a missing link are different
bugs, and only resolution tells them apart.
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


def _screen_spec(name: str, target: str | None = None) -> dict:
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
            "cases": [{"name": "doesThing", "intent": "does", "platforms": ["ios"]}],
        }
    return spec


class _Site(unittest.TestCase):
    def build(self, *, split: bool, flat_target: str | None) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        specs = root / "docs" / "screens" / "json"
        specs.mkdir(parents=True)
        (root / "tests" / "screens").mkdir(parents=True)
        (root / "ios" / "Tests").mkdir(parents=True)
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

        if flat_target:
            (specs / "flat.spec.json").write_text(
                json.dumps(_screen_spec("flat", flat_target)), encoding="utf-8")
        if split:
            (specs / "chat.spec.json").write_text(json.dumps({
                "type": "screen_parent_spec", "version": "1.0",
                "metadata": {"screenName": "chat", "name": "Chat",
                             "displayName": "Chat", "description": "Parent."},
                "subSpecs": [{"name": "chat-core", "file": "chat/chat-core.spec.json",
                              "description": "core"}],
            }), encoding="utf-8")
            (specs / "chat").mkdir()
            (specs / "chat" / "chat-core.spec.json").write_text(
                json.dumps(_screen_spec("chat-core", "ChatHandler")), encoding="utf-8")

        for t in filter(None, [flat_target, "ChatHandler" if split else None]):
            (root / "ios" / "Tests" / f"{t}ContractTests.swift").write_text(
                "import XCTest\n@testable import App\n"
                f"final class {t}ContractTests: XCTestCase {{ func test_doesThing() throws {{}} }}\n",
                encoding="utf-8")

        out = root / "out"
        out.mkdir()
        generate_html_directory(root / "tests", out, "T", project_root=root)
        return out

    def assert_links_to(self, page: Path, target_name: str):
        self.assertTrue(page.is_file(), f"{page} was not generated")
        m = re.search(rf'href="([^"]*unit/{target_name}\.html)"',
                      page.read_text(encoding="utf-8"))
        self.assertIsNotNone(m, f"{page.name} has no link to {target_name}")
        resolved = Path(os.path.normpath(page.parent / m.group(1)))
        self.assertTrue(resolved.is_file(),
                        f"{page.name} links to {m.group(1)}, which resolves to "
                        f"{resolved} — no such file (wrong relative depth)")


class SplitScreenReachability(_Site):
    def test_both_the_parent_and_the_sub_spec_link_to_the_unit_page(self):
        out = self.build(split=True, flat_target=None)
        self.assert_links_to(out / "specs" / "chat.html", "ChatHandler")
        self.assert_links_to(out / "specs" / "chat" / "chat-core.html", "ChatHandler")

    def test_a_flat_spec_links_too(self):
        # Control: the flat case worked before and must keep working, so a
        # regression here is distinguishable from the nested defect.
        out = self.build(split=False, flat_target="FlatHandler")
        self.assert_links_to(out / "specs" / "flat.html", "FlatHandler")

    def test_a_project_with_no_contracts_has_no_unit_links_anywhere(self):
        # Control on the other side: the link appears because contracts exist,
        # not because every spec page grew one.
        out = self.build(split=False, flat_target=None)
        for page in out.rglob("specs/**/*.html"):
            self.assertNotIn("unit-contract-link", page.read_text(encoding="utf-8"))


class PagesWrittenCount(_Site):
    def test_the_count_includes_the_unit_pages(self):
        out = self.build(split=True, flat_target="FlatHandler")
        on_disk = sorted(p for p in out.rglob("*.html"))
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
