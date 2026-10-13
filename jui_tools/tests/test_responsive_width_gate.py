"""Tests for the responsive width-condition gate (jui build ``ERROR [responsive]``,
core/responsive_width_gate.py, jui-responsive-width-threshold-conditions).

- the key parse agrees with responsive_resolver.rb: both read the shared
  ``key_cases`` of shared/core/responsive_resolution_vectors.json
- refused: a misspelt width condition (landscape combination, unit, fraction,
  case), width conditions beside size classes, a maxWidth above a minWidth
- passed: width conditions alone, a maxWidth equal to a minWidth, size classes
  alone, unknown keys that do not look like widths (left as they were)
- the gate reads layouts and styles, and a project with none passes
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from jui_cli.commands.build_cmd import _check_responsive_width_conditions
from jui_cli.core.config_manager import ConfigManager
from jui_cli.core.responsive_width_gate import block_errors, tree_errors, width_condition

VECTORS = Path(__file__).resolve().parents[2] / "shared" / "core" / "responsive_resolution_vectors.json"


class KeyParseTest(unittest.TestCase):
    def test_every_shared_key_case(self):
        cases = json.loads(VECTORS.read_text())["key_cases"]
        self.assertGreaterEqual(len(cases), 15)
        for case in cases:
            expected = case["condition"] and (case["condition"]["kind"], case["condition"]["value"])
            self.assertEqual(width_condition(case["key"]), expected, case["key"])


class BlockTest(unittest.TestCase):
    def test_width_conditions_alone_pass(self):
        self.assertEqual(block_errors({"maxWidth:700": {}, "minWidth:700": {}, "minWidth:900": {}}), [])
        self.assertEqual(block_errors({"maxWidth:400": {}, "maxWidth:700": {}}), [])

    def test_size_classes_alone_pass(self):
        self.assertEqual(block_errors({"compact": {}, "regular-landscape": {}}), [])

    def test_an_unknown_key_that_is_not_a_width_is_left_alone(self):
        self.assertEqual(block_errors({"tablet": {}, "maxHeight:700": {}}), [])

    def test_a_misspelt_width_condition_is_refused(self):
        for key in ["minWidth:700-landscape", "minWidth:700px", "minWidth:7.5", "minwidth:700",
                    "MaxWidth:700", "minWidth: 700", "min-width:700", "minWidth"]:
            errors = block_errors({key: {}})
            self.assertEqual(len(errors), 1, key)
            self.assertIn(f"'{key}' is not a width condition", errors[0])

    def test_width_conditions_beside_size_classes_are_refused(self):
        errors = block_errors({"minWidth:700": {}, "regular": {}})
        self.assertEqual(len(errors), 1)
        self.assertIn("and size classes (regular) in one responsive block", errors[0])

    def test_overlap_is_refused_and_named(self):
        errors = block_errors({"minWidth:600": {}, "maxWidth:900": {}})
        self.assertEqual(len(errors), 1)
        self.assertIn("'maxWidth:900' and 'minWidth:600' both hold between 600 and 900", errors[0])

    def test_overlap_boundary(self):
        # equal N: maxWidth:700 holds below 700, minWidth:700 from 700 — no overlap
        self.assertEqual(block_errors({"maxWidth:700": {}, "minWidth:700": {}}), [])
        # one past: both hold at 700
        self.assertEqual(len(block_errors({"maxWidth:701": {}, "minWidth:700": {}})), 1)

    def test_the_overlap_compares_the_largest_max_with_the_smallest_min(self):
        ok = {"maxWidth:300": {}, "maxWidth:600": {}, "minWidth:600": {}, "minWidth:900": {}}
        self.assertEqual(block_errors(ok), [])
        bad = {"maxWidth:300": {}, "maxWidth:950": {}, "minWidth:600": {}, "minWidth:900": {}}
        self.assertIn("'maxWidth:950' and 'minWidth:600'", block_errors(bad)[0])


class TreeTest(unittest.TestCase):
    def test_a_nested_block_is_found_with_its_path_and_id(self):
        tree = {"type": "View", "child": [{"type": "Label"},
                                          {"type": "View", "id": "pane", "responsive": {"minWidth:1": {}, "compact": {}}}]}
        errors = tree_errors(tree)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("child[1] id 'pane': width conditions"), errors[0])


def _gate_in(root: Path) -> bool:
    old = os.getcwd()
    os.chdir(root)
    try:
        return _check_responsive_width_conditions(ConfigManager())
    finally:
        os.chdir(old)


def _project(root: Path, layouts: dict[str, dict], styles: dict[str, dict] | None = None) -> None:
    (root / "jui.config.json").write_text(json.dumps({
        "spec_directory": "docs/screens/json",
        "layouts_directory": "docs/screens/layouts",
        "styles_directory": "docs/screens/styles",
        "platforms": {},
    }))
    for directory, files in (("docs/screens/layouts", layouts), ("docs/screens/styles", styles or {})):
        base = root / directory
        base.mkdir(parents=True, exist_ok=True)
        for name, tree in files.items():
            (base / name).write_text(json.dumps(tree))


class BuildGateTest(unittest.TestCase):
    def _run(self, layouts, styles=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _project(root, layouts, styles)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                ok = _gate_in(root)
            return ok, out.getvalue()

    def test_a_valid_project_passes_silently(self):
        ok, out = self._run({"home.json": {"type": "View", "responsive": {"maxWidth:700": {}, "minWidth:700": {}}}})
        self.assertTrue(ok)
        self.assertEqual(out, "")

    def test_a_project_without_layouts_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "jui.config.json").write_text(json.dumps({"platforms": {}}))
            self.assertTrue(_gate_in(Path(tmp)))

    def test_a_refused_layout_fails_the_build_and_names_the_file(self):
        ok, out = self._run({"home.json": {"type": "View", "responsive": {"minWidth:600": {}, "maxWidth:900": {}}}})
        self.assertFalse(ok)
        self.assertIn("ERROR [responsive]", out)
        self.assertIn("home.json: (root): 'maxWidth:900' and 'minWidth:600'", out)

    def test_a_style_is_read_too(self):
        ok, out = self._run({"home.json": {"type": "View", "style": "pane"}},
                            {"pane.json": {"responsive": {"minWidth:700-landscape": {}}}})
        self.assertFalse(ok)
        self.assertIn("pane.json: (root): 'minWidth:700-landscape' is not a width condition", out)


if __name__ == "__main__":
    unittest.main()
