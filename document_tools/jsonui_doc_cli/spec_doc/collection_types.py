"""A spec type written as a collection, read as jui_tools' TypeMapper reads it.

`[T]`, `[K: V]`, `Array(T)`, `List(T)`, `Dictionary(K, V)` and `Map(K, V)`,
optional and nested to any depth — brackets are matched, so `[[String: Int]]`
is a list of dictionaries and `[String: [Item]]` a dictionary of lists.

It is here, not imported from jui_cli: jsonui-doc is installed on its own
(`pip install …#subdirectory=document_tools`) and run from the distribution's
launcher with a project's python, neither of which carries jui_cli. 2.3.33's
initial-value check imported jui_cli's reading and crashed every `validate
spec` / `generate spec` there, whether or not a variable had an initial value
(tickets jsonui-doc-validate-imports-jui-cli-when-installed-alone and
2026-10-30-jsonui-doc-launcher-crashes-without-jui-cli-on-path). The two
readings are held to the same answers by
tests/test_collection_types_match_the_type_mapper.py.
"""

from __future__ import annotations

import re


def collection_shape(spec_type: str) -> tuple[str, list[str], bool] | None:
    """(``"list"`` or ``"map"``, member spec types, optional) for a spec type
    written as a collection, or None."""
    s = spec_type.strip()
    optional = s.endswith("?")
    if optional:
        s = s[:-1].rstrip()
    if s.startswith("[") and _closing(s, 0, "[", "]") == len(s) - 1:
        inner = s[1:-1].strip()
        halves = _split_top(inner, ":")
        if len(halves) == 2 and all(halves):
            return "map", halves, optional
        if len(halves) == 1 and inner:
            return "list", [inner], optional
        return None
    m = re.fullmatch(r"(Array|List|Dictionary|Map)\((.*)\)", s)
    if not m or _closing(s, s.index("("), "(", ")") != len(s) - 1:
        return None
    args = _split_top(m.group(2), ",")
    if m.group(1) in ("Array", "List") and len(args) == 1 and args[0]:
        return "list", args, optional
    if m.group(1) in ("Dictionary", "Map") and len(args) == 2 and all(args):
        return "map", args, optional
    return None


def _closing(s: str, start: int, open_ch: str, close_ch: str) -> int:
    """The index of the *close_ch* matching the *open_ch* at *start*, or -1."""
    depth = 0
    for i in range(start, len(s)):
        if s[i] == open_ch:
            depth += 1
        elif s[i] == close_ch:
            depth -= 1
            if depth == 0:
                return i
    return -1


def _split_top(s: str, sep: str) -> list[str]:
    """*s* split on *sep* outside brackets, parentheses and angle brackets.
    The ``>`` of a closure's ``->`` / ``=>`` closes nothing."""
    parts, depth, start = [], 0, 0
    for i, ch in enumerate(s):
        if ch in "[(<":
            depth += 1
        elif ch in "])" or (ch == ">" and s[i - 1:i] not in ("-", "=")):
            depth -= 1
        elif ch == sep and depth == 0:
            parts.append(s[start:i])
            start = i + 1
    parts.append(s[start:])
    return [p.strip() for p in parts]
