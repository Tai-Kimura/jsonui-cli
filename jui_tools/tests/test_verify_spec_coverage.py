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

from jui_cli.commands.verify_cmd import _check_spec_coverage


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
