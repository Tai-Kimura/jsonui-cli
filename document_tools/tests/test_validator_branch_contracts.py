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
        spec = self._spec(
            {
                "needsPayment": {
                    "meaning": "there is an amount to pay now",
                    "witness_true": {"payNowAmount": 1000},
                    "witness_false": {"payNowAmount": 0},
                }
            },
            # Gated on, so the condition is not flagged as a declaration
            # whose witnesses nothing ever arranges.
            branches=[
                {"when": {"cond": "needsPayment"}, "then": {"api": "none"}},
                {"when": {"cond": "!needsPayment"}, "then": {"api": "none"}},
            ],
        )
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
            # Declared with its parameter, so `arg.paymentType` below is
            # about the VALUE's shape and not about whether the argument
            # binds to anything (that is BranchArgBindings' subject).
            vm_methods=[{"name": "onConfirmTap",
                         "params": [{"name": "paymentType", "type": "String"}]}],
            ui_vars=[_ui_var("isAgreed"), _ui_var("mode", "String")],
            use_cases=[{"name": "ConfirmUseCase",
                        "methods": [{"name": "confirmBooking"}]}],
        )

    def test_unknown_when_key_is_error(self):
        # `vm.` is not a prefix the vocabulary has. (`state.` used to serve
        # as this fixture; it is now the seedable-state namespace, and an
        # undeclared name there gets its own message — see
        # BranchSeedableState. Either way it is an error.)
        result = _validate(self._spec({"vm.isAgreed": True}))
        errs = _errors_at(result, "when.vm.isAgreed")
        self.assertTrue(errs)
        self.assertIn("Unknown when key", errs[0].message)
        self.assertIn("state.<name>", errs[0].message)

    def test_data_scalar_values_pass(self):
        for value in (True, "compact", 0, None):
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
                "return_policy_digest": "@data.fingerprint",
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

    def test_api_request_scalar_list_leaf_passes(self):
        """Superseded 2026-09-07: this leaf used to be an error.

        The old ruling was that a list under a request leaf had "no defined
        partial-match meaning". It has one — whole-array equality, order
        included — and all three generated runtimes already implement it.
        """
        result = _validate(self._spec({
            "api.confirmBooking.request": {"ids": [1, 2]}
        }))
        self.assertEqual(
            _errors_at(result, "then.api.confirmBooking.request.ids"), [])

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


class BranchThenCollectionEmptiness(unittest.TestCase):
    """`then data.<field>: []` — "this collection is empty afterwards".

    Reported twice on the same day from two screens. A contract that clears
    a list on failure could only be witnessed by a scalar set in the same
    update (a visibility flag), and that witness stays satisfied when only
    the clearing is removed — so the guarantee never reached the observable
    surface. Both reports independently rejected `.length` paths and
    non-empty deep equality; only the empty case is opened here.

    `baseline` already accepted array seeds, so the gap was exactly the
    second half of "seed a loaded list, then assert it is emptied".
    """

    def _spec(self, then, *, baseline=None):
        contract = {"branches": [
            {"when": {"api.confirmBooking": "failure"}, "then": then}]}
        if baseline is not None:
            contract["baseline"] = baseline
        return _base_spec(
            {"methods": {"onConfirmTap": contract}},
            vm_methods=["onConfirmTap"],
            ui_vars=[_ui_var("rows", "[Row]"),
                     _ui_var("pagerVisibility", "String")],
            use_cases=[{"name": "ConfirmUseCase",
                        "methods": [{"name": "confirmBooking"}]}],
        )

    def test_an_empty_list_is_accepted(self):
        result = _validate(self._spec({"data.rows": []}))
        self.assertEqual(_errors_at(result, "then.data.rows"), [])

    def test_the_reported_shape_validates(self):
        """Seed a loaded list in baseline, assert it is emptied afterwards."""
        result = _validate(self._spec(
            {"data.rows": [], "data.pagerVisibility": "gone"},
            baseline={"rows": [{"id": "1"}]},
        ))
        self.assertEqual(_errors_at(result, "branches[0]"), [])

    def test_a_non_empty_list_is_still_rejected(self):
        result = _validate(self._spec({"data.rows": [{"id": "1"}]}))
        self.assertTrue(_errors_at(result, "then.data.rows"))

    def test_an_object_is_still_rejected(self):
        result = _validate(self._spec({"data.rows": {"a": 1}}))
        self.assertTrue(_errors_at(result, "then.data.rows"))

    def test_the_error_says_what_is_accepted_and_what_is_not(self):
        """A non-empty list should read as a scope decision, not an oversight.

        Otherwise the author's next move is to work around a rule whose
        reason they cannot see.
        """
        errs = _errors_at(_validate(self._spec({"data.rows": [1, 2]})),
                          "then.data.rows")
        self.assertTrue(errs)
        msg = errs[0].message
        self.assertIn("'[]'", msg)
        self.assertIn("empty", msg)
        self.assertIn("element-by-element matching is out of scope", msg)

    def test_a_request_match_leaf_takes_a_wider_exception(self):
        """The two sides allow different widths, on purpose.

        `data.<field>` takes `[]` only — matching elements there would bind
        the contract to the mock body. A request leaf takes any list of
        scalars, because there the list IS the value being sent, and the
        runtimes compare it whole.
        """
        result = _validate(
            self._spec({"api.confirmBooking.request": {"tags": []}}))
        self.assertEqual(
            _errors_at(result, "then.api.confirmBooking.request.tags"), [])

    def test_baseline_array_seeds_were_already_allowed(self):
        """Pinned because it is the half that already worked.

        If a later change routes baseline through the then-value check, this
        catches it before the asymmetry is rediscovered from the outside.
        """
        result = _validate(self._spec({"data.pagerVisibility": "gone"},
                                      baseline={"rows": [{"id": "1"}]}))
        self.assertEqual(_errors_at(result, "baseline"), [])


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


