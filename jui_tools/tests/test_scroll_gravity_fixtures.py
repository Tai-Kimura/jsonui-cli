"""The narrow-child ScrollView fixtures: what makes the frames discriminate.

* the ScrollView is vertical and wider than its one child, by enough that a
  centred child sits a band away from the start (80 of 200) and a
  right-placed one further (160);
* the gravity fixture declares the gravity on the ScrollView only, the
  child-gravity fixture on the child only, and the control nowhere;
* otherwise the three trees are the same.
"""
from __future__ import annotations

import copy
import unittest

from jui_cli.conformance import scroll_gravity_fixtures as sg


def _built():
    files, entries = sg.build_scroll_gravity_fixtures("src")
    return dict(files), {e["id"]: e for e in entries}


def _scroll(files, entry):
    return next(c for c in files[entry["layout"]]["child"] if c["id"] == "target")


class Shape(unittest.TestCase):
    def test_two_fixtures_one_control(self):
        _, by_id = _built()
        ids = sorted(by_id)
        self.assertEqual(ids, sorted([f"ScrollView/{sg.SCROLL_GRAVITY_CASE}", f"ScrollView/{sg.CHILD_GRAVITY_CASE}",
                                      f"__control/{sg.CONTROL_STEM}"]))
        control = by_id[f"__control/{sg.CONTROL_STEM}"]
        self.assertTrue(control["isControl"])
        for case in (sg.SCROLL_GRAVITY_CASE, sg.CHILD_GRAVITY_CASE):
            entry = by_id[f"ScrollView/{case}"]
            self.assertEqual(entry["class"], "visual")
            self.assertEqual(entry["control"], control["id"])
            self.assertEqual(entry["platforms"], ["ios", "android", "web"])

    def test_vertical_and_the_child_narrower_by_a_band(self):
        files, by_id = _built()
        for entry in by_id.values():
            scroll = _scroll(files, entry)
            self.assertNotIn("orientation", scroll)
            self.assertNotIn("horizontalScroll", scroll)
            self.assertEqual(len(scroll["child"]), 1)
            box = scroll["child"][0]
            # Centred, the box starts at (200 - 40) / 2 = 80; right-placed at 160.
            self.assertGreaterEqual((scroll["width"] - box["width"]) / 2, 40)

    def test_each_fixture_declares_its_gravity_in_one_place_only(self):
        files, by_id = _built()
        control = _scroll(files, by_id[f"__control/{sg.CONTROL_STEM}"])
        own = _scroll(files, by_id[f"ScrollView/{sg.SCROLL_GRAVITY_CASE}"])
        child = _scroll(files, by_id[f"ScrollView/{sg.CHILD_GRAVITY_CASE}"])
        self.assertEqual(own.get("gravity"), "centerHorizontal")
        self.assertNotIn("gravity", own["child"][0])
        self.assertNotIn("gravity", child)
        self.assertEqual(child["child"][0].get("gravity"), "right")
        self.assertNotIn("gravity", control)
        self.assertNotIn("gravity", control["child"][0])
        # Without the gravity, each is the control.
        for tree in (own, child):
            stripped = copy.deepcopy(tree)
            stripped.pop("gravity", None)
            stripped["child"][0].pop("gravity", None)
            self.assertEqual(stripped, control)


if __name__ == "__main__":
    unittest.main()
