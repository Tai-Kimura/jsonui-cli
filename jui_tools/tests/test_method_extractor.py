"""Tests for jui_cli.core.method_extractor."""
from __future__ import annotations

import unittest

from jui_cli.core.method_extractor import (
    ExtractionError,
    extract_marker_blocks,
)


class SingleLineMarkerTests(unittest.TestCase):
    def test_basic_swift(self):
        src = """
class Foo {
    // @jui:protocol func onTap()
    func onTap() {}
}
"""
        blocks = extract_marker_blocks(src)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].signature, "func onTap()")

    def test_basic_kotlin(self):
        src = """
class Foo {
    // @jui:protocol fun onTap()
    fun onTap() {}
}
"""
        blocks = extract_marker_blocks(src)
        self.assertEqual(blocks[0].signature, "fun onTap()")

    def test_kotlin_override_stripped(self):
        src = """
class Foo {
    // @jui:protocol override fun onTap()
    override fun onTap() {}
}
"""
        blocks = extract_marker_blocks(src)
        self.assertEqual(blocks[0].signature, "fun onTap()")

    def test_kotlin_suspend(self):
        src = """
class Foo {
    // @jui:protocol suspend fun fetch(): String
    suspend fun fetch(): String = ""
}
"""
        blocks = extract_marker_blocks(src)
        self.assertEqual(blocks[0].signature, "suspend fun fetch(): String")


class MultiLineMarkerBlockTests(unittest.TestCase):
    def test_swift_attributes_and_generics(self):
        src = """class Foo {
    // @jui:protocol @MainActor
    // @jui:protocol @discardableResult
    // @jui:protocol func update<T>(
    // @jui:protocol     _ id: String,
    // @jui:protocol     transform: (inout T) -> Void
    // @jui:protocol ) async throws -> T where T: Identifiable
    @MainActor
    @discardableResult
    func update<T>(
        _ id: String,
        transform: (inout T) -> Void
    ) async throws -> T where T: Identifiable { fatalError() }
}
"""
        blocks = extract_marker_blocks(src)
        self.assertEqual(len(blocks), 1)
        sig = blocks[0].signature
        self.assertIn("@MainActor", sig)
        self.assertIn("@discardableResult", sig)
        self.assertIn("where T: Identifiable", sig)
        self.assertIn("transform: (inout T)", sig)

    def test_kotlin_multiline_params(self):
        src = """class Foo {
    // @jui:protocol suspend fun <T> process(
    // @jui:protocol     items: List<T>,
    // @jui:protocol     block: suspend (T) -> Unit,
    // @jui:protocol ): Flow<T>
    suspend fun <T> process(
        items: List<T>,
        block: suspend (T) -> Unit,
    ): Flow<T> = TODO()
}
"""
        blocks = extract_marker_blocks(src)
        self.assertEqual(len(blocks), 1)
        self.assertIn("Flow<T>", blocks[0].signature)


class SkippedLinesTests(unittest.TestCase):
    def test_swift_doc_comment(self):
        src = """class Foo {
    // @jui:protocol func onTap()
    /// Handle taps.
    func onTap() {}
}
"""
        self.assertEqual(len(extract_marker_blocks(src)), 1)

    def test_kotlin_block_comment(self):
        src = """class Foo {
    // @jui:protocol fun onTap()
    /**
     * Called when the button is tapped.
     */
    fun onTap() {}
}
"""
        self.assertEqual(len(extract_marker_blocks(src)), 1)

    def test_if_debug(self):
        src = """class Foo {
    // @jui:protocol func debugOnly()
    #if DEBUG
    func debugOnly() {}
    #endif
}
"""
        self.assertEqual(len(extract_marker_blocks(src)), 1)

    def test_mark_section(self):
        src = """class Foo {
    // @jui:protocol func onTap()
    // MARK: - Actions
    func onTap() {}
}
"""
        self.assertEqual(len(extract_marker_blocks(src)), 1)


class ErrorCasesTests(unittest.TestCase):
    def test_no_decl_after_marker(self):
        src = """class Foo {
    // @jui:protocol func onTap()
}
"""
        with self.assertRaises(ExtractionError) as ctx:
            extract_marker_blocks(src)
        self.assertIn("line 2", str(ctx.exception))

    def test_class_boundary_crossed(self):
        src = """class Foo {
    // @jui:protocol func onTap()
}

class Bar {
    func onTap() {}
}
"""
        with self.assertRaises(ExtractionError):
            extract_marker_blocks(src)


class EncodingTests(unittest.TestCase):
    def test_crlf(self):
        src = "class Foo {\r\n    // @jui:protocol func onTap()\r\n    func onTap() {}\r\n}\r\n"
        self.assertEqual(len(extract_marker_blocks(src)), 1)

    def test_bom(self):
        src = "\ufeffclass Foo {\n    // @jui:protocol func onTap()\n    func onTap() {}\n}\n"
        self.assertEqual(len(extract_marker_blocks(src)), 1)


class UnknownGroupTests(unittest.TestCase):
    def test_silent_skip_unknown(self):
        src = """class Foo {
    // @jui:internal fun helper()
    fun helper() {}
    // @jui:protocol fun onTap()
    fun onTap() {}
}
"""
        blocks = extract_marker_blocks(src)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].signature, "fun onTap()")

    def test_silent_skip_modifier(self):
        # `@jui:protocol.doc` is reserved for v1.1 — must not break a v1.0 block.
        src = """class Foo {
    // @jui:protocol.doc some free-form text
    // @jui:protocol fun onTap()
    fun onTap() {}
}
"""
        blocks = extract_marker_blocks(src)
        # The `.doc` line breaks the aggregate; only the bare marker counts.
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].signature, "fun onTap()")


class TwoClassesTests(unittest.TestCase):
    def test_markers_dont_cross_classes(self):
        src = """class Foo {
    // @jui:protocol func fooTap()
    func fooTap() {}
}

class Bar {
    // @jui:protocol func barTap()
    func barTap() {}
}
"""
        blocks = extract_marker_blocks(src)
        self.assertEqual(len(blocks), 2)
        sigs = [b.signature for b in blocks]
        self.assertIn("func fooTap()", sigs)
        self.assertIn("func barTap()", sigs)


if __name__ == "__main__":
    unittest.main()