class BranchArgBindings(unittest.TestCase):
    """`arg.<name>` builds the generated act call out of the method's
    declared params. An argument that binds to nothing was accepted here and
    then dropped by the generator, so the branch ran with a different input
    than it declared — reported from a screen whose method lived only in
    stateManagement.eventHandlers."""

    def _spec(self, when, *, vm_methods, handlers=None):
        spec = _base_spec(
            {"methods": {"onStatusTap": {"branches": [
                {"when": when, "then": {"api": "none"}},
            ]}}},
            vm_methods=vm_methods,
            ui_vars=[_ui_var("isAgreed")],
        )
        if handlers is not None:
            spec["stateManagement"]["eventHandlers"] = handlers
        return spec

    _METHOD_WITH_PARAM = [{
        "name": "onStatusTap",
        "params": [{"name": "status", "type": "String"}],
    }]

    def test_declared_param_binds(self):
        result = _validate(self._spec(
            {"arg.status": "open"}, vm_methods=self._METHOD_WITH_PARAM))
        self.assertEqual(_errors_at(result, "branchContracts"), [])

    def test_undeclared_param_on_a_declared_method_is_an_error(self):
        result = _validate(self._spec(
            {"arg.mode": "open"}, vm_methods=self._METHOD_WITH_PARAM))
        errors = _errors_at(result, "when.arg.mode")
        self.assertEqual(1, len(errors))
        self.assertIn("declares no parameter", errors[0].message)
        self.assertIn("status", errors[0].message)  # what it does declare

    def test_event_handler_only_method_is_an_error_naming_the_fix(self):
        # eventHandlers carry no signature by design, so this is not a
        # matter of declaring params over there.
        result = _validate(self._spec(
            {"arg.status": "open"},
            vm_methods=[],
            handlers=[{"name": "onStatusTap", "description": "status tap"}],
        ))
        errors = _errors_at(result, "when.arg.status")
        self.assertEqual(1, len(errors))
        self.assertIn("dataFlow.viewModel.methods", errors[0].message)
        self.assertIn("eventHandlers", errors[0].message)

    def test_method_declared_as_a_bare_string_has_no_params(self):
        result = _validate(self._spec(
            {"arg.status": "open"}, vm_methods=["onStatusTap"]))
        errors = _errors_at(result, "when.arg.status")
        self.assertEqual(1, len(errors))
        self.assertIn("(none)", errors[0].message)

    def test_branches_without_args_are_unaffected(self):
        result = _validate(self._spec(
            {"data.isAgreed": True}, vm_methods=["onStatusTap"]))
        self.assertEqual(_errors_at(result, "branchContracts"), [])


