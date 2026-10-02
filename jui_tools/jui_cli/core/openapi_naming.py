"""Naming utilities shared by API model generators.

- ``snake_to_camel``: ``display_name`` → ``displayName``
- ``snake_to_pascal``: ``display_name`` → ``DisplayName``
- ``camel_to_lower``: ``HTTPResponse`` → ``httpResponse`` (per plan §2.2)
- ``escape_keyword``: language-specific reserved word handling
- ``resolve_enum_case_for_default``: match a swagger ``default`` value to its
  enum case identifier (used by per-platform default literal emitters)

The factory function naming rule from plan §2.2 — ``{camelCaseName}FromDto`` —
is implemented in :func:`factory_name`, with the special-case of leading
consecutive uppercase letters down-cased to only the first character
(``HTTPResponse`` → ``httpResponseFromDto``).
"""
from __future__ import annotations

import re
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .schema_ir import EnumDef

# Reserved-word tables. Generators consult the relevant set when emitting
# field / case / variable names. We err on the side of escaping anything
# that *could* parse as a keyword in any version of the language (e.g.
# Swift `actor` since 5.5, Kotlin `value class` etc.).

SWIFT_RESERVED: frozenset[str] = frozenset({
    # Declaration keywords
    "associatedtype", "class", "deinit", "enum", "extension", "fileprivate",
    "func", "import", "init", "inout", "internal", "let", "open", "operator",
    "private", "protocol", "public", "rethrows", "static", "struct",
    "subscript", "typealias", "var",
    # Statement keywords
    "break", "case", "continue", "default", "defer", "do", "else", "fallthrough",
    "for", "guard", "if", "in", "repeat", "return", "switch", "where", "while",
    # Expression keywords
    "as", "catch", "false", "is", "nil", "rethrows", "super", "self", "Self",
    "throw", "throws", "true", "try",
    # Pattern keywords (context-sensitive but still safer to escape)
    "_",
    # Modern additions
    "actor", "async", "await", "any", "some",
})

KOTLIN_RESERVED: frozenset[str] = frozenset({
    "as", "break", "class", "continue", "do", "else", "false", "for", "fun",
    "if", "in", "interface", "is", "null", "object", "package", "return",
    "super", "this", "throw", "true", "try", "typealias", "val", "var",
    "when", "while",
    # Soft keywords (context-sensitive)
    "by", "catch", "constructor", "delegate", "dynamic", "field", "file",
    "finally", "get", "import", "init", "param", "property", "receiver",
    "set", "setparam", "value", "where",
})

# TypeScript reserved words at the field / type level. The set is small
# because TS allows almost any identifier as a property name when quoted.
# We only escape genuine keywords that would cause a parse error in
# destructuring or interface position.
TYPESCRIPT_RESERVED: frozenset[str] = frozenset({
    "break", "case", "catch", "class", "const", "continue", "debugger",
    "default", "delete", "do", "else", "enum", "export", "extends", "false",
    "finally", "for", "function", "if", "import", "in", "instanceof", "new",
    "null", "return", "super", "switch", "this", "throw", "true", "try",
    "typeof", "var", "void", "while", "with",
})


_SNAKE_PARTS_RE = re.compile(r"[_\s-]+")
_LEADING_CAPS_RE = re.compile(r"^[A-Z]+(?=[A-Z][a-z]|$)")


def snake_to_pascal(name: str) -> str:
    """``display_name`` / ``display-name`` / ``displayName`` → ``DisplayName``.

    Idempotent: ``DisplayName`` → ``DisplayName``. Handles mixed input
    that already contains a mix of cases.
    """
    if not name:
        return name
    # If the input is already CamelCase-ish (no separators), capitalize the
    # first letter and return — preserves internal acronyms like ``HTTPResponse``.
    if not _SNAKE_PARTS_RE.search(name):
        return name[:1].upper() + name[1:]
    parts = [p for p in _SNAKE_PARTS_RE.split(name) if p]
    return "".join(p[:1].upper() + p[1:] for p in parts)


def snake_to_camel(name: str) -> str:
    """``display_name`` → ``displayName``.

    Preserves leading consecutive uppercase via the plan §2.2 rule:
    ``HTTPResponse`` → ``httpResponse`` (first letter only down-cased).
    """
    if not name:
        return name
    if _SNAKE_PARTS_RE.search(name):
        pascal = snake_to_pascal(name)
        return pascal[:1].lower() + pascal[1:]
    # Already CamelCase / camelCase — apply leading caps rule.
    return _down_case_leading_caps(name)


def _down_case_leading_caps(name: str) -> str:
    """Down-case the first letter only, even when leading caps form an acronym.

    ``HTTPResponse`` → ``httpResponse``
    ``URL`` → ``uRL`` (degenerate but consistent — caller can opt out for
    pure acronyms by leaving them in snake_case)
    ``displayName`` → ``displayName``
    """
    if not name:
        return name
    return name[:1].lower() + name[1:]


def factory_name(schema_name: str) -> str:
    """Web factory function name. ``UserProfile`` → ``userProfileFromDto``.

    Implements the v3 plan §2.2 contract:

    - Take the schema's PascalCase name as input
    - Down-case the leading consecutive uppercase block to a single lower
      character (``HTTPResponse`` → ``httpResponse``)
    - Append ``FromDto``

    Codegen calls this without an override hook — the rule is intentionally
    machine-applied for cross-schema consistency.
    """
    camel = _down_case_leading_caps(snake_to_pascal(schema_name))
    return f"{camel}FromDto"


