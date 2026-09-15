"""A host declared to report the web load-marker census must still implement it.

THE GAP THIS CLOSES

``gate.EXPECTED_WEB_MARKER_HOSTS`` makes a missing census a failure rather than
a silence, which is what separates "the census regressed to zero" from "no host
has adopted it yet". But it judges a RUN: the violation only appears after the
conformance suite finishes, and the iOS leg alone takes about 45 minutes. The
divergence it catches — the census code reverted or renamed out of the host —
is visible by reading the source in milliseconds.

So this arm reads the declared hosts' sources directly and fails at push time,
before the 45 minutes are spent. The two are not redundant: this one proves the
code is PRESENT, the gate proves it RAN and counted. Source can be present and
still not execute (the env flag never arriving is exactly that shape, and it is
what the census exists to detect).

WHY THE MAPPING LIVES HERE AND IS ITSELF ASSERTED

Adding a platform to the declaration without teaching this arm where its host
lives would give the new platform the gate's 45-minute check and none of this
one's, silently. So every declared host must have an entry in ``HOSTS`` below,
and that is the first thing asserted.

CROSS-REPO ARMS LEAVE CI FOR THREE INDEPENDENT REASONS

The job does not check the sibling out, the env var is spelled differently, or
the sparse pattern stops short of the file — and none of the three looks like a
failure. So all three are refusals HERE:

* named sibling, file absent — FAILS. That is the sparse shape, and a skip
  would turn "CI does not fetch this file" into a green suite.
* no sibling found at all, under ``CI`` — FAILS, naming the env var it looked
  for. This is the quiet one: rename or misspell the variable and the lookup
  falls back to a path the runner's layout does not have, so the gate vanishes
  while the file stays.
* no sibling found at all, locally — SKIPS and prints what was not compared.
  A developer without the checkout gets the honest answer.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from jui_cli.conformance.gate import EXPECTED_WEB_MARKER_HOSTS

REPO_ROOT = Path(__file__).resolve().parents[2]

#: declared platform -> (env var naming the sibling, default sibling dir name,
#: path to the host source within it, substrings that must appear in it)
HOSTS: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "ios": (
        "JSONUI_SWIFTJSONUI_PATH",
        "SwiftJsonUI",
        "ConformanceHost/UITests/ConformanceUITests.swift",
        (
            # the flag the host sets on the app under test — without it the
            # library builds no marker and every capture skips the wait
            'launchEnvironment["JSONUI_CONFORMANCE_WEB_MARKERS"] = "1"',
            # the element the wait keys on
            '"sjui_web_pending"',
            '"sjui_web_loaded"',
            # the census the gate reads, and its denominator
            "webMarkerCensus",
            # the declared fact the detector keys on — NOT a transient marker,
            # which is what the first version counted and cried wolf over
            "current.host == \"Web\"",
            "webFixturesReachedCapture",
            # the one bucket whose non-zero means the mechanism is gone
            "markerAbsent",
            # the census has to reach the results file, not just exist
            "webMarkers:",
        ),
    ),
}


def _sibling(env_var: str, name: str) -> tuple[Path | None, bool]:
    """Return (path, was_named_explicitly)."""
    override = os.environ.get(env_var)
    if override:
        return Path(override), True
    candidate = REPO_ROOT.parent / name
    return (candidate if candidate.exists() else None), False


class TheMappingItselfHasToBeAbleToFailTests(unittest.TestCase):
    """A mapping entry with no patterns satisfies every assertion below it.

    ⭐ An empty scan meets the claim and proves nothing. The name-set equality
    in the next class catches "declared but nowhere to look"; it does NOT catch
    "somewhere to look, nothing to look for" — the names match, the loop runs
    zero comparisons, and the platform passes. So the patterns are counted
    here, and the scan below asserts it actually compared that many.
    """

    def test_every_mapped_host_has_patterns_to_look_for(self) -> None:
        for platform, (_, _, relative, needles) in sorted(HOSTS.items()):
            with self.subTest(platform=platform):
                self.assertGreater(
                    len(needles),
                    0,
                    f"{platform} maps to {relative} but declares no patterns — "
                    "the scan would pass without comparing anything",
                )


class EveryDeclaredHostIsCoveredHereTests(unittest.TestCase):
    def test_the_declaration_and_this_arms_mapping_name_the_same_platforms(self) -> None:
        """Adding a platform to the declaration must not silently skip this arm.

        The gate would still check it — 45 minutes later, from a run. The point
        of this file is the check that happens before that, so a declared host
        with nowhere to look is a hole, not a pass.
        """
        self.assertEqual(
            sorted(EXPECTED_WEB_MARKER_HOSTS),
            sorted(HOSTS),
            "EXPECTED_WEB_MARKER_HOSTS and this file's HOSTS mapping disagree — "
            "a declared host with no entry here gets no push-time check at all",
        )


class TheDeclaredHostsSourcesStillCarryTheCensusTests(unittest.TestCase):
    def test_each_declared_host_implements_the_census(self) -> None:
        checked = 0
        skipped: list[str] = []
        for platform in sorted(EXPECTED_WEB_MARKER_HOSTS):
            entry = HOSTS.get(platform)
            if entry is None:
                continue  # the arm above is what fails for this
            env_var, dirname, relative, needles = entry
            root, named = _sibling(env_var, dirname)
            if root is None:
                # 🔻 IN CI, "I could not find the sibling" IS THE DEFECT.
                # A cross-repo arm leaves CI three ways and only one of them
                # looks like a failure; this is the quiet one — the env var
                # renamed or misspelled falls back to a path that does not
                # exist in the runner's layout, and a skip there removes the
                # gate without removing the file. Locally, a developer with no
                # sibling checkout gets a skip, which is the honest answer.
                if os.environ.get("CI"):
                    self.fail(
                        f"{platform}: running under CI but no {dirname} checkout was "
                        f"found — ${env_var} is unset (check its spelling in the "
                        f"workflow) and {REPO_ROOT.parent / dirname} does not exist. "
                        "A skip here would silently delete this gate"
                    )
                skipped.append(f"{platform}: no {dirname} sibling and ${env_var} unset")
                continue
            source = root / relative
            if not source.exists():
                # 🔻 NAMED BUT ABSENT IS THE SPARSE-CHECKOUT SHAPE. Skipping
                # here would turn "CI does not fetch this file" into a green
                # suite, which is the failure this whole file guards against.
                self.assertTrue(
                    named,
                    f"{platform}: {dirname} exists at {root} but {relative} is missing",
                )
                self.fail(
                    f"{platform}: ${env_var} names {root} but {relative} is not there — "
                    "widen the job's sparse-checkout rather than letting this skip"
                )
            text = source.read_text(encoding="utf-8")
            # Counted in the loop body rather than derived from `needles`, so
            # the number answers "how many comparisons actually happened" and
            # not "how many were declared" — a comprehension over `needles`
            # would agree with itself no matter what the loop did.
            comparisons = 0
            missing = []
            for needle in needles:
                comparisons += 1
                if needle not in text:
                    missing.append(needle)
            with self.subTest(platform=platform, source=relative):
                self.assertEqual(
                    comparisons,
                    len(needles),
                    f"{platform}: performed {comparisons} comparisons for "
                    f"{len(needles)} declared patterns — the scan exited early",
                )
                self.assertGreater(
                    comparisons, 0, f"{platform}: nothing was compared"
                )
                self.assertEqual(
                    missing,
                    [],
                    f"{platform} is declared in EXPECTED_WEB_MARKER_HOSTS but its host "
                    f"({relative}) no longer contains {missing!r}. Either restore the "
                    "census or drop the platform from the declaration — leaving both "
                    "as they are means the gate fails 45 minutes into every run",
                )
            checked += 1

        # A cross-repo arm that reports agreement between one list and nothing
        # is worse than no arm, so say out loud what was and was not compared.
        if checked == 0:
            self.skipTest(
                "no declared host's source was available — not compared: "
                + "; ".join(skipped)
            )
        elif skipped:
            print(f"[web-marker source arm] checked {checked}, not compared: {skipped}")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
