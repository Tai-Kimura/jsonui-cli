"""Report generation from standardized jsonui-test-results JSON.

Converts one or more results.json files (results.schema.json) into a
JUnit XML or standalone HTML report. Multiple input files (e.g. one per
platform) merge into one report; the platform becomes part of the suite name.
"""

from __future__ import annotations

import html as html_module
import json
import xml.etree.ElementTree as ET
from pathlib import Path

RESULTS_FORMAT = "jsonui-test-results"
RESULTS_VERSION = 1
VALID_RESULT_PLATFORMS = ["ios", "android", "web"]
VALID_RESULT_STATUSES = ["passed", "failed", "skipped"]
# Why a skipped result was skipped (platform gate vs responsive gate).
# Only meaningful when status == "skipped"; a reason on any other status is an error.
VALID_SKIP_REASONS = ["platform", "responsive"]
VALID_RESULTS_TOP_LEVEL_KEYS = ["format", "version", "platform", "generatedAt", "suites"]
VALID_SUITE_KEYS = ["suiteName", "totalDurationMs", "results"]
VALID_RESULT_KEYS = ["testName", "caseName", "status", "skipReason", "error", "warnings", "durationMs"]


def validate_results_data(data, source: str) -> list[str]:
    """Validate results data against results.schema.json. Returns error messages."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return [f"{source}: Results must be a JSON object"]

    if data.get("format") != RESULTS_FORMAT:
        errors.append(f"{source}: 'format' must be '{RESULTS_FORMAT}', got: {data.get('format')!r}")
    if data.get("version") != RESULTS_VERSION:
        errors.append(f"{source}: 'version' must be {RESULTS_VERSION}, got: {data.get('version')!r}")
    if data.get("platform") not in VALID_RESULT_PLATFORMS:
        errors.append(f"{source}: 'platform' must be one of {VALID_RESULT_PLATFORMS}, got: {data.get('platform')!r}")

    for key in data.keys():
        if key not in VALID_RESULTS_TOP_LEVEL_KEYS:
            errors.append(f"{source}: Unknown top-level key: {key}")

    suites = data.get("suites")
    if not isinstance(suites, list):
        errors.append(f"{source}: 'suites' must be an array")
        return errors

    for i, suite in enumerate(suites):
        suite_path = f"{source}: suites[{i}]"
        if not isinstance(suite, dict):
            errors.append(f"{suite_path} must be an object")
            continue
        for key in suite.keys():
            if key not in VALID_SUITE_KEYS:
                errors.append(f"{suite_path}: Unknown suite key: {key}")
        if not isinstance(suite.get("suiteName"), str):
            errors.append(f"{suite_path}: 'suiteName' must be a string")
        if "totalDurationMs" in suite:
            total = suite["totalDurationMs"]
            if not isinstance(total, (int, float)) or isinstance(total, bool) or total < 0:
                errors.append(f"{suite_path}: 'totalDurationMs' must be a non-negative number")

        results = suite.get("results")
        if not isinstance(results, list):
            errors.append(f"{suite_path}: 'results' must be an array")
            continue

        for j, case in enumerate(results):
            case_path = f"{suite_path}.results[{j}]"
            if not isinstance(case, dict):
                errors.append(f"{case_path} must be an object")
                continue
            for key in case.keys():
                if key not in VALID_RESULT_KEYS:
                    errors.append(f"{case_path}: Unknown result key: {key}")
            for required in ("testName", "caseName"):
                if not isinstance(case.get(required), str):
                    errors.append(f"{case_path}: '{required}' must be a string")
            if case.get("status") not in VALID_RESULT_STATUSES:
                errors.append(f"{case_path}: 'status' must be one of {VALID_RESULT_STATUSES}, got: {case.get('status')!r}")
            if "skipReason" in case:
                reason = case["skipReason"]
                if reason not in VALID_SKIP_REASONS:
                    errors.append(f"{case_path}: 'skipReason' must be one of {VALID_SKIP_REASONS}, got: {reason!r}")
                if case.get("status") != "skipped":
                    errors.append(
                        f"{case_path}: 'skipReason' is only meaningful when status is 'skipped', "
                        f"got status: {case.get('status')!r}"
                    )
            duration = case.get("durationMs")
            if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration < 0:
                errors.append(f"{case_path}: 'durationMs' must be a non-negative number")
            if "error" in case and not isinstance(case["error"], str):
                errors.append(f"{case_path}: 'error' must be a string")
            if "warnings" in case:
                warnings = case["warnings"]
                if not isinstance(warnings, list) or not all(isinstance(w, str) for w in warnings):
                    errors.append(f"{case_path}: 'warnings' must be an array of strings")

    return errors


def load_results_file(file_path: Path) -> tuple[dict | None, list[str]]:
    """Load and validate a results JSON file. Returns (data, errors)."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return None, [f"{file_path}: Invalid JSON: {e}"]
    except OSError as e:
        return None, [f"{file_path}: Cannot read file: {e}"]

    errors = validate_results_data(data, str(file_path))
    if errors:
        return None, errors
    return data, []


