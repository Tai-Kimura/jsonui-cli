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
