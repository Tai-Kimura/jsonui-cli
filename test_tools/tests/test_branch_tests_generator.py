"""Tests for `jsonui-test generate branch-tests` (P2 branch-contract codegen).

The generator must be mechanical AND fail hard when vocabulary cannot be
bound to real assets (endpoint declarations, mock files, scenario names,
witnesses) — a test that silently weakens is a ritual test.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from jsonui_test_cli.branch_tests import (
    KOTLIN_RUNTIME,
    BranchTestGenerationError,
    _kt_expected,
    _render_expected,
    _swift_expected,
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

    def test_when_declared_route_must_be_reached(self, tmp_path):
        # A branch that ARRANGES api.createOrder="conflict" asserted nothing
        # about the route being called: the implementation could stop before
        # the request and still satisfy the data assertion from a local
        # failure path. Measured in the wild — an error branch certified its
        # 409 handling against a local validation error.
        root = _project(tmp_path, BASIC)
        content = generate_branch_tests("checkout", root).test_file.read_text(
            encoding="utf-8")
        assert 'expect(rec.countFor("createOrder"),' in content
        assert content.count("was never hit") == 1

    def test_reach_failure_names_the_route_and_the_count(self, tmp_path):
        # `expected object, got nil` reads as a defect in the implementation.
        # The route name and the observed count say which of the two happened,
        # so the fix carries its own misattribution guard.
        root = _project(tmp_path, BASIC)
        content = generate_branch_tests("checkout", root).test_file.read_text(
            encoding="utf-8")
        assert ("route 'createOrder' declared in when was never hit "
                "(${rec.countFor(\"createOrder\")} requests)") in content

    def test_reach_is_asserted_before_the_then_entries(self, tmp_path):
        # An unreached route makes every data assertion ambiguous, so the
        # cause is reported first.
        root = _project(tmp_path, BASIC)
        content = generate_branch_tests("checkout", root).test_file.read_text(
            encoding="utf-8")
        assert content.index("was never hit") < content.index('readField("screenState")')

    def test_an_explicit_then_entry_suppresses_the_inferred_one(self, tmp_path):
        # `then` wins wherever it speaks: an inferred assertion must never
        # contradict, or duplicate, a written one.
        for then in ({"api.createOrder": "called"},
                     {"api.createOrder": "not-called"},
                     {"api.createOrder.request": {"id": 1}},
                     {"api": "none"}):
            root = _project(tmp_path / f"p{abs(hash(str(then)))}", _contract(
                [{"when": {"api.createOrder": "conflict"}, "then": then}]))
            content = generate_branch_tests("checkout", root).test_file.read_text(
                encoding="utf-8")
            assert "was never hit" not in content, then

    def test_every_platform_asserts_reach(self, tmp_path):
        for platform, kw, needle in (
            ("web", {}, 'expect(rec.countFor("createOrder"),'),
            ("android", {"package": "com.example.app"},
             'assertTrue("route \'createOrder\' declared in when was never hit'),
            ("ios", {"module": "App"},
             'XCTAssertGreaterThan(rec.countFor("createOrder"), 0, "route'),
        ):
            root = _project(tmp_path / platform, BASIC)
            content = generate_branch_tests(
                "checkout", root, platform=platform, **kw
            ).test_file.read_text(encoding="utf-8")
            assert needle in content, platform
            assert content.count("was never hit") == 1, platform

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
        # Through the runtime helper, not straight at the harness: the
        # helper is what refuses a harness that returns the key itself.
        assert 'resolveString(h, "order_error_generic")' in content

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


_FILE_RESPONSE_SCENARIOS = {
    "success": {"status": 200, "body": {"order": {"id": "o1"}}},
    "conflict": {"status": 409, "body": {"error": {"code": "sold_out"}}},
    # A CSV/PDF export: the file is named, not inlined.
    "csv": {"status": 200, "contentType": "text/csv", "bodyFile": None},
}


class TestFileBackedScenarios:
    """A mock for a CSV/PDF export declares `contentType` + `bodyFile`
    instead of an inline body. The web RouteSpec type admitted only
    `{status, body}`, so the generated test — which cannot be hand-edited —
    failed tsc; Kotlin and Swift compiled but served the literal `null`
    with a JSON content type, which is a response no server sends. All
    three now answer the way the project's own mock server does."""

    def _project(self, tmp_path):
        return _project(tmp_path, BASIC, scenarios=_FILE_RESPONSE_SCENARIOS)

    def test_web_type_admits_the_declared_fields(self, tmp_path):
        report = generate_branch_tests("checkout", self._project(tmp_path))
        runtime = report.runtime_file.read_text(encoding="utf-8")
        spec_type = runtime[runtime.index("export interface RouteSpec"):]
        spec_type = spec_type[:spec_type.index("\n}")]
        for field in ("body?:", "contentType?:", "bodyFile?:", "[key: string]:"):
            assert field in spec_type, field
        # The scenario is embedded verbatim, which is why the type has to
        # admit what mock files actually carry.
        assert '"contentType": "text/csv"' in report.test_file.read_text(encoding="utf-8")

    def test_web_serves_the_declared_content_type_and_an_empty_body(self, tmp_path):
        report = generate_branch_tests("checkout", self._project(tmp_path))
        runtime = report.runtime_file.read_text(encoding="utf-8")
        assert 'sc.contentType === "string" ? sc.contentType : "application/json"' in runtime
        assert "sc.body === undefined ? null : JSON.stringify(sc.body)" in runtime

    def test_kotlin_and_swift_carry_the_content_type(self, tmp_path):
        root = self._project(tmp_path)
        kotlin = generate_branch_tests(
            "checkout", root, platform="android", package="com.example.x",
            out_dir="app/src/test/java", harness_dir="app/src/test/java")
        swift = generate_branch_tests(
            "checkout", root, platform="ios", module="checkout_app",
            out_dir="Tests/Generated", harness_dir="Tests/Generated")
        kt = kotlin.test_file.read_text(encoding="utf-8")
        sw = swift.test_file.read_text(encoding="utf-8")
        assert '"text/csv"' in kt and '"text/csv"' in sw
        # Body-less scenario emits an empty payload, never the string "null".
        assert 'Triple(200, "", "text/csv")' in kt
        assert '(200, "", "text/csv")' in sw
        for runtime, header in (
            (kotlin.runtime_file.read_text(encoding="utf-8"), 'setHeader("Content-Type", sc.third)'),
            (swift.runtime_file.read_text(encoding="utf-8"), 'headerFields: ["Content-Type": contentType]'),
        ):
            assert header in runtime


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


