#!/usr/bin/env python3
"""The iOS conformance's named retaps: write a run's, judge them against the run before.

Ticket 2026-10-24-ios-conformance-tap-not-delivered-recurred (the requester's choice B, 2.3.23): a fixture whose
assertion failed after a tap and passed on a second tap is a pass that names itself (SwiftJsonUI ConformanceUITests,
results[].retap, RESULTS_SCHEMA.md) — the first touch was not delivered. A retry that names itself is not a fix; the
gate holds it to three rules:

  - more than MAX_PER_RUN retaps in one run: red;
  - the same fixture retapped on this run and on the one before it: red;
  - a second tap that did not make it pass either: the fixture's own error, red in the gate already (0 error).

  write <ios.results.json> <retaps.json> --run-id N --attempt N --sha SHA
      Prints every retap (fixture, tap, when, screenshot) and writes {"run_id", "run_attempt", "head_sha",
      "retaps": [{"id", "tap", "at", "screenshot"}]} — ios-merge uploads it as ios-retaps-a<attempt> (90 days).

  judge <retaps.json> --repo OWNER/NAME --run-id N --attempt N --workflow FILE
      Reads the run before (the same run's attempt before this one; for a first attempt, the last run of the workflow
      that started before this one and left its ios-retaps record) through the GitHub API (gh, GH_TOKEN), and exits 1
      on a rule broken. A record it cannot read (expired, a run without iOS, the API failing) is said as unknown, and
      that run's "twice in a row" is not counted: unknown is neither green nor red.
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Callable

MAX_PER_RUN = 2
ARTIFACT = "ios-retaps-a{attempt}"
LOOK_BACK = 30   # runs of the workflow read when looking for the one before


def retaps_of(results: dict) -> list[dict]:
    """The retaps in one ios.results.json, in its order."""
    out = []
    for row in results.get("results", []):
        retap = row.get("retap") if isinstance(row, dict) else None
        if isinstance(retap, dict):
            out.append({"id": row.get("id"), "tap": retap.get("tap"), "at": retap.get("at"),
                        "screenshot": retap.get("screenshot"), "reason": retap.get("reason")})
    return out


def write(results_path: Path, out_path: Path, run_id: str, attempt: str, sha: str) -> int:
    results = json.loads(results_path.read_text())
    retaps = retaps_of(results)
    for r in retaps:
        at = f"{r['at']:.3f}" if isinstance(r.get("at"), (int, float)) else r.get("at")
        print(f"RETAP {r['id']}: tap({r['tap']}) at +{at}s — {r['reason']}; screenshot {r['screenshot']}")
    print(f"[retaps] {len(retaps)} fixture(s) passed on a second tap in this run")
    out_path.write_text(json.dumps({"run_id": str(run_id), "run_attempt": str(attempt), "head_sha": sha,
                                    "retaps": retaps}, indent=1) + "\n")
    return 0


Api = Callable[[str], dict]
Download = Callable[[int], bytes]


def _gh_api(path: str) -> dict:
    return json.loads(subprocess.run(["gh", "api", path], check=True, capture_output=True, text=True).stdout)


def _gh_download(artifact_id: int, repo: str) -> bytes:
    return subprocess.run(["gh", "api", f"repos/{repo}/actions/artifacts/{artifact_id}/zip"],
                          check=True, capture_output=True).stdout


def _read_record(api: Api, download: Download, repo: str, run_id: str, attempt: int | None) -> tuple[dict | None, str]:
    """The ios-retaps record of a run (of `attempt`, or its latest), or None and why not."""
    try:
        listing = api(f"repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100")
    except Exception as exc:   # the API failing is said, never a pass
        return None, f"run {run_id}: the artifacts could not be listed ({exc})"
    records = [a for a in listing.get("artifacts", []) if str(a.get("name", "")).startswith("ios-retaps-a")]
    if attempt is not None:
        records = [a for a in records if a["name"] == ARTIFACT.format(attempt=attempt)]
    if not records:
        which = f"attempt {attempt}" if attempt is not None else "any attempt"
        return None, f"run {run_id}: no ios-retaps record for {which} (a run without iOS, or before this record)"
    best = max(records, key=lambda a: int(a["name"].rsplit("a", 1)[-1]))
    if best.get("expired"):
        return None, f"run {run_id}: its {best['name']} has expired"
    try:
        with zipfile.ZipFile(io.BytesIO(download(best["id"]))) as z:
            return json.loads(z.read(z.namelist()[0])), f"run {run_id} {best['name']}"
    except Exception as exc:
        return None, f"run {run_id}: {best['name']} could not be read ({exc})"


def previous(api: Api, download: Download, repo: str, run_id: str, attempt: int, workflow: str) -> tuple[dict | None, str]:
    """The record of the run before: this run's attempt before, else the last earlier run that left one."""
    if attempt > 1:
        return _read_record(api, download, repo, run_id, attempt - 1)
    try:
        this = api(f"repos/{repo}/actions/runs/{run_id}")
        runs = api(f"repos/{repo}/actions/workflows/{workflow}/runs?per_page={LOOK_BACK}").get("workflow_runs", [])
    except Exception as exc:
        return None, f"the runs before {run_id} could not be listed ({exc})"
    started = this.get("run_started_at") or this.get("created_at") or ""
    why = []
    for run in sorted(runs, key=lambda r: r.get("run_started_at") or r.get("created_at") or "", reverse=True):
        if str(run.get("id")) == str(run_id) or (run.get("run_started_at") or run.get("created_at") or "") >= started:
            continue
        record, said = _read_record(api, download, repo, str(run["id"]), None)
        if record is not None:
            return record, said
        why.append(said)
        if "expired" in said:   # older ones are older still
            break
    return None, "no earlier run left an ios-retaps record: " + ("; ".join(why[:3]) or f"none of the last {LOOK_BACK}")


