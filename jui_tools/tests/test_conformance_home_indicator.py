"""No iOS conformance screenshot shows the simulator's home indicator.

The iOS baselines hash the bottom of the picture and hold only while the
indicator is not drawn (0 of 901 in CI run 37213865798). An
XCUIApplication.snapshot() after a screenshot drew it into 110 of 178 later
pictures, and the pill alone moves a dHash by about 7 against 8 (SwiftJsonUI
ConformanceHost, iOS 26.5, 2026-10-05). These arms hold the gate's check on
the pill's own pixels.

Fixtures: the bottom 50 rows of common_background__static drawn with the pill
(the run with the snapshot) and without it (the run before), pasted at their
place in a 1206 x 2622 capture.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from jui_cli.conformance import home_indicator

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "home_indicator"


def _capture(band: str, size=home_indicator.CAPTURE_SIZE) -> Image.Image:
    canvas = Image.new("RGB", size, (255, 255, 255))
    with Image.open(FIXTURES / band) as strip:
        canvas.paste(strip.convert("RGB"), (0, size[1] - strip.size[1]))
    return canvas


class PillShareTests(unittest.TestCase):
    def setUp(self):
        self.pill = home_indicator.load_pill(home_indicator.TEMPLATE)
        self.tmp = Path(tempfile.mkdtemp())

    def _share(self, image: Image.Image) -> float | None:
        path = self.tmp / "shot.png"
        image.save(path)
        return home_indicator.pill_share(path, self.pill)

    def test_the_template_is_the_measured_pill(self):
        self.assertEqual(len(self.pill), 6452)

    def test_a_capture_with_the_pill_scores_all_of_it(self):
        # Positive control: the run whose snapshot drew the indicator.
        self.assertEqual(self._share(_capture("bottom_band_with_indicator.png")), 1.0)

    def test_a_capture_without_it_scores_nothing(self):
        self.assertEqual(self._share(_capture("bottom_band_without_indicator.png")), 0.0)

    def test_another_capture_size_is_not_judged(self):
        self.assertIsNone(self._share(_capture("bottom_band_with_indicator.png", size=(1179, 2556))))


class GateTests(unittest.TestCase):
    def _conformance_dir(self, shots: dict[str, str]) -> Path:
        root = Path(tempfile.mkdtemp())
        for rel, band in shots.items():
            path = root / "artifacts" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            _capture(band).save(path)
        return root

    def test_a_screenshot_with_the_indicator_is_a_problem_that_names_it(self):
        root = self._conformance_dir({
            "ios/common_a.png": "bottom_band_without_indicator.png",
            "ios-codegen/common_b.png": "bottom_band_with_indicator.png",
        })
        problems, notices = home_indicator.judge(root)
        self.assertEqual(len(problems), 1)
        self.assertIn("1 of 2 screenshot(s) show the home indicator", problems[0])
        self.assertIn("ios-codegen/common_b.png (100%)", problems[0])
        self.assertIn("2 screenshot(s) checked, 1 with the pill", notices[0])

    def test_screenshots_without_it_pass_and_are_counted(self):
        root = self._conformance_dir({
            "ios/common_a.png": "bottom_band_without_indicator.png",
            "ios/common_b.png": "bottom_band_without_indicator.png",
        })
        problems, notices = home_indicator.judge(root)
        self.assertEqual(problems, [])
        self.assertIn("2 screenshot(s) checked, 0 with the pill", notices[0])


class EvaluateTests(unittest.TestCase):
    """The arm is wired into `jui conformance gate`, for the iOS lane only."""

    def setUp(self):
        try:
            from .test_conformance_generator import SYNTHETIC_DEFS, _write_defs
            from .test_conformance_report import _write_results
        except ImportError:
            from test_conformance_generator import SYNTHETIC_DEFS, _write_defs
            from test_conformance_report import _write_results
        from jui_cli.conformance.fixture_generator import generate_conformance

        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.out_dir = tmp / "conformance"
        generate_conformance(_write_defs(tmp, SYNTHETIC_DEFS), self.out_dir)
        ids = [f["id"] for f in json.loads((self.out_dir / "manifest.json").read_text())["fixtures"]]
        for platform in ("ios", "web"):
            _write_results(self.out_dir, platform, {i: "pass" for i in ids})

    def tearDown(self):
        self._tmp.cleanup()

    def _shot(self, band: str):
        path = self.out_dir / "artifacts" / "ios" / "common_b.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        _capture(band).save(path)

    def _indicator_problems(self, platforms):
        from jui_cli.conformance.gate import evaluate

        outcome = evaluate(self.out_dir, platforms)
        return [p for p in outcome.problems if "home indicator" in p]

    def test_an_ios_screenshot_with_the_indicator_fails_the_gate(self):
        self._shot("bottom_band_with_indicator.png")
        problems = self._indicator_problems(["ios"])
        self.assertEqual(len(problems), 1)
        self.assertIn("ios/common_b.png (100%)", problems[0])

    def test_without_the_indicator_the_arm_adds_nothing(self):
        self._shot("bottom_band_without_indicator.png")
        self.assertEqual(self._indicator_problems(["ios"]), [])

    def test_a_gate_without_ios_does_not_look(self):
        self._shot("bottom_band_with_indicator.png")
        self.assertEqual(self._indicator_problems(["web"]), [])


if __name__ == "__main__":
    unittest.main()