class TestSharedRuntimeNotice:
    """The runtime is one file per output directory, so a release that
    changes its shape leaves every screen that was not regenerated pointing
    at the old one. Regenerating a single screen and then finding 30 broken
    ones is how a consumer learned that the unit is the project."""

    def _generate(self, root, screen):
        import subprocess, sys
        from pathlib import Path
        launcher = Path(__file__).resolve().parents[1] / "jsonui-test"
        return subprocess.run(
            [sys.executable, str(launcher), "generate", "branch-tests", screen],
            capture_output=True, text=True, cwd=root)

    def test_notice_lists_the_files_that_share_the_runtime(self, tmp_path):
        import json
        root = _project(tmp_path, BASIC)
        spec = json.loads(
            (root / "docs/specs/checkout.spec.json").read_text(encoding="utf-8"))
        spec["metadata"]["name"] = "Refunds"
        spec["metadata"]["layoutFile"] = "refunds"
        _write(root / "docs/specs/refunds.spec.json", spec)

        first = self._generate(root, "checkout")
        assert first.returncode == 0, first.stderr
        assert "note:" not in first.stdout  # nothing else shares it yet

        second = self._generate(root, "refunds")
        assert second.returncode == 0, second.stderr
        assert "1 other generated test file(s) share this runtime" in second.stdout
        assert "checkout.branches.test.ts" in second.stdout


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