class BranchResponsePassthrough(unittest.TestCase):
    """`@response.<path>` pins a value the server chose. Only its shape is
    checkable here — the text lives in the mock scenario — plus the one
    structural precondition: the branch must name a single scenario to read
    the response from."""

    def _spec(self, branch):
        return _base_spec(
            {"methods": {"onConfirmTap": {"branches": [branch]}}},
            vm_methods=["onConfirmTap"],
            ui_vars=[_ui_var("errorMessage", "String"), _ui_var("isAgreed")],
            repositories=[{"name": "OrderRepository", "methods": [
                {"name": "createOrder", "endpoint": "POST /api/orders"},
                {"name": "fetchOrder", "endpoint": "GET /api/orders"},
            ]}],
        )

    def test_response_reference_is_accepted(self):
        result = _validate(self._spec({
            "when": {"api.createOrder": "declined"},
            "then": {"data.errorMessage": "@response.error.message"},
        }))
        self.assertEqual(_errors_at(result, "branchContracts"), [])
        self.assertEqual(_warnings_at(result, "branches[0].then"), [])

    def test_top_level_path_is_accepted(self):
        result = _validate(self._spec({
            "when": {"api.createOrder": "declined"},
            "then": {"data.errorMessage": "@response.detail"},
        }))
        self.assertEqual(_errors_at(result, "branchContracts"), [])

    def test_bare_response_without_a_path_is_an_error(self):
        result = _validate(self._spec({
            "when": {"api.createOrder": "declined"},
            "then": {"data.errorMessage": "@response."},
        }))
        self.assertTrue(_errors_at(result, "branches[0].then"))

    def test_branch_with_no_scenario_is_warned(self):
        # Test generation hard-errors on this; validate says it first.
        result = _validate(self._spec({
            "when": {"data.isAgreed": False},
            "then": {"data.errorMessage": "@response.error.message"},
        }))
        warnings = [w for w in result.warnings if "exactly one" in w.message]
        self.assertEqual(1, len(warnings))

    def test_branch_with_two_scenarios_is_warned(self):
        result = _validate(self._spec({
            "when": {"api.createOrder": "declined", "api.fetchOrder": "ok"},
            "then": {"data.errorMessage": "@response.error.message"},
        }))
        warnings = [w for w in result.warnings if "exactly one" in w.message]
        self.assertEqual(1, len(warnings))

    def test_a_list_position_is_accepted(self):
        """FastAPI's 422 puts the text a screen shows inside `detail[]`, so
        without a numeric segment the one response class where "the screen
        shows what the server sent" is most worth stating is the one class
        that cannot state it.

        THIS GATE RUNS FIRST. The reporting lane named the generator, which
        is the second gate; a spec carrying this path was refused here
        before generation ever read a response body, and with a different
        message. Fixing one of the two would have moved the refusal rather
        than removed it.
        """
        result = _validate(self._spec({
            "when": {"api.createOrder": "declined"},
            "then": {"data.errorMessage": "@response.detail.0.msg"},
        }))
        self.assertEqual(_errors_at(result, "branchContracts"), [])

    def test_bracket_indexing_is_refused_by_name(self):
        """One spelling. The lane that asked for this offered brackets as an
        equally acceptable alternative; the rest of the vocabulary is dotted
        (`@data.<field>`, the `then` keys), and a second spelling is a
        second thing every reader of a contract has to know. So it is
        refused with the form to write instead, rather than accepted."""
        result = _validate(self._spec({
            "when": {"api.createOrder": "declined"},
            "then": {"data.errorMessage": "@response.detail[0].msg"},
        }))
        errors = _errors_at(result, "branches[0].then")
        self.assertTrue(errors)
        self.assertIn("@response.detail.0.msg",
                      " ".join(e.message for e in errors))

    def test_a_path_that_is_neither_is_still_refused(self):
        """The arm that keeps the loosening honest: opening the shape to
        numbers must not open it to anything else."""
        result = _validate(self._spec({
            "when": {"api.createOrder": "declined"},
            "then": {"data.errorMessage": "@response.detail.-1.msg"},
        }))
        self.assertTrue(_errors_at(result, "branches[0].then"))

    def test_branches_without_response_refs_are_unaffected(self):
        result = _validate(self._spec({
            "when": {"data.isAgreed": False},
            "then": {"data.errorMessage": "@checkout_failed"},
        }))
        self.assertEqual(
            [], [w for w in result.warnings if "exactly one" in w.message]
        )


class BranchConditionUsage(unittest.TestCase):
    """Conditions against the branches that gate on them.

    A witness is only worth anything once some branch arranges state with
    it, and a branch can only be arranged when the side it needs exists.
    Warnings: none of this makes an otherwise valid contract invalid.
    """

    def _spec(self, conditions, branches):
        return _base_spec(
            {"conditions": conditions,
             "methods": {"onConfirmTap": {"branches": branches}}},
            vm_methods=["onConfirmTap"],
            ui_vars=[_ui_var("isAgreed")],
        )

    _TRUE = {"isAgreed": True}
    _FALSE = {"isAgreed": False}

    def _cond(self, **kwargs):
        cond = {"meaning": "the terms are accepted"}
        cond.update(kwargs)
        return cond

    def _warnings_containing(self, result, needle):
        return [w for w in result.warnings if needle in w.message]

    def test_condition_gated_on_with_both_witnesses_is_clean(self):
        result = _validate(self._spec(
            {"agreed": self._cond(witness_true=self._TRUE,
                                  witness_false=self._FALSE)},
            [{"when": {"cond": "agreed"}, "then": {"api": "none"}},
             {"when": {"cond": "!agreed"}, "then": {"api": "none"}}],
        ))
        self.assertEqual([], result.warnings)

    def test_condition_no_branch_gates_on_is_warned(self):
        result = _validate(self._spec(
            {"agreed": self._cond(witness_true=self._TRUE,
                                  witness_false=self._FALSE),
             "unused": self._cond(witness_true=self._TRUE,
                                  witness_false=self._FALSE)},
            [{"when": {"cond": "agreed"}, "then": {"api": "none"}}],
        ))
        warnings = self._warnings_containing(result, "no branch gates on it")
        self.assertEqual(1, len(warnings))
        self.assertIn("conditions.unused", warnings[0].path)

    def test_missing_witness_for_the_side_a_branch_needs_is_warned(self):
        # Test generation hard-errors on this; validate says it first.
        result = _validate(self._spec(
            {"agreed": self._cond(witness_true=self._TRUE)},
            [{"when": {"cond": "!agreed"}, "then": {"api": "none"}}],
        ))
        warnings = self._warnings_containing(result, "no witness_false")
        self.assertEqual(1, len(warnings))
        self.assertIn("branches[0].when.cond", warnings[0].path)

    def test_only_the_needed_side_is_required(self):
        result = _validate(self._spec(
            {"agreed": self._cond(witness_true=self._TRUE)},
            [{"when": {"cond": "agreed"}, "then": {"api": "none"}}],
        ))
        self.assertEqual([], self._warnings_containing(result, "no witness"))

    def test_identical_witnesses_are_warned(self):
        result = _validate(self._spec(
            {"agreed": self._cond(witness_true=self._TRUE,
                                  witness_false=self._TRUE)},
            [{"when": {"cond": "agreed"}, "then": {"api": "none"}}],
        ))
        warnings = self._warnings_containing(result, "same state")
        self.assertEqual(1, len(warnings))

    def test_unknown_condition_reference_stays_a_single_error(self):
        # The reference check already errors; usage must not pile a
        # confusing second complaint on the same line.
        result = _validate(self._spec(
            {"agreed": self._cond(witness_true=self._TRUE,
                                  witness_false=self._FALSE)},
            [{"when": {"cond": "agreed"}, "then": {"api": "none"}},
             {"when": {"cond": "ghost"}, "then": {"api": "none"}}],
        ))
        self.assertEqual(
            [], self._warnings_containing(result, "cannot be arranged")
        )
        self.assertTrue(_errors_at(result, "branches[1].when.cond"))


