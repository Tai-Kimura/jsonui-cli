"""Ownership of a unit target is derived from the specs, not from its site.

The controls are the point of this file. A derivation that reads only one of
the four sources still answers every question — it just answers `0` for
everything it cannot see, and `0` means "owned by no screen", which reads as
"app-owned". That failure arrives as a plausible LARGER count of app-owned
targets, never as an error, so each source gets a control that must come back
`1` and the absence case gets one that must come back `0`.

Measured while designing this: a derivation built on `dataFlow` alone reported
two known ViewModels as `0`. A derivation built on the layout closure alone
would report every ViewModel as `0` for the opposite reason. Neither is
detectable without a control per source.
"""

from __future__ import annotations

import ast
import inspect
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jui_cli.core import shared_core  # noqa: E402

ownership = shared_core.load("unit_target_ownership")


# One screen per source, so a source that stops working takes exactly one
# control down with it.
SCREENS = {
    # source 1: the generator names this screen's ViewModel
    "AccountSettings": {"dataFlow": {}},
    # source 2: names a repository
    "Listing": {"dataFlow": {"repositories": [{"name": "ListingRepository",
                                               "methods": []}]}},
    # source 3: names a use case
    "Checkout": {"dataFlow": {"useCases": [{"name": "ConfirmUseCase",
                                            "methods": []}]}},
    # source 4 is supplied by the caller; this screen reaches a component
    "Dashboard": {"dataFlow": {}},
}

# What each screen DECLARES via `structure.customComponents`, resolved to the
# component's class name. Not what its layout uses — see the module docstring.
DECLARED_COMPONENTS = {"Dashboard": {"CalendarWidget"}}

KNOWN = {
    "AccountSettingsViewModel", "ListingRepository", "ConfirmUseCase",
    "CalendarWidget", "SharedHttpClient",
}


class EachSourceHasItsOwnControl(unittest.TestCase):
    def test_a_view_model_is_owned_by_its_screen(self):
        self.assertEqual(
            ["AccountSettings"],
            ownership.owner_screens("AccountSettingsViewModel", SCREENS, DECLARED_COMPONENTS))

    def test_a_named_repository_is_owned_by_the_screen_that_names_it(self):
        self.assertEqual(
            ["Listing"],
            ownership.owner_screens("ListingRepository", SCREENS, DECLARED_COMPONENTS))

    def test_a_named_use_case_is_owned_by_the_screen_that_names_it(self):
        self.assertEqual(
            ["Checkout"],
            ownership.owner_screens("ConfirmUseCase", SCREENS, DECLARED_COMPONENTS))

    def test_a_component_is_owned_by_the_screen_that_declares_it(self):
        self.assertEqual(
            ["Dashboard"],
            ownership.owner_screens("CalendarWidget", SCREENS, DECLARED_COMPONENTS))

    def test_a_shared_utility_is_owned_by_no_screen(self):
        """The negative control. Without it, an implementation that returns a
        non-empty answer for everything passes all four above."""
        self.assertEqual(
            [], ownership.owner_screens("SharedHttpClient", SCREENS, DECLARED_COMPONENTS))

    def test_the_four_controls_do_not_share_an_answer(self):
        """An implementation returning the same value for every target would
        satisfy any single control. Three distinct owners plus the empty case
        is what makes the set discriminating."""
        answers = [
            ownership.owner_screens(t, SCREENS, DECLARED_COMPONENTS)
            for t in ("AccountSettingsViewModel", "ListingRepository",
                      "ConfirmUseCase", "SharedHttpClient")
        ]
        self.assertEqual(len(answers), len({tuple(a) for a in answers}))


class TheCardinalityDecidesTheDeclarationSite(unittest.TestCase):
    def test_one_owner_is_screen_owned(self):
        kind, owners = ownership.classify(
            "ListingRepository", SCREENS, DECLARED_COMPONENTS, KNOWN)
        self.assertEqual(ownership.SCREEN_OWNED, kind)
        self.assertEqual(["Listing"], owners)

    def test_two_owners_is_app_owned(self):
        """P3's specimen, built rather than found: no target in the corpus
        measured so far has more than one owner, so running the corpus would
        never exercise this branch."""
        screens = dict(SCREENS)
        screens["Archive"] = {
            "dataFlow": {"repositories": [{"name": "ListingRepository",
                                           "methods": []}]}}
        kind, owners = ownership.classify(
            "ListingRepository", screens, DECLARED_COMPONENTS, KNOWN)
        self.assertEqual(ownership.APP_OWNED, kind)
        self.assertEqual(["Archive", "Listing"], owners)

    def test_zero_owners_with_a_real_symbol_is_app_owned(self):
        kind, _ = ownership.classify(
            "SharedHttpClient", SCREENS, DECLARED_COMPONENTS, KNOWN)
        self.assertEqual(ownership.APP_OWNED, kind)

    def test_a_symbol_nothing_defines_is_unresolved_not_app_owned(self):
        """A misspelled target reaches zero screens exactly as a shared
        utility does. Folding the two together turns a typo into a
        permission."""
        kind, _ = ownership.classify("SharedHtpClient", SCREENS, DECLARED_COMPONENTS, KNOWN)
        self.assertEqual(ownership.UNRESOLVED, kind)


