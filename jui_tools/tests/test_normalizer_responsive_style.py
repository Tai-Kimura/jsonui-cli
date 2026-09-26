"""A ``style`` named inside a responsive override is applied by no path.

sjui / kjui codegen, rjui and both Dynamic runtimes did not apply it; the
normalizer's StyleMerger did (it walked every dict value), so the hotloader
drew what no build draws. 4f's ruling (1.9.0): named on every path, applied
by none. The override keeps its own attributes; the style is dropped and the
sentence said once — the same as the shared validator's and SwiftJsonUI
Dynamic's ResponsiveResolver's.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.core.normalizer import normalize
from jui_cli.core.normalizer.style_merger import STYLE_IN_RESPONSIVE_OVERRIDE, StyleMerger

LAYOUT = {
    "type": "View",
    "child": [
        {"type": "View", "style": "box"},
        {"type": "View", "responsive": {"regular": {"style": "wide", "orientation": "horizontal"}}},
        {"type": "View", "responsive": {"regular": {"spacing": 44}}},
        {"type": "Label", "text": "ctl", "style": "red"},
    ],
}


class ResponsiveOverrideStyleTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.styles = root / "styles"
        self.layouts = root / "layouts"
        self.styles.mkdir()
        self.layouts.mkdir()
        for name, body in {
            "box": {"child": [{"type": "Label", "text": "k", "style": "red2"}]},
            "red2": {"fontSize": 23},
            "red": {"fontSize": 21},
            "wide": {"spacing": 33},
        }.items():
            (self.styles / f"{name}.json").write_text(json.dumps(body))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_the_overrides_style_is_not_applied_and_named_once(self) -> None:
        merger = StyleMerger(self.styles)
        out = merger.resolve(copy.deepcopy(LAYOUT))
        override = out["child"][1]["responsive"]["regular"]
        self.assertEqual(override, {"orientation": "horizontal"})
        self.assertNotIn("33", json.dumps(out))
        self.assertEqual(merger.warnings, [STYLE_IN_RESPONSIVE_OVERRIDE])

    def test_everything_else_is_as_it_was(self) -> None:
        out = StyleMerger(self.styles).resolve(copy.deepcopy(LAYOUT))
        self.assertEqual(out["child"][0]["child"][0]["fontSize"], 23)  # a style's child's style
        self.assertEqual(out["child"][2]["responsive"]["regular"], {"spacing": 44})
        self.assertEqual(out["child"][3]["fontSize"], 21)

    def test_l2_normalize_says_it(self) -> None:
        result = normalize(LAYOUT, level="L2", styles_dir=self.styles, layouts_dir=self.layouts)
        self.assertIn(STYLE_IN_RESPONSIVE_OVERRIDE, result.warnings)
        self.assertEqual(result.warnings.count(STYLE_IN_RESPONSIVE_OVERRIDE), 1)


if __name__ == "__main__":
    unittest.main()
