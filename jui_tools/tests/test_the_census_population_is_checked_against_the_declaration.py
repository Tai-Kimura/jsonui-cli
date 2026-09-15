"""The web-load census cannot check its own population, so the manifest does.

THE HOLE THIS CLOSES

Both conformance hosts derive `webFixturesRunnable` from the set the run
decided to execute — iOS from the `runnable` array it just built, android from
`classifySkip(fixture, filter)`. So the census's own invariant,
`Runnable == ReachedCapture`, compares two points INSIDE the run. It catches a
fixture that started and never reached the capture point. It is blind to one
that never entered `runnable` at all, because `runnable` shrinks with it and
the identity keeps holding.

Measured 2026-09-15 on a deliberately filtered android run: runnable 1,
reachedCapture 1, four buckets summing to 1, markerAbsent 0 — every in-run
check green while HALF the declared population was absent. The conservation law
is doing exactly its job; its job does not include this.

The declaration is the only number outside the run, so that is what the
population is compared against.

⚠️ AND A FILTERED RUN BREAKS IT LEGITIMATELY. Saying nothing there would mean
the check disappears whenever someone passes a filter — so a run that RECORDS
its filter is exempted out loud, and a run that records none is judged, with
the message saying which of the two it was.
"""
from __future__ import annotations

import unittest

from jui_cli.conformance.gate import _web_marker_population_problems
from jui_cli.conformance.report import ReportSummary


def _summary(declared: int, runnable: int, run_filter=None, platform="ios"):
    s = ReportSummary(out_path=None)
    s.declared_web_fixtures[platform] = declared
    s.web_markers[platform] = {
        "webFixturesRunnable": runnable,
        "webFixturesReachedCapture": runnable,
        "alreadySettled": runnable,
        "waitedThenSettled": 0,
        "timedOut": 0,
        "markerAbsent": 0,
    }
    s.run_filters[platform] = run_filter
    return s


class TheDeclarationIsWhatCatchesAMissingFixtureTests(unittest.TestCase):
    def test_a_population_matching_the_declaration_is_silent(self) -> None:
        problems, notices = _web_marker_population_problems(_summary(2, 2), ["ios"])
        self.assertEqual((problems, notices), ([], []))

    def test_a_fixture_that_left_the_population_is_a_problem(self) -> None:
        """THE HOLE. Every in-run number here is self-consistent — runnable 1,
        reached 1, buckets sum to 1, markerAbsent 0 — and half the declared
        population is gone."""
        problems, notices = _web_marker_population_problems(_summary(2, 1), ["ios"])
        self.assertEqual(notices, [])
        self.assertEqual(len(problems), 1)
        self.assertIn("declares 2", problems[0])
        self.assertIn("counted 1", problems[0])
        self.assertIn("records NO filter", problems[0])
        self.assertIn("does not say so", problems[0],
                      "a host that records no filter cannot be said to have run unfiltered")

    def test_a_recorded_filter_exempts_it_out_loud(self) -> None:
        """Not silence: a filtered run says why the numbers differ, so the
        check cannot be made to disappear by passing a filter."""
        problems, notices = _web_marker_population_problems(
            _summary(2, 1, run_filter="Web"), ["ios"]
        )
        self.assertEqual(problems, [])
        self.assertEqual(len(notices), 1)
        self.assertIn("NOT APPLICABLE", notices[0])
        self.assertIn("'Web'", notices[0])

    def test_a_filter_of_all_is_not_an_exemption_and_says_so_differently(self) -> None:
        """`all` is what an unfiltered run records; treating it as a filter
        would exempt every normal run. And it licenses a STRONGER sentence than
        a run that records nothing: with `all` the narrowing is ruled out."""
        problems, _ = _web_marker_population_problems(
            _summary(2, 1, run_filter="all"), ["ios"]
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("narrowed nothing", problems[0])
        self.assertNotIn("does not say so", problems[0])

    def test_an_undeclared_host_is_not_judged(self) -> None:
        """Only hosts the gate DECLARES should emit a census are held to it —
        the same population `EXPECTED_WEB_MARKER_HOSTS` governs elsewhere.

        ⚠️ The specimen is `web`, not `android`. android was the undeclared
        example until it adopted the census on 2026-09-16; leaving it here
        would have turned this arm into its own opposite — a declared host
        whose population disagrees, asserted to produce no problem.
        """
        problems, notices = _web_marker_population_problems(
            _summary(2, 1, platform="web"), ["web"]
        )
        self.assertEqual((problems, notices), ([], []))

    def test_a_missing_census_is_left_to_the_other_checks(self) -> None:
        """Absence of `webMarkers` is already a failure elsewhere; reporting it
        twice would count one defect in two places."""
        s = ReportSummary(out_path=None)
        s.declared_web_fixtures["ios"] = 2
        problems, notices = _web_marker_population_problems(s, ["ios"])
        self.assertEqual((problems, notices), ([], []))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
