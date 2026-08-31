"""`jui lint-strings --usage` — set agreement between strings.json and its
referencing sides.

The raw-literal lint proves every layout literal RESOLVES; nothing proved
the opposite directions until now:

- **unused key**: a text prepared in strings.json that no layout and no VM
  references — it never reaches a screen, and lint/build/verify all pass
  (a consumer shipped a member-search help text this way: the screen
  simply had no explanation on it).
- **missing key**: a VM reference to a key strings.json does not declare —
  the web runtime's ``getString`` returns the key itself and a property
  access renders ``undefined``, so an identifier leaks onto the screen.

Naive unused detection was measured at 98% false positives on a real
consumer (dynamically assembled keys, conditional key expressions), so
this check deliberately does NOT try to be clever about detection —
excluded prefixes would hide real dead keys forever. Instead it pairs
detection with a convention that makes the used set computable:

- A static reference is an accessor the toolchain itself emits, so its
  spelling is derivable from the declared keys (no guessing):
  web ``StringManager.currentLanguage.<camel-or-snake-flat>`` and
  ``getString("<flat>")``, iOS ``StringManager.<PascalSection>.<camelKey>``
  and ``"<flat>".localized()``, Android ``R.string.<flat>``.
- The sanctioned web wrapper pair ``str("...")`` / ``tpl("...")`` also
  counts: the global pair takes the flat key and per-ViewModel wrappers
  prefix their section, so a wrapper literal matches flat-or-bare
  (broad), and an unmatched one is not reported — ``str``/``tpl`` are
  ordinary identifiers in other code, while a direct ``getString``
  literal is unambiguous and keeps the strict missing check.
- **Dynamic keys must be declared**: any dynamically-selected key set
  lives in a constant map whose name ends in ``_STRING_KEYS``
  (``FIELD_STRING_KEYS = {"entry": "reservations_entry_label", ...}``).
  The check collects every string literal inside such declarations into
  the used set, and a literal there that is NOT a declared key is a
  missing-key finding — the map stays honest.
- A dynamic reference NOT routed through a ``*_STRING_KEYS`` name is
  itself a finding (the closure of the used set is enforced, not
  assumed). ``getString(expr)`` / ``currentLanguage[expr]`` pass only
  when the statement mentions a ``*_STRING_KEYS`` identifier.
- The escape hatch for intentionally-reserved keys is the same
  convention: declare them in e.g. ``LINT_KEEP_STRING_KEYS`` next to the
  code that will use them — a reviewed statement in source, not a ledger
  entry that rots.

The used set is the UNION over every face the project declares (layout
JSON plus the ios/android/web platform roots) and is judged only after
aggregation — judging per face would kill an iOS-only key on web. Layout
collection is deliberately broader than the raw-literal lint (every
string in the tree, list items included): over-collection can hide a
dead key, under-collection invents one, and false positives are what
kill trust in the check.

Missing-direction findings are only raised where the platform would NOT
catch the mistake at compile time: web property/getString references and
``*_STRING_KEYS`` map values. iOS accessors and Android ``R.string``
symbols that match nothing are a compile error on their platform
already, and ``.localized()`` may target platform string catalogs this
check cannot see — neither is reported here.

Generated ``StringManager*`` files are excluded from scanning: they
DECLARE every key (the web stub embeds the whole table), they do not use
them. Dependency/build directories are skipped.
"""
from __future__ import annotations

import json
import plistlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# Directories never scanned for VM references.
_SKIP_DIRS = {
    "node_modules", ".git", ".next", "dist", "build", "out",
    "Pods", "DerivedData", ".gradle", ".idea", "vendor",
    "__pycache__",
}

_WEB_SUFFIXES = (".ts", ".tsx", ".js", ".jsx")
_IOS_SUFFIXES = (".swift",)
_ANDROID_SUFFIXES = (".kt", ".java")

# The generated StringManager (any platform) declares the keys; scanning
# it would mark everything used.
_EXCLUDED_BASENAME_PREFIX = "StringManager"

_KEYS_MAP_NAME_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*_STRING_KEYS)\b")

