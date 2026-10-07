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

Now a generated row's wait — `settle()` on iOS and Android, the runtime's
`settleQuiet` on web — returns once nothing is in flight and QUIET_MS
(declared, 400) has passed since a request last arrived or was answered; any
activity starts the quiet over. A row that expects ops (its `when` routes, its `called`, its
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

Under a test's fake clock (ticket test-branch-runtime-web-settle-loops-
forever-under-a-frozen-date-and-drops-the-turns-argument, 1.9.0): the web
runtime measured the quiet window and both budgets with `Date.now()` read
when settle ran, so a test that froze Date (`vi.useFakeTimers({ toFake:
["Date"] })` + `vi.setSystemTime`, the usual way to pin "today") made every
settle loop until the runner's own timeout, naming nothing; and 1.8.120's
`settle(turns)` threw a TypeError, the number read as `until`. The runtime
now takes its clock (performance.now) and its timer when it loads; the
window a row waits over is `settleQuiet`, what the generated rows call; and
`settle()` / `settle(n)` — what a hand-written test calls — do what they did
in 1.8.120 again: drain the turns (ten without a number) and wait for the
delayed responses, with no quiet window. Those arms run the pinned vitest
with the fakes the way a test installs them — inside the case, and before
the runtime is imported — and each part of the change has a control that
takes it out and must turn its own cases red, and only those.
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

_TS_CHAIN = '''import { installFetchMock, settleQuiet } from "./runtime.ts";
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
try { await settleQuiet(); } catch (e) { console.log(`THROWN ${(e as Error).message}`); }
console.log(`LINKS ${vm.links}`);
console.log(`DONE ${vm.done}`);
console.log(`UNEXPECTED ${JSON.stringify(rec.unexpectedOps(["link"]))}`);
console.log(`WAITED ${Date.now() - started}`);
rec.restore();
process.exit(0);
'''

