"""`jsonui-doc validate spec` admits the contract-gap declarations and shapes them.

The hand-written allowlists in the validator are the real gate on a spec's
keys (the JSON schema describes, it does not validate), so the declaration
sites exist only once they are admitted THERE. The shape itself comes from
`jsonui_test_cli.contract_declarations` — the same parser the coverage
command reads with — imported inside the check, so a failed import is an
ERROR on a document that declares something and nothing on one that does
not (a module-level import would be folded into one WARNING by
`jui generate`'s `except ImportError`).

And the app contracts spec (design v4.1 §2.3.1): `unitContracts` is required
— a rule's `verifiedBy` names unit cases of the same file, so a rules-only
app spec cannot stand — `apiOutcomeRules` is optional, unknown keys are
refused (a misspelt `apiOutcomeRule` would otherwise be a rule with no
effect), and `branchContracts` / `transitions` stay forbidden.
"""
from __future__ import annotations

import builtins
import copy
import unittest

from jsonui_doc_cli.spec_doc.validator import APP_CONTRACTS_SPEC, SpecValidator

CASE = "request_onTerminal401_postsLogout"


def _screen(**bc_over):
    bc = {
        "methods": {"confirm": {
            "branches": [
                {"when": {"api.submitOrder": "default"},
                 "then": {"transition": "done"}},
                {"when": {"api.submitOrder": "error_500"},
                 "alsoStatuses": {"api.submitOrder": ["429", "503"]},
                 "then": {"transition": "done"}},
            ],
            "excludedOutcomes": {"api.submitOrder": {"409": {
                "by": "unit", "reason": "the retry policy is unit-tested"}}},
        }},
        "unreachedOps": {"api.prefetch": {"reason": "the parent screen calls it"}},
    }
    bc.update(bc_over)
    return {
        "type": "screen_spec", "version": "1.0",
        "metadata": {"name": "Checkout", "displayName": "Checkout",
                     "description": "d", "layoutFile": "checkout",
                     "platforms": ["ios", "android"]},
        "structure": {"components": [], "layout": {}},
        "dataFlow": {
            "viewModel": {"description": "vm", "vars": [],
                          "methods": [{"name": "confirm", "description": "d"}]},
            "repositories": [{"name": "OrderRepository", "methods": [
                {"name": "submitOrder", "endpoint": "POST /orders"},
                {"name": "prefetch", "endpoint": "GET /banner"}]}],
        },
        "stateManagement": {"uiVariables": [], "eventHandlers": []},
        "transitions": [{"destination": "done", "trigger": "confirm"}],
        "branchContracts": bc,
    }


def _rule(**over):
    rule = {"id": "session-end-logout", "statuses": ["401"],
            "sideCalls": ["postSessionLogout"], "verifiedBy": [CASE],
            "reason": "the client posts logout on a terminal 401"}
    rule.update(over)
    return rule


def _app(**over):
    spec = {"type": APP_CONTRACTS_SPEC, "version": "1.0",
            "metadata": {"name": "client", "description": "d"},
            "unitContracts": [{"target": "ApiClient", "cases": [{"name": CASE}]}],
            "apiOutcomeRules": [_rule()]}
    spec.update(over)
    return spec


def _errors(spec):
    return SpecValidator().validate_data(spec, "spec").errors


def _paths(spec):
    return [e.path for e in _errors(spec)]


def _bare(spec):
    bare = copy.deepcopy(spec)
    del bare["branchContracts"]["unreachedOps"]
    del bare["branchContracts"]["methods"]["confirm"]["excludedOutcomes"]
    del bare["branchContracts"]["methods"]["confirm"]["branches"][1]["alsoStatuses"]
    del bare["metadata"]["platforms"]
    return bare


