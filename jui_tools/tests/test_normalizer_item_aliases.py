"""An array attribute's objects fold the aliases their properties declare.

A partialAttributes range's handler: `onClick` is canonical and `onclick`
its alias (`items.properties.onClick.aliases` in attribute_definitions.json;
4f ruling, jsonui-cli 1.9.0). The canonicalizer rewrites `onclick` to
`onClick` in each range, keeps `onClick` when both are set (with a warning),
and leaves a node's own `onclick` alone — at the node, `onClick` and
`onclick` are two attributes.
"""
from __future__ import annotations

import unittest

from jui_cli.core.normalizer import AliasTable, Canonicalizer

DEFS = {
    "common": {"onClick": {"type": "binding"}, "onclick": {"type": ["string", "array"]}},
    "Label": {
        "partialAttributes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "range": {"type": ["array", "string"]},
                    "onClick": {"type": ["binding", "string"], "aliases": ["onclick"]},
                },
            },
        },
    },
}


class ItemAliasTest(unittest.TestCase):
    def setUp(self):
        self.canon = Canonicalizer(AliasTable(DEFS, {}))

    def ranges(self, *ranges):
        tree, warnings = self.canon.canonicalize(
            {"type": "Label", "text": "Terms and more", "partialAttributes": list(ranges)}, add_marker=False
        )
        return tree["partialAttributes"], warnings

    def test_the_alias_is_folded(self):
        got, warnings = self.ranges({"range": "Terms", "onclick": "onTerms"})
        self.assertEqual(got, [{"range": "Terms", "onClick": "onTerms"}])
        self.assertEqual(warnings, [])

    def test_both_set_keep_the_canonical_one(self):
        got, warnings = self.ranges({"range": "Terms", "onClick": "@{a}", "onclick": "b"})
        self.assertEqual(got, [{"range": "Terms", "onClick": "@{a}"}])
        self.assertEqual(len(warnings), 1)
        self.assertIn("keeping 'onClick', dropping 'onclick'", warnings[0])

    def test_both_set_in_the_other_order_keep_the_canonical_one(self):
        got, _ = self.ranges({"range": "Terms", "onclick": "b", "onClick": "@{a}"})
        self.assertEqual(got, [{"range": "Terms", "onClick": "@{a}"}])

    def test_the_canonical_one_is_untouched(self):
        got, warnings = self.ranges({"range": "Terms", "onClick": "@{a}"})
        self.assertEqual(got, [{"range": "Terms", "onClick": "@{a}"}])
        self.assertEqual(warnings, [])

    def test_each_range_is_folded(self):
        got, _ = self.ranges({"range": "a", "onclick": "x"}, {"range": "b"}, {"range": "c", "onclick": "y"})
        self.assertEqual([r.get("onClick") for r in got], ["x", None, "y"])

    def test_a_nodes_own_onclick_is_not_an_alias(self):
        tree, warnings = self.canon.canonicalize({"type": "Label", "text": "t", "onclick": "tap"}, add_marker=False)
        self.assertEqual(tree, {"type": "Label", "text": "t", "onclick": "tap"})
        self.assertEqual(warnings, [])

    def test_idempotent(self):
        once, _ = self.ranges({"range": "Terms", "onclick": "onTerms"})
        twice, w2 = self.ranges(*once)
        self.assertEqual(once, twice)
        self.assertEqual(w2, [])


class RealDefinitionsTest(unittest.TestCase):
    """The shared definitions declare the alias on Label's and Button's ranges."""

    def test_label_and_button_ranges_fold_onclick(self):
        table = AliasTable.from_file()
        for component in ("Label", "Button"):
            self.assertEqual(table.item_aliases_for(component).get("partialAttributes"), {"onclick": "onClick"}, component)
        canon = Canonicalizer(table)
        tree, _ = canon.canonicalize(
            {"type": "Button", "text": "Terms", "partialAttributes": [{"range": "Terms", "onclick": "go"}]}, add_marker=False
        )
        self.assertEqual(tree["partialAttributes"], [{"range": "Terms", "onClick": "go"}])


if __name__ == "__main__":
    unittest.main()
