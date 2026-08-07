"""Paired probe + binding-leak detection (plan 41, 2026-08-04).

Two additions to the codegen differential, tested here rather than in
`test_conformance_codegen_effect` so a shared checkout can land them without
touching a file another session is editing.

**The leak detector.** C1 used to pass whenever the emitted text contained the
probe variable's name. A converter that interpolates the raw `@{juiProbeValue}`
into its output satisfies that test — the variable name is *inside* the leaked
expression — so 85 judgements were passing on emitted source that is either not
a program (`fontSize = @{v}.sp`) or prints the expression to the user
(`Text("@{v}")`). The order of the checks is the fix, and it is pinned below.

**The paired probe.** An attribute the adjudication ledger says renders nothing
on its own cannot be judged by a probe that writes it alone. Companions are
written on the control AND on every case so they cancel; what is pinned here is
that cancellation, because a companion that reached only one side would turn
every paired attribute into a false finding.
"""
from __future__ import annotations

import unittest

from jui_cli.conformance import codegen_effect as ce
from jui_cli.conformance import companions as comp


def _defn(**kw):
    return dict(kw)


def _emit(text):
    return {"ok": True, "output": text}


class LeakPositionTest(unittest.TestCase):
    """`@{...}` in code position stops the build; in a string it does not."""

    def test_code_position_is_not_a_literal(self):
        self.assertFalse(ce._leak_is_literal("fontSize = @{juiProbeValue}.sp"))

    def test_double_quoted_string_is_a_literal(self):
        self.assertTrue(ce._leak_is_literal('Text("@{juiProbeValue}")'))

    def test_jsx_class_attribute_is_a_literal(self):
        self.assertTrue(
            ce._leak_is_literal('<span className="text-[@{juiProbeValue}px]" />')
        )

    def test_a_closed_string_earlier_on_the_line_does_not_count(self):
        # The quote pair before the leak is balanced, so the leak itself is in
        # code position — this is the case a naive "any quote on the line"
        # test would get wrong.
        self.assertFalse(
            ce._leak_is_literal('.frame(width: "px", height: @{juiProbeValue})')
        )

    def test_no_leak_at_all(self):
        self.assertFalse(ce._leak_is_literal(".frame(height: data.v)"))
        self.assertEqual(ce._leak_context(".frame(height: data.v)"), "")


class BoundClassificationTest(unittest.TestCase):
    """The four C1 verdicts, in the order the evaluator must apply them."""

    def _judge(self, bound_text: str, control_text: str = "CONTROL"):
        definitions = {"View": {"w": _defn(type=["number", "binding"])}}
        table = ce.build_jobs(definitions, platforms=("web",))
        outputs = {"web": {}}
        for job in table.jobs["web"]:
            job_id = job["id"]
            case = job_id.rsplit("|", 1)[-1]
            text = "PRIMARY"
            if job_id.startswith("__control"):
                text = control_text
            elif case == "bound":
                text = bound_text
            outputs["web"][job_id] = _emit(text)
        result = ce.evaluate(table, outputs)
        return [f for f in result.defects if f.check == "C1"]

    def test_identical_to_the_control_is_dropped(self):
        (finding,) = self._judge("CONTROL")
        self.assertEqual(finding.finding_class, "bound-dropped")

    def test_differs_without_the_variable_is_frozen(self):
        (finding,) = self._judge("width: 0")
        self.assertEqual(finding.finding_class, "bound-frozen")

    def test_a_leak_in_code_position_is_uncompilable(self):
        (finding,) = self._judge("width = @{juiProbeValue}.dp")
        self.assertEqual(finding.finding_class, "bound-uncompilable")
        self.assertEqual(finding.evidence["leak"], "width = @{juiProbeValue}.dp")

    def test_a_leak_inside_a_string_is_a_literal_leak(self):
        (finding,) = self._judge('Text("@{juiProbeValue}")')
        self.assertEqual(finding.finding_class, "bound-literal-leak")

    def test_the_leak_check_runs_before_the_variable_name_check(self):
        """The regression that motivated all of this.

        `@{juiProbeValue}` CONTAINS `juiProbeValue`, so a name-only test reads
        a leak as a pass. If this ever goes green with an empty finding list,
        85 defects have gone quiet again.
        """
        self.assertIn(ce.BINDING_VAR, "width = @{juiProbeValue}.dp")
        self.assertTrue(self._judge("width = @{juiProbeValue}.dp"))

    def test_a_resolved_binding_passes(self):
        self.assertEqual(self._judge("width: data.juiProbeValue"), [])


