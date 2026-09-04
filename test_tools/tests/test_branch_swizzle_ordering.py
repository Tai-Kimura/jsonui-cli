"""The swizzle survives BOTH entry points, in either order — measured by running it.

Consumer report (2026-09-04, after 1.8.27 landed): the ordering property has
no regression guard on our side. `method_exchangeImplementations` TOGGLES, so
interception is order-independent only because TWO things hold together:

  1. `installOnce()` exchanges at most once per process (lock + flag), and
  2. every entry point — `installBranchURLInterception`, `withBranchRoutes`
     AND `runBranchTest` — goes through that one installer.

Touch either one alone and the unit-level check of the other stays green. The
break then shows up only when a hand-written unit test and the generated branch
suite share a process, which is exactly where it is hardest to attribute: the
damage depends on XCTest's class execution order, so it is intermittent and
does not point at the version that caused it.

The consumer's own 70-passed co-residency run is NOT this guard, and they said
so themselves: it is "the order xcodebuild happened to pick today", not a swept
property. So this measures it here, by compiling the EMITTED runtime and
running the entry points in each order in a fresh process.

Why compile-and-run rather than assert on the source text: a string assertion
("`runBranchTest` contains `installBranchURLInterception()`") restates the rule
instead of testing it, and cannot see a flag that is present but wrong. The
cost is one `swiftc -Onone` of the 25KB runtime, module-scoped: measured 0.48s
setup plus ~10ms per arm, 0.86s for the file. macOS only.

⚠️ The file under test is byte-identical to what ships except for one stripped
line, `import XCTest` — the 6 XCTest call sites are shimmed below. The swizzle
machinery itself is untouched.

Red-check (2026-09-04, all four predictions registered BEFORE running):

    arm                  baseline   guard removed   runBranchTest bypasses
    UNIT_THEN_BRANCH     green      RED             green
    BRANCH_THEN_UNIT     green      RED             green
    BRANCH_ONLY          green      green           RED
    UNIT_ONLY            green      green           green
    NONE                 RED        RED             RED

Three things that table buys, none of which a single arm would:
  * the two mutants have DIFFERENT red sets, so a failure names which of the
    two invariants broke rather than only that one did;
  * NONE is red everywhere — the probe can read "not intercepting", so a green
    arm is not a stuck instrument;
  * UNIT_ONLY is green under both mutants, which is correct and is why it is
    kept: it is the single-entry control that says the mutants break the
    INTERACTION, not installation as such.

⚠️ The even/odd trap this table was rebuilt to avoid: the first draft ran three
installs per arm. Three exchanges is odd, so the toggle-bug mutant ends up
installed and the arm was green FOR the defect. Each arm now makes exactly two
entries, where a lost guard is visible. An odd-count arm cannot see it at all.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from test_branch_tests_generator import SEEDABLE, _project  # noqa: E402

from jsonui_test_cli.branch_tests import generate_branch_tests  # noqa: E402

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("swiftc") is None,
    reason="needs swiftc (macOS); the property is about the emitted Swift",
)

# The 6 XCTest call sites in the emitted runtime, stood up so the file compiles
# outside a test target. Failures print rather than abort: no arm below asserts
# through them, and swallowing one would only ever make an arm greener, which
# the NONE control would catch.
_SHIM = """import Foundation
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

# Each arm makes exactly TWO entries (see the even/odd note above), except the
# single-entry controls. Interception is read off the swizzled getter, which is
# the thing a consumer's URLSession(configuration: .default) actually consults.
_MAIN = """import Foundation
func interceptionActive() -> Bool {
  guard let first = URLSessionConfiguration.default.protocolClasses?.first else { return false }
  return ObjectIdentifier(first) == ObjectIdentifier(BranchURLProtocol.self)
}
let dummy = NSObject()
func viaRunBranchTest() {
  runBranchTest(routes: [], overrides: [:],
                harnessFactory: { BaseBranchHarness(vm: dummy) }, block: { _, _ in })
}
let mode = CommandLine.arguments.dropFirst().first ?? "NONE"
switch mode {
case "UNIT_THEN_BRANCH": installBranchURLInterception(); viaRunBranchTest()
case "BRANCH_THEN_UNIT": viaRunBranchTest(); installBranchURLInterception()
case "BRANCH_ONLY":      viaRunBranchTest()
case "UNIT_ONLY":        installBranchURLInterception()
default: break
}
print("\\(mode)=\\(interceptionActive())")
exit(interceptionActive() ? 0 : 1)
"""


