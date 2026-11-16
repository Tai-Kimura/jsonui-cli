"""Prose from a swagger `description` cannot end the comment holding it.

A shared swagger's `error_code` description contained a path glob — the
substring `/*` — and the Android DTO emitter put it verbatim into a KDoc.
Kotlin block comments NEST, so that opened an inner comment and the
trailing `*/` closed only that one: the KDoc stayed open, the rest of the
file was read as comment, and `:app:compileDevDebugKotlin` halted in two
consumer projects. Writing a description is not supposed to be able to
break a build.

The oracle here is a scanner implementing Kotlin's nesting rule rather
than a substring check: "looks fine" is not a verdict, and the failure
mode is precisely about how a parser pairs the delimiters.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "jui_tools") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "jui_tools"))

from jui_cli.core.comment_safety import sanitize_block_comment  # noqa: E402
from jui_cli.generators.android_api_model_generator import (  # noqa: E402
    _kdoc_lines,
)
from jui_cli.generators.web_api_model_generator import _jsdoc_lines  # noqa: E402


def kotlin_block_is_one_comment(source: str) -> bool:
    """True iff *source* is exactly one Kotlin block comment.

    Both failure directions matter and an "is it balanced" oracle only
    sees one of them: an unescaped `/*` leaves the KDoc UNCLOSED (the
    filed crash), while an unescaped `*/` closes it EARLY and spills the
    rest of the prose out as code. A depth counter returns 0 for both a
    healthy block and an early-closed one — measured, when a mutation
    that escaped only `/*` kept this test green.
    """
    if not source.startswith("/*"):
        return False
    depth = 0
    i = 0
    while i < len(source) - 1:
        pair = source[i:i + 2]
        if pair == "/*":
            depth += 1
            i += 2
            continue
        if pair == "*/":
            depth -= 1
            i += 2
            if depth == 0:
                return i == len(source)  # closed exactly at the end
            continue
        i += 1
    return False


def ts_comment_is_balanced(source: str) -> bool:
    """TS/JS: comments do NOT nest — the first `*/` closes."""
    if not source.startswith("/*"):
        return True
    return source.index("*/") == len(source) - 2


#: The filed description, plus the delimiters a scanner must also survive.
HAZARDS = [
    "error codes for /api/orders/* (see the guide)",
    "closes early: */ here",
    "both: /* and */",
    "adjacent: /*/",
    "empty comment: /**/",
    "multi\nline with /* inside",
]


class KotlinKdocSurvivesProseTests(unittest.TestCase):
    def test_every_hazard_leaves_exactly_one_closed_kdoc(self):
        for text in HAZARDS:
            with self.subTest(text=text):
                block = "\n".join(_kdoc_lines(text))
                self.assertTrue(kotlin_block_is_one_comment(block), block)

    def test_the_glob_is_still_readable(self):
        """Escaping must not delete what the description said — the path
        and the star are why the sentence exists."""
        block = "\n".join(_kdoc_lines("see /api/orders/* for details"))
        self.assertIn("/api/orders/", block)
        self.assertIn("*", block)

    def test_prose_without_delimiters_is_untouched(self):
        text = "the item's display name (may be empty)"
        self.assertEqual(_kdoc_lines(text), [f"/** {text} */"])


class WebJsdocSurvivesProseTests(unittest.TestCase):
    def test_a_closing_delimiter_cannot_end_the_block_early(self):
        # TS does not nest, so `/*` is harmless — but `*/` still ends the
        # comment and spills prose into code. The reporting lane measured
        # web as unaffected; that held for their text, not for this one.
        block = "\n".join(_jsdoc_lines("ends here */ and then code"))
        self.assertTrue(ts_comment_is_balanced(block), block)

    def test_every_hazard_stays_balanced(self):
        for text in HAZARDS:
            with self.subTest(text=text):
                block = "\n".join(_jsdoc_lines(text))
                self.assertNotIn("*/", block[:-2])


class SanitizerTests(unittest.TestCase):
    def test_output_contains_no_delimiter_at_all(self):
        for text in HAZARDS:
            with self.subTest(text=text):
                out = sanitize_block_comment(text)
                self.assertNotIn("/*", out)
                self.assertNotIn("*/", out)


if __name__ == "__main__":
    unittest.main()
