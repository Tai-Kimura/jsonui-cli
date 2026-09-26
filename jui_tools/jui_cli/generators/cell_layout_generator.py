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

The same holds for the Collection's ``header`` and ``footer`` (jsonui-cli 1.9.0; until
then only the cell was written, and only for an object root): each entry that
sets ``generateCellLayout: true`` gets its own Layout JSON, from either form —

- an object ``root``: that component tree;
- a string ``root`` (the pack's documented form, and the schema's layoutNode
  form): the component of that id from structure.components (or a View with
  that id), with ``children`` — component ids, or layoutChild objects with
  ``overlay`` / ``zIndex`` — under it, stacked when ``overlay`` is true and
  vertical otherwise, as the screen layout does it.

``uiVariables`` / ``eventHandlers`` give each file its ``data`` section. An
entry without ``generateCellLayout`` is a layout authored elsewhere, and
nothing is written for it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.spec_extractor import (
    CollectionDef, CollectionSlotDef, ComponentDef, ScreenSpec, slot_layout_ref,
)
from .layout_generator import LayoutGenerator


class CellLayoutGenerator:
    """Generate Collection cell Layout JSON from a structured cell spec."""

    def __init__(self, layout_generator: LayoutGenerator | None = None):
        # We reuse the screen layout generator's tree-walking helpers so
        # style/binding/children handling stays consistent.
        self._layout_gen = layout_generator or LayoutGenerator(type_mapper=None)  # type: ignore[arg-type]

    @staticmethod
    def should_generate_slot(slot: CollectionSlotDef | None) -> bool:
        """True when the entry opts in and has a root to build from."""
        return bool(slot and slot.generate and slot.root_id)

    def should_generate(self, collection: CollectionDef | None) -> bool:
        """Return True if the cell is opted in (see should_generate_slot)."""
        if collection is None:
            return False
        return self.should_generate_slot(collection.slots.get("cell"))

    def slots_to_generate(self, collection: CollectionDef) -> list[CollectionSlotDef]:
        return [s for s in collection.slots.values() if self.should_generate_slot(s)]

    def generate(self, collection: CollectionDef, spec: ScreenSpec) -> dict[str, Any]:
        """Build a cell Layout JSON dict from the collection definition."""
        if not self.should_generate(collection):
            raise ValueError(
                "CellLayoutGenerator.generate called with no generate_cell_layout"
            )
        return self.generate_slot(collection.slots["cell"], spec)

    def generate_slot(self, slot: CollectionSlotDef, spec: ScreenSpec) -> dict[str, Any]:
        """Build the Layout JSON of one cell / header / footer entry."""
        if not self.should_generate_slot(slot):
            raise ValueError(f"CellLayoutGenerator.generate_slot: {slot.kind} is not opted in")

        vis_map = self._layout_gen._build_visibility_map(spec)  # noqa: SLF001
        if isinstance(slot.root, ComponentDef):
            node = self._component_def_to_node(slot.root, vis_map)
        else:
            # A string root, with the layoutNode form's children under it —
            # built as the screen builds a layoutChild of that id.
            comp_map = self._layout_gen.component_map(spec)
            node = self._layout_gen._build_node(  # noqa: SLF001
                {"id": slot.root, "overlay": slot.overlay, "children": slot.children},
                comp_map, vis_map,
            ) or {"type": "View", "id": slot.root}
            if node.get("children") and not slot.overlay and "orientation" not in node:
                node["orientation"] = "vertical"

        # Cell-local typed `data` section, built from the entry's uiVariables
        # + eventHandlers. When absent, cells fall back to the old
        # behaviour (inherit untyped values via the parent Collection's
        # items binding) — i.e. just the root node, no data section.
        #
        # The @generated marker is injected at `jui build` time when the
        # cell layout is distributed to each platform's Layouts/ dir, not
        # here at the shared source layer.
        cell_data = self._build_slot_data_section(slot)
        if cell_data:
            return {"data": cell_data, **node}
        return node

    def _build_cell_data_section(
        self, collection: CollectionDef
    ) -> list[dict[str, Any]]:
        """The cell slot's `data` section (see _build_slot_data_section)."""
        cell = collection.slots.get("cell")
        return self._build_slot_data_section(cell) if cell else []

    def _build_slot_data_section(
        self, slot: CollectionSlotDef
    ) -> list[dict[str, Any]]:
        """Build the entry's Layout JSON `data` section from its uiVariables
        and eventHandlers. Empty list → emit no data section.
        """
        if not slot.ui_variables and not slot.event_handlers:
            return []

        data: list[dict[str, Any]] = []
        type_mapper = self._layout_gen._type_mapper  # noqa: SLF001

        for var in slot.ui_variables:
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
        for handler in slot.event_handlers:
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
        cell_entry: dict | None = None,
    ) -> Path:
        """Return ``layouts_directory/{cell.layoutFile}.json`` for the generated file.

        Reads ``layoutFile`` preferentially; falls back to the legacy ``layout``
        key; finally defaults to ``{collection.id}_cell``. ``cell_entry`` (the
        raw dict) is no longer needed — the parsed slot carries both keys.
        """
        cell = collection.slots.get("cell")
        if cell is None:
            return layouts_root / f"{collection.id}_cell.json"
        return self.slot_output_path(collection, cell, layouts_root)

    @staticmethod
    def slot_output_path(collection: CollectionDef, slot: CollectionSlotDef, layouts_root: Path) -> Path:
        """``layouts_directory/<the layout the Collection's section names>.json``
        — one name for the file and the reference (slot_layout_ref). For an
        entry that is written: ``layoutFile``, else ``<collection id>_<kind>``."""
        return layouts_root / f"{slot_layout_ref(collection.id, CollectionSlotDef(**{**slot.__dict__, 'generate': True}))}.json"

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

        platform = (comp.raw or {}).get("platform")
        if isinstance(platform, (str, dict)) and platform:
            node["platform"] = platform

        if comp.children:
            node["child"] = [
                self._component_def_to_node(c, vis_map) for c in comp.children
            ]

        if comp.id in vis_map:
            node["visibility"] = f"@{{{vis_map[comp.id]}}}"

        return node
