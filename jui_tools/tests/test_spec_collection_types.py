"""Collections a spec writes reach every protocol as a type of its language.

`returnType: "[String: String]?"` came out on Android as
`List<String: String>?` — the `[$T]` pattern read the dictionary as a list of
`String: String` — and `jui build` ended with exit 0 and no warning; Gradle
failed (ticket kjui-spec-swift-dictionary-type-emits-invalid-kotlin). The
spelling the project switched to, `Dictionary(String, String)?`, came out
verbatim on iOS and Android alike. Nested shapes (`[[Item]]`,
`[String: [Item]]`, `Map(String, [Item])`) passed through untouched too.

TypeMapper now reads the spec's collection shapes structurally — `[T]`,
`[K: V]`, `Array(T)`, `List(T)`, `Dictionary(K, V)`, `Map(K, V)`, optional
and nested — and a class that is no type of the platform's language (a
Kotlin or TypeScript collection reaching Swift, a TypeScript `T[]` reaching
Kotlin, a Swift tuple outside Swift) is recorded; the build's protocol sync
refuses to write such a file and fails. The Kotlin arm type-checks the
generated use case protocol with the pinned kotlinc.
"""

import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jui_cli.core.type_mapper import TypeMapper  # noqa: E402
from tests.test_usecase_protocol_sync import _project, _protocols, _run, _scaffold  # noqa: E402

# spec type -> (Swift, Kotlin, TypeScript)
MAPPED = {
    "[String]": ("[String]", "List<String>", "string[]"),
    "[[Item]]": ("[[Item]]", "List<List<Item>>", "Item[][]"),
    "[String: String]": ("[String: String]", "Map<String, String>", "Record<string, string>"),
    "[String: String]?": ("[String: String]?", "Map<String, String>?", "Record<string, string> | undefined"),
    "[String: Item?]": ("[String: Item?]", "Map<String, Item?>", "Record<string, Item | undefined>"),
    "[String: [Item]]": ("[String: [Item]]", "Map<String, List<Item>>", "Record<string, Item[]>"),
    "[[String: Int]]": ("[[String: Int]]", "List<Map<String, Int>>", "Record<string, number>[]"),
    "[String: Any]?": ("[String: Any]?", "Map<String, Any>?", "Record<string, any> | undefined"),
    "Dictionary(String, String)": ("[String: String]", "Map<String, String>", "Record<string, string>"),
    "Dictionary(String, String)?": ("[String: String]?", "Map<String, String>?", "Record<string, string> | undefined"),
    "Dictionary(String, [Item])": ("[String: [Item]]", "Map<String, List<Item>>", "Record<string, Item[]>"),
    "Map(String, [Item])": ("[String: [Item]]", "Map<String, List<Item>>", "Record<string, Item[]>"),
    "[(String) -> Void]": ("[(String) -> Void]", "List<(String) -> Unit>", None),
}

# What the patterns already wrote, unchanged: the arm the structural reader
# must not move.
UNCHANGED = {
    "[String?]": ("[String?]", "List<String?>", "(string | null)[]"),
    "[String]?": ("[String]?", "List<String>?", "string[] | undefined"),
    "Array(Item)?": ("[Item]?", "List<Item>?", "Item[] | undefined"),
    "List(Item)": ("[Item]", "List<Item>", "Item[]"),
    "Map(String, Item)": ("[String: Item]", "Map<String, Item>", "Record<string, Item>"),
    "[String: Any]": ("[String: Any]", "Map<String, Any>", "Record<string, any>"),
}

# spec type -> the platforms whose language has no such type
UNPORTABLE = {
    "List<Item>": {"ios", "web"},
    "Map<String, Item>": {"ios"},
    "Record<string, Item>": {"ios", "android"},
    "Item[]": {"ios", "android"},
    "(String, Int)": {"android", "web"},
}


class CollectionsMap(unittest.TestCase):
    def test_the_spec_shapes_come_out_in_each_language(self):
        m = TypeMapper()
        for table in (MAPPED, UNCHANGED):
            for spec_type, want in table.items():
                for platform, cls in zip(("ios", "android", "web"), want):
                    if cls is not None:
                        self.assertEqual(m.resolve_class(spec_type, platform), cls, (spec_type, platform))
        self.assertEqual(m.take_unportable(), [])

    def test_a_projects_own_list_pattern_does_not_swallow_a_dictionary(self):
        # A project map carrying `[$T]` (as the reporting one does) read
        # `[String: String]` as a list of `String: String`.
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / ".jsonui-type-map.json"
            path.write_text('{"types": {"[$T]": {"class": "[$T]", "android": {"class": "List<$T>"}}}}')
            m = TypeMapper(path)
            self.assertEqual(m.resolve_class("[String: String]?", "android"), "Map<String, String>?")
            self.assertEqual(m.resolve_class("[Item]", "android"), "List<Item>")

    def test_a_type_with_no_spelling_in_the_language_is_recorded_once(self):
        m = TypeMapper()
        for spec_type in UNPORTABLE:
            for platform in ("ios", "android", "web"):
                m.resolve_class(spec_type, platform)
                m.resolve_class(spec_type, platform)
        lines = m.take_unportable()
        got = {(line.split("'")[1], line.split(" on ")[1].split(" ")[0]) for line in lines}
        want = {(t, p) for t, ps in UNPORTABLE.items() for p in ps}
        self.assertEqual(got, want)
        self.assertEqual(len(lines), len(want))
        self.assertEqual(m.take_unportable(), [], "taken lines are forgotten")