class TestCollectionEmptinessAssert:
    """`then data.<field>: []` must emit a deep-equality assert that runs.

    Generating an assert and contracting a guarantee are different claims:
    the emitted line has to compile on each driver AND fail when the
    clearing is removed. The Swift and Kotlin renderers already handled
    lists, so this pins the emission rather than changing it — the risk was
    an empty literal that reads as valid and asserts nothing.

    While this was written the web emission was executed under vitest 4.1.9
    against a stand-in harness: with only the scalar witness the same
    regression stayed green, and with `[]` it went red on
    `expected [ { id: 'stale' } ] to deeply equal []`. The Swift shape was
    compiled and run under Swift 6 (Xcode 26.5): `[]` binds as `[Any]` in
    the `Any?` parameter and discriminates a stale list, an empty
    dictionary, and nil. Kotlin was not executed here — no kotlinc on this
    machine — so its emission is pinned by shape only.
    """

    EMPTY = _contract([
        {"when": {"api.createOrder": "conflict"},
         "then": {"data.rows": [], "data.screenState": "load_error"}},
    ])

    def _project_with_rows(self, tmp_path):
        return _project(tmp_path, self.EMPTY)

    def test_web_emits_deep_equality_against_an_empty_array(self, tmp_path):
        root = self._project_with_rows(tmp_path)
        report = generate_branch_tests("checkout", root)
        content = report.test_file.read_text(encoding="utf-8")
        assert 'expect(h.readField("rows")).toEqual([]);' in content
        # The sibling scalar in the same `then` still lands — the exception
        # is additive, not a replacement.
        assert 'expect(h.readField("screenState")).toEqual("load_error");' in content

    def test_android_emits_an_empty_list_not_null(self, tmp_path):
        root = self._project_with_rows(tmp_path)
        report = generate_branch_tests(
            "checkout", root, platform="android", package="com.example.x",
            out_dir="app/src/test/java", harness_dir="app/src/test/java")
        content = report.test_file.read_text(encoding="utf-8")
        assert 'assertFieldEquals(listOf<Any?>(), h.readField("rows"))' in content

    def test_ios_emits_an_empty_collection_literal(self, tmp_path):
        root = self._project_with_rows(tmp_path)
        report = generate_branch_tests(
            "checkout", root, platform="ios", module="checkout_app",
            out_dir="Tests/Generated", harness_dir="Tests/Generated")
        content = report.test_file.read_text(encoding="utf-8")
        assert 'assertFieldEquals([], h.readField("rows"))' in content

    def test_no_platform_drops_the_list_entry_while_keeping_the_scalar(self):
        """The failure mode a per-platform example test can miss.

        A renderer that cannot express a list would most plausibly skip the
        entry and emit the scalar beside it — leaving a green test that
        asserts strictly less than the contract says, on one platform only.
        """
        for render, expected in (
            (_render_expected, ("[]", '"load_error"')),
            (_kt_expected, ("listOf<Any?>()", '"load_error"')),
            (_swift_expected, ("[]", '"load_error"')),
        ):
            assert render([]) == expected[0]
            assert render("load_error") == expected[1]


SEEDABLE = {
    "seedableState": {"canRead": "Bool?", "selectedIds": "[Int]"},
    "methods": {"onConfirmTap": {"branches": [
        {"when": {"state.canRead": False}, "then": {"api": "none"}},
        {"when": {"state.canRead": True, "api.createOrder": "success"},
         "then": {"data.screenState": "ok"}},
    ]}},
}