class BranchCrossFaces(unittest.TestCase):
    """Weak-phase cross-face correlation (warnings only).

    Census-driven design (docs/plans/2026-08-24-spec-face-cross-consistency-
    design.md): checks fire only when branchContracts exists, only in the
    "prose says it, contract doesn't know it" direction — prose absence is
    always legal (project cultures differ on writing serverSide prose)."""

    def _spec(self, *, branches=None, server_side=None, user_actions=None,
              transitions=None, states=None):
        spec = _base_spec(
            {"methods": {"onConfirmTap": {"branches": branches or [
                {"when": {"api.createOrder": "sold_out"},
                 "then": {"data.screenState": "order_error"}},
            ]}}},
            vm_methods=["onConfirmTap"],
            ui_vars=[_ui_var("isAgreed"), _ui_var("screenState", "String")],
            use_cases=[{"name": "OrderUseCase",
                        "methods": [{"name": "createOrder"}]}],
            transitions=transitions,
            states=states,
        )
        if server_side is not None:
            spec["validation"] = {"serverSide": server_side}
        if user_actions is not None:
            spec["userActions"] = user_actions
        return spec

    # --- seam 1: serverSide prose vs contract vocabulary ---

    def test_prose_token_known_to_contract_is_clean(self):
        spec = self._spec(server_side=[
            {"condition": "order API error",
             "handling": "409 sold_out shows the retry screen"},
        ])
        result = _validate(spec)
        self.assertEqual(_warnings_at(result, "validation.serverSide"), [])

    def test_prose_only_error_code_warns(self):
        spec = self._spec(server_side=[
            {"condition": "order API error",
             "handling": "422 price_changed reloads the estimate"},
        ])
        warnings = _warnings_at(_validate(spec), "validation.serverSide[0]")
        self.assertTrue(any("price_changed" in w.message for w in warnings))

    def test_state_value_token_in_prose_is_not_drift(self):
        spec = self._spec(
            server_side=[{"condition": "err",
                          "handling": "goes to order_error_stock screen"}],
            states=[{"name": "screenState", "values": [
                {"value": "order_error_stock", "description": "d"}]}],
        )
        result = _validate(spec)
        self.assertEqual(_warnings_at(result, "validation.serverSide"), [])

    def test_request_field_token_in_prose_is_not_drift(self):
        spec = self._spec(
            branches=[{"when": {"api.createOrder": "sold_out"},
                       "then": {"api.createOrder.request": {
                           "coupon_code": "@data.isAgreed"}}}],
            server_side=[{"condition": "err",
                          "handling": "coupon_code mismatch is rejected"}],
        )
        result = _validate(spec)
        self.assertEqual(_warnings_at(result, "validation.serverSide"), [])

    def test_no_server_side_prose_is_legal(self):
        result = _validate(self._spec())
        self.assertEqual(_warnings_at(result, "validation.serverSide"), [])

    def test_without_branch_contracts_no_cross_face_checks(self):
        spec = self._spec(server_side=[
            {"condition": "err", "handling": "422 price_changed happens"},
        ])
        del spec["branchContracts"]
        result = _validate(spec)
        self.assertEqual(_warnings_at(result, "validation.serverSide"), [])

    # --- seam 2: userActions prose vs declared transitions ---

    def test_prose_destination_declared_by_branch_is_clean(self):
        spec = self._spec(
            branches=[{"when": {"api.createOrder": "sold_out"},
                       "then": {"transition": "order_complete"}}],
            transitions=[{"condition": "ok", "destination": "order_complete"}],
            user_actions=[{"action": "tap",
                           "processing": "onConfirmTap goes to order_complete"}],
        )
        result = _validate(spec)
        self.assertEqual(_warnings_at(result, "userActions"), [])

    def test_prose_only_destination_warns(self):
        spec = self._spec(
            transitions=[{"condition": "ok", "destination": "order_complete"}],
            user_actions=[{"action": "tap",
                           "processing": "onConfirmTap goes to order_complete"}],
        )
        warnings = _warnings_at(_validate(spec), "userActions[0]")
        self.assertTrue(any("order_complete" in w.message for w in warnings))

    def test_uncontracted_action_prose_is_skipped(self):
        # The back action's prose routes somewhere, but it never mentions a
        # contracted method — legacy actions stay out of scope.
        spec = self._spec(
            transitions=[{"condition": "back", "destination": "order_list"}],
            user_actions=[{"action": "back tap",
                           "processing": "onBackTap returns to order_list"}],
        )
        result = _validate(spec)
        self.assertEqual(_warnings_at(result, "userActions"), [])

    def test_pascal_case_destination_matches(self):
        spec = self._spec(
            branches=[{"when": {"api.createOrder": "sold_out"},
                       "then": {"transition": "OrderComplete"}}],
            transitions=[{"condition": "ok", "destination": "OrderComplete"}],
            user_actions=[{"action": "tap",
                           "processing": "onConfirmTap goes to OrderComplete"}],
        )
        result = _validate(spec)
        self.assertEqual(_warnings_at(result, "userActions"), [])


