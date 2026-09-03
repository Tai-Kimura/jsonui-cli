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

The third member is the crash shape a consumer's tree had and the corpus
did not: a wrapContent flow inside a scrolling parent. What is pinned is
that the parent scrolls (the root IS a ScrollView) and the child has no
bounds of its own — the two facts that make it the shape it is.
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


def _target(files, entry):
    return files[entry["layout"]]["child"][0]


class FamilyShape(unittest.TestCase):
    def test_seven_fixtures_six_controls_and_nothing_else(self):
        _, entries = _fixtures()
        fixtures = sorted(i for i, e in entries.items() if not e.get("isControl"))
        controls = sorted(i for i, e in entries.items() if e.get("isControl"))
        self.assertEqual(
            fixtures,
            ["Collection/flowOverflow__fill", "Collection/flowOverflow__none",
             "Collection/flowOverflow__noneWrapInBox",
             "Collection/flowOverflow__noneWrapInScroll",
             "Collection/flowOverflow__none_item11",
             "Collection/flowOverflow__scroll", "Collection/flowOverflow__wrap"],
        )
        self.assertEqual(
            controls,
            ["__control/Collection__flow-overflow-fill",
             "__control/Collection__flow-overflow-none",
             "__control/Collection__flow-overflow-none-wrapInBox",
             "__control/Collection__flow-overflow-none-wrapInScroll",
             "__control/Collection__flow-overflow-scroll",
             "__control/Collection__flow-overflow-wrap"],
        )
        classes = {i: e["class"] for i, e in entries.items()}
        self.assertEqual(classes.pop("Collection/flowOverflow__none_item11"), "assertable")
        self.assertTrue(all(c == "visual" for c in classes.values()), classes)

    def test_the_reachability_arm_asks_for_the_last_cell_past_the_box(self):
        # 51-E's hit-testing half: an unclipped overflow is drawn AND
        # tappable. The arm is none's body; it waits for the last cell of the
        # sixth row (past the 100pt box) and taps it.
        files, entries = _fixtures()
        reach = entries["Collection/flowOverflow__none_item11"]
        none = entries["Collection/flowOverflow__none"]
        mine, theirs = dict(files[reach["layout"]]), dict(files[none["layout"]])
        self.assertEqual(mine, theirs, "the reach arm must be none's exact body")
        self.assertIsNone(reach["control"])
        steps = files[reach["test"]]["cases"][0]["steps"]
        count = len(files[reach["layout"]]["data"][0]["defaultValue"])
        self.assertEqual(
            [(s["action"], s.get("id"), s.get("index")) for s in steps],
            [("waitFor", "root", None), ("waitFor", f"target_item_{count - 1}", None),
             ("tapItem", "target", count - 1)],
        )

    def test_each_box_fixture_is_compared_against_the_other_shape(self):
        files, entries = _fixtures()

        def lazy_of(entry):
            return _target(files, entry).get("lazy")

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


class WrapShape(unittest.TestCase):
    def setUp(self):
        self.files, self.entries = _fixtures()
        self.wrap = self.entries["Collection/flowOverflow__wrap"]
        self.control = self.entries[self.wrap["control"]]

    def test_the_parent_scrolls_and_the_child_has_no_bounds_of_its_own(self):
        layout = self.files[self.wrap["layout"]]
        self.assertEqual(layout["type"], "ScrollView")
        target = _target(self.files, self.wrap)
        self.assertEqual(target["height"], "wrapContent")
        self.assertNotIn("maxHeight", target)
        self.assertNotIn("lazy", target, "lazy must be IN EFFECT for the crash shape")
        self.assertEqual(target["layout"], "flow")

    def test_the_control_is_the_same_tree_self_bounded(self):
        control_layout = self.files[self.control["layout"]]
        self.assertEqual(control_layout["type"], "ScrollView")
        control_target = _target(self.files, self.control)
        self.assertIsInstance(control_target["height"], int)
        # Same tree otherwise: the attribute under test is the height alone.
        mine = dict(_target(self.files, self.wrap)); theirs = dict(control_target)
        mine.pop("height"); theirs.pop("height")
        self.assertEqual(mine, theirs)
        self.assertEqual(self.wrap["writtenKey"], "height")
        self.assertEqual(self.wrap["value"], "wrapContent")