class ScreenDeclarationsAreAdmitted(unittest.TestCase):
    def test_well_formed_declarations_add_no_error(self):
        spec = _screen()
        # The declarations add nothing: same errors as the spec without them.
        self.assertEqual(sorted(_paths(_bare(spec))), sorted(_paths(spec)))
        self.assertFalse([p for p in _paths(spec)
                          if "unreachedOps" in p or "excludedOutcomes" in p
                          or "alsoStatuses" in p or p.startswith("metadata.platforms")])

    def test_a_shape_error_is_an_error_at_its_path(self):
        spec = _screen()
        methods = spec["branchContracts"]["methods"]
        methods["confirm"]["excludedOutcomes"]["api.submitOrder"]["409"]["by"] = "method"
        methods["confirm"]["branches"][1]["alsoStatuses"] = {"api.submitOrder": ["5XX"]}
        spec["branchContracts"]["unreachedOps"]["api.prefetch"] = {}
        spec["metadata"]["platforms"] = ["desktop"]
        paths = _paths(spec)
        self.assertIn(
            "branchContracts.methods.confirm.excludedOutcomes.api.submitOrder.409.by", paths)
        self.assertIn(
            "branchContracts.methods.confirm.branches[1].alsoStatuses.api.submitOrder[0]", paths)
        self.assertIn("branchContracts.unreachedOps.api.prefetch.reason", paths)
        self.assertIn("metadata.platforms[0]", paths)

    def test_other_unknown_keys_are_still_refused(self):
        spec = _screen(unreached={"api.prefetch": {"reason": "r"}})
        self.assertIn("branchContracts.unreached", _paths(spec))
        spec = _screen()
        spec["branchContracts"]["methods"]["confirm"]["excluded"] = {}
        self.assertIn("branchContracts.methods.confirm.excluded", _paths(spec))
        spec = _screen()
        spec["branchContracts"]["methods"]["confirm"]["branches"][1]["alsoStatus"] = {}
        self.assertIn("branchContracts.methods.confirm.branches[1].alsoStatus", _paths(spec))

    def test_also_statuses_on_a_note_row_is_one_error(self):
        spec = _screen()
        spec["branchContracts"]["methods"]["confirm"]["branches"][1] = {
            "note": "handled by the parent", "alsoStatuses": {"api.submitOrder": ["429"]}}
        errors = [e for e in _errors(spec) if e.path.startswith("branchContracts.methods.confirm.branches[1]")]
        self.assertEqual(1, len(errors), [(e.path, e.message) for e in errors])
        self.assertIn("note", errors[0].message)
        # Another key on a note row is still the note check's to report.
        spec["branchContracts"]["methods"]["confirm"]["branches"][1]["then"] = {"x": 1}
        paths = [e.path for e in _errors(spec)]
        self.assertIn("branchContracts.methods.confirm.branches[1]", paths)

    def test_rules_on_a_screen_are_refused(self):
        spec = _screen()
        spec["apiOutcomeRules"] = [_rule()]
        self.assertIn("apiOutcomeRules", _paths(spec))