_WEB_PROP_RE = re.compile(
    r"\bStringManager\.currentLanguage\.([A-Za-z_][A-Za-z0-9_]*)"
)
_WEB_BRACKET_RE = re.compile(r"\bStringManager\.currentLanguage\[")
_GETSTRING_LITERAL_RE = re.compile(
    r"\bgetString\(\s*([\"'])([A-Za-z0-9_]+)\1\s*\)"
)
# The sanctioned wrapper pair (lib/i18n): the global pair takes the flat
# key, and consumers also write per-ViewModel wrappers that prefix their
# section — so a literal here may be flat OR a bare key of any section.
# Matching is therefore broad and an unmatched literal is NOT reported
# (str/tpl are ordinary identifiers elsewhere; getString is the
# unambiguous one and keeps the strict missing check).
#
# EXCEPT when the wrapper's own definition sits in the same file and its
# body is statically readable (see `_wrapper_prefixes`): then the composed
# key is knowable, the broad trade-off's justification disappears, and the
# literal is checked strictly. Without this, a call under a per-ViewModel
# prefix wrapper could never produce a missing finding at all — a typo'd
# key was silently ignored, and a literal that happened to equal another
# section's bare key read as usage, both reaching the screen as raw keys
# through getString's `|| key` fallback while the gate stayed green.
_WRAPPER_LITERAL_RE = re.compile(
    r"\b(str|tpl)\(\s*([\"'])([A-Za-z0-9_]+)\2"
)
_WRAPPER_DYNAMIC_RE = re.compile(
    r"\b(?:str|tpl|getString|StringManager\s*\.\s*plural)\(\s*(?![\"'])"
)
# StringManager.plural(key, count) — the CLDR plural face. Qualified, so
# it is as unambiguous as getString: a literal that matches nothing is a
# missing finding, and a bare `plural(` helper somewhere else is not
# swept in. Keys referenced ONLY through plural() were all reported
# unused before this pattern existed (11 of 11 on the reporting
# consumer).
_PLURAL_LITERAL_RE = re.compile(
    r"\bStringManager\s*\.\s*plural\(\s*([\"'])([A-Za-z0-9_]+)\1"
)
# `function str(key)` / `func …` / `fun …` — a wrapper DEFINITION, not a
# dynamic reference.
_FUNCTION_DEF_BEFORE_RE = re.compile(r"(?:function|func|fun|def)\s+$")
# Definitions of the sanctioned wrappers themselves. Their bodies are the
# delegation layer (param → getString, possibly with a section prefix) —
# key SELECTION happens at their call sites, where the literal rule is
# enforced, so flagging the plumbing adds nothing to the closure and
# would fire once per ViewModel-local wrapper. The captured name feeds
# `_wrapper_prefixes`, which reads the body to make call sites strict.
_WRAPPER_DEF_NAME_RE = re.compile(r"\bfunction\s+(str|tpl)\s*\(")
# The two statically readable wrapper bodies. Anything else (a variable
# prefix, several interpolations, a lookup table) keeps the broad match —
# unreadable must degrade to the old behaviour, never to a guess.
_WRAPPER_PREFIX_BODY_RE = re.compile(
    r"getString\(\s*`([A-Za-z0-9_]*)\$\{[^}`$]*\}`\s*\)")
_WRAPPER_FLAT_BODY_RE = re.compile(
    r"getString\(\s*[A-Za-z_][A-Za-z0-9_]*\s*\)")


def _wrapper_defs(text: str) -> list[tuple[str, int, int]]:
    """(name, start, end) for every `function str/tpl(...) {...}` in *text*."""
    defs: list[tuple[str, int, int]] = []
    for m in _WRAPPER_DEF_NAME_RE.finditer(text):
        brace = text.find("{", m.end())
        if brace < 0:
            continue
        depth = 0
        j = brace
        in_str: str | None = None
        while j < len(text):
            ch = text[j]
            if in_str is not None:
                if ch == "\\":
                    j += 2
                    continue
                if ch == in_str:
                    in_str = None
            elif ch in "\"'`":
                in_str = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        defs.append((m.group(1), m.start(), j + 1))
    return defs


