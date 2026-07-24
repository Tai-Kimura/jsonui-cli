"""Tests for build_cmd._check_variant_constraints — the hard gate for
responsive variant files (``home@regular.json``, 06 variant-file track).

Covers the v1 contract (06a-design.md D3):
- vocabulary: @compact/@medium/@regular pass; landscape/combined and
  unknown suffixes fail; @tablet gets the dedicated diagnostic
- orphan variants (no base) fail
- variants declaring ``data`` / ``platforms`` fail
- variant binding roots must be declared in the base ``data`` section
- screen-root only: partial bases and Collection cell bases fail
- reserved ``<base>_<class>_variant`` stem collision fails
- projects without variants never trip the gate
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from jui_cli.commands.build_cmd import _check_variant_constraints
from jui_cli.core.config_manager import ConfigManager


def _write_config(root: Path) -> None:
    (root / "jui.config.json").write_text(json.dumps({
        "spec_directory": "docs/screens/json",
        "layouts_directory": "docs/screens/layouts",
        "platforms": {},
    }, indent=2))


def _layouts(root: Path) -> Path:
    layouts = root / "docs/screens/layouts"
    layouts.mkdir(parents=True, exist_ok=True)
    return layouts


def _base_layout(data_names: list[str] | None = None, **extra) -> dict:
    layout: dict = {"type": "View", "id": "root", **extra}
    if data_names is not None:
        layout["data"] = [
            {"name": n, "class": "String", "defaultValue": ""} for n in data_names
        ]
    return layout


class VariantGateTest(unittest.TestCase):
    def _run(self, files: dict[str, dict], specs: dict[str, dict] | None = None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_config(root)
            layouts = _layouts(root)
            for name, tree in files.items():
                path = layouts / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(tree))
            if specs:
                spec_dir = root / "docs/screens/json"
                spec_dir.mkdir(parents=True, exist_ok=True)
                for name, tree in specs.items():
                    (spec_dir / name).write_text(json.dumps(tree))
            old = os.getcwd()
            os.chdir(root)
            captured = io.StringIO()
            try:
                with contextlib.redirect_stdout(captured):
                    ok = _check_variant_constraints(ConfigManager())
            finally:
                os.chdir(old)
            return ok, captured.getvalue()

    # --- happy paths -------------------------------------------------

    def test_no_variants_passes_silently(self):
        ok, out = self._run({"home.json": _base_layout()})
        self.assertTrue(ok)
        self.assertEqual(out, "")

    def test_valid_variant_classes_pass(self):
        files = {"home.json": _base_layout(["title"])}
        for cls in ("compact", "medium", "regular"):
            files[f"home@{cls}.json"] = {
                "type": "View", "id": "root",
                "child": [{"type": "Label", "text": "@{title}"}],
            }
        ok, out = self._run(files)
        self.assertTrue(ok, out)

    def test_variant_in_subdirectory_passes(self):
        ok, out = self._run({
            "shop/home.json": _base_layout(["title"]),
            "shop/home@regular.json": {"type": "View", "text": "@{title}"},
        })
        self.assertTrue(ok, out)

    # --- vocabulary --------------------------------------------------

    def test_tablet_suffix_gets_dedicated_diagnostic(self):
        ok, out = self._run({
            "home.json": _base_layout(),
            "home@tablet.json": {"type": "View"},
        })
        self.assertFalse(ok)
        self.assertIn("did you mean 'home@regular.json'", out)

    def test_landscape_and_combined_suffixes_fail(self):
        for cls in ("landscape", "compact-landscape", "medium-landscape",
                    "regular-landscape"):
            ok, out = self._run({
                "home.json": _base_layout(),
                f"home@{cls}.json": {"type": "View"},
            })
            self.assertFalse(ok, cls)
            self.assertIn("inline 'responsive' attribute", out)

    def test_unknown_suffix_fails(self):
        ok, out = self._run({
            "home.json": _base_layout(),
            "home@phone.json": {"type": "View"},
        })
        self.assertFalse(ok)
        self.assertIn("unknown variant size class '@phone'", out)

    def test_nested_variant_name_fails(self):
        ok, out = self._run({
            "home.json": _base_layout(),
            "home@compact@regular.json": {"type": "View"},
        })
        self.assertFalse(ok)
        self.assertIn("malformed variant name", out)

    # --- base / sections ---------------------------------------------

    def test_orphan_variant_fails(self):
        ok, out = self._run({"home@regular.json": {"type": "View"}})
        self.assertFalse(ok)
        self.assertIn("orphan variant", out)

    def test_variant_with_data_section_fails(self):
        ok, out = self._run({
            "home.json": _base_layout(["title"]),
            "home@regular.json": {
                "type": "View",
                "data": [{"name": "extra", "class": "String"}],
            },
        })
        self.assertFalse(ok)
        self.assertIn("must not declare a 'data' section", out)

    def test_variant_with_platforms_fails(self):
        ok, out = self._run({
            "home.json": _base_layout(),
            "home@regular.json": {"type": "View", "platforms": ["ios"]},
        })
        self.assertFalse(ok)
        self.assertIn("must not declare 'platforms'", out)

    # --- binding containment -----------------------------------------

    def test_variant_binding_outside_base_data_fails(self):
        ok, out = self._run({
            "home.json": _base_layout(["title"]),
            "home@regular.json": {
                "type": "View",
                "child": [
                    {"type": "Label", "text": "@{title}"},
                    {"type": "Label", "text": "@{subtitle ?? 'x'}"},
                    {"type": "View", "hidden": "@{!collapsed}"},
                ],
            },
        })
        self.assertFalse(ok)
        self.assertIn("collapsed, subtitle", out)
        self.assertNotIn("title,", out)

    def test_variant_binding_dot_path_root_resolves(self):
        ok, out = self._run({
            "home.json": _base_layout(["user"]),
            "home@regular.json": {
                "type": "View",
                "child": [{"type": "Label", "text": "@{user.name}"}],
            },
        })
        self.assertTrue(ok, out)

    # --- screen-root only --------------------------------------------

    def test_variant_of_partial_base_fails(self):
        ok, out = self._run({
            "header.json": _base_layout(partial=True),
            "header@regular.json": {"type": "View"},
        })
        self.assertFalse(ok)
        self.assertIn("partial", out)

    def test_variant_of_cell_layout_fails(self):
        ok, out = self._run(
            {
                "item_cell.json": _base_layout(),
                "item_cell@regular.json": {"type": "View"},
            },
            specs={
                "list.spec.json": {
                    "type": "screen_spec",
                    "metadata": {"name": "List"},
                    "structure": {
                        "collections": [{
                            "id": "items",
                            "cell": {"layoutFile": "item_cell"},
                        }],
                    },
                },
            },
        )
        self.assertFalse(ok)
        self.assertIn("cell layout", out)

    # --- collision ---------------------------------------------------

    def test_reserved_variant_stem_collision_fails(self):
        ok, out = self._run({
            "home.json": _base_layout(),
            "home@regular.json": {"type": "View"},
            "home_regular_variant.json": _base_layout(),
        })
        self.assertFalse(ok)
        self.assertIn("collides with the generated variant view name", out)


class VariantDistributionTest(unittest.TestCase):
    """_distribute_layouts applies the BASE layout's platforms whitelist
    to its variants (variants cannot declare their own — gate rule V5)."""

    def test_variant_inherits_base_platforms_whitelist(self):
        import argparse

        from jui_cli.commands.build_cmd import _distribute_layouts

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "jui.config.json").write_text(json.dumps({
                "spec_directory": "docs/screens/json",
                "layouts_directory": "docs/screens/layouts",
                "platforms": {
                    "ios": {"root": "ios", "layoutsDir": "Layouts"},
                    "android": {"root": "android", "layoutsDir": "assets/Layouts"},
                },
            }, indent=2))
            layouts = _layouts(root)
            (layouts / "home.json").write_text(json.dumps(
                {"type": "View", "platforms": ["android"]}
            ))
            (layouts / "home@regular.json").write_text(json.dumps(
                {"type": "View"}
            ))

            args = argparse.Namespace(
                clean=False, ios_only=False, android_only=False, web_only=False,
            )
            old = os.getcwd()
            os.chdir(root)
            try:
                config_mgr = ConfigManager()
                platforms = config_mgr.load()["platforms"]
                with contextlib.redirect_stdout(io.StringIO()):
                    _distribute_layouts(config_mgr, platforms, args)
            finally:
                os.chdir(old)

            self.assertTrue((root / "android/assets/Layouts/home.json").exists())
            self.assertTrue(
                (root / "android/assets/Layouts/home@regular.json").exists()
            )
            self.assertFalse((root / "ios/Layouts/home.json").exists())
            self.assertFalse(
                (root / "ios/Layouts/home@regular.json").exists(),
                "variant must inherit the base's platforms whitelist",
            )


if __name__ == "__main__":
    unittest.main()
