"""A scenario's `delayMs` delays its response in the generated branch tests —
measured by RUNNING the runtimes.

The web runtime's scenario type had `delayMs` and nothing read it; the iOS and
Android runtimes had no field for it. `mock serve` sleeps `min(delayMs,
30000)` before it sends the response, and the mock validator checks the
value, so the same declaration took effect under one tool and not under the
other: a view model whose outcome depends on which of two parallel requests
lands first could not be driven by a row's `when`. A consumer had to write
that red-check by hand.

The meaning is `mock serve`'s: the whole response arrives `delayMs` after the
request, capped at 30000. `settle` waits for every delayed response before
it returns, draining again after each arrival, so a row's `then` reads the
state after they landed; past its budget (one capped delay and a margin) it
fails by name, with how long it waited.

The probe on each face: a view model sends A, then B a gap later (50 ms;
1000 ms in the no-delay row, whose order is the sending order), and records
the order the responses land in. Delays are 3000 ms, the controls' 20000 ms:
these arms have run at a load average above 400, where a fixed drain took
seconds.

    scenario             order    settle
    none                 a, b     returns in under half the budget
    A delayed            b, a     waits for A
    B delayed            a, b     waits for B
    A delayed, no wait   b        (control: settle's wait taken out — A has
                                  not landed when the row would read)

Each delay is far longer than the face's fixed drain (web: ten
setTimeout(0) turns; iOS: 80 x 5 ms), so a settle that did not wait could
not see it land.
Android is in test_branch_scenario_delay_android.py: its runtime needs the
okhttp jars, which only a Gradle cache has.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from jsonui_test_cli import branch_tests as bt
from tests import _toolchain as tc

#: The delayed rows' delay, and how far behind A the probe sends B. A delayed
#: row needs B to land before A: 3000 ms of delay against a 50 ms gap holds
#: under the load average of 400+ these arms have run in (at 700 ms an iOS
#: drain stretched past it).
DELAY_MS = 3000
GAP_MS = 50
#: The no-delay row's gap: it asserts the order the requests were sent in,
#: which a loaded machine can reorder when they are 50 ms apart.
NO_DELAY_GAP_MS = 1000
#: The runtimes' settle budget (one capped delay and a margin) — the no-delay
#: rows are bound to half of it. test_the_runtimes_declare_the_budget
#: holds the three runtimes to this number.
SETTLE_BUDGET_MS = bt.DELAY_CAP_MS + 1000
#: The controls' delay: they take settle's wait out and read before it
#: lands, so it must outlast the fixed drain on a loaded machine — at 700 ms
#: an iOS drain stretched to 804 ms, at 3000 ms to 7190 ms, and the response
#: landed inside it. Inside the 30000 cap.
CONTROL_DELAY_MS = 20000


# ---------------------------------------------------------------- web ----

_TS_PROBE = '''import { installFetchMock, settle } from "./runtime.ts";

const scenarios = { ok: { status: 200, body: {} }, slow: { status: 200, body: {}, delayMs: %(delay)d } };
const ROUTES: any[] = [
  { op: "a", method: "GET", pattern: "^/a$", scenario: "ok", scenarios },
  { op: "b", method: "GET", pattern: "^/b$", scenario: "ok", scenarios },
];
const overrides: Record<string, string> = JSON.parse(process.argv[2]);
const gap = Number(process.argv[3]);
const rec = installFetchMock(ROUTES, overrides);
const order: string[] = [];
const started = Date.now();
// The view model: A, then B `gap` ms later; fire-and-forget, like a screen load.
void fetch("https://x.test/a").then(() => order.push("a"));
setTimeout(() => void fetch("https://x.test/b").then(() => order.push("b")), gap);
await new Promise((resolve) => setTimeout(resolve, gap + 10));
try {
  await settle();
  console.log(`ORDER ${order.join(",")}`);
} catch (e) {
  console.log(`THROWN ${(e as Error).message}`);
}
console.log(`WAITED ${Date.now() - started}`);
rec.restore();
process.exit(0);          // a delayed response still due must not hold the process
'''


def _run_web(tmp_path: Path, overrides: dict, runtime: str | None = None,
             delay: int = DELAY_MS, gap: int = GAP_MS) -> dict:
    tc.tool("node")
    (tmp_path / "runtime.ts").write_text(runtime or bt.RUNTIME_TS, encoding="utf-8")
    (tmp_path / "probe.ts").write_text(_TS_PROBE % {"delay": delay}, encoding="utf-8")
    run = subprocess.run(["node", "--experimental-strip-types", "probe.ts", json.dumps(overrides), str(gap)],
                         cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[:3000]
    return dict(line.split(" ", 1) for line in run.stdout.strip().splitlines())


@pytest.mark.parametrize("overrides, order, waits, gap", [
    ({}, "a,b", False, NO_DELAY_GAP_MS),
    ({"a": "slow"}, "b,a", True, GAP_MS),
    ({"b": "slow"}, "a,b", True, GAP_MS),
])
def test_web_the_delay_decides_the_order_and_settle_waits(tmp_path, overrides, order, waits, gap):
    got = _run_web(tmp_path, overrides, gap=gap)
    assert got.get("ORDER") == order, got
    # Timed against the DECLARED budget, not the machine: a delayed row waits
    # at least the delay; the no-delay row returns in under half the budget.
    # A loaded machine stretched iOS's fixed drain to 7190 ms (and the no-delay
    # row to 999 ms) and passes; a settle that always waits the budget out
    # (31 s) fails.
    waited = int(got["WAITED"])
    if waits:
        assert waited >= DELAY_MS, got
    else:
        assert waited < SETTLE_BUDGET_MS // 2, got


def _web_without_the_wait(runtime: str) -> str:
    """settle returning after its first drain, whatever is still pending."""
    quiet = "    if (pendingDeliveries.size === 0 && lastDeliveryAt < drainStarted) return;\n"
    assert runtime.count(quiet) == 1
    return runtime.replace(quiet, "    return;\n")


def test_web_control_a_settle_that_does_not_wait_reads_before_the_arrival(tmp_path):
    got = _run_web(tmp_path, {"a": "slow"}, _web_without_the_wait(bt.RUNTIME_TS), CONTROL_DELAY_MS)
    assert got.get("ORDER") == "b", got


_WEB_CHAIN = '''import { installFetchMock, settle } from "./runtime.ts";
const ROUTES: any[] = [{ op: "a", method: "GET", pattern: "^/a$", scenario: "slow",
  scenarios: { slow: { status: 200, body: {}, delayMs: 100 } } }];
const rec = installFetchMock(ROUTES);
// Each arrival sends the next request: a chain of delays.
const next = (): void => { void fetch("https://x.test/a").then(next); };
next();
try { await settle(); console.log("RETURNED"); }
catch (e) { console.log(`THROWN ${(e as Error).message}`); }
rec.restore();
process.exit(0);
'''


def test_web_past_the_budget_settle_fails_by_name(tmp_path):
    """A chain of delays longer than the budget. The budget is shortened in
    this copy of the runtime (one capped delay of 100 ms, budget 1100 ms), so
    the arm takes a second and not thirty."""
    tc.tool("node")
    runtime = bt.RUNTIME_TS
    assert runtime.count("export const DELAY_CAP_MS = 30000;") == 1
    runtime = runtime.replace("export const DELAY_CAP_MS = 30000;", "export const DELAY_CAP_MS = 100;")
    (tmp_path / "runtime.ts").write_text(runtime, encoding="utf-8")
    (tmp_path / "probe.ts").write_text(_WEB_CHAIN, encoding="utf-8")
    run = subprocess.run(["node", "--experimental-strip-types", "probe.ts"],
                         cwd=tmp_path, capture_output=True, text=True, timeout=120)
    out = run.stdout.strip()
    assert out.startswith("THROWN settle: delayed responses were still arriving after waiting "), out
    waited = int(re.search(r"after waiting (\d+) ms", out).group(1))
    assert waited >= 1100 and "budget 1100 ms" in out, out


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
# network stack reaches the protocol; landings are recorded on the main queue,
# where a view model's continuation would run.
_SWIFT_MAIN = """import Foundation
final class Landings: @unchecked Sendable {
  private let lock = NSLock()
  private var names: [String] = []
  func add(_ name: String) { lock.lock(); names.append(name); lock.unlock() }
  var order: String { lock.lock(); defer { lock.unlock() }; return names.joined(separator: ",") }
}
let scenarios = ["ok": (200, "{}", "application/json"), "slow": (200, "{}", "application/json")]
let routes = [
  RouteSpec(op: "a", method: "GET", pattern: "^/a$", defaultScenario: "ok",
            scenarios: scenarios, delays: ["slow": %(delay)d]),
  RouteSpec(op: "b", method: "GET", pattern: "^/b$", defaultScenario: "ok",
            scenarios: scenarios, delays: ["slow": %(delay)d]),
]
var overrides: [String: String] = [:]
var gap = 50
for arg in CommandLine.arguments.dropFirst() {
  if arg.hasPrefix("gap=") { gap = Int(arg.dropFirst(4)) ?? 50 } else { overrides[arg] = "slow" }
}
let dummy = NSObject()
runBranchTest(routes: routes, overrides: overrides,
              harnessFactory: { BaseBranchHarness(vm: dummy) }) { h, _ in
  let session = URLSession(configuration: .default)
  let landings = Landings()
  let started = Date()
  for name in ["a", "b"] {
    session.dataTask(with: URL(string: "https://example.test/" + name)!) { _, _, _ in
      DispatchQueue.main.async { landings.add(name) }
    }.resume()
    Thread.sleep(forTimeInterval: Double(gap) / 1000)
  }
  h.settle()
  print("ORDER \\(landings.order)")
  print("WAITED \\(Int(Date().timeIntervalSince(started) * 1000))")
  session.invalidateAndCancel()
}
"""


@pytest.fixture(scope="module")
def swift_runtime() -> str:
    runtime = bt.SWIFT_RUNTIME
    assert runtime.count("\nimport XCTest\n") == 1
    return runtime.replace("\nimport XCTest\n", "\n", 1)


def _build_swift(work: Path, runtime: str, main: str = _SWIFT_MAIN, delay: int = DELAY_MS) -> Path:
    tc.tool("swiftc")
    work.mkdir(parents=True, exist_ok=True)
    (work / "shim.swift").write_text(_SWIFT_SHIM, encoding="utf-8")
    (work / "runtime.swift").write_text(runtime, encoding="utf-8")
    (work / "main.swift").write_text(main % {"delay": delay}, encoding="utf-8")
    binary = work / "prog"
    build = subprocess.run(
        ["swiftc", "-Onone", "-o", str(binary), str(work / "shim.swift"),
         str(work / "runtime.swift"), str(work / "main.swift")],
        capture_output=True, text=True, timeout=600)
    assert build.returncode == 0, f"emitted runtime did not compile:\n{build.stderr[:4000]}"
    return binary


def _run_swift(binary: Path, *slow: str, gap: int = GAP_MS) -> dict:
    run = subprocess.run([str(binary), *slow, f"gap={gap}"], capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr[:3000]
    return dict(line.split(" ", 1) for line in run.stdout.strip().splitlines())


@pytest.fixture(scope="module")
def swift_binary(swift_runtime, tmp_path_factory) -> Path:
    return _build_swift(tmp_path_factory.mktemp("delay-ios"), swift_runtime)


@pytest.mark.parametrize("slow, order, waits, gap", [
    ((), "a,b", False, NO_DELAY_GAP_MS),
    (("a",), "b,a", True, GAP_MS),
    (("b",), "a,b", True, GAP_MS),
])
def test_ios_the_delay_decides_the_order_and_settle_waits(swift_binary, slow, order, waits, gap):
    got = _run_swift(swift_binary, *slow, gap=gap)
    assert got.get("ORDER") == order, got
    # Timed against the DECLARED budget, not the machine: a delayed row waits
    # at least the delay; the no-delay row returns in under half the budget.
    # A loaded machine stretched iOS's fixed drain to 7190 ms (and the no-delay
    # row to 999 ms) and passes; a settle that always waits the budget out
    # (31 s) fails.
    waited = int(got["WAITED"])
    if waits:
        assert waited >= DELAY_MS, got
    else:
        assert waited < SETTLE_BUDGET_MS // 2, got
    assert "XCTFail" not in got, got


def _swift_without_the_wait(runtime: str) -> str:
    """settle returning after its first drain, whatever is still pending."""
    quiet = "      if BranchDeliveries.shared.pending == 0 && BranchDeliveries.shared.lastDelivery < drainStarted {\n"
    assert runtime.count(quiet) == 1
    return runtime.replace(quiet, "      if true {\n")


def test_ios_control_a_settle_that_does_not_wait_reads_before_the_arrival(swift_runtime, tmp_path):
    binary = _build_swift(tmp_path / "nowait", _swift_without_the_wait(swift_runtime),
                          delay=CONTROL_DELAY_MS)
    got = _run_swift(binary, "a")
    assert got.get("ORDER") == "b", got


_SWIFT_CHAIN = """import Foundation
let routes = [RouteSpec(op: "a", method: "GET", pattern: "^/a$", defaultScenario: "slow",
                        scenarios: ["slow": (200, "{}", "application/json")], delays: ["slow": 100])]
