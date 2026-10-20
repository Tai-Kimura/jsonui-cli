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


#: The words as written beside a key, kept for a table that lacks it (the gate holds them to the Japanese table):
#: index.html's {{tl:key}}…{{/tl}} (viz/i18n.py fill_words) and app.css's var(--tl-name, '…') (web/js/05-i18n.js).
HTML_MARK = re.compile(r"\{\{(?:tl|tlhtml):([\w.\-]+)\}\}(.*?)\{\{/tl\}\}", re.S)
CSS_MARK = re.compile(r"var\(--tl-([\w-]+),\s*'((?:\\.|[^'\\])*)'\s*\)")


def marks(name: str, text: str) -> list[tuple[str, str, int, int]]:
    """(key, the words as written, start, end of those words) for each key mark of an .html or .css part."""
    if name.endswith(".html"):
        return [(m.group(1), m.group(2), m.start(2), m.end(2)) for m in HTML_MARK.finditer(text)]
    if name.endswith(".css"):
        return [("css." + m.group(1).replace("-", "."), m.group(2), m.start(2), m.end(2)) for m in CSS_MARK.finditer(text)]
    return []


def _code(text: str) -> str:
    return re.sub(r"`([^`]*)`", r"<code>\1</code>", text)


def mark_problems(name: str, text: str, ja: dict, en: dict) -> list[str]:
    """Each key mark of the part names a key of the table, and its words as written are the Japanese words letter for
    letter (index.html: HTML-escaped, a tlhtml mark's `…` as <code>; app.css: as a CSS string writes them)."""
    import html as html_mod

    out = []
    for key, written, start, _ in marks(name, text):
        if key not in en or key not in ja:
            out.append(f"{name}: {key} is not in the table")
            continue
        if not isinstance(ja[key], str):
            out.append(f"{name}: {key} changes with a count; a mark takes plain words")
            continue
        if name.endswith(".html"):
            want = html_mod.escape(ja[key], quote=True)
            if text.startswith("{{tlhtml:", text.rfind("{{", 0, start)):
                want = _code(want)
        else:
            if not re.fullmatch(r"css\.[a-z0-9]+(?:\.[a-z0-9]+)*", key):
                out.append(f"{name}: {key}: a css key is css. and lower-case words joined by dots")
            want = ja[key].replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\A ")
        if written != want:
            out.append(f"{name}: {key} is written {written!r}, the Japanese words are {want!r}")
    return out


def positions(name: str, text: str) -> list[int]:
    """The offsets of the Japanese a part says, by its kind (its name's extension). The words as written beside a
    key are not counted: the key says them."""
    if name.endswith(".js"):
        return _js(text)
    if name.endswith(".html"):
        found = _outside(text, "<!--", "-->")
    elif name.endswith(".css"):
        found = _outside(text, "/*", "*/")
    else:
        raise ValueError(f"{name}: not a .js, .html or .css part")
    held = [(a, b) for _, _, a, b in marks(name, text)]
    return [k for k in found if not any(a <= k < b for a, b in held)]


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
