"""A failure diagnostic screenshot is not a fixture capture.

THE DEFECT THIS EXISTS FOR

conformance-mobile run 38958247680: the iOS Dynamic host missed a tap in the
interactive fixture common/clipToBounds__hit_overflow_true and, as designed,
kept a screenshot of the miss — `common_clipToBounds__hit_overflow_true__post_
tap_failure.png` — in artifacts/ios, beside the captures. The codegen host does
not host interactive fixtures, so parity globbed every ``*.png`` and reported
the diagnostic as "rendered by only one pipeline (codegen host did not render
it)" — a second gate error, worded as a host that skipped work, for the one
fixture whose error the gate had already printed. A bake of the same run would
have filed the diagnostic as a new baseline entry.

The producers' spellings (SwiftJsonUI ConformanceHost/UITests):
ConformanceUITests.postTapDiagnosis writes ``<fixture>__post_tap_failure``,
CellDataRefreshProbeUITests writes ``<name>__post_tap_failure_v<N>``. Both are
held below, transcribed by hand — this module cannot read the Swift.

Every arm pairs the diagnostic with a control that must still be counted: a
non-diagnostic dynamic-only picture stays ``missing``, so an exclusion that
swallowed everything would fail here rather than pass.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests._shared_core import conformance_with_shared_core

try:
    from PIL import Image, ImageDraw

    HAVE_PILLOW = True
except ImportError:  # pragma: no cover - environment dependent
    HAVE_PILLOW = False

from jui_cli.conformance import baseline, parity

FIXTURE_DIAGNOSTIC = "common_clipToBounds__hit_overflow_true__post_tap_failure.png"
PROBE_DIAGNOSTIC = "CellDataRefresh_dynamic__post_tap_failure_v1.png"


def _write_png(path: Path, box=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("L", (256, 192))
    for x in range(256):
        img.paste(x, (x, 0, x + 1, 192))
    if box:
        ImageDraw.Draw(img).rectangle(box, fill=255)
    img.save(path)


class DiagnosticPredicateTest(unittest.TestCase):
    def test_the_producers_spellings_are_diagnostics(self):
        self.assertTrue(baseline.is_diagnostic_screenshot(FIXTURE_DIAGNOSTIC))
        self.assertTrue(baseline.is_diagnostic_screenshot(PROBE_DIAGNOSTIC))

    def test_captures_are_not(self):
        # Real capture names, including ones with a double underscore and the
        # word "tap" / "failure" in them, stay captures.
        for name in ("common_clipToBounds__hit_overflow_true.png",
                     "Web_html__static.png",
                     "control_Web.png",
                     "Button_onClick__tap.png",
                     "Web_onLoadFailed__callback_fire.png"):
            self.assertFalse(baseline.is_diagnostic_screenshot(name), name)


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed (jui-tools[conformance])")
class ParityAndBakeSkipDiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conf = conformance_with_shared_core(self._tmp.name)
        self.dyn = self.conf / "artifacts" / "ios"
        self.cg = self.conf / "artifacts" / "ios-codegen"
        _write_png(self.dyn / "A.png")
        baseline.update_baseline(self.conf, "ios")
        _write_png(self.cg / "A.png")

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_dynamic_only_diagnostic_is_not_one_sided(self):
        _write_png(self.dyn / FIXTURE_DIAGNOSTIC, box=(0, 0, 120, 120))
        _write_png(self.dyn / PROBE_DIAGNOSTIC, box=(0, 0, 60, 60))
        # Control: a real dynamic-only capture is still one-sided.
        _write_png(self.dyn / "C.png", box=(10, 10, 200, 100))
        result = parity.measure(self.conf, "ios")
        self.assertIsNone(result.error)
        self.assertEqual(result.missing, ["C.png"])
        verdict = parity.check(result, {})
        self.assertEqual(verdict.one_sided, ["C.png (codegen host did not render it)"])

    def test_a_codegen_only_diagnostic_is_not_one_sided(self):
        _write_png(self.cg / FIXTURE_DIAGNOSTIC, box=(0, 0, 120, 120))
        _write_png(self.cg / "D.png", box=(10, 10, 200, 100))
        result = parity.measure(self.conf, "ios")
        self.assertEqual(result.codegen_only, ["D.png"])

    def test_a_bake_does_not_file_a_diagnostic(self):
        _write_png(self.dyn / FIXTURE_DIAGNOSTIC, box=(0, 0, 120, 120))
        _write_png(self.dyn / "C.png", box=(10, 10, 200, 100))
        baseline.update_baseline(self.conf, "ios", only_new=True)
        hashes = json.loads(
            baseline.baseline_path(self.conf, "ios").read_text(encoding="utf-8")
        )["hashes"]
        self.assertIn("C.png", hashes)
        self.assertNotIn(FIXTURE_DIAGNOSTIC, hashes)


if __name__ == "__main__":
    unittest.main()