USE_CASE = {
    "name": "SettingsUseCase",
    "methods": [
        {"name": "loadCreditPrices", "params": [], "returnType": "[String: String]?", "isAsync": True},
    ],
}


class BuildRefusesWhatCannotCompile(unittest.TestCase):
    def test_the_reported_dictionary_reaches_every_protocol(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            mgr = _project(root, USE_CASE)
            _scaffold(mgr, root)
            self.assertTrue(_run(mgr))
            bodies = {e: p.read_text(encoding="utf-8") for e, p in _protocols(root).items()}
            self.assertIn("Map<String, String>?", bodies["kt"])
            self.assertIn("[String: String]?", bodies["swift"])
            self.assertNotIn("List<String: String>", bodies["kt"])

    def test_a_kotlin_collection_on_every_platform_fails_the_sync_and_is_not_written(self):
        use_case = {"name": "SettingsUseCase", "methods": [
            {"name": "loadItems", "params": [], "returnType": "List<Item>"}]}
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            mgr = _project(root, use_case)
            _scaffold(mgr, root)
            before = {e: p.read_text(encoding="utf-8") for e, p in _protocols(root).items()}
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertFalse(_run(mgr))
            self.assertIn("ERROR [protocol-sync]", out.getvalue())
            self.assertIn("'List<Item>' comes out on ios", out.getvalue())
            after = {e: p.read_text(encoding="utf-8") for e, p in _protocols(root).items()}
            self.assertEqual(after["swift"], before["swift"], "the Swift file is not written")
            self.assertNotIn("loadItems", after["swift"])

    def test_the_same_type_scoped_to_android_is_written(self):
        use_case = {"name": "SettingsUseCase", "methods": [
            {"name": "loadItems", "params": [], "returnType": "List<Item>", "platforms": ["android"]}]}
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            mgr = _project(root, use_case)
            _scaffold(mgr, root)
            self.assertTrue(_run(mgr))
            self.assertIn("fun loadItems(): List<Item>", _protocols(root)["kt"].read_text(encoding="utf-8"))


class GeneratedKotlinTypeChecks(unittest.TestCase):
    """The use case protocol with every mapped shape, through kotlinc."""

    def test_the_protocol_compiles(self):
        from jui_cli.commands.build_cmd import _platform_generator
        from jui_cli.core.spec_extractor import MethodDef, MethodParam, UseCaseDef
        from tests.test_api_model_enum_case_names import _kotlin_compiler

        found = _kotlin_compiler()
        if found[0] is None:
            self.skipTest(found[1])
        java, compiler_cp, stdlib, version = found
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            mgr = _project(root, {"name": "SettingsUseCase", "methods": []})
            tm = TypeMapper(mgr.type_map_file)
            gen = _platform_generator(root, "android", mgr.load()["platforms"]["android"], tm)
            methods = [MethodDef(name=f"m{i}", params=[MethodParam(name="arg", type=t)], return_type=t, is_async=True)
                       for i, t in enumerate([*MAPPED, *UNCHANGED])]
            source = gen.generate_usecase_protocol("SettingsUseCase", UseCaseDef(name="SettingsUseCase", methods=methods))
            self.assertEqual(tm.take_unportable("android"), [])
            package = next(line.split()[1] for line in source.splitlines() if line.startswith("package "))
            (root / "Protocol.kt").write_text(source, encoding="utf-8")
            (root / "Item.kt").write_text(f"package {package}\n\ndata class Item(val id: String)\n", encoding="utf-8")
            args = [java, "-cp", compiler_cp, "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler",
                    "-no-stdlib", "-cp", stdlib, "-d", str(root / "classes"),
                    str(root / "Protocol.kt"), str(root / "Item.kt")]
            print(f"[kotlinc] kotlin-compiler-embeddable {version}, {len(methods)} methods")
            r = subprocess.run(args, capture_output=True, text=True, timeout=600)
            errors = [line for line in (r.stdout + r.stderr).splitlines() if "error:" in line]
            self.assertEqual((r.returncode, errors), (0, []), source + r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