def _wrapper_body_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) offsets of every `function str/tpl(...) {...}` body."""
    return [(start, end) for _name, start, end in _wrapper_defs(text)]


def _wrapper_prefixes(text: str) -> dict:
    """``callee name -> static key prefix`` for this file's own wrappers.

    A name is present only when its definition sits in *text* AND the body
    is one of the two readable shapes: prefix composition
    (``getString(`section_${key}`)`` → that prefix) or flat delegation
    (``getString(key)`` → ``""``). The definition is the evidence that
    licenses the strict check at the call sites; a file that merely imports
    its wrapper — or defines an unrelated `str()` of its own with a body
    this cannot read — stays on the broad match. Conflicting definitions of
    one name make it unreadable too.
    """
    out: dict = {}
    unreadable: set = set()
    for name, start, end in _wrapper_defs(text):
        body = text[start:end]
        pm = _WRAPPER_PREFIX_BODY_RE.search(body)
        if pm:
            prefix = pm.group(1)
        elif _WRAPPER_FLAT_BODY_RE.search(body):
            prefix = ""
        else:
            unreadable.add(name)
            continue
        if name in out and out[name] != prefix:
            unreadable.add(name)
            continue
        out[name] = prefix
    for name in unreadable:
        out.pop(name, None)
    return out


def _in_spans(offset: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= offset < end for start, end in spans)


def _call_arg_span(text: str, start: int) -> str:
    """The balanced ``(...)`` argument text of a call whose opening paren
    is at or after *start* (first argument up to the matching close)."""
    i = text.find("(", start)
    if i < 0:
        return ""
    depth = 0
    j = i
    in_str: str | None = None
    while j < len(text):
        ch = text[j]
        if in_str is not None:
            if ch == "\\":
                j += 2
                continue
            if ch == in_str:
                in_str = None
        elif ch in "\"'`":
            in_str = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[i + 1 : j]
        j += 1
    return text[i + 1 :]


_KEY_LITERAL_RE = re.compile(r"([\"'])([A-Za-z0-9_]+)\1")


def _split_top_level(expr: str, sep: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    in_str: str | None = None
    last = 0
    i = 0
    while i < len(expr):
        ch = expr[i]
        if in_str is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
        elif ch in "\"'`":
            in_str = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0 and expr.startswith(sep, i):
            # `?` must not match `??` or `?.`
            if sep == "?" and (expr[i : i + 2] in ("??", "?.")):
                i += 2
                continue
            parts.append(expr[last:i])
            i += len(sep)
            last = i
            continue
        i += 1
    parts.append(expr[last:])
    return parts


def _is_static_choice_of_literals(expr: str) -> bool:
    """True when every VALUE the expression can produce is a string
    literal — ``cond ? "a_key" : "b_key"`` and nullish chains of
    literals. The key set is statically visible, so the closure the
    dynamic-reference finding protects is already satisfied; the ticket
    named this exact form as one a naive scan cannot read."""
    expr = expr.strip()
    while expr.startswith("(") and expr.endswith(")"):
        # strip only when the opening paren matches the LAST character
        depth = 0
        wraps = False
        for i, ch in enumerate(expr):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    wraps = i == len(expr) - 1
                    break
        if not wraps:
            break
        expr = expr[1:-1].strip()
    if _KEY_LITERAL_RE.fullmatch(expr):
        return True
    ternary = _split_top_level(expr, "?")
    if len(ternary) == 2:
        branches = _split_top_level(ternary[1], ":")
        return len(branches) == 2 and all(
            _is_static_choice_of_literals(b) for b in branches
        )
    nullish = _split_top_level(expr, "??")
    if len(nullish) > 1:
        return all(_is_static_choice_of_literals(p) for p in nullish)
    return False
_IOS_ACCESSOR_RE = re.compile(
    r"\bStringManager\.([A-Z][A-Za-z0-9]*)\.([a-z][A-Za-z0-9]*)"
)
_IOS_LOCALIZED_RE = re.compile(
    r"([\"'])([a-z][a-z0-9_]*)\1\.localized\(\)"
)
# Hand-written Foundation lookups. Unlike `.localized()` — which the
# SwiftUI generator also emits for sentinel vocabulary such as a
# visibility's "gone", so an unresolved one there is usually not a key at
# all — these two forms are only ever written by a person naming a key.
# An absent key does not fail to compile: NSLocalizedString returns the key
# string itself, so the raw key ships to the screen.
_IOS_NSLOCALIZED_RE = re.compile(
    r"\bNSLocalizedString\(\s*([\"'])([A-Za-z0-9_.]+)\1"
)
_IOS_STRING_LOCALIZED_RE = re.compile(
    r"\bString\(\s*localized:\s*([\"'])([A-Za-z0-9_.]+)\1"
)
_IOS_CATALOG_SUFFIXES = (".strings", ".stringsdict", ".xcstrings")
_STRINGS_ENTRY_RE = re.compile(r'^\s*"((?:[^"\\]|\\.)*)"\s*=', re.MULTILINE)
_ANDROID_R_STRING_RE = re.compile(r"\bR\.string\.([A-Za-z_][A-Za-z0-9_]*)")

_STRING_LITERAL_RE = re.compile(r"([\"'])((?:[^\"'\\\n]|\\.)*?)\1")
_BRANCH_HARNESS_RE = re.compile(r"BranchHarness", re.IGNORECASE)
_KEY_SHAPED_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")


def snake_to_pascal(s: str) -> str:
    """The sjui generator's section spelling (snake_to_pascal)."""
    return "".join(p[:1].upper() + p[1:] for p in s.split("_") if p)


