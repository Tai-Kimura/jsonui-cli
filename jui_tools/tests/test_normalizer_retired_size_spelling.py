"""Image's and CircleView's legacy ``size``, retired and folded by the L1 canonicalizer.

Ruled 2026-10-24 ("size を廃止する", docs/bugs/2026-10-24-image-circleview-size-spelling-retired.md):
``size`` was declared for Kotlin only, and kjui read it only behind the required width / height
(conformance/codegen_effect.json carried the two rows). It is no longer declared, no converter reads
it, and the normalizer folds it into width / height the way it folds Indicator's, with a named warning
(``Image legacy spelling`` / ``CircleView legacy spelling``).
"""
from __future__ import annotations

import json
import unittest

from jui_cli.core.normalizer import AliasTable, Canonicalizer
from jui_cli.core.normalizer.alias_table import default_definitions_path

DEFINITIONS = json.loads(default_definitions_path().read_text(encoding="utf-8"))


class RetiredSizeSpellingTest(unittest.TestCase):
    def setUp(self):
        self.table = AliasTable.from_file()
        self.canon = Canonicalizer(self.table)

    def fold(self, node):
        return self.canon.canonicalize(node, add_marker=False)

    def test_size_is_declared_on_neither(self):
        # The fold is for a spelling the definitions no longer hold; declared again, it
        # would be a live attribute rewritten away.
        for component in ("Image", "CircleView"):
            self.assertNotIn("size", DEFINITIONS[component], component)

    def test_size_becomes_width_and_height(self):
        for node_type in ("Image", "CircleView"):
            tree, warnings = self.fold({"type": node_type, "size": 30})
            self.assertEqual(tree, {"type": node_type, "width": 30, "height": 30}, node_type)
            self.assertEqual(len(warnings), 1, node_type)
            self.assertIn(f"{node_type} legacy spelling", warnings[0])
            self.assertIn("rewrote to 'width: 30, height: 30'", warnings[0])

    def test_the_synonyms_of_Image_are_folded_too(self):
        # CircleImage drew its 48dp default unless `size` was written; it is Image's spelling.
        for node_type in ("CircleImage", "CircleImageView", "ImageView"):
            tree, warnings = self.fold({"type": node_type, "size": 64})
            self.assertEqual((tree.get("width"), tree.get("height")), (64, 64), node_type)
            self.assertNotIn("size", tree, node_type)
            self.assertEqual(len(warnings), 1, node_type)
            self.assertIn("Image legacy spelling", warnings[0], node_type)

    def test_a_declared_width_or_height_wins_and_size_is_dropped_with_the_warning(self):
        for extra in ({"width": 10}, {"height": 10}, {"width": 10, "height": 12}):
            tree, warnings = self.fold({"type": "CircleView", "size": 30, **extra})
            self.assertEqual(tree, {"type": "CircleView", **extra}, extra)
            self.assertEqual(len(warnings), 1, extra)
            self.assertIn("keeping width / height", warnings[0])

    def test_a_bound_size_is_folded_as_it_is(self):
        tree, _ = self.fold({"type": "Image", "size": "@{iconSize}"})
        self.assertEqual((tree["width"], tree["height"]), ("@{iconSize}", "@{iconSize}"))

    def test_NetworkImage_keeps_its_size(self):
        # Outside the ruling: NetworkImage declares size and both Kotlin faces read it.
        self.assertIn("size", DEFINITIONS["NetworkImage"])
        tree, warnings = self.fold({"type": "NetworkImage", "size": 30})
        self.assertEqual(tree, {"type": "NetworkImage", "size": 30})
        self.assertEqual(warnings, [])

    def test_nested_and_idempotent(self):
        layout = {"type": "View", "child": [{"type": "Image", "srcName": "a", "size": 20}]}
        once, warnings = self.canon.canonicalize(layout)
        self.assertEqual(once["child"][0], {"type": "Image", "srcName": "a", "width": 20, "height": 20})
        self.assertEqual(len(warnings), 1)
        twice, again = self.canon.canonicalize(once)
        self.assertEqual(twice, once)
        self.assertEqual(again, [])


if __name__ == "__main__":
    unittest.main()
