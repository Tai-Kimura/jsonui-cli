"""jui build refuses a viewModel method the generated protocol cannot hold
next to a var: a var's JVM getter/setter name on Android (Kotlin "Platform
declaration clash"), the var's own name with no arguments on iOS (Swift
"invalid redeclaration"). Up to jsonui-cli 1.9.21 the spec validated and
built, and the Kotlin protocol did not compile (ticket
jui-protocol-var-and-setter-method-clash-on-jvm).

The cases are shared/core/viewmodel_member_clash_vectors.json, which
document_tools/tests/test_validator_viewmodel_member_clash_vectors.py runs
through jsonui-doc validate spec: the two gates must refuse the same set.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from jui_cli.core.spec_extractor import extract_screen_spec
from jui_cli.core.spec_validator import (
    SpecValidationError,
    kotlin_accessor_names,
    validate_screen_spec,
)

VECTORS = json.loads(
    (Path(__file__).resolve().parents[2] / "shared/core/viewmodel_member_clash_vectors.json")
    .read_text(encoding="utf-8"))["cases"]

#: The words each platform's ERROR carries.
RULE_MARKERS = {
    "android": "Platform declaration clash",
    "ios": "invalid redeclaration",
}


def _spec(case: dict):
    return extract_screen_spec({
        "type": "screen_spec",
        "metadata": {"name": "Clash", "layoutFile": "clash"},
        "dataFlow": {"viewModel": {"vars": case["vars"], "methods": case["methods"]}},
    })


def _clash_errors(case: dict) -> list[str]:
    try:
        validate_screen_spec(_spec(case))
    except SpecValidationError as e:
        return [line for line in str(e).splitlines()
                if any(m in line for m in RULE_MARKERS.values())]
    return []


class TheVectorsHoldBothSides(unittest.TestCase):
    def test_the_table_has_cases_on_both_sides_of_every_rule(self):
        expects = {c["expect"] for c in VECTORS}
        self.assertEqual(expects, {"reject", "accept"})
        rules = {r for c in VECTORS for r in c["rules"]}
        self.assertEqual(rules, set(RULE_MARKERS))
        ids = [c["id"] for c in VECTORS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("c01_var_setX", ids)


class JuiBuildRefusesExactlyTheRejectCases(unittest.TestCase):
    def test_each_case(self):
        for case in VECTORS:
            with self.subTest(case=case["id"]):
                errors = _clash_errors(case)
                fired = sorted(r for r, m in RULE_MARKERS.items()
                               if any(m in e for e in errors))
                self.assertEqual(fired, sorted(case["rules"]), errors)
                self.assertEqual(len(errors), len(case["rules"]), errors)
                if case["expect"] == "reject":
                    self.assertTrue(errors)
                else:
                    self.assertEqual(errors, [])

    def test_the_error_names_both_members(self):
        case = next(c for c in VECTORS if c["id"] == "c01_var_setX")
        (error,) = _clash_errors(case)
        self.assertIn("viewModel.methods['setMessageUuid']", error)
        self.assertIn("viewModel.vars['messageUuid']", error)


class KotlinAccessorNames(unittest.TestCase):
    def test_the_is_form_is_decided_by_the_third_character(self):
        self.assertEqual(kotlin_accessor_names("isOpen"), ("isOpen", "setOpen"))
        self.assertEqual(kotlin_accessor_names("is1"), ("is1", "set1"))
        self.assertEqual(kotlin_accessor_names("is_open"), ("is_open", "set_open"))
        self.assertEqual(kotlin_accessor_names("island"), ("getIsland", "setIsland"))
        self.assertEqual(kotlin_accessor_names("is"), ("getIs", "setIs"))
        self.assertEqual(kotlin_accessor_names("URL"), ("getURL", "setURL"))
        self.assertEqual(kotlin_accessor_names("url"), ("getUrl", "setUrl"))


if __name__ == "__main__":
    unittest.main()