class AppSpecRequiresUnitContracts(unittest.TestCase):
    def test_units_and_rules_are_a_valid_app_spec(self):
        self.assertEqual([], [e.message for e in _errors(_app())])

    def test_units_alone_are_too(self):
        spec = _app()
        del spec["apiOutcomeRules"]
        self.assertEqual([], [e.message for e in _errors(spec)])

    def test_rules_alone_are_an_error(self):
        # verifiedBy names unit cases of this file, so rules without
        # unitContracts cannot stand.
        spec = _app()
        del spec["unitContracts"]
        errors = _errors(spec)
        self.assertTrue(any("unitContracts" in e.message for e in errors),
                        [e.message for e in errors])
        self.assertIn("apiOutcomeRules[0].verifiedBy[0]", [e.path for e in errors])

    def test_neither_is_an_error_naming_unit_contracts(self):
        spec = _app()
        del spec["unitContracts"]
        del spec["apiOutcomeRules"]
        msgs = [e.message for e in _errors(spec)]
        self.assertTrue(any("unitContracts" in m for m in msgs), msgs)

    def test_unknown_keys_are_refused(self):
        self.assertIn("apiOutcomeRule", _paths(_app(apiOutcomeRule=[])))

    def test_forbidden_sections_keep_their_own_message(self):
        errors = _errors(_app(branchContracts={"methods": {}}, transitions=[{"destination": "x"}]))
        by_path = {e.path: e.message for e in errors}
        self.assertIn("belongs to a screen", by_path["branchContracts"])
        self.assertIn("belongs to a screen", by_path["transitions"])

    def test_a_rule_shape_error_is_an_error(self):
        spec = _app()
        del spec["apiOutcomeRules"][0]["sideCalls"]
        self.assertIn("apiOutcomeRules[0].sideCalls", _paths(spec))

    def test_a_v3_rule_is_told_its_keys_were_withdrawn(self):
        spec = _app(apiOutcomeRules=[_rule(then={"transition": "Login"})])
        errors = _errors(spec)
        self.assertTrue(any(e.path == "apiOutcomeRules[0].then" and "withdrawn" in e.message
                            for e in errors), [(e.path, e.message) for e in errors])


def _document_with(site: str, value) -> dict:
    """A bare document holding `value` at `site` (`*` → a method, `[]` → one element)."""
    doc: dict = {}
    node = doc
    parts = site.replace("*", "anyMethod").split(".")
    for part in parts[:-1]:
        if part.endswith("[]"):
            element: dict = {}
            node[part[:-2]] = [element]
            node = element
        else:
            node = node.setdefault(part, {})
    node[parts[-1]] = value
    return doc


class TheParserIsImportedInsideTheCheck(unittest.TestCase):
    """A failed import is an ERROR where it matters and silence elsewhere."""

    def _without_parser(self, spec):
        real_import = builtins.__import__

        def refusing(name, *args, **kwargs):
            if name.startswith("jsonui_test_cli.contract_declarations"):
                raise ImportError("simulated: jsonui_test_cli missing")
            return real_import(name, *args, **kwargs)

        builtins.__import__ = refusing
        try:
            return _errors(spec)
        finally:
            builtins.__import__ = real_import

    def test_a_declaring_document_gets_an_error_naming_every_site(self):
        errors = self._without_parser(_screen())
        message = next((e.message for e in errors if "not importable" in e.message), None)
        self.assertIsNotNone(message, [e.message for e in errors])
        for site in SpecValidator._CONTRACT_DECLARATION_SITES:
            self.assertIn(site, message)

    def test_a_document_without_declarations_is_unaffected(self):
        spec = _bare(_screen())
        self.assertEqual(sorted(e.path for e in _errors(spec)),
                         sorted(e.path for e in self._without_parser(spec)))

    def test_the_failed_import_message_knows_every_site_the_parser_reads(self):
        """The validator's copy of the sites equals the parser's, and means it.

        Equality alone would pass two lists that agree and are both read
        wrongly, so each site is also planted alone in an otherwise bare
        document and must be recognised — and a bare document (including an
        empty branches list) must not be.
        """
        from jsonui_test_cli.contract_declarations import DECLARATION_SITES

        self.assertEqual(DECLARATION_SITES, SpecValidator._CONTRACT_DECLARATION_SITES)
        mentions = SpecValidator._mentions_contract_declarations
        for site in DECLARATION_SITES:
            self.assertTrue(mentions(_document_with(site, {})), site)
        self.assertFalse(mentions({"metadata": {}, "branchContracts": {"methods": {
            "m": {"branches": [], "baseline": {}}, "n": {"branches": [{"when": {}}]}}}}))

    def test_the_validator_module_does_not_import_it_at_load(self):
        import inspect

        import jsonui_doc_cli.spec_doc.validator as v
        head = inspect.getsource(v).split("class SpecValidator", 1)[0]
        self.assertNotIn("contract_declarations", head)


if __name__ == "__main__":
    unittest.main()
