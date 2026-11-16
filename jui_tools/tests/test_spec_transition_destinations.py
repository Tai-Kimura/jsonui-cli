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
import re
import unittest
from pathlib import Path

from jui_cli.core.screen_identity import (
    ALIAS_POSITIONS,
    DESTINATION_KINDS,
    _NONE,
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


class TheAliasCarriesAPositionNotJustAString(unittest.TestCase):
    """Two affixes were measured and they sit at DIFFERENT ends.

        prefix ``Web``   50 of one face's 93 destinations
        suffix ``画面``   10 (9 distinct spellings) of another face's 69

    ⚠️ SET EQUALITY AND ONE SPECIMEN PER POSITION ARE NOT ENOUGH. An
    implementation that ignores the position and does `affix in text` passes
    both: declare ``Web`` as a suffix and it still resolves. The only arm that
    pins the position as a QUANTITY is the swap — and the swap has to be
    fired where candidates exist, or its zero is self-evident.

    🚫 AND THE SWAP NEEDS ITS OWN POSITIVE HALF, IN THE SAME RUN. A wrong
    position resolving nothing is also what a completely broken alias
    mechanism looks like. So each swap arm below asserts the correct position
    still works on the same input.
    """

    PREFIXED = "WebLedger（Next.js router.push）"      # prefix face's shape
    SUFFIXED = "ProductDetail画面"                      # suffix face's shape
    IDS = KNOWN + ("product_detail",)

    def classify(self, raw, aliases):
        return classify_destination(raw, self.IDS, aliases=aliases)

    def test_each_declared_position_resolves_its_own_shape(self):
        self.assertEqual(self.classify(self.PREFIXED, (("prefix", "Web"),)).kind,
                         "screen")
        self.assertEqual(self.classify(self.SUFFIXED, (("suffix", "画面"),)).kind,
                         "screen")

    def test_a_prefix_declared_as_a_suffix_does_not_fire(self):
        swapped = self.classify(self.PREFIXED, (("suffix", "Web"),))
        correct = self.classify(self.PREFIXED, (("prefix", "Web"),))
        self.assertEqual(swapped.kind, "unknown",
                         "the position was ignored — `affix in text` would do this")
        self.assertEqual(correct.kind, "screen",
                         "the positive half: the mechanism itself still works, "
                         "so the zero above is about position and not about a "
                         "broken alias path")

    def test_a_suffix_declared_as_a_prefix_does_not_fire(self):
        swapped = self.classify(self.SUFFIXED, (("prefix", "画面"),))
        correct = self.classify(self.SUFFIXED, (("suffix", "画面"),))
        self.assertEqual(swapped.kind, "unknown")
        self.assertEqual(correct.kind, "screen")

    def test_without_any_declaration_neither_resolves(self):
        self.assertEqual(self.classify(self.PREFIXED, ()).kind, "unknown")
        self.assertEqual(self.classify(self.SUFFIXED, ()).kind, "unknown")

    def test_the_wrong_affix_control(self):
        """Kept from the measurement session: a wrong affix resolves nothing.

        Without it, an implementation that strips ANY leading capitalised word
        passes the arms above and quietly rewrites every face's ids.
        """
        self.assertEqual(self.classify(self.PREFIXED, (("prefix", "Zzz"),)).kind,
                         "unknown")
        self.assertEqual(self.classify(self.SUFFIXED, (("suffix", "画面X"),)).kind,
                         "unknown")

    def test_the_report_names_the_position_that_fired(self):
        why = self.classify(self.SUFFIXED, (("suffix", "画面"),)).why
        self.assertIn("suffix", why)
        self.assertIn("画面", why)

    def test_an_unknown_position_is_refused_rather_than_ignored(self):
        # Silently doing nothing would look exactly like a face that declared
        # nothing, which is the failure this whole class is about.
        with self.assertRaises(ValueError):
            self.classify(self.SUFFIXED, (("infix", "画面"),))

    def test_the_alias_does_not_claim_a_plain_match(self):
        t = classify_destination("Ledger", self.IDS, aliases=(("prefix", "Web"),))
        self.assertEqual(t.why, "matched `Ledger`")


class TheParentheticalStripperCounts(unittest.TestCase):
    """Nesting, because the corpus nests and the first version did not.

    `Name (a=b / onNavigate(Screen.X))` — a transition explaining its own
    arguments. A flat `\\(...\\)` match consumes up to the INNER close and
    leaves the OUTER one, so the candidate becomes `Name )` and matches
    nothing. The value reads like prose the classifier could not handle; it
    was prose the classifier had damaged.

    ⚠️ THE ONE-LEVEL CASE PASSES UNDER BOTH IMPLEMENTATIONS, so an arm that
    only tries `Name (a / b)` proves nothing about nesting. Both are here, and
    the flat one is the control that says the stripper still works at all.
    """

    IDS = ("product_scanner", "chat")

    def k(self, raw):
        return classify_destination(raw, self.IDS).kind

    def test_one_level_still_works(self):
        self.assertEqual(self.k("ProductScanner (push, uuid)"), "screen")

    def test_a_nested_parenthetical_does_not_leave_a_stray_closer(self):
        self.assertEqual(
            self.k("ProductScanner (navigateToScreen=.x / onNavigate(Screen.Y))"),
            "screen", "the outer `)` survived into the candidate")

    def test_full_width_nesting_too(self):
        self.assertEqual(self.k("ProductScanner（外（内）外）"), "screen")

    def test_an_unbalanced_closer_is_dropped_not_kept(self):
        # `Name )` is the exact residue the flat version produced. Keeping a
        # stray closer would reintroduce the bug from the other direction.
        self.assertEqual(self.k("ProductScanner )"), "screen")

    def test_text_after_the_parenthetical_survives(self):
        # The stripper removes the spans, not the tail — otherwise
        # `A or B（note）` would lose B.
        t = classify_destination("Nope（note） or Chat", self.IDS)
        self.assertEqual(t.kind, "screen")
        self.assertEqual(t.screen_id, "chat")


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
        self.assertIn("aliases", spec["normalization"])
        self.assertIn("rule", spec["unresolvedReporting"])

    def test_the_canon_and_the_mechanism_agree_on_the_alias_positions(self):
        """BOTH directions, and then each one is fired.

        Set equality alone lets the canon grow a position the code ignores,
        or the code grow one the canon never declared — and one-directional
        containment is silent about exactly one of those. Firing each declared
        position is the third leg: agreeing sets whose members do nothing
        would still pass.
        """
        canon = load_canon(REPO_ROOT / "shared" / "core")
        declared = canon["diagram"]["specTransitions"]["normalization"]["aliases"]
        self.assertEqual(tuple(declared["positions"]), ALIAS_POSITIONS)
        for position in declared["positions"]:
            with self.subTest(position=position):
                affix, raw = {"prefix": ("Web", "WebLedger"),
                              "suffix": ("画面", "ProductDetail画面")}[position]
                t = classify_destination(raw, KNOWN + ("product_detail",),
                                         aliases=((position, affix),))
                self.assertEqual(t.kind, "screen",
                                 f"the canon declares {position} and it resolves nothing")

    def test_the_canon_says_the_positions_are_not_exhaustive(self):
        canon = load_canon(REPO_ROOT / "shared" / "core")
        note = canon["diagram"]["specTransitions"]["normalization"]["aliases"]["positionsNote"]
        self.assertIn("NOT covered", note,
                      "the canon reads as `these are all the positions`, which "
                      "turns the next counterexample into an exception")

    def test_the_canon_separates_what_failed_to_measure_from_what_did(self):
        # A withdrawn reason survives a correct decision unless the record
        # keeps the two claims apart.
        scoping = (load_canon(REPO_ROOT / "shared" / "core")
                   ["diagram"]["specTransitions"]["normalization"]["aliases"]
                   ["scopingIsARiskChoiceNotAMeasuredOne"])
        self.assertIn("whatWasMeasuredAndFailed", scoping)
        self.assertIn("whatCanBeMeasured", scoping)
        self.assertIn("web_view", scoping["whatCanBeMeasured"])

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


class TheNoneMarkerCarriesEnglishToo(unittest.TestCase):
    """`back` and `external` were bilingual; `none` was not, and that was all.

    A face writing "no transition" matched no marker and was reported as
    `unknown` — not because the order was wrong or the anchor was wrong, but
    because the alternatives were Japanese. `_BACK` already carries
    `previous screen` and `_EXTERNAL` already carries `External Browser`;
    nothing about the `none` kind is more Japanese than those.

    ⚠️ THIS ARM IS PLANTED AND SAYS SO. Measured 2026-09-11 over every
    ``transitions[].destination`` on this machine — 852 values, 459 distinct,
    6 faces — exactly 0 are matched by the English half. The widening changes
    no face's diagram today. An unexercised hazard is still a hazard; it just
    cannot be found by sampling, which is the same reason
    ``classify_destination``'s order arm is planted.
    """

    ENGLISH = ["Same screen", "same page (query param only)",
               "No transition", "no navigation", "No screen change",
               "does not navigate", "Does not transition",
               "stays on the current screen", "remains on this screen",
               "in-page（drawer）", "In page scroll",
               "Tab switch (SPA)", "switches tabs", "switch tab",
               "None", "none（SPA state change）"]

    def test_every_english_spelling_is_a_none(self):
        for raw in self.ENGLISH:
            with self.subTest(raw=raw):
                self.assertEqual(kind(raw), "none")

    def test_the_case_folding_is_what_carries_half_of_them(self):
        """`_EXTERNAL` is case-SENSITIVE and this one is not, so the three
        markers no longer share one answer. Pin the difference, or a later
        tidy-up that "makes them consistent" drops the capitalised spellings
        without a single arm going red."""
        for raw in ["NO TRANSITION", "Same Screen", "TAB SWITCH"]:
            with self.subTest(raw=raw):
                self.assertEqual(kind(raw), "none")

    def test_the_japanese_spellings_still_classify(self):
        """The control from inside the window: real values this marker
        matched BEFORE the English half was added. A widening that quietly
        broke the alternation would otherwise show up only as a face's
        diagram losing nodes."""
        for raw in ["遷移なし", "同画面内のタブ切替（SPA内遷移）",
                    "現在の画面に留まる（エラーメッセージ表示）",
                    "画面内（ペイン切替。push なし）", "なし",
                    "なし（送信のみ）"]:
            with self.subTest(raw=raw):
                self.assertEqual(kind(raw), "none")

    def test_a_resolvable_screen_is_still_a_screen(self):
        """The order control, in English this time. `_NONE` is unanchored, so
        a real transition whose parenthetical explains that the push happens
        in place would be filed `none` if the markers ran before the ids."""
        t = classify_destination("Chat（stays on the same screen until sent）",
                                 KNOWN)
        self.assertEqual(t.kind, "screen",
                         "the English `none` vocabulary outran screen resolution")
        self.assertEqual(t.screen_id, "chat")

    def test_the_bare_none_is_anchored(self):
        r"""`\Anone` mirrors `\Aなし`. Unanchored it would swallow any prose
        with the word in it — and because the markers run LAST, what it
        swallows is an `unknown`: a destination the unresolved report names,
        turned into a `none` the report is silent about."""
        for raw in ["Login none required", "Browse with none of the filters"]:
            with self.subTest(raw=raw):
                self.assertEqual(kind(raw), "unknown")

    def test_the_corpuss_own_near_misses_stay_unknown(self):
        """Decoys taken from the window, not invented. One face's spec pages
        write these; both carry `tab`, and `tab` alone is not a declaration
        that nothing happens — only `tab switch` is."""
        for raw in ["Target screen or tab", "Target spec screen or tab",
                    "Checkout（no coupon）", "Notification"]:
            with self.subTest(raw=raw):
                self.assertEqual(kind(raw), "unknown")


class TheEnglishNoneVocabularyIsMultiWordOrAnchored(unittest.TestCase):
    r"""A rule about the NEXT alternative, not about the ones there now.

    The Japanese half can afford single words — 同画面 is not a word that
    turns up inside unrelated prose. `none`, `back`, `stay`, `tab` are. The
    protection is that every English alternative either starts at `\A` or
    cannot match a string with no separator in it, and that is checked by
    EXECUTION rather than by reading the source: a syntactic "contains a
    space" test passes `(?:stay|stays on)`, and this one does not.
    """

    #: Probe tokens, derived from the pattern itself rather than listed, plus
    #: the words a reader would expect to be dangerous.
    EXTRA = ("none", "back", "stay", "stays", "remain", "remains", "same",
             "screen", "page", "tab", "tabs", "switch", "switches",
             "navigate", "transition", "change", "in", "on", "no", "not")

    @staticmethod
    def _top_level_alternatives(pattern: str) -> list[str]:
        r"""Split on `|` at depth 0 only.

        Depth-counted rather than split, for the same reason
        ``_strip_parentheticals`` is: `(?=\s*[（(]|\s*\Z)` and
        `(?:navigate|transition)` both carry a `|` that is not a top-level
        alternation, and a naive split tears them in half — producing
        fragments that are not regexes and an arm that passes by accident.
        """
        out, buf, depth, in_class, escaped = [], [], 0, False, False
        for ch in pattern:
            if escaped:
                buf.append(ch)
                escaped = False
                continue
            if ch == "\\":
                buf.append(ch)
                escaped = True
                continue
            if in_class:
                buf.append(ch)
                if ch == "]":
                    in_class = False
                continue
            if ch == "[":
                in_class = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "|" and depth == 0:
                out.append("".join(buf))
                buf = []
                continue
            buf.append(ch)
        out.append("".join(buf))
        return out

    def setUp(self):
        self.alts = self._top_level_alternatives(_NONE.pattern)

    def test_the_splitter_did_not_tear_a_group(self):
        """The control on the control. Every fragment must still compile, and
        the count must be plausible — a splitter that returned the whole
        pattern as one alternative would make every assertion below vacuous.
        """
        for alt in self.alts:
            with self.subTest(alt=alt):
                re.compile(alt)
        self.assertGreaterEqual(len(self.alts), 8, self.alts)
        self.assertIn("同画面", self.alts)
        self.assertTrue(any("does not" in a for a in self.alts), self.alts)

    def test_no_unanchored_english_alternative_matches_a_bare_word(self):
        tokens = set(re.findall(r"[a-z]+", _NONE.pattern.lower()))
        tokens.update(self.EXTRA)
        for alt in self.alts:
            if alt.startswith("\\A") or not re.search(r"[A-Za-z]", alt):
                continue
            probe = re.compile(alt, re.IGNORECASE)
            for token in sorted(tokens):
                with self.subTest(alt=alt, token=token):
                    self.assertIsNone(
                        probe.search(token),
                        f"the unanchored alternative {alt!r} matches the bare "
                        f"word {token!r}; anchor it with \\A or widen it to a "
                        f"phrase — _NONE runs last, so what it swallows is an "
                        f"`unknown` that stops being reported")

    def test_the_probe_would_catch_a_bare_word(self):
        """The positive control: the check above is only worth having if it
        goes red on the thing it is for."""
        tokens = set(re.findall(r"[a-z]+", _NONE.pattern.lower()))
        tokens.update(self.EXTRA)
        bad = re.compile(r"(?:stay|stays on)", re.IGNORECASE)
        self.assertTrue(any(bad.search(tok) for tok in tokens),
                        "the probe set cannot see a bare-word alternative")


if __name__ == "__main__":
    unittest.main()