def _suite_display_name(platform: str, suite: dict) -> str:
    return f"[{platform}] {suite.get('suiteName', '')}"


def _suite_time_seconds(suite: dict) -> float:
    total_ms = suite.get("totalDurationMs")
    if not isinstance(total_ms, (int, float)) or isinstance(total_ms, bool):
        total_ms = sum(case.get("durationMs", 0) for case in suite.get("results", []))
    return total_ms / 1000.0


def summarize_skips(runs: list[dict]) -> dict:
    """Aggregate skip accounting across all runs (guard against write-only tests).

    Returns a dict with:
    - "reasonCounts": skip counts keyed by reason ("platform" / "responsive" /
      "unspecified" for skips without a skipReason).
    - "permanentlySkipped": sorted "testName :: caseName" entries whose every
      result across all runs is skipped (any reason). A gate no run's device
      satisfies (e.g. tablet-only responsive on phone-only CI) never exercises
      the test; surface it in the summary instead of hiding it as green.
    """
    reason_counts: dict[str, int] = {}
    statuses: dict[tuple[str, str], list[str]] = {}
    for run in runs:
        for suite in run.get("suites", []):
            for case in suite.get("results", []):
                key = (case.get("testName", ""), case.get("caseName", ""))
                status = case.get("status")
                statuses.setdefault(key, []).append(status)
                if status == "skipped":
                    reason = case.get("skipReason") or "unspecified"
                    reason_counts[reason] = reason_counts.get(reason, 0) + 1
    permanently_skipped = sorted(
        f"{test_name} :: {case_name}"
        for (test_name, case_name), case_statuses in statuses.items()
        if case_statuses and all(s == "skipped" for s in case_statuses)
    )
    return {"reasonCounts": reason_counts, "permanentlySkipped": permanently_skipped}


