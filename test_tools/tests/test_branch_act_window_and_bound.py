"""The act window and the upper bound on calls — measured by RUNNING them.

Two changes to what a generated branch test does:

- **The act window.** The mock goes in before the harness is built, the
  construction settles, the arrangement is written, and only then does the
  recorder start counting (`mark()`). In the old order a call the
  constructor started ran in the settle AFTER act: it overwrote the arranged
  state, landed inside the window, and did so in an order that differed per
  platform.
- **The bound (⊆).** Every generated test asserts that the declared routes
  called during act are ones its method's rows reach, plus the side calls
  the app contracts spec admits for the statuses the test serves, minus what
  the row says `not-called`. Without it, deleting the row that reaches an
  endpoint made that endpoint's uncovered statuses disappear.

Whether an assertion holds is a fact about execution. The web face is run
end to end: the generator writes a real test file, a hand-written harness
builds a fake view model, and node runs the file against a minimal stand-in
for vitest. Each expectation has a control that mutates ONE thing and must
flip the rows that thing is responsible for — without it, a test file that
never ran would report the same rows as one that did.

The Kotlin and Swift recorders are run as probes (the shape
`test_recorder_refuses_an_undeclared_op` uses), and their emission is read
for the order of the window.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from jsonui_test_cli import branch_tests as bt
from tests import _toolchain as tc


# ---------------------------------------------------------------------------
# the recorder's window, on all three faces
# ---------------------------------------------------------------------------

_WINDOW_EXPECTED = {
    "unmarked-sees-everything": True,
    "pre-mark-not-counted": True,
    "pre-mark-no-body": True,
    "pre-mark-not-matched": True,
    "post-mark-counted": True,
    "unexpected-names-the-extra-op-once": True,
    "unexpected-ignores-unmatched": True,
    "unexpected-ignores-pre-mark": True,
    "unexpected-empty-when-allowed": True,
    # P2e(a): the requests no declared route answered, as "METHOD path".
    "unmatched-unmarked-sees-the-early-one": True,
    "unmatched-names-only-the-window": True,
}

#: Rows that exist only because `mark()` moves the start of the window
#: (`post-mark-counted` too: unmarked, the call before counts as a third).
_WINDOW_CONTROL_ROWS = {
    "pre-mark-not-counted", "pre-mark-no-body", "pre-mark-not-matched",
    "unexpected-ignores-pre-mark", "post-mark-counted",
    "unmatched-names-only-the-window",
}


def _results(stdout: str) -> dict[str, bool]:
    out = {}
    for line in stdout.splitlines():
        parts = line.split(None, 2)
        if len(parts) >= 2 and parts[0] in ("PASS", "FAIL"):
            out[parts[1]] = parts[0] == "PASS"
    return out


def _assert_rows(results: dict, expected: dict, stdout: str) -> None:
    missing = set(expected) - set(results)
    assert not missing, f"probe never reported {sorted(missing)}:\n{stdout}"
    wrong = {k: results[k] for k in expected if results[k] != expected[k]}
    assert not wrong, f"rows disagreed: {wrong}\n{stdout}"


def _flipped(results: dict, expected: dict) -> set:
    return {k for k in expected if k in results and results[k] != expected[k]}


def _no_mark(runtime: str, body: str) -> str:
    """The runtime with `mark()` doing nothing — the control for every row
    the window is responsible for. Checked to have matched exactly once."""
    assert runtime.count(body) == 1, f"expected one '{body}' in the runtime"
    return runtime.replace(body, "")


_TS_WINDOW_PROBE = '''import { installFetchMock } from "./runtime.ts";

const ROUTES: any[] = [
  { op: "a", method: "GET", pattern: "^/a$", scenario: "default",
    scenarios: { default: { status: 200, body: { n: 1 } } } },
  { op: "b", method: "POST", pattern: "^/b$", scenario: "default",
    scenarios: { default: { status: 200, body: {} } } },
];
function check(name: string, got: boolean) {
  console.log(`${got ? "PASS" : "FAIL"} ${name}`);
}
const rec = installFetchMock(ROUTES);
await fetch("https://x.test/a");
await fetch("https://x.test/b", { method: "POST", body: JSON.stringify({ before: true }) });
await fetch("https://x.test/early", { method: "POST" });
check("unmarked-sees-everything", rec.countFor("a") === 1 && rec.countFor("b") === 1);
check("unmatched-unmarked-sees-the-early-one",
      JSON.stringify(rec.unmatchedCalls()) === '["POST /early"]');
rec.mark();
check("pre-mark-not-counted", rec.countFor("a") === 0);
check("pre-mark-no-body", rec.lastBodyFor("b") === undefined);
check("pre-mark-not-matched", rec.matchedCalls().length === 0);
check("unexpected-ignores-pre-mark", rec.unexpectedOps([]).length === 0);
await fetch("https://x.test/b", { method: "POST", body: "{}" });
await fetch("https://x.test/b", { method: "POST", body: "{}" });
await fetch("https://x.test/elsewhere");
check("post-mark-counted", rec.countFor("b") === 2);
check("unexpected-names-the-extra-op-once",
      JSON.stringify(rec.unexpectedOps(["a"])) === '["b"]');
check("unexpected-ignores-unmatched", !rec.unexpectedOps(["a"]).includes("(unmatched)"));
check("unexpected-empty-when-allowed", rec.unexpectedOps(["a", "b"]).length === 0);
await fetch("https://x.test/elsewhere");
check("unmatched-names-only-the-window",
      JSON.stringify(rec.unmatchedCalls()) === '["GET /elsewhere"]');
rec.restore();
'''


def _run_ts_window(tmp_path: Path, runtime: str) -> tuple[dict, str]:
    (tmp_path / "runtime.ts").write_text(runtime, encoding="utf-8")
    (tmp_path / "probe.ts").write_text(_TS_WINDOW_PROBE, encoding="utf-8")
    run = subprocess.run(["node", "--experimental-strip-types", "probe.ts"],
                         cwd=tmp_path, capture_output=True, text=True, timeout=120)
    return _results(run.stdout), run.stdout + run.stderr[:3000]


def test_web_recorder_window(tmp_path):
    tc.tool("node")
    results, out = _run_ts_window(tmp_path, bt.RUNTIME_TS)
    _assert_rows(results, _WINDOW_EXPECTED, out)


def test_web_recorder_window_control(tmp_path):
    tc.tool("node")
    results, out = _run_ts_window(
        tmp_path, _no_mark(bt.RUNTIME_TS, "windowStart = calls.length;"))
    assert _flipped(results, _WINDOW_EXPECTED) == _WINDOW_CONTROL_ROWS, out


def _swift_block(emitted: str, signature: str) -> str:
    pattern = r"(?:nonisolated\ )?" + re.escape(signature)
    if signature.startswith("private"):
        pattern = re.escape(signature).replace(r"private\ ", r"private\ (?:nonisolated\ )?", 1)
    i = re.search(pattern, emitted).start()
    return emitted[i:emitted.index("\n}\n", i) + 3]


_SWIFT_SHIM = '''import Foundation
func XCTFail(_ m: String = "", file: StaticString = #filePath, line: UInt = #line) {}
'''

_SWIFT_WINDOW_MAIN = '''
func check(_ name: String, _ got: Bool) { print((got ? "PASS" : "FAIL") + " " + name) }
func call(_ rec: Recorder, _ op: String, _ body: Any? = nil) {
  rec.calls.append(RecordedCall(op: op, method: "GET", path: "/" + op, body: body))
}
let rec = Recorder(routeOps: ["a", "b"])
call(rec, "a")
call(rec, "b", ["before": true])
rec.calls.append(RecordedCall(op: "(unmatched)", method: "POST", path: "/early", body: nil))
check("unmarked-sees-everything", rec.countFor("a") == 1 && rec.countFor("b") == 1)
check("unmatched-unmarked-sees-the-early-one", rec.unmatchedCalls() == ["POST /early"])
rec.mark()
check("pre-mark-not-counted", rec.countFor("a") == 0)
check("pre-mark-no-body", rec.lastBodyFor("b") == nil)
check("pre-mark-not-matched", rec.matchedCalls().isEmpty)
check("unexpected-ignores-pre-mark", rec.unexpectedOps([]).isEmpty)
call(rec, "b", [:] as [String: Any])
call(rec, "b", [:] as [String: Any])
call(rec, "(unmatched)")
check("post-mark-counted", rec.countFor("b") == 2)
check("unexpected-names-the-extra-op-once", rec.unexpectedOps(["a"]) == ["b"])
check("unexpected-ignores-unmatched", !rec.unexpectedOps(["a"]).contains("(unmatched)"))
check("unexpected-empty-when-allowed", rec.unexpectedOps(["a", "b"]).isEmpty)
call(rec, "(unmatched)")
check("unmatched-names-only-the-window", rec.unmatchedCalls() == ["GET /(unmatched)"])
// The warning before the gate: compiled and run here (nothing else compiles
// the file-scope Swift runtime without an app's XCTest target).
reportUnmatched(rec.unmatchedCalls(), "9.9.9")
reportUnmatched([], nil)
'''


def _run_swift_window(tmp_path: Path, runtime: str) -> tuple[dict, str]:
    parts = [_swift_block(runtime, "struct RecordedCall {"),
             _swift_block(runtime, "private func quotedValue("),
             _swift_block(runtime, "final class Recorder {"),
             _swift_block(runtime, "func reportUnmatched(")]
    (tmp_path / "shim.swift").write_text(_SWIFT_SHIM, encoding="utf-8")
    (tmp_path / "runtime.swift").write_text(
        "import Foundation\n\n" + "\n\n".join(parts), encoding="utf-8")
    (tmp_path / "main.swift").write_text(_SWIFT_WINDOW_MAIN, encoding="utf-8")
    binary = tmp_path / "probe"
    build = subprocess.run(
        ["swiftc", "-Onone", "-o", str(binary), str(tmp_path / "shim.swift"),
         str(tmp_path / "runtime.swift"), str(tmp_path / "main.swift")],
        capture_output=True, text=True, timeout=600)
    assert build.returncode == 0, f"emitted Swift did not compile:\n{build.stderr[:4000]}"
    run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
    return _results(run.stdout), run.stdout


def test_ios_recorder_window(tmp_path):
    tc.tool("swiftc")
    results, out = _run_swift_window(tmp_path, bt.SWIFT_RUNTIME)
    _assert_rows(results, _WINDOW_EXPECTED, out)


def test_ios_recorder_window_control(tmp_path):
    tc.tool("swiftc")
    results, out = _run_swift_window(
        tmp_path, _no_mark(bt.SWIFT_RUNTIME, "windowStart = calls.count"))
    assert _flipped(results, _WINDOW_EXPECTED) == _WINDOW_CONTROL_ROWS, out


_KOTLIN_WINDOW_MAIN = '''
fun check(name: String, got: Boolean) { println((if (got) "PASS" else "FAIL") + " " + name) }
fun call(rec: Recorder, op: String, body: String? = null) {
  rec.calls.add(RecordedCall(op, "GET", "/" + op, body))
}
fun main() {
  val rec = Recorder(setOf("a", "b"))
  call(rec, "a")
  call(rec, "b", "{\\"before\\":true}")
  rec.calls.add(RecordedCall("(unmatched)", "POST", "/early", null))
  check("unmarked-sees-everything", rec.countFor("a") == 1 && rec.countFor("b") == 1)
  check("unmatched-unmarked-sees-the-early-one", rec.unmatchedCalls() == listOf("POST /early"))
  rec.mark()
  check("pre-mark-not-counted", rec.countFor("a") == 0)
  check("pre-mark-no-body", rec.lastBodyFor("b") == null)
  check("pre-mark-not-matched", rec.matchedCalls().isEmpty())
  check("unexpected-ignores-pre-mark", rec.unexpectedOps(setOf()).isEmpty())
  call(rec, "b", "{}")
  call(rec, "b", "{}")
  call(rec, "(unmatched)")
  check("post-mark-counted", rec.countFor("b") == 2)
  check("unexpected-names-the-extra-op-once", rec.unexpectedOps(setOf("a")) == listOf("b"))
  check("unexpected-ignores-unmatched", "(unmatched)" !in rec.unexpectedOps(setOf("a")))
  check("unexpected-empty-when-allowed", rec.unexpectedOps(setOf("a", "b")).isEmpty())
  call(rec, "(unmatched)")
  check("unmatched-names-only-the-window", rec.unmatchedCalls() == listOf("GET /(unmatched)"))
  // The warning before the gate, compiled and run (see the Swift probe).
  reportUnmatched(rec.unmatchedCalls(), "9.9.9")
  reportUnmatched(emptyList(), null)
}
'''


def _kotlin_window_source(runtime: str) -> str:
    recorded_call = re.search(r"^data class RecordedCall\(.*$", runtime, re.M).group(0)

    def block(signature: str) -> str:
        i = runtime.index(signature)
        return runtime[i:runtime.index("\n}\n", i) + 3]

    return "\n\n".join([recorded_call, block("private fun quotedValue("),
                        block("class Recorder("), block("fun reportUnmatched(")]) + _KOTLIN_WINDOW_MAIN


def _run_kotlin_window(tmp_path: Path, runtime: str) -> tuple[dict, str]:
    run = tc.compile_and_run_kotlin(
        tmp_path, tc.KOTLIN_SHIM + "\n" + _kotlin_window_source(runtime))
    return _results(run.stdout), run.stdout


def test_android_recorder_window(tmp_path):
    results, out = _run_kotlin_window(tmp_path, bt.KOTLIN_RUNTIME)
    _assert_rows(results, _WINDOW_EXPECTED, out)


def test_android_recorder_window_control(tmp_path):
    results, out = _run_kotlin_window(
        tmp_path, _no_mark(bt.KOTLIN_RUNTIME, "windowStart = calls.size"))
    assert _flipped(results, _WINDOW_EXPECTED) == _WINDOW_CONTROL_ROWS, out


# ---------------------------------------------------------------------------
# a generated web test, run end to end
# ---------------------------------------------------------------------------

def _mock(root: Path, name: str, method: str, path: str, operation_id: str,
          scenarios: dict) -> None:
    target = root / "tests/mocks/generated" / f"{name}.mock.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "source": {"method": method, "path": path, "operationId": operation_id},
        "activeScenario": "default", "scenarios": scenarios}), encoding="utf-8")


_RULE = {"id": "session-end-logout", "statuses": ["401"], "sideCalls": ["postLogout"],
         "verifiedBy": ["request_onTerminal401_postsLogout"],
         "reason": "the network layer posts logout on a terminal 401"}


def _project(root: Path, *, rules: list | None = (_RULE,)) -> Path:
    spec_dir = root / "docs/screens/json"
    spec_dir.mkdir(parents=True)
    (root / "jui.config.json").write_text(json.dumps(
        {"spec_directory": "docs/screens/json", "platforms": ["web"]}), encoding="utf-8")
    spec = {
        "type": "screen_spec",
        "metadata": {"name": "checkout"},
        "dataFlow": {
            "viewModel": {"methods": [{"name": "submit"}, {"name": "refresh"}]},
            "repositories": [{"name": "OrderRepository", "methods": [
                {"name": "submitOrder", "endpoint": "POST /api/orders"},
                {"name": "getProfile", "endpoint": "GET /api/profile"},
                {"name": "logout", "endpoint": "POST /api/logout"},
                {"name": "getHistory", "endpoint": "GET /api/history"},
            ]}],
        },
        "branchContracts": {"methods": {
            "submit": {"branches": [
                # 1: the constructor's profile load is outside the window, and
                #    the arranged name survives it.
                {"when": {"api.submitOrder": "default", "data.name": "seeded"},
                 "then": {"data.status": "done", "data.name": "seeded",
                          "api.getProfile": "not-called"}},
                # 2: 500, and 429 the same way (alsoStatuses).
                {"when": {"api.submitOrder": "error_500"},
                 "alsoStatuses": {"api.submitOrder": ["429"]},
                 "then": {"data.status": "failed"}},
                # 3: 401 — the network layer's logout is admitted by the rule.
                {"when": {"api.submitOrder": "error_401"},
                 "then": {"data.status": "failed"}},
                # 4: 401, and the row says logout must NOT happen: the row
                #    wins over the rule, so the VM's logout makes this red.
                {"when": {"api.submitOrder": "error_401"},
                 "then": {"data.status": "failed", "api.logout": "not-called"}},
            ]},
            "refresh": {"branches": [
                # The VM also fetches the profile here, which no row of
                # refresh reaches: the bound makes this red.
                {"when": {"api.getHistory": "default"},
                 "then": {"data.status": "idle"}},
            ]},
        }},
    }
    (spec_dir / "checkout.spec.json").write_text(json.dumps(spec), encoding="utf-8")
    if rules is not None:
        (spec_dir / "app_contracts.spec.json").write_text(json.dumps({
            "type": "app_contracts_spec",
            "metadata": {"name": "app", "description": "d"},
            "unitContracts": [{"target": "ApiClient", "cases": [
                {"name": "request_onTerminal401_postsLogout"}]}],
            "apiOutcomeRules": list(rules)}), encoding="utf-8")
    _mock(root, "orders", "POST", "/api/orders", "submitOrder", {
        "default": {"status": 200, "body": {}},
        "error_500": {"status": 500, "body": {"message": "boom"}},
        "error_429": {"status": 429, "body": {}},
        "error_401": {"status": 401, "body": {}}})
    _mock(root, "profile", "GET", "/api/profile", "getProfile",
          {"default": {"status": 200, "body": {"name": "loaded"}}})
    _mock(root, "logout", "POST", "/api/logout", "postLogout",
          {"default": {"status": 204}})
    _mock(root, "history", "GET", "/api/history", "getHistory",
          {"default": {"status": 200, "body": []}})
    return root


_HARNESS = '''import { applyDeclaredKeys } from "../generated/jsonui-branch-runtime";

class CheckoutViewModel {
  status = "idle";
  name = "initial";
  constructor() {
    void this.load();
  }
  async load() {
    const r = await fetch("https://api.test/api/profile");
    const j = await r.json();
    this.name = j.name;
  }
  async submit() {
    const r = await fetch("https://api.test/api/orders",
                          { method: "POST", body: JSON.stringify({}) });
    if (r.status === 401) {
      // What an app's network layer does on a terminal 401.
      await fetch("https://api.test/api/logout", { method: "POST" });
      this.status = "failed";
      return;
    }
    this.status = r.ok ? "done" : "failed";
  }
  async refresh() {
    await fetch("https://api.test/api/history");
    await fetch("https://api.test/api/profile");
  }
}

export function createHarness() {
  const vm = new CheckoutViewModel();
  return {
    vm,
    setState(state: Record<string, unknown>) { applyDeclaredKeys(vm, state); },
    readField(name: string) { return (vm as any)[name]; },
    expectTransition(_d: string) {},
    resolveString(key: string) { return key; },
  };
}
'''

_VITEST = '''const tests = [];
const prefix = [];
export function describe(name, fn) { prefix.push(name); fn(); prefix.pop(); }
export function it(name, fn) { tests.push([[...prefix, name].join(" > "), fn]); }
export function expect(actual, message) {
  const fail = (why) => { throw new Error((message ? message + " :: " : "") + why); };
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  return {
    toEqual(e) { if (!same(actual, e)) fail(`expected ${JSON.stringify(e)}, got ${JSON.stringify(actual)}`); },
    toBe(e) { if (!Object.is(actual, e)) fail(`expected ${e}, got ${actual}`); },
    toBeGreaterThan(n) { if (!(actual > n)) fail(`expected > ${n}, got ${actual}`); },
  };
}
export async function run() {
  for (const [name, fn] of tests) {
    try { await fn(); console.log(`PASS ${name}`); }
    catch (e) { console.log(`FAIL ${name} :: ${String(e && e.message).split("\\n")[0]}`); }
  }
}
'''

#: The generated test imports without extensions (vitest resolves them);
#: node does not. The hook adds `.ts` to a relative specifier that fails —
#: the generated file itself is run as written.
_HOOKS = '''export async function resolve(specifier, context, next) {
  try { return await next(specifier, context); }
  catch (e) {
    if (specifier.startsWith(".")) return next(specifier + ".ts", context);
    throw e;
  }
}
'''
_REGISTER = '''import { register } from "node:module";
register("./hooks.mjs", import.meta.url);
'''
_RUNNER = '''import { run } from "vitest";
await import("./tests/unit/generated/checkout.branches.test.ts");
await run();
'''


def _generate_web(root: Path) -> Path:
    report = bt.generate_branch_tests(
        "checkout", root, platform="web", config_platforms=["web"])
    return report.test_file


def _run_web(root: Path, test_file: Path) -> dict[str, tuple[bool, str]]:
    harness = root / "tests/unit/branch-harness/checkout.ts"
    harness.write_text(_HARNESS, encoding="utf-8")
    vitest = root / "node_modules/vitest"
    vitest.mkdir(parents=True, exist_ok=True)
    (vitest / "package.json").write_text(
        '{"name": "vitest", "type": "module", "main": "index.js"}', encoding="utf-8")
    (vitest / "index.js").write_text(_VITEST, encoding="utf-8")
    (root / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (root / "hooks.mjs").write_text(_HOOKS, encoding="utf-8")
    (root / "register.mjs").write_text(_REGISTER, encoding="utf-8")
    (root / "runner.mjs").write_text(_RUNNER, encoding="utf-8")
    run = subprocess.run(
        ["node", "--experimental-strip-types", "--import", "./register.mjs", "runner.mjs"],
        cwd=root, capture_output=True, text=True, timeout=120)
    rows = {}
    for line in run.stdout.splitlines():
        m = re.match(r"^(PASS|FAIL) (.+?)(?: :: (.*))?$", line)
        if m:
            rows[m.group(2)] = (m.group(1) == "PASS", m.group(3) or "")
    assert rows, f"the generated test produced no rows:\n{run.stdout}\n{run.stderr[:4000]}"
    return rows


def _row(rows: dict, method: str, number: int, also: str | None = None) -> tuple[bool, str]:
    hits = [(name, v) for name, v in rows.items()
            if f"checkout.{method} > branch {number}:" in name
            and ((f"[+{also} via" in name) if also else "[+" not in name)]
    assert len(hits) == 1, f"expected one row for {method} {number} {also}: {sorted(rows)}"
    return hits[0][1]


def test_the_generated_web_test_runs_with_the_window_and_the_bound(tmp_path):
    tc.tool("node")
    root = _project(tmp_path)
    rows = _run_web(root, _generate_web(root))
    # 6 tests: 4 submit rows + the 429 copy + 1 refresh row.
    assert len(rows) == 6, sorted(rows)
    assert _row(rows, "submit", 1)[0], rows          # window + seed
    assert _row(rows, "submit", 2)[0], rows
    assert _row(rows, "submit", 2, also="429")[0], rows
    assert _row(rows, "submit", 3)[0], rows          # logout admitted by the rule
    passed, why = _row(rows, "submit", 4)            # not-called beats the rule
    assert not passed and "logout" in why, rows
    passed, why = _row(rows, "refresh", 1)           # outside refresh's reach
    assert not passed and "getProfile" in why, rows


def test_control_without_mark_the_constructor_call_is_counted(tmp_path):
    tc.tool("node")
    root = _project(tmp_path)
    test_file = _generate_web(root)
    text = test_file.read_text(encoding="utf-8")
    assert text.count("      rec.mark();\n") == 6
    test_file.write_text(text.replace("      rec.mark();\n", ""), encoding="utf-8")
    rows = _run_web(root, test_file)
    # The constructor's profile load now lands in every submit row's window,
    # outside what submit reaches — the bound names it on each of them.
    for number, also in ((1, None), (2, None), (2, "429"), (3, None)):
        passed, why = _row(rows, "submit", number, also)
        assert not passed and "getProfile" in why, (number, also, rows)


def test_control_without_the_first_settle_the_seed_is_overwritten(tmp_path):
    tc.tool("node")
    root = _project(tmp_path)
    test_file = _generate_web(root)
    text = test_file.read_text(encoding="utf-8")
    first = "      const h = createHarness();\n      await settle();\n"
    assert text.count(first) == 6
    test_file.write_text(text.replace(first, "      const h = createHarness();\n"),
                         encoding="utf-8")
    rows = _run_web(root, test_file)
    passed, why = _row(rows, "submit", 1)
    assert not passed and "loaded" in why, rows


def test_control_without_the_rule_the_side_call_is_red(tmp_path):
    tc.tool("node")
    root = _project(tmp_path, rules=None)
    rows = _run_web(root, _generate_web(root))
    passed, why = _row(rows, "submit", 3)
    assert not passed and "logout" in why, rows
    # The rule's statuses decide: a 500 row never admitted logout anyway.
    assert _row(rows, "submit", 2)[0], rows


def test_control_without_the_bound_the_extra_call_passes(tmp_path):
    tc.tool("node")
    root = _project(tmp_path)
    test_file = _generate_web(root)
    text = test_file.read_text(encoding="utf-8")
    bound = re.compile(r"^      expect\(rec\.unexpectedOps\(.*\n", re.M)
    assert len(bound.findall(text)) == 6
    test_file.write_text(bound.sub("", text), encoding="utf-8")
    rows = _run_web(root, test_file)
    assert _row(rows, "refresh", 1)[0], rows


def test_the_emitted_allowed_sets(tmp_path):
    """What each test admits, read from the file the runs above executed."""
    root = _project(tmp_path)
    text = _generate_web(root).read_text(encoding="utf-8")
    allowed = re.findall(r"rec\.unexpectedOps\((\[.*?\])\)", text)
    assert [json.loads(a) for a in allowed] == [
        ["submitOrder"],                 # 1: getProfile is not-called
        ["submitOrder"],                 # 2: a 500 admits nothing
        ["submitOrder"],                 # 2 +429: a 429 admits nothing
        ["logout", "submitOrder"],       # 3: the 401 admits the side call
        ["submitOrder"],                 # 4: not-called takes it back out
        ["getHistory"],                  # refresh
    ], allowed


# ---------------------------------------------------------------------------
# red-check xxv: how far one row's "called" reaches, and what the red says
# ---------------------------------------------------------------------------
#
# A save method whose success row refetches the list and whose error rows do
# not. The bound is per method, so `api.listMembers: "called"` on the success
# row allows the refetch in the error rows too — unless a row says
# "not-called". The failure message is what a writer reads when clearing the
# red, so it has to say that.

def _roster(root: Path, *, called: bool = True, not_called_on_404: bool = False) -> Path:
    spec_dir = root / "docs/screens/json"
    spec_dir.mkdir(parents=True)
    (root / "jui.config.json").write_text(json.dumps(
        {"spec_directory": "docs/screens/json", "platforms": ["web", "android", "ios"]}),
        encoding="utf-8")
    ok = {"data.status": "saved"}
    if called:
        ok["api.listMembers"] = "called"
    missing = {"data.status": "missing"}
    if not_called_on_404:
        missing["api.listMembers"] = "not-called"
    spec = {
        "type": "screen_spec",
        "metadata": {"name": "roster"},
        "dataFlow": {
            "viewModel": {"methods": [{"name": "save"}]},
            "repositories": [{"name": "MemberRepository", "methods": [
                {"name": "updateMember", "endpoint": "PUT /api/members/{id}"},
                {"name": "listMembers", "endpoint": "GET /api/members"},
            ]}],
        },
        "branchContracts": {"methods": {"save": {"branches": [
            {"when": {"api.updateMember": "default"}, "then": ok},
            {"when": {"api.updateMember": "error_400"}, "then": {"data.status": "invalid"}},
            {"when": {"api.updateMember": "error_404"}, "then": missing},
        ]}}},
    }
    (spec_dir / "roster.spec.json").write_text(json.dumps(spec), encoding="utf-8")
    _mock(root, "update", "PUT", "/api/members/{id}", "updateMember", {
        "default": {"status": 200, "body": {}},
        "error_400": {"status": 400, "body": {}},
        "error_404": {"status": 404, "body": {}}})
    _mock(root, "list", "GET", "/api/members", "listMembers",
          {"default": {"status": 200, "body": []}})
    return root


def _roster_harness(refetch_on_error: bool) -> str:
    return f'''import {{ applyDeclaredKeys }} from "../generated/jsonui-branch-runtime";

class RosterViewModel {{
  status = "idle";
  async save() {{
    const r = await fetch("https://api.test/api/members/1",
                          {{ method: "PUT", body: JSON.stringify({{}}) }});
    if (r.ok || {str(refetch_on_error).lower()}) {{
      await fetch("https://api.test/api/members");
    }}
    this.status = r.ok ? "saved" : (r.status === 404 ? "missing" : "invalid");
  }}
}}

export function createHarness() {{
  const vm = new RosterViewModel();
  return {{
    vm,
    setState(state: Record<string, unknown>) {{ applyDeclaredKeys(vm, state); }},
    readField(name: string) {{ return (vm as any)[name]; }},
    expectTransition(_d: string) {{}},
    resolveString(key: string) {{ return key; }},
  }};
}}
'''


def _run_roster(root: Path, *, refetch_on_error: bool = False) -> dict[str, tuple[bool, str]]:
    report = bt.generate_branch_tests("roster", root, platform="web", config_platforms=["web"])
    harness = root / "tests/unit/branch-harness/roster.ts"
    harness.write_text(_roster_harness(refetch_on_error), encoding="utf-8")
    vitest = root / "node_modules/vitest"
    vitest.mkdir(parents=True, exist_ok=True)
    (vitest / "package.json").write_text(
        '{"name": "vitest", "type": "module", "main": "index.js"}', encoding="utf-8")
    (vitest / "index.js").write_text(_VITEST, encoding="utf-8")
    (root / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (root / "hooks.mjs").write_text(_HOOKS, encoding="utf-8")
    (root / "register.mjs").write_text(_REGISTER, encoding="utf-8")
    (root / "runner.mjs").write_text(
        _RUNNER.replace("checkout.branches.test.ts", report.test_file.name), encoding="utf-8")
    run = subprocess.run(
        ["node", "--experimental-strip-types", "--import", "./register.mjs", "runner.mjs"],
        cwd=root, capture_output=True, text=True, timeout=120)
    rows = {}
    for line in run.stdout.splitlines():
        m = re.match(r"^(PASS|FAIL) roster\.save > branch (\d+):.*?(?: :: (.*))?$", line)
        if m:
            rows[int(m.group(2))] = (m.group(1) == "PASS", m.group(3) or "")
    assert sorted(rows) == [1, 2, 3], f"expected three rows:\n{run.stdout}\n{run.stderr[:3000]}"
    return rows


def test_xxv_called_on_the_success_row_reaches_the_error_rows(tmp_path):
    """What the message now says, read off the emitted file: the success row's
    "called" is in the error rows' allowed sets too."""
    root = _roster(tmp_path)
    text = bt.generate_branch_tests(
        "roster", root, platform="web", config_platforms=["web"]).test_file.read_text()
    allowed = [json.loads(a) for a in re.findall(r"rec\.unexpectedOps\((\[.*?\])\)", text)]
    assert allowed == [["listMembers", "updateMember"]] * 3, allowed


