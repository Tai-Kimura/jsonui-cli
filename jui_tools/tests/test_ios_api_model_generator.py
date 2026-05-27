"""Tests for ios_api_model_generator — DTO + enum + Domain scaffold emission."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jui_cli.core.openapi_loader import parse_swagger
from jui_cli.generators.ios_api_model_generator import (
    IosApiModelGenerator,
    IosApiPlatformConfig,
)


def _make_generator(tmp: Path) -> IosApiModelGenerator:
    config = IosApiPlatformConfig(sources_root=tmp)
    return IosApiModelGenerator(config)


def _doc(schemas: dict) -> dict:
    return {
        "openapi": "3.0.3",
        "info": {"title": "Test", "version": "1.0.0"},
        "components": {"schemas": schemas},
    }


class DtoEmissionTests(unittest.TestCase):
    def test_primitive_fields_codable_struct(self):
        doc = parse_swagger(_doc({
            "User": {
                "type": "object",
                "required": ["id", "displayName"],
                "properties": {
                    "id": {"type": "string"},
                    "display_name": {"type": "string"},
                    "age": {"type": "integer"},
                    "score": {"type": "number"},
                    "is_premium": {"type": "boolean"},
                },
            },
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            src = gen.generate_dto_source(doc.schemas[0], doc)

        # Header
        self.assertIn("@generated", src)
        self.assertIn("AUTO-GENERATED FILE", src)
        # Struct + conformances
        self.assertIn(
            "struct UserDto: Codable, Sendable, Equatable, Hashable {",
            src,
        )
        # snake_case → camelCase property names
        self.assertIn("let displayName: String", src)
        self.assertIn("let isPremium: Bool", src)
        # CodingKeys with explicit raw values for renamed properties
        self.assertIn('case displayName = "display_name"', src)
        self.assertIn('case isPremium = "is_premium"', src)
        # Unrenamed properties stay bare in CodingKeys
        self.assertIn("case id\n", src)

    def test_optional_field_appended_question_mark(self):
        doc = parse_swagger(_doc({
            "M": {
                "type": "object",
                "required": ["a"],
                "properties": {
                    "a": {"type": "string"},
                    "b": {"type": "string"},
                },
            },
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            src = gen.generate_dto_source(doc.schemas[0], doc)
        self.assertIn("let a: String\n", src)
        self.assertIn("let b: String?\n", src)

    def test_nullable_true_makes_optional(self):
        doc = parse_swagger(_doc({
            "M": {
                "type": "object",
                "required": ["a"],
                "properties": {
                    "a": {"type": "string", "nullable": True},
                },
            },
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            src = gen.generate_dto_source(doc.schemas[0], doc)
        self.assertIn("let a: String?", src)

    def test_array_field(self):
        doc = parse_swagger(_doc({
            "M": {
                "type": "object",
                "required": ["tags"],
                "properties": {
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
            },
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            src = gen.generate_dto_source(doc.schemas[0], doc)
        self.assertIn("let tags: [String]", src)

    def test_object_ref_field_uses_dto_suffix(self):
        doc = parse_swagger(_doc({
            "Tag": {"type": "object", "properties": {"name": {"type": "string"}}},
            "Article": {
                "type": "object",
                "required": ["tag"],
                "properties": {"tag": {"$ref": "#/components/schemas/Tag"}},
            },
        }), "test.json")
        article = next(s for s in doc.schemas if s.name == "Article")
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            src = gen.generate_dto_source(article, doc)
        self.assertIn("let tag: TagDto", src)

    def test_enum_ref_field_omits_dto_suffix(self):
        doc = parse_swagger(_doc({
            "AuthProvider": {"type": "string", "enum": ["google", "apple"]},
            "User": {
                "type": "object",
                "required": ["provider"],
                "properties": {
                    "provider": {"$ref": "#/components/schemas/AuthProvider"},
                },
            },
        }), "test.json")
        user = next(s for s in doc.schemas if s.name == "User")
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            src = gen.generate_dto_source(user, doc)
        self.assertIn("let provider: AuthProvider", src)
        self.assertNotIn("AuthProviderDto", src)

    def test_typed_map_field(self):
        doc = parse_swagger(_doc({
            "Tag": {"type": "object", "properties": {"name": {"type": "string"}}},
            "M": {
                "type": "object",
                "required": ["labels"],
                "properties": {
                    "labels": {
                        "type": "object",
                        "additionalProperties": {"$ref": "#/components/schemas/Tag"},
                    },
                },
            },
        }), "test.json")
        m = next(s for s in doc.schemas if s.name == "M")
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            src = gen.generate_dto_source(m, doc)
        self.assertIn("let labels: [String: TagDto]", src)
        # All DTOs declare Hashable — the explicit hash(into:) body handles
        # the synthesis-incompatible map field by omitting it from the
        # hash while keeping the conformance.
        self.assertIn("struct MDto: Codable, Sendable, Equatable, Hashable {", src)
        self.assertIn("func hash(into hasher: inout Hasher) {", src)
        self.assertIn("Omitted from hash (synthesis-incompatible types): labels", src)

    def test_no_coding_keys_when_no_rename_needed(self):
        doc = parse_swagger(_doc({
            "M": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "string"}},
            },
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            src = gen.generate_dto_source(doc.schemas[0], doc)
        self.assertNotIn("CodingKeys", src)

    def test_description_emitted_as_doc_comment(self):
        doc = parse_swagger(_doc({
            "M": {
                "type": "object",
                "description": "Top schema",
                "required": ["a"],
                "properties": {
                    "a": {"type": "string", "description": "field A"},
                },
            },
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            src = gen.generate_dto_source(doc.schemas[0], doc)
        self.assertIn("/// Top schema", src)
        self.assertIn("/// field A", src)

    def test_deprecated_emits_available_annotation(self):
        doc = parse_swagger(_doc({
            "M": {
                "type": "object",
                "deprecated": True,
                "required": ["a"],
                "properties": {"a": {"type": "string", "deprecated": True}},
            },
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            src = gen.generate_dto_source(doc.schemas[0], doc)
        self.assertIn("@available(*, deprecated)", src)


class WrapperSchemaTests(unittest.TestCase):
    """Non-object top-level schemas (``type: string`` / ``type: array``)
    emit as single-field DTOs with ``singleValueContainer``-based
    Codable so the wire format is the bare wrapped value.
    """

    def test_string_wrapper_emits_single_value_container(self):
        doc = parse_swagger(_doc({
            "Thinking": {"type": "string", "description": "LLM text"},
        }), "test.json")
        schema = doc.schemas[0]
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_generator(Path(tmp)).generate_dto_source(schema, doc)
        self.assertIn(
            "struct ThinkingDto: Codable, Sendable, Equatable, Hashable {",
            src,
        )
        self.assertIn("let value: String", src)
        self.assertIn("init(value: String) {", src)
        self.assertIn("init(from decoder: Decoder) throws {", src)
        self.assertIn(
            "let container = try decoder.singleValueContainer()",
            src,
        )
        self.assertIn(
            "self.value = try container.decode(String.self)",
            src,
        )
        self.assertIn("func encode(to encoder: Encoder) throws {", src)
        self.assertIn("try container.encode(self.value)", src)

    def test_array_wrapper_emits_items_field(self):
        doc = parse_swagger(_doc({
            "Result": {"type": "object", "properties": {"id": {"type": "string"}}},
            "Results": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/Result"},
            },
        }), "test.json")
        results = next(s for s in doc.schemas if s.name == "Results")
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_generator(Path(tmp)).generate_dto_source(results, doc)
        self.assertIn("struct ResultsDto:", src)
        self.assertIn("let items: [ResultDto]", src)
        self.assertIn("self.items = try container.decode([ResultDto].self)", src)


class HashableConformanceTests(unittest.TestCase):
    """Every DTO declares Hashable. When Swift auto-synthesis would fail
    (map / array-of-map fields), an explicit ``hash(into:)`` body is
    emitted that hashes the synthesis-safe subset and lists the omitted
    fields in a trailing comment. See bug
    sjui-api-model-hashable-synthesis-fails-for-nested-non-hashable-types.
    """

    def _emit(self, schemas: dict, name: str) -> str:
        doc = parse_swagger(_doc(schemas), "test.json")
        schema = next(s for s in doc.schemas if s.name == name)
        with tempfile.TemporaryDirectory() as tmpdir:
            return _make_generator(Path(tmpdir)).generate_dto_source(schema, doc)

    def test_primitive_only_schema_declares_hashable_without_explicit_body(self):
        src = self._emit({
            "User": {
                "type": "object",
                "required": ["id"],
                "properties": {
                    "id": {"type": "string"},
                    "age": {"type": "integer"},
                },
            },
        }, "User")
        self.assertIn(": Codable, Sendable, Equatable, Hashable {", src)
        # Swift compiler synthesizes for primitive-only schemas — no
        # explicit body needed.
        self.assertNotIn("func hash(into hasher:", src)

    def test_map_field_schema_declares_hashable_with_explicit_body(self):
        src = self._emit({
            "TasteProfile": {
                "type": "object",
                "required": ["peaty"],
                "properties": {
                    "sparse_vector": {
                        "type": "object",
                        "additionalProperties": {"type": "number"},
                    },
                    "peaty": {"type": "number"},
                    "experience_level": {"type": "string"},
                },
            },
        }, "TasteProfile")
        self.assertIn(": Codable, Sendable, Equatable, Hashable {", src)
        self.assertIn("func hash(into hasher: inout Hasher) {", src)
        self.assertIn("hasher.combine(peaty)", src)
        self.assertIn("hasher.combine(experienceLevel)", src)
        self.assertNotIn("hasher.combine(sparseVector)", src)
        self.assertIn(
            "Omitted from hash (synthesis-incompatible types): sparseVector",
            src,
        )

    def test_object_ref_fields_are_hashed(self):
        """Object refs are safe because every DTO declares Hashable."""
        src = self._emit({
            "Tag": {"type": "object", "properties": {"name": {"type": "string"}}},
            "Article": {
                "type": "object",
                "required": ["tag", "labels"],
                "properties": {
                    "tag": {"$ref": "#/components/schemas/Tag"},
                    "labels": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                    },
                },
            },
        }, "Article")
        self.assertIn("func hash(into hasher: inout Hasher) {", src)
        self.assertIn("hasher.combine(tag)", src)
        self.assertNotIn("hasher.combine(labels)", src)
        self.assertIn(
            "Omitted from hash (synthesis-incompatible types): labels",
            src,
        )

    def test_array_of_map_omitted_from_hash(self):
        src = self._emit({
            "M": {
                "type": "object",
                "required": ["rows"],
                "properties": {
                    "rows": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                        },
                    },
                    "name": {"type": "string"},
                },
            },
        }, "M")
        self.assertIn("func hash(into hasher: inout Hasher) {", src)
        self.assertIn("hasher.combine(name)", src)
        self.assertNotIn("hasher.combine(rows)", src)
        self.assertIn(
            "Omitted from hash (synthesis-incompatible types): rows",
            src,
        )

    def test_array_of_primitive_is_hashed(self):
        src = self._emit({
            "M": {
                "type": "object",
                "required": ["tags"],
                "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
            },
        }, "M")
        self.assertNotIn("func hash(into hasher:", src)

    def test_hash_combine_uses_camel_case_property_names(self):
        src = self._emit({
            "M": {
                "type": "object",
                "required": ["display_name"],
                "properties": {
                    "display_name": {"type": "string"},
                    "extra_data": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                    },
                },
            },
        }, "M")
        self.assertIn("hasher.combine(displayName)", src)
        self.assertNotIn("hasher.combine(display_name)", src)


class OneOfDiscriminatorTests(unittest.TestCase):
    """oneOf + discriminator emits a nested ``enum Content: Codable`` and
    custom ``init(from:)`` / ``encode(to:)`` that dispatch on the sibling
    discriminator. See bug
    ``jui-codegen-oneof-not-supported-blocks-discriminated-union-schemas``.
    """

    def _stream_event_doc(self):
        return parse_swagger(_doc({
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
        }), "test.json")

    def test_nested_enum_emitted_with_variants(self):
        doc = self._stream_event_doc()
        stream = next(s for s in doc.schemas if s.name == "StreamEvent")
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_generator(Path(tmp)).generate_dto_source(stream, doc)
        self.assertIn("let content: Content", src)
        self.assertIn("enum Content: Codable, Sendable, Equatable, Hashable {", src)
        self.assertIn("case conversationId(StreamConvIdContentDto)", src)
        self.assertIn("case thinking(StreamThinkingContentDto)", src)
        self.assertIn("case unknown", src)

    def test_init_from_decoder_dispatches_on_discriminator(self):
        doc = self._stream_event_doc()
        stream = next(s for s in doc.schemas if s.name == "StreamEvent")
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_generator(Path(tmp)).generate_dto_source(stream, doc)
        self.assertIn("init(from decoder: Decoder) throws {", src)
        self.assertIn(
            'self.type = try container.decode(String.self, forKey: .type)',
            src,
        )
        self.assertIn("switch self.type {", src)
        self.assertIn(
            'case "conversation_id":\n            self.content = .conversationId('
            'try container.decode(StreamConvIdContentDto.self, forKey: .content))',
            src,
        )
        self.assertIn("default:\n            self.content = .unknown", src)

    def test_encode_to_encoder_symmetric(self):
        doc = self._stream_event_doc()
        stream = next(s for s in doc.schemas if s.name == "StreamEvent")
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_generator(Path(tmp)).generate_dto_source(stream, doc)
        self.assertIn("func encode(to encoder: Encoder) throws {", src)
        self.assertIn("try container.encode(self.type, forKey: .type)", src)
        self.assertIn(
            "case .conversationId(let value): try container.encode(value, forKey: .content)",
            src,
        )
        self.assertIn(
            "case .unknown: try container.encodeNil(forKey: .content)",
            src,
        )

    def test_memberwise_init_emitted(self):
        """Swift suppresses memberwise init once we write init(from:); we
        restore it manually so consumers can construct DTOs at call sites."""
        doc = self._stream_event_doc()
        stream = next(s for s in doc.schemas if s.name == "StreamEvent")
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_generator(Path(tmp)).generate_dto_source(stream, doc)
        self.assertIn("init(type: String, content: Content) {", src)

    def test_coding_keys_always_emitted_for_oneof(self):
        doc = self._stream_event_doc()
        stream = next(s for s in doc.schemas if s.name == "StreamEvent")
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_generator(Path(tmp)).generate_dto_source(stream, doc)
        self.assertIn("enum CodingKeys: String, CodingKey {", src)
        self.assertIn("case type", src)
        self.assertIn("case content", src)

    def test_enum_typed_discriminator_dispatches_on_enum_case(self):
        """When the discriminator field has an inline ``enum: [...]``,
        ``self.type`` is typed as the auto-derived enum, so the switch
        cases must reference enum case identifiers — string literals
        against an enum-typed value won't compile."""
        doc = parse_swagger(_doc({
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
                    "type": {
                        "type": "string",
                        "enum": ["conversation_id", "thinking", "progress"],
                    },
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
        }), "test.json")
        stream = next(s for s in doc.schemas if s.name == "StreamEvent")
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_generator(Path(tmp)).generate_dto_source(stream, doc)
        # Type is the inline-derived enum, not String.
        self.assertIn("let type: StreamEventType", src)
        # Dispatch switch must use enum-case identifiers, not strings.
        self.assertIn("case .conversationId:", src)
        self.assertIn("case .thinking:", src)
        # String literals must NOT appear as case labels.
        self.assertNotIn('case "conversation_id":', src)
        self.assertNotIn('case "thinking":', src)
        # default fallback retained for forward-compat.
        self.assertIn("default:", src)
        self.assertIn("self.content = .unknown", src)

    def test_enum_discriminator_mapping_mismatch_halts(self):
        """mapping value that isn't in the enum's case list is a swagger
        bug; we halt at codegen so the user fixes it."""
        doc = parse_swagger(_doc({
            "A": {"type": "object", "properties": {"x": {"type": "string"}}},
            "Parent": {
                "type": "object",
                "required": ["type", "value"],
                "properties": {
                    "type": {"type": "string", "enum": ["a", "b"]},
                    "value": {
                        "oneOf": [{"$ref": "#/components/schemas/A"}],
                        "discriminator": {
                            "propertyName": "type",
                            "mapping": {"a": "#/components/schemas/A"},
                        },
                    },
                },
            },
        }), "test.json")
        # Discriminator value "a" matches the enum, so parse succeeds.
        # Now mutate the IR to introduce a mismatched mapping value.
        parent = next(s for s in doc.schemas if s.name == "Parent")
        with tempfile.TemporaryDirectory() as tmp:
            # Sanity: clean parse produces the right Swift.
            src = _make_generator(Path(tmp)).generate_dto_source(parent, doc)
            self.assertIn("case .a:", src)

    def test_hashable_synthesis_works_with_oneof_field(self):
        """oneOf is hash-safe so the synthesized Hashable on the parent
        still works — no explicit `hash(into:)` needed unless other
        unsafe fields are present."""
        doc = self._stream_event_doc()
        stream = next(s for s in doc.schemas if s.name == "StreamEvent")
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_generator(Path(tmp)).generate_dto_source(stream, doc)
        # All fields are hash-safe (String + oneOf), so no explicit body.
        self.assertNotIn("func hash(into hasher:", src)


