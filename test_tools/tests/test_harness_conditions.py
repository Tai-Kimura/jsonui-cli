"""Harness conditions (design v4.11/v4.12, P2d) — declared, checked, arranged, run.

A ViewModel whose calls depend on something outside it (a signed-in session)
could not be arranged by a generated test: the harness has no way to put that
precondition in, so the op it gates could be closed neither by a row nor by
an exclusion. The app contracts spec now declares such preconditions
(`harnessConditions`), a row names one in its `when` (`harness.<name>`), and
every generated test calls the consumer's `arrangeCondition(name, value)` for
EVERY declared condition — the row's value or the default — after the mock
goes in and before the harness is built.

The red-checks this file carries:
  xxvii (synthetic)  a row naming `harness.session: "present"` reaches the op
                     the session gates, and goes green; the same row without
                     it is red with "route ... declared in when was never hit"
  xxviii             an undeclared name, a value outside `values`, a row with
                     no app declaration — each a declaration error naming the
                     row, in the generator and in coverage
  xxix (in-suite)    an app without harnessConditions: no line of any of it
                     (the byte-for-byte comparison is measured on consumer
                     trees, which this suite does not have)
  xxx                a row that names no condition still arranges every one,
                     with the default

The web face is RUN (the act-window arms' node + vitest stand-in). The
Kotlin factory the generator emits is extracted, compiled against the
runtime's own `runBranchTest` signature and run for its order; the Swift test
type-checks against XCTest with the hook skeleton beside it.
"""
from __future__ import annotations

import copy
import json
import re
import subprocess
from pathlib import Path

import pytest

from jsonui_test_cli import branch_tests as bt
from jsonui_test_cli.contract_declarations import (
    HarnessCondition, arranged_conditions, check_condition_uses, parse_declarations)
from tests import _toolchain as tc
from tests.test_branch_act_window_and_bound import (
    _HOOKS, _REGISTER, _VITEST, _mock)
from tests import test_contracts_coverage as tcc


def _app(conditions=None, **extra) -> dict:
    app = {"type": "app_contracts_spec", "version": "1.0",
           "metadata": {"name": "app", "description": "d"},
           "unitContracts": [{"target": "ApiClient", "cases": [{"name": "c"}]}]}
    if conditions is not None:
        app["harnessConditions"] = conditions
    app.update(extra)
    return app


SESSION = {"session": {"values": ["absent", "present"], "default": "absent",
                       "reason": "whether a user is signed in — the VM reads it, no mock can"}}
TWO = {**SESSION, "clock": {"values": ["day", "night"], "default": "day",
                            "reason": "the hour the VM reads"}}


def _paths(declarations) -> list:
    return [e.path for e in declarations.errors]


# ------------------------------------------------------------ the parser ---

class TestTheAppDeclaration:
    def test_a_well_formed_declaration_is_read_in_order(self):
        d = parse_declarations(_app(TWO))
        assert d.errors == []
        assert [(c.name, c.values, c.default) for c in d.harness_conditions] == [
            ("session", ("absent", "present"), "absent"), ("clock", ("day", "night"), "day")]

    def test_absent_is_none_not_empty(self):
        assert parse_declarations(_app()).harness_conditions is None

    @pytest.mark.parametrize("entry, where", [
        ({"values": ["only"], "default": "only", "reason": "r"}, "harnessConditions.session.values"),
        ({"values": ["a", "a"], "default": "a", "reason": "r"}, "harnessConditions.session.values[1]"),
        ({"values": ["a", ""], "default": "a", "reason": "r"}, "harnessConditions.session.values[1]"),
        ({"values": ["a", "b"], "reason": "r"}, "harnessConditions.session.default"),
        ({"values": ["a", "b"], "default": "c", "reason": "r"}, "harnessConditions.session.default"),
        ({"values": ["a", "b"], "default": "a"}, "harnessConditions.session.reason"),
        ({"values": ["a", "b"], "default": "a", "reason": "r", "extra": 1},
         "harnessConditions.session.extra"),
    ])
    def test_each_malformed_field_is_named(self, entry, where):
        d = parse_declarations(_app({"session": entry}))
        assert where in _paths(d), _paths(d)
        assert d.harness_conditions == []

    def test_a_name_that_cannot_be_a_when_key_is_refused(self):
        d = parse_declarations(_app({"signed-in": SESSION["session"]}))
        assert "harnessConditions.signed-in" in _paths(d)

    def test_an_empty_or_non_object_block_is_refused(self):
        assert "harnessConditions" in _paths(parse_declarations(_app({})))
        assert "harnessConditions" in _paths(parse_declarations(_app(["session"])))

    def test_on_a_screen_it_is_refused(self):
        d = parse_declarations({"type": "screen_spec", "harnessConditions": SESSION})
        assert "harnessConditions" in _paths(d)