def snake_to_camel(s: str) -> str:
    """The sjui generator's key spelling (snake_to_camel)."""
    parts = [p for p in s.split("_") if p]
    if not parts:
        return s
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def camelize_flat(flat: str) -> str:
    """The web stub's proxy spelling: ``a_b_1`` → ``aB1`` (snake stays
    valid too — the proxy keeps both)."""
    return re.sub(r"_([a-z0-9])", lambda m: m.group(1).upper(), flat)


@dataclass(frozen=True)
class UsageFinding:
    kind: str  # "unused-key" | "missing-key" | "dynamic-ref"
    site: str  # "<section>.<key>" for unused; "<file>:<line>" otherwise
    detail: str


@dataclass
class UsageReport:
    unused: list[UsageFinding] = field(default_factory=list)
    missing: list[UsageFinding] = field(default_factory=list)
    dynamic: list[UsageFinding] = field(default_factory=list)
    scanned_files: int = 0
    faces: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not (self.unused or self.missing or self.dynamic)

    def warning_lines(self) -> list[str]:
        lines = []
        for f in self.unused:
            lines.append(
                f"strings.json key {f.site} is referenced by no layout and "
                f"no VM code across faces ({', '.join(self.faces)}) — it "
                f"never reaches a screen. Wire it up, delete it, or declare "
                f"it in a *_STRING_KEYS map next to the code that will use it"
            )
        for f in self.missing:
            lines.append(
                f"{f.site}: {f.detail} — strings.json declares no such key, "
                f"so the identifier itself would reach the screen"
            )
        for f in self.dynamic:
            lines.append(
                f"{f.site}: {f.detail} — dynamic key selection must go "
                f"through a constant map named *_STRING_KEYS so the used "
                f"set stays computable"
            )
        return lines


class DeclaredKeys:
    """strings.json keys with every reference spelling precomputed."""

    def __init__(self, groups: dict[str, dict[str, Any]]):
        self.pairs: set[tuple[str, str]] = set()
        # flat "<section>_<key>" → pairs (several on underscore ambiguity)
        self.by_flat: dict[str, set[tuple[str, str]]] = {}
        # web camel spelling of the flat key → pairs
        self.by_camel: dict[str, set[tuple[str, str]]] = {}
        # iOS accessor spelling (PascalSection, camelKey) → pairs
        self.by_accessor: dict[tuple[str, str], set[tuple[str, str]]] = {}
        # exact declared value → pairs (layout value-match resolution)
        self.by_value: dict[str, set[tuple[str, str]]] = {}
        # bare key → pairs (scoped by own sections at the call site)
        self.by_bare: dict[str, set[tuple[str, str]]] = {}
        for section, entries in groups.items():
            for key, value in entries.items():
                pair = (section, key)
                self.pairs.add(pair)
                flat = f"{section}_{key}"
                self.by_flat.setdefault(flat, set()).add(pair)
                self.by_camel.setdefault(camelize_flat(flat), set()).add(pair)
                self.by_accessor.setdefault(
                    (snake_to_pascal(section), snake_to_camel(key)), set()
                ).add(pair)
                self.by_bare.setdefault(key, set()).add(pair)
                if isinstance(value, str):
                    self.by_value.setdefault(value, set()).add(pair)
                elif isinstance(value, dict):
                    for lang_value in value.values():
                        if isinstance(lang_value, str):
                            self.by_value.setdefault(lang_value, set()).add(pair)

    def layout_targets(
        self, text: str, own_sections: Iterable[str]
    ) -> set[tuple[str, str]]:
        """Every declared pair the given layout string could be read as.
        Deliberately broad — see the module docstring."""
        targets = set(self.by_flat.get(text, ()))
        targets |= self.by_value.get(text, set())
        own = set(own_sections)
        for pair in self.by_bare.get(text, ()):
            if pair[0] in own:
                targets.add(pair)
        return targets


