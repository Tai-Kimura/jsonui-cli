"""Two calls in flight at once are two calls recorded — measured by RUNNING them.

An act that starts two requests together (a screen loading its content and a
side list in parallel) reaches the recorder from two places at once, and the
recorder was a plain list on both mobile faces:

- Android: MockWebServer serves each connection on its own thread and
  `dispatch` appends from there. Two parallel OkHttp calls inside the emitted
  `runBranchTest` (MockWebServer 4.12.0, the whole runtime compiled) recorded
  fewer than two in 32 of 900 rounds on v1.8.114 and in 0 of 900 after this
  change. The first two adds into an empty ArrayList both grow it and one
  grown array is thrown away — so a reach assert reads 0 for a call that was
  made. A second shape of the same race left a null slot, and the next read
  threw a NullPointerException instead.
- iOS: CFNetwork ran every `startLoading` on one thread in these runs (64
  calls in flight, never two bodies at once), so the protocol's appends do
  not race each other. The protocol and the TEST do: when a call lands after
  `settle()` has returned, the test reads the array the protocol is growing.
  A test reading while 16 calls were in flight crashed 5 of 5 runs (index out
  of range, SIGSEGV) on v1.8.114, and ThreadSanitizer names the pair.
- web: the fetch mock records synchronously on the calling thread. Nothing to
  race, no arm.

WHAT THE ARMS CAN AND CANNOT SEE. The `runBranchTest` shape above needs
the okhttp and kotlinx jars, which only a Gradle cache has, and CI has no
cache; it was measured by hand and is recorded here, not re-run. What CI runs instead is a
shape the old list fails EVERY time: eight writers and a reader on one
recorder. Two threads adding once each — the act's own shape without a
server — lost a call 0-4 times in 20,000 rounds on the old list, so an arm
built on it would pass for the defect; it is not used.

Red-check (2026-09-24, predictions written before each run):

    arm                                   fixed        old list / no lock
    android: 8 writers + reader, 20 rds    0 short      20/20 rounds short or
                                                        thrown, in 3 runs of 3
    ios: read while 16 in flight, 20 rds   rc 0, 0      crashed 5 of 5 runs
    ios: same, ThreadSanitizer             0 races      2 races reported, or
                                                        index out of range first

The controls below take the fix out of the SAME emitted source and assert it
goes red, so a probe that stopped exercising the recorder would fail its
control instead of passing both.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from test_branch_tests_generator import SEEDABLE, _project  # noqa: E402

from jsonui_test_cli import branch_tests as bt  # noqa: E402
from jsonui_test_cli.branch_tests import generate_branch_tests  # noqa: E402

from tests import _toolchain as tc  # noqa: E402

_ROUNDS = 20


def _counts(stdout: str) -> dict[str, int]:
    out = {}
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in ("ROUNDS", "SHORT", "THROWN") and parts[1].isdigit():
            out[parts[0]] = int(parts[1])
    return out


# ---------------------------------------------------------------------------
# android
# ---------------------------------------------------------------------------

_KOTLIN_COW = "java.util.concurrent.CopyOnWriteArrayList()"

# The writers call `rec.calls.add`, which is exactly what `dispatch` calls.
# Fully qualified: the probe is one file with the runtime's declarations
# above it, and Kotlin takes imports only at the top.
_KOTLIN_MAIN = """
fun main() {
  val rounds = %(rounds)d
  val writers = 8
  val each = 1000
  var short = 0
  val thrown = java.util.concurrent.atomic.AtomicInteger()
  repeat(rounds) {
    val rec = Recorder(setOf("a", "b"))
    val start = java.util.concurrent.CyclicBarrier(writers + 1)
    val done = java.util.concurrent.atomic.AtomicBoolean(false)
    val ws = (0 until writers).map { t ->
      Thread {
        start.await()
        try {
          repeat(each) { rec.calls.add(RecordedCall(if (t %% 2 == 0) "a" else "b", "GET", "/x", null)) }
        } catch (e: Throwable) { thrown.incrementAndGet() }
      }
    }
    val reader = Thread {
      start.await()
      try { while (!done.get()) { rec.countFor("a"); rec.matchedCalls() } }
      catch (e: Throwable) { thrown.incrementAndGet() }
    }
    ws.forEach { it.start() }
    reader.start()
    ws.forEach { it.join() }
    done.set(true)
    reader.join()
    val n = try { rec.countFor("a") + rec.countFor("b") } catch (e: Throwable) { -1 }
    if (n != writers * each) short++
  }
  println("ROUNDS " + rounds)
  println("SHORT " + short)
  println("THROWN " + thrown.get())
}
"""


def _kotlin_block(emitted: str, signature: str) -> str:
    i = emitted.index(signature)
    return emitted[i:emitted.index("\n}\n", i) + 3]


def _run_kotlin(tmp_path: Path, runtime_source: str) -> dict[str, int]:
    # `RecordedCall` is one line with no body; the brace slice would run past
    # it into `Recorder`, so it is taken by line.
    recorded_call = re.search(r"^data class RecordedCall\(.*$",
                              runtime_source, re.M).group(0)
    parts = [recorded_call,
             _kotlin_block(runtime_source, "private fun quotedValue("),
             _kotlin_block(runtime_source, "class Recorder(")]
    run = tc.compile_and_run_kotlin(
        tmp_path, tc.KOTLIN_SHIM + "\n" + "\n\n".join(parts)
        + _KOTLIN_MAIN % {"rounds": _ROUNDS})
    counts = _counts(run.stdout)
    assert counts.get("ROUNDS") == _ROUNDS, (
        f"probe did not finish its rounds: rc={run.returncode}\n"
        f"{run.stdout[-2000:]}{run.stderr[-2000:]}")
    return counts


def test_android_keeps_every_call_added_from_many_threads(tmp_path):
    counts = _run_kotlin(tmp_path, bt.KOTLIN_RUNTIME)
    assert counts == {"ROUNDS": _ROUNDS, "SHORT": 0, "THROWN": 0}, counts


def test_android_control_a_plain_list_loses_calls(tmp_path):
    """The same probe over the list v1.8.114 shipped. Measured 20/20 rounds
    red in each of 3 runs; one red round is all this asks for."""
    assert bt.KOTLIN_RUNTIME.count(_KOTLIN_COW) == 1, "the list declaration moved"
    old = bt.KOTLIN_RUNTIME.replace(_KOTLIN_COW, "mutableListOf()")
    counts = _run_kotlin(tmp_path, old)
    assert counts["SHORT"] + counts["THROWN"] > 0, (
        f"the old list survived 8 writers and a reader: {counts} — the probe "
        "is no longer racing, so the arm above would pass for the defect too")


# ---------------------------------------------------------------------------
# ios
# ---------------------------------------------------------------------------

# The emitted runtime's XCTest call sites, stood up so it compiles as a
# program (the same shim the swizzle arms use).
_SWIFT_SHIM = """import Foundation
func XCTFail(_ m: String = "", file: StaticString = #filePath, line: UInt = #line) {
  FileHandle.standardError.write("XCTFail: \\(m)\\n".data(using: .utf8)!)
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

# Requests go through `URLSessionConfiguration.default`, so they reach the
# protocol the way a consumer's network stack does. The test thread reads
# while they land — what a `settle()` that returned early leaves behind.
_SWIFT_MAIN = """import Foundation
let rounds = %(rounds)d
let n = 16
let routes = [
  RouteSpec(op: "a", method: "GET", pattern: "^/a$", defaultScenario: "ok",
            scenarios: ["ok": (200, "{}", "application/json")]),
  RouteSpec(op: "b", method: "GET", pattern: "^/b$", defaultScenario: "ok",
            scenarios: ["ok": (200, "{}", "application/json")]),
]
let dummy = NSObject()
var short = 0
for _ in 0..<rounds {
  runBranchTest(routes: routes, overrides: [:],
                harnessFactory: { BaseBranchHarness(vm: dummy) }) { _, rec in
    let session = URLSession(configuration: .default)
    let group = DispatchGroup()
    for i in 0..<n {
      group.enter()
      let url = URL(string: "https://example.test/" + (i %% 2 == 0 ? "a" : "b"))!
      session.dataTask(with: url) { _, _, _ in group.leave() }.resume()
    }
    while group.wait(timeout: .now()) == .timedOut {
      _ = rec.countFor("a")
      _ = rec.calls.count
    }
    if rec.countFor("a") + rec.countFor("b") != n { short += 1 }
    session.invalidateAndCancel()
  }
}
print("ROUNDS \\(rounds)")
print("SHORT \\(short)")
"""



@pytest.fixture(scope="module")
def swift_runtime(tmp_path_factory) -> str:
    """The emitted runtime as it ships, less its one `import XCTest`."""
    tc.tool("swiftc")
    work = tmp_path_factory.mktemp("recorder-runtime")
    root = _project(work, SEEDABLE)
    result = generate_branch_tests(
        "checkout", root, platform="ios", module="checkout_app",
        out_dir="Tests/Generated", harness_dir="Tests/Generated",
    )
    emitted = result.runtime_file.read_text(encoding="utf-8")
    assert emitted.count("\nimport XCTest\n") == 1, "expected exactly one XCTest import"
    return emitted.replace("\nimport XCTest\n", "\n", 1)


def _build_swift(work: Path, runtime: str, *flags: str) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    (work / "shim.swift").write_text(_SWIFT_SHIM, encoding="utf-8")
    (work / "runtime.swift").write_text(runtime, encoding="utf-8")
    (work / "main.swift").write_text(_SWIFT_MAIN % {"rounds": _ROUNDS}, encoding="utf-8")
    binary = work / "prog"
    build = subprocess.run(
        ["swiftc", "-Onone", *flags, "-o", str(binary), str(work / "shim.swift"),
         str(work / "runtime.swift"), str(work / "main.swift")],
        capture_output=True, text=True, timeout=600)
    assert build.returncode == 0, f"emitted runtime did not compile:\n{build.stderr[:4000]}"
    return binary


def _without_the_lock(runtime: str) -> str:
    """The same runtime with the recorder's lock made a no-op in all three
    accessors — replaced by a statement rather than deleted, because
    `get { ; return … }` does not parse. Only inside `Recorder`: the swizzle
    installer holds a lock of its own, and taking that one out would measure
    something else. Counted, so a replace that matched nothing cannot pass as
    a control."""
    start = runtime.index("final class Recorder {")
    end = runtime.index("\n}\n", start) + 3
    body = runtime[start:end]
    for call in ("lock.lock()", "lock.unlock()"):
        assert body.count(call) == 3, (
            f"expected {call} in get, set and record; found {body.count(call)}")
        body = body.replace(call, "_ = lock")
    return runtime[:start] + body + runtime[end:]


def _run(binary: Path, **env: str) -> subprocess.CompletedProcess:
    import os
    return subprocess.run([str(binary)], capture_output=True, text=True, timeout=300,
                          env={**os.environ, **env})


def test_ios_a_read_while_calls_land_is_safe(swift_runtime, tmp_path):
    binary = _build_swift(tmp_path, swift_runtime)
    for attempt in range(3):
        run = _run(binary)
        assert run.returncode == 0, (
            f"run {attempt + 1} died (rc={run.returncode}):\n{run.stderr[-3000:]}")
        assert _counts(run.stdout) == {"ROUNDS": _ROUNDS, "SHORT": 0}, run.stdout


def test_ios_control_without_the_lock_crashes(swift_runtime, tmp_path):
    """v1.8.114 crashed 5 of 5 runs of this probe. Three runs, one crash or
    short round asked for."""
    binary = _build_swift(tmp_path, _without_the_lock(swift_runtime))
    outcomes = []
    for _ in range(3):
        run = _run(binary)
        counts = _counts(run.stdout)
        outcomes.append((run.returncode, counts.get("SHORT")))
    assert any(rc != 0 or short != 0 for rc, short in outcomes), (
        f"an unlocked recorder survived three runs {outcomes} — the probe is no "
        "longer reading while calls land")


def test_ios_thread_sanitizer_finds_no_race(swift_runtime, tmp_path):
    """The timing-free form. A crash needs the two accesses to collide; the
    sanitizer reports them when nothing orders them, collision or not."""
    binary = _build_swift(tmp_path, swift_runtime, "-sanitize=thread")
    run = _run(binary, TSAN_OPTIONS="halt_on_error=0")
    assert "ThreadSanitizer" not in run.stderr, run.stderr[-4000:]
    assert run.returncode == 0, run.stderr[-3000:]
    assert _counts(run.stdout) == {"ROUNDS": _ROUNDS, "SHORT": 0}, run.stdout


def test_ios_thread_sanitizer_control_names_the_race(swift_runtime, tmp_path):
    """Red either way: the sanitizer names the pair, or the unlocked array
    breaks first ("Index out of range") before it can. Both were seen."""
    binary = _build_swift(tmp_path, _without_the_lock(swift_runtime), "-sanitize=thread")
    run = _run(binary, TSAN_OPTIONS="halt_on_error=0")
    assert "WARNING: ThreadSanitizer" in run.stderr or run.returncode != 0, (
        f"no race reported and no crash without the lock (rc={run.returncode}) — "
        f"the sanitizer arm above is not measuring the recorder:\n{run.stderr[-2000:]}")


def test_ios_every_write_the_protocol_makes_goes_through_record():
    """The arms above exercise the two write sites that exist today. A third
    written as `calls.append` would compile and race again."""
    assert bt.SWIFT_RUNTIME.count("Self.recorder?.record(") == 2
    assert "calls.append(" not in bt.SWIFT_RUNTIME
