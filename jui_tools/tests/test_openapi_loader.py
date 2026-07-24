"""Tests for openapi_loader — schema parsing + ERROR halt rules.

Covers the §3.3 invariants from the plan:

- ``oneOf`` / ``anyOf`` / discriminator halts
- multi-file ``$ref`` halts
- direct self-reference halts; collection-mediated cycle OK
- inline-derived name collision halts
- ``type: object`` with no shape halts
- string/integer enums, ``x-enum-varnames``
- ``allOf`` flattening
- ``additionalProperties`` typed-map ↔ inline object
"""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.core.openapi_loader import (
    OpenAPILoadError,
    is_swagger_file,
    load_swagger,
    parse_swagger,
)
from jui_cli.core.schema_filter import SchemaFilterConfig
from jui_cli.core.schema_ir import PrimitiveKind


def _doc(schemas: dict, info: dict | None = None) -> dict:
    return {
        "openapi": "3.0.3",
        "info": info or {"title": "Test", "version": "1.0.0"},
        "components": {"schemas": schemas},
    }


class IsSwaggerFileTests(unittest.TestCase):
    def test_openapi_3(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({"openapi": "3.0.3", "info": {}}, f)
            path = Path(f.name)
        try:
            self.assertTrue(is_swagger_file(path))
        finally:
            path.unlink()

    def test_swagger_2(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({"swagger": "2.0", "info": {}}, f)
            path = Path(f.name)
        try:
            self.assertTrue(is_swagger_file(path))
        finally:
            path.unlink()

    def test_non_swagger_json(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({"hello": "world"}, f)
            path = Path(f.name)
        try:
            self.assertFalse(is_swagger_file(path))
        finally:
            path.unlink()

    def test_malformed_json(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            f.write("not json{{{")
            path = Path(f.name)
        try:
            self.assertFalse(is_swagger_file(path))
        finally:
            path.unlink()


class PrimitiveFieldsTests(unittest.TestCase):
    def test_string_int_bool_double(self):
        doc = parse_swagger(_doc({
            "User": {
                "type": "object",
                "required": ["id", "active"],
                "properties": {
                    "id": {"type": "string"},
                    "age": {"type": "integer"},
                    "score": {"type": "number"},
                    "active": {"type": "boolean"},
                },
            },
        }), "test.json")
        self.assertEqual(len(doc.schemas), 1)
        user = doc.schemas[0]
        self.assertEqual(user.name, "User")
        self.assertEqual([f.wire_name for f in user.fields], ["id", "age", "score", "active"])
        kinds = [f.type.primitive for f in user.fields]
        self.assertEqual(kinds, [
            PrimitiveKind.STRING,
            PrimitiveKind.INTEGER,
            PrimitiveKind.DOUBLE,
            PrimitiveKind.BOOLEAN,
        ])

    def test_int32_int64_float(self):
        doc = parse_swagger(_doc({
            "M": {
                "type": "object",
                "properties": {
                    "a": {"type": "integer", "format": "int32"},
                    "b": {"type": "integer", "format": "int64"},
                    "c": {"type": "number", "format": "float"},
                },
            },
        }), "test.json")
        kinds = [f.type.primitive for f in doc.schemas[0].fields]
        self.assertEqual(kinds, [
            PrimitiveKind.INTEGER_32,
            PrimitiveKind.INTEGER_64,
            PrimitiveKind.FLOAT,
        ])

    def test_format_hint_for_string_is_discarded(self):
        """date-time / uuid / binary all collapse to STRING (Q9 — v1)."""
        doc = parse_swagger(_doc({
            "M": {
                "type": "object",
                "properties": {
                    "a": {"type": "string", "format": "date-time"},
                    "b": {"type": "string", "format": "uuid"},
                    "c": {"type": "string", "format": "binary"},
                },
            },
        }), "test.json")
        for f in doc.schemas[0].fields:
            self.assertEqual(f.type.primitive, PrimitiveKind.STRING)

    def test_required_vs_optional(self):
        doc = parse_swagger(_doc({
            "M": {
                "type": "object",
                "required": ["a"],
                "properties": {
                    "a": {"type": "string"},
                    "b": {"type": "string"},
                    "c": {"type": "string", "nullable": True},
                },
            },
        }), "test.json")
        a, b, c = doc.schemas[0].fields
        self.assertTrue(a.required)
        self.assertFalse(a.type.nullable)
        self.assertFalse(b.required)
        self.assertTrue(b.type.nullable)
        self.assertTrue(c.type.nullable)

    def test_description_and_deprecated(self):
        doc = parse_swagger(_doc({
            "M": {
                "type": "object",
                "properties": {
                    "a": {
                        "type": "string",
                        "description": "user name",
                        "deprecated": True,
                    },
                },
            },
        }), "test.json")
        f = doc.schemas[0].fields[0]
        self.assertEqual(f.description, "user name")
        self.assertTrue(f.deprecated)


class RefAndArrayTests(unittest.TestCase):
    def test_object_ref(self):
        doc = parse_swagger(_doc({
            "Address": {"type": "object", "properties": {"city": {"type": "string"}}},
            "User": {
                "type": "object",
                "properties": {
                    "home": {"$ref": "#/components/schemas/Address"},
                },
            },
        }), "test.json")
        user = next(s for s in doc.schemas if s.name == "User")
        f = user.fields[0]
        self.assertTrue(f.type.is_object_ref)
        self.assertEqual(f.type.ref_name, "Address")

    def test_array_of_primitive(self):
        doc = parse_swagger(_doc({
            "M": {
                "type": "object",
                "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
            },
        }), "test.json")
        t = doc.schemas[0].fields[0].type
        self.assertTrue(t.is_array)
        self.assertTrue(t.element.is_primitive)
        self.assertEqual(t.element.primitive, PrimitiveKind.STRING)

    def test_array_of_ref(self):
        doc = parse_swagger(_doc({
            "Tag": {"type": "object", "properties": {"name": {"type": "string"}}},
            "Article": {
                "type": "object",
                "properties": {
                    "tags": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/Tag"},
                    },
                },
            },
        }), "test.json")
        art = next(s for s in doc.schemas if s.name == "Article")
        t = art.fields[0].type
        self.assertTrue(t.is_array)
        self.assertTrue(t.element.is_object_ref)
        self.assertEqual(t.element.ref_name, "Tag")

    def test_typed_additional_properties_is_map(self):
        doc = parse_swagger(_doc({
            "Tag": {"type": "object", "properties": {"name": {"type": "string"}}},
            "M": {
                "type": "object",
                "properties": {
                    "labels": {
                        "type": "object",
                        "additionalProperties": {"$ref": "#/components/schemas/Tag"},
                    },
                },
            },
        }), "test.json")
        m = next(s for s in doc.schemas if s.name == "M")
        t = m.fields[0].type
        self.assertTrue(t.is_map)
        self.assertTrue(t.element.is_object_ref)
        self.assertEqual(t.element.ref_name, "Tag")


class EnumTests(unittest.TestCase):
    def test_string_enum(self):
        doc = parse_swagger(_doc({
            "AuthProvider": {
                "type": "string",
                "enum": ["google", "apple", "email"],
            },
        }), "test.json")
        self.assertEqual(len(doc.enums), 1)
        e = doc.enums[0]
        self.assertEqual(e.name, "AuthProvider")
        self.assertEqual(e.kind, PrimitiveKind.STRING)
        self.assertEqual(e.case_names, ["google", "apple", "email"])
        self.assertEqual(e.string_values, ["google", "apple", "email"])

    def test_integer_enum_with_x_enum_varnames(self):
        doc = parse_swagger(_doc({
            "Severity": {
                "type": "integer",
                "enum": [1, 2, 3],
                "x-enum-varnames": ["low", "medium", "high"],
            },
        }), "test.json")
        e = doc.enums[0]
        self.assertEqual(e.kind, PrimitiveKind.INTEGER)
        self.assertEqual(e.case_names, ["low", "medium", "high"])
        self.assertEqual(e.integer_values, [1, 2, 3])

    def test_integer_enum_without_varnames_uses_value_n(self):
        doc = parse_swagger(_doc({
            "Status": {"type": "integer", "enum": [0, 1, 2]},
        }), "test.json")
        e = doc.enums[0]
        self.assertEqual(e.case_names, ["value_0", "value_1", "value_2"])


class FieldLevelAllOfWrapperTests(unittest.TestCase):
    """Common OpenAPI 3 idiom: ``allOf: [{$ref}]`` wraps a $ref to attach
    ``nullable`` / ``default`` / ``description``. Must unwrap to a plain ref."""

    def test_all_of_single_ref_unwrapped_to_object_ref(self):
        doc = parse_swagger(_doc({
            "TasteProfile": {
                "type": "object",
                "properties": {"score": {"type": "integer"}},
            },
            "TasteProfileResponse": {
                "type": "object",
                "properties": {
                    "profile": {
                        "nullable": True,
                        "allOf": [{"$ref": "#/components/schemas/TasteProfile"}],
                        "description": "profile or null",
                    },
                },
            },
        }), "test.json")
        resp = next(s for s in doc.schemas if s.name == "TasteProfileResponse")
        f = resp.fields[0]
        self.assertTrue(f.type.is_object_ref)
        self.assertEqual(f.type.ref_name, "TasteProfile")

    def test_all_of_single_ref_with_default(self):
        """Field carries default + description, allOf wraps a $ref to an enum."""
        doc = parse_swagger(_doc({
            "ReactionType": {"type": "string", "enum": ["like", "love"]},
            "Body": {
                "type": "object",
                "required": ["reaction_type"],
                "properties": {
                    "reaction_type": {
                        "allOf": [{"$ref": "#/components/schemas/ReactionType"}],
                        "default": "like",
                    },
                },
            },
        }), "test.json")
        body = next(s for s in doc.schemas if s.name == "Body")
        f = body.fields[0]
        self.assertTrue(f.type.is_object_ref)
        self.assertEqual(f.type.ref_name, "ReactionType")


class InlineEnumTests(unittest.TestCase):
    def test_inline_string_enum_derived(self):
        doc = parse_swagger(_doc({
            "User": {
                "type": "object",
                "required": ["provider"],
                "properties": {
                    "provider": {"type": "string", "enum": ["google", "apple"]},
                },
            },
        }), "test.json")
        # Inline enum becomes a top-level EnumDef
        enum_names = {e.name for e in doc.enums}
        self.assertIn("UserProvider", enum_names)
        # The field references it
        user = doc.schemas[0]
        f = user.fields[0]
        self.assertTrue(f.type.is_enum_ref)
        self.assertEqual(f.type.ref_name, "UserProvider")

    def test_inline_integer_enum_with_varnames(self):
        doc = parse_swagger(_doc({
            "Msg": {
                "type": "object",
                "required": ["severity"],
                "properties": {
                    "severity": {
                        "type": "integer",
                        "enum": [1, 2, 3],
                        "x-enum-varnames": ["low", "mid", "high"],
                    },
                },
            },
        }), "test.json")
        e = next(e for e in doc.enums if e.name == "MsgSeverity")
        self.assertEqual(e.case_names, ["low", "mid", "high"])
        self.assertEqual(e.integer_values, [1, 2, 3])

    def test_inline_enum_name_collision_with_top_level_halts(self):
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(_doc({
                "UserProvider": {"type": "object", "properties": {"a": {"type": "string"}}},
                "User": {
                    "type": "object",
                    "properties": {
                        "provider": {"type": "string", "enum": ["x"]},
                    },
                },
            }), "test.json")
        self.assertEqual(ctx.exception.code, "inline-name-collision")

    def test_inline_enum_x_jui_name_override(self):
        doc = parse_swagger(_doc({
            "User": {
                "type": "object",
                "properties": {
                    "provider": {
                        "type": "string",
                        "enum": ["x"],
                        "x-jui-name": "AuthSource",
                    },
                },
            },
        }), "test.json")
        names = {e.name for e in doc.enums}
        self.assertIn("AuthSource", names)


class AllOfTests(unittest.TestCase):
    def test_all_of_merges_properties(self):
        doc = parse_swagger(_doc({
            "Base": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "string"}},
            },
            "User": {
                "allOf": [
                    {"$ref": "#/components/schemas/Base"},
                    {
                        "type": "object",
                        "required": ["name"],
                        "properties": {"name": {"type": "string"}},
                    },
                ],
            },
        }), "test.json")
        user = next(s for s in doc.schemas if s.name == "User")
        names = [f.wire_name for f in user.fields]
        self.assertEqual(sorted(names), ["id", "name"])
        for f in user.fields:
            self.assertTrue(f.required)