def generate_junit(runs: list[dict]) -> str:
    """Generate JUnit XML from validated results data (one dict per input file)."""
    root = ET.Element("testsuites")
    total_tests = 0
    total_failures = 0
    total_skipped = 0
    total_time = 0.0

    for run in runs:
        platform = run.get("platform", "")
        for suite in run.get("suites", []):
            results = suite.get("results", [])
            failures = sum(1 for c in results if c.get("status") == "failed")
            skipped = sum(1 for c in results if c.get("status") == "skipped")
            suite_time = _suite_time_seconds(suite)

            suite_el = ET.SubElement(root, "testsuite", {
                "name": _suite_display_name(platform, suite),
                "tests": str(len(results)),
                "failures": str(failures),
                "skipped": str(skipped),
                "time": f"{suite_time:.3f}",
            })

            for case in results:
                case_el = ET.SubElement(suite_el, "testcase", {
                    "name": case.get("caseName", ""),
                    "classname": case.get("testName", ""),
                    "time": f"{case.get('durationMs', 0) / 1000.0:.3f}",
                })
                status = case.get("status")
                if status == "failed":
                    failure_el = ET.SubElement(case_el, "failure", {
                        "message": case.get("error", "Test failed"),
                    })
                    failure_el.text = case.get("error", "")
                elif status == "skipped":
                    skipped_attrs = {}
                    if case.get("skipReason") in VALID_SKIP_REASONS:
                        skipped_attrs["message"] = f"skipped-{case['skipReason']}"
                    ET.SubElement(case_el, "skipped", skipped_attrs)
                warnings = case.get("warnings") or []
                if warnings:
                    system_out = ET.SubElement(case_el, "system-out")
                    system_out.text = "\n".join(f"[warning] {w}" for w in warnings)

            total_tests += len(results)
            total_failures += failures
            total_skipped += skipped
            total_time += suite_time

    root.set("tests", str(total_tests))
    root.set("failures", str(total_failures))
    root.set("skipped", str(total_skipped))
    root.set("time", f"{total_time:.3f}")

    # Surface permanently-skipped tests (skipped in every result across the
    # run) so they don't hide as green in CI.
    skip_summary = summarize_skips(runs)
    if skip_summary["permanentlySkipped"]:
        lines = "\n".join(f"  {entry}" for entry in skip_summary["permanentlySkipped"])
        root.append(ET.Comment(
            f" permanently skipped (skipped in every result across this report):\n{lines}\n"
        ))

    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


_HTML_STYLES = """
    body { font-family: -apple-system, "Segoe UI", Roboto, "Hiragino Sans", sans-serif;
           margin: 0; padding: 24px; background: #f5f6f8; color: #1f2430; }
    h1 { font-size: 22px; margin: 0 0 16px; }
    h2 { font-size: 16px; margin: 28px 0 8px; }
    .summary { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 8px; }
    .summary-card { background: #fff; border: 1px solid #e2e5ea; border-radius: 8px;
                    padding: 12px 16px; min-width: 150px; }
    .summary-card .platform { font-weight: 600; margin-bottom: 6px; }
    .summary-card .counts span { margin-right: 10px; white-space: nowrap; }
    table { border-collapse: collapse; width: 100%; background: #fff;
            border: 1px solid #e2e5ea; border-radius: 8px; overflow: hidden; }
    th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid #edeff2;
             font-size: 13px; vertical-align: top; }
    th { background: #f0f2f5; font-weight: 600; }
    tr:last-child td { border-bottom: none; }
    .status { display: inline-block; padding: 2px 10px; border-radius: 10px;
              font-size: 12px; font-weight: 600; }
    .status-passed { background: #e3f4e6; color: #1e7a34; }
    .status-failed { background: #fbe3e4; color: #b02a30; }
    .status-skipped { background: #eef0f3; color: #5b6472; }
    .count-passed { color: #1e7a34; }
    .count-failed { color: #b02a30; }
    .count-skipped { color: #5b6472; }
    .skip-reasons { color: #5b6472; font-size: 12px; }
    .perm-skipped { background: #fdf6e3; border: 1px solid #ecdfb8; border-radius: 8px;
                    padding: 12px 16px; margin: 16px 0; }
    .perm-skipped .title { font-weight: 600; color: #8a6d1a; margin-bottom: 6px; }
    .perm-skipped ul { margin: 0; padding-left: 20px; font-size: 13px; }
    details { margin: 4px 0; }
    details summary { cursor: pointer; font-size: 12px; color: #4a5261; }
    details pre { background: #f7f8fa; border: 1px solid #e2e5ea; border-radius: 6px;
                  padding: 8px; margin: 6px 0 0; font-size: 12px; white-space: pre-wrap;
                  word-break: break-word; }
    .duration { color: #5b6472; white-space: nowrap; }
"""