_TS_FIRST = '''import { installFetchMock, settleQuiet } from "./runtime.ts";
const ROUTES: any[] = [{ op: "first", method: "GET", pattern: "^/first$", scenario: "ok",
  scenarios: { ok: { status: 200, body: {} } } }];
const after = Number(process.argv[2]), expecting = process.argv[3] === "expect";
const rec = installFetchMock(ROUTES, {});
rec.mark();
// The view model: one request, `after` ms after the act.
setTimeout(() => void fetch("https://x.test/first"), after);
const started = Date.now();
try { await (expecting ? settleQuiet({ rec, expect: ["first"] }) : settleQuiet()); }
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


# ------------------------------------------- web, the early close ----
#
# Ticket test-branch-web-generated-rows-take-800ms-each-under-the-quiet-window:
# every generated row waited the quiet window twice, 800 ms at the least,
# whatever it did. settleQuiet now also closes once nothing is due — no
# request in flight, no delayed response, no timer the row scheduled through
# setTimeout / setInterval — for ten idle turns; a timer due keeps the quiet
# window, and a timer past it is not waited for. settleHarness (the wait
# after building the harness) skips when construction did nothing.

#: A view model's late call: sent this long after the act, from a timer —
#: inside the quiet window, far past the ten idle turns of the early close.
TIMER_LATE_MS = bt.QUIET_MS // 2
#: A setInterval's period, and the tick that sends the late call.
TICK_MS, TICKS = 50, 3
#: A timer far past the quiet window: never waited for.
FAR_MS = 600000
#: What "closed early" means here: well under the quiet window it replaced.
EARLY_MS = bt.QUIET_MS // 2


def test_the_early_close_specimens_are_bound_to_the_declarations():
    assert 10 * 5 < TIMER_LATE_MS < bt.QUIET_MS       # past ten polls, inside the window
    assert TICK_MS * TICKS < bt.QUIET_MS
    assert FAR_MS >= 100 * bt.QUIET_MS
    assert EARLY_MS <= bt.QUIET_MS // 2


_TS_TIMERS = """import { installFetchMock, settleHarness, settleQuiet } from "./runtime.ts";
const ok = { status: 200, body: {} };
const ROUTES: any[] = [
  { op: "late", method: "GET", pattern: "^/late$", scenario: "ok", scenarios: { ok } },
];
const mode = process.argv[2];
// The timer a fake installed after the install would run on: its own, not
// the one the row watches.
const unseenSetTimeout = globalThis.setTimeout;
const LATE = TIMER_LATE_MS, TICK = TICK_MS, TICKS_N = TICKS, FAR = FAR_MS;
const rec = installFetchMock(ROUTES, {}, null, "early-close");
const late = (): void => void fetch("https://x.test/late");
let fired = false;
let cleanup = (): void => {};
const started = Date.now();
if (mode === "harness-nothing" || mode === "harness-timer") {
  // A constructor: nothing, or state loaded LATE ms later from a timer.
  const vm = { loaded: false };
  if (mode === "harness-timer") setTimeout(() => { vm.loaded = true; }, LATE);
  try { await settleHarness(); } catch (e) { console.log(`THROWN ${(e as Error).message}`); }
  console.log(`LOADED ${vm.loaded}`);
} else {
  rec.mark();
  // The act: what the view model left behind.
  if (mode === "late-timeout") setTimeout(() => { fired = true; late(); }, LATE);
  if (mode === "late-interval") {
    let ticks = 0;
    const t = setInterval(() => { ticks += 1; if (ticks === TICKS_N) { clearInterval(t); fired = true; late(); } }, TICK);
  }
  if (mode === "far-interval") {
    const t = setInterval(() => { fired = true; }, FAR);
    cleanup = () => clearInterval(t);
  }
  if (mode === "far-timeout") {
    const t = setTimeout(() => { fired = true; }, FAR);
    cleanup = () => clearTimeout(t);
  }
  if (mode === "cleared") clearTimeout(setTimeout(() => { fired = true; late(); }, LATE));
  if (mode === "cleared-by-number") clearTimeout(Number(setTimeout(() => { fired = true; late(); }, LATE)));
  if (mode === "displaced") {
    // A test replaced the timers after the install (vi.useFakeTimers() in
    // the row, say): the row cannot see what is scheduled on them.
    (globalThis as any).setTimeout = (f: () => void, ms: number) => unseenSetTimeout(f, ms);
    setTimeout(() => { fired = true; late(); }, LATE);
  }
  try { await settleQuiet(); } catch (e) { console.log(`THROWN ${(e as Error).message}`); }
}
console.log(`WAITED ${Date.now() - started}`);
console.log(`FIRED ${fired}`);
console.log(`UNEXPECTED ${JSON.stringify(rec.unexpectedOps([]))}`);
cleanup();
rec.restore();
process.exit(0);
""".replace("TIMER_LATE_MS", str(TIMER_LATE_MS)).replace("TICK_MS", str(TICK_MS)).replace(
    "= TICKS,", f"= {TICKS},").replace("FAR_MS", str(FAR_MS))


def _timers(tmp_path: Path, mode: str, runtime: str = bt.RUNTIME_TS) -> dict:
    return _node(tmp_path, runtime, _TS_TIMERS, mode)


def test_web_nothing_due_closes_early(tmp_path):
    got = _timers(tmp_path, "nothing")
    assert "THROWN" not in got and got["UNEXPECTED"] == "[]", got
    assert int(got["WAITED"]) < EARLY_MS, got


def test_web_control_without_the_early_close_nothing_due_waits_the_window(tmp_path):
    got = _timers(tmp_path, "nothing", _without("early"))
    assert int(got["WAITED"]) >= bt.QUIET_MS, got


@pytest.mark.parametrize("mode, sent_at", [
    ("late-timeout", TIMER_LATE_MS),
    ("late-interval", TICK_MS * TICKS),
])
def test_web_a_late_call_from_a_view_model_timer_is_still_caught(tmp_path, mode, sent_at):
    """The arm the quiet window exists for: an undeclared call the view model
    sends from a timer, inside the window, reads in `unexpectedOps` — and the
    row closes soon after it, not QUIET_MS after it."""
    got = _timers(tmp_path, mode)
    assert "THROWN" not in got and got["FIRED"] == "true", got
    assert got["UNEXPECTED"] == '["late"]', got
    assert sent_at <= int(got["WAITED"]) < sent_at + bt.QUIET_MS, got


def test_web_control_without_the_timer_watch_the_late_call_is_a_vacuous_green(tmp_path):
    got = _timers(tmp_path, "late-timeout", _without("watch"))
    assert got["FIRED"] == "false" and got["UNEXPECTED"] == "[]", got


def test_web_control_an_interval_read_as_done_after_one_tick_misses_the_late_call(tmp_path):
    got = _timers(tmp_path, "late-interval", _without("interval"))
    assert got["FIRED"] == "false" and got["UNEXPECTED"] == "[]", got


@pytest.mark.parametrize("mode", ["far-timeout", "far-interval"])
def test_web_a_timer_past_the_window_keeps_the_window_and_is_not_waited_for(tmp_path, mode):
    """A timer due takes the early close away; it never holds the row past
    the quiet window — a setInterval never cleared, a setTimeout of minutes."""
    got = _timers(tmp_path, mode)
    assert "THROWN" not in got and got["FIRED"] == "false", got
    assert bt.QUIET_MS <= int(got["WAITED"]) < 10 * bt.QUIET_MS, got


@pytest.mark.parametrize("mode", ["cleared", "cleared-by-number"])
def test_web_a_cleared_timer_is_not_due(tmp_path, mode):
    got = _timers(tmp_path, mode)
    assert "THROWN" not in got and got["FIRED"] == "false", got
    assert int(got["WAITED"]) < EARLY_MS, got


def test_web_timers_replaced_after_the_install_keep_the_window(tmp_path):
    got = _timers(tmp_path, "displaced")
    assert "THROWN" not in got and got["UNEXPECTED"] == '["late"]', got
    assert int(got["WAITED"]) >= bt.QUIET_MS, got


def test_web_control_a_watch_that_misses_the_replacement_misses_the_late_call(tmp_path):
    got = _timers(tmp_path, "displaced", _without("displaced"))
    assert got["FIRED"] == "false" and got["UNEXPECTED"] == "[]", got


def test_web_the_harness_wait_skips_when_construction_did_nothing(tmp_path):
    got = _timers(tmp_path, "harness-nothing")
    assert "THROWN" not in got and got["LOADED"] == "false", got
    assert int(got["WAITED"]) < EARLY_MS, got


def test_web_the_harness_wait_waits_for_a_constructor_timer(tmp_path):
    got = _timers(tmp_path, "harness-timer")
    assert "THROWN" not in got and got["LOADED"] == "true", got
    assert TIMER_LATE_MS <= int(got["WAITED"]) < TIMER_LATE_MS + bt.QUIET_MS, got


def test_web_control_without_the_skip_the_harness_wait_is_settle_quiet(tmp_path):
    """The skip is what makes it shorter than settleQuiet: without it (and
    without the early close) a harness that did nothing waits the window."""
    got = _timers(tmp_path, "harness-nothing", _without("harness-skip", "early"))
    assert int(got["WAITED"]) >= bt.QUIET_MS, got


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


# ------------------------------------- web, under a test's fake clock ----

#: How long a case gives settle, in real time, before reading it as 1.9.0's
#: loop ("still waiting"): past every return the passing cases make — the
#: quiet window, and the shortened budget and EXPECT_MS below.
STILL_MS = 3000
#: The same for the cases whose clock was frozen before the runtime loaded:
#: settle names it after STALLED_POLLS polls, or STALLED_TURNS turns —
#: a second at the least, more on a loaded machine.
STILL_BEFORE_IMPORT_MS = 10000
#: The copy of the runtime the named-failure cases run: one capped delay of
#: SHORT_CAP_MS (the budget is that and 1000 ms) and EXPECT_MS of
#: SHORT_EXPECT_MS, so the cases take a second and not thirty.
SHORT_CAP_MS, SHORT_EXPECT_MS = 100, 1000
#: A delayed response in flight when `settle(20)` is called: far past the
#: twenty turns it drains, so only its wait for the delivery gets it read.
DELIVERY_MS = 300
#: The event loop held up this long by synchronous work: the quiet window has
#: passed by the first poll after it.
HELD_MS = 2 * bt.QUIET_MS
#: Below this a settle "returned within QUIET_MS" (timed()). Half the quiet
#: window, not the window itself: a settle that waits the window out — the
#: "until" control's mutant — takes QUIET_MS, and a real timer that fires a
#: fraction early, rounded, read 399 and passed as fast (release-check run
#: 37650040409, ticket test-branch-settle-control-real-clock-threshold-sits-
#: on-the-mutants-wait). The fast paths drain turns: settle(40), the longest,
#: took 52 ms here (2026-10-08); forty turns at a browser's clamped 4 ms each
#: would be 160.
FAST_MS = bt.QUIET_MS // 2


def test_the_fake_clock_specimens_are_bound_to_the_declarations():
    assert STILL_MS >= 7 * bt.QUIET_MS
    assert STILL_MS >= 2 * (SHORT_CAP_MS + 1000) and STILL_MS >= 2 * SHORT_EXPECT_MS
    assert STILL_MS >= 5 * DELIVERY_MS
    assert "const STALLED_POLLS = 200;" in bt.RUNTIME_TS
    assert "const STALLED_TURNS = 200;" in bt.RUNTIME_TS
    assert STILL_BEFORE_IMPORT_MS >= 10 * 200 * 5
    assert HELD_MS > bt.QUIET_MS
    # Away from the mutant's wait on one side and from forty clamped turns on the other.
    assert FAST_MS <= bt.QUIET_MS // 2
    assert FAST_MS > 40 * 4
    assert "const DEFAULT_SETTLE_TURNS = 10;" in bt.RUNTIME_TS


_CLOCK_RACE_TS = '''// The real timers and clock, taken when this helper loads — a static import
// runs before any case, or its file's own top level, fakes one — so each case
// ends, and is timed, on real time whatever it did to the clock.
const wall = globalThis.setTimeout;
const unwall = globalThis.clearTimeout;
const wallNow = performance.now.bind(performance);

