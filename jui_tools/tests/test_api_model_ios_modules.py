"""api.platforms.ios.modules — iOS DTOs written into a Swift module of their own, public, so a framework the app and an
App Extension share can hold them (ticket jui-api-model-ios-dto-cannot-be-shared-with-framework-target).

The compile arms build the module's files as a library module and the app's files as a second module that imports
it, as Xcode does for an app and its framework; the internal control proves the public spelling is what lets the
app see them."""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from jui_cli.core.api_model_sync import apply_plan, collect_docs, plan_android, plan_ios, plan_web
from jui_cli.core.config_manager import ConfigManager
from jui_cli.core.openapi_loader import OpenAPILoadError

R = "#/components/schemas/"


def _ref(name: str) -> dict:
    return {"$ref": R + name}


SCHEMAS = {
    "EventPlace": {"type": "object", "required": ["x", "y"], "properties": {
        "x": {"type": "number"}, "y": {"type": "number"}}},
    "EventLevel": {"type": "string", "enum": ["basic", "expert"]},
    "EventLabels": {"type": "object", "additionalProperties": {"type": "string"}},
    "EventIds": {"type": "array", "items": {"type": "string"}},
    "EventTalk": {"type": "object", "required": ["kind", "title"], "properties": {
        "kind": {"type": "string"}, "title": {"type": "string"}}},
    "EventStand": {"type": "object", "required": ["kind", "item"], "properties": {
        "kind": {"type": "string"}, "item": {"type": "string"}}},
    "EventSlot": {"oneOf": [_ref("EventTalk"), _ref("EventStand")], "discriminator": {
        "propertyName": "kind", "mapping": {"talk": R + "EventTalk", "stand": R + "EventStand"}}},
    "EventNote": {"type": "object", "required": ["type", "content"], "properties": {
        "type": {"type": "string", "enum": ["talk", "stand"]},
        "content": {"oneOf": [_ref("EventTalk"), _ref("EventStand")], "discriminator": {"propertyName": "type", "mapping": {
            "talk": R + "EventTalk", "stand": R + "EventStand"}}}}},
    "EventBundle": {"type": "object", "required": ["id", "startsAt", "level", "state", "places"], "properties": {
        "id": {"type": "string"},
        "startsAt": {"type": "string", "format": "date-time"},
        "level": _ref("EventLevel"),
        "state": {"type": "string", "enum": ["draft", "open"]},
        "places": {"type": "array", "items": _ref("EventPlace")},
        "labels": _ref("EventLabels"),
        "slot": _ref("EventSlot"),
        "ids": _ref("EventIds"),
        "retries": {"type": "integer", "default": 3},
        "counts": {"type": "object", "additionalProperties": {"type": "integer"}},
        "note_text": {"type": "string"},
    }},
    "Profile": {"type": "object", "required": ["name"], "properties": {
        "name": {"type": "string"}, "favorite": _ref("EventBundle")}},
    "Plain": {"type": "object", "properties": {"a": {"type": "string"}}},
}
EVENT_FILES = {"EventPlaceDto.swift", "EventLevel.swift", "EventLabelsDto.swift", "EventIdsDto.swift",
               "EventTalkDto.swift", "EventStandDto.swift", "EventSlotDto.swift", "EventBundleDto.swift",
               "EventBundleState.swift", "EventNoteDto.swift", "EventNoteType.swift"}
MODULE = {"module": "EventCore", "include_schemas": ["Event*"], "model_dir": "../EventCore/Model"}


def _doc(schemas: dict) -> dict:
    return {"openapi": "3.0.3", "info": {"title": "t", "version": "1"}, "paths": {},
            "components": {"schemas": schemas}}


def _project(root: Path, ios_api: dict | None = None, schemas: dict | None = None,
             format_mapping: bool = True, enum_unknown_case: bool = True) -> ConfigManager:
    api: dict = {"format_mapping": format_mapping, "enum_unknown_case": enum_unknown_case}
    if ios_api is not None:
        api["platforms"] = {"ios": ios_api}
    (root / "jui.config.json").write_text(json.dumps({
        "api_directory": "docs/api", "platforms": {"ios": {"root": "ios"}}, "api": api}), encoding="utf-8")
    (root / "ios" / "App").mkdir(parents=True, exist_ok=True)
    (root / "ios" / "sjui.config.json").write_text(json.dumps({"source_directory": "App"}), encoding="utf-8")
    (root / "docs" / "api").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "api" / "api.json").write_text(json.dumps(_doc(schemas or SCHEMAS)), encoding="utf-8")
    return ConfigManager(root / "jui.config.json")


