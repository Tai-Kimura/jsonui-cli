"""`jui build` stops when two nodes share an id once includes expand (design U8).

An include's id prefixes the ids inside it (`hero` + `type_badge` ->
`heroTypeBadge`), so different spellings can land on one id. The runtime and
every driver find an element by its id as written; neither dynamic runtime
treats a duplicate as an error, so this generation-time check is the gate.
ee's collision specimens 1, 2 and 6 (the same include id twice) are red;
6 with different include ids, and a platform-only node, are not.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from jui_cli.commands.build_cmd import _check_layout_id_uniqueness
from jui_cli.core.config_manager import ConfigManager


def _hero(children):
    return {"type": "View", "id": "hero_root", "child": children}


class LayoutIdUniquenessTest(unittest.TestCase):
    def _run(self, files: dict, platforms=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "jui.config.json").write_text(json.dumps({
                "spec_directory": "docs/screens/json",
                "layouts_directory": "docs/screens/layouts",
                "platforms": platforms or {}}))
            layouts = root / "docs/screens/layouts"
            for name, tree in files.items():
                path = layouts / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(tree))
            old = os.getcwd()
            os.chdir(root)
            out = io.StringIO()
            try:
                with contextlib.redirect_stdout(out):
                    ok = _check_layout_id_uniqueness(ConfigManager(), platforms or {})
            finally:
                os.chdir(old)
            return ok, out.getvalue()

    def test_1_two_spellings_in_one_partial_meet(self):
        ok, out = self._run({
            "detail.json": {"type": "View", "id": "root",
                            "child": [{"include": "part/hero", "id": "hero"}]},
            "part/hero.json": _hero([{"type": "Label", "id": "type_badge"},
                                     {"type": "Label", "id": "typeBadge"}])})
        self.assertIs(ok, False)
        self.assertIn("detail.json (ios): 'heroTypeBadge' is the id of 2 nodes", out)
        self.assertIn("ERROR [layout-ids]", out)

    def test_2_two_include_ids_meet(self):
        ok, out = self._run({
            "detail.json": {"type": "View", "id": "root", "child": [
                {"include": "part/a", "id": "hero"},
                {"include": "part/b", "id": "hero_card"}]},
            "part/a.json": {"type": "View", "id": "a_root",
                            "child": [{"type": "Label", "id": "card_type_badge"}]},
            "part/b.json": {"type": "View", "id": "b_root",
                            "child": [{"type": "Label", "id": "type_badge"}]}})
        self.assertIs(ok, False)
        self.assertIn("'heroCardTypeBadge' is the id of 2 nodes", out)

    def test_6_one_partial_twice_under_one_id_is_red(self):
        ok, out = self._run({
            "detail.json": {"type": "View", "id": "root", "child": [
                {"include": "part/hero", "id": "hero"},
                {"include": "part/hero", "id": "hero"}]},
            "part/hero.json": _hero([{"type": "Label", "id": "title"}])})
        self.assertIs(ok, False)
        self.assertIn("'heroTitle' is the id of 2 nodes", out)

    def test_6_one_partial_twice_under_two_ids_passes(self):
        ok, out = self._run({
            "detail.json": {"type": "View", "id": "root", "child": [
                {"include": "part/hero", "id": "hero"},
                {"include": "part/hero", "id": "side"}]},
            "part/hero.json": _hero([{"type": "Label", "id": "title"}])})
        self.assertIs(ok, True, out)
        self.assertEqual(out, "")

    def test_a_node_one_platform_filters_out_is_not_a_duplicate(self):
        # The same id on an iOS-only node and a web-only node: one per platform.
        ok, out = self._run({"detail.json": {"type": "View", "id": "root", "child": [
            {"type": "Label", "id": "title", "platform": "ios"},
            {"type": "Label", "id": "title", "platform": "web"}]}})
        self.assertIs(ok, True, out)

    def test_boundary_the_same_two_nodes_on_one_platform_are_red(self):
        ok, out = self._run({"detail.json": {"type": "View", "id": "root", "child": [
            {"type": "Label", "id": "title", "platform": "ios"},
            {"type": "Label", "id": "title", "platform": "ios"}]}})
        self.assertIs(ok, False)
        self.assertIn("detail.json (ios): 'title' is the id of 2 nodes", out)
        self.assertNotIn("(web)", out)

    def test_only_the_platforms_the_project_builds(self):
        files = {"detail.json": {"type": "View", "id": "root", "child": [
            {"type": "Label", "id": "title", "platform": "ios"},
            {"type": "Label", "id": "title", "platform": "ios"}]}}
        ok, out = self._run(files, platforms={"web": {"root": "."}})
        self.assertIs(ok, True, out)

    def test_control_unique_ids_pass_silently(self):
        ok, out = self._run({"detail.json": {"type": "View", "id": "root", "child": [
            {"type": "Label", "id": "title"}, {"type": "Label", "id": "subtitle"}]}})
        self.assertIs(ok, True)
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