export const TODAY = new Date("2026-07-20T10:00:00+09:00");

/** What `p` did within `ms` of real time: "returned", "threw: <message>", or
 * "still waiting after <ms> ms of real time" — 1.9.0's loop under a frozen
 * clock, which neither returned nor threw. */
export function outcome(p: Promise<unknown>, ms = STILL_MS): Promise<string> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const late = new Promise<string>((resolve) => {
    timer = wall(() => resolve(`still waiting after ${ms} ms of real time`), ms);
  });
  return Promise.race([p.then(() => "returned", (e: Error) => `threw: ${e.message}`), late])
    .finally(() => unwall(timer));
}

/** Below this it returned "within QUIET_MS": half of it, so a settle that
 * waits the window out reads as slow even when the timer fires early. */
export const FAST_MS = FAST_MS_VALUE;

/** The outcome, and whether it returned well before QUIET_MS of real time —
 * the least a settle with the quiet window takes. `now` is the clock it is
 * timed on: real time, or a stand-in in the threshold's own cases. */
export async function timed(p: Promise<unknown>, now: () => number = wallNow): Promise<string> {
  const started = now();
  const got = await outcome(p);
  const took = Math.round(now() - started);
  if (got !== "returned") return got;
  return took < FAST_MS ? "returned within QUIET_MS" : `returned in ${took} ms, not under QUIET_MS / 2 (FAST_MS_VALUE ms)`;
}

/** Fail with the whole outcome in the message — an assertion library cuts a
 * long value short — so the report says which way the case went. */
export function must(got: string, want: string | RegExp): void {
  if (typeof want === "string" ? got !== want : !want.test(got)) throw new Error(`OUTCOME ${got}`);
}
'''.replace("STILL_MS", str(STILL_MS)).replace("FAST_MS_VALUE", str(FAST_MS))


#: Faked inside each case, after the runtime was imported — the usual place.
#: The settle() cases run before any delayed response lands in this file:
#: settle(turns) reads the module-wide time of the last one.
_CLOCK_AFTER_IMPORT_TS = r'''import { it, vi, afterEach } from "vitest";
import { installFetchMock, settle, settleQuiet, type RouteSpec } from "./generated/jsonui-branch-runtime";
import * as short from "./generated/short-budget-runtime";
import { TODAY, must, outcome, timed } from "./race";

afterEach(() => { vi.useRealTimers(); });

// The ways a test pins "today", or takes the timers over.
const FAKES: Record<string, () => void> = {
  "Date": () => { vi.useFakeTimers({ toFake: ["Date"] }); vi.setSystemTime(TODAY); },
  "Date, setInterval, clearInterval": () => {
    vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"] });
    vi.setSystemTime(TODAY);
  },
  "setSystemTime alone": () => { vi.setSystemTime(TODAY); },
  "every timer": () => { vi.useFakeTimers(); vi.setSystemTime(TODAY); },
};
const REAL = (): void => {};
const CLOCKS: [string, () => void][] = [["real clock", REAL],
  ...Object.entries(FAKES).map(([fake, install]): [string, () => void] => [`fake: ${fake}`, install])];

// A view model's timer far past the quiet window, scheduled after the install
// so the row watches it: it takes the early close away, and the case measures
// the quiet window — on the clock the runtime took — as it did before there
// was an early close. Cleared when the case ends.
function hold(): () => void {
  const t = setTimeout(() => {}, 600000);
  return () => clearTimeout(t);
}

function route(op: string, delayMs?: number): RouteSpec {
  const ok = delayMs === undefined ? { status: 200, body: {} } : { status: 200, body: {}, delayMs };
  return { op, method: "GET", pattern: `^/${op}$`, scenario: "ok", scenarios: { ok } };
}

// The generated row's wait: the quiet window, on a clock the fake leaves alone.
for (const [fake, install] of Object.entries(FAKES)) {
  it(`settleQuiet() returns — fake: ${fake}`, async () => {
    install();
    const rec = installFetchMock([], {}, null, fake);
    const release = hold();
    try { must(await outcome(settleQuiet()), "returned"); } finally { release(); rec.restore(); }
  }, 10000);
}

// Nothing due: the early close, which reads no clock — so a frozen one
// cannot hold it, and it takes about ten turns, not QUIET_MS.
for (const fake of ["Date", "every timer"]) {
  it(`settleQuiet() closes early with nothing due — fake: ${fake}`, async () => {
    FAKES[fake]();
    const rec = installFetchMock([], {}, null, `early ${fake}`);
    try { must(await timed(settleQuiet()), "returned within QUIET_MS"); } finally { rec.restore(); }
  }, 10000);
}

// A hand-written test's settle(): 1.8.120's ten turns — no quiet window.
for (const [clock, install] of CLOCKS) {
  it(`settle() returns within QUIET_MS — ${clock}`, async () => {
    install();
    const rec = installFetchMock([], {}, null, "no-arg");
    try { must(await timed(settle()), "returned within QUIET_MS"); } finally { rec.restore(); }
  }, 10000);
}

