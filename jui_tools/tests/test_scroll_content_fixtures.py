"""The short-content ScrollView pair: what makes the frames discriminate.

The generic generator tests hold the pair to the manifest invariants. What
they cannot see is what the fixture rests on:

* the ScrollView is vertical (no orientation, no horizontalScroll) — a
  horizontal one asks the cross-axis question its own fixtures ask;
* the content is SHORTER than the ScrollView, by enough that a centring
  platform puts the box a whole band lower (60 of 200), and the control's
  content fills it exactly;
* the two differ in the box's height only.
"""
from __future__ import annotations

import unittest

from jui_cli.conformance import scroll_content_fixtures as sc


def _pair():
    files, entries = sc.build_scroll_content_fixtures("src")
    files = dict(files)
    by_id = {e["id"]: e for e in entries}
    fixture = by_id[f"ScrollView/{sc.CASE}"]
    control = by_id[fixture["control"]]
    return files, by_id, fixture, control


def _scroll(files, entry):
    return next(c for c in files[entry["layout"]]["child"] if c["id"] == "target")


def _box(scroll):
    return scroll["child"][0]["child"][0]


class Shape(unittest.TestCase):
    def test_one_fixture_one_control(self):
        _, by_id, fixture, control = _pair()
        self.assertEqual(sorted(by_id), sorted([f"ScrollView/{sc.CASE}", f"__control/{sc.CONTROL_STEM}"]))
        self.assertEqual(fixture["class"], "visual")
        self.assertTrue(control["isControl"])
        self.assertEqual(fixture["platforms"], ["ios", "android", "web"])

    def test_the_scrollview_is_vertical(self):
        files, _, fixture, control = _pair()
        for entry in (fixture, control):
            scroll = _scroll(files, entry)
            self.assertEqual(scroll["type"], "ScrollView")
            self.assertNotIn("orientation", scroll)
            self.assertNotIn("horizontalScroll", scroll)

    def test_the_content_is_short_and_the_control_fills(self):
        files, _, fixture, control = _pair()
        scroll = _scroll(files, fixture)
        self.assertEqual(scroll["height"], 200)
        self.assertEqual(scroll["child"][0]["height"], "wrapContent")
        short = _box(scroll)["height"]
        # Centred, the box would start at (200 - 80) / 2 = 60: a band, not a hairline.
        self.assertGreaterEqual((scroll["height"] - short) / 2, 40)
        self.assertEqual(_box(_scroll(files, control))["height"], scroll["height"])

    def test_they_differ_in_the_box_height_only(self):
        files, _, fixture, control = _pair()
        a, b = _scroll(files, fixture), _scroll(files, control)
        _box(b)["height"] = _box(a)["height"]
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
