"""Tests for jui_cli.hotloader package (config, style merge, include
expansion, platform filter, end-to-end layout resolution)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.hotloader.config_loader import (
    DEFAULT_CONFIG,
    load_config,
    write_default_config,
)
from jui_cli.hotloader.include_expander import IncludeExpander
from jui_cli.hotloader.layout_resolver import LayoutResolver
from jui_cli.hotloader.platform_filter import filter_for_platform
from jui_cli.hotloader.style_merger import StyleMerger


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


class ConfigLoaderTest(unittest.TestCase):
    def test_load_uses_defaults_when_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = load_config(root)
            self.assertEqual(cfg.host, DEFAULT_CONFIG["server"]["host"])
            self.assertEqual(cfg.port, DEFAULT_CONFIG["server"]["port"])
            self.assertEqual(cfg.ws_path, DEFAULT_CONFIG["server"]["wsPath"])

    def test_load_merges_partial_user_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "docs" / "hotload" / "config.json",
                {"server": {"port": 19999}},
            )
            cfg = load_config(root)
            self.assertEqual(cfg.port, 19999)
            # Defaults still applied for unspecified keys
            self.assertEqual(cfg.ws_path, "/ws")
            self.assertTrue(cfg.fallback_to_localhost)

    def test_write_default_config_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = write_default_config(root)
            self.assertTrue(path.exists())
            # Pretend user edited the file
            user_edit = json.loads(path.read_text())
            user_edit["server"]["port"] = 12345
            path.write_text(json.dumps(user_edit))
            # Second call must not overwrite
            write_default_config(root)
            self.assertEqual(json.loads(path.read_text())["server"]["port"], 12345)

    def test_load_uses_jui_config_for_spec_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "jui.config.json",
                {
                    "layouts_directory": "custom/layouts",
                    "styles_directory": "custom/styles",
                },
            )
            cfg = load_config(root)
            self.assertEqual(cfg.layouts_dir, (root / "custom/layouts").resolve())
            self.assertEqual(cfg.styles_dir, (root / "custom/styles").resolve())


class StyleMergerTest(unittest.TestCase):
    def test_merges_style_file_into_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            styles = Path(tmp)
            _write(styles / "primary.json", {
                "color": "red",
                "font": 16,
            })
            merger = StyleMerger(styles)
            result = merger.resolve({
                "type": "Label",
                "style": "primary",
                "color": "blue",  # node wins over style
            })
            self.assertEqual(result["type"], "Label")
            self.assertEqual(result["color"], "blue")
            self.assertEqual(result["font"], 16)
            self.assertNotIn("style", result)

    def test_drops_style_type_when_node_has_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            styles = Path(tmp)
            _write(styles / "card.json", {"type": "StyleType", "padding": 8})
            merger = StyleMerger(styles)
            out = merger.resolve({"type": "View", "style": "card"})
            self.assertEqual(out["type"], "View")
            self.assertEqual(out["padding"], 8)

    def test_recurses_into_children(self):
        with tempfile.TemporaryDirectory() as tmp:
            styles = Path(tmp)
            _write(styles / "hdr.json", {"bold": True})
            merger = StyleMerger(styles)
            result = merger.resolve({
                "type": "View",
                "child": [
                    {"type": "Label", "style": "hdr", "text": "x"},
                ],
            })
            self.assertTrue(result["child"][0]["bold"])
            self.assertNotIn("style", result["child"][0])

    def test_missing_style_drops_reference_silently(self):
        with tempfile.TemporaryDirectory() as tmp:
            merger = StyleMerger(Path(tmp))
            out = merger.resolve({"type": "Label", "style": "nope", "text": "hi"})
            self.assertNotIn("style", out)
            self.assertEqual(out["text"], "hi")

    def test_cache_invalidation(self):
        with tempfile.TemporaryDirectory() as tmp:
            styles = Path(tmp)
            _write(styles / "s.json", {"a": 1})
            merger = StyleMerger(styles)
            self.assertEqual(merger.resolve({"style": "s"})["a"], 1)
            _write(styles / "s.json", {"a": 2})
            # Cache still holds the old value
            self.assertEqual(merger.resolve({"style": "s"})["a"], 1)
            merger.invalidate("s")
            self.assertEqual(merger.resolve({"style": "s"})["a"], 2)


class IncludeExpanderTest(unittest.TestCase):
    def test_inline_expands_include(self):
        with tempfile.TemporaryDirectory() as tmp:
            layouts = Path(tmp)
            _write(layouts / "header.json", {"type": "Label", "text": "Hello"})
            expander = IncludeExpander(layouts, StyleMerger(layouts))
            out = expander.expand({"include": "header"})
            self.assertEqual(out["type"], "Label")
            self.assertEqual(out["text"], "Hello")
            self.assertNotIn("include", out)

    def test_camel_case_id_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            layouts = Path(tmp)
            _write(layouts / "card.json", {
                "type": "View",
                "id": "card_root",
                "child": [
                    {"type": "Label", "id": "title"},
                ],
            })
            expander = IncludeExpander(layouts, StyleMerger(layouts))
            out = expander.expand({"include": "card", "id": "main"})
            # prefix derived from outer id "main" stays "main" across the
            # included subtree. Inner ids get merged with prefix.
            self.assertEqual(out["id"], "mainCardRoot")
            self.assertEqual(out["child"][0]["id"], "mainTitle")

    def test_binding_reference_prefixed(self):
        with tempfile.TemporaryDirectory() as tmp:
            layouts = Path(tmp)
            _write(layouts / "row.json", {
                "type": "Label",
                "id": "inner",
                "text": "@{label}",
            })
            expander = IncludeExpander(layouts, StyleMerger(layouts))
            out = expander.expand({"include": "row", "id": "x"})
            # prefix "x" applies to @{label} → @{xLabel}
            self.assertEqual(out["text"], "@{xLabel}")

    def test_binding_this_reference_not_prefixed(self):
        with tempfile.TemporaryDirectory() as tmp:
            layouts = Path(tmp)
            _write(layouts / "row.json", {
                "type": "Label",
                "id": "inner",
                "text": "@{this.value}",
            })
            expander = IncludeExpander(layouts, StyleMerger(layouts))
            out = expander.expand({"include": "row", "id": "x"})
            self.assertEqual(out["text"], "@{this.value}")

    def test_missing_include_drops_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            layouts = Path(tmp)
            expander = IncludeExpander(layouts, StyleMerger(layouts))
            out = expander.expand({"include": "nope", "type": "View"})
            self.assertNotIn("include", out)
            self.assertEqual(out["type"], "View")


class PlatformFilterTest(unittest.TestCase):
    def test_dict_overrides_merge_for_target_platform(self):
        node = {
            "type": "View",
            "height": 100,
            "platform": {
                "ios": {"height": 220},
                "android": {"height": 180},
            },
        }
        ios = filter_for_platform(node, "ios")
        self.assertEqual(ios["height"], 220)
        self.assertNotIn("platform", ios)
        android = filter_for_platform(node, "android")
        self.assertEqual(android["height"], 180)

    def test_string_platform_filter_drops_mismatched_nodes(self):
        tree = {
            "type": "View",
            "child": [
                {"type": "Label", "platform": "ios", "text": "A"},
                {"type": "Label", "platform": "android", "text": "B"},
                {"type": "Label", "text": "C"},
            ],
        }
        ios = filter_for_platform(tree, "ios")
        texts = [c["text"] for c in ios["child"]]
        self.assertEqual(texts, ["A", "C"])

    def test_invalid_platform_raises(self):
        with self.assertRaises(ValueError):
            filter_for_platform({}, "windows")


class LayoutResolverTest(unittest.TestCase):
    def test_end_to_end_style_include_platform(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            layouts = root / "layouts"
            styles = root / "styles"

            _write(styles / "hdr.json", {"font": 18, "weight": "bold"})
            _write(layouts / "banner.json", {
                "type": "Label",
                "id": "bnr",
                "style": "hdr",
                "text": "Banner",
            })
            _write(layouts / "home.json", {
                "type": "View",
                "platform": {"ios": {"padding": 20}},
                "child": [
                    {"include": "banner", "id": "top"},
                    {"type": "Label", "platform": "android", "text": "A-only"},
                ],
            })

            resolver = LayoutResolver(layouts, styles)
            ios = resolver.resolve("home", "ios")
            self.assertEqual(ios["padding"], 20)
            self.assertEqual(len(ios["child"]), 1)
            banner = ios["child"][0]
            self.assertEqual(banner["font"], 18)
            self.assertEqual(banner["weight"], "bold")
            # id prefix: topBnr (camelCase from "bnr")
            self.assertEqual(banner["id"], "topBnr")
            self.assertNotIn("platform", ios)
            self.assertNotIn("style", banner)

            android = resolver.resolve("home", "android")
            # Android doesn't get ios padding override
            self.assertNotIn("padding", android)
            # Android keeps the A-only label
            self.assertEqual(len(android["child"]), 2)

    def test_missing_layout_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resolver = LayoutResolver(root / "layouts", root / "styles")
            self.assertIsNone(resolver.resolve("nope", "ios"))

    def test_subdirectory_layout_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            layouts = Path(tmp)
            _write(layouts / "home" / "header.json", {"type": "Label"})
            resolver = LayoutResolver(layouts, layouts)
            out = resolver.resolve("home/header", "ios")
            self.assertEqual(out["type"], "Label")

    def test_layout_name_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            layouts = Path(tmp).resolve()  # macOS /tmp → /private/tmp symlink
            _write(layouts / "home" / "hdr.json", {"type": "Label"})
            resolver = LayoutResolver(layouts, layouts)
            p = (layouts / "home" / "hdr.json").resolve()
            self.assertEqual(resolver.layout_name_for_path(p), "home/hdr")


if __name__ == "__main__":
    unittest.main()
