"""Tests for the report module (results contract: skipReason + skip accounting)."""

import pytest
import sys
from pathlib import Path

# Add package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.report import (
    generate_html,
    generate_junit,
    summarize_skips,
    validate_results_data,
)


def _result(status="passed", test_name="login", case_name="case1", **extra):
    item = {"testName": test_name, "caseName": case_name, "status": status, "durationMs": 10}
    item.update(extra)
    return item


def _run(results, platform="web"):
    return {
        "format": "jsonui-test-results",
        "version": 1,
        "platform": platform,
        "suites": [{"suiteName": "suite1", "results": results}],
    }


class TestSkipReasonValidation:
    """Tests for the optional 'skipReason' result key (results.schema.json)."""

    def test_valid_skip_reasons(self):
        for reason in ["platform", "responsive"]:
            data = _run([_result(status="skipped", skipReason=reason)])
            errors = validate_results_data(data, "test")
            assert errors == [], reason

    def test_skipped_without_reason_still_valid(self):
        # skipReason is optional; an old driver that emits bare skips stays valid
        data = _run([_result(status="skipped")])
        assert validate_results_data(data, "test") == []

    def test_invalid_skip_reason_value(self):
        data = _run([_result(status="skipped", skipReason="flaky")])
        errors = validate_results_data(data, "test")
        assert any("'skipReason' must be one of" in e for e in errors)

    def test_skip_reason_without_skipped_status(self):
        # Only meaningful when status is 'skipped' — reason on passed/failed is an error
        for status in ["passed", "failed"]:
            data = _run([_result(status=status, skipReason="responsive")])
            errors = validate_results_data(data, "test")
            assert any("only meaningful when status is 'skipped'" in e for e in errors), status

    def test_version_must_stay_1(self):
        data = _run([_result()])
        data["version"] = 2
        errors = validate_results_data(data, "test")
        assert any("'version' must be 1" in e for e in errors)


class TestSummarizeSkips:
    """Tests for skip-reason aggregation and the permanently-skipped flag."""

    def test_counts_by_reason(self):
        runs = [_run([
            _result(status="skipped", case_name="a", skipReason="platform"),
            _result(status="skipped", case_name="b", skipReason="responsive"),
            _result(status="skipped", case_name="c", skipReason="responsive"),
            _result(status="skipped", case_name="d"),
            _result(status="passed", case_name="e"),
        ])]
        summary = summarize_skips(runs)
        assert summary["reasonCounts"] == {"platform": 1, "responsive": 2, "unspecified": 1}

    def test_permanently_skipped_flagged(self):
        # 'tablet_only :: regular_case' is skipped in every run -> flagged
        runs = [
            _run([_result(status="skipped", test_name="tablet_only", case_name="regular_case",
                          skipReason="responsive")], platform="ios"),
            _run([_result(status="skipped", test_name="tablet_only", case_name="regular_case",
                          skipReason="responsive")], platform="android"),
        ]
        summary = summarize_skips(runs)
        assert summary["permanentlySkipped"] == ["tablet_only :: regular_case"]

    def test_exercised_somewhere_not_flagged(self):
        # skipped on ios but passed on web -> exercised, not permanently skipped
        runs = [
            _run([_result(status="skipped", skipReason="responsive")], platform="ios"),
            _run([_result(status="passed")], platform="web"),
        ]
        summary = summarize_skips(runs)
        assert summary["permanentlySkipped"] == []

    def test_no_skips(self):
        summary = summarize_skips([_run([_result()])])
        assert summary["reasonCounts"] == {}
        assert summary["permanentlySkipped"] == []


class TestReportOutput:
    """Tests for skipReason surfacing in JUnit / HTML output."""

    def test_junit_skipped_message_carries_reason(self):
        xml = generate_junit([_run([_result(status="skipped", skipReason="responsive")])])
        assert 'message="skipped-responsive"' in xml

    def test_junit_skipped_without_reason_has_no_message(self):
        xml = generate_junit([_run([_result(status="skipped")])])
        assert "<skipped />" in xml or "<skipped/>" in xml

    def test_junit_lists_permanently_skipped(self):
        xml = generate_junit([_run([
            _result(status="skipped", test_name="tablet_only", case_name="regular_case",
                    skipReason="responsive"),
        ])])
        assert "permanently skipped" in xml
        assert "tablet_only :: regular_case" in xml

    def test_html_summary_shows_skip_reason_breakdown(self):
        html = generate_html([_run([
            _result(status="skipped", case_name="a", skipReason="platform"),
            _result(status="skipped", case_name="b", skipReason="responsive"),
            _result(status="passed", case_name="c"),
        ])])
        assert "platform 1" in html
        assert "responsive 1" in html

    def test_html_lists_permanently_skipped(self):
        html = generate_html([_run([
            _result(status="skipped", test_name="tablet_only", case_name="regular_case",
                    skipReason="responsive"),
            _result(status="passed", test_name="login", case_name="ok"),
        ])])
        assert "Permanently skipped" in html
        assert "tablet_only :: regular_case" in html
        assert "login :: ok" not in html

    def test_html_no_permanently_skipped_section_when_all_exercised(self):
        html = generate_html([_run([_result(status="passed")])])
        assert "Permanently skipped" not in html

    def test_html_status_badge_carries_reason(self):
        html = generate_html([_run([_result(status="skipped", skipReason="responsive")])])
        assert "skipped (responsive)" in html


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
