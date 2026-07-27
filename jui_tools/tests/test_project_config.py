"""Guard for locating the config that owns a path.

The test validator walks up from a test file and the doc generator walks
up from a test tree; both need the same answer, including in the multi-app
layout where the config is a SIBLING of the tests rather than an ancestor.
A second copy of that probe is what let the diagram miss a project's
declarations while the validator found them.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.core.project_config import declared_app_owned_screens, find_project_config


class FindProjectConfigTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _write_config(self, rel: str, payload: dict) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_ancestor_config_is_found(self):
        expected = self._write_config("jui.config.json", {"project_name": "single"})
        start = self.root / "tests" / "flows"
        start.mkdir(parents=True)
        config, path = find_project_config(start)
        self.assertEqual(path, expected)
        self.assertEqual(config["project_name"], "single")

    def test_multi_app_config_is_a_sibling_of_the_tests(self):
        # tests/<app>/... next to <app>/jui.config.json — the config is
        # never an ancestor here, so a plain walk-up finds nothing.
        expected = self._write_config("user/jui.config.json", {"project_name": "user"})
        self._write_config("admin/jui.config.json", {"project_name": "admin"})
        start = self.root / "tests" / "user" / "screens"
        start.mkdir(parents=True)
        config, path = find_project_config(start)
        self.assertEqual(path, expected)
        self.assertEqual(config["project_name"], "user")

    def test_alternate_config_name_is_accepted(self):
        expected = self._write_config("jsonui-test.config.json", {"project_name": "t"})
        config, path = find_project_config(self.root)
        self.assertEqual(path, expected)
        self.assertEqual(config["project_name"], "t")

    def test_no_config_anywhere_returns_none(self):
        start = self.root / "tests"
        start.mkdir()
        self.assertEqual(find_project_config(start), (None, None))

    def test_unparseable_config_is_skipped_for_a_readable_ancestor(self):
        (self.root / "broken").mkdir()
        (self.root / "broken" / "jui.config.json").write_text("{ not json", encoding="utf-8")
        expected = self._write_config("jui.config.json", {"project_name": "root"})
        config, path = find_project_config(self.root / "broken")
        self.assertEqual(path, expected)
        self.assertEqual(config["project_name"], "root")


class DeclaredAppOwnedScreensTests(unittest.TestCase):
    """Returned unparsed — one place knows both declaration shapes."""

    def test_list_is_returned_as_written(self):
        declared = ["a", {"id": "b", "group": "static"}]
        self.assertEqual(
            declared_app_owned_screens({"test": {"appOwnedScreens": declared}}), declared
        )

    def test_missing_or_malformed_sections_yield_an_empty_list(self):
        for config in (None, {}, {"test": None}, {"test": "nope"}, {"test": {}},
                       {"test": {"appOwnedScreens": "nope"}}):
            with self.subTest(config=config):
                self.assertEqual(declared_app_owned_screens(config), [])


if __name__ == "__main__":
    unittest.main()
