"""The contract-gap declarations: what their one parser accepts and refuses.

`excludedOutcomes` / `unreachedOps` / `metadata.platforms` on a screen and
`apiOutcomeRules` in the app contracts spec are read by the coverage command
and shape-checked by `jsonui-doc validate spec`, both through
`parse_declarations`. These arms pin the shape (design §2.3 / §2.6): keys,
types, closed sets, and same-file references. Each refusal names the path an
author has to edit.
"""
from __future__ import annotations

import unittest

from jsonui_test_cli.contract_declarations import (
    APP_CONTRACTS_SPEC,
    EXCLUSION_BY,
    Exclusion,
    OutcomeRule,
    UnreachedOp,
    parse_declarations,
)


def _screen(**bc_over):
    methods = {"setApproval": {
        "branches": [{"when": {"api.setApproval": "default"},
                      "then": {"data.status": "approved"}}],
        "excludedOutcomes": {"api.detail": {"403": {
            "by": "unreachable", "reason": "the PUT returns 403 first"}}},
    }}
    bc = {"methods": methods,
          "unreachedOps": {"api.prefetchBanner": {"reason": "the parent calls it"}}}
    bc.update(bc_over)
    return {"type": "screen_spec", "version": "1.0",
            "metadata": {"name": "Detail", "displayName": "Detail",
                         "description": "d", "platforms": ["ios", "android"]},
            "branchContracts": bc}


def _app(rules):
    return {"type": APP_CONTRACTS_SPEC, "version": "1.0",
            "metadata": {"name": "client", "description": "d"},
            "unitContracts": [{"target": "ApiClient", "cases": [
                {"name": "anyServerError_showsToast"}]}],
            "apiOutcomeRules": rules}


def _then_rule(**over):
    rule = {"id": "session-expired", "statuses": ["401"], "security": ["bearerAuth"],
            "then": {"transition": "Login"},
            "except": [{"operationId": "changePassword", "reason": "401 = wrong password"}],
            "reason": "the client signs out on 401"}
    rule.update(over)
    return rule


def _vm_rule(**over):
    rule = {"id": "server", "statuses": ["5XX", "429"], "security": "*",
            "vm": "not-reached", "handledBy": "ApiErrorToast",
            "verifiedBy": ["anyServerError_showsToast"], "reason": "a toast"}
    rule.update(over)
    return rule


def _paths(decl):
    return [e.path for e in decl.errors]


class WellFormedDeclarationsParse(unittest.TestCase):
    def test_screen_declarations(self):
        d = parse_declarations(_screen())
        self.assertEqual([], d.errors)
        self.assertEqual([Exclusion("setApproval", "detail", "403", "unreachable",
                                    "the PUT returns 403 first", None)], d.exclusions)
        self.assertEqual([UnreachedOp("prefetchBanner", "the parent calls it", None)],
                         d.unreached_ops)
        self.assertEqual(("ios", "android"), d.platforms)

    def test_app_rules_both_forms(self):
        d = parse_declarations(_app([_then_rule(), _vm_rule()]))
        self.assertEqual([], d.errors)
        self.assertEqual(2, len(d.rules))
        then, vm = d.rules
        self.assertIsInstance(then, OutcomeRule)
        self.assertEqual(("401",), then.statuses)
        self.assertEqual(("bearerAuth",), then.security)
        self.assertEqual({"transition": "Login"}, then.then)
        self.assertEqual((("changePassword", "401 = wrong password"),), then.exceptions)
        self.assertEqual("*", vm.security)
        self.assertEqual(("5XX", "429"), vm.statuses)
        self.assertEqual(("anyServerError_showsToast",), vm.verified_by)

    def test_a_document_without_declarations_yields_nothing(self):
        spec = _screen()
        del spec["branchContracts"]
        del spec["metadata"]["platforms"]
        d = parse_declarations(spec)
        self.assertEqual(([], [], [], None, []),
                         (d.exclusions, d.unreached_ops, d.rules, d.platforms, d.errors))

    def test_platforms_on_an_exclusion_are_kept(self):
        spec = _screen()
        spec["branchContracts"]["methods"]["setApproval"]["excludedOutcomes"][
            "api.detail"]["403"]["platforms"] = ["web"]
        self.assertEqual(("web",), parse_declarations(spec).exclusions[0].platforms)


