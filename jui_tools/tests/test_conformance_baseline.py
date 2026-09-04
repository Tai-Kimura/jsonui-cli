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
class IosLocalChromeCropTest(unittest.TestCase):
    """What the ios crop buys, on the local lane as well as ci.

    Two "iPhone 16 Pro / iOS 18.6" simulators differing only in UDID rendered
    the same corpus with 849 of 852 hashes moved while the content was
    identical; the differing pixels sat in the status-bar rows, and cropping
    them brought the same pairs to 0-4 (measured 2026-09-04). Android local
    stays uncropped on purpose — that AVD has no taskbar, so those rows hold
    real content.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _pair_differing_only_in_chrome(self):
        """Same content, different status-bar band — the cross-device shape.

        Glyphs drawn black on one and white on the other: the documented real
        case is exactly that (the clock's colour is inferred from the
        luminance behind the bar and flipped between two runs of the same
        image, dhash 23). A gentler contrast does not clear the threshold,
        which is the arm passing for the wrong reason — the first draft used
        black vs grey and stayed under it.
        """
        a = _write_png(self.tmp / "a.png", size=(603, 1311))
        b = _write_png(self.tmp / "b.png", size=(603, 1311))
        # Content well below the band, identical on both.
        for path in (a, b):
            img = Image.open(path).convert("RGB")
            draw = ImageDraw.Draw(img)
            draw.rectangle([80, 300, 520, 900], fill=(40, 90, 200))
            img.save(path)
        for path, fill in ((a, "black"), (b, "white")):
            img = Image.open(path).convert("RGB")
            draw = ImageDraw.Draw(img)
            # glyph-sized marks inside the top band only (rows 39..58 of 1311,
            # the same fraction of the frame as rows 78..117 of 2622)
            for x in range(40, 560, 24):
                draw.rectangle([x, 39, x + 14, 58], fill=fill)
            img.save(path)
        return a, b

    def test_a_chrome_only_difference_moves_an_uncropped_hash(self):
        a, b = self._pair_differing_only_in_chrome()
        distance = baseline.hamming(baseline.dhash_file(a), baseline.dhash_file(b))
        self.assertGreater(distance, baseline.DEFAULT_THRESHOLD)

    def test_the_ios_crop_removes_it_on_both_lanes(self):
        a, b = self._pair_differing_only_in_chrome()
        for env in ("ci", "local"):
            crop = baseline.chrome_crop("ios", env)
            distance = baseline.hamming(
                baseline.dhash_file(a, crop=crop), baseline.dhash_file(b, crop=crop)
            )
            self.assertLessEqual(distance, baseline.DEFAULT_THRESHOLD, env)

    def test_the_crop_still_sees_a_change_below_the_band(self):
        """The crop must not blind the lane to content. The content here sits
        BELOW row 160 — the first draft put it at rows 50..149, inside the
        band, so the arm passed for the wrong reason and proved nothing."""
        a, b = self._pair_differing_only_in_chrome()
        img = Image.open(b).convert("RGB")
        draw = ImageDraw.Draw(img)
        for x in range(60, 300, 40):
            draw.rectangle([x, 400, x + 20, 700], fill="black")
        img.save(b)
        crop = baseline.chrome_crop("ios", "local")
        distance = baseline.hamming(
            baseline.dhash_file(a, crop=crop), baseline.dhash_file(b, crop=crop)
        )
        self.assertGreater(distance, baseline.DEFAULT_THRESHOLD)


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
class AdditiveBakeTest(unittest.TestCase):
    """`--only-new`: insert what is missing, touch nothing else.

    The wholesale rewrite is right for a recalibration and wrong for "these
    fixtures never got baselines", because it also writes every drifted
    picture into the baseline in the same pass. On 2026-09-04 two lanes did
    that job with a hand-written merge and a `git diff --numstat` check; the
    check was what made it safe, not the command. These arms are that check,
    moved into the tool.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conf = Path(self._tmp.name)
        self.art = self.conf / "artifacts" / "web"
        _write_png(self.art / "stable.png")
        _write_png(self.art / "drifts.png", gradient_horizontal=True)
        _write_png(self.art / "goes_away.png")
        baseline.update_baseline(
            self.conf, "web", rendered_by={"rjui": "tree:abc123"}
        )
        self.committed = json.loads(
            baseline.baseline_path(self.conf, "web").read_text(encoding="utf-8")
        )
        # Second run: one picture changed, one vanished, one is brand new.
        _write_png(self.art / "drifts.png", gradient_horizontal=False)
        (self.art / "goes_away.png").unlink()
        _write_png(self.art / "brand_new.png", gradient_horizontal=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _hashes(self):
        return json.loads(
            baseline.baseline_path(self.conf, "web").read_text(encoding="utf-8")
        )["hashes"]

    def test_only_new_inserts_the_missing_entry(self):
        s = baseline.update_baseline(self.conf, "web", only_new=True)
        self.assertIn("brand_new.png", self._hashes())
        self.assertEqual(list(s.new), ["brand_new.png"])

    def test_only_new_keeps_a_drifted_picture_at_its_committed_hash(self):
        # The arm that matters: absorbing this silently is how a regression
        # stops being a regression.
        before = self.committed["hashes"]["drifts.png"]
        baseline.update_baseline(self.conf, "web", only_new=True)
        self.assertEqual(self._hashes()["drifts.png"], before)

    def test_only_new_does_not_remove_a_vanished_entry(self):
        baseline.update_baseline(self.conf, "web", only_new=True)
        self.assertIn("goes_away.png", self._hashes())

    def test_only_new_keeps_the_committed_provenance_it_did_not_redraw(self):
        # An additive bake did not draw the old pictures, so it must not
        # restate — or blank — who drew them.
        baseline.update_baseline(self.conf, "web", only_new=True)
        payload = json.loads(
            baseline.baseline_path(self.conf, "web").read_text(encoding="utf-8")
        )
        self.assertEqual(payload["rendered_by"], {"rjui": "tree:abc123"})

    def test_the_wholesale_default_still_rewrites_everything(self):
        # Not a defect: recalibration needs it. Pinned so that "only-new is
        # the default now" cannot happen by accident.
        baseline.update_baseline(self.conf, "web")
        h = self._hashes()
        self.assertNotEqual(h["drifts.png"], self.committed["hashes"]["drifts.png"])
        self.assertNotIn("goes_away.png", h)

    def test_classification_is_reported_before_the_mode_is_applied(self):
        # The counts describe what the run FOUND, not what it wrote, so a
        # reader can see what a wholesale bake would have changed while
        # running the additive one. Both modes classify against the same
        # committed baseline, so both must report the same four sets.
        additive = baseline.update_baseline(self.conf, "web", only_new=True)
        self.assertEqual(list(additive.new), ["brand_new.png"])
        self.assertEqual([n for n, _ in additive.moved], ["drifts.png"])
        self.assertEqual(list(additive.dropped), ["goes_away.png"])
        self.assertEqual(list(additive.same), ["stable.png"])
        self.assertTrue(all(d > 0 for _, d in additive.moved))


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
    and neither can carry fixture pixels there. The local AVD has no taskbar, so
    the same rows hold real content and must stay in the hash.

    A lane is cropped when its chrome is nondeterministic, not because it is a
    CI lane — this used to be asserted as "local is never cropped", which held
    only while android was the sole cropped platform.
    """

    def test_a_lane_is_cropped_when_its_chrome_is_nondeterministic(self):
        # android/web local: those rows carry fixture pixels and nothing in
        # them moves on its own, so they stay in the hash.
        self.assertEqual(baseline.chrome_crop("android", "local"), (0, 0))
        self.assertEqual(baseline.chrome_crop("web", "local"), (0, 0))
        # ios local: the same status-bar glyphs as the ci lane, and they are
        # not stable across simulator INSTANCES either — two iPhone 16 Pro /
        # iOS 18.6 devices differing only in UDID moved 849 of 852 hashes with
        # the content identical, and 0-4 once cropped (2026-09-04).
        self.assertEqual(baseline.chrome_crop("ios", "local"), (160, 0))
        # an unknown lane still never crops silently
        self.assertEqual(baseline.chrome_crop("web", "ci"), (0, 0))
        self.assertEqual(baseline.chrome_crop(None, None), (0, 0))

    def test_ci_android_excludes_the_measured_chrome_bands(self):
        self.assertEqual(baseline.chrome_crop("android", "ci"), (48, 120))

    def test_ci_ios_excludes_the_status_bar_band(self):
        # The glyphs live at rows 78–116 and their color is inferred from the
        # luminance behind the bar — a race the fixture cannot pin (measured
        # flipping black/white across runs 32657361988/33333136630 on
        # effectStyle__regular with every non-glyph pixel identical). The app
        # is edge-to-edge on ios, so unlike android this band carries fixture
        # pixels; the crop trades them away and says so at the definition.
        self.assertEqual(baseline.chrome_crop("ios", "ci"), (160, 0))

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