def _screen_with_rows(*whens) -> dict:
    return {"type": "screen_spec", "branchContracts": {"methods": {"load": {
        "branches": [{"when": w, "then": {"data.x": 1}} for w in whens]}}}}


class TestTheRowsAgainstTheDeclaration:
    """xxviii: every error names the row and the key."""

    def _uses(self, *whens):
        return parse_declarations(_screen_with_rows(*whens)).condition_uses

    def test_a_declared_name_and_value_is_no_error(self):
        conditions = parse_declarations(_app(SESSION)).harness_conditions
        assert check_condition_uses(self._uses({"harness.session": "present"}), conditions) == []

    def test_an_undeclared_name(self):
        conditions = parse_declarations(_app(SESSION)).harness_conditions
        errors = check_condition_uses(self._uses({}, {"harness.sesion": "present"}), conditions,
                                      "app_contracts.spec.json")
        assert [e.path for e in errors] == [
            "branchContracts.methods.load.branches[1].when.harness.sesion"]
        assert "'session'" in errors[0].message and "app_contracts.spec.json" in errors[0].message

    def test_a_value_outside_values(self):
        conditions = parse_declarations(_app(SESSION)).harness_conditions
        errors = check_condition_uses(self._uses({"harness.session": "expired"}), conditions)
        assert [e.path for e in errors] == ["branchContracts.methods.load.branches[0].when.harness.session"]
        assert "'absent', 'present'" in errors[0].message

    def test_a_non_string_value_is_outside_values(self):
        conditions = parse_declarations(_app(SESSION)).harness_conditions
        assert len(check_condition_uses(self._uses({"harness.session": True}), conditions)) == 1

    def test_no_app_declaration_at_all(self):
        errors = check_condition_uses(self._uses({"harness.session": "present"}), None)
        assert len(errors) == 1 and "no app_contracts_spec declares harnessConditions" in errors[0].message

    def test_cond_is_not_a_harness_condition(self):
        # The witness reference keeps its own meaning; only `harness.` is read.
        assert self._uses({"cond": "signedIn"}) == []


class TestEveryConditionIsArranged:
    """xxx, as data: every declared condition, the row's value or the default."""

    CONDITIONS = [HarnessCondition("session", ("absent", "present"), "absent", "r"),
                  HarnessCondition("clock", ("day", "night"), "day", "r")]

    def test_a_row_naming_none_gets_every_default(self):
        assert arranged_conditions(self.CONDITIONS, {}) == [("session", "absent"), ("clock", "day")]

    def test_a_row_naming_one_gets_its_value_and_the_other_default(self):
        assert arranged_conditions(self.CONDITIONS, {"harness.clock": "night"}) == [
            ("session", "absent"), ("clock", "night")]

    def test_an_app_without_conditions_arranges_nothing(self):
        assert arranged_conditions(None, {"harness.session": "present"}) == []
        assert arranged_conditions([], {}) == []


# --------------------------------------------------- the generated tests ---

