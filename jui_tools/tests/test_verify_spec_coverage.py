"""Screens shipped without a spec.

Every other gate compares things that exist — build generates from the
Layout, verify diffs declared against actual, validate checks the specs on
disk — so a screen with no spec is absent from all three inputs and nothing
was ever positioned to notice it. Reported by a consumer lane after such a
screen ran for five days, found only because someone happened to look for
its spec file.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.commands.verify_cmd import (
    SpecCoverage,
    _check_spec_coverage,
    _coverage_lines,
)


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class SpecCoverageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.layouts = self.root / "layouts"
        self.specs = self.root / "specs"
        self.layouts.mkdir()
        self.specs.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _layout(self, name, data=None):
        _write(self.layouts / f"{name}.json", data or {"type": "View"})

    def _spec(self, name, *, layout_file=None, spec_type="screen_spec"):
        metadata = {"name": name}
        if layout_file is not None:
            metadata["layoutFile"] = layout_file
        _write(self.specs / f"{name}.spec.json",
               {"type": spec_type, "metadata": metadata})

    def _check(self, config=None):
        return _check_spec_coverage(None, config or {}, self.specs, self.layouts)

    def test_screen_without_a_spec_is_reported(self):
        self._layout("home")
        self._layout("admin_users")
        self._spec("home", layout_file="home")
        coverage = self._check()
        self.assertEqual(["admin_users"], coverage.missing_specs)
        self.assertEqual([], coverage.missing_layouts)

    def test_correspondence_follows_layout_file_not_the_file_name(self):
        # The spec is named differently from the layout it declares.
        self._layout("home")
        self._spec("dashboard", layout_file="home")
        self.assertEqual([], self._check().missing_specs)

    def test_layout_file_may_carry_a_directory(self):
        _write(self.layouts / "settings" / "profile.json", {"type": "View"})
        self._spec("profile", layout_file="settings/profile")
        self.assertEqual([], self._check().missing_specs)

    def test_a_fragment_excuses_itself_on_the_layout_root(self):
        # No exclusion list here: the layout says what it is.
        self._layout("home")
        self._layout("row_cell", {"type": "View", "role": "cell"})
        self._spec("home", layout_file="home")
        self.assertEqual([], self._check().missing_specs)

    def test_a_referenced_cell_is_not_a_screen(self):
        self._layout("home", {"type": "View", "child": [{"cell": "item_row"}]})
        self._layout("item_row")
        self._spec("home", layout_file="home")
        self.assertEqual([], self._check().missing_specs)

    def test_sub_specs_claim_no_layout(self):
        # They inherit the parent's, so they must not register as orphans.
        self._layout("chat")
        self._spec("chat", layout_file="chat")
        self._spec("chat-core", spec_type="screen_sub_spec")
        coverage = self._check()
        self.assertEqual([], coverage.missing_specs)
        self.assertEqual([], coverage.missing_layouts)

    def test_spec_naming_a_layout_that_is_gone_is_reported(self):
        # Half of a rename: the spec still points at the old name.
        self._layout("home")
        self._spec("home", layout_file="home")
        self._spec("legacy", layout_file="removed_screen")
        self.assertEqual(["removed_screen"], self._check().missing_layouts)

    def test_app_owned_screens_are_outside_this_check(self):
        # A hand-written page has no layout, so it is not the failure this
        # watches for (a Layout generating a screen nobody declared). It
        # also could not comply: there is no layout root to carry
        # `"role": "cell"`, and a spec for a screen with nothing to
        # generate describes nothing. Reported by a lane whose declared
        # static pages warned on every run with no way to clear them.
        self._layout("home")
        self._spec("home", layout_file="home")
        config = {"test": {"appOwnedScreens": [
            "native_settings", {"id": "company", "group": "static"},
        ]}}
        coverage = _check_spec_coverage(None, config, self.specs, self.layouts)
        self.assertEqual([], coverage.missing_specs)
        self.assertEqual([], coverage.missing_layouts)

    def test_a_layout_backed_screen_still_warns_alongside_app_owned_ones(self):
        # The exemption is for the declared ids, not a blanket off switch.
        self._layout("home")
        self._layout("admin_users")
        self._spec("home", layout_file="home")
        config = {"test": {"appOwnedScreens": ["native_settings"]}}
        coverage = _check_spec_coverage(None, config, self.specs, self.layouts)
        self.assertEqual(["admin_users"], coverage.missing_specs)

    def test_missing_layouts_directory_is_not_an_error(self):
        coverage = _check_spec_coverage(None, {}, self.specs, self.root / "nope")
        self.assertEqual([], coverage.missing_specs)
        self.assertEqual([], coverage.missing_layouts)


if __name__ == "__main__":
    unittest.main()


class SpecTypeClassificationTests(SpecCoverageTests):
    """The type question, asked positively — and what happens to a stranger.

    1.8.52 shipped a remedy and a check in one version and the remedy tripped
    the check: `app_contracts_spec` was created as the home for a unit target
    no single screen owns, and this command read it as a screen whose layout
    had gone missing. The skip test named the one type to skip, so every type
    invented after it was a screen by default.
    """

    def test_app_contracts_spec_is_not_a_screen_missing_its_layout(self):
        # The 1.8.52 regression, in the shape the consumer reported it: the
        # file has no `metadata.layoutFile` and no layout, because it stands
        # for no screen. Before the fix its FILENAME became a layout id.
        self._layout("home")
        self._spec("home", layout_file="home")
        _write(self.specs / "app_contracts.spec.json",
               {"type": "app_contracts_spec", "unitContracts": []})
        coverage = self._check()
        self.assertEqual([], coverage.missing_layouts)
        self.assertEqual([], coverage.unknown_types)

    def test_a_parent_spec_is_a_screen_and_still_claims_its_layout(self):
        # The positive table has two members and this is the second one. If
        # `screen_parent_spec` were dropped from SCREEN_TYPES the file would
        # stop claiming `parent`, and `parent` would be reported as a screen
        # with no spec — so this arm reddens in the missing_specs direction.
        self._layout("parent")
        self._spec("parent", layout_file="parent", spec_type="screen_parent_spec")
        coverage = self._check()
        self.assertEqual([], coverage.missing_specs)
        self.assertEqual([], coverage.unknown_types)

    def test_a_sub_spec_is_still_skipped(self):
        self._layout("home")
        self._spec("home", layout_file="home")
        self._spec("home_header", spec_type="screen_sub_spec")
        coverage = self._check()
        self.assertEqual([], coverage.missing_layouts)
        self.assertEqual([], coverage.unknown_types)

    def test_an_unknown_type_is_skipped_and_named(self):
        # Skipped AND named. Skipping alone is the failure mode this whole
        # change exists to remove: it makes a spec that fell out of coverage
        # indistinguishable from one that passed.
        self._layout("home")
        self._spec("home", layout_file="home")
        _write(self.specs / "gizmo.spec.json",
               {"type": "some_future_spec", "metadata": {"name": "gizmo"}})
        coverage = self._check()
        self.assertEqual([], coverage.missing_layouts)
        self.assertEqual([], coverage.missing_specs)
        self.assertEqual(1, len(coverage.unknown_types))
        path, kind = coverage.unknown_types[0]
        self.assertTrue(path.endswith("gizmo.spec.json"), path)
        self.assertEqual("some_future_spec", kind)

    def test_a_spec_with_no_type_is_named_as_none_not_as_a_python_type(self):
        # `<none>` is the spelling the printed advice explains. `<NoneType>`
        # would be the same information in a word no author can act on.
        self._layout("home")
        self._spec("home", layout_file="home")
        _write(self.specs / "typeless.spec.json", {"metadata": {"name": "x"}})
        coverage = self._check()
        self.assertEqual(["<none>"], [t for _, t in coverage.unknown_types])


class CoverageLinesTests(unittest.TestCase):
    """The paragraphs themselves.

    `unknown_types` was collected and printed from inside a 300-line command,
    which is a field that reports nothing: no test could reach the print, and
    the suite was green with the list going nowhere. These arms exist because
    the collection arms above passed while the output did not exist.
    """

    def _coverage(self, **kw):
        cov = SpecCoverage()
        for k, v in kw.items():
            setattr(cov, k, v)
        return cov

    def test_unknown_types_reach_the_output(self):
        lines = _coverage_lines(
            self._coverage(unknown_types=[("specs/gizmo.spec.json", "future_spec")]),
            require_coverage=False)
        text = "\n".join(lines)
        self.assertIn("NOTICE", text)
        self.assertIn("specs/gizmo.spec.json", text)
        self.assertIn("future_spec", text)

    def test_no_unknown_types_says_nothing(self):
        self.assertEqual([], _coverage_lines(self._coverage(), require_coverage=False))

    def test_the_notice_is_a_notice_in_both_modes(self):
        # The two lists above swing ERROR/WARNING with requireSpecPerScreen.
        # This one does not, and does not move the exit code: an unknown type
        # is what a doc tool shipping a type first looks like, and a gate that
        # fires on the normal order of two releases gets switched off.
        cov = self._coverage(unknown_types=[("a.spec.json", "future_spec")])
        for require in (True, False):
            text = "\n".join(_coverage_lines(cov, require_coverage=require))
            self.assertIn("NOTICE", text)
            self.assertNotIn("ERROR", text)
            self.assertNotIn("WARNING", text)

    def test_the_two_failing_lists_still_say_error_when_coverage_is_required(self):
        text = "\n".join(_coverage_lines(
            self._coverage(missing_specs=["admin"], missing_layouts=["gone"]),
            require_coverage=True))
        self.assertIn("ERROR", text)
        self.assertIn("admin", text)
        self.assertIn("gone", text)
        self.assertNotIn("requireSpecPerScreen", text)

    def test_the_hint_appears_only_when_coverage_is_not_required(self):
        text = "\n".join(_coverage_lines(
            self._coverage(missing_specs=["admin"]), require_coverage=False))
        self.assertIn("WARNING", text)
        self.assertIn("requireSpecPerScreen", text)