class InlineObjectTests(unittest.TestCase):
    def test_inline_object_extracted_as_derived(self):
        doc = parse_swagger(_doc({
            "User": {
                "type": "object",
                "properties": {
                    "address": {
                        "type": "object",
                        "properties": {
                            "city": {"type": "string"},
                            "zip": {"type": "string"},
                        },
                    },
                },
            },
        }), "test.json")
        names = sorted(s.name for s in doc.schemas)
        self.assertEqual(names, ["User", "UserAddress"])
        user = next(s for s in doc.schemas if s.name == "User")
        self.assertEqual(user.fields[0].type.ref_name, "UserAddress")

    def test_inline_name_collision_with_top_level_halts(self):
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(_doc({
                "UserAddress": {
                    "type": "object",
                    "properties": {"x": {"type": "string"}},
                },
                "User": {
                    "type": "object",
                    "properties": {
                        "address": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                        },
                    },
                },
            }), "test.json")
        self.assertEqual(ctx.exception.code, "inline-name-collision")

    def test_x_jui_name_override_avoids_collision(self):
        doc = parse_swagger(_doc({
            "UserAddress": {
                "type": "object",
                "properties": {"x": {"type": "string"}},
            },
            "User": {
                "type": "object",
                "properties": {
                    "address": {
                        "type": "object",
                        "x-jui-name": "UserHome",
                        "properties": {"city": {"type": "string"}},
                    },
                },
            },
        }), "test.json")
        names = sorted(s.name for s in doc.schemas)
        self.assertIn("UserHome", names)
        self.assertIn("UserAddress", names)


class CycleDetectionTests(unittest.TestCase):
    def test_collection_mediated_self_ref_ok(self):
        """``children: [Self]`` is allowed — Array provides indirection."""
        doc = parse_swagger(_doc({
            "Tree": {
                "type": "object",
                "properties": {
                    "value": {"type": "string"},
                    "children": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/Tree"},
                    },
                },
            },
        }), "test.json")
        self.assertEqual(len(doc.schemas), 1)

    def test_direct_self_ref_halts(self):
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(_doc({
                "LinkedNode": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "string"},
                        "next": {"$ref": "#/components/schemas/LinkedNode"},
                    },
                },
            }), "test.json")
        self.assertEqual(ctx.exception.code, "direct-self-reference")

    def test_map_mediated_self_ref_ok(self):
        doc = parse_swagger(_doc({
            "Folder": {
                "type": "object",
                "properties": {
                    "children": {
                        "type": "object",
                        "additionalProperties": {"$ref": "#/components/schemas/Folder"},
                    },
                },
            },
        }), "test.json")
        self.assertEqual(len(doc.schemas), 1)


class PolymorphicHaltsTests(unittest.TestCase):
    def test_one_of_without_discriminator_halts(self):
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(_doc({
                "Response": {
                    "oneOf": [
                        {"$ref": "#/components/schemas/Success"},
                        {"$ref": "#/components/schemas/Error"},
                    ],
                },
                "Success": {"type": "object", "properties": {"ok": {"type": "boolean"}}},
                "Error": {"type": "object", "properties": {"msg": {"type": "string"}}},
            }), "test.json")
        self.assertEqual(ctx.exception.code, "polymorphic-not-supported")

    def test_any_of_halts(self):
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(_doc({
                "M": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
            }), "test.json")
        self.assertEqual(ctx.exception.code, "polymorphic-not-supported")

    def test_discriminator_alone_halts(self):
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(_doc({
                "M": {
                    "type": "object",
                    "discriminator": {"propertyName": "kind"},
                    "properties": {"kind": {"type": "string"}},
                },
            }), "test.json")
        self.assertEqual(ctx.exception.code, "polymorphic-not-supported")


