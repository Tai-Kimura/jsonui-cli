"""Tests for screenshot baseline hashing (`jui conformance baseline`).

Covers the plan-12 §3 acceptance criteria on the baseline side:

- hash stability (same image -> same hash; deterministic across calls)
- sensitivity (a small localized change must exceed the threshold — this is
  the regression that motivated the 64x64 grid: a 16x16 dHash missed it)
- noise tolerance (distance <= threshold for near-identical renders)
- baseline update determinism (sorted keys, no timestamps, @generated)
- comparison buckets: match / regression / no-baseline / missing-artifact
  (a screenshot without a baseline is *reported*, never a silent pass)

Pillow is an optional dependency (`jui-tools[conformance]`); the whole
module is skipped when it is unavailable.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

try:
    from PIL import Image, ImageDraw

    HAVE_PILLOW = True
except ImportError:  # pragma: no cover - environment dependent
    HAVE_PILLOW = False

from jui_cli.conformance import baseline


def _write_png(path: Path, *, box: tuple[int, int, int, int] | None = None,
               gradient_horizontal: bool | None = None, size=(512, 384)) -> Path:
    """Deterministic synthetic screenshot: white page + optional content."""
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    if gradient_horizontal is not None:
        # 100x100 gradient box at a fixed position (mimics a fixture target
        # occupying a small fraction of the page).
        for i in range(100):
            shade = int(255 * i / 99)
            if gradient_horizontal:
                draw.line([(50 + i, 50), (50 + i, 149)], fill=(shade, 0, 255 - shade))
            else:
                draw.line([(50, 50 + i), (149, 50 + i)], fill=(shade, 0, 255 - shade))
    if box:
        draw.rectangle(box, fill="black")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed (jui-tools[conformance])")
class DhashTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_hash_is_stable_and_hex_encoded(self):
        png = _write_png(self.tmp / "a.png")
        h1 = baseline.dhash_file(png)
        h2 = baseline.dhash_file(png)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), baseline.HASH_SIZE * baseline.HASH_SIZE // 4)
        int(h1, 16)  # must be valid hex

    def test_identical_content_different_files_match(self):
        a = _write_png(self.tmp / "a.png")
        b = _write_png(self.tmp / "b.png")
        self.assertEqual(baseline.dhash_file(a), baseline.dhash_file(b))

    def test_small_localized_change_exceeds_threshold(self):
        """A gradient-direction flip inside a 100x100 box on a mostly white
        page — the exact change class a 16x16 global hash failed to see."""
        a = _write_png(self.tmp / "a.png", gradient_horizontal=False)
        b = _write_png(self.tmp / "b.png", gradient_horizontal=True)
        distance = baseline.hamming(baseline.dhash_file(a), baseline.dhash_file(b))
        self.assertGreater(distance, baseline.DEFAULT_THRESHOLD)

    def test_hamming_rejects_length_mismatch(self):
        with self.assertRaises(ValueError):
            baseline.hamming("00", "0000")


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed (jui-tools[conformance])")
class BaselineUpdateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conf = Path(self._tmp.name)
        self.artifacts = self.conf / "artifacts" / "web"
        _write_png(self.artifacts / "B_fixture.png")
        _write_png(self.artifacts / "A_fixture.png", box=(10, 10, 40, 40))

    def tearDown(self):
        self._tmp.cleanup()

    def test_update_writes_deterministic_manifest(self):
        summary = baseline.update_baseline(self.conf, "web")
        self.assertEqual(summary.hashed, 2)
        content1 = summary.out_path.read_text(encoding="utf-8")
        baseline.update_baseline(self.conf, "web")
        self.assertEqual(content1, summary.out_path.read_text(encoding="utf-8"))

        payload = json.loads(content1)
        self.assertEqual(payload["_generated"]["sentinel"], "@generated")
        self.assertEqual(payload["algorithm"], baseline.ALGORITHM)
        self.assertEqual(payload["threshold"], baseline.DEFAULT_THRESHOLD)
        self.assertEqual(list(payload["hashes"]), ["A_fixture.png", "B_fixture.png"])
        self.assertNotIn("generatedAt", content1)

    def test_update_without_artifacts_errors(self):
        with self.assertRaises(baseline.BaselineError):
            baseline.update_baseline(self.conf, "ios")


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed (jui-tools[conformance])")
class ComparePlatformTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conf = Path(self._tmp.name)
        self.artifacts = self.conf / "artifacts" / "web"
        _write_png(self.artifacts / "stable.png")
        _write_png(self.artifacts / "changed.png", gradient_horizontal=False)
        baseline.update_baseline(self.conf, "web")

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_baseline_recorded_reports_every_screenshot(self):
        comparison = baseline.compare_platform(self.conf, "android", ["x.png"])
        self.assertFalse(comparison.baseline_exists)
        self.assertEqual(comparison.no_baseline, ["x.png"])
        self.assertEqual(comparison.compared, 0)

    def test_clean_rerun_has_no_regressions(self):
        comparison = baseline.compare_platform(
            self.conf, "web", ["stable.png", "changed.png"]
        )
        self.assertTrue(comparison.baseline_exists)
        self.assertEqual(comparison.compared, 2)
        self.assertEqual(comparison.regressions, [])
        self.assertEqual(comparison.no_baseline, [])
        self.assertEqual(comparison.missing_artifact, [])

    def test_visual_change_is_detected_as_regression(self):
        _write_png(self.artifacts / "changed.png", gradient_horizontal=True)
        comparison = baseline.compare_platform(
            self.conf, "web", ["stable.png", "changed.png"]
        )
        self.assertEqual(len(comparison.regressions), 1)
        name, distance = comparison.regressions[0]
        self.assertEqual(name, "changed.png")
        self.assertGreater(distance, comparison.threshold)

    def test_new_screenshot_without_baseline_is_reported_not_passed(self):
        _write_png(self.artifacts / "brand_new.png")
        comparison = baseline.compare_platform(
            self.conf, "web", ["stable.png", "changed.png", "brand_new.png"]
        )
        self.assertEqual(comparison.no_baseline, ["brand_new.png"])
        self.assertEqual(comparison.regressions, [])

    def test_missing_artifact_and_stale_baseline_entries_are_reported(self):
        (self.artifacts / "changed.png").unlink()
        comparison = baseline.compare_platform(
            self.conf, "web", ["stable.png", "changed.png"]
        )
        self.assertEqual(comparison.missing_artifact, ["changed.png"])
        # baseline-only entries (fixture removed) surface too
        comparison2 = baseline.compare_platform(self.conf, "web", ["stable.png"])
        self.assertIn("changed.png", comparison2.missing_artifact)

    def test_algorithm_mismatch_marks_baseline_stale(self):
        path = baseline.baseline_path(self.conf, "web")
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["algorithm"] = "dhash-8"
        path.write_text(json.dumps(payload), encoding="utf-8")
        comparison = baseline.compare_platform(self.conf, "web", ["stable.png"])
        self.assertEqual(comparison.algorithm_mismatch, "dhash-8")
        self.assertEqual(comparison.compared, 0)


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed (jui-tools[conformance])")
class EnvironmentKeyTest(unittest.TestCase):
    """Render-environment keying: baselines/<env>/, default ``local``.

    A baseline is a fact about one renderer — the 2026-08-01 CI run proved a
    local bake and a CI render disagree wholesale while both are internally
    healthy. These tests pin that environments are isolated, self-describing,
    and refuse cross-env comparison.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conf = Path(self._tmp.name)
        self.artifacts = self.conf / "artifacts" / "web"
        _write_png(self.artifacts / "stable.png")

    def tearDown(self):
        self._tmp.cleanup()

    def test_update_defaults_to_the_local_env_dir_and_records_it(self):
        summary = baseline.update_baseline(self.conf, "web")
        self.assertEqual(
            summary.out_path,
            self.conf / "baselines" / "local" / "web.hashes.json",
        )
        payload = json.loads(summary.out_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["environment"], "local")

    def test_update_bakes_under_a_named_env(self):
        summary = baseline.update_baseline(self.conf, "web", env="ci")
        self.assertEqual(
            summary.out_path, self.conf / "baselines" / "ci" / "web.hashes.json"
        )
        payload = json.loads(summary.out_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["environment"], "ci")

    def test_environments_are_isolated(self):
        baseline.update_baseline(self.conf, "web")  # local only
        comparison = baseline.compare_platform(
            self.conf, "web", ["stable.png"], env="ci"
        )
        self.assertFalse(comparison.baseline_exists)
        self.assertEqual(comparison.no_baseline, ["stable.png"])

    def test_env_mismatch_refuses_to_compare(self):
        # A ci-baked manifest copied into the local slot must not be compared
        # as local — that IS the cross-renderer comparison the key prevents.
        baked = baseline.update_baseline(self.conf, "web", env="ci")
        local_path = baseline.baseline_path(self.conf, "web")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(baked.out_path.read_text(encoding="utf-8"))
        comparison = baseline.compare_platform(self.conf, "web", ["stable.png"])
        self.assertIsNotNone(comparison.error)
        self.assertIn("records environment 'ci'", comparison.error)
        self.assertEqual(comparison.compared, 0)

    def test_update_stores_a_recalibrated_threshold(self):
        summary = baseline.update_baseline(self.conf, "web", env="ci", threshold=12)
        payload = json.loads(summary.out_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["threshold"], 12)
        # comparisons pick the stored value up (compare_platform reads it)
        comparison = baseline.compare_platform(
            self.conf, "web", ["stable.png"], env="ci"
        )
        self.assertEqual(comparison.threshold, 12)

    def test_legacy_manifest_without_environment_field_still_compares(self):
        baseline.update_baseline(self.conf, "web")
        path = baseline.baseline_path(self.conf, "web")
        payload = json.loads(path.read_text(encoding="utf-8"))
        del payload["environment"]  # pre-env-key manifest: location is the claim
        path.write_text(json.dumps(payload), encoding="utf-8")
        comparison = baseline.compare_platform(self.conf, "web", ["stable.png"])
        self.assertIsNone(comparison.error)
        self.assertEqual(comparison.compared, 1)


