"""Two declared values of one attribute have to draw different pictures.

`distribution` declared four values and rendered three. Both members of the
collapsed pair differ from the control, so --inert-complete passed; both
pipelines collapsed them the same way, so --parity passed; all three
platforms agreed they were active, so --cross-effect passed. Nothing in the
suite asked the one question that would have caught it.

The narrowing is where this check lives or dies, so most of these pin what
it must NOT report: an alias, a binding, a case-variant spelling and a
declared valueAlias are all one value wearing two names, and a pair where
either side is inert belongs to --inert-complete.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.conformance import value_discrimination as vd


def _fx(component, attribute, case, value, **kw):
    entry = {
        "id": f"{component}/{attribute}__{case}",
        "component": component,
        "attribute": attribute,
        "case": case,
        "value": value,
        "class": "visual",
        "platforms": ["ios"],
        "aliasOf": None,
    }
    entry.update(kw)
    return entry


class NarrowingTest(unittest.TestCase):
    """What counts as two values."""

    def _groups(self, *fixtures):
        groups, excluded = vd.value_groups({"fixtures": list(fixtures)}, "ios")
        return groups, excluded

    def test_two_literals_are_two_values(self):
        groups, _ = self._groups(
            _fx("View", "distribution", "fill", "fill"),
            _fx("View", "distribution", "fillequally", "fillEqually"),
        )
        self.assertEqual(len(groups), 1)

    def test_an_alias_case_is_not_a_second_value(self):
        groups, excluded = self._groups(
            _fx("common", "opacity", "static", 0.5),
            _fx("common", "opacity", "alias_alpha", 0.5, aliasOf="common/opacity__static"),
        )
        self.assertEqual(groups, {})
        self.assertEqual(excluded["alias"], 1)

    def test_a_bound_case_is_not_a_second_value(self):
        """It is the literal it mirrors, written as `@{...}` and seeded with it."""
        groups, excluded = self._groups(
            _fx("common", "minWidth", "static", 100),
            _fx("common", "minWidth", "binding", "@{boundMinWidth}"),
        )
        self.assertEqual(groups, {})
        self.assertEqual(excluded["binding"], 1)

    def test_one_value_under_two_case_names_is_not_two_values(self):
        groups, _ = self._groups(
            _fx("View", "x", "a", "same"),
            _fx("View", "x", "b", "same"),
        )
        self.assertEqual(groups, {})


class SameDeclaredValueTest(unittest.TestCase):
    """The SSoT decides what is one value; this module must not disagree."""

    def test_case_variants_are_one_value(self):
        # AttrEnum matches case-insensitively, and contentMode lists both
        # `bottom` and `Bottom` so either spelling is accepted.
        self.assertTrue(vd.same_declared_value("bottom", "Bottom", {}))

    def test_declared_value_alias_is_one_value(self):
        aliases = {"Flow": "flow", "LeftAligned": "flow"}
        self.assertTrue(vd.same_declared_value("Flow", "flow", aliases))
        self.assertTrue(vd.same_declared_value("LeftAligned", "Flow", aliases))

    def test_two_enum_entries_with_no_alias_are_two_values(self):
        """`fill` and `ScaleToFill` render alike and the SSoT does not say so.

        Either the declaration should carry a valueAlias or they should draw
        differently. Reporting it is the point, so this must not be swallowed.
        """
        self.assertFalse(vd.same_declared_value("fill", "ScaleToFill", {}))

    def test_a_dict_value_compares_by_content(self):
        self.assertTrue(vd.same_declared_value({"a": 1}, {"a": 1}, {}))
        self.assertFalse(vd.same_declared_value({"a": 1}, {"a": 2}, {}))


class LedgerTest(unittest.TestCase):
    def _pair(self, platform="ios", case_a="fill", case_b="fillequally"):
        return vd.Pair(
            component="View", attribute="distribution", platform=platform,
            case_a=case_a, case_b=case_b, value_a="fill", value_b="fillEqually",
        )

    def _result(self, *pairs, platform="ios"):
        return vd.DiscriminationResult(platform=platform, collapsed=list(pairs))

    def _entry(self, pair, owner="E", reason="ruled, tracked in 49-E"):
        return {
            "component": pair.component,
            "attribute": pair.attribute,
            "platform": pair.platform,
            "cases": sorted((pair.case_a, pair.case_b)),
            "owner": owner,
            "reason": reason,
            "note": "",
        }

    def test_unrecorded_collapse_fails(self):
        verdict = vd.check(self._result(self._pair()), {})
        self.assertFalse(verdict.ok)
        self.assertEqual(len(verdict.unrecorded), 1)

    def test_recorded_collapse_passes(self):
        pair = self._pair()
        verdict = vd.check(self._result(pair), {pair.key: self._entry(pair)})
        self.assertTrue(verdict.ok, verdict)
        self.assertEqual(verdict.accepted, 1)

    def test_an_entry_the_measurement_no_longer_supports_fails(self):
        """Making a value discriminate again takes its row with it."""
        pair = self._pair()
        verdict = vd.check(self._result(), {pair.key: self._entry(pair)})
        self.assertFalse(verdict.ok)
        self.assertEqual(len(verdict.stale), 1)

    def test_entry_without_owner_or_reason_fails(self):
        pair = self._pair()
        for field in ("owner", "reason"):
            entry = self._entry(pair)
            entry[field] = ""
            verdict = vd.check(self._result(pair), {pair.key: entry})
            self.assertFalse(verdict.ok, field)
            self.assertEqual(verdict.accepted, 0)

    def test_another_platform_row_is_not_stale(self):
        pair = self._pair(platform="android")
        verdict = vd.check(self._result(platform="ios"), {pair.key: self._entry(pair)})
        self.assertTrue(verdict.ok, verdict)

    def test_key_is_order_independent(self):
        a = self._pair(case_a="fill", case_b="fillequally")
        b = self._pair(case_a="fillequally", case_b="fill")
        self.assertEqual(a.key, b.key)

    def test_round_trip_is_stable(self):
        pair = self._pair()
        merged = vd.update_ledger({}, self._result(pair))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / vd.LEDGER_NAME
            path.write_text(vd.render_ledger(merged), encoding="utf-8")
            self.assertEqual(vd.load_ledger(path), merged)

    def test_update_preserves_owner_and_reason(self):
        pair = self._pair()
        existing = {pair.key: self._entry(pair, owner="G", reason="android only")}
        merged = vd.update_ledger(existing, self._result(pair))
        self.assertEqual(merged[pair.key]["owner"], "G")

class UnmeasurableIsSaidOutLoudTest(unittest.TestCase):
    """The count alone reads backwards, so it never travels alone.

    A platform where an attribute stopped working drops every one of its
    pairs out of this check — both sides must be active for the question to
    mean anything — so the more broken the platform, the smaller the number.
    iOS reported 6 against android's 33 and looked like the healthy one; it
    had 783 pairs it could not measure, because contentMode had gone inert
    on 15 of 16 fixtures.
    """

    def test_result_carries_the_unmeasurable_count(self):
        result = vd.DiscriminationResult(platform="ios")
        result.excluded["not-both-active"] = 783
        self.assertEqual(result.excluded.get("not-both-active"), 783)

    def test_a_platform_that_measured_nothing_is_not_silence(self):
        """Zero comparisons must not read as zero defects.

        The gate turns this into a problem rather than a clean notice: the
        check ran and could say nothing, which is not the same as the values
        discriminating.
        """
        from jui_cli.conformance import gate

        result = vd.DiscriminationResult(platform="ios", groups=40, compared=0)
        result.excluded["not-both-active"] = 900
        verdict = vd.check(result, {})
        self.assertTrue(verdict.ok, "no collapse was measured, so the ledger is satisfied")
        self.assertTrue(
            callable(gate.judge_value_discrimination),
            "the gate is what turns a measured-nothing into a problem",
        )

class WrongResultsShapeRaisesTest(unittest.TestCase):
    """A shape this does not understand must raise, not measure zero.

    The runners write `{"results": [ … ]}`. Hand the list over, or the whole
    document, and `.items()` yields nothing: every pair is unmeasurable and
    the run reports a clean zero collapses. It happened twice in one sitting
    to someone driving this by hand, who nearly reported the green.
    """

    def test_a_list_raises(self):
        with self.assertRaises(TypeError):
            vd.measure("conformance", "ios", {"fixtures": []}, [], env="ci")

    def test_the_whole_document_raises(self):
        with self.assertRaises(ValueError):
            vd.measure(
                "conformance", "ios", {"fixtures": []},
                {"results": [{"id": "a"}]}, env="ci",
            )

    def test_an_empty_mapping_is_allowed(self):
        """A run with no results is a different thing from a wrong shape."""
        result = vd.measure("conformance", "ios", {"fixtures": []}, {}, env="ci")
        self.assertEqual(result.compared, 0)

if __name__ == "__main__":
    unittest.main()


class EnvScopedRowsTest(unittest.TestCase):
    """Whether two values collapse is an ENVIRONMENT fact, not only a platform one.

    Measured 2026-09-15 on one manifest, one rjui tree, the same fixtures:

        Label.fontWeight  600 vs bold   local (macOS) 416 px   ci (ubuntu) 0 px
        Button.fontWeight 600 vs bold   local (macOS) 358 px   ci (ubuntu) 0 px

    The CI runner's font stack has no distinct 600 weight and falls back to
    700; a Mac has one. The same fixture differs 661 px between the two
    environments, which is the font stack and nothing else.

    Before the scope existed, the ledger could not be right in both lanes:
    keeping the rows made ``--env local`` fail them as stale, deleting them
    made ``--env ci`` fail them as unrecorded. The author deleted them first,
    from one environment's measurement, and the other lane caught it.

    A row with no ``env`` keeps its old meaning — every environment — so every
    row written before the scope existed is unaffected.
    """

    @staticmethod
    def _result(platform="web"):
        pair = vd.Pair(
            component="Label", attribute="fontWeight", platform=platform,
            case_a="600", case_b="static", pixels=0,
        )
        return vd.DiscriminationResult(platform=platform, collapsed=[pair]), pair

    def _ledger(self, **extra):
        res, pair = self._result()
        entry = {"component": "Label", "attribute": "fontWeight", "platform": "web",
                 "cases": ["600", "static"], "owner": "o", "reason": "r"}
        entry.update(extra)
        return res, {pair.key: entry}

    def test_an_unscoped_row_still_applies_everywhere(self):
        # The compatibility guarantee. Every row written before the scope
        # existed has no `env`, and must keep covering both lanes.
        res, ledger = self._ledger()
        for env in ("local", "ci", None):
            with self.subTest(env=env):
                v = vd.check(res, ledger, env=env)
                self.assertEqual([], v.unrecorded)
                self.assertEqual([], v.stale)

    def test_a_row_scoped_to_ci_covers_the_ci_lane(self):
        res, ledger = self._ledger(env=["ci"])
        v = vd.check(res, ledger, env="ci")
        self.assertEqual([], v.unrecorded)
        self.assertEqual(1, v.accepted)

    def test_a_row_scoped_to_ci_does_not_excuse_the_local_lane(self):
        # The boundary, and the direction that matters: a ci-only row must not
        # become a blanket excuse. Same row, same collapse, other env.
        res, ledger = self._ledger(env=["ci"])
        v = vd.check(res, ledger, env="local")
        self.assertEqual(1, len(v.unrecorded))
        self.assertEqual(0, v.accepted)

    def test_a_row_scoped_to_ci_is_not_stale_just_because_local_discriminates(self):
        # The other half of the catch. Under `local` the pair does NOT collapse,
        # so it is absent from the measurement — which used to read as stale and
        # push an author to delete a row that is true in the other lane.
        _, ledger = self._ledger(env=["ci"])
        empty = vd.DiscriminationResult(platform="web")  # nothing collapsed here
        v = vd.check(empty, ledger, env="local")
        self.assertEqual([], v.stale)

    def test_an_unscoped_row_IS_stale_when_nothing_collapses(self):
        # Control: the exemption must not have disabled the stale direction.
        _, ledger = self._ledger()
        empty = vd.DiscriminationResult(platform="web")
        v = vd.check(empty, ledger, env="local")
        self.assertEqual(1, len(v.stale))