class OneOfDiscriminatorTests(unittest.TestCase):
    """Field-level ``oneOf`` + ``discriminator`` is now a supported v1
    construct — it parses into an :class:`OneOfRef` carrying the
    sibling discriminator property name and the variant tag mapping.
    """

    def _stream_event_doc(self, extra: dict | None = None):
        body = {
            "StreamConvIdContent": {
                "type": "object",
                "required": ["cid"],
                "properties": {"cid": {"type": "string"}},
            },
            "StreamThinkingContent": {
                "type": "object",
                "required": ["msg"],
                "properties": {"msg": {"type": "string"}},
            },
            "StreamEvent": {
                "type": "object",
                "required": ["type", "content"],
                "properties": {
                    "type": {"type": "string"},
                    "content": {
                        "oneOf": [
                            {"$ref": "#/components/schemas/StreamConvIdContent"},
                            {"$ref": "#/components/schemas/StreamThinkingContent"},
                        ],
                        "discriminator": {
                            "propertyName": "type",
                            "mapping": {
                                "conversation_id": "#/components/schemas/StreamConvIdContent",
                                "thinking": "#/components/schemas/StreamThinkingContent",
                            },
                        },
                    },
                },
            },
        }
        if extra:
            body.update(extra)
        return _doc(body)

    def test_oneof_with_discriminator_parses_ir(self):
        doc = parse_swagger(self._stream_event_doc(), "test.json")
        stream = next(s for s in doc.schemas if s.name == "StreamEvent")
        content_field = next(f for f in stream.fields if f.wire_name == "content")
        self.assertTrue(content_field.type.is_one_of_ref)
        self.assertIsNotNone(content_field.type.one_of)
        one_of = content_field.type.one_of
        self.assertEqual(one_of.discriminator_property, "type")
        self.assertEqual(
            [(v.discriminator_value, v.ref_name) for v in one_of.variants],
            [
                ("conversation_id", "StreamConvIdContent"),
                ("thinking", "StreamThinkingContent"),
            ],
        )

    def test_oneof_preserves_mapping_order(self):
        """Mapping order is preserved so codegen emits cases deterministically."""
        doc_dict = self._stream_event_doc()
        # Reverse the mapping declaration order.
        doc_dict["components"]["schemas"]["StreamEvent"]["properties"]["content"][
            "discriminator"
        ]["mapping"] = {
            "thinking": "#/components/schemas/StreamThinkingContent",
            "conversation_id": "#/components/schemas/StreamConvIdContent",
        }
        doc = parse_swagger(doc_dict, "test.json")
        stream = next(s for s in doc.schemas if s.name == "StreamEvent")
        one_of = next(f for f in stream.fields if f.wire_name == "content").type.one_of
        self.assertEqual(
            [v.discriminator_value for v in one_of.variants],
            ["thinking", "conversation_id"],
        )

    def test_oneof_referenced_schemas_includes_variants(self):
        """``referenced_schemas`` must include every variant so orphan
        prune and import emit don't strand them."""
        doc = parse_swagger(self._stream_event_doc(), "test.json")
        stream = next(s for s in doc.schemas if s.name == "StreamEvent")
        refs = stream.referenced_schemas()
        self.assertIn("StreamConvIdContent", refs)
        self.assertIn("StreamThinkingContent", refs)

    def test_oneof_variant_not_in_top_level_halts(self):
        doc_dict = self._stream_event_doc()
        # Point mapping at a non-existent ref.
        doc_dict["components"]["schemas"]["StreamEvent"]["properties"]["content"][
            "discriminator"
        ]["mapping"]["thinking"] = "#/components/schemas/DoesNotExist"
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(doc_dict, "test.json")
        self.assertEqual(ctx.exception.code, "oneof-variant-not-found")

    def test_oneof_inline_variant_halts(self):
        doc_dict = self._stream_event_doc()
        doc_dict["components"]["schemas"]["StreamEvent"]["properties"]["content"]["oneOf"][0] = {
            "type": "object",
            "properties": {"foo": {"type": "string"}},
        }
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(doc_dict, "test.json")
        self.assertEqual(ctx.exception.code, "invalid-oneof")

    def test_oneof_mapping_referencing_missing_variant_halts(self):
        doc_dict = self._stream_event_doc()
        # mapping has an extra variant not in oneOf list.
        doc_dict["components"]["schemas"]["StreamEvent"]["properties"]["content"][
            "discriminator"
        ]["mapping"]["extra"] = "#/components/schemas/StreamConvIdContent"
        # Remove StreamConvIdContent from oneOf to force mismatch (extra now
        # points to a schema not in oneOf).
        doc_dict["components"]["schemas"]["StreamEvent"]["properties"]["content"]["oneOf"] = [
            {"$ref": "#/components/schemas/StreamThinkingContent"},
        ]
        del doc_dict["components"]["schemas"]["StreamEvent"]["properties"]["content"][
            "discriminator"
        ]["mapping"]["conversation_id"]
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(doc_dict, "test.json")
        self.assertEqual(ctx.exception.code, "discriminator-mapping-mismatch")

    def test_oneof_missing_mapping_halts(self):
        doc_dict = self._stream_event_doc()
        del doc_dict["components"]["schemas"]["StreamEvent"]["properties"]["content"][
            "discriminator"
        ]["mapping"]
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(doc_dict, "test.json")
        self.assertEqual(ctx.exception.code, "invalid-discriminator")

    def test_oneof_discriminator_sibling_missing_halts(self):
        doc_dict = self._stream_event_doc()
        # Rename `type` so the sibling no longer matches discriminator.propertyName.
        props = doc_dict["components"]["schemas"]["StreamEvent"]["properties"]
        props["kind"] = props.pop("type")
        doc_dict["components"]["schemas"]["StreamEvent"]["required"] = ["kind", "content"]
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(doc_dict, "test.json")
        self.assertEqual(ctx.exception.code, "oneof-discriminator-sibling-missing")

    def test_field_level_variant_that_is_a_union_halts(self):
        """A schema-level union cannot appear as a field-level oneOf
        variant (union-as-variant freeze)."""
        doc_dict = self._stream_event_doc()
        # Turn StreamThinkingContent into a (valid, explicit-mapping)
        # schema-level union; the field-level oneOf on StreamEvent then
        # references a union as one of its variants → halt.
        doc_dict["components"]["schemas"]["StreamThinkingContent"] = {
            "oneOf": [
                {"$ref": "#/components/schemas/StreamConvIdContent"},
            ],
            "discriminator": {
                "propertyName": "kind",
                "mapping": {"cid": "#/components/schemas/StreamConvIdContent"},
            },
        }
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(doc_dict, "test.json")
        self.assertEqual(ctx.exception.code, "union-variant-not-supported")


def _pet_doc(
    *,
    mapping: dict | None = None,
    dog_tag: dict | None = None,
    cat_tag: dict | None = None,
    extra: dict | None = None,
):
    """Schema-level union fixture: ``Pet = oneOf(Dog, Cat)``.

    ``dog_tag`` / ``cat_tag`` are the ``pet_type`` property bodies on the
    variants (pass ``None`` explicitly via sentinel ``OMIT`` to drop the
    property). Defaults model the inference-friendly shape: single-value
    string enum on Dog, ``const`` on Cat.
    """
    discriminator: dict = {"propertyName": "pet_type"}
    if mapping is not None:
        discriminator["mapping"] = mapping
    dog_props: dict = {"bark_volume": {"type": "integer"}}
    if dog_tag is not _OMIT:
        dog_props["pet_type"] = (
            dog_tag if dog_tag is not None else {"type": "string", "enum": ["dog"]}
        )
    cat_props: dict = {"lives_left": {"type": "integer"}}
    if cat_tag is not _OMIT:
        cat_props["pet_type"] = (
            cat_tag if cat_tag is not None else {"type": "string", "const": "cat"}
        )
    schemas = {
        "Pet": {
            "oneOf": [
                {"$ref": "#/components/schemas/Dog"},
                {"$ref": "#/components/schemas/Cat"},
            ],
            "discriminator": discriminator,
        },
        "Dog": {"type": "object", "required": ["pet_type"], "properties": dog_props},
        "Cat": {"type": "object", "required": ["pet_type"], "properties": cat_props},
    }
    if extra:
        schemas.update(extra)
    return _doc(schemas)


