#!/usr/bin/env python3
"""Name the iOS conformance tests that failed, from the run's xcodebuild.log.

conformance-mobile's `ios` and `ios-codegen` jobs run this when their suite
step fails.

Why it exists (2026-10-03): SwiftJsonUI's run_conformance.sh prints only
`tail -40` of xcodebuild's output, and when xcodebuild fails the script exits
before it says where the full log is. Run 37112820775 (the 1.9.8 candidate)
failed with "Executed 95 tests, with 61 tests skipped and 1 failure" and the
job log did not hold the name of the test; telling a flake from a regression
took a 55-minute re-run (ticket conformance-ios-failure-name-is-not-in-the-ci-log).

    name_failed_xctests.py <xcodebuild.log> [...]

Prints, from each log given:
  - every `Test Case '-[…]' failed` line, also as a GitHub error annotation;
  - every `file:line: error:` line (an assertion's message, or a compile
    error when the run never reached the tests);
  - the `Executed N tests …` summary lines.
A failed run whose log names no failed test case says so in its own line
(a crash, a build failure, a runner that stopped before its summary).

Exit 1 when no log was given or a path is not a file (the step's shell passes
an unmatched glob through as is), so a missing log is not read as "nothing
failed". Otherwise exit 0: the suite step already failed the job.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

FAILED_CASE = re.compile(r"^Test Case '(-\[[^\]]+\])' failed")
ERROR_LINE = re.compile(r":\d+: error: ")
SUMMARY = re.compile(r"^\s*Executed \d+ tests?, ")


def read_log(text: str) -> dict:
    cases: list[str] = []
    errors: list[str] = []
    summaries: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        m = FAILED_CASE.match(line)
        if m:
            if m.group(1) not in cases:
                cases.append(m.group(1))
            continue
        if ERROR_LINE.search(line):
            errors.append(line.strip())
        elif SUMMARY.match(line):
            summaries.append(line.strip())
    return {"cases": cases, "errors": errors, "summaries": summaries}


def report(path: str, found: dict, out=sys.stdout) -> None:
    cases, errors = found["cases"], found["errors"]
    print(f"[failed tests] {path}: {len(cases)} failed test case(s), "
          f"{len(errors)} error line(s)", file=out)
    for case in cases:
        print(f"  FAILED {case}", file=out)
        print(f"::error title=iOS conformance test failed::{case}", file=out)
    for line in errors:
        print(f"  {line}", file=out)
    for line in found["summaries"]:
        print(f"  {line}", file=out)
    if not cases:
        print("  the log names no failed test case — the run stopped before "
              "its tests, or a test crashed; the lines above and the log's "
              "end are what it has", file=out)


def main(argv: list[str]) -> int:
    if not argv:
        print("error: no xcodebuild.log given", file=sys.stderr)
        return 1
    rc = 0
    for path in argv:
        p = Path(path)
        if not p.is_file():
            print(f"error: {path} is not a file — the run's xcodebuild.log "
                  "was not found, so the failing test cannot be named",
                  file=sys.stderr)
            rc = 1
            continue
        report(path, read_log(p.read_text(errors="replace")))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
