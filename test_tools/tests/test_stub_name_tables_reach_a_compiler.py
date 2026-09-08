"""The identifier tables answer to a compiler, not to a transcript of one.

`test_stub_names_reach_two_different_positions.py` encodes what swiftc and
kotlinc accept, and every rule in it WAS measured against a real compiler.
But the measurement happened once, into a Python table, and the arms compare
against the table. Counted on both tips of 1.8.52: files under a `tests/` or
`spec/` path that invoke a compiler AND mention stub emission -- zero, with
36 runner-invoking files and 4 stub-surface files as positive controls, so
the scan was working and the zero was real.

So swiftc could change its answer and nothing would redden. That is not
hypothetical: the table's header reads `swiftc (Xcode 26.5)` and iOS 27
support is scheduled to start this month.

These arms close that loop for the platforms whose compiler is reachable.
They do NOT replace the table -- the table is more precise than anything
generated here (240 code points, both sides of every range boundary) and is
what makes a REFUSAL message specific. These ask a narrower question: for a
handful of specimens, does the table still agree with the tool it was
transcribed from?

Measured 2026-09-08, Apple Swift 6.3.2 / Xcode-26.5.0 -- the header's exact
version -- and both documented spec/compiler disagreements still hold:
`$` accepted though the published grammar omits it, U+FFFD rejected though
the grammar includes it.

⚠️ Reach, stated per platform rather than as a count:
    ios      swiftc      reachable, and the arms below ran
    web      node        reachable, and the arms below ran
    android  kotlinc     NOT INSTALLED here -- UNMEASURED, not zero. The
                         arm skips locally and fails in CI, so the gap is
                         visible rather than silent.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.unit_contracts import (  # noqa: E402
    IOS_TEST_PREFIX,
    UnitCase,
    identifier_problem,
    stub_text,
)


def _tool(name: str):
    """The compiler, or a decision about its absence.

    In CI this FAILS: a skipped gate gates nothing, and a green summary hides
    it. Locally it skips, so the absence lands in the skipped count instead of
    passing silently. Copied deliberately from
    `test_emitted_typescript_compiles.py`, which already made this decision --
    a second spelling of the same policy is how the two drift apart.
    """
    found = shutil.which(name)
    if found:
        return found
    if os.environ.get("CI"):
        raise AssertionError(
            f"{name} is not installed and this is CI. The identifier table "
            f"would go unchecked against the compiler it was transcribed from"
        )
    raise unittest.SkipTest(f"{name} not installed — table left UNMEASURED here")


#: One specimen per rule the table states, including both places the table
#: deliberately contradicts the published grammar. A specimen set is not the
#: table's 240 code points and is not trying to be: it is enough to notice
#: that the tool changed its mind.
IOS_SPECIMENS = [
    ("ab", True, "plain ascii"),
    ("名前を返す", True, "letters of any script are legal"),
    ("🎉を返す", True, "an emoji is legal"),
    ("a$b", True, "legal although the published grammar omits it"),
    ("a�b", False, "illegal although the grammar's range includes it"),
    ("returns a name", False, "a space is not an identifier character"),
    ("a-b", False, "a hyphen is not"),
]


class TheSwiftTableStillAgreesWithSwiftc(unittest.TestCase):
    """The arm the ticket is about: it reaches swiftc.

    Breaking `_SWIFT_IDENT_RANGES` reddens this and nothing else in the file
    -- which is the test that it is not a second transcript.
    """

    def _swiftc_accepts(self, swiftc: str, name: str) -> bool:
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "probe.swift"
            src.write_text(f"func {IOS_TEST_PREFIX}{name}() {{ }}\n",
                           encoding="utf-8")
            done = subprocess.run(
                [swiftc, "-parse", str(src)],
                capture_output=True, text=True, timeout=120,
            )
            return done.returncode == 0

    def test_the_table_and_the_compiler_give_the_same_verdict(self):
        swiftc = _tool("swiftc")
        for name, expected_legal, why in IOS_SPECIMENS:
            with self.subTest(name=name, why=why):
                compiler_ok = self._swiftc_accepts(swiftc, name)
                table_ok = identifier_problem("ios", name) is None
                self.assertEqual(
                    compiler_ok, table_ok,
                    f"swiftc says {'legal' if compiler_ok else 'illegal'} for "
                    f"{name!r} ({why}) and the table says "
                    f"{'legal' if table_ok else 'illegal'}. The table was "
                    f"transcribed from a compiler; one of them has moved.")

    def test_the_specimens_still_mean_what_they_say(self):
        """The control for the arm above.

        If swiftc accepted everything, the agreement arm would pass with a
        table that also accepted everything. This pins the specimens to the
        verdicts they were chosen for, so a compiler that stopped refusing
        anything fails HERE, naming the compiler rather than the table.
        """
        swiftc = _tool("swiftc")
        for name, expected_legal, why in IOS_SPECIMENS:
            with self.subTest(name=name, why=why):
                self.assertEqual(
                    expected_legal, self._swiftc_accepts(swiftc, name),
                    f"swiftc changed its answer for {name!r} ({why}). The "
                    f"table is a transcript of this compiler, so the "
                    f"transcript now needs re-measuring -- do not 'fix' the "
                    f"arm.")


class TheEmittedWebStubStillParses(unittest.TestCase):
    """`web` puts the name in a string literal, so the risk is the QUOTE.

    The template is single-quoted and the reported defect was a sanitiser
    written for the double-quoted platforms. `node --check` is what measured
    that; it was never wired to an arm.
    """

    def _cases(self, name: str, intent: str = "") -> list[UnitCase]:
        return [UnitCase(screen="Chat", target="ChatViewModel", name=name,
                         platforms=("web",), intent=intent)]

    def _node_parses(self, node: str, text: str) -> tuple[bool, str]:
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "probe.js"
            src.write_text(text, encoding="utf-8")
            done = subprocess.run([node, "--check", str(src)],
                                  capture_output=True, text=True, timeout=120)
            return done.returncode == 0, done.stderr

    def test_an_apostrophe_in_a_name_still_parses(self):
        """The reported break, kept as an arm rather than a comment."""
        node = _tool("node")
        text = stub_text("web", "ChatViewModel", self._cases("it's fine"))
        ok, err = self._node_parses(node, text)
        self.assertTrue(ok, f"emitted web stub does not parse:\n{err}\n{text}")

    def test_an_apostrophe_in_an_intent_still_parses(self):
        node = _tool("node")
        text = stub_text("web", "ChatViewModel",
                         self._cases("plain", intent="the user's name"))
        ok, err = self._node_parses(node, text)
        self.assertTrue(ok, f"emitted web stub does not parse:\n{err}\n{text}")

    def test_the_check_can_fail(self):
        """The negative control. Without it, a `_node_parses` that always
        returned True would satisfy both arms above."""
        node = _tool("node")
        ok, _ = self._node_parses(node, "describe('x', () => {\n")
        self.assertFalse(ok)


class TheAndroidTableIsUnmeasuredHere(unittest.TestCase):
    """Named, not counted as zero.

    kotlinc is absent on this machine, so the Kotlin half of the table has no
    arm that reaches its compiler. Saying so in an arm keeps the gap in the
    skipped count instead of leaving it to be inferred from silence.
    """

    def test_kotlinc_would_be_asked_the_same_question(self):
        kotlinc = _tool("kotlinc")
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "Probe.kt"
            src.write_text("class Probe {\n    fun `a b`() { }\n}\n",
                           encoding="utf-8")
            done = subprocess.run([kotlinc, str(src), "-d", d],
                                  capture_output=True, text=True, timeout=600)
            self.assertEqual(
                0, done.returncode,
                "kotlinc refuses a space inside an escaped identifier, which "
                f"the table says is legal:\n{done.stderr}")
            self.assertIsNone(identifier_problem("android", "a b"))


if __name__ == "__main__":
    unittest.main()
