"""Web DTOs say "may be omitted" and "may be null" apart (ticket
jui-web-api-model-types-nullable-fields-as-optional-only).

The loader folds "not in `required`" and "`nullable: true`" into one flag,
`FieldType.nullable`, and web rendered that flag as `?:` alone: a field the
server sends as JSON `null` was typed `T | undefined`, so a view model that
trusted the type let `null` through (`lat !== undefined`). `FieldDef.nullable`
now carries the declaration apart, and web renders

    required, nullable      name: T | null
    not required            name?: T
    not required, nullable  name?: T | null

and carries `null` through parse / serialize as `null`. iOS and Android keep
reading the folded flag — an optional there already admits nil — so their
output is the same bytes whatever the new flag says.
"""
from __future__ import annotations

import dataclasses
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

SCHEMAS = {
    "Place": {
        "type": "object",
        "required": ["name", "lat", "seen_at"],
        "properties": {
            "name": {"type": "string"},
            "lat": {"type": "number", "nullable": True},                          # required, nullable
            "note": {"type": "string"},                                           # optional
            "lng": {"type": "number", "nullable": True},                          # optional, nullable
            "seen_at": {"type": "string", "format": "date-time", "nullable": True},  # required, nullable
            "due_at": {"type": "string", "format": "date-time"},                  # optional
            "left_at": {"type": "string", "format": "date-time", "nullable": True},  # both
        },
    },
}


def _doc():
    return parse_swagger({"openapi": "3.0.3", "info": {"title": "T", "version": "1"},
                          "components": {"schemas": SCHEMAS}}, "test.json")


def _gen(tmp: Path, case: str = "snake_case", formats: bool = False) -> WebApiModelGenerator:
    return WebApiModelGenerator(WebApiPlatformConfig(
        sources_root=tmp, model_dir="models", dto_subdir="generated",
        case_convention=case, format_mapping=formats))


def _src(case="snake_case", formats=False) -> str:
    doc = _doc()
    with tempfile.TemporaryDirectory() as tmp:
        return _gen(Path(tmp), case, formats).generate_dto_source(doc.schemas[0], doc)


class TheIrKeepsTheTwoApart(unittest.TestCase):
    def test_each_field_says_required_and_nullable(self):
        fields = {f.wire_name: (f.required, f.nullable) for f in _doc().schemas[0].fields}
        self.assertEqual(fields, {
            "name": (True, False), "lat": (True, True), "note": (False, False),
            "lng": (False, True), "seen_at": (True, True), "due_at": (False, False),
            "left_at": (False, True)})


class TheDtoSaysBoth(unittest.TestCase):
    EXPECTED = ["name: string;", "lat: number | null;", "note?: string;",
                "lng?: number | null;"]

    def test_snake_case(self):
        src = _src("snake_case")
        for line in self.EXPECTED + ["seen_at: string | null;", "due_at?: string;",
                                     "left_at?: string | null;"]:
            self.assertIn(f"  {line}", src)

    def test_camel_case_dto_and_wire(self):
        src = _src("camelCase")
        dto = src.split("export interface PlaceDto {")[1].split("}")[0]
        wire = src.split("export interface PlaceWire {")[1].split("}")[0]
        for line in ["lat: number | null;", "lng?: number | null;", "seenAt: string | null;",
                     "leftAt?: string | null;", "note?: string;"]:
            self.assertIn(f"  {line}", dto)
        for line in ["lat: number | null;", "lng?: number | null;", "seen_at: string | null;",
                     "left_at?: string | null;", "note?: string;"]:
            self.assertIn(f"  {line}", wire)

    def test_format_mapping_dto_and_wire(self):
        src = _src("camelCase", formats=True)
        dto = src.split("export interface PlaceDto {")[1].split("}")[0]
        wire = src.split("export interface PlaceWire {")[1].split("}")[0]
        for line in ["seenAt: Date | null;", "dueAt?: Date;", "leftAt?: Date | null;"]:
            self.assertIn(f"  {line}", dto)
        for line in ["seen_at: string | null;", "due_at?: string;", "left_at?: string | null;"]:
            self.assertIn(f"  {line}", wire)

    def test_control_nothing_else_moves(self):
        # A schema with no `nullable: true` renders as it always did.
        src = _src("snake_case")
        self.assertEqual(src.count("| null"), 4)
        self.assertNotIn("| undefined", src)


