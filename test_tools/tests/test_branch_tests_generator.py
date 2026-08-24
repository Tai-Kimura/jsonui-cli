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
        assert "expect(rec.matchedCalls()).toEqual([]);" in content
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

    def test_harness_skeleton_uses_closed_string_keys_map(self, tmp_path):
        # Consumer feedback (2026-08-24): a dynamic getString(`<screen>_${key}`)
        # in the harness trips `jui lint-strings --usage` and blocks consumers
        # running the always-on usage gate. The skeleton must teach the closed
        # *_STRING_KEYS map form instead.
        root = _project(tmp_path, BASIC)
        report = generate_branch_tests("checkout", root)
        skeleton = report.harness_file.read_text(encoding="utf-8")
        assert "CHECKOUT_BRANCH_STRING_KEYS" in skeleton
        assert "lint-strings --usage" in skeleton
        assert "SCREEN_ROUTES" in skeleton

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


class TestAndroidEmission:
    PKG = "com.example.checkout"

    def _generate(self, tmp_path, bc=None):
        root = _project(tmp_path, bc or BASIC)
        return generate_branch_tests(
            "checkout", root, platform="android", package=self.PKG,
            out_dir="app/src/test/java", harness_dir="app/src/test/java",
        ), root

    def test_files_land_under_package_path(self, tmp_path):
        report, root = self._generate(tmp_path)
        base = root / "app/src/test/java/com/example/checkout"
        assert report.test_file == base / "CheckoutBranchesTest.kt"
        assert report.runtime_file == base / "JsonuiBranchRuntime.kt"
        assert report.harness_file == base / "CheckoutBranchHarness.kt"
        assert report.harness_created is True
        assert report.declared_branches == 2

    def test_kotlin_test_content_shape(self, tmp_path):
        report, _root = self._generate(tmp_path)
        content = report.test_file.read_text(encoding="utf-8")
        assert "@generated" in content
        assert f"package {self.PKG}" in content
        assert "@RunWith(RobolectricTestRunner::class)" in content
        assert "class CheckoutBranchesTest" in content
        # arrange / act / settle / asserts
        assert 'h.setState(mapOf<String, Any?>("isAgreed" to false))' in content
        assert 'h.invoke("onConfirmTap")' in content
        assert "h.settle()" in content
        assert "rec.matchedCalls().isEmpty()" in content
        # scenario override map for when.api
        assert '"createOrder" to "conflict"' in content
        assert 'assertFieldEquals("order_error", h.readField("screenState"))' in content
        # note branch listed as a comment, not a test
        assert "#3: polling sequence is out of scope" in content
        assert content.count("@Test") == 2
        # scenario bodies are embedded (self-contained tests)
        assert "sold_out" in content

    def test_kotlin_runtime_and_harness(self, tmp_path):
        report, _root = self._generate(tmp_path)
        runtime = report.runtime_file.read_text(encoding="utf-8")
        assert f"package {self.PKG}" in runtime
        assert "MockWebServer" in runtime
        assert "BaseBranchHarness" in runtime
        assert "partialMismatches" in runtime
        skeleton = report.harness_file.read_text(encoding="utf-8")
        assert "createCheckoutBranchHarness" in skeleton
        assert "NotImplementedError" in skeleton

    def test_kotlin_data_ref_and_request_partial(self, tmp_path):
        bc = _contract([
            {"when": {"api.createOrder": "success"},
             "then": {"api.createOrder.request": {
                 "fingerprint": "@data.fingerprint", "coupon": None}}},
        ])
        report, _root = self._generate(tmp_path, bc)
        content = report.test_file.read_text(encoding="utf-8")
        capture = content.index('val ref_fingerprint = h.readField("fingerprint")')
        act = content.index('h.invoke("onConfirmTap")')
        assert capture < act
        assert '"fingerprint" to Ref(ref_fingerprint)' in content
        assert '"coupon" to null' in content

    def test_android_requires_package(self, tmp_path):
        root = _project(tmp_path, BASIC)
        with pytest.raises(BranchTestGenerationError, match="--package"):
            generate_branch_tests("checkout", root, platform="android")

    def test_kotlin_harness_not_overwritten(self, tmp_path):
        report, root = self._generate(tmp_path)
        report.harness_file.write_text("// customized", encoding="utf-8")
        report2, _ = (generate_branch_tests(
            "checkout", root, platform="android", package=self.PKG,
            out_dir="app/src/test/java", harness_dir="app/src/test/java",
        ), root)
        assert report2.harness_created is False
        assert report.harness_file.read_text(encoding="utf-8") == "// customized"

    def test_web_output_unchanged_by_android_support(self, tmp_path):
        # The web path must stay byte-stable: platform defaults to web.
        root = _project(tmp_path, BASIC)
        report = generate_branch_tests("checkout", root)
        assert report.test_file.name == "checkout.branches.test.ts"
        content = report.test_file.read_text(encoding="utf-8")
        assert "vitest" in content


