"""Tests for TypeMapper pipe-union and Map(K,V) generic pattern."""
from __future__ import annotations

import unittest

from jui_cli.core.type_mapper import TypeMapper, _pick_union_segment


class PipeUnionTests(unittest.TestCase):
    def test_two_segments_android_ios(self):
        self.assertEqual(_pick_union_segment("ByteArray|Data", "android"), "ByteArray")
        self.assertEqual(_pick_union_segment("ByteArray|Data", "ios"), "Data")
        # Web falls back to ios when there's only a 2-segment union
        self.assertEqual(_pick_union_segment("ByteArray|Data", "web"), "Data")

    def test_three_segments(self):
        self.assertEqual(_pick_union_segment("A|B|C", "android"), "A")
        self.assertEqual(_pick_union_segment("A|B|C", "ios"), "B")
        self.assertEqual(_pick_union_segment("A|B|C", "web"), "C")

    def test_optional_across_all_segments(self):
        self.assertEqual(_pick_union_segment("ByteArray?|Data?", "ios"), "Data?")
        self.assertEqual(_pick_union_segment("ByteArray?|Data?", "android"), "ByteArray?")

    def test_closure_passes_through(self):
        self.assertEqual(
            _pick_union_segment("() -> Void", "ios"), "() -> Void"
        )

    def test_no_pipe_passes_through(self):
        self.assertEqual(_pick_union_segment("String", "ios"), "String")

    def test_via_type_mapper_resolve_class(self):
        tm = TypeMapper(None)
        self.assertEqual(tm.resolve_class("ByteArray|Data", "ios"), "Data")
        self.assertEqual(tm.resolve_class("ByteArray|Data", "android"), "ByteArray")


class MapGenericTests(unittest.TestCase):
    def test_map_with_primitives(self):
        tm = TypeMapper(None)
        self.assertEqual(tm.resolve_class("Map(String,String)", "ios"), "[String: String]")
        self.assertEqual(tm.resolve_class("Map(String,String)", "android"), "Map<String, String>")
        self.assertEqual(tm.resolve_class("Map(String,String)", "web"), "Record<string, string>")

    def test_map_with_custom_type(self):
        tm = TypeMapper(None)
        self.assertEqual(
            tm.resolve_class("Map(String,ItemImage)", "ios"),
            "[String: ItemImage]",
        )
        self.assertEqual(
            tm.resolve_class("Map(String,ItemImage)", "android"),
            "Map<String, ItemImage>",
        )


class ResolveInStringTests(unittest.TestCase):
    def test_closure_with_bool_param_android(self):
        tm = TypeMapper(None)
        self.assertEqual(
            tm.resolve_in_string("(Bool) -> Void", "android"),
            "(Boolean) -> Unit",
        )

    def test_closure_with_array_spec_notation_android(self):
        tm = TypeMapper(None)
        self.assertEqual(
            tm.resolve_in_string(
                "(Array(PriceItem)) -> Void", "android"
            ),
            "(List<PriceItem>) -> Unit",
        )

    def test_closure_with_array_spec_notation_ios(self):
        tm = TypeMapper(None)
        self.assertEqual(
            tm.resolve_in_string(
                "(Array(PriceItem)) -> Void", "ios"
            ),
            "([PriceItem]) -> Void",
        )

    def test_closure_with_swift_array_literal(self):
        tm = TypeMapper(None)
        self.assertEqual(
            tm.resolve_in_string("([Foo]) -> Void", "android"),
            "(List<Foo>) -> Unit",
        )

    def test_closure_with_optional_param(self):
        tm = TypeMapper(None)
        self.assertEqual(
            tm.resolve_in_string("(String?) -> Void", "android"),
            "(String?) -> Unit",
        )

    def test_no_closure_passthrough(self):
        tm = TypeMapper(None)
        # Without `->` the caller would route through resolve_class instead;
        # in_string still works but is essentially a no-op for atomic types.
        self.assertEqual(
            tm.resolve_in_string("Bool", "android"), "Boolean",
        )

    def test_nested_qualified_type_in_closure(self):
        tm = TypeMapper(None)
        self.assertEqual(
            tm.resolve_in_string(
                "(ChatViewModel.TabState) -> Void", "android"
            ),
            "(ChatViewModel.TabState) -> Unit",
        )


class AndroidBuiltinTypeTests(unittest.TestCase):
    def test_bitmap_android_class_and_import(self):
        tm = TypeMapper(None)
        resolved = tm.resolve("Bitmap", "android")
        self.assertEqual(resolved["class"], "Bitmap")
        self.assertIn("android.graphics.Bitmap", resolved["imports"])


