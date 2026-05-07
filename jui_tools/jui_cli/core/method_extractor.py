"""Extract `// @jui:protocol` marker blocks + their paired declarations.

Supported grammar::

    // @jui:<group>(.<modifier>)?[ <signature>]

In v1.0 only ``group == "protocol"`` is recognised; unknown groups are
silently skipped so v1.1 additions (``@jui:protocol.doc`` etc.) don't break
older tools.

Consecutive ``// @jui:protocol`` lines form a single block — their payloads
are joined with ``\\n`` preserving internal indentation so multi-line
signatures (``@MainActor`` attributes, multi-line generics) round-trip
verbatim into the Protocol body.

After each block we scan forward for the paired declaration:
    - skip blank lines
    - skip attribute lines (``@MainActor``, ``@JvmStatic``, ``@Composable``)
    - skip doc comments (``///``, ``/** */``, ``//``, ``/* */``)
    - skip conditional/section markers (``#if``, ``// MARK:``, ``// TODO:``)

The first non-skip line must be a ``func``/``fun`` or ``var``/``val``/``let``
declaration. ``kind`` on the returned ``MarkerBlock`` distinguishes method
("func"/"fun") from property ("var"/"val"/"let"). If we cross a class/struct
boundary or run off the file first, that's an ``ExtractionError``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator


class ExtractionError(Exception):
    """Raised when a marker block can't be paired with a declaration."""


@dataclass
class MarkerBlock:
    signature: str
    marker_start_line: int  # 1-indexed, first `// @jui:protocol` line
    marker_end_line: int    # 1-indexed, last `// @jui:protocol` line
    decl_line: int          # 1-indexed, line holding the declaration
    decl_raw: str           # the raw declaration line (for override-injection)
    kind: str = "method"    # "method" (func/fun) | "var" (var/val/let)


# A single "marker" line: `// @jui:<group>(.<modifier>)? [payload]`.
# Captures: (1) group, (2) modifier (optional), (3) payload (optional).
MARKER_LINE_RE = re.compile(
    r"^[ \t]*//[ \t]*@jui:(?P<group>[A-Za-z_][\w]*)"
    r"(?:\.(?P<modifier>[A-Za-z_][\w]*))?"
    r"(?:[ \t]+(?P<payload>.*?))?[ \t]*$"
)

# Attribute line: `@Ident(...)` possibly with args. Must match the *first*
# non-blank token only — we don't parse the attribute body.
ATTRIBUTE_LINE_RE = re.compile(r"^[ \t]*@[A-Za-z_][\w.]*\b")

# Conditional / section markers that sit between marker and declaration.
CONDITIONAL_LINE_RE = re.compile(
    r"^[ \t]*(?:#if\b|#else\b|#elseif\b|#endif\b|//[ \t]*MARK:|//[ \t]*TODO:|//[ \t]*FIXME:)"
)

# Declaration starters, in order of specificity.
# Kotlin: (public/internal/private/protected)? (override)? (suspend)? (inline/operator/infix/tailrec)? fun
# Swift:  (public/internal/private/fileprivate/open)? (override)? (static/class/final)? func
_COMMON_MODS = (
    r"(?:(?:public|internal|private|protected|fileprivate|open)\s+)?"
    r"(?:override\s+)?"
    r"(?:(?:suspend|static|class|final|inline|operator|infix|tailrec|lateinit|abstract|open)\s+)*"
    r"(?:override\s+)?"
    r"(?:(?:suspend|static|class|final|lateinit)\s+)*"
)

DECL_LINE_RE = re.compile(
    r"^[ \t]*" + _COMMON_MODS + r"(?:func|fun)\s+(?:<[^>]+>\s+)?\w"
)

# Var/val/let with optional property wrappers (Swift @Published / @State /
# Combine, Kotlin @JvmField / @Volatile).
VAR_LINE_RE = re.compile(
    r"^[ \t]*"
    r"(?:@\w+(?:\([^)]*\))?\s+)*"  # swallow any leading @Wrappers
    + _COMMON_MODS +
    r"(?:var|val|let)\s+\w"
)

# Class/struct/object/protocol/interface boundary — hitting one of these while
# searching for a declaration is a hard error (marker was orphaned).
CLASS_BOUNDARY_RE = re.compile(
    r"^[ \t]*"
    r"(?:(?:public|internal|private|protected|fileprivate|open|abstract|"
    r"sealed|data|value|inner|final)\s+)*"
    r"(?:class|struct|object|enum|protocol|interface)\s+\w"
)


def _strip_bom(source: str) -> str:
    if source.startswith("\ufeff"):
        return source[1:]
    return source


def _iter_lines_with_numbers(source: str) -> Iterator[tuple[int, str]]:
    """Yield (1-indexed line number, content without trailing newline)."""
    # splitlines() handles CRLF/CR/LF uniformly and discards the separator.
    for i, line in enumerate(source.splitlines(), start=1):
        yield i, line


