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
    destination_parts,
    normalize_id,
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


class ADestinationCanNameSeveralScreens(unittest.TestCase):
    def test_parts_are_the_classifiers_split(self):
        self.assertEqual(destination_parts("Chat or Mypage（source依存。戻る）"), ["Chat", "Mypage"])
        self.assertEqual(destination_parts("A / B、C"), ["A", "B", "C"])

    def test_a_single_destination_has_no_parts(self):
        self.assertEqual(destination_parts("Ledger（Next.js router.push）"), [])
        self.assertEqual(destination_parts(""), [])

    def test_the_classifier_alone_returns_the_first_screen(self):
        # the reason the diagram asks for the parts
        t = classify_destination("Chat or Mypage（戻る）", ("chat", "mypage"))
        self.assertEqual((t.kind, t.screen_id), ("screen", "chat"))


class ExternalSpellingsReadOffTheSecondCorpus(unittest.TestCase):
    """2026-09-10: three of a face's unresolved destinations said 'external'
    in English and were filed as unknown."""

    def test_each(self):
        for raw in ("External Browser（商品URL）", "Browser (URL)", "External Map App（バー座標）",
                    "地図アプリ（バー座標）", "電話アプリ（tel:）", "メールアプリ"):
            with self.subTest(raw=raw):
                self.assertEqual(classify_destination(raw, ("chat",)).kind, "external")

    def test_a_screen_named_browser_still_wins(self):
        self.assertEqual(classify_destination("Browser (URL)", ("browser",)).kind, "screen")


class ABareNoneIsANone(unittest.TestCase):
    """The notice named なし as the word; the code had only 遷移なし."""

    def test_bare_and_with_parenthetical(self):
        for raw in ("なし", "なし（アラート表示）", "なし (sheet)"):
            with self.subTest(raw=raw):
                self.assertEqual(classify_destination(raw, ("chat",)).kind, "none")

    def test_prose_containing_nashi_is_not_swallowed(self):
        self.assertEqual(classify_destination("ログインなしで閲覧", ("chat",)).kind, "unknown")
        self.assertEqual(classify_destination("Chat（ログインなし）", ("chat",)).kind, "screen")


class TheClassifierIsDeterministicUnderCollidingIds(unittest.TestCase):
    """`known = {_norm_id(k): k for k in known_ids}` let the LAST id win, and
    a set's order follows PYTHONHASHSEED. Sorted, first wins — the same
    answer for the same input; a caller who knows the ids' provenance
    collapses them before calling (spec_graph does)."""

    def test_same_answer_whatever_the_order(self):
        for ids in (["forgotpassword", "forgot_password"], ["forgot_password", "forgotpassword"],
                    {"forgotpassword", "forgot_password"}):
            with self.subTest(ids=list(ids)):
                self.assertEqual(classify_destination("ForgotPassword", ids).screen_id, "forgot_password")

    def test_normalize_id_is_the_classifiers_key(self):
        self.assertEqual(normalize_id("Forgot_Password"), normalize_id("forgot-password"))
        self.assertEqual(normalize_id("Forgot Password"), "forgotpassword")
