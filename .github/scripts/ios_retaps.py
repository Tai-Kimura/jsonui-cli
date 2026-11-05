#!/usr/bin/env python3
"""The iOS conformance's named retaps: write a run's, judge them against the run before.

Ticket 2026-10-24-ios-conformance-tap-not-delivered-recurred (the requester's choice B, 2.3.23): a fixture whose
assertion failed after a tap and passed on a second tap is a pass that names itself (SwiftJsonUI ConformanceUITests,
results[].retap, RESULTS_SCHEMA.md) — the first touch was not delivered. A retry that names itself is not a fix; the
gate holds it to three rules:

  - more than MAX_PER_RUN retaps in one run: red;
  - the same fixture retapped on this run and on the one before it: red;
  - a second tap that did not make it pass either: the fixture's own error, red in the gate already (0 error).

The probes hold to the same rules, on the same count. A probe that retaps says so in the run's xcodebuild.log
(SwiftJsonUI ProbeRetap: `PROBE_RETAP <probe> <what>: ...`; the older `GATE_PROBE retap <id>:` and `CANTAP_PROBE retap
<id>:`). A touch that did not land is one thing whoever noticed it, so a fixture's retap and a probe's add up to the one
MAX_PER_RUN, over both faces (iOS dynamic and codegen). The past runs behind that (ticket above, 2026-11-05): never more
than one lost touch in a run, so a second cap of its own would only have let four through. "Twice in a row" is per
fixture, and per probe whatever its row: the rows of one probe are one test's touches.

  scan <xcodebuild.log> <probe_retaps.json> --attempt N
      A shard's lines, written beside its results. It records how many test cases the log held: a log that cannot be
      read is not a run without retaps.

  write <ios.results.json> <retaps.json> --run-id N --attempt N --sha SHA [--face FACE --shard-dirs DIR ...]
      Prints every retap (fixture, tap, when, screenshot; probe, what) and writes {"run_id", "run_attempt", "head_sha",
      "face", "retaps": [{"id", "tap", "at", "screenshot"}], "probe_retaps": [{"probe", "what", "kind", "attempt"}],
      "probe_cases", "unread"} — the merge job uploads it as <face>-retaps-a<attempt> (90 days).

  judge <retaps.json> ... --repo OWNER/NAME --run-id N --attempt N --workflow FILE
      Takes every record of this run: for each face it reads the latest attempt's. Reads the run before (the same run's
      attempt before that record's; for a first attempt, the last run of the workflow that started before this one and
      left that face's record) through the GitHub API (gh, GH_TOKEN), and exits 1 on a rule broken. A record it cannot
      read (expired, a run without iOS, the API failing) is said as unknown, and that run's "twice in a row" is not
      counted: unknown is neither green nor red. A shard's log that was not read is red: it would read as no retaps.
      A record's attempt can be older than the run's: re-running failed jobs does not re-run a merge that passed. A row
      a re-run merge carried over from a shard it did not re-run is the same touch, not a second one.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Callable

MAX_PER_RUN = 2
ARTIFACT = "{face}-retaps-a{attempt}"
FACES = ("ios", "ios-codegen")
LOOK_BACK = 30   # runs of the workflow read when looking for the one before
SCAN_FILE = "probe_retaps.json"
NAMED_AT_MOST = 30   # names in an ::error line or the summary; every one is printed in the step's log

# What a probe prints (SwiftJsonUI ConformanceHost/UITests/ProbeRetap.swift, InteractionGateProbeUITests.tapControl,
# and CanTapGateProbeUITests before ProbeRetap). "retap": touched once more. "refused": a lost touch this test had no
# retap left for. "nothing": the second touch of a retap already counted showed nothing either, said and not counted.
_PROBE_LINE = re.compile(r"^PROBE_RETAP (\S+) (.+?): (no effect.*|the second touch.*)$")
_OLD_LINE = re.compile(r"^(GATE_PROBE|CANTAP_PROBE) retap (\S+): (.*)$")
_OLD_NAMES = {"GATE_PROBE": "InteractionGate", "CANTAP_PROBE": "CanTapGate"}
_TEST_CASE = re.compile(r"^Test Case '-\[\S+\.\w+ \w+\]' started")
_PROBE_RAN = re.compile(r"^Test Case '-\[\S+\.\w+ProbeUITests \w+\]' (?:passed|failed)")   # a skipped one did not run
COUNTED = ("retap", "refused")


def retaps_of(results: dict) -> list[dict]:
    """The retaps in one ios.results.json, in its order."""
    out = []
    for row in results.get("results", []):
        retap = row.get("retap") if isinstance(row, dict) else None
        if isinstance(retap, dict):
            out.append({"id": row.get("id"), "tap": retap.get("tap"), "at": retap.get("at"),
                        "screenshot": retap.get("screenshot"), "reason": retap.get("reason")})
    return out


def write(results_path: Path, out_path: Path, run_id: str, attempt: str, sha: str, face: str = "ios",
          shard_dirs: list[Path] | None = None) -> int:
    results = json.loads(results_path.read_text())
    retaps = retaps_of(results)
    for r in retaps:
        at = f"{r['at']:.3f}" if isinstance(r.get("at"), (int, float)) else r.get("at")
        print(f"RETAP {r['id']}: tap({r['tap']}) at +{at}s — {r['reason']}; screenshot {r['screenshot']}")
    print(f"[retaps] {len(retaps)} fixture(s) passed on a second tap in this run")
    rows, probes, unread = read_scans(shard_dirs or [])
    for row in rows:
        print(f"PROBE_RETAP {face} {row['probe']} {row['what']}: {row['said']}")
    for line in unread:
        print(f"[retaps] not read — {line}")
    print(f"[retaps] {sum(r['kind'] in COUNTED for r in rows)} probe touch(es) not delivered in {probes} probe test case(s)")
    out_path.write_text(json.dumps({"run_id": str(run_id), "run_attempt": str(attempt), "head_sha": sha, "face": face,
                                    "retaps": retaps, "probe_retaps": rows, "probe_cases": probes, "unread": unread},
                                   indent=1) + "\n")
    return 0


def probe_rows(log: str) -> tuple[list[dict], int, int]:
    """The retap lines of one xcodebuild.log, the test cases it started, and how many probe tests ran."""
    rows, cases, probes = [], 0, 0
    for line in log.splitlines():
        if _TEST_CASE.match(line):
            cases += 1
            continue
        if _PROBE_RAN.match(line):
            probes += 1
            continue
        if "PROBE_RETAP " not in line and " retap " not in line:
            continue
        new, old = _PROBE_LINE.match(line), _OLD_LINE.match(line)
        if new:
            said = new.group(3)
            kind = "nothing" if said.startswith("the second touch") else "refused" if "not tapped again" in said else "retap"
            rows.append({"probe": new.group(1), "what": new.group(2), "kind": kind, "said": said})
        elif old:
            rows.append({"probe": _OLD_NAMES[old.group(1)], "what": old.group(2), "kind": "retap", "said": old.group(3)})
        elif "PROBE_RETAP " in line:   # a wording this does not know is still a retap: counted and named, never dropped
            rows.append({"probe": "unparsed", "what": line.strip()[:200], "kind": "retap", "said": line.strip()[:200]})
    return rows, cases, probes


def scan(log_path: Path, out_path: Path, attempt: str) -> int:
    try:
        rows, cases, probes = probe_rows(log_path.read_text(errors="replace"))
    except OSError as exc:
        print(f"[retaps] {log_path} could not be read ({exc})")
        rows, cases, probes = [], 0, 0
    for row in rows:
        row["attempt"] = str(attempt)
        print(f"PROBE_RETAP {row['probe']} {row['what']}: {row['said']}")
    print(f"[retaps] {len(rows)} probe retap line(s) in {cases} test case(s), {probes} probe test(s) ran")
    out_path.write_text(json.dumps({"attempt": str(attempt), "test_cases": cases, "probe_cases": probes, "rows": rows}, indent=1) + "\n")
    return 0


def read_scans(shard_dirs: list[Path]) -> tuple[list[dict], int, list[str]]:
    """Every shard's rows, the probe test cases they ran, and the shards whose log was not read."""
    rows, probes, unread = [], 0, []
    for shard in shard_dirs:
        try:
            scanned = json.loads((shard / SCAN_FILE).read_text())
        except (OSError, ValueError) as exc:
            unread.append(f"{shard.name}: no record of its log ({exc})")
            continue
        if not scanned.get("test_cases"):
            unread.append(f"{shard.name}: its log held no test case")
            continue
        probes += scanned.get("probe_cases", 0)
        rows.extend(scanned.get("rows", []))
    return rows, probes, unread