def _plan(cfg: ConfigManager):
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        plan = plan_ios(cfg, {"root": "ios"}, collect_docs(cfg))
    return plan, err.getvalue()


def _by_dir(plan, root: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for path, src in plan.expected_files.items():
        out.setdefault(str(path.parent.relative_to(root)), {})[path.name] = src
    return out


class PlacementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_without_the_key_nothing_moves_and_nothing_is_public(self):
        plan, err = _plan(_project(self.root))
        dirs = _by_dir(plan, self.root)
        self.assertEqual(list(dirs), ["ios/App/Model/Generated"])
        for src in plan.expected_files.values():
            self.assertNotIn("public ", src)
            self.assertEqual([ln for ln in src.splitlines() if ln.startswith("import ")], ["import Foundation"])
        self.assertEqual(err, "")

    def test_an_empty_list_is_the_same_as_no_key(self):
        a, _ = _plan(_project(self.root))
        other = Path(self.tmp.name) / "b"
        other.mkdir()
        b, _ = _plan(_project(other, {"modules": []}))
        self.assertEqual({p.name: s for p, s in a.expected_files.items()},
                         {p.name: s for p, s in b.expected_files.items()})

    def test_picked_schemas_and_their_inline_types_go_to_the_module_public(self):
        plan, _ = _plan(_project(self.root, {"modules": [MODULE]}))
        dirs = _by_dir(plan, self.root)
        self.assertEqual(set(dirs["ios/EventCore/Model/Generated"]), EVENT_FILES)
        self.assertEqual(set(dirs["ios/App/Model/Generated"]), {"ProfileDto.swift", "PlainDto.swift"})
        for name, src in dirs["ios/EventCore/Model/Generated"].items():
            self.assertRegex(src, r"(?m)^public (nonisolated )?(struct|enum|typealias) ", name)
        bundle = dirs["ios/EventCore/Model/Generated"]["EventBundleDto.swift"]
        for member in ("    public let id: String", "    public init(id: String", "    public init(from decoder",
                       "    public func encode(to encoder", "    public func hash(into hasher"):
            self.assertIn(member, bundle)
        self.assertIn("    enum CodingKeys: String, CodingKey {", bundle)   # no API names it: stays internal
        self.assertIn("fileprivate func _juiParseIsoDate", bundle)
        self.assertIn("public typealias EventLabelsDto = [String: String]",
                      dirs["ios/EventCore/Model/Generated"]["EventLabelsDto.swift"])

    def test_an_app_type_naming_a_module_type_imports_the_module(self):
        plan, _ = _plan(_project(self.root, {"modules": [MODULE]}))
        app = _by_dir(plan, self.root)["ios/App/Model/Generated"]
        self.assertIn("import Foundation\nimport EventCore\n", app["ProfileDto.swift"])
        self.assertNotIn("import EventCore", app["PlainDto.swift"])
        self.assertNotIn("public", app["ProfileDto.swift"])

    def test_domain_scaffolds_stay_in_the_app_and_a_new_one_imports_the_module(self):
        plan, _ = _plan(_project(self.root, {"modules": [MODULE]}))
        scaffolds = {str(p.relative_to(self.root)): s for p, s in plan.domain_scaffolds.items()}
        self.assertIn("ios/App/Model/EventBundle.swift", scaffolds)
        self.assertTrue(scaffolds["ios/App/Model/EventBundle.swift"].startswith("import Foundation\nimport EventCore\n"))
        self.assertEqual(scaffolds["ios/App/Model/Profile.swift"].count("import "), 1)
        self.assertFalse(any(k.startswith("ios/EventCore") for k in scaffolds))

    def test_internal_access_moves_the_files_without_public(self):
        plan, _ = _plan(_project(self.root, {"modules": [dict(MODULE, access_level="internal")]}))
        mod = _by_dir(plan, self.root)["ios/EventCore/Model/Generated"]
        self.assertTrue(all("public " not in s for s in mod.values()))

    def test_no_other_platform_reads_the_key(self):
        cfg = _project(self.root, {"modules": [MODULE]})
        raw = json.loads((self.root / "jui.config.json").read_text())
        raw["platforms"].update({"android": {"root": "android"}, "web": {"root": "web"}})
        raw["api"]["platforms"]["android"] = {"serializer": "kotlinx"}
        (self.root / "jui.config.json").write_text(json.dumps(raw))
        cfg = ConfigManager(self.root / "jui.config.json")
        docs = collect_docs(cfg)
        for planner, root in ((plan_android, "android"), (plan_web, "web")):
            with_key = {p.name: s for p, s in planner(cfg, {"root": root}, docs).expected_files.items()}
            self.assertIn("EventBundleDto." + ("kt" if root == "android" else "ts"), with_key)


class HaltAndWarnTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _halt(self, ios_api, schemas=None) -> OpenAPILoadError:
        with self.assertRaises(OpenAPILoadError) as cm:
            _plan(_project(self.root, ios_api, schemas))
        return cm.exception

    def test_a_ref_leaving_the_module_halts_naming_it_and_the_fix(self):
        e = self._halt({"modules": [dict(MODULE, include_schemas=[
            "EventBundle", "EventLevel", "EventLabels", "EventIds", "EventSlot", "EventTalk", "EventStand"])]})
        self.assertEqual(e.code, "module-ref-outside")
        self.assertIn("'EventBundle'", str(e))
        self.assertIn("'EventPlace'", str(e))
        self.assertIn("include_schemas", str(e))

    def test_two_modules_taking_one_schema_halt(self):
        e = self._halt({"modules": [MODULE, {"module": "Other", "include_schemas": ["EventPlace"],
                                             "model_dir": "../Other"}]})
        self.assertEqual(e.code, "module-name-collision")
        self.assertIn("'EventPlace'", str(e))

    def test_an_inline_type_reached_from_two_modules_halts(self):
        shared_inline = {"type": "string", "enum": ["a", "b"], "x-jui-name": "SharedState"}
        schemas = {"A": {"type": "object", "properties": {"s": shared_inline}},
                   "B": {"type": "object", "properties": {"s": shared_inline}}}
        e = self._halt({"modules": [{"module": "MA", "include_schemas": ["A"], "model_dir": "../MA"},
                                    {"module": "MB", "include_schemas": ["B"], "model_dir": "../MB"}]}, schemas)
        self.assertEqual(e.code, "module-name-collision")
        self.assertIn("'SharedState'", str(e))

    def test_a_module_sharing_the_apps_directory_halts(self):
        e = self._halt({"modules": [dict(MODULE, model_dir="Model")]})
        self.assertEqual(e.code, "module-dir-overlap")

    def test_two_modules_sharing_a_directory_halt(self):
        e = self._halt({"modules": [dict(MODULE, include_schemas=["Profile"], module="A", model_dir="../X"),
                                    {"module": "B", "include_schemas": ["Plain"], "model_dir": "../X"}]})
        self.assertEqual(e.code, "module-dir-overlap")

    def test_a_module_inside_the_apps_sources_warns_once(self):
        _, err = _plan(_project(self.root, {"modules": [dict(MODULE, model_dir="EventCore")]}))
        self.assertEqual(err.count("WARNING [api-model]"), 1)
        self.assertIn("inside the app's source directory", err)

    def test_a_module_outside_the_apps_sources_is_silent(self):
        _, err = _plan(_project(self.root, {"modules": [MODULE]}))
        self.assertEqual(err, "")

    def test_patterns_matching_nothing_warn_and_write_nothing_there(self):
        plan, err = _plan(_project(self.root, {"modules": [dict(MODULE, include_schemas=["event*"])]}))
        self.assertEqual(err.count("WARNING [api-model]"), 1)
        self.assertIn("matches no generated schema", err)
        self.assertEqual(list(_by_dir(plan, self.root)), ["ios/App/Model/Generated"])

    def test_a_bad_entry_halts_naming_the_key(self):
        for bad in ({"modules": {}}, {"modules": [{"module": "1x", "include_schemas": ["E"], "model_dir": "d"}]},
                    {"modules": [{"module": "M", "include_schemas": [], "model_dir": "d"}]},
                    {"modules": [{"module": "M", "include_schemas": ["E"]}]},
                    {"modules": [dict(MODULE, access_level="open")]},
                    {"modules": [dict(MODULE, path="x")]}):
            with self.subTest(bad=bad):
                self.assertEqual(self._halt(bad).code, "ios-modules-config")

    def test_existing_scaffolds_without_the_import_warn_in_one_line(self):
        model = self.root / "ios" / "App" / "Model"
        model.mkdir(parents=True, exist_ok=True)
        (model / "EventBundle.swift").write_text("import Foundation\nstruct EventBundle { let dto: EventBundleDto }\n")
        (model / "EventPlace.swift").write_text("import Foundation\nimport EventCore\nstruct EventPlace {}\n")
        (model / "Profile.swift").write_text("import Foundation\nstruct Profile {}\n")
        _, err = _plan(_project(self.root, {"modules": [MODULE]}))
        lines = [ln for ln in err.splitlines() if "WARNING" in ln]
        self.assertEqual(len(lines), 1)
        self.assertIn("1 Domain scaffold(s)", lines[0])
        self.assertIn("EventBundle", lines[0])
        self.assertNotIn("EventPlace", lines[0])


class PruneTests(unittest.TestCase):
    def test_each_place_prunes_only_its_own_directory(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            app_dir = root / "ios" / "App" / "Model" / "Generated"
            mod_dir = root / "ios" / "EventCore" / "Model" / "Generated"
            cfg = _project(root)
            apply_plan(_plan(cfg)[0], prune_orphans=True)
            self.assertTrue((app_dir / "EventBundleDto.swift").exists())
            mod_dir.mkdir(parents=True)
            (mod_dir / "Stale.swift").write_text("// not written by this plan\n")
            (mod_dir.parent / "Hand.swift").write_text("// the module's own code\n")
            (app_dir.parent / "Mine.swift").write_text("// the app's own code\n")
            raw = json.loads((root / "jui.config.json").read_text())
            raw["api"]["platforms"] = {"ios": {"modules": [MODULE]}}
            (root / "jui.config.json").write_text(json.dumps(raw))
            apply_plan(_plan(ConfigManager(root / "jui.config.json"))[0], prune_orphans=True)
            self.assertEqual({p.name for p in mod_dir.iterdir()}, EVENT_FILES)       # its stray pruned
            self.assertEqual({p.name for p in app_dir.iterdir()}, {"ProfileDto.swift", "PlainDto.swift"})
            self.assertTrue((mod_dir.parent / "Hand.swift").exists())
            self.assertTrue((app_dir.parent / "Mine.swift").exists())
            # And back: dropping the key moves them home and leaves the module's directory alone.
            raw["api"].pop("platforms")
            (root / "jui.config.json").write_text(json.dumps(raw))
            apply_plan(_plan(ConfigManager(root / "jui.config.json"))[0], prune_orphans=True)
            self.assertIn("EventBundleDto.swift", {p.name for p in app_dir.iterdir()})
            self.assertEqual({p.name for p in mod_dir.iterdir()}, EVENT_FILES)


_FRAMEWORK_API = """\
import Foundation

/// What the extension calls: the bundle it reads from the App Group.
public func loadEventBundle(_ data: Data) throws -> EventBundleDto {
    try JSONDecoder().decode(EventBundleDto.self, from: data)
}
"""

_APP_MAIN = """\
import Foundation
import EventCore

let json = #"{"id":"e1","startsAt":"2026-11-12T09:00:00Z","level":"expert","state":"open","places":[{"x":1,"y":2}],"labels":{"ja":"hall"},"slot":{"kind":"stand","item":"b1"},"ids":["a","b"],"counts":{"n":2},"note_text":"hi"}"#
let bundle = try loadEventBundle(Data(json.utf8))
precondition(bundle.id == "e1" && bundle.level == .expert && bundle.state == .open)
precondition(bundle.places[0].x == 1 && bundle.labels?["ja"] == "hall" && bundle.retries == 3)
if case .stand(let stand)? = bundle.slot { precondition(stand.item == "b1") } else { preconditionFailure("slot") }
precondition(bundle.ids?.items == ["a", "b"] && bundle.counts?["n"] == 2 && bundle.noteText == "hi")
precondition(bundle.startsAt.timeIntervalSince1970 == 1_794_474_000)
let made = EventBundleDto(id: "e2", startsAt: Date(timeIntervalSince1970: 0), level: .basic, state: .draft,
                          places: [EventPlaceDto(x: 3, y: 4)], labels: nil, slot: .talk(EventTalkDto(kind: "talk", title: "t")),
                          ids: EventIdsDto(items: []), counts: nil, noteText: nil)
let again = try JSONDecoder().decode(EventBundleDto.self, from: JSONEncoder().encode(made))
precondition(again == made && Set([again, made]).count == 1)
let profile = ProfileDto(name: "p", favorite: bundle)
precondition(profile.favorite?.id == "e1" && EventLevel.allCases.count == 2)
let note = try JSONDecoder().decode(EventNoteDto.self, from: Data(#"{"type":"stand","content":{"kind":"stand","item":"b2"}}"#.utf8))
if case .stand(let stand) = note.content { precondition(stand.item == "b2" && note.type == .stand) } else { preconditionFailure("note") }
let built = EventNoteDto(type: .talk, content: .talk(EventTalkDto(kind: "talk", title: "x")))
let builtAgain = try JSONDecoder().decode(EventNoteDto.self, from: JSONEncoder().encode(built))
precondition(builtAgain == built)
print("ok")
"""


@unittest.skipUnless(shutil.which("swiftc"), "swiftc not installed")
class TwoModuleCompileTests(unittest.TestCase):
    """The module's files and a public function returning EventBundleDto are one library module; the app's files and
    a main that imports it are another."""

    def _build(self, access: str, enum_unknown_case: bool = True
               ) -> tuple[subprocess.CompletedProcess, subprocess.CompletedProcess | None]:
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            cfg = _project(root, {"modules": [dict(MODULE, access_level=access)]},
                           enum_unknown_case=enum_unknown_case)
            apply_plan(_plan(cfg)[0], prune_orphans=True)
            core = sorted((root / "ios" / "EventCore" / "Model" / "Generated").glob("*.swift"))
            (root / "api.swift").write_text(_FRAMEWORK_API.replace("public ", "public " if access == "public" else ""))
            out = root / "out"
            out.mkdir()
            lib = subprocess.run(
                ["swiftc", "-parse-as-library", "-emit-library", "-module-name", "EventCore", "-emit-module",
                 "-emit-module-path", str(out / "EventCore.swiftmodule"), "-o", str(out / "libEventCore.dylib"),
                 *map(str, core), str(root / "api.swift")],
                capture_output=True, text=True, timeout=600)
            if lib.returncode != 0:
                return lib, None
            app = sorted((root / "ios" / "App" / "Model" / "Generated").glob("*.swift"))
            (root / "main.swift").write_text(_APP_MAIN)
            build = subprocess.run(
                ["swiftc", "-module-name", "App", "-I", str(out), "-L", str(out), "-lEventCore",
                 "-o", str(out / "app"), *map(str, app), str(root / "main.swift")],
                capture_output=True, text=True, timeout=600)
            if build.returncode != 0:
                return lib, build
            run = subprocess.run([str(out / "app")], capture_output=True, text=True, timeout=60,
                                 env={**os.environ, "DYLD_LIBRARY_PATH": str(out)})
            return lib, run

    def test_public_module_compiles_without_warnings_and_the_app_uses_it(self):
        for open_enums in (True, False):   # the open enum and the raw-value enum api.enum_unknown_case false writes
            with self.subTest(enum_unknown_case=open_enums):
                lib, run = self._build("public", open_enums)
                self.assertEqual(lib.returncode, 0, lib.stderr)
                self.assertNotIn("warning:", lib.stderr)
                self.assertIsNotNone(run)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stdout.strip(), "ok")

    def test_the_internal_control_does_not_let_the_app_see_them(self):
        lib, app = self._build("internal")
        self.assertEqual(lib.returncode, 0, lib.stderr)
        self.assertIsNotNone(app)
        self.assertNotEqual(app.returncode, 0)
        self.assertIn("EventBundleDto", app.stderr)


if __name__ == "__main__":
    unittest.main()
