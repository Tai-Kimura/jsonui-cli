"""Tests for branchContracts validation (P1: schema + validate + vocabulary lint).

Exercises _validate_branch_contracts through the public validate_data()
entry point so error paths match the real CLI flow.

Design source: docs/plans/2026-08-24-spec-branch-declarations-feasibility.md
and the P0 pilot (2026-08-24-branch-declarations-p0-pilot.md). The
vocabulary is closed: unknown KEYS are errors; unknown data-field NAMES are
warnings (VM-internal state may intentionally stay undeclared); reference
checks are skipped when the referenced declaration section is absent.
"""
from __future__ import annotations

import unittest

from jsonui_doc_cli.spec_doc.validator import SpecValidator


def _base_spec(branch_contracts, *, vm_methods=None, ui_vars=None,
               repositories=None, use_cases=None, transitions=None,
               states=None):
    spec = {
        "type": "screen_spec",
        "version": "1.0",
        "metadata": {
            "name": "Checkout",
            "displayName": "Checkout",
            "description": "Checkout confirmation screen.",
            "layoutFile": "checkout",
        },
        "structure": {"components": [], "layout": {}},
        "dataFlow": {
            "viewModel": {
                "description": "Checkout VM",
                "methods": vm_methods if vm_methods is not None else [],
                "vars": [],
            },
        },
        "stateManagement": {
            "uiVariables": ui_vars if ui_vars is not None else [],
            "eventHandlers": [],
        },
        "branchContracts": branch_contracts,
    }
    if repositories is not None:
        spec["dataFlow"]["repositories"] = repositories
    if use_cases is not None:
        spec["dataFlow"]["useCases"] = use_cases
    if transitions is not None:
        spec["transitions"] = transitions
    if states is not None:
        spec["stateManagement"]["states"] = states
    return spec


def _ui_var(name, type_="Bool"):
    return {"name": name, "type": type_, "description": name}


def _errors_at(result, path_substr):
    return [e for e in result.errors if path_substr in e.path]


def _warnings_at(result, path_substr):
    return [w for w in result.warnings if path_substr in w.path]


def _validate(spec):
    return SpecValidator().validate_data(spec)


class BranchContractsOptIn(unittest.TestCase):
    def test_absent_section_changes_nothing(self):
        spec = _base_spec({})
        del spec["branchContracts"]
        result = _validate(spec)
        self.assertEqual(_errors_at(result, "branchContracts"), [])
        self.assertEqual(_warnings_at(result, "branchContracts"), [])

    def test_minimal_valid_contract_passes(self):
        spec = _base_spec(
            {
                "methods": {
                    "onConfirmTap": {
                        "branches": [
                            {"when": {"data.isAgreed": False},
                             "then": {"api": "none"}},
                        ]
                    }
                }
            },
            vm_methods=["onConfirmTap"],
            ui_vars=[_ui_var("isAgreed")],
        )
        result = _validate(spec)
        self.assertEqual(_errors_at(result, "branchContracts"), [])
        self.assertEqual(_warnings_at(result, "branchContracts"), [])

    def test_non_object_section_is_error(self):
        result = _validate(_base_spec(["not", "an", "object"]))
        self.assertTrue(_errors_at(result, "branchContracts"))

    def test_unknown_top_level_key_is_error(self):
        result = _validate(_base_spec({
            "branchTables": {},
            "methods": {},
        }))
        errs = _errors_at(result, "branchContracts.branchTables")
        self.assertTrue(errs)


