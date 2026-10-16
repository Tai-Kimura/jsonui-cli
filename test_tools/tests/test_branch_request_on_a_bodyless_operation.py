"""`then "api.<op>.request"` on an operation that sends no request body.

`.request` is a partial match on the request BODY the runtimes record
(`rec.lastBodyFor`). On a GET / HEAD, or an operation whose OpenAPI document
declares no `requestBody`, that body is always absent, so the generated
assertion failed every run with "$: expected object, got undefined" — the
same whether the view model sent the right query or not — while the spec
validator, the generator and `contracts coverage` all passed the row.

The refusal is one predicate (shared/core/openapi_canonical.py
`request_body_absence`) reached through the route binding both the generator
and coverage use; `jsonui-doc validate spec` asks the same predicate (its own
test in document_tools). An operation with a body keeps `.request` as it was.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from jsonui_test_cli.branch_tests import BranchTestGenerationError, generate_branch_tests
from tests.test_branch_tests_generator import _contract, _project
from tests import test_contracts_coverage as cov


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")


def _request_row(op: str, body: dict) -> dict:
    return _contract([{"when": {"data.isAgreed": True},
                       "then": {f"api.{op}.request": body}}])


class TestGenerate:
    def test_a_get_request_match_is_refused_and_says_why(self, tmp_path):
        root = _project(tmp_path, _request_row("fetchOrder", {"id": "o1"}))
        with pytest.raises(BranchTestGenerationError) as e:
            generate_branch_tests("checkout", root)
        msg = str(e.value)
        assert "branches[0].then.api.fetchOrder.request" in msg
        assert "GET /api/user/orders/{id} sends no request body" in msg
        assert "partial match on the request body" in msg

    def test_check_refuses_it_too(self, tmp_path):
        root = _project(tmp_path, _request_row("fetchOrder", {"id": "o1"}))
        with pytest.raises(BranchTestGenerationError, match="sends no request body"):
            generate_branch_tests("checkout", root, check=True)

    def test_a_post_request_match_still_generates(self, tmp_path):
        root = _project(tmp_path, _request_row("createOrder", {"id": 1}))
        content = generate_branch_tests("checkout", root).test_file.read_text(encoding="utf-8")
        assert 'partialMismatches(rec.lastBodyFor("createOrder"), { "id": 1 })' in content

    @pytest.mark.parametrize("declares_body,refused", [(False, True), (True, False)])
    def test_a_post_is_judged_by_the_requestbody_the_canon_declares(
            self, tmp_path, declares_body, refused):
        root = _project(tmp_path, _request_row("createOrder", {"id": 1}))
        post = {"operationId": "createOrder", "responses": {"200": {}}}
        if declares_body:
            post["requestBody"] = {"content": {"application/json": {"schema": {"type": "object"}}}}
        _write(root / "docs/api/api.json", {"openapi": "3.0.0", "paths": {
            "/api/user/orders": {"post": post},
            "/api/user/orders/{id}": {"get": {"responses": {"200": {}}}}}})
        if refused:
            with pytest.raises(BranchTestGenerationError) as e:
                generate_branch_tests("checkout", root)
            assert "POST /api/user/orders sends no request body" in str(e.value)
            assert "declares no requestBody" in str(e.value)
        else:
            generate_branch_tests("checkout", root)


class TestCoverage:
    """`contracts coverage` (and with it `jsonui-test validate`'s coverage
    section) binds through the same route resolution."""

    def _errors(self, tmp_path, op, openapi=None):
        screen = cov._screen()
        branches = screen["branchContracts"]["methods"]["approve"]["branches"]
        branches[0]["then"][f"api.{op}.request"] = {"id": 1}
        root = cov._project(tmp_path, screen, openapi=openapi)
        report = cov._run(root)
        # A row that cannot bind is not evaluated (as an unknown scenario is),
        # and its statuses count not-evaluated.
        result = cov._screen_result(report)
        return [e["message"] for e in result.not_evaluated + result.declaration_errors]

    def test_a_get_request_match_is_refused(self, tmp_path):
        errors = self._errors(tmp_path, "getItem")
        assert any("GET /api/items/{id} sends no request body" in m for m in errors), errors

    def test_a_put_the_canon_declares_without_a_body_is_one_too(self, tmp_path):
        errors = self._errors(tmp_path, "setApproval")
        assert any("PUT /api/items/{id}/approval sends no request body" in m
                   for m in errors), errors

    def test_a_put_with_a_body_is_not(self, tmp_path):
        openapi = copy.deepcopy(cov._OPENAPI)
        openapi["paths"]["/api/items/{id}/approval"]["put"]["requestBody"] = {
            "content": {"application/json": {"schema": {"type": "object"}}}}
        errors = self._errors(tmp_path, "setApproval", openapi=openapi)
        assert not any("sends no request body" in m for m in errors), errors
