"""Tests for cross-platform attribute-effect matching (plan 33 Phase 1).

Everything here is pure — the matcher is set arithmetic over control-diff
verdicts, so no Pillow, no images, no filesystem beyond the ledger
round-trip through a temp directory.

The contract pinned:

- agreement across in-scope platforms is consistent; disagreement is a
  finding, keyed by fixture with the per-platform verdicts
- SSoT scope is respected: a platform the fixture is not declared for is
  excluded before judging, and <2 in-scope platforms means nothing to
  compare
- a fixture missing a verdict on any in-scope platform is not compared —
  never a silent pass
- a declared enum value inert on EVERY in-scope platform is flagged
  uniformly-inert (the ``layout: leftAligned`` class, invisible to the
  agreement check)
- the ledger ratchets both directions: unrecorded findings fail, entries
  the measurement no longer supports fail; entries the run could not verify
  are a notice, not a pass and not a stale
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.conformance import cross_effect as ce
from jui_cli.conformance.control_diff import DiffResult
from jui_cli.conformance.gate import judge_cross_effect
from jui_cli.conformance.report import ReportSummary

ALL = ["ios", "android", "web"]


def _measure(scope, verdicts, platforms=None, enum_values=None):
    return ce.measure(scope, verdicts, platforms or ALL, enum_values)


class MeasureTest(unittest.TestCase):
    def test_agreement_is_consistent(self):
        scope = {"f/active": ALL, "f/inert": ALL}
        verdicts = {
            p: {"f/active": ce.ACTIVE, "f/inert": ce.INERT} for p in ALL
        }
        result = _measure(scope, verdicts)
        self.assertEqual(sorted(result.consistent), ["f/active", "f/inert"])
        self.assertEqual(result.mismatched, {})
        self.assertEqual(result.uniform_inert, {})

    def test_disagreement_is_a_finding_with_verdicts(self):
        scope = {"f/x": ALL}
        verdicts = {
            "ios": {"f/x": ce.ACTIVE},
            "android": {"f/x": ce.ACTIVE},
            "web": {"f/x": ce.INERT},
        }
        result = _measure(scope, verdicts)
        self.assertEqual(result.consistent, [])
        self.assertEqual(
            result.mismatched,
            {"f/x": {"ios": ce.ACTIVE, "android": ce.ACTIVE, "web": ce.INERT}},
        )

    def test_out_of_scope_platform_is_excluded_before_judging(self):
        # web disagrees, but the fixture is not declared for web — no finding.
        scope = {"f/x": ["ios", "android"]}
        verdicts = {
            "ios": {"f/x": ce.ACTIVE},
            "android": {"f/x": ce.ACTIVE},
            "web": {"f/x": ce.INERT},
        }
        result = _measure(scope, verdicts)
        self.assertEqual(result.consistent, ["f/x"])
        self.assertEqual(result.mismatched, {})

    def test_fewer_than_two_in_scope_platforms_compares_nothing(self):
        scope = {"f/ios-only": ["ios"]}
        result = _measure(scope, {"ios": {"f/ios-only": ce.ACTIVE}})
        self.assertEqual(result.out_of_scope, 1)
        self.assertEqual(result.consistent, [])
        self.assertEqual(result.not_compared, [])

    def test_missing_verdict_anywhere_means_not_compared(self):
        # android produced no verdict (no screenshot / no control / errored
        # comparison) — agreement on the other two must not count as a pass.
        scope = {"f/x": ALL}
        verdicts = {"ios": {"f/x": ce.ACTIVE}, "web": {"f/x": ce.ACTIVE}}
        result = _measure(scope, verdicts)
        self.assertEqual(result.not_compared, ["f/x"])
        self.assertEqual(result.consistent, [])
        self.assertEqual(result.mismatched, {})

    def test_selected_platforms_narrow_the_comparison(self):
        # Same data, gate selected only ios+android: web's divergence is not
        # this run's business.
        scope = {"f/x": ALL}
        verdicts = {
            "ios": {"f/x": ce.ACTIVE},
            "android": {"f/x": ce.ACTIVE},
            "web": {"f/x": ce.INERT},
        }
        result = _measure(scope, verdicts, platforms=["ios", "android"])
        self.assertEqual(result.consistent, ["f/x"])
        self.assertEqual(result.mismatched, {})

    def test_uniformly_inert_declared_value_is_flagged(self):
        scope = {"Collection/layout__leftaligned": ALL}
        verdicts = {p: {"Collection/layout__leftaligned": ce.INERT} for p in ALL}
        enum_values = {"Collection/layout__leftaligned": "LeftAligned"}
        result = _measure(scope, verdicts, enum_values=enum_values)
        self.assertEqual(result.consistent, ["Collection/layout__leftaligned"])
        self.assertEqual(
            result.uniform_inert, {"Collection/layout__leftaligned": "LeftAligned"}
        )

    def test_uniform_inert_needs_enum_declaration(self):
        # A representative (non-enum) value inert everywhere is control-diff's
        # documented benign case — not flagged here.
        scope = {"f/x": ALL}
        verdicts = {p: {"f/x": ce.INERT} for p in ALL}
        result = _measure(scope, verdicts, enum_values={})
        self.assertEqual(result.uniform_inert, {})

    def test_active_enum_value_is_not_flagged(self):
        scope = {"f/x": ALL}
        verdicts = {p: {"f/x": ce.ACTIVE} for p in ALL}
        result = _measure(scope, verdicts, enum_values={"f/x": "flow"})
        self.assertEqual(result.uniform_inert, {})


class InputAdaptersTest(unittest.TestCase):
    MANIFEST = {
        "fixtures": [
            {"id": "f/x", "control": "__control/View", "platforms": ["ios", "web"],
             "component": "common", "attribute": "layout", "value": "flow"},
            {"id": "__control/View", "isControl": True, "platforms": ALL,
             "component": "common", "attribute": None, "value": None},
            {"id": "f/nocontrol", "control": None, "platforms": ALL,
             "component": "common", "attribute": "onClick", "value": None},
        ]
    }

    def test_scope_from_manifest_takes_control_bearing_fixtures_only(self):
        scope = ce.scope_from_manifest(self.MANIFEST)
        self.assertEqual(scope, {"f/x": ["ios", "web"]})

    def test_verdicts_from_diffs(self):
        diffs = {
            "ios": DiffResult(platform="ios", active=["f/a"], inert=[("f/b", 0)]),
            "web": DiffResult(platform="web", error="Pillow missing"),
        }
        verdicts = ce.verdicts_from_diffs(diffs)
        self.assertEqual(verdicts, {"ios": {"f/a": ce.ACTIVE, "f/b": ce.INERT}})

    def test_enum_fixture_values_reads_ssot_enums(self):
        definitions = {
            "common": {
                "layout": {"type": "string", "enum": ["vertical", "flow"]},
                "width": {"type": ["number", {"enum": ["matchParent"]}]},
            }
        }
        manifest = {
            "fixtures": [
                {"id": "f/enum", "control": "c", "component": "common",
                 "attribute": "layout", "value": "flow"},
                {"id": "f/typed-enum", "control": "c", "component": "common",
                 "attribute": "width", "value": "matchParent"},
                {"id": "f/plain", "control": "c", "component": "common",
                 "attribute": "layout", "value": "#FF0000"},
                {"id": "f/unknown-attr", "control": "c", "component": "common",
                 "attribute": "nope", "value": "flow"},
            ]
        }
        self.assertEqual(
            ce.enum_fixture_values(manifest, definitions),
            {"f/enum": "flow", "f/typed-enum": "matchParent"},
        )


def _result(**overrides) -> ce.CrossEffectResult:
    result = ce.CrossEffectResult(platforms=list(ALL))
    for name, value in overrides.items():
        setattr(result, name, value)
    return result


DIVERGENCE = {"ios": ce.ACTIVE, "android": ce.INERT, "web": ce.INERT}


class CheckTest(unittest.TestCase):
    def test_unrecorded_finding_fails(self):
        verdict = ce.check(_result(mismatched={"f/x": dict(DIVERGENCE)}), {})
        self.assertFalse(verdict.ok)
        self.assertEqual(len(verdict.unrecorded), 1)
        self.assertIn("f/x", verdict.unrecorded[0])

    def test_matching_entry_is_accepted(self):
        ledger = {"f/x": {"fixture": "f/x", "platforms": dict(DIVERGENCE),
                          "reason": "platform idiom"}}
        verdict = ce.check(_result(mismatched={"f/x": dict(DIVERGENCE)}), ledger)
        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.accepted, 1)

    def test_resolved_entry_is_stale(self):
        ledger = {"f/x": {"fixture": "f/x", "platforms": dict(DIVERGENCE),
                          "reason": "was drifting"}}
        verdict = ce.check(_result(consistent=["f/x"]), ledger)
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.stale, ["f/x"])

    def test_changed_pattern_is_unrecorded_and_stale(self):
        # The entry justified a different fact — it must be re-adjudicated.
        ledger = {"f/x": {"fixture": "f/x", "platforms": dict(DIVERGENCE),
                          "reason": "idiom"}}
        flipped = {"ios": ce.INERT, "android": ce.ACTIVE, "web": ce.INERT}
        verdict = ce.check(_result(mismatched={"f/x": flipped}), ledger)
        self.assertEqual(len(verdict.unrecorded), 1)
        self.assertIn("recorded fact differs", verdict.unrecorded[0])
        self.assertEqual(verdict.stale, ["f/x"])

    def test_unverified_entry_is_a_notice_not_a_stale(self):
        # The run could not compare the fixture — an unverified assertion is
        # neither resolved (stale) nor confirmed (accepted).
        ledger = {"f/x": {"fixture": "f/x", "platforms": dict(DIVERGENCE),
                          "reason": "idiom"}}
        verdict = ce.check(_result(not_compared=["f/x"]), ledger)
        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.unverified, ["f/x"])
        self.assertEqual(verdict.stale, [])

    def test_uniform_inert_unrecorded_fails(self):
        result = _result(consistent=["f/u"], uniform_inert={"f/u": "leftAligned"})
        verdict = ce.check(result, {})
        self.assertFalse(verdict.ok)
        self.assertIn("uniformly-inert", verdict.unrecorded[0])

    def test_uniform_inert_matching_entry_is_accepted(self):
        ledger = {"f/u": {"fixture": "f/u", "verdict": ce.UNIFORMLY_INERT,
                          "declared": "vertical", "reason": "value is the default"}}
        result = _result(consistent=["f/u"], uniform_inert={"f/u": "vertical"})
        verdict = ce.check(result, ledger)
        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.accepted, 1)

    def test_uniform_entry_goes_stale_when_value_takes_effect(self):
        ledger = {"f/u": {"fixture": "f/u", "verdict": ce.UNIFORMLY_INERT,
                          "declared": "flow", "reason": "unimplemented"}}
        verdict = ce.check(_result(consistent=["f/u"]), ledger)  # now active
        self.assertEqual(verdict.stale, ["f/u"])


class LedgerTest(unittest.TestCase):
    def test_roundtrip_both_entry_kinds(self):
        entries = {
            "f/d": {"fixture": "f/d", "platforms": dict(DIVERGENCE),
                    "reason": "idiom", "note": "n"},
            "f/u": {"fixture": "f/u", "verdict": ce.UNIFORMLY_INERT,
                    "declared": "vertical", "reason": "default", "note": ""},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ce.LEDGER_NAME
            path.write_text(ce.render_ledger(entries), encoding="utf-8")
            loaded = ce.load_ledger(path)
        self.assertEqual(loaded["f/d"]["platforms"], DIVERGENCE)
        self.assertEqual(loaded["f/u"]["verdict"], ce.UNIFORMLY_INERT)
        self.assertEqual(loaded["f/u"]["declared"], "vertical")

    def test_render_is_deterministic(self):
        entries = {
            "f/b": {"fixture": "f/b", "platforms": dict(DIVERGENCE), "reason": "r"},
            "f/a": {"fixture": "f/a", "verdict": ce.UNIFORMLY_INERT,
                    "declared": "x", "reason": "r"},
        }
        self.assertEqual(ce.render_ledger(entries), ce.render_ledger(dict(reversed(entries.items()))))
        rendered = json.loads(ce.render_ledger(entries))
        self.assertEqual([e["fixture"] for e in rendered["entries"]], ["f/a", "f/b"])

    def test_missing_ledger_is_empty(self):
        self.assertEqual(ce.load_ledger(Path("/nonexistent/cross_effect.json")), {})


class UpdateLedgerTest(unittest.TestCase):
    def test_new_finding_gets_unreviewed_marker(self):
        merged = ce.update_ledger({}, _result(mismatched={"f/x": dict(DIVERGENCE)}))
        self.assertEqual(merged["f/x"]["reason"], ce.UNREVIEWED)

    def test_surviving_entry_keeps_reason_and_note(self):
        existing = {"f/x": {"fixture": "f/x", "platforms": dict(DIVERGENCE),
                            "reason": "idiom", "note": "keep me"}}
        merged = ce.update_ledger(existing, _result(mismatched={"f/x": dict(DIVERGENCE)}))
        self.assertEqual(merged["f/x"]["reason"], "idiom")
        self.assertEqual(merged["f/x"]["note"], "keep me")

    def test_changed_pattern_returns_to_backlog(self):
        existing = {"f/x": {"fixture": "f/x", "platforms": dict(DIVERGENCE),
                            "reason": "idiom", "note": "old"}}
        flipped = {"ios": ce.INERT, "android": ce.ACTIVE, "web": ce.INERT}
        merged = ce.update_ledger(existing, _result(mismatched={"f/x": flipped}))
        self.assertEqual(merged["f/x"]["reason"], ce.UNREVIEWED)
        self.assertEqual(merged["f/x"]["platforms"], flipped)

    def test_resolved_entry_is_pruned(self):
        existing = {"f/x": {"fixture": "f/x", "platforms": dict(DIVERGENCE),
                            "reason": "was drifting"}}
        merged = ce.update_ledger(existing, _result(consistent=["f/x"]))
        self.assertEqual(merged, {})

    def test_unmeasured_entry_survives_untouched(self):
        existing = {"f/x": {"fixture": "f/x", "platforms": dict(DIVERGENCE),
                            "reason": "idiom", "note": "n"}}
        merged = ce.update_ledger(existing, _result(not_compared=["f/x"]))
        self.assertEqual(merged, existing)

    def test_uniform_inert_entry_written_and_preserved(self):
        result = _result(consistent=["f/u"], uniform_inert={"f/u": "vertical"})
        merged = ce.update_ledger({}, result)
        self.assertEqual(merged["f/u"]["verdict"], ce.UNIFORMLY_INERT)
        self.assertEqual(merged["f/u"]["reason"], ce.UNREVIEWED)
        merged["f/u"]["reason"] = "value is the default"
        again = ce.update_ledger(merged, result)
        self.assertEqual(again["f/u"]["reason"], "value is the default")


def _summary(**overrides) -> ReportSummary:
    summary = ReportSummary(out_path=Path("REPORT.md"), platforms=list(ALL))
    summary.effect_scope = {"f/x": list(ALL)}
    summary.effect_verdicts = {
        "ios": {"f/x": ce.ACTIVE},
        "android": {"f/x": ce.ACTIVE},
        "web": {"f/x": ce.INERT},
    }
    for name, value in overrides.items():
        setattr(summary, name, value)
    return summary


class JudgeCrossEffectTest(unittest.TestCase):
    def test_unrecorded_finding_is_a_problem_under_local(self):
        problems, notices = judge_cross_effect(_summary(), ALL, {})
        self.assertEqual(len(problems), 1)
        self.assertIn("cross_effect.json", problems[0])
        self.assertIn("f/x", problems[0])

    def test_non_local_env_downgrades_to_notice(self):
        problems, notices = judge_cross_effect(_summary(), ALL, {}, env="ci")
        self.assertEqual(problems, [])
        self.assertTrue(any("f/x" in n for n in notices))

    def test_accepted_finding_passes_with_notice(self):
        ledger = {"f/x": {"fixture": "f/x", "reason": "idiom", "platforms": {
            "ios": ce.ACTIVE, "android": ce.ACTIVE, "web": ce.INERT}}}
        problems, notices = judge_cross_effect(_summary(), ALL, ledger)
        self.assertEqual(problems, [])
        self.assertTrue(any("cross-effect OK" in n for n in notices))

    def test_stale_entry_is_a_problem(self):
        summary = _summary(
            effect_verdicts={p: {"f/x": ce.ACTIVE} for p in ALL}
        )
        ledger = {"f/x": {"fixture": "f/x", "reason": "idiom", "platforms": {
            "ios": ce.ACTIVE, "android": ce.ACTIVE, "web": ce.INERT}}}
        problems, notices = judge_cross_effect(summary, ALL, ledger)
        self.assertEqual(len(problems), 1)
        self.assertIn("stale", problems[0])

    def test_fewer_than_two_platforms_is_a_problem(self):
        problems, _ = judge_cross_effect(_summary(), ["ios"], {})
        self.assertEqual(len(problems), 1)
        self.assertIn("at least two", problems[0])

    def test_judgment_spans_selected_platforms_only(self):
        # web diverges, but only ios+android were selected — clean.
        problems, notices = judge_cross_effect(_summary(), ["ios", "android"], {})
        self.assertEqual(problems, [])
        self.assertTrue(any("cross-effect OK" in n for n in notices))


if __name__ == "__main__":
    unittest.main()