Api = Callable[[str], dict]
Download = Callable[[int], bytes]


def _gh_api(path: str) -> dict:
    return json.loads(subprocess.run(["gh", "api", path], check=True, capture_output=True, text=True).stdout)


def _gh_download(artifact_id: int, repo: str) -> bytes:
    return subprocess.run(["gh", "api", f"repos/{repo}/actions/artifacts/{artifact_id}/zip"],
                          check=True, capture_output=True).stdout


def _read_record(api: Api, download: Download, repo: str, run_id: str, attempt: int | None,
                 face: str = "ios") -> tuple[dict | None, str]:
    """A face's retaps record of a run (of `attempt`, or its latest), or None and why not."""
    try:
        listing = api(f"repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100")
    except Exception as exc:   # the API failing is said, never a pass
        return None, f"run {run_id}: the artifacts could not be listed ({exc})"
    records = [a for a in listing.get("artifacts", []) if str(a.get("name", "")).startswith(f"{face}-retaps-a")]
    if attempt is not None:
        records = [a for a in records if a["name"] == ARTIFACT.format(face=face, attempt=attempt)]
    if not records:
        which = f"attempt {attempt}" if attempt is not None else "any attempt"
        return None, f"run {run_id}: no {face}-retaps record for {which} (a run without iOS, or before this record)"
    best = max(records, key=lambda a: int(a["name"].rsplit("a", 1)[-1]))
    if best.get("expired"):
        return None, f"run {run_id}: its {best['name']} has expired"
    try:
        with zipfile.ZipFile(io.BytesIO(download(best["id"]))) as z:
            return json.loads(z.read(z.namelist()[0])), f"run {run_id} {best['name']}"
    except Exception as exc:
        return None, f"run {run_id}: {best['name']} could not be read ({exc})"


