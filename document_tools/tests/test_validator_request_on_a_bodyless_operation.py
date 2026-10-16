"""`then "api.<op>.request"` on an operation that sends no request body.

`.request` is a partial match on the request BODY. On a GET / HEAD, or an
operation the API canon declares without a `requestBody`, the body the
runtimes record is always absent, so the generated assertion failed every
run while this validator said nothing about the row. It is now an error,
from the predicate the generator and `contracts coverage` use
(shared/core/openapi_canonical.py `request_body_absence`). An operation
with a body is unchanged.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonui_doc_cli.spec_doc.validator import SpecValidator

try:
    from .test_validator_branch_contracts import _base_spec, _errors_at, _ui_var
except ImportError:  # unittest discover runs tests as top-level modules
    from test_validator_branch_contracts import _base_spec, _errors_at, _ui_var


def _spec(endpoint: str, op: str = "loadCalls") -> dict:
    return _base_spec(
        {"methods": {"onConfirmTap": {"branches": [
            {"when": {"data.isAgreed": True},
             "then": {f"api.{op}.request": {"from": "2026-10-01"}}},
        ]}}},
        vm_methods=["onConfirmTap"],
        ui_vars=[_ui_var("isAgreed")],
        repositories=[{"name": "CallsRepository", "methods": [
            {"name": op, "endpoint": endpoint}]}],
    )


def _request_errors(result, op: str = "loadCalls"):
    return [e.message for e in _errors_at(result, f"then.api.{op}.request")]


class WithoutACanon(unittest.TestCase):
    def test_a_get_is_refused_and_the_message_says_why(self):
        errors = _request_errors(SpecValidator().validate_data(_spec("GET /api/calls")))
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("GET /api/calls sends no request body", errors[0])
        self.assertIn("partial match on the request body", errors[0])

    def test_a_head_is_refused(self):
        errors = _request_errors(SpecValidator().validate_data(_spec("HEAD /api/calls")))
        self.assertEqual(len(errors), 1, errors)

    def test_the_qualified_spelling_is_refused_too(self):
        spec = _spec("GET /api/calls")
        then = spec["branchContracts"]["methods"]["onConfirmTap"]["branches"][0]["then"]
        then["api.CallsRepository.loadCalls.request"] = then.pop("api.loadCalls.request")
        errors = _request_errors(SpecValidator().validate_data(spec),
                                 "CallsRepository.loadCalls")
        self.assertEqual(len(errors), 1, errors)

    def test_a_post_is_not_judged_without_a_canon(self):
        self.assertEqual(
            _request_errors(SpecValidator().validate_data(_spec("POST /api/calls"))), [])


class WithACanon(unittest.TestCase):
    """A method other than GET / HEAD is judged by the `requestBody` the
    project's API document declares for it."""

    def _validate(self, endpoint: str, operation: dict):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "jui.config.json").write_text("{}", encoding="utf-8")
            method, path = endpoint.split(" ", 1)
            api = root / "docs" / "api" / "swagger.json"
            api.parent.mkdir(parents=True)
            api.write_text(json.dumps({"openapi": "3.0.3", "paths": {
                path: {method.lower(): {"responses": {"200": {}}, **operation}}}}),
                encoding="utf-8")
            spec_path = root / "docs" / "screens" / "calls.spec.json"
            spec_path.parent.mkdir(parents=True)
            spec_path.write_text(json.dumps(_spec(endpoint)), encoding="utf-8")
            return _request_errors(SpecValidator().validate_file(spec_path))

    def test_a_post_without_a_requestbody_is_refused(self):
        errors = self._validate("POST /api/calls", {})
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("declares no requestBody", errors[0])

    def test_a_delete_without_a_requestbody_is_refused(self):
        self.assertEqual(len(self._validate("DELETE /api/calls/{id}", {})), 1)

    def test_a_post_with_a_requestbody_is_unchanged(self):
        body = {"requestBody": {"content": {"application/json": {
            "schema": {"type": "object"}}}}}
        self.assertEqual(self._validate("POST /api/calls", body), [])


if __name__ == "__main__":
    unittest.main()