class NullIsCarriedAsNull(unittest.TestCase):
    def test_a_converted_field_keeps_null_and_undefined_apart(self):
        src = _src("camelCase", formats=True)
        # declared nullable: null stays null (and an absent one stays absent)
        self.assertIn("seenAt: wire.seen_at == null ? wire.seen_at : parseIsoDate(wire.seen_at)",
                      src)
        self.assertIn("leftAt: wire.left_at == null ? wire.left_at : parseIsoDate(wire.left_at)",
                      src)
        self.assertIn("seen_at: model.seenAt == null ? model.seenAt : model.seenAt.toISOString()",
                      src)
        # optional only: as before — the type admits undefined, not null
        self.assertIn("dueAt: wire.due_at == null ? undefined : parseIsoDate(wire.due_at)", src)

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_round_trip_on_node(self):
        harness = """
import { parsePlaceDto, serializePlaceDto } from "./PlaceDto.ts";
const dto = parsePlaceDto({ name: "a", lat: null, seen_at: null, left_at: null } as any);
if (dto.lat !== null) throw new Error("lat must be null");
if (dto.seenAt !== null) throw new Error("seenAt must be null");
if (dto.leftAt !== null) throw new Error("leftAt must be null");
if (dto.dueAt !== undefined) throw new Error("dueAt must be undefined");
const absent = parsePlaceDto({ name: "a", lat: 1, seen_at: "2026-01-02T03:04:05Z" } as any);
if (absent.leftAt !== undefined) throw new Error("an absent leftAt must stay undefined");
if (!(absent.seenAt instanceof Date)) throw new Error("seenAt must be a Date");
const wire = serializePlaceDto(dto);
if (wire.seen_at !== null || wire.left_at !== null) throw new Error("serialize keeps null");
console.log("NULL_OK");
"""
        doc = _doc()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "generated"
            out.mkdir()
            src = _gen(Path(tmp), "camelCase", formats=True).generate_dto_source(doc.schemas[0], doc)
            (out / "PlaceDto.ts").write_text(
                re.sub(r'from "\./([A-Za-z0-9_]+)";', r'from "./\1.ts";', src), encoding="utf-8")
            (out / "harness.ts").write_text(harness, encoding="utf-8")
            proc = subprocess.run(["node", "--experimental-strip-types", "--no-warnings",
                                   str(out / "harness.ts")], capture_output=True, text=True,
                                  timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("NULL_OK", proc.stdout)


def _one_of(nullable: bool) -> dict:
    return {"oneOf": [{"$ref": "#/components/schemas/Dog"}, {"$ref": "#/components/schemas/Cat"}],
            "discriminator": {"propertyName": "kind", "mapping": {
                "dog": "#/components/schemas/Dog", "cat": "#/components/schemas/Cat"}},
            **({"nullable": True} if nullable else {})}


#: Every place iOS / Android read a field's optionality: plain fields, dates
#: (the custom decoder / encoder under format mapping), and a oneOf field
#: (its own type function) — each required-and-nullable and optional-and-nullable.
NATIVE_SCHEMAS = {
    **SCHEMAS,
    "Dog": {"type": "object", "required": ["bark"], "properties": {"bark": {"type": "string"}}},
    "Cat": {"type": "object", "required": ["purr"], "properties": {"purr": {"type": "string"}}},
    "Pet": {"type": "object", "required": ["kind", "body"],
            "properties": {"kind": {"type": "string"}, "body": _one_of(True),
                           "spare": _one_of(True), "plain": _one_of(False)}},
}


class IosAndAndroidAreTheSameBytes(unittest.TestCase):
    """They read the folded flag. The same document with `FieldDef.nullable`
    cleared on every field must generate the same bytes — DTOs and domain
    scaffolds, with and without format mapping — so the new flag reaches
    neither."""

    def _cleared(self, doc):
        schemas = [dataclasses.replace(s, fields=[dataclasses.replace(f, nullable=False)
                                                  for f in s.fields]) for s in doc.schemas]
        return dataclasses.replace(doc, schemas=schemas)

    def _doc(self):
        return parse_swagger({"openapi": "3.0.3", "info": {"title": "T", "version": "1"},
                              "components": {"schemas": NATIVE_SCHEMAS}}, "test.json")

    def _sources(self, doc):
        from jui_cli.generators.android_api_model_generator import (
            AndroidApiModelGenerator, AndroidApiPlatformConfig)
        from jui_cli.generators.ios_api_model_generator import (
            IosApiModelGenerator, IosApiPlatformConfig)
        out = []
        with tempfile.TemporaryDirectory() as tmp:
            for formats in (False, True):
                gens = [(IosApiModelGenerator(IosApiPlatformConfig(
                            sources_root=Path(tmp), format_mapping=formats)), doc.schemas),
                        (AndroidApiModelGenerator(AndroidApiPlatformConfig(
                            sources_root=Path(tmp), format_mapping=formats,
                            serializer="kotlinx")), doc.schemas)]
                if not formats:
                    # moshi, the default, where it applies (no oneOf there)
                    gens.append((AndroidApiModelGenerator(AndroidApiPlatformConfig(
                        sources_root=Path(tmp), serializer="moshi")),
                        [s for s in doc.schemas
                         if not any(f.type.is_one_of_ref for f in s.fields)]))
                for gen, schemas in gens:
                    out += [gen.generate_dto_source(s, doc) for s in schemas]
                    out += [gen.generate_domain_source(s) for s in schemas]
        return out

    def test_the_new_flag_changes_no_byte(self):
        doc = self._doc()
        pet = next(s for s in doc.schemas if s.name == "Pet")
        # the flag is set where it could matter: plain, date and oneOf fields
        self.assertEqual({f.wire_name: (f.required, f.nullable) for f in pet.fields
                          if f.type.is_one_of_ref},
                         {"body": (True, True), "spare": (False, True), "plain": (False, False)})
        self.assertEqual(self._sources(doc), self._sources(self._cleared(doc)))


if __name__ == "__main__":
    unittest.main()
