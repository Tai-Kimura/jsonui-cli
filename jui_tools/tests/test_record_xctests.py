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

    # The tap timing distribution (SwiftJsonUI ConformanceHost prints one
    # TAP_TIMING line per tap): a number to look at, not a wait.
    def test_the_tap_timing_lines_become_a_distribution_with_the_fastest_named(self):
        lines = "".join(
            f"TAP_TIMING Switch/f{i} target +{at:.3f}s exists=true hittable=true frame=(0,0,1,1)\n"
            for i, at in enumerate([1.2, 0.4, 3.0, 1.1, 0.9, 2.2, 1.0, 1.4, 0.7, 5.0, 1.3])
        )
        found = R.read_log(GREEN_RUN + lines)
        printed = io.StringIO()
        R.tap_timing(found, out=printed)
        text = printed.getvalue()
        self.assertIn("[tap timing] 11 tap(s) after the fixture marker: min 0.400s, p10 0.700s, "
                      "median 1.200s, p90 3.000s, max 5.000s", text)
        self.assertIn("fastest: +0.400s Switch/f1 (target)", text)
        self.assertEqual(text.count("fastest:"), 5)
        self.assertIn("slowest: +5.000s Switch/f9 (target)", text)
        self.assertEqual(text.count("slowest:"), 5)
        # No tap is named twice: 11 taps, 5 fastest + 5 slowest of the rest.
        named = [line.split()[-2] for line in text.splitlines() if "fastest:" in line or "slowest:" in line]
        self.assertEqual(len(named), len(set(named)))

    def test_a_log_without_tap_timing_says_so(self):
        printed = io.StringIO()
        R.tap_timing(R.read_log(GREEN_RUN), out=printed)
        self.assertIn("no TAP_TIMING lines", printed.getvalue())

    # The distribution and the fastest / slowest five are made of each
    # fixture's FIRST tap; a multi-step fixture's later taps (Embed: push, then
    # two pops) are listed apart. These are the shapes of the local run that
    # replaced v1.9.15's unavailable log (9 lines).
    def test_first_taps_make_the_distribution_and_later_taps_are_listed_apart(self):
        rows = [("Embed/pop_boundary", "push-button", 1.043, 1.043, 1),
                ("Embed/pop_boundary", "pop-button", 3.975, 2.893, 2),
                ("Embed/pop_boundary", "pop-button", 6.879, 2.860, 3)]
        rows += [(f"common/f{i}", "target", 1.08 + i / 100, 1.08 + i / 100, 1) for i in range(6)]
        lines = "".join(f"TAP_TIMING {f} {i} +{at:.3f}s prev=+{prev:.3f}s n={n} exists=true hittable=true frame=(0,0,1,1)\n"
                        for f, i, at, prev, n in rows)
        printed = io.StringIO()
        R.tap_timing(R.read_log(GREEN_RUN + lines), out=printed)
        text = printed.getvalue()
        self.assertIn("[tap timing] 7 first tap(s) of their fixture after the fixture marker: min 1.043s", text)
        self.assertIn("max 1.130s", text)
        self.assertIn("driver's waitFor reaching its first check", text)
        dist = [l for l in text.splitlines() if "fastest:" in l or "slowest:" in l]
        self.assertFalse(any("pop-button" in l for l in dist), text)
        self.assertIn("[tap timing] 2 later tap(s) of multi-step fixtures (n>=2), apart:", text)
        self.assertIn("later: Embed/pop_boundary (pop-button, tap 2): prev +2.893s, +3.975s from the marker", text)
        self.assertIn("later: Embed/pop_boundary (pop-button, tap 3): prev +2.860s, +6.879s from the marker", text)
        self.assertNotIn("no n= / prev=", text)

    def test_the_raw_lines_are_kept_beside_the_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "xcodebuild.log"
            log.write_text(GREEN_RUN + "TAP_TIMING Switch/a target +1.100s prev=+1.100s n=1 x\n")
            self.assertEqual(R.main([str(log), str(Path(tmp) / "rec" / "xctests.txt")]), 0)
            self.assertEqual((Path(tmp) / "rec" / "tap_timing.txt").read_text(),
                             "TAP_TIMING Switch/a target +1.100s prev=+1.100s n=1 x\n")

    def test_old_lines_without_prev_fall_back_to_the_marker_and_say_so(self):
        lines = "TAP_TIMING Switch/a target +7.000s exists=true hittable=true frame=(0,0,1,1)\n"
        printed = io.StringIO()
        R.tap_timing(R.read_log(GREEN_RUN + lines), out=printed)
        self.assertIn("1 tap(s) after the fixture marker: min 7.000s", printed.getvalue())
        self.assertIn("no n= / prev= on these lines", printed.getvalue())


if __name__ == "__main__":
    unittest.main()
