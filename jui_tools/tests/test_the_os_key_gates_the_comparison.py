"""The OS in the key must PREVENT a comparison, not merely annotate one.

`test_an_os_dependent_baseline_needs_the_os_in_its_key` says the key has to
exist. This file says it has to work, and the difference is the whole point:
`rendered_by` already recorded the runtime and produced a notice AFTER a
regression was measured. A notice explains; a key stops.

🔻 THE FAILURE THIS GUARDS IS SILENCE, NOT NOISE. A key that gates too much
takes the whole corpus out of comparison and every gate goes green having
measured nothing — the shape this tree has hit repeatedly (`Executed 649
tests, with 0 failures` beside three arms that never ran; `warning lines: 0`
because compilation never started). So every arm below asserts the COMPARED
count as well as the excluded one, and the probe deliberately mixes an
OS-dependent picture with an OS-agnostic one so the two cannot move together.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(REPO / "jui_tools"))

from jui_cli.conformance.os_dependence import (  # noqa: E402
    os_dependent_screenshots_for,
    os_key_from_runner,
)

CONFORMANCE = REPO / "conformance"


class TheKeyIsDerivedFromTheRun(unittest.TestCase):
    def test_an_ios_runner_yields_its_major_version(self):
        self.assertEqual(os_key_from_runner({"version": "ios-26.2"}), "26")
        self.assertEqual(os_key_from_runner({"version": "ios-18.6"}), "18")

    def test_the_patch_level_is_not_part_of_the_key(self):
        """`#available(iOS 26.0, *)` answers the same for 26.2 and 26.3, so a
        patch bump must not split the baseline — every split costs a re-bake
        that proves nothing."""
        self.assertEqual(
            os_key_from_runner({"version": "ios-26.2"}),
            os_key_from_runner({"version": "ios-26.9"}),
        )

    def test_a_tool_version_is_not_an_os(self):
        """android reports uiautomator, web reports playwright. Reading either
        as an OS would invent a key and file pictures under it."""
        for v in ("2.3.0", "playwright 1.61.1", "1.61.1", ""):
            self.assertIsNone(os_key_from_runner({"version": v}), v)
        self.assertIsNone(os_key_from_runner(None))
        self.assertIsNone(os_key_from_runner({}))


class TheKeyGatesTheComparison(unittest.TestCase):
    """Positive and negative in one table, against the committed ci baseline."""

    @classmethod
    def setUpClass(cls):
        path = CONFORMANCE / "baselines" / "ci" / "ios.hashes.json"
        if not path.is_file():
            raise unittest.SkipTest("no ci/ios baseline in this tree")
        cls.baseline = json.loads(path.read_text(encoding="utf-8"))
        cls.os_dependent = os_dependent_screenshots_for(CONFORMANCE)

    def test_the_probe_is_not_empty(self):
        """Positive control for every arm below."""
        self.assertTrue(self.os_dependent, "no OS-dependent screenshots — arms measure nothing")
        self.assertTrue(self.baseline.get("hashes"), "baseline has no OS-agnostic entries")

    def test_no_os_dependent_entry_sits_in_the_agnostic_table(self):
        leaked = sorted(self.os_dependent & set(self.baseline.get("hashes", {})))
        self.assertEqual(leaked, [], f"filed without an OS: {leaked}")

    def test_they_are_filed_under_some_os_instead_of_dropped(self):
        """The other way to satisfy the arm above is to bake them nowhere,
        which removes them from visual coverage silently. That is worse."""
        filed = set()
        for bucket in (self.baseline.get("hashes_by_os") or {}).values():
            filed |= set(bucket)
        missing = sorted(self.os_dependent - filed)
        self.assertEqual(missing, [], f"OS-dependent and baked nowhere: {missing}")

    def test_the_agnostic_corpus_is_still_the_bulk_of_the_baseline(self):
        """A key that gates too much is the silent failure. If the split ever
        moves the corpus wholesale, this says so instead of the gate going
        quiet."""
        agnostic = len(self.baseline.get("hashes", {}))
        keyed = sum(len(b) for b in (self.baseline.get("hashes_by_os") or {}).values())
        self.assertGreater(agnostic, 100, "the OS-agnostic table has been emptied")
        self.assertLess(
            keyed, agnostic / 10,
            f"{keyed} entries are OS-keyed against {agnostic} agnostic — the split has "
            "grown past the availability-gated attributes it was built for; if that is "
            "real, the per-file key is the right structure and this design should change",
        )


if __name__ == "__main__":
    unittest.main()
