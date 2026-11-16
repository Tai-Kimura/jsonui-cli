"""A check's counts say what they count, and out of how many.

`ok=236 mismatch=0 ...` is unreadable as a gate: 236 of what, and out of what
total? A consumer lane built all three answers into a wrapper — inferring the
unit from the spelling of `target` strings, which made its gate depend on this
report's internal format — and reported that a single added `ignore_paths`
line silently took 100 operations out of the comparison while the output still
read `ok=136` and success.

The zero case is the endpoint of the same problem and reads exactly like a
clean pass: every count is zero because nothing happened. Guarded here, but
the exit code is deliberately unchanged — excluding everything is a legitimate
configuration, so this is loud, not fatal.

`declared` and `compared` are `None` when a checker does not report them,
which stays distinguishable from reporting zero: absent means "this checker
does not say", and that must not read as "it compared nothing".
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_doc_cli.check.openapi_diff import (
    DEFAULT_IGNORE_PATHS,
    DEFAULT_IGNORE_RESPONSE_CODES,
    diff_specs,
    normalize_spec,
)
from jsonui_doc_cli.check.report import (
    CheckReport,
    ResultItem,
    report_from_dict,
)

SPEC = {
    "openapi": "3.0.3",
    "paths": {
        "/api/alpha": {"get": {"responses": {"200": {"description": "ok"}}}},
        "/api/beta": {"get": {"responses": {"200": {"description": "ok"}}}},
        "/api/internal/gamma": {
            "get": {"responses": {"200": {"description": "ok"}}}},
    },
}


def coverage_of(ignore_paths):
    cov: dict = {}
    diff_specs(
        normalize_spec(SPEC, "doc"), normalize_spec(SPEC, "impl"),
        ignore_paths=list(DEFAULT_IGNORE_PATHS) + list(ignore_paths),
        ignore_codes=set(DEFAULT_IGNORE_RESPONSE_CODES),
        coverage=cov,
    )
    return cov


class CoverageIsCountedWhereTheExcludingHappens(unittest.TestCase):
    def test_nothing_excluded_compares_everything(self):
        self.assertEqual(coverage_of([]), {"compared": 3, "excluded": 0})

    def test_one_pattern_moves_operations_from_compared_to_excluded(self):
        """The reported case, in miniature: the total must not just shrink."""
        cov = coverage_of(["/api/internal/*"])
        self.assertEqual(cov, {"compared": 2, "excluded": 1})

    def test_excluding_everything_compares_nothing(self):
        self.assertEqual(coverage_of(["/api/*"]), {"compared": 0,
                                                   "excluded": 3})

    def test_the_two_always_account_for_the_declared_total(self):
        for patterns in ([], ["/api/internal/*"], ["/api/*"], ["/api/alpha"]):
            with self.subTest(patterns=patterns):
                cov = coverage_of(patterns)
                self.assertEqual(cov["compared"] + cov["excluded"], 3)

    def test_coverage_is_optional(self):
        """Callers that do not ask are unaffected — the arity did not change."""
        results, warnings = diff_specs(
            normalize_spec(SPEC, "doc"), normalize_spec(SPEC, "impl"),
            ignore_paths=list(DEFAULT_IGNORE_PATHS),
            ignore_codes=set(DEFAULT_IGNORE_RESPONSE_CODES))
        self.assertTrue(results)


def report(**kw) -> CheckReport:
    base = dict(checker="c", target_kind="api", target_name="api",
                results=[ResultItem("GET /x", "ok", "proof")])
    base.update(kw)
    return CheckReport(**base)


class SummaryNamesItsUnitAndDenominator(unittest.TestCase):
    def test_unit_and_counts_reach_the_summary(self):
        s = report(unit="operation", declared=236, compared=136,
                   excluded=100).summary
        self.assertEqual(s["unit"], "operation")
        self.assertEqual(s["declared"], 236)
        self.assertEqual(s["compared"], 136)
        self.assertEqual(s["excluded"], 100)

    def test_status_counts_are_unchanged(self):
        s = report(unit="operation", declared=1, compared=1).summary
        self.assertEqual(s["ok"], 1)
        self.assertEqual(s["mismatch"], 0)

    def test_a_checker_that_says_nothing_omits_the_keys(self):
        """Absent must not read as zero — that is the whole distinction."""
        s = report().summary
        for key in ("unit", "declared", "compared", "excluded"):
            self.assertNotIn(key, s)

    def test_excluded_zero_is_not_printed_as_noise(self):
        s = report(unit="operation", declared=5, compared=5).summary
        self.assertNotIn("excluded", s)


class ArithmeticThatDoesNotCloseIsShown(unittest.TestCase):
    def test_a_closing_sum_reports_no_remainder(self):
        r = report(unit="operation", declared=10, compared=7, excluded=3)
        self.assertEqual(r.coverage_residual, 0)
        self.assertNotIn("unaccounted", r.summary)

    def test_a_gap_is_surfaced_not_rounded_away(self):
        """A denominator nobody can reconcile is worse than none."""
        r = report(unit="operation", declared=10, compared=7, excluded=1)
        self.assertEqual(r.coverage_residual, 2)
        self.assertEqual(r.summary["unaccounted"], 2)

    def test_a_negative_gap_is_surfaced_too(self):
        r = report(unit="operation", declared=3, compared=5, excluded=0)
        self.assertEqual(r.summary["unaccounted"], -2)

    def test_no_coverage_means_no_arithmetic(self):
        self.assertEqual(report().coverage_residual, 0)


class ComparedNothingIsNotAPass(unittest.TestCase):
    def test_it_is_detected(self):
        self.assertTrue(report(declared=236, compared=0).compared_nothing)

    def test_comparing_some_is_not_it(self):
        self.assertFalse(report(declared=236, compared=1).compared_nothing)

    def test_a_project_declaring_nothing_is_not_it(self):
        """Zero of zero is vacuous, not suspicious."""
        self.assertFalse(report(declared=0, compared=0).compared_nothing)

    def test_a_checker_reporting_no_coverage_is_not_it(self):
        self.assertFalse(report().compared_nothing)


class CoverageSurvivesTheWire(unittest.TestCase):
    def test_round_trip_preserves_coverage_and_inputs(self):
        original = report(unit="operation", declared=9, compared=8, excluded=1,
                          inputs={"impl_openapi_sha256": "sha256:abc"})
        restored = report_from_dict(json.loads(json.dumps(original.to_dict())))
        self.assertEqual(restored.unit, "operation")
        self.assertEqual(restored.declared, 9)
        self.assertEqual(restored.compared, 8)
        self.assertEqual(restored.excluded, 1)
        self.assertEqual(restored.inputs["impl_openapi_sha256"], "sha256:abc")

    def test_a_plugin_report_without_coverage_reads_back_as_absent(self):
        """Not zero. A plugin that does not count has not counted nothing."""
        restored = report_from_dict(json.loads(json.dumps(report().to_dict())))
        self.assertIsNone(restored.declared)
        self.assertIsNone(restored.compared)
        self.assertEqual(restored.excluded, 0)

    def test_inputs_are_omitted_when_empty(self):
        self.assertNotIn("inputs", report().to_dict())


class ProvenanceIsMetadataOnly(unittest.TestCase):
    """`inputs` names the sides; it must not become a staleness signal."""

    def test_is_stale_ignores_inputs(self):
        from jsonui_doc_cli.check.report import is_stale

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            r = report(inputs={"impl_openapi_sha256": "sha256:whatever",
                               "doc_source_rev": "0" * 40})
            # No input_hashes at all: staleness has nothing to check, and the
            # provenance block must not invent an answer.
            self.assertFalse(is_stale(r, root))


if __name__ == "__main__":
    unittest.main()