class BranchSeedableState(unittest.TestCase):
    """`seedableState` — ViewModel-internal state a branch may arrange.

    The arrange surface was uiVariables only, so a branch gated on private
    state could not be arranged from the contract at all; the reproduction
    lived in a consumer-owned harness, which is where the reproduction
    condition then stopped being readable from the spec.

    Letting `when` reach for an arbitrary property path was considered and
    rejected by the reporter: the contract would bind to the
    implementation's private vocabulary, and a rename would make the
    arrange step silently stop arranging. Naming the seedable state in the
    spec keeps that binding in one declared place.
    """

    def _spec(self, bc_extra, when):
        bc = {
            "methods": {"onConfirmTap": {"branches": [
                {"when": when, "then": {"api": "none"}},
            ]}},
        }
        bc.update(bc_extra)
        return _base_spec(
            bc,
            vm_methods=[{"name": "onConfirmTap"}],
            ui_vars=[_ui_var("isAgreed")],
        )

    def test_a_declared_name_is_accepted(self):
        result = _validate(self._spec(
            {"seedableState": {"canRead": "Bool?"}}, {"state.canRead": False}))
        self.assertEqual(_errors_at(result, "state.canRead"), [])

    def test_an_undeclared_name_is_an_error(self):
        """(b) — and an error rather than the warning an undeclared DATA
        field gets. A data field may exist on a platform this spec does not
        describe; internal state is arranged by the generated test itself,
        so an undeclared name means nothing is seeded and the branch runs
        against whatever state it started in."""
        result = _validate(self._spec({}, {"state.canRead": False}))
        errs = _errors_at(result, "when.state.canRead")
        self.assertTrue(errs)
        self.assertIn("not declared in branchContracts.seedableState",
                      errs[0].message)
        # names the alternative, so the fix does not require reading source
        self.assertIn("data.<field>", errs[0].message)

    def test_a_declared_name_may_be_arranged_in_a_baseline(self):
        bc = {
            "seedableState": {"canRead": "Bool?"},
            "methods": {"onConfirmTap": {
                "baseline": {"isAgreed": True, "state.canRead": None},
                "branches": [{"when": {"data.isAgreed": False},
                              "then": {"api": "none"}}],
            }},
        }
        result = _validate(_base_spec(
            bc, vm_methods=[{"name": "onConfirmTap"}],
            ui_vars=[_ui_var("isAgreed")]))
        self.assertEqual(_errors_at(result, "baseline"), [])

    def test_an_undeclared_name_in_a_baseline_is_an_error(self):
        bc = {
            "methods": {"onConfirmTap": {
                "baseline": {"state.canRead": None},
                "branches": [{"when": {"data.isAgreed": False},
                              "then": {"api": "none"}}],
            }},
        }
        result = _validate(_base_spec(
            bc, vm_methods=[{"name": "onConfirmTap"}],
            ui_vars=[_ui_var("isAgreed")]))
        self.assertTrue(_errors_at(result, "baseline.state.canRead"))

    def test_a_witness_may_arrange_declared_internal_state(self):
        bc = {
            "seedableState": {"canRead": "Bool?"},
            "conditions": {"readable": {
                "meaning": "permission resolved",
                "witness_true": {"state.canRead": True},
                "witness_false": {"state.canRead": False},
            }},
            "methods": {"onConfirmTap": {"branches": [
                {"when": {"cond": "readable"}, "then": {"api": "none"}},
            ]}},
        }
        result = _validate(_base_spec(bc, vm_methods=[{"name": "onConfirmTap"}]))
        self.assertEqual([e.message for e in result.errors], [])

    def test_the_name_must_be_camel_case(self):
        result = _validate(self._spec(
            {"seedableState": {"can_read": "Bool?"}}, {"data.isAgreed": False}))
        errs = _errors_at(result, "seedableState.can_read")
        self.assertTrue(errs)
        self.assertIn("camelCase", errs[0].message)

    def test_the_type_must_be_a_non_empty_string(self):
        for bad in (None, "", 7, {"t": "Bool"}):
            with self.subTest(type=bad):
                result = _validate(self._spec(
                    {"seedableState": {"canRead": bad}}, {"data.isAgreed": False}))
                errs = _errors_at(result, "seedableState.canRead")
                self.assertTrue(errs)
                # (4) no new type language: the message points at the
                # existing vars vocabulary rather than defining one here.
                self.assertIn("dataFlow.viewModel.vars", errs[0].message)

    def test_the_section_must_be_an_object(self):
        result = _validate(self._spec(
            {"seedableState": ["canRead"]}, {"data.isAgreed": False}))
        self.assertTrue(_errors_at(result, "branchContracts.seedableState"))

    def test_a_spec_without_the_section_is_unaffected(self):
        """(d) — opt-in. An existing spec validates exactly as before."""
        result = _validate(self._spec({}, {"data.isAgreed": False}))
        self.assertEqual([e.message for e in result.errors], [])


