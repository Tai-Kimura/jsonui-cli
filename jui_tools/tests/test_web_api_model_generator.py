"""Tests for web_api_model_generator — DTO + enum + Domain + camelCase mode."""
from __future__ import annotations

import re
import shutil
import subprocess
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


def _fmt_gen(
    tmp: Path,
    case_convention: str = "snake_case",
    excluded: frozenset[str] = frozenset(),
) -> WebApiModelGenerator:
    return WebApiModelGenerator(
        WebApiPlatformConfig(
            sources_root=tmp,
            model_dir="models",
            dto_subdir="generated",
            case_convention=case_convention,
            format_mapping=True,
            format_excluded_docs=excluded,
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


class WrapperSchemaTests(unittest.TestCase):
    """Non-object top-level schemas emit as TS type aliases — structural
    typing makes the alias indistinguishable from the underlying primitive
    at every call site."""

    def test_string_wrapper_emits_type_alias(self):
        doc = parse_swagger(_doc({
            "Thinking": {"type": "string", "description": "LLM text"},
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp)).generate_dto_source(doc.schemas[0], doc)
        self.assertIn("export type ThinkingDto = string;", src)
        self.assertIn("/** LLM text */", src)
        # No interface — wrapper is purely a type alias.
        self.assertNotIn("export interface ThinkingDto", src)

    def test_array_wrapper_imports_element_type(self):
        doc = parse_swagger(_doc({
            "Result": {"type": "object", "properties": {"id": {"type": "string"}}},
            "Results": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/Result"},
            },
        }), "test.json")
        results = next(s for s in doc.schemas if s.name == "Results")
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp)).generate_dto_source(results, doc)
        self.assertIn(
            'import type { ResultDto } from "./ResultDto";',
            src,
        )
        self.assertIn("export type ResultsDto = ResultDto[];", src)


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


class SchemaLevelUnionTests(unittest.TestCase):
    """Schema-level oneOf union emits a payload union type alias plus
    ``{Name}DtoCase`` / ``match{Name}Dto`` / ``serialize{Name}Dto``."""

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
                "properties": {"bark_volume": {"type": "integer"}},
            },
            "Cat": {
                "type": "object",
                "properties": {"lives_left": {"type": "integer"}},
            },
        }), "test.json")

    def _union_source(self):
        doc = self._pet_doc()
        with tempfile.TemporaryDirectory() as tmp:
            return _gen(Path(tmp)).generate_union_source(doc.unions[0], doc)

    def test_payload_union_type_alias(self):
        src = self._union_source()
        self.assertIn("export type PetDto = DogDto | CatDto;", src)
        self.assertIn('import type { CatDto } from "./CatDto";', src)
        self.assertIn('import type { DogDto } from "./DogDto";', src)

    def test_case_type_includes_unknown_arm(self):
        src = self._union_source()
        self.assertIn("export type PetDtoCase =", src)
        self.assertIn('| { kind: "dog"; data: DogDto }', src)
        self.assertIn('| { kind: "cat"; data: CatDto }', src)
        self.assertIn('| { kind: "unknown" };', src)

    def test_match_helper_dispatches_on_payload_tag(self):
        src = self._union_source()
        self.assertIn(
            "export const matchPetDto = (value: PetDto | unknown): PetDtoCase => {",
            src,
        )
        self.assertIn(
            'switch ((value as Record<string, unknown> | null)?.["pet_type"]) {',
            src,
        )
        self.assertIn('return { kind: "dog", data: value as DogDto };', src)
        self.assertIn('return { kind: "unknown" };', src)

    def test_serialize_helper_injects_tag(self):
        src = self._union_source()
        self.assertIn(
            "export const serializePetDto = (value: PetDtoCase): unknown => {",
            src,
        )
        self.assertIn('return { ...value.data, ["pet_type"]: "dog" };', src)
        self.assertIn('case "unknown":', src)
        self.assertIn("return {};", src)

    def test_union_domain_scaffold(self):
        doc = self._pet_doc()
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp)).generate_union_domain_source(doc.unions[0])
        self.assertIn("export interface Pet {", src)
        self.assertIn("dto: PetDto;", src)
        self.assertIn(
            "export const petFromDto = (dto: PetDto): Pet => ({ dto });", src
        )
        self.assertIn("matchPetDto(dto)", src)

    def test_schema_referencing_union_imports_and_uses_dto_type(self):
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
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp)).generate_dto_source(owner, doc)
        self.assertIn('import type { PetDto } from "./PetDto";', src)
        self.assertIn("pet: PetDto;", src)


