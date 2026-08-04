"""Tests for the codegen-stage differential (plan 41).

The check compares emitted TEXT, so the interesting contract is not "does it
run" but "what does a failing comparison mean" — the two shipped defects it
exists for (plan 36's bound dimension, plan 34's slider tint) both looked like
passes to every pixel-based lane. What is pinned here:

- the three judgements read TOGETHER: C0 on its own cannot separate "nothing
  reads the spelling" from "the representative value equals the default", and
  C2 is what decides between them
- an attribute the host's base already carries is not a control at all, so C0
  is recorded as inapplicable rather than reported as a failure
- C1 needs the bound output to NAME the bound property: at the codegen stage
  the static and bound forms are supposed to differ, so "differs from the
  control" alone proves nothing
- nothing is dropped silently — an attribute with no probe lands in
  ``out_of_scope`` or ``not_applicable`` with a reason, which is the same
  discipline the inert audit runs on
- the second value is derived, not tabulated, and it stays inside the SSoT's
  declared min/max
"""
from __future__ import annotations

import contextlib
import unittest

from jui_cli.conformance import codegen_effect as ce
from jui_cli.conformance import rules


def _defn(**kw):
    return dict(kw)


def _emit(text, ok=True, error=None):
    return {"ok": ok, "output": text, **({"error": error} if error else {})}


@contextlib.contextmanager
def _base_attrs(overrides):
    """Temporarily set ``rules.BASE_ATTRS`` entries (restored on exit)."""
    saved = {k: rules.BASE_ATTRS.get(k) for k in overrides}
    rules.BASE_ATTRS.update(overrides)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                rules.BASE_ATTRS.pop(key, None)
            else:
                rules.BASE_ATTRS[key] = value


class SecondaryValueTest(unittest.TestCase):
    def test_boolean_flips(self):
        self.assertEqual(ce.secondary_value("common", "x", _defn(type="boolean"), True), (True, False))

    def test_number_stays_inside_declared_bounds(self):
        defn = _defn(type="number", min=0, max=1)
        found, value = ce.secondary_value("common", "opacity", defn, 0.5)
        self.assertTrue(found)
        self.assertNotEqual(value, 0.5)
        self.assertGreaterEqual(value, 0)
        self.assertLessEqual(value, 1)

    def test_integer_stays_integral(self):
        found, value = ce.secondary_value("common", "lines", _defn(type="number"), 2)
        self.assertTrue(found)
        self.assertIsInstance(value, int)

    def test_colour_becomes_a_different_colour(self):
        found, value = ce.secondary_value("common", "fontColor", _defn(type="color"), "#FF0000")
        self.assertTrue(found)
        self.assertTrue(value.startswith("#"))
        self.assertNotEqual(value.upper(), "#FF0000")

    def test_image_stays_inside_the_two_bundled_assets(self):
        found, value = ce.secondary_value(
            "Image", "src", _defn(type="string"), rules.IMAGE_ASSET_NAME
        )
        self.assertTrue(found)
        self.assertEqual(value, rules.IMAGE_ALT_ASSET_NAME)

    def test_view_reference_has_no_second_value(self):
        # The fixture layout carries exactly one anchor sibling.
        found, _ = ce.secondary_value("common", "alignTopOfView", _defn(type="string"), "anchor")
        self.assertFalse(found)

    def test_composite_values_move_every_leaf(self):
        found, value = ce.secondary_value(
            "common", "paddings", _defn(type="array"), [8, 8, 8, 8]
        )
        self.assertTrue(found)
        self.assertNotEqual(value, [8, 8, 8, 8])

    def test_object_value_moves_at_least_one_leaf(self):
        primary = {"color": "#FF0000", "blur": 4}
        found, value = ce.secondary_value("Label", "textShadow", _defn(type="object"), primary)
        self.assertTrue(found)
        self.assertNotEqual(value, primary)
        self.assertEqual(set(value), set(primary))


