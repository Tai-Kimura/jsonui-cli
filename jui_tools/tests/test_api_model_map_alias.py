"""A top-level schema that is only a typed ``additionalProperties`` is a map alias.

Ticket jui-api-model-ref-to-map-schema-generates-empty-dto: such a schema
(``{type: object, additionalProperties: {type: string}}``, no ``properties``)
used to fall through to ``_extract_fields``, which reads ``properties`` only,
and became a DTO with no fields on every face — iOS decoded it and dropped
every entry (and wrote ``{}`` back), Kotlin refused the empty data class
(kotlinx and moshi alike), web typed it ``{}``. Whatever the path that
referenced it (a field, an array element, a map value, an allOf / anyOf-null
wrapper, a schema-level allOf, a top-level array) and whatever the value type.

It is now a ``typealias`` of the map on iOS / Kotlin and ``export type`` on
web — the same type a map written in place gets, readable as
``dto.name["ja"]`` with every Android serializer. Not a wrapper like a
top-level array: an array needs a field name to be held in a struct, a
dictionary does not.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from jui_cli.core.openapi_loader import OpenAPILoadError, parse_swagger
from jui_cli.generators.android_api_model_generator import (
    AndroidApiModelGenerator,
    AndroidApiPlatformConfig,
    _patch_kotlinx_domain,
)
from jui_cli.generators.ios_api_model_generator import (
    IosApiModelGenerator,
    IosApiPlatformConfig,
)
from jui_cli.generators.web_api_model_generator import (
    WebApiModelGenerator,
    WebApiPlatformConfig,
)

R = "#/components/schemas/"


def _ref(name: str) -> dict:
    return {"$ref": R + name}


def _doc(schemas: dict) -> dict:
    return {"openapi": "3.0.3", "info": {"title": "t", "version": "1"}, "paths": {},
            "components": {"schemas": schemas}}


def _parse(schemas: dict):
    return parse_swagger(_doc(schemas), "/repro/swagger.json")


# Every path the family table measured, with a value type of each kind.
SCHEMAS = {
    "Color": {"type": "string", "enum": ["red", "blue"]},
    "Obj": {"type": "object", "properties": {"a": {"type": "string"}}},
    "LocalizedText": {"type": "object", "description": "language code -> text",
                      "additionalProperties": {"type": "string"}},
    "Counts": {"type": "object", "additionalProperties": {"type": "integer"}},
    "ObjMap": {"type": "object", "additionalProperties": _ref("Obj")},
    "ColorMap": {"type": "object", "additionalProperties": _ref("Color")},
    "InlineMap": {"type": "object", "additionalProperties": {
        "type": "object", "properties": {"a": {"type": "string"}}}},
    "ListMap": {"type": "object", "additionalProperties": {"type": "array", "items": {"type": "string"}}},
    "Nested": {"type": "object", "additionalProperties": _ref("LocalizedText")},
    "Wrapped": {"allOf": [_ref("LocalizedText")]},
    "TopArr": {"type": "array", "items": _ref("LocalizedText")},
    "Kind": {"type": "object", "required": ["name"], "properties": {
        "name": _ref("LocalizedText"),
        "opt": _ref("LocalizedText"),
        "arr": {"type": "array", "items": _ref("LocalizedText")},
        "map_of_alias": {"type": "object", "additionalProperties": _ref("LocalizedText")},
        "nested": _ref("Nested"),
        "wrapped": _ref("Wrapped"),
        "nullable": {"allOf": [_ref("LocalizedText")], "nullable": True},
        "any_null": {"anyOf": [_ref("LocalizedText"), {"type": "null"}]},
        "counts": _ref("Counts"),
        "objs": _ref("ObjMap"),
        "colors": _ref("ColorMap"),
        "inl": _ref("InlineMap"),
        "lists": _ref("ListMap"),
    }},
}
ALIASES = {"LocalizedText", "Counts", "ObjMap", "ColorMap", "InlineMap", "ListMap", "Nested", "Wrapped"}
KIND_JSON = ('{"name":{"ja":"酒","en":"sake"},"opt":{"en":"x"},"arr":[{"a":"b"}],"map_of_alias":{"k":{"ja":"y"}},'
             '"nested":{"o":{"ja":"z"}},"wrapped":{"w":"1"},"any_null":{"q":"r"},"counts":{"c":3},'
             '"objs":{"o1":{"a":"x"}},"colors":{"c1":"red"},"inl":{"i":{"a":"v"}},"lists":{"l":["a","b"]}}')


class LoaderTests(unittest.TestCase):
    def test_every_map_only_schema_is_an_alias_of_its_map(self):
        doc = _parse(SCHEMAS)
        by = {s.name: s for s in doc.schemas}
        self.assertEqual({n for n, s in by.items() if s.is_map_alias}, ALIASES)
        for name in ALIASES:
            self.assertTrue(by[name].wrapped_type.is_map, name)
            self.assertEqual(len(by[name].fields), 1, name)   # never a DTO with no fields
        # the inline value object is named as a map written in place would name it
        self.assertIn("InlineMapValue", by)
        self.assertFalse(by["Kind"].is_map_alias)
        self.assertFalse(by["TopArr"].is_map_alias)

    def test_every_ref_to_an_alias_carries_its_map(self):
        kind = {f.wire_name: f.type for f in {s.name: s for s in _parse(SCHEMAS).schemas}["Kind"].fields}
        for name in ("name", "opt", "nullable", "any_null", "nested", "wrapped", "counts"):
            self.assertIsNotNone(kind[name].alias_map, name)
            self.assertTrue(kind[name].alias_map.is_map, name)
        self.assertIsNotNone(kind["arr"].element.alias_map)
        self.assertIsNotNone(kind["map_of_alias"].element.alias_map)
        # through an alias of an alias
        self.assertIsNotNone(kind["nested"].alias_map.element.alias_map)

    def test_a_schema_with_properties_too_stays_an_object(self):
        doc = _parse({"M": {"type": "object", "properties": {"id": {"type": "string"}},
                            "additionalProperties": {"type": "string"}}})
        m = doc.schemas[0]
        self.assertFalse(m.is_map_alias)
        self.assertEqual([f.wire_name for f in m.fields], ["id"])

    def test_an_empty_value_schema_halts_as_it_does_in_place(self):
        for body in ({"type": "object", "additionalProperties": {}},
                     {"type": "object", "properties": {"f": {"type": "object", "additionalProperties": {}}}}):
            with self.assertRaises(OpenAPILoadError) as cm:
                _parse({"M": body})
            self.assertEqual(cm.exception.code, "unknown-type")

    def test_an_untyped_map_still_halts(self):
        with self.assertRaises(OpenAPILoadError) as cm:
            _parse({"M": {"type": "object", "additionalProperties": True}})
        self.assertEqual(cm.exception.code, "object-without-type")

    def test_an_alias_reaching_itself_through_aliases_halts(self):
        for schemas in ({"A": {"type": "object", "additionalProperties": _ref("A")}},
                        {"A": {"type": "object", "additionalProperties": _ref("B")},
                         "B": {"type": "object", "additionalProperties": {"type": "array", "items": _ref("A")}}}):
            with self.assertRaises(OpenAPILoadError) as cm:
                _parse(schemas)
            self.assertEqual(cm.exception.code, "map-alias-cycle")

    def test_an_object_on_the_way_breaks_the_cycle(self):
        doc = _parse({"A": {"type": "object", "additionalProperties": _ref("O")},
                      "O": {"type": "object", "properties": {"m": _ref("A")}}})
        self.assertEqual({s.name: s.is_map_alias for s in doc.schemas}, {"A": True, "O": False})

    def test_a_document_without_an_alias_parses_to_the_same_ir(self):
        schemas = {"Obj": SCHEMAS["Obj"], "Color": SCHEMAS["Color"],
                   "K": {"type": "object", "properties": {"m": {"type": "object", "additionalProperties": _ref("Obj")},
                                                          "o": _ref("Obj")}}}
        k = {s.name: s for s in _parse(schemas).schemas}["K"]
        self.assertTrue(all(f.type.alias_map is None and (f.type.element is None or f.type.element.alias_map is None)
                            for f in k.fields))


class EmitTests(unittest.TestCase):
    def setUp(self):
        self.doc = _parse(SCHEMAS)
        self.by = {s.name: s for s in self.doc.schemas}

    def _ios(self, name, fmt=False):
        g = IosApiModelGenerator(IosApiPlatformConfig(sources_root=Path("/x"), format_mapping=fmt))
        return g.generate_dto_source(self.by[name], self.doc)

    def _kt(self, name, serializer):
        g = AndroidApiModelGenerator(AndroidApiPlatformConfig(sources_root=Path("/x"), serializer=serializer))
        return g.generate_dto_source(self.by[name], self.doc)

    def test_ios_is_a_typealias(self):
        src = self._ios("LocalizedText")
        self.assertIn("/// language code -> text", src)
        self.assertIn("typealias LocalizedTextDto = [String: String]", src)
        self.assertNotIn("struct", src)
        self.assertIn("typealias InlineMapDto = [String: InlineMapValueDto]", self._ios("InlineMap"))
        self.assertIn("typealias NestedDto = [String: LocalizedTextDto]", self._ios("Nested"))
        self.assertIn("typealias ColorMapDto = [String: Color]", self._ios("ColorMap"))

    def test_ios_does_not_hash_an_alias_as_a_struct(self):
        src = self._ios("Kind")
        self.assertIn("let name: LocalizedTextDto", src)
        self.assertIn("// Omitted from hash (synthesis-incompatible types): name, opt", src)

    def test_kotlin_is_a_typealias_with_every_serializer(self):
        for serializer in ("kotlinx", "moshi", "none"):
            src = self._kt("LocalizedText", serializer)
            self.assertIn("typealias LocalizedTextDto = Map<String, String>", src, serializer)
            self.assertNotIn("data class", src, serializer)

    def test_web_is_a_record(self):
        g = WebApiModelGenerator(WebApiPlatformConfig(sources_root=Path("/x")))
        self.assertIn("export type LocalizedTextDto = Record<string, string>;",
                      g.generate_dto_source(self.by["LocalizedText"], self.doc))

    def test_a_kotlinx_wrapper_of_an_alias_looks_its_serializer_up(self):
        src = self._kt("TopArr", "kotlinx")
        self.assertIn("ListSerializer(kotlinx.serialization.serializer<LocalizedTextDto>())", src)

    def test_the_kotlinx_domain_of_an_alias_looks_its_serializer_up_and_others_keep_theirs(self):
        g = AndroidApiModelGenerator(AndroidApiPlatformConfig(sources_root=Path("/x"), serializer="kotlinx"))
        self.assertIn("private val dtoSerializer = kotlinx.serialization.serializer<LocalizedTextDto>()",
                      g.generate_domain_source(self.by["LocalizedText"]))
        self.assertIn("private val dtoSerializer = KindDto.serializer()", g.generate_domain_source(self.by["Kind"]))

    def test_an_existing_domain_is_patched_by_its_kind(self):
        g = AndroidApiModelGenerator(AndroidApiPlatformConfig(sources_root=Path("/x"), serializer="kotlinx"))
        with tempfile.TemporaryDirectory() as tmp:
            # a non-alias Domain written by an earlier build stays byte for byte
            kind = Path(tmp) / "Kind.kt"
            kind.write_text(g.generate_domain_source(self.by["Kind"]), encoding="utf-8")
            before = kind.read_bytes()
            self.assertFalse(_patch_kotlinx_domain(kind, "Kind", map_alias=False))
            self.assertEqual(kind.read_bytes(), before)
            # an alias's Domain written before the fix (Dto.serializer()) is rewritten in its block only
            alias = Path(tmp) / "LocalizedText.kt"
            old = g.generate_domain_source(self.by["LocalizedText"]).replace(
                "kotlinx.serialization.serializer<LocalizedTextDto>()", "LocalizedTextDto.serializer()")
            alias.write_text(old, encoding="utf-8")
            self.assertTrue(_patch_kotlinx_domain(alias, "LocalizedText", map_alias=True))
            self.assertEqual(alias.read_text(encoding="utf-8"), g.generate_domain_source(self.by["LocalizedText"]))


DATE_SCHEMAS = {
    "Stamps": {"type": "object", "additionalProperties": {"type": "string", "format": "date-time"}},
    "Ev": {"type": "object", "required": ["at", "inplace"], "properties": {
        "at": _ref("Stamps"),
        "maybe": _ref("Stamps"),
        "inplace": {"type": "object", "additionalProperties": {"type": "string", "format": "date-time"}}}},
}


class FormatMappingTests(unittest.TestCase):
    def test_ios_converts_an_aliased_date_map_as_it_does_one_in_place(self):
        doc = _parse(DATE_SCHEMAS)
        g = IosApiModelGenerator(IosApiPlatformConfig(sources_root=Path("/x"), format_mapping=True))
        by = {s.name: s for s in doc.schemas}
        self.assertIn("typealias StampsDto = [String: Date]", g.generate_dto_source(by["Stamps"], doc))
        ev = g.generate_dto_source(by["Ev"], doc)
        self.assertIn("self.at = try (try container.decode([String: String].self, forKey: .at)).mapValues "
                      "{ try _juiParseIsoDate($0, codingPath: decoder.codingPath) }", ev)
        self.assertIn("try container.encode(self.at.mapValues { _juiFormatIsoDate($0) }, forKey: .at)", ev)
        self.assertIn("decodeIfPresent([String: String].self, forKey: .maybe)", ev)


@unittest.skipUnless(shutil.which("swiftc"), "swiftc not installed")
class SwiftCompilesTests(unittest.TestCase):
    """The aliases compile, decode every path, and write back what they read."""

    def test_compiles_and_round_trips(self):
        doc = _parse(SCHEMAS)
        dates = _parse(DATE_SCHEMAS)
        g = IosApiModelGenerator(IosApiPlatformConfig(sources_root=Path("/x")))
        gd = IosApiModelGenerator(IosApiPlatformConfig(sources_root=Path("/x"), format_mapping=True))
        main = '''
import Foundation
let data = #"%s"#.data(using: .utf8)!
let k = try JSONDecoder().decode(KindDto.self, from: data)
precondition(k.name["ja"] == "酒" && k.objs?["o1"]?.a == "x" && k.colors?["c1"] == .red)
precondition(k.nested?["o"]?["ja"] == "z" && k.wrapped?["w"] == "1" && k.lists?["l"] == ["a", "b"])
precondition(k.arr?[0]["a"] == "b" && k.mapOfAlias?["k"]?["ja"] == "y" && k.anyNull?["q"] == "r")
let a = try JSONSerialization.jsonObject(with: data) as! NSDictionary
let b = try JSONSerialization.jsonObject(with: try JSONEncoder().encode(k)) as! NSDictionary
precondition(a.isEqual(to: b as! [AnyHashable: Any]), "\\(b)")
let set: Set<KindDto> = [k]
let top = try JSONDecoder().decode(TopArrDto.self, from: #"[{"ja":"a"}]"#.data(using: .utf8)!)
precondition(set.count == 1 && top.items[0]["ja"] == "a")
let e = try JSONDecoder().decode(EvDto.self, from: #"{"at":{"x":"2026-11-11T00:00:00Z"},"inplace":{}}"#.data(using: .utf8)!)
precondition(e.at["x"] == Date(timeIntervalSince1970: 1_794_355_200))
print("MAP_ALIAS_OK")
''' % KIND_JSON
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            paths = []
            for gen, docu in ((g, doc), (gd, dates)):
                for s in docu.schemas:
                    p = d / f"{s.name}Dto.swift"
                    p.write_text(gen.generate_dto_source(s, docu), encoding="utf-8")
                    paths.append(str(p))
                for e in docu.enums:
                    p = d / f"{e.name}.swift"
                    p.write_text(gen.generate_enum_source(e, docu), encoding="utf-8")
                    paths.append(str(p))
            (d / "main.swift").write_text(main, encoding="utf-8")
            build = subprocess.run(["swiftc", "-o", str(d / "h"), *paths, str(d / "main.swift")],
                                   capture_output=True, text=True, timeout=600)
            self.assertEqual(build.returncode, 0, build.stderr)
            self.assertNotIn("warning:", build.stderr)
            run = subprocess.run([str(d / "h")], capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("MAP_ALIAS_OK", run.stdout)


from tests.test_android_api_model_generator import GeneratedKotlinCompilesTests  # noqa: E402

KOTLINX_MAIN = r'''
import kotlinx.serialization.json.Json
import com.example.app.model.generated.*
import com.example.app.model.*
fun main() {
    val json = Json { ignoreUnknownKeys = true }
    val text = """__KIND__"""
    val k = json.decodeFromString(KindDto.serializer(), text)
    check(k.name["ja"] == "酒" && k.objs?.get("o1")?.a == "x" && k.nested?.get("o")?.get("ja") == "z")
    check(k.wrapped?.get("w") == "1" && k.lists?.get("l") == listOf("a", "b") && k.arr?.get(0)?.get("a") == "b")
    check(json.parseToJsonElement(json.encodeToString(KindDto.serializer(), k)) == json.parseToJsonElement(text))
    val top = json.decodeFromString(TopArrDto.serializer(), """[{"ja":"a"}]""")
    check(top.items[0]["ja"] == "a")
    val dom = json.decodeFromString(LocalizedTextSerializer, """{"ja":"d"}""")
    check(dom.dto["ja"] == "d" && json.encodeToString(LocalizedTextSerializer, dom) == """{"ja":"d"}""")
    println("KOTLINX_MAP_ALIAS_OK")
}
'''


class KotlinCompilesTests(GeneratedKotlinCompilesTests):
    """kotlinx (compiled and run, through the Domain serializer too) and moshi."""

    def _emit_all(self, out: Path, serializer: str) -> list[str]:
        doc = _parse(SCHEMAS)
        g = AndroidApiModelGenerator(AndroidApiPlatformConfig(sources_root=out, serializer=serializer))
        out.mkdir(parents=True, exist_ok=True)
        paths = []
        for s in doc.schemas:
            if serializer != "kotlinx" and s.is_wrapper and not s.is_map_alias:
                continue  # an array wrapper needs kotlinx by design
            for name, src in ((f"{s.name}Dto.kt", g.generate_dto_source(s, doc)),
                              (f"{s.name}.kt", g.generate_domain_source(s))):
                (out / name).write_text(src, encoding="utf-8")
                paths.append(str(out / name))
        for e in doc.enums:
            (out / f"{e.name}.kt").write_text(g.generate_enum_source(e, doc), encoding="utf-8")
            paths.append(str(out / f"{e.name}.kt"))
        return paths

    def test_kotlinx_compiles_and_reads_every_path(self):
        target = [self.jars[n] for n in self.SERIALIZATION]
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            paths = self._emit_all(t / "src", "kotlinx")
            (t / "Main.kt").write_text(KOTLINX_MAIN.replace("__KIND__", KIND_JSON), encoding="utf-8")
            self._compile(t, paths + [str(t / "Main.kt")], target, plugin=True)
            run = subprocess.run([self.java, "-cp", ":".join([str(t / "classes"), self.stdlib, *target]),
                                  "MainKt"], capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("KOTLINX_MAP_ALIAS_OK", run.stdout)

    def test_moshi_compiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            self._compile(t, self._emit_all(t / "src", "moshi"), [self.jars[self.MOSHI]], plugin=False)


for _inherited in [n for n in dir(GeneratedKotlinCompilesTests) if n.startswith("test_")]:
    setattr(KotlinCompilesTests, _inherited, None)
del GeneratedKotlinCompilesTests


if __name__ == "__main__":
    unittest.main()