// The 1.8.120 call with a number of turns: what it did then — no quiet window.
for (const turns of [2, 20, 40]) {
  it(`settle(${turns}) returns within QUIET_MS — real clock`, async () => {
    const rec = installFetchMock([], {}, null, "turns");
    try { must(await timed(settle(turns)), "returned within QUIET_MS"); } finally { rec.restore(); }
  }, 10000);
}

it("settle(20) returns within QUIET_MS — fake: Date", async () => {
  FAKES["Date"]();
  const rec = installFetchMock([], {}, null, "turns");
  try { must(await timed(settle(20)), "returned within QUIET_MS"); } finally { rec.restore(); }
}, 10000);

// ...and it waits for a response a delayMs holds back, as it did then.
for (const [clock, install] of [["real clock", REAL], ["fake: Date", FAKES["Date"]]] as const) {
  it(`settle(20) waits for a delayed response in flight — ${clock}`, async () => {
    install();
    const rec = installFetchMock([route("slow", DELIVERY_MS)], {}, null, "delivery");
    let arrived = false;
    void fetch("https://x.test/slow").then(() => { arrived = true; });
    try {
      must(await outcome(settle(20)), "returned");
      must(`arrived ${arrived}`, "arrived true");
    } finally { rec.restore(); }
  }, 10000);
}

// A generated row's form: wait for the op the row expects — through
// settleQuiet, and through settle({ rec, expect }), what a 1.9.0 row called.
for (const [name, wait] of [["settleQuiet", settleQuiet], ["settle", settle]] as const) {
  it(`${name}({ rec, expect }) returns once the op is called — fake: Date`, async () => {
    FAKES["Date"]();
    const rec = installFetchMock([route("first")], {}, null, "expect");
    rec.mark();
    const release = hold();
    setTimeout(() => void fetch("https://x.test/first"), 100);
    try {
      must(await outcome(wait({ rec, expect: ["first"] })), "returned");
      must(`called ${rec.countFor("first")}`, "called 1");
    } finally { release(); rec.restore(); }
  }, 10000);
}

// A delayed response stays on the timer the test drives; settleQuiet, on the
// real one, waits until the test has delivered it.
it("a delayed response is waited for once the test advances its timers — fake: every timer", async () => {
  FAKES["every timer"]();
  const rec = installFetchMock([route("slow", 200)], {}, null, "delayed");
  const release = hold();
  let arrived = false;
  void fetch("https://x.test/slow").then(() => { arrived = true; });
  try {
    const settled = outcome(settleQuiet());
    await vi.advanceTimersByTimeAsync(200);
    must(await settled, "returned");
    must(`arrived ${arrived}`, "arrived true");
  } finally { release(); rec.restore(); }
}, 10000);

