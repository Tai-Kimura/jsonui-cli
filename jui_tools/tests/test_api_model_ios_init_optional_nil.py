"""iOS DTO init: a field the server may leave out defaults to ``nil``, as on
Android (ticket jui-api-model-ios-init-optional-without-default-nil).

Android's constructor gives every optional field (not ``required``) without a
swagger ``default`` the default ``null``; a required field — nullable or
not — is a parameter every call names. Until jsonui-cli 2.5.32 the iOS
memberwise init gave such a parameter no default, and a DTO that needed no
init of its own took Swift's synthesized one, which gives a ``let`` optional
no default either: each optional field added to the swagger broke every
hand-written call on iOS while Android's still compiled.

Measured with swiftc, not read: the calls that leave the optional fields out
compile, the calls written before (every argument named) still compile, a
hand-written init that takes some of the fields keeps being the one chosen,
and a call that leaves out a required nullable field is still refused.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from jui_cli.core.openapi_loader import parse_swagger
from jui_cli.generators.android_api_model_generator import (
    AndroidApiModelGenerator,
    AndroidApiPlatformConfig,
)
from jui_cli.generators.ios_api_model_generator import (
    IosApiModelGenerator,
    IosApiPlatformConfig,
)

R = "#/components/schemas/"


def _ref(name: str) -> dict:
    return {"$ref": R + name}


# name -> (property schema, required)
KINDS = {
    "req_str": ({"type": "string"}, True),
    "opt_str": ({"type": "string"}, False),
    "req_null": ({"type": "string", "nullable": True}, True),
    "opt_null": ({"type": "string", "nullable": True}, False),
    "opt_default": ({"type": "string", "default": "x"}, False),
    "req_default": ({"type": "integer", "default": 3}, True),
    "opt_null_default_null": ({"type": "string", "nullable": True, "default": None}, False),
    "opt_enum": (_ref("Color"), False),
    "opt_enum_default": ({"allOf": [_ref("Color")], "default": "red"}, False),
    "opt_arr": ({"type": "array", "items": {"type": "string"}}, False),
    "opt_dict": ({"type": "object", "additionalProperties": {"type": "string"}}, False),
    "opt_alias": (_ref("Labels"), False),
    "opt_obj": (_ref("Obj"), False),
    "opt_date": ({"type": "string", "format": "date-time"}, False),
}
# No default and no date: the DTO that took Swift's synthesized init.
PLAIN = {k: v for k, v in KINDS.items() if "default" not in k and k != "opt_date"}
UNION = {"oneOf": [_ref("A"), _ref("B")],
         "discriminator": {"propertyName": "type", "mapping": {"a": R + "A", "b": R + "B"}}}

SCHEMAS = {
    "Color": {"type": "string", "enum": ["red", "blue"]},
    "Obj": {"type": "object", "properties": {"a": {"type": "string"}}},
    "Labels": {"type": "object", "additionalProperties": {"type": "string"}},
    "A": {"type": "object", "required": ["k"], "properties": {"k": {"type": "string"}}},
    "B": {"type": "object", "required": ["m"], "properties": {"m": {"type": "string"}}},
    "Kinds": {"type": "object", "required": [k for k, (_, r) in KINDS.items() if r],
              "properties": {k: v for k, (v, _) in KINDS.items()}},
    "Plain": {"type": "object", "required": [k for k, (_, r) in PLAIN.items() if r],
              "properties": {k: v for k, (v, _) in PLAIN.items()}},
    "WithUnion": {"type": "object", "required": ["type", "req_u"],
                  "properties": {"type": {"type": "string"}, "req_u": UNION, "opt_u": UNION,
                                 "opt_str": {"type": "string"}}},
    # Every field required: the synthesized init stays, as before.
    "AllRequired": {"type": "object", "required": ["id", "name"],
                    "properties": {"id": {"type": "string"}, "name": {"type": "string", "nullable": True}}},
}

TARGETS = ("Kinds", "Plain", "WithUnion", "AllRequired")


def _doc(schemas: dict | None = None):
    return parse_swagger({"openapi": "3.0.3", "info": {"title": "t", "version": "1"}, "paths": {},
                          "components": {"schemas": schemas or SCHEMAS}}, "/repro/swagger.json")


# An optional oneOf field does not compile on iOS whatever its init says
# (decodeIfPresent ?? <Variant>() and an encode switch with no `.none` —
# measured before and after this ticket, its own finding), so the compiled
# DTOs carry the required one only.
COMPILED = dict(SCHEMAS, WithUnion={
    "type": "object", "required": ["type", "req_u"],
    "properties": {"type": {"type": "string"}, "req_u": UNION, "opt_str": {"type": "string"}}})


def _ios(tmp: Path, **kw) -> IosApiModelGenerator:
    return IosApiModelGenerator(IosApiPlatformConfig(sources_root=tmp, **kw))


def _init_params(src: str) -> dict[str, str]:
    """``name -> "Type"`` or ``"Type = default"`` of the memberwise init."""
    m = re.search(r"(?m)^\s*(?:public )?init\((?!from)(.*)\) \{", src)
    if not m:
        return {}
    return {p.split(":", 1)[0].strip(): p.split(":", 1)[1].strip()
            for p in re.split(r", (?=\w+: )", m.group(1))}


def _kotlin_defaults(src: str) -> dict[str, bool]:
    """``name -> has a default`` of the Kotlin data class constructor."""
    return {m.group(1): " = " in m.group(2)
            for m in re.finditer(r"(?m)^    (?:@\S+ )*va[lr] (\w+): ([^\n]+?),?$", src)}


class InitParametersTests(unittest.TestCase):
    def test_an_omittable_field_defaults_to_nil_and_a_required_one_has_no_default(self):
        doc = _doc()
        by = {s.name: s for s in doc.schemas}
        with tempfile.TemporaryDirectory() as tmp:
            for kw in ({}, {"format_mapping": True}, {"access_level": "public"}):
                params = _init_params(_ios(Path(tmp), **kw).generate_dto_source(by["Kinds"], doc))
                with self.subTest(**kw):
                    for name in ("optStr", "optNull", "optEnum", "optArr", "optDict", "optAlias",
                                 "optObj", "optDate"):
                        self.assertTrue(params[name].endswith("? = nil"), (name, params[name]))
                    self.assertEqual(params["reqStr"], "String")
                    self.assertEqual(params["reqNull"], "String?")  # required, nullable: named
                    # A swagger default stays the default it was.
                    self.assertEqual(params["optDefault"], 'String? = "x"')
                    self.assertEqual(params["reqDefault"], "Int = 3")
                    self.assertEqual(params["optEnumDefault"], "Color? = Color.red")
                    self.assertEqual(params["optNullDefaultNull"], "String? = nil")

    def test_a_dto_that_took_the_synthesized_init_now_writes_one_with_the_defaults(self):
        doc = _doc()
        by = {s.name: s for s in doc.schemas}
        with tempfile.TemporaryDirectory() as tmp:
            params = _init_params(_ios(Path(tmp)).generate_dto_source(by["Plain"], doc))
        self.assertEqual(params["optStr"], "String? = nil")
        self.assertEqual(params["reqNull"], "String?")

    def test_a_oneof_field_the_server_may_leave_out_defaults_to_nil(self):
        doc = _doc()
        by = {s.name: s for s in doc.schemas}
        with tempfile.TemporaryDirectory() as tmp:
            params = _init_params(_ios(Path(tmp)).generate_dto_source(by["WithUnion"], doc))
        self.assertEqual(params["optU"], "OptU? = nil")
        self.assertEqual(params["reqU"], "ReqU")

    def test_control_a_dto_whose_fields_are_all_required_keeps_the_synthesized_init(self):
        doc = _doc()
        by = {s.name: s for s in doc.schemas}
        with tempfile.TemporaryDirectory() as tmp:
            src = _ios(Path(tmp)).generate_dto_source(by["AllRequired"], doc)
        self.assertEqual(_init_params(src), {})

    def test_the_parameters_with_a_default_are_the_ones_android_gives_a_default(self):
        doc = _doc()
        by = {s.name: s for s in doc.schemas}
        with tempfile.TemporaryDirectory() as tmp:
            ios = _ios(Path(tmp))
            android = AndroidApiModelGenerator(AndroidApiPlatformConfig(sources_root=Path(tmp), serializer="kotlinx"))
            for name in ("Kinds", "Plain", "WithUnion"):
                swift = {k: " = " in v for k, v in _init_params(ios.generate_dto_source(by[name], doc)).items()}
                kotlin = _kotlin_defaults(android.generate_dto_source(by[name], doc))
                with self.subTest(name):
                    self.assertEqual(set(swift), set(kotlin))
                    self.assertEqual(swift, kotlin)


@unittest.skipUnless(shutil.which("swiftc"), "swiftc not installed")
class SwiftCompilesTests(unittest.TestCase):
    """The calls compile, under the internal and the public spelling."""

    MAIN = '''
import Foundation
// The optional fields left out.
let k = KindsDto(reqStr: "a", reqNull: nil)
let p = PlainDto(reqStr: "a", reqNull: nil)
let u = WithUnionDto(type: "a", reqU: .a(ADto(k: "k")))  // optStr left out
precondition(k.optStr == nil && k.optDefault == "x" && k.reqDefault == 3 && k.optEnumDefault == .red)
precondition(p.optObj == nil && u.optStr == nil)
// Some of them given, out of the middle.
let k2 = KindsDto(reqStr: "a", reqNull: "n", optEnum: .blue, optDate: nil)
precondition(k2.optEnum == .blue && k2.optStr == nil)
// The calls written before: every argument named.
let full = PlainDto(reqStr: "a", optStr: "s", reqNull: nil, optNull: nil, optEnum: nil, optArr: [],
                    optDict: [:], optAlias: nil, optObj: nil)
precondition(full.optStr == "s")
// A hand-written init that takes some of the fields stays the one chosen.
extension PlainDto {
    init(reqStr: String) {
        self.init(reqStr: reqStr, optStr: "hand", reqNull: nil)
    }
}
precondition(PlainDto(reqStr: "z").optStr == "hand")
let all = AllRequiredDto(id: "i", name: nil)
precondition(all.id == "i")
print("INIT_NIL_OK")
'''

    # A required field, nullable or not, is still named by every call.
    REFUSED = '''
let k = KindsDto(reqStr: "a")
'''

    def _sources(self, d: Path, **kw) -> list[str]:
        doc = _doc(COMPILED)
        gen = _ios(d, **kw)
        paths = []
        for s in doc.schemas:
            p = d / f"{s.name}Dto.swift"
            p.write_text(gen.generate_dto_source(s, doc), encoding="utf-8")
            paths.append(str(p))
        for e in doc.enums:
            p = d / f"{e.name}.swift"
            p.write_text(gen.generate_enum_source(e, doc), encoding="utf-8")
            paths.append(str(p))
        return paths

    def test_the_calls_that_leave_the_optional_fields_out_compile_and_run(self):
        for kw in ({}, {"format_mapping": True}, {"access_level": "public"}):
            with self.subTest(**kw), tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp)
                paths = self._sources(d, **kw)
                (d / "main.swift").write_text(self.MAIN, encoding="utf-8")
                build = subprocess.run(["swiftc", "-o", str(d / "h"), *paths, str(d / "main.swift")],
                                       capture_output=True, text=True, timeout=600)
                self.assertEqual(build.returncode, 0, build.stderr)
                self.assertNotIn("warning:", build.stderr)
                run = subprocess.run([str(d / "h")], capture_output=True, text=True, timeout=60)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertIn("INIT_NIL_OK", run.stdout)

    def test_control_a_call_that_leaves_out_a_required_nullable_field_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            paths = self._sources(d)
            (d / "main.swift").write_text(self.REFUSED, encoding="utf-8")
            build = subprocess.run(["swiftc", "-typecheck", *paths, str(d / "main.swift")],
                                   capture_output=True, text=True, timeout=600)
        self.assertNotEqual(build.returncode, 0)
        self.assertIn("reqNull", build.stderr)


if __name__ == "__main__":
    unittest.main()
