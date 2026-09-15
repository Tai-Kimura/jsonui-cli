"""The gate asserts, by count, that Web captures waited for the page to paint.

🔻 WHY A COUNT AND NOT A PICTURE. A web view exists the instant it is made, so
a screenshot taken mid-load is blank — and a blank fixture still DIFFERS from
its control, so ``control_diff`` calls the attribute active and a baseline
re-bake of the same race calls itself a pass. Both sides of that race sat in
committed iOS baselines under a green gate. No arm that looks at pixels can
separate "waited and painted" from "did not wait"; only the host knows, so the
host counts and the gate reads the count.

The wait's own failure wears the same face as the bug it fixes: when the load
marker is absent the capture proceeds immediately, exactly as before, and the
timeout is never reached. ``exists == false`` has four causes and only one of
them ("this fixture has no web view") is correct.

Both controls are here, and they are the two the ledger asks for:
  * positive — a census one short of its denominator FAILS
  * boundary — the same census at the denominator PASSES
so a dead predicate cannot produce an all-green table.

The second class covers the other silence: the arm going quiet because the
census DISAPPEARED. Which hosts must report is therefore declared, not
inferred from who reported this run — an inference that is silent in exactly
the failing case.
"""
from __future__ import annotations

import unittest

from jui_cli.conformance.gate import EXPECTED_WEB_MARKER_HOSTS, judge
from jui_cli.conformance.report import ReportSummary


def _summary(web_markers: dict) -> ReportSummary:
    """A summary carrying nothing but the census under test."""
    return ReportSummary(
        out_path=__import__("pathlib").Path("REPORT.md"),
        platforms=sorted(web_markers),
        web_markers=web_markers,
    )


def _census(reached: int, *, already=0, waited=0, timed_out=0, absent=0) -> dict:
    """A census whose four buckets sum to the fixtures that reached capture."""
    return {
        "webFixturesRunnable": reached,
        "webFixturesReachedCapture": reached,
        "alreadySettled": already,
        "waitedThenSettled": waited,
        "timedOut": timed_out,
        "markerAbsent": absent,
    }


class TheGateFailsWhenAWebCaptureHadNoMarkerTests(unittest.TestCase):
    """``markerAbsent`` is the one bucket that means the mechanism is gone.

    🔻 THE FIRST VERSION OF THIS CHECK CRIED WOLF ON ITS FIRST REAL RUN. It
    counted observations of the PENDING marker, and pending is transient: a
    local ``loadHTMLString`` settles before the runner's first query, so the
    tree carried only the loaded marker, the census read 0 of 2, and the
    pictures were byte-identical to the baseline. The detector is now the
    declared fact (``manifest.host == "Web"``) and each bucket's zero means
    exactly one thing.
    """

    def test_a_fixture_with_no_marker_at_all_fails(self) -> None:
        outcome = judge(
            _summary({"ios": _census(2, already=1, absent=1)}), ["ios"], visual=False
        )
        self.assertFalse(outcome.ok)
        hit = [p for p in outcome.problems if "no load marker" in p]
        self.assertEqual(len(hit), 1, outcome.problems)
        self.assertIn("1 Web fixture(s)", hit[0])

    def test_all_settled_passes(self) -> None:
        outcome = judge(_summary({"ios": _census(2, already=2)}), ["ios"], visual=False)
        self.assertTrue(outcome.ok, outcome.problems)
        self.assertEqual(outcome.notices, [])

    def test_waiting_and_then_settling_passes(self) -> None:
        """The branch that actually does the waiting is not a defect."""
        outcome = judge(
            _summary({"ios": _census(2, already=1, waited=1)}), ["ios"], visual=False
        )
        self.assertTrue(outcome.ok, outcome.problems)

    def test_a_timeout_is_a_notice_and_not_a_failure(self) -> None:
        """A slow page must not be indistinguishable from a broken marker.

        Failing here would collapse the two, and only one of them invalidates
        the capture — the timed-out one is still judged by fixture-vs-control.
        """
        outcome = judge(
            _summary({"ios": _census(2, already=1, timed_out=1)}), ["ios"], visual=False
        )
        self.assertTrue(outcome.ok, outcome.problems)
        hit = [n for n in outcome.notices if "load timeout" in n]
        self.assertEqual(len(hit), 1, outcome.notices)

    def test_buckets_that_do_not_add_up_fail(self) -> None:
        """Conservation: a future branch falling through every bucket would
        shrink the population, and a judgment with nothing left to judge passes.
        """
        census = _census(5, already=2)  # 2 bucketed, 5 reached
        outcome = judge(_summary({"ios": census}), ["ios"], visual=False)
        hit = [p for p in outcome.problems if "does not add up" in p]
        self.assertEqual(len(hit), 1, outcome.problems)
        self.assertIn("2 bucketed vs 5", hit[0])

    def test_a_missing_bucket_is_named_not_assumed_zero(self) -> None:
        """An absent count is unreadable, which is neither satisfied nor zero."""
        census = _census(2, already=2)
        del census["markerAbsent"]
        outcome = judge(_summary({"ios": census}), ["ios"], visual=False)
        hit = [p for p in outcome.problems if "missing bucket counts" in p]
        self.assertEqual(len(hit), 1, outcome.problems)
        self.assertIn("markerAbsent", hit[0])

    def test_an_unselected_platform_is_not_judged(self) -> None:
        outcome = judge(
            _summary({"ios": _census(2, absent=2), "web": _census(1, already=1)}),
            ["web"],
            visual=False,
        )
        self.assertEqual([p for p in outcome.problems if "no load marker" in p], [])


