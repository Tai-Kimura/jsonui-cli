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

from jui_cli.conformance import gate
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
    # …while `python -m unittest discover -s tests` loads test modules
    # top-level with no parent package. CI runs pytest since 1.7.0, so this
    # branch is now for the runs people type by hand — still real, so the
    # fallback stays.
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


class JudgeInertCompleteTest(unittest.TestCase):
    """Gate wiring for the completeness ratchet (plan 34 Phase 3).

    The decision logic lives in inert_audit.check_ledger and is covered
    there; what matters here is that a lane which cannot measure says so
    instead of passing.
    """

    def test_a_missing_manifest_is_a_problem_not_a_pass(self):
        from jui_cli.conformance.gate import judge_inert_complete

        with tempfile.TemporaryDirectory() as tmp:
            problems, notices = judge_inert_complete(Path(tmp), ["ios", "web"])
        self.assertEqual(len(problems), 1)
        self.assertIn("manifest not found", problems[0])
        self.assertEqual(notices, [])

    def test_no_results_reports_completeness_rather_than_silence(self):
        from jui_cli.conformance.gate import judge_inert_complete

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "manifest.json").write_text(json.dumps({"fixtures": []}))
            problems, notices = judge_inert_complete(root, ["ios", "web"])
        self.assertEqual(problems, [])
        self.assertTrue(any("inert completeness OK" in n for n in notices))

    # ------------------------------------------------------------------ #
    # Zero-denominator holes (the wave's homework): an audit whose
    # denominator shrinks must say so, and one whose denominator is zero
    # while the manifest holds work must fail. "0 unattributed, all on the
    # ledger" from an empty measurement is the exact silence this exists
    # to forbid.
    # ------------------------------------------------------------------ #

    @staticmethod
    def _manifest_with_scope(root: Path) -> None:
        (root / "manifest.json").write_text(
            json.dumps(
                {
                    "fixtures": [
                        {
                            "id": "Label/text__static",
                            "platforms": ["ios", "web"],
                            "control": "__control/Label",
                        },
                        {
                            "id": "__control/Label",
                            "platforms": ["ios", "web"],
                            "isControl": True,
                        },
                    ]
                }
            )
        )

    @staticmethod
    def _write_results(root: Path, platform: str, results: list[dict]) -> None:
        import hashlib

        manifest_hash = hashlib.sha256(
            (root / "manifest.json").read_bytes()
        ).hexdigest()
        results_dir = root / "results"
        results_dir.mkdir(exist_ok=True)
        (results_dir / f"{platform}.results.json").write_text(
            json.dumps(
                {
                    "platform": platform,
                    "manifestHash": manifest_hash,
                    "results": results,
                }
            )
        )

    def test_fixtures_in_scope_with_no_results_measured_nothing(self):
        from jui_cli.conformance.gate import judge_inert_complete

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._manifest_with_scope(root)
            problems, notices = judge_inert_complete(root, ["ios", "web"])
        self.assertTrue(
            any("measured NOTHING" in p for p in problems), problems
        )
        self.assertFalse(any("inert completeness OK" in n for n in notices))

    def test_a_platform_that_left_the_denominator_is_said_out_loud(self):
        from jui_cli.conformance.gate import judge_inert_complete

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._manifest_with_scope(root)
            self._write_results(
                root,
                "web",
                [{"id": "Label/text__static", "status": "pass", "screenshot": None}],
            )
            problems, notices = judge_inert_complete(root, ["ios", "web"])
        self.assertFalse(any("measured NOTHING" in p for p in problems))
        self.assertTrue(
            any("no results for ios" in n for n in notices), notices
        )

    def test_a_fixture_without_its_control_is_an_exclusion_not_a_pass(self):
        from jui_cli.conformance.gate import judge_inert_complete

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._manifest_with_scope(root)
            self._write_results(
                root,
                "web",
                [
                    {
                        "id": "Label/text__static",
                        "status": "pass",
                        "screenshot": "artifacts/web/Label_text__static.png",
                    }
                ],
            )
            problems, notices = judge_inert_complete(root, ["web", "ios"])
        self.assertTrue(
            any("excluded from the completeness audit" in n for n in notices),
            notices,
        )


if __name__ == "__main__":
    unittest.main()