class BranchConditions(unittest.TestCase):
    def _spec(self, conditions, branches=None):
        return _base_spec(
            {
                "conditions": conditions,
                "methods": {
                    "onConfirmTap": {
                        "branches": branches or [
                            {"when": {"data.isAgreed": True},
                             "then": {"api": "none"}},
                        ]
                    }
                },
            },
            vm_methods=["onConfirmTap"],
            ui_vars=[_ui_var("isAgreed"), _ui_var("payNowAmount", "Int")],
        )

    def test_valid_condition_with_witnesses_passes(self):
        spec = self._spec({
            "needsPayment": {
                "meaning": "there is an amount to pay now",
                "witness_true": {"payNowAmount": 1000},
                "witness_false": {"payNowAmount": 0},
            }
        })
        result = _validate(spec)
        self.assertEqual(_errors_at(result, "branchContracts"), [])
        self.assertEqual(_warnings_at(result, "branchContracts"), [])

    def test_missing_meaning_is_error(self):
        spec = self._spec({"needsPayment": {"witness_true": {"payNowAmount": 1}}})
        self.assertTrue(_errors_at(
            _validate(spec), "branchContracts.conditions.needsPayment.meaning"))

    def test_non_camel_condition_name_is_error(self):
        spec = self._spec({"needs_payment": {"meaning": "snake"}})
        self.assertTrue(_errors_at(
            _validate(spec), "branchContracts.conditions.needs_payment"))

    def test_unknown_condition_key_is_error(self):
        spec = self._spec({
            "needsPayment": {"meaning": "x", "witnessTrue": {"payNowAmount": 1}}
        })
        self.assertTrue(_errors_at(
            _validate(spec),
            "branchContracts.conditions.needsPayment.witnessTrue"))

    def test_undeclared_witness_field_is_warning(self):
        spec = self._spec({
            "needsPayment": {"meaning": "x", "witness_true": {"ghostField": 1}}
        })
        result = _validate(spec)
        self.assertEqual(_errors_at(result, "witness_true"), [])
        self.assertTrue(_warnings_at(result, "witness_true.ghostField"))

    def test_witness_check_skipped_without_declarations(self):
        # No uiVariables / vars / states declared → cannot prove dangling.
        spec = _base_spec(
            {
                "conditions": {
                    "needsPayment": {"meaning": "x",
                                     "witness_true": {"anything": 1}}
                },
                "methods": {},
            },
        )
        result = _validate(spec)
        self.assertEqual(_warnings_at(result, "witness_true"), [])


class BranchMethodReferences(unittest.TestCase):
    def test_undeclared_method_is_error(self):
        spec = _base_spec(
            {"methods": {"onGhostTap": {"branches": [
                {"when": {"data.isAgreed": True}, "then": {"api": "none"}},
            ]}}},
            vm_methods=["onConfirmTap"],
            ui_vars=[_ui_var("isAgreed")],
        )
        self.assertTrue(_errors_at(
            _validate(spec), "branchContracts.methods.onGhostTap"))

    def test_method_check_skipped_without_declarations(self):
        spec = _base_spec(
            {"methods": {"onGhostTap": {"branches": [
                {"when": {"data.isAgreed": True}, "then": {"api": "none"}},
            ]}}},
            ui_vars=[_ui_var("isAgreed")],
        )
        # vm_methods=[] + eventHandlers=[] → empty declared set → skip.
        result = _validate(spec)
        self.assertEqual(
            [e for e in _errors_at(result, "branchContracts.methods.onGhostTap")
             if "not found" in e.message],
            [],
        )

    def test_event_handler_method_is_accepted(self):
        spec = _base_spec(
            {"methods": {"onRetryTap": {"branches": [
                {"when": {"data.isAgreed": True}, "then": {"api": "none"}},
            ]}}},
            vm_methods=["onConfirmTap"],
            ui_vars=[_ui_var("isAgreed")],
        )
        spec["stateManagement"]["eventHandlers"] = [
            {"name": "onRetryTap", "description": "retry"},
        ]
        result = _validate(spec)
        self.assertEqual(
            [e for e in _errors_at(result, "branchContracts.methods.onRetryTap")
             if "not found" in e.message],
            [],
        )

    def test_empty_branches_is_error(self):
        spec = _base_spec(
            {"methods": {"onConfirmTap": {"branches": []}}},
            vm_methods=["onConfirmTap"],
        )
        self.assertTrue(_errors_at(
            _validate(spec), "branchContracts.methods.onConfirmTap.branches"))

    def test_unknown_contract_key_is_error(self):
        spec = _base_spec(
            {"methods": {"onConfirmTap": {
                "branches": [{"when": {"data.isAgreed": True},
                              "then": {"api": "none"}}],
                "witnesses": {},
            }}},
            vm_methods=["onConfirmTap"],
            ui_vars=[_ui_var("isAgreed")],
        )
        self.assertTrue(_errors_at(
            _validate(spec), "branchContracts.methods.onConfirmTap.witnesses"))

    def test_baseline_witness_fields_are_checked(self):
        spec = _base_spec(
            {"methods": {"onConfirmTap": {
                "baseline": {"ghostField": True},
                "branches": [{"when": {"data.isAgreed": True},
                              "then": {"api": "none"}}],
            }}},
            vm_methods=["onConfirmTap"],
            ui_vars=[_ui_var("isAgreed")],
        )
        self.assertTrue(_warnings_at(
            _validate(spec), "baseline.ghostField"))


