"""Protocol sync reads and rewrites only the ViewModel class's own members (ticket
jui-kotlin-override-inserted-on-local-val).

`jui build` put `override` on every line starting `val <name>` / `fun <name>` in a hand-written Kotlin ViewModel, so a
local `val plan = …` in a function body became `override val plan` and kotlinc refused it. The same line reading
counted a local (or a nested type's member, a raw string's line, a comment's line) as the class declaring the name,
let a local beside a `private val plan` member hide the narrowing check (and the member became `private override
val`), and on Swift read a local function's labels in place of the member's."""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from jui_cli.core.class_scope import member_lines
from jui_cli.core.impl_updater import (
    extract_swift_method_labels,
    inject_kotlin_override,
    inject_kotlin_var_override,
)
from jui_cli.core.protocol_sync import (
    list_impl_method_names,
    list_impl_narrowed_vars,
    list_impl_var_names,
)

VM = "FooViewModel"


def _kt(body: str, ctor: str = "") -> str:
    return f"package x\n\nclass {VM}{ctor} : P {{\n{body}}}\n"


def _rewrite(source: str, class_name: str | None = VM) -> str:
    return inject_kotlin_override(inject_kotlin_var_override(source, ["plan"], class_name), ["onTap"], class_name)


def _changed(before: str, after: str) -> list[str]:
    return [a.strip() for b, a in zip(before.splitlines(), after.splitlines()) if a != b]


# Each place a name can sit, and whether `override` belongs there.
KOTLIN_FAMILY = {
    "member": ("    val plan: Int = 0\n", ["override val plan: Int = 0"]),
    "member at column 0": ("val plan: Int = 0\n", ["override val plan: Int = 0"]),
    "member indented deep": ("            val plan: Int = 0\n", ["override val plan: Int = 0"]),
    "member with annotation": ("    @Volatile var plan: Int = 0\n", ["@Volatile override var plan: Int = 0"]),
    "member fun": ("    fun onTap() {}\n", ["override fun onTap() {}"]),
    "local val in a fun": ("    fun render() {\n        val plan = 1\n        println(plan)\n    }\n", []),
    "local val at column 0": ("    fun render() {\nval plan = 1\n        println(plan)\n    }\n", []),
    "local val in a lambda": ("    val cb: () -> Unit = {\n        val plan = 1\n        println(plan)\n    }\n", []),
    "local val in init": ("    init {\n        val plan = 1\n        println(plan)\n    }\n", []),
    "companion object": ("    companion object {\n        val plan = 1\n    }\n", []),
    "nested class": ("    class Inner {\n        val plan = 1\n    }\n", []),
    "anonymous object": ("    val o = object : Runnable {\n        val plan = 1\n        override fun run() {}\n    }\n", []),
    "raw string line": ('    val doc = """\n    val plan = 1\n    """\n', []),
    "block comment line": ("    /*\n    val plan = 1\n    */\n", []),
    "nested block comment": ("    /* /* */\n    val plan = 1\n    */\n", []),
    "template with braces before": ('    val s = "${ if (true) { "}" } else "" }"\n    val plan: Int = 0\n',
                                    ["override val plan: Int = 0"]),
    # `'}'` read as code would close the class early and leave the member after it outside.
    "char literal brace before": ("    val c = '}'\n    val plan: Int = 0\n", ["override val plan: Int = 0"]),
    "local fun": ("    fun render() {\n        fun onTap() {}\n        onTap()\n    }\n", []),
}


