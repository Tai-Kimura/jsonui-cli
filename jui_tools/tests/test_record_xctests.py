"""The step that records every iOS conformance XCTest result.

.github/scripts/record_xctests.py runs after the ios / ios-codegen suite step
on every run, green or red. The jobs need a simulator, so only a hosted runner
reaches the step; the reader is plain Python and is checked here on every
push. The lines are xcodebuild's own shapes (a local codegen run recorded 93
test cases against its "Executed 93 tests").
"""
from __future__ import annotations

import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "record_xctests.py"


def _load():
    spec = importlib.util.spec_from_file_location("record_xctests", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = _load()

GREEN_RUN = """\
Test Suite 'All tests' started at 2026-10-04 08:00:00.000.
Test Case '-[ConformanceHostUITests.PagerIdentityProbeUITests testAPageKeepsItsPlace]' started.
Test Case '-[ConformanceHostUITests.PagerIdentityProbeUITests testAPageKeepsItsPlace]' passed (12.100 seconds).
Test Case '-[ConformanceHostUITests.PagerIdentityProbeUITests testAPageKeepsItsPlaceGenerated]' skipped (0.170 seconds).
Test Case '-[ConformanceHostUITests.WrapMaxProbeUITests testAWrapContentAxisWithAMaxSizesToItsContentDynamic]' failed (4.000 seconds).
Test Case '-[ConformanceHostUITests.WrapMaxProbeUITests testAWrapContentAxisWithAMaxSizesToItsContentDynamic]' passed (11.600 seconds).
Test Suite 'All tests' passed at 2026-10-04 08:50:00.000.
\t Executed 3 tests, with 1 test skipped and 0 failures (0 unexpected) in 23.870 (23.871) seconds
"""


class RecordXCTestsTest(unittest.TestCase):
    def run_on(self, text: str) -> tuple[int, str, str]:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "xcodebuild.log"
            log.write_text(text)
            out_file = Path(tmp) / "record" / "ios-xctests.txt"
            printed = io.StringIO()
            R.summarize(R.read_log(text), out=printed)
            rc = R.main([str(log), str(out_file)])
            return rc, printed.getvalue(), out_file.read_text()

    def test_a_green_run_records_its_passed_tests_and_prints_a_line_per_class(self):
        rc, printed, record = self.run_on(GREEN_RUN)
        self.assertEqual(rc, 0)
        self.assertIn("PagerIdentityProbeUITests: 1 passed, 0 failed, 1 skipped", printed)
        self.assertIn("[xctest record] 3 test(s) in 2 class(es): 2 passed, 0 failed, 1 skipped", printed)
        self.assertIn("PagerIdentityProbeUITests testAPageKeepsItsPlace]' passed", record)
        self.assertEqual(len(record.splitlines()), 3)
        self.assertNotIn("::warning", printed)

    def test_a_retried_test_keeps_its_last_verdict(self):
        _, printed, record = self.run_on(GREEN_RUN)
        self.assertIn("WrapMaxProbeUITests: 1 passed, 0 failed, 0 skipped", printed)
        self.assertNotIn("Dynamic]' failed", record)

    def test_the_total_is_held_against_the_runs_own_executed_count(self):
        short = GREEN_RUN.replace("Executed 3 tests", "Executed 4 tests")
        _, printed, _ = self.run_on(short)
        self.assertIn("::warning title=XCTest record::3 test case line(s) recorded, but the run says it executed 4",
                      printed)

    def test_a_run_that_did_not_finish_says_so(self):
        cut = GREEN_RUN.split("Test Suite 'All tests' passed")[0]
        _, printed, _ = self.run_on(cut)
        self.assertIn("the log has no 'All tests' summary", printed)

    def test_a_missing_log_is_not_read_as_nothing_ran(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(R.main(["/tmp/jsonui-conformance-ios.ci/xcodebuild.log.absent",
                                     str(Path(tmp) / "x.txt")]), 1)
        self.assertEqual(R.main([]), 1)


if __name__ == "__main__":
    unittest.main()