let dummy = NSObject()
runBranchTest(routes: routes, overrides: [:], harnessFactory: { BaseBranchHarness(vm: dummy) }) { h, _ in
  let session = URLSession(configuration: .default)
  // Each arrival sends the next request: a chain of delays.
  final class Chain: @unchecked Sendable {
    let session: URLSession
    init(_ s: URLSession) { session = s }
    func next() {
      session.dataTask(with: URL(string: "https://example.test/a")!) { _, _, _ in self.next() }.resume()
    }
  }
  Chain(session).next()
  h.settle()
  print("RETURNED")
  session.invalidateAndCancel()
}
"""


def test_ios_past_the_budget_settle_fails_by_name(swift_runtime, tmp_path):
    """A chain of delays longer than the budget, in a runtime whose cap is
    shortened to 100 ms (budget 1100 ms) so the arm takes a second."""
    cap = "  let capMs = 30000\n"
    assert swift_runtime.count(cap) == 1
    binary = _build_swift(tmp_path / "chain", swift_runtime.replace(cap, "  let capMs = 100\n"),
                          _SWIFT_CHAIN)
    run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=300)
    fails = [l for l in run.stdout.splitlines() if l.startswith("XCTFail settle: ")]
    assert len(fails) == 1 and "delayed responses were still arriving after waiting" in fails[0], run.stdout
    waited = int(re.search(r"after waiting (\d+) ms", fails[0]).group(1))
    assert waited >= 1100 and "budget 1100 ms" in fails[0], fails


def test_the_runtimes_declare_the_budget_the_arms_bound_against():
    assert SETTLE_BUDGET_MS == 31000
    assert "export const DELAY_CAP_MS = 30000;" in bt.RUNTIME_TS
    assert "export const SETTLE_DELAY_BUDGET_MS = DELAY_CAP_MS + 1000;" in bt.RUNTIME_TS
    assert "  let capMs = 30000\n" in bt.SWIFT_RUNTIME
    assert "  var settleBudgetMs: Int { capMs + 1000 }\n" in bt.SWIFT_RUNTIME
    assert "  const val CAP_MS = 30000L\n" in bt.KOTLIN_RUNTIME
    assert "  const val SETTLE_BUDGET_MS = CAP_MS + 1000L\n" in bt.KOTLIN_RUNTIME


# ------------------------------------------------------ generated files ----

def _mock(root: Path, name: str, path: str, operation_id: str, scenarios: dict) -> None:
    target = root / "tests/mocks/generated" / f"{name}.mock.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "source": {"method": "GET", "path": path, "operationId": operation_id},
        "activeScenario": "default", "scenarios": scenarios}), encoding="utf-8")


def _project(root: Path, *, delay) -> Path:
    """A screen whose load sends two requests; the staff route's `slow`
    scenario carries `delayMs` (or no such scenario when `delay` is None)."""
    spec_dir = root / "docs/screens/json"
    spec_dir.mkdir(parents=True)
    (root / "jui.config.json").write_text(json.dumps(
        {"spec_directory": "docs/screens/json", "platforms": ["web", "ios", "android"]}),
        encoding="utf-8")
    (spec_dir / "roles.spec.json").write_text(json.dumps({
        "type": "screen_spec", "metadata": {"name": "roles"},
        "dataFlow": {
            "viewModel": {"methods": [{"name": "load"}]},
            "repositories": [{"name": "RoleRepository", "methods": [
                {"name": "getStaff", "endpoint": "GET /api/staff"},
                {"name": "getRoles", "endpoint": "GET /api/roles"}]}]},
        "branchContracts": {"methods": {"load": {"branches": [
            {"when": {"api.getStaff": "slow" if delay is not None else "default",
                      "api.getRoles": "default"},
             "then": {"data.notice": "shown"}}]}}}}), encoding="utf-8")
    staff = {"default": {"status": 200, "body": []}}
    if delay is not None:
        staff["slow"] = {"status": 200, "body": [], "delayMs": delay}
    _mock(root, "staff", "/api/staff", "getStaff", staff)
    _mock(root, "roles", "/api/roles", "getRoles", {"default": {"status": 200, "body": []}})
    return root


def _generated(root: Path, platform: str) -> str:
    report = bt.generate_branch_tests("roles", root, platform=platform, module="roles_app",
                                      package="com.example.roles", out_dir="Tests/Generated",
                                      harness_dir="Tests/Generated",
                                      config_platforms=["web", "ios", "android"])
    return report.test_file.read_text(encoding="utf-8")


def test_the_mobile_routes_carry_the_delay_of_the_route_that_has_one(tmp_path):
    root = _project(tmp_path / "p", delay=700)
    swift, kotlin, web = (_generated(root, p) for p in ("ios", "android", "web"))
    assert swift.count('delays: ["slow": 700]') == 1, swift
    assert kotlin.count('mapOf("slow" to 700L)') == 1, kotlin
    assert web.count('"delayMs": 700') == 1, web            # the web routes carry scenarios whole


def test_a_screen_without_a_delay_generates_no_delays(tmp_path):
    """No `delayMs` anywhere: the route lines are what they were (the
    parameter defaults to empty), so the generated file does not move."""
    root = _project(tmp_path / "p", delay=None)
    assert "delays:" not in _generated(root, "ios")
    kotlin = _generated(root, "android")
    assert not re.search(r"to \d+L\)", kotlin), kotlin


def test_the_scenario_delay_is_read_as_the_runtimes_apply_it():
    assert [bt._scenario_delay_ms({"delayMs": v}) for v in
            (None, 0, -5, True, "700", 700, 12.7, 45000)] == [0, 0, 0, 0, 0, 700, 12, 30000]
    assert bt._scenario_delay_ms({}) == 0
