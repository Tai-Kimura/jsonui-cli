"""A picture whose element moved down must not pass the visual gate as unchanged.

THE DEFECT THIS EXISTS FOR (ticket conformance-moved-dhash-misses-a-small-pale-box-moving)

Every bit of the dhash-64 compares a pixel with its RIGHT neighbour, so an
element that moves inside its own column changes few bits. Measured on CI
renders 2026-10-06 (run 37189084185 against run 37368630695, the gate's own
hash and crop): `common_alignTopOfView__static` on iOS moved its 50 pt
#DDDDDD target 132 pt down — 26400 px changed — at distance 6 against a
threshold of 8, while `common_alignLeftOfView__static`, the same box moved
sideways, measured 29. Every picture with >= 10k px changed that the gate
called unchanged (web 1, ios 2, android 1) was a vertical move.

The same hash of the TRANSPOSED picture (`vdhash_file`, committed as
`vhashes`) compares each pixel with the one below it: 27 on that move, 16 on
the sideways one. A picture is moved when either distance is over the
threshold.

THE ARMS: a vertical move must be caught by the vertical hash AND passed by
the horizontal one (asserted together — caught alone would not say which hash
did it); a sideways move is the control, caught by the horizontal hash first;
an unchanged picture is caught by neither; and a baseline baked before
`vhashes` reports the move as UNCOVERED, never as unmoved, and the gate says
how many.

⚠️ The specimens are drawn here (no PNG is committed); their distances are
asserted before anything is judged, so a specimen that drifts off the
discriminating position fails by name instead of passing vacuously.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jui_cli.conformance import baseline
from jui_cli.conformance.baseline import (
    DEFAULT_THRESHOLD,
    compare_platform,
    dhash_file,
    hamming,
    update_baseline,
    vdhash_file,
)
from jui_cli.conformance.gate import judge
from jui_cli.conformance.report import ReportSummary

try:
    from PIL import Image

    HAVE_PILLOW = True
except ImportError:  # pragma: no cover
    HAVE_PILLOW = False

#: The shape of the measured case: a phone-sized page, a 50 px pale box.
PAGE = (402, 874)
BOX = 50
PALE = (0xDD, 0xDD, 0xDD)


def _scene(path: Path, x: int, y: int) -> None:
    img = Image.new("RGB", PAGE, (255, 255, 255))
    img.paste(PALE, (x, y, x + BOX, y + BOX))
    img.save(path)


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed (jui-tools[conformance])")
class AMoveInsideAColumnIsCaughtTests(unittest.TestCase):
    NAME = "common_alignTopOfView__static.png"

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.conf = self.tmp / "conformance"
        self.art = self.conf / "artifacts" / "web"
        self.art.mkdir(parents=True)
        (self.conf / "baselines" / "local").mkdir(parents=True)
        _scene(self.art / self.NAME, 0, 0)
        # The baseline render, kept to measure the specimens against.
        self.before = self.tmp / "before.png"
        _scene(self.before, 0, 0)
        update_baseline(self.conf, "web", artifacts_dir=self.art, env="local")
        self.path = self.conf / "baselines" / "local" / "web.hashes.json"

    def _compare(self):
        return compare_platform(self.conf, "web", [self.NAME], artifacts_dir=self.art, env="local")

    def _distances(self) -> tuple[int, int]:
        now = self.art / self.NAME
        return (
            hamming(dhash_file(self.before), dhash_file(now)),
            hamming(vdhash_file(self.before), vdhash_file(now)),
        )

    def test_the_bake_records_a_vertical_hash_for_every_entry_it_hashed(self) -> None:
        baked = json.loads(self.path.read_text())
        self.assertEqual(sorted(baked["vhashes"]), sorted(baked["hashes"]))
        self.assertEqual(len(baked["vhashes"][self.NAME]), len(baked["hashes"][self.NAME]))

    def test_an_unchanged_picture_is_caught_by_neither_hash(self) -> None:
        """The control that makes the arms below mean something."""
        c = self._compare()
        self.assertEqual(c.regressions, [])
        self.assertEqual(c.vertical_checked, 1, "a vertical check that judged nothing passes vacuously")
        self.assertEqual(c.vertical_uncovered, [])

    def test_a_vertical_move_passes_the_horizontal_hash_and_is_caught_by_the_vertical_one(self) -> None:
        """THE TICKET. 132 down, as measured on iOS."""
        _scene(self.art / self.NAME, 0, 132)
        h, v = self._distances()
        self.assertLessEqual(h, DEFAULT_THRESHOLD, "the specimen must be one the horizontal hash passes")
        self.assertGreater(v, DEFAULT_THRESHOLD, "the specimen must be one the vertical hash sees")
        c = self._compare()
        self.assertEqual(c.regressions, [(self.NAME, v)])
        self.assertEqual(c.regression_axis, {self.NAME: "vertical"})

    def test_a_sideways_move_is_caught_by_the_horizontal_hash_first(self) -> None:
        """The control: the move the old gate already saw stays its job."""
        _scene(self.art / self.NAME, 120, 0)
        h, _ = self._distances()
        self.assertGreater(h, DEFAULT_THRESHOLD)
        c = self._compare()
        self.assertEqual(c.regressions, [(self.NAME, h)])
        self.assertEqual(c.regression_axis, {})

    def test_without_the_vertical_comparison_the_vertical_move_passes(self) -> None:
        """The mutation: take the vertical comparison away and THE TICKET's
        move is green again — so the arm above is the vertical hash's doing."""
        _scene(self.art / self.NAME, 0, 132)
        baked = json.loads(self.path.read_text())
        with mock.patch.object(baseline, "load_baseline", return_value={**baked, "vhashes": {}}):
            c = self._compare()
        self.assertEqual(c.regressions, [])
        self.assertEqual(c.vertical_uncovered, [self.NAME])

    def test_a_baseline_baked_before_vhashes_reports_the_move_as_uncovered(self) -> None:
        """Absence is not "did not move": a pre-`vhashes` baseline still
        compares on the horizontal hash and names what it could not ask."""
        baked = json.loads(self.path.read_text())
        del baked["vhashes"]
        del baked["vhashes_by_os"]
        self.path.write_text(json.dumps(baked))
        _scene(self.art / self.NAME, 0, 132)
        c = self._compare()
        self.assertEqual(c.regressions, [])
        self.assertEqual(c.vertical_checked, 0)
        self.assertEqual(c.vertical_uncovered, [self.NAME])

    def test_an_only_new_bake_does_not_attach_a_new_vertical_hash_to_an_old_entry(self) -> None:
        """ink's rule: an entry that keeps its committed horizontal hash keeps
        its committed vertical one, or none — never today's against an older
        render."""
        baked = json.loads(self.path.read_text())
        del baked["vhashes"]
        del baked["vhashes_by_os"]
        self.path.write_text(json.dumps(baked))
        _scene(self.art / self.NAME, 0, 132)
        _scene(self.art / "new.png", 0, 0)
        update_baseline(self.conf, "web", artifacts_dir=self.art, env="local", only_new=True)
        rebaked = json.loads(self.path.read_text())
        self.assertEqual(rebaked["hashes"][self.NAME], baked["hashes"][self.NAME])
        self.assertNotIn(self.NAME, rebaked["vhashes"])
        self.assertIn("new.png", rebaked["vhashes"])

    def test_a_vertical_move_is_moved_to_the_bake_as_well(self) -> None:
        """`--fail-on-moved` reads the same two hashes, so a wholesale bake
        cannot absorb a move only the vertical hash saw."""
        _scene(self.art / self.NAME, 0, 132)
        with self.assertRaises(baseline.BaselineMoved):
            update_baseline(self.conf, "web", artifacts_dir=self.art, env="local", refuse_if_moved=True)


class TheGateNamesTheUncoveredCountTests(unittest.TestCase):
    """Not gated on Pillow: the judgment is pure."""

    def test_uncovered_entries_are_a_notice_with_their_number(self) -> None:
        summary = ReportSummary(out_path=Path("REPORT.md"), platforms=["web"])
        summary.vertical_uncovered = {"web": 880}
        summary.vertical_checked = {"web": 0}
        outcome = judge(summary, ["web"], env="ci")
        lines = [n for n in outcome.notices if "vertical hash" in n]
        self.assertEqual(len(lines), 1, outcome.notices)
        self.assertIn("880 compared screenshot(s) have no committed vertical hash", lines[0])
        self.assertIn("--fail-on-moved", lines[0])

    def test_a_fully_covered_lane_says_nothing_about_it(self) -> None:
        summary = ReportSummary(out_path=Path("REPORT.md"), platforms=["web"])
        summary.vertical_uncovered = {"web": 0}
        summary.vertical_checked = {"web": 880}
        outcome = judge(summary, ["web"], env="ci")
        self.assertEqual([n for n in outcome.notices if "vertical hash" in n], [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
