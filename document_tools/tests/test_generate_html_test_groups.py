"""Regression: doc-html-tests-flattened-across-apps.

A project holding several apps keeps their tests apart on disk —
``tests/user/screens/`` next to ``tests/admin/screens/`` — but the docsite
poured both into one ``screens/`` directory keyed by file name alone. Two
apps naming a screen the same way is not a coincidence, it is the norm, and
the second page silently overwrote the first: one app's documentation went
missing while the index went on linking to it.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonui_doc_cli.test_doc import generate_html_directory
from jsonui_doc_cli.test_doc.generator import _test_group


def _screen_test(name: str) -> str:
    return json.dumps({
        "type": "screen",
        "metadata": {"name": name},
        "cases": [{"name": "c", "steps": []}],
    })


def _flow_test(name: str) -> str:
    return json.dumps({
        "type": "flow",
        "metadata": {"name": name},
        "steps": [],
    })


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestGroupDerivationTests(unittest.TestCase):
    """The app is read off the path, not declared a second time."""

    def test_segments_before_the_type_directory_are_the_app(self):
        self.assertEqual(
            _test_group(Path("user/screens/account_settings.test.json")), "user")
        self.assertEqual(
            _test_group(Path("admin/flows/booking.test.json")), "admin")

    def test_a_type_directory_in_first_position_means_no_app(self):
        # Single-app layout: tests/screens/<area>/… . The nesting under
        # screens/ is an area, not an app, so nothing is grouped.
        self.assertEqual(_test_group(Path("screens/login/login.test.json")), "")
        self.assertEqual(_test_group(Path("flows/mypage/cancel.test.json")), "")

    def test_a_test_at_the_root_has_no_app(self):
        self.assertEqual(_test_group(Path("sample.test.json")), "")

    def test_nesting_under_the_type_directory_does_not_change_the_app(self):
        self.assertEqual(
            _test_group(Path("user/screens/login/login.test.json")), "user")


class MultiAppSiteTests(unittest.TestCase):
    def _multi_app_site(self, tmp: Path) -> tuple[Path, Path]:
        tests = tmp / "tests"
        # The same screen name in both apps — the shape that used to lose a page.
        _write(tests / "user" / "screens" / "account_settings.test.json",
               _screen_test("Account Settings (user)"))
        _write(tests / "admin" / "screens" / "account_settings.test.json",
               _screen_test("Account Settings (admin)"))
        _write(tests / "user" / "screens" / "booking.test.json",
               _screen_test("Booking"))
        _write(tests / "user" / "flows" / "signup.test.json",
               _flow_test("Signup"))
        out = tmp / "out"
        generate_html_directory(tests, out, "multi")
        return tests, out

    def test_each_app_gets_its_own_directory(self):
        with TemporaryDirectory() as td:
            _, out = self._multi_app_site(Path(td))
            self.assertTrue((out / "screens" / "user" / "account_settings.test.html").exists())
            self.assertTrue((out / "screens" / "admin" / "account_settings.test.html").exists())
            self.assertTrue((out / "screens" / "user" / "booking.test.html").exists())
            self.assertTrue((out / "flows" / "user" / "signup.test.html").exists())
            # Nothing is left at the old flat location.
            self.assertFalse((out / "screens" / "account_settings.test.html").exists())

    def test_both_same_named_screens_keep_their_own_content(self):
        with TemporaryDirectory() as td:
            _, out = self._multi_app_site(Path(td))
            user = (out / "screens" / "user" / "account_settings.test.html").read_text(encoding="utf-8")
            admin = (out / "screens" / "admin" / "account_settings.test.html").read_text(encoding="utf-8")
            # The title is the page's own subject; both sidebars mention both
            # names, so only the title tells the two pages apart.
            self.assertIn("<title>Account Settings (user)", user)
            self.assertIn("<title>Account Settings (admin)", admin)

    def test_index_lists_each_app_as_its_own_subsection(self):
        with TemporaryDirectory() as td:
            _, out = self._multi_app_site(Path(td))
            index = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn("id='screens-user-header'", index)
            self.assertIn("id='screens-admin-header'", index)
            self.assertIn("id='flows-user-header'", index)
            # The counts are per app, and the category still totals them.
            self.assertIn("<span class='category-badge screen'>3</span>", index)

    def test_links_out_of_a_nested_page_account_for_the_extra_level(self):
        with TemporaryDirectory() as td:
            _, out = self._multi_app_site(Path(td))
            page = (out / "screens" / "admin" / "account_settings.test.html").read_text(encoding="utf-8")
            self.assertIn("href='../../index.html'", page)
            self.assertIn("href='../../screens/user/booking.test.html'", page)
            self.assertNotIn("href='../index.html'", page)


class SingleAppSiteTests(unittest.TestCase):
    def test_a_single_app_project_stays_flat(self):
        """No app in the path means no extra level — existing sites do not move."""
        with TemporaryDirectory() as td:
            tmp = Path(td)
            tests = tmp / "tests"
            _write(tests / "screens" / "login" / "login.test.json", _screen_test("Login"))
            _write(tests / "flows" / "mypage" / "cancel.test.json", _flow_test("Cancel"))
            out = tmp / "out"
            generate_html_directory(tests, out, "single")

            self.assertTrue((out / "screens" / "login.test.html").exists())
            self.assertTrue((out / "flows" / "cancel.test.html").exists())
            self.assertFalse((out / "screens" / "login").exists())

            index = (out / "index.html").read_text(encoding="utf-8")
            # Match the rendered element, not the stylesheet: the CSS for
            # subcategories ships on every page whether one is used or not.
            self.assertNotIn("<div class='subcategory'>", index)

            page = (out / "screens" / "login.test.html").read_text(encoding="utf-8")
            self.assertIn("href='../index.html'", page)


class CollisionGuardTests(unittest.TestCase):
    def test_two_tests_named_alike_inside_one_app_both_survive(self):
        """Grouping separates the apps; this is what is left over.

        ``screens/<area>/<name>`` collapses to ``<name>``, so two areas may
        still agree on a file name. The page that loses used to disappear
        without a word — the guard has to keep both and say so.
        """
        with TemporaryDirectory() as td:
            tmp = Path(td)
            tests = tmp / "tests"
            _write(tests / "screens" / "login" / "detail.test.json", _screen_test("Login detail"))
            _write(tests / "screens" / "mypage" / "detail.test.json", _screen_test("Mypage detail"))
            out = tmp / "out"
            generate_html_directory(tests, out, "collide")

            pages = sorted(p.name for p in (out / "screens").glob("*.html"))
            self.assertEqual(len(pages), 2, f"a page was overwritten: {pages}")
            bodies = [
                (out / "screens" / name).read_text(encoding="utf-8")
                for name in pages
            ]
            self.assertTrue(any("Login detail" in b for b in bodies))
            self.assertTrue(any("Mypage detail" in b for b in bodies))