def extract_marker_blocks(source: str) -> list[MarkerBlock]:
    """Scan *source* and return one ``MarkerBlock`` per ``@jui:protocol``
    sequence paired with its declaration.

    Raises ``ExtractionError`` if a marker can't be paired with a declaration
    before a class/struct boundary or EOF.
    """
    source = _strip_bom(source)
    lines = list(_iter_lines_with_numbers(source))
    n = len(lines)
    blocks: list[MarkerBlock] = []

    i = 0
    while i < n:
        lineno, content = lines[i]
        m = MARKER_LINE_RE.match(content)
        # Skip anything that isn't a bare `@jui:protocol` marker. That
        # includes unknown groups (`@jui:internal`) and reserved modifier
        # variants (`@jui:protocol.doc` in v1.1) — they're silent no-ops.
        if (not m
                or m.group("group") != "protocol"
                or m.group("modifier")):
            i += 1
            continue

        # Gather consecutive `@jui:protocol` lines.
        block_start = lineno
        block_end = lineno
        block_payloads: list[str] = []
        while i < n:
            cur_lineno, cur_content = lines[i]
            cm = MARKER_LINE_RE.match(cur_content)
            if not cm or cm.group("group") != "protocol" or cm.group("modifier"):
                break
            block_payloads.append(cm.group("payload") or "")
            block_end = cur_lineno
            i += 1

        # Find the paired declaration.
        decl_idx, decl_kind = _find_paired_decl(lines, i, block_start)
        decl_lineno, decl_raw = lines[decl_idx]

        signature = _build_signature(block_payloads, kind=decl_kind)

        blocks.append(MarkerBlock(
            signature=signature,
            marker_start_line=block_start,
            marker_end_line=block_end,
            decl_line=decl_lineno,
            decl_raw=decl_raw,
            kind=decl_kind,
        ))

        # Advance past the declaration — nested markers inside the same body
        # are not supported in v1.0.
        i = decl_idx + 1

    return blocks


def _find_paired_decl(
    lines: list[tuple[int, str]],
    start_idx: int,
    block_start_lineno: int,
) -> tuple[int, str]:
    """Return ``(index, kind)`` for the declaration paired with a marker block.

    ``kind`` is ``"method"`` (func/fun) or ``"var"`` (var/val/let).
    Skips blank/attribute/doc-comment/conditional lines.
    """
    n = len(lines)
    j = start_idx
    while j < n:
        lineno, content = lines[j]
        stripped = content.strip()

        if not stripped:
            j += 1
            continue

        # doc/single/multi-line comments — skip
        if stripped.startswith("///") or stripped.startswith("/**") or \
           stripped.startswith("/*") or stripped.startswith("*"):
            j += 1
            continue

        if CONDITIONAL_LINE_RE.match(content):
            j += 1
            continue

        # Plain `//` comment, but not one of our markers — skip.
        if stripped.startswith("//"):
            j += 1
            continue

        # A line like `@Published var x` needs to be caught as a var decl
        # *before* the attribute-line skip — property wrappers are inline
        # with their declarations. Same for `@MainActor func foo()`.
        if VAR_LINE_RE.match(content):
            return j, "var"
        if DECL_LINE_RE.match(content):
            return j, "method"

        # Standalone attribute line (e.g. `@MainActor` on its own) — skip.
        if ATTRIBUTE_LINE_RE.match(content):
            j += 1
            continue

        if CLASS_BOUNDARY_RE.match(content):
            raise ExtractionError(
                f"@jui:protocol block at line {block_start_lineno} crosses a "
                f"class/struct/interface boundary at line {lineno} without a "
                f"matching func/fun/var declaration."
            )

        raise ExtractionError(
            f"@jui:protocol block at line {block_start_lineno} is not followed "
            f"by a func/fun/var declaration (found at line {lineno}: {content!r})."
        )

    raise ExtractionError(
        f"@jui:protocol block at line {block_start_lineno} has no following "
        f"declaration (reached end of file)."
    )


def _build_signature(payloads: list[str], *, kind: str = "method") -> str:
    """Join marker payloads into a single verbatim signature.

    - Single-line block: ``rstrip`` and return.
    - Multi-line block: preserve each line's indentation relative to the
      first payload, join with ``\\n``, then strip a leading ``override ``
      (Kotlin-only; Protocol declarations don't take ``override``).

    For ``kind == "var"`` we also normalise Swift ``@Published var`` ->
    ``var { get set }`` style when emitting into the Protocol — but that's
    the generator's job. Here we only strip ``override`` and property
    wrappers so the raw var signature lands in the marker output cleanly.
    """
    if not payloads:
        return ""
    if len(payloads) == 1:
        sig = payloads[0].rstrip()
    else:
        sig = "\n".join(p.rstrip() for p in payloads)

    # Drop a leading `override ` (Kotlin var/fun conformance doesn't belong
    # in the Protocol).
    sig = re.sub(r"^override\s+", "", sig)
    return sig