class ArrayGenericTests(unittest.TestCase):
    """Swift array syntax with all four nullability combinations.

    Without the [$T]?, [$T?], [$T?]? variants the pattern engine only
    catches the elements-required form, so a Repository spec with
    `params: [{type: "[String?]"}]` would leak `[String?]` into the
    Kotlin Protocol and trigger a `jui build` warning every run.
    """

    def test_array_required_list(self):
        tm = TypeMapper(None)
        self.assertEqual(tm.resolve_class("[Foo]", "android"), "List<Foo>")
        self.assertEqual(tm.resolve_class("[Foo]", "web"), "Foo[]")

    def test_array_optional_list(self):
        tm = TypeMapper(None)
        self.assertEqual(tm.resolve_class("[Foo]?", "android"), "List<Foo>?")
        self.assertEqual(tm.resolve_class("[Foo]?", "web"), "Foo[] | undefined")

    def test_array_nullable_elements(self):
        tm = TypeMapper(None)
        self.assertEqual(tm.resolve_class("[String?]", "android"), "List<String?>")
        self.assertEqual(tm.resolve_class("[String?]", "web"), "(string | null)[]")

    def test_array_nullable_elements_optional_list(self):
        tm = TypeMapper(None)
        self.assertEqual(tm.resolve_class("[String?]?", "android"), "List<String?>?")
        self.assertEqual(
            tm.resolve_class("[String?]?", "web"),
            "(string | null)[] | undefined",
        )

    def test_array_nullable_elements_with_custom_type(self):
        tm = TypeMapper(None)
        self.assertEqual(
            tm.resolve_class("[BarItem?]", "android"), "List<BarItem?>"
        )

    def test_array_patterns_registered(self):
        tm = TypeMapper(None)
        self.assertTrue(tm.is_registered("[Foo]?"))
        self.assertTrue(tm.is_registered("[Foo?]"))
        self.assertTrue(tm.is_registered("[Foo?]?"))


class ListAliasTests(unittest.TestCase):
    """Canonical `List(T)` spelling must resolve identically to `Array(T)`.

    Regression: jui-generate-project-list-canonical-type-not-converted-for-swift.
    Spec authors mix `List(T)` and `Array(T)` interchangeably; without an
    explicit `List($T)` builtin the iOS Repository Protocol emitted
    `List(Foo)` verbatim — invalid Swift. Kotlin/TS were symmetrically
    broken (`List(Foo)` is not Kotlin syntax either); only Swift hard-
    failed first because xcodebuild surfaced the error fastest.
    """

    def test_list_canonical_resolves_per_platform(self):
        tm = TypeMapper(None)
        self.assertEqual(tm.resolve_class("List(UserTag)", "ios"), "[UserTag]")
        self.assertEqual(tm.resolve_class("List(UserTag)", "android"), "List<UserTag>")
        self.assertEqual(tm.resolve_class("List(UserTag)", "web"), "UserTag[]")

    def test_list_canonical_with_primitive(self):
        tm = TypeMapper(None)
        self.assertEqual(tm.resolve_class("List(String)", "ios"), "[String]")
        self.assertEqual(tm.resolve_class("List(String)", "android"), "List<String>")
        self.assertEqual(tm.resolve_class("List(String)", "web"), "string[]")

    def test_list_canonical_is_registered(self):
        tm = TypeMapper(None)
        self.assertTrue(tm.is_registered("List(Foo)"))
        self.assertTrue(tm.is_registered("List(String)"))


class IsRegisteredTests(unittest.TestCase):
    def test_primitive_is_registered(self):
        tm = TypeMapper(None)
        self.assertTrue(tm.is_registered("String"))
        self.assertTrue(tm.is_registered("Bool"))
        self.assertTrue(tm.is_registered("Void"))

    def test_pattern_is_registered(self):
        tm = TypeMapper(None)
        # Resolves via generic patterns
        self.assertTrue(tm.is_registered("[Product]"))
        self.assertTrue(tm.is_registered("Map(String, Any)"))
        self.assertTrue(tm.is_registered("Array(Product)"))
        # Optional wrapper
        self.assertTrue(tm.is_registered("Product?"))

    def test_unknown_type_not_registered(self):
        tm = TypeMapper(None)
        self.assertFalse(tm.is_registered("ItemImage"))
        self.assertFalse(tm.is_registered("Candidate"))

    def test_pipe_union_registered_if_any_segment_is(self):
        tm = TypeMapper(None)
        # Data is builtin, ByteArray is not a pattern target exactly — but
        # the segment approach: Data registered → whole string counts.
        self.assertTrue(tm.is_registered("ByteArray|Data"))


if __name__ == "__main__":
    unittest.main()
