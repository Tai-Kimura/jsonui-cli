"""Tests for AndroidGenerator's nested-type handling.

Regression coverage for: Parent.Child types in spec must
- be referenced qualified (``Parent.Child``)
- import the parent only (never the nested child)
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jui_cli.core.type_mapper import TypeMapper
from jui_cli.generators.android_generator import AndroidGenerator


def _make_generator(root: Path) -> AndroidGenerator:
    pconfig = {
        "package_name": "com.example.app",
        "source_directory": "src/main",
    }
    return AndroidGenerator(root, pconfig, TypeMapper(None))


class SymbolIndexNestedTypeTests(unittest.TestCase):
    def test_nested_enum_not_indexed_as_top_level(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            kfile = root / "app/src/main/kotlin/com/example/app/viewmodels/ChatViewModel.kt"
            kfile.parent.mkdir(parents=True)
            kfile.write_text(
                "package com.example.app.viewmodels\n"
                "\n"
                "class ChatViewModel {\n"
                "    enum class TabState { PURCHASE, BAR }\n"
                "}\n"
            )
            gen = _make_generator(root)
            index = gen._build_symbol_index()
            self.assertEqual(
                index.get("ChatViewModel"),
                "com.example.app.viewmodels.ChatViewModel",
            )
            # Nested enum must NOT appear at top level — `Parent.Child`
            # references reach `Child` through `Parent`'s import.
            self.assertNotIn("TabState", index)

    def test_top_level_enum_is_indexed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            kfile = root / "app/src/main/kotlin/com/example/app/model/SortOption.kt"
            kfile.parent.mkdir(parents=True)
            kfile.write_text(
                "package com.example.app.model\n"
                "\n"
                "enum class SortOption { NAME, DATE }\n"
            )
            gen = _make_generator(root)
            index = gen._build_symbol_index()
            self.assertEqual(
                index.get("SortOption"),
                "com.example.app.model.SortOption",
            )


class TokenExtractionNestedTypeTests(unittest.TestCase):
    def test_imports_only_parent_for_nested_type(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            kfile = root / "app/src/main/kotlin/com/example/app/viewmodels/ChatViewModel.kt"
            kfile.parent.mkdir(parents=True)
            kfile.write_text(
                "package com.example.app.viewmodels\n"
                "\n"
                "class ChatViewModel {\n"
                "    enum class TabState { PURCHASE, BAR }\n"
                "}\n"
            )
            gen = _make_generator(root)
            imports = gen._imports_for_names(
                spec_types=["ChatViewModel.TabState"],
                current_package="com.example.app.viewmodel.protocol",
            )
            self.assertIn(
                "import com.example.app.viewmodels.ChatViewModel", imports,
            )
            # No bogus standalone TabState import — the nested type is
            # reached through ChatViewModel.
            self.assertFalse(
                any(line.endswith(".TabState") for line in imports),
                f"Unexpected nested-type import in {imports!r}",
            )

    def test_array_of_nested_type_imports_parent(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            kfile = (
                root / "app/src/main/kotlin/com/example/app/viewmodels/ItemsListViewModel.kt"
            )
            kfile.parent.mkdir(parents=True)
            kfile.write_text(
                "package com.example.app.viewmodels\n"
                "\n"
                "class ItemsListViewModel {\n"
                "    enum class SortOption { ASC, DESC }\n"
                "}\n"
            )
            gen = _make_generator(root)
            imports = gen._imports_for_names(
                spec_types=["[ItemsListViewModel.SortOption]"],
                current_package="com.example.app.viewmodel.protocol",
            )
            self.assertIn(
                "import com.example.app.viewmodels.ItemsListViewModel",
                imports,
            )
            self.assertFalse(
                any(line.endswith(".SortOption") for line in imports),
            )


if __name__ == "__main__":
    unittest.main()
