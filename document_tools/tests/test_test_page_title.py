"""Regression of `doc-test-html-description-rendered-as-h1-title`.

Test detail pages (screen and flow) must use `metadata.name` as the visible
<h1> and browser <title>; `metadata.description` — often paragraphs long —
renders as a muted `.test-description` block below the heading, never as
the heading itself.
"""

import json
import re
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.test_doc.generator import generate_html_directory

LONG_DESCRIPTION = (
    "Test-runner FLOW-type coverage (login-local, no auth): a single-session "
    "journey across three screens using top-level flow steps. This paragraph "
    "is deliberately long to reproduce the giant-H1 symptom."
)


class TestPageTitleTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        tests_dir = self.root / "tests"
        (tests_dir / "screens").mkdir(parents=True)
        (tests_dir / "flows").mkdir(parents=True)

        (tests_dir / "screens" / "login.test.json").write_text(json.dumps({
            "type": "screen",
            "source": {"layout": "Layouts/login.json"},
            "metadata": {"name": "Login Screen", "description": LONG_DESCRIPTION},
            "cases": [{"name": "shows", "steps": [
                {"assert": "visible", "id": "root"}]}],
        }), encoding="utf-8")

        (tests_dir / "flows" / "login_nav_flow.test.json").write_text(json.dumps({
            "type": "flow",
            "metadata": {"name": "Login Nav Flow", "description": LONG_DESCRIPTION},
            "steps": [{"file": "login", "case": "shows"}],
        }), encoding="utf-8")

        self.out = self.root / "html"
        generate_html_directory(tests_dir, self.out)

    def tearDown(self):
        self._tmp.cleanup()

    def _read(self, rel: str) -> str:
        matches = list(self.out.rglob(rel))
        self.assertTrue(matches, f"{rel} not generated under {self.out}")
        return matches[0].read_text(encoding="utf-8")

    def _h1(self, html: str) -> str:
        m = re.search(r"<h1>(.*?)</h1>", html, re.DOTALL)
        self.assertIsNotNone(m, "no <h1> in page")
        return m.group(1).strip()

    def test_screen_page_h1_and_title_are_name(self):
        html = self._read("login.test.html")
        self.assertEqual(self._h1(html), "Login Screen")
        self.assertIn("<title>Login Screen - Test Documentation</title>", html)

    def test_screen_page_description_is_muted_block(self):
        html = self._read("login.test.html")
        self.assertIn(
            f"<p class='test-description'>{LONG_DESCRIPTION}</p>", html)
        self.assertIn(".test-description", html)  # style shipped with the page

    def test_flow_page_h1_and_title_are_name(self):
        html = self._read("login_nav_flow.test.html")
        self.assertEqual(self._h1(html), "Login Nav Flow")
        self.assertIn("<title>Login Nav Flow - Flow Test Documentation</title>", html)

    def test_flow_page_description_is_muted_block(self):
        html = self._read("login_nav_flow.test.html")
        self.assertIn(
            f"<p class='test-description'>{LONG_DESCRIPTION}</p>", html)
        self.assertIn(".test-description", html)

    def test_description_absent_falls_back_to_name_only(self):
        # A test without description keeps h1 = name and emits no empty block
        tests_dir = self.root / "tests2"
        (tests_dir / "screens").mkdir(parents=True)
        (tests_dir / "screens" / "bare.test.json").write_text(json.dumps({
            "type": "screen",
            "source": {"layout": "Layouts/bare.json"},
            "metadata": {"name": "Bare"},
            "cases": [{"name": "shows", "steps": [
                {"assert": "visible", "id": "root"}]}],
        }), encoding="utf-8")
        out = self.root / "html2"
        generate_html_directory(tests_dir, out)
        html = next(out.rglob("bare.test.html")).read_text(encoding="utf-8")
        self.assertEqual(self._h1(html), "Bare")
        self.assertNotIn("<p class='test-description'>", html)


if __name__ == "__main__":
    unittest.main()
