"""One source for what the three branch runtimes say about `resolveString`.

The same diagnostic was hand-copied into a TypeScript literal, a Kotlin
literal and a Swift literal. Three blockers came out of that in one day,
and two of them were produced by the fix for the one before:

- `f43b8fb1` — the Kotlin copy's `\\"` collapsed inside a non-raw Python
  triple-quoted string, so the emitted Kotlin did not compile and every
  Android branch test in the reporting project ran zero tests.
- `89efcda1` — the web copy spelled a resolver call to teach the fix,
  which `jui lint-strings` read as a real reference and exited 2 on every
  project running the usage gate. Kotlin and Swift had already been
  worded without one: the three copies had drifted apart.
- `73a5e32a` — rewording the web copy dropped the `+` between two
  adjacent literals. Python joins those, TypeScript does not, and `tsc`
  stopped on TS1005.

Not one of those is a fact about the sentence. They are facts about
TRANSCRIPTION — escaping, adjacency, and one copy moving while two stay
put — so the sentence is declared once as prose here, and each language's
escaping, wrapping and joining is COMPUTED rather than typed. A reword is
then an edit to one Python string, and the failure mode it used to have
is unreachable instead of merely tested for.

What is deliberately NOT shared is the guard. The predicate deciding
whether a returned value is key-shaped is different in each language for
reasons that are about the language (`resolved.all {}` is vacuously true
on an empty Kotlin string; a regex says it in TypeScript), and one source
for three genuinely different expressions would be a worse lie than three
copies. The line is drawn at text, which has no reason to differ.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass

LANGUAGES = ("ts", "kotlin", "swift")

#: Line budget including the indent, the quotes and the join operator. The
#: surrounding runtimes are written to it.
WIDTH = 76


@dataclass(frozen=True)
class Value:
    """A runtime expression spliced into a message between two literals.

    Joined with `+` in all three languages rather than with each one's own
    interpolation. Kotlin's `$name`, Swift's `\\(name)` and a TypeScript
    template literal are each more idiomatic, and each would put a second
    escaping regime — and a second literal delimiter — back into the
    emitter. The property tests that caught `f43b8fb1` and `73a5e32a` read
    double-quoted literals; one literal form everywhere keeps them reading
    all three languages rather than two.
    """

    expr: str


#: Order matters: the backslash rule has to run before the rules that
#: introduce backslashes. Kotlin additionally reads `$` inside a plain
#: literal as the start of a template expression; the other two do not.
_ESCAPES = {
    "ts": (("\\", "\\\\"), ('"', '\\"')),
    "kotlin": (("\\", "\\\\"), ('"', '\\"'), ("$", "\\$")),
    "swift": (("\\", "\\\\"), ('"', '\\"')),
}

#: opener, continuation, closer, blank-line form.
_DOC_STYLE = {
    "ts": ("/** ", " * ", " */", " *"),
    "kotlin": ("/** ", " * ", " */", " *"),
    "swift": ("/// ", "/// ", None, "///"),
}


def escape(text: str, language: str) -> str:
    """The text as it must appear inside a double-quoted literal."""
    for old, new in _ESCAPES[language]:
        text = text.replace(old, new)
    return text


def _chunks(text: str, language: str, budget: int) -> list[str]:
    """Greedy wrap over the UNESCAPED text, measured on the escaped form.

    Wrapping the escaped form could cut a `\\"` in half. Each token carries
    the whitespace that follows it, so concatenating the chunks reproduces
    `text` byte for byte — which is the property the caller relies on when
    it joins them with `+`.
    """
    tokens = re.split(r"(?<=\s)(?=\S)", text) if text.strip() else [text]
    out: list[str] = []
    current = ""
    for token in tokens:
        if current and len(escape(current + token, language)) > budget:
            out.append(current)
            current = token
        else:
            current += token
    if current:
        out.append(current)
    return out or [text]


def message(parts, language: str, *, indent: int, width: int = WIDTH) -> str:
    """Render `parts` as one string expression in `language`.

    Every line but the last ends with the join operator. That is what makes
    "a line closing a literal followed by a line opening one, with nothing
    between them" unreachable here rather than only asserted against.
    """
    pad = " " * indent
    budget = width - indent - len('" +')
    terms: list[str] = []
    for part in parts:
        if isinstance(part, Value):
            terms.append(part.expr)
        else:
            terms += [f'"{escape(chunk, language)}"'
                      for chunk in _chunks(part, language, budget)]
    lines: list[str] = []
    current = ""
    for term in terms:
        joined = term if not current else f"{current} + {term}"
        if current and indent + len(joined) + len(" +") > width:
            lines.append(f"{pad}{current} +")
            current = term
        else:
            current = joined
    lines.append(f"{pad}{current}")
    return "\n".join(lines)


def doc(paragraphs, language: str, *, indent: int, width: int = WIDTH) -> str:
    """Render `paragraphs` as a doc comment in `language`.

    A paragraph given as a tuple is emitted verbatim, line by line: the web
    harness carries a code sample whose indentation is the point of it, and
    reflowing that would be the same defect as reflowing the sentence.
    """
    opener, cont, closer, blank = _DOC_STYLE[language]
    pad = " " * indent
    lines: list[str] = []
    for index, para in enumerate(paragraphs):
        if index:
            lines.append(f"{pad}{blank}")
        if isinstance(para, tuple):
            body = list(para)
        else:
            body = textwrap.wrap(para, width=width - indent - len(cont),
                                 break_long_words=False,
                                 break_on_hyphens=False) or [""]
        for offset, line in enumerate(body):
            prefix = opener if (index == 0 and offset == 0) else cont
            lines.append(f"{pad}{prefix}{line}".rstrip())
    if closer:
        lines.append(f"{pad}{closer}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The prose itself. Everything below is what a reword edits.
# ---------------------------------------------------------------------------

#: The runtime's failure message. The quotes around the two values are part
#: of the PROSE, not of the emitter: `returned ""` is how an empty return
#: reads as a return rather than as a truncated sentence, and putting them
#: here means the escaping that `f43b8fb1` got wrong is computed.
RESOLVE_STRING_FAILURE = (
    'resolveString("',
    Value("key"),
    '") returned "',
    Value("resolved"),
    '", which is not the text that key names. Bindings are not resolved '
    "when a component renders, so the field holds resolved text — return "
    "the string manager's lookup of the full key. A key, or nothing, means "
    "the table did not resolve.",
)

#: The reason, ordered. The general one (the render path) leads; the
#: sufficient one (server messages) follows and is marked as such. Reversed,
#: a reader concludes that a field which never carries server text may
#: return a key — it may not, because rendering resolves nothing.
RESOLVE_STRING_RUNTIME_DOC = (
    "Resolve an '@key' expectation through the harness, refusing a KEY.",

    "`resolveString` must return the RESOLVED TEXT. The reason is the "
    "render path, not the field: `@{...}` bindings are not resolved when a "
    "component renders — the value is emitted raw, and only a layout's "
    "static text goes through the string manager. A data field therefore "
    "holds resolved text, and an expectation compared against it has to be "
    "resolved text too.",

    "(A second fact points the same way and is often reached first: a "
    "field that can also carry a server message has no front-end key for "
    "that value. That is a SUFFICIENT reason, not the reason — read alone "
    'it invites "then a field servers never touch may return a key", which '
    "is wrong, because the render path resolves keys for no field at all.)",

    "Checked rather than only documented, because the shape hides: of 12 "
    "harnesses in one project 3 returned the key, and 2 of those had an "
    "empty table, so `resolveString` was never called — broken and green "
    "until that screen's first '@key' contract arrived. A check on the "
    "call has no dormant state.",
)

#: The same reason where the harness AUTHOR reads it. Two people on the
#: reporting project wrote the two different forms, so a new harness has to
#: be right before anything calls it — the runtime check alone is too late.
RESOLVE_STRING_HARNESS_REASON = (
    "RETURN THE RESOLVED TEXT, never the key. `@{...}` bindings are not "
    "resolved when a component renders — the value is emitted raw, and "
    "only a layout's static text goes through the string manager — so a "
    "data field holds resolved text and the expectation compared against "
    "it must too. (A field that can also carry a server message has no "
    "front-end key for that value either; that is a second reason, not the "
    'reason. The render path resolves keys for no field at all, so "this '
    'field never holds server text, so a key is fine" is wrong.)'
)

RESOLVE_STRING_HARNESS_CLOSE = (
    "The runtime rejects a key-shaped return when this is called, so the "
    "mistake surfaces at the first '@key' contract rather than living in a "
    "harness whose table is still empty."
)


def harness_doc(language: str, *, summary: str, indent: int,
                sample: tuple = ()) -> str:
    """The interface doc for `resolveString`, per language.

    The summary line differs because the web harness owns the key table on
    the same file and the other two do not, and only the web skeleton
    carries a code sample. The reason and the closing are shared, which is
    the part a reword touches.
    """
    paragraphs = [summary, RESOLVE_STRING_HARNESS_REASON]
    if sample:
        paragraphs.append(sample)
    paragraphs.append(RESOLVE_STRING_HARNESS_CLOSE)
    return doc(paragraphs, language, indent=indent)
