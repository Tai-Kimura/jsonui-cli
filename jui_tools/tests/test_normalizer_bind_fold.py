"""`bind` beside a component's own value attribute, folded by the L1
canonicalizer, against the shared table (shared/core/bind_fold_vectors.json).

SSoT common.bind: "an alternative spelling to each component's own value
attribute, which takes precedence when both are set"; ``primaryValue`` names,
per section, the attribute a lone `bind` stands for and the other spellings of
that value. The converters disagreed (rjui and sjui's Switch took the own
attribute, sjui's CheckBox the binding, kjui showed one and wrote the other);
the normalizer settles it in one place.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from jui_cli.core.normalizer import AliasTable, Canonicalizer

VECTORS = Path(__file__).resolve().parents[2] / "shared" / "core" / "bind_fold_vectors.json"


class BindFoldVectorsTest(unittest.TestCase):
    def setUp(self):
        self.canon = Canonicalizer(AliasTable.from_file())

    def test_every_case_of_the_shared_table(self):
        cases = json.loads(VECTORS.read_text())["cases"]
        self.assertGreaterEqual(len(cases), 12)
        for case in cases:
            with self.subTest(case["name"]):
                tree, warnings = self.canon.canonicalize(case["node"], add_marker=False)
                self.assertEqual(tree, case["expect"])
                # The normalizer says the "is ignored" sentences, where it folds;
                # any other sentence (a Collection's bind) is the validator's,
                # said on the layout the normalizer leaves it in.
                folded = [w for w in warnings if "is ignored:" in w or "'bind" in w]
                if case["warning"] is None or "is ignored:" not in case["warning"]:
                    self.assertEqual(folded, [])
                else:
                    self.assertEqual(len(folded), 1)
                    self.assertTrue(folded[0].endswith(case["warning"]), folded[0])

    def test_every_attributes_for_case(self):
        # The one function every reader of primaryValue answers the same
        # (the generated JsonUIBindPrimaryValue on Kotlin / Swift, the shared
        # validator): here, AliasTable.bind_value_attributes.
        cases = json.loads(VECTORS.read_text())["attributes_for_cases"]
        self.assertGreaterEqual(len(cases), 7)
        table = AliasTable.from_file()
        for case in cases:
            with self.subTest(case["name"]):
                self.assertEqual(table.bind_value_attributes(case["type"], case["node"]), case["expect"])

    def test_the_table_is_the_declaration(self):
        # Swap the authority: a section the declaration maps elsewhere folds
        # there, and one it does not map keeps its bind (a list hard-coded in
        # the canonicalizer would not follow).
        defs = {"common": {"bind": {"type": "binding", "primaryValue": {"Switch": ["checked"]}}},
                "Switch": {"isOn": {"type": "boolean"}, "checked": {"type": "boolean"}},
                "Slider": {"value": {"type": "number"}}}
        canon = Canonicalizer(AliasTable(defs))
        tree, _ = canon.canonicalize({"type": "Switch", "bind": "@{on}"}, add_marker=False)
        self.assertEqual(tree, {"type": "Switch", "checked": "@{on}"})
        tree, warnings = canon.canonicalize({"type": "Slider", "bind": "@{v}"}, add_marker=False)
        self.assertEqual(tree, {"type": "Slider", "bind": "@{v}"})
        self.assertEqual(warnings, [])

    def test_a_list_by_another_attribute_follows_the_declaration(self):
        # A section whose value depends on another attribute (SelectBox by
        # selectItemType): the list is picked by the node's value of it, else
        # whenAbsent. Swapping the declared lists moves the fold with them.
        entry = {"by": "kind", "whenAbsent": "A", "lists": {"A": ["first"], "B": ["second"]}}
        defs = {"common": {"bind": {"type": "binding", "primaryValue": {"Box": entry}}},
                "Box": {"kind": {"type": "string", "enum": ["A", "B"]},
                        "first": {"type": "string"}, "second": {"type": "string"}}}
        canon = Canonicalizer(AliasTable(defs))
        for node, folded in [
            ({"type": "Box", "bind": "@{v}"}, {"type": "Box", "first": "@{v}"}),
            ({"type": "Box", "kind": "A", "bind": "@{v}"}, {"type": "Box", "kind": "A", "first": "@{v}"}),
            ({"type": "Box", "kind": "B", "bind": "@{v}"}, {"type": "Box", "kind": "B", "second": "@{v}"}),
            # a value the lists do not name is the whenAbsent one
            ({"type": "Box", "kind": "b", "bind": "@{v}"}, {"type": "Box", "kind": "b", "first": "@{v}"}),
            # the other kind's attribute is not this kind's value: bind still folds
            ({"type": "Box", "kind": "B", "first": "x", "bind": "@{v}"},
             {"type": "Box", "kind": "B", "first": "x", "second": "@{v}"}),
        ]:
            with self.subTest(node=node):
                tree, _ = canon.canonicalize(node, add_marker=False)
                self.assertEqual(tree, folded)
        swapped = dict(entry, lists={"A": ["second"], "B": ["first"]})
        defs["common"]["bind"]["primaryValue"]["Box"] = swapped
        tree, _ = Canonicalizer(AliasTable(defs)).canonicalize({"type": "Box", "kind": "B", "bind": "@{v}"}, add_marker=False)
        self.assertEqual(tree, {"type": "Box", "kind": "B", "first": "@{v}"})

    def test_nested_and_idempotent(self):
        layout = {"type": "View", "child": [{"type": "Switch", "isOn": True, "bind": "@{on}"},
                                            {"type": "Toggle", "bind": "@{t}"}]}
        once, warnings = self.canon.canonicalize(layout)
        self.assertEqual(once["child"][0], {"type": "Switch", "isOn": True})
        self.assertEqual(once["child"][1], {"type": "Switch", "isOn": "@{t}"})
        twice, again = self.canon.canonicalize(once)
        self.assertEqual(twice, once)
        self.assertEqual([w for w in again if "is ignored:" in w], [])


if __name__ == "__main__":
    unittest.main()
