"""Two declaration keys the diagram reads from jui.config.json, and the canon
lines that say so.

⚠️ WHY. From 2026-09-09 the canon described per-face aliases by SHAPE only:
no key, no reader — measured 2026-09-10, zero faces could declare one, and
the numbers the canon recorded ("prefix Web resolves 50 of 93") described a
mechanism nobody could switch on. A declaration site is a key AND a reader
AND a test that fails when either goes missing.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from jui_cli.core.project_config import (
    declared_app_owned_screens,
    declared_transition_aliases,
)
from jui_cli.core.screen_identity import (
    ALIAS_POSITIONS,
    TRANSITION_ALIASES_KEY,
    app_owned_transitions,
    classify_destination,
    load_canon,
    parse_app_owned_screens,
    parse_transition_aliases,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


class TransitionAliasesAreDeclaredUnderSpec(unittest.TestCase):
    def test_the_raw_list_is_read_from_spec_transitionAliases(self):
        cfg = {"spec": {"transitionAliases": [{"position": "suffix", "affix": "画面"}]}}
        self.assertEqual(declared_transition_aliases(cfg), [{"position": "suffix", "affix": "画面"}])
        self.assertEqual(TRANSITION_ALIASES_KEY, ("spec", "transitionAliases"))

    def test_nothing_declared_is_an_empty_list_not_none(self):
        self.assertEqual(declared_transition_aliases({}), [])
        self.assertEqual(declared_transition_aliases(None), [])
        self.assertEqual(declared_transition_aliases({"spec": {"transitionAliases": "Web"}}), [])

    def test_parse_yields_position_affix_pairs_in_order(self):
        pairs = parse_transition_aliases([{"position": "prefix", "affix": "Web"},
                                          {"position": "suffix", "affix": "View"}])
        self.assertEqual(pairs, [("prefix", "Web"), ("suffix", "View")])

    def test_a_wrong_position_is_refused_naming_the_entry(self):
        with self.assertRaises(ValueError) as ctx:
            parse_transition_aliases([{"position": "infix", "affix": "x"}])
        self.assertIn("[0].position", str(ctx.exception))
        self.assertIn("infix", str(ctx.exception))

    def test_a_missing_affix_is_refused(self):
        with self.assertRaises(ValueError):
            parse_transition_aliases([{"position": "suffix"}])
        with self.assertRaises(ValueError):
            parse_transition_aliases([{"position": "suffix", "affix": ""}])

    def test_a_non_object_entry_is_refused(self):
        with self.assertRaises(ValueError):
            parse_transition_aliases(["suffix:View"])

    def test_the_parsed_pairs_drive_the_classifier(self):
        pairs = parse_transition_aliases([{"position": "suffix", "affix": "View"}])
        self.assertEqual(classify_destination("LicensesView", ("licenses",), aliases=pairs).kind, "screen")
        self.assertEqual(classify_destination("LicensesView", ("licenses",)).kind, "unknown")


class AppOwnedScreensCarryTransitions(unittest.TestCase):
    def test_the_object_form_carries_transitions(self):
        parsed = parse_app_owned_screens([
            "tokushoho",
            {"id": "company", "group": "static", "transitions": ["Licenses", "Tokushoho"]},
        ])
        self.assertEqual(parsed[0].transitions, ())
        self.assertEqual(parsed[1].transitions, ("Licenses", "Tokushoho"))

    def test_app_owned_transitions_maps_only_declarers(self):
        declared = ["tokushoho", {"id": "company", "transitions": ["Licenses"]}, {"id": "licenses", "transitions": []}]
        self.assertEqual(app_owned_transitions(declared), {"company": ["Licenses"]})

    def test_a_single_string_and_blanks(self):
        parsed = parse_app_owned_screens([{"id": "company", "transitions": "Licenses"},
                                          {"id": "x", "transitions": [" ", 3, "Y"]}])
        self.assertEqual(parsed[0].transitions, ("Licenses",))
        self.assertEqual(parsed[1].transitions, ("Y",))

    def test_the_raw_list_comes_from_test_appOwnedScreens(self):
        cfg = {"test": {"appOwnedScreens": [{"id": "company", "transitions": ["Licenses"]}]}}
        self.assertEqual(app_owned_transitions(declared_app_owned_screens(cfg)), {"company": ["Licenses"]})


class TheCanonNamesTheKeysTheCodeReads(unittest.TestCase):
    def setUp(self):
        self.canon = load_canon(REPO_ROOT / "shared" / "core")

    def test_the_alias_declaration_key(self):
        decl = self.canon["diagram"]["specTransitions"]["normalization"]["aliases"]["declaration"]
        self.assertEqual(decl["location"], "jui.config.json")
        self.assertEqual(decl["key"], ".".join(TRANSITION_ALIASES_KEY))
        for entry in decl["example"]:
            self.assertIn(entry["position"], ALIAS_POSITIONS)
        # The example must parse under the reader it names.
        self.assertEqual(len(parse_transition_aliases(decl["example"])), len(decl["example"]))

    def test_the_app_owned_transitions_key(self):
        decl = self.canon["appOwnedScreens"]["declaration"]
        self.assertIn("transitions", decl["shape"])
        self.assertIn("transitions", decl)
        parsed = parse_app_owned_screens(decl["example"])
        self.assertTrue(any(p.transitions for p in parsed), "the example must exercise the key")

    def test_the_diagram_declares_one_source_and_the_check(self):
        diagram = self.canon["diagram"]
        self.assertIn("ONE source", diagram["nodeSource"])
        check = diagram["flowTestCheck"]
        self.assertIn("back", check["exempt"].lower())
        self.assertIn("ABSENT", diagram["specTransitions"]["unresolvedReporting"]["treatment"])
        self.assertIn("exits 1", check["severity"])

    def test_unknown_is_declared_absent(self):
        kinds = {v["kind"]: v for v in self.canon["diagram"]["specTransitions"]["kinds"]["values"]}
        self.assertIn("ABSENT", kinds["unknown"]["drawn"])
        self.assertIn("absent", kinds["route"]["drawn"])


if __name__ == "__main__":
    unittest.main()
