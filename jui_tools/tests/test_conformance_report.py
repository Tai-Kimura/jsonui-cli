"""Tests for `jui conformance report` (results merge + REPORT.md).

Covers plan-01 acceptance criterion 4: a REPORT.md is generated from
hand-written dummy results for two platforms, the cross-platform mismatch
table works, and stale results are flagged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.conformance.fixture_generator import generate_conformance
from jui_cli.conformance.report import ReportError, generate_report

try:
    # pytest collects tests as a package (relative import works)…
    from .test_conformance_generator import SYNTHETIC_DEFS, _write_defs
except ImportError:
    # …while CI runs `python -m unittest discover -s tests`, which loads
    # test modules top-level with no parent package.
    from test_conformance_generator import SYNTHETIC_DEFS, _write_defs


def _manifest_hash(out_dir: Path) -> str:
    return hashlib.sha256((out_dir / "manifest.json").read_bytes()).hexdigest()


def _write_results(
    out_dir: Path,
    platform: str,
    statuses: dict[str, str],
    *,
    manifest_hash: str | None = None,
    details: dict[str, str] | None = None,
) -> Path:
    payload = {
        "platform": platform,
        "manifestHash": manifest_hash if manifest_hash is not None else _manifest_hash(out_dir),
        "runner": {"name": f"dummy-{platform}", "version": "0.0.1"},
        "results": [
            {
                "id": fixture_id,
                "status": status,
                "detail": (details or {}).get(fixture_id, ""),
                "screenshot": None,
            }
            for fixture_id, status in statuses.items()
        ],
    }
    results_dir = out_dir / "results"
    results_dir.mkdir(exist_ok=True)
    path = results_dir / f"{platform}.results.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


class ConformanceReportTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        defs_path = _write_defs(tmp, SYNTHETIC_DEFS)
        self.out_dir = tmp / "conformance"
        generate_conformance(defs_path, self.out_dir)
        self.manifest = json.loads((self.out_dir / "manifest.json").read_text(encoding="utf-8"))
        self.all_ids = [f["id"] for f in self.manifest["fixtures"]]

    def tearDown(self):
        self._tmp.cleanup()

    def _report(self) -> str:
        summary = generate_report(self.out_dir)
        return (self.out_dir / "REPORT.md").read_text(encoding="utf-8"), summary

    def test_mismatch_table_lists_diverging_fixtures_first(self):
        base = {fixture_id: "pass" for fixture_id in self.all_ids}
        _write_results(self.out_dir, "web", base)
        android = dict(base)
        android["Label/text__static"] = "fail"
        android["common/hidden__true"] = "error"
        _write_results(
            self.out_dir,
            "android",
            android,
            details={"Label/text__static": "expected 'Conformance Text', got ''"},
        )

        content, summary = self._report()
        self.assertEqual(summary.mismatch_count, 2)
        mismatch_section = content.split("## Platforms")[0]
        self.assertIn("`Label/text__static`", mismatch_section)
        self.assertIn("`common/hidden__true`", mismatch_section)
        self.assertIn("expected 'Conformance Text', got ''", mismatch_section)
        # Mismatch section comes before the full matrix.
        self.assertLess(content.index("## Cross-platform mismatches"), content.index("## Matrix"))

    def test_identical_results_produce_no_mismatches(self):
        statuses = {fixture_id: "pass" for fixture_id in self.all_ids}
        _write_results(self.out_dir, "web", statuses)
        _write_results(self.out_dir, "android", statuses)
        content, summary = self._report()
        self.assertEqual(summary.mismatch_count, 0)
        self.assertIn("_No cross-platform mismatches._", content)

    def test_skipped_results_do_not_count_as_mismatch(self):
        statuses = {fixture_id: "pass" for fixture_id in self.all_ids}
        _write_results(self.out_dir, "web", statuses)
        android = dict(statuses)
        android["Label/text__static"] = "skipped"
        _write_results(self.out_dir, "android", android)
        _, summary = self._report()
        self.assertEqual(summary.mismatch_count, 0)

    def test_stale_results_are_flagged(self):
        _write_results(self.out_dir, "web", {self.all_ids[0]: "pass"})
        _write_results(
            self.out_dir,
            "ios",
            {self.all_ids[0]: "pass"},
            manifest_hash="0" * 64,
        )
        content, summary = self._report()
        self.assertEqual(summary.stale_platforms, ["ios"])
        self.assertIn("STALE", content)
        self.assertIn("ios.results.json", content)

    def test_unknown_fixture_ids_are_reported(self):
        _write_results(
            self.out_dir, "web", {self.all_ids[0]: "pass", "Nope/ghost__static": "pass"}
        )
        content, summary = self._report()
        self.assertEqual(summary.unknown_ids.get("web"), ["Nope/ghost__static"])
        self.assertIn("Nope/ghost__static", content)

    def test_matrix_and_skipped_sections_render(self):
        _write_results(self.out_dir, "web", {fid: "pass" for fid in self.all_ids})
        content, _ = self._report()
        self.assertIn("## Matrix", content)
        self.assertIn("### Label", content)
        self.assertIn("## Skipped attributes", content)
        self.assertIn("`onclick`", content)
        self.assertIn("callback", content)
        # @generated marker on the report itself.
        self.assertTrue(content.startswith("<!-- @generated"))

    def test_report_without_results_still_renders(self):
        content, summary = self._report()
        self.assertEqual(summary.platforms, [])
        self.assertIn("No platform results loaded", content)

    def test_report_is_deterministic(self):
        _write_results(self.out_dir, "web", {fid: "pass" for fid in self.all_ids})
        first, _ = self._report()
        second, _ = self._report()
        self.assertEqual(first, second)

    def test_missing_manifest_raises(self):
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(ReportError):
                generate_report(Path(empty))

    def test_cmd_report_returns_zero(self):
        from jui_cli.commands.conformance_cmd import cmd_conformance

        _write_results(self.out_dir, "web", {fid: "pass" for fid in self.all_ids})
        args = argparse.Namespace(
            conformance_target="report",
            conformance_dir=str(self.out_dir),
            results=None,
            out=None,
        )
        self.assertEqual(cmd_conformance(args), 0)
        self.assertTrue((self.out_dir / "REPORT.md").is_file())


class InteractiveSectionTest(unittest.TestCase):
    """v2: the report surfaces interactive fixtures + promotion accounting."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        defs_path = _write_defs(tmp, SYNTHETIC_DEFS)
        self.out_dir = tmp / "conformance"
        generate_conformance(defs_path, self.out_dir)
        self.manifest = json.loads((self.out_dir / "manifest.json").read_text(encoding="utf-8"))
        self.all_ids = [f["id"] for f in self.manifest["fixtures"]]

    def tearDown(self):
        self._tmp.cleanup()

    def test_interactive_section_shows_promotions_and_statuses(self):
        statuses = {fid: "pass" for fid in self.all_ids}
        statuses["common/onclick__callback_fire"] = "fail"
        _write_results(
            self.out_dir,
            "web",
            statuses,
            details={"common/onclick__callback_fire": "mirror stayed 'ready'"},
        )
        generate_report(self.out_dir)
        content = (self.out_dir / "REPORT.md").read_text(encoding="utf-8")

        self.assertIn("## Interactive fixtures", content)
        section = content.split("## Interactive fixtures")[1].split("## ")[0]
        # promoted accounting: 1 promoted out of `callback`, the
        # non-promotable callback (Label/onTextChange) still counted as skipped.
        self.assertIn("callback: 1", section)
        self.assertIn("still skipped", section)
        self.assertIn("`common/onclick__callback_fire`", section)
        self.assertIn("mirror stayed 'ready'", section)
        self.assertIn("❌", section)
        # non-promoted interactive fixtures render with an em-dash origin
        self.assertIn("`Label/text__binding_initial`", section)

    def test_interactive_section_precedes_platforms(self):
        _write_results(self.out_dir, "web", {fid: "pass" for fid in self.all_ids})
        generate_report(self.out_dir)
        content = (self.out_dir / "REPORT.md").read_text(encoding="utf-8")
        self.assertLess(
            content.index("## Interactive fixtures"), content.index("## Platforms")
        )


