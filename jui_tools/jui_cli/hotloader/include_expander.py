"""Inline-expand ``include`` references with ID prefixing.

Port of ``sjui_tools/lib/swiftui/include_expander.rb``. A node
``{"include": "foo", "id": "bar", ...}`` is replaced with the contents
of ``<layouts_dir>/foo.json`` (style-merged), with the parent's ``id``
propagated as a camelCase prefix to all descendant ``id``s and
``@{binding}`` references.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .style_merger import StyleMerger


BINDING_RE = re.compile(r"@\{([^}]+)\}")


class IncludeExpander:
    def __init__(self, layouts_dir: Path, style_merger: StyleMerger):
        self._layouts_dir = layouts_dir
        self._style_merger = style_merger

    def expand(self, node: Any, id_prefix: str | None = None) -> Any:
        if not isinstance(node, dict):
            return node

        if "include" in node:
            included = self._load_include(node["include"])
            if included is None:
                # File missing — drop the include field and continue.
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
                return self.expand(expanded, new_prefix)

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
                node[child_key] = [self.expand(c, id_prefix) for c in value]
            elif isinstance(value, dict):
                node[child_key] = self.expand(value, id_prefix)
            if child_key == "children":
                node["child"] = node.pop("children")

        return node

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
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None


def _to_camel_case(s: str) -> str:
    if "_" not in s:
        return s
    parts = s.split("_")
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:] if p)


def _combine_with_prefix(prefix: str | None, name: str) -> str:
    if not prefix:
        return name
    camel_name = _to_camel_case(name)
    if not camel_name:
        return prefix
    return prefix + camel_name[:1].upper() + camel_name[1:]


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