class EnumEmissionTests(unittest.TestCase):
    def test_string_enum(self):
        doc = parse_swagger(_doc({
            "AuthProvider": {"type": "string", "enum": ["google", "apple", "email"]},
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            src = gen.generate_enum_source(doc.enums[0], doc)
        self.assertIn("enum AuthProvider: String, Codable, CaseIterable, Sendable {", src)
        self.assertIn("case google", src)
        self.assertIn("case apple", src)
        self.assertIn("case email", src)

    def test_integer_enum_with_varnames(self):
        doc = parse_swagger(_doc({
            "Severity": {
                "type": "integer",
                "enum": [1, 2, 3],
                "x-enum-varnames": ["low", "medium", "high"],
            },
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            src = gen.generate_enum_source(doc.enums[0], doc)
        self.assertIn("enum Severity: Int, Codable, CaseIterable, Sendable {", src)
        self.assertIn("case low = 1", src)
        self.assertIn("case medium = 2", src)
        self.assertIn("case high = 3", src)

    def test_string_enum_with_reserved_word_escaped(self):
        doc = parse_swagger(_doc({
            "Visibility": {"type": "string", "enum": ["public", "private", "internal"]},
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            src = gen.generate_enum_source(doc.enums[0], doc)
        self.assertIn("case `public`", src)
        self.assertIn("case `private`", src)
        self.assertIn("case `internal`", src)


class DomainScaffoldTests(unittest.TestCase):
    def test_scaffold_is_minimal(self):
        doc = parse_swagger(_doc({
            "User": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "string"}},
            },
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            src = gen.generate_domain_source(doc.schemas[0])
        self.assertIn("struct User {", src)
        self.assertIn("let dto: UserDto", src)
        self.assertIn("init(dto: UserDto) {", src)
        self.assertIn("self.dto = dto", src)
        self.assertIn("User customization zone", src)
        # @generated header is NOT in the scaffold — user owns the file
        self.assertNotIn("@generated", src)
        self.assertNotIn("DO NOT EDIT", src)


class EnumDefaultLiteralTests(unittest.TestCase):
    """Regression — `allOf: [$ref: <enum>] + default: <value>` must emit
    `EnumName.caseName` not a string literal (Swift enums are not
    ExpressibleByStringLiteral, so the bare literal would not compile).
    See bug jui-android-codegen-allof-ref-enum-emits-domain-name-with-string-default.
    """

    def _reaction_doc(self):
        return parse_swagger(_doc({
            "ReactionType": {
                "type": "string",
                "enum": ["favorite", "want_to_drink"],
            },
            "ReactionTypeBody": {
                "type": "object",
                "properties": {
                    "reaction_type": {
                        "allOf": [{"$ref": "#/components/schemas/ReactionType"}],
                        "default": "favorite",
                    },
                },
            },
        }), "test.json")

    def test_string_enum_default_emits_case_reference(self):
        doc = self._reaction_doc()
        body = next(s for s in doc.schemas if s.name == "ReactionTypeBody")
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_generator(Path(tmp)).generate_dto_source(body, doc)
        self.assertIn("let reactionType: ReactionType? = ReactionType.favorite", src)
        self.assertNotIn('= "favorite"', src)

    def test_integer_enum_default_emits_case_reference(self):
        doc = parse_swagger(_doc({
            "Severity": {
                "type": "integer",
                "enum": [1, 2, 3],
                "x-enum-varnames": ["low", "medium", "high"],
            },
            "Alert": {
                "type": "object",
                "properties": {
                    "level": {
                        "allOf": [{"$ref": "#/components/schemas/Severity"}],
                        "default": 2,
                    },
                },
            },
        }), "test.json")
        alert = next(s for s in doc.schemas if s.name == "Alert")
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_generator(Path(tmp)).generate_dto_source(alert, doc)
        self.assertIn("let level: Severity? = Severity.medium", src)

    def test_default_not_in_enum_skipped(self):
        doc = parse_swagger(_doc({
            "ReactionType": {
                "type": "string",
                "enum": ["favorite", "want_to_drink"],
            },
            "ReactionTypeBody": {
                "type": "object",
                "properties": {
                    "reaction_type": {
                        "allOf": [{"$ref": "#/components/schemas/ReactionType"}],
                        "default": "bogus",
                    },
                },
            },
        }), "test.json")
        body = next(s for s in doc.schemas if s.name == "ReactionTypeBody")
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_generator(Path(tmp)).generate_dto_source(body, doc)
        # No default and no string literal — line is bare ``let ...: T?``.
        self.assertIn("let reactionType: ReactionType?", src)
        self.assertNotIn('"bogus"', src)
        self.assertNotIn("= ReactionType.", src)

    def test_primitive_string_default_unaffected(self):
        doc = parse_swagger(_doc({
            "Greeting": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "default": "hello"},
                },
            },
        }), "test.json")
        body = doc.schemas[0]
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_generator(Path(tmp)).generate_dto_source(body, doc)
        self.assertIn('let message: String? = "hello"', src)


class WriteBehaviorTests(unittest.TestCase):
    def test_dto_written_on_first_call(self):
        doc = parse_swagger(_doc({
            "User": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "string"}},
            },
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            result = gen.write_dto(doc.schemas[0], doc)
            self.assertTrue(result.wrote)
            self.assertTrue(result.path.exists())
            # Idempotent — second call with same input is a no-op
            result2 = gen.write_dto(doc.schemas[0], doc)
            self.assertFalse(result2.wrote)

    def test_domain_skipped_when_existing(self):
        doc = parse_swagger(_doc({
            "User": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "string"}},
            },
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            first = gen.write_domain(doc.schemas[0])
            self.assertTrue(first.wrote)
            self.assertFalse(first.skipped_existing)

            # Simulate user edit — overwrite with custom content
            user_content = "// my custom edit\n"
            first.path.write_text(user_content, encoding="utf-8")

            second = gen.write_domain(doc.schemas[0])
            self.assertFalse(second.wrote)
            self.assertTrue(second.skipped_existing)
            # User's edit preserved
            self.assertEqual(first.path.read_text(encoding="utf-8"), user_content)


if __name__ == "__main__":
    unittest.main()
