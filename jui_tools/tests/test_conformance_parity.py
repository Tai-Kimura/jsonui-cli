"""Tests for dynamic ≡ codegen parity (`jui conformance parity` / `gate --parity`).

The measurement compares codegen-host screenshots against the SAME
platform's dynamic baseline (same dhash, same stored threshold) — no second
truth. The ledger (`codegen_parity.json`) is operated like coverage.json:
recorded deviations pass with their reason, unrecorded ones fail, entries
the measurement no longer supports are stale and must be pruned.

Pillow-dependent (image hashing); the whole module skips without it.
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

from jui_cli.conformance import baseline, parity


def _write_png(path: Path, *, box=None, gradient_horizontal=True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("L", (256, 192))
    for x in range(256):
        for y in range(0, 192, 8):
            value = x if gradient_horizontal else (y * 255) // 192
            img.paste(value, (x, y, x + 1, min(y + 8, 192)))
    if box:
        ImageDraw.Draw(img).rectangle(box, fill=255)
    img.save(path)


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed (jui-tools[conformance])")
class ParityMeasureTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conf = Path(self._tmp.name)
        # dynamic artifacts -> baked local baseline (three screenshots)
        dyn = self.conf / "artifacts" / "ios"
        _write_png(dyn / "A.png")
        _write_png(dyn / "B.png", box=(10, 10, 60, 60))
        _write_png(dyn / "C.png", gradient_horizontal=False)
        baseline.update_baseline(self.conf, "ios")
        # codegen artifacts: A matches, B differs, C missing, D is extra
        cg = self.conf / "artifacts" / "ios-codegen"
        _write_png(cg / "A.png")
        _write_png(cg / "B.png", box=(120, 100, 240, 180))
        _write_png(cg / "D.png")

    def tearDown(self):
        self._tmp.cleanup()

    def test_buckets_every_name_from_both_pipelines_exactly_once(self):
        result = parity.measure(self.conf, "ios")
        self.assertIsNone(result.error)
        self.assertEqual(result.source, "dynamic")
        self.assertEqual(result.matched, ["A.png"])
        self.assertEqual([n for n, _ in result.mismatched], ["B.png"])
        self.assertGreater(result.mismatched[0][1], result.threshold)
        # One-sided names are kept apart from the deviations and from each
        # other: C is a fixture the codegen host did not render, D one the
        # dynamic host did not. Neither is "the two draw different things".
        self.assertEqual(result.missing, ["C.png"])
        self.assertEqual(result.codegen_only, ["D.png"])

    def test_compares_names_the_baseline_predates(self):
        """A fixture added after the bake is compared, not skipped.

        The first shape looped over the baseline's key space, so a new
        fixture was never measured — 168 of 662 renders in the run that
        found it, most of them this wave's bound fixtures.
        """
        _write_png(self.conf / "artifacts" / "ios" / "E.png")
        _write_png(
            self.conf / "artifacts" / "ios-codegen" / "E.png", box=(0, 0, 200, 180)
        )
        result = parity.measure(self.conf, "ios")
        self.assertIn("E.png", [n for n, _ in result.mismatched])

    def test_stale_baseline_does_not_invent_deviations(self):
        """Drift of the baseline is not drift between the pipelines.

        Rehashing the baseline off a different render leaves the two
        pipelines agreeing; only the baseline moved. The measurement must
        not report that as a codegen defect.
        """
        _write_png(self.conf / "artifacts" / "ios-codegen" / "C.png",
                   gradient_horizontal=False)
        for name in ("A.png", "B.png", "C.png"):
            _write_png(self.conf / "artifacts" / "ios" / name,
                       box=(5, 5, 250, 185))
            _write_png(self.conf / "artifacts" / "ios-codegen" / name,
                       box=(5, 5, 250, 185))
        result = parity.measure(self.conf, "ios")
        self.assertEqual(result.mismatched, [])
        self.assertEqual(result.missing, [])
        self.assertEqual(result.codegen_only, ["D.png"])

    def test_falls_back_to_baseline_without_dynamic_renders(self):
        result = parity.measure(
            self.conf, "ios", dynamic_dir=self.conf / "artifacts" / "absent"
        )
        self.assertEqual(result.source, "baseline")
        self.assertEqual(result.matched, ["A.png"])
        self.assertEqual([n for n, _ in result.mismatched], ["B.png"])

    def test_no_baseline_for_env_is_an_error_not_a_pass(self):
        result = parity.measure(self.conf, "ios", env="ci")
        self.assertIsNotNone(result.error)
        self.assertIn("baselines/ci/ios", result.error)

    def test_missing_codegen_dir_is_an_error(self):
        result = parity.measure(self.conf, "android")
        # android has no baseline either — bake one to isolate the dir error
        dyn = self.conf / "artifacts" / "android"
        _write_png(dyn / "A.png")
        baseline.update_baseline(self.conf, "android")
        result = parity.measure(self.conf, "android")
        self.assertIsNotNone(result.error)
        self.assertIn("android-codegen", result.error)


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed (jui-tools[conformance])")
class ParityLedgerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conf = Path(self._tmp.name)
        dyn = self.conf / "artifacts" / "ios"
        _write_png(dyn / "A.png")
        _write_png(dyn / "B.png", box=(10, 10, 60, 60))
        baseline.update_baseline(self.conf, "ios")
        cg = self.conf / "artifacts" / "ios-codegen"
        _write_png(cg / "A.png")
        _write_png(cg / "B.png", box=(120, 100, 240, 180))  # mismatch

    def tearDown(self):
        self._tmp.cleanup()

    def _measure(self):
        return parity.measure(self.conf, "ios")

    def test_unrecorded_deviation_fails_check(self):
        verdict = parity.check(self._measure(), {})
        self.assertFalse(verdict.ok)
        self.assertEqual(len(verdict.unrecorded), 1)
        self.assertIn("B.png", verdict.unrecorded[0])

    def test_update_records_and_check_accepts(self):
        path = parity.ledger_path(self.conf)
        merged = parity.update_ledger({}, self._measure())
        path.write_text(parity.render_ledger(merged), encoding="utf-8")

        ledger = parity.load_ledger(path)
        self.assertIn(("B.png", "ios", "local"), ledger)
        self.assertEqual(ledger[("B.png", "ios", "local")]["reason"], parity.UNREVIEWED)

        verdict = parity.check(self._measure(), ledger)
        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.accepted, 1)

    def test_update_preserves_reviewed_reasons(self):
        first = parity.update_ledger({}, self._measure())
        first[("B.png", "ios", "local")]["reason"] = "font-rasterizer difference"
        first[("B.png", "ios", "local")]["note"] = "verified by eye 2026-08-02"
        second = parity.update_ledger(first, self._measure())
        self.assertEqual(second[("B.png", "ios", "local")]["reason"], "font-rasterizer difference")
        self.assertEqual(second[("B.png", "ios", "local")]["note"], "verified by eye 2026-08-02")

    def test_stale_entry_is_flagged_and_pruned_by_update(self):
        # Record the deviation, then fix the codegen render.
        ledger = parity.update_ledger({}, self._measure())
        _write_png(self.conf / "artifacts" / "ios-codegen" / "B.png", box=(10, 10, 60, 60))

        verdict = parity.check(self._measure(), ledger)
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.stale, ["B.png"])

        pruned = parity.update_ledger(ledger, self._measure())
        self.assertNotIn(("B.png", "ios", "local"), pruned)

    def test_other_platforms_entries_are_untouched(self):
        ledger = {
            ("Z.png", "android", "local"): {
                "screenshot": "Z.png",
                "platform": "android",
                "env": "local",
                "status": "mismatch",
                "distance": 20,
                "reason": "reviewed",
                "note": "",
            }
        }
        merged = parity.update_ledger(ledger, self._measure())
        self.assertIn(("Z.png", "android", "local"), merged)
        verdict = parity.check(self._measure(), parity.load_ledger(parity.ledger_path(self.conf)))
        # android entry must not count as stale for an ios measurement
        self.assertNotIn("Z.png", verdict.stale)


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed (jui-tools[conformance])")
class GateParityTest(unittest.TestCase):
    """`evaluate(..., parity=True)` wires the verdict into problems/notices."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        try:
            from .test_conformance_generator import SYNTHETIC_DEFS, _write_defs
            from .test_conformance_report import _write_results
        except ImportError:
            from test_conformance_generator import SYNTHETIC_DEFS, _write_defs
            from test_conformance_report import _write_results
        from jui_cli.conformance.fixture_generator import generate_conformance

        defs_path = _write_defs(tmp, SYNTHETIC_DEFS)
        self.conf = tmp / "conformance"
        generate_conformance(defs_path, self.conf)
        manifest = json.loads((self.conf / "manifest.json").read_text(encoding="utf-8"))
        ids = [f["id"] for f in manifest["fixtures"]]
        _write_results(self.conf, "android", {fixture_id: "pass" for fixture_id in ids})

        # Name the stand-in screenshot after a fixture the manifest really
        # has: the parity ledger is screenshot-keyed and judge_ledger_keys
        # now runs by default, so an invented "A.png" would (correctly) be
        # reported as a row pointing nowhere.
        from jui_cli.conformance.gate import screenshot_name

        self.shot = screenshot_name(ids[0])
        dyn = self.conf / "artifacts" / "android"
        _write_png(dyn / self.shot)
        baseline.update_baseline(self.conf, "android")
        # The synthetic results reference no screenshots, so the baked
        # baseline entry counts as missing_artifact on the DYNAMIC side —
        # give that metric slack; parity is what this test exercises.
        (self.conf / "gate_ratchet.json").write_text(
            json.dumps({"missing_artifact": {"android": 1}}), encoding="utf-8"
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _evaluate(self):
        from jui_cli.conformance.gate import evaluate

        return evaluate(self.conf, ["android"], parity=True)

    def test_missing_codegen_artifacts_fail_when_parity_requested(self):
        outcome = self._evaluate()
        self.assertFalse(outcome.ok)
        self.assertTrue(any("parity not measured" in p for p in outcome.problems))

    def test_unrecorded_drift_fails_and_ledgered_drift_passes(self):
        cg = self.conf / "artifacts" / "android-codegen"
        _write_png(cg / self.shot, box=(120, 100, 240, 180))

        outcome = self._evaluate()
        self.assertFalse(outcome.ok)
        self.assertTrue(any("codegen-parity deviation" in p for p in outcome.problems))

        result = parity.measure(self.conf, "android")
        path = parity.ledger_path(self.conf)
        path.write_text(
            parity.render_ledger(parity.update_ledger({}, result)), encoding="utf-8"
        )
        outcome = self._evaluate()
        self.assertTrue(outcome.ok)
        self.assertTrue(any("codegen parity OK" in n for n in outcome.notices))

    def test_web_is_out_of_parity_scope(self):
        # Web's host already renders through the rjui codegen — parity would
        # compare a pipeline to itself, so the gate must not demand
        # artifacts/web-codegen.
        from jui_cli.conformance.gate import evaluate

        try:
            from .test_conformance_report import _write_results
        except ImportError:
            from test_conformance_report import _write_results
        import json as _json

        manifest = _json.loads((self.conf / "manifest.json").read_text(encoding="utf-8"))
        ids = [f["id"] for f in manifest["fixtures"]]
        _write_results(self.conf, "web", {fixture_id: "pass" for fixture_id in ids})
        dyn = self.conf / "artifacts" / "web"
        _write_png(dyn / self.shot)
        baseline.update_baseline(self.conf, "web")
        (self.conf / "gate_ratchet.json").write_text(
            _json.dumps({"missing_artifact": {"web": 1, "android": 1}}), encoding="utf-8"
        )
        cg = self.conf / "artifacts" / "android-codegen"
        _write_png(cg / self.shot)
        outcome = evaluate(self.conf, ["web", "android"], parity=True)
        self.assertTrue(outcome.ok, outcome.problems)

    def test_matching_codegen_render_passes_clean(self):
        cg = self.conf / "artifacts" / "android-codegen"
        _write_png(cg / self.shot)
        outcome = self._evaluate()
        self.assertTrue(outcome.ok)
        self.assertTrue(any("codegen parity OK" in n for n in outcome.notices))


if __name__ == "__main__":
    unittest.main()
