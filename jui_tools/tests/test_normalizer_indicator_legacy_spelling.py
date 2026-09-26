"""An Indicator's legacy spellings, folded by the L1 canonicalizer.

``style`` naming an indicator style is the indicator's style written with the
style-file key; ``size`` is an undeclared length. The Compose converter reads
neither any more (kjui indicator_component.rb reads ``indicatorStyle`` and the
declared width / height), so the normalizer folds them, each with a named
warning (``Indicator legacy spelling``) —
docs/bugs/kjui-dynamic-components-that-skip-the-common-modifiers.md, item C.
"""
from __future__ import annotations

import unittest

from jui_cli.core.normalizer import AliasTable, Canonicalizer

TAG = "Indicator legacy spelling"


class IndicatorLegacySpellingTest(unittest.TestCase):
    def setUp(self):
        self.table = AliasTable.from_file()
        self.canon = Canonicalizer(self.table)

    def fold(self, node):
        return self.canon.canonicalize(node, add_marker=False)

    def test_the_styles_are_the_declared_ones(self):
        # Read from shared/core/attribute_definitions.json, not listed here.
        self.assertEqual(self.table.enum_for("Indicator", "indicatorStyle"), ["small", "medium", "large", "linear"])

    def test_style_naming_an_indicator_style_becomes_indicatorStyle(self):
        for style in self.table.enum_for("Indicator", "indicatorStyle"):
            tree, warnings = self.fold({"type": "Indicator", "style": style})
            self.assertEqual(tree, {"type": "Indicator", "indicatorStyle": style}, style)
            self.assertEqual(len(warnings), 1, style)
            self.assertIn(TAG, warnings[0])
            self.assertIn(f"rewrote to 'indicatorStyle: {style}'", warnings[0])

    def test_a_synonym_of_Indicator_is_folded_too(self):
        tree, warnings = self.fold({"type": "ActivityIndicator", "style": "small"})
        self.assertEqual(tree.get("indicatorStyle"), "small")
        self.assertNotIn("style", tree)
        self.assertEqual(len(warnings), 1)

    def test_style_naming_anything_else_is_a_style_file_and_stays(self):
        tree, warnings = self.fold({"type": "Indicator", "style": "brand_spinner"})
        self.assertEqual(tree, {"type": "Indicator", "style": "brand_spinner"})
        self.assertEqual(warnings, [])

    def test_size_becomes_width_and_height(self):
        tree, warnings = self.fold({"type": "Indicator", "size": 30})
        self.assertEqual(tree, {"type": "Indicator", "width": 30, "height": 30})
        self.assertEqual(len(warnings), 1)
        self.assertIn(TAG, warnings[0])

    def test_a_declared_attribute_wins_and_the_legacy_one_is_dropped_with_the_warning(self):
        tree, warnings = self.fold(
            {"type": "Indicator", "style": "large", "indicatorStyle": "small", "size": 30, "width": 10}
        )
        self.assertEqual(tree, {"type": "Indicator", "indicatorStyle": "small", "width": 10})
        self.assertEqual(len(warnings), 2)
        self.assertTrue(all(TAG in w for w in warnings))
        self.assertIn("keeping indicatorStyle", warnings[0])
        self.assertIn("keeping width / height", warnings[1])

    def test_other_types_are_untouched(self):
        tree, warnings = self.fold({"type": "View", "style": "large", "size": 3})
        self.assertEqual(tree, {"type": "View", "style": "large", "size": 3})
        self.assertEqual(warnings, [])

    def test_nested_and_idempotent(self):
        layout = {"type": "View", "child": [{"type": "Indicator", "style": "linear", "size": 20}]}
        once, warnings = self.canon.canonicalize(layout)
        self.assertEqual(once["child"][0], {"type": "Indicator", "indicatorStyle": "linear", "width": 20, "height": 20})
        self.assertEqual(len(warnings), 2)
        twice, again = self.canon.canonicalize(once)
        self.assertEqual(twice, once)
        self.assertEqual(again, [])

    def test_the_fold_follows_the_declaration(self):
        # Swap the authority: a table declaring other styles folds those, and
        # the real ones no longer (a list hard-coded in the canonicalizer would
        # not follow).
        table = AliasTable({"common": {}, "Indicator": {"indicatorStyle": {"type": "string", "enum": ["tiny"]}}})
        canon = Canonicalizer(table)
        tree, _ = canon.canonicalize({"type": "Indicator", "style": "tiny"}, add_marker=False)
        self.assertEqual(tree, {"type": "Indicator", "indicatorStyle": "tiny"})
        tree, warnings = canon.canonicalize({"type": "Indicator", "style": "large"}, add_marker=False)
        self.assertEqual(tree, {"type": "Indicator", "style": "large"})
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
