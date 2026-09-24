"""`jsonui-doc validate spec` admits the contract-gap declarations and shapes them.

The hand-written allowlists in the validator are the real gate on a spec's
keys (the JSON schema describes, it does not validate), so the new
declaration sites exist only once they are admitted THERE. The shape itself
comes from `jsonui_test_cli.contract_declarations` — the same parser the
coverage command reads with — imported inside the check, so a failed import
is an ERROR on a document that declares something and nothing on one that
does not (a module-level import would be folded into one WARNING by
`jui generate`'s `except ImportError`).

And the app contracts spec: `apiOutcomeRules` alone is a valid document,
unknown keys are refused (a misspelt `apiOutcomeRule` would otherwise be a
rule with no effect), and `branchContracts` / `transitions` stay forbidden.
"""
from __future__ import annotations

import builtins
import copy
import unittest

from jsonui_doc_cli.spec_doc.validator import APP_CONTRACTS_SPEC, SpecValidator


def _screen(**bc_over):
    bc = {
        "methods": {"confirm": {
            "branches": [{"when": {"api.submitOrder": "default"},
                          "then": {"transition": "done"}}],
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


def _app(**over):
    spec = {"type": APP_CONTRACTS_SPEC, "version": "1.0",
            "metadata": {"name": "client", "description": "d"},
            "apiOutcomeRules": [{
                "id": "session-expired", "statuses": ["401"],
                "security": ["bearerAuth"], "then": {"transition": "Login"},
                "reason": "the client signs out on 401"}]}
    spec.update(over)
    return spec


def _errors(spec):
    return SpecValidator().validate_data(spec, "spec").errors


def _paths(spec):
    return [e.path for e in _errors(spec)]


class ScreenDeclarationsAreAdmitted(unittest.TestCase):
    def test_well_formed_declarations_add_no_error(self):
        spec = _screen()
        bare = copy.deepcopy(spec)
        del bare["branchContracts"]["unreachedOps"]
        del bare["branchContracts"]["methods"]["confirm"]["excludedOutcomes"]
        del bare["metadata"]["platforms"]
        # The declarations add nothing: same errors as the spec without them.
        self.assertEqual(sorted(_paths(bare)), sorted(_paths(spec)))
        self.assertFalse([p for p in _paths(spec)
                          if "unreachedOps" in p or "excludedOutcomes" in p
                          or p.startswith("metadata.platforms")])

    def test_a_shape_error_is_an_error_at_its_path(self):
        spec = _screen()
        spec["branchContracts"]["methods"]["confirm"]["excludedOutcomes"][
            "api.submitOrder"]["409"]["by"] = "method"
        spec["branchContracts"]["unreachedOps"]["api.prefetch"] = {}
        spec["metadata"]["platforms"] = ["desktop"]
        paths = _paths(spec)
        self.assertIn(
            "branchContracts.methods.confirm.excludedOutcomes.api.submitOrder.409.by", paths)
        self.assertIn("branchContracts.unreachedOps.api.prefetch.reason", paths)
        self.assertIn("metadata.platforms[0]", paths)

    def test_other_unknown_keys_are_still_refused(self):
        spec = _screen(unreached={"api.prefetch": {"reason": "r"}})
        self.assertIn("branchContracts.unreached", _paths(spec))
        spec = _screen()
        spec["branchContracts"]["methods"]["confirm"]["excluded"] = {}
        self.assertIn("branchContracts.methods.confirm.excluded", _paths(spec))

    def test_rules_on_a_screen_are_refused(self):
        spec = _screen()
        spec["apiOutcomeRules"] = _app()["apiOutcomeRules"]
        self.assertIn("apiOutcomeRules", _paths(spec))


class AppSpecCarriesRules(unittest.TestCase):
    def test_rules_alone_are_a_valid_app_spec(self):
        self.assertEqual([], [e.message for e in _errors(_app())])

    def test_units_alone_still_are(self):
        spec = _app(unitContracts=[{"target": "ApiClient", "cases": [{"name": "c"}]}])
        del spec["apiOutcomeRules"]
        self.assertEqual([], [e.message for e in _errors(spec)])

    def test_neither_is_refused(self):
        spec = _app()
        del spec["apiOutcomeRules"]
        msgs = [e.message for e in _errors(spec)]
        self.assertTrue(any("unitContracts" in m and "apiOutcomeRules" in m for m in msgs), msgs)

    def test_unknown_keys_are_refused(self):
        self.assertIn("apiOutcomeRule", _paths(_app(apiOutcomeRule=[])))

    def test_forbidden_sections_keep_their_own_message(self):
        errors = _errors(_app(branchContracts={"methods": {}}, transitions=[{"destination": "x"}]))
        by_path = {e.path: e.message for e in errors}
        self.assertIn("belongs to a screen", by_path["branchContracts"])
        self.assertIn("belongs to a screen", by_path["transitions"])

    def test_a_rule_shape_error_is_an_error(self):
        spec = _app()
        del spec["apiOutcomeRules"][0]["security"]
        self.assertIn("apiOutcomeRules[0].security", _paths(spec))

    def test_verified_by_names_a_case_in_this_file(self):
        rule = {"id": "server", "statuses": ["5XX"], "security": "*",
                "vm": "not-reached", "handledBy": "Toast",
                "verifiedBy": ["serverError_showsToast"], "reason": "r"}
        ok = _app(apiOutcomeRules=[rule], unitContracts=[
            {"target": "ApiClient", "cases": [{"name": "serverError_showsToast"}]}])
        self.assertEqual([], [e.message for e in _errors(ok)])
        missing = _app(apiOutcomeRules=[rule])
        self.assertIn("apiOutcomeRules[0].verifiedBy[0]", _paths(missing))


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

    def test_a_declaring_document_gets_an_error(self):
        errors = self._without_parser(_screen())
        self.assertTrue(any("not importable" in e.message for e in errors),
                        [e.message for e in errors])

    def test_a_document_without_declarations_is_unaffected(self):
        spec = _screen()
        del spec["branchContracts"]["unreachedOps"]
        del spec["branchContracts"]["methods"]["confirm"]["excludedOutcomes"]
        del spec["metadata"]["platforms"]
        self.assertEqual(sorted(e.path for e in _errors(spec)),
                         sorted(e.path for e in self._without_parser(spec)))

    def test_the_failed_import_message_knows_every_site_the_parser_reads(self):
        """The validator's copy of the sites equals the parser's, and means it.

        Equality alone would pass two lists that agree and are both read
        wrongly, so each site is also planted alone in an otherwise bare
        document and must be recognised — and a bare document must not be.
        """
        from jsonui_test_cli.contract_declarations import DECLARATION_SITES

        self.assertEqual(DECLARATION_SITES, SpecValidator._CONTRACT_DECLARATION_SITES)
        mentions = SpecValidator._mentions_contract_declarations
        for site in DECLARATION_SITES:
            doc: dict = {}
            node = doc
            parts = site.replace("*", "anyMethod").split(".")
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = {}
            self.assertTrue(mentions(doc), site)
        self.assertFalse(mentions({"metadata": {}, "branchContracts": {"methods": {"m": {}}}}))

    def test_the_validator_module_does_not_import_it_at_load(self):
        import inspect

        import jsonui_doc_cli.spec_doc.validator as v
        head = inspect.getsource(v).split("class SpecValidator", 1)[0]
        self.assertNotIn("contract_declarations", head)


if __name__ == "__main__":
    unittest.main()