@pytest.mark.parametrize("not_called, refetch_on_error, row3_passes", [
    (False, False, True),    # the code is right: green either way
    (True, False, True),
    (True, True, False),     # the 404 row refuses the refetch: red
    (False, True, True),     # nothing refuses it: green — the hole the message names
])
def test_xxv_only_not_called_refuses_the_call_in_an_error_row(tmp_path, not_called,
                                                             refetch_on_error, row3_passes):
    tc.tool("node")
    rows = _run_roster(_roster(tmp_path, not_called_on_404=not_called),
                       refetch_on_error=refetch_on_error)
    assert rows[1][0], rows
    assert rows[3][0] is row3_passes, rows


def test_xxv_without_called_the_success_row_is_red_and_says_how_to_fix_it(tmp_path):
    tc.tool("node")
    rows = _run_roster(_roster(tmp_path, called=False))
    passed, why = rows[1]
    assert not passed and "listMembers" in why, rows
    assert "that allows <op> in every row of this method that does not mention it" in why
    assert 'says api.<op>: "not-called"' in why
    assert "apiOutcomeRules" in why
    assert rows[2][0] and rows[3][0], rows          # the error rows never refetch


def test_xxv_control_restoring_called_turns_it_green(tmp_path):
    tc.tool("node")
    rows = _run_roster(_roster(tmp_path, called=True))
    assert all(passed for passed, _ in rows.values()), rows


