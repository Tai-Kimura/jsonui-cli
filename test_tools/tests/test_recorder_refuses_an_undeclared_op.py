"""The read side refuses an op no route declares — measured by RUNNING it.

`countFor` and `lastBodyFor` match recorded calls by op STRING. A name that
matches nothing answered 0 and nothing, and both are PLAUSIBLE: an assert
written against a misspelled op checked nothing and stayed green for ever.
The write side has refused an undeclared op since `resolve_routes`, but that
runs at GENERATION time, inside the generator. These two are read at TEST
time, by hand-written tests — the population the runtime is exported for,
and the only population the generator's checks cannot reach.

TEXT ARMS CANNOT SEE THIS. Whether a guard refuses is a fact about
execution, and `assertDeclared(op);` appearing in the emitted source is a
fact about a string. Each face below compiles what the generator emits and
runs it, and skips visibly where the toolchain is absent.

Each face asserts THE SAME ROWS, so a face that disagrees with another shows
up as a different row rather than as a different test. `_CONTROL_ROWS` are
the rows the guard is responsible for: a control that strips the guard's
call sites out of the emitted source must flip exactly those and leave the
rest alone. Without it, a probe that never reached the guard at all would
report the same all-PASS as one that reached it and was refused.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from jsonui_test_cli import branch_tests as bt
from tests import _toolchain as tc

#: The op the route table declares, and the typo a hand-written test makes.
_DECLARED_OP = "createOrder"
_TYPO_OP = "createOrde"

_EXPECTED = {
    # The guard must not change what a correct read answers.
    "declared-count": True,       # a declared op still counts its calls
    "declared-body": True,        # a declared op still returns its body
    "sentinel-count": True,       # "(unmatched)" is a real op, not a typo
    # The defect itself.
    "undeclared-count-refused": True,
    "undeclared-body-refused": True,
    # A refusal that does not say WHICH name, or what the names ARE, leaves
    # the reader with the same question the 0 left them with.
    "message-names-the-op": True,
    "message-lists-declared": True,
}

#: The rows the guard is responsible for. Stripping the guard must flip
#: these and only these — a control that flips everything would also pass a
#: probe that simply stopped running.
_CONTROL_ROWS = {
    "undeclared-count-refused", "undeclared-body-refused",
    "message-names-the-op", "message-lists-declared",
}


def _results(stdout: str) -> dict[str, bool]:
    out = {}
    for line in stdout.splitlines():
        parts = line.split(None, 2)
        if len(parts) >= 2 and parts[0] in ("PASS", "FAIL"):
            out[parts[1]] = parts[0] == "PASS"
    return out


def _assert_all(results: dict[str, bool], stdout: str) -> None:
    assert results, f"probe produced no result rows:\n{stdout}"
    missing = set(_EXPECTED) - set(results)
    assert not missing, f"probe never reported {sorted(missing)}:\n{stdout}"
    wrong = {k: v for k, v in results.items()
             if k in _EXPECTED and _EXPECTED[k] != v}
    assert not wrong, f"rows disagreed with the contract: {wrong}\n{stdout}"


def _strip_guard(emitted: str, call: str) -> str:
    """The same source with the guard's call sites removed.

    Checked rather than assumed: a `replace` that matched nothing would
    produce a control identical to the subject, and the control would then
    "pass" by measuring the guarded code twice. Both read sites call it, so
    the count is exactly two.
    """
    assert emitted.count(call) == 2, (
        f"expected 2 guard call sites, found {emitted.count(call)}")
    return emitted.replace(call, "")


# ---------------------------------------------------------------------------
# web
# ---------------------------------------------------------------------------

_TS_PROBE = '''import { installFetchMock } from "./%(runtime)s";

const ROUTES: any[] = [{
  op: "%(declared)s", method: "POST", pattern: "^/api/orders$",
  scenario: "default",
  scenarios: { default: { status: 200, body: { ok: true } } },
}];

function check(name: string, got: boolean) {
  console.log(`${got ? "PASS" : "FAIL"} ${name}`);
}
function refusal(fn: () => unknown): string | null {
  try { fn(); return null; } catch (e) { return String(e); }
}

const rec = installFetchMock(ROUTES);
await fetch("https://example.test/api/orders",
            { method: "POST", body: JSON.stringify({ a: 1 }) });
// A real unmatched call, so the sentinel the mock WRITES is the same string
// the guard ALLOWS. Two literals, one meaning — the drift this would hide
// is a guard that refuses a question the recorder itself answers.
await fetch("https://example.test/api/elsewhere");

check("declared-count", rec.countFor("%(declared)s") === 1);
check("declared-body",
      JSON.stringify(rec.lastBodyFor("%(declared)s")) === '{"a":1}');
check("sentinel-count", rec.countFor("(unmatched)") === 1);

const counted = refusal(() => rec.countFor("%(typo)s"));
const bodied = refusal(() => rec.lastBodyFor("%(typo)s"));
check("undeclared-count-refused", counted !== null);
check("undeclared-body-refused", bodied !== null);
check("message-names-the-op", (counted ?? "").includes("%(typo)s"));
check("message-lists-declared", (counted ?? "").includes("%(declared)s"));
rec.restore();
'''


def _run_ts(tmp_path: Path, runtime_source: str) -> dict[str, bool]:
    (tmp_path / "runtime.ts").write_text(runtime_source, encoding="utf-8")
    (tmp_path / "probe.ts").write_text(
        _TS_PROBE % {"runtime": "runtime.ts", "declared": _DECLARED_OP,
                     "typo": _TYPO_OP},
        encoding="utf-8")
    run = subprocess.run(
        ["node", "--experimental-strip-types", "probe.ts"],
        cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert "PASS" in run.stdout or "FAIL" in run.stdout, (
        f"probe produced no rows:\n{run.stdout}\n{run.stderr[:3000]}")
    return _results(run.stdout)


def test_web_refuses_an_undeclared_op(tmp_path):
    tc.tool("node")
    _assert_all(_run_ts(tmp_path, bt.RUNTIME_TS), "")


def test_web_control_without_the_guard_reports_the_old_behaviour(tmp_path):
    tc.tool("node")
    stripped = _strip_guard(bt.RUNTIME_TS, "      assertDeclared(op);\n")
    results = _run_ts(tmp_path, stripped)

    flipped = {k for k, v in results.items()
               if k in _EXPECTED and _EXPECTED[k] != v}
    assert flipped == _CONTROL_ROWS, (
        f"stripping the guard flipped {sorted(flipped)}, "
        f"expected {sorted(_CONTROL_ROWS)}")


# ---------------------------------------------------------------------------
# ios
# ---------------------------------------------------------------------------

def _swift_block(emitted: str, signature: str) -> str:
    i = emitted.index(signature)
    return emitted[i:emitted.index("\n}\n", i) + 3]


_SWIFT_SHIM = '''import Foundation

var recordedFailures: [String] = []
func XCTFail(_ m: String = "", file: StaticString = #filePath,
             line: UInt = #line) {
  recordedFailures.append(m)
}
'''

_SWIFT_MAIN = '''
func check(_ name: String, _ got: Bool) {
  print((got ? "PASS" : "FAIL") + " " + name)
}

let rec = Recorder(routeOps: ["%(declared)s"])
rec.calls.append(RecordedCall(op: "%(declared)s", method: "POST",
                              path: "/api/orders", body: ["a": 1]))
rec.calls.append(RecordedCall(op: "(unmatched)", method: "GET",
                              path: "/api/elsewhere", body: nil))

check("declared-count", rec.countFor("%(declared)s") == 1)
check("declared-body", (rec.lastBodyFor("%(declared)s") as? [String: Int]) == ["a": 1])
check("sentinel-count", rec.countFor("(unmatched)") == 1)
// Reading a correct name must not have failed anything.
check("declared-quiet", recordedFailures.isEmpty)

recordedFailures = []
_ = rec.countFor("%(typo)s")
let counted = recordedFailures
recordedFailures = []
_ = rec.lastBodyFor("%(typo)s")
let bodied = recordedFailures

check("undeclared-count-refused", !counted.isEmpty)
check("undeclared-body-refused", !bodied.isEmpty)
check("message-names-the-op", (counted.first ?? "").contains("%(typo)s"))
check("message-lists-declared", (counted.first ?? "").contains("%(declared)s"))
'''


def _run_swift(tmp_path: Path, runtime_source: str) -> dict[str, bool]:
    parts = [_swift_block(runtime_source, "struct RecordedCall {"),
             _swift_block(runtime_source, "private func quotedValue("),
             _swift_block(runtime_source, "final class Recorder {")]
    (tmp_path / "shim.swift").write_text(_SWIFT_SHIM, encoding="utf-8")
    (tmp_path / "runtime.swift").write_text(
        "import Foundation\n\n" + "\n\n".join(parts), encoding="utf-8")
    (tmp_path / "main.swift").write_text(
        _SWIFT_MAIN % {"declared": _DECLARED_OP, "typo": _TYPO_OP},
        encoding="utf-8")
    binary = tmp_path / "probe"
    build = subprocess.run(
        ["swiftc", "-Onone", "-o", str(binary), str(tmp_path / "shim.swift"),
         str(tmp_path / "runtime.swift"), str(tmp_path / "main.swift")],
        capture_output=True, text=True, timeout=600)
    assert build.returncode == 0, (
        f"emitted Swift did not compile:\n{build.stderr[:4000]}")
    run = subprocess.run([str(binary)], capture_output=True, text=True,
                         timeout=120)
    return _results(run.stdout)


def test_ios_refuses_an_undeclared_op(tmp_path):
    tc.tool("swiftc")
    results = _run_swift(tmp_path, bt.SWIFT_RUNTIME)
    _assert_all(results, "")
    # Swift's refusal is `XCTFail`, not a throw: `countFor` is called from
    # inside `XCTAssert...` at every generated site, and making it `throws`
    # would break every one of them — including the correct ones. The
    # property that matters is that the test goes RED, which XCTFail does.
    # This row says the guard is silent on a name that IS declared.
    assert results.get("declared-quiet") is True, results


def test_ios_control_without_the_guard_reports_the_old_behaviour(tmp_path):
    tc.tool("swiftc")
    stripped = _strip_guard(bt.SWIFT_RUNTIME, "    assertDeclared(op)\n")
    results = _run_swift(tmp_path, stripped)

    flipped = {k for k, v in results.items()
               if k in _EXPECTED and _EXPECTED[k] != v}
    assert flipped == _CONTROL_ROWS, (
        f"stripping the guard flipped {sorted(flipped)}, "
        f"expected {sorted(_CONTROL_ROWS)}")


# ---------------------------------------------------------------------------
# android
# ---------------------------------------------------------------------------

def _kotlin_block(emitted: str, signature: str) -> str:
    i = emitted.index(signature)
    return emitted[i:emitted.index("\n}\n", i) + 3]


_KOTLIN_MAIN = '''
fun check(name: String, got: Boolean) {
  println((if (got) "PASS" else "FAIL") + " " + name)
}

fun main() {
  val rec = Recorder(setOf("%(declared)s"))
  rec.calls.add(RecordedCall("%(declared)s", "POST", "/api/orders",
                             "{\\"a\\":1}"))
  rec.calls.add(RecordedCall("(unmatched)", "GET", "/api/elsewhere", null))

  check("declared-count", rec.countFor("%(declared)s") == 1)
  check("declared-body",
        rec.lastBodyFor("%(declared)s").toString() == "{\\"a\\":1}")
  check("sentinel-count", rec.countFor("(unmatched)") == 1)

  val counted = try { rec.countFor("%(typo)s"); null } catch (e: Throwable) { e.message }
  val bodied = try { rec.lastBodyFor("%(typo)s"); null } catch (e: Throwable) { e.message }
  check("undeclared-count-refused", counted != null)
  check("undeclared-body-refused", bodied != null)
  check("message-names-the-op", (counted ?: "").contains("%(typo)s"))
  check("message-lists-declared", (counted ?: "").contains("%(declared)s"))
}
'''


def _kotlin_probe_source(runtime_source: str) -> str:
    # `RecordedCall` is a ONE-LINE declaration with no body, so the
    # brace-to-brace slice used for the other two runs past it and swallows
    # the whole `Recorder` class — which the compiler then sees twice.
    # Taken by line for that reason.
    recorded_call = re.search(r"^data class RecordedCall\(.*$",
                              runtime_source, re.M).group(0)
    parts = [recorded_call,
             _kotlin_block(runtime_source, "private fun quotedValue("),
             _kotlin_block(runtime_source, "class Recorder(")]
    return ("\n\n".join(parts)
            + _KOTLIN_MAIN % {"declared": _DECLARED_OP, "typo": _TYPO_OP})


def _run_kotlin(tmp_path: Path, runtime_source: str) -> dict[str, bool]:
    return _results(tc.compile_and_run_kotlin(
        tmp_path, tc.KOTLIN_SHIM + "\n" + _kotlin_probe_source(runtime_source)
    ).stdout)


def test_android_refuses_an_undeclared_op(tmp_path):
    _assert_all(_run_kotlin(tmp_path, bt.KOTLIN_RUNTIME), "")


def test_android_control_without_the_guard_reports_the_old_behaviour(tmp_path):
    stripped = _strip_guard(bt.KOTLIN_RUNTIME, "    assertDeclared(op)\n")
    results = _run_kotlin(tmp_path, stripped)

    flipped = {k for k, v in results.items()
               if k in _EXPECTED and _EXPECTED[k] != v}
    assert flipped == _CONTROL_ROWS, (
        f"stripping the guard flipped {sorted(flipped)}, "
        f"expected {sorted(_CONTROL_ROWS)}")


# ---------------------------------------------------------------------------
# the population, read from the emitter rather than listed here
# ---------------------------------------------------------------------------

class TestEveryFaceHasTheGuard:
    """The runtimes are three emitters. A guard added to two of them is the
    shape of the defect it fixes, one layer up."""

    #: How each face spells "this recorded call is the op I was asked
    #: about". Counting THIS rather than the accessor names: a name can be
    #: added to an interface without reading anything, and the interface
    #: declaration carries the same spelling as the definition.
    _OP_MATCH = {"ts": "c.op === op", "kotlin": "it.op == op",
                 "swift": "$0.op == op"}

    #: Parametrized by NAME, with the source looked up inside. Passing the
    #: runtime text as a parameter puts the whole emitted file into the test
    #: id: `-v` printed 78 KB for three rows, and a CI log that long is one
    #: nobody reads to the end.
    _SOURCE = {"ts": "RUNTIME_TS", "kotlin": "KOTLIN_RUNTIME",
               "swift": "SWIFT_RUNTIME"}

    @pytest.mark.parametrize("name", ["ts", "kotlin", "swift"])
    def test_every_read_by_op_is_guarded(self, name):
        source = getattr(bt, self._SOURCE[name])
        reads = source.count(self._OP_MATCH[name])
        guards = source.count("assertDeclared(op)")

        # Derived on both sides. A third accessor that filters by op adds a
        # read and, if it is written without the guard, breaks the equality
        # — which is the failure this whole ticket is, one layer up.
        assert reads == 2, f"{name}: {reads} op comparison(s), expected 2"
        assert guards == reads, (
            f"{name}: {reads} read(s) by op but {guards} guard(s)")
        assert "(unmatched)" in source, f"{name}: sentinel missing"
