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
import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonui_doc_cli.test_doc import generate_html_directory
from jsonui_doc_cli.test_doc.generator import _report_stale_pages, _test_group


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

    def test_an_app_without_a_type_directory_is_still_an_app(self):
        # `tests/<app>/*.test.json` is a real layout, and a project can hold
        # one app in each style at once — grouping only the one that uses the
        # marker would file the other under no app at all.
        self.assertEqual(_test_group(Path("admin/settings.test.json")), "admin")

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


class MixedLayoutTests(unittest.TestCase):
    """One app using the type directory, one not — both must group."""

    def test_both_apps_land_under_their_own_name(self):
        with TemporaryDirectory() as td:
            tmp = Path(td)
            tests = tmp / "tests"
            _write(tests / "user" / "screens" / "settings.test.json",
                   _screen_test("Settings (user)"))
            _write(tests / "admin" / "settings.test.json",
                   _screen_test("Settings (admin)"))
            out = tmp / "out"
            generate_html_directory(tests, out, "mixed")

            self.assertTrue((out / "screens" / "user" / "settings.test.html").exists())
            self.assertTrue((out / "screens" / "admin" / "settings.test.html").exists())
            # Neither app is left at the top level, which is what made the
            # index read as though one of them had no app.
            self.assertFalse((out / "screens" / "settings.test.html").exists())


class StalePageTests(unittest.TestCase):
    def test_a_leftover_page_is_named(self):
        """The leftover is what made a short count look complete."""
        with TemporaryDirectory() as td:
            tmp = Path(td)
            tests = tmp / "tests"
            _write(tests / "screens" / "login.test.json", _screen_test("Login"))
            out = tmp / "out"
            generate_html_directory(tests, out, "stale")

            orphan = out / "screens" / "removed.test.html"
            orphan.write_text("<html></html>", encoding="utf-8")
            generate_html_directory(tests, out, "stale")

            stale = _report_stale_pages(out)
            self.assertIn(orphan.resolve(), {p.resolve() for p in stale})

    def test_a_page_this_run_wrote_is_not_a_leftover_even_if_unregistered(self):
        """The false positive: not every writer reports through the tally.

        The Figma pages did not, and twelve of them were named leftovers by
        the same run that was writing them. Membership of the written set
        cannot be the only condition, because the set does not know about a
        writer nobody has noticed.
        """
        with TemporaryDirectory() as td:
            tmp = Path(td)
            tests = tmp / "tests"
            _write(tests / "screens" / "login.test.json", _screen_test("Login"))
            out = tmp / "out"
            started = time.time()
            generate_html_directory(tests, out, "unregistered")

            bypassed = out / "figma" / "canvas" / "screen.html"
            bypassed.parent.mkdir(parents=True, exist_ok=True)
            bypassed.write_text("<html></html>", encoding="utf-8")

            stale = _report_stale_pages(out, started)
            self.assertNotIn(bypassed.resolve(), {p.resolve() for p in stale})

    def test_a_page_older_than_the_run_is_still_a_leftover(self):
        """The guard must not swallow the case the check exists for."""
        with TemporaryDirectory() as td:
            tmp = Path(td)
            tests = tmp / "tests"
            _write(tests / "screens" / "login.test.json", _screen_test("Login"))
            out = tmp / "out"
            started = time.time()
            generate_html_directory(tests, out, "leftover")

            orphan = out / "screens" / "removed.test.html"
            orphan.write_text("<html></html>", encoding="utf-8")
            old = started - 3600
            os.utime(orphan, (old, old))

            stale = _report_stale_pages(out, started)
            self.assertIn(orphan.resolve(), {p.resolve() for p in stale})

    def test_a_clean_run_reports_nothing(self):
        with TemporaryDirectory() as td:
            tmp = Path(td)
            tests = tmp / "tests"
            _write(tests / "screens" / "login.test.json", _screen_test("Login"))
            out = tmp / "out"
            generate_html_directory(tests, out, "clean")
            self.assertEqual(_report_stale_pages(out), [])


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