_OMIT = object()


class SchemaLevelUnionTests(unittest.TestCase):
    """Schema-level ``oneOf`` + ``discriminator`` parses into UnionDef
    (2026-07 lift, plan 2026-07-24-v1-unsupported/02)."""

    def test_explicit_mapping_parses_union(self):
        doc = parse_swagger(_pet_doc(mapping={
            "dog": "#/components/schemas/Dog",
            "cat": "#/components/schemas/Cat",
        }), "test.json")
        self.assertEqual(len(doc.unions), 1)
        union = doc.unions[0]
        self.assertEqual(union.name, "Pet")
        self.assertEqual(union.discriminator_property, "pet_type")
        self.assertFalse(union.mapping_inferred)
        self.assertEqual(
            [(v.discriminator_value, v.ref_name) for v in union.variants],
            [("dog", "Dog"), ("cat", "Cat")],
        )
        # The union is NOT in doc.schemas — it has its own IR list.
        self.assertNotIn("Pet", {s.name for s in doc.schemas})

    def test_inferred_mapping_from_variant_tags(self):
        """No mapping → inferred from the variants' internal tag (enum /
        const), in oneOf order, with a WARNING on stderr."""
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            doc = parse_swagger(_pet_doc(), "test.json")
        union = doc.unions[0]
        self.assertTrue(union.mapping_inferred)
        self.assertEqual(
            [(v.discriminator_value, v.ref_name) for v in union.variants],
            [("dog", "Dog"), ("cat", "Cat")],
        )
        self.assertIn("WARNING [api-model]", stderr.getvalue())
        self.assertIn("dog -> Dog", stderr.getvalue())
        self.assertIn("cat -> Cat", stderr.getvalue())

    def test_inferred_and_explicit_mapping_yield_same_variants(self):
        with contextlib.redirect_stderr(io.StringIO()):
            inferred = parse_swagger(_pet_doc(), "test.json").unions[0]
        explicit = parse_swagger(_pet_doc(mapping={
            "dog": "#/components/schemas/Dog",
            "cat": "#/components/schemas/Cat",
        }), "test.json").unions[0]
        self.assertEqual(inferred.variants, explicit.variants)
        self.assertEqual(
            inferred.discriminator_property, explicit.discriminator_property
        )

    def test_inference_tag_via_all_of_base_is_seen(self):
        """A tag declared on an allOf base schema still counts."""
        doc_dict = _pet_doc(dog_tag=_OMIT)
        doc_dict["components"]["schemas"]["Dog"] = {
            "allOf": [
                {"$ref": "#/components/schemas/DogBase"},
                {"type": "object", "properties": {"bark_volume": {"type": "integer"}}},
            ],
        }
        doc_dict["components"]["schemas"]["DogBase"] = {
            "type": "object",
            "properties": {"pet_type": {"type": "string", "enum": ["dog"]}},
        }
        with contextlib.redirect_stderr(io.StringIO()):
            doc = parse_swagger(doc_dict, "test.json")
        self.assertEqual(
            [v.discriminator_value for v in doc.unions[0].variants],
            ["dog", "cat"],
        )

    def test_inference_tagless_variant_halts(self):
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(_pet_doc(dog_tag=_OMIT), "test.json")
        self.assertEqual(ctx.exception.code, "invalid-discriminator")
        self.assertIn("does not declare", str(ctx.exception))

    def test_inference_non_string_tag_halts(self):
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(
                _pet_doc(dog_tag={"type": "integer", "enum": [1]}), "test.json"
            )
        self.assertEqual(ctx.exception.code, "invalid-discriminator")
        self.assertIn("non-string", str(ctx.exception))

    def test_inference_multi_value_enum_tag_halts(self):
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(
                _pet_doc(dog_tag={"type": "string", "enum": ["dog", "puppy"]}),
                "test.json",
            )
        self.assertEqual(ctx.exception.code, "invalid-discriminator")
        self.assertIn("exactly one", str(ctx.exception))

    def test_inference_duplicate_tag_halts(self):
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(
                _pet_doc(cat_tag={"type": "string", "const": "dog"}), "test.json"
            )
        self.assertEqual(ctx.exception.code, "invalid-discriminator")
        self.assertIn("unique", str(ctx.exception))

    def test_explicit_mapping_conflicting_variant_tag_halts(self):
        """mapping says dog → Dog but Dog.pet_type enum says canine."""
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(_pet_doc(
                mapping={
                    "dog": "#/components/schemas/Dog",
                    "cat": "#/components/schemas/Cat",
                },
                dog_tag={"type": "string", "enum": ["canine"]},
            ), "test.json")
        self.assertEqual(ctx.exception.code, "discriminator-tag-conflict")

    def test_explicit_mapping_non_string_variant_tag_halts(self):
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(_pet_doc(
                mapping={
                    "dog": "#/components/schemas/Dog",
                    "cat": "#/components/schemas/Cat",
                },
                dog_tag={"type": "integer", "enum": [1]},
            ), "test.json")
        self.assertEqual(ctx.exception.code, "discriminator-tag-conflict")

    def test_explicit_mapping_matching_tag_ok(self):
        doc = parse_swagger(_pet_doc(mapping={
            "dog": "#/components/schemas/Dog",
            "cat": "#/components/schemas/Cat",
        }), "test.json")
        self.assertEqual(len(doc.unions), 1)

    def test_tagless_variant_with_explicit_mapping_ok(self):
        """Variants without an internal tag are fine when mapping is
        explicit — the union codegen injects the tag on encode."""
        doc = parse_swagger(_pet_doc(
            mapping={
                "dog": "#/components/schemas/Dog",
                "cat": "#/components/schemas/Cat",
            },
            dog_tag=_OMIT,
            cat_tag=_OMIT,
        ), "test.json")
        self.assertEqual(len(doc.unions), 1)

    def test_schema_level_oneof_without_discriminator_halts(self):
        doc_dict = _pet_doc()
        del doc_dict["components"]["schemas"]["Pet"]["discriminator"]
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(doc_dict, "test.json")
        self.assertEqual(ctx.exception.code, "polymorphic-not-supported")

    def test_mixed_oneof_and_properties_halts(self):
        doc_dict = _pet_doc()
        doc_dict["components"]["schemas"]["Pet"]["properties"] = {
            "shared": {"type": "string"},
        }
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(doc_dict, "test.json")
        self.assertEqual(ctx.exception.code, "invalid-oneof")

    def test_inline_variant_halts(self):
        doc_dict = _pet_doc()
        doc_dict["components"]["schemas"]["Pet"]["oneOf"][0] = {
            "type": "object",
            "properties": {"x": {"type": "string"}},
        }
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(doc_dict, "test.json")
        self.assertEqual(ctx.exception.code, "invalid-oneof")

    def test_union_as_variant_of_union_halts(self):
        doc_dict = _pet_doc(extra={
            "Robot": {
                "type": "object",
                "properties": {"pet_type": {"type": "string", "const": "robot"}},
            },
            "Creature": {
                "oneOf": [
                    {"$ref": "#/components/schemas/Pet"},
                    {"$ref": "#/components/schemas/Robot"},
                ],
                "discriminator": {"propertyName": "pet_type"},
            },
        })
        with self.assertRaises(OpenAPILoadError) as ctx:
            with contextlib.redirect_stderr(io.StringIO()):
                parse_swagger(doc_dict, "test.json")
        self.assertEqual(ctx.exception.code, "union-variant-not-supported")

    def test_union_reference_positions(self):
        """Reference matrix: plain property / array items / nullable all
        resolve to an object ref named after the union."""
        doc_dict = _pet_doc(extra={
            "Owner": {
                "type": "object",
                "required": ["pet"],
                "properties": {
                    "pet": {"$ref": "#/components/schemas/Pet"},
                    "previous_pet": {"$ref": "#/components/schemas/Pet"},
                },
            },
            "Zoo": {
                "type": "object",
                "properties": {
                    "animals": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/Pet"},
                    },
                },
            },
        })
        with contextlib.redirect_stderr(io.StringIO()):
            doc = parse_swagger(doc_dict, "test.json")
        owner = next(s for s in doc.schemas if s.name == "Owner")
        pet = next(f for f in owner.fields if f.wire_name == "pet")
        self.assertTrue(pet.type.is_object_ref)
        self.assertEqual(pet.type.ref_name, "Pet")
        self.assertFalse(pet.type.nullable)
        prev = next(f for f in owner.fields if f.wire_name == "previous_pet")
        self.assertTrue(prev.type.nullable)
        zoo = next(s for s in doc.schemas if s.name == "Zoo")
        animals = next(f for f in zoo.fields if f.wire_name == "animals")
        self.assertTrue(animals.type.is_array)
        self.assertEqual(animals.type.element.ref_name, "Pet")

    def test_union_skip_domain_flag(self):
        doc_dict = _pet_doc(mapping={
            "dog": "#/components/schemas/Dog",
            "cat": "#/components/schemas/Cat",
        })
        doc_dict["components"]["schemas"]["Pet"]["x-jui-skip-domain"] = True
        doc = parse_swagger(doc_dict, "test.json")
        self.assertTrue(doc.unions[0].skip_domain)
        self.assertTrue(doc.should_skip_domain(doc.unions[0]))

    def test_no_warning_for_explicit_mapping(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            parse_swagger(_pet_doc(mapping={
                "dog": "#/components/schemas/Dog",
                "cat": "#/components/schemas/Cat",
            }), "test.json")
        self.assertEqual(stderr.getvalue(), "")


class FreezeDeclarationTests(unittest.TestCase):
    """anyOf / direct self-ref / union-as-variant are permanent halts —
    messages no longer promise a future version."""

    def test_any_of_message_is_permanent(self):
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(_doc({
                "M": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
            }), "test.json")
        self.assertEqual(ctx.exception.code, "polymorphic-not-supported")
        self.assertIn("permanently", str(ctx.exception))
        self.assertNotIn("v2", str(ctx.exception))

    def test_self_ref_message_is_permanent(self):
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(_doc({
                "Node": {
                    "type": "object",
                    "properties": {
                        "next": {"$ref": "#/components/schemas/Node"},
                    },
                },
            }), "test.json")
        self.assertEqual(ctx.exception.code, "direct-self-reference")
        self.assertIn("permanent", str(ctx.exception))

    def test_union_as_variant_message_is_permanent(self):
        doc_dict = _pet_doc(extra={
            "Creature": {
                "oneOf": [{"$ref": "#/components/schemas/Pet"}],
                "discriminator": {"propertyName": "pet_type"},
            },
        })
        with self.assertRaises(OpenAPILoadError) as ctx:
            with contextlib.redirect_stderr(io.StringIO()):
                parse_swagger(doc_dict, "test.json")
        self.assertEqual(ctx.exception.code, "union-variant-not-supported")
        self.assertIn("permanent", str(ctx.exception))


class WrapperSchemaTests(unittest.TestCase):
    """Non-object top-level schemas (``type: string`` / ``type: array``)
    parse into ``SchemaDef(is_wrapper=True)`` with a synthesized single
    field — used for oneOf variants that wrap a bare value. See bug
    jui-android-codegen-empty-data-class-for-non-object-schema-types.
    """

    def test_string_wrapper(self):
        doc = parse_swagger(_doc({
            "Thinking": {"type": "string", "description": "LLM text"},
        }), "test.json")
        schema = doc.schemas[0]
        self.assertTrue(schema.is_wrapper)
        self.assertEqual(schema.wrapper_field_name, "value")
        self.assertIsNotNone(schema.wrapped_type)
        self.assertTrue(schema.wrapped_type.is_primitive)
        self.assertEqual(len(schema.fields), 1)
        self.assertEqual(schema.fields[0].wire_name, "value")

    def test_array_wrapper(self):
        doc = parse_swagger(_doc({
            "Item": {"type": "object", "properties": {"id": {"type": "string"}}},
            "Results": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/Item"},
            },
        }), "test.json")
        results = next(s for s in doc.schemas if s.name == "Results")
        self.assertTrue(results.is_wrapper)
        self.assertEqual(results.wrapper_field_name, "items")
        self.assertTrue(results.wrapped_type.is_array)
        self.assertEqual(results.wrapped_type.element.ref_name, "Item")

    def test_object_schema_not_wrapper(self):
        doc = parse_swagger(_doc({
            "User": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "string"}},
            },
        }), "test.json")
        self.assertFalse(doc.schemas[0].is_wrapper)
        self.assertIsNone(doc.schemas[0].wrapped_type)

    def test_enum_only_schema_not_wrapper(self):
        """``type: string`` + ``enum: [...]`` is still parsed as an
        :class:`EnumDef`, not a wrapper schema."""
        doc = parse_swagger(_doc({
            "Color": {"type": "string", "enum": ["red", "blue"]},
        }), "test.json")
        self.assertEqual(len(doc.schemas), 0)
        self.assertEqual(len(doc.enums), 1)
        self.assertEqual(doc.enums[0].name, "Color")

    def test_integer_wrapper(self):
        doc = parse_swagger(_doc({
            "Count": {"type": "integer", "format": "int64"},
        }), "test.json")
        schema = doc.schemas[0]
        self.assertTrue(schema.is_wrapper)
        self.assertEqual(schema.fields[0].wire_name, "value")
        self.assertEqual(
            schema.wrapped_type.primitive,
            schema.fields[0].type.primitive,
        )