class TestSeedableState:
    """ViewModel-internal state a branch may arrange.

    The arrange surface reached uiVariables only, so a branch gated on
    private state — a stale-fetch guard, a selection id, an ordered
    selection — could not be arranged from the contract. Three independent
    cases in one consumer is what opened this; the reporter had ruled it
    out until a third arrived.

    The declaration is not only vocabulary. The harness applies data keys
    leniently on purpose (a data-only field assigned onto the ViewModel
    invents a property that then shadows the store), so the writer cannot
    tell "should be on the VM" from "belongs to the store". These names
    carry exactly that bit, which is what makes a strict write checkable.
    """

    def test_seeded_names_are_written_through_the_checked_path(self, tmp_path):
        root = _project(tmp_path, SEEDABLE)
        report = generate_branch_tests("checkout", root)
        content = report.test_file.read_text(encoding="utf-8")
        assert 'seedState(h, {"canRead": false})' in content
        assert 'seedState(h, {"canRead": true})' in content

    def test_seeded_names_do_not_go_through_setState(self, tmp_path):
        # The split is the point: setState stays lenient for data keys, so
        # routing an internal name through it would drop it in silence.
        #
        # Asserted on the emitted CALLS, not on a text split around the word
        # "seedState": the runtime import names it unconditionally, so a
        # split on the bare word matched the file header and the assertion
        # held whatever the generator emitted. A red-check caught it.
        root = _project(tmp_path, SEEDABLE)
        content = generate_branch_tests(
            "checkout", root).test_file.read_text(encoding="utf-8")
        set_state_calls = [ln for ln in content.splitlines() if "h.setState(" in ln]
        assert set_state_calls == []
        seed_calls = [ln.strip() for ln in content.splitlines() if "seedState(h," in ln]
        # one per branch, both naming the seeded field
        assert len(seed_calls) == 2
        assert all("canRead" in call for call in seed_calls)

    def test_the_runtime_helper_is_imported(self, tmp_path):
        root = _project(tmp_path, SEEDABLE)
        content = generate_branch_tests(
            "checkout", root).test_file.read_text(encoding="utf-8")
        assert "seedState" in content.split("from \"./jsonui-branch-runtime\"")[0]

    def test_baseline_and_witnesses_split_the_same_way(self, tmp_path):
        bc = {
            "seedableState": {"canRead": "Bool?"},
            "conditions": {
                "readable": {
                    "description": "permission has resolved",
                    "witness_true": {"state.canRead": True},
                    "witness_false": {"state.canRead": False},
                },
            },
            "methods": {"onConfirmTap": {
                "baseline": {"isAgreed": True, "state.canRead": None},
                "branches": [
                    {"when": {"cond": "readable", "api.createOrder": "success"},
                     "then": {"data.screenState": "ok"}},
                    {"when": {"cond": "!readable"}, "then": {"api": "none"}},
                ]}},
        }
        root = _project(tmp_path, bc)
        content = generate_branch_tests(
            "checkout", root).test_file.read_text(encoding="utf-8")
        # baseline data key on the lenient path, baseline seed on the strict
        # one, and the witness overriding the baseline seed (later wins).
        assert 'h.setState({"isAgreed": true})' in content
        assert 'seedState(h, {"canRead": true})' in content
        assert 'seedState(h, {"canRead": false})' in content

    def test_a_spec_without_seedable_state_is_unchanged(self, tmp_path):
        # (d): the section is opt-in. Nothing about an existing spec moves.
        root = _project(tmp_path, BASIC)
        content = generate_branch_tests(
            "checkout", root).test_file.read_text(encoding="utf-8")
        assert "seedState(h," not in content

    def test_android_and_ios_emit_the_same_seed(self, tmp_path):
        # Parity: a contract that arranges internal state has to arrange it
        # on every platform that renders the contract, or the same branch
        # means different things per driver.
        root = _project(tmp_path, SEEDABLE)
        android = generate_branch_tests(
            "checkout", root, platform="android", package="com.example.checkout",
            out_dir="app/src/test/java", harness_dir="app/src/test/java",
        ).test_file.read_text(encoding="utf-8")
        ios = generate_branch_tests(
            "checkout", root, platform="ios", module="CheckoutApp",
        ).test_file.read_text(encoding="utf-8")
        assert 'seedState(h, mapOf<String, Any?>("canRead" to false))' in android
        assert 'seedState(h, ["canRead": false])' in ios

    def test_the_seed_reads_the_view_model_not_read_field(self, tmp_path):
        """The decision an execution arm caught, pinned here.

        The first version read the value back through `readField`, which
        falls back to the data store — and a harness hands the same object
        to both, so a name the ViewModel never received still read back
        correctly and the check passed over a branch that was never
        arranged. Measured with vitest on a generated project: the stale
        arm went green. Reading the ViewModel directly also separates "no
        such field" from "the harness did not write it", which are
        different repairs.
        """
        root = _project(tmp_path, SEEDABLE)
        runtime = generate_branch_tests(
            "checkout", root).runtime_file.read_text(encoding="utf-8")
        body = runtime.split("export function seedState")[1].split("\n}\n")[0]
        assert "h.vm" in body
        # the CALL, not the word: the comment above it names readField as
        # the thing deliberately not used
        assert "readField(" not in body
        # two causes, two repairs, each named
        assert "has no" in body and "such field" in body
        assert "did not take" in body


# A contract that references no API operation at all: every branch is decided
# by data alone. Legitimate — a screen can validate input or track selection
# without touching the network — and the only shape that reaches an empty
# routes list.
NO_ROUTES = _contract([
    {"when": {"data.isAgreed": False}, "then": {"api": "none"}},
    {"when": {"data.isAgreed": True}, "then": {"data.screenState": "ready"}},
])


class TestEmptyRouteListStaysCompilable:
    """A screen with no routes must still emit a typed empty list.

    Kotlin cannot infer `T` from `listOf()`, and a Kotlin test source set
    compiles as one unit — so a single screen with no API routes took every
    other screen's branch tests down with it (a reporting project: 16
    screens generated, 2 uncompilable, the remaining 14 unable to run).
    Swift and TypeScript already annotated; Android was the asymmetric
    emitter.

    The negative test has to use a zero-route screen. Any contract that
    references one operation infers `T` from its elements and passes on the
    broken generator too.
    """

