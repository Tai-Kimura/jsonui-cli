"""Tests for the typed-attribute codegen intermediate model.

Covers the classification matrix (alias / enum / binding / dimension /
raw fallback / skip) plus a sanity pass over the real bundled
``shared/core/attribute_definitions.json``.
"""
from __future__ import annotations

import unittest

from jui_cli.generators.attr_codegen.model import (
    AttrKind,
    Attribute,
    SkippedAttr,
    build_model,
    classify_attr,
    default_definitions_path,
    load_model,
    skipped_payload,
)


class ClassifyAttrTests(unittest.TestCase):
    def test_plain_string(self):
        attr = classify_attr("common", "id", {"type": "string", "description": "d"})
        self.assertIsInstance(attr, Attribute)
        self.assertEqual(attr.kind, AttrKind.STRING)
        self.assertFalse(attr.bindable)

    def test_bindable_string(self):
        attr = classify_attr("Label", "text", {"type": ["string", "binding"]})
        self.assertEqual(attr.kind, AttrKind.STRING)
        self.assertTrue(attr.bindable)

    def test_binding_only_is_not_attrvalue_wrapped(self):
        attr = classify_attr("common", "onClick", {"type": "binding"})
        self.assertEqual(attr.kind, AttrKind.BINDING)
        self.assertFalse(attr.bindable)

    def test_enum_with_string_type(self):
        attr = classify_attr(
            "common",
            "visibility",
            {"type": ["string", "binding"], "enum": ["visible", "invisible", "gone"]},
        )
        self.assertEqual(attr.kind, AttrKind.ENUM)
        self.assertTrue(attr.bindable)
        self.assertEqual(attr.enum_values, ("visible", "invisible", "gone"))

    def test_number_enum_is_plain_number(self):
        # SelectBox.minuteInterval — numeric enum values can't become a
        # string-raw-value language enum; typed as NUMBER.
        attr = classify_attr(
            "SelectBox", "minuteInterval", {"type": "number", "enum": [1, 5, 10]}
        )
        self.assertEqual(attr.kind, AttrKind.NUMBER)
        self.assertEqual(attr.enum_values, ())

    def test_dimension_union(self):
        attr = classify_attr(
            "common",
            "width",
            {
                "type": ["number", {"enum": ["matchParent", "wrapContent"]}, "binding"],
                "required": True,
            },
        )
        self.assertEqual(attr.kind, AttrKind.DIMENSION)
        self.assertTrue(attr.bindable)
        self.assertTrue(attr.required)
        self.assertEqual(attr.dimension_keywords, ("matchParent", "wrapContent"))

    def test_multi_type_union_falls_back_to_raw(self):
        attr = classify_attr("common", "shadow", {"type": ["string", "object"]})
        self.assertEqual(attr.kind, AttrKind.RAW)
        self.assertEqual(attr.raw_kinds, ("string", "object"))

    def test_enum_with_array_union_falls_back_to_raw(self):
        # common.gravity: ["string", "array"] + enum — no clean enum repr.
        attr = classify_attr(
            "common", "gravity", {"type": ["string", "array"], "enum": ["top", "left"]}
        )
        self.assertEqual(attr.kind, AttrKind.RAW)

    def test_aliases_preserved(self):
        attr = classify_attr(
            "common", "opacity", {"type": ["number", "binding"], "aliases": ["alpha"]}
        )
        self.assertEqual(attr.aliases, ("alpha",))

    def test_deprecated_carried(self):
        attr = classify_attr(
            "Label",
            "edgeInset",
            {"type": "number", "deprecated": True, "deprecation_note": "use padding"},
        )
        self.assertTrue(attr.deprecated)
        self.assertEqual(attr.deprecation_note, "use padding")

    def test_callback_is_skipped(self):
        result = classify_attr("Collection", "onItemAppear", {"type": "callback"})
        self.assertIsInstance(result, SkippedAttr)
        self.assertIn("callback", result.reason)

    def test_metadata_is_skipped(self):
        result = classify_attr("common", "generatedBy", {"type": "string"})
        self.assertIsInstance(result, SkippedAttr)
        self.assertIn("metadata", result.reason)

    def test_dollar_prefixed_marker_is_skipped(self):
        # $jui is the normalizer marker; $ is not a valid Swift/Kotlin identifier.
        result = classify_attr("common", "$jui", {"type": "object"})
        self.assertIsInstance(result, SkippedAttr)
        self.assertIn("metadata", result.reason)

    def test_color_kind(self):
        attr = classify_attr("common", "background", {"type": "color"})
        self.assertEqual(attr.kind, AttrKind.COLOR)

    def test_any_kind(self):
        attr = classify_attr("Radio", "value", {"type": "any"})
        self.assertEqual(attr.kind, AttrKind.ANY)

    def test_unknown_single_type_never_crashes(self):
        attr = classify_attr("X", "weird", {"type": "quaternion"})
        self.assertEqual(attr.kind, AttrKind.RAW)
        self.assertEqual(attr.raw_kinds, ("quaternion",))