def _strip_comments(text: str) -> str:
    """Blank out ``//`` and ``/* */`` comments, preserving offsets.

    Comment text is prose: a swagger description mentioning Python's
    ``str(int)`` rode a generated DTO's doc comment straight into a
    dynamic-ref finding, and a ``getString("key")`` in a comment is worse
    — a false USED that silently hides a real unused key. Comment bytes
    become spaces (newlines kept), so every line number and span computed
    later stays valid.

    String literals are respected while walking (``"http://x"`` is not a
    comment) and their CONTENT is kept: template interpolations
    (`` `${str("key")}` ``, Kotlin/Swift string templates) are genuine
    reference sites, and a walker cannot cheaply tell those from prose —
    the broad-used bias keeps that direction safe. Block comments nest,
    as in Swift/Kotlin.
    """
    out = list(text)
    i = 0
    n = len(text)
    in_str: str | None = None
    while i < n:
        ch = text[i]
        if in_str is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in "\"'`":
            in_str = ch
            i += 1
            continue
        if ch == "/" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "/":
                j = text.find("\n", i)
                if j < 0:
                    j = n
                for k in range(i, j):
                    out[k] = " "
                i = j
                continue
            if nxt == "*":
                depth = 1
                j = i + 2
                while j < n and depth:
                    if text.startswith("/*", j):
                        depth += 1
                        j += 2
                    elif text.startswith("*/", j):
                        depth -= 1
                        j += 2
                    else:
                        j += 1
                for k in range(i, j):
                    if out[k] != "\n":
                        out[k] = " "
                i = j
                continue
        i += 1
    return "".join(out)


def _iter_source_files(root: Path, suffixes: tuple[str, ...]) -> Iterable[Path]:
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            children = sorted(current.iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_dir():
                if child.name not in _SKIP_DIRS and not child.name.startswith("."):
                    stack.append(child)
            elif child.suffix in suffixes:
                if child.name.startswith(_EXCLUDED_BASENAME_PREFIX):
                    continue
                yield child


def collect_ios_catalog_keys(root: Path) -> set[str]:
    """Keys carried by the platform's own string catalogs.

    A key may legitimately live in Localizable.strings / .xcstrings rather
    than in the JsonUI SSoT — that possibility is why an unresolved iOS
    reference used to be passed over in silence. Reading the catalogs turns
    the assumption into a measurement, so what is left over really is a
    reference that resolves nowhere.
    """
    keys: set[str] = set()
    for path in _iter_source_files(root, _IOS_CATALOG_SUFFIXES):
        try:
            if path.suffix == ".xcstrings":
                data = json.loads(path.read_text(encoding="utf-8"))
                strings = data.get("strings") if isinstance(data, dict) else None
                if isinstance(strings, dict):
                    keys.update(k for k in strings if isinstance(k, str))
                continue
            if path.suffix == ".stringsdict":
                with open(path, "rb") as fh:
                    data = plistlib.load(fh)
                if isinstance(data, dict):
                    keys.update(k for k in data if isinstance(k, str))
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError, plistlib.InvalidFileException):
            continue
        keys.update(m.group(1) for m in _STRINGS_ENTRY_RE.finditer(text))
    return keys


def _extract_keys_map_literals(text: str) -> tuple[list[str], list[str]]:
    """``(strict, lenient)`` string literals from every ``*_STRING_KEYS``
    declaration.

    Walks from the declaration to the end of its balanced ``{...}`` /
    ``[...]`` / ``mapOf(...)`` initializer (quotes respected). Dict
    shapes contribute STRICT literals — only the value side of each
    pair, so an unmatched one is a genuine missing key. List shapes
    contribute LENIENT literals: a tuple array (``[[prop, key], ...]``)
    interleaves non-key strings with keys and nothing structural tells
    them apart, so every literal feeds the used set but none is judged
    missing (a tuple's first element read as a missing key on a real
    consumer before this split).
    """
    strict: list[str] = []
    lenient: list[str] = []
    for m in _KEYS_MAP_NAME_RE.finditer(text):
        eq = text.find("=", m.end())
        if eq < 0:
            continue
        # A mention (not a declaration) has no initializer right after it;
        # only walk when an opening brace/bracket follows the '='.
        i = eq + 1
        while i < len(text) and text[i] in " \t\r\n":
            i += 1
        # Type annotations between name and '=' are fine (the '=' search
        # skipped them); a colon path like FOO_STRING_KEYS[x] has no '='
        # nearby and lands here with a non-brace char.
        # Kotlin spells the initializer mapOf( ... ) — skip a builder-call
        # name so the walk starts at its parenthesis.
        call = re.match(r"\s*(?:mapOf|listOf|setOf|arrayOf)\s*", text[i:])
        if call:
            i += call.end()
        if i >= len(text) or text[i] not in "{[(":
            continue
        opener, closer = text[i], {"{": "}", "[": "]", "(": ")"}[text[i]]
        depth = 0
        j = i
        in_str: str | None = None
        while j < len(text):
            ch = text[j]
            if in_str is not None:
                if ch == "\\":
                    j += 2
                    continue
                if ch == in_str:
                    in_str = None
            elif ch in "\"'":
                in_str = ch
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    break
            j += 1
        body = text[i : j + 1]
        pair_values = re.findall(
            r"(?::|=>|\bto\s)\s*([\"'])([A-Za-z0-9_]+)\1", body
        )
        if opener in "{(" and pair_values:
            # value side of `name: "literal"` / `"name": "literal"` /
            # `name to "literal"` (Kotlin mapOf) pairs
            strict.extend(v for _, v in pair_values)
        else:
            # plain list / tuple array — no structural key/value split
            for pm in _STRING_LITERAL_RE.finditer(body):
                lenient.append(pm.group(2))
    return strict, lenient


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _statement_mentions_keys_map(text: str, offset: int) -> bool:
    """Whether the statement at *offset* references a *_STRING_KEYS name —
    the declared-map route that exempts a dynamic reference.

    The window is the physical line containing *offset*, extended to the
    close of any ``(...)``/``[...]`` group that opens on that line and
    runs past it. Formatters wrap long calls at printWidth and push the
    map name onto its own line inside the call's arguments, so a one-line
    window turned convention-compliant calls into dynamic-ref warnings
    (the warning text always said "statement"). Balancing stops at the
    group's own closer, so the widened window cannot reach a
    *_STRING_KEYS mention in a neighbouring statement. A group left
    unclosed at EOF falls back to the one-line window.
    """
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    if end < 0:
        end = len(text)
    window_end = end
    depth = 0
    in_str: str | None = None
    j = start
    while j < len(text):
        if j >= end and depth == 0:
            break
        ch = text[j]
        if in_str is not None:
            if ch == "\\":
                j += 2
                continue
            if ch == in_str:
                in_str = None
        elif ch in "\"'`":
            in_str = ch
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            # A closer at depth 0 belongs to a group opened on an earlier
            # line; the statement continues past it — skip it.
            if depth > 0:
                depth -= 1
                if depth == 0 and j >= end:
                    window_end = j + 1
                    break
        j += 1
    return _KEYS_MAP_NAME_RE.search(text, start, window_end) is not None