def judge(current: dict, before: dict | None, before_said: str) -> list[str]:
    """The broken rules, each a sentence naming its fixtures and runs (empty: none broken)."""
    bad = []
    here = current.get("retaps", [])
    run = f"run {current.get('run_id')} attempt {current.get('run_attempt')}"
    if len(here) > MAX_PER_RUN:
        bad.append(f"{len(here)} retaps in {run} (more than {MAX_PER_RUN}): " + ", ".join(r["id"] for r in here))
    if before is not None:
        then = {r["id"]: r for r in before.get("retaps", [])}
        for r in here:
            if r["id"] in then:
                bad.append(f"{r['id']} retapped twice in a row: {run} (screenshot {r['screenshot']}) and {before_said} "
                           f"(screenshot {then[r['id']].get('screenshot')})")
    return bad


def main(argv: list[str] | None = None, api: Api | None = None, download: Download | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write")
    w.add_argument("results", type=Path)
    w.add_argument("out", type=Path)
    w.add_argument("--run-id", required=True)
    w.add_argument("--attempt", required=True)
    w.add_argument("--sha", default="")
    j = sub.add_parser("judge")
    j.add_argument("retaps", type=Path)
    j.add_argument("--repo", required=True)
    j.add_argument("--run-id", required=True)
    j.add_argument("--attempt", required=True, type=int)
    j.add_argument("--workflow", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "write":
        return write(a.results, a.out, a.run_id, a.attempt, a.sha)
    current = json.loads(a.retaps.read_text())
    before, said = previous(api or _gh_api, download or (lambda i: _gh_download(i, a.repo)),
                            a.repo, a.run_id, a.attempt, a.workflow)
    if before is None:
        print(f"[retaps] the run before: unknown — {said}; 'twice in a row' is not counted on this run")
    else:
        print(f"[retaps] the run before: {said}, {len(before.get('retaps', []))} retap(s)")
    print(f"[retaps] this run: {len(current.get('retaps', []))} retap(s)")
    bad = judge(current, before, said)
    for line in bad:
        print(f"::error::{line}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
