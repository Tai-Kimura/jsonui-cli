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

#: Skip reasons this repository accepts, as substrings of the skip message.
#: DECLARED, not inferred — the same shape the conformance ledgers use, and for
#: the same reason: "no skips at all" is a property that happens to hold on a
#: developer machine and has never held in CI, so asserting it made the arm fail
#: on its first real run against 71 skips that are entirely by design. Allowing
#: *any* skip would empty the gate instead; allowing *named* reasons keeps a new
#: one — an arm quietly dropping out — a failure.
#:
#: Measured 2026-09-15 on ci run 34932870285: 71 skipped, every one of them
#: Pillow-dependent, because the python-suite job installs `pip install -e .`
#: without the `[conformance]` extra on purpose (the image-hashing tests are
#: covered by the conformance lanes that actually render).
#: ⚠️ THESE TWO ARE NOT THE SAME KIND OF REASON, and they are kept apart on
#: purpose. Lumping them would hide that the second one names an arm CI can
#: never run, which is a different fact from an optional dependency.
ALLOWED_SKIP_REASONS: tuple[str, ...] = (
    # A DELIBERATE OMISSION. The python-suite job installs `pip install -e .`
    # without the `[conformance]` extra, so the image-hashing tests skip. They
    # are covered where they mean something — the conformance lanes that
    # actually render. Measured on ci run 34932870285: 70 of these.
    # ⚠️ AND IT NO LONGER FIRES IN CI, WHICH IS THE POINT. Until 1.8.87 the
    # python-suite job installed the bare package and 86 arms skipped here —
    # including both files covering the gates 1.8.85 shipped, which had
    # therefore never executed in CI. ci.yml now installs `[conformance]`.
    #
    # The reason stays DECLARED because developer machines and other lanes can
    # legitimately lack Pillow, and a declaration that is removed the moment it
    # stops firing cannot tell "fixed" from "regressed". What stops it becoming
    # a licence is elsewhere: run-suites.sh asserts that ci.yml still installs
    # the extra, so dropping it fails the release rather than re-earning this
    # allowance. 🔻 A DECLARED SKIP IS STILL A SKIP — the per-reason count is
    # printed every run so the number is looked at, not just classified.
    "Pillow not installed",
    # AN ARM THAT CANNOT RUN HERE AT ALL. The audited canonical set it
    # cross-checks against lives under `docs/`, which is gitignored, so it is
    # absent from every checkout CI makes — this is not a dependency anyone
    # can install. It is a BONUS cross-check by its own docstring, and the
    # safety properties it would confirm are pinned by a sibling that DOES run
    # in CI: verified 2026-09-15 by hiding `docs/` and re-running the class —
    # `test_the_committed_ledgers_derive_a_safe_exclusion` passed, only the
    # cross-check skipped. Allowing it is therefore not a hole; the hole would
    # be allowing it without having checked that sibling.
    "no committed conformance dir",
    # A THIRD KIND AGAIN, AND IT IS THE CHECKOUT ITSELF. The arm that runs
    # `what_moved.py` over the last released range needs a release tag, and
    # `actions/checkout@v4` here is depth-1 with no tags — not a dependency
    # anyone can install, and not something a sparse pattern can widen.
    # Fetching tags into every python-suite run was considered and not taken:
    # the note on this job already weighs ~11.5 MB of history against 41 KB of
    # sources for the cross-repo arms, and this would spend it for a check the
    # release itself must pass anyway.
    #
    # ⚠️ ALLOWING IT IS ONLY HONEST BECAUSE THE PROPERTY IS CHECKED ELSEWHERE,
    # and that was made true in the same commit rather than assumed:
    # `dev-guide/release/run-suites.sh` now runs `what_moved.py` over
    # <last tag>..HEAD as its own leg and fails the release when a path has no
    # named surface. A release cannot be announced from a tree whose suites
    # did not run, so the gate sits in front of every announcement.
    "no release tags in this checkout",
)


def unexpected_skips(suite: ET.Element) -> tuple[list[tuple[str, str]], dict[str, int]]:
    """Return (skips whose reason is not declared, a census by declared reason).

    Read from the report's own ``<skipped message=...>`` rather than from a
    ``-rs`` summary, so the classification comes from the same artifact as the
    counts and cannot disagree with them.
    """
    unexpected: list[tuple[str, str]] = []
    census: dict[str, int] = {reason: 0 for reason in ALLOWED_SKIP_REASONS}
    for case in suite.iter("testcase"):
        for skipped in case.iter("skipped"):
            message = (skipped.get("message") or "") + " " + (skipped.text or "")
            for reason in ALLOWED_SKIP_REASONS:
                if reason in message:
                    census[reason] += 1
                    break
            else:
                name = f"{case.get('classname','')}::{case.get('name','')}"
                unexpected.append((name, message.strip()[:120]))
    return unexpected, census


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
    unexpected, skip_census = unexpected_skips(suite)
    for reason, count in sorted(skip_census.items()):
        print(f"[collection] declared skip reason {reason!r}: {count}")
    if unexpected:
        print(
            f"::error::{len(unexpected)} test(s) skipped for a reason this repository "
            "has not declared. A skip is not a pass — add the reason to "
            "ALLOWED_SKIP_REASONS with a note on why it is legitimate, or give the "
            "job what it needs:"
        )
        for name, message in unexpected[:20]:
            print(f"::error::  {name} — {message}")
        failed = True
    # Conservation: every skip is either declared or reported. A classifier that
    # silently matched nothing would otherwise pass by finding no unexpected ones.
    classified = sum(skip_census.values()) + len(unexpected)
    if classified != skipped:
        print(
            f"::error::skip classification does not add up: {classified} classified "
            f"vs {skipped} reported by the run — the reader is broken, not the suite"
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
