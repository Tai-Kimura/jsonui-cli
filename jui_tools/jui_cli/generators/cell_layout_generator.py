"""Generate Layout JSON for Collection cells.

When a screen spec's ``structure.collection.cell`` defines a full tree
(via ``root`` as an object *and* ``generateCellLayout: true``), this
module renders that tree as an independent Layout JSON file alongside
the main screen Layout.

Example spec fragment::

    "collection": {
        "id": "favorites_grid",
        "cell": {
            "viewName": "FavoriteListGridCellView",
            "layoutFile": "favorite_list/favorite_list_grid_cell",
            "generateCellLayout": true,
            "root": {
                "type": "View",
                "id": "favorite_list_grid_cell_root",
                "style": {"background": "card_bg", "cornerRadius": 12},
                "children": [...]
            }
        }
    }

The file is written to ``layouts_directory/{cell.layoutFile}.json``.
The legacy key ``cell.layout`` is accepted as a fallback for backward
compatibility.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.spec_extractor import CollectionDef, ComponentDef, ScreenSpec
from .layout_generator import LayoutGenerator


class CellLayoutGenerator:
    """Generate Collection cell Layout JSON from a structured cell spec."""

    def __init__(self, layout_generator: LayoutGenerator | None = None):
        # We reuse the screen layout generator's tree-walking helpers so
        # style/binding/children handling stays consistent.
        self._layout_gen = layout_generator or LayoutGenerator(type_mapper=None)  # type: ignore[arg-type]

    def should_generate(self, collection: CollectionDef | None) -> bool:
        """Return True if the cell has a structured root and is opted in."""
        if collection is None:
            return False
        if not collection.generate_cell_layout:
            return False
        if collection.cell_root is None:
            return False
        return True

    def generate(self, collection: CollectionDef, spec: ScreenSpec) -> dict[str, Any]:
        """Build a cell Layout JSON dict from the collection definition."""
        if not self.should_generate(collection):
            raise ValueError(
                "CellLayoutGenerator.generate called with no generate_cell_layout"
            )

        vis_map = self._layout_gen._build_visibility_map(spec)  # noqa: SLF001
        root_def = collection.cell_root
        assert root_def is not None
        node = self._component_def_to_node(root_def, vis_map)

        # Cell-local typed `data` section, built from cellNode.uiVariables
        # + cellNode.eventHandlers. When absent, cells fall back to the old
        # behaviour (inherit untyped values via the parent Collection's
        # items binding) — i.e. just the root node, no data section.
        #
        # The @generated marker is injected at `jui build` time when the
        # cell layout is distributed to each platform's Layouts/ dir, not
        # here at the shared source layer.
        cell_data = self._build_cell_data_section(collection)
        if cell_data:
            return {"data": cell_data, **node}
        return node

    def _build_cell_data_section(
        self, collection: CollectionDef
    ) -> list[dict[str, Any]]:
        """Build the cell's Layout JSON `data` section from cellNode.uiVariables
        and cellNode.eventHandlers. Empty list → emit no data section.
        """
        if not collection.cell_ui_variables and not collection.cell_event_handlers:
            return []

        data: list[dict[str, Any]] = []
        type_mapper = self._layout_gen._type_mapper  # noqa: SLF001

        for var in collection.cell_ui_variables:
            resolved = type_mapper.resolve(var.type) if type_mapper else {
                "class": var.type, "defaultValue": None,
            }
            entry: dict[str, Any] = {
                "name": var.name,
                "class": resolved["class"],
            }
            default = var.default if var.default is not None else resolved.get("defaultValue")
            if default is not None:
                entry["defaultValue"] = default
            if var.description:
                entry["description"] = var.description
            data.append(entry)

        # Event handlers become callback-typed data entries so Layout JSON
        # bindings like `"onClick": "@{onMapTap}"` resolve against the cell's
        # own data. Use the same `(() -> Void)?` alias screens use.
        existing_names = {e["name"] for e in data}
        for handler in collection.cell_event_handlers:
            if handler.name in existing_names:
                continue
            resolved = type_mapper.resolve("(() -> Void)?") if type_mapper else {
                "class": "(() -> Void)?", "defaultValue": None,
            }
            data.append({
                "name": handler.name,
                "class": resolved["class"],
            })
            existing_names.add(handler.name)

        return data

    def resolve_output_path(
        self,
        collection: CollectionDef,
        layouts_root: Path,
        cell_entry: dict | None,
    ) -> Path:
        """Return ``layouts_directory/{cell.layoutFile}.json`` for the generated file.

        Reads ``layoutFile`` preferentially; falls back to the legacy ``layout``
        key; finally defaults to ``{collection.id}_cell``.
        """
        layout_rel = None
        if cell_entry and isinstance(cell_entry, dict):
            layout_rel = cell_entry.get("layoutFile") or cell_entry.get("layout")
        if not layout_rel:
            layout_rel = collection.id + "_cell"
        return layouts_root / f"{layout_rel}.json"

    # ------------------------------------------------------------------

    def _component_def_to_node(
        self, comp: ComponentDef, vis_map: dict[str, str]
    ) -> dict[str, Any]:
        """Render a typed ComponentDef as a Layout JSON node."""
        node: dict[str, Any] = {"type": comp.type, "id": comp.id}

        for k, v in (comp.style or {}).items():
            node[k] = v

        for attr, var in (comp.binding or {}).items():
            if isinstance(var, str):
                node[attr] = f"@{{{var}}}"

        if comp.children:
            node["child"] = [
                self._component_def_to_node(c, vis_map) for c in comp.children
            ]

        if comp.id in vis_map:
            node["visibility"] = f"@{{{vis_map[comp.id]}}}"

        return node