def _routeless_project(tmp_path: Path) -> Path:
    """A screen whose spec declares no repository endpoints at all.

    `_project` cannot express this: routes are collected from the spec's
    repository `endpoint` declarations, not from what the contract's `when`
    clauses reference. Reusing it here produced three routes and the
    precondition assert below caught it — the same proxy-measure mistake a
    consumer lane made reading its own corpus ("no api. key in when").
    """
    root = tmp_path / "proj"
    root.mkdir(parents=True, exist_ok=True)
    _write(root / "jui.config.json", {"spec_directory": "docs/specs"})
    _write(root / "docs/specs/checkout.spec.json", {
        "type": "screen_spec",
        "version": "1.0",
        "metadata": {"name": "Checkout", "displayName": "Checkout",
                     "description": "d", "layoutFile": "checkout"},
        "structure": {"components": [], "layout": {}},
        "dataFlow": {
            "viewModel": {"methods": [{"name": "onConfirmTap"}], "vars": []},
            "repositories": [],
        },
        "stateManagement": {"uiVariables": []},
        "branchContracts": NO_ROUTES,
    })
    return root


class TestEmptyRouteListStaysCompilableFixture:
    def test_the_fixture_really_produces_no_routes(self, tmp_path):
        # Assert the precondition rather than trusting the contract's shape:
        # routes are collected from more than `when` (a lane misread its own
        # corpus by using "no api. key in when" as a proxy and got a false
        # positive). If this ever gains a route the tests below would pass
        # against the defect they exist to catch.
        root = _routeless_project(tmp_path)
        report = generate_branch_tests("checkout", root, platform="android",
                                       package="com.example.x")
        assert report.routes == []

    def test_android_annotates_the_empty_list(self, tmp_path):
        root = _routeless_project(tmp_path)
        report = generate_branch_tests("checkout", root, platform="android",
                                       package="com.example.x")
        content = report.test_file.read_text(encoding="utf-8")
        assert "private val routes: List<RouteSpec> = listOf(" in content
        assert "private val routes = listOf(" not in content

    def test_ios_and_web_are_annotated_too(self, tmp_path):
        # The fix made the three emitters symmetric; assert the other two so a
        # future edit cannot restore the asymmetry from the other side.
        root = _routeless_project(tmp_path)
        ios = generate_branch_tests("checkout", root, platform="ios",
                                    module="checkout_app")
        assert "private let routes: [RouteSpec] = [" in \
            ios.test_file.read_text(encoding="utf-8")
        web = generate_branch_tests("checkout", root)
        assert "const ROUTES: RouteSpec[] = [" in \
            web.test_file.read_text(encoding="utf-8")

    def test_a_populated_list_is_annotated_as_well(self, tmp_path):
        # No branch on emptiness: "only when empty" would leave the two forms
        # to drift, and the annotation costs nothing when elements exist.
        root = _project(tmp_path, BASIC)
        report = generate_branch_tests("checkout", root, platform="android",
                                       package="com.example.x")
        content = report.test_file.read_text(encoding="utf-8")
        assert "private val routes: List<RouteSpec> = listOf(" in content
        assert report.routes  # the arm that passes on the broken generator