@pytest.fixture(scope="module")
def program(tmp_path_factory) -> Path:
    """Compile the emitted runtime once; every arm runs it in a fresh process.

    Fresh processes are the point — the flag is per-process, so two arms in one
    process would measure the first arm's leftovers.
    """
    work = tmp_path_factory.mktemp("swizzle")
    root = _project(work, SEEDABLE)
    result = generate_branch_tests(
        "checkout", root, platform="ios", module="checkout_app",
        out_dir="Tests/Generated", harness_dir="Tests/Generated",
    )
    emitted = result.runtime_file.read_text(encoding="utf-8")

    # Assert the one modification is the one intended: exactly the import, and
    # nothing in the swizzle. If the emitted file ever stops importing XCTest
    # this silently becomes a no-op, so it is checked rather than assumed.
    assert emitted.count("\nimport XCTest\n") == 1, "expected exactly one XCTest import"
    runtime = emitted.replace("\nimport XCTest\n", "\n", 1)

    (work / "shim.swift").write_text(_SHIM, encoding="utf-8")
    (work / "runtime.swift").write_text(runtime, encoding="utf-8")
    (work / "main.swift").write_text(_MAIN, encoding="utf-8")
    binary = work / "prog"
    proc = subprocess.run(
        ["swiftc", "-Onone", "-o", str(binary),
         str(work / "shim.swift"), str(work / "runtime.swift"), str(work / "main.swift")],
        capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 0, f"emitted runtime did not compile:\n{proc.stderr[:4000]}"
    return binary


def _intercepting(program: Path, mode: str) -> bool:
    proc = subprocess.run([str(program), mode], capture_output=True, text=True, timeout=120)
    assert proc.stdout.strip() in (f"{mode}=true", f"{mode}=false"), (
        f"arm did not report: rc={proc.returncode} out={proc.stdout!r} err={proc.stderr[:2000]!r}"
    )
    return proc.stdout.strip() == f"{mode}=true"


def test_unit_entry_then_branch_test_keeps_interception(program):
    """A hand-written unit test installs first; a branch test then runs.

    RED when the idempotence guard is gone: two exchanges toggle it back off.
    """
    assert _intercepting(program, "UNIT_THEN_BRANCH")


def test_branch_test_then_unit_entry_keeps_interception(program):
    """The reverse order. Same two entries, opposite sequence.

    Both orders are kept because the guard and the shared installer are not
    symmetric in the source, so one order going green is not evidence for the
    other. XCTest picks the order, not us.
    """
    assert _intercepting(program, "BRANCH_THEN_UNIT")


def test_a_branch_test_alone_intercepts(program):
    """RED when `runBranchTest` stops routing through the shared installer.

    This is the arm the two-entry orders cannot see: bypassing the installer
    leaves each entry point working alone, and only a branch-suite-only process
    reveals that the generated suite is no longer intercepting anything.
    """
    assert _intercepting(program, "BRANCH_ONLY")


def test_a_unit_entry_alone_intercepts(program):
    """Single-entry control. Green under BOTH mutants above, deliberately.

    It is what makes the other arms' red mean "the interaction broke" rather
    than "installation broke".
    """
    assert _intercepting(program, "UNIT_ONLY")


def test_nothing_intercepts_before_any_entry_point_runs(program):
    """The probe's own control: it must be able to read "not intercepting".

    Without this, all four arms above could be green because
    `interceptionActive()` is stuck true — a swizzle test that cannot observe
    the un-swizzled state proves nothing about the swizzled one.
    """
    assert not _intercepting(program, "NONE")
