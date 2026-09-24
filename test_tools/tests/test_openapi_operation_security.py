"""`Operation.security` is the operation's EFFECTIVE requirement list.

The contract-gap check's app-wide rules match on it ("a 401 on a call that
carries credentials"), and until this nothing in the toolchain read security
at all. OpenAPI's rule: an operation's own `security` replaces the
document's, and an operation that declares `security: []` has none even
under a document-wide requirement.
"""
from __future__ import annotations

import unittest

from jsonui_test_cli.mock.openapi import OpenApiDoc


def _doc(doc_security=None, **ops):
    spec = {"openapi": "3.0.3", "info": {"title": "t", "version": "1"},
            "components": {"securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer"},
                "apiKey": {"type": "apiKey", "in": "header", "name": "X-Key"}}},
            "paths": {}}
    if doc_security is not None:
        spec["security"] = doc_security
    for op_id, op_security in ops.items():
        op = {"operationId": op_id, "responses": {"200": {"description": "ok"}}}
        if op_security != "absent":
            op["security"] = op_security
        spec["paths"][f"/{op_id}"] = {"get": op}
    return OpenApiDoc(spec)


def _security(doc):
    return {op.operation_id: op.security for op in doc.operations()}


class EffectiveSecurity(unittest.TestCase):
    def test_the_document_default_applies_where_the_operation_says_nothing(self):
        doc = _doc([{"bearerAuth": []}], inherits="absent")
        self.assertEqual({"inherits": [{"bearerAuth": []}]}, _security(doc))

    def test_the_operation_replaces_the_document(self):
        doc = _doc([{"bearerAuth": []}], own=[{"apiKey": []}])
        self.assertEqual({"own": [{"apiKey": []}]}, _security(doc))

    def test_an_empty_list_means_no_credentials_even_under_a_default(self):
        doc = _doc([{"bearerAuth": []}], public=[])
        self.assertEqual({"public": []}, _security(doc))

    def test_optional_auth_keeps_its_empty_requirement(self):
        doc = _doc(None, optional=[{}, {"bearerAuth": []}])
        self.assertEqual({"optional": [{}, {"bearerAuth": []}]}, _security(doc))

    def test_nothing_declared_anywhere_is_empty(self):
        self.assertEqual({"bare": []}, _security(_doc(None, bare="absent")))

    def test_scheme_names_and_definitions(self):
        doc = _doc(None, x="absent")
        self.assertEqual({"bearerAuth", "apiKey"}, doc.security_scheme_names())
        self.assertEqual("bearer", doc.security_schemes()["bearerAuth"]["scheme"])
        self.assertEqual(set(), OpenApiDoc({"paths": {}}).security_scheme_names())


if __name__ == "__main__":
    unittest.main()
