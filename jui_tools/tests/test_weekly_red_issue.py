"""A red weekly conformance run opens one issue a week (.github/scripts/weekly_red_issue.py and conformance-mobile's
weekly-red job; ticket 2026-10-21-conformance-weekly-ios-interaction-gate-red). The 10-18 scheduled run sat red for
three days: GitHub mailed only whoever last edited the cron line, and nothing else said it.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "weekly_red_issue.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "conformance-mobile.yml"


def _load():
    spec = importlib.util.spec_from_file_location("weekly_red_issue", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W = _load()
URL = "https://github.com/o/r/actions/runs/39160542473"
RED = {"ios-codegen": {"result": "failure"}, "ios-codegen-merge": {"result": "failure"},
       "report": {"result": "failure"}, "web": {"result": "success"}, "android-library-tests": {"result": "skipped"}}


def test_a_green_run_does_nothing():
    assert W.plan("2026-W42", "1", URL, [], []) == {"action": "none"}
    assert W.red_jobs({"web": {"result": "success"}, "tap": {"result": "skipped"}}) == []


def test_a_red_run_opens_the_weeks_issue_with_the_run_in_its_title():
    failed = W.red_jobs(RED)
    assert failed == ["ios-codegen", "ios-codegen-merge", "report"]
    step = W.plan(W.week_of("2026-10-18T19:49:52Z"), "39160542473", URL, failed, [])
    assert step["action"] == "create" and step["label"] == W.LABEL
    assert step["title"] == "conformance weekly red: 2026-W42 (run 39160542473)"
    assert URL in step["body"] and "ios-codegen, ios-codegen-merge, report" in step["body"]


def test_a_second_red_run_that_week_comments_instead_of_opening_another():
    open_issues = [{"number": 7, "title": "conformance weekly red: 2026-W41 (run 1)"},
                   {"number": 9, "title": "conformance weekly red: 2026-W42 (run 39160542473)"}]
    step = W.plan("2026-W42", "39170000000", URL, ["web"], open_issues)
    assert step == {"action": "comment", "issue": 9, "body": step["body"]} and "39170000000" in step["body"]
    # last week's open issue is not this week's: a new one
    assert W.plan("2026-W43", "3", URL, ["web"], open_issues)["action"] == "create"


def test_a_cancelled_job_is_red_and_a_skipped_one_is_not():
    assert W.red_jobs({"a": {"result": "cancelled"}, "b": {"result": "skipped"}, "c": None}) == ["a"]


def test_the_week_is_the_runs_iso_week():
    """Sunday 18:00 UTC is the cron; Sunday is the ISO week's last day, Monday the next week's first."""
    assert W.week_of("2026-10-18T23:59:59Z") == "2026-W42"
    assert W.week_of("2026-10-19T00:00:01Z") == "2026-W43"
    assert W.week_of("2027-01-03T18:00:00+00:00") == "2026-W53"


def test_the_job_runs_on_a_schedule_only_and_waits_for_every_other_job():
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    job = wf["jobs"]["weekly-red"]
    assert "github.event_name == 'schedule'" in job["if"] and "always()" in job["if"]
    others = set(wf["jobs"]) - {"weekly-red", "tap-repro"}       # tap-repro runs only when dispatched
    assert set(job["needs"]) == others
    run = job["steps"][-1]["run"]
    # a permissions block sets every scope it does not name to none: the run's own read (gh run view) needs actions
    assert job["permissions"] == {"contents": "read", "issues": "write", "actions": "read"}
    assert "gh run view" in run
    assert "weekly_red_issue.py" in run and "createdAt" in run and job["steps"][-1]["env"]["NEEDS"] == "${{ toJSON(needs) }}"
