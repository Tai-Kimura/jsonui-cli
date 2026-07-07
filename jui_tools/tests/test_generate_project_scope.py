"""Regression test: `jui g project --file <spec>` scopes per-screen
artifacts only — the aggregated Repository protocol must always be built
from EVERY spec in the project, not just the requested one (a single-spec
run used to rewrite the aggregated protocols with that spec's methods
alone, silently dropping every other spec's methods)."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import unittest
from pathlib import Path

from jui_cli.commands.generate_cmd import _cmd_generate_project


def _make_args(**overrides):
    ns = argparse.Namespace(
        file=None,
        force=False,
        skip_layout=True,
        dry_run=False,
        ios_only=True,
        android_only=False,
        web_only=False,
        type_map=None,
    )
    for k, v in overrides.items():
        setattr(ns, k, v)
    return ns


def _spec(name: str, method: str) -> dict:
    return {
        "type": "screen_spec",
        "metadata": {"name": name, "displayName": name},
        "structure": {"components": []},
        "dataFlow": {
            "repositories": [{
                "name": "ItemRepository",
                "methods": [{"name": method, "returnType": "Bool"}],
            }],
            "viewModel": {"methods": [], "vars": []},
        },
        "stateManagement": {"uiVariables": []},
    }


class GenerateProjectScopeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "jui.config.json").write_text(json.dumps({
            "spec_directory": "docs/screens/json",
            "layouts_directory": "docs/screens/layouts",
            "platforms": {"ios": {"root": "ios", "layoutsDir": "Layouts"}},
        }))
        spec_dir = self.root / "docs/screens/json"
        spec_dir.mkdir(parents=True)
        (self.root / "docs/screens/layouts").mkdir(parents=True)
        (spec_dir / "home.spec.json").write_text(
            json.dumps(_spec("Home", "getItems")))
        (spec_dir / "detail.spec.json").write_text(
            json.dumps(_spec("Detail", "updateItem")))
        self._cwd = os.getcwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _protocol_text(self) -> str:
        hits = list((self.root / "ios").rglob("ItemRepositoryProtocol.swift"))
        self.assertEqual(len(hits), 1, hits)
        return hits[0].read_text(encoding="utf-8")

    def test_full_run_aggregates_both_specs(self):
        self.assertEqual(_cmd_generate_project(_make_args()), 0)
        content = self._protocol_text()
        self.assertIn("getItems", content)
        self.assertIn("updateItem", content)

    def test_single_spec_run_keeps_other_specs_methods(self):
        # Baseline full run, then a --file --force run for one spec: the
        # aggregated protocol must still carry the other spec's method.
        self.assertEqual(_cmd_generate_project(_make_args()), 0)
        self.assertEqual(
            _cmd_generate_project(
                _make_args(file="home.spec.json", force=True)), 0)
        content = self._protocol_text()
        self.assertIn("getItems", content)
        self.assertIn("updateItem", content,
                      "aggregated protocol lost methods from specs outside "
                      "the --file scope")

    def test_single_spec_run_from_clean_tree_aggregates_all(self):
        self.assertEqual(
            _cmd_generate_project(
                _make_args(file="home.spec.json", force=True)), 0)
        content = self._protocol_text()
        self.assertIn("updateItem", content)

    def test_missing_file_errors(self):
        self.assertEqual(
            _cmd_generate_project(_make_args(file="nope.spec.json")), 1)


if __name__ == "__main__":
    unittest.main()