class RefHaltsTests(unittest.TestCase):
    def test_relative_file_ref_halts(self):
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(_doc({
                "M": {
                    "type": "object",
                    "properties": {
                        "x": {"$ref": "./other.yaml#/components/schemas/Other"},
                    },
                },
            }), "test.json")
        self.assertEqual(ctx.exception.code, "multi-file-ref")

    def test_url_ref_halts(self):
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(_doc({
                "M": {
                    "type": "object",
                    "properties": {
                        "x": {"$ref": "https://example.com/schemas/Other.json"},
                    },
                },
            }), "test.json")
        self.assertEqual(ctx.exception.code, "multi-file-ref")


class ObjectWithoutTypeTests(unittest.TestCase):
    def test_shapeless_object_halts(self):
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(_doc({"M": {"type": "object"}}), "test.json")
        self.assertEqual(ctx.exception.code, "object-without-type")

    def test_additional_properties_true_without_props_halts(self):
        with self.assertRaises(OpenAPILoadError) as ctx:
            parse_swagger(_doc({
                "M": {"type": "object", "additionalProperties": True},
            }), "test.json")
        self.assertEqual(ctx.exception.code, "object-without-type")


class SkipDomainTests(unittest.TestCase):
    def test_x_jui_skip_domain_flag(self):
        doc = parse_swagger(_doc({
            "LoginRequest": {
                "type": "object",
                "x-jui-skip-domain": True,
                "properties": {"email": {"type": "string"}},
            },
        }), "test.json")
        self.assertTrue(doc.schemas[0].skip_domain)


class ConformanceFlagTests(unittest.TestCase):
    def test_map_field_drops_hashable(self):
        doc = parse_swagger(_doc({
            "Tag": {"type": "object", "properties": {"name": {"type": "string"}}},
            "M": {
                "type": "object",
                "properties": {
                    "labels": {
                        "type": "object",
                        "additionalProperties": {"$ref": "#/components/schemas/Tag"},
                    },
                },
            },
        }), "test.json")
        m = next(s for s in doc.schemas if s.name == "M")
        self.assertFalse(m.is_hashable)
        self.assertTrue(m.is_equatable)
        self.assertTrue(m.is_sendable)

    def test_primitive_only_keeps_all(self):
        doc = parse_swagger(_doc({
            "M": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            },
        }), "test.json")
        m = doc.schemas[0]
        self.assertTrue(m.is_equatable)
        self.assertTrue(m.is_hashable)
        self.assertTrue(m.is_sendable)


