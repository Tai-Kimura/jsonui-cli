"""Tests for `jsonui-test generate branch-tests` (P2 branch-contract codegen).

The generator must be mechanical AND fail hard when vocabulary cannot be
bound to real assets (endpoint declarations, mock files, scenario names,
witnesses) — a test that silently weakens is a ritual test.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jsonui_test_cli.branch_tests import (
    BranchTestGenerationError,
    generate_branch_tests,
    path_to_pattern,
)


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _project(tmp_path: Path, branch_contracts, *, scenarios=None) -> Path:
    root = tmp_path / "proj"
    root.mkdir(parents=True, exist_ok=True)
    _write(root / "jui.config.json", {"spec_directory": "docs/specs"})
    spec = {
        "type": "screen_spec",
        "version": "1.0",
        "metadata": {"name": "Checkout", "displayName": "Checkout",
                     "description": "d", "layoutFile": "checkout"},
        "structure": {"components": [], "layout": {}},
        "dataFlow": {
            "viewModel": {
                "methods": [
                    {"name": "onConfirmTap"},
                    {"name": "onModeSelected",
                     "params": [{"name": "mode", "type": "String"},
                                {"name": "index", "type": "Int"}]},
                ],
                "vars": [],
            },
            "repositories": [
                {"name": "OrderRepository", "methods": [
                    {"name": "createOrder", "endpoint": "POST /api/user/orders"},
                    {"name": "fetchOrder",
                     "endpoint": "GET /api/user/orders/{id}"},
                    {"name": "noMockOp", "endpoint": "DELETE /api/user/orders/{id}"},
                ]},
            ],
        },
        "stateManagement": {"uiVariables": []},
        "branchContracts": branch_contracts,
    }
    _write(root / "docs/specs/checkout.spec.json", spec)
    _write(root / "tests/mocks/orders/post_api-user-orders.mock.json", {
        "source": {"method": "POST", "path": "/api/user/orders"},
        "activeScenario": "success",
        "scenarios": scenarios or {
            "success": {"status": 200, "body": {"order": {"id": "o1"}}},
            "conflict": {"status": 409,
                         "body": {"error": {"code": "sold_out"}}},
        },
    })
    _write(root / "tests/mocks/orders/get_api-user-orders-by-id.mock.json", {
        "source": {"method": "GET", "path": "/api/user/orders/{id}"},
        "activeScenario": "reserved",
        "scenarios": {"reserved": {"status": 200,
                                   "body": {"order": {"status": "reserved"}}}},
    })
    return root


def _contract(branches, *, conditions=None, baseline=None):
    contract = {"branches": branches}
    if baseline is not None:
        contract["baseline"] = baseline
    bc = {"methods": {"onConfirmTap": contract}}
    if conditions is not None:
        bc["conditions"] = conditions
    return bc


BASIC = _contract([
    {"when": {"data.isAgreed": False}, "then": {"api": "none"}},
    {"when": {"api.createOrder": "conflict"},
     "then": {"data.screenState": "order_error"}},
    {"note": "polling sequence is out of scope"},
])


class TestPathPattern:
    def test_static_and_param_paths(self):
        assert path_to_pattern("/api/user/orders") == r"^/api/user/orders$"
        pattern = path_to_pattern("/api/user/orders/{id}")
        import re
        assert re.match(pattern, "/api/user/orders/abc-123")
        assert not re.match(pattern, "/api/user/orders/abc/extra")


class TestGenerationHappyPath:
    def test_files_and_counts(self, tmp_path):
        root = _project(tmp_path, BASIC)
        report = generate_branch_tests("checkout", root)
        assert report.declared_branches == 2
        assert report.note_branches == 1
        assert report.test_file.exists()
        assert report.runtime_file.exists()
        assert report.harness_file.exists()
        assert report.harness_created is True

    def test_test_content_shape(self, tmp_path):
        root = _project(tmp_path, BASIC)
        report = generate_branch_tests("checkout", root)
        content = report.test_file.read_text(encoding="utf-8")
        assert "@generated" in content
        # arrange from when.data
        assert 'h.setState({"isAgreed": false})' in content
        # api none assertion
        assert "expect(rec.calls).toEqual([]);" in content
        # scenario override for when.api
        assert 'installFetchMock(ROUTES, {"createOrder": "conflict"})' in content
        # data assertion
        assert 'expect(h.readField("screenState")).toEqual("order_error");' in content
        # note branch is listed as a comment with its number, not a test
        assert "#3: polling sequence is out of scope" in content
        assert content.count("it(") == 2
        # both mock-backed routes join the table; the mockless one does not
        assert '"createOrder"' in content and '"fetchOrder"' in content
        assert "noMockOp" not in content

    def test_harness_not_overwritten(self, tmp_path):
        root = _project(tmp_path, BASIC)
        generate_branch_tests("checkout", root)
        harness = root / "tests/unit/branch-harness/checkout.ts"
        harness.write_text("// customized", encoding="utf-8")
        report = generate_branch_tests("checkout", root)
        assert report.harness_created is False
        assert harness.read_text(encoding="utf-8") == "// customized"

    def test_baseline_and_condition_witness_merge_order(self, tmp_path):
        bc = _contract(
            [{"when": {"cond": "!needsPayment", "data.isAgreed": True},
              "then": {"api.createOrder": "not-called"}}],
            conditions={"needsPayment": {
                "meaning": "m",
                "witness_true": {"amount": 100},
                "witness_false": {"amount": 0, "isAgreed": False},
            }},
            baseline={"amount": 999, "plate": "x"},
        )
        root = _project(tmp_path, bc)
        report = generate_branch_tests("checkout", root)
        content = report.test_file.read_text(encoding="utf-8")
        # baseline < witness_false < when.data — when.data wins on isAgreed,
        # witness wins on amount, baseline survives on plate.
        assert '"amount": 0' in content
        assert '"isAgreed": true' in content
        assert '"plate": "x"' in content
        assert 'expect(rec.countFor("createOrder")).toBe(0);' in content

    def test_arg_mapping_by_param_order(self, tmp_path):
        bc = {"methods": {"onModeSelected": {"branches": [
            {"when": {"arg.index": 2, "data.isAgreed": True},
             "then": {"api": "none"}},
        ]}}}
        root = _project(tmp_path, bc)
        report = generate_branch_tests("checkout", root)
        content = report.test_file.read_text(encoding="utf-8")
        # first param (mode) undeclared -> undefined, second -> 2
        assert ".onModeSelected(undefined, 2);" in content

    def test_data_ref_captured_before_act(self, tmp_path):
        bc = _contract([
            {"when": {"api.createOrder": "success"},
             "then": {"api.createOrder.request": {
                 "fingerprint": "@data.fingerprint", "amount": 10,
                 "coupon": None},
                 "data.echo": "@data.fingerprint"}},
        ])
        root = _project(tmp_path, bc)
        report = generate_branch_tests("checkout", root)
        content = report.test_file.read_text(encoding="utf-8")
        capture = content.index('const ref_fingerprint = h.readField("fingerprint");')
        act = content.index(".onConfirmTap();")
        assert capture < act
        assert '"fingerprint": ref_fingerprint' in content
        assert '"coupon": null' in content

    def test_strings_key_resolves_through_harness(self, tmp_path):
        bc = _contract([
            {"when": {"data.isAgreed": True},
             "then": {"data.errorMessage": "@order_error_generic"}},
        ])
        root = _project(tmp_path, bc)
        content = generate_branch_tests("checkout", root).test_file.read_text(encoding="utf-8")
        assert 'h.resolveString("order_error_generic")' in content

    def test_transition_goes_through_harness(self, tmp_path):
        bc = _contract([
            {"when": {"api.createOrder": "success"},
             "then": {"transition": "order_complete"}},
        ])
        root = _project(tmp_path, bc)
        content = generate_branch_tests("checkout", root).test_file.read_text(encoding="utf-8")
        assert 'h.expectTransition("order_complete");' in content


class TestGenerationHardErrors:
    def test_unknown_api_op_is_error(self, tmp_path):
        bc = _contract([
            {"when": {"api.ghostOp": "success"}, "then": {"api": "none"}},
        ])
        root = _project(tmp_path, bc)
        with pytest.raises(BranchTestGenerationError, match="ghostOp"):
            generate_branch_tests("checkout", root)

    def test_missing_mock_file_is_error(self, tmp_path):
        bc = _contract([
            {"when": {"api.noMockOp": "success"}, "then": {"api": "none"}},
        ])
        root = _project(tmp_path, bc)
        with pytest.raises(BranchTestGenerationError, match="no mock file"):
            generate_branch_tests("checkout", root)

    def test_missing_scenario_is_error(self, tmp_path):
        bc = _contract([
            {"when": {"api.createOrder": "ghost_scenario"},
             "then": {"api": "none"}},
        ])
        root = _project(tmp_path, bc)
        with pytest.raises(BranchTestGenerationError, match="ghost_scenario"):
            generate_branch_tests("checkout", root)

    def test_missing_witness_is_error(self, tmp_path):
        bc = _contract(
            [{"when": {"cond": "needsPayment"}, "then": {"api": "none"}}],
            conditions={"needsPayment": {"meaning": "m"}},
        )
        root = _project(tmp_path, bc)
        with pytest.raises(BranchTestGenerationError, match="witness_true"):
            generate_branch_tests("checkout", root)

    def test_no_contracts_is_error(self, tmp_path):
        root = _project(tmp_path, {"methods": {}})
        with pytest.raises(BranchTestGenerationError, match="nothing to generate"):
            generate_branch_tests("checkout", root)

    def test_missing_spec_is_error(self, tmp_path):
        root = _project(tmp_path, BASIC)
        with pytest.raises(BranchTestGenerationError, match="spec not found"):
            generate_branch_tests("ghost_screen", root)
