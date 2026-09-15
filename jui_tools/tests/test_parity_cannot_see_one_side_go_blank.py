"""Parity judged by Hamming alone, so a blank codegen render matched a faint one.

THE DEFECT THIS EXISTS FOR

`hamming(h, 0) == popcount(h)`, so a codegen render that is COMPLETELY BLANK
sits within the threshold of any dynamic render whose popcount is at or below
it — and the fainter the dynamic picture, the more blank codegen renders it
accepts. Those pairs land in `matched`: agreement claimed for the wrong reason,
with no ledger entry and no deviation to read.

Measured 2026-09-15 on the committed artifacts, and every one of these was
sitting in `matched` before this:

    ci/ios      2 pairs   Web_html__static  codegen ink 0 vs dynamic 533
                          control_Web       codegen ink 0 vs dynamic 205
    ci/android  6 pairs   NetworkImage_placeholder  codegen 2560 vs dynamic 0
                          (5 of the 6 were in `matched`)

🔻 THE POPULATION IS TWO-SIDED, UNLIKE THE BASELINE GATE'S. There, one side is
a committed hash and the question is "did THIS picture go blank". Here both
sides are renders, so either going blank opens the same hole — a pair is blind
when EITHER hash is within the threshold of zero. A one-sided derivation was
measured against the real corpus and it changes the population (ci/android 101
-> 100); it did not change the finding on today's data, so the guard is
defended by construction rather than by that measurement.

⚠️ AND PARITY HAS THE EASY HALF OF THE PROBLEM. Both pictures are in hand, so
there is nothing to have recorded ahead of time — the baseline gate needs a
committed ink because one side of its comparison is only a hash.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.conformance import parity

try:
    from PIL import Image

    HAVE_PILLOW = True
except ImportError:  # pragma: no cover
    HAVE_PILLOW = False


def _blank(path: Path) -> None:
    Image.new("RGB", (64, 64), (255, 255, 255)).save(path)


def _faint(path: Path, ink: int) -> None:
    img = Image.new("RGB", (64, 64), (255, 255, 255))
    for i in range(ink):
        img.putpixel((i % 64, i // 64), (0, 0, 0))
    img.save(path)


def _loud(path: Path) -> None:
    img = Image.new("RGB", (64, 64), (255, 255, 255))
    for x in range(0, 64, 2):
        for y in range(64):
            img.putpixel((x, y), (0, 0, 0))
    img.save(path)


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed (jui-tools[conformance])")
class ParitySeesOneSideGoBlankTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.conf = self.tmp / "conformance"
        self.codegen = self.conf / "artifacts" / "ios-codegen"
        self.dynamic = self.conf / "artifacts" / "ios"
        self.codegen.mkdir(parents=True)
        self.dynamic.mkdir(parents=True)
        (self.conf / "baselines" / "ci").mkdir(parents=True)
        (self.conf / "baselines" / "ci" / "ios.hashes.json").write_text(
            json.dumps({"platform": "ios", "environment": "ci", "algorithm": "dhash-64",
                        "threshold": 8, "hashes": {}})
        )

    def _measure(self):
        return parity.measure(
            self.conf, "ios", env="ci",
            codegen_dir=self.codegen, dynamic_dir=self.dynamic,
        )

    def _lane_proof(self) -> None:
        """One pair that hashes blank on both sides — the existence proof that
        a blank picture reaches zero on this lane. Every real face has them
        (20 on ci/ios, 11 on ci/android, 8 on ci/web)."""
        _blank(self.codegen / "empty.png")
        _blank(self.dynamic / "empty.png")

    def test_a_blank_codegen_against_a_faint_dynamic_is_caught(self) -> None:
        """THE TICKET. Both halves asserted: Hamming calls it matched, and the
        ink predicate does not."""
        self._lane_proof()
        _blank(self.codegen / "web.png")
        _faint(self.dynamic / "web.png", 400)
        r = self._measure()
        self.assertIn("web.png", r.matched, "if Hamming catches this, the arm is not measuring the defect")
        self.assertEqual([n for n, _, _ in r.ink_mismatched], ["web.png"])

    def test_the_other_direction_too(self) -> None:
        """Either side going blank opens the same hole — that is why the
        population is two-sided."""
        self._lane_proof()
        _faint(self.codegen / "web.png", 400)
        _blank(self.dynamic / "web.png")
        r = self._measure()
        self.assertIn("web.png", r.matched)
        self.assertEqual([n for n, _, _ in r.ink_mismatched], ["web.png"])

    def test_two_faint_pictures_that_agree_are_not_flagged(self) -> None:
        """The control that makes the arms above mean something."""
        self._lane_proof()
        _faint(self.codegen / "web.png", 400)
        _faint(self.dynamic / "web.png", 390)
        r = self._measure()
        self.assertIn("web.png", r.matched)
        self.assertEqual(r.ink_mismatched, [])
        self.assertGreater(r.ink_checked, 0, "an ink check that judged nothing passes vacuously")

    def test_a_loud_pair_is_left_to_hamming(self) -> None:
        """The boundary: the new predicate must not expand past its population.

        ⚠️ BOTH SIDES HAVE TO BE LOUD. The first version put a BLANK on the
        dynamic side, which makes the pair blind BY DEFINITION under the
        two-sided rule — the arm was asserting against the very property it
        was written to protect, and it failed for being right.
        """
        self._lane_proof()
        # 🔻 THE DISCRIMINATING FIXTURE: Hamming already calls this a
        # mismatch AND the inks differ wildly. A version that ink-checked
        # every pair instead of only the matched ones would report it twice —
        # once as a deviation and once as a blank-render finding — which is
        # the same defect counted in two places. A pair of high-contrast stripes offset by one
        # column was the first fixture here and could not tell the two versions
        # apart, because both its sides carry similar ink.
        _loud(self.codegen / "loud.png")
        _blank(self.dynamic / "loud.png")
        r = self._measure()
        self.assertIn("loud.png", [n for n, _ in r.mismatched], "Hamming's job")
        self.assertNotIn(
            "loud.png", r.matched,
            "the ink check only looks at MATCHED pairs, so a mismatched one must "
            "stay out of its population entirely",
        )
        self.assertEqual([n for n, _, _ in r.ink_mismatched], [])

    def test_the_baseline_fallback_reports_its_pairs_as_unjudged(self) -> None:
        """🔴 NOT "nothing to check". With no dynamic renders the comparison
        falls back to committed hashes, and a hash cannot be asked how much ink
        it has — so those matched pairs were never checked, and silence there
        would let the fallback read as a full check."""
        _faint(self.codegen / "a.png", 400)
        import shutil
        shutil.rmtree(self.dynamic)
        path = self.conf / "baselines" / "ci" / "ios.hashes.json"
        baked = json.loads(path.read_text())
        from jui_cli.conformance.baseline import dhash_file
        baked["hashes"] = {"a.png": dhash_file(self.codegen / "a.png")}
        path.write_text(json.dumps(baked))
        r = self._measure()
        self.assertEqual(r.source, "baseline")
        self.assertEqual(r.ink_checked, 0)
        self.assertEqual(r.blank_check_unavailable, len(r.matched))
        self.assertGreater(r.blank_check_unavailable, 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