class LoadSwaggerDirectoryTests(unittest.TestCase):
    def test_yaml_swagger_loads(self):
        # Q8 lift (2026-07): YAML swagger is parsed, no longer halts.
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "doc.yaml").write_text(
                "openapi: 3.0.3\n"
                "info:\n  title: T\n  version: '1'\n"
                "components:\n"
                "  schemas:\n"
                "    User:\n"
                "      type: object\n"
                "      properties:\n"
                "        id:\n"
                "          type: string\n",
                encoding="utf-8",
            )
            docs = load_swagger(tmp)
            self.assertEqual(len(docs), 1)
            self.assertEqual(docs[0].schemas[0].name, "User")

    def test_skips_non_swagger_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "notes.json").write_text(json.dumps({"foo": 1}), encoding="utf-8")
            docs = load_swagger(tmp)
            self.assertEqual(docs, [])

    def test_skips_unrelated_yaml_does_not_halt(self):
        # A YAML artifact that is NOT a swagger doc (another workstream's
        # notes, a CI config) must be skipped like a non-swagger JSON — not
        # hard-halt the build. Regression: jui-api-dir-unrelated-yaml-hard-error.
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "cs-bot-notes.yaml").write_text(
                "name: cs-bot\nsteps:\n  - build\n  - deploy\n", encoding="utf-8"
            )
            docs = load_swagger(tmp)
            self.assertEqual(docs, [])

    def test_unrelated_yaml_does_not_block_real_json_swagger(self):
        # The real JSON SSoT must still load even when an unrelated YAML
        # shares the directory.
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "unrelated.yaml").write_text("name: not-a-swagger\n", encoding="utf-8")
            (tmp / "api.json").write_text(
                json.dumps(_doc({
                    "User": {"type": "object", "properties": {"id": {"type": "string"}}},
                })),
                encoding="utf-8",
            )
            docs = load_swagger(tmp)
            self.assertEqual(len(docs), 1)

    def test_swagger_2_authored_in_yml_loads(self):
        # Swagger 2.0 in a .yml file also parses (definitions container).
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "spec.yml").write_text(
                "swagger: '2.0'\n"
                "info:\n  title: X\n  version: '1'\n"
                "definitions:\n"
                "  Item:\n"
                "    type: object\n"
                "    properties:\n"
                "      name:\n"
                "        type: string\n",
                encoding="utf-8",
            )
            docs = load_swagger(tmp)
            self.assertEqual(len(docs), 1)
            self.assertEqual(docs[0].schemas[0].name, "Item")

    def test_loads_valid_swagger(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "api.json").write_text(
                json.dumps(_doc({
                    "User": {
                        "type": "object",
                        "properties": {"id": {"type": "string"}},
                    },
                })),
                encoding="utf-8",
            )
            docs = load_swagger(tmp)
            self.assertEqual(len(docs), 1)
            self.assertEqual(len(docs[0].schemas), 1)


class FilterIntegrationTests(unittest.TestCase):
    """End-to-end: parse_swagger with an active filter skips parsing of
    excluded schemas entirely (lenient — their polymorphic/shapeless
    constructs do NOT raise)."""

    def _api_doc(self, schemas: dict, paths: dict) -> dict:
        return {
            "openapi": "3.0.3",
            "info": {"title": "T", "version": "1"},
            "paths": paths,
            "components": {"schemas": schemas},
        }

    def test_excluded_polymorphic_schema_does_not_halt(self):
        """oneOf inside a schema would normally halt parse_swagger, but
        when the schema is filtered out the parser never sees it."""
        raw = self._api_doc(
            schemas={
                "Kept": {"type": "object", "properties": {"x": {"type": "string"}}},
                "Polymorphic": {
                    "oneOf": [
                        {"$ref": "#/components/schemas/A"},
                        {"$ref": "#/components/schemas/B"},
                    ],
                },
                "A": {"type": "object", "properties": {"a": {"type": "string"}}},
                "B": {"type": "object", "properties": {"b": {"type": "string"}}},
            },
            paths={
                "/api/kept": {
                    "get": {
                        "responses": {
                            "200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Kept"}}}}
                        },
                    },
                },
            },
        )
        cfg = SchemaFilterConfig(include_paths=("/api/kept",))
        # Without filter this would halt on Polymorphic's oneOf;
        # with the filter it parses cleanly.
        doc = parse_swagger(raw, "test.json", schema_filter=cfg)
        names = {s.name for s in doc.schemas}
        self.assertEqual(names, {"Kept"})
        self.assertIn("Polymorphic", doc.filtered_out)
        self.assertIn("A", doc.filtered_out)
        self.assertIn("B", doc.filtered_out)

    def test_skip_domain_overrides_propagated(self):
        raw = self._api_doc(
            schemas={
                "User": {"type": "object", "properties": {"id": {"type": "string"}}},
                "Bar": {"type": "object", "properties": {"id": {"type": "string"}}},
            },
            paths={},
        )
        cfg = SchemaFilterConfig(skip_domain=("Bar",))
        doc = parse_swagger(raw, "test.json", schema_filter=cfg)
        self.assertEqual(doc.skip_domain_overrides, frozenset({"Bar"}))
        # Both schemas still parse (skip_domain alone is_active() is False)
        self.assertEqual({s.name for s in doc.schemas}, {"User", "Bar"})

    def test_skip_domain_or_evaluation_with_per_schema_flag(self):
        """SwaggerDocument.should_skip_domain ORs per-app and per-schema flags."""
        raw = self._api_doc(
            schemas={
                "User": {"type": "object", "properties": {"id": {"type": "string"}}},
                "LoginRequest": {
                    "type": "object",
                    "x-jui-skip-domain": True,
                    "properties": {"email": {"type": "string"}},
                },
                "Bar": {"type": "object", "properties": {"id": {"type": "string"}}},
            },
            paths={},
        )
        cfg = SchemaFilterConfig(skip_domain=("Bar",))
        doc = parse_swagger(raw, "test.json", schema_filter=cfg)
        for s in doc.schemas:
            if s.name == "User":
                self.assertFalse(doc.should_skip_domain(s))
            elif s.name == "LoginRequest":
                self.assertTrue(doc.should_skip_domain(s))  # per-schema
            elif s.name == "Bar":
                self.assertTrue(doc.should_skip_domain(s))  # per-app

    def test_filter_disabled_when_no_dimensions(self):
        """Empty filter keeps all schemas (backwards compat)."""
        raw = self._api_doc(
            schemas={
                "A": {"type": "object", "properties": {"x": {"type": "string"}}},
                "B": {"type": "object", "properties": {"y": {"type": "string"}}},
            },
            paths={},
        )
        doc = parse_swagger(raw, "test.json", schema_filter=SchemaFilterConfig())
        self.assertEqual({s.name for s in doc.schemas}, {"A", "B"})
        self.assertEqual(doc.filtered_out, frozenset())


def _write_json(tmp: Path, name: str, data: dict) -> Path:
    p = tmp / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


_MONEY = {
    "type": "object",
    "properties": {
        "amount": {"type": "integer"},
        "currency": {"type": "string"},
    },
}


def _fragment(schemas: dict) -> dict:
    """A shared schema file that is NOT itself a swagger doc (no openapi key)."""
    return {"components": {"schemas": schemas}}


