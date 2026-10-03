"""The step that names the failed iOS conformance tests.

.github/scripts/name_failed_xctests.py reads the run's xcodebuild.log when
conformance-mobile's `ios` / `ios-codegen` suite step fails. The jobs need a
simulator, so only a hosted runner reaches the step, but the reader is plain
Python and is checked here on every push.

The lines below are xcodebuild's own shapes, copied from a local codegen run
that failed (13 `' failed (` lines, 13 named).
"""
from __future__ import annotations

import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "name_failed_xctests.py"


def _load():
    spec = importlib.util.spec_from_file_location("name_failed_xctests", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


N = _load()

FAILED_RUN = """\
Test Case '-[ConformanceHostUITests.WrapMaxProbeUITests testAWrapContentAxisWithAMaxSizesToItsContentDynamic]' started.
Test Case '-[ConformanceHostUITests.WrapMaxProbeUITests testAWrapContentAxisWithAMaxSizesToItsContentDynamic]' passed (11.600 seconds).
Test Case '-[ConformanceHostUITests.CollectionFitProbeUITests testAWrapContentCollectionSizesToItsContentGenerated]' started.
/tmp/ci/x/SwiftJsonUI/ConformanceHost/UITests/CollectionFitProbeUITests.swift:71: error: -[ConformanceHostUITests.CollectionFitProbeUITests testAWrapContentCollectionSizesToItsContentGenerated] : XCTAssertEqual failed: ("120.0") is not equal to ("44.0")
Test Case '-[ConformanceHostUITests.CollectionFitProbeUITests testAWrapContentCollectionSizesToItsContentGenerated]' failed (4.833 seconds).
Test Case '-[ConformanceHostUITests.CollectionFitProbeUITests testAWrapContentCollectionSizesToItsContentGenerated]' failed (4.833 seconds).
Test Suite 'ConformanceHostUITests.xctest' failed at 2026-10-03 10:53:54.542.
\t Executed 95 tests, with 61 tests skipped and 1 failure (0 unexpected) in 3099.067 (3099.153) seconds
"""

COMPILE_ERROR_RUN = """\
/tmp/ci/x/SwiftJsonUI/ConformanceHost/CodegenStaging/View/Fx0997/Fx0997GeneratedView.swift:12:5: error: cannot find 'foo' in scope
** TEST FAILED **
"""


class NameFailedXCTestsTest(unittest.TestCase):
    def run_on(self, text: str) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "xcodebuild.log"
            log.write_text(text)
            out = io.StringIO()
            N.report(str(log), N.read_log(text), out=out)
            rc = N.main([str(log)])
        return rc, out.getvalue()

    def test_names_the_failed_case_once_and_not_the_passed_one(self):
        found = N.read_log(FAILED_RUN)
        self.assertEqual(found["cases"], [
            "-[ConformanceHostUITests.CollectionFitProbeUITests "
            "testAWrapContentCollectionSizesToItsContentGenerated]"])
        rc, out = self.run_on(FAILED_RUN)
        self.assertEqual(rc, 0)
        self.assertIn("1 failed test case(s), 1 error line(s)", out)
        self.assertIn("::error title=iOS conformance test failed::-[ConformanceHostUITests."
                      "CollectionFitProbeUITests", out)
        self.assertIn("XCTAssertEqual failed", out)
        self.assertIn("Executed 95 tests, with 61 tests skipped and 1 failure", out)
        self.assertNotIn("WrapMaxProbeUITests", out)
        self.assertNotIn("names no failed test case", out)

    def test_a_run_that_never_reached_its_tests_says_so(self):
        rc, out = self.run_on(COMPILE_ERROR_RUN)
        self.assertEqual(rc, 0)
        self.assertIn("0 failed test case(s), 1 error line(s)", out)
        self.assertIn("cannot find 'foo' in scope", out)
        self.assertIn("the log names no failed test case", out)

    def test_a_missing_log_is_not_read_as_nothing_failed(self):
        # The step's shell passes an unmatched glob through as is.
        self.assertEqual(N.main(["/tmp/jsonui-conformance-ios.*/xcodebuild.log"]), 1)
        self.assertEqual(N.main([]), 1)


if __name__ == "__main__":
    unittest.main()