class AMissingInputIsNotAPermission(unittest.TestCase):
    def test_without_the_closure_a_zero_is_undetermined(self):
        """The failure this guards against: a caller that has not resolved the
        declared components sees component-owned targets as owned by nobody."""
        kind, _ = ownership.classify(
            "CalendarWidget", SCREENS, None, KNOWN)
        self.assertEqual(ownership.UNDETERMINED, kind)

    def test_without_known_targets_a_zero_is_undetermined(self):
        kind, _ = ownership.classify(
            "SharedHttpClient", SCREENS, DECLARED_COMPONENTS, None)
        self.assertEqual(ownership.UNDETERMINED, kind)

    def test_neither_undetermined_nor_unresolved_permits_an_app_declaration(self):
        for target, closure, known in (
            ("CalendarWidget", None, KNOWN),      # undetermined
            ("SharedHtpClient", DECLARED_COMPONENTS, KNOWN),  # unresolved
        ):
            with self.subTest(target=target):
                self.assertFalse(ownership.app_level_allowed(
                    target, SCREENS, closure, known))

    def test_a_app_owned_target_is_permitted(self):
        self.assertTrue(ownership.app_level_allowed(
            "SharedHttpClient", SCREENS, DECLARED_COMPONENTS, KNOWN))


class TheViewModelSpellingMatchesTheGenerator(unittest.TestCase):
    """The ownership rule and `jui build` must agree on what a ViewModel is
    called, or source 1 silently stops matching. They are two files, so this
    compares the generator's own source rather than restating the convention.
    """

    def test_build_cmd_constructs_the_same_name(self):
        from jui_cli.commands import build_cmd

        src = inspect.getsource(build_cmd)
        wanted = ownership.view_model_name("{spec.name}")
        self.assertIn(
            wanted, src,
            f"build_cmd no longer spells a ViewModel as {wanted!r}; source 1 "
            "of the ownership rule would stop matching without failing")

    def test_the_generator_builds_it_from_the_screen_name(self):
        """Not just the suffix: the name is the SCREEN's, which is what makes
        the owner derivable at all."""
        from jui_cli.commands import build_cmd

        tree = ast.parse(inspect.getsource(build_cmd))
        joined = {
            ast.unparse(node)
            for node in ast.walk(tree)
            if isinstance(node, ast.JoinedStr)
        }
        self.assertTrue(
            any("spec.name" in j and "ViewModel" in j for j in joined),
            "no f-string in build_cmd joins a spec name to 'ViewModel'")


class TheConstantsHoldTheValuesTheyName(unittest.TestCase):
    """Every other arm compares against the constants, so none of them can see
    a constant whose VALUE is wrong. A rename that moved `APP_OWNED` but left
    it equal to `"face_owned"` left all sixteen green; it was found by reading,
    not by running. These four read the literals."""

    def test_each_kind_is_spelled_as_it_reads(self):
        self.assertEqual("screen_owned", ownership.SCREEN_OWNED)
        self.assertEqual("app_owned", ownership.APP_OWNED)
        self.assertEqual("unresolved", ownership.UNRESOLVED)
        self.assertEqual("undetermined", ownership.UNDETERMINED)

    def test_the_view_model_suffix_is_spelled_as_it_reads(self):
        self.assertEqual("ViewModel", ownership.VIEW_MODEL_SUFFIX)


class OwnershipClosesInsideOneApp(unittest.TestCase):
    """A repository can hold several apps (`--app admin:… --app user:…`), and
    two of them may name the same target. Mixed into one `screens` dict that
    reads as two owners — app-owned — and then NO single app's contracts spec
    can hold it, because each app has its own. The frame is the caller's to
    supply: discovery has one `spec_directory` per project while the doc
    generator keys by app, so this module cannot check its own scope.
    """

    ADMIN = {"Listing": {"dataFlow": {"repositories": [
        {"name": "SharedListingRepository", "methods": []}]}}}
    USER = {"Listing": {"dataFlow": {"repositories": [
        {"name": "SharedListingRepository", "methods": []}]}}}

    def test_within_one_app_the_shared_name_has_one_owner(self):
        for app in (self.ADMIN, self.USER):
            kind, owners = ownership.classify(
                "SharedListingRepository", app, {}, {"SharedListingRepository"})
            self.assertEqual(ownership.SCREEN_OWNED, kind)
            self.assertEqual(["Listing"], owners)

    def test_mixing_two_apps_invents_a_second_owner(self):
        """The failure, stated as a fact rather than a warning: passing both
        apps at once turns a screen-owned target into an app-owned one."""
        mixed = {f"{app}/{screen}": spec
                 for app, screens in (("admin", self.ADMIN), ("user", self.USER))
                 for screen, spec in screens.items()}
        kind, owners = ownership.classify(
            "SharedListingRepository", mixed, {}, {"SharedListingRepository"})
        self.assertEqual(ownership.APP_OWNED, kind)
        self.assertEqual(2, len(owners))


if __name__ == "__main__":
    unittest.main()