def scan_vm_sources(
    face: str,
    root: Path,
    declared: DeclaredKeys,
    report: UsageReport,
    used: set[tuple[str, str]],
    harness_keys: set[str] | None = None,
) -> None:
    """Scan one platform root; add to *used* and append findings."""
    suffixes = {
        "web": _WEB_SUFFIXES,
        "ios": _IOS_SUFFIXES,
        "android": _ANDROID_SUFFIXES,
    }[face]
    catalog_keys = collect_ios_catalog_keys(root) if face == "ios" else set()
    for src in _iter_source_files(root, suffixes):
        try:
            text = src.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        text = _strip_comments(text)
        report.scanned_files += 1
        rel = src.as_posix()

        # *_STRING_KEYS declarations: every literal is a used key; a
        # literal that is not a declared flat key is a missing finding
        # (the map must stay honest for the closure to mean anything).
        strict_literals, lenient_literals = _extract_keys_map_literals(text)
        if harness_keys is not None:
            harness_keys.update(strict_literals)
            harness_keys.update(lenient_literals)
            # A generated branch harness IS the declaration site for the
            # keys a contract resolves through it — the Swift and Kotlin
            # skeletons spell that closure as a closed switch rather than
            # a map, so the map scan above does not see it.
            if _BRANCH_HARNESS_RE.search(src.name):
                harness_keys.update(
                    m.group(2) for m in _STRING_LITERAL_RE.finditer(text)
                    if _KEY_SHAPED_RE.match(m.group(2))
                )
        for literal in strict_literals:
            pairs = declared.by_flat.get(literal)
            if pairs:
                used |= pairs
            else:
                report.missing.append(UsageFinding(
                    kind="missing-key",
                    site=rel,
                    detail=f"*_STRING_KEYS map declares {literal!r}",
                ))
        for literal in lenient_literals:
            pairs = declared.by_flat.get(literal)
            if pairs:
                used |= pairs
            # a tuple array interleaves non-key strings — no missing
            # judgment on the list shape

        if face == "web":
            for m in _WEB_PROP_RE.finditer(text):
                ident = m.group(1)
                pairs = declared.by_camel.get(ident) or declared.by_flat.get(ident)
                if pairs:
                    used |= pairs
                else:
                    report.missing.append(UsageFinding(
                        kind="missing-key",
                        site=f"{rel}:{_line_of(text, m.start())}",
                        detail=f"StringManager.currentLanguage.{ident}",
                    ))
            for m in _GETSTRING_LITERAL_RE.finditer(text):
                literal = m.group(2)
                pairs = declared.by_flat.get(literal)
                if pairs:
                    used |= pairs
                else:
                    report.missing.append(UsageFinding(
                        kind="missing-key",
                        site=f"{rel}:{_line_of(text, m.start())}",
                        detail=f"getString({literal!r})",
                    ))
            wrapper_prefixes = _wrapper_prefixes(text)
            for m in _WRAPPER_LITERAL_RE.finditer(text):
                callee = m.group(1)
                literal = m.group(3)
                prefix = wrapper_prefixes.get(callee)
                if prefix is not None:
                    # This file defines the wrapper and its composition is
                    # readable, so the key the call will look up is exactly
                    # `prefix + literal` — checked strictly, like getString.
                    composed = prefix + literal
                    pairs = declared.by_flat.get(composed)
                    if pairs:
                        used |= pairs
                    else:
                        report.missing.append(UsageFinding(
                            kind="missing-key",
                            site=f"{rel}:{_line_of(text, m.start())}",
                            detail=(
                                f"{callee}({literal!r}) — this file's "
                                f"{callee}() wrapper composes "
                                f"'{composed}', which is not declared"),
                        ))
                    continue
                pairs = declared.by_flat.get(literal) or declared.by_bare.get(
                    literal
                )
                if pairs:
                    used |= pairs
                # unmatched: str/tpl are ordinary identifiers elsewhere —
                # only getString is unambiguous enough for a missing finding
            for m in _PLURAL_LITERAL_RE.finditer(text):
                literal = m.group(2)
                pairs = declared.by_flat.get(literal) or declared.by_bare.get(
                    literal
                )
                if pairs:
                    used |= pairs
                else:
                    report.missing.append(UsageFinding(
                        kind="missing-key",
                        site=f"{rel}:{_line_of(text, m.start())}",
                        detail=f"StringManager.plural({literal!r})",
                    ))
            for m in _WEB_BRACKET_RE.finditer(text):
                if not _statement_mentions_keys_map(text, m.start()):
                    report.dynamic.append(UsageFinding(
                        kind="dynamic-ref",
                        site=f"{rel}:{_line_of(text, m.start())}",
                        detail="StringManager.currentLanguage[...] with no "
                               "*_STRING_KEYS on the statement",
                    ))
            wrapper_spans = _wrapper_body_spans(text)
            for m in _WRAPPER_DYNAMIC_RE.finditer(text):
                if _FUNCTION_DEF_BEFORE_RE.search(text, 0, m.start()):
                    continue  # the wrapper's own definition line
                if _in_spans(m.start(), wrapper_spans):
                    continue  # sanctioned wrapper's delegation body
                # Only the FIRST argument selects the key: tpl(expr,
                # {params}) and plural(expr, count) carry trailing
                # arguments that made the whole span read as dynamic even
                # when the key expression was a literal choice, and their
                # param strings are not key references.
                arg = _split_top_level(
                    _call_arg_span(text, m.start()), ","
                )[0]
                # Literals inside the key argument are usage whatever the
                # verdict below — a ternary branch or a map fallback still
                # names a key.
                for lm in _KEY_LITERAL_RE.finditer(arg):
                    pairs = declared.by_flat.get(lm.group(2)) or \
                        declared.by_bare.get(lm.group(2))
                    if pairs:
                        used |= pairs
                if _is_static_choice_of_literals(arg):
                    continue  # every producible value is a literal
                if not _statement_mentions_keys_map(text, m.start()):
                    report.dynamic.append(UsageFinding(
                        kind="dynamic-ref",
                        site=f"{rel}:{_line_of(text, m.start())}",
                        detail="str/tpl/getString/plural(<expression>) "
                               "with no *_STRING_KEYS on the statement",
                    ))
        elif face == "ios":
            for m in _IOS_ACCESSOR_RE.finditer(text):
                pairs = declared.by_accessor.get((m.group(1), m.group(2)))
                if pairs:
                    used |= pairs
                # unmatched: a compile error on iOS, and StringManager
                # also has non-accessor members — not reported here
            for m in _IOS_LOCALIZED_RE.finditer(text):
                pairs = declared.by_flat.get(m.group(2))
                if pairs:
                    used |= pairs
                # unmatched: usage only. The SwiftUI generator emits this
                # form for sentinel vocabulary too (a visibility's "gone"),
                # so absence here does not mean a broken key reference.
            for regex, form in (
                (_IOS_NSLOCALIZED_RE, "NSLocalizedString"),
                (_IOS_STRING_LOCALIZED_RE, "String(localized:)"),
            ):
                for m in regex.finditer(text):
                    key = m.group(2)
                    pairs = declared.by_flat.get(key) or declared.by_bare.get(key)
                    if pairs:
                        used |= pairs
                    elif key not in catalog_keys:
                        report.missing.append(UsageFinding(
                            kind="missing-key",
                            site=f"{rel}:{_line_of(text, m.start())}",
                            detail=(
                                f"{form}({key!r}) resolves in neither "
                                "strings.json nor the platform string "
                                "catalogs — the raw key reaches the screen"
                            ),
                        ))
        elif face == "android":
            for m in _ANDROID_R_STRING_RE.finditer(text):
                pairs = declared.by_flat.get(m.group(1))
                if pairs:
                    used |= pairs
                # unmatched: plain Android resources share R.string,
                # and a truly absent symbol fails Android compile


