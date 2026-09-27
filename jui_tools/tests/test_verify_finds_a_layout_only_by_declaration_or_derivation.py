"""Which layout `jui verify` compares a screen spec with, and what it says when
there is none.

The declaration is `metadata.layoutFile`: when a spec gives it, that file is
the only candidate, and a declared file that is not there is named — not
replaced by another file. Without it, two derivations that need no table: the
spec's file name, and `metadata.name` in snake_case. A spec that resolves to
no layout is named with the paths tried and the hint to declare
`metadata.layoutFile`.

Until 1.9.0 verify also looked a spec's stem up in a table of one
downstream app's screen names — in every project, and after a declared
layoutFile that did not exist. Measured 2026-09-26: no screen spec of that
app's three faces (97) resolved only through the table. Ticket
verify-carries-a-consumer-specific-name-map.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from jui_cli.commands import verify_cmd
from jui_cli.commands.verify_cmd import _resolve_actual_layout, cmd_verify


def _layout_candidates(*args):
    # Looked up when called, so the rest of the file runs on a tree without it.
    return verify_cmd._layout_candidates(*args)


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class Candidates(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.layouts = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_declared_layout_file_is_the_only_candidate(self):
        self.assertEqual(_layout_candidates(self.layouts, "home.spec", "Home", "shop/home"),
                         [self.layouts / "shop/home.json"])

    def test_without_one_the_file_name_then_the_screen_name_in_snake_case(self):
        self.assertEqual(_layout_candidates(self.layouts, "orderlist.spec", "OrderList"),
                         [self.layouts / "orderlist.json", self.layouts / "order_list.json"])

    def test_a_declared_file_that_is_missing_is_not_replaced_by_a_guess(self):
        _write(self.layouts / "home.json", {"type": "View"})
        self.assertIsNone(_resolve_actual_layout(self.layouts, "home.spec", "Home", "shop/home"))

    def test_the_derivations_resolve_without_a_table(self):
        _write(self.layouts / "order_list.json", {"type": "View"})
        self.assertEqual(_resolve_actual_layout(self.layouts, "orderlist.spec", "OrderList"),
                         self.layouts / "order_list.json")

    def test_the_module_carries_no_table_of_app_names(self):
        self.assertFalse(any(isinstance(v, dict) and v and all(
            isinstance(k, str) and isinstance(x, str) for k, x in v.items())
            and name.isupper() and "MAP" in name for name, v in vars(verify_cmd).items()),
            "a module-level name map is back")


class RunNamesAMissingLayout(unittest.TestCase):
    """End to end: `cmd_verify` on a project with a spec it cannot resolve."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _write(self.root / "jui.config.json", {
            "spec_directory": "specs", "layouts_directory": "layouts",
            "platforms": {"ios": {"root": "ios"}},
        })
        (self.root / "layouts").mkdir()
        self._cwd = os.getcwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _run(self) -> str:
        out = io.StringIO()
        args = argparse.Namespace(file=None, detail=False, fail_on_diff=False, platform=None, json_out=None)
        with contextlib.redirect_stdout(out):
            cmd_verify(args)
        return out.getvalue()

    def _spec(self, stem: str, name: str, layout_file: str | None = None) -> None:
        metadata = {"name": name, "displayName": name, "description": "d"}
        if layout_file:
            metadata["layoutFile"] = layout_file
        _write(self.root / "specs" / f"{stem}.spec.json", {
            "type": "screen_spec", "version": "1.0", "metadata": metadata,
            "structure": {"components": [{"id": "title", "type": "Label"}],
                          "layout": {"root": "root", "children": ["title"]}},
        })

    def test_an_unresolved_spec_is_named_with_the_paths_tried_and_the_hint(self):
        self._spec("orderlist", "OrderList")
        said = self._run()
        self.assertIn("orderlist.spec: no layout at orderlist.json or order_list.json — declare it with "
                      "metadata.layoutFile", said)

    def test_a_declared_file_that_is_missing_is_named_as_declared(self):
        self._spec("home", "Home", layout_file="shop/home")
        _write(self.root / "layouts" / "home.json", {"type": "View", "child": []})
        said = self._run()
        self.assertIn("home.spec: metadata.layoutFile 'shop/home' names shop/home.json, which is not in", said)


if __name__ == "__main__":
    unittest.main()