class VisualRegressionSectionTest(unittest.TestCase):
    """v2: baseline comparison surfaces in the report (regression + no-baseline)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        defs_path = _write_defs(tmp, SYNTHETIC_DEFS)
        self.out_dir = tmp / "conformance"
        generate_conformance(defs_path, self.out_dir)
        self.manifest = json.loads((self.out_dir / "manifest.json").read_text(encoding="utf-8"))
        self.all_ids = [f["id"] for f in self.manifest["fixtures"]]

    def tearDown(self):
        self._tmp.cleanup()

    def _write_results_with_screenshots(self, screenshots: dict[str, str]) -> None:
        payload = {
            "platform": "web",
            "manifestHash": _manifest_hash(self.out_dir),
            "runner": {"name": "dummy-web", "version": "0.0.1"},
            "results": [
                {"id": fid, "status": "pass", "detail": ""}
                | ({"screenshot": screenshots[fid]} if fid in screenshots else {})
                for fid in self.all_ids
            ],
        }
        results_dir = self.out_dir / "results"
        results_dir.mkdir(exist_ok=True)
        (results_dir / "web.results.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )

    def test_no_baseline_recorded_is_reported_not_silent(self):
        self._write_results_with_screenshots(
            {self.all_ids[0]: "artifacts/web/shot_one.png"}
        )
        summary = generate_report(self.out_dir)
        content = (self.out_dir / "REPORT.md").read_text(encoding="utf-8")
        self.assertIn("## Visual regression", content)
        self.assertIn("none recorded", content)
        self.assertEqual(summary.no_baseline.get("web"), 1)
        self.assertEqual(summary.visual_regressions.get("web"), 0)

    def test_regression_detected_end_to_end(self):
        try:
            from test_conformance_baseline import HAVE_PILLOW, _write_png
        except ImportError:
            from .test_conformance_baseline import HAVE_PILLOW, _write_png
        if not HAVE_PILLOW:
            self.skipTest("Pillow not installed (jui-tools[conformance])")

        from jui_cli.conformance import baseline

        artifacts = self.out_dir / "artifacts" / "web"
        _write_png(artifacts / "stable.png")
        _write_png(artifacts / "changed.png", gradient_horizontal=False)
        baseline.update_baseline(self.out_dir, "web")

        # deliberate visual change + one screenshot that has no baseline
        _write_png(artifacts / "changed.png", gradient_horizontal=True)
        _write_png(artifacts / "brand_new.png")
        self._write_results_with_screenshots(
            {
                self.all_ids[0]: "artifacts/web/stable.png",
                self.all_ids[1]: "artifacts/web/changed.png",
                self.all_ids[2]: "artifacts/web/brand_new.png",
            }
        )

        summary = generate_report(self.out_dir)
        content = (self.out_dir / "REPORT.md").read_text(encoding="utf-8")
        self.assertEqual(summary.visual_regressions.get("web"), 1)
        self.assertEqual(summary.no_baseline.get("web"), 1)
        self.assertIn("### web: regressions", content)
        self.assertIn("`changed.png`", content)
        self.assertIn("`brand_new.png`", content)
        self.assertIn("NOT a pass", content)

        # revert the deliberate change -> clean report again
        _write_png(artifacts / "changed.png", gradient_horizontal=False)
        self._write_results_with_screenshots(
            {
                self.all_ids[0]: "artifacts/web/stable.png",
                self.all_ids[1]: "artifacts/web/changed.png",
            }
        )
        summary = generate_report(self.out_dir)
        self.assertEqual(summary.visual_regressions.get("web"), 0)

    def test_a_comparison_that_could_not_run_is_surfaced_not_counted_as_clean(self):
        # The gate reads visual_regressions; when Pillow is missing every
        # comparison is skipped and that dict is all zeros, so the gate
        # reported a clean run for a check that never executed. Both mobile
        # baselines drifted wholesale under that silence.
        from jui_cli.conformance import baseline

        artifacts = self.out_dir / "artifacts" / "web"
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / "shot_one.png").write_bytes(b"not really a png")
        self._write_results_with_screenshots(
            {self.all_ids[0]: "artifacts/web/shot_one.png"}
        )

        original = baseline.compare_platform

        def _unavailable(*args, **kwargs):
            comparison = baseline.VisualComparison(platform="web")
            comparison.error = "Pillow is required for screenshot baselines"
            return comparison

        baseline.compare_platform = _unavailable
        try:
            summary = generate_report(self.out_dir)
        finally:
            baseline.compare_platform = original

        self.assertIn("web", summary.baseline_errors)
        self.assertIn("Pillow", summary.baseline_errors["web"])
        self.assertEqual(summary.visual_regressions.get("web"), 0)

    def test_a_stale_hash_algorithm_is_surfaced_the_same_way(self):
        from jui_cli.conformance import baseline

        artifacts = self.out_dir / "artifacts" / "web"
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / "shot_one.png").write_bytes(b"not really a png")
        baseline.baseline_path(self.out_dir, "web").parent.mkdir(
            parents=True, exist_ok=True
        )
        baseline.baseline_path(self.out_dir, "web").write_text(
            json.dumps({"algorithm": "dhash-16", "threshold": 8, "hashes": {}}),
            encoding="utf-8",
        )
        self._write_results_with_screenshots(
            {self.all_ids[0]: "artifacts/web/shot_one.png"}
        )
        summary = generate_report(self.out_dir)
        self.assertIn("web", summary.baseline_errors)
        self.assertIn("dhash-16", summary.baseline_errors["web"])


class CommittedDummyResultsTest(unittest.TestCase):
    """The hand-written dummy results under tests/fixtures/ obey the contract."""

    FIXTURES_DIR = Path(__file__).parent / "fixtures" / "conformance"

    def test_dummy_results_conform_to_results_schema(self):
        paths = sorted(self.FIXTURES_DIR.glob("*.results.json"))
        self.assertGreaterEqual(len(paths), 2, "expected two dummy platform results")
        for path in paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["platform"], path.name[: -len(".results.json")])
            self.assertIn("manifestHash", payload)
            self.assertIn("name", payload["runner"])
            for entry in payload["results"]:
                self.assertIn("id", entry)
                self.assertIn(entry["status"], {"pass", "fail", "error", "skipped"})


if __name__ == "__main__":
    unittest.main()
