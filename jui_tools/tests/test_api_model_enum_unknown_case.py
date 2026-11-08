"""api.enum_unknown_case: a generated enum takes a value it does not know (ticket
jui-api-model-enum-unknown-value-fails-whole-decode).

A swagger enum is a closed set in the generated DTOs, and a value the server adds later failed the whole response's
decode in an app already out, wherever the enum sat (measured on 2.5.14: required, optional, nullable, inline, integer,
an array's element, a map's value, a nested object's field — iOS Codable on all of them, Android kotlinx on all of them
with its default Json, and on all but the optional ones with coerceInputValues). Web reads its enums as types only, and
is the same either way.

On (the default): Swift gets ``case unknown(<raw>)``, holding the value as it came and writing it back as it came;
Kotlin (kotlinx and moshi) gets ``UNKNOWN`` and a serializer beside the enum. Writing UNKNOWN throws and names the
enum, so a value the app does not know is never sent as another; its ``wire`` is ``""`` (an integer enum's
``Int.MIN_VALUE``), which no entry has, so ``entries.firstOrNull { it.wire == s }`` (as the apps find an entry) stays
null for a string no entry has. Off
(``"api": {"enum_unknown_case": false}``): the generators write what 2.5.14 wrote, to the byte (the golden).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from jui_cli.core.openapi_loader import parse_swagger
from jui_cli.generators.android_api_model_generator import AndroidApiModelGenerator, AndroidApiPlatformConfig
from jui_cli.generators.ios_api_model_generator import IosApiModelGenerator, IosApiPlatformConfig
from tests import api_enum_off_fixture as fixture

GOLDEN = Path(__file__).parent / "golden" / "api_enum_unknown_case_off"


class OffIsTheOldOutputTests(unittest.TestCase):
    def test_off_writes_what_2_5_14_wrote(self):
        compared = 0
        for face in fixture.FACES:
            got = fixture.sources(face, off=True)
            want = {p.name: p.read_text(encoding="utf-8") for p in (GOLDEN / face).iterdir()}
            self.assertEqual(sorted(got), sorted(want), face)
            for name in want:
                self.assertEqual(got[name], want[name], f"{face}/{name}")
                compared += 1
        self.assertEqual(compared, 40)

    def test_on_changes_the_enums_only(self):
        """The DTOs are the same text on or off (an enum's type name is all they hold), and web and Android's
        ``none`` (no serializer: nothing is decoded) are the same files."""
        for face in fixture.FACES:
            on, off = fixture.sources(face, off=False), fixture.sources(face, off=True)
            for name in off:
                same = name.endswith(("Dto.swift", "Dto.kt", "Dto.ts")) or face in ("web", "android-none")
                (self.assertEqual if same else self.assertNotEqual)(on[name], off[name], f"{face}/{name}")


class BuildPathTests(unittest.TestCase):
    """The key read where jui build reads it (ticket 2026-11-08-enum-unknown-case-false-ignored-on-android: 2.5.15 gave
    it to the iOS generator only, and Android kept UNKNOWN and its adapters with the key false). A project with the key
    is planned through api_model_sync, as jui build plans it, and each face's enums and DTOs are the golden's, to the
    byte; with the key left out, Android's enums are open."""

    def _plan(self, api: dict, face: str) -> dict[str, str]:
        from jui_cli.core.api_model_sync import collect_docs, plan_for
        from jui_cli.core.config_manager import ConfigManager

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        platform = face.split("-", 1)[0]
        android = {"model_package": "model", "dto_subpackage": "generated"}
        if face.startswith("android-"):
            android["serializer"] = face.split("-", 1)[1]
        (root / "jui.config.json").write_text(json.dumps({
            "api_directory": "docs/api",
            "api": {**api, "platforms": {"android": android, "web": {"model_dir": "models", "dto_subdir": "generated"}}},
            "platforms": {"ios": {"root": "ios"}, "android": {"root": "android"}, "web": {"root": "web"}},
        }), encoding="utf-8")
        (root / "ios").mkdir()
        (root / "ios" / "sjui.config.json").write_text(json.dumps({"source_directory": ""}), encoding="utf-8")
        (root / "android" / "app" / "src" / "main" / "kotlin").mkdir(parents=True)
        (root / "android" / "kjui.config.json").write_text(
            json.dumps({"package_name": "com.example", "source_directory": "app/src/main"}), encoding="utf-8")
        (root / "web").mkdir()
        (root / "docs" / "api").mkdir(parents=True)
        (root / "docs" / "api" / "spec.json").write_text(json.dumps(fixture.SPEC), encoding="utf-8")
        cfg = ConfigManager(root / "jui.config.json")
        plan = plan_for(platform, cfg, {"root": platform}, collect_docs(cfg))
        return {p.name: src for p, src in plan.expected_files.items()}

    def test_the_key_false_writes_the_golden_on_every_face(self):
        compared = 0
        for face in fixture.FACES:
            got = self._plan({"enum_unknown_case": False}, face)
            for golden in sorted((GOLDEN / face).iterdir()):
                with self.subTest(file=f"{face}/{golden.name}"):
                    self.assertIn(golden.name, got, f"{face}: {sorted(got)}")
                    self.assertEqual(got[golden.name], golden.read_text(encoding="utf-8"), f"{face}/{golden.name}")
                    compared += 1
        self.assertEqual(compared, 40)

    def test_the_key_left_out_opens_the_enums(self):
        for face in ("ios", "android-kotlinx", "android-moshi"):
            got = self._plan({}, face)
            name = "DeviceKind.swift" if face == "ios" else "DeviceKind.kt"
            self.assertIn("unknown(String)" if face == "ios" else "UNKNOWN(\"\")", got[name], face)


class DefaultTests(unittest.TestCase):
    def test_the_generators_default_on(self):
        self.assertTrue(IosApiPlatformConfig(sources_root=Path("/x")).enum_unknown_case)
        self.assertTrue(AndroidApiPlatformConfig(sources_root=Path("/x")).enum_unknown_case)

    def test_the_config_key(self):
        from jui_cli.core.config_manager import ConfigManager

        for api, want in ((None, True), ({}, True), ({"enum_unknown_case": True}, True),
                          ({"enum_unknown_case": False}, False)):
            with tempfile.TemporaryDirectory() as tmp:
                cfg = {"project_name": "p"} | ({"api": api} if api is not None else {})
                (Path(tmp) / "jui.config.json").write_text(json.dumps(cfg), encoding="utf-8")
                self.assertEqual(ConfigManager(Path(tmp) / "jui.config.json").api_enum_unknown_case(), want, api)


def _enum_source(face: str, name: str) -> str:
    return fixture.sources(face, off=False)[name]


class TextTests(unittest.TestCase):
    def test_swift(self):
        src = _enum_source("ios", "LoginMethod.swift")
        self.assertIn("nonisolated enum LoginMethod: RawRepresentable, Codable, CaseIterable, Sendable, Equatable, Hashable {", src)
        self.assertIn("    case unknown(String)", src)
        self.assertIn("    static let allCases: [LoginMethod] = [.emailLink, .appleId, .google]", src)
        self.assertIn('        case "apple-id": self = .appleId', src)
        self.assertIn("        case .unknown(let value): return value", src)
        self.assertIn("        self = LoginMethod(rawValue: value) ?? .unknown(value)", src)
        level = _enum_source("ios", "Level.swift")
        self.assertIn("    case unknown(Int)", level)
        self.assertIn("        case -1: self = .valueMinus1", level)
        self.assertIn("@available(*, deprecated)\nnonisolated enum Legacy", _enum_source("ios", "Legacy.swift"))

    def test_kotlin(self):
        for ser, writer in (("kotlinx", "object LoginMethodSerializer : KSerializer<LoginMethod>"),
                            ("moshi", "class LoginMethodJsonAdapter : JsonAdapter<LoginMethod>()")):
            src = _enum_source(f"android-{ser}", "LoginMethod.kt")
            self.assertIn("enum class LoginMethod(val wire: String) {", src)
            self.assertIn('    APPLE_ID("apple-id"),', src)
            self.assertIn('    UNKNOWN("");', src)
            self.assertIn("        fun fromWire(wire: String): LoginMethod = entries.firstOrNull { it != UNKNOWN && it.wire == wire } ?: UNKNOWN", src)
            self.assertIn(writer, src)
        self.assertIn("@Serializable(with = LoginMethodSerializer::class)", _enum_source("android-kotlinx", "LoginMethod.kt"))
        self.assertIn('@JsonClass(generateAdapter = true, generator = "jui")', _enum_source("android-moshi", "LoginMethod.kt"))
        level = _enum_source("android-kotlinx", "Level.kt")
        self.assertIn("enum class Level(val wire: Int) {", level)
        self.assertIn("    UNKNOWN(Int.MIN_VALUE);", level)

    def test_a_value_named_unknown_stops_the_build_by_name(self):
        doc = parse_swagger({"openapi": "3.0.3", "info": {"title": "T", "version": "1"}, "components": {"schemas": {
            "State": {"type": "string", "enum": ["ok", "unknown"]}}}}, "spec.json")
        ios = IosApiModelGenerator(IosApiPlatformConfig(sources_root=Path("/x")))
        android = AndroidApiModelGenerator(AndroidApiPlatformConfig(sources_root=Path("/x"), serializer="kotlinx"))
        for gen in (ios, android):
            with self.assertRaisesRegex(ValueError, r"enum State has a value named .*x-enum-varnames.*enum_unknown_case"):
                gen.generate_enum_source(doc.enums[0], doc)
        off = IosApiModelGenerator(IosApiPlatformConfig(sources_root=Path("/x"), enum_unknown_case=False))
        self.assertIn("case unknown", off.generate_enum_source(doc.enums[0], doc))   # off: as before


# Every place an enum sits, the second row's value in it unknown (the measured family): the response is read whole.
_GOOD = {"id": "a", "kind": "phone", "optKind": "tablet", "nullKind": None, "defaulted": "Google", "inline": "email",
         "level": 0, "severity": 5, "kinds": ["phone", "desktop"], "byName": {"main": "phone"}, "inner": {"kind": "tablet"}}
PLACES = [("required", ("kind",), "watch"), ("optional", ("optKind",), "watch"), ("nullable", ("nullKind",), "watch"),
          ("defaulted", ("defaulted",), "line"), ("inline", ("inline",), "line"), ("integer", ("level",), 9),
          ("varnames integer", ("severity",), 9), ("array element", ("kinds", 1), "watch"),
          ("map value", ("byName", "main"), "watch"), ("nested", ("inner", "kind"), "watch")]


def _bodies() -> list[tuple[str, str]]:
    import copy
    out = [("known", json.dumps({"items": [_GOOD, _GOOD]}))]
    for name, path, value in PLACES:
        row = copy.deepcopy(_GOOD)
        t = row
        for k in path[:-1]:
            t = t[k]
        t[path[-1]] = value
        out.append((name, json.dumps({"items": [_GOOD, row]})))
    return out


_LIST_SCHEMA = {"type": "object", "required": ["items"], "properties": {"items": {"type": "array", "items": {"$ref": "#/components/schemas/Item"}}}}


def _ref(name: str) -> dict:
    return {"$ref": f"#/components/schemas/{name}"}


# Every place the generated code switches on an enum: a oneOf dispatched on an enum discriminator whose every value is
# mapped (the shape that failed to compile on 2.5.15: "switch must be exhaustive", ticket
# sjui-api-model-union-decoder-switch-misses-unknown), one mapped in part, and a schema-level union.
_UNIONS = {
    "Progress": {"type": "object", "required": ["pct"], "properties": {"pct": {"type": "integer"}}},
    "Done": {"type": "object", "required": ["score"], "properties": {"score": {"type": "integer"}}},
    "Oops": {"type": "object", "required": ["message"], "properties": {"message": {"type": "string"}}},
    "Event": {"type": "object", "required": ["type", "content"], "properties": {
        "type": {"type": "string", "enum": ["progress", "result", "error"]},
        "content": {"oneOf": [_ref("Progress"), _ref("Done"), _ref("Oops")], "discriminator": {"propertyName": "type", "mapping": {
            "progress": "#/components/schemas/Progress", "result": "#/components/schemas/Done", "error": "#/components/schemas/Oops"}}}}},
    "PartKind": {"type": "string", "enum": ["a", "b", "c"]},
    "PartEvent": {"type": "object", "required": ["type", "content"], "properties": {
        "type": _ref("PartKind"),
        "content": {"oneOf": [_ref("Progress"), _ref("Done")], "discriminator": {"propertyName": "type", "mapping": {
            "a": "#/components/schemas/Progress", "b": "#/components/schemas/Done"}}}}},
    "Circle": {"type": "object", "required": ["kind", "r"], "properties": {"kind": {"type": "string"}, "r": {"type": "integer"}}},
    "Square": {"type": "object", "required": ["kind", "side"], "properties": {"kind": {"type": "string"}, "side": {"type": "integer"}}},
    "Shape": {"oneOf": [_ref("Circle"), _ref("Square")], "discriminator": {"propertyName": "kind", "mapping": {
        "circle": "#/components/schemas/Circle", "square": "#/components/schemas/Square"}}},
    "EventList": {"type": "object", "required": ["items", "parts", "shapes"], "properties": {
        "items": {"type": "array", "items": _ref("Event")}, "parts": {"type": "array", "items": _ref("PartEvent")},
        "shapes": {"type": "array", "items": _ref("Shape")}}},
}
EVENTS_KNOWN = json.dumps({"items": [{"type": "progress", "content": {"pct": 5}}, {"type": "error", "content": {"message": "m"}}],
                           "parts": [{"type": "a", "content": {"pct": 1}}, {"type": "b", "content": {"score": 2}}],
                           "shapes": [{"kind": "circle", "r": 1}, {"kind": "square", "side": 2}]})
# the second of each a value the app does not know (and PartEvent's "c": known, mapped to nothing)
EVENTS_UNKNOWN = json.dumps({"items": [{"type": "progress", "content": {"pct": 5}}, {"type": "warning", "content": {"text": "t"}}],
                             "parts": [{"type": "a", "content": {"pct": 1}}, {"type": "c", "content": {}}],
                             "shapes": [{"kind": "circle", "r": 1}, {"kind": "hexagon", "n": 6}]})


def _spec_with_list() -> dict:
    spec = json.loads(json.dumps(fixture.SPEC))
    spec["components"]["schemas"]["ItemList"] = _LIST_SCHEMA
    spec["components"]["schemas"].update(json.loads(json.dumps(_UNIONS)))
    return spec


SWIFT_MAIN = r'''
import Foundation
let bodies: [(String, String)] = __BODIES__
// what a DTO writes leaves its nil fields out; compared without the nulls
nonisolated func noNulls(_ v: Any) -> Any {
    if let d = v as? [String: Any] { return d.filter { !($0.value is NSNull) }.mapValues(noNulls) }
    if let a = v as? [Any] { return a.map(noNulls) }
    return v
}
nonisolated func check() throws {
    for (name, body) in bodies {
        let list = try JSONDecoder().decode(ItemListDto.self, from: body.data(using: .utf8)!)
        precondition(list.items.count == 2, name)
        let written = try JSONEncoder().encode(list)
        let again = try JSONDecoder().decode(ItemListDto.self, from: written)
        precondition(again == list, "\(name): written back the same")
        let raw = try JSONSerialization.jsonObject(with: body.data(using: .utf8)!) as! [String: Any]
        let back = try JSONSerialization.jsonObject(with: written) as! [String: Any]
        precondition(NSDictionary(dictionary: noNulls(raw) as! [String: Any]).isEqual(to: noNulls(back) as! [String: Any]),
                     "\(name): the unknown value is sent back as it came")
    }
    let one = try JSONDecoder().decode(ItemListDto.self, from: bodies[1].1.data(using: .utf8)!).items[1]
    precondition(one.kind == .unknown("watch") && one.kind.rawValue == "watch", "\(one.kind)")
    precondition(DeviceKind(rawValue: "watch") == nil && DeviceKind(rawValue: "phone") == .phone)
    precondition(DeviceKind.allCases == [.phone, .tablet, .desktop] && Level.allCases.count == 3)
    let n = try JSONDecoder().decode(ItemListDto.self, from: bodies[6].1.data(using: .utf8)!).items[1]
    precondition(n.level == .unknown(9), "\(n.level)")
    let known = try JSONDecoder().decode(EventListDto.self, from: __EVENTS_KNOWN__.data(using: .utf8)!)
    precondition(known.items[1].type == .error && known.parts[1].type == .b && known.shapes.count == 2, "\(known)")
    if case .error(let o) = known.items[1].content { precondition(o.message == "m") } else { preconditionFailure("\(known.items[1])") }
    let events = try JSONDecoder().decode(EventListDto.self, from: __EVENTS_UNKNOWN__.data(using: .utf8)!)
    precondition(events.items.count == 2 && events.items[1].type == .unknown("warning") && events.items[1].content == .unknown, "\(events.items[1])")
    precondition(events.parts[1].type == .c && events.parts[1].content == .unknown, "\(events.parts[1])")
    precondition(events.shapes[1] == .unknown, "\(events.shapes[1])")
}
try check()
print("SWIFT_OPEN_ENUM_OK")
'''


class SwiftCompilesAndReadsEveryPlaceTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("swiftc"), "swiftc not installed")
    def test_reads_every_place_and_writes_the_unknown_back(self):
        doc = parse_swagger(_spec_with_list(), "spec.json")
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            gen = IosApiModelGenerator(IosApiPlatformConfig(sources_root=d))
            paths = []
            for name, src in [*((f"{e.name}.swift", gen.generate_enum_source(e, doc)) for e in doc.enums),
                              *((f"{s.name}Dto.swift", gen.generate_dto_source(s, doc)) for s in doc.schemas)]:
                (d / name).write_text(src, encoding="utf-8")
                paths.append(str(d / name))
            for u in doc.unions:
                (d / f"{u.name}Dto.swift").write_text(gen.generate_union_source(u, doc), encoding="utf-8")
                paths.append(str(d / f"{u.name}Dto.swift"))
            main = (SWIFT_MAIN.replace("__BODIES__", _swift_bodies()).replace("__EVENTS_KNOWN__", json.dumps(EVENTS_KNOWN))
                    .replace("__EVENTS_UNKNOWN__", json.dumps(EVENTS_UNKNOWN)))
            (d / "main.swift").write_text(main, encoding="utf-8")
            # as an app builds: the main actor by default, the Swift 6 language mode, decoded off the main actor
            build = subprocess.run(["swiftc", "-swift-version", "6", "-default-isolation", "MainActor", "-o",
                                    str(d / "h"), *paths, str(d / "main.swift")], capture_output=True, text=True, timeout=300)
            self.assertEqual(build.returncode, 0, build.stderr)
            self.assertNotIn("warning:", build.stderr)
            run = subprocess.run([str(d / "h")], capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("SWIFT_OPEN_ENUM_OK", run.stdout)


class OffCompilesTests(unittest.TestCase):
    """With the key false, the same unions (an enum discriminator mapped whole, in part, by $ref, and a schema-level
    union) compile without a warning: the decoder's default stays out where the closed enum is mapped whole (Swift
    warns "default will never be executed" otherwise)."""

    @unittest.skipUnless(shutil.which("swiftc"), "swiftc not installed")
    def test_swift(self):
        doc = parse_swagger(_spec_with_list(), "spec.json")
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            gen = IosApiModelGenerator(IosApiPlatformConfig(sources_root=d, enum_unknown_case=False))
            sources = [*((f"{e.name}.swift", gen.generate_enum_source(e, doc)) for e in doc.enums),
                       *((f"{s.name}Dto.swift", gen.generate_dto_source(s, doc)) for s in doc.schemas),
                       *((f"{u.name}Dto.swift", gen.generate_union_source(u, doc)) for u in doc.unions)]
            for name, src in sources:
                (d / name).write_text(src, encoding="utf-8")
            r = subprocess.run(["swiftc", "-typecheck", "-swift-version", "6", "-default-isolation", "MainActor",
                                *(str(d / n) for n, _ in sources)], capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("warning:", r.stderr)
        self.assertNotIn("default:", dict(sources)["EventDto.swift"])   # mapped whole, closed: no default
        self.assertIn("default:", dict(sources)["PartEventDto.swift"])


def _swift_bodies() -> str:
    return "[" + ", ".join(f"({json.dumps(n)}, {json.dumps(b)})" for n, b in _bodies()) + "]"


def _kotlin_lit(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$") + '"'


def _kotlin_bodies() -> str:
    return "listOf(" + ", ".join(f"{_kotlin_lit(n)} to {_kotlin_lit(b)}" for n, b in _bodies()) + ")"


KOTLINX_MAIN = """
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import com.example.app.model.generated.*

val bodies = __BODIES__

fun main() {
    for (json in listOf(Json, Json { ignoreUnknownKeys = true; coerceInputValues = true })) {
        for ((name, body) in bodies) {
            val list = json.decodeFromString(ItemListDto.serializer(), body)
            check(list.items.size == 2) { name }
        }
    }
    val one = Json.decodeFromString(ItemListDto.serializer(), bodies[1].second)
    check(one.items[1].kind == DeviceKind.UNKNOWN) { "${one.items[1]}" }
    val sent = runCatching { Json.encodeToString(ItemListDto.serializer(), one) }.exceptionOrNull()
    check(sent is SerializationException && sent.message!!.startsWith("DeviceKind.UNKNOWN")) { "writing UNKNOWN: $sent" }
    check(one.items[1].kind.wire == "") { "UNKNOWN.wire: ${one.items[1].kind.wire}" }
    // as the apps find an entry by its string: a string no entry has stays null, UNKNOWN's wire matching nothing
    check(DeviceKind.entries.firstOrNull { it.wire == "watch" } == null && DeviceKind.entries.firstOrNull { it.wire == "tablet" } == DeviceKind.TABLET)
    val n = Json.decodeFromString(ItemListDto.serializer(), bodies[6].second)
    check(n.items[1].level == Level.UNKNOWN) { "${n.items[1].level}" }
    val known = Json.decodeFromString(ItemListDto.serializer(), bodies[0].second)
    val out = Json.encodeToString(ItemListDto.serializer(), known)
    check(Json.decodeFromString(ItemListDto.serializer(), out) == known) { "known written back: $out" }   // defaults (null) are left out
    check(DeviceKind.fromWire("tablet") == DeviceKind.TABLET && DeviceKind.fromWire("watch") == DeviceKind.UNKNOWN)
    val known2 = Json.decodeFromString(EventListDto.serializer(), __EVENTS_KNOWN__)
    check(known2.items[1].content == EventDto.Content.Error(OopsDto("m")) && known2.shapes.size == 2) { "$known2" }
    val ev = Json.decodeFromString(EventListDto.serializer(), __EVENTS_UNKNOWN__)
    check(ev.items[1].type == EventType.UNKNOWN && ev.items[1].content == EventDto.Content.Unknown) { "${ev.items[1]}" }
    check(ev.parts[1].type == PartKind.C && ev.parts[1].content == PartEventDto.Content.Unknown) { "${ev.parts[1]}" }
    check(ev.shapes[1] == ShapeDto.Unknown) { "${ev.shapes[1]}" }
    println("KOTLINX_OPEN_ENUM_OK")
}
"""

MOSHI_MAIN = """
import com.squareup.moshi.JsonDataException
import com.squareup.moshi.Moshi
import com.example.app.model.generated.*

fun main() {
    val moshi = Moshi.Builder().build()
    val kind = moshi.adapter(DeviceKind::class.java)
    check(kind.fromJson("\\"watch\\"") == DeviceKind.UNKNOWN && kind.fromJson("\\"phone\\"") == DeviceKind.PHONE) { "kind" }
    check(kind.toJson(DeviceKind.TABLET) == "\\"tablet\\"" && kind.fromJson("null") == null) { "kind out" }
    val sent = runCatching { kind.toJson(DeviceKind.UNKNOWN) }.exceptionOrNull()
    check(sent is JsonDataException && sent.message!!.startsWith("DeviceKind.UNKNOWN")) { "writing UNKNOWN: $sent" }
    val level = moshi.adapter(Level::class.java)
    check(level.fromJson("9") == Level.UNKNOWN && level.fromJson("-1") == Level.VALUE_MINUS_1 && level.toJson(Level.VALUE_2) == "2") { "level" }
    println("MOSHI_OPEN_ENUM_OK")
}
"""


class KotlinCompilesAndReadsEveryPlaceTests(unittest.TestCase):
    """kotlinx (decoded and written) and moshi (each enum's adapter), with the compile arm's pinned jars."""

    def setUp(self):
        from tests import test_android_api_model_generator as android

        self.android = android.GeneratedKotlinCompilesTests
        for key in ("PLUGIN", "SERIALIZATION", "DATETIME", "MOSHI"):   # what its setUp reads
            setattr(self, key, getattr(self.android, key))
        self.android.setUp(self)

    def _emit(self, out: Path, serializer: str, open_enums: bool = True) -> list[str]:
        doc = parse_swagger(_spec_with_list(), "spec.json")
        gen = AndroidApiModelGenerator(AndroidApiPlatformConfig(sources_root=out, serializer=serializer,
                                                                enum_unknown_case=open_enums))
        sources = {f"{e.name}.kt": gen.generate_enum_source(e, doc) for e in doc.enums}
        if serializer == "kotlinx":
            sources |= {f"{s.name}Dto.kt": gen.generate_dto_source(s, doc) for s in doc.schemas}
            sources |= {f"{u.name}Dto.kt": gen.generate_union_source(u, doc) for u in doc.unions}
        elif serializer == "none":   # no oneOf without kotlinx (the generator refuses it by design): the unions' schemas out
            sources |= {f"{s.name}Dto.kt": gen.generate_dto_source(s, doc) for s in doc.schemas if s.name not in _UNIONS}
        out.mkdir(parents=True, exist_ok=True)
        for name, src in sources.items():
            (out / name).write_text(src, encoding="utf-8")
        return [str(out / n) for n in sources]

    def _run(self, t: Path, target: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run([self.java, "-cp", ":".join([str(t / "classes"), self.stdlib, *target]), "MainKt"],
                              capture_output=True, text=True, timeout=120)

    def test_kotlinx_reads_every_place_and_refuses_to_write_unknown(self):
        target = [self.jars[n] for n in self.android.SERIALIZATION]
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            main = (KOTLINX_MAIN.replace("__BODIES__", _kotlin_bodies()).replace("__EVENTS_KNOWN__", _kotlin_lit(EVENTS_KNOWN))
                    .replace("__EVENTS_UNKNOWN__", _kotlin_lit(EVENTS_UNKNOWN)))
            (t / "Main.kt").write_text(main, encoding="utf-8")
            self.android._compile(self, t, self._emit(t / "src", "kotlinx") + [str(t / "Main.kt")], target, plugin=True)
            run = self._run(t, target)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("KOTLINX_OPEN_ENUM_OK", run.stdout)

    def test_kotlinx_off_compiles(self):
        target = [self.jars[n] for n in self.android.SERIALIZATION]
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            self.android._compile(self, t, self._emit(t / "src", "kotlinx", open_enums=False), target, plugin=True)

    def test_none_compiles(self):
        """The none serializer: the enums as before and the DTOs that hold them, against the stdlib alone."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            self.android._compile(self, t, self._emit(t / "src", "none"), [], plugin=False)

    def test_moshi_reads_an_unknown_value_and_refuses_to_write_it(self):
        from tests.test_android_api_model_generator import _pinned_jar_of

        okio = _pinned_jar_of(("com.squareup.okio", "okio-jvm"))
        if okio is None:
            self.skipTest("okio-jvm is not in the Gradle cache at the pinned version")
        target = [self.jars[self.android.MOSHI], okio]
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "Main.kt").write_text(MOSHI_MAIN, encoding="utf-8")
            self.android._compile(self, t, self._emit(t / "src", "moshi") + [str(t / "Main.kt")], target, plugin=False)
            run = self._run(t, target)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("MOSHI_OPEN_ENUM_OK", run.stdout)


if __name__ == "__main__":
    unittest.main()
