"""The section header / footer pairs (a flow, a list): what makes the pictures discriminate.

The generic generator tests hold the pair to the manifest invariants (a
control per visual fixture, the control differing in ``writtenKey``). What
they cannot see is what this fixture rests on:

* the data carries a header / footer for every edge the layout declares —
  the renderers draw an edge only when its section has data, so an edge
  declared without data draws nothing on iOS and Android and the fixture
  would render like its control on the paths it exists to measure;
* the control differs in the edges only — same box, same cells, same data;
* the arithmetic: on the flow two companion cells to a line and not three,
  on both every row inside the box (a clip would hide the footer), and a
  header narrower than the box, so a row drawn full width shows the view at
  the row's start and a stretched or centred view reads differently.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from jui_cli.conformance import flow_section_edge_fixtures as fe

REPO = Path(__file__).resolve().parents[2]
CELL = REPO / "conformance" / "fixtures" / "Collection" / "__cells" / "conformance_cell.layout.json"


PAIRS = {"flow": (fe.CASE, fe.CONTROL_STEM), "list": (fe.LIST_CASE, fe.LIST_CONTROL_STEM)}


def _pair(kind="flow"):
    files, entries = fe.build_flow_section_edge_fixtures("src")
    files = dict(files)
    by_id = {e["id"]: e for e in entries}
    fixture = by_id[f"Collection/{PAIRS[kind][0]}"]
    control = by_id[fixture["control"]]
    return files, by_id, fixture, control


def _target(files, entry):
    return next(c for c in files[entry["layout"]]["child"] if c["id"] == "target")


class Shape(unittest.TestCase):
    def test_two_fixtures_two_controls(self):
        _, by_id, _, _ = _pair()
        self.assertEqual(sorted(by_id), sorted(
            [f"Collection/{case}" for case, _ in PAIRS.values()] + [f"__control/{stem}" for _, stem in PAIRS.values()]))

    def test_each_fixture_is_visual_with_its_control(self):
        for kind in PAIRS:
            files, _, fixture, control = _pair(kind)
            self.assertEqual(fixture["class"], "visual", kind)
            self.assertTrue(control["isControl"], kind)
            self.assertEqual(fixture["writtenKey"], "sections", kind)
            self.assertEqual(fixture["value"], _target(files, fixture)["sections"], kind)
            # The flow is a flow, the list a vertical list (no layout key).
            self.assertEqual(_target(files, fixture).get("layout"), "flow" if kind == "flow" else None, kind)

    def test_the_control_differs_in_the_edges_only(self):
        for kind in PAIRS:
            files, _, fixture, control = _pair(kind)
            mine, theirs = _target(files, fixture), _target(files, control)
            self.assertEqual({k: v for k, v in mine.items() if k != "sections"},
                             {k: v for k, v in theirs.items() if k != "sections"}, kind)
            self.assertEqual([{"cell": s["cell"]} for s in mine["sections"]], theirs["sections"], kind)
            self.assertTrue(any("header" in s or "footer" in s for s in mine["sections"]), kind)
            self.assertEqual(files[fixture["layout"]]["data"], files[control["layout"]]["data"], kind)

    def test_every_declared_edge_has_data(self):
        for kind in PAIRS:
            files, _, fixture, _ = _pair(kind)
            sections = _target(files, fixture)["sections"]
            data = files[fixture["layout"]]["data"][0]["defaultValue"]["sections"]
            self.assertEqual(len(sections), len(data), kind)
            for declared, given in zip(sections, data):
                for edge in ("header", "footer"):
                    self.assertEqual(edge in declared, isinstance(given.get(edge), dict), (kind, edge, declared, given))


class Arithmetic(unittest.TestCase):
    def test_every_row_inside_the_box_and_a_narrow_header(self):
        cell = json.loads(CELL.read_text(encoding="utf-8"))
        for kind, per_row in (("flow", 2), ("list", 1)):
            files, _, fixture, _ = _pair(kind)
            target = _target(files, fixture)
            width, height = target["width"], target["height"]
            if kind == "flow":
                self.assertTrue(2 * cell["width"] <= width < 3 * cell["width"])
            # Undeclared gaps are 0 (attribute_semantics collectionSpacing).
            self.assertNotIn("itemSpacing", target)
            self.assertNotIn("lineSpacing", target)
            rows = 0
            for section in files[fixture["layout"]]["data"][0]["defaultValue"]["sections"]:
                rows += ("header" in section) + ("footer" in section)
                rows += -(-len(section["cells"]) // per_row)
            self.assertLessEqual(rows * cell["height"], height, kind)
            self.assertLess(cell["width"], width, kind)


if __name__ == "__main__":
    unittest.main()