class BranchWhenVocabulary(unittest.TestCase):
    def _spec(self, when, *, conditions=None):
        bc = {
            "methods": {"onConfirmTap": {"branches": [
                {"when": when, "then": {"api": "none"}},
            ]}},
        }
        if conditions is not None:
            bc["conditions"] = conditions
        return _base_spec(
            bc,
            vm_methods=["onConfirmTap"],
            ui_vars=[_ui_var("isAgreed"), _ui_var("mode", "String")],
            use_cases=[{"name": "ConfirmUseCase",
                        "methods": [{"name": "confirmBooking"}]}],
        )

    def test_unknown_when_key_is_error(self):
        result = _validate(self._spec({"state.isAgreed": True}))
        errs = _errors_at(result, "when.state.isAgreed")
        self.assertTrue(errs)
        self.assertIn("Unknown when key", errs[0].message)

    def test_data_scalar_values_pass(self):
        for value in (True, "daily", 0, None):
            result = _validate(self._spec({"data.mode": value}))
            self.assertEqual(_errors_at(result, "when.data.mode"), [],
                             f"value {value!r} should be accepted")

    def test_data_object_value_is_error(self):
        result = _validate(self._spec({"data.mode": {"nested": 1}}))
        self.assertTrue(_errors_at(result, "when.data.mode"))

    def test_undeclared_data_field_is_warning(self):
        result = _validate(self._spec({"data.ghostField": True}))
        self.assertEqual(_errors_at(result, "when.data.ghostField"), [])
        self.assertTrue(_warnings_at(result, "when.data.ghostField"))

    def test_non_camel_data_field_is_error(self):
        result = _validate(self._spec({"data.is_agreed": True}))
        self.assertTrue(_errors_at(result, "when.data.is_agreed"))

    def test_arg_scalar_passes_and_object_fails(self):
        self.assertEqual(
            _errors_at(_validate(self._spec({"arg.paymentType": "card"})),
                       "when.arg.paymentType"),
            [])
        self.assertTrue(
            _errors_at(_validate(self._spec({"arg.paymentType": ["a"]})),
                       "when.arg.paymentType"))

    def test_api_scenario_string_passes(self):
        result = _validate(self._spec({"api.confirmBooking": "error_409"}))
        self.assertEqual(_errors_at(result, "when.api.confirmBooking"), [])
        self.assertEqual(_warnings_at(result, "when.api.confirmBooking"), [])

    def test_api_non_string_scenario_is_error(self):
        result = _validate(self._spec({"api.confirmBooking": 409}))
        self.assertTrue(_errors_at(result, "when.api.confirmBooking"))

    def test_api_undeclared_op_is_warning(self):
        result = _validate(self._spec({"api.ghostOp": "error"}))
        self.assertEqual(_errors_at(result, "when.api.ghostOp"), [])
        self.assertTrue(_warnings_at(result, "when.api.ghostOp"))

    def test_api_request_suffix_in_when_is_error(self):
        result = _validate(self._spec({"api.confirmBooking.request": "x"}))
        self.assertTrue(_errors_at(result, "when.api.confirmBooking.request"))

    def test_cond_reference_resolves(self):
        conditions = {"needsPayment": {"meaning": "x"}}
        for ref in ("needsPayment", "!needsPayment"):
            result = _validate(self._spec({"cond": ref}, conditions=conditions))
            self.assertEqual(_errors_at(result, "when.cond"), [],
                             f"cond {ref!r} should resolve")

    def test_cond_undeclared_reference_is_error(self):
        result = _validate(self._spec({"cond": "ghostCond"},
                                      conditions={}))
        self.assertTrue(_errors_at(result, "when.cond"))