class YamlInputTests(unittest.TestCase):
    """Q8 lift (plan 2026-07-24-v1-unsupported/01): YAML swagger input."""

    def test_yaml_ir_matches_json(self):
        import yaml as yaml_mod

        schemas = {
            "User": {
                "type": "object",
                "required": ["id"],
                "properties": {
                    "id": {"type": "string"},
                    "age": {"type": "integer"},
                    "role": {"type": "string", "enum": ["admin", "member"]},
                },
            },
        }
        with tempfile.TemporaryDirectory() as d_json, \
                tempfile.TemporaryDirectory() as d_yaml:
            _write_json(Path(d_json), "api.json", _doc(schemas))
            (Path(d_yaml) / "api.yaml").write_text(
                yaml_mod.safe_dump(_doc(schemas), sort_keys=False), encoding="utf-8"
            )
            doc_j = load_swagger(Path(d_json))[0]
            doc_y = load_swagger(Path(d_yaml))[0]
        self.assertEqual(
            [s.name for s in doc_y.schemas], [s.name for s in doc_j.schemas]
        )
        self.assertEqual(doc_y.schemas[0].fields, doc_j.schemas[0].fields)
        self.assertEqual(doc_y.enums, doc_j.enums)

    def test_broken_yaml_halts_with_parse_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "api.yaml").write_text(
                "openapi: 3.0.3\ninfo: {unclosed\n", encoding="utf-8"
            )
            with self.assertRaises(OpenAPILoadError) as ctx:
                load_swagger(tmp)
            self.assertEqual(ctx.exception.code, "yaml-parse-error")

    def test_regex_false_match_without_top_level_key_skips(self):
        # The cheap text prefilter matches `openapi:` at a line start inside
        # a multi-line quoted scalar; the parsed document is not a mapping
        # with a swagger key, so it must be skipped, not halted.
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "notes.yaml").write_text(
                '"text with\nopenapi: 3"\n', encoding="utf-8"
            )
            self.assertEqual(load_swagger(tmp), [])

    def test_norway_problem_enum_halts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "api.yaml").write_text(
                "openapi: 3.0.3\n"
                "info:\n  title: T\n  version: '1'\n"
                "components:\n"
                "  schemas:\n"
                "    CountryCode:\n"
                "      type: string\n"
                "      enum: [NO, SE, DK]\n",
                encoding="utf-8",
            )
            with self.assertRaises(OpenAPILoadError) as ctx:
                load_swagger(tmp)
            self.assertEqual(ctx.exception.code, "yaml-type-coercion")
            self.assertIn("Quote", str(ctx.exception))

    def test_quoted_norway_enum_loads(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "api.yaml").write_text(
                "openapi: 3.0.3\n"
                "info:\n  title: T\n  version: '1'\n"
                "components:\n"
                "  schemas:\n"
                "    CountryCode:\n"
                "      type: string\n"
                "      enum: ['NO', 'SE']\n",
                encoding="utf-8",
            )
            docs = load_swagger(tmp)
            self.assertEqual(docs[0].enums[0].string_values, ["NO", "SE"])

    def test_date_literal_halts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "api.yaml").write_text(
                "openapi: 3.0.3\n"
                "info:\n  title: T\n  version: '1'\n"
                "components:\n"
                "  schemas:\n"
                "    M:\n"
                "      type: object\n"
                "      properties:\n"
                "        since:\n"
                "          type: string\n"
                "          default: 2026-07-24\n",
                encoding="utf-8",
            )
            with self.assertRaises(OpenAPILoadError) as ctx:
                load_swagger(tmp)
            self.assertEqual(ctx.exception.code, "yaml-type-coercion")

    def test_duplicate_basename_yaml_and_json_halts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_json(tmp, "api.json", _doc({
                "User": {"type": "object", "properties": {"id": {"type": "string"}}},
            }))
            (tmp / "api.yaml").write_text(
                "openapi: 3.0.3\ninfo:\n  title: T\n  version: '1'\n",
                encoding="utf-8",
            )
            with self.assertRaises(OpenAPILoadError) as ctx:
                load_swagger(tmp)
            self.assertEqual(ctx.exception.code, "duplicate-swagger-basename")

    def test_same_stem_non_swagger_json_does_not_halt(self):
        # The basename guard only fires between actual swagger docs.
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_json(tmp, "api.json", {"not": "swagger"})
            (tmp / "api.yaml").write_text(
                "openapi: 3.0.3\n"
                "info:\n  title: T\n  version: '1'\n"
                "components:\n"
                "  schemas:\n"
                "    User:\n"
                "      type: object\n"
                "      properties:\n"
                "        id:\n"
                "          type: string\n",
                encoding="utf-8",
            )
            docs = load_swagger(tmp)
            self.assertEqual(len(docs), 1)

    def test_pyyaml_missing_halts_with_install_guidance(self):
        from jui_cli.core import openapi_loader as loader_mod

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "api.yaml").write_text(
                "openapi: 3.0.3\ninfo:\n  title: T\n", encoding="utf-8"
            )
            original = loader_mod._import_yaml
            loader_mod._import_yaml = lambda: None
            try:
                with self.assertRaises(OpenAPILoadError) as ctx:
                    load_swagger(tmp)
            finally:
                loader_mod._import_yaml = original
            self.assertEqual(ctx.exception.code, "pyyaml-missing")
            self.assertIn("pip3 install pyyaml", str(ctx.exception))