class BranchRequestScalarLists(unittest.TestCase):
    """`then api.<op>.request` leaves take lists of scalars.

    Reported from an endpoint whose field means three things: absent = leave
    alone, `null` = leave alone, `[]` = detach everything. The `[]` half had
    no way to be stated, so a regression dropping it from the wire was
    undetectable — the contract could only witness the other two.

    Superseded ruling (2026-08): request leaves took no list at all, because
    `[]` there "would be a claim about a request, which is a different
    statement with no defined partial-match meaning". The meaning is defined
    now: whole-array equality including order, which is what all three
    generated runtimes already do (web `Array.isArray(expected)` branch,
    Android `exp is List<*>`, iOS `exp as? [Any]` — each compares length then
    recurses per index). Measured before widening, not assumed.
    """

    def _spec(self, then):
        return _base_spec(
            {"methods": {"onConfirmTap": {"branches": [
                {"when": {"api.confirmBooking": "failure"}, "then": then}]}}},
            vm_methods=["onConfirmTap"],
            ui_vars=[_ui_var("fingerprint", "String")],
            use_cases=[{"name": "ConfirmUseCase",
                        "methods": [{"name": "confirmBooking"}]}],
        )

    def _errs(self, leaf_value, at="then.api.confirmBooking.request.tags"):
        return _errors_at(
            _validate(self._spec({"api.confirmBooking.request": {"tags": leaf_value}})),
            at)

    def test_the_reported_three_states(self):
        """The shape from the report: `[]`, `null`, and a populated list."""
        self.assertEqual(self._errs([]), [])
        self.assertEqual(self._errs(None), [])
        self.assertEqual(self._errs(["a", "b"]), [])

    def test_mixed_scalars_are_accepted(self):
        self.assertEqual(self._errs([1, "a", True, None]), [])

    def test_a_nested_object_element_is_rejected(self):
        errs = self._errs([{"id": "1"}], "then.api.confirmBooking.request.tags[0]")
        self.assertTrue(errs)
        self.assertIn("scalar", errs[0].message)

    def test_a_nested_list_element_is_rejected(self):
        errs = self._errs([["a"]], "then.api.confirmBooking.request.tags[0]")
        self.assertTrue(errs)

    def test_a_reference_element_is_rejected_and_says_why(self):
        """The generators resolve `@data.<f>` only directly under a key.

        Inside a list the element falls through to the literal renderer and
        is emitted as the string "@data.fingerprint" on all three faces
        (measured 2026-09-07). Accepting it would produce a contract that
        reads like a reference and compares like a string — green for the
        wrong reason, which is worse than the error.
        """
        errs = self._errs(["@data.fingerprint"],
                          "then.api.confirmBooking.request.tags[0]")
        self.assertTrue(errs)
        msg = errs[0].message
        self.assertIn("@data.fingerprint", msg)
        self.assertIn("literal string", msg)

    def test_a_strings_key_element_is_rejected_too(self):
        errs = self._errs(["@some_key"],
                          "then.api.confirmBooking.request.tags[0]")
        self.assertTrue(errs)

    def test_data_side_is_unchanged(self):
        """The widening must not leak to `then data.<field>`.

        There a non-empty list still binds the contract to the mock body,
        which is the reason the narrow rule exists on that side.
        """
        spec = _base_spec(
            {"methods": {"onConfirmTap": {"branches": [
                {"when": {"api.confirmBooking": "failure"},
                 "then": {"data.rows": [1, 2]}}]}}},
            vm_methods=["onConfirmTap"],
            ui_vars=[_ui_var("rows", "[Row]")],
            use_cases=[{"name": "ConfirmUseCase",
                        "methods": [{"name": "confirmBooking"}]}],
        )
        self.assertTrue(_errors_at(_validate(spec), "then.data.rows"))

    def test_a_dict_leaf_is_still_recursed_not_errored(self):
        """Why there is no "got dict" message on this side.

        `_validate_branch_request_match` takes dicts itself (nested objects
        are allowed), and lists are taken above, so the only values that reach
        the scalar error builder are scalars — which do not error. The first
        cut of this change added a request-side arm to that message; nothing
        could ever read it.
        """
        result = _validate(self._spec({
            "api.confirmBooking.request": {"nested": {"amount": 1000}}}))
        self.assertEqual(
            _errors_at(result, "then.api.confirmBooking.request.nested"), [])


