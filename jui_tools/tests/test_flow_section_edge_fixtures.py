"""The flow section header / footer pair: what makes the picture discriminate.

The generic generator tests hold the pair to the manifest invariants (a
control per visual fixture, the control differing in ``writtenKey``). What
they cannot see is what this fixture rests on:

* the data carries a header / footer for every edge the layout declares —
  the renderers draw an edge only when its section has data, so an edge
  declared without data draws nothing on iOS and Android and the fixture
  would render like its control on the paths it exists to measure;
* the control differs in the edges only — same box, same cells, same data;
* the arithmetic: two companion cells to a line and not three, every row
  inside the box (a clip would hide the footer), and a header narrower than
  the box, so a row drawn full width shows the view at the row's start and
  a stretched or centred view reads differently.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from jui_cli.conformance import flow_section_edge_fixtures as fe

REPO = Path(__file__).resolve().parents[2]
CELL = REPO / "conformance" / "fixtures" / "Collection" / "__cells" / "conformance_cell.layout.json"


def _pair():
    files, entries = fe.build_flow_section_edge_fixtures("src")
    files = dict(files)
    by_id = {e["id"]: e for e in entries}
    fixture = by_id[f"Collection/{fe.CASE}"]
    control = by_id[fixture["control"]]
    return files, by_id, fixture, control


def _target(files, entry):
    return next(c for c in files[entry["layout"]]["child"] if c["id"] == "target")


class Shape(unittest.TestCase):
    def test_one_fixture_one_control(self):
        files, by_id, fixture, control = _pair()
        self.assertEqual(sorted(by_id), [f"Collection/{fe.CASE}", f"__control/{fe.CONTROL_STEM}"])
        self.assertEqual(fixture["class"], "visual")
        self.assertTrue(control["isControl"])
        self.assertEqual(fixture["writtenKey"], "sections")
        self.assertEqual(fixture["value"], _target(files, fixture)["sections"])

    def test_the_control_differs_in_the_edges_only(self):
        files, _, fixture, control = _pair()
        mine, theirs = _target(files, fixture), _target(files, control)
        self.assertEqual({k: v for k, v in mine.items() if k != "sections"},
                         {k: v for k, v in theirs.items() if k != "sections"})
        self.assertEqual([{"cell": s["cell"]} for s in mine["sections"]], theirs["sections"])
        self.assertTrue(any("header" in s or "footer" in s for s in mine["sections"]))
        self.assertEqual(files[fixture["layout"]]["data"], files[control["layout"]]["data"])

    def test_every_declared_edge_has_data(self):
        files, _, fixture, _ = _pair()
        sections = _target(files, fixture)["sections"]
        data = files[fixture["layout"]]["data"][0]["defaultValue"]["sections"]
        self.assertEqual(len(sections), len(data))
        for declared, given in zip(sections, data):
            for edge in ("header", "footer"):
                self.assertEqual(edge in declared, isinstance(given.get(edge), dict), (edge, declared, given))


class Arithmetic(unittest.TestCase):
    def test_two_cells_to_a_line_every_row_inside_the_box_and_a_narrow_header(self):
        cell = json.loads(CELL.read_text(encoding="utf-8"))
        files, _, fixture, _ = _pair()
        target = _target(files, fixture)
        width, height = target["width"], target["height"]
        self.assertTrue(2 * cell["width"] <= width < 3 * cell["width"])
        # Undeclared gaps are 0 (attribute_semantics collectionSpacing).
        self.assertNotIn("itemSpacing", target)
        self.assertNotIn("lineSpacing", target)
        rows = 0
        for section in files[fixture["layout"]]["data"][0]["defaultValue"]["sections"]:
            rows += ("header" in section) + ("footer" in section)
            rows += -(-len(section["cells"]) // 2)
        self.assertLessEqual(rows * cell["height"], height)
        self.assertLess(cell["width"], width)


if __name__ == "__main__":
    unittest.main()