// The named failures still fire on a frozen Date.
it("past the budget, settleQuiet fails by name — fake: Date", async () => {
  FAKES["Date"]();
  const rec = short.installFetchMock([route("a", SHORT_CAP_MS)], {}, null, "budget");
  let going = true;
  const next = (): void => { if (going) void fetch("https://x.test/a").then(next); };
  next();
  try {
    must(await outcome(short.settleQuiet()),
      /^threw: settle: still busy after \d+ ms — \d+ request\(s\) in flight \(budget SHORT_BUDGET_MS ms/);
  } finally { going = false; rec.restore(); }
}, 10000);

it("an expected op never called fails by name at EXPECT_MS — fake: Date", async () => {
  FAKES["Date"]();
  const rec = short.installFetchMock([route("first")], {}, null, "never");
  rec.mark();
  try {
    must(await outcome(short.settleQuiet({ rec, expect: ["first"] })),
      /^threw: settle: the row expects first, never called within EXPECT_MS \(SHORT_EXPECT_MS ms\)/);
  } finally { rec.restore(); }
}, 10000);

it("settle(20) past the budget fails by name — fake: Date", async () => {
  FAKES["Date"]();
  const rec = short.installFetchMock([route("a", SHORT_CAP_MS)], {}, null, "turns-budget");
  let going = true;
  const next = (): void => { if (going) void fetch("https://x.test/a").then(next); };
  next();
  try {
    must(await outcome(short.settle(20)),
      /^threw: settle: delayed responses were still arriving after waiting \d+ ms \(\d+ pending; budget SHORT_BUDGET_MS ms/);
  } finally { going = false; rec.restore(); }
}, 10000);
'''.replace("SHORT_CAP_MS", str(SHORT_CAP_MS)).replace(
    "SHORT_BUDGET_MS", str(SHORT_CAP_MS + 1000)).replace(
    "SHORT_EXPECT_MS", str(SHORT_EXPECT_MS)).replace("DELIVERY_MS", str(DELIVERY_MS))

#: Date frozen before the runtime loads — where a `setupFiles` entry puts it.
#: performance is left alone, so the clock the runtime takes is real.
_CLOCK_DATE_BEFORE_IMPORT_TS = '''import { it, vi, afterAll } from "vitest";
import { TODAY, must, outcome } from "./race";

vi.useFakeTimers({ toFake: ["Date"] });
vi.setSystemTime(TODAY);
const { installFetchMock, settleQuiet } = await import("./generated/jsonui-branch-runtime");
afterAll(() => { vi.useRealTimers(); });

it("settleQuiet() returns — Date frozen before the runtime was imported", async () => {
  const rec = installFetchMock([], {}, null, "date-before-import");
  // A timer past the quiet window: no early close, the window is measured.
  const t = setTimeout(() => {}, 600000);
  try { must(await outcome(settleQuiet()), "returned"); } finally { clearTimeout(t); rec.restore(); }
}, 10000);
'''

#: Date AND performance frozen before the runtime loads, setTimeout real: the
#: clock the runtime took stands still while its timer runs. Named, on both
#: paths — settle(turns) only loops on it after a delayed response lands.
_CLOCK_BOTH_BEFORE_IMPORT_TS = r'''import { it, vi, afterAll } from "vitest";
import { must, outcome } from "./race";

vi.useFakeTimers({ toFake: ["Date", "performance"] });
const { installFetchMock, settle, settleQuiet } = await import("./generated/jsonui-branch-runtime");
afterAll(() => { vi.useRealTimers(); });

it("settleQuiet() names the clock — Date and performance frozen before the runtime was imported", async () => {
  const rec = installFetchMock([], {}, null, "clock-before-import");
  // A timer past the quiet window: no early close, the window is measured.
  const t = setTimeout(() => {}, 600000);
  try {
    must(await outcome(settleQuiet(), STILL_BEFORE_IMPORT_MS),
      /^threw: settle: the clock it measures with \(performance\.now, taken when this runtime loaded\) read the same time across 200 polls/);
  } finally { clearTimeout(t); rec.restore(); }
}, STILL_BEFORE_IMPORT_MS + 10000);

it("settle(20) names the clock after a delayed response — Date and performance frozen before the runtime was imported", async () => {
  const rec = installFetchMock([{ op: "slow", method: "GET", pattern: "^/slow$", scenario: "ok",
    scenarios: { ok: { status: 200, body: {}, delayMs: 50 } } }], {}, null, "turns-clock-before-import");
  void fetch("https://x.test/slow");
  try {
    must(await outcome(settle(20), STILL_BEFORE_IMPORT_MS),
      /^threw: settle: the clock it measures with \(performance\.now, taken when this runtime loaded\) read the same time across 200 macrotask turns/);
  } finally { rec.restore(); }
}, STILL_BEFORE_IMPORT_MS + 10000);
'''.replace("STILL_BEFORE_IMPORT_MS", str(STILL_BEFORE_IMPORT_MS))

_FAKES = ("Date", "Date, setInterval, clearInterval", "setSystemTime alone", "every timer")
#: The quiet wait on a frozen clock: passes only if its window runs while the
#: test's clock stands.
_FROZEN = [*(f"settleQuiet() returns — fake: {f}" for f in _FAKES),
           "settleQuiet({ rec, expect }) returns once the op is called — fake: Date",
           "settle({ rec, expect }) returns once the op is called — fake: Date"]
_EARLY = [f"settleQuiet() closes early with nothing due — fake: {f}" for f in ("Date", "every timer")]
_DELAYED = "a delayed response is waited for once the test advances its timers — fake: every timer"
_NAMED = ["past the budget, settleQuiet fails by name — fake: Date",
          "an expected op never called fails by name at EXPECT_MS — fake: Date"]
#: settle() and settle(turns): back to what they did in 1.8.120.
_NO_ARG_FAST = [f"settle() returns within QUIET_MS — {c}" for c in ("real clock", *(f"fake: {f}" for f in _FAKES))]
_TURNS_FAST = [*(f"settle({n}) returns within QUIET_MS — real clock" for n in (2, 20, 40)),
               "settle(20) returns within QUIET_MS — fake: Date"]
_DELIVERY_REAL = "settle(20) waits for a delayed response in flight — real clock"
_DELIVERY_DATE = "settle(20) waits for a delayed response in flight — fake: Date"
_TURNS_BUDGET = "settle(20) past the budget fails by name — fake: Date"
_DATE_BEFORE = "settleQuiet() returns — Date frozen before the runtime was imported"
_BOTH_BEFORE = "settleQuiet() names the clock — Date and performance frozen before the runtime was imported"
_TURNS_BOTH_BEFORE = ("settle(20) names the clock after a delayed response — Date and performance "
                      "frozen before the runtime was imported")
#: timed()'s threshold on a stand-in clock: they pass whatever the runtime
#: is, so each control below leaves them green.
_THRESHOLD = ["timed() reads a quiet window that ends 1 ms early as slow",
              "timed() reads ten turns' time as fast",
              "timed() reads FAST_MS - 1 as fast and FAST_MS as slow"]
_CLOCK_CASES = [*_FROZEN, *_EARLY, *_NO_ARG_FAST, *_TURNS_FAST, _DELIVERY_REAL, _DELIVERY_DATE, _DELAYED, *_NAMED,
                _TURNS_BUDGET, _DATE_BEFORE, _BOTH_BEFORE, _TURNS_BOTH_BEFORE, *_THRESHOLD]

#: The threshold's cases: timed() on a clock that reads `started`, then
#: `started + took` — no timer, so no jitter, and the boundary is exact.
_CLOCK_THRESHOLD_TS = '''import { it } from "vitest";
import { FAST_MS, must, timed } from "./race";

function clockThatTakes(took: number): () => number {
  const reads = [1000, 1000 + took];
  return () => reads.shift() ?? 1000 + took;
}

it("timed() reads a quiet window that ends 1 ms early as slow", async () => {
  // The "until" mutant waits QUIET_MS; its timer fired a fraction early and
  // read 399 (release-check run 37650040409).
  must(await timed(Promise.resolve(), clockThatTakes(QUIET_MS_VALUE - 1)),
       /^returned in QUIET_MS_VALUE_MINUS_ONE ms, not under QUIET_MS \\/ 2/);
});

it("timed() reads ten turns' time as fast", async () => {
  must(await timed(Promise.resolve(), clockThatTakes(13)), "returned within QUIET_MS");
});

it("timed() reads FAST_MS - 1 as fast and FAST_MS as slow", async () => {
  must(await timed(Promise.resolve(), clockThatTakes(FAST_MS - 1)), "returned within QUIET_MS");
  must(await timed(Promise.resolve(), clockThatTakes(FAST_MS)), /^returned in \\d+ ms, not under/);
});
'''.replace("QUIET_MS_VALUE_MINUS_ONE", str(bt.QUIET_MS - 1)).replace("QUIET_MS_VALUE", str(bt.QUIET_MS))

#: How settle sends a call without an object — to settleTurns, ten turns when
#: it is not given a number.
_TO_TURNS = "  return settleTurns(typeof arg === \"number\" ? arg : DEFAULT_SETTLE_TURNS);\n"

#: Each part of the change, taken out: (the line as it is, the line without it).
_PARTS = {
    # 1.9.0's clock: Date.now(), read when settle runs.
    "clock": [("const realClock: { now: () => number; name: string } = loadedClock();\n",
               'const realClock: { now: () => number; name: string } = { now: () => Date.now(), name: "Date.now" };\n')],
    # 1.9.0's timer: the global setTimeout, looked up when settle sleeps.
    "timer": [("const loadedSetTimeout = globalThis.setTimeout;\n",
               "const loadedSetTimeout = (callback: () => void, ms: number) => globalThis.setTimeout(callback, ms);\n")],
    # 1.9.0's settle: anything but an object is `until` for the quiet wait —
    # a number throws, and settle() is the quiet window.
    "until": [(_TO_TURNS, "  return waitForQuiet(arg as any, DEFAULT_SETTLE_TURNS);\n")],
    # 99492ffa: a number goes to the quiet window, with a floor of that many polls.
    "quiet-for-numbers": [(_TO_TURNS, "  return typeof arg === \"number\" ? waitForQuiet(undefined, arg) : "
                                      "settleTurns(DEFAULT_SETTLE_TURNS);\n")],
    # d5808b85: settle() goes to the quiet window.
    "quiet-for-no-arg": [(_TO_TURNS, "  return typeof arg === \"number\" ? settleTurns(arg) : "
                                     "waitForQuiet(undefined, DEFAULT_SETTLE_TURNS);\n")],
    # settle(turns) without its wait for delayed responses.
    "no-deliveries": [("    if (pendingDeliveries.size === 0 && lastDeliveryAt < drainStarted) return;\n",
                       "    return;\n")],
    # The clock taken from Date rather than performance.
    "date-clock": [('  if (perf && typeof perf.now === "function") {\n', "  if (false) {\n")],
    # No stall guard, on either path.
    "guard": [("    if (stalled >= STALLED_POLLS) throw", "    if (false) throw"),
              ("    if (stalled >= STALLED_TURNS) throw", "    if (false) throw")],
    # No floor of polls on the quiet path.
    "floor": [("    if (quiet && missing.length === 0 && polls >= minPolls) return;\n",
               "    if (quiet && missing.length === 0) return;\n")],
    # settle(turns) draining one turn, whatever it was asked for.
    "one-turn": [("    for (let i = 0; i < turns; i += 1) {\n", "    for (let i = 0; i < 1; i += 1) {\n")],
    # No early close: every settleQuiet waits out the quiet window (1.9.0).
    "early": [("    if (missing.length === 0 && idle >= minPolls) return;\n", "")],
    # No timer watch, and a watch that vouches anyway: the early close is
    # taken while a view model's timer is still due.
    "watch": [("  const unwatchTimers = watchRowTimers(mine);\n",
               "  mine.watching = () => true;\n  const unwatchTimers = (): void => {};\n")],
    # A watch that does not notice a replaced setTimeout.
    "displaced": [("    !traffic.unwatched && traffic.watching();\n", "    !traffic.unwatched;\n")],
    # A setInterval read as done after its first tick.
    "interval": [("    setInterval: schedule(original.setInterval, true),\n",
                  "    setInterval: schedule(original.setInterval, false),\n")],
    # settleHarness without its skip: settleQuiet after every harness.
    "harness-skip": [("  if (traffic.seq === 0 && nothingDue()) return;\n", "")],
}


def _without(*parts: str) -> str:
    runtime = bt.RUNTIME_TS
    for part in parts:
        for old, new in _PARTS[part]:
            assert runtime.count(old) == 1, (part, old)
            runtime = runtime.replace(old, new)
    return runtime


def _clock_project(root: Path, runtime: str) -> Path:
    from tests import test_branch_notices_reach_agent_runs as n
    short = runtime
    for old, new in (("export const DELAY_CAP_MS = 30000;", f"export const DELAY_CAP_MS = {SHORT_CAP_MS};"),
                     ("export const EXPECT_MS = 10000;", f"export const EXPECT_MS = {SHORT_EXPECT_MS};")):
        assert short.count(old) == 1, old
        short = short.replace(old, new)
    unit = root / "tests" / "unit"
    n._write(unit / "generated" / "jsonui-branch-runtime.ts", runtime)
    n._write(unit / "generated" / "short-budget-runtime.ts", short)
    n._write(unit / "race.ts", _CLOCK_RACE_TS)
    n._write(unit / "timed-threshold.test.ts", _CLOCK_THRESHOLD_TS)
    n._write(unit / "fake-after-import.test.ts", _CLOCK_AFTER_IMPORT_TS)
    n._write(unit / "date-before-import.test.ts", _CLOCK_DATE_BEFORE_IMPORT_TS)
    n._write(unit / "clock-before-import.test.ts", _CLOCK_BOTH_BEFORE_IMPORT_TS)
    n._runner_files(root)
    return root


def _same_cases(what: str, got: set[str], want: set[str],
                cases: dict[str, tuple[str, str]] | None = None) -> None:
    """Fail with every name that differs and, when known, its outcome and
    message, written out in full. pytest's own diff of two lists stops at
    the first difference and ends "Use -v to get more diff": a local run on
    2026-10-08 failed one of these controls and the case's name was lost
    with it (ticket test-branch-settle-control-real-clock-threshold-sits-on-
    the-mutants-wait). The message is ours, so it does not depend on -v."""
    if got == want:
        return
    lines = [f"{what}: {len(got)} cases, {len(want)} expected"]
    for label, names in (("expected, not got", sorted(want - got)), ("got, not expected", sorted(got - want))):
        lines.append(f"  {label}: {len(names)}")
        for name in names:
            state, message = (cases or {}).get(name, ("-", ""))
            lines.append(f"    {name!r}: {state} {message!r}")
    raise AssertionError("\n".join(lines))


def _clock_cases(tmp_path: Path, runtime: str) -> dict[str, tuple[str, str]]:
    """Each case's (outcome, failure message) — every case, or the arm fails:
    a case that did not run is not one that passed."""
    run, tests = _vitest(_clock_project(tmp_path / "p", runtime))
    got = {name: (state, message) for name, state, message in tests}
    try:
        _same_cases("cases that ran", set(got), set(_CLOCK_CASES), got)
    except AssertionError as error:
        raise AssertionError(f"{error}\n{(run.stdout + run.stderr)[-4000:]}") from None
    return got


def test_web_settle_runs_its_windows_under_a_fake_clock_and_takes_a_number_again(tmp_path):
    got = _clock_cases(tmp_path, bt.RUNTIME_TS)
    _same_cases("cases that passed", {name for name, (state, _) in got.items() if state == "passed"},
                set(_CLOCK_CASES), got)


_STOOD = "OUTCOME threw: settle: the clock it measures with (Date.now, taken when this runtime loaded) read the same time across "
_WAITING = "OUTCOME still waiting after "
_TYPE_ERROR = "OUTCOME threw: Cannot read properties of undefined (reading 'filter')"
_SLOW = "OUTCOME returned in "


@pytest.mark.parametrize("parts, red", [
    # 1.9.0's clock: every case on a frozen clock that has to measure time
    # fails — named by the stall guards, which now stand between that
    # regression and a loop. settle() and settle(20) on a frozen Date with
    # nothing delayed still return: 1.8.120's did too.
    (("clock",), {**dict.fromkeys([*_FROZEN, _DELAYED, *_NAMED, _DATE_BEFORE, _BOTH_BEFORE], _STOOD + "200 polls"),
                  **dict.fromkeys([_DELIVERY_DATE, _TURNS_BUDGET, _TURNS_BOTH_BEFORE], _STOOD + "200 macrotask turns")}),
    # ...and without the guards: the reported failure, neither returned nor threw.
    (("clock", "guard"), dict.fromkeys([*_FROZEN, _DELAYED, *_NAMED, _DATE_BEFORE, _BOTH_BEFORE,
                                        _DELIVERY_DATE, _TURNS_BUDGET, _TURNS_BOTH_BEFORE], _WAITING)),
    # 1.9.0's timer: the waits' own sleep on a timer only the test advances.
    # And the early close is lost on a real timer too: the runtime's own
    # sleeps then go through the row's watched setTimeout, and each counts
    # as the row's activity.
    (("timer",), {**dict.fromkeys(["settleQuiet() returns — fake: every timer", _DELAYED,
                                   "settleQuiet() closes early with nothing due — fake: every timer",
                                   "settle() returns within QUIET_MS — fake: every timer"],
                                  f"OUTCOME still waiting after {STILL_MS} ms"),
                  "settleQuiet() closes early with nothing due — fake: Date": _SLOW}),
    # The next three are what 1.9.0 and its fixes wired settle to: the quiet
    # window as it was then, with no early close — so each takes the early
    # close out too, and the early-close cases go red with it (_EARLY). With
    # the early close in, a settle() sent through the quiet window with
    # nothing due returns in ten turns, and these wirings read as fast.
    # 1.9.0's settle: a number is the TypeError the 1.8.120 callers got, and
    # settle() is the quiet window, QUIET_MS on every call.
    (("until", "early"), {**dict.fromkeys([*_TURNS_FAST, _DELIVERY_REAL, _DELIVERY_DATE, _TURNS_BUDGET,
                                           _TURNS_BOTH_BEFORE], _TYPE_ERROR),
                          **dict.fromkeys([*_NO_ARG_FAST, *_EARLY], _SLOW)}),
    # A number sent through the quiet window (99492ffa): QUIET_MS more on
    # every call, and the quiet path's budget and stall messages.
    (("quiet-for-numbers", "early"), {**dict.fromkeys([*_TURNS_FAST, *_EARLY], _SLOW),
                                      _TURNS_BUDGET: "OUTCOME threw: settle: still busy after ",
                                      _TURNS_BOTH_BEFORE: "OUTCOME threw: settle: the clock it measures with "
                                                          "(performance.now, taken when this runtime loaded) read "
                                                          "the same time across 200 polls"}),
    # settle() sent through the quiet window (d5808b85): QUIET_MS on every call.
    (("quiet-for-no-arg", "early"), dict.fromkeys([*_NO_ARG_FAST, *_EARLY], _SLOW)),
    # settle(turns) that does not wait for a delayed response.
    (("no-deliveries",), {_DELIVERY_REAL: "OUTCOME arrived false", _DELIVERY_DATE: "OUTCOME arrived false",
                          _TURNS_BUDGET: "OUTCOME returned", _TURNS_BOTH_BEFORE: "OUTCOME returned"}),
    # The clock taken from Date: a Date frozen before the import is the one taken.
    (("date-clock",), {_DATE_BEFORE: _STOOD + "200 polls", _BOTH_BEFORE: _STOOD + "200 polls",
                       _TURNS_BOTH_BEFORE: _STOOD + "200 macrotask turns"}),
    # No stall guards: the clock frozen before the import loops again.
    (("guard",), dict.fromkeys([_BOTH_BEFORE, _TURNS_BOTH_BEFORE],
                               f"OUTCOME still waiting after {STILL_BEFORE_IMPORT_MS} ms")),
    # No early close: a row with nothing due takes the quiet window again.
    (("early",), dict.fromkeys(_EARLY, _SLOW)),
], ids=["clock", "clock-and-guard", "timer", "until", "quiet-for-numbers", "quiet-for-no-arg",
        "no-deliveries", "date-clock", "guard", "early"])
def test_web_control_each_part_taken_out_turns_its_own_cases_red(tmp_path, parts, red):
    got = _clock_cases(tmp_path, _without(*parts))
    _same_cases("cases that went red", {name for name, (state, _) in got.items() if state != "passed"},
                set(red), got)
    wrong = {name: (says, got[name][1]) for name, says in red.items() if got[name][1][:len(says)] != says}
    assert not wrong, "red for another reason:\n" + "\n".join(
        f"  {name!r}: expected {says!r}…, got {message!r}" for name, (says, message) in sorted(wrong.items()))


_TS_TURNS = '''import { installFetchMock, settle, settleQuiet } from "./runtime.ts";
const arg = process.argv[2];
const held = Number(process.argv[3]);
const rec = installFetchMock([], {});
// The view model: holds the event loop for `held` ms, then a chain of
// setTimeout(0) hops — one per macrotask turn.
let hops = 0;
const hop = (): void => { hops += 1; if (hops < 100000) setTimeout(hop, 0); };
setTimeout(() => { const t = Date.now(); while (Date.now() - t < held) { /* held */ } hop(); }, 0);
await (arg === "quiet" ? settleQuiet() : arg === "none" ? settle() : settle(Number(arg)));
console.log(`HOPS ${hops}`);
rec.restore();
process.exit(0);
'''


@pytest.mark.parametrize("arg, turns", [("20", 20), ("40", 40), ("none", 10), ("quiet", 10)])
def test_web_settle_lets_at_least_its_turns_run_when_the_quiet_passes_sooner(tmp_path, arg, turns):
    """What a 1.8.120 caller counted on: `settle(n)` ran n macrotask turns
    before it returned, `settle()` ten. Here the quiet window has passed by
    the first poll (the event loop was held up past it): settle drains its
    turns as it did, and settleQuiet keeps polling to ten."""
    got = _node(tmp_path, bt.RUNTIME_TS, _TS_TURNS, arg, str(HELD_MS))
    assert int(got["HOPS"]) >= turns, got


@pytest.mark.parametrize("part, arg, turns", [("floor", "quiet", 10), ("one-turn", "20", 20),
                                              ("one-turn", "none", 10)])
def test_web_control_without_the_floor_the_turns_do_not_all_run(tmp_path, part, arg, turns):
    got = _node(tmp_path, _without(part), _TS_TURNS, arg, str(HELD_MS))
    assert int(got["HOPS"]) < turns, got


# ------------------------------------------ web, the generated rows' wait ----

#: A view model that finishes its work this long after the act, with no
#: request after it: inside the quiet window a row waits over, far past the
#: ten turns settle() drains.
LATE_MS = bt.QUIET_MS // 2

_TICKER_SPEC = {
    "type": "screen_spec", "metadata": {"name": "ticker"},
    "dataFlow": {"viewModel": {"methods": [{"name": "tick"}]}},
    "branchContracts": {"methods": {"tick": {"branches": [{"when": {}, "then": {"data.status": "ticked"}}]}}},
}

_TICKER_HARNESS = '''import { applyDeclaredKeys } from "../generated/jsonui-branch-runtime";
class TickerViewModel {
  status = "idle";
  async tick() { setTimeout(() => { this.status = "ticked"; }, LATE_MS); }
}
export function createHarness() {
  const vm = new TickerViewModel();
  return {
    vm,
    setState(state: Record<string, unknown>) { applyDeclaredKeys(vm, state); },
    readField(name: string) { return (vm as any)[name]; },
    expectTransition(_d: string) {},
    resolveString(key: string) { return key; },
  };
}
'''.replace("LATE_MS", str(LATE_MS))


def _ticker(root: Path, harness: str = _TICKER_HARNESS) -> Path:
    import json

    from tests import test_branch_notices_reach_agent_runs as n
    n._write(root / "jui.config.json", json.dumps({"spec_directory": "docs/screens/json", "platforms": ["web"]}))
    n._write(root / "docs/screens/json/ticker.spec.json", json.dumps(_TICKER_SPEC))
    report = bt.generate_branch_tests("ticker", root, platform="web", config_platforms=["web"])
    n._write(root / "tests/unit/branch-harness/ticker.ts", harness)
    n._runner_files(root)
    return report.test_file


def _waits(text: str) -> list[str]:
    """Every settle-family call the generated file makes, and what it imports."""
    import re
    return sorted(set(re.findall(r"\b(settle\w*)\(", text))) + sorted(
        set(re.findall(r"\b(settle\w*),\n  type RouteSpec", text)))


def test_web_generated_rows_wait_with_settle_quiet(tmp_path):
    """After the harness, settleHarness (settleQuiet, skipped when
    construction did nothing); after the act, settleQuiet."""
    text = _ticker(tmp_path / "p").read_text(encoding="utf-8")
    assert _waits(text) == ["settleHarness", "settleQuiet", "settleQuiet"], text
    assert "settleHarness, settleQuiet,\n  type RouteSpec," in text, text
    assert text.count("      const h = createHarness();\n      await settleHarness();\n") == 1, text
    assert text.count("      await settleQuiet();\n") == 1, text


def test_web_control_rows_emitting_settle_would_call_the_turns(tmp_path, monkeypatch):
    monkeypatch.setattr(bt, "WEB_ROW_WAIT", "settle")
    monkeypatch.setattr(bt, "WEB_HARNESS_WAIT", "settle")
    text = _ticker(tmp_path / "p").read_text(encoding="utf-8")
    assert _waits(text) == ["settle", "settle"], text


def test_web_a_generated_row_reads_the_state_after_the_quiet_window(tmp_path):
    test_file = _ticker(tmp_path / "p")
    run, tests = _vitest(tmp_path / "p")
    assert [s for _, s, _ in tests] == ["passed"], (tests, test_file.read_text(encoding="utf-8"))


def test_web_control_a_row_that_called_settle_reads_it_half_done(tmp_path, monkeypatch):
    monkeypatch.setattr(bt, "WEB_ROW_WAIT", "settle")
    _ticker(tmp_path / "p")
    run, tests = _vitest(tmp_path / "p")
    assert [(s, m) for _, s, m in tests] == [("failed", "expected 'idle' to deeply equal 'ticked'")], tests


# ------------------------------- web, a generated row's time (the ticket) ----

#: A view model whose act does its work at once: no request, no timer.
_TICKER_AT_ONCE = _TICKER_HARNESS.replace(
    f'async tick() {{ setTimeout(() => {{ this.status = "ticked"; }}, {LATE_MS}); }}',
    'async tick() { this.status = "ticked"; }')


def _row_ms(root: Path) -> list[tuple[str, int]]:
    """Each test's (outcome, duration in ms) from the junit report."""
    import xml.etree.ElementTree as ET

    from tests import test_branch_notices_reach_agent_runs as n
    tc.tool("node")
    n._vitest()
    out = root / "vitest-junit.xml"
    run = n._vitest_run(root, {}, "--reporter=junit", f"--outputFile={out}")
    assert out.is_file(), (run.stdout + run.stderr)[-4000:]
    return [("failed" if case.find("failure") is not None else "passed",
             round(float(case.get("time", "0")) * 1000))
            for case in ET.parse(out).getroot().iter("testcase")]


def test_web_a_generated_row_with_nothing_due_takes_less_than_the_quiet_window(tmp_path):
    """1.9.0's rows took 2 x QUIET_MS at the least, whatever they did."""
    assert _TICKER_AT_ONCE != _TICKER_HARNESS
    _ticker(tmp_path / "p", _TICKER_AT_ONCE)
    [(state, ms)] = _row_ms(tmp_path / "p")
    assert state == "passed" and ms < bt.QUIET_MS, (state, ms)


def test_web_control_without_the_early_close_and_the_skip_a_row_takes_two_windows(tmp_path, monkeypatch):
    """1.9.0's wait: settleQuiet after the harness, and no early close."""
    monkeypatch.setattr(bt, "RUNTIME_TS", _without("early"))
    monkeypatch.setattr(bt, "WEB_HARNESS_WAIT", "settleQuiet")
    _ticker(tmp_path / "p", _TICKER_AT_ONCE)
    [(state, ms)] = _row_ms(tmp_path / "p")
    assert state == "passed" and ms >= 2 * bt.QUIET_MS, (state, ms)


def test_web_a_generated_row_whose_view_model_finishes_from_a_timer_closes_after_it(tmp_path):
    """The ticker finishes LATE_MS after the act, from a timer and with no
    request: the row reads it (test_web_a_generated_row_reads_the_state_after_
    the_quiet_window) and closes soon after it, not QUIET_MS after it."""
    _ticker(tmp_path / "p")
    [(state, ms)] = _row_ms(tmp_path / "p")
    assert state == "passed" and LATE_MS <= ms < LATE_MS + bt.QUIET_MS, (state, ms)
