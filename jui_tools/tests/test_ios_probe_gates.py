"""conformance-mobile raises the iOS ConformanceHost probes' switches derived
from the UITests (.github/scripts/ios_probe_gates.py), and turns a gated probe
that skipped anyway red. Before jsonui-cli 1.9.23 nothing raised them but the
two image probes', and 23 classes / 40 tests with assertions never ran in a
dispatch (ticket conformance-mobile-ios-probe-guards-never-run-in-dispatch).
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "ios_probe_gates.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "conformance-mobile.yml"


def _load():
    spec = importlib.util.spec_from_file_location("ios_probe_gates", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gates = _load()


def _write(directory: Path, name: str, body: str) -> None:
    (directory / name).write_text(textwrap.dedent(body), encoding="utf-8")


class Derivation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_both_spellings_are_switches(self):
        _write(self.dir, "A.swift", '''
            final class AProbeUITests: XCTestCase {
                func testA() throws {
                    guard ProcessInfo.processInfo.environment["A_PROBE"] == "1" else { throw XCTSkip("") }
                }
            }
        ''')
        _write(self.dir, "B.swift", '''
            final class BProbeUITests: XCTestCase {
                func testB() throws {
                    let env = ProcessInfo.processInfo.environment
                    guard env["B_PROBE"] == "1" else { throw XCTSkip("") }
                }
            }
        ''')
        self.assertEqual(gates.scan(self.dir), {"A_PROBE": {"AProbeUITests"}, "B_PROBE": {"BProbeUITests"}})

    def test_what_is_not_a_switch(self):
        _write(self.dir, "C.swift", '''
            // every gate of the form `["X"] == "1"` is raised
            /* and ["Y"] == "1" in a block comment */
            final class CUITests: XCTestCase {
                func testC() throws {
                    let codegen = ProcessInfo.processInfo.environment["CONFORMANCE_HOST_MODE"] == "1"
                    if ProcessInfo.processInfo.environment["MARKERS_OFF"] != "1" {}
                    let paths = ProcessInfo.processInfo.environment["C_PATHS"] ?? "a,b"
                    _ = (codegen, paths)
                }
            }
        ''')
        self.assertEqual(gates.scan(self.dir), {})

    def test_a_switch_is_followed_without_a_list(self):
        # The point of deriving: a new probe is raised with no workflow edit.
        _write(self.dir, "A.swift", 'final class AUITests: XCTestCase { func t() { _ = env["A_PROBE"] == "1" } }\n')
        before = set(gates.scan(self.dir))
        _write(self.dir, "New.swift", 'final class NewUITests: XCTestCase { func t() { _ = env["NEW_PROBE"] == "1" } }\n')
        self.assertEqual(set(gates.scan(self.dir)) - before, {"NEW_PROBE"})

    def test_exports_are_test_runner_variables(self):
        _write(self.dir, "A.swift", 'final class AUITests: XCTestCase { func t() { _ = env["A_PROBE"] == "1" } }\n')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(gates.main(["x", "exports", str(self.dir)]), 0)
        self.assertEqual(out.getvalue().splitlines(), ["TEST_RUNNER_A_PROBE=1"])


class Check(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "UITests"
        self.dir.mkdir()
        _write(self.dir, "A.swift", 'final class AProbeUITests: XCTestCase { func t() { _ = env["A_PROBE"] == "1" } }\n')
        _write(self.dir, "Plain.swift", 'final class PlainUITests: XCTestCase {}\n')
        self.record = Path(self.tmp.name) / "xctests.txt"

    def tearDown(self):
        self.tmp.cleanup()

    def _check(self, lines: list[str]) -> int:
        self.record.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            return gates.check(self.record, self.dir)

    def test_a_gated_probe_that_ran_is_green(self):
        self.assertEqual(self._check([
            "Test Case '-[ConformanceHostUITests.AProbeUITests testOne]' passed (1.0 seconds).",
            "Test Case '-[ConformanceHostUITests.PlainUITests testP]' skipped (0.1 seconds).",
        ]), 0)

    def test_a_gated_probe_that_skipped_is_red(self):
        self.assertEqual(self._check([
            "Test Case '-[ConformanceHostUITests.AProbeUITests testOne]' passed (1.0 seconds).",
            "Test Case '-[ConformanceHostUITests.AProbeUITests testTwo]' skipped (0.1 seconds).",
        ]), 1)

    def test_a_gated_class_missing_from_the_record_is_red(self):
        self.assertEqual(self._check([
            "Test Case '-[ConformanceHostUITests.PlainUITests testP]' passed (0.1 seconds).",
        ]), 1)

    def test_a_failed_probe_is_left_to_the_suite(self):
        # check judges "did it run"; a failure is the suite step's to report.
        self.assertEqual(self._check([
            "Test Case '-[ConformanceHostUITests.AProbeUITests testOne]' failed (1.0 seconds).",
        ]), 0)


class Workflow(unittest.TestCase):
    """The two iOS jobs raise the derived switches and check them; nothing
    else does (the tap-repro job runs no probe)."""

    def test_the_ios_jobs_raise_and_check_the_derived_switches(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("ios_probes:", text)
        self.assertEqual(text.count("ios_probe_gates.py exports SwiftJsonUI/ConformanceHost/UITests"), 2)
        self.assertEqual(text.count("ios_probe_gates.py check "), 2)
        self.assertIn("ios_probe_gates.py check /tmp/jsonui-conformance-ios.ci/xctests.txt", text)
        self.assertIn("ios_probe_gates.py check /tmp/jsonui-conformance-ios-codegen.ci/xctests.txt", text)


if __name__ == "__main__":
    unittest.main()