class BranchThenVocabulary(unittest.TestCase):
    def _spec(self, then, *, transitions=None):
        return _base_spec(
            {"methods": {"onConfirmTap": {"branches": [
                {"when": {"data.isAgreed": True}, "then": then},
            ]}}},
            vm_methods=["onConfirmTap"],
            ui_vars=[
                _ui_var("isAgreed"),
                _ui_var("screenState", "String"),
                _ui_var("errorMessage", "String"),
                _ui_var("fingerprint", "String"),
            ],
            use_cases=[{"name": "ConfirmUseCase",
                        "methods": [{"name": "confirmBooking"}]}],
            transitions=transitions,
        )

    def test_unknown_then_key_is_error(self):
        result = _validate(self._spec({"navigate": "home"}))
        errs = _errors_at(result, "then.navigate")
        self.assertTrue(errs)
        self.assertIn("Unknown then key", errs[0].message)

    def test_data_assignment_literal_passes(self):
        result = _validate(self._spec({"data.screenState": "payment_error"}))
        self.assertEqual(_errors_at(result, "then.data.screenState"), [])

    def test_data_assignment_strings_key_ref_passes(self):
        result = _validate(self._spec({"data.errorMessage": "@fee_mismatch_error"}))
        self.assertEqual(_errors_at(result, "then.data.errorMessage"), [])

    def test_data_assignment_bad_strings_key_is_error(self):
        result = _validate(self._spec({"data.errorMessage": "@FeeMismatch"}))
        self.assertTrue(_errors_at(result, "then.data.errorMessage"))

    def test_data_assignment_data_ref_passes_and_checks_field(self):
        ok = _validate(self._spec({"data.errorMessage": "@data.fingerprint"}))
        self.assertEqual(_errors_at(ok, "then.data.errorMessage"), [])
        ghost = _validate(self._spec({"data.errorMessage": "@data.ghostField"}))
        self.assertTrue(_warnings_at(ghost, "then.data.errorMessage"))

    def test_api_none_passes_other_values_fail(self):
        self.assertEqual(
            _errors_at(_validate(self._spec({"api": "none"})), "then.api"), [])
        result = _validate(self._spec({"api": "skipped"}))
        self.assertTrue(_errors_at(result, "then.api"))

    def test_api_op_verdicts(self):
        for verdict in ("called", "not-called"):
            result = _validate(self._spec({"api.confirmBooking": verdict}))
            self.assertEqual(
                _errors_at(result, "then.api.confirmBooking"), [],
                f"verdict {verdict!r} should be accepted")
        result = _validate(self._spec({"api.confirmBooking": "error_409"}))
        self.assertTrue(_errors_at(result, "then.api.confirmBooking"))

    def test_api_request_partial_match_passes(self):
        result = _validate(self._spec({
            "api.confirmBooking.request": {
                "payment_type": "card",
                "payment_method_id": None,
                "cancel_policy_fingerprint": "@data.fingerprint",
                "nested": {"amount": 1000},
            }
        }))
        self.assertEqual(
            _errors_at(result, "then.api.confirmBooking.request"), [])
        self.assertEqual(
            _warnings_at(result, "then.api.confirmBooking.request"), [])

    def test_api_request_non_object_is_error(self):
        result = _validate(self._spec({"api.confirmBooking.request": "card"}))
        self.assertTrue(_errors_at(result, "then.api.confirmBooking.request"))

    def test_api_request_array_leaf_is_error(self):
        result = _validate(self._spec({
            "api.confirmBooking.request": {"ids": [1, 2]}
        }))
        self.assertTrue(_errors_at(result, "then.api.confirmBooking.request.ids"))

    def test_transition_matches_declared_destination(self):
        transitions = [{"condition": "success", "destination": "booking_complete"}]
        ok = _validate(self._spec({"transition": "booking_complete"},
                                  transitions=transitions))
        self.assertEqual(_warnings_at(ok, "then.transition"), [])
        ghost = _validate(self._spec({"transition": "ghost_screen"},
                                     transitions=transitions))
        self.assertTrue(_warnings_at(ghost, "then.transition"))

    def test_transition_check_skipped_without_transitions(self):
        result = _validate(self._spec({"transition": "anywhere"}))
        self.assertEqual(_warnings_at(result, "then.transition"), [])


