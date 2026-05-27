"""Tests for web_api_model_generator — DTO + enum + Domain + camelCase mode."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jui_cli.core.openapi_loader import parse_swagger
from jui_cli.generators.web_api_model_generator import (
    WebApiModelGenerator,
    WebApiPlatformConfig,
)


def _gen(tmp: Path, case_convention: str = "snake_case") -> WebApiModelGenerator:
    return WebApiModelGenerator(
        WebApiPlatformConfig(
            sources_root=tmp,
            model_dir="models",
            dto_subdir="generated",
            case_convention=case_convention,
        )
    )


def _doc(schemas: dict) -> dict:
    return {
        "openapi": "3.0.3",
        "info": {"title": "T", "version": "1.0.0"},
        "components": {"schemas": schemas},
    }


def _user_schema():
    return {
        "User": {
            "type": "object",
            "required": ["id", "display_name"],
            "properties": {
                "id": {"type": "string"},
                "display_name": {"type": "string"},
                "age": {"type": "integer"},
                "is_premium": {"type": "boolean"},
            },
        },
    }


class SnakeCaseModeTests(unittest.TestCase):
    def test_snake_case_default(self):
        doc = parse_swagger(_doc(_user_schema()), "test.json")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "snake_case").generate_dto_source(doc.schemas[0], doc)
        self.assertIn("export interface UserDto {", src)
        self.assertIn("id: string;", src)
        # Wire name kept as-is in snake_case mode
        self.assertIn("display_name: string;", src)
        self.assertIn("is_premium?: boolean;", src)
        # Optional via ?: rather than | undefined
        self.assertNotIn("| undefined", src)
        # No parse/serialize helpers in snake_case mode
        self.assertNotIn("parseUser", src)
        self.assertNotIn("serializeUser", src)


class CamelCaseModeTests(unittest.TestCase):
    def test_camel_case_renames_fields(self):
        doc = parse_swagger(_doc(_user_schema()), "test.json")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "camelCase").generate_dto_source(doc.schemas[0], doc)
        self.assertIn("displayName: string;", src)
        self.assertIn("isPremium?: boolean;", src)
        # Wire-format alias interface emitted
        self.assertIn("export interface UserWire {", src)
        self.assertIn("display_name: string;", src)
        # parse/serialize helpers
        self.assertIn("export const parseUser = (wire: UserWire): UserDto => ({", src)
        self.assertIn("displayName: wire.display_name,", src)
        self.assertIn("export const serializeUser = (model: UserDto): UserWire => ({", src)
        self.assertIn("display_name: model.displayName,", src)

    def test_no_helpers_when_no_skew(self):
        """camelCase mode with all-camelCase wire names → no helpers needed."""
        doc = parse_swagger(_doc({
            "M": {
                "type": "object",
                "required": ["a", "b"],
                "properties": {
                    "a": {"type": "string"},
                    "b": {"type": "string"},
                },
            },
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp), "camelCase").generate_dto_source(doc.schemas[0], doc)
        self.assertNotIn("MWire", src)
        self.assertNotIn("parseM", src)


class InvalidCaseConventionTests(unittest.TestCase):
    def test_rejects_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                WebApiModelGenerator(
                    WebApiPlatformConfig(
                        sources_root=Path(tmp),
                        case_convention="PascalCase",
                    )
                )


class EnumEmissionTests(unittest.TestCase):
    def test_string_enum_literal_union(self):
        doc = parse_swagger(_doc({
            "AuthProvider": {"type": "string", "enum": ["google", "apple", "email"]},
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp)).generate_enum_source(doc.enums[0], doc)
        self.assertIn('export type AuthProvider = "google" | "apple" | "email";', src)

    def test_integer_enum(self):
        doc = parse_swagger(_doc({
            "Status": {"type": "integer", "enum": [0, 1, 2]},
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp)).generate_enum_source(doc.enums[0], doc)
        self.assertIn("export type Status = 0 | 1 | 2;", src)


class DomainScaffoldTests(unittest.TestCase):
    def test_factory_naming(self):
        """Per plan §2.2: ``{camelCaseName}FromDto``."""
        doc = parse_swagger(_doc({
            "OrderItem": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}},
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp)).generate_domain_source(doc.schemas[0])
        self.assertIn("export interface OrderItem {", src)
        self.assertIn("dto: OrderItemDto;", src)
        self.assertIn(
            "export const orderItemFromDto = (dto: OrderItemDto): OrderItem => ({ dto });",
            src,
        )
        # No @generated banner — user owns this file
        self.assertNotIn("@generated", src)

    def test_factory_leading_acronym(self):
        doc = parse_swagger(_doc({
            "HTTPResponse": {"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}}},
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp)).generate_domain_source(doc.schemas[0])
        self.assertIn("hTTPResponseFromDto", src)


class RefTypeTests(unittest.TestCase):
    def test_object_ref_uses_dto_suffix(self):
        doc = parse_swagger(_doc({
            "Tag": {"type": "object", "properties": {"n": {"type": "string"}}},
            "Article": {
                "type": "object",
                "required": ["tag"],
                "properties": {"tag": {"$ref": "#/components/schemas/Tag"}},
            },
        }), "test.json")
        article = next(s for s in doc.schemas if s.name == "Article")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp)).generate_dto_source(article, doc)
        self.assertIn("tag: TagDto;", src)
        self.assertIn('import type { TagDto } from "./TagDto";', src)

    def test_enum_ref_omits_dto_suffix(self):
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
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp)).generate_dto_source(user, doc)
        self.assertIn("provider: AuthProvider;", src)
        self.assertIn('import type { AuthProvider } from "./AuthProvider";', src)

    def test_array_and_map_types(self):
        doc = parse_swagger(_doc({
            "Tag": {"type": "object", "properties": {"n": {"type": "string"}}},
            "M": {
                "type": "object",
                "required": ["tags", "labels"],
                "properties": {
                    "tags": {"type": "array", "items": {"$ref": "#/components/schemas/Tag"}},
                    "labels": {
                        "type": "object",
                        "additionalProperties": {"$ref": "#/components/schemas/Tag"},
                    },
                },
            },
        }), "test.json")
        m = next(s for s in doc.schemas if s.name == "M")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp)).generate_dto_source(m, doc)
        self.assertIn("tags: TagDto[];", src)
        self.assertIn("labels: Record<string, TagDto>;", src)


class OneOfDiscriminatorTests(unittest.TestCase):
    """oneOf + discriminator emits a TypeScript discriminated-union type
    + ``parse{Name}Dto`` / ``serialize{Name}Dto`` helpers that dispatch
    on the sibling discriminator wire value. See bug
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

    def test_discriminated_union_type_emitted(self):
        doc = self._stream_event_doc()
        stream = next(s for s in doc.schemas if s.name == "StreamEvent")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp)).generate_dto_source(stream, doc)
        self.assertIn("export type StreamEventContent =", src)
        self.assertIn(
            '| { kind: "conversation_id"; data: StreamConvIdContentDto }',
            src,
        )
        self.assertIn(
            '| { kind: "thinking"; data: StreamThinkingContentDto }',
            src,
        )
        self.assertIn('| { kind: "unknown" };', src)

    def test_interface_uses_union_type(self):
        doc = self._stream_event_doc()
        stream = next(s for s in doc.schemas if s.name == "StreamEvent")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp)).generate_dto_source(stream, doc)
        self.assertIn("export interface StreamEventDto {", src)
        self.assertIn("content: StreamEventContent;", src)

    def test_parse_helper_dispatches_on_discriminator(self):
        doc = self._stream_event_doc()
        stream = next(s for s in doc.schemas if s.name == "StreamEvent")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp)).generate_dto_source(stream, doc)
        self.assertIn(
            "export const parseStreamEventDto = (wire: any): StreamEventDto =>",
            src,
        )
        self.assertIn('switch (wire["type"]) {', src)
        self.assertIn('case "conversation_id":', src)
        self.assertIn(
            'content = { kind: "conversation_id", data: '
            'wire["content"] as StreamConvIdContentDto };',
            src,
        )
        self.assertIn('default:\n      content = { kind: "unknown" };', src)

    def test_serialize_helper_unwraps_union(self):
        doc = self._stream_event_doc()
        stream = next(s for s in doc.schemas if s.name == "StreamEvent")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp)).generate_dto_source(stream, doc)
        self.assertIn(
            "export const serializeStreamEventDto = (model: StreamEventDto): any =>",
            src,
        )
        self.assertIn("switch (model.content.kind) {", src)
        self.assertIn('case "conversation_id":\n      content = model.content.data;', src)
        self.assertIn('case "unknown":\n      content = null;', src)


class WriteBehaviorTests(unittest.TestCase):
    def test_dto_written_idempotent(self):
        doc = parse_swagger(_doc(_user_schema()), "test.json")
        with tempfile.TemporaryDirectory() as tmp:
            gen = _gen(Path(tmp))
            r1 = gen.write_dto(doc.schemas[0], doc)
            self.assertTrue(r1.wrote)
            r2 = gen.write_dto(doc.schemas[0], doc)
            self.assertFalse(r2.wrote)

    def test_domain_skipped_when_existing(self):
        doc = parse_swagger(_doc(_user_schema()), "test.json")
        with tempfile.TemporaryDirectory() as tmp:
            gen = _gen(Path(tmp))
            first = gen.write_domain(doc.schemas[0])
            self.assertTrue(first.wrote)
            first.path.write_text("// custom\n", encoding="utf-8")
            second = gen.write_domain(doc.schemas[0])
            self.assertTrue(second.skipped_existing)
            self.assertEqual(first.path.read_text(), "// custom\n")


if __name__ == "__main__":
    unittest.main()