class MultiFileRefTests(unittest.TestCase):
    """Q12 lift (plan 2026-07-24-v1-unsupported/01): cross-file $ref."""

    def test_relative_ref_with_and_without_dot_prefix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_json(tmp, "main.json", _doc({
                "Order": {
                    "type": "object",
                    "properties": {
                        "total": {"$ref": "./common.json#/components/schemas/Money"},
                        "fee": {"$ref": "common.json#/components/schemas/Money"},
                    },
                },
            }))
            _write_json(tmp, "common.json", _fragment({"Money": _MONEY}))
            docs = load_swagger(tmp)
        # The fragment has no openapi key — it is not its own document.
        self.assertEqual(len(docs), 1)
        self.assertEqual({s.name for s in docs[0].schemas}, {"Order", "Money"})
        order = next(s for s in docs[0].schemas if s.name == "Order")
        for f in order.fields:
            self.assertTrue(f.type.is_object_ref)
            self.assertEqual(f.type.ref_name, "Money")

    def test_yaml_doc_refs_json_fragment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "main.yaml").write_text(
                "openapi: 3.0.3\n"
                "info:\n  title: T\n  version: '1'\n"
                "components:\n"
                "  schemas:\n"
                "    Order:\n"
                "      type: object\n"
                "      properties:\n"
                "        total:\n"
                "          $ref: './common.json#/components/schemas/Money'\n",
                encoding="utf-8",
            )
            _write_json(tmp, "common.json", _fragment({"Money": _MONEY}))
            docs = load_swagger(tmp)
        self.assertEqual({s.name for s in docs[0].schemas}, {"Order", "Money"})

    def test_nested_chain_and_transitive_local_refs(self):
        # main → a.json#A; A refs b.json#B (cross-file) AND #/…/Helper
        # (local to a.json). Both must be pulled into main's scope.
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_json(tmp, "main.json", _doc({
                "Root": {
                    "type": "object",
                    "properties": {
                        "a": {"$ref": "./a.json#/components/schemas/A"},
                    },
                },
            }))
            _write_json(tmp, "a.json", _fragment({
                "A": {
                    "type": "object",
                    "properties": {
                        "b": {"$ref": "./b.json#/components/schemas/B"},
                        "h": {"$ref": "#/components/schemas/Helper"},
                    },
                },
                "Helper": {
                    "type": "object",
                    "properties": {"x": {"type": "string"}},
                },
            }))
            _write_json(tmp, "b.json", _fragment({
                "B": {"type": "object", "properties": {"y": {"type": "string"}}},
            }))
            docs = load_swagger(tmp)
        self.assertEqual(
            {s.name for s in docs[0].schemas}, {"Root", "A", "B", "Helper"}
        )

    def test_cross_file_cycle_halts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_json(tmp, "main.json", _doc({
                "Root": {
                    "type": "object",
                    "properties": {
                        "a": {"$ref": "./a.json#/components/schemas/A"},
                    },
                },
            }))
            _write_json(tmp, "a.json", _fragment({
                "A": {
                    "type": "object",
                    "properties": {
                        "b": {"$ref": "./b.json#/components/schemas/B"},
                    },
                },
            }))
            _write_json(tmp, "b.json", _fragment({
                "B": {
                    "type": "object",
                    "properties": {
                        "a": {"$ref": "./a.json#/components/schemas/A"},
                    },
                },
            }))
            with self.assertRaises(OpenAPILoadError) as ctx:
                load_swagger(tmp)
            self.assertEqual(ctx.exception.code, "cross-file-ref-cycle")

    def test_ref_outside_api_dir_halts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            api = tmp / "api"
            api.mkdir()
            _write_json(tmp, "outside.json", _fragment({"Money": _MONEY}))
            _write_json(api, "main.json", _doc({
                "Order": {
                    "type": "object",
                    "properties": {
                        "m": {"$ref": "../outside.json#/components/schemas/Money"},
                    },
                },
            }))
            with self.assertRaises(OpenAPILoadError) as ctx:
                load_swagger(api)
            self.assertEqual(ctx.exception.code, "ref-outside-api-dir")

    def test_url_ref_halts_during_directory_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_json(tmp, "main.json", _doc({
                "Order": {
                    "type": "object",
                    "properties": {
                        "m": {"$ref": "https://example.com/common.json#/components/schemas/Money"},
                    },
                },
            }))
            with self.assertRaises(OpenAPILoadError) as ctx:
                load_swagger(tmp)
            self.assertEqual(ctx.exception.code, "multi-file-ref")

    def test_non_schema_pointer_halts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_json(tmp, "common.json", {"components": {"parameters": {"Page": {}}}})
            _write_json(tmp, "main.json", _doc({
                "Order": {
                    "type": "object",
                    "properties": {
                        "p": {"$ref": "./common.json#/components/parameters/Page"},
                    },
                },
            }))
            with self.assertRaises(OpenAPILoadError) as ctx:
                load_swagger(tmp)
            self.assertEqual(ctx.exception.code, "ref-non-schema-pointer")

    def test_whole_file_ref_halts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_json(tmp, "common.json", _fragment({"Money": _MONEY}))
            _write_json(tmp, "main.json", _doc({
                "Order": {
                    "type": "object",
                    "properties": {"m": {"$ref": "./common.json"}},
                },
            }))
            with self.assertRaises(OpenAPILoadError) as ctx:
                load_swagger(tmp)
            self.assertEqual(ctx.exception.code, "ref-non-schema-pointer")

    def test_ref_missing_schema_halts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_json(tmp, "common.json", _fragment({"Money": _MONEY}))
            _write_json(tmp, "main.json", _doc({
                "Order": {
                    "type": "object",
                    "properties": {
                        "m": {"$ref": "./common.json#/components/schemas/Nope"},
                    },
                },
            }))
            with self.assertRaises(OpenAPILoadError) as ctx:
                load_swagger(tmp)
            self.assertEqual(ctx.exception.code, "ref-not-found")

    def test_swagger2_root_merges_into_definitions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_json(tmp, "main.json", {
                "swagger": "2.0",
                "info": {"title": "T", "version": "1"},
                "definitions": {
                    "Item": {
                        "type": "object",
                        "properties": {
                            "m": {"$ref": "./common.json#/components/schemas/Money"},
                        },
                    },
                },
            })
            _write_json(tmp, "common.json", _fragment({"Money": _MONEY}))
            docs = load_swagger(tmp)
        self.assertEqual({s.name for s in docs[0].schemas}, {"Item", "Money"})

    def test_shared_schema_identical_across_docs_ok(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_json(tmp, "a.json", _doc({
                "OrderA": {
                    "type": "object",
                    "properties": {
                        "m": {"$ref": "./common.json#/components/schemas/Money"},
                    },
                },
            }))
            _write_json(tmp, "b.json", _doc({
                "OrderB": {
                    "type": "object",
                    "properties": {
                        "m": {"$ref": "common.json#/components/schemas/Money"},
                    },
                },
            }))
            _write_json(tmp, "common.json", _fragment({"Money": _MONEY}))
            docs = load_swagger(tmp)
        self.assertEqual(len(docs), 2)
        for doc in docs:
            self.assertIn("Money", {s.name for s in doc.schemas})

    def test_cross_doc_same_name_different_body_halts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_json(tmp, "a.json", _doc({
                "User": {"type": "object", "properties": {"id": {"type": "string"}}},
            }))
            _write_json(tmp, "b.json", _doc({
                "User": {"type": "object", "properties": {"uid": {"type": "integer"}}},
            }))
            with self.assertRaises(OpenAPILoadError) as ctx:
                load_swagger(tmp)
            self.assertEqual(ctx.exception.code, "cross-doc-schema-conflict")

    def test_cross_doc_same_name_identical_body_ok(self):
        shared = {"type": "object", "properties": {"id": {"type": "string"}}}
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_json(tmp, "a.json", _doc({"User": shared}))
            _write_json(tmp, "b.json", _doc({"User": shared}))
            docs = load_swagger(tmp)
        self.assertEqual(len(docs), 2)


class FormatRetentionTests(unittest.TestCase):
    """String format hints are retained on FieldType.format (plan 03).

    The IR carries the hint unconditionally (no flag involved at the
    loader layer); the primitive kind stays STRING so flag-off consumers
    of the IR are untouched.
    """

    def _field(self, doc, schema_name, wire_name):
        schema = next(s for s in doc.schemas if s.name == schema_name)
        return next(f for f in schema.fields if f.wire_name == wire_name)

    def test_recognized_formats_retained(self):
        doc = parse_swagger(_doc({
            "M": {
                "type": "object",
                "required": ["a", "b", "c"],
                "properties": {
                    "a": {"type": "string", "format": "date-time"},
                    "b": {"type": "string", "format": "uuid"},
                    "c": {"type": "string", "format": "binary"},
                },
            },
        }), "test.json")
        for wire, fmt in (("a", "date-time"), ("b", "uuid"), ("c", "binary")):
            f = self._field(doc, "M", wire)
            self.assertTrue(f.type.is_primitive)
            self.assertEqual(f.type.primitive, PrimitiveKind.STRING)
            self.assertEqual(f.type.format, fmt)

    def test_unrecognized_format_discarded(self):
        doc = parse_swagger(_doc({
            "M": {
                "type": "object",
                "required": ["a", "b"],
                "properties": {
                    "a": {"type": "string", "format": "email"},
                    "b": {"type": "string"},
                },
            },
        }), "test.json")
        self.assertIsNone(self._field(doc, "M", "a").type.format)
        self.assertIsNone(self._field(doc, "M", "b").type.format)

    def test_nullable_rebuild_preserves_format(self):
        """_extract_fields reconstructs FieldType to attach nullable — the
        format side channel must survive that rebuild (01 handover #3)."""
        doc = parse_swagger(_doc({
            "M": {
                "type": "object",
                "properties": {
                    "a": {"type": "string", "format": "date-time"},
                },
            },
        }), "test.json")
        f = self._field(doc, "M", "a")
        self.assertTrue(f.type.nullable)
        self.assertEqual(f.type.format, "date-time")

    def test_array_and_map_elements_carry_format(self):
        doc = parse_swagger(_doc({
            "M": {
                "type": "object",
                "required": ["xs", "m"],
                "properties": {
                    "xs": {"type": "array", "items": {"type": "string", "format": "date-time"}},
                    "m": {
                        "type": "object",
                        "additionalProperties": {"type": "string", "format": "uuid"},
                    },
                },
            },
        }), "test.json")
        self.assertEqual(self._field(doc, "M", "xs").type.element.format, "date-time")
        self.assertEqual(self._field(doc, "M", "m").type.element.format, "uuid")

    def test_wrapper_schema_carries_format(self):
        doc = parse_swagger(_doc({
            "Stamp": {"type": "string", "format": "date-time"},
        }), "test.json")
        wrapper = doc.schemas[0]
        self.assertTrue(wrapper.is_wrapper)
        self.assertEqual(wrapper.wrapped_type.format, "date-time")

    def test_integer_formats_untouched(self):
        doc = parse_swagger(_doc({
            "M": {
                "type": "object",
                "required": ["a"],
                "properties": {"a": {"type": "integer", "format": "int64"}},
            },
        }), "test.json")
        f = self._field(doc, "M", "a")
        self.assertEqual(f.type.primitive, PrimitiveKind.INTEGER_64)
        self.assertIsNone(f.type.format)


if __name__ == "__main__":
    unittest.main()