class JobTableTest(unittest.TestCase):
    def test_a_uikit_only_attribute_is_scoped_out_with_a_reason(self):
        definitions = {"View": {"chrome": _defn(type="string", mode="uikit")}}
        table = ce.build_jobs(definitions)
        self.assertEqual(table.probes, [])
        self.assertEqual(
            [(e.attribute, e.scope_reason) for e in table.out_of_scope],
            [("chrome", "no-codegen-platform")],
        )

    def test_a_callback_is_scoped_out_with_the_rules_reason(self):
        definitions = {"View": {"onTap": _defn(type="callback")}}
        table = ce.build_jobs(definitions)
        self.assertEqual(table.probes, [])
        entry = table.out_of_scope[0]
        self.assertEqual(entry.scope_reason, "unfixturable")
        self.assertEqual(entry.detail, rules.REASON_CALLBACK)

    def test_one_probe_per_declared_platform(self):
        definitions = {"View": {"tintColor": _defn(type="color")}}
        table = ce.build_jobs(definitions)
        self.assertEqual([p.platform for p in table.probes], list(ce.PLATFORMS))

    def test_a_bound_job_exists_only_for_binding_declared_attributes(self):
        definitions = {
            "View": {
                "bound": _defn(type=["number", "binding"]),
                "plain": _defn(type="number"),
            }
        }
        table = ce.build_jobs(definitions)
        ids = {job["id"] for job in table.jobs["web"]}
        self.assertIn("View|bound|bound", ids)
        self.assertNotIn("View|plain|bound", ids)

    def test_controls_are_shared_between_attributes_of_one_shape(self):
        definitions = {
            "View": {"tintColor": _defn(type="color"), "fontColor": _defn(type="color")}
        }
        table = ce.build_jobs(definitions)
        controls = [j["id"] for j in table.jobs["web"] if j["id"].startswith("__control|")]
        self.assertEqual(len(controls), len(set(controls)))
        self.assertEqual(len(controls), 1)

    def test_a_base_supplied_value_is_flagged_rather_than_probed_blind(self):
        # A base that supplies the very value under test makes fixture and
        # control coincide. `Image.src` used to be the live example; plan 34
        # gave it a distinct representative value (the alt asset), so the
        # condition is set up here instead of borrowed from the real table —
        # the mechanism is what this test is about, not that one fixture.
        with _base_attrs({"Image": {"src": "conformance_sample_alt"}}):
            table = ce.build_jobs({"Image": {"src": _defn(type="string")}})
            self.assertTrue(all(p.control_carries_primary for p in table.probes))

    def test_a_base_with_a_different_value_is_probed_normally(self):
        """The other side of the same switch — this is the fixed state."""
        table = ce.build_jobs({"Image": {"src": _defn(type="string")}})
        self.assertFalse(any(p.control_carries_primary for p in table.probes))


def _table_with(check_defn, host="View", attribute="x"):
    return ce.build_jobs({host: {attribute: check_defn}}, platforms=("web",))