class TestMockDirResolution:
    """`mock.mockDir` is how a project says where its mocks live, and the
    other mock subcommands honour it. Branch-test generation read only the
    flag, so a project whose mocks sit outside the app directory was told
    the file was missing when it existed somewhere never searched."""

    def test_error_names_the_directory_it_searched(self, tmp_path):
        bc = _contract([{"when": {"api.noMockOp": "whatever"},
                         "then": {"api": "none"}}])
        root = _project(tmp_path, bc)
        with pytest.raises(BranchTestGenerationError) as excinfo:
            generate_branch_tests("checkout", root, mocks_dir="tests/elsewhere")
        message = str(excinfo.value)
        assert str((root / "tests/elsewhere").resolve()) in message
        assert "found 0 mock file(s)" in message

    def test_generation_uses_the_directory_it_is_given(self, tmp_path):
        root = _project(tmp_path, BASIC)
        moved = root / "custom" / "mocks"
        moved.parent.mkdir(parents=True, exist_ok=True)
        (root / "tests" / "mocks").rename(moved)
        # The default location no longer holds them...
        with pytest.raises(BranchTestGenerationError):
            generate_branch_tests("checkout", root)
        # ...and naming the real one succeeds.
        report = generate_branch_tests("checkout", root, mocks_dir="custom/mocks")
        assert report.declared_branches == 2


class TestDeclaredKeyGuard:
    """Arranging a data-only field used to invent a property on the
    ViewModel, and readField consults the ViewModel first — so every later
    read returned the arranged value and the branch failed against correct
    code. It only surfaces once a baseline arranges a pre-state, which is
    exactly what "… is cleared" contracts need. Reported from a consumer
    lane after following that advice."""

    def test_runtime_ships_the_guard(self, tmp_path):
        root = _project(tmp_path, BASIC)
        report = generate_branch_tests("checkout", root)
        runtime = report.runtime_file.read_text(encoding="utf-8")
        assert "export function applyDeclaredKeys(" in runtime
        body = runtime[runtime.index("export function applyDeclaredKeys("):]
        assert "if (key in target)" in body

    def test_skeleton_points_at_the_guard(self, tmp_path):
        root = _project(tmp_path, BASIC)
        report = generate_branch_tests("checkout", root)
        skeleton = report.harness_file.read_text(encoding="utf-8")
        assert "applyDeclaredKeys(vm, state)" in skeleton
        # Says why, not just what — the guard is worthless if someone
        # "simplifies" it back to an assignment loop.
        assert "data-only fields" in skeleton
        assert "rather than assigning in a loop" in skeleton


class TestArgBindings:
    """An `arg.<name>` that binds to no declared parameter used to be
    dropped: the method was invoked with no arguments and the branch ran a
    different case than it declared. Reported from a screen whose method was
    declared only in stateManagement.eventHandlers, which by design carries
    no signature."""

    def test_declared_param_is_passed_to_the_call(self, tmp_path):
        bc = _contract([{"when": {"arg.mode": "express"},
                         "then": {"api": "none"}}])
        bc["methods"]["onModeSelected"] = bc["methods"].pop("onConfirmTap")
        root = _project(tmp_path, bc)
        report = generate_branch_tests("checkout", root)
        content = report.test_file.read_text(encoding="utf-8")
        assert '"express"' in content

    def test_unknown_param_on_a_declared_method_is_a_hard_error(self, tmp_path):
        bc = _contract([{"when": {"arg.ghost": "x"}, "then": {"api": "none"}}])
        bc["methods"]["onModeSelected"] = bc["methods"].pop("onConfirmTap")
        root = _project(tmp_path, bc)
        with pytest.raises(BranchTestGenerationError) as excinfo:
            generate_branch_tests("checkout", root)
        message = str(excinfo.value)
        assert "declares no parameter 'ghost'" in message
        assert "mode" in message  # the params it does declare

    def test_method_without_a_parameter_list_is_a_hard_error(self, tmp_path):
        # onConfirmTap is declared, but with no params — the shape a
        # handler-only method also produces.
        bc = _contract([{"when": {"arg.status": "open"},
                         "then": {"api": "none"}}])
        root = _project(tmp_path, bc)
        with pytest.raises(BranchTestGenerationError, match="declares no parameter"):
            generate_branch_tests("checkout", root)

    def test_undeclared_method_points_at_the_viewmodel(self, tmp_path):
        bc = _contract([{"when": {"arg.status": "open"},
                         "then": {"api": "none"}}])
        bc["methods"]["onStatusTap"] = bc["methods"].pop("onConfirmTap")
        root = _project(tmp_path, bc)
        with pytest.raises(BranchTestGenerationError) as excinfo:
            generate_branch_tests("checkout", root)
        message = str(excinfo.value)
        assert "dataFlow.viewModel.methods" in message
        assert "eventHandlers" in message