_TWO_OWNERS = [
    {"name": "AccountRepository", "methods": [
        {"name": "getProfile", "endpoint": "GET /api/account/profile"}]},
    {"name": "PreferencesRepository", "methods": [
        {"name": "getProfile", "endpoint": "GET /api/preferences/profile"}]},
]

_ONE_OWNER = [
    {"name": "AccountRepository", "methods": [
        {"name": "getProfile", "endpoint": "GET /api/account/profile"}]},
]


class BranchApiOpQualification(unittest.TestCase):
    """`api.<Owner>.<op>` when two owners declare the same method name.

    The op set was flat, so a name declared twice looked exactly like a name
    declared once, and the generator's flat `name -> endpoint` dict kept
    whichever came last. The spec validated, the contract read as if it named
    an endpoint, and the other endpoint had no route — its calls 599'd with
    nothing in the spec to explain why.

    Both sides of a branch have to take the same qualification. Selecting the
    endpoint in `when` while `then` could only say the bare name would leave
    the contract unable to state anything about the endpoint it selected.
    """

    def _spec(self, when, then, repositories):
        return _base_spec(
            {"methods": {"onAppear": {"branches": [
                {"when": when, "then": then}]}}},
            vm_methods=["onAppear"],
            repositories=repositories,
        )

    def _result(self, when, then, repositories=None):
        return _validate(self._spec(
            when, then, repositories if repositories is not None else _TWO_OWNERS))

    def test_a_bare_reference_to_a_duplicated_name_is_an_error(self):
        errs = _errors_at(
            self._result({"api.getProfile": "failure"}, {"api": "none"}),
            "when.api.getProfile")
        self.assertTrue(errs)
        msg = errs[0].message
        self.assertIn("AccountRepository.getProfile", msg)
        self.assertIn("PreferencesRepository.getProfile", msg)

    def test_a_qualified_reference_resolves(self):
        result = self._result(
            {"api.AccountRepository.getProfile": "failure"}, {"api": "none"})
        self.assertEqual(
            _errors_at(result, "when.api.AccountRepository.getProfile"), [])
        self.assertEqual(
            _warnings_at(result, "when.api.AccountRepository.getProfile"), [])

    def test_the_then_side_takes_the_same_qualification(self):
        result = self._result(
            {"api.AccountRepository.getProfile": "failure"},
            {"api.PreferencesRepository.getProfile": "not-called"})
        self.assertEqual(
            _errors_at(result, "then.api.PreferencesRepository.getProfile"), [])

    def test_a_qualified_request_match_is_accepted(self):
        result = self._result(
            {"api.AccountRepository.getProfile": "success"},
            {"api.AccountRepository.getProfile.request": {"scope": "full"}})
        self.assertEqual(
            _errors_at(result, "then.api.AccountRepository.getProfile.request"), [])

    def test_a_bare_then_reference_to_a_duplicated_name_is_an_error(self):
        """Both sides, not just `when` — an error on one side only would let
        half of a contract name an endpoint it cannot have meant."""
        errs = _errors_at(
            self._result({"cond": "always"}, {"api.getProfile": "called"}),
            "then.api.getProfile")
        self.assertTrue(errs)
        self.assertIn("AccountRepository.getProfile", errs[0].message)

    def test_a_third_segment_is_still_rejected(self):
        errs = _errors_at(
            self._result({"api.A.b.c": "failure"}, {"api": "none"}),
            "when.api.A.b.c")
        self.assertTrue(errs)

    def test_an_unambiguous_bare_name_is_unchanged(self):
        """The population this change is not for.

        One owner, one declaration — the bare name must keep working exactly
        as before, with no warning and no qualification required.
        """
        result = self._result(
            {"api.getProfile": "failure"}, {"api": "none"}, _ONE_OWNER)
        self.assertEqual(_errors_at(result, "when.api.getProfile"), [])
        self.assertEqual(_warnings_at(result, "when.api.getProfile"), [])

    def test_an_unambiguous_name_may_still_be_qualified(self):
        result = self._result(
            {"api.AccountRepository.getProfile": "failure"}, {"api": "none"},
            _ONE_OWNER)
        self.assertEqual(
            _errors_at(result, "when.api.AccountRepository.getProfile"), [])
        self.assertEqual(
            _warnings_at(result, "when.api.AccountRepository.getProfile"), [])

    def test_an_undeclared_op_still_only_warns(self):
        """Ambiguity is an error; absence stays a warning.

        An op may legitimately be an operation id the spec never lists, so
        the widening must not turn every unlisted name into a failure.
        """
        result = self._result(
            {"api.neverDeclared": "failure"}, {"api": "none"})
        self.assertEqual(_errors_at(result, "when.api.neverDeclared"), [])
        self.assertTrue(_warnings_at(result, "when.api.neverDeclared"))



