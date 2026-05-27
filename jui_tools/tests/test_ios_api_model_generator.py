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
        # Map drops Hashable
        self.assertIn("struct MDto: Codable, Sendable, Equatable {", src)
        self.assertNotIn(", Hashable", src)

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