def collect_layout_used(
    trees: dict[str, Any],
    own_sections_by_layout: dict[str, tuple[str, ...]],
    declared: DeclaredKeys,
) -> set[tuple[str, str]]:
    """Every declared pair some layout string could be read as.

    Broader than the raw-literal scan on purpose: list items and non
    string-prop positions resolve through the builders' items/label
    paths, and a missed reference here becomes a false unused finding.
    """
    used: set[tuple[str, str]] = set()

    def walk(node: Any, own: tuple[str, ...]) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value, own)
        elif isinstance(node, list):
            for item in node:
                walk(item, own)
        elif isinstance(node, str):
            if "@{" in node or node.startswith("${"):
                return
            used.update(declared.layout_targets(node, own))

    for rel, tree in trees.items():
        walk(tree, own_sections_by_layout.get(rel, ()))
    return used


def collect_spec_branch_used(
    spec_dir: Path,
    declared: DeclaredKeys,
    report: UsageReport,
    used: set[tuple[str, str]],
    harness_keys: set[str] | None = None,
) -> None:
    """`@strings_key` references declared in branchContracts.

    validate checks the shape of these references but cannot check that
    the key exists — it does not know where the strings table lives. Here
    it is already known, and a branch asserting a key nothing declares
    fails only when someone runs the generated test.

    A branch may also assert a *pseudo* key that the test harness formats
    into a real one (`..._step_0_of_10` for a table entry carrying
    placeholders), which by design never appears in strings.json. Those
    are recognised through the same closure the rest of this check relies
    on: a harness that resolves keys dynamically declares them in a
    `*_STRING_KEYS` map. A reference in neither place is a typo.
    """
    harness_keys = harness_keys or set()
    if not spec_dir.is_dir():
        return
    for spec_file in sorted(spec_dir.rglob("*.spec.json")):
        try:
            spec = json.loads(spec_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        contracts = spec.get("branchContracts") if isinstance(spec, dict) else None
        if not isinstance(contracts, dict):
            continue
        seen: set[str] = set()

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)
            elif isinstance(node, str) and node.startswith("@"):
                ref = node[1:]
                if ref and not ref.startswith("data.") and "." not in ref:
                    seen.add(ref)

        walk(contracts)
        for ref in sorted(seen):
            pairs = declared.by_flat.get(ref) or declared.by_bare.get(ref)
            if pairs:
                used |= pairs
            elif ref not in harness_keys:
                report.missing.append(UsageFinding(
                    kind="missing-key",
                    site=spec_file.as_posix(),
                    detail=(
                        f"branchContracts references '@{ref}', which neither "
                        "strings.json nor a *_STRING_KEYS map declares"
                    ),
                ))


