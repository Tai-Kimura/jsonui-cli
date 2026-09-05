"""The exact `moved` check, and the two shapes that cannot satisfy it.

`--fail-on-moved` exists so a bake cannot absorb a picture that changed
without someone attributing the change. A fixture whose picture is not a
function of the code defeats that by construction: measured 2026-09-05 on one
host, one device, one corpus, four runs gave four different pictures for
`Indicator/color__alias_tint` (hamming 1, 0, 3, 3 against the committed
baseline) and three for the `NetworkImage` control with no `defaultImage`
(1, 0, 0, 2). A gate that fires on a correct machine every time is one the
operator learns to pass `--no-fail-on-moved` to, and then it guards nothing.

So the exact check keeps its teeth on stable fixtures and drops to the gate's
own threshold for the two declared-unstable shapes. These arms pin all three
outcomes, because "unstable fixtures are tolerated" and "unstable fixtures
are ignored" are different claims and only the third arm separates them.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jui_cli.conformance import baseline
from jui_cli.conformance.visual_stability import screenshot_name, unstable_screenshots


def _layout(nodes: list[dict]) -> dict:
    return {"type": "View", "id": "root", "child": nodes}


class UnstableSetDerivation(unittest.TestCase):
    """The set comes from what a layout declares, not from a list of names."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        (self.dir / "fixtures").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _corpus(self, entries: list[tuple[str, dict]]):
        fixtures = []
        for fid, layout in entries:
            rel = f"fixtures/{fid.replace('/', '_')}.layout.json"
            (self.dir / rel).write_text(json.dumps(layout), encoding="utf-8")
            fixtures.append({"id": fid, "layout": rel})
        (self.dir / "manifest.json").write_text(
            json.dumps({"fixtures": fixtures}), encoding="utf-8"
        )

    def test_an_indicator_anywhere_in_the_layout_marks_it_animated(self):
        self._corpus([("Indicator/color__static", _layout([{"type": "Indicator"}]))])
        found = unstable_screenshots(self.dir)
        self.assertIn("Indicator_color__static.png", found)
        self.assertIn("animated", found["Indicator_color__static.png"])

    def test_a_network_image_without_defaultimage_is_async(self):
        self._corpus([("NetworkImage/placeholder__static", _layout([{"type": "NetworkImage"}]))])
        self.assertIn(
            "NetworkImage_placeholder__static.png", unstable_screenshots(self.dir)
        )

    def test_a_network_image_WITH_defaultimage_is_stable(self):
        # The discriminator, not the component: a declared defaultImage gives
        # the view something to draw before the load lands.
        self._corpus([
            ("NetworkImage/defaultImage__static",
             _layout([{"type": "NetworkImage", "defaultImage": "placeholder"}])),
        ])
        self.assertEqual(unstable_screenshots(self.dir), {})

    def test_an_ordinary_fixture_is_stable(self):
        self._corpus([("Label/text__static", _layout([{"type": "Label", "text": "x"}]))])
        self.assertEqual(unstable_screenshots(self.dir), {})

    def test_the_control_naming_matches_the_screenshot_on_disk(self):
        # `__control/X` is written as `control_X.png`; getting this wrong
        # would silently exempt nothing at all.
        self.assertEqual(
            screenshot_name("__control/NetworkImage__no-defaultImage_url-efd3e3a7"),
            "control_NetworkImage__no-defaultImage_url-efd3e3a7.png",
        )
        self.assertEqual(
            screenshot_name("Indicator/color__alias_tint"),
            "Indicator_color__alias_tint.png",
        )


