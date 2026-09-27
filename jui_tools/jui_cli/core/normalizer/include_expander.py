"""Inline-expand ``include`` references with ID prefixing.

Port of ``sjui_tools/lib/swiftui/include_expander.rb``. A node
``{"include": "foo", "id": "bar", ...}`` is replaced with the contents
of ``<layouts_dir>/foo.json`` (style-merged), with the parent's ``id``
propagated as a camelCase prefix to all descendant ``id``s and
``@{binding}`` references.

An include the expander cannot expand — its file is not there, does not
parse, or is one the node is already inside (a cycle) — leaves the node in
place without its ``include``. sjui / kjui stop the build on the first two
("Include file not found", a JSON parse error) and recurse on a cycle until
the stack runs out. A caller that passes ``unresolved`` is told of each one
there; a cycle is otherwise an :class:`IncludeCycleError`, so it is never cut
silently.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .style_merger import StyleMerger


BINDING_RE = re.compile(r"@\{([^}]+)\}")


class IncludeCycleError(RecursionError):
    """An include of a layout the node is already inside.

    Until jsonui-cli 1.9.1 the expander recursed on one until Python's limit
    (a RecursionError, which this is, so a caller that caught that still
    does); sjui / kjui do the same until the stack runs out (SystemStackError).
    This stops at the first repeat and names the chain."""

    def __init__(self, chain: list[str]):
        self.chain = chain
        super().__init__("include cycle: " + " -> ".join(chain))


class IncludeExpander:
    def __init__(self, layouts_dir: Path, style_merger: StyleMerger):
        self._layouts_dir = layouts_dir
        self._style_merger = style_merger

    def expand(self, node: Any, id_prefix: str | None = None, *,
               unresolved: list | None = None, inside: tuple = ()) -> Any:
        """*node* with every include replaced as sjui / kjui replace it.

        *inside*: the layout files (resolved paths) whose content *node*
        already is — the caller may name the file *node* comes from, so an
        include of that file is a cycle at the first step. *unresolved*, when
        given, receives ``(reference, reason)`` for every include left
        unexpanded: ``"not found"``, ``"unreadable"`` or ``"cycle"``."""
        if not isinstance(node, dict):
            return node

        if "include" in node:
            ref = node["include"]
            path = self._include_path(ref)
            if path in inside:
                if unresolved is None:
                    raise IncludeCycleError(
                        [self._name(p) for p in inside[inside.index(path):]] + [self._name(path)])
                included = None
            else:
                included = self._load_include(ref)
            if included is None:
                if unresolved is not None:
                    reason = ("cycle" if path in inside
                              else "not found" if not path.exists() else "unreadable")
                    unresolved.append((str(ref), reason))
                # Not expanded — drop the include field and continue.
                node = {k: v for k, v in node.items() if k != "include"}
            else:
                included = self._style_merger.resolve(included)
                include_id = node.get("id")
                new_prefix = _derive_prefix(id_prefix, include_id)

                # Merge parent overrides (excluding include/id)
                for key, value in node.items():
                    if key in ("include", "id"):
                        continue
                    if key in ("data", "shared_data"):
                        existing = included.get(key) or []
                        if isinstance(value, list):
                            included[key] = list(existing) + list(value)
                        else:
                            included[key] = existing
                    else:
                        included[key] = value

                expanded = _apply_id_prefix(included, new_prefix)
                return self.expand(expanded, new_prefix, unresolved=unresolved,
                                   inside=inside + (path,))

        # Apply prefix to this node's own id
        if id_prefix and "id" in node and isinstance(node["id"], str):
            node["id"] = _combine_with_prefix(id_prefix, node["id"])

        # Normalize children key + recurse
        child_key = None
        if "child" in node:
            child_key = "child"
        elif "children" in node:
            child_key = "children"

        if child_key:
            value = node[child_key]
            if isinstance(value, list):
                node[child_key] = [self.expand(c, id_prefix, unresolved=unresolved, inside=inside)
                                   for c in value]
            elif isinstance(value, dict):
                node[child_key] = self.expand(value, id_prefix, unresolved=unresolved, inside=inside)
            if child_key == "children":
                node["child"] = node.pop("children")

        return node

    def _include_path(self, include_path: Any) -> Path:
        """The file an include reference names, resolved — the identity a
        cycle is found by, so `a` and `sub/../a` are one file."""
        path = self._layouts_dir / f"{include_path}.json"
        try:
            return path.resolve()
        except (OSError, RuntimeError):
            return path

    def _name(self, path: Path) -> str:
        """*path* as an include names it (relative to the layouts root)."""
        try:
            return str(path.relative_to(Path(self._layouts_dir).resolve()).with_suffix(""))
        except ValueError:
            return str(path)

    def _load_include(self, include_path: str) -> dict[str, Any] | None:
        """Resolve an include reference relative to the layouts root.

        ``"foo"`` → ``<layouts_dir>/foo.json``
        ``"sub/foo"`` → ``<layouts_dir>/sub/foo.json``
        """
        path = self._layouts_dir / f"{include_path}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                tree = json.load(f)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return None
        # A layout is an object; anything else is as unreadable as bad JSON
        # (it failed further on, reading the include node's keys into it).
        return tree if isinstance(tree, dict) else None


def _to_camel_case(s: str) -> str:
    """An id's snake_case in camelCase, spelled as codegen spells it.

    The generated screens are the ids that exist, so this is sjui/kjui's
    `to_camel_case` (include_expander.rb): every part after the first is
    Ruby's `capitalize` — first letter up, the REST DOWN. It kept the rest,
    and an upper-case part split the toolchain: `verify_2FA_form` was
    `verify2FAForm` here and in layout facts, `verify2faForm` in the
    generated screen. The one snake->camel for ids in jui_tools
    (layout_generator calls it); the answers are
    shared/core/camel_case_vectors.json, which the Ruby specs hold too.
    """
    if "_" not in s:
        return s
    parts = s.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _combine_with_prefix(prefix: str | None, name: str) -> str:
    """`prefix` + `name` in camelCase; as codegen, the joined name's first
    letter goes up only when it is a-z (`[a-z]`, Ruby's `sub(/^[a-z]/)`)."""
    if not prefix:
        return name
    camel_name = _to_camel_case(name)
    return prefix + re.sub(r"^[a-z]", lambda m: m.group(0).upper(), camel_name)


def _derive_prefix(outer_prefix: str | None, include_id: str | None) -> str | None:
    if outer_prefix and include_id:
        return _combine_with_prefix(outer_prefix, include_id)
    if include_id:
        return _to_camel_case(include_id)
    return outer_prefix


def _apply_id_prefix(node: Any, prefix: str | None) -> Any:
    if not prefix or not isinstance(node, dict):
        return node
    _prefix_data_names(node, prefix)
    _transform_bindings_in_place(node, prefix)
    return node


def _prefix_data_names(node: Any, prefix: str) -> None:
    if not isinstance(node, dict):
        return
    data = node.get("data")
    if isinstance(data, list):
        new_data = []
        for item in data:
            if isinstance(item, dict) and "name" in item and isinstance(item["name"], str):
                item = dict(item)
                item["name"] = _combine_with_prefix(prefix, item["name"])
            new_data.append(item)
        node["data"] = new_data

    child = node.get("child") or node.get("children")
    if isinstance(child, list):
        for c in child:
            _prefix_data_names(c, prefix)
    elif isinstance(child, dict):
        _prefix_data_names(child, prefix)


def _transform_bindings_in_place(node: Any, prefix: str) -> Any:
    if isinstance(node, dict):
        for k, v in list(node.items()):
            node[k] = _transform_bindings_in_place(v, prefix)
        return node
    if isinstance(node, list):
        return [_transform_bindings_in_place(v, prefix) for v in node]
    if isinstance(node, str):
        return BINDING_RE.sub(
            lambda m: f"@{{{_combine_with_prefix(prefix, m.group(1))}}}"
            if "." not in m.group(1)
            else m.group(0),
            node,
        )
    return node
