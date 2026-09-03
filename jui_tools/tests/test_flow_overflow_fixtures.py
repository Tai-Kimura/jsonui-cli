"""The flow-overflow family: the rule is only visible when the cells overflow.

The generic generator tests already hold every family to the manifest
invariants (counts, a control per visual fixture, the control differing in
the attribute under test). What they cannot see is the arithmetic this
family rests on: the box must be narrower than three companion cells and
shorter than the rows twelve of them make, or the fixture renders a
Collection that fits and the two shapes draw the same picture — the exact
silence the family exists to break. That arithmetic is pinned here against
the companion cell as committed, so a resized cell fails this test instead
of quietly un-overflowing the fixture.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from jui_cli.conformance import flow_overflow_fixtures as fo

REPO = Path(__file__).resolve().parents[2]
CELL = REPO / "conformance" / "fixtures" / "Collection" / "__cells" / "conformance_cell.layout.json"


def _fixtures():
    files, entries = fo.build_flow_overflow_fixtures("src")
    return dict(files), {e["id"]: e for e in entries}


class FamilyShape(unittest.TestCase):
    def test_two_fixtures_two_controls_and_nothing_else(self):
        _, entries = _fixtures()
        fixtures = sorted(i for i, e in entries.items() if not e.get("isControl"))
        controls = sorted(i for i, e in entries.items() if e.get("isControl"))
        self.assertEqual(
            fixtures, ["Collection/flowOverflow__none", "Collection/flowOverflow__scroll"]
        )
        self.assertEqual(
            controls,
            ["__control/Collection__flow-overflow-none",
             "__control/Collection__flow-overflow-scroll"],
        )
        self.assertTrue(all(e["class"] == "visual" for e in entries.values()))

    def test_each_fixture_is_compared_against_the_other_shape(self):
        files, entries = _fixtures()

        def lazy_of(entry):
            target = files[entry["layout"]]["child"][0]
            return target.get("lazy")

        none = entries["Collection/flowOverflow__none"]
        scroll = entries["Collection/flowOverflow__scroll"]
        self.assertEqual(lazy_of(none), "none")
        self.assertIsNone(lazy_of(scroll))
        # `none`'s control is the default body; `scroll`'s is the none body.
        self.assertIsNone(lazy_of(entries[none["control"]]))
        self.assertEqual(lazy_of(entries[scroll["control"]]), "none")
        # writtenKey tells the generic control-differs test which key to
        # compare; the undeclared shape writes nothing.
        self.assertEqual(none["writtenKey"], "lazy")
        self.assertIsNone(scroll["writtenKey"])

    def test_controls_stage_the_cell_too(self):
        # rules.py: what travels with the fixture has to travel with the
        # control, or the pair stops being comparable.
        _, entries = _fixtures()
        companions = {tuple(e["companions"]) for e in entries.values()}
        self.assertEqual(len(companions), 1, companions)
        self.assertTrue(any("conformance_cell" in c for c in next(iter(companions))))


class OverflowArithmetic(unittest.TestCase):
    """Measured against the committed companion cell, not a copy of its size."""

    def setUp(self):
        cell = json.loads(CELL.read_text(encoding="utf-8"))
        self.cell_w, self.cell_h = cell["width"], cell["height"]
        files, entries = _fixtures()
        layout = files[entries["Collection/flowOverflow__scroll"]["layout"]]
        self.target = layout["child"][0]
        self.count = len(layout["data"][0]["defaultValue"])

    def test_the_box_admits_two_cells_per_row_and_not_three(self):
        self.assertGreaterEqual(self.target["width"], 2 * self.cell_w)
        self.assertLess(self.target["width"], 3 * self.cell_w)

    def test_the_rows_overflow_the_box_by_whole_rows(self):
        per_row = self.target["width"] // self.cell_w
        rows = -(-self.count // per_row)  # ceil
        content_h = rows * self.cell_h
        # At least two full rows past the box: a hairline would sit inside the
        # baseline threshold and the two shapes would compare identical.
        self.assertGreaterEqual(content_h - self.target["height"], 2 * self.cell_h,
                                f"{rows} rows x {self.cell_h} vs box {self.target['height']}")

    def test_the_box_paints_its_own_background(self):
        # Without it the spill reads as a taller Collection, not as cells
        # outside the box.
        self.assertIn("background", self.target)


if __name__ == "__main__":
    unittest.main()