def collect_usage(
    *,
    strings_groups: dict[str, dict[str, Any]],
    trees: dict[str, Any],
    own_sections_by_layout: dict[str, tuple[str, ...]],
    platform_roots: dict[str, Path],
    spec_dir: Path | None = None,
) -> UsageReport:
    """Aggregate the used set over every face, then judge both directions.

    *platform_roots* holds only the faces the project declares; a face
    with no configured root simply contributes nothing (its absence is
    the project's shape, not a scanning gap).
    """
    declared = DeclaredKeys(strings_groups)
    report = UsageReport()
    report.faces = ["layout"] + sorted(platform_roots)

    used = collect_layout_used(trees, own_sections_by_layout, declared)
    harness_keys: set[str] = set()
    for face in sorted(platform_roots):
        scan_vm_sources(
            face, platform_roots[face], declared, report, used, harness_keys
        )
    if spec_dir is not None:
        report.faces.append("spec")
        collect_spec_branch_used(
            spec_dir, declared, report, used, harness_keys
        )

    for section, key in sorted(declared.pairs - used):
        report.unused.append(UsageFinding(
            kind="unused-key",
            site=f"{section}.{key}",
            detail="",
        ))
    report.missing.sort(key=lambda f: (f.site, f.detail))
    report.dynamic.sort(key=lambda f: (f.site, f.detail))
    return report
