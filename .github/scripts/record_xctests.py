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
# One line per tap, printed by SwiftJsonUI's ConformanceHost (c016de9+):
#   TAP_TIMING <fixture id> <element id> +<seconds>s <exists/hittable/frame>
TAP_TIMING = re.compile(r"^TAP_TIMING (?P<fixture>\S+) (?P<id>\S+) \+(?P<at>[0-9.]+)s"
                        r"(?: prev=\+(?P<prev>[0-9.]+)s n=(?P<n>\d+))?")
# SwiftJsonUI 8931208 added `prev=+<s>s n=<k>`: seconds since the last
# action that could change the screen (the marker for a fixture's first tap)
# and which tap of the fixture it is. A line without them is an older host's.


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
    taps = []
    for raw in text.splitlines():
        m = TAP_TIMING.match(raw.strip())
        if m:
            taps.append({
                "at": float(m.group("at")),
                "prev": float(m.group("prev")) if m.group("prev") else None,
                "n": int(m.group("n")) if m.group("n") else None,
                "fixture": m.group("fixture"),
                "id": m.group("id"),
            })
    return {"cases": cases, "executed": executed, "taps": taps}


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


def tap_timing(found: dict, out=sys.stdout) -> None:
    """How soon each tap landed — a distribution to look at, not a wait
    (ticket ios-dynamic-interactive-fixture-tap-not-delivered-intermittently).

    The distribution and the fastest / slowest five are made of each
    fixture's FIRST tap (n=1): every first tap follows the same steps
    (waitFor root -> asserts -> tap), so their times compare. A fixture's later
    taps (n>=2) follow its own earlier steps — Embed's pops come after a push,
    a navigation and a second waitFor, which made v1.9.13's and v1.9.15's
    4-7 s tails — so they are listed apart with n, prev= (seconds since the
    last screen-changing action) and the time from the marker. Lines from a
    host before prev= / n= carry only the marker time; then every tap is in
    the distribution, ordered by it, and the summary says so."""
    taps = found.get("taps", [])
    if not taps:
        print("[tap timing] no TAP_TIMING lines — a host before SwiftJsonUI c016de9, or no tap ran",
              file=out)
        return
    has_n = all(t["n"] is not None for t in taps)
    first = [t for t in taps if t["n"] == 1] if has_n else list(taps)
    later = sorted((t for t in taps if has_n and t["n"] > 1),
                   key=lambda t: (t["fixture"], t["n"]))
    first.sort(key=lambda t: (t["at"], t["fixture"], t["id"]))
    seconds = [t["at"] for t in first]

    def pct(p: float) -> float:
        return seconds[min(len(seconds) - 1, int(p * (len(seconds) - 1) + 0.5))]

    which = "first tap(s) of their fixture" if has_n else "tap(s)"
    if seconds:
        print(f"[tap timing] {len(first)} {which} after the fixture marker: min {seconds[0]:.3f}s, "
              f"p10 {pct(0.10):.3f}s, median {pct(0.50):.3f}s, p90 {pct(0.90):.3f}s, "
              f"max {seconds[-1]:.3f}s", file=out)
    print("  (most of a first tap's ~1.0 s is the driver's waitFor reaching its first check, "
          "not the tap: an element already there is still found ~1.04 s after the wait starts)",
          file=out)
    if not has_n:
        print("  (no n= / prev= on these lines — a host before SwiftJsonUI 8931208; "
              "a multi-step fixture's later taps are in this distribution and look slow)", file=out)

    def name(t: dict) -> str:
        return f"+{t['at']:.3f}s {t['fixture']} ({t['id']})"

    for t in first[:5]:
        print(f"  fastest: {name(t)}", file=out)
    for t in sorted(first[5:], key=lambda t: (t["at"], t["fixture"], t["id"]), reverse=True)[:5]:
        print(f"  slowest: {name(t)}", file=out)
    if later:
        print(f"[tap timing] {len(later)} later tap(s) of multi-step fixtures (n>=2), apart:", file=out)
        for t in later:
            print(f"  later: {t['fixture']} ({t['id']}, tap {t['n']}): prev +{t['prev']:.3f}s, "
                  f"+{t['at']:.3f}s from the marker", file=out)


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
    # The TAP_TIMING lines as printed, beside the record: a future way of
    # reading them can be re-run on this run (they lived only in
    # xcodebuild.log, which no step uploads).
    raw = [line.strip() for line in log.read_text(errors="replace").splitlines()
           if line.strip().startswith("TAP_TIMING ")]
    (out_path.parent / "tap_timing.txt").write_text("".join(line + "\n" for line in raw))
    summarize(found)
    tap_timing(found)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