class MovedJudgment(unittest.TestCase):
    """Three arms through `update_baseline` itself.

    The first draft of these arms recomputed the rule inline — `name in
    unstable and distance < threshold` — and passed. That tests a copy of the
    decision, not the decision: deleting the feature from baseline.py would
    have left them green. They call the real entry point now, so removing the
    tolerance turns the middle arm red.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        (self.dir / "fixtures").mkdir()
        (self.dir / "artifacts" / "ios").mkdir(parents=True)
        (self.dir / "baselines" / "local").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    #: What `dhash_file` returns for every artifact in these arms. The
    #: distance is the quantity under test and it is constructed below, so
    #: the PIXELS are irrelevant — and drawing them cost the CI gate: the
    #: first version built images with Pillow, which is not installed on the
    #: python-suite runner, so these three arms raised ModuleNotFoundError
    #: and the gate they exist to be was absent exactly where it matters.
    #: Skipping without PIL would have been the same absence, quieter.
    MEASURED = "0" * (baseline.HASH_SIZE * baseline.HASH_SIZE // 4)

    def _artifact(self, name: str):
        # Only has to exist and end in .png: update_baseline globs the
        # directory, and dhash_file is patched below.
        (self.dir / "artifacts" / "ios" / name).write_bytes(b"not a real png")

    def _corpus(self, fid: str, layout: dict):
        rel = f"fixtures/{fid.replace('/', '_')}.layout.json"
        (self.dir / rel).write_text(json.dumps(layout), encoding="utf-8")
        (self.dir / "manifest.json").write_text(
            json.dumps({"fixtures": [{"id": fid, "layout": rel}]}), encoding="utf-8"
        )

    def _commit_baseline(self, name: str, digest: str):
        (self.dir / "baselines" / "local" / "ios.hashes.json").write_text(
            json.dumps({
                "platform": "ios", "environment": "local",
                "algorithm": baseline.ALGORITHM,
                "threshold": baseline.DEFAULT_THRESHOLD,
                "rendered_by": {}, "hashes": {name: digest},
            }),
            encoding="utf-8",
        )

    @staticmethod
    def _at_distance(digest: str, bits: int) -> str:
        """A hash exactly `bits` away from `digest`.

        Built directly rather than by drawing a second picture: dhash
        compares each pixel with its right neighbour, so moving one column
        of a 64x64 image flips 256 bits and every arm landed far above the
        threshold. The distance IS the quantity under test.
        """
        value = int(digest, 16) ^ ((1 << bits) - 1)
        return f"{value:0{len(digest)}x}"

    def _run(self, fid: str, layout: dict, distance: int):
        """Commit a baseline `distance` bits from what this run 'draws'."""
        name = screenshot_name(fid)
        self._corpus(fid, layout)
        self._artifact(name)
        self._commit_baseline(name, self._at_distance(self.MEASURED, distance))
        with mock.patch.object(baseline, "dhash_file", return_value=self.MEASURED):
            summary = baseline.update_baseline(self.dir, "ios", env="local")
        return name, summary

    def test_a_stable_fixture_moving_ONE_BIT_is_reported_moved(self):
        name, summary = self._run(
            "Label/text__static", _layout([{"type": "Label", "text": "x"}]), distance=1
        )
        self.assertIn(name, [n for n, _ in summary.moved])
        self.assertEqual(summary.tolerated, ())

    def test_an_unstable_fixture_under_the_threshold_is_tolerated_not_moved(self):
        name, summary = self._run(
            "Indicator/color__static", _layout([{"type": "Indicator"}]), distance=3
        )
        tolerated = {n: d for n, d, _ in summary.tolerated}
        self.assertIn(name, tolerated, f"expected tolerance; moved={summary.moved}")
        self.assertLess(tolerated[name], baseline.DEFAULT_THRESHOLD)
        self.assertNotIn(name, [n for n, _ in summary.moved])

    def test_an_unstable_fixture_at_or_above_the_threshold_still_moves(self):
        # Tolerated is not exempt. Without this arm an Indicator that really
        # broke would pass unnoticed.
        name, summary = self._run(
            "Indicator/color__static", _layout([{"type": "Indicator"}]), distance=baseline.DEFAULT_THRESHOLD
        )
        distances = {n: d for n, d in summary.moved}
        self.assertIn(name, distances, f"tolerated={summary.tolerated}")
        self.assertGreaterEqual(distances[name], baseline.DEFAULT_THRESHOLD)


if __name__ == "__main__":
    unittest.main()
