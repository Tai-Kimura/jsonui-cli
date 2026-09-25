"""`settle` returns when the work the act started has landed, not after a fixed
time — measured by RUNNING the runtimes (web and iOS here; Android in
test_branch_settle_quiescence_android.py).

It used to drain a fixed time (iOS 80 x 5 ms, Android 60 x 5 ms, web ten
setTimeout(0) turns) and look only at responses a `delayMs` held back. A view
model that thinks a moment after each response before its next request was
read half done: its `then` red, or — the worse direction — an undeclared call
it makes at the end not yet recorded when `unexpectedOps` was checked, a
vacuous green. Measured 2026-09-25 on 1.8.120's runtimes (settle unchanged
through 1.8.121's rel, ee0bec5c) with the think chain below: web 0/50 links,
iOS 21/50, Android 13/50; web with setTimeout(0) between links 10/15 and
10/40; `unexpectedOps` [] every time.

Now `settle` returns once nothing is in flight and QUIET_MS (declared, 400)
has passed since a request last arrived or was answered; any activity starts
the quiet over. A row that expects ops (its `when` routes, its `called`, its
`.request`) is also waited for until the recorder has each — once nothing is
in flight, up to EXPECT_MS (declared, 10000) after the act, and then it
fails naming them.

The specimens' timings are bound to the declarations, orders of magnitude
away from them:

    specimen                         bound
    think chain, 20 ms x 50 links    gap <= QUIET_MS / 20; 1 s in all, over
                                     twice the old fixed drain
    setTimeout(0) chain, 15 / 40     (web) deeper than the old ten turns
    first request at EXPECT_MS / 5   waited for (5 x QUIET_MS after the act)
    first request at 2 x EXPECT_MS   named at EXPECT_MS

Each has a control that takes the mechanism out (QUIET_MS 0; no expected
ops) and must read the row half done — without it, a probe that never
exercised the wait would pass the same way.

A generated web row also passes vitest its own timeout (ROW_TIMEOUT_MS):
under vitest's default a row that waited for its work ended "Test timed
out in 5000ms", naming nothing. That arm runs the pinned vitest.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from jsonui_test_cli import branch_tests as bt
from tests import _toolchain as tc

#: The think chain: each response, then CHAIN_GAP_MS of "thinking", then the
#: next request; CHAIN_LINKS of them, then one call no row declares (`late`).
CHAIN_GAP_MS = 20
CHAIN_LINKS = 50
#: The expected op's first request, sent this long after the act.
FIRST_SOON_MS = bt.EXPECT_MS // 5
FIRST_LATE_MS = 2 * bt.EXPECT_MS


def test_the_specimens_are_orders_of_magnitude_from_the_declarations():
    assert CHAIN_GAP_MS * 20 <= bt.QUIET_MS
    assert CHAIN_GAP_MS * CHAIN_LINKS >= 1000          # twice the old 0.4 s drain
    assert FIRST_SOON_MS >= 5 * bt.QUIET_MS           # past the quiet: only the wait keeps it
    assert FIRST_SOON_MS * 5 <= bt.EXPECT_MS
    assert FIRST_LATE_MS >= 2 * bt.EXPECT_MS


def test_the_runtimes_declare_the_windows_the_arms_bind_to():
    """One value on every face, and the messages name it."""
    assert (bt.QUIET_MS, bt.EXPECT_MS) == (400, 10000)
    assert "export const QUIET_MS = 400;" in bt.RUNTIME_TS
    assert "export const EXPECT_MS = 10000;" in bt.RUNTIME_TS
    assert "  const val QUIET_MS = 400L\n" in bt.KOTLIN_RUNTIME
    assert "  const val EXPECT_MS = 10000L\n" in bt.KOTLIN_RUNTIME
    assert "  let quietMs = 400\n" in bt.SWIFT_RUNTIME
    assert "  let expectMs = 10000\n" in bt.SWIFT_RUNTIME
    window = "within the act and until no request was in flight for 400 ms after it"
    assert bt.ABSENCE_WINDOW == window
    assert f"({window})" in bt.not_called_message("x")
    assert f"({window})" in bt.UNEXPECTED_OPS_MESSAGE


def _without_the_quiet(runtime: str, declaration: str, zero: str) -> str:
    assert runtime.count(declaration) == 1, declaration
    return runtime.replace(declaration, zero)


# ---------------------------------------------------------------- web ----

_TS_CHAIN = '''import { installFetchMock, settle } from "./runtime.ts";
const ok = { status: 200, body: {} };
const ROUTES: any[] = [
  { op: "link", method: "GET", pattern: "^/link$", scenario: "ok", scenarios: { ok } },
  { op: "late", method: "GET", pattern: "^/late$", scenario: "ok", scenarios: { ok } },
];
const n = Number(process.argv[2]), gap = Number(process.argv[3]);
const rec = installFetchMock(ROUTES, {});
rec.mark();
const vm = { links: 0, done: false };
const hop = () => new Promise((resolve) => setTimeout(resolve, gap));
// The view model: n links, each `gap` ms after the last response; then a
// call no row declares.
void (async () => {
  for (let i = 0; i < n; i++) { await hop(); await fetch("https://x.test/link"); vm.links++; }
  await hop(); await fetch("https://x.test/late"); vm.done = true;
})();
const started = Date.now();
try { await settle(); } catch (e) { console.log(`THROWN ${(e as Error).message}`); }
console.log(`LINKS ${vm.links}`);
console.log(`DONE ${vm.done}`);
console.log(`UNEXPECTED ${JSON.stringify(rec.unexpectedOps(["link"]))}`);
console.log(`WAITED ${Date.now() - started}`);
rec.restore();
process.exit(0);
'''

_TS_FIRST = '''import { installFetchMock, settle } from "./runtime.ts";
const ROUTES: any[] = [{ op: "first", method: "GET", pattern: "^/first$", scenario: "ok",
  scenarios: { ok: { status: 200, body: {} } } }];
const after = Number(process.argv[2]), expecting = process.argv[3] === "expect";
const rec = installFetchMock(ROUTES, {});
rec.mark();
// The view model: one request, `after` ms after the act.
setTimeout(() => void fetch("https://x.test/first"), after);
const started = Date.now();
try { await (expecting ? settle({ rec, expect: ["first"] }) : settle()); }
catch (e) { console.log(`THROWN ${(e as Error).message}`); }
console.log(`COUNT ${rec.countFor("first")}`);
console.log(`WAITED ${Date.now() - started}`);
rec.restore();
process.exit(0);          // a request still due must not hold the process
'''


def _node(tmp_path: Path, runtime: str, probe: str, *args: str) -> dict:
    tc.tool("node")
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "runtime.ts").write_text(runtime, encoding="utf-8")
    (tmp_path / "probe.ts").write_text(probe, encoding="utf-8")
    run = subprocess.run(["node", "--experimental-strip-types", "probe.ts", *args],
                         cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[:3000]
    return dict(line.split(" ", 1) for line in run.stdout.strip().splitlines())


@pytest.mark.parametrize("links, gap", [
    (CHAIN_LINKS, CHAIN_GAP_MS),
    # setTimeout(0) between links: deeper than the ten turns settle drained.
    (15, 0),
    (40, 0),
])
def test_web_settle_waits_out_a_chain_and_sees_the_late_call(tmp_path, links, gap):
    got = _node(tmp_path, bt.RUNTIME_TS, _TS_CHAIN, str(links), str(gap))
    assert "THROWN" not in got, got
    assert (got["LINKS"], got["DONE"]) == (str(links), "true"), got
    assert got["UNEXPECTED"] == '["late"]', got


def test_web_control_without_the_quiet_the_chain_is_read_half_done(tmp_path):
    runtime = _without_the_quiet(bt.RUNTIME_TS, "export const QUIET_MS = 400;",
                                 "export const QUIET_MS = 0;")
    got = _node(tmp_path, runtime, _TS_CHAIN, str(CHAIN_LINKS), str(CHAIN_GAP_MS))
    assert int(got["LINKS"]) < CHAIN_LINKS and got["DONE"] == "false", got
    assert got["UNEXPECTED"] == "[]", got               # the vacuous green


def test_web_an_expected_op_sent_late_is_waited_for(tmp_path):
    got = _node(tmp_path, bt.RUNTIME_TS, _TS_FIRST, str(FIRST_SOON_MS), "expect")
    assert "THROWN" not in got and got["COUNT"] == "1", got
    assert int(got["WAITED"]) >= FIRST_SOON_MS, got


def test_web_control_without_the_expectation_it_is_read_as_never_sent(tmp_path):
    got = _node(tmp_path, bt.RUNTIME_TS, _TS_FIRST, str(FIRST_SOON_MS), "plain")
    assert "THROWN" not in got and got["COUNT"] == "0", got


def test_web_an_expected_op_never_sent_fails_by_name_at_expect_ms(tmp_path):
    got = _node(tmp_path, bt.RUNTIME_TS, _TS_FIRST, str(FIRST_LATE_MS), "expect")
    assert got.get("THROWN", "").startswith(
        "settle: the row expects first, never called within EXPECT_MS (10000 ms) after the act, "
        "0 request(s) in flight (waited "), got
    assert got["COUNT"] == "0", got
    assert bt.EXPECT_MS <= int(got["WAITED"]) < FIRST_LATE_MS, got


# ---------------------------------------------------------------- ios ----

_SWIFT_SHIM = """import Foundation
func XCTFail(_ m: String = "", file: StaticString = #filePath, line: UInt = #line) {
  print("XCTFail \\(m)")
}
func XCTAssertEqual<T: Equatable>(_ a: T, _ b: T, _ m: String = "",
                                  file: StaticString = #filePath, line: UInt = #line) {
  if a != b { XCTFail("\\(a) != \\(b) \\(m)") }
}
func XCTAssertEqual(_ a: Double, _ b: Double, accuracy: Double, _ m: String = "",
                    file: StaticString = #filePath, line: UInt = #line) {
  if abs(a - b) > accuracy { XCTFail("\\(a) != \\(b) \\(m)") }
}
"""

# Requests go through `URLSessionConfiguration.default`, the way a consumer's
# network stack reaches the protocol; the view model's continuation runs on
# the main queue, and its "thinking" is a timer off it.
_SWIFT_MAIN = """import Foundation
final class VM: @unchecked Sendable {
  private let lock = NSLock()
  private var _links = 0
  private var _done = false
  var links: Int { lock.lock(); defer { lock.unlock() }; return _links }
  var done: Bool { lock.lock(); defer { lock.unlock() }; return _done }
  func bump() { lock.lock(); _links += 1; lock.unlock() }
  func finish() { lock.lock(); _done = true; lock.unlock() }
}
let ok = ["ok": (200, "{}", "application/json")]
let routes = [
  RouteSpec(op: "link", method: "GET", pattern: "^/link$", defaultScenario: "ok", scenarios: ok),
  RouteSpec(op: "late", method: "GET", pattern: "^/late$", defaultScenario: "ok", scenarios: ok),
  RouteSpec(op: "first", method: "GET", pattern: "^/first$", defaultScenario: "ok", scenarios: ok),
]
let args = Array(CommandLine.arguments.dropFirst())
let dummy = NSObject()
runBranchTest(routes: routes, overrides: [:], harnessFactory: { BaseBranchHarness(vm: dummy) }) { h, rec in
  rec.mark()
  let session = URLSession(configuration: .default)
  let started = Date()
  if args[0] == "chain" {
    // The view model: n links, each sent `gap` ms after the last response
    // lands; then a call no row declares.
    let n = Int(args[1])!, gap = Int(args[2])!
    let vm = VM()
    func step(_ i: Int) {
      DispatchQueue.global().asyncAfter(deadline: .now() + .milliseconds(gap)) {
        session.dataTask(with: URL(string: "https://example.test/" + (i < n ? "link" : "late"))!) { _, _, _ in
          DispatchQueue.main.async { if i < n { vm.bump(); step(i + 1) } else { vm.finish() } }
        }.resume()
      }
    }
    step(0)
    h.settle()
    print("LINKS \\(vm.links)")
    print("DONE \\(vm.done)")
    print("UNEXPECTED \\(rec.unexpectedOps(["link"]))")
  } else {
    // The view model: one request, `after` ms after the act.
    let after = Int(args[1])!
    DispatchQueue.global().asyncAfter(deadline: .now() + .milliseconds(after)) {
      session.dataTask(with: URL(string: "https://example.test/first")!) { _, _, _ in }.resume()
    }
    if args[2] == "expect" { settleUntilAnswered(h, rec, ["first"]) } else { h.settle() }
    print("COUNT \\(rec.countFor("first"))")
  }
  print("WAITED \\(Int(Date().timeIntervalSince(started) * 1000))")
  session.invalidateAndCancel()
}
"""


def _swift_runtime(runtime: str = bt.SWIFT_RUNTIME) -> str:
    assert runtime.count("\nimport XCTest\n") == 1
    return runtime.replace("\nimport XCTest\n", "\n", 1)


def _build_swift(work: Path, runtime: str) -> Path:
    tc.tool("swiftc")
    work.mkdir(parents=True, exist_ok=True)
    (work / "shim.swift").write_text(_SWIFT_SHIM, encoding="utf-8")
    (work / "runtime.swift").write_text(runtime, encoding="utf-8")
    (work / "main.swift").write_text(_SWIFT_MAIN, encoding="utf-8")
    binary = work / "prog"
    build = subprocess.run(
        ["swiftc", "-Onone", "-o", str(binary), str(work / "shim.swift"),
         str(work / "runtime.swift"), str(work / "main.swift")],
        capture_output=True, text=True, timeout=600)
    assert build.returncode == 0, f"emitted runtime did not compile:\n{build.stderr[:4000]}"
    return binary


def _run_swift(binary: Path, *args: str) -> dict:
    run = subprocess.run([str(binary), *args], capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr[:3000]
    return dict(line.split(" ", 1) for line in run.stdout.strip().splitlines())


@pytest.fixture(scope="module")
def swift_binary(tmp_path_factory) -> Path:
    return _build_swift(tmp_path_factory.mktemp("settle-ios"), _swift_runtime())


def test_ios_settle_waits_out_a_chain_and_sees_the_late_call(swift_binary):
    got = _run_swift(swift_binary, "chain", str(CHAIN_LINKS), str(CHAIN_GAP_MS))
    assert "XCTFail" not in got, got
    assert (got["LINKS"], got["DONE"]) == (str(CHAIN_LINKS), "true"), got
    assert got["UNEXPECTED"] == '["late"]', got


def test_ios_control_without_the_quiet_the_chain_is_read_half_done(tmp_path):
    runtime = _without_the_quiet(_swift_runtime(), "  let quietMs = 400\n", "  let quietMs = 0\n")
    got = _run_swift(_build_swift(tmp_path / "noquiet", runtime),
                     "chain", str(CHAIN_LINKS), str(CHAIN_GAP_MS))
    assert int(got["LINKS"]) < CHAIN_LINKS and got["DONE"] == "false", got
    assert got["UNEXPECTED"] == "[]", got               # the vacuous green


def test_ios_an_expected_op_sent_late_is_waited_for(swift_binary):
    got = _run_swift(swift_binary, "first", str(FIRST_SOON_MS), "expect")
    assert "XCTFail" not in got and got["COUNT"] == "1", got
    assert int(got["WAITED"]) >= FIRST_SOON_MS, got


def test_ios_control_without_the_expectation_it_is_read_as_never_sent(swift_binary):
    got = _run_swift(swift_binary, "first", str(FIRST_SOON_MS), "plain")
    assert "XCTFail" not in got and got["COUNT"] == "0", got


def test_ios_an_expected_op_never_sent_fails_by_name_at_expect_ms(swift_binary):
    got = _run_swift(swift_binary, "first", str(FIRST_LATE_MS), "expect")
    assert got.get("XCTFail", "").startswith(
        "settle: the row expects first, never called within EXPECT_MS (10000 ms) after the act, "
        "0 request(s) in flight (waited "), got
    assert got["COUNT"] == "0", got
    assert bt.EXPECT_MS <= int(got["WAITED"]) < FIRST_LATE_MS, got


# ------------------------------------------------- web, in real vitest ----

#: Past vitest's default testTimeout (5000 ms), which a generated row used to
#: run under: a row that waited that long for its work ended "Test timed out
#: in 5000ms", naming nothing — before this change already, for any
#: `delayMs` over 5 s (measured on 1.8.120: both rows of the feed below).
PAST_VITEST_DEFAULT_MS = 6000


def _feed_with_a_delay(root: Path, *, without_the_row_timeout: bool = False) -> Path:
    import json

    from tests import test_branch_notices_reach_agent_runs as n
    n._write(root / "jui.config.json", json.dumps({"spec_directory": "docs/screens/json",
                                                   "platforms": ["web"]}))
    n._write(root / "docs/screens/json/feed.spec.json", json.dumps(n._FEED_SPEC))
    n._write(root / "tests/mocks/generated/feed.mock.json", json.dumps({
        "source": {"method": "GET", "path": "/api/feed", "operationId": "getFeed"},
        "activeScenario": "default",
        "scenarios": {"default": {"status": 200, "body": [], "delayMs": PAST_VITEST_DEFAULT_MS}}}))
    report = bt.generate_branch_tests("feed", root, platform="web", config_platforms=["web"])
    if without_the_row_timeout:
        text = report.test_file.read_text(encoding="utf-8")
        assert text.count("  }, ROW_TIMEOUT_MS);\n") == 2, text
        report.test_file.write_text(text.replace("  }, ROW_TIMEOUT_MS);\n", "  });\n"), encoding="utf-8")
    n._write(root / "tests/unit/branch-harness/feed.ts", n._FEED_HARNESS)
    n._runner_files(root)
    return root


def _vitest(root: Path) -> tuple[subprocess.CompletedProcess, list[tuple[str, str, str]]]:
    """Run the pinned vitest; each test's (name, outcome, failure message),
    read from the junit reporter's file.

    Not from what vitest prints: that depends on where it runs. On GitHub
    Actions it adds a `::error file=…` annotation carrying each failure's
    message, so a count of "Test timed out in 5000ms" over the output read 4
    there and 2 on a developer machine for the same two timeouts (CI run
    36139124943). The file holds one entry per test whatever the reporters
    around it print. Not the JSON reporter's: vitest 4.1.11 writes a timeout
    there as "Error: STACK_TRACE_ERROR" and a stack, without the message."""
    import xml.etree.ElementTree as ET

    from tests import test_branch_notices_reach_agent_runs as n
    tc.tool("node")
    n._vitest()
    out = root / "vitest-junit.xml"
    run = n._vitest_run(root, {}, "--reporter=junit", f"--outputFile={out}")
    assert out.is_file(), (run.stdout + run.stderr)[-4000:]
    tests = []
    for case in ET.parse(out).getroot().iter("testcase"):
        failure = case.find("failure")
        outcome = ("failed" if failure is not None
                   else "skipped" if case.find("skipped") is not None else "passed")
        tests.append((case.get("name", ""), outcome,
                      "" if failure is None else failure.get("message", "")))
    return run, tests


def test_web_a_row_that_waits_past_vitests_default_timeout_runs_to_its_end(tmp_path):
    assert PAST_VITEST_DEFAULT_MS > 5000
    run, tests = _vitest(_feed_with_a_delay(tmp_path / "p"))
    assert run.returncode == 0 and [s for _, s, _ in tests] == ["passed", "passed"], tests


def test_web_control_without_the_row_timeout_vitest_ends_it_naming_nothing(tmp_path):
    run, tests = _vitest(_feed_with_a_delay(tmp_path / "p", without_the_row_timeout=True))
    assert run.returncode != 0, tests
    # Per test, not per line: each of the two rows failed, and on the timeout.
    assert [(s, "Test timed out in 5000ms" in m) for _, s, m in tests] == [("failed", True)] * 2, tests
