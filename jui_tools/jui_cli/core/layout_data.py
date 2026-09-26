"""A Layout JSON's `data` declarations, as the platform tools read them.

A layout may declare `data` at its root — the form `jui g project` writes —
or in any node below it, typically a `{"data": [...]}` first child: the form
most hand-written layouts use. sjui / kjui gather every one of them into the
screen's Data type (`extract_data_properties` in each tool's
data_model_updater_core.rb walks `child`); `children` is walked too, the key
`jui g project` writes for a layout tree's children.

Until jsonui-cli 1.9.0 the Python side read the root `data` only: `jui verify`'s
data-section check and `jui g project`'s orphan guard saw nothing in a layout
whose data sits in a child. On the three faces measured on 2026-09-26, none
of the 1283 initial values their screen specs declare was in a root `data`
section; 1269 were in a child's.
"""
from __future__ import annotations

import json
from typing import Any, Iterator


def layout_data_entries(layout: Any) -> Iterator[dict]:
    """Every `data` entry (a dict with a string `name`), root first, in
    document order. A name can occur more than once (per-platform entries)."""
    if isinstance(layout, dict):
        data = layout.get("data")
        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                    yield entry
        for key in ("child", "children"):
            if key in layout:
                yield from layout_data_entries(layout[key])
    elif isinstance(layout, list):
        for item in layout:
            yield from layout_data_entries(item)


def initial_value_key(value: Any, klass: Any = None) -> str:
    """One spelling per initial value, so two spellings of one value compare
    equal and two values do not.

    A Layout's `defaultValue` for a non-String class is often the literal in a
    string — "0", "false", "[]" — and the platform tools emit the same code for
    it as for 0 / false / []: sjui passes a non-String value through as the
    literal, kjui's format_default_value reads Int / Bool from either. So for
    a non-String class a string holding a JSON literal (not a JSON string) is
    that literal. For String, `''` is the empty string — the shorthand both
    tools read so; any other quoting is compared as written (the tools do not
    agree on it). Double / Float / CGFloat compare as numbers.
    """
    base = klass.rstrip("?") if isinstance(klass, str) else ""
    if isinstance(value, str):
        if base == "String":
            value = "" if value == "''" else value
        else:
            try:
                parsed = json.loads(value)
            except ValueError:
                parsed = value
            if not isinstance(parsed, str):
                value = parsed
    if (base in ("Double", "Float", "CGFloat") and isinstance(value, (int, float))
            and not isinstance(value, bool)):
        value = float(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False)