def test_xxv_the_three_renderers_print_the_same_message(tmp_path):
    """One constant, escaped per language — no face prints a different fix."""
    root = _roster(tmp_path)
    web = bt.generate_branch_tests("roster", root, platform="web",
                                   config_platforms=["web", "android", "ios"]).test_file.read_text()
    kotlin = bt.generate_branch_tests("roster", root, platform="android", package="com.example.roster",
                                      config_platforms=["web", "android", "ios"]).test_file.read_text()
    swift = bt.generate_branch_tests("roster", root, platform="ios", module="RosterApp",
                                     config_platforms=["web", "android", "ios"]).test_file.read_text()
    message = bt.UNEXPECTED_OPS_MESSAGE
    assert web.count(bt._ts(message)) == 3
    assert kotlin.count(bt._kt_str(message)) == 3
    assert swift.count(bt._swift_str(message)) == 3


# ---------------------------------------------------------------------------
# the window's order in the Kotlin and Swift emission
# ---------------------------------------------------------------------------

def _body_order(text: str, first_line: str, markers: list[str]) -> list[int]:
    i = text.index(first_line)
    end = text.index("\n  }\n", i)
    body = text[i:end]
    return [body.index(m) for m in markers]


def test_kotlin_emits_the_window_in_order(tmp_path):
    root = _project(tmp_path)
    report = bt.generate_branch_tests(
        "checkout", root, platform="android", package="com.example.app",
        out_dir="app/src/test/java", harness_dir="app/src/test/java",
        config_platforms=["web", "android"])
    text = report.test_file.read_text(encoding="utf-8")
    order = _body_order(text, "fun `submit branch 1`()", [
        "h.settle()", "h.setState(", "rec.mark()", 'h.invoke("submit")',
        "h.settle()\n      assert", "rec.unexpectedOps(setOf<String>(\"submitOrder\"))"])
    assert order == sorted(order), order
    assert "fun `submit branch 2 also 429`()" in text


