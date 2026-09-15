"""`--fail-on-moved` must refuse BEFORE the write, not report after it.

THE DEFECT THIS EXISTS FOR

`update_baseline` wrote the file unconditionally and the CLI checked the flag on
the summary it returned — i.e. after the baseline had already been replaced. The
exit code was honest and the file was gone. Measured 2026-09-15: baking two
android entries with the flag on landed 797 insertions / 800 deletions and then
exited 1, so the flag performed the exact thing it exists to prevent. The run
even printed "a wholesale bake rewrote the moved entries above" one line above
the error, so both halves of the contradiction were in the same output.

⚠️ AND THE MEASUREMENT THAT VOUCHED FOR THE FLAG WAS THE SYMPTOM. The shipped
README said: "the flag exits 1 with 2 moved, and on a re-run against the
already-baked set it exits 0 with moved 0 — it fires on the thing and not on
everything." That second run is not evidence the flag discriminates. It is
evidence the first run wrote. A flag that refused would report the same count
both times, because nothing would have changed between them.

So the arm below is that comparison, turned the right way up: run the same bake
twice and require the same number. It is the only one that measures "did not
write" directly rather than by inspecting the file afterwards.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.conformance.baseline import BaselineMoved, update_baseline

try:
    from PIL import Image

    HAVE_PILLOW = True
except ImportError:  # pragma: no cover
    HAVE_PILLOW = False


def _png(path: Path, shade: int) -> None:
    img = Image.new("RGB", (64, 64), (255, 255, 255))
    for x in range(0, 64, 4):
        for y in range(32):
            img.putpixel((x, y), (shade, shade, shade))
    img.save(path)


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed (jui-tools[conformance])")
class TheFlagRefusesInsteadOfReporting(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.conf = self.tmp / "conformance"
        (self.conf / "artifacts" / "ios").mkdir(parents=True)
        (self.conf / "baselines" / "local").mkdir(parents=True)
        self.art = self.conf / "artifacts" / "ios"
        _png(self.art / "a.png", 0)
        _png(self.art / "b.png", 40)
        # A committed baseline, then a render that moves one of the two.
        update_baseline(self.conf, "ios", artifacts_dir=self.art, env="local")
        self.baseline = self.conf / "baselines" / "local" / "ios.hashes.json"
        self.before = self.baseline.read_bytes()
        _png(self.art / "b.png", 200)  # now it differs

    def _bake(self, **kw):
        return update_baseline(
            self.conf, "ios", artifacts_dir=self.art, env="local", **kw
        )

    def test_it_raises_and_the_file_is_byte_identical(self) -> None:
        with self.assertRaises(BaselineMoved) as caught:
            self._bake(refuse_if_moved=True)
        self.assertTrue(caught.exception.moved, "the refusal must carry what moved")
        self.assertEqual(
            self.baseline.read_bytes(),
            self.before,
            "the baseline was rewritten despite the refusal — the whole defect",
        )

    def test_the_same_bake_twice_reports_the_same_count(self) -> None:
        """The arm that measures "did not write" DIRECTLY.

        Under the defect the second run reported zero, because the first had
        already absorbed the move. Equality across two runs is the only check
        that does not depend on reading the file afterwards.
        """
        counts = []
        for _ in range(2):
            with self.assertRaises(BaselineMoved) as caught:
                self._bake(refuse_if_moved=True)
            counts.append(len(caught.exception.moved))
        self.assertEqual(
            counts[0],
            counts[1],
            f"second run saw {counts[1]} where the first saw {counts[0]} — "
            "the first run wrote",
        )
        self.assertGreater(counts[0], 0, "the fixture must actually move something")

    def test_without_the_flag_it_still_writes(self) -> None:
        """The boundary: the refusal must not have disabled baking."""
        summary = self._bake()
        self.assertTrue(summary.moved)
        self.assertNotEqual(
            self.baseline.read_bytes(), self.before, "a wholesale bake must still write"
        )

    def test_a_clean_bake_writes_even_with_the_flag(self) -> None:
        """Nothing moved, so there is nothing to refuse."""
        self._bake()  # absorb the move
        stable = self.baseline.read_bytes()
        summary = self._bake(refuse_if_moved=True)
        self.assertEqual(summary.moved, ())
        self.assertEqual(self.baseline.read_bytes(), stable)

    def test_only_new_is_a_different_door(self) -> None:
        """`--only-new` keeps moved entries by construction, so the refusal is
        not wired to it — the CLI passes `fail_on_moved and not only_new`."""
        summary = self._bake(only_new=True)
        after = json.loads(self.baseline.read_text())
        before = json.loads(self.before.decode())
        self.assertEqual(
            after["hashes"]["b.png"],
            before["hashes"]["b.png"],
            "--only-new must leave a moved entry at its committed hash",
        )
        self.assertTrue(summary.moved)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
