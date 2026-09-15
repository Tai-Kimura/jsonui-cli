#!/usr/bin/env python3
"""Assert that the pytest run actually reached every arm, and skipped none.

🔻 A TEST THAT NEVER RUNS CANNOT FAIL, SO A GREEN SUITE DOES NOT PROVE IT RAN.

Cross-repo and environment-dependent arms leave CI three independent ways: the
job does not check the sibling out, the env var naming it is spelled
differently, or the sparse pattern stops short of the file. Two of those can be
turned into refusals *inside* the arm — it can fail when a named checkout is
missing the file, and fail when it is running under CI and found no checkout at
all. The third cannot: an arm that is never COLLECTED raises no assertion, so
the suite is green and nothing says a gate disappeared.

That is measurable only from outside the arm, which is what this is. It reads
the run's own JUnit XML and asserts two things:

* **skipped == 0.** A skip is the third state between pass and fail, and the
  only signal left for the residual case where an arm's CI-detection itself
  depends on an environment variable. Silence there looks exactly like success.
* **every ``tests/test_*.py`` on disk contributed at least one testcase.** A
  file that stops being collected — renamed out of the discovery pattern, an
  import error swallowed by a conftest, a step narrowed with ``-k`` — vanishes
  from the run without vanishing from the repo. The population is DERIVED from
  the directory rather than listed here, so a new arm is covered the moment it
  is written and this file never needs editing to keep up.

Both directions of the conservation are checked, not just one: every file on
disk must contribute a testcase, AND every testcase must resolve back to a file
that exists. Without the second, a junit naming change that breaks the
derivation for SOME modules reports "N files contributed nothing" — a
catastrophic-looking finding, with no control firing, because N is neither zero
nor everything. (The all-or-nothing case was measured: reading ``file`` instead
of ``classname`` maps 0 of 114.)

⚠️ KNOWN GRANULARITY GAP, LEFT OPEN DELIBERATELY. This asserts at FILE
granularity while the thing worth protecting is the ARM: a module that still
contributes one testcase counts as present even if twenty of its arms stopped
being collected (a class renamed out of the discovery pattern, a dropped
``TestCase`` base). The cheap closure — fail when the total testcase count
falls — is not taken, because a floor pinned to today's measurement turns every
legitimate consolidation red and creates pressure to lower the floor, which is
how a ratchet stops meaning anything. Thresholds belong on a declaration, and
there is no per-arm declaration to hang this one on.

The closure, when it is worth the cost, needs no floor and no new declaration:
THE SOURCE IS THE DECLARATION. Import each ``tests/test_*.py``, enumerate the
``test_*`` methods defined on its ``TestCase`` subclasses, and require each to
appear at least once in the report (prefix match, since parametrised cases and
subTests expand the name). Nothing is pinned to a measurement, so consolidating
arms moves both sides together and stays green, while a class renamed out of
the discovery pattern or a dropped ``TestCase`` base leaves a method defined
with no testcase — which is the defect. One new third state comes with it: a
module whose import fails enumerates zero methods, so import failure has to be
a refusal in the same pass rather than an empty set.

Exit 0 when the checks hold; exit 1 with the offending names otherwise.

Usage:  python -m pytest --junitxml=pytest.xml && python tools/check_pytest_collection.py pytest.xml
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent.parent / "tests"


def mapped_and_unmapped(suite: ET.Element) -> tuple[set[str], int]:
    """Return (module paths derived from testcases, testcases that derived none).

    The second number is the other side of the conservation law. Checking only
    "did every file on disk contribute" is one direction; a junit writer whose
    naming changes for SOME modules leaves that side looking like a discovery —
    "54 files contributed nothing" — with the all-or-nothing control silent,
    because the count is neither 0 nor everything. Counting the testcases that
    fail to resolve catches partial instrument death at the same threshold as
    total death: anything above zero is the reader, not the repository.

    ⚠️ Derived from ``classname`` (``tests.test_foo.SomeTests``), NOT from the
    ``file`` attribute: pytest's JUnit writer does not populate ``file`` here.
    Measured 2026-09-15 on the same report: ``file`` resolved 0 of 114 files,
    ``classname`` resolved 114 of 114.
    """
    mapped: set[str] = set()
    unmapped = 0
    for case in suite.iter("testcase"):
        parts = (case.get("classname") or "").split(".")
        for index, part in enumerate(parts):
            if part.startswith("test_"):
                mapped.add("/".join(parts[: index + 1]) + ".py")
                break
        else:
            unmapped += 1
    return mapped, unmapped


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    report = Path(argv[1])
    if not report.is_file():
        print(f"::error::{report} does not exist — the pytest run wrote no report")
        return 1

    root = ET.parse(report).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        print(f"::error::{report} contains no <testsuite>")
        return 1

    total = int(suite.get("tests", 0))
    skipped = int(suite.get("skipped", 0))

    collected, unmapped = mapped_and_unmapped(suite)
    on_disk = {
        str(path.relative_to(TESTS_DIR.parent)) for path in TESTS_DIR.glob("test_*.py")
    }
    uncollected = sorted(on_disk - collected)
    # The report side of the conservation law: a derived module path that does
    # not exist on disk means the derivation is wrong, not that the file was
    # deleted (a deleted file contributes no testcases at all).
    phantom = sorted(name for name in collected if not (TESTS_DIR.parent / name).is_file())

    # Print the measurement whether or not it fails: a number that only appears
    # on failure cannot be watched for drift.
    print(
        f"[collection] testcases={total} skipped={skipped} "
        f"test files on disk={len(on_disk)} contributing={len(on_disk) - len(uncollected)} "
        f"testcases that resolved to no module={unmapped} "
        f"modules resolving to no file={len(phantom)}"
    )

    # A positive control in the same output: if the instrument were dead it
    # would report zero contributing files, which is indistinguishable from a
    # real catastrophe. Saying the number out loud makes that legible.
    if on_disk and not collected:
        print(
            "::error::no test file could be mapped back from the report — "
            "this is the instrument failing, not every arm disappearing"
        )
        return 1

    # Both of these are the instrument, not the repository, so they are said
    # first and in their own words — a reader who sees "N files contributed
    # nothing" underneath them would otherwise read a catastrophe.
    if unmapped or phantom:
        print(
            f"::error::the report could not be read: {unmapped} testcase(s) map to no "
            f"module and {len(phantom)} derived module(s) do not exist on disk "
            f"({phantom[:5]}). This is the DERIVATION failing, not arms disappearing — "
            "pytest's junit naming changed under it"
        )
        return 1

    failed = False
    if skipped:
        print(
            f"::error::{skipped} test(s) were SKIPPED. A skip is not a pass — "
            "run with -rs to see which, and either make the arm's precondition "
            "a refusal or give the job what it needs"
        )
        failed = True
    if uncollected:
        print(
            f"::error::{len(uncollected)} test file(s) contributed no testcase, "
            "so whatever they assert was not asserted:"
        )
        for name in uncollected:
            print(f"::error::  {name}")
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
