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

An `include` is expanded into the screen by sjui / kjui before its data is
read (data_model_updater_core.rb's `expand_includes`, each tool's
IncludeExpander): the included layout's entries join the screen's Data type,
named with the include id as a camelCase prefix (`card` + `title` ->
`cardTitle`). `layout_data_entries` reads one file and does not open an
include; `data_entries_with_includes` is the screen's Data as the tools build
it, through the normalizer's IncludeExpander — the Python port those tools'
spelling is held to (shared/core/camel_case_vectors.json). `jui verify`'s
initial-value check reads the latter: until jsonui-cli 1.9.1 it read the
former, and a value a spec declared under the prefixed name was reported as
"declares no data entry". The orphan checks (`jui verify`'s data section,
`jui g project`'s guard) read the file: what they ask is what replacing that
file drops, and an entry an include contributes lives in another file.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Iterator


def layout_data_entries(layout: Any) -> Iterator[dict]:
    """Every `data` entry (a dict with a string `name`), root first, in
    document order. A name can occur more than once (per-platform entries).
    An `include` is not opened — see `data_entries_with_includes`."""
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


def data_entries_with_includes(layout: Any, *, layouts_root: Path, styles_root: Path,
                               source: Path | None = None
                               ) -> tuple[list[tuple[dict, str | None]], list[tuple[str, str]]]:
    """The `data` entries of *layout* with its includes expanded as sjui /
    kjui expand them — each with the include reference of the file that
    declares it (None: *layout* itself) — and the includes that could not be.

    The order is data_model_updater_core.rb's `process_json_file`: styles
    merged, then includes expanded from *layouts_root* (`"card"` and
    `"sub/card"` name `<layouts_root>/card.json` and
    `<layouts_root>/sub/card.json`, at any depth). An include's entries take
    its id as a prefix (`card` + `title` -> `cardTitle`, `card_row` +
    `title_text` -> `cardRowTitleText`); one without an id passes the prefix
    above it on, none at the top; a nested include with an id adds its own
    (`outer` then `inner` -> `outerInner...`). The include node's own `data`
    list joins the included layout's and takes the same prefix — one inside
    an included layout takes both, as the tools give it (`outer`, then
    `outerInner`: `note` -> `outerInnerOuterNote`).

    An include that is not expanded — its file missing or unparsable (the
    tools stop the build: "Include file not found"), or one that names a
    layout it is already inside (the tools recurse until the stack runs out)
    — stays out of the entries and is returned as ``(reference, reason)``;
    *source*, the file *layout* was read from, makes including itself a cycle
    at the first step. *layout* is not modified.
    """
    from .normalizer.include_expander import IncludeExpander
    from .normalizer.style_merger import StyleMerger

    mark = "$jui.declaredIn"

    class _Marking(IncludeExpander):
        """Marks each entry of an included file with the reference it was
        included by, before the expander prefixes it (a copy keeps it)."""

        def _load_include(self, include_path):
            tree = super()._load_include(include_path)
            for entry in layout_data_entries(tree):
                entry.setdefault(mark, str(include_path))
            return tree

    merger = StyleMerger(Path(styles_root))
    expander = _Marking(Path(layouts_root), merger)
    unresolved: list[tuple[str, str]] = []
    inside = ()
    if source is not None:
        try:
            inside = (Path(source).resolve(),)
        except (OSError, RuntimeError):
            inside = (Path(source),)
    expanded = expander.expand(merger.resolve(copy.deepcopy(layout)),
                               unresolved=unresolved, inside=inside)
    entries = []
    for entry in layout_data_entries(expanded):
        declared_in = entry.pop(mark, None)
        entries.append((entry, declared_in))
    return entries, unresolved


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
