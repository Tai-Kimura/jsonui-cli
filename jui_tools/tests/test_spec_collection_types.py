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
import os
import shutil
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


def _viewmodel_project(root: Path, var_type: str) -> None:
    """A ViewModel shaped as a distribution lane's (an observable optional
    closure whose parameter is a collection), no Impl files."""
    import json
    (root / "jui.config.json").write_text(json.dumps({
        "spec_directory": "docs/screens/json", "layouts_directory": "docs/screens/layouts",
        "platforms": {"ios": {"root": "ios", "layoutsDir": "Layouts"},
                      "android": {"root": "android", "layoutsDir": "app/src/main/assets/Layouts"}}}))
    (root / "docs/screens/json").mkdir(parents=True)
    (root / "docs/screens/json/price_edit.spec.json").write_text(json.dumps({
        "type": "screen_spec", "metadata": {"name": "PriceEdit", "displayName": "Price edit"},
        "structure": {"components": []},
        "dataFlow": {"viewModel": {
            "vars": [{"name": "onSaveSuccess", "type": var_type, "observable": True, "optional": True}],
            "methods": [{"name": "configure", "params": [{"name": "prices", "type": "Array(Item)"}]}]}}}))
    (root / "ios").mkdir()
    (root / "ios/sjui.config.json").write_text('{"source_directory": ""}')


def _sync_viewmodels(root: Path) -> tuple[bool, str]:
    from argparse import Namespace
    from jui_cli.commands.build_cmd import _sync_viewmodel_protocols
    from jui_cli.core.config_manager import ConfigManager
    mgr = ConfigManager(root / "jui.config.json")
    config = mgr.load()
    out = io.StringIO()
    with redirect_stdout(out):
        ok = _sync_viewmodel_protocols(mgr, config, config["platforms"], Namespace(
            clean=False, ios_only=False, android_only=False, web_only=False))
    return ok is not False, out.getvalue()


class AClosureIsJudgedByWhatIsInsideIt(unittest.TestCase):
    """`(Array(ProductListing)) -> Void` on a distribution lane: the
    protocol held `(([ProductListing]) -> Void)?` and
    `((List<ProductListing>) -> Unit)?`, and the sync still refused it —
    the whole closure was judged as a constructor left as written. Measured
    on that lane's build (exit 1 on the fix's first cut, 0 on the base)."""

    # Three arms where there was one: the one before skipped on Linux for
    # want of `xcrun` (the iOS simulator SDK) and took the Kotlin check down
    # with it, an undeclared skip that turned python-suite red from 2.3.32
    # (run 41070786517). The Swift check now asks `swiftc` as the other Swift
    # arms here do (test_api_model_enum_case_names), with the iOS-only imports
    # stood in for, so it runs on the Linux runner too.

    def _synced(self, root: Path) -> tuple[Path, Path]:
        _viewmodel_project(root, "(Array(Item)) -> Void")
        ok, out = _sync_viewmodels(root)
        self.assertTrue(ok, out)
        self.assertNotIn("ERROR", out)
        return (next(root.rglob("PriceEditViewModelProtocol.swift")),
                next(root.rglob("PriceEditViewModelProtocol.kt")))

    def test_a_closure_over_a_collection_is_written_without_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            swift, kotlin = self._synced(Path(d))
            self.assertIn("var onSaveSuccess: (([Item]) -> Void)?", swift.read_text(encoding="utf-8"))
            self.assertIn("val onSaveSuccess: StateFlow<((List<Item>) -> Unit)?>", kotlin.read_text(encoding="utf-8"))

    def test_the_kotlin_protocol_type_checks(self):
        # kotlinc, with kotlinx-coroutines for StateFlow
        from tests.test_api_model_enum_case_names import _kotlin_compiler, _pinned, _pinned_jar
        found = _kotlin_compiler()
        if found[0] is None:
            self.skipTest(found[1])
        java, compiler_cp, stdlib, _ = found
        home = Path(os.environ.get("GRADLE_USER_HOME", Path.home() / ".gradle"))
        coroutines = _pinned_jar(home, "org.jetbrains.kotlinx", "kotlinx-coroutines-core-jvm", _pinned())
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _, kotlin = self._synced(root)
            (root / "Data.kt").write_text("package com.example.app.data\n\nclass PriceEditData\n", encoding="utf-8")
            (root / "Item.kt").write_text("package com.example.app.viewmodel.protocol\n\nclass Item\n", encoding="utf-8")
            r = subprocess.run([java, "-cp", compiler_cp, "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler",
                                "-no-stdlib", "-cp", f"{stdlib}:{coroutines}", "-d", str(root / "classes"),
                                str(kotlin), str(root / "Data.kt"), str(root / "Item.kt")],
                               capture_output=True, text=True, timeout=600)
            errors = [line for line in (r.stdout + r.stderr).splitlines() if "error:" in line]
            self.assertEqual((r.returncode, errors), (0, []), r.stdout + r.stderr)

    @unittest.skipUnless(shutil.which("swiftc"), "swiftc not installed")
    def test_the_swift_protocol_type_checks(self):
        # The protocol imports UIKit, SwiftUI and Combine; the members under
        # test need none of them, so those lines are replaced by Foundation and
        # the one Combine name the protocol uses — and the check runs wherever
        # swiftc does, the Linux runner included.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            swift, _ = self._synced(root)
            body = [line for line in swift.read_text(encoding="utf-8").splitlines()
                    if not line.startswith("import ")]
            self.assertTrue(any("onSaveSuccess" in line for line in body))
            checked = root / "Protocol.swift"
            checked.write_text("import Foundation\nprotocol ObservableObject: AnyObject {}\n"
                               "struct PriceEditData {}\nstruct Item {}\n" + "\n".join(body) + "\n",
                               encoding="utf-8")
            r = subprocess.run(["swiftc", "-typecheck", str(checked)], capture_output=True, text=True, timeout=600)
            self.assertEqual(r.returncode, 0, r.stderr + checked.read_text(encoding="utf-8"))

    def test_a_type_inside_a_closure_with_no_spelling_still_stops_the_sync(self):
        # The control: `List<Item>` inside the closure reaches Swift as is.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _viewmodel_project(root, "(List<Item>) -> Void")
            ok, out = _sync_viewmodels(root)
            self.assertFalse(ok)
            self.assertIn("ERROR [protocol-sync]", out)
            self.assertIn("type 'List<Item>' comes out on ios", out)
            self.assertFalse(list(root.rglob("PriceEditViewModelProtocol.swift")), "the Swift file is not written")