class EvaluateTest(unittest.TestCase):
    def _run(self, defn, emits, attribute="x", host="View"):
        table = _table_with(defn, host=host, attribute=attribute)
        probe = table.probes[0]
        outputs = {
            "web": {
                f"__control|{probe.control_id}": _emit(emits["control"]),
                f"{host}|{attribute}|primary": _emit(emits["primary"]),
                **(
                    {f"{host}|{attribute}|secondary": _emit(emits["secondary"])}
                    if "secondary" in emits
                    else {}
                ),
                **(
                    {f"{host}|{attribute}|bound": _emit(emits["bound"])}
                    if "bound" in emits
                    else {}
                ),
            }
        }
        return ce.evaluate(table, outputs)

    def test_a_read_attribute_produces_no_finding(self):
        result = self._run(
            _defn(type="color"),
            {"control": "a", "primary": "b", "secondary": "c"},
        )
        self.assertEqual(result.findings, [])
        self.assertTrue(result.ok)

    def test_identical_for_every_value_is_an_unread_spelling(self):
        result = self._run(
            _defn(type="color"),
            {"control": "a", "primary": "a", "secondary": "a"},
        )
        self.assertEqual([f.finding_class for f in result.findings], ["unread-spelling"])
        self.assertEqual(result.findings[0].check, "C0")

    def test_identical_to_control_but_value_sensitive_is_value_is_default(self):
        # This is the judgement plan 34 recorded as NOT machine-derivable from
        # the SSoT: C2 supplies it from the other side.
        result = self._run(
            _defn(type="color"),
            {"control": "a", "primary": "a", "secondary": "b"},
        )
        self.assertEqual([f.finding_class for f in result.findings], ["value-is-default"])

    def test_a_value_is_default_finding_is_advice_not_a_defect(self):
        # It says the FIXTURE discriminates nothing, so it must not gate and
        # must never be ledgered (2026-08-04 adjudication) — a recorded entry
        # would go stale the moment the representative value changed.
        result = self._run(
            _defn(type="color"),
            {"control": "a", "primary": "a", "secondary": "b"},
        )
        self.assertEqual(result.defects, [])
        self.assertEqual(len(result.advisories), 1)
        self.assertTrue(result.ok)

    def test_a_real_defect_still_fails(self):
        result = self._run(
            _defn(type="color"),
            {"control": "a", "primary": "a", "secondary": "a"},
        )
        self.assertEqual(len(result.defects), 1)
        self.assertEqual(result.advisories, [])
        self.assertFalse(result.ok)

    def test_reacting_to_presence_but_not_to_value_is_reported_once(self):
        result = self._run(
            _defn(type="color"),
            {"control": "a", "primary": "b", "secondary": "b"},
        )
        self.assertEqual([f.finding_class for f in result.findings], ["presence-only"])
        self.assertEqual(result.findings[0].check, "C2")

    def test_one_root_never_produces_two_queue_items(self):
        result = self._run(
            _defn(type="color"),
            {"control": "a", "primary": "a", "secondary": "a"},
        )
        self.assertEqual(len(result.findings), 1)

    def test_a_dropped_binding_is_caught(self):
        result = self._run(
            _defn(type=["number", "binding"]),
            {"control": "a", "primary": "b", "secondary": "c", "bound": "a"},
        )
        self.assertEqual([f.check for f in result.findings], ["C1"])
        self.assertEqual(result.findings[0].finding_class, "bound-dropped")

    def test_a_bound_emit_that_never_names_the_property_is_caught(self):
        # Differing from the control is not enough: the static and bound forms
        # are SUPPOSED to differ here (`h-[100px]` vs a style expression).
        result = self._run(
            _defn(type=["number", "binding"]),
            {"control": "a", "primary": "b", "secondary": "c", "bound": "something-else"},
        )
        self.assertEqual([f.check for f in result.findings], ["C1"])

    def test_a_bound_emit_naming_the_property_passes(self):
        result = self._run(
            _defn(type=["number", "binding"]),
            {
                "control": "a",
                "primary": "b",
                "secondary": "c",
                "bound": f"style={{height: {ce.BINDING_VAR}}}",
            },
        )
        self.assertEqual(result.findings, [])

    def test_a_converter_that_raises_is_an_error_not_a_pass(self):
        table = _table_with(_defn(type="color"))
        probe = table.probes[0]
        outputs = {
            "web": {
                f"__control|{probe.control_id}": _emit("a"),
                "View|x|primary": {"ok": False, "error": "TypeError"},
            }
        }
        result = ce.evaluate(table, outputs)
        self.assertEqual(len(result.errors), 1)
        self.assertFalse(result.ok)

    def test_an_inapplicable_check_is_recorded_with_a_reason(self):
        # Same setup as the job-table case: the base has to carry the value
        # under test for C0 to be inapplicable, and plan 34 removed the one
        # real fixture that did (`Image.src`), so it is arranged here.
        with _base_attrs({"Image": {"src": "conformance_sample_alt"}}):
            table = _table_with(_defn(type="string"), host="Image", attribute="src")
            probe = table.probes[0]
            outputs = {
                "web": {
                    f"__control|{probe.control_id}": _emit("a"),
                    "Image|src|primary": _emit("a"),
                    "Image|src|secondary": _emit("b"),
                }
            }
            result = ce.evaluate(table, outputs)
        self.assertEqual(result.findings, [])
        self.assertIn("C0", result.not_applicable)

    def test_an_unenumerated_string_says_so_instead_of_blaming_the_converter(self):
        # `keyboardType` is declared as a bare string, so the probe value is
        # "sample" and the second is "sampleTwo" — neither is in the
        # vocabulary any converter accepts. The comparison is sound; the
        # repair is in attribute_definitions.json.
        result = self._run(
            _defn(type="string"),
            {"control": "a", "primary": "a", "secondary": "a"},
            attribute="keyboardType",
        )
        self.assertEqual(
            [f.finding_class for f in result.findings], ["unenumerated-vocabulary"]
        )

    def test_an_enumerated_string_is_judged_normally(self):
        result = self._run(
            _defn(type="string", enum=["one", "two"]),
            {"control": "a", "primary": "a", "secondary": "a"},
            attribute="mode",
        )
        self.assertEqual([f.finding_class for f in result.findings], ["unread-spelling"])

    def test_the_two_spellings_of_a_number_must_agree(self):
        # C3 is the judgement that compares for EQUALITY (plan 43): `10` and
        # `"10"` are the same value and have no reason to emit differently.
        table = _table_with(_defn(type="number"), attribute="fontSize")
        probe = table.probes[0]
        outputs = {
            "web": {
                f"__control|{probe.control_id}": _emit("a"),
                "View|fontSize|primary": _emit("text-xl"),
                "View|fontSize|secondary": _emit("text-3xl"),
                "View|fontSize|numeric_string": _emit(""),
            }
        }
        result = ce.evaluate(table, outputs)
        c3 = [f for f in result.findings if f.check == "C3"]
        self.assertEqual([f.finding_class for f in c3], ["numeric-string-divergence"])

    def test_a_numeric_string_divergence_is_advice_not_a_defect(self):
        # 2026-08-04 ruling: a numeric string is not a number, every
        # platform's validator warns on it, and `jui build` at zero warnings
        # keeps it out of a build. The CRASH side still gates — see below.
        table = _table_with(_defn(type="number"), attribute="fontSize")
        probe = table.probes[0]
        outputs = {
            "web": {
                f"__control|{probe.control_id}": _emit("a"),
                "View|fontSize|primary": _emit("text-xl"),
                "View|fontSize|secondary": _emit("text-3xl"),
                "View|fontSize|numeric_string": _emit(""),
            }
        }
        result = ce.evaluate(table, outputs)
        self.assertEqual(result.defects, [])
        self.assertEqual(len(result.advised("numeric-string-divergence")), 1)
        self.assertTrue(result.ok)

    def test_a_converter_that_raises_on_a_numeric_string_still_fails(self):
        # The warning that makes divergence tolerable is printed by
        # `jui build` — and a converter that raises aborts before it prints.
        # That is the escape hatch plan 43 closed, so it stays hard.
        table = _table_with(_defn(type="number"), attribute="fontSize")
        probe = table.probes[0]
        outputs = {
            "web": {
                f"__control|{probe.control_id}": _emit("a"),
                "View|fontSize|primary": _emit("text-xl"),
                "View|fontSize|secondary": _emit("text-3xl"),
                "View|fontSize|numeric_string": {"ok": False, "error": "TypeError"},
            }
        }
        result = ce.evaluate(table, outputs)
        self.assertEqual(len(result.errors), 1)
        self.assertFalse(result.ok)

    def test_matching_spellings_pass(self):
        table = _table_with(_defn(type="number"), attribute="fontSize")
        probe = table.probes[0]
        outputs = {
            "web": {
                f"__control|{probe.control_id}": _emit("a"),
                "View|fontSize|primary": _emit("text-xl"),
                "View|fontSize|secondary": _emit("text-3xl"),
                "View|fontSize|numeric_string": _emit("text-xl"),
            }
        }
        result = ce.evaluate(table, outputs)
        self.assertEqual([f for f in result.findings if f.check == "C3"], [])
        self.assertEqual(result.per_check["C3"], 1)

    def test_c3_runs_on_an_attribute_that_declares_no_binding(self):
        # C1 short-circuits for a non-bindable attribute; C3 must not be
        # skipped with it — a number written as a string is legal input
        # whether or not the attribute accepts `@{...}`.
        table = _table_with(_defn(type="number"), attribute="fontSize")
        self.assertFalse(table.probes[0].bindable)
        outputs = {
            "web": {
                f"__control|{table.probes[0].control_id}": _emit("a"),
                "View|fontSize|primary": _emit("b"),
                "View|fontSize|secondary": _emit("c"),
                "View|fontSize|numeric_string": _emit("d"),
            }
        }
        result = ce.evaluate(table, outputs)
        self.assertEqual(result.per_check["C3"], 1)

    def test_c3_finds_the_number_behind_an_enum(self):
        # `width` leads with `matchParent`; its numeric case is further down
        # the plan, and that is the spelling plan 43 crashed on.
        table = ce.build_jobs(
            {"View": {"width": _defn(type=["number", {"enum": ["matchParent"]}])}},
            platforms=("web",),
        )
        self.assertEqual(table.probes[0].primary, "matchParent")
        self.assertIsInstance(table.probes[0].numeric, (int, float))

    def test_a_non_numeric_attribute_records_why_c3_did_not_run(self):
        result = self._run(
            _defn(type="color"), {"control": "a", "primary": "b", "secondary": "c"}
        )
        self.assertIn("C3", result.not_applicable)
        self.assertEqual(result.per_check["C3"], 0)

    def test_a_non_bindable_attribute_records_why_c1_did_not_run(self):
        result = self._run(
            _defn(type="color"), {"control": "a", "primary": "b", "secondary": "c"}
        )
        self.assertIn("C1", result.not_applicable)
        self.assertEqual(result.per_check["C1"], 0)


