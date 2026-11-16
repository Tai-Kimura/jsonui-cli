"""Every tl('key', {...}) / tlHTML('key', {...}) the page's code writes with a literal key names a key both tables have
(en.json, ja.json) and fills every {slot} its words have in either language (ticket
2026-10-21-viz-english-screen-checks). A miss would read on the page as the key or as {name}; tl() says it on the
console in a browser test (test_viz_tl_says_what_is_missing), and this finds the written ones without a browser. A
call whose key is built at run time (a handful) or whose params spread another object is left to the browser test.
"""
from __future__ import annotations

import json
import re

from tests.test_viz_bundle import WEB, web_text

CALL = re.compile(r"\btl(?:HTML)?\('([a-z][\w.]*)'(\s*,\s*\{)?")


def _slots(v) -> set:
    return {s for words in (v.values() if isinstance(v, dict) else [v]) for s in re.findall(r"\{(\w+)\}", words)}


def _given(src: str, at: int) -> set | None:
    """The top-level names of the object literal that starts at src[at] ('{'); None when it spreads another."""
    depth, end = 0, at
    for end in range(at, len(src)):
        depth += {"{": 1, "}": -1}.get(src[end], 0)
        if depth == 0:
            break
    body = src[at + 1:end]
    if "..." in body:
        return None
    parts, depth, cur = [], 0, ""
    for ch in body:
        depth += 1 if ch in "{([" else -1 if ch in "})]" else 0
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return {m.group(1) for p in parts if (m := re.match(r"\s*([A-Za-z_]\w*)\s*(?::|$)", p))}


def _misses() -> tuple[list, list]:
    en = json.loads(web_text("i18n", "en.json"))
    ja = json.loads(web_text("i18n", "ja.json"))
    no_key, unfilled = [], []
    for path in sorted((WEB / "js").glob("*.js")):
        src = path.read_text(encoding="utf-8")
        for m in CALL.finditer(src):
            key = m.group(1)
            if key not in en or key not in ja:
                no_key.append(f"{path.name}: {key}")
                continue
            given = _given(src, m.end() - 1) if m.group(2) else set()
            if given is None:
                continue
            lack = (_slots(en[key]) | _slots(ja[key])) - given
            if lack:
                unfilled.append(f"{path.name}: {key} leaves {sorted(lack)}")
    return no_key, unfilled


def test_every_written_key_is_in_both_tables():
    assert _misses()[0] == []


def test_every_written_call_fills_its_slots():
    assert _misses()[1] == []


def test_the_scan_reads_the_calls():
    """Not vacuous: it finds the page's calls, and one whose slot is dropped is seen."""
    src = "x = tl('a.b', { name, n: 3 }); y = tlHTML('c.d'); z = tl('e.f', { ...o });"
    assert [m.group(1) for m in CALL.finditer(src)] == ["a.b", "c.d", "e.f"]
    assert _given(src, src.index("{")) == {"name", "n"} and _given(src, src.rindex("{")) is None
    total = sum(len(CALL.findall(p.read_text(encoding="utf-8"))) for p in (WEB / "js").glob("*.js"))
    assert total > 1500
