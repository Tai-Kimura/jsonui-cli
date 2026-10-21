"""The weekly conformance run says when it is red: one issue a week (ticket
2026-10-21-conformance-weekly-ios-interaction-gate-red, the family "a weekly red nobody notices").

The scheduled run had no step that told anyone: GitHub mails a scheduled run's failure only to whoever last edited
the cron line, and no session reads that mail. The 10-18 run was red for three days before a session stumbled on it.

conformance-mobile.yml's weekly-red job runs this on a scheduled run whose jobs did not all pass (a run dispatched by
hand never opens one: whoever dispatched it is watching). A week is the ISO week of the run; a second red run in the
same week adds a comment to that week's issue instead of opening another.

    python3 .github/scripts/weekly_red_issue.py <repo> <run id> <run url> <needs JSON> <run started (ISO 8601)>

The decision (``plan``) is a pure function, tested without GitHub; ``main`` only reads the open issues and acts
through the gh CLI the runner has.
"""
from __future__ import annotations

import datetime
import json
import subprocess
import sys

LABEL = "conformance-weekly-red"
TITLE = "conformance weekly red: {week} (run {run})"


def week_of(started: str) -> str:
    """The run's ISO week, "2026-W42", from its start time ("2026-10-18T19:49:52Z")."""
    day = datetime.datetime.fromisoformat(started.replace("Z", "+00:00")).date()
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def red_jobs(needs: dict) -> list[str]:
    """The jobs that did not pass (failure or cancelled; skipped is a job this run did not ask for)."""
    return sorted(name for name, job in needs.items() if (job or {}).get("result") in ("failure", "cancelled"))


def plan(week: str, run: str, url: str, failed: list[str], open_issues: list[dict]) -> dict:
    """What to do: {"action": "none"} when every job passed; else comment on this week's open issue (its title holds
    the week) or create one. ``open_issues``: the open issues labelled LABEL, as gh lists them (number, title)."""
    if not failed:
        return {"action": "none"}
    body = (f"The scheduled conformance run {run} is red: {', '.join(failed)}.\n\n{url}\n\n"
            "Read the failed jobs' logs (`gh run view <id> --log-failed`) and the failure-log artifacts before "
            "dispatching anything: a red here is judged once, as a flake or a defect, and recorded in docs/bugs.")
    same_week = [i for i in open_issues if f"conformance weekly red: {week} " in i.get("title", "")]
    if same_week:
        return {"action": "comment", "issue": same_week[0]["number"], "body": body}
    return {"action": "create", "title": TITLE.format(week=week, run=run), "body": body, "label": LABEL}


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        print(__doc__, file=sys.stderr)
        return 2
    repo, run, url, needs_json, started = argv
    failed = red_jobs(json.loads(needs_json))
    issues = json.loads(_gh("issue", "list", "--repo", repo, "--label", LABEL, "--state", "open",
                            "--json", "number,title", "--limit", "50") or "[]") if failed else []
    step = plan(week_of(started), run, url, failed, issues)
    if step["action"] == "comment":
        _gh("issue", "comment", str(step["issue"]), "--repo", repo, "--body", step["body"])
    elif step["action"] == "create":
        subprocess.run(["gh", "label", "create", LABEL, "--repo", repo, "--color", "B60205",
                        "--description", "the weekly conformance run is red"], capture_output=True)
        _gh("issue", "create", "--repo", repo, "--title", step["title"], "--body", step["body"],
            "--label", LABEL)
    print(f"weekly red: {step['action']}" + (f" ({', '.join(failed)})" if failed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