class FillShape(unittest.TestCase):
    """The parent is finite and the child borrows its bounds — the two facts
    that make it the shape the static emit could not decide."""

    def setUp(self):
        self.files, self.entries = _fixtures()
        self.fill = self.entries["Collection/flowOverflow__fill"]
        self.control = self.entries[self.fill["control"]]

    def test_the_parent_is_the_finite_box_and_the_child_matches_it(self):
        layout = self.files[self.fill["layout"]]
        self.assertEqual(layout["type"], "View")
        self.assertIsInstance(layout["height"], int)
        self.assertIsInstance(layout["width"], int)
        self.assertIn("background", layout, "the box paints itself so the clip reads")
        target = _target(self.files, self.fill)
        self.assertEqual(target["height"], "matchParent")
        self.assertNotIn("maxHeight", target, "a maxHeight would make it self-bounded, the static arm")
        self.assertNotIn("lazy", target, "lazy must be IN EFFECT")
        self.assertEqual(target["layout"], "flow")

    def test_the_same_box_as_the_other_members(self):
        scroll = self.files[self.entries["Collection/flowOverflow__scroll"]["layout"]]
        box = scroll["child"][0]
        layout = self.files[self.fill["layout"]]
        self.assertEqual((layout["width"], layout["height"]), (box["width"], box["height"]))
        self.assertEqual(len(layout["data"][0]["defaultValue"]), len(scroll["data"][0]["defaultValue"]))

    def test_the_control_is_the_same_tree_with_lazy_none(self):
        control_layout = self.files[self.control["layout"]]
        control_target = _target(self.files, self.control)
        self.assertEqual(control_target.get("lazy"), "none")
        mine = dict(_target(self.files, self.fill)); theirs = dict(control_target)
        theirs.pop("lazy")
        self.assertEqual(mine, theirs)
        mine_root = dict(self.files[self.fill["layout"]]); theirs_root = dict(control_layout)
        mine_root.pop("child"); theirs_root.pop("child")
        self.assertEqual(mine_root, theirs_root)
        # as for `scroll`: the undeclared shape writes nothing
        self.assertIsNone(self.fill["writtenKey"])
        self.assertEqual(self.fill["attribute"], "lazy")


class DuplicateOverflowModifierPairs(unittest.TestCase):
    """The shape the corpus had no arm for.

    kjui emits `.wrapContentHeight()` for an EXPLICIT `height: "wrapContent"`
    and nothing when the key is absent, while the flow arm appends
    `.wrapContentHeight(Alignment.Top, unbounded = true)` in both cases — so a
    declared wrapContent flow renders through two stacked wrapContentHeight
    modifiers and an undeclared one through a single modifier. Measured on the
    emit: 2 vs 1, with every other modifier identical. The dynamic renderer has
    the same asymmetry (ModifierBuilder.applySingleDimension returns the
    modifier untouched when the key is absent), so both faces stack the same
    pair.

    Each fixture's control is its own undeclared twin, which makes the
    control-diff verdict the measurement: inert means the duplicate changes
    nothing, active means the outer modifier (default CenterVertically) is
    overriding the alignment the inner one asked for.
    """

    def setUp(self):
        self.files, self.entries = _fixtures()

    def test_both_parents_are_covered(self):
        ids = sorted(i for i in self.entries if "noneWrap" in i)
        self.assertEqual(
            ids,
            ["Collection/flowOverflow__noneWrapInBox",
             "Collection/flowOverflow__noneWrapInScroll"],
        )

    def test_each_fixture_is_paired_with_its_undeclared_twin(self):
        for suffix in ("InBox", "InScroll"):
            fixture = self.entries[f"Collection/flowOverflow__noneWrap{suffix}"]
            control = self.entries[fixture["control"]]
            self.assertTrue(control.get("isControl"), suffix)
            mine = dict(_target(self.files, fixture))
            theirs = dict(_target(self.files, control))
            # The declared height is the whole difference — that is what makes
            # the pair a measurement of the duplicate and of nothing else.
            self.assertEqual(mine.pop("height"), "wrapContent", suffix)
            self.assertNotIn("height", theirs, suffix)
            self.assertEqual(mine, theirs, suffix)
            self.assertEqual(fixture["writtenKey"], "height")
            root_mine = {k: v for k, v in self.files[fixture["layout"]].items() if k != "child"}
            root_theirs = {k: v for k, v in self.files[control["layout"]].items() if k != "child"}
            self.assertEqual(root_mine, root_theirs, suffix)

    def test_the_two_parents_are_the_bounded_and_unbounded_cases(self):
        boxed = self.files[self.entries["Collection/flowOverflow__noneWrapInBox"]["layout"]]
        free = self.files[self.entries["Collection/flowOverflow__noneWrapInScroll"]["layout"]]
        # bounded: a clip can happen at all
        self.assertEqual(boxed["type"], "View")
        self.assertIsInstance(boxed["height"], int)
        # unbounded: the consumer shape, where nothing was being clipped anyway
        self.assertEqual(free["type"], "ScrollView")
        self.assertEqual(free["height"], "matchParent")

    def test_every_arm_is_a_lazy_none_flow_that_overflows(self):
        for suffix in ("InBox", "InScroll"):
            fixture = self.entries[f"Collection/flowOverflow__noneWrap{suffix}"]
            for entry in (fixture, self.entries[fixture["control"]]):
                target = _target(self.files, entry)
                self.assertEqual(target["layout"], "flow", entry["id"])
                self.assertEqual(target["lazy"], "none", entry["id"])
                count = len(self.files[entry["layout"]]["data"][0]["defaultValue"])
                self.assertGreaterEqual(count, 12, entry["id"])


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
