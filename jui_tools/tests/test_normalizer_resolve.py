"""Tests for L2 (resolved) normalization.

The style/include/platform behavior of ``normalize(tree, "L2", ...)``
must match the hotloader's ``LayoutResolver`` output exactly — the L2
pipeline is the same promoted modules, so for alias-free fixtures the
only permitted difference is the top-level ``$jui`` marker.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.core.normalizer import MARKER_KEY, AliasTable, normalize
from jui_cli.hotloader.layout_resolver import LayoutResolver


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _fixture(root: Path) -> tuple[Path, Path]:
    layouts = root / "layouts"
    styles = root / "styles"
    _write(styles / "card.json", {"cornerRadius": 8, "background": "#FFFFFF"})
    _write(
        layouts / "header.json",
        {
            "type": "View",
            "id": "container",
            "child": [{"type": "Label", "id": "title", "text": "@{title}"}],
        },
    )
    _write(
        layouts / "home.json",
        {
            "type": "SafeAreaView",
            "id": "root",
            "child": [
                {"type": "View", "style": "card", "id": "card_box"},
                {"include": "header", "id": "top"},
                {
                    "type": "Label",
                    "id": "ios_only",
                    "platform": "ios",
                    "text": "iOS",
                },
                {
                    "type": "Label",
                    "id": "sized",
                    "fontSize": 12,
                    "platform": {"ios": {"fontSize": 14}},
                },
            ],
        },
    )
    return layouts, styles


class L2MatchesHotloaderTest(unittest.TestCase):
    def test_l2_equals_hotloader_output_modulo_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            layouts, styles = _fixture(root)
            raw = json.loads((layouts / "home.json").read_text())

            for platform in ("ios", "android"):
                with self.subTest(platform=platform):
                    expected = LayoutResolver(layouts, styles).resolve(
                        "home", platform
                    )
                    result = normalize(
                        raw,
                        "L2",
                        platform=platform,
                        styles_dir=styles,
                        layouts_dir=layouts,
                    )
                    marker = result.tree.pop(MARKER_KEY)
                    self.assertEqual(
                        marker,
                        {
                            "normalized": "L2",
                            "schemaVersion": 1,
                            "platform": platform,
                        },
                    )
                    self.assertEqual(result.tree, expected)

    def test_l2_without_platform_keeps_platform_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            layouts, styles = _fixture(root)
            raw = json.loads((layouts / "home.json").read_text())
            result = normalize(
                raw, "L2", styles_dir=styles, layouts_dir=layouts
            )
            self.assertEqual(
                result.tree[MARKER_KEY],
                {"normalized": "L2", "schemaVersion": 1},
            )
            # platform filter not applied without a platform argument
            ids = json.dumps(result.tree)
            self.assertIn("ios_only", ids)

    def test_l2_canonicalizes_aliases_from_styles(self):
        """A style file that uses an alias spelling still resolves to the
        canonical attribute in the L2 output."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            layouts = root / "layouts"
            styles = root / "styles"
            _write(styles / "faded.json", {"alpha": 0.25})
            table = AliasTable(
                {"common": {"opacity": {"type": "number", "aliases": ["alpha"]}}}
            )
            result = normalize(
                {"type": "View", "style": "faded", "id": "x"},
                "L2",
                platform="ios",
                styles_dir=styles,
                layouts_dir=layouts,
                alias_table=table,
            )
            self.assertEqual(result.tree["opacity"], 0.25)
            self.assertNotIn("alpha", result.tree)

    def test_l2_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            layouts, styles = _fixture(root)
            raw = json.loads((layouts / "home.json").read_text())
            once = normalize(
                raw, "L2", platform="ios", styles_dir=styles, layouts_dir=layouts
            )
            twice = normalize(
                once.tree,
                "L2",
                platform="ios",
                styles_dir=styles,
                layouts_dir=layouts,
            )
            self.assertEqual(once.tree, twice.tree)


if __name__ == "__main__":
    unittest.main()
