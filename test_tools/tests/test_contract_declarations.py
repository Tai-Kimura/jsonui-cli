"""The contract-gap declarations: what their one parser accepts and refuses.

`excludedOutcomes` / `unreachedOps` / a row's `alsoStatuses` /
`metadata.platforms` on a screen and `apiOutcomeRules` in the app contracts
spec are read by the coverage command and shape-checked by
`jsonui-doc validate spec`, both through `parse_declarations`. These arms pin
the shape (design v4.1 §2.3): keys, types, closed sets, and same-file
references. Each refusal names the path an author has to edit.
"""
from __future__ import annotations

import unittest

from jsonui_test_cli.contract_declarations import (
    APP_CONTRACTS_SPEC,
    DECLARATION_SITES,
    EXCLUSION_BY,
    AlsoStatuses,
    Exclusion,
    OutcomeRule,
    UnreachedOp,
    parse_declarations,
)

CASE = "request_onTerminal401_postsLogout"


def _screen(**bc_over):
    methods = {"setApproval": {
        "branches": [
            {"when": {"api.setApproval": "default"},
             "then": {"data.status": "approved"}},
            {"when": {"api.setApproval": "error_500"},
             "alsoStatuses": {"api.setApproval": ["429", "503"]},
             "then": {"data.errorVisible": "visible"}},
        ],
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
            "unitContracts": [{"target": "ApiClient", "cases": [{"name": CASE}]}],
            "apiOutcomeRules": rules}


def _rule(**over):
    rule = {"id": "session-end-logout", "statuses": ["401"],
            "sideCalls": ["postSessionLogout"], "verifiedBy": [CASE],
            "reason": "the client posts logout on a terminal 401"}
    rule.update(over)
    return rule


def _paths(decl):
    return [e.path for e in decl.errors]


def _messages(decl):
    return [e.message for e in decl.errors]


class WellFormedDeclarationsParse(unittest.TestCase):
    def test_screen_declarations(self):
        d = parse_declarations(_screen())
        self.assertEqual([], d.errors)
        self.assertEqual([Exclusion("setApproval", "detail", "403", "unreachable",
                                    "the PUT returns 403 first", None)], d.exclusions)
        self.assertEqual([UnreachedOp("prefetchBanner", "the parent calls it", None)],
                         d.unreached_ops)
        self.assertEqual([AlsoStatuses("setApproval", 1, "setApproval", ("429", "503"))],
                         d.also_statuses)
        self.assertEqual(("ios", "android"), d.platforms)

    def test_an_app_rule(self):
        d = parse_declarations(_app([_rule()]))
        self.assertEqual([], d.errors)
        self.assertEqual([OutcomeRule("session-end-logout", ("401",), ("postSessionLogout",),
                                      (CASE,), "the client posts logout on a terminal 401")],
                         d.rules)

    def test_a_document_without_declarations_yields_nothing(self):
        spec = _screen()
        del spec["branchContracts"]
        del spec["metadata"]["platforms"]
        d = parse_declarations(spec)
        self.assertEqual(([], [], [], [], None, []),
                         (d.exclusions, d.unreached_ops, d.also_statuses, d.rules,
                          d.platforms, d.errors))

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


class AlsoStatusesShape(unittest.TestCase):
    """§2.3.3's parser row: empty, not an array, repeats, not a number, a
    range, `default`, on a note row, a key the row's when does not name."""

    BASE = "branchContracts.methods.setApproval.branches[1].alsoStatuses"

    def _errs(self, also=None, *, branch=None):
        spec = _screen()
        row = spec["branchContracts"]["methods"]["setApproval"]["branches"][1]
        if branch is not None:
            spec["branchContracts"]["methods"]["setApproval"]["branches"][1] = branch
        elif also is not None:
            row["alsoStatuses"] = also
        return parse_declarations(spec)

    def test_statuses_are_plain_numbers(self):
        for bad, why in (("4XX", "is a range"), ("default", "not a status"),
                         ("abc", "not a status"), (429, "as a string")):
            d = self._errs({"api.setApproval": [bad]})
            self.assertIn(f"{self.BASE}.api.setApproval[0]", _paths(d), bad)
            self.assertTrue(any(why in m for m in _messages(d)), (bad, _messages(d)))
            self.assertEqual([], d.also_statuses)

    def test_empty_and_repeated(self):
        self.assertIn(self.BASE, _paths(self._errs({})))
        self.assertIn(f"{self.BASE}.api.setApproval", _paths(self._errs({"api.setApproval": []})))
        self.assertIn(f"{self.BASE}.api.setApproval", _paths(self._errs({"api.setApproval": "429"})))
        self.assertIn(f"{self.BASE}.api.setApproval[1]",
                      _paths(self._errs({"api.setApproval": ["429", "429"]})))

    def test_the_key_must_be_named_in_the_rows_when_with_a_scenario(self):
        # Another op, and the same op spelled with its owner: neither is in when.
        for key in ("api.detail", "api.Repo.setApproval"):
            self.assertIn(f"{self.BASE}.{key}", _paths(self._errs({key: ["429"]})), key)
        branch = {"when": {"api.setApproval": {"not": "a scenario"}},
                  "alsoStatuses": {"api.setApproval": ["429"]}, "then": {"data.x": 1}}
        self.assertIn(f"{self.BASE}.api.setApproval", _paths(self._errs(branch=branch)))
        self.assertIn(f"{self.BASE}.setApproval", _paths(self._errs({"setApproval": ["429"]})))

    def test_a_note_row_cannot_carry_it(self):
        d = self._errs(branch={"note": "handled by the parent", "alsoStatuses": {"api.setApproval": ["429"]}})
        self.assertIn(self.BASE, _paths(d))
        self.assertEqual([], d.also_statuses)


class ApiOutcomeRulesShape(unittest.TestCase):
    def _paths_for(self, *rules):
        return _paths(parse_declarations(_app(list(rules))))

    def test_every_key_is_required(self):
        for key in ("id", "statuses", "sideCalls", "verifiedBy", "reason"):
            rule = _rule()
            del rule[key]
            self.assertIn(f"apiOutcomeRules[0].{key}", self._paths_for(rule), key)

    def test_the_v3_keys_are_refused_by_name(self):
        for key, value in (("then", {"transition": "Login"}), ("vm", "not-reached"),
                           ("handledBy", "ApiClient"), ("security", ["bearerAuth"]),
                           ("except", [{"operationId": "x", "reason": "r"}])):
            d = parse_declarations(_app([_rule(**{key: value})]))
            self.assertIn(f"apiOutcomeRules[0].{key}", _paths(d), key)
            self.assertTrue(any("withdrawn" in m for m in _messages(d)), key)
            self.assertEqual([], d.rules)

    def test_other_keys_are_unknown(self):
        d = parse_declarations(_app([_rule(scope="all")]))
        self.assertIn("apiOutcomeRules[0].scope", _paths(d))
        self.assertTrue(any("Unknown key" in m for m in _messages(d)))

    def test_statuses_are_plain_numbers(self):
        for bad in ("4XX", "5XX", "default", 401, "4O1"):
            self.assertIn("apiOutcomeRules[0].statuses[0]",
                          self._paths_for(_rule(statuses=[bad])), bad)
        self.assertIn("apiOutcomeRules[0].statuses[1]",
                      self._paths_for(_rule(statuses=["401", "401"])))
        self.assertIn("apiOutcomeRules[0].statuses", self._paths_for(_rule(statuses=[])))

    def test_side_calls_are_operation_ids(self):
        self.assertIn("apiOutcomeRules[0].sideCalls[0]",
                      self._paths_for(_rule(sideCalls=["POST /api/user/auth/logout"])))
        self.assertIn("apiOutcomeRules[0].sideCalls", self._paths_for(_rule(sideCalls=[])))
        self.assertIn("apiOutcomeRules[0].sideCalls[0]", self._paths_for(_rule(sideCalls=[""])))

    def test_verified_by_names_a_case_in_this_file(self):
        self.assertIn("apiOutcomeRules[0].verifiedBy[0]",
                      self._paths_for(_rule(verifiedBy=["noSuchCase"])))
        self.assertIn("apiOutcomeRules[0].verifiedBy", self._paths_for(_rule(verifiedBy=[])))

    def test_ids_are_unique_and_the_block_is_not_empty(self):
        self.assertIn("apiOutcomeRules[1].id", self._paths_for(_rule(), _rule(statuses=["426"])))
        self.assertIn("apiOutcomeRules", _paths(parse_declarations(_app([]))))

    def test_a_refused_rule_is_not_returned(self):
        d = parse_declarations(_app([_rule(sideCalls=[]), _rule(id="other")]))
        self.assertEqual(["other"], [r.id for r in d.rules])


def _document_with(site: str, value) -> dict:
    """A bare document holding `value` at `site` (`*` → a method, `[]` → one element)."""
    doc: dict = {"type": APP_CONTRACTS_SPEC if site == "apiOutcomeRules" else "screen_spec"}
    node = doc
    parts = site.replace("*", "anyMethod").split(".")
    for part in parts[:-1]:
        if part.endswith("[]"):
            element: dict = {"when": {}, "then": {}}
            node[part[:-2]] = [element]
            node = element
        else:
            node = node.setdefault(part, {})
    node[parts[-1]] = value
    return doc


class EveryListedSiteIsRead(unittest.TestCase):
    """`DECLARATION_SITES` is what the parser reads, not a list beside it.

    The validator keys its failed-import message on this constant, so a
    site listed here that the parser ignores (or a name that drifted) would
    make that message claim a check nobody runs. Each site gets an invalid
    value and must come back as an error at that site.
    """

    def test_an_invalid_value_at_each_site_is_reported_there(self):
        for site in DECLARATION_SITES:
            paths = _paths(parse_declarations(_document_with(site, "not a valid value")))
            where = site.replace("*", "anyMethod").replace("[]", "[0]")
            self.assertTrue(any(p.startswith(where) for p in paths), (site, paths))


class DeclarationsInTheWrongDocument(unittest.TestCase):
    def test_rules_on_a_screen_are_refused(self):
        spec = _screen()
        spec["apiOutcomeRules"] = [_rule()]
        d = parse_declarations(spec)
        self.assertIn("apiOutcomeRules", _paths(d))
        self.assertEqual([], d.rules)


if __name__ == "__main__":
    unittest.main()