class KotlinFamilyTests(unittest.TestCase):
    def test_override_goes_on_the_class_members_only(self):
        for label, (body, expected) in KOTLIN_FAMILY.items():
            with self.subTest(label):
                src = _kt(body)
                self.assertEqual(_changed(src, _rewrite(src)), expected)

    def test_a_primary_constructor_property_is_a_member(self):
        src = _kt("    fun render() {}\n", "(\n    val plan: Int,\n    private val other: Int = run { val plan = 2; plan },\n)")
        self.assertEqual(_changed(src, _rewrite(src)), ["override val plan: Int,"])

    def test_another_class_in_the_file_is_left_alone(self):
        src = "package x\n\nclass Helper {\n    val plan = 1\n}\n\n" + _kt("    val plan: Int = 0\n")
        self.assertEqual(_changed(src, _rewrite(src)), ["override val plan: Int = 0"])

    def test_a_second_run_changes_nothing(self):
        src = _kt("".join(body for body, _ in KOTLIN_FAMILY.values()))
        once = _rewrite(src)
        self.assertEqual(_rewrite(once), once)

    def test_without_a_class_name_every_line_is_read_as_before(self):
        src = _kt(KOTLIN_FAMILY["local val in a fun"][0])
        self.assertEqual(_changed(src, _rewrite(src, None)), ["override val plan = 1"])

    def test_a_local_is_not_the_class_declaring_the_name(self):
        src = _kt("    fun render() {\n        val plan = 1\n        fun onTap() {}\n    }\n")
        self.assertNotIn("plan", list_impl_var_names(src, VM, "android"))
        self.assertNotIn("onTap", list_impl_method_names(src, VM, "android"))
        self.assertIn("plan", list_impl_var_names(src))   # the whole-file reading, kept for no class name

    def test_a_local_beside_a_private_member_does_not_hide_the_narrowing(self):
        src = _kt("    private val plan: Int = 0\n    fun render() {\n        val plan = 1\n    }\n")
        self.assertEqual(list_impl_narrowed_vars(src, "android", VM), {"plan": "private"})
        self.assertEqual(list_impl_narrowed_vars(src, "android"), {})   # what hid it

    def test_an_unknown_class_reads_the_whole_file(self):
        self.assertIsNone(member_lines(_kt("    val plan = 0\n"), "Other", "kotlin"))
        src = _kt("    fun render() {\n        val plan = 1\n    }\n")
        self.assertEqual(_changed(src, _rewrite(src, "Other")), ["override val plan = 1"])


class SwiftTests(unittest.TestCase):
    def test_a_local_function_does_not_give_the_members_labels(self):
        src = (f"final class {VM}: P {{\n    func render() {{\n        func onTap(y: Int) {{}}\n    }}\n"
               "    func onTap(_ x: Int) {}\n}\n")
        self.assertEqual(extract_swift_method_labels(src, "onTap", VM), [("_", "x")])
        self.assertEqual(extract_swift_method_labels(src, "onTap"), [("y", "y")])   # what it read

    def test_an_extensions_members_are_the_classs(self):
        src = (f"final class {VM}: P {{\n    var plan = 0\n}}\n\nextension {VM} {{\n"
               "    func onTap(_ x: Int) {}\n    var count: Int { 1 }\n}\n")
        self.assertEqual(list_impl_method_names(src, VM, "ios"), {"onTap"})
        self.assertEqual(list_impl_var_names(src, VM, "ios"), {"plan", "count"})

    def test_a_local_let_and_a_multiline_string_are_not_members(self):
        src = (f'final class {VM}: P {{\n    let doc = """\n    var count = 1\n    """\n'
               '    let s = "\\(f("}"))"\n    let r = #"raw "} \\#(x) "#\n'
               "    func render() {\n        let plan = 1\n    }\n    var real = 0\n}\n")
        self.assertEqual(list_impl_var_names(src, VM, "ios"), {"doc", "s", "r", "real"})


