#!/usr/bin/env python3
"""Did the arms in a pytest run EXECUTE, or were they only collected?

A JOB'S RESULT CANNOT TELL THE TWO APART. "9 passed" and "9 collected, 9
skipped" are both `success`, and a green summary prints the same word for
each — so a reader checking job by job is reading a value that two very
different runs share. That is the same shape as the defect this was written
alongside: a plausible answer returned where nothing was measured.

It matters for the arms that ask real compilers. `swiftc` and `kotlinc` are
absent on a stock ubuntu image, and a `skipif` on their presence turns the
whole face into a silent subtraction. The arms themselves refuse to skip
when `CI` is set — but that refusal only fires IF THE ARM RUNS, and a step
that never collected the file, or a job that lost its toolchain before
collection, is invisible to it.

So the discriminator goes in the OUTPUT, not in the exit status: read how
many tests ran, from the report pytest writes.

    pytest <files> --junitxml=report.xml
    dev-guide/ci/executed-or-skipped.py report.xml

Exits 0 only when at least one test executed and none was skipped. In CI a
missing toolchain is a failure, not a quiet subtraction.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <junit-xml>", file=sys.stderr)
        return 2

    try:
        root = ET.parse(argv[1]).getroot()
    except (OSError, ET.ParseError) as exc:
        print(f"{argv[1]}: cannot be read as a JUnit report — {exc}",
              file=sys.stderr)
        return 1

    # pytest writes <testsuites><testsuite .../></testsuites>; older writers
    # made <testsuite> the root. Both are read, because a report shape this
    # has not seen must not resolve to "fine".
    suite = root.find("testsuite") if root.tag == "testsuites" else root
    if suite is None or suite.tag != "testsuite":
        print(f"{argv[1]}: no <testsuite> element — pytest wrote no results",
              file=sys.stderr)
        return 1

    total = int(suite.get("tests", 0))
    skipped = int(suite.get("skipped", 0))
    executed = total - skipped
    print(f"collected={total} skipped={skipped} executed={executed}")

    if executed <= 0:
        print("NOTHING EXECUTED: every arm was skipped, or none was "
              "collected. A green job here would mean the opposite of what "
              "it says.", file=sys.stderr)
        return 1
    if skipped:
        print(f"{skipped} arm(s) skipped. In CI a missing toolchain is a "
              "failure, not a quiet subtraction.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