class TestEmittedRuntimesHaveBalancedStringLiterals:
    """Every emitted runtime must have balanced quotes, line by line.

    A diagnostic added to the Kotlin runtime was written inside a NON-raw
    Python triple-quoted string, so its `\\"` collapsed to `"` before it was
    ever emitted:

        "resolveString("" + key + "") returned "" + resolved + "", which " +

    The Kotlin file did not compile, which took every Android branch test in
    the project down with it — 8 screens, 17 tests, `0 tests` run.

    `--check` stayed green throughout: it compares the copy on disk to what
    the generator produces, and both were equally broken. "The generated
    tests are current" and "the generated tests compile" are different
    claims, and only the first had a gate. Second instance of that pair in
    one day; the first was an untyped empty `listOf()`.

    Comparing the emitted text to an expected string would not have caught
    it either — the expectation would have been written from the same
    source and collapsed the same way. This asserts a property the escaping
    has to satisfy instead: strip the escaped quotes, and what remains must
    pair up.
    """

    def _runtimes(self, tmp_path):
        out = {}
        for platform, kwargs in (("android", {"package": "com.example.x"}),
                                 ("ios", {"module": "app"}),
                                 ("web", {})):
            root = _project(tmp_path / platform, BASIC)
            report = generate_branch_tests("checkout", root,
                                           platform=platform, **kwargs)
            out[platform] = report.runtime_file.read_text(encoding="utf-8")
        return out

    @staticmethod
    def _unescaped_quotes(code: str) -> int:
        """Count the quotes a compiler would see as opening or closing one.

        The first version stripped `\\"` and counted what was left, which
        reads a line ending in an escaped BACKSLASH as unbalanced: in
        `out.append("\\\\")` the last backslash of the pair is followed by
        the closing quote, so the naive strip removes a `\\"` that is not
        there and leaves an odd count.

        That surfaced the day a `quotedValue` helper — whose whole job is
        emitting backslashes — was added to the Kotlin runtime, on a line
        the Kotlin compiler accepts (measured: compiled and run). A net
        that reports correct output is a net people start ignoring, so the
        escape is tracked rather than pattern-matched.
        """
        count = 0
        index = 0
        in_double = False
        while index < len(code):
            char = code[index]
            if char == "\\":
                index += 2
                continue
            if char == '"':
                count += 1
                in_double = not in_double
            elif char == "'" and not in_double:
                # A Kotlin CHARACTER literal, or a TypeScript string. Either
                # way the quote inside `'"'` is not a delimiter, and counting
                # it reported the `when (ch)` arm of a helper the compiler
                # accepts. Skip to the close; an unclosed one falls out of
                # the loop and is left to the compiler to describe.
                closing = index + 1
                while closing < len(code):
                    if code[closing] == "\\":
                        closing += 2
                        continue
                    if code[closing] == "'":
                        break
                    closing += 1
                index = closing + 1
                continue
            index += 1
        return count

    @pytest.mark.parametrize("line,odd", [
        # What it catches: a literal left OPEN. `\\"` collapsing to `"`
        # inside a call is the shape.
        ('out.append("\\")', True),
        # What it must not catch — every one of these compiles, and the
        # Kotlin ones were compiled and run. Each was reported by an
        # earlier version of the counter.
        ('out.append("\\"")', False),
        ('return out.append("\\"").toString()', False),
        ('''      '"' -> out.append("\\\\\\"")''', False),
        ('      "resolveString(" + quotedValue(key) + ") returned " +', False),
    ])
    def test_the_counter_catches_an_open_literal_and_nothing_else(
            self, line, odd):
        """The counter was loosened twice — escape-aware, then char-literal
        aware — and each loosening is a chance to stop catching anything.

        MEASURED WHILE WRITING THIS, and it corrects the premise the test
        started from: the `f43b8fb1` line is BALANCED. Ten quotes, even
        under the original heuristic and under this one. So this counter
        never caught that regression and was never going to; the named
        assertion below (`resolveString(""` is absent) is what catches it.
        Two nets, two different fish, and it was worth finding out which
        was which before loosening one of them.
        """
        assert (self._unescaped_quotes(line) % 2 == 1) is odd, line

    @pytest.mark.parametrize("platform", ["android", "ios", "web"])
    def test_no_line_has_an_odd_number_of_unescaped_quotes(
            self, tmp_path, platform):
        text = self._runtimes(tmp_path)[platform]
        offenders = []
        for n, line in enumerate(text.splitlines(), 1):
            code = line.split("//")[0] if "//" in line else line
            if code.lstrip().startswith(("*", "/*")):
                continue
            if self._unescaped_quotes(code) % 2:
                offenders.append(f"{platform} runtime line {n}: {line.strip()}")
        assert offenders == [], "\n".join(offenders)

    def test_the_kotlin_diagnostic_escapes_its_quotes(self, tmp_path):
        # The specific regression, named. The property test above is the net;
        # this says which fish was caught, so a future edit that reintroduces
        # it fails with the reason rather than with a line number.
        #
        # Re-aimed when the quotes around the values moved out of the
        # message literal and into `quotedValue`: the old needle
        # (`resolveString(\\"`) no longer exists, and asserting it would have
        # to be deleted rather than moved. The collapse it was watching for
        # can still happen — the helper is the densest escaping in any of
        # the three runtimes — so the needle follows it there.
        text = self._runtimes(tmp_path)["android"]
        assert 'out.append("\\\\\\"")' in text, "the escaped-quote arm collapsed"
        assert 'out.append("\\\\\\\\")' in text, "the escaped-backslash arm collapsed"
        # `resolveString(""` is the f43b8fb1 line itself. A collapsed pair
        # elsewhere is what the counter above is for; a negative needle on
        # `out.append("\\"")` was tried and removed, because the helper
        # legitimately appends one closing quote with exactly that spelling.
        assert 'resolveString(""' not in text


