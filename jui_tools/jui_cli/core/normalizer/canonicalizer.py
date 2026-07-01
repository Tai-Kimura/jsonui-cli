"""L1 canonicalization: alias → canonical attribute rewrite + ``$jui`` marker.

Specification (renderer SSoT plan, phase 05 §2.2):

1. Aliases are rewritten to their canonical spelling using the ``aliases``
   fields of attribute_definitions.json (component-specific definitions
   override ``common``).
2. When a node carries both an alias and its canonical name, the canonical
   value wins and a warning is emitted (never a silent drop).
3. ``deprecated`` attributes produce a warning but are NOT rewritten
   (there is no rewrite target in the definitions).
4. The top-level tree gains ``"$jui": {"normalized": "L1", "schemaVersion": 1}``.
5. ``style`` / ``include`` / ``platform`` are left untouched at L1.
6. Unknown attributes pass through unchanged (validation is the attribute
   validator's job; the normalizer only transforms).

The transform is idempotent: ``canonicalize(canonicalize(x)) == canonicalize(x)``.
"""
from __future__ import annotations

import copy
from typing import Any

from .alias_table import AliasTable

MARKER_KEY = "$jui"
SCHEMA_VERSION = 1

# Keys that hold nested component nodes. L1 only rewrites attributes on
# component nodes reached through the layout tree — arbitrary dict-valued
# attributes (e.g. ``data`` entries, ``partialAttributes``) are NOT
# rewritten, since their keys are not component attributes.
_CHILD_KEYS = ("child", "children")


class Canonicalizer:
    """Applies the L1 alias→canonical rewrite across a layout tree."""

    def __init__(self, alias_table: AliasTable | None = None):
        self._table = alias_table or AliasTable.from_file()

    def canonicalize(
        self,
        tree: Any,
        *,
        source: str = "",
        add_marker: bool = True,
    ) -> tuple[Any, list[str]]:
        """Return ``(canonical_tree, warnings)``. *tree* is not mutated.

        *source* is an optional file label used to prefix warnings.
        ``add_marker=False`` skips the ``$jui`` marker (used by the L2
        pipeline, which stamps its own marker at the end).
        """
        warnings: list[str] = []
        if not isinstance(tree, dict):
            return tree, warnings

        result = self._canonicalize_node(
            copy.deepcopy(tree), warnings, source=source, path="root"
        )
        if add_marker:
            result = apply_marker(result, level="L1")
        return result, warnings

    # ------------------------------------------------------------------

    def _canonicalize_node(
        self, node: Any, warnings: list[str], *, source: str, path: str
    ) -> Any:
        if not isinstance(node, dict):
            return node

        node_type = node.get("type") if isinstance(node.get("type"), str) else None
        alias_map = self._table.aliases_for(node_type)
        deprecated_map = self._table.deprecated_for(node_type)
        label = self._node_label(node, node_type, path)

        rebuilt: dict[str, Any] = {}
        for key, value in node.items():
            if key == MARKER_KEY:
                continue  # re-stamped by apply_marker (root only)
            canonical = alias_map.get(key)
            if canonical is None:
                target = key
            elif canonical in node:
                # Alias + canonical both present → canonical wins, warn.
                warnings.append(
                    self._fmt(
                        source,
                        label,
                        f"'{key}' is an alias of '{canonical}' and both are "
                        f"set — keeping '{canonical}', dropping '{key}'",
                    )
                )
                continue
            elif canonical in rebuilt:
                # Two aliases of the same canonical → first one won.
                warnings.append(
                    self._fmt(
                        source,
                        label,
                        f"'{key}' is an alias of '{canonical}' which was "
                        f"already set via another alias — dropping '{key}'",
                    )
                )
                continue
            else:
                target = canonical
            rebuilt[target] = value

            dep = deprecated_map.get(target)
            if dep is not None:
                note = f" — {dep.note}" if dep.note else ""
                warnings.append(
                    self._fmt(
                        source,
                        label,
                        f"'{target}' is deprecated ({dep.scope_label()}){note}",
                    )
                )

        # Recurse into child nodes (structure keys are never aliases).
        for child_key in _CHILD_KEYS:
            if child_key not in rebuilt:
                continue
            value = rebuilt[child_key]
            if isinstance(value, list):
                rebuilt[child_key] = [
                    self._canonicalize_node(
                        c, warnings, source=source, path=f"{path}.{child_key}[{i}]"
                    )
                    for i, c in enumerate(value)
                ]
            elif isinstance(value, dict):
                rebuilt[child_key] = self._canonicalize_node(
                    value, warnings, source=source, path=f"{path}.{child_key}"
                )

        return rebuilt

    @staticmethod
    def _node_label(node: dict, node_type: str | None, path: str) -> str:
        node_id = node.get("id")
        where = f"id={node_id}" if isinstance(node_id, str) and node_id else path
        return f"{where} ({node_type})" if node_type else where

    @staticmethod
    def _fmt(source: str, label: str, message: str) -> str:
        prefix = f"{source}: " if source else ""
        return f"{prefix}[{label}] {message}"


def apply_marker(
    tree: dict[str, Any], *, level: str, platform: str | None = None
) -> dict[str, Any]:
    """Return *tree* with the ``$jui`` normalization marker as first key.

    Any pre-existing marker is replaced (keeps normalize idempotent).
    """
    marker: dict[str, Any] = {"normalized": level, "schemaVersion": SCHEMA_VERSION}
    if platform:
        marker["platform"] = platform
    rest = {k: v for k, v in tree.items() if k != MARKER_KEY}
    return {MARKER_KEY: marker, **rest}
