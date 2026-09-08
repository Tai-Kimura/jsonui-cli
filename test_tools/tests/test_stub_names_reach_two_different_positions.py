"""A declared case name lands in an identifier on ios/android and in a string
literal on web, and the two need opposite treatment.

The reported defect was one half of that: `generate unit-stubs` put natural-
language names straight into `func test_{name}()`, so 575 of one face's 589
declared names produced Swift that does not parse. The reporter classified the
three platforms correctly -- "ios/android are identifiers, web is a string
literal" -- and the second half hid INSIDE that correct classification: the web
literal is SINGLE-quoted and nothing escaped it, and the intent was run through
`.replace('"', "'")`, which is right for the two double-quoted platforms and
exactly backwards here. So a "safe" platform emitted unparseable JavaScript for
any name carrying an apostrophe, and the sanitiser MANUFACTURED that break out
of a double quote the literal would have accepted.

⇒ "it is a string literal, therefore safe" is not a claim until the literal's
QUOTE is named.

Every rule below was measured against a real compiler, never read off a
specification, and the two places where the specification and the compiler
disagree are pinned here so that "fixing" them back reddens an arm:

    swiftc (Xcode 26.5)     240 code points, one file each -- all printable
                            ASCII plus both sides of every range boundary.
                            `$` is legal though the grammar omits it; U+FFFD
                            is rejected though the grammar includes it.
    kotlinc 2.1.20/JDK 17   one name per file, with `@Test` and `fail()`
                            removed so an unresolved reference could not be
                            mistaken for an illegal identifier -- the same
                            separation `swiftc -parse` gives.
    node --check            the emitted web file, parsed.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jsonui_test_cli.unit_contracts import (  # noqa: E402
    IDENTIFIER_PLATFORMS,
    UnitCase,
    UnitContractError,
    _as_declared,
    check_unit_contracts,
    _web_test_names,
    identifier_problem,
    stub_text,
)


def _case(name: str, intent: str = "", platform: str = "ios") -> UnitCase:
    return UnitCase(screen="S", target="Foo", name=name,
                    platforms=(platform,), intent=intent)


class SwiftIdentifierRule(unittest.TestCase):
    """What `func test_{name}()` accepts, per swiftc."""

    def test_a_japanese_name_is_legal(self):
        # The reporter's control: 14 of their 589 names parse, and all 14 are
        # Japanese. A rule of "ASCII only" would reject every one of them.
        self.assertIsNone(identifier_problem("ios", "名前を返す"))

    def test_an_ascii_name_with_a_space_is_not(self):
        why = identifier_problem("ios", "returns a name")
        self.assertIsNotNone(why)
        # The offending character is named. A refusal that does not say which
        # character sends the author looking at the script.
        self.assertIn("' '", why)

    def test_the_prefix_means_a_name_may_open_with_a_digit(self):
        # `IOS_TEST_PREFIX` puts `t` first, so only the CHARACTER rule applies.
        # A check written against `identifier-head` would refuse this.
        self.assertIsNone(identifier_problem("ios", "1を返す"))

    def test_an_emoji_is_legal(self):
        # U+1F389 sits in U+10000-U+1FFFD. Measured: it compiles.
        self.assertIsNone(identifier_problem("ios", "🎉を返す"))

    def test_dollar_is_legal_although_the_published_grammar_omits_it(self):
        # ⚠️ Reconciliation arm. swiftc takes `func test_a$b()` to an object
        # file (-parse, -typecheck and -emit-object all exit 0). Restoring the
        # grammar's table here would reject a name Swift accepts -- a false
        # positive, which is the direction this check must never fail in.
        self.assertIsNone(identifier_problem("ios", "a$b"))

    def test_the_replacement_character_is_illegal_although_the_grammar_ends_there(self):
        # ⚠️ The other reconciliation, in the opposite direction. The grammar's
        # last range ends at U+FFFD; swiftc answers "invalid character in
        # source file". Trusting the grammar would let an uncompilable file be
        # written, which is the reported defect itself.
        self.assertIsNotNone(identifier_problem("ios", "a�b"))


class KotlinIdentifierRule(unittest.TestCase):
    """What ``fun `{name}`()`` accepts, per kotlinc."""

    #: Measured one character at a time. Everything NOT here compiled.
    ILLEGAL = "/.;[]<>:\\`\n\r"

    def test_every_measured_illegal_character_is_refused(self):
        for ch in self.ILLEGAL:
            with self.subTest(char=repr(ch)):
                self.assertIsNotNone(identifier_problem("android", f"a{ch}b"))

    def test_android_accepts_what_ios_refuses(self):
        # The asymmetry is the point: backticks take spaces and punctuation, so
        # a rule shared between the two platforms would reject names android
        # compiles. All four of these were measured green on kotlinc and red on
        # swiftc.
        for name in ("returns a name", "名前を 返す", "名前を返す。括弧(あり)",
                     "%s は invoke と settle を持つ"):
            with self.subTest(name=name):
                self.assertIsNone(identifier_problem("android", name))
                self.assertIsNotNone(identifier_problem("ios", name))

    def test_punctuation_outside_the_measured_set_is_accepted(self):
        # A guard against widening the set by reading rather than measuring:
        # every one of these compiled.
        for ch in "@$#%^&*()-+=|~'\"?!,{} \t":
            with self.subTest(char=repr(ch)):
                self.assertIsNone(identifier_problem("android", f"a{ch}b"))


class WebIsNotAnIdentifierPosition(unittest.TestCase):
    """The name is data there, so it is escaped rather than refused."""

    def test_no_name_is_ever_refused_for_web(self):
        for name in ("a/b", "it's fine", 'says "hello"', "returns a name"):
            with self.subTest(name=name):
                self.assertIsNone(identifier_problem("web", name))

    def test_web_is_not_in_the_identifier_platforms(self):
        self.assertEqual(("ios", "android"), IDENTIFIER_PLATFORMS)

    def test_an_apostrophe_in_the_name_is_escaped(self):
        text = stub_text("web", "Foo", [_case("it's fine", platform="web")])
        # Measured with `node --check`: the unescaped form was
        # "SyntaxError: missing ) after argument list".
        self.assertIn(r"it('it\'s fine'", text)

    def test_the_escape_round_trips_through_the_scanner(self):
        # ⭐ This is what makes escaping the NAME safe where sanitising it
        # would not be. `--check` compares declared against scanned verbatim,
        # so a transformation without an inverse would make a run write a file
        # whose every case is `missing` and `undeclared` at once. The inverse
        # already exists, and this arm is what says so.
        for name in ("it's fine", 'says "hello"', "a\\b", "returns a name"):
            with self.subTest(name=name):
                text = stub_text("web", "Foo", [_case(name, platform="web")])
                found, unreadable = _web_test_names(text)
                self.assertEqual(0, unreadable)
                self.assertEqual([name], [_as_declared("web", f) for f in found])


class TheScannerUnescapesOnceNotTwice(unittest.TestCase):
    """Inversion arm for a defect the round trip above uncovered."""

    def test_as_declared_does_not_unescape_what_the_reader_already_read(self):
        # ⚠️ `_read_js_literal` resolves the escapes; `_as_declared` used to do
        # it a SECOND time. `a\b` came back as a backspace and stood in both
        # the missing and the undeclared column of one run. Invisible until a
        # name carries a backslash, because the escape both halves actually
        # meet is `\'`, and unescaping that twice changes nothing -- so the
        # arm has to use a backslash, not an apostrophe, to be an arm at all.
        self.assertEqual("a\\b", _as_declared("web", "a\\b"))

    def test_it_still_strips(self):
        # The behaviour `_as_declared` exists for, kept separate so removing
        # the unescape cannot quietly remove this too.
        self.assertEqual("says", _as_declared("web", "says "))


class TheIntentIsAStringLiteralOnEveryPlatform(unittest.TestCase):
    """And the three literals do not take the same escape."""

    def test_web_no_longer_turns_a_double_quote_into_the_closing_quote(self):
        # ⚠️ Inversion arm for a REMOVED behaviour. `.replace('"', "'")` used
        # to run on all three platforms; on web it converted a character the
        # single-quoted literal accepts into the one that ends it, and
        # `node --check` reported "SyntaxError". Re-introducing that shared
        # replace reddens exactly this.
        text = stub_text("web", "Foo", [_case("n", intent='has "quotes"',
                                              platform="web")])
        self.assertIn('has "quotes"', text)
        self.assertNotIn("has 'quotes'", text)

    def test_kotlin_escapes_the_string_template_marker(self):
        # Measured: an intent reading `costs $total yen` and one reading
        # `${x}` are both compile errors, because `$` opens a template. `"`
        # and `\b` are not -- so the old replace was escaping the character
        # that was not the problem.
        text = stub_text("android", "Foo",
                         [_case("n", intent="costs $total yen",
                                platform="android")], package="p")
        self.assertIn(r"costs \$total yen", text)

    def test_swift_escapes_rather_than_downgrades_a_double_quote(self):
        text = stub_text("ios", "Foo",
                         [_case("n", intent='has "quotes"')], module="M")
        self.assertIn(r'has \"quotes\"', text)
        self.assertNotIn("has 'quotes'", text)

    def test_a_backslash_in_the_intent_does_not_become_an_escape_sequence(self):
        # `swiftc`: "invalid escape sequence in literal". The name is validated
        # and so can never carry one; the intent is free text and can.
        text = stub_text("ios", "Foo", [_case("n", intent="a\\b")], module="M")
        self.assertIn(r"a\\b", text)


class GenerationRefusesBeforeItWrites(unittest.TestCase):
    """The same standing as the missing module and package."""

    def test_an_illegal_ios_name_raises(self):
        with self.assertRaises(UnitContractError) as caught:
            stub_text("ios", "Foo", [_case("returns a name")], module="M")
        self.assertIn("returns a name", str(caught.exception))

    def test_the_same_name_is_written_for_android(self):
        # Not a copy of the arm above: it fails if the refusal is hoisted to
        # something platform-independent, which is the shape a shared rule
        # would take.
        text = stub_text("android", "Foo",
                         [_case("returns a name", platform="android")],
                         package="p")
        self.assertIn("fun `returns a name`()", text)


class TheCheckReportsItWithoutGenerating(unittest.TestCase):
    """`--check` has to say it, not only `generate`.

    ⚠️ The check is in `check_unit_contracts`, not in `_cases_of` where a
    reader looks for it, and that is forced: `_cases_of` reads one spec and
    has no project platform list, while the dangerous declaration is the one
    that OMITS `platforms` and therefore reaches all of them.
    """

    def _project(self, tmp: Path, platforms: dict, case: dict) -> Path:
        (tmp / "docs" / "screens" / "json").mkdir(parents=True)
        (tmp / "jui.config.json").write_text(json.dumps({
            "spec_directory": "docs/screens/json",
            "platforms": platforms,
        }))
        for p in platforms:
            (tmp / "tests" / p).mkdir(parents=True, exist_ok=True)
        (tmp / "docs" / "screens" / "json" / "home.spec.json").write_text(json.dumps({
            "type": "screen_spec", "metadata": {"name": "Home"},
            "unitContracts": [{"target": "HomeViewModel", "cases": [case]}],
        }))
        return tmp

    def test_an_omitted_platforms_list_is_judged_against_every_platform(self):
        with tempfile.TemporaryDirectory() as d:
            root = self._project(
                Path(d),
                {"ios": {"unitTestsDir": "tests/ios"},
                 "web": {"unitTestsDir": "tests/web"}},
                {"name": "returns a name", "intent": "x"},
            )
            report = check_unit_contracts(root)
            # The denominator first: an empty read would satisfy every
            # assertion below by declaring nothing.
            self.assertEqual(1, len(report.cases))
            self.assertFalse(report.ok)
            hits = [p for p in report.problems if "returns a name" in p]
            self.assertEqual(1, len(hits), report.problems)
            # ios only -- web takes it as data.
            self.assertIn("ios", hits[0])

    def test_declaring_platforms_without_ios_is_the_documented_way_out(self):
        with tempfile.TemporaryDirectory() as d:
            root = self._project(
                Path(d),
                {"ios": {"unitTestsDir": "tests/ios"},
                 "web": {"unitTestsDir": "tests/web"}},
                {"name": "returns a name", "intent": "x", "platforms": ["web"]},
            )
            report = check_unit_contracts(root)
            # ⚠️ Same reason, and it matters more here: this arm asserts an
            # ABSENCE, which a spec that was never read also produces.
            self.assertEqual(1, len(report.cases))
            self.assertEqual([], [p for p in report.problems
                                  if "returns a name" in p])


class GenerationStopsBeforeTheFirstFile(unittest.TestCase):
    """A refused run leaves no half-written tree behind."""

    def test_nothing_is_written_and_every_offender_is_named(self):
        from jsonui_test_cli.unit_contracts import write_stubs

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "docs" / "screens" / "json").mkdir(parents=True)
            (root / "tests" / "ios").mkdir(parents=True)
            (root / "jui.config.json").write_text(json.dumps({
                "spec_directory": "docs/screens/json",
                "platforms": {"ios": {"unitTestsDir": "tests/ios",
                                      "testModule": "M"}},
            }))
            (root / "docs" / "screens" / "json" / "home.spec.json").write_text(
                json.dumps({
                    "type": "screen_spec", "metadata": {"name": "Home"},
                    "unitContracts": [{"target": "HomeViewModel", "cases": [
                        {"name": "returns a name", "intent": "x"},
                        {"name": "名前を返す", "intent": "y"},
                        {"name": "raises on empty input", "intent": "z"},
                    ]}],
                }))
            report = check_unit_contracts(root)
            self.assertEqual(3, len(report.cases))
            with self.assertRaises(UnitContractError) as caught:
                write_stubs(root, report)
            message = str(caught.exception)
            # ⚠️ Both offenders, not the first: a run that stops at name one
            # sends the author back once per name for a fault they could have
            # been shown all of.
            self.assertIn("returns a name", message)
            self.assertIn("raises on empty input", message)
            self.assertNotIn("名前を返す", message)
            # And the file the legal case would have gone into does not exist:
            # `stub_text` alone would have refused only AFTER the loop had
            # written the earlier targets.
            self.assertEqual([], list((root / "tests" / "ios").iterdir()))


if __name__ == "__main__":
    unittest.main()