class FormatAwareMappingTests(unittest.TestCase):
    """Opt-in format-aware mapping (plan 2026-07-24-v1-unsupported/03)."""

    def _event_schemas(self):
        return {
            "Attachment": {
                "type": "object",
                "required": ["id", "data"],
                "properties": {
                    "id": {"type": "string", "format": "uuid"},
                    "data": {"type": "string", "format": "binary"},
                    "created_at": {"type": "string", "format": "date-time"},
                },
            },
            "Event": {
                "type": "object",
                "required": ["at", "tags"],
                "properties": {
                    "at": {"type": "string", "format": "date-time"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string", "format": "date-time"},
                    },
                    "attachment": {"$ref": "#/components/schemas/Attachment"},
                    "note": {"type": "string"},
                },
            },
            "Plain": {
                "type": "object",
                "required": ["x"],
                "properties": {"x": {"type": "string"}},
            },
        }

    def _event_doc(self):
        return parse_swagger(_doc(self._event_schemas()), "test.json")

    def test_native_types_and_wire_helpers(self):
        doc = self._event_doc()
        event = next(s for s in doc.schemas if s.name == "Event")
        with tempfile.TemporaryDirectory() as tmp:
            src = _fmt_gen(Path(tmp)).generate_dto_source(event, doc)
        self.assertIn("at: Date;", src)
        self.assertIn("tags: Date[];", src)
        self.assertIn("export interface EventWire {", src)
        self.assertIn("at: string;", src)
        self.assertIn("tags: string[];", src)
        self.assertIn("export const parseEventDto = (wire: EventWire): EventDto =>", src)
        self.assertIn("at: parseIsoDate(wire.at)", src)
        self.assertIn("tags: wire.tags.map((v0) => parseIsoDate(v0))", src)
        self.assertIn("export const serializeEventDto = (model: EventDto): EventWire =>", src)
        self.assertIn("at: model.at.toISOString()", src)
        # invalid dates throw instead of producing Invalid Date silently
        self.assertIn("Number.isNaN(parsed.getTime())", src)

    def test_affected_ref_delegates(self):
        doc = self._event_doc()
        event = next(s for s in doc.schemas if s.name == "Event")
        with tempfile.TemporaryDirectory() as tmp:
            src = _fmt_gen(Path(tmp)).generate_dto_source(event, doc)
        self.assertIn(
            'import { parseAttachmentDto, serializeAttachmentDto } from "./AttachmentDto";',
            src,
        )
        self.assertIn(
            'import type { AttachmentDto, AttachmentWire } from "./AttachmentDto";',
            src,
        )
        self.assertIn("attachment?: AttachmentWire;", src)
        self.assertIn(
            "attachment: wire.attachment == null ? undefined : "
            "parseAttachmentDto(wire.attachment)",
            src,
        )

    def test_uuid_binary_aliases(self):
        doc = self._event_doc()
        attachment = next(s for s in doc.schemas if s.name == "Attachment")
        with tempfile.TemporaryDirectory() as tmp:
            src = _fmt_gen(Path(tmp)).generate_dto_source(attachment, doc)
        self.assertIn('import type { Uuid } from "./Uuid";', src)
        self.assertIn('import type { Base64Data } from "./Base64Data";', src)
        self.assertIn("id: Uuid;", src)
        self.assertIn("data: Base64Data;", src)
        # aliases are strings — no conversion in parse/serialize
        self.assertIn("id: wire.id", src)
        self.assertIn("data: wire.data", src)

    def test_unaffected_schema_output_unchanged(self):
        doc = self._event_doc()
        plain = next(s for s in doc.schemas if s.name == "Plain")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            on = _fmt_gen(tmp_path).generate_dto_source(plain, doc)
            off = _gen(tmp_path).generate_dto_source(plain, doc)
        self.assertEqual(on, off)

    def test_flag_off_and_opt_out_unchanged(self):
        doc = self._event_doc()
        event = next(s for s in doc.schemas if s.name == "Event")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            off = _gen(tmp_path).generate_dto_source(event, doc)
            excluded = _fmt_gen(tmp_path, excluded=frozenset({"test.json"})).generate_dto_source(event, doc)
        self.assertEqual(off, excluded)
        self.assertNotIn("Date", off)
        self.assertNotIn("EventWire", off)

    def test_camel_case_unified_with_dates(self):
        doc = self._event_doc()
        attachment = next(s for s in doc.schemas if s.name == "Attachment")
        with tempfile.TemporaryDirectory() as tmp:
            src = _fmt_gen(Path(tmp), "camelCase").generate_dto_source(attachment, doc)
        # DTO renamed, Wire keeps wire names, one helper pair does both jobs
        self.assertIn("createdAt?: Date;", src)
        self.assertIn("created_at?: string;", src)
        self.assertIn(
            "createdAt: wire.created_at == null ? undefined : parseIsoDate(wire.created_at)",
            src,
        )
        self.assertIn(
            "created_at: model.createdAt == null ? undefined : model.createdAt.toISOString()",
            src,
        )
        # the old camel-skew helpers are subsumed, not duplicated
        self.assertNotIn("export const parseAttachment =", src)

    def test_support_file_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            gen = _fmt_gen(Path(tmp))
            uuid_src = gen.generate_uuid_alias_source()
            b64_src = gen.generate_base64_alias_source()
        self.assertIn("export type Uuid = string;", uuid_src)
        self.assertIn("export type Base64Data = string;", b64_src)
        self.assertIn("@generated", uuid_src)

    def test_wrapper_date_alias_and_helpers(self):
        doc = parse_swagger(_doc({
            "Stamp": {"type": "string", "format": "date-time"},
        }), "test.json")
        with tempfile.TemporaryDirectory() as tmp:
            src = _fmt_gen(Path(tmp)).generate_dto_source(doc.schemas[0], doc)
        self.assertIn("export type StampDto = Date;", src)
        self.assertIn("export type StampWire = string;", src)
        self.assertIn(
            "export const parseStampDto = (wire: StampWire): StampDto => parseIsoDate(wire);",
            src,
        )
        self.assertIn(
            "export const serializeStampDto = (value: StampDto): StampWire => value.toISOString();",
            src,
        )


