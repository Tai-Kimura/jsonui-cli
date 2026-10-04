#!/usr/bin/env python3
"""Record every iOS conformance XCTest result, passed ones included.

conformance-mobile's `ios` and `ios-codegen` jobs run this after the suite
step on EVERY run, green or red. name_failed_xctests.py (its sibling) names
the failures of a red run; this one keeps the record a green run used to
throw away.

Why it exists (2026-10-04): run_conformance.sh prints only `tail -40` of
xcodebuild, and a green run's staging (where the full log lives) was removed
with it. Run 37154953027 was green with 99 tests and 0 failures, and its logs
held 0 occurrences of the pager probe's class: whether that probe passed could
only be inferred from counts (ticket
conformance-ios-passing-tests-leave-no-per-test-record).

    record_xctests.py <xcodebuild.log> <out.txt>

- Writes every `Test Case '-[Module.Class test]' passed|failed|skipped` line
  to <out.txt>, one per test (the last verdict when a test was retried), so
  the job can upload it.
- Prints one line per test class — `Class: N passed, M failed, K skipped` —
  and a total, so a named probe's result is in the job log itself.
- Conservation: the total is compared with the run's own
  `Test Suite 'All tests'` → `Executed N tests` line. A mismatch is printed as
  a warning (the record step does not turn a run red); a log without that
  line says so.

Exit 1 when the log is missing (an unmatched glob arrives as is), so "no
record" is not read as "nothing ran". Otherwise exit 0.
"""
from __future__ import annotations

import re
import sys
from collections import OrderedDict
from pathlib import Path

CASE = re.compile(r"^Test Case '-\[(?P<module>[\w.]+?)\.(?P<cls>\w+) (?P<test>\w+)\]' "
                  r"(?P<verdict>passed|failed|skipped)\b")
ALL_TESTS = re.compile(r"^Test Suite 'All tests' (passed|failed)")
EXECUTED = re.compile(r"^\s*Executed (\d+) tests?, ")
VERDICTS = ("passed", "failed", "skipped")


def read_log(text: str) -> dict:
    cases: "OrderedDict[tuple[str, str], tuple[str, str]]" = OrderedDict()
    executed = None
    after_all = False
    for raw in text.splitlines():
        line = raw.rstrip()
        m = CASE.match(line)
        if m:
            key = (m.group("cls"), m.group("test"))
            cases.pop(key, None)  # a retried test keeps its last verdict
            cases[key] = (m.group("verdict"), line)
            continue
        if ALL_TESTS.match(line):
            after_all = True
            continue
        if after_all:
            e = EXECUTED.match(line)
            if e:
                executed = int(e.group(1))
                after_all = False
    return {"cases": cases, "executed": executed}


def summarize(found: dict, out=sys.stdout) -> None:
    per_class: "OrderedDict[str, dict[str, int]]" = OrderedDict()
    for (cls, _), (verdict, _) in found["cases"].items():
        per_class.setdefault(cls, {v: 0 for v in VERDICTS})[verdict] += 1
    total = {v: sum(c[v] for c in per_class.values()) for v in VERDICTS}
    for cls, counts in per_class.items():
        print(f"  {cls}: {counts['passed']} passed, {counts['failed']} failed, "
              f"{counts['skipped']} skipped", file=out)
    recorded = len(found["cases"])
    print(f"[xctest record] {recorded} test(s) in {len(per_class)} class(es): "
          f"{total['passed']} passed, {total['failed']} failed, {total['skipped']} skipped",
          file=out)
    executed = found["executed"]
    if executed is None:
        print("[xctest record] the log has no 'All tests' summary — the run stopped before "
              "it finished; the record holds what it reached", file=out)
    elif executed != recorded:
        print(f"::warning title=XCTest record::{recorded} test case line(s) recorded, but the run "
              f"says it executed {executed}", file=out)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: record_xctests.py <xcodebuild.log> <out.txt>", file=sys.stderr)
        return 1
    log, out_path = Path(argv[0]), Path(argv[1])
    if not log.is_file():
        print(f"error: {argv[0]} is not a file — the run's xcodebuild.log was not found, so "
              "no per-test record was kept", file=sys.stderr)
        return 1
    found = read_log(log.read_text(errors="replace"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(line + "\n" for _, line in found["cases"].values()))
    summarize(found)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