class TestEmittedRuntimesDoNotQuoteResolverCalls:
    """A diagnostic must not spell a resolver call, and must not carry a
    Python comment into the emitted language.

    Two failures from one release, both of the same shape — a construct
    from the generator's language ending up in the generated one:

    - The web diagnostic said `StringManager.getString(TABLE[key])` to
      teach the fix. `jui lint-strings` scans for `getString(<expression>)`
      and cannot tell a real reference from one quoted inside a message, so
      it reported an undeclared dynamic ref and exited 2 on every project
      with `lint.stringsUsage`. Generated files cannot be hand-edited and
      the raw-literal allowlist does not cover dynamic refs, so the
      consumer had no way out: emit and lint is red, do not emit and
      `--check` is red. Comments are blanked for that scan (v1.6.16);
      string literals deliberately are not, because interpolation inside
      one IS a reference site. A message that quotes code is a third case.
    - Writing the explanation as a `#` comment inside the emitted template
      put Python comments into the TypeScript. Committed and caught in the
      same minute.

    Kotlin and Swift already worded it without a call, so the fix also
    makes the three agree.
    """

    def _runtime(self, tmp_path, platform, **kw):
        root = _project(tmp_path / platform, BASIC)
        return generate_branch_tests(
            "checkout", root, platform=platform, **kw
        ).runtime_file.read_text(encoding="utf-8")

    @pytest.mark.parametrize("platform,kw", [
        ("web", {}), ("android", {"package": "com.example.x"}),
        ("ios", {"module": "app"}),
    ])
    def test_no_resolver_call_is_spelled_in_a_diagnostic(
            self, tmp_path, platform, kw):
        text = self._runtime(tmp_path, platform, **kw)
        assert "getString(" not in text, (
            "a quoted resolver call reads as a real reference to the "
            "strings-usage scan")

    @pytest.mark.parametrize("platform,kw", [
        ("web", {}), ("android", {"package": "com.example.x"}),
        ("ios", {"module": "app"}),
    ])
    def test_no_python_comment_survives_into_the_emitted_language(
            self, tmp_path, platform, kw):
        text = self._runtime(tmp_path, platform, **kw)
        # `# ` with the space, not a bare `#`: Swift has `#selector` and
        # `#available` as real syntax, and the first version of this
        # assertion reported one of them. The predicate was the defect, not
        # the emitted code — third time today that a check's own claim was
        # the thing that was wrong.
        leaked = [l for l in text.splitlines() if l.strip().startswith("# ")]
        assert leaked == [], "\n".join(leaked)


class TestEmittedRuntimesConcatenateTheirStrings:
    """Two string literals on consecutive lines need an operator between them.

    Rewording the web diagnostic dropped the trailing `+`, so the emitted
    TypeScript held two adjacent string literals inside a call:

        "…the field holds resolved text — return the string manager's lookup "
        "of the full key, not the key itself."

    Python concatenates adjacent literals, so the generator's own source was
    fine and every string-comparison test agreed with it. TypeScript does
    not: `tsc` reported TS1005, twelve test files failed to collect, the
    unit suite went 130 → 64, and `next build` stopped type-checking.

    That fix was for a lint failure in the SAME diagnostic, made minutes
    after writing "the only tool that can say whether output is valid in its
    own language is a compiler". This is the property standing in for the
    compiler until the CI step exists — narrower, but it covers exactly the
    way Python's concatenation rule leaks into a language that has none.
    """

    def _runtime(self, tmp_path, platform, **kw):
        root = _project(tmp_path / platform, BASIC)
        return generate_branch_tests(
            "checkout", root, platform=platform, **kw
        ).runtime_file.read_text(encoding="utf-8")

    @pytest.mark.parametrize("platform,kw", [
        ("web", {}), ("android", {"package": "com.example.x"}),
        ("ios", {"module": "app"}),
    ])
    def test_no_two_string_literals_sit_adjacent_without_an_operator(
            self, tmp_path, platform, kw):
        lines = self._runtime(tmp_path, platform, **kw).splitlines()
        offenders = []
        for n, (a, b) in enumerate(zip(lines, lines[1:]), 1):
            first, second = a.strip(), b.strip()
            if first.lstrip().startswith(("*", "//", "/*")):
                continue
            # a line that ENDS a literal, followed by one that OPENS a
            # literal, with nothing joining them
            if first.endswith('"') and second.startswith('"'):
                offenders.append(f"{platform} line {n}: {first}\n    then: {second}")
        assert offenders == [], "\n".join(offenders)