class BranchNoteEscapeHatch(unittest.TestCase):
    def _spec(self, branch):
        return _base_spec(
            {"methods": {"onConfirmTap": {"branches": [branch]}}},
            vm_methods=["onConfirmTap"],
            ui_vars=[_ui_var("isAgreed")],
        )

    def test_note_only_branch_passes(self):
        result = _validate(self._spec({"note": "3DS polling is out of v1 scope"}))
        self.assertEqual(_errors_at(result, "branchContracts"), [])

    def test_note_with_when_is_error(self):
        result = _validate(self._spec({
            "note": "half-declared",
            "when": {"data.isAgreed": True},
        }))
        self.assertTrue(_errors_at(result, "branches[0]"))

    def test_empty_note_is_error(self):
        result = _validate(self._spec({"note": ""}))
        self.assertTrue(_errors_at(result, "branches[0].note"))

    def test_branch_missing_then_is_error(self):
        result = _validate(self._spec({"when": {"data.isAgreed": True}}))
        self.assertTrue(_errors_at(result, "branches[0].then"))

    def test_unknown_branch_key_is_error(self):
        result = _validate(self._spec({
            "when": {"data.isAgreed": True},
            "then": {"api": "none"},
            "expect": "x",
        }))
        self.assertTrue(_errors_at(result, "branches[0].expect"))


class BranchContractsPilotShape(unittest.TestCase):
    """The P0 pilot declaration shape (generic vocabulary) must validate clean."""

    def test_pilot_shaped_contract_is_clean(self):
        spec = _base_spec(
            {
                "conditions": {
                    "needsPaymentStep": {
                        "meaning": "an amount is due now",
                        "witness_true": {"payNowAmount": 1000},
                        "witness_false": {"payNowAmount": 0},
                    },
                },
                "methods": {
                    "onConfirmTap": {
                        "baseline": {"isAgreed": True, "payNowAmount": 1000},
                        "branches": [
                            {"when": {"data.isAgreed": False},
                             "then": {"api": "none"}},
                            {"when": {"cond": "!needsPaymentStep"},
                             "then": {"api.registerCard": "not-called",
                                      "api.confirmBooking.request": {
                                          "payment_method_id": None}}},
                            {"when": {"api.confirmBooking": "success"},
                             "then": {"transition": "complete",
                                      "api.confirmBooking.request": {
                                          "fingerprint": "@data.fingerprint"}}},
                            {"when": {"api.confirmBooking": "error_conflict"},
                             "then": {"data.screenState": "payment_error",
                                      "data.errorMessage": "@payment_error_generic"}},
                            {"note": "session cache invalidation is outside the outcome vocabulary"},
                        ],
                    },
                },
            },
            vm_methods=["onConfirmTap"],
            ui_vars=[
                _ui_var("isAgreed"),
                _ui_var("payNowAmount", "Int"),
                _ui_var("screenState", "String"),
                _ui_var("errorMessage", "String"),
                _ui_var("fingerprint", "String"),
            ],
            use_cases=[{"name": "ConfirmUseCase",
                        "methods": [{"name": "confirmBooking"}]}],
            repositories=[{"name": "PaymentRepository",
                           "methods": [{"name": "registerCard"}]}],
            transitions=[{"condition": "success", "destination": "complete"}],
        )
        result = _validate(spec)
        self.assertEqual(_errors_at(result, "branchContracts"), [],
                         f"pilot shape should be clean: "
                         f"{[str(e) for e in _errors_at(result, 'branchContracts')]}")
        self.assertEqual(_warnings_at(result, "branchContracts"), [])


if __name__ == "__main__":
    unittest.main()


class BranchPlatforms(unittest.TestCase):
    def _spec(self, branch):
        return _base_spec(
            {"methods": {"onConfirmTap": {"branches": [branch]}}},
            vm_methods=["onConfirmTap"],
            ui_vars=[_ui_var("isAgreed")],
        )

    def test_valid_platforms_pass(self):
        result = _validate(self._spec({
            "when": {"data.isAgreed": True}, "then": {"api": "none"},
            "platforms": ["android", "ios"],
        }))
        self.assertEqual(_errors_at(result, "branchContracts"), [])

    def test_invalid_platform_value_is_error(self):
        result = _validate(self._spec({
            "when": {"data.isAgreed": True}, "then": {"api": "none"},
            "platforms": ["android", "desktop"],
        }))
        self.assertTrue(_errors_at(result, "branches[0].platforms"))

    def test_empty_platforms_is_error(self):
        result = _validate(self._spec({
            "when": {"data.isAgreed": True}, "then": {"api": "none"},
            "platforms": [],
        }))
        self.assertTrue(_errors_at(result, "branches[0].platforms"))