def resolve_enum_case_for_default(enum: "EnumDef", value: Any) -> str | None:
    """Find the case identifier of *enum* that matches *value*, or None.

    Used by per-platform default literal emitters to translate a swagger
    ``default: "favorite"`` on an enum-typed field into the platform-native
    enum case reference (``ReactionType.FAVORITE`` / ``ReactionType.favorite``)
    instead of a string literal — which would be a compile-time type
    mismatch on Swift and Kotlin.

    Returns the **raw case name** (as stored in :attr:`EnumDef.case_names`).
    Callers must apply their language's identifier transform (Kotlin
    SCREAMING_SNAKE, Swift camelCase, keyword escape) themselves.

    Returns ``None`` when the swagger ``default`` does not match any case —
    that's a schema bug; the emitter skips the default rather than halting
    so the decoder fills the field at runtime.
    """
    from .schema_ir import PrimitiveKind

    if enum.kind == PrimitiveKind.STRING and isinstance(value, str):
        for case_name, raw in zip(enum.case_names, enum.string_values):
            if raw == value:
                return case_name
        return None
    if enum.kind == PrimitiveKind.INTEGER and isinstance(value, int) and not isinstance(value, bool):
        for case_name, raw_int in zip(enum.case_names, enum.integer_values):
            if raw_int == value:
                return case_name
    return None


def escape_keyword(name: str, *, language: str) -> str:
    """Escape *name* if it collides with a *language* reserved word.

    Swift / Kotlin use backticks (`` `private` ``). TypeScript declarations
    can use the keyword as a property name when quoted (``"if": string``),
    but for emitted identifiers we still avoid them — callers should
    prefer string-keyed declarations when emitting interfaces.

    Idempotent: passing an already-escaped name through again is a no-op
    (the function checks the unwrapped form).
    """
    if not name:
        return name
    bare = name.strip("`")
    table = {
        "swift": SWIFT_RESERVED,
        "kotlin": KOTLIN_RESERVED,
        "typescript": TYPESCRIPT_RESERVED,
    }.get(language)
    if not table:
        return name
    if bare in table:
        if language in ("swift", "kotlin"):
            return f"`{bare}`"
        # TypeScript: caller already gets the quoted form via interface
        # property syntax; return the name as-is for callers that handle
        # it elsewhere.
        return name
    return name


# --------------------------------------------------------------------------- #
# Enum case identifiers (jui-api-model-swift-negative-integer-enum-cases-collide)
# --------------------------------------------------------------------------- #

# A minus sign that starts a number — at the start of the name or after a
# word separator — is spelled ``minus``: the integer enum value -1 gets the
# default case name ``value_-1`` (openapi_loader), which reads as
# ``value_minus_1`` → Swift ``valueMinus1``, Kotlin ``VALUE_MINUS_1``. TS
# emits the values themselves (``-1 | 0 | 1``) and names no case. Through
# jsonui-cli 1.9.5 Swift dropped the sign (``value_-1`` and ``value_1`` were
# both ``value1``: the enum did not compile) and Kotlin kept it as a second
# underscore (``VALUE__1``).
_NUMBER_MINUS_RE = re.compile(r"(^|[_\s-])-(?=\d)")


def enum_case_source(case_name: str) -> str:
    """The case name with a number's minus sign spelled ``minus_``."""
    return _NUMBER_MINUS_RE.sub(lambda m: f"{m.group(1)}minus_", case_name)


_ASCII_NON_WORD_RE = re.compile(r"[\x00-\x2f\x3a-\x40\x5b-\x5e\x60\x7b-\x7f]")


def enum_case_problems(raw_values: list, identifiers: list[str]) -> list[str]:
    """What keeps the emitted case identifiers from compiling, one line each.

    ``identifiers`` are the emitted names in value order (backticks allowed);
    an empty result means every name is a distinct identifier. Conservative on
    purpose — it rejects only what no Swift / Kotlin compiler accepts, so a
    name that compiles today is never refused: an empty name, a name of
    underscores only, a leading digit, an ASCII character other than a
    letter, a digit or ``_``, and two values that get one name (after the
    naming rules: ``active`` / ``ACTIVE``, ``foo_bar`` / ``fooBar``).
    """
    problems: list[str] = []
    seen: dict[str, object] = {}
    for raw, ident in zip(raw_values, identifiers):
        bare = ident.strip("`")
        if not bare or set(bare) == {"_"}:
            problems.append(f"{raw!r} gets no name ({ident!r})")
            continue
        if bare[0].isdigit() or _ASCII_NON_WORD_RE.search(bare):
            problems.append(f"{raw!r} gets {ident!r}, which is no identifier")
            continue
        if bare in seen:
            problems.append(f"{seen[bare]!r} and {raw!r} both get {ident!r}")
        else:
            seen[bare] = raw
    return problems


def check_enum_case_identifiers(enum, identifiers: list[str], *, language: str, source: str = "") -> None:
    """Stop the build on an enum whose case names cannot compile.

    The generator writes the names and the compiler is the next to read
    them; a name two values share, or one that is no identifier, is caught
    here, by name, instead of as ``invalid redeclaration`` in the app's
    build (jui-api-model-swift-negative-integer-enum-cases-collide: 7 Swift
    files, rc 65, with jui build at warning 0).
    """
    from .openapi_loader import OpenAPILoadError

    raw_values = enum.string_values if enum.string_values else enum.integer_values
    problems = enum_case_problems(list(raw_values), identifiers)
    if problems:
        raise OpenAPILoadError(
            "enum-case-names",
            f"Enum '{enum.name}' ({language}): "
            + "; ".join(problems)
            + ". Name the cases with x-enum-varnames on the schema "
            "(one name per value, in order).",
            source=source,
            pointer=f"#/components/schemas/{enum.name}",
        )