class FormatAwareUnionTests(unittest.TestCase):
    """Schema-level unions with date-affected variants delegate (plan 03)."""

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
                "required": ["born_at"],
                "properties": {"born_at": {"type": "string", "format": "date-time"}},
            },
            "Cat": {
                "type": "object",
                "properties": {"lives_left": {"type": "integer"}},
            },
        }), "test.json")

    def test_union_wire_and_parse_delegation(self):
        doc = self._pet_doc()
        with tempfile.TemporaryDirectory() as tmp:
            src = _fmt_gen(Path(tmp)).generate_union_source(doc.unions[0], doc)
        self.assertIn(
            'import { parseDogDto, serializeDogDto } from "./DogDto";', src
        )
        self.assertIn("export type PetWire = DogWire | CatDto;", src)
        self.assertIn(
            "export const parsePetDto = (wire: PetWire | unknown): PetDto => {", src
        )
        self.assertIn("return parseDogDto(wire as DogWire);", src)
        self.assertIn("return wire as CatDto;", src)
        # serialize delegates the affected variant, injects the tag
        self.assertIn(
            'return { ...serializeDogDto(value.data), ["pet_type"]: "dog" };', src
        )
        self.assertIn('return { ...value.data, ["pet_type"]: "cat" };', src)

    def test_union_flag_off_unchanged(self):
        doc = self._pet_doc()
        with tempfile.TemporaryDirectory() as tmp:
            src = _gen(Path(tmp)).generate_union_source(doc.unions[0], doc)
        self.assertNotIn("PetWire", src)
        self.assertNotIn("parsePetDto", src)

    def test_parent_referencing_affected_union_delegates(self):
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
                "required": ["born_at"],
                "properties": {"born_at": {"type": "string", "format": "date-time"}},
            },
            "Owner": {
                "type": "object",
                "required": ["pet"],
                "properties": {"pet": {"$ref": "#/components/schemas/Pet"}},
            },
        }), "test.json")
        owner = next(s for s in doc.schemas if s.name == "Owner")
        with tempfile.TemporaryDirectory() as tmp:
            src = _fmt_gen(Path(tmp)).generate_dto_source(owner, doc)
        self.assertIn("pet: parsePetDto(wire.pet)", src)
        self.assertIn("pet: serializePetDto(model.pet)", src)


