"""The index's denominator describes the RUN, not one of its apps.

The line was added so a zero could not be mistaken for "nothing to find". On a
multi-app site it did the opposite: it kept the first app's summary it saw, so
a site whose alphabetically-first app declared nothing rendered

    Unit Targets 5
    unit contracts: 0 case(s) declared across 18 spec file(s) scanned (0 …)

four lines apart on one page. Whichever number a reader trusted, the page
disagreed with itself, and the zero was the more believable of the two because
it came with a denominator.

Pinned here:

* the aggregate is what the `<p>` denominator says, and it matches the closing
  line on stdout — the two are read by the same person minutes apart;
* one app's numbers never stand alone as THE denominator;
* with more than one app, each app still gets its own line, because "the run
  read 141 files" does not tell you which app is the empty one;
* a single-app site renders exactly what it rendered before — one line, no
  list.

The fixture is built so aggregate and per-app numbers differ: app `aaa` sorts
first and declares nothing, app `zzz` sorts last and declares one. A fixture
where every app declares the same amount is green under the bug.
"""
from __future__ import annotations

import contextlib
import io
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.test_doc.generator import (
    generate_html_directory,
    generation_summary_line,
)


def _spec(screen: str, target: str | None) -> dict:
    spec = {
        "type": "screen_spec", "version": "1.0",
        "metadata": {"screenName": screen, "name": "S", "displayName": "S",
                     "description": "d."},
        "structure": {"components": [{"type": "View", "id": "root",
                                      "description": "r"}],
                      "layout": {"root": "root", "children": []}},
    }
    if target:
        spec["unitContracts"] = {
            "target": target,
            "cases": [{"name": "c1", "intent": "i", "platforms": ["ios"]}]}
    return spec


class _Site(unittest.TestCase):
    def build(self, apps: dict[str, str | None]) -> tuple[Path, str]:
        """*apps* maps app name -> the target it declares (None = declares none)."""
        root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "tests" / "screens").mkdir(parents=True)
        (root / "tests" / "screens" / "s.test.json").write_text(json.dumps({
            "type": "screen", "platform": "ios", "source": {"layout": "s"},
            "metadata": {"name": "s", "description": "d"},
            "cases": [{"name": "o", "description": "o",
                       "steps": [{"action": "tap", "id": "x"}]}]}), encoding="utf-8")

        app_args, roots = [], []
        for name, target in apps.items():
            base = root / name
            (base / "docs" / "screens" / "json").mkdir(parents=True)
            (base / "ios" / "Tests").mkdir(parents=True)
            (base / "jui.config.json").write_text(json.dumps({
                "spec_directory": "docs/screens/json",
                "platforms": {"ios": {"root": "ios", "unitTestsDir": "Tests",
                                      "testModule": "App"}}}), encoding="utf-8")
            (base / "docs" / "screens" / "json" / "s.spec.json").write_text(
                json.dumps(_spec(f"s_{name}", target)), encoding="utf-8")
            if target:
                (base / "ios" / "Tests" / f"{target}ContractTests.swift").write_text(
                    "import XCTest\n@testable import App\n"
                    f"final class {target}ContractTests: XCTestCase "
                    "{ func test_c1() throws {} }\n", encoding="utf-8")
            app_args.append({"name": name, "docs_path": base / "docs"})
            roots.append({"app": name, "root": base})

        out = root / "out"
        out.mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            generate_html_directory(root / "tests", out, "T",
                                    apps=app_args, unit_roots=roots)
        return out, (out / "index.html").read_text(encoding="utf-8")

    def denominator(self, html: str) -> str:
        m = re.search(r"<p class='denominator'>(.*?)</p>", html, re.S)
        self.assertIsNotNone(m, "no denominator line on the index")
        return m.group(1)

    def per_app_lines(self, html: str) -> list[str]:
        block = re.search(r"<ul class='denominator'>(.*?)</ul>", html, re.S)
        if not block:
            return []
        return re.findall(r"<li>(.*?)</li>", block.group(1), re.S)


class MultiApp(_Site):
    #: aaa sorts first and declares nothing; zzz sorts last and declares one.
    APPS = {"aaa": None, "zzz": "ZetaHandler"}

    def test_the_denominator_is_the_run_not_one_app(self):
        _, html = self.build(self.APPS)
        line = self.denominator(html)
        self.assertIn("1 case(s) declared across 2 spec file(s) scanned", line)
        self.assertIn("(1 spec file(s) carrying", line)

    def test_the_empty_apps_numbers_are_not_the_denominator(self):
        # The exact shape reported: one app's zero standing as the whole run's.
        _, html = self.build(self.APPS)
        self.assertNotIn("0 case(s) declared across 1 spec file(s) scanned",
                         self.denominator(html))

    def test_the_denominator_agrees_with_the_closing_line(self):
        # Same run, two places a reader looks minutes apart. They are built
        # from the same totals, so disagreement here means one of them is
        # reading a subset.
        _, html = self.build(self.APPS)
        closing = generation_summary_line()
        scanned = re.search(r"from (\d+) spec file\(s\) scanned", closing).group(1)
        declaring = re.search(r"(\d+) spec file\(s\) declaring", closing).group(1)
        line = self.denominator(html)
        self.assertIn(f"across {scanned} spec file(s) scanned", line)
        self.assertIn(f"({declaring} spec file(s) carrying", line)

    def test_the_denominator_is_exactly_what_the_shared_aggregate_says(self):
        # The sentence is worded once, in `jsonui_test_cli`. Asserting the
        # string this way — rather than re-listing the words here — means a
        # change to the wording moves both sides or fails, instead of leaving
        # the site and the gate describing one run differently.
        from jsonui_test_cli.unit_contracts import aggregate_unit_totals, unit_contract_pages

        out, html = self.build(self.APPS)
        root = out.parent          # build() hands back the OUTPUT dir
        totals = [unit_contract_pages(root / name)["totals"] for name in self.APPS]
        self.assertEqual(self.denominator(html),
                         aggregate_unit_totals(totals)["summary_line"])

    def test_each_app_still_gets_its_own_line(self):
        # The aggregate cannot say WHICH app is empty, and that is the thing
        # someone reading a four-app site actually wants.
        _, html = self.build(self.APPS)
        lines = self.per_app_lines(html)
        self.assertEqual(len(lines), 2, lines)
        self.assertTrue(any(l.startswith("aaa: ") and "0 case(s)" in l for l in lines), lines)
        self.assertTrue(any(l.startswith("zzz: ") and "1 case(s)" in l for l in lines), lines)


class SingleApp(_Site):
    def test_one_app_renders_one_line_and_no_list(self):
        # Control: the per-app list would only repeat the aggregate, and a
        # single-app site is the shape every project had before this change.
        _, html = self.build({"only": "OnlyHandler"})
        self.assertIn("1 case(s) declared across 1 spec file(s) scanned",
                      self.denominator(html))
        self.assertEqual(self.per_app_lines(html), [])


if __name__ == "__main__":
    unittest.main()