class CompanionDerivationTest(unittest.TestCase):
    """Companions come from the ledger. Nothing here may hard-code a pair."""

    LEDGER = {
        "border": {
            "widthAlone": "no-draw",
            "styleAlone": "no-draw",
            "observable": {
                "common/borderWidth__static": "uniformly-inert",
                "common/borderColor__static": "uniformly-inert",
            },
        },
        "unrelated": {
            "someKey": "a value",
            "observable": {"common/opacity__static": "uniformly-active"},
        },
    }
    DEFINITIONS = {
        "common": {
            "borderWidth": {"type": "number"},
            "borderColor": {"type": "string"},
            "opacity": {"type": "number"},
        }
    }

    def test_an_alone_no_draw_topic_pairs_its_members(self):
        specs = comp.derive(self.LEDGER, self.DEFINITIONS)
        width = specs[("common", "borderWidth")]
        self.assertEqual(list(width.companions), ["borderColor"])
        self.assertEqual(width.kind, "ATTRIBUTE_PAIR")
        self.assertFalse(width.provisional)

    def test_the_pairing_is_symmetric(self):
        specs = comp.derive(self.LEDGER, self.DEFINITIONS)
        self.assertEqual(
            list(specs[("common", "borderColor")].companions), ["borderWidth"]
        )

    def test_a_topic_without_an_alone_key_is_not_paired(self):
        specs = comp.derive(self.LEDGER, self.DEFINITIONS)
        self.assertNotIn(("common", "opacity"), specs)

    def test_the_derivation_names_the_ledger_statement_it_came_from(self):
        spec = comp.derive(self.LEDGER, self.DEFINITIONS)[("common", "borderWidth")]
        self.assertIn("semantics.border", spec.source)
        self.assertIn("widthAlone", spec.source)

    def test_the_real_ledger_pairs_the_border_family(self):
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parents[2] / "shared" / "core"
        ledger = json.loads((root / "attribute_semantics.json").read_text("utf-8"))
        definitions = json.loads((root / "attribute_definitions.json").read_text("utf-8"))
        specs = comp.derive(ledger["semantics"], definitions)
        self.assertIn(("common", "borderWidth"), specs)
        self.assertIn("borderColor", specs[("common", "borderWidth")].companions)

    def test_the_real_ledger_pairs_the_highlight_family(self):
        """The pairing `View.highlighted` used to get from PROVISIONAL.

        It was the one unledgered family plan 41 probed on an informed guess;
        49-E wrote the ruling from that measurement, so the pairing must now
        come from the ledger — with a source naming it, and provisional off.
        """
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parents[2] / "shared" / "core"
        ledger = json.loads((root / "attribute_semantics.json").read_text("utf-8"))
        definitions = json.loads((root / "attribute_definitions.json").read_text("utf-8"))
        specs = comp.derive(ledger["semantics"], definitions)
        highlighted = specs[("View", "highlighted")]
        self.assertIn("highlightBackground", highlighted.companions)
        self.assertFalse(highlighted.provisional)
        self.assertIn("semantics.highlight", highlighted.source)

    def test_a_provisional_spec_says_so_and_says_why(self):
        """Every PROVISIONAL entry must announce itself as an unruled gap.

        Asserted over whatever the table holds rather than over one named
        family: the table is empty in the healthy state (a provisional probe
        exists to be retired into the ledger), and the contract still has to
        hold for the next entry someone adds.
        """
        for spec in comp.PROVISIONAL:
            with self.subTest(spec=spec.key):
                self.assertTrue(spec.provisional)
                self.assertTrue(spec.reason)
                self.assertEqual(spec.source, "")
                self.assertEqual(spec.kind, "PROVISIONAL")

    def test_state_gated_families_are_reported_not_probed(self):
        rows = comp.unmeasurable_report()
        attributes = {a for row in rows for a in row["attributes"]}
        self.assertIn("NetworkImage.errorImage", attributes)
        for row in rows:
            self.assertTrue(row["reason"])


class CompanionApplicationTest(unittest.TestCase):
    """Companions must reach BOTH sides, or the probe measures the companion.

    The example attribute must be one with NO base companion of its own, or
    `test_without_a_spec_no_companion_is_written` cannot tell the two sources
    apart. It used `View.borderWidth`, which acquired a `borderColor` base
    companion when the border fixtures were paired up (lane E2's shaping
    queue) — the assertion then failed on the BASE companion while the spec
    mechanism it is testing was working exactly as before. `View.opacity`
    carries no base attributes, so it distinguishes them again.
    """

    DEFINITIONS = {"View": {"opacity": _defn(type=["number", "binding"])}}
    SPEC = comp.CompanionSpec(
        component="View",
        attribute="opacity",
        companions={"borderColor": "#FF0000"},
        source="test",
        kind="ATTRIBUTE_PAIR",
    )

    def _targets(self, companion_specs):
        table = ce.build_jobs(
            self.DEFINITIONS, platforms=("web",), companion_specs=companion_specs
        )
        return {
            ("control" if job["id"].startswith("__control")
             else job["id"].rsplit("|", 1)[-1]): ce._target_node(job["node"])
            for job in table.jobs["web"]
        }

    def test_without_a_spec_no_companion_is_written(self):
        targets = self._targets(None)
        self.assertNotIn("borderColor", targets["primary"])

    def test_the_companion_reaches_the_control_too(self):
        targets = self._targets({("View", "opacity"): self.SPEC})
        self.assertEqual(targets["control"].get("borderColor"), "#FF0000")
        self.assertEqual(targets["primary"].get("borderColor"), "#FF0000")

    def test_the_companion_reaches_the_bound_case(self):
        targets = self._targets({("View", "opacity"): self.SPEC})
        self.assertEqual(targets["bound"].get("borderColor"), "#FF0000")
        self.assertEqual(targets["bound"].get("opacity"), ce.BOUND_VALUE)

    def test_the_control_still_does_not_carry_the_attribute_under_test(self):
        targets = self._targets({("View", "opacity"): self.SPEC})
        self.assertNotIn("opacity", targets["control"])

    def test_the_applied_spec_is_recorded_for_the_report(self):
        table = ce.build_jobs(
            self.DEFINITIONS,
            platforms=("web",),
            companion_specs={("View", "opacity"): self.SPEC},
        )
        self.assertEqual(list(table.paired), [("View", "opacity")])

    def test_an_unpaired_run_records_nothing(self):
        table = ce.build_jobs(self.DEFINITIONS, platforms=("web",))
        self.assertEqual(table.paired, {})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
