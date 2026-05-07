"""Tests for the create_spec_file path/filename logic."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.spec_doc.template import _pascal_to_kebab, create_spec_file


class PascalToKebabTest(unittest.TestCase):
    def test_simple_single_word(self):
        self.assertEqual(_pascal_to_kebab("Login"), "login")

    def test_pascal_case(self):
        self.assertEqual(_pascal_to_kebab("LearnHelloWorld"), "learn-hello-world")

    def test_camel_case(self):
        self.assertEqual(_pascal_to_kebab("userProfile"), "user-profile")

    def test_uppercase_run_followed_by_mixed(self):
        self.assertEqual(_pascal_to_kebab("HTTPServer"), "http-server")


class CreateSpecFileTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_derives_kebab_case_when_file_path_absent(self):
        out = create_spec_file("LearnHelloWorld", self.tmp_path)
        self.assertEqual(out.name, "learn-hello-world.spec.json")
        self.assertTrue(out.exists())

    def test_explicit_file_path_nested(self):
        out = create_spec_file(
            "LearnHelloWorld",
            self.tmp_path,
            file_path="learn/hello-world.spec.json",
        )
        self.assertEqual(out, self.tmp_path / "learn" / "hello-world.spec.json")
        self.assertTrue(out.exists())
        self.assertTrue((self.tmp_path / "learn").is_dir())

    def test_explicit_file_path_without_suffix_gets_spec_json(self):
        out = create_spec_file(
            "Login",
            self.tmp_path,
            file_path="auth/login",
        )
        self.assertEqual(out.name, "login.spec.json")
        self.assertEqual(out.parent.name, "auth")
        self.assertTrue(out.exists())

    def test_explicit_file_path_json_suffix_is_upgraded_to_spec_json(self):
        out = create_spec_file(
            "Login",
            self.tmp_path,
            file_path="auth/login.json",
        )
        # The caller forgot the `.spec.` infix — we add it so downstream
        # tooling still recognises this as a spec file.
        self.assertEqual(out.name, "login.spec.json")

    def test_generated_file_contains_screen_name(self):
        out = create_spec_file("MyScreen", self.tmp_path)
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(data["metadata"]["name"], "MyScreen")


if __name__ == "__main__":
    unittest.main()
