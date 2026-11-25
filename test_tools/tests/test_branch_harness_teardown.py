"""The harness's `tearDown`: called after every generated test, on all three
platforms, whether the test passed or failed.

Reported from a consumer's Android face: a row's response set a flag on a
Kotlin `object`, and Robolectric keeps one class loader across test classes,
so the flag outlived the test. The harness factory runs BEFORE a case, so a
harness could put the flag back only for the next row of its own screen;
the last row's flag stayed for whatever test ran next. No face of the
library had a hook after a case (iOS consumers used XCTestObservation, web
ones could use a setupFiles afterEach), so the member is added on all three
under one name, and the parity check (test_branch_harness_members) holds it.

What every face must keep:
- called when the block passed and when it failed;
- not called when the harness factory failed (there is no harness);
- a failure in tearDown fails a test that passed, and never hides the
  failure of a test that had already failed (Android: suppressed on the
  block's; web: printed, the test's thrown; iOS: tearDown does not throw);
- a harness written without it compiles and runs as before.

Here: the Swift runtime compiled with swiftc and run on macOS (XCTest's
asserts stood in), and the web face's GENERATED test file run under the
vitest stand-in — CI's branch-runtime step, with the compilers. The Kotlin
runtime is compiled whole and run on the JVM in
test_branch_harness_teardown_android.py (pinned jars from a Gradle cache:
run-suites.sh's Android leg). The generated web test is type-checked with
the pinned tsc, against a harness with no tearDown, in
test_emitted_typescript_compiles.py (python-suite, where tsc is installed).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from jsonui_test_cli import branch_tests as bt
from tests import _toolchain as tc
from tests.test_branch_act_window_and_bound import _HOOKS, _REGISTER, _VITEST
from tests.test_branch_scenario_delay import _SWIFT_SHIM
from tests.test_harness_conditions import _SUMMARY_HARNESS, _SUMMARY_RUNNER, _generate, _summary


# -------------------------------------------------------------------- ios --

_SWIFT_MAIN = '''import Foundation
nonisolated(unsafe) var log: [String] = []
struct BlockFailure: Error {}

/// Overrides tearDown on BaseBranchHarness.
final class CleaningHarness: BaseBranchHarness {
  override func tearDown() { log.append("sub.tearDown") }
}

/// Written before tearDown: BaseBranchHarness, no override.
final class OlderHarness: BaseBranchHarness {}

/// Conforms itself, without BaseBranchHarness and without tearDown.
final class OwnHarness: BranchHarness {
  let vm: AnyObject = NSObject()
  func readField(_ name: String) -> Any? { nil }
  func setState(_ state: [String: Any]) {}
  func invoke(_ name: String, args: [Any]) {}
  func expectTransition(_ destination: String) {}
  func resolveString(_ key: String) -> String { key }
  func settle() {}
}

/// Conforms itself and declares tearDown.
final class OwnCleaningHarness: BranchHarness {
  let vm: AnyObject = NSObject()
  func readField(_ name: String) -> Any? { nil }
  func setState(_ state: [String: Any]) {}
  func invoke(_ name: String, args: [Any]) {}
  func expectTransition(_ destination: String) {}
  func resolveString(_ key: String) -> String { key }
  func settle() {}
  func tearDown() { log.append("own.tearDown") }
}

let kind = CommandLine.arguments[1]
let fails = CommandLine.arguments.count > 2 && CommandLine.arguments[2] == "block-fails"
let make: () -> BranchHarness = {
  switch kind {
  case "sub": return CleaningHarness(vm: NSObject())
  case "older": return OlderHarness(vm: NSObject())
  case "own": return OwnHarness()
  default: return OwnCleaningHarness()
  }
}
do {
  try runBranchTest(routes: [], overrides: [:], harnessFactory: make) { _, _ in
    log.append("block")
    if fails { throw BlockFailure() }
  }
  print("THROWN none")
} catch {
  print("THROWN \\(type(of: error))")
}
print("LOG \\(log.joined(separator: ","))")
'''


@pytest.fixture(scope="module")
def swift_binary(tmp_path_factory) -> Path:
    tc.tool("swiftc")
    runtime = bt.SWIFT_RUNTIME
    assert runtime.count("\nimport XCTest\n") == 1
    work = tmp_path_factory.mktemp("teardown-ios")
    (work / "shim.swift").write_text(_SWIFT_SHIM, encoding="utf-8")
    (work / "runtime.swift").write_text(runtime.replace("\nimport XCTest\n", "\n", 1), encoding="utf-8")
    (work / "main.swift").write_text(_SWIFT_MAIN, encoding="utf-8")
    binary = work / "prog"
    build = subprocess.run(
        ["swiftc", "-Onone", "-o", str(binary), str(work / "shim.swift"),
         str(work / "runtime.swift"), str(work / "main.swift")],
        capture_output=True, text=True, timeout=600)
    assert build.returncode == 0, f"emitted runtime did not compile:\n{build.stderr[:4000]}"
    return binary


def _swift_run(binary: Path, *args: str) -> dict:
    run = subprocess.run([str(binary), *args], capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[:3000]
    return dict(line.split(" ", 1) if " " in line else (line, "")
                for line in run.stdout.strip().splitlines())


@pytest.mark.parametrize("fails", [False, True])
def test_ios_a_subclass_override_is_the_teardown_called(swift_binary, fails):
    """Through the protocol, a BaseBranchHarness subclass's override runs —
    not the extension's default, which a call through the protocol would
    reach statically were the member declared in the extension alone."""
    got = _swift_run(swift_binary, "sub", *(["block-fails"] if fails else []))
    assert got["LOG"] == "block,sub.tearDown", got
    assert got["THROWN"] == ("BlockFailure" if fails else "none"), got


def test_ios_a_conformance_of_its_own_gets_its_teardown_called(swift_binary):
    got = _swift_run(swift_binary, "own-cleaning", "block-fails")
    assert got["LOG"] == "block,own.tearDown" and got["THROWN"] == "BlockFailure", got


def test_ios_control_declared_in_the_extension_alone_the_subclass_is_skipped(tmp_path):
    """The control for the arm above: without the member on
    BaseBranchHarness, a subclass's `tearDown` (no `override` then) is not
    reached through the protocol — the extension's default runs instead."""
    tc.tool("swiftc")
    base = ("  /// Override to put back what a test left behind (see\n"
            "  /// BranchHarness.tearDown). Declared here, not only in the protocol's\n"
            "  /// extension, so a subclass's override is the one runBranchTest calls.\n"
            "  func tearDown() {}\n")
    runtime = bt.SWIFT_RUNTIME
    assert runtime.count(base) == 1
    (tmp_path / "shim.swift").write_text(_SWIFT_SHIM, encoding="utf-8")
    (tmp_path / "runtime.swift").write_text(
        runtime.replace(base, "").replace("\nimport XCTest\n", "\n", 1), encoding="utf-8")
    main = _SWIFT_MAIN.replace("  override func tearDown() { log.append(\"sub.tearDown\") }",
                               "  func tearDown() { log.append(\"sub.tearDown\") }")
    assert main != _SWIFT_MAIN
    (tmp_path / "main.swift").write_text(main, encoding="utf-8")
    binary = tmp_path / "prog"
    build = subprocess.run(["swiftc", "-Onone", "-o", str(binary), str(tmp_path / "shim.swift"),
                            str(tmp_path / "runtime.swift"), str(tmp_path / "main.swift")],
                           capture_output=True, text=True, timeout=600)
    assert build.returncode == 0, build.stderr[:4000]
    assert _swift_run(binary, "sub")["LOG"] == "block", "the control did not fall to the default"


