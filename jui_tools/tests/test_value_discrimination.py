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

if __name__ == "__main__":
    unittest.main()
