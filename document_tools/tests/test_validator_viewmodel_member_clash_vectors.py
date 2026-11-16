"""jsonui-doc validate spec refuses a viewModel method the generated
protocol cannot hold next to a var — the same set jui build refuses
(jui_tools/tests/test_viewmodel_member_clash_vectors.py), from the same
table, shared/core/viewmodel_member_clash_vectors.json. Up to jsonui-cli
1.9.21 the ticket's spec (var messageUuid beside setMessageUuid(String))
validated PASSED and the Kotlin protocol did not compile (ticket
jui-protocol-var-and-setter-method-clash-on-jvm).
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonui_doc_cli.spec_doc.validator import SpecValidator

VECTORS = json.loads(
    (Path(__file__).resolve().parents[2] / "shared/core/viewmodel_member_clash_vectors.json")
    .read_text(encoding="utf-8"))["cases"]

RULE_MARKERS = {
    "android": "Platform declaration clash",
    "ios": "invalid redeclaration",
}


def _spec(case: dict) -> dict:
    return {
        "type": "screen_spec",
        "version": "1.0",
        "metadata": {
            "name": "Clash",
            "displayName": "Clash",
            "description": "A viewModel whose members may collide.",
            "layoutFile": "clash",
        },
        "structure": {"components": [], "layout": {}},
        "dataFlow": {"viewModel": {"description": "VM",
                                   "vars": case["vars"], "methods": case["methods"]}},
        "stateManagement": {"uiVariables": [], "eventHandlers": []},
    }


def _clash_errors(case: dict):
    result = SpecValidator().validate_data(_spec(case))
    return [e for e in result.errors
            if any(m in e.message for m in RULE_MARKERS.values())]


class JsonuiDocRefusesExactlyTheRejectCases(unittest.TestCase):
    def test_the_table_is_read(self):
        self.assertGreater(len(VECTORS), 30)
        self.assertEqual({c["expect"] for c in VECTORS}, {"reject", "accept"})

    def test_each_case(self):
        for case in VECTORS:
            with self.subTest(case=case["id"]):
                errors = _clash_errors(case)
                fired = sorted(r for r, m in RULE_MARKERS.items()
                               if any(m in e.message for e in errors))
                self.assertEqual(fired, sorted(case["rules"]),
                                 [e.message for e in errors])
                self.assertEqual(len(errors), len(case["rules"]),
                                 [e.message for e in errors])

    def test_the_error_points_at_the_method_and_names_the_var(self):
        case = next(c for c in VECTORS if c["id"] == "c01_var_setX")
        (error,) = _clash_errors(case)
        self.assertEqual(error.path, "dataFlow.viewModel.methods[0]")
        self.assertIn("'setMessageUuid'", error.message)
        self.assertIn("'messageUuid'", error.message)


if __name__ == "__main__":
    unittest.main()