class TestResolveStringRejectsAnEmptyReturn:
    """Returning nothing is a failure the guard used to pass.

    The guard rejected a key and a `<prefix>_<key>` identifier. It let `""`
    through, and a consumer measured that: a harness whose table lookup
    misses returns an empty string, the check says nothing, and the
    assertion compares the field to `""` — which passes whenever the field
    is also empty.

    Worse, the comment beside the guard cited "an empty table, so
    `resolveString` was never called" as the motivation. That is about
    dormancy and is true, but it reads as a claim that empty tables are
    caught. They are only caught when the harness returns the key; a
    harness that returns nothing was still green.

    Kotlin makes it easy to miss: `resolved.all { … }` on an empty string
    is vacuously true, so `identifier` was true and only the suffix test
    saved it from a wrong message.

    One condition and one message for both, not two blocks: a key and
    nothing are the same failure — the table did not resolve — and every
    extra emitted block is more surface in a file this release has already
    broken three times.
    """

    def _runtime(self, tmp_path, platform, **kw):
        root = _project(tmp_path / platform, BASIC)
        return generate_branch_tests(
            "checkout", root, platform=platform, **kw
        ).runtime_file.read_text(encoding="utf-8")

    @pytest.mark.parametrize("platform,kw,empty_test", [
        ("web", {}, "!resolved"),
        ("android", {"package": "com.example.x"}, "resolved.isEmpty()"),
        # The guard line itself, not the bare call: `!resolved.isEmpty`
        # already appears in the `identifier` line above it, so matching the
        # call alone stayed true with the guard deleted. Measured — the
        # mutation killed web and android and left ios green.
        ("ios", {"module": "app"}, "if resolved.isEmpty || resolved == key"),
    ])
    def test_the_guard_tests_for_an_empty_return(
            self, tmp_path, platform, kw, empty_test):
        text = self._runtime(tmp_path, platform, **kw)
        assert empty_test in text

    @pytest.mark.parametrize("platform,kw", [
        ("web", {}), ("android", {"package": "com.example.x"}),
        ("ios", {"module": "app"}),
    ])
    def test_the_message_covers_both_failures(self, tmp_path, platform, kw):
        # It no longer says "is a strings KEY", which was wrong for the
        # empty case — the diagnostic has to be true of what it fired on.
        # Compare the EFFECTIVE message, not the source lines. Each runtime
        # splits the sentence across concatenated literals at a different
        # point, so a phrase that is contiguous in one is cut in another —
        # the first version of this assertion reported Swift for a message
        # that was correct. Fourth time today the predicate was the defect.
        text = self._runtime(tmp_path, platform, **kw)
        joined = re.sub(r'"\s*\+\s*\n\s*"', "", text)
        assert "is not the text that key names" in joined
        assert "A key, or nothing, means the table did not resolve" in joined
        assert "is a strings KEY" not in joined


class TestCoerceUsesKotlinsOwnClassSpellings:
    """`coerce` matches Class objects, and how it spells them is visible.

    The Java boxed literals (`java.lang.Long::class.java`) draw "This class
    is not recommended for use in Kotlin" once per type, in every consumer
    that generates Android branch tests — and the file is `@generated`, so
    nobody downstream can silence them. Measured on Kotlin 2.4.10: the
    emitted text produced 4 warnings before this change and 0 after, and the
    two spellings select the same Class objects (identity true for all four
    types, and `coerce` answered identically across 104 (type, value) pairs
    covering primitive, boxed, unrelated and null inputs).

    Both halves are asserted because either alone would pass a broken fix: a
    file with no boxed literals could have dropped the primitive branch, and
    one with both spellings would still warn.
    """

    RUNTIME = KOTLIN_RUNTIME % {"package": "com.example.x"}

    @pytest.mark.parametrize("boxed", [
        "java.lang.Long::class.java", "java.lang.Integer::class.java",
        "java.lang.Double::class.java", "java.lang.Float::class.java",
    ])
    def test_no_boxed_class_literal_is_emitted_as_code(self, boxed):
        code = "\n".join(
            line for line in self.RUNTIME.splitlines()
            if not line.lstrip().startswith("//")
        )
        assert boxed not in code

    @pytest.mark.parametrize("kotlin_type", ["Long", "Int", "Double", "Float"])
    def test_both_class_objects_are_still_matched(self, kotlin_type):
        # javaPrimitiveType is the same Class as java.lang.Long.TYPE and
        # javaObjectType the same as the boxed literal, so dropping either
        # would stop matching inputs coerce used to convert.
        assert f"{kotlin_type}::class.javaPrimitiveType" in self.RUNTIME
        assert f"{kotlin_type}::class.javaObjectType" in self.RUNTIME
