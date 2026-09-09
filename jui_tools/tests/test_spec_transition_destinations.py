"""A spec transition's destination is prose, and the arms are about the order.

``transitions[].destination`` has never been constrained — the validator asks
only that the key exists. Measured 2026-09-09 over 4 faces / 271 destinations,
one column carries six kinds of value: screen ids, router paths, external
targets, positive declarations that nothing happens, stack returns, and prose
nobody has classified yet.

⚠️ THE LOAD-BEARING PART IS THE ORDER, NOT THE PATTERNS. A real transition
explains itself in a parenthetical, and the explanation is full of the words
the other kinds are detected by:

    "Chat or Mypage（source依存。onDismissコールバックで遷移元に戻る）"

Marker-first files that as a ``back``. It would look right — 戻る is there, in
the text. Only the id space can say that ``Chat`` is a screen. So screen
resolution runs BEFORE the markers, and ``TheOrderIsLoadBearing`` is the arm
that fails when someone reorders them for readability.

⚠️ AND THE ALIAS DEFAULTS TO EMPTY. Stripping a leading ``Web`` resolves 50 of
one face's 93 destinations and 0 of the other three faces'. A rewrite that
helps exactly one face has to arrive as that face's declaration; as a global
default it silently rewrites everyone's ids. The ``Zzz`` control below is kept
from the measurement session for exactly that reason: it shows the code reads
the prefix it was given rather than merely stripping something.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from jui_cli.core.screen_identity import (
    DESTINATION_KINDS,
    classify_destination,
    load_canon,
    summarize_destinations,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The face's id space, as a spec author would see it.
KNOWN = ("chat", "mypage", "subscription", "ledger", "b2b_order_detail",
         "admin_login")


def kind(raw, **kw):
    return classify_destination(raw, KNOWN, **kw).kind


class TheOrderIsLoadBearing(unittest.TestCase):
    def test_a_screen_transition_whose_parenthetical_says_back_is_a_screen(self):
        t = classify_destination(
            "Chat or Mypage（source依存。onDismissコールバックで遷移元に戻る）", KNOWN)
        self.assertEqual(t.kind, "screen",
                         "the parenthetical hijacked the classification")
        self.assertEqual(t.screen_id, "chat")

    def test_a_screen_transition_whose_parenthetical_says_router_is_a_screen(self):
        t = classify_destination("Ledger（Next.js router.push）", KNOWN)
        self.assertEqual(t.kind, "screen")

    def test_an_unanchored_marker_in_a_parenthetical_does_not_win(self):
        """PLANTED. The corpus has 0 of these — measured, 4 faces / 271.

        `_BACK` is `\\A`-anchored, so the 戻る case above survives even with
        the markers checked first; the mutation that reordered them left the
        suite green and taught this. `_NONE` and `_EXTERNAL` match anywhere,
        and for those the order is the only thing standing between a real
        transition and a wrong kind. No spec author has written one yet.
        """
        self.assertEqual(
            kind("Chat（画面内のタブから遷移。SPA ではない）"), "screen",
            "an unanchored `none` marker in a parenthetical won")
        self.assertEqual(
            kind("Mypage（https://example.test/help へのリンクも同居）"), "screen",
            "an unanchored `external` marker in a parenthetical won")

    def test_a_real_back_with_no_id_in_it_is_still_back(self):
        # The control for the two above: if screen-first swallowed everything,
        # nothing would ever be classified `back` and they would pass anyway.
        self.assertEqual(kind("Previous screen (pop)"), "back")

    def test_a_route_is_not_torn_apart_by_the_slash_splitter(self):
        # `/` splits "A or B/C" into parts, so a router path has to be
        # recognised before that runs, or "/admin/login" becomes ["admin",
        # "login"] and matches nothing.
        t = classify_destination("/admin/login", KNOWN)
        self.assertEqual(t.kind, "route")
        self.assertIsNone(t.screen_id)


class TheAliasIsOneFacesDeclarationNotAGlobalRule(unittest.TestCase):
    RAW = "WebLedger（Next.js router.push）"

    def test_without_the_declaration_it_does_not_resolve(self):
        self.assertEqual(kind(self.RAW), "unknown",
                         "the prefix was stripped for a face that never "
                         "declared it")

    def test_with_the_declaration_it_resolves(self):
        t = classify_destination(self.RAW, KNOWN, alias_prefixes=("Web",))
        self.assertEqual(t.kind, "screen")
        self.assertEqual(t.screen_id, "ledger")
        self.assertIn("Web", t.why, "the report does not say an alias was used")

    def test_the_zzz_control(self):
        """Kept from the measurement: a wrong prefix must resolve nothing.

        Without it, an implementation that strips ANY leading capitalised word
        passes the arm above and quietly rewrites every face's ids.
        """
        self.assertEqual(kind(self.RAW, alias_prefixes=("Zzz",)), "unknown")

    def test_the_alias_does_not_fire_on_a_value_that_already_resolves(self):
        t = classify_destination("Ledger", KNOWN, alias_prefixes=("Web",))
        self.assertEqual(t.why, "matched `Ledger`",
                         "the alias path claimed a plain match")


class TheMarkerSpellingsAreReadOffACorpus(unittest.TestCase):
    """A marker set is a claim about how people write, and it rots.

    `前画面` was in the pattern and `前の画面` was not. Seven destinations that
    say, in plain Japanese, "go back to the previous screen" were filed as
    `unknown` — not because the order was wrong or the anchor was wrong, but
    because of one の. The corpus found it; no arm would have.
    """

    SPELLINGS = ["前の画面に戻る", "前の画面（dismiss）", "前画面に戻る",
                 "Previous screen (pop)", "dismiss（親に戻る）"]

    def test_every_spelling_the_corpus_uses_is_a_back(self):
        for raw in self.SPELLINGS:
            with self.subTest(raw=raw):
                self.assertEqual(kind(raw), "back")

    def test_the_anchor_still_holds(self):
        """The control. Widening the spellings must not unanchor them, or a
        screen whose parenthetical says 戻る becomes a `back` again."""
        t = classify_destination(
            "Chat（完了後に前の画面に戻る）", KNOWN)
        self.assertEqual(t.kind, "screen",
                         "the widened marker escaped its \\A anchor")


class TheVocabularyIsClosedAndTheCanonSaysSo(unittest.TestCase):
    """The declaration and the code are two implementations of one rule.

    Pinning them to each other is the only thing that keeps the SSoT entry
    from becoming decoration that drifts from what ships.
    """

    def test_every_kind_the_code_returns_is_in_the_closed_set(self):
        for raw in ["Chat", "/admin/login", "https://example.test", "同画面内",
                    "dismiss", "ProductListView (push, itemUuid)", "", "-"]:
            self.assertIn(kind(raw), DESTINATION_KINDS, raw)

    def test_the_canon_declares_exactly_these_kinds(self):
        canon = load_canon(REPO_ROOT / "shared" / "core")
        declared = tuple(
            v["kind"] for v in
            canon["diagram"]["specTransitions"]["kinds"]["values"])
        self.assertEqual(declared, DESTINATION_KINDS)

    def test_the_canon_declares_the_field_the_code_actually_reads(self):
        """Structural, not a substring of the prose.

        The first version asserted `"transitions" in nodeSource`. A mutation
        that prefixed the sentence with "flow test only." left that green —
        the word was still further along in the paragraph. Prose cannot be
        pinned by looking for a word in it; the structure can.
        """
        canon = load_canon(REPO_ROOT / "shared" / "core")
        spec = canon["diagram"]["specTransitions"]
        self.assertEqual(spec["source"], "<screen spec>.transitions[].destination")
        self.assertIn("aliasesNote", spec["normalization"])
        self.assertIn("rule", spec["unresolvedReporting"])

    def test_the_declared_pipeline_matches_the_order_the_code_runs(self):
        canon = load_canon(REPO_ROOT / "shared" / "core")
        steps = canon["diagram"]["specTransitions"]["normalization"]["pipeline"]
        self.assertEqual(len(steps), 3)
        self.assertIn("aliases", steps[-1],
                      "the canon does not put the alias last, but the code does")

    def test_the_canon_file_is_valid_json_on_disk(self):
        path = REPO_ROOT / "shared" / "core" / "screen_identity.json"
        json.loads(path.read_text(encoding="utf-8"))


class UnknownIsCountedAndListed(unittest.TestCase):
    def make(self, *raws, **kw):
        return [classify_destination(r, KNOWN, **kw) for r in raws]

    def test_the_scanned_total_sits_beside_the_count(self):
        lines = summarize_destinations({"bar": self.make("Chat", "mystery")})
        self.assertTrue(any("scanned 2" in l and "unknown=1" in l
                            for l in lines), lines)

    def test_each_unknown_is_listed_with_its_raw_value(self):
        lines = summarize_destinations({"bar": self.make("mystery value")})
        self.assertTrue(any("mystery value" in l for l in lines), lines)

    def test_the_count_follows_its_input(self):
        """The 1->0 arm. A constant would satisfy both assertions above."""
        def unknowns(*raws):
            text = "\n".join(summarize_destinations({"f": self.make(*raws)}))
            return [l for l in text.splitlines() if "unknown=" in l][0]
        self.assertIn("unknown=1", unknowns("Chat", "mystery"))
        self.assertIn("unknown=0", unknowns("Chat", "Mypage"))

    def test_each_face_is_reported_separately(self):
        # Measured rates were 28/61/50/100 percent. Summed, the face that
        # resolves nothing disappears into the average.
        lines = summarize_destinations({
            "good": self.make("Chat", "Mypage"),
            "bad": self.make("mystery", "another"),
        })
        self.assertTrue(any(l.startswith("  bad:") and "unknown=2" in l
                            for l in lines), lines)
        self.assertTrue(any(l.startswith("  good:") and "unknown=0" in l
                            for l in lines), lines)

    def test_no_face_scanned_is_not_zero_unresolved(self):
        lines = summarize_destinations({})
        self.assertTrue(any("no face was scanned" in l for l in lines), lines)


class TheKindsThemselves(unittest.TestCase):
    CASES = {
        "Subscription（iOS: .navigationDestination）": "screen",
        "/admin/two-fa": "route",
        "外部ブラウザ（https://example.test/help）": "external",
        "Phone app (tel://)": "external",
        "同画面内のタブ切替（SPA内遷移）": "none",
        "dismiss（親に戻る）": "back",
        "ProductListView (push, itemUuid)": "unknown",
        "": "unknown",
        "-": "unknown",
    }

    def test_each(self):
        for raw, expected in self.CASES.items():
            with self.subTest(raw=raw):
                self.assertEqual(kind(raw), expected)

    def test_an_empty_destination_is_not_a_declaration_of_none(self):
        # `none` is a POSITIVE declaration that nothing happens. A blank is
        # an author who wrote nothing, and folding them loses that.
        t = classify_destination("", KNOWN)
        self.assertEqual(t.kind, "unknown")
        self.assertIn("no destination declared", t.why)


if __name__ == "__main__":
    unittest.main()