class BuildSyncTests(unittest.TestCase):
    """Through `jui build`'s protocol sync, on the e2e fixture project (spec Login: methods onLogin / onCancel, var
    isLoading)."""

    ANDROID = "android/app/src/main/kotlin/com/example/app/viewmodel/LoginViewModel.kt"
    IOS = "ios/ViewModel/LoginViewModel.swift"

    def _sync(self, android: str | None = None, ios: str | None = None):
        import contextlib
        import io
        from tests.test_build_sync_e2e import _build_fixture_project, _load_config, _make_args
        from jui_cli.commands.build_cmd import _sync_viewmodel_protocols
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        _build_fixture_project(root)
        if android is not None:
            (root / self.ANDROID).write_text(android, encoding="utf-8")
        if ios is not None:
            (root / self.IOS).write_text(ios, encoding="utf-8")
        config_mgr, config = _load_config(root)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ok = _sync_viewmodel_protocols(config_mgr, config, config["platforms"], _make_args())
        return ok, out.getvalue(), root

    _KT_HEAD = ("package com.example.app.viewmodel\n\nimport androidx.lifecycle.ViewModel\n"
                "import kotlinx.coroutines.flow.MutableStateFlow\nimport kotlinx.coroutines.flow.StateFlow\n"
                "import kotlinx.coroutines.flow.asStateFlow\n\nclass LoginViewModel : ViewModel() {\n"
                "    private val _data = MutableStateFlow(LoginData())\n"
                "    val data: StateFlow<LoginData> = _data.asStateFlow()\n")

    def test_a_local_of_a_protocol_name_keeps_its_line(self):
        ok, out, root = self._sync(android=self._KT_HEAD + (
            "    var isLoading: Boolean = false\n"
            "    fun onLogin() {\n        val isLoading = true\n        fun onCancel() {}\n        onCancel()\n    }\n"
            "    fun onCancel() {}\n}\n"))
        self.assertIsNot(ok, False, out)
        impl = (root / self.ANDROID).read_text()
        self.assertIn("    override var isLoading: Boolean = false\n", impl)
        self.assertIn("        val isLoading = true\n", impl)
        self.assertIn("        fun onCancel() {}\n", impl)
        self.assertIn("    override fun onCancel() {}\n", impl)

    def test_a_local_does_not_stand_in_for_a_missing_member(self):
        ok, out, _ = self._sync(android=self._KT_HEAD + (
            "    fun onLogin() {\n        val isLoading = true\n    }\n    fun onCancel() {}\n}\n"))
        self.assertIs(ok, False)
        self.assertIn("declares 'isLoading' but no matching var/val found in Impl", out)

    def test_a_local_beside_a_private_member_is_named_not_injected(self):
        ok, out, root = self._sync(android=self._KT_HEAD + (
            "    private var isLoading: Boolean = false\n"
            "    fun onLogin() {\n        val isLoading = true\n    }\n    fun onCancel() {}\n}\n"))
        self.assertIs(ok, False)
        self.assertIn("declares 'isLoading' but the Impl declares it `private`", out)
        self.assertNotIn("private override", (root / self.ANDROID).read_text())

    def test_a_swift_local_function_does_not_read_as_label_drift(self):
        ok, out, _ = self._sync(ios=(
            "import Foundation\n\nclass LoginViewModel: ObservableObject {\n"
            "    @Published var data = LoginData()\n    @Published var isLoading: Bool = false\n"
            "    func helper() {\n        func onLogin(_ x: Int) {}\n        onLogin(1)\n    }\n"
            "    func onLogin() {}\n    func onCancel() {}\n}\n"))
        self.assertIsNot(ok, False, out)
        self.assertNotIn("external-label drift", out)


# Compiled: an interface and an Impl holding the protocol's names in every place above. Only the class's own
# declarations get `override`; kotlinc accepts the result, and refuses what the line reading wrote.
_KOTLIN_VM = '''package x

interface FooViewModelProtocol {
    val plan: Int
    var count: Int
    fun onTap()
}

class Helper {
    val plan = 5
}

class FooViewModel(
    val plan: Int,
) : FooViewModelProtocol {
    var count: Int = 0
    private val doc = """
    val plan = 1
    """
    /*
    var count = 2
    */
    init {
        val count = 3
        println(count + doc.length)
    }
    fun onTap() {
        val plan = 1
        fun onTap() {}
        onTap()
        val cb: () -> Unit = {
            val count = 4
            println(count)
        }
        cb()
        println(plan)
    }
    companion object {
        val plan = 6
    }
    class Inner {
        var count = 7
    }
    val o = object : Runnable {
        val plan = 8
        override fun run() { println(plan) }
    }
}
'''


class KotlinCompilesTests(unittest.TestCase):
    def setUp(self):
        from tests.test_api_model_enum_case_names import _kotlin_compiler
        found = _kotlin_compiler()
        if found[0] is None:
            self.skipTest(found[1])
        self.java, self.compiler_cp, self.stdlib, self.version = found

    def _compile(self, source: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "Vm.kt").write_text(source, encoding="utf-8")
            return subprocess.run(
                [self.java, "-cp", self.compiler_cp, "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler",
                 "-no-stdlib", "-cp", self.stdlib, "-d", str(t / "classes"), str(t / "Vm.kt")],
                capture_output=True, text=True, timeout=600)

    def _sync(self, class_name: str | None) -> str:
        src = inject_kotlin_var_override(_KOTLIN_VM, ["data", "plan", "count"], class_name)
        return inject_kotlin_override(src, ["onTap"], class_name)

    def test_the_class_members_get_override_and_it_compiles(self):
        out = self._sync("FooViewModel")
        self.assertEqual(_changed(_KOTLIN_VM, out),
                         ["override val plan: Int,", "override var count: Int = 0", "override fun onTap() {"])
        r = self._compile(out)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("error:", r.stdout + r.stderr)

    def test_the_line_reading_does_not_compile(self):
        r = self._compile(self._sync(None))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("modifier 'override' is not applicable to 'local variable'", (r.stdout + r.stderr).lower())


if __name__ == "__main__":
    unittest.main()
