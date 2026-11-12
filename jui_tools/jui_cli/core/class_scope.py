"""Which lines of a hand-written ViewModel declare a member of its class.

Protocol sync reads and rewrites the Impl by name: it counts the vars and functions the class declares, and on
Kotlin puts ``override`` on the ones the protocol declares. It used to take every line that started with
``val <name>`` / ``fun <name>`` anywhere in the file, so a local ``val plan = …`` in a function body became
``override val plan`` and Kotlin refused it (ticket jui-kotlin-override-inserted-on-local-val); so did a local
function, a member of a nested class or companion object or anonymous object, and a line inside a raw string or a
block comment. Each of those also counted as the class declaring the name.

:func:`member_lines` answers it from the source's structure, not its indentation: strings and comments are masked
(Kotlin ``"…"``, ``\"\"\"…\"\"\"`` with ``${…}`` templates, char literals, nested ``/* */``; Swift ``"…"``, multi-line,
raw ``#"…"#`` with ``\\(…)`` interpolation), then the class body is found by its braces. A line declares a member
when its first character of code sits directly in that body (or, on Kotlin, directly in the primary constructor's
parentheses, where ``val``/``var`` parameters are properties). Swift ``extension <Class>`` bodies count too: their
members satisfy the protocol as the class's own do.
"""
from __future__ import annotations

import re

_KOTLIN = "kotlin"
_SWIFT = "swift"


def _mask(source: str, language: str) -> list[bool]:
    """True for each character inside a string literal or a comment."""
    n = len(source)
    masked = [False] * n
    # Frames: ("code", closer, depth) — closer is "}" for a Kotlin template, ")" for a Swift interpolation, None at
    # the top; ("str", end, raw, hashes); ("block", nesting).
    stack: list[tuple] = [("code", None, 0)]
    i = 0

    def mark(a: int, b: int) -> None:
        for k in range(a, min(b, n)):
            masked[k] = True

    while i < n:
        frame = stack[-1]
        c = source[i]
        if frame[0] == "block":
            if source.startswith("/*", i):
                stack[-1] = ("block", frame[1] + 1)
                mark(i, i + 2)
                i += 2
            elif source.startswith("*/", i):
                mark(i, i + 2)
                i += 2
                if frame[1] == 1:
                    stack.pop()
                else:
                    stack[-1] = ("block", frame[1] - 1)
            else:
                masked[i] = True
                i += 1
            continue
        if frame[0] == "str":
            _, end, raw, hashes = frame
            if source.startswith(end, i):
                mark(i, i + len(end))
                i += len(end)
                stack.pop()
                continue
            if language == _KOTLIN:
                if not raw and c == "\\":
                    mark(i, i + 2)
                    i += 2
                    continue
                if c == "\n" and end == '"':
                    stack.pop()   # an unterminated one-line string: stop at the line's end
                    continue
                if source.startswith("${", i):
                    mark(i, i + 2)
                    i += 2
                    stack.append(("code", "}", 0))
                    continue
            else:
                escape = "\\" + "#" * hashes
                if source.startswith(escape + "(", i):
                    mark(i, i + len(escape) + 1)
                    i += len(escape) + 1
                    stack.append(("code", ")", 0))
                    continue
                if source.startswith(escape, i):
                    mark(i, i + len(escape) + 1)
                    i += len(escape) + 1
                    continue
                if c == "\n" and not end.startswith('"""'):
                    stack.pop()   # an unterminated one-line string: stop at the line's end
                    continue
            masked[i] = True
            i += 1
            continue
        # code
        _, closer, depth = frame
        inside = closer is not None   # template / interpolation code is part of the string: masked
        if source.startswith("//", i):
            j = source.find("\n", i)
            j = n if j < 0 else j
            mark(i, j)
            i = j
            continue
        if source.startswith("/*", i):
            mark(i, i + 2)
            stack.append(("block", 1))
            i += 2
            continue
        if language == _KOTLIN:
            if source.startswith('"""', i):
                mark(i, i + 3)
                stack.append(("str", '"""', True, 0))
                i += 3
                continue
            if c == '"':
                masked[i] = True
                stack.append(("str", '"', False, 0))
                i += 1
                continue
            if c == "'":
                m = re.match(r"'(?:\\u[0-9a-fA-F]{4}|\\.|[^'\\\n])'", source[i:i + 8])
                if m:
                    mark(i, i + m.end())
                    i += m.end()
                    continue
        else:
            m = re.match(r'(#*)("""|")', source[i:i + 64])
            if m and (m.group(1) or c == '"'):
                hashes = len(m.group(1))
                quote = m.group(2)
                mark(i, i + m.end())
                stack.append(("str", quote + "#" * hashes, hashes > 0, hashes))
                i += m.end()
                continue
        if inside:
            masked[i] = True
            opener = "{" if closer == "}" else "("
            if c == opener:
                stack[-1] = ("code", closer, depth + 1)
            elif c == closer:
                if depth == 0:
                    stack.pop()
                else:
                    stack[-1] = ("code", closer, depth - 1)
        i += 1
    return masked