@pytest.mark.parametrize("kind", ["older", "own"])
def test_ios_a_harness_without_teardown_compiles_and_runs(swift_binary, kind):
    got = _swift_run(swift_binary, kind)
    assert got["LOG"] == "block" and got["THROWN"] == "none", got


# -------------------------------------------------------------------- web --

_ROWS = [
    {"when": {"api.getOrder": "default"}, "then": {"data.status": "ready"}},
    {"when": {"api.getOrder": "default"}, "then": {"data.status": "never"}},
]

#: The summary harness, with a tearDown that logs (and throws when asked).
_CLEANING_HARNESS = _SUMMARY_HARNESS.replace(
    "    resolveString(key: string) { return key; },\n",
    "    resolveString(key: string) { return key; },\n"
    "    async tearDown() {\n"
    "      cleaned.push(vm.status);\n"
    "      if (teardownThrows.on) throw new Error(\"from tearDown\");\n"
    "    },\n",
).replace("export function createHarness() {",
          "export const cleaned: string[] = [];\n"
          "export const teardownThrows = { on: false };\n"
          "export function createHarness() {")
assert _CLEANING_HARNESS.count("async tearDown()") == 1

_SESSION_STATE = "export const session = { present: false };\n"


def _web_project(root: Path, harness: str, *, throws: bool = False) -> Path:
    _summary(root, conditions=None, rows=_ROWS)
    _generate(root)
    harness_dir = root / "tests/unit/branch-harness"
    (harness_dir / "summary.ts").write_text(harness, encoding="utf-8")
    (harness_dir / "session-state.ts").write_text(_SESSION_STATE, encoding="utf-8")
    vitest = root / "node_modules/vitest"
    vitest.mkdir(parents=True, exist_ok=True)
    (vitest / "package.json").write_text(
        '{"name": "vitest", "type": "module", "main": "index.js", "types": "index.d.ts"}',
        encoding="utf-8")
    (vitest / "index.js").write_text(_VITEST, encoding="utf-8")
    (vitest / "index.d.ts").write_text(
        "export declare function describe(name: string, fn: () => void): void;\n"
        "export declare function it(name: string, fn: () => unknown, timeout?: number): void;\n"
        "export declare function expect(actual: unknown, message?: string): any;\n"
        "export declare function run(): Promise<void>;\n", encoding="utf-8")
    (root / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (root / "hooks.mjs").write_text(_HOOKS, encoding="utf-8")
    (root / "register.mjs").write_text(_REGISTER, encoding="utf-8")
    runner = _SUMMARY_RUNNER
    if "cleaned" in harness:
        runner = ('import { cleaned, teardownThrows } from "./tests/unit/branch-harness/summary.ts";\n'
                  f"teardownThrows.on = {'true' if throws else 'false'};\n"
                  + runner + 'console.log(`CLEANED ${cleaned.join(",")}`);\n')
    (root / "runner.mjs").write_text(runner, encoding="utf-8")
    return root


def _web_run(root: Path) -> tuple[list[str], str]:
    tc.tool("node")
    run = subprocess.run(
        ["node", "--experimental-strip-types", "--import", "./register.mjs", "runner.mjs"],
        cwd=root, capture_output=True, text=True, timeout=120)
    lines = [l for l in run.stdout.splitlines() if l.startswith(("PASS ", "FAIL ", "CLEANED "))]
    assert len([l for l in lines if not l.startswith("CLEANED")]) == 2, run.stdout + run.stderr[-3000:]
    return lines, run.stderr


def test_web_teardown_runs_after_a_test_that_passed_and_one_that_failed(tmp_path):
    lines, _ = _web_run(_web_project(tmp_path / "p", _CLEANING_HARNESS))
    assert lines[0].startswith("PASS ") and lines[1].startswith("FAIL "), lines
    assert "expected \"never\"" in lines[1], lines
    assert lines[2] == "CLEANED ready,ready", lines           # both, after the act


def test_web_a_failing_teardown_never_hides_the_tests_failure(tmp_path):
    lines, err = _web_run(_web_project(tmp_path / "p", _CLEANING_HARNESS, throws=True))
    # Passed, then tearDown threw: the test fails with tearDown's error.
    assert lines[0].startswith("FAIL ") and lines[0].endswith(":: from tearDown"), lines
    # Failed already: the test's own failure is reported, tearDown's printed.
    assert lines[1].startswith("FAIL ") and "expected \"never\"" in lines[1], lines
    printed = [l for l in err.splitlines() if "tearDown failed after the test had already failed" in l]
    assert len(printed) == 1 and "from tearDown" in printed[0], err[-2000:]


def test_web_a_harness_without_teardown_runs_as_before(tmp_path):
    lines, _ = _web_run(_web_project(tmp_path / "p", _SUMMARY_HARNESS))
    assert lines[0].startswith("PASS ") and lines[1].startswith("FAIL "), lines


def test_web_control_a_teardown_error_thrown_regardless_hides_the_tests_failure(tmp_path):
    """The control for the arm above: a tearDownHarness that throws whatever
    happened puts tearDown's error over the failed test's own."""
    root = _web_project(tmp_path / "p", _CLEANING_HARNESS, throws=True)
    runtime = root / "tests/unit/generated/jsonui-branch-runtime.ts"
    text = runtime.read_text(encoding="utf-8")
    assert text.count("    if (testPassed) throw e;\n") == 1
    runtime.write_text(text.replace("    if (testPassed) throw e;\n", "    throw e;\n"), encoding="utf-8")
    lines, _ = _web_run(root)
    assert lines[1].startswith("FAIL ") and lines[1].endswith(":: from tearDown"), lines