def previous(api: Api, download: Download, repo: str, run_id: str, attempt: int, workflow: str,
             face: str = "ios") -> tuple[dict | None, str]:
    """A face's record of the run before: this run's attempt before, else the last earlier run that left one."""
    if attempt > 1:
        return _read_record(api, download, repo, run_id, attempt - 1, face)
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
        record, said = _read_record(api, download, repo, str(run["id"]), None, face)
        if record is not None:
            return record, said
        why.append(said)
        if "expired" in said:   # older ones are older still
            break
    return None, f"no earlier run left a {face}-retaps record: " + ("; ".join(why[:3]) or f"none of the last {LOOK_BACK}")


def _named(names: list[str]) -> str:
    more = len(names) - NAMED_AT_MOST
    return ", ".join(names[:NAMED_AT_MOST]) + (f" and {more} more (all in this step's log)" if more > 0 else "")


def _probe_name(row: dict) -> str:
    return f"{row['probe']} {row['what']}"


def judge(current: dict, before: dict | None, before_said: str) -> list[str]:
    """The broken rules, each a sentence naming its fixtures and runs (empty: none broken)."""
    bad = []
    here = current.get("retaps", [])
    probes = [r for r in current.get("probe_retaps", []) if r.get("kind") in COUNTED]
    run = f"run {current.get('run_id')} attempt {current.get('run_attempt')}"
    total = len(here) + len(probes)
    if total > MAX_PER_RUN:
        counted = [r["id"] for r in here] + [_probe_name(r) for r in probes]
        bad.append(f"{total} retaps in {run} (more than {MAX_PER_RUN}): " + _named(counted))
    for line in current.get("unread", []):
        bad.append(f"{run}: a shard's probe retaps could not be counted — {line}")
    if before is not None:
        same_run = str(before.get("run_id")) == str(current.get("run_id"))
        then = {r["id"]: r for r in before.get("retaps", [])}
        for r in here:
            carried = same_run and r["id"] in then and then[r["id"]].get("at") == r.get("at")
            if r["id"] in then and not carried:
                bad.append(f"{r['id']} retapped twice in a row: {run} (screenshot {r['screenshot']}) and {before_said} "
                           f"(screenshot {then[r['id']].get('screenshot')})")
        rows_then = [r for r in before.get("probe_retaps", []) if r.get("kind") in COUNTED]
        for probe in sorted({r["probe"] for r in probes}):
            mine = [r for r in probes if r["probe"] == probe]
            theirs = [r for r in rows_then if r["probe"] == probe]
            if same_run:   # a row of a shard that was not re-run is the same touch
                seen = {(r.get("what"), r.get("attempt")) for r in theirs}
                mine = [r for r in mine if (r.get("what"), r.get("attempt")) not in seen]
            if mine and theirs:
                bad.append(f"probe {probe} retapped twice in a row: {run} ({_named([r['what'] for r in mine])}) and "
                           f"{before_said} ({_named([r['what'] for r in theirs])})")
    return bad


def latest_per_face(records: list[dict]) -> dict[str, dict]:
    """Each face's record of the latest attempt that left one."""
    latest: dict[str, dict] = {}
    for record in records:
        face = record.get("face", "ios")
        if face not in latest or int(record.get("run_attempt", 0)) > int(latest[face].get("run_attempt", 0)):
            latest[face] = record
    return latest