def _class_regions(source: str, masked: list[bool], class_name: str, language: str) -> list[tuple[int, int, str]]:
    """(start, end, kind) character ranges: "body" for the class's (and Swift extensions') brace bodies, "ctor" for a
    Kotlin primary constructor's parentheses (both exclusive of their delimiters)."""
    code = "".join(" " if m else ch for ch, m in zip(source, masked))
    keywords = "class" if language == _KOTLIN else "class|extension"
    regions: list[tuple[int, int, str]] = []
    for m in re.finditer(rf"\b(?:{keywords})\s+{re.escape(class_name)}\b", code):
        i, paren, ctor_open = m.end(), 0, None
        body_open = None
        while i < len(code):
            ch = code[i]
            if ch == "(":
                if paren == 0 and ctor_open is None and language == _KOTLIN:
                    ctor_open = i
                paren += 1
            elif ch == ")":
                paren -= 1
                if paren == 0 and ctor_open is not None and not any(r[0] == ctor_open + 1 for r in regions):
                    regions.append((ctor_open + 1, i, "ctor"))
            elif ch == "{" and paren == 0:
                body_open = i
                break
            elif ch == "}" and paren == 0:
                break   # a class without a body, followed by the end of an enclosing one
            i += 1
        if body_open is None:
            continue
        depth, j = 0, body_open
        while j < len(code):
            if code[j] == "{":
                depth += 1
            elif code[j] == "}":
                depth -= 1
                if depth == 0:
                    regions.append((body_open + 1, j, "body"))
                    break
            j += 1
    return regions


def member_lines(source: str, class_name: str, language: str) -> set[int] | None:
    """0-based indexes of the lines that start a declaration directly in *class_name* (see the module docstring).
    None when the class is not found, so a caller can keep its whole-file reading rather than report every member
    missing."""
    masked = _mask(source, language)
    regions = _class_regions(source, masked, class_name, language)
    if not any(kind == "body" for _, _, kind in regions):
        return None
    lines: set[int] = set()
    starts = [0] + [m.end() for m in re.finditer(r"\n", source)]
    for start, end, kind in regions:
        # Depth of braces / parens relative to the region's opening, counted over code only.
        brace = paren = 0
        line_idx = _line_of(starts, start)
        pos = start
        while pos < end:
            ch = source[pos]
            if ch == "\n":
                line_idx += 1
                first = _first_code(source, pos + 1, end)
                if first is not None and not masked[first]:
                    b, p = _depth_between(source, masked, pos + 1, first, brace, paren)
                    if b == 0 and p == 0:
                        lines.add(line_idx)
            elif not masked[pos]:
                if ch == "{":
                    brace += 1
                elif ch == "}":
                    brace -= 1
                elif ch in "([":
                    paren += 1
                elif ch in ")]":
                    paren -= 1
            pos += 1
        # The region's own first line, when a declaration follows the opening on it (`class A { val x = 1`).
        first = _first_code(source, start, end)
        if first is not None and not masked[first] and "\n" not in source[start:first]:
            lines.add(_line_of(starts, start))
    return lines


def _line_of(starts: list[int], pos: int) -> int:
    lo, hi = 0, len(starts) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if starts[mid] <= pos:
            lo = mid
        else:
            hi = mid - 1
    return lo


def _first_code(source: str, pos: int, end: int) -> int | None:
    """Position of the first non-blank character of the line starting at *pos*, if it is before *end*."""
    while pos < end and source[pos] in " \t\r":
        pos += 1
    if pos >= end or source[pos] == "\n":
        return None
    return pos


def _depth_between(source, masked, a, b, brace, paren):
    for k in range(a, b):
        if masked[k]:
            continue
        ch = source[k]
        if ch == "{":
            brace += 1
        elif ch == "}":
            brace -= 1
        elif ch in "([":
            paren += 1
        elif ch in ")]":
            paren -= 1
    return brace, paren


def member_filter(source: str, class_name: str | None, language: str):
    """A predicate over character offsets: True when the offset is on a line :func:`member_lines` keeps. Everything
    passes when *class_name* is None or the class is not found (the reading before this module)."""
    if class_name is None:
        return lambda pos: True
    lines = member_lines(source, class_name, language)
    if lines is None:
        return lambda pos: True
    starts = [0] + [m.end() for m in re.finditer(r"\n", source)]
    return lambda pos: _line_of(starts, pos) in lines
