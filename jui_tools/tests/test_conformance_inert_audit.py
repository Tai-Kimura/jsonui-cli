"""Tests for the inert-verdict attribution audit (plan 34 Phase 0).

The audit's only job is completeness: every inert control-diff verdict is
either claimed by a ledger that already has an opinion about it, or it is in
the adjudication queue. So the contract pinned here is mostly about what must
NOT silently disappear.

- attribution is per (fixture, platform): a fixture ledgered on ios and
  unledgered on android is queued for android alone
- each of the four channels claims what it owns — control_diff assertions,
  cross_effect entries, contract observables, coverage gaps — and a coverage
  gap recorded for one platform does not excuse another
- an active verdict is never queued, and a fixture with no verdict at all is
  ``not-compared`` rather than an implicit pass
- the ``kind`` names WHY the existing checks missed it: single-platform scope
  and uniformly-inert-with-an-undeclared-value are the two structural holes
- mechanical triage only tags what it can prove (identical-to-control layout,
  value equal to the SSoT default, alias of a queued canonical); everything
  else stays ``untriaged`` for the human round
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.conformance import inert_audit as ia

ALL = ["ios", "android", "web"]


def _fixture(fid, component="common", attribute="x", value="v", platforms=None, **kw):
    entry = {
        "id": fid,
        "component": component,
        "attribute": attribute,
        "value": value,
        "platforms": list(platforms or ALL),
        "control": "__control/View",
        "layout": f"fixtures/{fid}.layout.json",
    }
    entry.update(kw)
    return entry


def _manifest(*fixtures):
    return {
        "fixtures": [
            {"id": "__control/View", "isControl": True, "platforms": ALL},
            *fixtures,
        ]
    }


def _verdicts(**by_platform):
    return {p: dict(v) for p, v in by_platform.items()}


def _audit(manifest, verdicts, platforms=None, **kw):
    return ia.audit(manifest, verdicts, platforms or ALL, **kw)


class AttributionTest(unittest.TestCase):
    def test_inert_with_no_ledger_is_queued(self):
        manifest = _manifest(_fixture("common/a__static"))
        result = _audit(manifest, _verdicts(**{p: {"common/a__static": "inert"} for p in ALL}))
        self.assertEqual([i.fixture for i in result.items], ["common/a__static"])
        self.assertEqual(result.items[0].inert_on, ALL)
        self.assertEqual(result.unattributed, {"ios": 1, "android": 1, "web": 1})

    def test_active_is_never_queued(self):
        manifest = _manifest(_fixture("common/a__static"))
        result = _audit(manifest, _verdicts(**{p: {"common/a__static": "active"} for p in ALL}))
        self.assertEqual(result.items, [])
        self.assertEqual(result.measured, {"ios": 0, "android": 0, "web": 0})

    def test_control_diff_assertion_claims_it(self):
        # Asserted active on ios: an inert verdict there is already a
        # control_diff regression, so it must not be queued a second time.
        manifest = _manifest(_fixture("common/a__static"))
        result = _audit(
            manifest,
            _verdicts(**{p: {"common/a__static": "inert"} for p in ALL}),
            control_diff_ledger={"common/a__static": {"ios"}},
        )
        self.assertEqual(result.items[0].inert_on, ["android", "web"])
        self.assertEqual(result.attributed["ios"][ia.CHANNEL_CONTROL_DIFF], 1)

    def test_cross_effect_entry_claims_every_platform(self):
        manifest = _manifest(_fixture("common/a__static"))
        result = _audit(
            manifest,
            _verdicts(**{p: {"common/a__static": "inert"} for p in ALL}),
            cross_effect_ledger={"common/a__static": {"reason": "adjudicated"}},
        )
        self.assertEqual(result.items, [])
        self.assertEqual(
            [result.attributed[p][ia.CHANNEL_CROSS_EFFECT] for p in ALL], [1, 1, 1]
        )

    def test_contract_observable_claims_every_platform(self):
        manifest = _manifest(_fixture("common/a__static"))
        result = _audit(
            manifest,
            _verdicts(**{p: {"common/a__static": "inert"} for p in ALL}),
            contract={"common/a__static": "uniformly-inert"},
        )
        self.assertEqual(result.items, [])
        self.assertEqual(
            [result.attributed[p][ia.CHANNEL_CONTRACT] for p in ALL], [1, 1, 1]
        )

    def test_coverage_gap_claims_only_its_own_platform(self):
        manifest = _manifest(_fixture("Slider/step__static", component="Slider", attribute="step"))
        result = _audit(
            manifest,
            _verdicts(**{p: {"Slider/step__static": "inert"} for p in ALL}),
            coverage={("Slider", "step", "web")},
        )
        self.assertEqual(result.items[0].inert_on, ["ios", "android"])
        self.assertEqual(result.attributed["web"][ia.CHANNEL_COVERAGE], 1)
        self.assertEqual(result.attributed["ios"][ia.CHANNEL_COVERAGE], 0)

    def test_out_of_scope_platform_contributes_nothing(self):
        manifest = _manifest(_fixture("common/a__static", platforms=["ios", "android"]))
        result = _audit(manifest, _verdicts(**{p: {"common/a__static": "inert"} for p in ALL}))
        self.assertEqual(result.items[0].scope, ["ios", "android"])
        self.assertEqual(result.items[0].inert_on, ["ios", "android"])
        self.assertEqual(result.measured["web"], 0)

    def test_controls_and_control_less_fixtures_are_not_audited(self):
        manifest = _manifest(_fixture("common/a__static", control=None))
        result = _audit(manifest, _verdicts(**{p: {"common/a__static": "inert"} for p in ALL}))
        self.assertEqual(result.items, [])


class KindTest(unittest.TestCase):
    def test_single_platform_scope(self):
        manifest = _manifest(_fixture("Web/allow__static", platforms=["web"]))
        result = _audit(manifest, _verdicts(web={"Web/allow__static": "inert"}))
        self.assertEqual(result.items[0].kind, ia.KIND_SINGLE_PLATFORM)

    def test_uniform_inert_undeclared_value(self):
        manifest = _manifest(_fixture("common/a__static"))
        result = _audit(manifest, _verdicts(**{p: {"common/a__static": "inert"} for p in ALL}))
        self.assertEqual(result.items[0].kind, ia.KIND_UNIFORM_UNDECLARED)

    def test_uniform_inert_declared_value(self):
        manifest = _manifest(_fixture("common/a__enumvalue"))
        result = _audit(
            manifest,
            _verdicts(**{p: {"common/a__enumvalue": "inert"} for p in ALL}),
            enum_values={"common/a__enumvalue": "leftAligned"},
        )
        self.assertEqual(result.items[0].kind, ia.KIND_UNIFORM_DECLARED)

    def test_divergent_inert_side(self):
        manifest = _manifest(_fixture("common/a__static"))
        result = _audit(
            manifest,
            _verdicts(
                ios={"common/a__static": "active"},
                android={"common/a__static": "inert"},
                web={"common/a__static": "active"},
            ),
        )
        self.assertEqual(result.items[0].kind, ia.KIND_DIVERGENT_SIDE)
        self.assertEqual(result.items[0].inert_on, ["android"])

    def test_missing_verdict_is_not_compared(self):
        manifest = _manifest(_fixture("common/a__static"))
        result = _audit(
            manifest,
            _verdicts(
                ios={"common/a__static": "inert"},
                android={"common/a__static": "inert"},
            ),
        )
        self.assertEqual(result.items[0].kind, ia.KIND_NOT_COMPARED)
        self.assertIsNone(result.items[0].verdicts["web"])


class TriageTest(unittest.TestCase):
    def _queued(self, manifest, **kw):
        result = _audit(
            manifest,
            _verdicts(**{p: {f["id"]: "inert" for f in manifest["fixtures"][1:]} for p in ALL}),
        )
        return ia.triage(result, manifest=manifest, **kw)

    def test_untriaged_by_default(self):
        manifest = _manifest(_fixture("common/a__static"))
        result = self._queued(manifest)
        self.assertEqual(result.items[0].family, ia.FAMILY_UNTRIAGED)
        self.assertEqual(result.items[0].evidence, "")
        self.assertEqual(len(result.untriaged), 1)

    def test_control_identical_layout(self):
        manifest = _manifest(_fixture("Image/src__static", component="Image", attribute="src"))
        result = self._queued(
            manifest, control_identical={"Image/src__static": "__control/Image"}
        )
        self.assertEqual(result.items[0].family, ia.FAMILY_CONTROL_IDENTICAL)
        self.assertIn("__control/Image", result.items[0].evidence)
        self.assertEqual(result.untriaged, [])

    def test_value_equal_to_the_ssot_default(self):
        manifest = _manifest(
            _fixture("common/borderStyle__solid", attribute="borderStyle", value="solid")
        )
        result = self._queued(manifest, defaults={("common", "borderStyle"): "solid"})
        self.assertEqual(result.items[0].family, ia.FAMILY_VALUE_IS_DEFAULT)

    def test_a_differing_default_does_not_match(self):
        manifest = _manifest(
            _fixture("common/borderStyle__dashed", attribute="borderStyle", value="dashed")
        )
        result = self._queued(manifest, defaults={("common", "borderStyle"): "solid"})
        self.assertEqual(result.items[0].family, ia.FAMILY_UNTRIAGED)

    def test_type_fallback_value(self):
        manifest = _manifest(
            _fixture(
                "TextField/hintFont__static",
                component="TextField",
                attribute="hintFont",
                value="sample",
            )
        )
        result = self._queued(manifest, fallback_values=("sample", 8))
        self.assertEqual(result.items[0].family, ia.FAMILY_TYPE_FALLBACK_VALUE)
        self.assertIn("rules.py", result.items[0].evidence)

    def test_numeric_type_fallback_value(self):
        # 8 is also what platforms pick as their own default spacing — the
        # kjui CheckBox literally reads `json_data['spacing'] || 8`.
        manifest = _manifest(
            _fixture(
                "CheckBox/spacing__static",
                component="CheckBox",
                attribute="spacing",
                value=8,
            )
        )
        result = self._queued(manifest, fallback_values=("sample", 8))
        self.assertEqual(result.items[0].family, ia.FAMILY_TYPE_FALLBACK_VALUE)

    def test_a_domain_value_is_not_a_type_fallback(self):
        manifest = _manifest(_fixture("Label/hint__static", value="Conformance Hint"))
        result = self._queued(manifest, fallback_values=("sample", 8))
        self.assertEqual(result.items[0].family, ia.FAMILY_UNTRIAGED)

    def test_alias_of_a_queued_canonical(self):
        manifest = _manifest(
            _fixture("Slider/maximum__static", component="Slider", attribute="maximum"),
            _fixture(
                "Slider/maximum__alias_maxValue",
                component="Slider",
                attribute="maximum",
                aliasOf="Slider/maximum__static",
            ),
        )
        result = self._queued(manifest)
        families = {i.fixture: i.family for i in result.items}
        self.assertEqual(
            families["Slider/maximum__alias_maxValue"], ia.FAMILY_ALIAS_OF_QUEUED
        )
        # The canonical is the one somebody has to adjudicate.
        self.assertEqual(families["Slider/maximum__static"], ia.FAMILY_UNTRIAGED)

    def test_alias_whose_canonical_is_adjudicated_is_not_excused(self):
        # Canonical claimed by the cross-effect ledger, alias not: the alias
        # is a separate spelling and must be adjudicated on its own.
        manifest = _manifest(
            _fixture("Slider/maximum__static", component="Slider", attribute="maximum"),
            _fixture(
                "Slider/maximum__alias_maxValue",
                component="Slider",
                attribute="maximum",
                aliasOf="Slider/maximum__static",
            ),
        )
        result = _audit(
            manifest,
            _verdicts(**{
                p: {
                    "Slider/maximum__static": "inert",
                    "Slider/maximum__alias_maxValue": "inert",
                }
                for p in ALL
            }),
            cross_effect_ledger={"Slider/maximum__static": {"reason": "adjudicated"}},
        )
        ia.triage(result, manifest=manifest)
        self.assertEqual([i.fixture for i in result.items], ["Slider/maximum__alias_maxValue"])
        self.assertEqual(result.items[0].family, ia.FAMILY_UNTRIAGED)


class SiblingValueTest(unittest.TestCase):
    """The one hypothesis a screenshot round is expensive to rule out."""

    def _setup(self, verdicts_by_platform, inert_platforms=ALL):
        manifest = _manifest(
            _fixture("Label/textTransform__none", component="Label",
                     attribute="textTransform", value="none", platforms=inert_platforms),
            _fixture("Label/textTransform__uppercase", component="Label",
                     attribute="textTransform", value="uppercase", platforms=inert_platforms),
            _fixture("Label/lines__static", component="Label", attribute="lines", value=2,
                     platforms=inert_platforms),
        )
        result = _audit(manifest, verdicts_by_platform, inert_platforms)
        proof = ia.sibling_value_evidence(manifest, verdicts_by_platform, result)
        ia.triage(result, manifest=manifest, sibling_active=proof)
        return result, proof

    def test_active_sibling_on_every_unattributed_platform(self):
        verdicts = _verdicts(**{
            p: {
                "Label/textTransform__none": "inert",
                "Label/textTransform__uppercase": "active",
                "Label/lines__static": "inert",
            }
            for p in ALL
        })
        result, proof = self._setup(verdicts)
        families = {i.fixture: i.family for i in result.items}
        self.assertEqual(
            families["Label/textTransform__none"], ia.FAMILY_SIBLING_VALUE_ACTIVE
        )
        self.assertEqual(
            proof["Label/textTransform__none"],
            {p: ["Label/textTransform__uppercase"] for p in ALL},
        )
        # `lines` has no sibling at all — nothing to demonstrate.
        self.assertEqual(families["Label/lines__static"], ia.FAMILY_UNTRIAGED)

    def test_one_platform_reading_it_does_not_excuse_another(self):
        verdicts = _verdicts(
            ios={
                "Label/textTransform__none": "inert",
                "Label/textTransform__uppercase": "active",
                "Label/lines__static": "inert",
            },
            android={
                "Label/textTransform__none": "inert",
                "Label/textTransform__uppercase": "inert",
                "Label/lines__static": "inert",
            },
            web={
                "Label/textTransform__none": "inert",
                "Label/textTransform__uppercase": "active",
                "Label/lines__static": "inert",
            },
        )
        result, proof = self._setup(verdicts)
        families = {i.fixture: i.family for i in result.items}
        # android has no live demonstration, so the whole item stays open.
        self.assertNotIn("Label/textTransform__none", proof)
        self.assertEqual(families["Label/textTransform__none"], ia.FAMILY_UNTRIAGED)

    def test_a_fixture_is_not_its_own_sibling(self):
        verdicts = _verdicts(**{
            p: {
                "Label/textTransform__none": "inert",
                "Label/textTransform__uppercase": "inert",
                "Label/lines__static": "inert",
            }
            for p in ALL
        })
        _result, proof = self._setup(verdicts)
        self.assertEqual(proof, {})


class LoaderTest(unittest.TestCase):
    def test_coverage_gaps_expands_platforms(self):
        doc = {
            "entries": [
                {"component": "Slider", "attribute": "step", "platforms": ["web", "ios"]},
                {"component": "View", "attribute": "direction", "platforms": ["ios"]},
                {"attribute": "orphan", "platforms": ["web"]},
            ]
        }
        self.assertEqual(
            ia.coverage_gaps(doc),
            {("Slider", "step", "web"), ("Slider", "step", "ios"), ("View", "direction", "ios")},
        )

    def test_attribute_defaults_reads_only_declared_defaults(self):
        defs = {
            "_comment": "not a component",
            "common": {"borderStyle": {"default": "solid"}, "width": {"type": "string"}},
            "Collection": {"lazy": {"default": "lazy"}},
        }
        self.assertEqual(
            ia.attribute_defaults(defs),
            {("common", "borderStyle"): "solid", ("Collection", "lazy"): "lazy"},
        )

    def test_control_identical_ignores_the_generated_banner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "fixtures").mkdir()
            body = {"type": "View", "child": [{"type": "Image", "src": "sample"}]}
            (root / "fixtures" / "control.layout.json").write_text(
                json.dumps({"_generated": {"sentinel": "@generated"}, **body})
            )
            (root / "fixtures" / "same.layout.json").write_text(
                json.dumps({"_generated": {"sentinel": "@generated", "extra": 1}, **body})
            )
            (root / "fixtures" / "other.layout.json").write_text(
                json.dumps({"_generated": {}, "type": "View", "child": []})
            )
            manifest = {
                "fixtures": [
                    {
                        "id": "__control/Image",
                        "isControl": True,
                        "layout": "fixtures/control.layout.json",
                    },
                    {
                        "id": "Image/src__static",
                        "control": "__control/Image",
                        "layout": "fixtures/same.layout.json",
                    },
                    {
                        "id": "Image/other__static",
                        "control": "__control/Image",
                        "layout": "fixtures/other.layout.json",
                    },
                    {
                        "id": "Image/missing__static",
                        "control": "__control/Image",
                        "layout": "fixtures/gone.layout.json",
                    },
                ]
            }
            self.assertEqual(
                ia.control_identical_fixtures(root, manifest),
                {"Image/src__static": "__control/Image"},
            )


class RenderTest(unittest.TestCase):
    def test_queue_json_carries_counts_and_is_deterministic(self):
        manifest = _manifest(
            _fixture("common/b__static"),
            _fixture("common/a__static"),
        )
        result = _audit(
            manifest,
            _verdicts(**{
                p: {"common/a__static": "inert", "common/b__static": "inert"} for p in ALL
            }),
            contract={"common/b__static": "uniformly-inert"},
        )
        ia.triage(result, manifest=manifest)
        rendered = ia.render_queue(result)
        self.assertEqual(rendered, ia.render_queue(result))
        doc = json.loads(rendered)
        self.assertEqual(doc["schemaVersion"], ia.SCHEMA_VERSION)
        self.assertEqual([e["fixture"] for e in doc["entries"]], ["common/a__static"])
        self.assertEqual(doc["counts"]["queuedFixtures"], 1)
        self.assertEqual(doc["counts"]["untriagedFixtures"], 1)
        self.assertEqual(doc["counts"]["unattributed"], {"ios": 1, "android": 1, "web": 1})
        self.assertEqual(
            doc["counts"]["attributed"]["ios"][ia.CHANNEL_CONTRACT], 1
        )
        self.assertEqual(doc["entries"][0]["verdicts"], {p: "inert" for p in ALL})

    def test_entries_are_sorted_by_fixture_id(self):
        manifest = _manifest(
            _fixture("common/z__static"),
            _fixture("common/a__static"),
        )
        result = _audit(
            manifest,
            _verdicts(**{
                p: {"common/a__static": "inert", "common/z__static": "inert"} for p in ALL
            }),
        )
        self.assertEqual(
            [i.fixture for i in result.items], ["common/a__static", "common/z__static"]
        )


class CompletenessRatchetTest(unittest.TestCase):
    """The Phase 3 ledger: both directions, and neither of them vacuous."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _result(self, *fixture_ids, verdict="inert"):
        manifest = _manifest(*[_fixture(f) for f in fixture_ids])
        return _audit(
            manifest,
            _verdicts(**{p: {f: verdict for f in fixture_ids} for p in ALL}),
        )

    def test_an_unrecorded_inert_verdict_is_reported(self):
        # The whole point: an attribute that quietly stops rendering produces
        # a fixture identical to its control and nothing else. If this passed
        # silently the ratchet would be decoration.
        result = self._result("common/a__static")
        unrecorded, stale = ia.check_ledger(result, {})
        self.assertEqual([i.fixture for i in unrecorded], ["common/a__static"])
        self.assertEqual(stale, [])

    def test_a_recorded_verdict_is_accepted(self):
        result = self._result("common/a__static")
        path = ia.ledger_path(self.dir)
        ia.update_ledger(result, path)
        unrecorded, stale = ia.check_ledger(result, ia.load_ledger(path))
        self.assertEqual(unrecorded, [])
        self.assertEqual(stale, [])

    def test_an_entry_the_measurement_dropped_is_stale(self):
        recorded = self._result("common/a__static")
        path = ia.ledger_path(self.dir)
        ia.update_ledger(recorded, path)
        # The attribute got fixed: the fixture now differs from its control.
        fixed = self._result("common/a__static", verdict="active")
        unrecorded, stale = ia.check_ledger(fixed, ia.load_ledger(path))
        self.assertEqual(unrecorded, [])
        self.assertEqual(stale, ["common/a__static"])

    def test_a_changed_platform_set_is_not_silently_accepted(self):
        manifest = _manifest(_fixture("common/a__static"))
        both = _audit(
            manifest, _verdicts(**{p: {"common/a__static": "inert"} for p in ALL})
        )
        path = ia.ledger_path(self.dir)
        ia.update_ledger(both, path)
        # Fixed on web only — the adjudication on file was about all three.
        partial = _audit(
            manifest,
            _verdicts(
                ios={"common/a__static": "inert"},
                android={"common/a__static": "inert"},
                web={"common/a__static": "active"},
            ),
        )
        unrecorded, _stale = ia.check_ledger(partial, ia.load_ledger(path))
        self.assertEqual([i.fixture for i in unrecorded], ["common/a__static"])

    def test_an_adjudicated_reason_survives_a_re_record(self):
        result = self._result("common/a__static")
        path = ia.ledger_path(self.dir)
        ia.update_ledger(result, path)
        doc = json.loads(path.read_text())
        doc["entries"][0]["reason"] = "adjudicated: the value equals the default"
        path.write_text(json.dumps(doc))
        ia.update_ledger(result, path)
        self.assertEqual(
            ia.load_ledger(path)["common/a__static"]["reason"],
            "adjudicated: the value equals the default",
        )

    def test_a_reason_does_NOT_survive_a_changed_fact(self):
        manifest = _manifest(_fixture("common/a__static"))
        path = ia.ledger_path(self.dir)
        ia.update_ledger(
            _audit(manifest, _verdicts(**{p: {"common/a__static": "inert"} for p in ALL})),
            path,
        )
        doc = json.loads(path.read_text())
        doc["entries"][0]["reason"] = "adjudicated: inert on all three by design"
        path.write_text(json.dumps(doc))
        ia.update_ledger(
            _audit(
                manifest,
                _verdicts(
                    ios={"common/a__static": "inert"},
                    android={"common/a__static": "inert"},
                    web={"common/a__static": "active"},
                ),
            ),
            path,
        )
        self.assertEqual(
            ia.load_ledger(path)["common/a__static"]["reason"], ia.UNREVIEWED
        )

    def test_a_missing_ledger_file_reads_as_empty_not_as_a_pass(self):
        self.assertEqual(ia.load_ledger(self.dir / "nope.json"), {})
        result = self._result("common/a__static")
        unrecorded, _ = ia.check_ledger(result, ia.load_ledger(self.dir / "nope.json"))
        self.assertEqual(len(unrecorded), 1)