class BranchThenDataNestedPath(unittest.TestCase):
    """`then data.<a>.<b>` names a value inside a nested data structure.

    A screen whose Data holds a nested struct — a sheet's own error state,
    a card's own visibility — could not state the value the contract is
    actually about. The reported symptom was real; the reported mechanism
    was not. The gate is the camelCase check, which fires on the dot and
    returns before the declaration check is ever reached, so the quoted
    "is not declared" message cannot come from this path. (Measured: the
    installed copy is byte-identical to the source tree, and the check has
    been there since branchContracts was introduced, so no shipped version
    behaved otherwise.)

    Only the READ side opens. `when`, `witness_*`/`baseline` and
    `'@data.<f>'` are arrange-side or become an identifier, and each fails
    in silence rather than loudly if a dotted name reaches it — see
    _check_branch_data_field's docstring.
    """

    def _spec(self, then, when=None, ui_vars=None):
        return _base_spec(
            {"methods": {"onSaveTap": {"branches": [
                {"when": when or {"data.isBusy": False}, "then": then}]}}},
            vm_methods=["onSaveTap"],
            ui_vars=ui_vars if ui_vars is not None else [
                _ui_var("noticeSheetData", "NoticeSheetData"),
                _ui_var("isBusy"),
            ],
        )

    def test_a_nested_then_path_is_accepted(self):
        result = _validate(self._spec(
            {"data.noticeSheetData.errorVisibility": "visible"}))
        self.assertEqual(_errors_at(result, "branchContracts"), [])
        self.assertEqual(_warnings_at(result, "branchContracts"), [])

    def test_more_than_two_segments_is_accepted(self):
        result = _validate(self._spec({"data.noticeSheetData.inner.leaf": "x"}))
        self.assertEqual(_errors_at(result, "branchContracts"), [])

    def test_only_the_head_is_matched_against_declarations(self):
        """The tail names members of whatever the head holds, and the spec's
        declaration surface does not describe those — so an undeclared HEAD
        still warns, and a declared head with any tail does not."""
        warns = _warnings_at(
            _validate(self._spec({"data.ghostField.errorVisibility": "x"})),
            "then.data.ghostField.errorVisibility")
        self.assertTrue(warns)
        self.assertIn("'ghostField'", warns[0].message)

    def test_a_non_camel_segment_is_still_an_error(self):
        errs = _errors_at(
            _validate(self._spec({"data.noticeSheetData.Error": "x"})),
            "then.data.noticeSheetData.Error")
        self.assertTrue(errs)
        self.assertIn("'Error'", errs[0].message)

    def test_a_flat_then_field_is_unchanged(self):
        """The population this change is not for."""
        result = _validate(self._spec({"data.isBusy": True}))
        self.assertEqual(_errors_at(result, "branchContracts"), [])
        self.assertEqual(_warnings_at(result, "branchContracts"), [])

    def test_when_keeps_rejecting_a_dotted_path(self):
        """setState writes by flat name. Kotlin's looks the key up with
        findField and then by `copy` parameter name — a dotted key matches
        neither and is dropped WITH NO ERROR — and Swift's is a hand-written
        closed map in the consumer. Opening this would arrange nothing and
        assert the right outcome for an un-arranged branch."""
        errs = _errors_at(
            _validate(self._spec(
                {"api": "none"},
                when={"data.noticeSheetData.errorVisibility": "visible"})),
            "when.data.noticeSheetData.errorVisibility")
        self.assertTrue(errs)
        self.assertIn("read-back only", errs[0].message)

    def test_a_data_reference_value_keeps_rejecting_a_dotted_path(self):
        """`'@data.<f>'` becomes the generated identifier `ref_<f>`; a dot
        there is a syntax error on all three faces."""
        errs = _errors_at(
            _validate(self._spec(
                {"data.isBusy": "@data.noticeSheetData.errorVisibility"})),
            "then.data.isBusy")
        self.assertTrue(errs)

    def test_a_witness_field_rejects_a_dotted_path(self):
        """The fourth site, and the one that had NO name check at all: a
        dotted witness passed with only the undeclared-warning, and
        generation then emitted a flat read of a name no face has. Witnesses
        are arranged, so this closes rather than opens."""
        spec = _base_spec(
            {"conditions": {"hasError": {
                "meaning": "the sheet is showing an error",
                "witness_true": {"noticeSheetData.errorVisibility": "visible"},
                "witness_false": {"isBusy": False}}},
             "methods": {"onSaveTap": {"branches": [
                 {"when": {"cond": "hasError"}, "then": {"api": "none"}},
                 {"when": {"cond": "!hasError"}, "then": {"api": "none"}}]}}},
            vm_methods=["onSaveTap"],
            ui_vars=[_ui_var("noticeSheetData", "NoticeSheetData"),
                     _ui_var("isBusy")],
        )
        errs = _errors_at(
            _validate(spec),
            "witness_true.noticeSheetData.errorVisibility")
        self.assertTrue(errs)
        self.assertIn("camelCase", errs[0].message)

    def test_a_flat_witness_field_is_unchanged(self):
        spec = _base_spec(
            {"conditions": {"busy": {
                "meaning": "a save is in flight",
                "witness_true": {"isBusy": True},
                "witness_false": {"isBusy": False}}},
             "methods": {"onSaveTap": {"branches": [
                 {"when": {"cond": "busy"}, "then": {"api": "none"}},
                 {"when": {"cond": "!busy"}, "then": {"api": "none"}}]}}},
            vm_methods=["onSaveTap"], ui_vars=[_ui_var("isBusy")],
        )
        self.assertEqual(_errors_at(_validate(spec), "witness"), [])