class ExcludedOutcomesShape(unittest.TestCase):
    def _errs(self, excluded):
        spec = _screen()
        spec["branchContracts"]["methods"]["setApproval"]["excludedOutcomes"] = excluded
        return parse_declarations(spec)

    BASE = "branchContracts.methods.setApproval.excludedOutcomes"

    def test_by_is_closed(self):
        for by in ("method", "delegated", None):
            d = self._errs({"api.detail": {"403": {"by": by, "reason": "r"}}})
            self.assertIn(f"{self.BASE}.api.detail.403.by", _paths(d), by)
            self.assertEqual([], d.exclusions)
        for by in EXCLUSION_BY:
            self.assertEqual([], self._errs(
                {"api.detail": {"403": {"by": by, "reason": "r"}}}).errors)

    def test_by_method_says_why_it_does_not_exist(self):
        d = self._errs({"api.detail": {"403": {"by": "method", "reason": "r"}}})
        self.assertIn("write the row", d.errors[0].message)

    def test_reason_is_required(self):
        for entry in ({"by": "unit"}, {"by": "unit", "reason": "  "}):
            self.assertIn(f"{self.BASE}.api.detail.403.reason",
                          _paths(self._errs({"api.detail": {"403": entry}})))

    def test_status_keys(self):
        ok = self._errs({"api.detail": {"4XX": {"by": "unit", "reason": "r"},
                                        "503": {"by": "unit", "reason": "r"}}})
        self.assertEqual([], ok.errors)
        for bad in ("default", "40", "600", "4xx", "4X0"):
            d = self._errs({"api.detail": {bad: {"by": "unit", "reason": "r"}}})
            self.assertIn(f"{self.BASE}.api.detail.{bad}", _paths(d), bad)
        d = self._errs({"api.detail": {"default": {"by": "unit", "reason": "r"}}})
        self.assertIn("catch-all", d.errors[0].message)

    def test_op_needs_the_api_prefix(self):
        d = self._errs({"detail": {"403": {"by": "unit", "reason": "r"}}})
        self.assertIn(f"{self.BASE}.detail", _paths(d))
        self.assertEqual([], d.exclusions)

    def test_unknown_keys_and_empty_blocks(self):
        d = self._errs({"api.detail": {"403": {"by": "unit", "reason": "r",
                                               "distinguish": False}}})
        self.assertIn(f"{self.BASE}.api.detail.403.distinguish", _paths(d))
        self.assertIn(self.BASE, _paths(self._errs({})))
        self.assertIn(f"{self.BASE}.api.detail", _paths(self._errs({"api.detail": {}})))

    def test_platforms(self):
        for bad in ([], ["ios", "ios"], ["macos"], "ios"):
            d = self._errs({"api.detail": {"403": {"by": "unit", "reason": "r",
                                                   "platforms": bad}}})
            self.assertTrue(any(p.startswith(f"{self.BASE}.api.detail.403.platforms")
                                for p in _paths(d)), bad)


class UnreachedOpsShape(unittest.TestCase):
    def _errs(self, value):
        return parse_declarations(_screen(unreachedOps=value))

    def test_reason_required_and_keys_closed(self):
        self.assertIn("branchContracts.unreachedOps.api.x.reason",
                      _paths(self._errs({"api.x": {}})))
        self.assertIn("branchContracts.unreachedOps.api.x.by",
                      _paths(self._errs({"api.x": {"reason": "r", "by": "unit"}})))
        self.assertIn("branchContracts.unreachedOps.x",
                      _paths(self._errs({"x": {"reason": "r"}})))
        self.assertIn("branchContracts.unreachedOps", _paths(self._errs({})))


class MetadataPlatformsShape(unittest.TestCase):
    def test_values(self):
        for bad in ([], ["ios", "ios"], ["desktop"], None, "web"):
            spec = _screen()
            spec["metadata"]["platforms"] = bad
            d = parse_declarations(spec)
            self.assertTrue(any(p.startswith("metadata.platforms") for p in _paths(d)), bad)


