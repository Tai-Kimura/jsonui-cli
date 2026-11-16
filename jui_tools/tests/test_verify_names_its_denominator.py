"""`jui verify` says how much it verified, not just what it found.

`match=0` with `has_diffs: false` is the same output whether every screen
agreed or every screen was skipped. A downstream lane read a run that
compared NOTHING as "no differences" and only caught it by running
`jui build` separately (2026-09-03) — the same "a zero that never ran"
shape as a warning count from a compile that failed at its imports, or a
resource step that stopped before any Kotlin was analysed.

The exit code deliberately stays 0. An all-skip run is legitimate where
layouts are authored externally, and a permanently red gate is one nobody
reads — the honesty has to live somewhere a face can floor at its own
number instead. So two places carry it: a line whose shape is fixed
(`verified N of M screen(s)`) and a JSON summary for automation that never
sees the report.

Both are asserted, because either alone passes a half-done fix: the line
without the JSON leaves the machine-readable side reading exit code only,
and the JSON without the line leaves every human reader where they were.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path

from jui_cli.commands.verify_cmd import (
    _skip_counts, _summary_payload, _verified_line,
)


class VerifiedLineTests(unittest.TestCase):
    def test_an_all_skip_run_names_the_denominator(self):
        skips = _skip_counts(["a -> a.json"] * 11, [])
        line = _verified_line(0, 11, skips)
        self.assertIn("verified 0 of 11 screen(s)", line)
        self.assertIn("11 skipped", line)

    def test_the_reason_is_named_so_zero_is_readable(self):
        # A count answers "how many"; without the reason nobody can answer
        # "why is it zero", which is the question that follows.
        line = _verified_line(0, 11, _skip_counts(["a -> a.json"] * 11, []))
        self.assertIn("layout authored externally", line)

    def test_a_partial_run_shows_both_numbers(self):
        skips = _skip_counts(["a -> a.json"] * 8, [])
        line = _verified_line(3, 11, skips)
        self.assertIn("verified 3 of 11 screen(s)", line)
        self.assertIn("8 skipped", line)

    def test_a_full_run_claims_no_skips(self):
        line = _verified_line(11, 11, _skip_counts([], []))
        self.assertIn("verified 11 of 11 screen(s)", line)
        self.assertNotIn("skipped", line)

    def test_both_skip_reasons_are_counted_separately(self):
        skips = _skip_counts(["a -> a.json"] * 2, ["b", "c", "d"])
        line = _verified_line(1, 6, skips)
        self.assertIn("5 skipped", line)
        self.assertIn("2 layout authored externally", line)
        self.assertIn("3 layout not found on disk", line)

    def test_an_empty_denominator_is_not_worded_as_an_all_skip_run(self):
        # `verified 0 of 0 screen(s)` reads as "every screen was skipped"
        # when it means "there was nothing to look at". The two were
        # confused while measuring this very change — a run pointed at a
        # tree whose spec_directory was unset reported the same shape as a
        # genuine all-skip run.
        line = _verified_line(0, 0, [], spec_dir="/tmp/proj/specs")
        self.assertIn("no screens found", line)
        self.assertNotIn("verified 0 of 0", line)
        # Which tree answered is part of the answer.
        self.assertIn("/tmp/proj/specs", line)

    def test_an_all_skip_run_keeps_saying_verified(self):
        # The control for the line above: a real denominator still reports
        # in the shape a face floors on.
        line = _verified_line(0, 11, _skip_counts(["a -> a.json"] * 11, []))
        self.assertIn("verified 0 of 11 screen(s)", line)
        self.assertNotIn("no screens found", line)

    def test_the_shape_is_fixed_for_one_screen_too(self):
        # A face floors on the reported shape; pluralising would move
        # that shape out from under it.
        self.assertIn("verified 1 of 1 screen(s)", _verified_line(1, 1, []))


class JsonSummaryTests(unittest.TestCase):
    """The shape automation reads, built the way verify builds it.

    The MCP wrapper reports `has_diffs: exitCode != 0` and passes the report
    through as text, so a consumer with no report parser has only the exit
    code — which is 0 for an all-skip run by design. These counts are what
    such a consumer can floor instead.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    @staticmethod
    def _result(match=0, has_diff=False):
        """A DiffResult as far as the summary reads one."""
        return SimpleNamespace(
            match=match, missing=[], extra=[], type_mismatch=[],
            has_diff=has_diff,
        )

    def _round_trip(self, payload):
        """Through a file, because that is how a consumer receives it."""
        path = self.root / "out" / "verify.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_the_three_numbers_are_readable_for_an_all_skip_run(self):
        # Built by the shipped function, not by a copy of it here — a test
        # that rebuilds the payload asserts its own arithmetic.
        payload = _summary_payload([], _skip_counts(["a -> a.json"] * 11, []))
        loaded = self._round_trip(payload)
        self.assertEqual(0, loaded["verified"])
        self.assertEqual(11, loaded["skipped"])
        self.assertEqual(11, loaded["total"])
        self.assertEqual(
            {"layout authored externally": 11}, loaded["skippedByReason"]
        )
        # The distinction the exit code cannot carry: nothing compared is
        # not the same as nothing found.
        self.assertFalse(loaded["hasDiffs"])

    def test_a_partial_run_reports_both_sides(self):
        payload = _summary_payload(
            [self._result(match=3), self._result(match=2)],
            _skip_counts(["a -> a.json"] * 2, ["b"]),
        )
        loaded = self._round_trip(payload)
        self.assertEqual(2, loaded["verified"])
        self.assertEqual(3, loaded["skipped"])
        self.assertEqual(5, loaded["total"])
        self.assertEqual(5, loaded["match"])

    def test_verified_plus_skipped_is_the_total(self):
        payload = _summary_payload(
            [self._result(), self._result()],
            _skip_counts(["a -> a.json"] * 2, ["b"]),
        )
        self.assertEqual(
            payload["total"], payload["verified"] + payload["skipped"]
        )


if __name__ == "__main__":
    unittest.main()