class LedgerKeyTest(unittest.TestCase):
    """A ledger key has to name a fixture the manifest still has.

    Three renames in one wave broke three separate things this way — the
    committed baselines, a control shape, and a semantics contract whose
    member pointed at a fixture whose representative value had been
    flipped. That contract sat on the ledger with the gate running and had
    not been checked once since the rename.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conf = Path(self._tmp.name)
        (self.conf / "manifest.json").write_text(
            json.dumps(
                {
                    "fixtures": [
                        {"id": "Label/text__static"},
                        {"id": "__control/TabView"},
                    ]
                }
            )
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, name, entries):
        (self.conf / name).write_text(json.dumps({"entries": entries}))

    def test_live_keys_pass(self):
        self._write("control_diff.json", [{"fixture": "Label/text__static"}])
        self._write("codegen_parity.json", [{"screenshot": "Label_text__static.png"}])
        self.assertEqual(gate.judge_ledger_keys(self.conf), [])

    def test_a_renamed_fixture_leaves_a_dangling_row(self):
        self._write("control_diff.json", [{"fixture": "Label/text__flipped"}])
        problems = gate.judge_ledger_keys(self.conf)
        self.assertEqual(len(problems), 1)
        self.assertIn("Label/text__flipped", problems[0])

    def test_screenshot_keys_are_matched_in_their_own_shape(self):
        self._write("codegen_parity.json", [{"screenshot": "Label_text__gone.png"}])
        problems = gate.judge_ledger_keys(self.conf)
        self.assertEqual(len(problems), 1)
        self.assertIn("Label_text__gone.png", problems[0])

    def test_a_control_row_is_matched_under_the_name_the_runners_write(self):
        # `__control/TabView` is written `control_TabView.png` by all three
        # runners — 166 such files across the committed ci baselines, and no
        # `__control_*.png` anywhere. Deriving the id verbatim made every
        # control row permanently dangling, so a PERMANENT accepted deviation
        # read as stale and "cleanup" would have un-accepted a user ruling.
        self.assertEqual(gate.screenshot_name("__control/TabView"), "control_TabView.png")
        self._write("codegen_parity.json", [{"screenshot": "control_TabView.png"}])
        self.assertEqual(gate.judge_ledger_keys(self.conf), [])

    def test_a_control_row_can_still_go_stale(self):
        self._write("codegen_parity.json", [{"screenshot": "control_Gone.png"}])
        problems = gate.judge_ledger_keys(self.conf)
        self.assertEqual(len(problems), 1)
        self.assertIn("control_Gone.png", problems[0])

    def test_a_contract_pointing_at_a_renamed_fixture_is_caught(self):
        semantics = self.conf / "attribute_semantics.json"
        semantics.write_text(
            json.dumps(
                {"semantics": {"skin": {"observable": {"TabView/showLabels__true": "x"}}}}
            )
        )
        problems = gate.judge_ledger_keys(self.conf, semantics)
        self.assertEqual(len(problems), 1)
        self.assertIn("skin:TabView/showLabels__true", problems[0])

    def test_reports_without_deleting(self):
        """Whoever renamed the fixture knows what the row was for.

        A device that quietly drops it destroys the only record that
        something was being tracked.
        """
        self._write("control_diff.json", [{"fixture": "Label/text__flipped"}])
        before = (self.conf / "control_diff.json").read_text()
        gate.judge_ledger_keys(self.conf)
        self.assertEqual((self.conf / "control_diff.json").read_text(), before)

    def test_missing_manifest_is_a_problem_not_a_pass(self):
        (self.conf / "manifest.json").unlink()
        self.assertEqual(len(gate.judge_ledger_keys(self.conf)), 1)


class LedgerKeyFlagBecomesDefaultTest(unittest.TestCase):
    """The flag is temporary, and this is what stops it from being forever.

    `--ledger-keys` is opt-in only because 31 rows were already dangling
    when the check landed, and turning it on would have reddened every
    other lane's gate for someone else's rename. The moment those are gone
    the reason is gone with them — and a check nobody passes the flag for
    is a check that does not run, which is the exact failure plan 50 found
    in a script the dev-guide swore was enforcing something.

    So this test fails as soon as the backlog clears: not a reminder in a
    document, which is the form that failed before.
    """

    REPO = Path(__file__).resolve().parents[2]

    @unittest.skipUnless((REPO / "conformance" / "manifest.json").is_file(),
                         "not a repo checkout")
    def test_flag_flips_to_default_once_the_backlog_is_clear(self):
        import inspect

        problems = gate.judge_ledger_keys(
            self.REPO / "conformance",
            self.REPO / "shared" / "core" / "attribute_semantics.json",
        )
        default_on = (
            inspect.signature(gate.evaluate).parameters["ledger_keys"].default is True
        )
        if problems:
            self.assertFalse(
                default_on,
                "dangling ledger rows remain; turning the check on by default now "
                "would fail every lane's gate for someone else's rename",
            )
            return
        self.assertTrue(
            default_on,
            "no ledger row is dangling any more, so --ledger-keys has nothing left "
            "to protect other lanes from: make it the default (evaluate(..., "
            "ledger_keys: bool = True)) and drop the flag from the workflows, or "
            "it becomes a check that only runs when someone remembers to ask",
        )


class InertAuditCountsTest(unittest.TestCase):
    """`counts` is derived from `entries`, so it must agree with them.

    The generator computes both from the same list and cannot disagree; a
    hand edit to `entries` can, and did — 77 entries carried counts of
    78/84. Anyone reading `counts` to decide something reads a number
    nobody re-derived, which is the shape this whole plan keeps finding: a
    summary that outlived what it summarised.
    """

    LEDGER = Path(__file__).resolve().parents[2] / "conformance" / "inert_audit.json"

    @unittest.skipUnless(LEDGER.is_file(), "no committed inert_audit.json")
    def test_counts_match_the_entries_they_summarise(self):
        from jui_cli.conformance.inert_audit import UNREVIEWED

        doc = json.loads(self.LEDGER.read_text(encoding="utf-8"))
        entries = doc.get("entries", [])
        counts = doc.get("counts", {})
        self.assertEqual(
            counts.get("entries"),
            len(entries),
            "counts.entries disagrees with the entry list — regenerate, or the "
            "next reader trusts a number nobody re-derived",
        )
        self.assertEqual(
            counts.get("unreviewed"),
            sum(1 for e in entries if e.get("reason") == UNREVIEWED),
            "counts.unreviewed disagrees with the entry list. It counts ENTRIES, "
            "not (fixture, platform) pairs: one entry inert on two platforms "
            "counts once",
        )


class AdjudicationBacklogRatchetTest(unittest.TestCase):
    """The backlog of measured-but-unjudged findings may not grow.

    The three older guards were measured on 2026-08-07 and only two of them
    hold this line: a finding with no ledger row fails as unrecorded, and a
    row the measurement no longer supports fails as stale — but an
    ``--update`` folds a NEW finding in as a row whose reason is the
    unreviewed marker, and ``cross_effect.check()`` counts that row as
    accepted. That is how plan 33's "unreviewed 0" regrew to 126 rows after
    the fixture expansion, with no bypass anywhere.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conf = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _ledger(self, unreviewed, ruled=0):
        entries = [
            {"fixture": f"F/u__{i}", "reason": gate.UNREVIEWED_MARKER}
            for i in range(unreviewed)
        ] + [{"fixture": f"F/r__{i}", "reason": "ruled"} for i in range(ruled)]
        (self.conf / "cross_effect.json").write_text(json.dumps({"entries": entries}))

    def _ceiling(self, value):
        (self.conf / RATCHET_FILENAME).write_text(
            json.dumps({"unreviewed": {"cross_effect.json": value}})
        )

    def test_at_the_ceiling_is_green(self):
        self._ledger(unreviewed=3)
        self._ceiling(3)
        problems, notices = gate.judge_adjudication_backlog(self.conf)
        self.assertEqual(problems, [])
        self.assertEqual(notices, [])

    def test_one_row_over_the_ceiling_fails(self):
        self._ledger(unreviewed=4)
        self._ceiling(3)
        problems, _ = gate.judge_adjudication_backlog(self.conf)
        self.assertEqual(len(problems), 1)
        self.assertIn("4 unreviewed row(s) > ratchet ceiling 3", problems[0])

    def test_burning_a_row_down_asks_for_the_ceiling_to_follow(self):
        self._ledger(unreviewed=2, ruled=1)
        self._ceiling(3)
        problems, notices = gate.judge_adjudication_backlog(self.conf)
        self.assertEqual(problems, [])
        self.assertEqual(len(notices), 1)
        self.assertIn("lower the ceiling", notices[0])

    def test_a_ledger_with_no_ceiling_entry_must_be_clean(self):
        """A fresh ledger starts strict, like a fresh render environment."""
        self._ledger(unreviewed=1)
        self._ceiling(0)
        problems, _ = gate.judge_adjudication_backlog(self.conf)
        self.assertEqual(len(problems), 1)

    def test_the_marker_is_also_read_from_the_owner_field(self):
        """value_discrimination / codegen_effect carry the verdict in `owner`."""
        (self.conf / "value_discrimination.json").write_text(
            json.dumps({"entries": [{"fixture": "F/a", "owner": gate.UNREVIEWED_MARKER}]})
        )
        problems, _ = gate.judge_adjudication_backlog(self.conf)
        self.assertEqual(len(problems), 1)
        self.assertIn("value_discrimination.json", problems[0])

    def test_the_committed_ceilings_match_the_committed_ledgers(self):
        """The real tree, not a synthetic one: today's gate must be green.

        Committing the ceilings at reality is the point — gating an
        unconsumed queue makes red the normal color.
        """
        conf = Path(__file__).resolve().parents[2] / "conformance"
        if not (conf / RATCHET_FILENAME).is_file():
            self.skipTest("no committed conformance dir")
        problems, _ = gate.judge_adjudication_backlog(conf)
        self.assertEqual(
            problems,
            [],
            "the committed unreviewed ceilings no longer match the committed "
            "ledgers — rule on the new rows, or move the ceiling with a reason",
        )