@unittest.skipUnless(shutil.which("node"), "node not available")
class NodeRoundTripTests(unittest.TestCase):
    """Semantic round-trip of the generated web code, executed on node.

    Node ≥ 22.6 strips erasable TS syntax natively, so the generated
    files run as-is once the extensionless relative imports are given an
    explicit ``.ts`` extension (a test-harness concern only — bundlers
    resolve extensionless imports fine).
    """

    def _write_generated(self, gen: WebApiModelGenerator, doc, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        for schema in doc.schemas:
            src = gen.generate_dto_source(schema, doc)
            src = re.sub(r'from "\./([A-Za-z0-9_]+)";', r'from "./\1.ts";', src)
            (out_dir / f"{schema.name}Dto.ts").write_text(src, encoding="utf-8")
        (out_dir / "Uuid.ts").write_text(gen.generate_uuid_alias_source(), encoding="utf-8")
        (out_dir / "Base64Data.ts").write_text(gen.generate_base64_alias_source(), encoding="utf-8")

    def test_round_trip_semantics(self):
        doc = parse_swagger(_doc({
            "Attachment": {
                "type": "object",
                "required": ["id", "data"],
                "properties": {
                    "id": {"type": "string", "format": "uuid"},
                    "data": {"type": "string", "format": "binary"},
                    "created_at": {"type": "string", "format": "date-time"},
                },
            },
            "Event": {
                "type": "object",
                "required": ["at", "tags"],
                "properties": {
                    "at": {"type": "string", "format": "date-time"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string", "format": "date-time"},
                    },
                    "attachment": {"$ref": "#/components/schemas/Attachment"},
                    "note": {"type": "string"},
                },
            },
        }), "test.json")
        harness = """
import { parseEventDto, serializeEventDto } from "./EventDto.ts";

const wire = {
  at: "2026-07-24T12:34:56.789Z",
  tags: ["2026-07-24T00:00:00+09:00"],
  attachment: {
    id: "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    data: "aGVsbG8=",
    created_at: "2026-07-23T01:02:03Z",
  },
  note: "hi",
};
const dto = parseEventDto(wire as any);
if (!(dto.at instanceof Date)) throw new Error("at is not a Date");
if (dto.at.toISOString() !== "2026-07-24T12:34:56.789Z") throw new Error("at value");
// TZ normalization is semantic equivalence, not byte equivalence:
// +09:00 re-emits as UTC.
if (dto.tags[0].toISOString() !== "2026-07-23T15:00:00.000Z") throw new Error("tz normalize");
if (!(dto.attachment!.created_at instanceof Date)) throw new Error("nested date");
if (dto.attachment!.id !== wire.attachment.id) throw new Error("uuid passthrough");
if (dto.attachment!.data !== wire.attachment.data) throw new Error("binary passthrough");

const wire2 = serializeEventDto(dto);
const dto2 = parseEventDto(wire2 as any);
if (dto2.at.getTime() !== dto.at.getTime()) throw new Error("round-trip at");
if (dto2.tags[0].getTime() !== dto.tags[0].getTime()) throw new Error("round-trip tag");
if (dto2.attachment!.created_at!.getTime() !== dto.attachment!.created_at!.getTime()) {
  throw new Error("round-trip nested");
}

let threw = false;
try {
  parseEventDto({ at: "not-a-date", tags: [] } as any);
} catch {
  threw = true;
}
if (!threw) throw new Error("invalid date must throw");
console.log("ROUND_TRIP_OK");
"""
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "generated"
            self._write_generated(_fmt_gen(Path(tmp)), doc, out_dir)
            harness_path = out_dir / "harness.ts"
            harness_path.write_text(harness, encoding="utf-8")
            proc = subprocess.run(
                ["node", "--experimental-strip-types", "--no-warnings", str(harness_path)],
                capture_output=True,
                text=True,
                timeout=60,
            )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("ROUND_TRIP_OK", proc.stdout)


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