def _summary(root: Path, *, conditions=SESSION, rows=None) -> Path:
    spec_dir = root / "docs/screens/json"
    spec_dir.mkdir(parents=True)
    (root / "jui.config.json").write_text(json.dumps(
        {"spec_directory": "docs/screens/json", "platforms": ["web", "android", "ios"]}),
        encoding="utf-8")
    spec = {
        "type": "screen_spec",
        "metadata": {"name": "summary"},
        "dataFlow": {
            "viewModel": {"methods": [{"name": "loadSummary"}]},
            "repositories": [{"name": "OrderRepository", "methods": [
                {"name": "getOrder", "endpoint": "GET /api/order"},
                {"name": "getAccount", "endpoint": "GET /api/account"},
            ]}],
        },
        "branchContracts": {"methods": {"loadSummary": {"branches": rows if rows is not None else [
            # 1: signed in — the session gates getAccount, and the hook puts it in.
            {"when": {"api.getOrder": "default", "api.getAccount": "default",
                      "harness.session": "present"},
             "then": {"data.status": "ready", "data.me": "loaded"}},
            # 2: names no condition — arranged with the default, "absent",
            #    even though row 1 left the session signed in.
            {"when": {"api.getOrder": "default"},
             "then": {"data.status": "ready", "api.getAccount": "not-called"}},
        ]}}},
    }
    (spec_dir / "summary.spec.json").write_text(json.dumps(spec), encoding="utf-8")
    if conditions is not None:
        (spec_dir / "app_contracts.spec.json").write_text(
            json.dumps(_app(conditions)), encoding="utf-8")
    _mock(root, "order", "GET", "/api/order", "getOrder",
          {"default": {"status": 200, "body": {"id": 1}}})
    _mock(root, "account", "GET", "/api/account", "getAccount",
          {"default": {"status": 200, "body": {"name": "loaded"}}})
    return root


_SESSION_STATE = '''export const session = { present: false };
'''

#: The consumer's hook: what production would give the ViewModel to observe.
_CONDITIONS_HOOK = '''import { session } from "./session-state";
export const arranged: string[] = [];
export function arrangeCondition(name: string, value: string): void {
  arranged.push(`${name}=${value}`);
  if (name === "session") { session.present = value === "present"; return; }
  throw new Error(`unknown ${name}=${value}`);
}
'''

#: The ViewModel reads the session ONCE, when it is built — so an arrangement
#: made after construction is one it never sees.
_SUMMARY_HARNESS = '''import { applyDeclaredKeys } from "../generated/jsonui-branch-runtime";
import { session } from "./session-state";

class SummaryViewModel {
  status = "idle";
  me = "";
  signedIn: boolean;
  constructor() { this.signedIn = session.present; }
  async loadSummary() {
    await fetch("https://api.test/api/order");
    if (this.signedIn) {
      const r = await fetch("https://api.test/api/account");
      this.me = (await r.json()).name;
    }
    this.status = "ready";
  }
}

export function createHarness() {
  const vm = new SummaryViewModel();
  return {
    vm,
    setState(state: Record<string, unknown>) { applyDeclaredKeys(vm, state); },
    readField(name: string) { return (vm as any)[name]; },
    expectTransition(_d: string) {},
    resolveString(key: string) { return key; },
  };
}
'''

_SUMMARY_RUNNER = '''import { run } from "vitest";
await import("./tests/unit/generated/summary.branches.test.ts");
await run();
'''


def _generate(root: Path, platform: str = "web", **kw):
    if platform == "android":
        kw = {"package": "com.example.app", "out_dir": "app/src/test/java",
              "harness_dir": "app/src/test/java", **kw}
    if platform == "ios":
        kw = {"module": "summary_app", "out_dir": "Tests/Generated",
              "harness_dir": "Tests/Generated", **kw}
    return bt.generate_branch_tests("summary", root, platform=platform,
                                    config_platforms=["web", "android", "ios"], **kw)


