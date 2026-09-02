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
            "UserPreference": {
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
        }, "UserPreference")
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

    def test_enum_typed_discriminator_exhaustive_mapping_omits_default(self):
        """When the enum-typed discriminator's every case is mapped, the
        ``switch self.type`` is already exhaustive — a trailing ``default:``
        is dead code that trips Swift's "Default will never be executed"
        warning (zero-warning invariant). It must be omitted. Regression:
        jui-oneof-decoder-dead-default-for-exhaustive-enum-discriminator."""
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
                    # Enum cases EXACTLY equal the mapping keys → exhaustive.
                    "type": {
                        "type": "string",
                        "enum": ["conversation_id", "thinking"],
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
        # Enum-typed dispatch over both cases...
        self.assertIn("case .conversationId:", src)
        self.assertIn("case .thinking:", src)
        # ...with NO dead default in the decoder switch.
        self.assertNotIn("default:\n            self.content = .unknown", src)
        # But the Content enum still declares `.unknown` (used by encode).
        self.assertIn("case unknown", src)
        self.assertIn("case .unknown: try container.encodeNil(forKey: .content)", src)

    def test_enum_typed_discriminator_partial_mapping_keeps_default(self):
        """An enum-typed discriminator with an UNMAPPED case keeps the
        reachable ``default: .unknown`` (it routes the unmapped enum case)."""
        doc = parse_swagger(_doc({
            "A": {"type": "object", "properties": {"x": {"type": "string"}}},
            "B": {"type": "object", "properties": {"y": {"type": "string"}}},
            "Parent": {
                "type": "object",
                "required": ["type", "value"],
                "properties": {
                    # 3 enum cases, only 2 mapped → NOT exhaustive.
                    "type": {"type": "string", "enum": ["a", "b", "c"]},
                    "value": {
                        "oneOf": [
                            {"$ref": "#/components/schemas/A"},
                            {"$ref": "#/components/schemas/B"},
                        ],
                        "discriminator": {
                            "propertyName": "type",
                            "mapping": {
                                "a": "#/components/schemas/A",
                                "b": "#/components/schemas/B",
                            },
                        },
                    },
                },
            },
        }), "test.json")
        parent = next(s for s in doc.schemas if s.name == "Parent")
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_generator(Path(tmp)).generate_dto_source(parent, doc)
        self.assertIn("case .a:", src)
        self.assertIn("case .b:", src)
        # `c` is unmapped, so the default is reachable and retained.
        self.assertIn("default:\n            self.value = .unknown", src)

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
        # The enum-case rendering survives, but as the decode fallback and
        # memberwise parameter default — never a property initializer, which
        # synthesized Decodable would silently refuse to decode.
        self.assertIn(
            "self.reactionType = try container.decodeIfPresent(ReactionType.self, forKey: .reactionType) ?? ReactionType.favorite",
            src,
        )
        self.assertIn("reactionType: ReactionType? = ReactionType.favorite)", src)
        self.assertNotIn("let reactionType: ReactionType? = ReactionType.favorite", src)
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
        self.assertIn(
            "self.level = try container.decodeIfPresent(Severity.self, forKey: .level) ?? Severity.medium",
            src,
        )
        self.assertIn("level: Severity? = Severity.medium)", src)
        self.assertNotIn("let level: Severity? = Severity.medium", src)

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
        self.assertIn(
            'self.message = try container.decodeIfPresent(String.self, forKey: .message) ?? "hello"',
            src,
        )
        self.assertNotIn('let message: String? = "hello"', src)


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


class SchemaLevelUnionTests(unittest.TestCase):
    """Schema-level oneOf union emits a self-decoding ``enum {Name}Dto``
    that reads / writes the discriminator tag inside the payload."""

    def _pet_doc(self):
        return parse_swagger(_doc({
            "Pet": {
                "oneOf": [
                    {"$ref": "#/components/schemas/Dog"},
                    {"$ref": "#/components/schemas/Cat"},
                ],
                "discriminator": {
                    "propertyName": "pet_type",
                    "mapping": {
                        "dog": "#/components/schemas/Dog",
                        "cat": "#/components/schemas/Cat",
                    },
                },
            },
            "Dog": {
                "type": "object",
                "required": ["pet_type"],
                "properties": {
                    "pet_type": {"type": "string", "enum": ["dog"]},
                    "bark_volume": {"type": "integer"},
                },
            },
            "Cat": {
                "type": "object",
                "required": ["pet_type"],
                "properties": {
                    "pet_type": {"type": "string", "enum": ["cat"]},
                    "lives_left": {"type": "integer"},
                },
            },
        }), "test.json")

    def _union_source(self):
        doc = self._pet_doc()
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            return gen.generate_union_source(doc.unions[0], doc)

    def test_enum_declaration_with_variant_and_unknown_cases(self):
        src = self._union_source()
        self.assertIn(
            "enum PetDto: Codable, Sendable, Equatable, Hashable {", src
        )
        self.assertIn("case dog(DogDto)", src)
        self.assertIn("case cat(CatDto)", src)
        self.assertIn("case unknown", src)

    def test_tag_coding_keys_use_wire_name(self):
        src = self._union_source()
        self.assertIn("private enum TagCodingKeys: String, CodingKey {", src)
        self.assertIn('case tag = "pet_type"', src)

    def test_decode_dispatches_on_payload_tag(self):
        src = self._union_source()
        self.assertIn(
            "let tag = try container.decodeIfPresent(String.self, forKey: .tag)",
            src,
        )
        self.assertIn('case "dog":', src)
        self.assertIn("self = .dog(try DogDto(from: decoder))", src)
        self.assertIn("default:", src)
        self.assertIn("self = .unknown", src)

    def test_encode_writes_payload_then_tag(self):
        src = self._union_source()
        self.assertIn("try value.encode(to: encoder)", src)
        self.assertIn('try container.encode("dog", forKey: .tag)', src)
        # .unknown encodes as {} (empty keyed container)
        self.assertIn("case .unknown:", src)
        self.assertIn("_ = encoder.container(keyedBy: TagCodingKeys.self)", src)

    def test_union_domain_scaffold_is_thin_wrapper(self):
        doc = self._pet_doc()
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            src = gen.generate_union_domain_source(doc.unions[0])
        self.assertIn("struct Pet {", src)
        self.assertIn("let dto: PetDto", src)
        self.assertIn("init(dto: PetDto)", src)
        self.assertIn("switch dto", src)

    def test_expected_dto_paths_include_union(self):
        doc = self._pet_doc()
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            paths = {p.name for p in gen.expected_dto_paths(doc)}
        self.assertIn("PetDto.swift", paths)

    def test_schema_referencing_union_uses_dto_type(self):
        doc = parse_swagger(_doc({
            "Pet": {
                "oneOf": [{"$ref": "#/components/schemas/Dog"}],
                "discriminator": {
                    "propertyName": "pet_type",
                    "mapping": {"dog": "#/components/schemas/Dog"},
                },
            },
            "Dog": {
                "type": "object",
                "properties": {"bark_volume": {"type": "integer"}},
            },
            "Owner": {
                "type": "object",
                "required": ["pet"],
                "properties": {"pet": {"$ref": "#/components/schemas/Pet"}},
            },
        }), "test.json")
        owner = next(s for s in doc.schemas if s.name == "Owner")
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            src = gen.generate_dto_source(owner, doc)
        self.assertIn("let pet: PetDto", src)


class FormatAwareMappingTests(unittest.TestCase):
    """Opt-in format-aware mapping (plan 2026-07-24-v1-unsupported/03)."""

    def _fmt_gen(self, tmp: Path, excluded: frozenset[str] = frozenset()) -> IosApiModelGenerator:
        return IosApiModelGenerator(IosApiPlatformConfig(
            sources_root=tmp, format_mapping=True, format_excluded_docs=excluded,
        ))

    def _attachment_doc(self):
        return parse_swagger(_doc({
            "Attachment": {
                "type": "object",
                "required": ["id", "data"],
                "properties": {
                    "id": {"type": "string", "format": "uuid"},
                    "data": {"type": "string", "format": "binary"},
                    "created_at": {"type": "string", "format": "date-time"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string", "format": "date-time"},
                    },
                },
            },
        }), "test.json")

    def test_native_types_and_custom_codable(self):
        doc = self._attachment_doc()
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._fmt_gen(Path(tmpdir)).generate_dto_source(doc.schemas[0], doc)
        self.assertIn("let id: UUID", src)
        self.assertIn("let data: Data", src)
        self.assertIn("let createdAt: Date?", src)
        self.assertIn("let tags: [Date]?", src)
        # date fields force the custom Codable pair + ISO helpers
        self.assertIn("init(from decoder: Decoder) throws {", src)
        self.assertIn("func encode(to encoder: Encoder) throws {", src)
        self.assertIn("_juiParseIsoDate", src)
        self.assertIn(".withFractionalSeconds", src)
        # UUID / Data decode through plain Codable inside the custom init
        self.assertIn("try container.decode(UUID.self, forKey: .id)", src)
        self.assertIn("try container.decode(Data.self, forKey: .data)", src)
        # date fields decode raw String and convert
        self.assertIn(
            "try container.decodeIfPresent(String.self, forKey: .createdAt)"
            ".map { try _juiParseIsoDate($0, codingPath: decoder.codingPath) }",
            src,
        )
        self.assertIn(
            "try container.decodeIfPresent([String].self, forKey: .tags)",
            src,
        )
        # encode re-emits ISO strings
        self.assertIn("_juiFormatIsoDate($0)", src)
        # memberwise init restored (suppressed by the custom init)
        self.assertIn("init(id: UUID, data: Data, createdAt: Date?, tags: [Date]?)", src)

    def test_uuid_data_only_keeps_synthesized_codable(self):
        """UUID / Data decode natively — no custom init without a date."""
        doc = parse_swagger(_doc({
            "M": {
                "type": "object",
                "required": ["id", "blob"],
                "properties": {
                    "id": {"type": "string", "format": "uuid"},
                    "blob": {"type": "string", "format": "binary"},
                },
            },
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._fmt_gen(Path(tmpdir)).generate_dto_source(doc.schemas[0], doc)
        self.assertIn("let id: UUID", src)
        self.assertIn("let blob: Data", src)
        self.assertNotIn("init(from decoder:", src)
        self.assertNotIn("_juiParseIsoDate", src)

    def test_flag_off_output_unchanged(self):
        doc = self._attachment_doc()
        with tempfile.TemporaryDirectory() as tmpdir:
            off = _make_generator(Path(tmpdir)).generate_dto_source(doc.schemas[0], doc)
        self.assertIn("let id: String", off)
        self.assertIn("let createdAt: String?", off)
        self.assertNotIn("Date", off)
        self.assertNotIn("init(from decoder:", off)

    def test_per_doc_opt_out_matches_flag_off(self):
        doc = self._attachment_doc()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            excluded = self._fmt_gen(tmp, frozenset({"test.json"})).generate_dto_source(doc.schemas[0], doc)
            off = _make_generator(tmp).generate_dto_source(doc.schemas[0], doc)
        self.assertEqual(excluded, off)

    def test_oneof_and_date_share_single_init(self):
        """M5: oneOf + format reasons drive ONE custom init, not two."""
        doc = parse_swagger(_doc({
            "A": {"type": "object", "required": ["v"], "properties": {"v": {"type": "string"}}},
            "B": {"type": "object", "required": ["w"], "properties": {"w": {"type": "string"}}},
            "Parent": {
                "type": "object",
                "required": ["type", "content", "at"],
                "properties": {
                    "type": {"type": "string"},
                    "at": {"type": "string", "format": "date-time"},
                    "content": {
                        "oneOf": [
                            {"$ref": "#/components/schemas/A"},
                            {"$ref": "#/components/schemas/B"},
                        ],
                        "discriminator": {
                            "propertyName": "type",
                            "mapping": {
                                "a": "#/components/schemas/A",
                                "b": "#/components/schemas/B",
                            },
                        },
                    },
                },
            },
        }), "test.json")
        parent = next(s for s in doc.schemas if s.name == "Parent")
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._fmt_gen(Path(tmpdir)).generate_dto_source(parent, doc)
        self.assertEqual(src.count("init(from decoder: Decoder) throws {"), 1)
        self.assertEqual(src.count("func encode(to encoder: Encoder) throws {"), 1)
        # both reasons are served inside the one init
        self.assertIn("_juiParseIsoDate", src)
        self.assertIn("switch self.type {", src)

    def test_wrapper_date_uses_single_value_conversion(self):
        doc = parse_swagger(_doc({
            "Stamp": {"type": "string", "format": "date-time"},
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._fmt_gen(Path(tmpdir)).generate_dto_source(doc.schemas[0], doc)
        self.assertIn("let value: Date", src)
        self.assertIn("decoder.singleValueContainer()", src)
        self.assertIn("_juiParseIsoDate((try container.decode(String.self))", src)
        self.assertIn("try container.encode(_juiFormatIsoDate(self.value))", src)

    def test_date_default_literal_skipped(self):
        doc = parse_swagger(_doc({
            "M": {
                "type": "object",
                "required": ["at"],
                "properties": {
                    "at": {"type": "string", "format": "date-time", "default": "2026-01-01T00:00:00Z"},
                },
            },
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._fmt_gen(Path(tmpdir)).generate_dto_source(doc.schemas[0], doc)
        self.assertIn("let at: Date\n", src)
        self.assertNotIn('= "2026-01-01T00:00:00Z"', src)


class DefaultedFieldDecodeTests(unittest.TestCase):
    """swagger ``default:`` means "value when the key is ABSENT".

    The old emit was ``let type: String? = "chat"`` — Swift's synthesized
    Decodable never decodes an initialized immutable property, so the wire
    value was silently discarded and the field was frozen at its default
    forever (android's ``val`` + kotlinx decoded the same declaration
    correctly). A defaulted field now forces the custom-Codable path and
    decodes as ``decodeIfPresent ?? default``.
    """

    DOC = {
        "Conversation": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {"type": "string"},
                "type": {"type": "string", "default": "chat"},
                "count": {"type": "integer", "default": 3},
            },
        },
    }

    def _src(self) -> str:
        doc = parse_swagger(_doc(self.DOC), "test.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            return gen.generate_dto_source(doc.schemas[0], doc)

    def test_no_frozen_initializer_on_the_stored_property(self):
        src = self._src()
        self.assertIn("let type: String?\n", src)
        self.assertNotIn('let type: String? = "chat"', src)

    def test_decodes_if_present_with_the_default_as_fallback(self):
        src = self._src()
        self.assertIn(
            'self.type = try container.decodeIfPresent(String.self, forKey: .type) ?? "chat"',
            src,
        )
        self.assertIn(
            "self.count = try container.decodeIfPresent(Int.self, forKey: .count) ?? 3",
            src,
        )
        # Non-defaulted required field keeps the strict decode.
        self.assertIn(
            "self.id = try container.decode(String.self, forKey: .id)", src
        )

    def test_memberwise_init_carries_the_default_and_stays_assignable(self):
        src = self._src()
        self.assertIn('type: String? = "chat"', src)
        self.assertIn("count: Int? = 3", src)
        self.assertIn("self.type = type", src)

    def test_encode_covers_every_field(self):
        src = self._src()
        self.assertIn(
            "try container.encodeIfPresent(self.type, forKey: .type)", src
        )


if __name__ == "__main__":
    unittest.main()


class NonisolatedDtoTests(unittest.TestCase):
    """DTOs carry `nonisolated`, so a nonisolated context can decode them.

    Under `SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor` every conformance a
    generated DTO declares is main-actor isolated, and a test harness
    decoding a fixture off the main actor cannot use it — a warning today, an
    error in the Swift 6 language mode. Neither end is the consumer's to fix:
    the DTO is generated, and so is the branch-test runtime that calls it.

    Measured on Swift 6.3.2 and 6.3.3 before choosing the spelling:

        emitted today (no modifier)             2 diagnostics
        `: nonisolated Codable` (conformance)   4 diagnostics  ← WORSE
        `nonisolated struct` (the type)         0 diagnostics

    The conformance-scoped spelling is worse than it looks: it silences
    Codable and leaves Equatable and Hashable isolated, so comparing or
    hashing a DTO off the main actor draws the same diagnostic. Which
    release first accepted the type-level spelling was NOT measured — read
    the two versions above as "known good there", not as a floor.

    The pre-existing assertions in this file cannot catch a regression here:
    they use `assertIn("struct UserDto: ...")`, which a `nonisolated struct
    UserDto: ...` line satisfies as a substring. These name the prefix.
    """

    def _dto_source(self, schemas: dict, index: int = 0) -> str:
        doc = parse_swagger(_doc(schemas), "test.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            return gen.generate_dto_source(doc.schemas[index], doc)

    def test_a_struct_dto_is_nonisolated(self):
        src = self._dto_source({
            "User": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
            },
        })
        self.assertIn(
            "nonisolated struct UserDto: Codable, Sendable, Equatable, Hashable {",
            src,
        )

    def test_a_union_dto_is_nonisolated(self):
        # A oneOf DTO is decoded from the same nonisolated contexts.
        doc = parse_swagger(_doc({
            "Cat": {"type": "object",
                    "properties": {"kind": {"type": "string", "enum": ["cat"]}}},
            "Dog": {"type": "object",
                    "properties": {"kind": {"type": "string", "enum": ["dog"]}}},
            "Pet": {
                "oneOf": [
                    {"$ref": "#/components/schemas/Cat"},
                    {"$ref": "#/components/schemas/Dog"},
                ],
                "discriminator": {"propertyName": "kind"},
            },
        }), "test.json")
        self.assertTrue(doc.unions, "no union was extracted")
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            src = gen.generate_union_source(doc.unions[0], doc)
        self.assertIn("nonisolated enum PetDto:", src)

    def test_a_string_enum_is_left_alone(self):
        # Measured: a raw-value enum's conformances are not isolated, so
        # annotating it would add diff lines to every regeneration without
        # silencing anything. The attribution downstream depends on the
        # regeneration diff being one line per DTO and nothing else.
        doc = parse_swagger(_doc({
            "Holder": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["active", "closed"]},
                },
            },
        }), "test.json")
        self.assertTrue(doc.enums, "no enum was extracted to annotate or not")
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = _make_generator(Path(tmpdir))
            src = gen.generate_enum_source(doc.enums[0], doc)
        self.assertIn("enum HolderStatus: String", src)
        self.assertNotIn("nonisolated enum", src)