def together(faces: dict[str, dict], run_id: str, attempt: int) -> dict:
    """The faces' records as the one count the rules hold them to."""
    return {"run_id": str(run_id), "run_attempt": str(attempt),
            "retaps": [r for record in faces.values() for r in record.get("retaps", [])],
            "probe_retaps": [r for record in faces.values() for r in record.get("probe_retaps", [])],
            "probe_cases": sum(record.get("probe_cases", 0) for record in faces.values()),
            "unread": [line for record in faces.values() for line in record.get("unread", [])]}


def summary(current: dict, faces: dict[str, dict], bad: list[str]) -> str:
    fixtures = [f"fixture {r['id']}" for r in current["retaps"]]
    probes = [f"probe {_probe_name(r)}" for r in current["probe_retaps"] if r.get("kind") in COUNTED]
    per_face = ", ".join(f"{face} {len(record.get('retaps', [])) + sum(r.get('kind') in COUNTED for r in record.get('probe_retaps', []))}"
                         for face, record in sorted(faces.items()))
    ran = (f"{current['probe_cases']} probe test case(s) ran" if current["probe_cases"]
           else "no probe ran: the probes' count says nothing on this run")
    lines = ["### iOS retaps (touches not delivered)", "",
             f"**{len(fixtures) + len(probes)}** in this run, at most {MAX_PER_RUN}: "
             f"{len(fixtures)} fixture(s), {len(probes)} probe touch(es). By face: {per_face}. {ran}.", ""]
    lines += [f"- {name}" for name in (fixtures + probes)[:NAMED_AT_MOST]]
    if len(fixtures) + len(probes) > NAMED_AT_MOST:
        lines.append(f"- and {len(fixtures) + len(probes) - NAMED_AT_MOST} more, all in the step's log")
    lines += [f"- 🔴 {line}" for line in bad]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None, api: Api | None = None, download: Download | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write")
    w.add_argument("results", type=Path)
    w.add_argument("out", type=Path)
    w.add_argument("--run-id", required=True)
    w.add_argument("--attempt", required=True)
    w.add_argument("--sha", default="")
    w.add_argument("--face", default="ios")
    w.add_argument("--shard-dirs", nargs="*", type=Path, default=[])
    c = sub.add_parser("scan")
    c.add_argument("log", type=Path)
    c.add_argument("out", type=Path)
    c.add_argument("--attempt", required=True)
    j = sub.add_parser("judge")
    j.add_argument("retaps", type=Path, nargs="+")
    j.add_argument("--repo", required=True)
    j.add_argument("--run-id", required=True)
    j.add_argument("--attempt", required=True, type=int)
    j.add_argument("--workflow", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "scan":
        return scan(a.log, a.out, a.attempt)
    if a.cmd == "write":
        return write(a.results, a.out, a.run_id, a.attempt, a.sha, a.face, a.shard_dirs)
    records = []
    for path in a.retaps:
        try:
            records.append(json.loads(path.read_text()))
        except (OSError, ValueError) as exc:
            print(f"::error::the retaps record {path} could not be read ({exc})")
            return 1
    faces = latest_per_face(records)
    for face in FACES:
        if face not in faces:
            print(f"[retaps] {face}: no record in this run — its face is not judged, and this count leaves it out")
    current = together(faces, a.run_id, a.attempt)
    get, fetch = api or _gh_api, download or (lambda i: _gh_download(i, a.repo))
    bad, befores = [], []
    for face, record in sorted(faces.items()):
        before, said = previous(get, fetch, a.repo, a.run_id, int(record.get("run_attempt", a.attempt)), a.workflow, face)
        if before is None:
            print(f"[retaps] the run before, {face}: unknown — {said}; 'twice in a row' is not counted on this run")
        else:
            print(f"[retaps] the run before, {face}: {said}, {len(before.get('retaps', []))} retap(s), "
                  f"{sum(r.get('kind') in COUNTED for r in before.get('probe_retaps', []))} probe touch(es)")
        befores.append((before, said))
    print(f"[retaps] this run: {len(current['retaps'])} retap(s), "
          f"{sum(r.get('kind') in COUNTED for r in current['probe_retaps'])} probe touch(es), "
          f"{current['probe_cases']} probe test case(s)")
    for row in current["probe_retaps"]:
        print(f"PROBE_RETAP {_probe_name(row)}: {row.get('said', row.get('kind'))}")
    rules = judge(current, None, "")   # the count is over the faces; the run before is read per face, below
    bad.extend(rules)
    for before, said in befores:
        if before is not None:
            bad.extend(line for line in judge(current, before, said) if line not in rules)
    bad = list(dict.fromkeys(bad))
    for line in bad:
        print(f"::error::{line}")
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as out:
            out.write(summary(current, faces, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