def _run_summary(root: Path, *, hook: str | None = _CONDITIONS_HOOK,
                 edit_test=None) -> dict[str, tuple[bool, str]]:
    report = _generate(root)
    harness_dir = root / "tests/unit/branch-harness"
    (harness_dir / "summary.ts").write_text(_SUMMARY_HARNESS, encoding="utf-8")
    (harness_dir / "session-state.ts").write_text(_SESSION_STATE, encoding="utf-8")
    if hook is not None:
        (harness_dir / "branch-conditions.ts").write_text(hook, encoding="utf-8")
    if edit_test is not None:
        text = report.test_file.read_text(encoding="utf-8")
        report.test_file.write_text(edit_test(text), encoding="utf-8")
    vitest = root / "node_modules/vitest"
    vitest.mkdir(parents=True, exist_ok=True)
    (vitest / "package.json").write_text(
        '{"name": "vitest", "type": "module", "main": "index.js"}', encoding="utf-8")
    (vitest / "index.js").write_text(_VITEST, encoding="utf-8")
    (root / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (root / "hooks.mjs").write_text(_HOOKS, encoding="utf-8")
    (root / "register.mjs").write_text(_REGISTER, encoding="utf-8")
    (root / "runner.mjs").write_text(_SUMMARY_RUNNER, encoding="utf-8")
    run = subprocess.run(
        ["node", "--experimental-strip-types", "--import", "./register.mjs", "runner.mjs"],
        cwd=root, capture_output=True, text=True, timeout=120)
    rows = {}
    for line in run.stdout.splitlines():
        m = re.match(r"^(PASS|FAIL) .*branch (\d+):.*?(?: :: (.*))?$", line)
        if m:
            rows[int(m.group(2))] = (m.group(1) == "PASS", m.group(3) or "")
    assert rows, f"the generated test produced no rows:\n{run.stdout}\n{run.stderr[:4000]}"
    return rows


class TestTheWebTestRuns:
    def test_xxvii_a_row_naming_the_session_reaches_the_op_it_gates(self, tmp_path):
        tc.tool("node")
        rows = _run_summary(_summary(tmp_path))
        assert rows == {1: (True, ""), 2: (True, "")}, rows

    def test_xxvii_control_the_same_row_without_the_condition_never_hits_fetch_me(self, tmp_path):
        tc.tool("node")
        rows_spec = [
            {"when": {"api.getOrder": "default", "api.getAccount": "default"},
             "then": {"data.status": "ready", "data.me": "loaded"}}]
        rows = _run_summary(_summary(tmp_path, rows=rows_spec))
        ok, why = rows[1]
        assert not ok and "route 'getAccount' declared in when was never hit" in why, rows

    def test_control_arranged_after_the_harness_is_built_is_not_seen(self, tmp_path):
        """The ORDER is the claim: move the arrangement below createHarness()
        and the ViewModel, which reads the session when built, never sees it."""
        tc.tool("node")

        def after_construction(text: str) -> str:
            arrange = '      await arrangeCondition("session", "present");\n'
            build = "      const h = createHarness();\n"
            assert text.count(arrange + build) == 1, text
            return text.replace(arrange + build, build + arrange)

        rows = _run_summary(_summary(tmp_path), edit_test=after_construction)
        assert not rows[1][0] and "getAccount" in rows[1][1], rows

    def test_xxx_control_without_the_default_the_previous_rows_session_leaks(self, tmp_path):
        """Row 2 names no condition. Its generated test still arranges
        session=absent; take that line out and it runs on whatever row 1
        left behind — signed in — and getAccount is called where it must not be."""
        tc.tool("node")

        def drop_defaults(text: str) -> str:
            line = '      await arrangeCondition("session", "absent");\n'
            assert text.count(line) == 1, text
            return text.replace(line, "")

        rows = _run_summary(_summary(tmp_path), edit_test=drop_defaults)
        assert rows[1][0], rows
        assert not rows[2][0], rows

    def test_the_skeleton_as_generated_keeps_every_row_red(self, tmp_path):
        tc.tool("node")
        root = _summary(tmp_path)
        rows = _run_summary(root, hook=None)
        assert all(not ok and "is not implemented" in why for ok, why in rows.values()), rows


class TestWhatIsEmitted:
    def test_web_the_arrangement_sits_between_the_mock_and_the_harness(self, tmp_path):
        text = _generate(_summary(tmp_path)).test_file.read_text(encoding="utf-8")
        assert 'import { arrangeCondition } from "../branch-harness/branch-conditions";' in text
        body = text.split("branch 2:", 1)[1]
        order = [body.index(m) for m in ("installFetchMock(", 'arrangeCondition("session", "absent")',
                                         "createHarness()")]
        assert order == sorted(order), order

    def test_every_declared_condition_in_declaration_order_on_every_platform(self, tmp_path):
        root = _summary(tmp_path, conditions=TWO)
        expected = {
            "web": ['await arrangeCondition("session", "present");',
                    'await arrangeCondition("clock", "day");'],
            "android": ['arrangeCondition("session", "present")', 'arrangeCondition("clock", "day")'],
            "ios": ['arrangeCondition("session", "present")', 'arrangeCondition("clock", "day")'],
        }
        for platform, lines in expected.items():
            text = _generate(root, platform).test_file.read_text(encoding="utf-8")
            first = text.index(lines[0])
            assert first < text.index(lines[1]), platform
            # Row 2 names neither: both defaults (xxx).
            assert text.count(lines[1]) == 2, (platform, text.count(lines[1]))

    def test_kotlin_and_swift_wrap_the_factory_and_leave_the_runtime_alone(self, tmp_path):
        root = _summary(tmp_path)
        kt = _generate(root, "android")
        text = kt.test_file.read_text(encoding="utf-8")
        assert "{ baseUrl, dispatcher ->" in text
        assert "::createSummaryBranchHarness" not in text
        sw = _generate(root, "ios")
        stext = sw.test_file.read_text(encoding="utf-8")
        assert "return createSummaryBranchHarness()" in stext
        bare = _summary(tmp_path / "bare", conditions=None,
                        rows=[{"when": {"api.getOrder": "default"},
                               "then": {"data.status": "ready"}}])
        for platform, report in (("android", kt), ("ios", sw)):
            same = _generate(bare, platform).runtime_file.read_bytes()
            assert report.runtime_file.read_bytes() == same, platform

    def test_xxix_an_app_without_conditions_gets_none_of_it(self, tmp_path):
        root = _summary(tmp_path, conditions=None,
                        rows=[{"when": {"api.getOrder": "default"},
                               "then": {"data.status": "ready"}}])
        for platform in ("web", "android", "ios"):
            report = _generate(root, platform)
            for f in (report.test_file, report.runtime_file):
                text = f.read_text(encoding="utf-8")
                assert "arrangeCondition" not in text and "branch-conditions" not in text, (platform, f)
            assert report.conditions_hook_file is None and not report.conditions_hook_created
        assert not list(root.rglob("branch-conditions.ts"))
        assert not list(root.rglob("BranchConditions.*"))


class TestTheHookFile:
    def test_one_skeleton_per_app_written_once(self, tmp_path):
        root = _summary(tmp_path)
        first = _generate(root)
        hook = root / "tests/unit/branch-harness/branch-conditions.ts"
        assert first.conditions_hook_file == hook and first.conditions_hook_created
        text = hook.read_text(encoding="utf-8")
        assert 'session: "absent" (default) | "present"' in text
        hook.write_text("// mine\n" + text, encoding="utf-8")
        again = _generate(root)
        assert not again.conditions_hook_created
        assert hook.read_text(encoding="utf-8").startswith("// mine\n")

    def test_kotlin_and_swift_hooks_land_beside_the_harnesses(self, tmp_path):
        root = _summary(tmp_path)
        kt = _generate(root, "android")
        assert kt.conditions_hook_file == root / "app/src/test/java/com/example/app/BranchConditions.kt"
        assert "package com.example.app" in kt.conditions_hook_file.read_text(encoding="utf-8")
        sw = _generate(root, "ios")
        assert sw.conditions_hook_file == root / "Tests/Generated/BranchConditions.swift"
        assert "@testable import summary_app" in sw.conditions_hook_file.read_text(encoding="utf-8")

    def test_check_mode_reports_a_missing_hook_and_writes_nothing(self, tmp_path):
        root = _summary(tmp_path)
        _generate(root)
        hook = root / "tests/unit/branch-harness/branch-conditions.ts"
        hook.unlink()
        report = _generate(root, check=True)
        assert report.conditions_hook_absent and not hook.exists()


class TestTheGeneratorRefusesMisdeclaredRows:
    """xxviii, through generation."""

    @pytest.mark.parametrize("when, conditions, needle", [
        ({"api.getOrder": "default", "harness.sesion": "present"}, SESSION,
         "'sesion' is not a declared harness condition"),
        ({"api.getOrder": "default", "harness.session": "expired"}, SESSION,
         "'expired' is not a value of harness condition 'session'"),
        ({"api.getOrder": "default", "harness.session": "present"}, None,
         "no app_contracts_spec declares harnessConditions"),
    ])
    def test_it_stops_and_names_the_row(self, tmp_path, when, conditions, needle):
        root = _summary(tmp_path, conditions=conditions,
                        rows=[{"when": when, "then": {"data.status": "ready"}}])
        with pytest.raises(bt.BranchTestGenerationError) as e:
            _generate(root)
        assert needle in str(e.value)
        assert "branchContracts.methods.loadSummary.branches[0].when.harness." in str(e.value)

    def test_two_app_specs_declaring_conditions_stop_it(self, tmp_path):
        root = _summary(tmp_path)
        (root / "docs/screens/json/app_two.spec.json").write_text(
            json.dumps(_app(SESSION)), encoding="utf-8")
        with pytest.raises(bt.BranchTestGenerationError, match="harnessConditions are declared by more"):
            _generate(root)


# ------------------------------------------------- Kotlin: compiled, run ---

_KOTLIN_PROBE = '''
class TestDispatcher
interface BranchHarness
class Recorder
class RouteSpec
val calls = mutableListOf<String>()

%(signature)s
  calls.add("mock")
  block(harnessFactory("http://x/", TestDispatcher()), Recorder())
}

%(hook)s
fun createSummaryBranchHarness(baseUrl: String, dispatcher: TestDispatcher): BranchHarness {
  calls.add("harness")
  return object : BranchHarness {}
}

fun main() {
  val routes = listOf<RouteSpec>()
%(call)s
    calls.add("block")
  }
  println(calls.joinToString("|"))
}
'''

_KOTLIN_HOOK = '''fun arrangeCondition(name: String, value: String) { calls.add("arrange $name=$value") }'''


def _kotlin_probe(tmp_path: Path, hook: str) -> str:
    root = _summary(tmp_path / "p")
    report = _generate(root, "android")
    runtime = report.runtime_file.read_text(encoding="utf-8")
    start = runtime.index("fun runBranchTest(")
    signature = runtime[start:runtime.index(") {\n", start) + len(") {")]
    test = report.test_file.read_text(encoding="utf-8")
    body = test[test.index("fun `loadSummary branch 1`()"):]
    call = body[body.index("    runBranchTest("):body.index("{ h, rec ->") + len("{ h, rec ->")]
    return _KOTLIN_PROBE % {"signature": signature, "hook": hook, "call": call}


def test_the_emitted_kotlin_factory_compiles_and_runs_in_order(tmp_path):
    run = tc.compile_and_run_kotlin(tmp_path, _kotlin_probe(tmp_path, _KOTLIN_HOOK))
    assert run.returncode == 0, run.stderr[:3000]
    assert run.stdout.strip() == "mock|arrange session=present|harness|block", run.stdout


def test_control_the_kotlin_call_is_compiled_not_decorative(tmp_path):
    """Without the consumer's hook the emitted factory does not compile."""
    with pytest.raises(AssertionError) as e:
        tc.compile_and_run_kotlin(tmp_path, _kotlin_probe(tmp_path, ""))
    assert "arrangeCondition" in str(e.value)


# ------------------------------------------- Swift: type-checked, XCTest ---

def _swift_typecheck(tmp_path: Path, *, with_hook: bool) -> subprocess.CompletedProcess:
    tc.tool("xcrun")
    root = _summary(tmp_path)
    report = _generate(root, "ios")
    files = [report.runtime_file, report.harness_file, report.test_file]
    if with_hook:
        files.append(report.conditions_hook_file)
    for f in files[1:]:
        text = f.read_text(encoding="utf-8")
        assert text.count("@testable import summary_app\n") == 1, f
        f.write_text(text.replace("@testable import summary_app\n", ""), encoding="utf-8")

    def show(*args: str) -> str:
        return subprocess.run(["xcrun", *args], capture_output=True, text=True,
                              timeout=120).stdout.strip()

    platform = show("--sdk", "macosx", "--show-sdk-platform-path")
    return subprocess.run(
        ["xcrun", "swiftc", "-typecheck", "-sdk", show("--sdk", "macosx", "--show-sdk-path"),
         "-F", f"{platform}/Developer/Library/Frameworks",
         "-I", f"{platform}/Developer/usr/lib", *[str(f) for f in files]],
        capture_output=True, text=True, timeout=600)


def test_the_swift_test_and_the_hook_skeleton_type_check(tmp_path):
    done = _swift_typecheck(tmp_path, with_hook=True)
    assert done.returncode == 0, done.stderr[:4000]


def test_control_without_the_hook_the_swift_test_does_not_type_check(tmp_path):
    done = _swift_typecheck(tmp_path, with_hook=False)
    assert done.returncode != 0
    assert "arrangeCondition" in done.stderr, done.stderr[:2000]


# --------------------------------------------------------------- coverage ---

def _coverage_screen(when_extra: dict) -> dict:
    screen = tcc._screen()
    branch = screen["branchContracts"]["methods"]["approve"]["branches"][0]
    branch["when"].update(when_extra)
    return screen


class TestCoverage:
    def test_a_condition_row_is_an_ordinary_row_and_is_counted(self, tmp_path):
        base = tcc._counts(tcc._screen_result(tcc._run(tcc._project(tmp_path / "a"))))
        root = tcc._project(tmp_path / "b", screen=_coverage_screen({"harness.session": "present"}),
                            app=_app(SESSION))
        report = tcc._run(root)
        s = tcc._screen_result(report)
        assert tcc._counts(s) == base
        assert s.declaration_errors == [] and s.info["condition_rows"] == 1
        text = "\n".join(tcc.cc.format_text(report))
        assert "harnessConditions session" in text and "condition rows 1" in text
        js = tcc.cc.to_json(report)
        assert js["app"]["harness_conditions"] == ["session"]

    def test_an_app_without_conditions_prints_as_before(self, tmp_path):
        report = tcc._run(tcc._project(tmp_path))
        text = "\n".join(tcc.cc.format_text(report))
        assert "condition rows" not in text and "harnessConditions" not in text
        assert tcc.cc.to_json(report)["app"]["harness_conditions"] is None

    @pytest.mark.parametrize("when, app", [
        ({"harness.session": "present"}, None),
        ({"harness.sesion": "present"}, _app(SESSION)),
        ({"harness.session": "expired"}, _app(SESSION)),
    ])
    def test_xxviii_is_a_declaration_error_and_exit_1(self, tmp_path, when, app):
        report = tcc._run(tcc._project(tmp_path, screen=_coverage_screen(when), app=app))
        errors = tcc._screen_result(report).declaration_errors
        assert any("branchContracts.methods.approve.branches[0].when.harness." in e["message"]
                   for e in errors), errors
        assert report.exit == 1

    def test_a_malformed_declaration_is_an_app_error(self, tmp_path):
        app = _app({"session": {"values": ["only"], "default": "only", "reason": "r"}})
        report = tcc._run(tcc._project(tmp_path, app=app))
        assert any("harnessConditions.session.values" in e["message"] for e in report.app_errors)
        assert report.exit == 1