class RealLedgerCountsTests(unittest.TestCase):
    """`counts` in the committed ledger must describe `entries`.

    It is derived by update_ledger, but the file is hand-adjudicated between
    runs — three lanes edited entries and left counts alone, so `unreviewed`
    still read 84 from the first bake while the real figure had fallen to 74.
    A number nobody recomputes is read by people who do not read the entries.
    """

    @staticmethod
    def _ledger():
        import json
        from pathlib import Path

        path = Path(__file__).resolve().parents[2] / "conformance" / "inert_audit.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_counts_match_the_entries_they_describe(self):
        doc = self._ledger()
        entries = doc["entries"]
        self.assertEqual(doc["counts"]["entries"], len(entries))
        self.assertEqual(
            doc["counts"]["unreviewed"],
            sum(1 for e in entries if e["reason"] == ia.UNREVIEWED),
        )

    def test_an_added_entry_that_forgets_counts_fails(self):
        """The regression this guards is adding a row and not recounting.

        Asserted by doing exactly that to a copy — not by editing `counts`,
        which would only prove the comparison runs.
        """
        doc = self._ledger()
        doc["entries"].append(
            {
                "fixture": "common/invented__static",
                "component": "common",
                "attribute": "invented",
                "inertOn": ["web"],
                "kind": "uniform-inert-undeclared-value",
                "family": "untriaged",
                "reason": ia.UNREVIEWED,
                "note": "",
            }
        )
        self.assertNotEqual(doc["counts"]["entries"], len(doc["entries"]))
        self.assertNotEqual(
            doc["counts"]["unreviewed"],
            sum(1 for e in doc["entries"] if e["reason"] == ia.UNREVIEWED),
        )


if __name__ == "__main__":
    unittest.main()