def generate_html(runs: list[dict]) -> str:
    """Generate a standalone single-file HTML report from validated results data."""
    esc = html_module.escape

    # Per-platform summary (skips broken down by reason — §5 coverage accounting)
    platform_stats: dict[str, dict[str, int]] = {}
    platform_skip_reasons: dict[str, dict[str, int]] = {}
    for run in runs:
        platform = run.get("platform", "")
        stats = platform_stats.setdefault(platform, {"total": 0, "passed": 0, "failed": 0, "skipped": 0})
        reasons = platform_skip_reasons.setdefault(platform, {})
        for suite in run.get("suites", []):
            for case in suite.get("results", []):
                stats["total"] += 1
                status = case.get("status", "failed")
                if status in ("passed", "failed", "skipped"):
                    stats[status] += 1
                if status == "skipped" and case.get("skipReason") in VALID_SKIP_REASONS:
                    reason = case["skipReason"]
                    reasons[reason] = reasons.get(reason, 0) + 1

    skip_summary = summarize_skips(runs)

    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append('<meta charset="utf-8">')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append("<title>JsonUI Test Report</title>")
    parts.append(f"<style>{_HTML_STYLES}</style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append("<h1>JsonUI Test Report</h1>")

    # Summary header
    parts.append('<div class="summary">')
    for platform, stats in platform_stats.items():
        reasons = platform_skip_reasons.get(platform, {})
        skip_breakdown = ", ".join(
            f"{reason} {reasons[reason]}" for reason in VALID_SKIP_REASONS if reason in reasons
        )
        skipped_label = f'skipped {stats["skipped"]}'
        if skip_breakdown:
            skipped_label += f' <span class="skip-reasons">({esc(skip_breakdown)})</span>'
        parts.append('<div class="summary-card">')
        parts.append(f'<div class="platform">{esc(platform)}</div>')
        parts.append(
            '<div class="counts">'
            f'<span>total {stats["total"]}</span>'
            f'<span class="count-passed">passed {stats["passed"]}</span>'
            f'<span class="count-failed">failed {stats["failed"]}</span>'
            f'<span class="count-skipped">{skipped_label}</span>'
            "</div>"
        )
        parts.append("</div>")
    parts.append("</div>")

    # Permanently-skipped tests: skipped in every result across this report —
    # never exercised (e.g. a responsive/platform gate no run's device satisfies).
    if skip_summary["permanentlySkipped"]:
        parts.append('<div class="perm-skipped">')
        parts.append(
            f'<div class="title">Permanently skipped '
            f'({len(skip_summary["permanentlySkipped"])}) — skipped in every result, never exercised</div>'
        )
        parts.append("<ul>")
        for entry in skip_summary["permanentlySkipped"]:
            parts.append(f"<li>{esc(entry)}</li>")
        parts.append("</ul>")
        parts.append("</div>")

    # Suite tables
    for run in runs:
        platform = run.get("platform", "")
        for suite in run.get("suites", []):
            parts.append(f"<h2>{esc(_suite_display_name(platform, suite))}</h2>")
            parts.append("<table>")
            parts.append("<tr><th>Test</th><th>Case</th><th>Status</th><th>Duration</th><th>Details</th></tr>")
            for case in suite.get("results", []):
                status = case.get("status", "failed")
                status_label = status
                if status == "skipped" and case.get("skipReason") in VALID_SKIP_REASONS:
                    status_label = f"{status} ({case['skipReason']})"
                details_parts = []
                error = case.get("error")
                if error:
                    details_parts.append(
                        f"<details><summary>Error</summary><pre>{esc(error)}</pre></details>"
                    )
                warnings = case.get("warnings") or []
                if warnings:
                    warnings_text = "\n".join(warnings)
                    details_parts.append(
                        f"<details><summary>Warnings ({len(warnings)})</summary>"
                        f"<pre>{esc(warnings_text)}</pre></details>"
                    )
                details_html = "".join(details_parts) or "&mdash;"
                parts.append(
                    "<tr>"
                    f"<td>{esc(case.get('testName', ''))}</td>"
                    f"<td>{esc(case.get('caseName', ''))}</td>"
                    f'<td><span class="status status-{esc(status)}">{esc(status_label)}</span></td>'
                    f'<td class="duration">{case.get("durationMs", 0) / 1000.0:.3f}s</td>'
                    f"<td>{details_html}</td>"
                    "</tr>"
                )
            parts.append("</table>")

    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts) + "\n"
