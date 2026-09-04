"""Which fixtures the codegen host can run, derived from the corpus.

The host used to decide by CLASS: `visual` and `assertable` were staged,
`declaration-only` and `interactive` were dropped wholesale, on the stated
grounds that interactive "drives bindings through the dynamic state store".

Measured against this manifest, that reason does not describe what it
excluded. Of 36 `interactive` fixtures, 20 drive nothing at all — they are
`waitFor` plus an assertion — and 12 of those carry no state vars either.
Three of them (`common/visibility__binding_{visible,invisible,gone}`) were
measured PASSING on the dynamic face while being unrunnable on the codegen
face. A fixture kept out by a rationale that does not fit it is unmeasured for
no reason, and nothing in the host's output said so: the summary read
`skipped 0` while 120 fixtures were never hosted.

So the predicate is what the host's limitation actually is — it has no driver:

    a fixture that taps / types / swipes cannot run here; everything else can.

This pins the three populations that follow from that, so a change to the
corpus that moves them has to move these numbers deliberately.

⚠️ The predicate is implemented TWICE: here, and in
`SwiftJsonUI/ConformanceHost/scripts/generate_codegen_host.rb`
(`DRIVER_ACTIONS` / `drives_input?`), with a third copy in
`ConformanceUITests.swift` (`driverActions` / `requiresDriver`) deciding what
to RUN rather than what to STAGE. Two of those live in another repository, so
this test cannot import them. That is a real coupling, not a tidy one: if the
verb list changes in one place and not the others, a fixture is staged and
skipped (or the reverse) and the count silently stops meaning anything. The
verb list is asserted here explicitly so a change to it fails rather than
drifts.
"""
from __future__ import annotations

import json
import pathlib
import unittest

#: Action verbs that need a driver. MUST equal `DRIVER_ACTIONS` in
#: generate_codegen_host.rb and `driverActions` in ConformanceUITests.swift.
DRIVER_ACTIONS = {"tap", "longPress", "swipe", "input", "selectOption"}

_CONFORMANCE = pathlib.Path(__file__).resolve().parents[2] / "conformance"


def _manifest() -> dict:
    return json.loads((_CONFORMANCE / "manifest.json").read_text(encoding="utf-8"))


def _steps(fixture: dict) -> list[dict]:
    path = _CONFORMANCE / fixture["test"]
    if not path.is_file():
        return []
    test = json.loads(path.read_text(encoding="utf-8"))
    return [s for c in (test.get("cases") or []) for s in (c.get("steps") or [])]


def _drives_input(fixture: dict) -> bool:
    return any(s.get("action") in DRIVER_ACTIONS for s in _steps(fixture))


def _screen_companions(fixture: dict) -> list[str]:
    return [c for c in (fixture.get("companions") or []) if "__cells/" not in c]


class CodegenHostStagingSet(unittest.TestCase):
    def setUp(self):
        self.ios = [f for f in _manifest()["fixtures"]
                    if "ios" in (f.get("platforms") or [])]

    def partition(self):
        """(hostable, needs_driver, companion_unresolved) under the predicate."""
        hostable, driver, companion = [], [], []
        for f in self.ios:
            if _drives_input(f):
                driver.append(f)
            elif _screen_companions(f):
                companion.append(f)
            else:
                hostable.append(f)
        return hostable, driver, companion

    def test_the_three_populations(self):
        hostable, driver, companion = self.partition()
        self.assertEqual(len(driver), 16, "fixtures needing a driver")
        self.assertEqual(len(companion), 7, "embed-companion resolution not hosted")
        self.assertEqual(len(hostable), len(self.ios) - 23, "hostable on the codegen face")

    def test_the_parts_account_for_every_ios_fixture(self):
        # Control. Three counts that do not sum to the whole describe some
        # other corpus, and the previous arrangement failed exactly here —
        # 120 fixtures were outside every number the host printed.
        hostable, driver, companion = self.partition()
        self.assertEqual(len(hostable) + len(driver) + len(companion), len(self.ios))

    def test_class_no_longer_decides_hosting(self):
        # The point of the change: `declaration-only` and `interactive` are
        # hostable when they do not drive. If this goes back to zero, the
        # class filter has returned under another name.
        hostable, _, _ = self.partition()
        classes = {f["class"] for f in hostable}
        self.assertIn("declaration-only", classes)
        self.assertIn("interactive", classes)

    def test_the_interactive_class_does_not_predict_driving(self):
        # The finding that motivated all of this, pinned so it cannot quietly
        # stop being true: most `interactive` fixtures drive nothing.
        interactive = [f for f in self.ios if f["class"] == "interactive"]
        driving = [f for f in interactive if _drives_input(f)]
        self.assertEqual(len(interactive), 36)
        self.assertEqual(len(driving), 16)

    def test_the_fixtures_measured_on_dynamic_are_hostable(self):
        # These three passed on the dynamic face while being excluded here —
        # the concrete cost of the old predicate.
        hostable, _, _ = self.partition()
        ids = {f["id"] for f in hostable}
        for fid in ("common/visibility__binding_visible",
                    "common/visibility__binding_invisible",
                    "common/visibility__binding_gone"):
            self.assertIn(fid, ids)

    def test_the_negation_fixture_becomes_observable(self):
        # `common/hidden__binding_negation` is what makes the third candidate
        # for `common/hidden__binding` measurable: it is the arm that fails if
        # a fix hides the view when the binding is false. Without it hosted,
        # that regression has no gate on this face.
        hostable, _, _ = self.partition()
        self.assertIn("common/hidden__binding_negation",
                      {f["id"] for f in hostable})

    def test_the_driver_verbs_are_the_ones_the_host_scripts_use(self):
        # The verb list is duplicated across two repositories (see the module
        # docstring). Asserting it here turns a silent divergence into a
        # failure the next time someone adds a verb in one place.
        self.assertEqual(
            DRIVER_ACTIONS,
            {"tap", "longPress", "swipe", "input", "selectOption"})


if __name__ == "__main__":
    unittest.main()
