"""`unitContracts` shape validation in `jsonui-doc validate spec`.

The section declares the SET of hand-written unit cases a screen owns, so two
platforms implementing one spec cannot drift apart. Only the set is checked;
the bodies stay hand-written.

Why the shape is checked HERE and not only in `jsonui-test generate
unit-stubs --check`: the person writing a spec runs this gate. In 1.8.24 a
misspelled key made a whole declaration vanish while both gates printed clean
zeros, and 1.8.25 closed it on the unit-stubs side only — leaving the error
and its discovery far apart, because a spec author would see PASSED and not
learn otherwise until someone ran the other command.
"""
from __future__ import annotations

import unittest

from jsonui_doc_cli.spec_doc.validator import SpecValidator


def _spec(unit_contracts):
    return {
        "type": "screen_spec",
        "version": "1.0",
        "metadata": {
            "name": "Chat",
            "displayName": "Chat",
            "description": "Chat screen.",
            "layoutFile": "chat",
        },
        "structure": {"components": [], "layout": {}},
        "dataFlow": {"viewModel": {"description": "VM", "methods": [], "vars": []}},
        "stateManagement": {"uiVariables": [], "eventHandlers": []},
        "unitContracts": unit_contracts,
    }


def _errors(unit_contracts):
    result = SpecValidator().validate_data(_spec(unit_contracts), "chat.spec.json")
    return [f"{e.path}: {e.message}" for e in result.errors]


_OK = {"target": "ChatViewModel",
       "cases": [{"name": "sends_when_online", "intent": "sends", "platforms": ["ios"]}]}


class UnitContractsShape(unittest.TestCase):

    def test_a_well_formed_block_is_clean(self):
        # Positive control. Everything below has to be measured against a
        # shape that genuinely passes, or "it errors" proves nothing.
        self.assertEqual(_errors(_OK), [])

    def test_absent_section_is_clean(self):
        spec = _spec(_OK)
        del spec["unitContracts"]
        result = SpecValidator().validate_data(spec, "chat.spec.json")
        self.assertEqual([e.message for e in result.errors], [])

    def test_a_misspelled_block_key_is_an_error(self):
        # The reported shape: one typo removed an entire declaration.
        errs = _errors({"target": "VM", "caes": [{"name": "x"}]})
        self.assertTrue(any("caes" in e and "Unknown unitContracts key" in e for e in errs), errs)
        self.assertTrue(any("drops the whole declaration" in e for e in errs), errs)

    def test_a_misspelled_case_key_is_an_error(self):
        errs = _errors({"target": "VM", "cases": [{"name": "x", "platfroms": ["ios"]}]})
        self.assertTrue(any("platfroms" in e and "Unknown case key" in e for e in errs), errs)

    def test_missing_target_is_an_error(self):
        errs = _errors({"cases": [{"name": "x"}]})
        self.assertTrue(any("'target' is required" in e for e in errs), errs)

    def test_missing_cases_is_an_error(self):
        errs = _errors({"target": "VM"})
        self.assertTrue(any("'cases' is required" in e for e in errs), errs)

    def test_cases_of_the_wrong_type_is_an_error(self):
        errs = _errors({"target": "VM", "cases": "not-an-array"})
        self.assertTrue(any("must be an array" in e for e in errs), errs)

    def test_a_case_without_a_name_is_an_error(self):
        # `name` is what the two platforms are compared on; without it the
        # case cannot participate in the comparison it exists for.
        errs = _errors({"target": "VM", "cases": [{"intent": "does a thing"}]})
        self.assertTrue(any("'name' is required" in e for e in errs), errs)

    def test_a_duplicate_case_name_is_an_error(self):
        # The set is compared by name, so a duplicate hides one of the two.
        errs = _errors({"target": "VM", "cases": [{"name": "same"}, {"name": "same"}]})
        self.assertTrue(any("Duplicate case name" in e for e in errs), errs)

    def test_an_unknown_platform_is_an_error(self):
        errs = _errors({"target": "VM", "cases": [{"name": "x", "platforms": ["iOS"]}]})
        self.assertTrue(any("Unknown platform" in e for e in errs), errs)

    def test_omitted_platforms_is_allowed(self):
        # Positive control for the arm above: absent means "every platform
        # the project builds", which is a legitimate declaration.
        self.assertEqual(_errors({"target": "VM", "cases": [{"name": "x"}]}), [])

    def test_an_empty_platforms_array_is_an_error(self):
        # Distinct from omitting it: an empty list says "no platforms", which
        # would declare a case nothing has to implement.
        errs = _errors({"target": "VM", "cases": [{"name": "x", "platforms": []}]})
        self.assertTrue(any("non-empty array" in e for e in errs), errs)

    def test_an_empty_block_is_an_error(self):
        errs = _errors([])
        self.assertTrue(any("declares nothing" in e for e in errs), errs)

    def test_an_array_of_blocks_is_accepted(self):
        self.assertEqual(_errors([_OK]), [])


if __name__ == "__main__":
    unittest.main()