class BuildModelTests(unittest.TestCase):
    DEFS = {
        "_comment": "test",
        "common": {
            "_comment": "shared",
            "id": {"type": "string"},
            "tintColor": {"type": "string"},
            "generatedBy": {"type": "string"},
        },
        "Switch": {
            "tintColor": {"type": "string"},
            "onValueChange": {"type": "binding"},
        },
        "Collection": {
            "onItemAppear": {"type": "callback"},
            "layout": {"type": "string", "enum": ["vertical", "horizontal"]},
        },
    }

    def test_component_order_and_attr_order_deterministic(self):
        model = build_model(self.DEFS)
        self.assertEqual([c.name for c in model.components], ["Collection", "Switch"])
        self.assertEqual([a.name for a in model.common.attrs], ["id", "tintColor"])

    def test_common_overrides_detected(self):
        model = build_model(self.DEFS)
        switch = next(c for c in model.components if c.name == "Switch")
        self.assertEqual(switch.common_overrides, ("tintColor",))

    def test_skip_list(self):
        model = build_model(self.DEFS)
        skipped = {(s.component, s.name) for s in model.skipped}
        self.assertEqual(
            skipped, {("Collection", "onItemAppear"), ("common", "generatedBy")}
        )

    def test_skipped_payload_shape(self):
        payload = skipped_payload(build_model(self.DEFS))
        self.assertIn("@generated", payload["_comment"])
        self.assertEqual(len(payload["skipped"]), 2)
        entry = payload["skipped"][0]
        self.assertEqual(
            set(entry), {"component", "attribute", "type", "reason"}
        )


class RealDefinitionsTests(unittest.TestCase):
    """Sanity over the bundled SSoT file — guards against shape drift."""

    @classmethod
    def setUpClass(cls):
        cls.model = load_model()

    def test_definitions_file_exists(self):
        self.assertTrue(default_definitions_path().exists())

    def test_component_counts(self):
        # 31 top-level keys = _comment + common + 29 components
        self.assertEqual(len(self.model.components), 29)
        self.assertGreaterEqual(len(self.model.common.attrs), 140)

    def test_known_skips_present(self):
        skipped = {(s.component, s.name) for s in self.model.skipped}
        self.assertIn(("Collection", "onItemAppear"), skipped)
        self.assertIn(("Collection", "onPageChanged"), skipped)
        self.assertIn(("common", "generatedBy"), skipped)

    def test_width_height_are_bindable_dimensions(self):
        by_name = {a.name: a for a in self.model.common.attrs}
        for name in ("width", "height"):
            self.assertEqual(by_name[name].kind, AttrKind.DIMENSION)
            self.assertTrue(by_name[name].bindable)
        self.assertEqual(
            self.model.dimension_keyword_sets, [("matchParent", "wrapContent")]
        )

    def test_known_alias_resolution_inputs(self):
        by_name = {a.name: a for a in self.model.common.attrs}
        self.assertEqual(by_name["opacity"].aliases, ("alpha",))

    def test_no_crash_kinds(self):
        # Every attribute classified into a known kind (never crashes).
        for comp in self.model.all_components():
            for attr in comp.attrs:
                self.assertIsInstance(attr.kind, AttrKind)


if __name__ == "__main__":
    unittest.main()
