"""A baseline records which library drew it, and the gate can say so.

The manifest recorded how a measurement was taken — platform, env,
algorithm, threshold — and nothing about what was measured. conformance-
mobile checks SwiftJsonUI out at `master` and KotlinJsonUI at `main`, so
two bakes at the same jsonui-cli commit can hold different pictures and the
file could not say why. In one run thirteen regressions were neither
fixture nor codegen; two lanes reached "the library moved" by elimination
because nothing pointed at it.

Recorded as metadata, deliberately outside `hashes`: a library bump must
not read as "the picture changed", which is the confusion this ends.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

try:
    from PIL import Image

    HAVE_PILLOW = True
except ImportError:  # pragma: no cover - environment dependent
    HAVE_PILLOW = False

from jui_cli.conformance import baseline, gate
from jui_cli.conformance.report import ReportSummary


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed (jui-tools[conformance])")
class RenderedByTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conf = Path(self._tmp.name)
        shots = self.conf / "artifacts" / "ios"
        shots.mkdir(parents=True)
        Image.new("L", (64, 48), 120).save(shots / "A.png")

    def tearDown(self):
        self._tmp.cleanup()

    def _manifest(self) -> dict:
        return json.loads(
            (self.conf / "baselines" / "local" / "ios.hashes.json").read_text()
        )

    def test_absent_unless_given(self):
        """A local bake does not know what CI would have checked out.

        Looking it up here would write a confident wrong answer.
        """
        baseline.update_baseline(self.conf, "ios")
        self.assertEqual(self._manifest()["rendered_by"], {})

    def test_recorded_when_given(self):
        baseline.update_baseline(self.conf, "ios", rendered_by={"swiftjsonui": "abc123"})
        self.assertEqual(self._manifest()["rendered_by"], {"swiftjsonui": "abc123"})

    def test_does_not_touch_the_hashes(self):
        """The whole point: it is metadata, not part of the comparison."""
        baseline.update_baseline(self.conf, "ios", rendered_by={"swiftjsonui": "aaa"})
        first = self._manifest()
        baseline.update_baseline(self.conf, "ios", rendered_by={"swiftjsonui": "zzz"})
        second = self._manifest()
        self.assertNotEqual(first["rendered_by"], second["rendered_by"])
        self.assertEqual(first["hashes"], second["hashes"])
        self.assertEqual(first["threshold"], second["threshold"])

    def test_bake_stays_deterministic(self):
        baseline.update_baseline(self.conf, "ios", rendered_by={"b": "2", "a": "1"})
        first = (self.conf / "baselines" / "local" / "ios.hashes.json").read_bytes()
        baseline.update_baseline(self.conf, "ios", rendered_by={"a": "1", "b": "2"})
        second = (self.conf / "baselines" / "local" / "ios.hashes.json").read_bytes()
        self.assertEqual(first, second, "same inputs must give a byte-identical bake")


class LibraryDriftNoticeTest(unittest.TestCase):
    """The notice fires where it helps and stays quiet where it would not."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conf = Path(self._tmp.name)
        path = self.conf / "baselines" / "local" / "ios.hashes.json"
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps(
                {
                    "platform": "ios",
                    "environment": "local",
                    "algorithm": "dhash-64",
                    "threshold": 8,
                    "rendered_by": {"swiftjsonui": "1111111111"},
                    "hashes": {"A.png": "ff"},
                }
            )
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _notices(self, regressions: int, rendered_by: dict) -> list[str]:
        summary = ReportSummary(out_path=self.conf / "REPORT.md")
        summary.visual_regressions = {"ios": regressions}
        return gate.library_drift_notices(self.conf, ["ios"], summary, rendered_by)

    def test_silent_when_nothing_regressed(self):
        """A clean run has nothing to explain.

        Saying it every time would train people to skip the line, and then
        it is not there on the run that needed it.
        """
        self.assertEqual(self._notices(0, {"swiftjsonui": "2222222222"}), [])

    def test_silent_when_the_library_did_not_move(self):
        self.assertEqual(self._notices(5, {"swiftjsonui": "1111111111"}), [])

    def test_speaks_up_when_both_are_true(self):
        notices = self._notices(5, {"swiftjsonui": "2222222222"})
        self.assertEqual(len(notices), 1)
        self.assertIn("5 regression(s)", notices[0])
        self.assertIn("11111111->22222222", notices[0])

    def test_says_so_when_the_baseline_predates_the_field(self):
        path = self.conf / "baselines" / "local" / "ios.hashes.json"
        data = json.loads(path.read_text())
        del data["rendered_by"]
        path.write_text(json.dumps(data))
        notices = self._notices(3, {"swiftjsonui": "2222222222"})
        self.assertEqual(len(notices), 1)
        self.assertIn("predates", notices[0])

    def test_is_never_a_failure(self):
        """The library moving is a state, not a defect.

        It is supposed to move; the baseline is supposed to be rebaked.
        """
        outcome = gate.GateOutcome()
        outcome.notices.extend(self._notices(5, {"swiftjsonui": "2222222222"}))
        self.assertTrue(outcome.ok)


if __name__ == "__main__":
    unittest.main()
