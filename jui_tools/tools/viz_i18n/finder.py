"""Where the view's parts still say something in Japanese (ticket 2026-10-21-jui-viz-language-switch-ja-en).

Comments are not counted: they are for the people who read the code, not words on the page. What is counted, by kind:

- .js: strings, templates, regex literals and code. Comments are // to the line's end and /* … */, skipped only
  where no string is open; a ' or " string ends at its line (a quote inside a regex opens nothing).
- .html: everything but <!-- … --> (text, attributes, titles).
- .css: everything but /* … */ (``content:`` words).

Used by the gate (tests/test_viz_i18n.py) and by the mover (move.py).
"""
from __future__ import annotations

import re

JA = re.compile(r"[぀-ヿ㐀-鿿！-｠]")


def _js(text: str) -> list[int]:
    out, i, n, quote = [], 0, len(text), None
    while i < n:
        c = text[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote or (c == "\n" and quote != "`"):
                quote = None
            elif JA.match(c):
                out.append(i)
        elif text.startswith("//", i):
            i = text.find("\n", i)
            i = n if i < 0 else i
            continue
        elif text.startswith("/*", i):
            i = text.find("*/", i + 2)
            i = n if i < 0 else i + 2
            continue
        elif c in "'\"`":
            quote = c
        elif c == "/" and re.search(r"(^|[(,=:\[!&|?{};+\-*%<>~^]|\breturn)\s*$", text[max(0, i - 40):i]):
            # a regex literal (where a value starts): its Japanese is code, a quote in it opens nothing
            j, in_class = i + 1, False
            while j < n and text[j] != "\n" and (in_class or text[j] != "/"):
                in_class = (in_class or text[j] == "[") and text[j] != "]"
                j += 2 if text[j] == "\\" else 1
            out.extend(k for k in range(i, min(j, n)) if JA.match(text[k]))
            i = j + 1
            continue
        elif JA.match(c):
            out.append(i)
        i += 1
    return out


def _outside(text: str, start: str, end: str) -> list[int]:
    """Japanese positions outside start … end (comments)."""
    out, i = [], 0
    for m in re.finditer(re.escape(start) + r".*?" + re.escape(end), text, re.S):
        out.extend(k for k in range(i, m.start()) if JA.match(text[k]))
        i = m.end()
    out.extend(k for k in range(i, len(text)) if JA.match(text[k]))
    return out


def positions(name: str, text: str) -> list[int]:
    """The offsets of the Japanese a part says, by its kind (its name's extension)."""
    if name.endswith(".js"):
        return _js(text)
    if name.endswith(".html"):
        return _outside(text, "<!--", "-->")
    if name.endswith(".css"):
        return _outside(text, "/*", "*/")
    raise ValueError(f"{name}: not a .js, .html or .css part")


def chars(name: str, text: str) -> list[str]:
    return [text[k] for k in positions(name, text)]


def runs(name: str, text: str) -> list[str]:
    """The Japanese as runs: characters next to each other, each run one piece of words."""
    out: list[str] = []
    last = -2
    for k in positions(name, text):
        if k == last + 1:
            out[-1] += text[k]
        else:
            out.append(text[k])
        last = k
    return out


def lines(name: str, text: str) -> list[tuple[int, str]]:
    """(line number, line) for each line that says Japanese."""
    at = sorted({text.count("\n", 0, k) for k in positions(name, text)})
    all_lines = text.split("\n")
    return [(n + 1, all_lines[n]) for n in at]