def test_swift_emits_the_window_in_order(tmp_path):
    root = _project(tmp_path)
    report = bt.generate_branch_tests(
        "checkout", root, platform="ios", module="checkout_app",
        out_dir="Tests/Generated", harness_dir="Tests/Generated",
        config_platforms=["ios"])
    text = report.test_file.read_text(encoding="utf-8")
    order = _body_order(text, "func test_submit_branch_1()", [
        "h.settle()", "h.setState(", "rec.mark()", 'h.invoke("submit"',
        "h.settle()\n      XCT", 'rec.unexpectedOps(["submitOrder"])'])
    assert order == sorted(order), order
    assert "func test_submit_branch_2_also_429()" in text


# ---------------------------------------------------------------------------
# the generated Swift test type-checks against XCTest
# ---------------------------------------------------------------------------

def _xctest_typecheck(tmp_path: Path, runtime_edit=None) -> subprocess.CompletedProcess:
    """Type-check the generated test, its runtime and the harness skeleton.

    The generated file is the only place `rec.mark()` and
    `rec.unexpectedOps([...])` are CALLED, and a string assertion cannot tell
    a call that resolves from one that does not. Typed against the macOS SDK's
    XCTest; the one line removed is the `@testable import` of an app module
    this fixture does not have (checked to be exactly one per file).
    """
    tc.tool("xcrun")
    root = _project(tmp_path)
    report = bt.generate_branch_tests(
        "checkout", root, platform="ios", module="checkout_app",
        out_dir="Tests/Generated", harness_dir="Tests/Generated",
        config_platforms=["ios"])
    files = [report.runtime_file, report.harness_file, report.test_file]
    for f in files:
        text = f.read_text(encoding="utf-8")
        if f == report.runtime_file:
            if runtime_edit:
                text = runtime_edit(text)
            f.write_text(text, encoding="utf-8")
            continue
        assert text.count("@testable import checkout_app\n") == 1, f
        f.write_text(text.replace("@testable import checkout_app\n", ""), encoding="utf-8")

    def show(*args: str) -> str:
        return subprocess.run(["xcrun", *args], capture_output=True, text=True,
                              timeout=120).stdout.strip()

    platform = show("--sdk", "macosx", "--show-sdk-platform-path")
    return subprocess.run(
        ["xcrun", "swiftc", "-typecheck", "-sdk", show("--sdk", "macosx", "--show-sdk-path"),
         "-F", f"{platform}/Developer/Library/Frameworks",
         "-I", f"{platform}/Developer/usr/lib", *[str(f) for f in files]],
        capture_output=True, text=True, timeout=600)


def test_the_generated_swift_test_type_checks(tmp_path):
    done = _xctest_typecheck(tmp_path)
    assert done.returncode == 0, done.stderr[:4000]


def test_the_type_check_reads_the_new_call_sites(tmp_path):
    """The control: a runtime whose recorder has no `mark` must not pass."""
    def rename(text: str) -> str:
        assert text.count("func mark()") == 1
        return text.replace("func mark()", "func markRenamed()")

    done = _xctest_typecheck(tmp_path, rename)
    assert done.returncode != 0
    assert "mark" in done.stderr and "error:" in done.stderr, done.stderr[:2000]