_PASSTHROUGH_SCENARIOS = {
    "success": {"status": 200, "body": {"order": {"id": "o1"}}},
    "declined": {"status": 402, "body": {"error": {
        "code": "card_declined", "message": "お支払いを確認できませんでした"}}},
}


class TestResponsePassthrough:
    """A screen that shows a message the server chose could not be
    contracted: the text is neither ours to spell nor a strings key, so such
    branches were written as prose notes. `@response.<path>` says "this field
    shows what the server sent" and resolves against the branch's own
    scenario at generation time."""

    def _project_with(self, tmp_path, then, when=None):
        bc = _contract([{
            "when": when or {"api.createOrder": "declined"},
            "then": then,
        }])
        return _project(tmp_path, bc, scenarios=_PASSTHROUGH_SCENARIOS)

    def test_resolves_to_the_text_the_scenario_returns(self, tmp_path):
        root = self._project_with(
            tmp_path, {"data.errorMessage": "@response.error.message"})
        report = generate_branch_tests("checkout", root)
        content = report.test_file.read_text(encoding="utf-8")
        assert "お支払いを確認できませんでした" in content
        # Resolved to a literal, so every renderer gets it without new
        # runtime support — no marker survives into the emitted test.
        assert "@response" not in content

    def test_resolves_for_every_platform(self, tmp_path):
        root = self._project_with(
            tmp_path, {"data.errorMessage": "@response.error.message"})
        android = generate_branch_tests(
            "checkout", root, platform="android", package="com.example.x",
            out_dir="app/src/test/java", harness_dir="app/src/test/java")
        ios = generate_branch_tests(
            "checkout", root, platform="ios", module="checkout_app",
            out_dir="Tests/Generated", harness_dir="Tests/Generated")
        for report in (android, ios):
            content = report.test_file.read_text(encoding="utf-8")
            assert "お支払いを確認できませんでした" in content

    def test_scalar_at_the_top_level_resolves(self, tmp_path):
        scenarios = {
            "success": {"status": 200, "body": {"order": {"id": "o1"}}},
            "declined": {"status": 402, "body": {"detail": "no funds"}},
        }
        bc = _contract([{"when": {"api.createOrder": "declined"},
                         "then": {"data.errorMessage": "@response.detail"}}])
        root = _project(tmp_path, bc, scenarios=scenarios)
        report = generate_branch_tests("checkout", root)
        assert "no funds" in report.test_file.read_text(encoding="utf-8")

    def test_absent_path_is_a_hard_error_naming_what_is_there(self, tmp_path):
        root = self._project_with(
            tmp_path, {"data.errorMessage": "@response.error.detail"})
        with pytest.raises(BranchTestGenerationError) as excinfo:
            generate_branch_tests("checkout", root)
        message = str(excinfo.value)
        assert "error.detail" in message
        assert "code, message" in message  # the keys that do exist

    def test_object_valued_path_is_a_hard_error(self, tmp_path):
        root = self._project_with(
            tmp_path, {"data.errorMessage": "@response.error"})
        with pytest.raises(BranchTestGenerationError, match="must be a scalar"):
            generate_branch_tests("checkout", root)

    def test_branch_without_a_scenario_is_a_hard_error(self, tmp_path):
        root = self._project_with(
            tmp_path, {"data.errorMessage": "@response.error.message"},
            when={"data.isAgreed": False})
        with pytest.raises(BranchTestGenerationError, match="exactly one"):
            generate_branch_tests("checkout", root)


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


