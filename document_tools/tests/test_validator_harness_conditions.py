"""`jsonui-doc validate spec` admits harness conditions and shapes them (P2d).

Two sites. The app contracts spec's `harnessConditions` is shaped by the one
parser `contracts coverage` reads with (`jsonui_test_cli.contract_declarations`);
the validator's own allowlist is what lets the key through at all. A row's
`when` key `harness.<name>` joins the closed when vocabulary here, beside
`cond` — which names a branchContracts.conditions witness and is a different
thing, so the unknown-key message lists both, each with what it is.

Whether the app declares the name and the value needs both documents; that
is the generator's and coverage's (red-check xxviii), not this lint's.
"""
from __future__ import annotations

import copy
import unittest

from jsonui_doc_cli.spec_doc.validator import SpecValidator
from test_validator_contract_declarations import _app, _screen

SESSION = {"session": {"values": ["absent", "present"], "default": "absent",
                       "reason": "whether a user is signed in"}}


def _errors(spec):
    return SpecValidator().validate_data(spec, "spec").errors


def _with_when(key, value):
    spec = copy.deepcopy(_screen())
    spec["branchContracts"]["methods"]["confirm"]["branches"][0]["when"][key] = value
    return spec


WHEN_PATH = "branchContracts.methods.confirm.branches[0].when"


class TheWhenKey(unittest.TestCase):
    def test_a_harness_key_with_a_string_value_adds_no_error(self):
        self.assertEqual(
            sorted(e.path for e in _errors(_with_when("harness.session", "present"))),
            sorted(e.path for e in _errors(_screen())))

    def test_a_non_string_value_is_an_error(self):
        errors = [e for e in _errors(_with_when("harness.session", True))
                  if e.path == f"{WHEN_PATH}.harness.session"]
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("declared values", errors[0].message)

    def test_a_name_that_is_not_an_identifier_is_an_error(self):
        errors = [e for e in _errors(_with_when("harness.signed-in", "yes"))
                  if e.path == f"{WHEN_PATH}.harness.signed-in"]
        self.assertEqual(len(errors), 1, errors)

    def test_the_old_spelling_is_an_unknown_key_that_names_both(self):
        """`condition.<name>` was the draft's spelling; it reads like `cond`."""
        errors = [e for e in _errors(_with_when("condition.session", "present"))
                  if e.path == f"{WHEN_PATH}.condition.session"]
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("'cond' (a branchContracts.conditions witness)", errors[0].message)
        self.assertIn("'harness.<name>' (a precondition the harness sets up", errors[0].message)


class TheAppDeclaration(unittest.TestCase):
    def test_a_well_formed_declaration_adds_no_error(self):
        self.assertEqual(_errors(_app(harnessConditions=SESSION)), [])

    def test_the_key_is_admitted_not_just_parsed(self):
        # Without it in the allowlist: "Unknown app_contracts_spec key".
        paths = [e.path for e in _errors(_app(harnessConditions=SESSION))]
        self.assertNotIn("harnessConditions", paths)

    def test_the_parser_shapes_it(self):
        bad = {"session": {"values": ["only"], "default": "only", "reason": "r"}}
        paths = [e.path for e in _errors(_app(harnessConditions=bad))]
        self.assertIn("harnessConditions.session.values", paths)

    def test_on_a_screen_it_is_refused(self):
        spec = copy.deepcopy(_screen())
        spec["harnessConditions"] = SESSION
        self.assertIn("harnessConditions", [e.path for e in _errors(spec)])


if __name__ == "__main__":
    unittest.main()
