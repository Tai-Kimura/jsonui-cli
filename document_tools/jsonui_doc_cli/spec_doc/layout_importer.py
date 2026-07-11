"""Import Layout JSON and convert to spec-compatible structure.

When a spec has ``metadata.layoutFile``, this module reads the referenced
Layout JSON and extracts components, layout hierarchy, and data bindings
into the same format as the spec's ``structure`` and ``stateManagement``
sections.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def import_layout_into_spec(spec_data: dict, layouts_dir: Path) -> dict:
    """Merge Layout JSON data into *spec_data* if ``layoutFile`` is set.

    Returns a **new** dict with the imported data merged.  The original
    *spec_data* is not modified.

    Covers three reference points, all driven by the same Layout JSON model:

      1. ``metadata.layoutFile`` — the screen's main layout.
      2. ``structure.collection.{cell,header,footer}.layoutFile`` (or the
         legacy ``layout`` key) — per-section cell layouts.
      3. ``structure.collection.cellClasses[]`` + ``sections[].{cell,header,
         footer}`` — multi-cell Collection references, expanded into
         ``collection._resolvedCells`` keyed by the reference string.

    If no references resolve, returns *spec_data* unchanged.
    """
    result = _deep_copy(spec_data)

    # 1. Screen-level layoutFile (unchanged behaviour).
    layout_file = (result.get("metadata") or {}).get("layoutFile")
    if layout_file:
        layout_json = _read_layout_by_ref(layouts_dir, layout_file)
        if layout_json is not None:
            imported = _extract_from_layout(layout_json)
            structure = result.setdefault("structure", {})
            state_mgmt = result.setdefault("stateManagement", {})

            if imported["components"]:
                existing = structure.get("components", [])
                if not existing or _is_placeholder(existing):
                    structure["components"] = imported["components"]

            if imported["layout"]:
                existing_layout = structure.get("layout", {})
                if not existing_layout or not existing_layout.get("children"):
                    structure["layout"] = imported["layout"]

            if imported["uiVariables"]:
                existing_vars = {v["name"] for v in state_mgmt.get("uiVariables", [])}
                new_vars = [v for v in imported["uiVariables"] if v["name"] not in existing_vars]
                state_mgmt.setdefault("uiVariables", []).extend(new_vars)

            if imported["eventHandlers"]:
                existing_handlers = {h["name"] for h in state_mgmt.get("eventHandlers", [])}
                new_handlers = [
                    h for h in imported["eventHandlers"] if h["name"] not in existing_handlers
                ]
                state_mgmt.setdefault("eventHandlers", []).extend(new_handlers)

            result.setdefault("metadata", {})["_layoutFileImported"] = True

    # 2 + 3. Collection cell / header / footer / cellClasses references.
    _expand_collection_refs(result, layouts_dir)

    return result


def _expand_collection_refs(spec_data: dict, layouts_dir: Path) -> None:
    """Mutate *spec_data* in place to inline Collection cell layout refs."""
    structure = spec_data.get("structure")
    if not isinstance(structure, dict):
        return
    targets = [structure.get("collection"), *(structure.get("collections") or [])]
    for collection in targets:
        if isinstance(collection, dict):
            _expand_one_collection(collection, layouts_dir)


def _expand_one_collection(collection: dict, layouts_dir: Path) -> None:
    # 2a. Single-cell object form (legacy single-cell Collections) plus header/footer.
    for key in ("cell", "header", "footer"):
        entry = collection.get(key)
        if isinstance(entry, dict):
            expanded = _expand_cell_entry(entry, layouts_dir)
            if expanded is not None:
                collection[key] = expanded

    # 3a. cellClasses[] (multi-cell Collections) — resolve each into _resolvedCells.
    resolved: dict[str, dict] = {}
    cell_classes = collection.get("cellClasses") or []
    if isinstance(cell_classes, list):
        for ref in cell_classes:
            if isinstance(ref, str) and ref and ref not in resolved:
                entry = _extracted_cell_for_ref(ref, layouts_dir)
                if entry is not None:
                    resolved[ref] = entry

    # 3b. sections[].{cell, header, footer} — collect any string refs into _resolvedCells.
    sections = collection.get("sections") or []
    if isinstance(sections, list):
        for sec in sections:
            if not isinstance(sec, dict):
                continue
            for k in ("cell", "header", "footer"):
                ref = sec.get(k)
                if isinstance(ref, str) and ref and ref not in resolved:
                    entry = _extracted_cell_for_ref(ref, layouts_dir)
                    if entry is not None:
                        resolved[ref] = entry

    if resolved:
        collection["_resolvedCells"] = resolved


def _expand_cell_entry(cell: dict, layouts_dir: Path) -> dict | None:
    """Inline layoutFile-driven data into a single cellNode-shaped dict.

    Returns a new dict with `components`/`layout`/`uiVariables`/`eventHandlers`
    filled in when a referenced Layout JSON is found. Returns the input dict
    unchanged when neither ``layoutFile`` nor the legacy ``layout`` key is set,
    or the reference cannot be resolved.
    """
    layout_ref = cell.get("layoutFile") or cell.get("layout")
    if not isinstance(layout_ref, str) or not layout_ref:
        return cell
    layout_json = _read_layout_by_ref(layouts_dir, layout_ref)
    if layout_json is None:
        return cell
    extracted = _extract_from_layout(layout_json)
    out = dict(cell)
    if extracted["components"] and not out.get("components"):
        out["components"] = extracted["components"]
    if extracted["layout"] and not out.get("layout"):
        out["layout"] = extracted["layout"]
    if extracted["uiVariables"] and not out.get("uiVariables"):
        out["uiVariables"] = extracted["uiVariables"]
    if extracted["eventHandlers"] and not out.get("eventHandlers"):
        out["eventHandlers"] = extracted["eventHandlers"]
    out["_layoutFileImported"] = True
    return out


def _extracted_cell_for_ref(ref: str, layouts_dir: Path) -> dict | None:
    """Read a Layout JSON by reference and return an expanded cell record."""
    layout_json = _read_layout_by_ref(layouts_dir, ref)
    if layout_json is None:
        return None
    extracted = _extract_from_layout(layout_json)
    return {
        "layoutFile": ref,
        "components": extracted["components"],
        "layout": extracted["layout"],
        "uiVariables": extracted["uiVariables"],
        "eventHandlers": extracted["eventHandlers"],
        "_layoutFileImported": True,
    }


def _read_layout_by_ref(layouts_dir: Path, ref: str) -> dict | None:
    """Resolve ``"bar_list/bar_cell"`` → ``{layouts_dir}/bar_list/bar_cell.json``.

    Accepts paths with or without the ``.json`` suffix. Returns ``None``
    when the file is missing or the JSON is malformed.
    """
    clean = ref.replace("\\", "/").lstrip("/")
    if not clean.endswith(".json"):
        clean += ".json"
    path = layouts_dir / clean
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _extract_from_layout(layout: dict) -> dict:
    """Extract spec-compatible structure from Layout JSON."""
    components: list[dict] = []
    layout_tree: dict = {}
    bindings: list[str] = []
    event_handlers: list[str] = []

    # Skip data section
    data_section = layout.get("data", {})

    # Extract component tree
    root_comp = _node_to_component(layout, bindings, event_handlers)
    if root_comp:
        components = [root_comp]

    # Build layout hierarchy
    layout_tree = _build_layout_tree(layout)

    # Extract uiVariables from data section
    ui_variables = _extract_ui_variables(data_section)

    # Extract event handlers from data section
    handler_defs = _extract_event_handlers(data_section)

    # Also add handlers found via bindings
    for name in event_handlers:
        if not any(h["name"] == name for h in handler_defs):
            handler_defs.append({"name": name, "description": ""})

    # Also add variables found via bindings
    for name in bindings:
        if not any(v["name"] == name for v in ui_variables):
            ui_variables.append({
                "name": name,
                "type": "String",
                "description": "(from binding)",
            })

    return {
        "components": components,
        "layout": layout_tree,
        "uiVariables": ui_variables,
        "eventHandlers": handler_defs,
    }


def _node_to_component(
    node: dict,
    bindings: list[str],
    event_handlers: list[str],
    _skip_keys: set | None = None,
) -> dict | None:
    """Convert a Layout JSON node to a spec component dict."""
    if not isinstance(node, dict):
        return None

    comp_type = node.get("type")
    if not comp_type:
        return None

    comp: dict[str, Any] = {
        "type": comp_type,
    }

    comp_id = node.get("id")
    if comp_id:
        comp["id"] = comp_id

    # Preserve platform filter / override so the Components table can
    # surface it as a badge (e.g. AppleSignInButton → iOS-only).
    platform_value = node.get("platform")
    if platform_value:
        comp["platform"] = platform_value

    # Collect style attributes
    style: dict[str, Any] = {}
    skip = {"type", "id", "child", "children", "data", "sections",
            "cellClasses", "include", "tabs", "responsive", "platform"}

    for k, v in node.items():
        if k in skip:
            continue
        # Detect bindings
        if isinstance(v, str) and v.startswith("@{") and v.endswith("}"):
            var_name = v[2:-1]
            if k in ("onClick", "onLongPress", "onValueChange", "onTextChange",
                      "onSelect", "onTabChange", "onSubmit"):
                event_handlers.append(var_name)
                comp.setdefault("binding", {})[k] = var_name
            else:
                bindings.append(var_name)
                comp.setdefault("binding", {})[k] = var_name
        elif k not in ("style",):
            style[k] = v

    if style:
        comp["style"] = style

    # Process children
    children_raw = node.get("child") or node.get("children") or []
    if isinstance(children_raw, dict):
        children_raw = [children_raw]

    child_comps = []
    for child_node in children_raw:
        if isinstance(child_node, dict):
            # Skip include nodes
            if "include" in child_node:
                child_comps.append({
                    "type": "include",
                    "id": child_node.get("id", ""),
                    "description": f'include: {child_node["include"]}',
                })
                continue
            child_comp = _node_to_component(child_node, bindings, event_handlers)
            if child_comp:
                child_comps.append(child_comp)

    if child_comps:
        comp["children"] = child_comps

    return comp


def _build_layout_tree(node: dict) -> dict:
    """Build a spec-compatible layout hierarchy."""
    root_id = node.get("id", "root")
    children_raw = node.get("child") or node.get("children") or []
    if isinstance(children_raw, dict):
        children_raw = [children_raw]

    children_ids = []
    for child in children_raw:
        if isinstance(child, dict):
            child_id = child.get("id")
            if child_id:
                children_ids.append({"id": child_id})

    tree: dict[str, Any] = {"root": root_id}
    if children_ids:
        tree["children"] = children_ids

    orientation = node.get("orientation")
    if orientation:
        tree["orientation"] = orientation

    return tree


def _iter_data_entries(data: Any):
    """Iterate (name, value) pairs from data section (dict or list form)."""
    if isinstance(data, dict):
        yield from data.items()
    elif isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict):
                name = entry.get("name")
                if name:
                    # list form: {"name": x, "type": y, "defaultValue": z}
                    # Pass the rest as the value dict
                    yield name, entry


def _extract_ui_variables(data: Any) -> list[dict]:
    """Extract uiVariables from Layout JSON data section."""
    variables = []
    for name, value in _iter_data_entries(data):
        if isinstance(value, dict):
            var_type = value.get("type", "String")
            default = value.get("defaultValue")
            entry: dict[str, Any] = {"name": name, "type": var_type}
            if default is not None:
                entry["default"] = default
            # Skip callback types
            if "Void" in var_type or "-> " in var_type:
                continue
            variables.append(entry)
        elif isinstance(value, str):
            # Check if it's a callback type
            if "Void" in value or "-> " in value:
                continue
            variables.append({"name": name, "type": value})
    return variables


def _extract_event_handlers(data: Any) -> list[dict]:
    """Extract event handlers from Layout JSON data section."""
    handlers = []
    for name, value in _iter_data_entries(data):
        type_str = ""
        if isinstance(value, dict):
            type_str = value.get("type", "")
        elif isinstance(value, str):
            type_str = value

        if "Void" in type_str or "-> " in type_str:
            handlers.append({"name": name, "description": ""})
    return handlers


def _is_placeholder(components: list) -> bool:
    """Check if components list is just a placeholder root."""
    if len(components) != 1:
        return False
    c = components[0]
    return (
        c.get("type") == "View"
        and c.get("id") in ("root_view", "root")
        and not c.get("children")
    )


def _deep_copy(obj: Any) -> Any:
    """Simple deep copy for JSON-compatible dicts."""
    import copy
    return copy.deepcopy(obj)