class ReportTest(unittest.TestCase):
    def test_the_report_carries_the_probe_mode_of_every_platform(self):
        table = ce.build_jobs({"View": {"tintColor": _defn(type="color")}})
        doc = ce.render_report(ce.EffectResult(), table)
        # Naming the mode is what keeps the coverage claim honest: uikit and
        # the frozen kjui XML mode are not probed and never will be here.
        self.assertEqual(doc["probeModes"]["ios"], "swiftui")
        self.assertEqual(doc["probeModes"]["android"], "compose")

    def test_advisories_ride_in_their_own_section(self):
        table = ce.build_jobs({"View": {"tintColor": _defn(type="color")}})
        result = ce.EffectResult(
            findings=[
                ce.Finding("View", "a", "web", "C0", "View", "x", "unread-spelling"),
                ce.Finding("View", "b", "web", "C0", "View", "x", "value-is-default"),
            ]
        )
        doc = ce.render_report(result, table)
        self.assertEqual([f["attribute"] for f in doc["findings"]], ["a"])
        self.assertEqual(
            [f["attribute"] for f in doc["representativeValueCandidates"]], ["b"]
        )
        self.assertEqual(doc["counts"]["findings"], 1)
        self.assertEqual(doc["counts"]["representativeValueCandidates"], 1)


if __name__ == "__main__":
    unittest.main()
