"""The Unit Tests section of the generated site.

`unitContracts` declares hand-written business logic cases and the faces that
must carry them. Before this section the declaration had nowhere to be read:
the tests index listed Screen and Flow only, and a reader had to run
`jsonui-test generate unit-stubs --check` to learn that one face was missing a
case the other had.

What is pinned here:

* the index gains a section, and gains NOTHING when a project declares no
  unitContracts — the feature must not move output for projects that do not
  use it;
* the denominator line is the gate's own string, not a second sentence
  composed from the same numbers. Two places counting the same thing is how a
  site and a gate come to disagree about how much was scanned;
* `never_runs` renders differently from `missing`. A method that exists but
  which XCTest will never discover is not an unwritten test, and showing it as
  one sends the reader to write a test that is already written — which does
  not fix it, because the name is what stops it running.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.test_doc.html.index import generate_index_html
from jsonui_doc_cli.test_doc.html.unit import generate_unit_html
from jsonui_doc_cli.spec_doc.html_generator import generate_spec_html


def _spec(with_contracts: bool) -> dict:
    spec = {
        "type": "screen_spec",
        "version": "1.0",
        "metadata": {"screenName": "item_detail", "name": "ItemDetail",
                     "displayName": "Item Detail", "description": "Item detail."},
        "structure": {"components": [{"type": "View", "id": "root", "description": "r"}],
                      "layout": {"root": "root", "children": []}},
    }
    if with_contracts:
        spec["unitContracts"] = {
            "target": "ItemDetailViewModel",
            "cases": [{"name": "loadItem", "intent": "loads", "platforms": ["ios"]}],
        }
    return spec


def _target() -> dict:
    return {
        "target": "ItemDetailViewModel",
        "screens": ["item_detail"],
        "spec_files": ["item_detail.spec.json"],
        "cases": [
            {"name": "written", "intent": "ok", "platforms": ["ios", "android"],
             "status": {"ios": "implemented", "android": "missing"}},
            {"name": "unrunnable", "intent": "no prefix", "platforms": ["ios"],
             "status": {"ios": "never_runs", "android": "not_declared_for_face"}},
        ],
        "faces": {
            "ios": {"declared": ["written", "unrunnable"], "implemented": ["written"],
                    "missing": [], "never_runs": ["unrunnable"],
                    "files": ["ios/Tests/ItemDetailViewModelContractTests.swift"]},
            "android": {"declared": ["written"], "implemented": [], "missing": ["written"],
                        "never_runs": [], "files": []},
        },
    }


class UnitSectionOnTheIndex(unittest.TestCase):
    def _index(self, **kwargs) -> str:
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            files = [{"type": "screen", "path": "screens/a.html", "name": "a",
                      "platform": "ios", "description": "", "case_count": 1,
                      "step_count": 2}]
            generate_index_html(out, files, "T", **kwargs)
            return (out / "index.html").read_text(encoding="utf-8")

    def test_a_project_with_no_unit_contracts_gains_no_unit_markup(self):
        html = self._index()
        for token in ("Unit Tests", "Unit Targets", "unit contracts:",
                      "Undeclared unit tests", "units-content"):
            self.assertNotIn(token, html, token)

    def test_the_section_and_its_count_appear_when_targets_exist(self):
        html = self._index(unit_files=[{
            "name": "ItemDetailViewModel", "path": "unit/ItemDetailViewModel.html",
            "platform": "ios", "description": "item_detail", "group": "",
            "case_count": 2, "faces_summary": "ios 1/2"}])
        self.assertIn("Unit Tests", html)
        self.assertIn("unit/ItemDetailViewModel.html", html)
        self.assertIn("2 cases, ios 1/2", html)

    def test_the_denominator_is_reproduced_verbatim(self):
        # Passed through, never recomposed: the index and `--check` must not
        # be able to disagree about how many specs were read.
        line = "unit contracts: 14 case(s) declared across 21 spec(s) scanned (5 carrying a unitContracts block)"
        html = self._index(unit_files=[], unit_summary=line)
        self.assertIn(line, html)

    def test_undeclared_implementations_are_reported_outside_any_target(self):
        html = self._index(unit_undeclared={"android": ["strayTest"]})
        self.assertIn("Undeclared unit tests", html)
        self.assertIn("strayTest", html)


#: A rendered badge, not a stylesheet rule. The page embeds its own CSS, so
#: every `.status-<name>` class name appears in the <style> block whether or
#: not any badge uses it — asserting on the bare class name passes even when
#: nothing renders it. Found by mutation: collapsing `never_runs` onto the
#: `missing` badge left the first version of these tests green.
def _badge(status: str) -> str:
    return f"class='status status-{status}'"


class UnitTargetPage(unittest.TestCase):
    def test_never_runs_is_not_rendered_as_missing(self):
        html = generate_unit_html(_target(), ["android", "ios"])
        # The two must be distinguishable, or the page sends a reader to
        # rewrite a test that already exists — and rewriting will not fix it,
        # because the method name is what stops it running.
        self.assertIn(_badge("never_runs"), html)
        self.assertIn(_badge("missing"), html)
        self.assertIn("never run", html)

    def test_a_face_the_case_does_not_name_is_not_shown_as_missing(self):
        html = generate_unit_html(_target(), ["android", "ios"])
        self.assertIn(_badge("not_declared_for_face"), html)

    def test_an_unknown_status_is_shown_rather_than_left_blank(self):
        target = _target()
        target["cases"][0]["status"]["ios"] = "something_new"
        html = generate_unit_html(target, ["ios"])
        self.assertIn("something_new", html)

    def test_implementation_files_are_listed(self):
        html = generate_unit_html(_target(), ["ios"])
        self.assertIn("ItemDetailViewModelContractTests.swift", html)

    def test_the_spec_link_uses_the_callers_url(self):
        html = generate_unit_html(_target(), ["ios"],
                                  spec_href_fn=lambda s, f: "../specs/item_detail.html")
        self.assertIn("../specs/item_detail.html", html)

    def test_a_face_that_could_not_be_compared_says_so(self):
        html = generate_unit_html(_target(), ["ios"],
                                  unscannable={"ios": "unitTestsDir is not declared"})
        self.assertIn("NOT CHECKED", html)
        self.assertIn("unitTestsDir is not declared", html)


class SpecPageLink(unittest.TestCase):
    def test_the_declaration_is_not_copied_onto_the_spec_page(self):
        html = generate_spec_html(_spec(True), title="item_detail")
        for token in ("unitContracts", "loadItem", "loads"):
            self.assertNotIn(token, html, token)

    def test_a_spec_that_declares_contracts_links_to_the_unit_page(self):
        html = generate_spec_html(_spec(True), title="item_detail",
                                  unit_href="../unit/ItemDetailViewModel.html")
        self.assertIn("../unit/ItemDetailViewModel.html", html)

    def test_a_spec_without_contracts_gets_no_link_even_if_one_is_offered(self):
        html = generate_spec_html(_spec(False), title="item_detail",
                                  unit_href="../unit/ItemDetailViewModel.html")
        self.assertNotIn("unit-contract-link", html)


if __name__ == "__main__":
    unittest.main()