class ApiOutcomeRulesShape(unittest.TestCase):
    def _paths_for(self, *rules):
        return _paths(parse_declarations(_app(list(rules))))

    def test_security_is_required(self):
        rule = _then_rule()
        del rule["security"]
        self.assertIn("apiOutcomeRules[0].security", self._paths_for(rule))
        for bad in ([], [""], "bearerAuth", ["a", "a"]):
            self.assertIn("apiOutcomeRules[0].security",
                          self._paths_for(_then_rule(security=bad)), bad)

    def test_exactly_one_of_then_and_vm(self):
        both = _then_rule(vm="not-reached", handledBy="x", verifiedBy=["anyServerError_showsToast"])
        self.assertIn("apiOutcomeRules[0]", self._paths_for(both))
        neither = _then_rule()
        del neither["then"]
        self.assertIn("apiOutcomeRules[0]", self._paths_for(neither))

    def test_then_is_closed_to_transition(self):
        self.assertIn("apiOutcomeRules[0].then.data.items",
                      self._paths_for(_then_rule(then={"data.items": "[]"})))
        self.assertIn("apiOutcomeRules[0].then", self._paths_for(_then_rule(then={})))

    def test_vm_rule_needs_handler_and_same_file_cases(self):
        rule = _vm_rule()
        del rule["handledBy"]
        self.assertIn("apiOutcomeRules[0].handledBy", self._paths_for(rule))
        self.assertIn("apiOutcomeRules[0].verifiedBy[0]",
                      self._paths_for(_vm_rule(verifiedBy=["noSuchCase"])))
        self.assertIn("apiOutcomeRules[0].vm", self._paths_for(_vm_rule(vm="skipped")))

    def test_handler_keys_do_not_belong_on_a_then_rule(self):
        self.assertIn("apiOutcomeRules[0].handledBy",
                      self._paths_for(_then_rule(handledBy="ApiClient")))

    def test_statuses(self):
        self.assertIn("apiOutcomeRules[0].statuses[0]", self._paths_for(_then_rule(statuses=[401])))
        self.assertIn("apiOutcomeRules[0].statuses[1]",
                      self._paths_for(_then_rule(statuses=["401", "401"])))
        self.assertIn("apiOutcomeRules[0].statuses", self._paths_for(_then_rule(statuses=[])))
        self.assertIn("apiOutcomeRules[0].statuses[0]",
                      self._paths_for(_then_rule(statuses=["default"])))

    def test_ids_are_unique_and_except_is_by_operation_id(self):
        self.assertIn("apiOutcomeRules[1].id",
                      self._paths_for(_then_rule(), _then_rule(statuses=["403"])))
        # `VERB /path` is not an exception key: operationId only.
        paths = self._paths_for(_then_rule(**{"except": [{"path": "PUT /x", "reason": "r"}]}))
        self.assertIn("apiOutcomeRules[0].except[0].operationId", paths)
        self.assertIn("apiOutcomeRules[0].except[0].path", paths)

    def test_reason_required_and_unknown_keys(self):
        rule = _then_rule()
        del rule["reason"]
        self.assertIn("apiOutcomeRules[0].reason", self._paths_for(rule))
        self.assertIn("apiOutcomeRules[0].scope", self._paths_for(_then_rule(scope="all")))

    def test_an_empty_block_is_refused(self):
        self.assertIn("apiOutcomeRules", _paths(parse_declarations(_app([]))))

    def test_a_refused_rule_is_not_returned(self):
        d = parse_declarations(_app([_then_rule(security=None), _vm_rule()]))
        self.assertEqual(["server"], [r.id for r in d.rules])


class DeclarationsInTheWrongDocument(unittest.TestCase):
    def test_rules_on_a_screen_are_refused(self):
        spec = _screen()
        spec["apiOutcomeRules"] = [_then_rule()]
        d = parse_declarations(spec)
        self.assertIn("apiOutcomeRules", _paths(d))
        self.assertEqual([], d.rules)


if __name__ == "__main__":
    unittest.main()
