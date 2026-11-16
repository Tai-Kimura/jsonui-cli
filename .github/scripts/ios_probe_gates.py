#!/usr/bin/env python3
"""The iOS conformance host's opt-in probe switches, derived from the tests.

A probe in SwiftJsonUI's ConformanceHost/UITests skips unless an environment
variable is "1" — `ProcessInfo.processInfo.environment["X_PROBE"] == "1"`, or
the same through a local (`env["X_PROBE"] == "1"`). Until jsonui-cli 1.9.23 no
conformance-mobile input raised any of them except the two image probes', so
23 classes / 40 tests with assertions never ran in a dispatch (run
38276352120; ticket conformance-mobile-ios-probe-guards-never-run-in-dispatch).
A hand-kept list would drop the next probe the same way, so the switches are
read from the sources, as kjui_device_tests.py does for Android.

    ios_probe_gates.py gates   <UITests dir>               one switch per line
    ios_probe_gates.py exports <UITests dir>               TEST_RUNNER_<X>=1 per line
    ios_probe_gates.py check   <xctests.txt> <UITests dir>

A switch is any `["NAME"] == "1"` in a UITests source's code — comments are
removed first: a comment that shows the form ("every gate of the form
`["X"] == "1"`") raised a switch named X. `CONFORMANCE_*` names are not
switches — run_conformance.sh forwards those by its own convention — and
`!= "1"` is the opposite test, so neither is raised.

`check` is the step after a run that raised them: every XCTestCase class in a
file that reads a switch must have tests in the record, and none of them may
be `skipped`. A probe whose switch was raised and that skipped anyway is a
probe that did not run, which is the hole this closes; the record is
record_xctests.py's (`Test Case '-[Module.Class test]' verdict` per line).
Exit 1 naming each such test or class; 2 when an input is missing.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

SWITCH = re.compile(r'\[\s*"([A-Z][A-Z0-9_]*)"\s*\]\s*==\s*"1"')
TEST_CASE_CLASS = re.compile(r"\bclass\s+(\w+)\s*:\s*XCTestCase\b")
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
LINE_COMMENT = re.compile(r"//[^\n]*")
RECORD = re.compile(r"^Test Case '-\[[\w.]+?\.(\w+) (\w+)\]' (passed|failed|skipped)\b")


def code(text: str) -> str:
    """The source without its comments. A string literal holding `//` loses
    its tail too; no switch sits after one on the same line."""
    return LINE_COMMENT.sub("", BLOCK_COMMENT.sub("", text))


def scan(uitests: Path) -> dict[str, set[str]]:
    """{switch: {XCTestCase classes in the files that read it}}."""
    out: dict[str, set[str]] = defaultdict(set)
    for source in sorted(uitests.rglob("*.swift")):
        text = code(source.read_text(encoding="utf-8", errors="replace"))
        switches = {m.group(1) for m in SWITCH.finditer(text) if not m.group(1).startswith("CONFORMANCE_")}
        if not switches:
            continue
        classes = set(TEST_CASE_CLASS.findall(text))
        for switch in switches:
            out[switch] |= classes
    return dict(out)


def check(record: Path, uitests: Path) -> int:
    gated = scan(uitests)
    classes = sorted({cls for found in gated.values() for cls in found})
    verdicts: dict[str, dict[str, str]] = defaultdict(dict)
    for line in record.read_text(encoding="utf-8", errors="replace").splitlines():
        m = RECORD.match(line)
        if m:
            verdicts[m.group(1)][m.group(2)] = m.group(3)
    problems: list[str] = []
    for cls in classes:
        tests = verdicts.get(cls)
        if not tests:
            problems.append(f"{cls}: no test of this class in the record — its switch was raised and it did not run")
            continue
        skipped = sorted(t for t, v in tests.items() if v == "skipped")
        counts = {v: sum(1 for x in tests.values() if x == v) for v in ("passed", "failed", "skipped")}
        print(f"{cls}: {counts['passed']} passed, {counts['failed']} failed, {counts['skipped']} skipped")
        problems += [f"{cls}.{t}: skipped with its switch raised" for t in skipped]
    print(f"switches: {len(gated)}, classes: {len(classes)}")
    if problems:
        for p in problems:
            print(f"::error::{p}")
        return 1
    print("every gated probe ran")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[1] in ("gates", "exports"):
        uitests = Path(argv[2])
        if not uitests.is_dir():
            print(f"{uitests}: not a directory", file=sys.stderr)
            return 2
        for switch in sorted(scan(uitests)):
            print(switch if argv[1] == "gates" else f"TEST_RUNNER_{switch}=1")
        return 0
    if len(argv) == 4 and argv[1] == "check":
        record, uitests = Path(argv[2]), Path(argv[3])
        if not record.is_file() or not uitests.is_dir():
            print(f"missing input: {record if not record.is_file() else uitests}", file=sys.stderr)
            return 2
        return check(record, uitests)
    print(__doc__.split("\n\n")[2], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