class BaselineCommandTest(unittest.TestCase):
    """`jui conformance baseline` argparse dispatch."""

    @unittest.skipUnless(HAVE_PILLOW, "Pillow not installed (jui-tools[conformance])")
    def test_update_subcommand_returns_zero(self):
        import argparse

        from jui_cli.commands.conformance_cmd import cmd_conformance

        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp)
            _write_png(conf / "artifacts" / "web" / "one.png")
            args = argparse.Namespace(
                conformance_target="baseline",
                baseline_action="update",
                platform="web",
                conformance_dir=str(conf),
                artifacts=None,
                env=None,
            )
            self.assertEqual(cmd_conformance(args), 0)
            self.assertTrue((conf / "baselines" / "local" / "web.hashes.json").is_file())

    def test_missing_action_prints_usage(self):
        import argparse

        from jui_cli.commands.conformance_cmd import cmd_conformance

        args = argparse.Namespace(
            conformance_target="baseline", baseline_action=None
        )
        self.assertEqual(cmd_conformance(args), 1)


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed")
class ChromeCropTests(unittest.TestCase):
    """System-chrome exclusion is per (platform, env) — see PLATFORM_ENV_CHROME_CROP.

    The CI android lane draws an opaque status bar and launcher taskbar over an
    inset app; both move on their own (clock ticks, predicted-apps row reorders)
    and neither can carry fixture pixels there. Local has no taskbar, so the same
    rows hold real content and must stay in the hash.
    """

    def test_local_lanes_are_never_cropped(self):
        for platform in ("android", "ios", "web"):
            self.assertEqual(baseline.chrome_crop(platform, "local"), (0, 0))
        self.assertEqual(baseline.chrome_crop("ios", "ci"), (0, 0))
        self.assertEqual(baseline.chrome_crop(None, None), (0, 0))

    def test_ci_android_excludes_the_measured_chrome_bands(self):
        self.assertEqual(baseline.chrome_crop("android", "ci"), (48, 120))

    def test_crop_hides_change_confined_to_the_excluded_band(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = _write_png(root / "clean.png", size=(512, 384))
            # A change entirely inside the bottom band: same fixture, different
            # taskbar. Uncropped it is a regression; cropped it is invisible.
            # The icons must have horizontal structure — dHash compares
            # left-to-right neighbours, so a full-width band of one colour is
            # invisible to it either way and would prove nothing.
            img = Image.open(clean).convert("RGB")
            draw = ImageDraw.Draw(img)
            for x in range(180, 340, 40):
                draw.rectangle((x, 310, x + 20, 350), fill="black")
            noisy = root / "noisy.png"
            img.save(noisy)

            crop = (48, 120)
            self.assertNotEqual(
                baseline.dhash_file(clean), baseline.dhash_file(noisy)
            )
            self.assertEqual(
                baseline.dhash_file(clean, crop), baseline.dhash_file(noisy, crop)
            )

    def test_crop_still_sees_change_above_the_band(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = _write_png(root / "clean.png", size=(512, 384))
            img = Image.open(clean).convert("RGB")
            draw = ImageDraw.Draw(img)
            draw.rectangle((100, 150, 200, 250), fill="black")
            changed = root / "changed.png"
            img.save(changed)

            crop = (48, 120)
            distance = baseline.hamming(
                baseline.dhash_file(clean, crop), baseline.dhash_file(changed, crop)
            )
            self.assertGreater(distance, baseline.DEFAULT_THRESHOLD)


if __name__ == "__main__":
    unittest.main()
