"""Tests for jui_cli.core.impl_updater."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jui_cli.core.impl_updater import (
    atomic_write_text,
    ensure_kotlin_import,
    ensure_kotlin_inheritance,
    ensure_swift_inheritance,
    inject_kotlin_override,
)


class SwiftInheritanceTests(unittest.TestCase):
    def test_adds_to_empty_inheritance(self):
        src = "class LoginViewModel {\n    func a() {}\n}\n"
        out = ensure_swift_inheritance(src, "LoginViewModel", "LoginViewModelProtocol")
        self.assertIn("class LoginViewModel : LoginViewModelProtocol {", out)

    def test_appends_to_existing(self):
        src = "class LoginViewModel: ObservableObject {\n}\n"
        out = ensure_swift_inheritance(src, "LoginViewModel", "LoginViewModelProtocol")
        self.assertIn("ObservableObject, LoginViewModelProtocol", out)

    def test_idempotent(self):
        src = "class Foo : FooProtocol {\n}\n"
        self.assertEqual(ensure_swift_inheritance(src, "Foo", "FooProtocol"), src)

    def test_preserves_where_clause(self):
        src = """class Foo<T>: BaseClass,
    AnotherProtocol where T: Codable, T.ID == String {
}
"""
        out = ensure_swift_inheritance(src, "Foo", "FooProtocol")
        self.assertIn("FooProtocol", out)
        self.assertIn("where T: Codable, T.ID == String", out)

    def test_raises_when_class_missing(self):
        src = "class Bar {}\n"
        with self.assertRaises(ValueError):
            ensure_swift_inheritance(src, "Foo", "FooProtocol")


class KotlinInheritanceTests(unittest.TestCase):
    def test_appends_to_existing_super(self):
        src = "class LoginViewModel : ViewModel() {\n}\n"
        out = ensure_kotlin_inheritance(src, "LoginViewModel", "LoginViewModelProtocol")
        self.assertIn("ViewModel(), LoginViewModelProtocol", out)

    def test_data_class(self):
        src = "data class Foo(val x: Int) : Bar {\n}\n"
        out = ensure_kotlin_inheritance(src, "Foo", "FooProtocol")
        self.assertIn(": Bar, FooProtocol", out)

    def test_sealed_class(self):
        src = "sealed class Foo : Bar {\n}\n"
        out = ensure_kotlin_inheritance(src, "Foo", "FooProtocol")
        self.assertIn("FooProtocol", out)

    def test_value_class(self):
        src = "value class Foo(val x: Int) : Bar {\n}\n"
        out = ensure_kotlin_inheritance(src, "Foo", "FooProtocol")
        self.assertIn("FooProtocol", out)

    def test_inner_class(self):
        src = "inner class Foo : Bar {\n}\n"
        out = ensure_kotlin_inheritance(src, "Foo", "FooProtocol")
        self.assertIn("FooProtocol", out)

    def test_internal_visibility(self):
        src = "internal class Foo : Bar {\n}\n"
        out = ensure_kotlin_inheritance(src, "Foo", "FooProtocol")
        self.assertIn("FooProtocol", out)

    def test_where_clause_preserved(self):
        src = "class Foo<T> : Base<T>() where T : Comparable<T> {\n}\n"
        out = ensure_kotlin_inheritance(src, "Foo", "FooProtocol")
        self.assertIn("FooProtocol", out)
        self.assertIn("where T : Comparable<T>", out)

    def test_hilt_constructor_annotation(self):
        src = "class Foo @Inject constructor(val x: Int) : ViewModel() {\n}\n"
        out = ensure_kotlin_inheritance(src, "Foo", "FooProtocol")
        self.assertIn("ViewModel(), FooProtocol", out)

    def test_idempotent(self):
        src = "class Foo : FooProtocol {\n}\n"
        self.assertEqual(ensure_kotlin_inheritance(src, "Foo", "FooProtocol"), src)


class KotlinOverrideInjectionTests(unittest.TestCase):
    def test_simple_fun(self):
        src = "class Foo {\n    fun onTap() {}\n}\n"
        out = inject_kotlin_override(src, ["onTap"])
        self.assertIn("override fun onTap()", out)

    def test_already_override(self):
        src = "class Foo {\n    override fun onTap() {}\n}\n"
        self.assertEqual(inject_kotlin_override(src, ["onTap"]), src)

    def test_suspend_modifier(self):
        src = "class Foo {\n    suspend fun fetch() {}\n}\n"
        out = inject_kotlin_override(src, ["fetch"])
        self.assertIn("override", out)
        # `override` may land before or after `suspend` depending on regex
        # ordering; both orders are compile-valid in Kotlin.
        self.assertIn("fun fetch()", out)
        self.assertIn("suspend", out)

    def test_private_modifier(self):
        src = "class Foo {\n    private fun onTap() {}\n}\n"
        out = inject_kotlin_override(src, ["onTap"])
        self.assertIn("override fun onTap()", out)

    def test_idempotent(self):
        src = "class Foo {\n    fun onTap() {}\n}\n"
        once = inject_kotlin_override(src, ["onTap"])
        twice = inject_kotlin_override(once, ["onTap"])
        self.assertEqual(once, twice)

    def test_non_target_untouched(self):
        src = "class Foo {\n    fun onTap() {}\n    fun other() {}\n}\n"
        out = inject_kotlin_override(src, ["onTap"])
        self.assertIn("override fun onTap()", out)
        self.assertIn("\n    fun other()", out)


class SwiftLabelExtractionTests(unittest.TestCase):
    def test_plain_param(self):
        from jui_cli.core.impl_updater import extract_swift_method_labels
        src = "class Foo {\n    func foo(x: Int) {}\n}\n"
        self.assertEqual(extract_swift_method_labels(src, "foo"), [("x", "x")])

    def test_underscore_label(self):
        from jui_cli.core.impl_updater import extract_swift_method_labels
        src = "class Foo {\n    func onImageSelected(_ imageData: Data) {}\n}\n"
        self.assertEqual(
            extract_swift_method_labels(src, "onImageSelected"),
            [("_", "imageData")],
        )

    def test_explicit_external_label(self):
        from jui_cli.core.impl_updater import extract_swift_method_labels
        src = "class Foo {\n    func loadWith(for item: Product) {}\n}\n"
        self.assertEqual(
            extract_swift_method_labels(src, "loadWith"),
            [("for", "item")],
        )

    def test_multiple_params_mixed_labels(self):
        from jui_cli.core.impl_updater import extract_swift_method_labels
        src = (
            "class Foo {\n"
            "    func update(_ id: String, with value: Int, plain: Bool) {}\n"
            "}\n"
        )
        self.assertEqual(
            extract_swift_method_labels(src, "update"),
            [("_", "id"), ("with", "value"), ("plain", "plain")],
        )

    def test_missing_func(self):
        from jui_cli.core.impl_updater import extract_swift_method_labels
        self.assertIsNone(extract_swift_method_labels("class Foo {}\n", "x"))

    def test_extract_from_signature_string(self):
        from jui_cli.core.impl_updater import extract_expected_labels_from_swift_sig
        self.assertEqual(
            extract_expected_labels_from_swift_sig("func foo(x: Int)"),
            [("x", "x")],
        )
        self.assertEqual(
            extract_expected_labels_from_swift_sig("func foo(_ x: Int)"),
            [("_", "x")],
        )
        self.assertEqual(
            extract_expected_labels_from_swift_sig("func foo(for x: Int, y: String)"),
            [("for", "x"), ("y", "y")],
        )


class AtomicWriteTests(unittest.TestCase):
    def test_writes_new_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.txt"
            self.assertTrue(atomic_write_text(p, "hello"))
            self.assertEqual(p.read_text(), "hello")

    def test_skips_when_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.txt"
            atomic_write_text(p, "hello")
            self.assertFalse(atomic_write_text(p, "hello"))

    def test_creates_nested_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a" / "b" / "c.txt"
            self.assertTrue(atomic_write_text(p, "x"))
            self.assertTrue(p.exists())


class KotlinImportTests(unittest.TestCase):
    def test_appends_after_last_import(self):
        src = (
            "package com.example.viewmodels\n"
            "\n"
            "import androidx.lifecycle.ViewModel\n"
            "import com.example.data.LoginData\n"
            "\n"
            "class LoginViewModel : ViewModel() {}\n"
        )
        out = ensure_kotlin_import(
            src, "com.example.viewmodel.protocol.LoginViewModelProtocol"
        )
        self.assertIn(
            "import com.example.data.LoginData\n"
            "import com.example.viewmodel.protocol.LoginViewModelProtocol\n",
            out,
        )

    def test_inserts_after_package_when_no_imports(self):
        src = "package com.example.viewmodels\n\nclass LoginViewModel {}\n"
        out = ensure_kotlin_import(
            src, "com.example.viewmodel.protocol.LoginViewModelProtocol"
        )
        self.assertIn(
            "package com.example.viewmodels\n"
            "\n"
            "import com.example.viewmodel.protocol.LoginViewModelProtocol\n",
            out,
        )

    def test_idempotent(self):
        src = (
            "package com.example.viewmodels\n"
            "\n"
            "import com.example.viewmodel.protocol.LoginViewModelProtocol\n"
            "\n"
            "class LoginViewModel {}\n"
        )
        self.assertEqual(
            ensure_kotlin_import(
                src, "com.example.viewmodel.protocol.LoginViewModelProtocol"
            ),
            src,
        )

    def test_no_op_for_empty_fqn(self):
        src = "package x\n"
        self.assertEqual(ensure_kotlin_import(src, ""), src)


if __name__ == "__main__":
    unittest.main()