class TheExpectationIsDeclaredNotInferredTests(unittest.TestCase):
    """A regression to zero must not wear the face of pre-adoption.

    Inferring "who should report" from "who did report this run" is silent in
    exactly the failing case: the run where the census vanishes has no
    reporting hosts, which is indistinguishable from the run before anyone
    implemented it. And a census removed from the host takes the host's own
    assertion with it, so both sides fall quiet at once.
    """

    def test_a_declared_host_that_emitted_nothing_fails(self) -> None:
        outcome = judge(_summary({"ios": {}}), ["ios"], visual=False)
        self.assertFalse(outcome.ok)
        hit = [p for p in outcome.problems if "declared to report" in p]
        self.assertEqual(len(hit), 1, outcome.problems)
        self.assertIn("none at all", hit[0])

    def test_a_declared_host_that_emitted_an_unreadable_census_fails(self) -> None:
        """Unreadable is "cannot judge", not "passed" and not "not applicable"."""
        outcome = judge(
            _summary({"ios": {"pendingObserved": 4, "webFixturesReachedCapture": "4"}}),
            ["ios"],
            visual=False,
        )
        hit = [p for p in outcome.problems if "declared to report" in p]
        self.assertEqual(len(hit), 1, outcome.problems)
        self.assertIn("an unreadable one", hit[0])

    def test_an_undeclared_host_that_emits_nothing_is_silent(self) -> None:
        """A host that has not adopted the census yet is not a defect."""
        outcome = judge(
            _summary({"ios": _census(4, already=4), "web": {}, "android": {}}),
            ["ios", "web", "android"],
            visual=False,
        )
        self.assertTrue(outcome.ok, outcome.problems)
        self.assertEqual(outcome.notices, [])

    def test_an_undeclared_host_that_starts_reporting_asks_to_be_declared(self) -> None:
        """Adoption should become a visible diff, not a property of the run."""
        outcome = judge(
            _summary({"ios": _census(4, already=4), "web": _census(1, already=1)}),
            ["ios", "web"],
            visual=False,
        )
        self.assertTrue(outcome.ok, outcome.problems)
        hit = [n for n in outcome.notices if "EXPECTED_WEB_MARKER_HOSTS" in n]
        self.assertEqual(len(hit), 1, outcome.notices)
        self.assertIn("web", hit[0])

    def test_the_declaration_is_scoped_to_the_selected_platforms(self) -> None:
        """A run that does not select ios must not fail for ios's census."""
        outcome = judge(_summary({"ios": {}, "web": {}}), ["web"], visual=False)
        self.assertEqual([p for p in outcome.problems if "declared to report" in p], [])

    def test_ios_is_the_declaration_today(self) -> None:
        """Pins the declaration itself, so growing it is a deliberate edit."""
        self.assertEqual(sorted(EXPECTED_WEB_MARKER_HOSTS), ["ios"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
