"""Tests for the ScrollView axis gate (jui build ``ERROR [scrollview]``,
core/scrollview_axis_gate.py, jui-scrollview-horizontalscroll-false-disagrees,
user ruling 2026-10-14).

- refused: orientation horizontal with horizontalScroll false, orientation
  vertical with horizontalScroll true — as written, with the node's style
  merged, under one responsive key only, in a style file that is a
  ScrollView, and on a synonym spelling (Scroll)
- passed: either key alone, both saying the same, a horizontal child (the
  axis is never the child's), a bound value, the same pair on a Collection
- the gate reads layouts and styles, names the file, path and id, and a
  project with none passes
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from jui_cli.commands.build_cmd import _check_scrollview_axes
from jui_cli.core.config_manager import ConfigManager
from jui_cli.core.scrollview_axis_gate import disagreement, node_errors, tree_errors


class PairTest(unittest.TestCase):
    def test_the_two_disagreeing_pairs_are_named(self):
        self.assertEqual(disagreement({"orientation": "horizontal", "horizontalScroll": False}),
                         "orientation 'horizontal' with horizontalScroll false")
        self.assertEqual(disagreement({"orientation": "vertical", "horizontalScroll": True}),
                         "orientation 'vertical' with horizontalScroll true")

    def test_pairs_that_agree_and_single_keys_pass(self):
        for attrs in ({}, {"orientation": "horizontal"}, {"orientation": "vertical"},
                      {"horizontalScroll": True}, {"horizontalScroll": False},
                      {"orientation": "horizontal", "horizontalScroll": True},
                      {"orientation": "vertical", "horizontalScroll": False}):
            self.assertIsNone(disagreement(attrs), attrs)

    def test_a_bound_value_is_not_judged(self):
        self.assertIsNone(disagreement({"orientation": "horizontal", "horizontalScroll": "@{scrolls}"}))
        self.assertIsNone(disagreement({"orientation": "@{axis}", "horizontalScroll": False}))

    def test_a_disagreement_under_one_responsive_key_is_named_with_it(self):
        node = {"type": "ScrollView", "horizontalScroll": False,
                "responsive": {"regular": {"orientation": "horizontal"}, "compact": {"padding": 4}}}
        self.assertEqual(node_errors(node),
                         ["under responsive 'regular': orientation 'horizontal' with horizontalScroll false"])

    def test_an_override_that_mends_the_base_leaves_only_the_base(self):
        node = {"type": "ScrollView", "orientation": "vertical", "horizontalScroll": True,
                "responsive": {"regular": {"orientation": "horizontal"}}}
        self.assertEqual(node_errors(node), ["orientation 'vertical' with horizontalScroll true"])


class TreeTest(unittest.TestCase):
    def test_a_nested_scroll_view_is_found_with_its_path_and_id(self):
        tree = {"type": "View", "child": [{"type": "Label"},
                                          {"type": "ScrollView", "id": "feed", "orientation": "horizontal",
                                           "horizontalScroll": False}]}
        errors = tree_errors(tree)
        self.assertEqual(len(errors), 1, errors)
        self.assertTrue(errors[0].startswith("child[1] id 'feed': orientation 'horizontal'"), errors[0])

    def test_a_synonym_spelling_is_a_scroll_view(self):
        self.assertEqual(len(tree_errors({"type": "Scroll", "orientation": "vertical", "horizontalScroll": True})), 1)

    def test_a_collection_with_the_same_pair_is_not_this_gates(self):
        self.assertEqual(tree_errors({"type": "Collection", "orientation": "horizontal", "horizontalScroll": False}), [])

    def test_a_horizontal_child_is_no_disagreement(self):
        tree = {"type": "ScrollView", "horizontalScroll": False,
                "child": [{"type": "View", "orientation": "horizontal"}]}
        self.assertEqual(tree_errors(tree), [])


def _gate_in(root: Path) -> bool:
    old = os.getcwd()
    os.chdir(root)
    try:
        return _check_scrollview_axes(ConfigManager())
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
            (base / name).parent.mkdir(parents=True, exist_ok=True)
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
        ok, out = self._run({"home.json": {"type": "ScrollView", "orientation": "horizontal",
                                           "child": [{"type": "View", "orientation": "vertical"}]}})
        self.assertTrue(ok)
        self.assertEqual(out, "")

    def test_a_project_without_layouts_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "jui.config.json").write_text(json.dumps({"platforms": {}}))
            self.assertTrue(_gate_in(Path(tmp)))

    def test_a_refused_layout_fails_the_build_and_names_the_file(self):
        ok, out = self._run({"screens/home.json": {"type": "SafeAreaView", "child": [
            {"type": "ScrollView", "id": "rail", "orientation": "horizontal", "horizontalScroll": False}]}})
        self.assertFalse(ok)
        self.assertIn("ERROR [scrollview]", out)
        self.assertIn("screens/home.json: child[0] id 'rail': orientation 'horizontal' with horizontalScroll false", out)

    def test_a_pair_split_between_the_style_and_the_node_is_refused(self):
        ok, out = self._run({"home.json": {"type": "ScrollView", "style": "rail", "horizontalScroll": False}},
                            {"rail.json": {"orientation": "horizontal"}})
        self.assertFalse(ok)
        self.assertIn("home.json: (root): orientation 'horizontal' with horizontalScroll false", out)

    def test_a_style_file_that_is_a_scroll_view_is_read_too(self):
        ok, out = self._run({}, {"rail.json": {"type": "ScrollView", "orientation": "vertical",
                                               "horizontalScroll": True}})
        self.assertFalse(ok)
        self.assertIn("rail.json: (root): orientation 'vertical' with horizontalScroll true", out)


if __name__ == "__main__":
    unittest.main()
