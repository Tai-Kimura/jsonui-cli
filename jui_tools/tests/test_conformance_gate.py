"""Tests for ``jui conformance gate`` (plan 06 §2/§3).

The judgment that used to live as duplicated Python heredocs in ``ci.yml``
and ``conformance-mobile.yml`` is now :func:`jui_cli.conformance.gate.judge`.
These tests pin its contract: what fails, what is a notice, how the
``missing_artifact`` / ``no_baseline`` ratchets behave at their boundaries,
and that judgment is scoped to the selected platforms only.

``judge`` is pure (summary in, outcome out), so the visual checks are tested
without Pillow or image files — CI's python-suite job installs jui_tools
without the ``[conformance]`` extra. The end-to-end tests go through
:func:`evaluate` with ``visual=False`` for the same reason; the visual path
end-to-end is exercised against the repo's real committed results by the
local/CI gate runs themselves.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.conformance.fixture_generator import generate_conformance
from jui_cli.conformance.gate import (
    RATCHET_FILENAME,
    evaluate,
    judge,
    load_ratchet,
    ratchet_for_env,
)
from jui_cli.conformance.report import ReportError, ReportSummary

try:
    # pytest collects tests as a package (relative import works)…
    from .test_conformance_generator import SYNTHETIC_DEFS, _write_defs
    from .test_conformance_report import _write_results
except ImportError:
    # …while CI runs `python -m unittest discover -s tests`, which loads
    # test modules top-level with no parent package.
    from test_conformance_generator import SYNTHETIC_DEFS, _write_defs
    from test_conformance_report import _write_results

ALL = ["android", "ios", "web"]


def _summary(**overrides) -> ReportSummary:
    """An all-green three-platform summary; override fields per test."""
    summary = ReportSummary(out_path=Path("REPORT.md"), platforms=list(ALL))
    summary.status_tallies = {
        p: {"pass": 10, "fail": 0, "error": 0, "skipped": 1} for p in ALL
    }
    for name, value in overrides.items():
        setattr(summary, name, value)
    return summary


class JudgeResultChecksTest(unittest.TestCase):
    def test_all_green_passes(self):
        outcome = judge(_summary(), ALL)
        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.problems, [])
        self.assertEqual(outcome.notices, [])

    def test_fail_and_error_results_fail(self):
        summary = _summary()
        summary.status_tallies["ios"] = {"pass": 8, "fail": 1, "error": 1, "skipped": 1}
        outcome = judge(summary, ALL)
        self.assertFalse(outcome.ok)
        self.assertTrue(any("ios: 2 fail/error" in p for p in outcome.problems))

    def test_missing_platform_results_fail(self):
        summary = _summary(platforms=["web"])
        outcome = judge(summary, ["ios", "web"])
        self.assertFalse(outcome.ok)
        self.assertTrue(any("missing platform results: ios" in p for p in outcome.problems))

    def test_stale_results_fail_only_when_selected(self):
        summary = _summary(stale_platforms=["ios"])
        self.assertTrue(judge(summary, ["web"]).ok)
        outcome = judge(summary, ["ios"])
        self.assertFalse(outcome.ok)
        self.assertTrue(any("stale" in p for p in outcome.problems))

    def test_unknown_fixture_ids_fail(self):
        summary = _summary(unknown_ids={"web": ["Nope/ghost__static"]})
        outcome = judge(summary, ["web"])
        self.assertFalse(outcome.ok)
        self.assertTrue(any("not in manifest" in p for p in outcome.problems))

    def test_mismatch_fails_only_with_all_three_platforms(self):
        summary = _summary(mismatch_count=3)
        # Partial selection: the other platforms' results are committed
        # snapshots, not this run's — mismatch is the full lane's business.
        self.assertTrue(judge(summary, ["web"]).ok)
        self.assertTrue(judge(summary, ["ios", "web"]).ok)
        outcome = judge(summary, ALL)
        self.assertFalse(outcome.ok)
        self.assertTrue(any("3 cross-platform mismatch(es)" in p for p in outcome.problems))


class JudgeVisualChecksTest(unittest.TestCase):
    def test_visual_regression_fails(self):
        summary = _summary(visual_regressions={"android": 2})
        outcome = judge(summary, ALL)
        self.assertFalse(outcome.ok)
        self.assertTrue(any("android: 2 visual regression(s)" in p for p in outcome.problems))

    def test_uncompared_screenshots_fail(self):
        summary = _summary(baseline_errors={"ios": "Pillow is not installed"})
        outcome = judge(summary, ALL)
        self.assertFalse(outcome.ok)
        self.assertTrue(
            any("ios: screenshots were not compared" in p for p in outcome.problems)
        )

    def test_inert_regression_fails_and_unrecorded_is_a_notice(self):
        summary = _summary(
            inert_regressions={"web": ["Label/text__static"]},
            inert_unrecorded={"android": 4},
        )
        outcome = judge(summary, ALL)
        self.assertFalse(outcome.ok)
        self.assertTrue(any("no longer change what is rendered" in p for p in outcome.problems))
        self.assertTrue(any("not yet recorded in control_diff.json" in n for n in outcome.notices))
        # The notice alone must not fail the gate.
        alone = judge(_summary(inert_unrecorded={"android": 4}), ALL)
        self.assertTrue(alone.ok)
        self.assertEqual(len(alone.notices), 1)

    def test_no_visual_skips_every_visual_check(self):
        summary = _summary(
            baseline_errors={"ios": "Pillow is not installed"},
            visual_regressions={"android": 5},
            inert_regressions={"web": ["Label/text__static"]},
            inert_unrecorded={"web": 9},
            missing_artifact={"web": 99},
            no_baseline={"web": 99},
        )
        outcome = judge(summary, ALL, visual=False)
        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.notices, [])

    def test_visual_checks_scope_to_selected_platforms(self):
        summary = _summary(
            visual_regressions={"android": 5},
            baseline_errors={"ios": "Pillow is not installed"},
        )
        self.assertTrue(judge(summary, ["web"]).ok)


class JudgeRatchetTest(unittest.TestCase):
    RATCHET = {"missing_artifact": {"android": 12}, "no_baseline": {"android": 0}}

    def test_count_at_ceiling_passes_silently(self):
        summary = _summary(missing_artifact={"android": 12})
        outcome = judge(summary, ["android"], ratchet=self.RATCHET)
        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.notices, [])

    def test_count_above_ceiling_fails(self):
        summary = _summary(missing_artifact={"android": 13})
        outcome = judge(summary, ["android"], ratchet=self.RATCHET)
        self.assertFalse(outcome.ok)
        self.assertTrue(
            any("android: missing_artifact 13 > ratchet ceiling 12" in p for p in outcome.problems)
        )

    def test_count_below_ceiling_passes_with_tighten_notice(self):
        summary = _summary(missing_artifact={"android": 9})
        outcome = judge(summary, ["android"], ratchet=self.RATCHET)
        self.assertTrue(outcome.ok)
        self.assertTrue(any(RATCHET_FILENAME in n and "tighten" in n for n in outcome.notices))

    def test_unlisted_platform_defaults_to_zero_ceiling(self):
        summary = _summary(no_baseline={"web": 1})
        outcome = judge(summary, ["web"], ratchet=self.RATCHET)
        self.assertFalse(outcome.ok)
        self.assertTrue(any("web: no_baseline 1 > ratchet ceiling 0" in p for p in outcome.problems))

    def test_uncompared_platform_is_not_ratcheted(self):
        # The comparison never ran — that is already a problem; a ratchet
        # verdict on unmeasured counts would just be noise on top.
        summary = _summary(
            baseline_errors={"ios": "Pillow is not installed"},
            missing_artifact={"ios": 99},
        )
        outcome = judge(summary, ["ios"], ratchet={"missing_artifact": {"ios": 0}})
        self.assertFalse(outcome.ok)
        self.assertEqual(len(outcome.problems), 1)
        self.assertIn("screenshots were not compared", outcome.problems[0])


class LoadRatchetTest(unittest.TestCase):
    def test_missing_file_means_zero_ceilings(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(load_ratchet(Path(d)), {})

    def test_reads_metrics_and_drops_junk_values(self):
        # Junk-value filtering happens at env resolution (ratchet_for_env),
        # which is the only path the gate consumes ceilings through.
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / RATCHET_FILENAME
            path.write_text(
                json.dumps(
                    {
                        "_comment": ["ignored"],
                        "missing_artifact": {"android": 12, "ios": "many", "web": True},
                        "no_baseline": {"web": 0},
                        "unknown_metric": {"android": 5},
                    }
                )
            )
            ratchet = ratchet_for_env(load_ratchet(Path(d)), "local")
            self.assertEqual(ratchet["missing_artifact"], {"android": 12})
            self.assertEqual(ratchet["no_baseline"], {"web": 0})
            self.assertNotIn("unknown_metric", ratchet)


class RatchetForEnvTest(unittest.TestCase):
    def test_flat_table_is_the_local_env(self):
        flat = {"missing_artifact": {"android": 12}}
        self.assertEqual(
            ratchet_for_env(flat, "local")["missing_artifact"], {"android": 12}
        )
        # Any other env gets no slack from a table measured on local renders.
        self.assertEqual(ratchet_for_env(flat, "ci").get("missing_artifact", {}), {})

    def test_nested_table_resolves_per_env_and_unknown_env_is_strict(self):
        nested = {
            "missing_artifact": {"local": {"android": 12}, "ci": {"android": 0}}
        }
        self.assertEqual(
            ratchet_for_env(nested, "local")["missing_artifact"], {"android": 12}
        )
        self.assertEqual(
            ratchet_for_env(nested, "ci")["missing_artifact"], {"android": 0}
        )
        self.assertEqual(
            ratchet_for_env(nested, "staging").get("missing_artifact", {}), {}
        )


class JudgeEnvTest(unittest.TestCase):
    def test_inert_regression_is_a_notice_outside_local(self):
        summary = _summary(
            inert_regressions={"ios": ["SelectBox/selectedValue__static"]}
        )
        local = judge(summary, ALL)
        self.assertFalse(local.ok)
        ci = judge(summary, ALL, env="ci")
        self.assertTrue(ci.ok)
        self.assertTrue(any("informational under env 'ci'" in n for n in ci.notices))

    def test_visual_regression_fails_under_any_env_and_names_the_env(self):
        summary = _summary(visual_regressions={"android": 2})
        outcome = judge(summary, ALL, env="ci")
        self.assertFalse(outcome.ok)
        self.assertTrue(
            any(
                "--env ci" in p and "baselines/ci/android.hashes.json" in p
                for p in outcome.problems
            )
        )

    def test_nested_ratchet_is_resolved_with_the_judged_env(self):
        nested = {
            "missing_artifact": {"local": {"android": 12}, "ci": {"android": 0}},
            "no_baseline": {"local": {"android": 0}, "ci": {"android": 0}},
        }
        at_local_ceiling = _summary(missing_artifact={"android": 12})
        self.assertTrue(judge(at_local_ceiling, ["android"], ratchet=nested).ok)
        over_ci_ceiling = judge(
            at_local_ceiling, ["android"], ratchet=nested, env="ci"
        )
        self.assertFalse(over_ci_ceiling.ok)
        self.assertTrue(
            any("missing_artifact 12 > ratchet ceiling 0" in p for p in over_ci_ceiling.problems)
        )


class EvaluateEndToEndTest(unittest.TestCase):
    """`evaluate` against a synthetic conformance dir (visual=False — no Pillow)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        defs_path = _write_defs(tmp, SYNTHETIC_DEFS)
        self.out_dir = tmp / "conformance"
        generate_conformance(defs_path, self.out_dir)
        manifest = json.loads((self.out_dir / "manifest.json").read_text(encoding="utf-8"))
        self.all_ids = [f["id"] for f in manifest["fixtures"]]

    def tearDown(self):
        self._tmp.cleanup()

    def test_green_results_pass_and_write_report(self):
        statuses = {fixture_id: "pass" for fixture_id in self.all_ids}
        _write_results(self.out_dir, "web", statuses)
        outcome = evaluate(self.out_dir, ["web"], visual=False)
        self.assertTrue(outcome.ok)
        self.assertTrue((self.out_dir / "REPORT.md").is_file())
        self.assertEqual(
            outcome.summary.status_tallies["web"]["pass"], len(self.all_ids)
        )

    def test_failing_results_fail_the_gate(self):
        statuses = {fixture_id: "pass" for fixture_id in self.all_ids}
        statuses[self.all_ids[0]] = "fail"
        statuses[self.all_ids[1]] = "error"
        _write_results(self.out_dir, "web", statuses)
        outcome = evaluate(self.out_dir, ["web"], visual=False)
        self.assertFalse(outcome.ok)
        self.assertTrue(any("web: 2 fail/error" in p for p in outcome.problems))

    def test_stale_results_fail_the_gate(self):
        _write_results(
            self.out_dir,
            "web",
            {self.all_ids[0]: "pass"},
            manifest_hash="0" * 64,
        )
        outcome = evaluate(self.out_dir, ["web"], visual=False)
        self.assertFalse(outcome.ok)
        self.assertTrue(any("stale" in p for p in outcome.problems))

    def test_missing_manifest_raises_report_error(self):
        with self.assertRaises(ReportError):
            evaluate(Path(self._tmp.name) / "nowhere", ["web"], visual=False)

    def test_ratchet_file_is_loaded_by_default(self):
        # visual=True would need Pillow only when screenshots exist; dummy
        # results carry none, so the visual path is exercised structurally:
        # the committed-style ratchet file loads and the judgment runs.
        statuses = {fixture_id: "pass" for fixture_id in self.all_ids}
        _write_results(self.out_dir, "web", statuses)
        (self.out_dir / RATCHET_FILENAME).write_text(
            json.dumps({"missing_artifact": {"web": 0}, "no_baseline": {"web": 0}})
        )
        outcome = evaluate(self.out_dir, ["web"])
        self.assertTrue(outcome.ok)


if __name__ == "__main__":
    unittest.main()