class TestLauncher:
    def test_self_contained_launcher_knows_branch_tests(self):
        # Consumer report (2026-08-24): a stale pip/homebrew `jsonui-test`
        # console script shadowed the synced toolchain and did not know
        # `generate branch-tests`. bootstrap.sh probes for this launcher —
        # it must exist, be executable, and resolve the subcommand.
        import subprocess, sys
        from pathlib import Path
        launcher = Path(__file__).resolve().parents[1] / "jsonui-test"
        assert launcher.exists()
        assert launcher.stat().st_mode & 0o111, "launcher must be executable"
        proc = subprocess.run(
            [sys.executable, str(launcher), "generate", "branch-tests", "--help"],
            capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        assert "--platform" in proc.stdout


class TestIosEmission:
    MODULE = "checkout_app"

    def _generate(self, tmp_path, bc=None):
        root = _project(tmp_path, bc or BASIC)
        return generate_branch_tests(
            "checkout", root, platform="ios", module=self.MODULE,
            out_dir="Tests/Generated", harness_dir="Tests/Generated",
        ), root

    def test_files_and_shape(self, tmp_path):
        report, root = self._generate(tmp_path)
        base = root / "Tests/Generated"
        assert report.test_file == base / "CheckoutBranchesTest.swift"
        assert report.runtime_file == base / "JsonuiBranchRuntime.swift"
        assert report.harness_file == base / "CheckoutBranchHarness.swift"
        assert report.harness_created is True
        content = report.test_file.read_text(encoding="utf-8")
        assert "@generated" in content
        assert f"@testable import {self.MODULE}" in content
        assert "final class CheckoutBranchesTest: XCTestCase" in content
        assert 'h.setState(["isAgreed": false])' in content
        assert 'h.invoke("onConfirmTap", args: [])' in content
        assert "h.settle()" in content
        assert "XCTAssertTrue(rec.matchedCalls().isEmpty" in content
        assert '"createOrder": "conflict"' in content
        assert 'assertFieldEquals("order_error", h.readField("screenState"))' in content
        assert "#3: polling sequence is out of scope" in content
        assert content.count("func test_") == 2

    def test_runtime_and_harness(self, tmp_path):
        report, _root = self._generate(tmp_path)
        runtime = report.runtime_file.read_text(encoding="utf-8")
        assert "BranchURLProtocol" in runtime
        assert "URLProtocol.registerClass" in runtime
        assert "httpBodyStream" in runtime
        assert "mirrorField" in runtime
        assert "partialMismatches" in runtime
        skeleton = report.harness_file.read_text(encoding="utf-8")
        assert "createCheckoutBranchHarness" in skeleton
        assert f"@testable import {self.MODULE}" in skeleton
        assert "Data.update(dictionary:)" in skeleton

    def test_null_expectation_normalizes_against_swift_nil(self, tmp_path):
        # A contract asserting a field returns to "unset" spells it `null`,
        # which emits NSNull(); a harness handing an Optional property
        # straight through returns Swift nil. Comparing their descriptions
        # ("<null>" vs "nil") never matched, so such a branch could not be
        # written on iOS at all — reported from a rollback contract.
        bc = _contract([
            {"when": {"api.createOrder": "conflict"},
             "then": {"data.reactionType": None}},
        ])
        report, _root = self._generate(tmp_path, bc)
        runtime = report.runtime_file.read_text(encoding="utf-8")
        assert "func normalizeNull(" in runtime
        # Applied to both sides, and before the numeric comparison so a
        # null expectation cannot fall through it.
        body = runtime[runtime.index("func assertFieldEquals("):]
        body = body[:body.index("\nprivate func asDouble")]
        assert "let exp = normalizeNull(" in body
        assert "let act = normalizeNull(actual)" in body
        assert "asDouble(act)" in body
        assert report.test_file.read_text(encoding="utf-8").count("NSNull()") >= 1

    def test_ios_requires_module(self, tmp_path):
        root = _project(tmp_path, BASIC)
        with pytest.raises(BranchTestGenerationError, match="--module"):
            generate_branch_tests("checkout", root, platform="ios")

    def test_data_ref_and_request_partial(self, tmp_path):
        bc = _contract([
            {"when": {"api.createOrder": "success"},
             "then": {"api.createOrder.request": {
                 "fingerprint": "@data.fingerprint", "coupon": None}}},
        ])
        report, _root = self._generate(tmp_path, bc)
        content = report.test_file.read_text(encoding="utf-8")
        capture = content.index('let ref_fingerprint = h.readField("fingerprint")')
        act = content.index('h.invoke("onConfirmTap", args: [])')
        assert capture < act
        assert '"fingerprint": Ref(value: ref_fingerprint)' in content
        assert '"coupon": NSNull()' in content


class TestPlatformScopedBranches:
    def _bc(self):
        return _contract([
            {"when": {"data.isAgreed": False}, "then": {"api": "none"}},
            {"when": {"data.isAgreed": True}, "then": {"api": "none"},
             "platforms": ["android"]},
            {"when": {"data.isAgreed": True}, "then": {"api": "none"},
             "platforms": ["ios", "web"]},
        ])

    def test_each_platform_filters_and_counts(self, tmp_path):
        root = _project(tmp_path, self._bc())
        web = generate_branch_tests("checkout", root)
        assert (web.declared_branches, web.platform_skipped) == (2, 1)
        android = generate_branch_tests(
            "checkout", root, platform="android", package="com.example.x",
            out_dir="app/src/test/java", harness_dir="app/src/test/java")
        assert (android.declared_branches, android.platform_skipped) == (2, 1)
        ios = generate_branch_tests(
            "checkout", root, platform="ios", module="checkout_app",
            out_dir="Tests/Generated", harness_dir="Tests/Generated")
        assert (ios.declared_branches, ios.platform_skipped) == (2, 1)
        # The skip is announced in the emitted file, not silent.
        assert "platform-scoped" in web.test_file.read_text(encoding="utf-8")
