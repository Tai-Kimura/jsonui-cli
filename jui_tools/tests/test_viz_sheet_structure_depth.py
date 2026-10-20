"""The sheet's structure carries each component's depth (ticket 2026-10-20-jui-viz-spec-structure-shows-no-nesting).

The page rebuilds the tree from the order and the depths (a row's parent is the nearest row above it one level up),
so the rows must be depth-first with depth 0 first and never more than one level deeper than the row above.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from jui_cli.viz.sheet import build_doc
from jui_cli.viz.sources.jsonui_project import layout_nodes, section_items

IMPL = {"total": 0, "done": 0}

# the requester's shape (item_detail): four levels under the root, siblings at each, an id-less View
LAYOUT = {"type": "SafeAreaView", "id": "root_view", "child": [
    {"type": "View", "id": "loading_container", "child": [{"type": "Indicator", "id": "loading_indicator"}]},
    {"type": "View", "id": "content_container", "child": [
        {"type": "View", "id": "add_item_dock", "child": {"type": "Button", "id": "add_item_button"}},
        {"type": "View", "id": "promo_dock", "children": [
            {"type": "View", "children": [{"type": "Image", "id": "lock_icon"}, {"type": "Label", "id": "dock_label"}]},
            {"type": "Button", "id": "dock_button"}]}]}]}
# each id's parent in LAYOUT (None: the root; "#6": the id-less View, the 7th node)
PARENT = {"root_view": None, "loading_container": "root_view", "loading_indicator": "loading_container",
          "content_container": "root_view", "add_item_dock": "content_container", "add_item_button": "add_item_dock",
          "promo_dock": "content_container", "#7": "promo_dock", "lock_icon": "#7", "dock_label": "#7", "dock_button": "promo_dock"}


def nodes_of(tree) -> list:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(tree, f)
    try:
        return layout_nodes(Path(f.name))
    finally:
        os.unlink(f.name)


def rebuild(rows) -> dict:
    """The page's rule: a row's parent is the nearest row above it one level up."""
    out, stack = {}, []
    for i, row in enumerate(rows):
        name, depth = row[1] or f"#{i}", row[3]
        del stack[depth:]
        out[name] = stack[-1] if stack else None
        stack.append(name)
    return out


def well_formed(rows) -> bool:
    depths = [r[3] for r in rows]
    return bool(depths) and depths[0] == 0 and all(isinstance(d, int) and 0 <= d <= p + 1 for p, d in zip(depths, depths[1:]))


def test_the_layout_tree_comes_with_numeric_depths_that_rebuild_it():
    doc = build_doc({}, nodes_of(LAYOUT), [], IMPL)
    rows = doc["components"]
    assert [r[3] for r in rows] == [0, 1, 2, 1, 2, 3, 2, 3, 4, 4, 3]
    assert well_formed(rows)
    assert rebuild(rows) == PARENT
    # the description is the type alone: the depth is no longer spaces in front of it
    assert all(r[2] == r[0] for r in rows)


def test_a_cut_layout_is_still_a_tree():
    deep = {"type": "View", "id": "d0"}
    node = deep
    for k in range(1, 400):
        node["child"] = {"type": "View", "id": f"d{k}"}
        node = node["child"]
    rows = build_doc({}, nodes_of(deep), [], IMPL)["components"]
    assert len(rows) == 300 and well_formed(rows) and rows[-1][3] == 299


def test_listed_components_follow_structure_layout():
    spec = {"structure": {
        "components": [{"type": "Label", "id": "orphan", "description": "not in the tree"},
                       {"type": "Button", "id": "save", "description": "保存"},
                       {"type": "View", "id": "root", "description": "画面"},
                       {"type": "View", "id": "form", "description": "フォーム"},
                       {"type": "TextField", "id": "name", "description": "名前"},
                       {"type": "Label", "id": "hint", "description": "説明"}],
        "layout": {"root": "root", "children": [
            {"id": "form", "children": ["name", {"id": "unlisted_row", "children": ["hint"]}]}, "save"]}}}
    rows = build_doc(spec, [], [], IMPL)["components"]
    assert [(r[1], r[3]) for r in rows] == [("root", 0), ("form", 1), ("name", 2), ("hint", 2), ("save", 1), ("orphan", 0)]
    assert rows[1] == ["View", "form", "フォーム", 1]
    assert well_formed(rows)
    # each listed component once: the count the spec list gives
    assert len(rows) == section_items(spec, "structure") == 6


def test_listed_components_without_a_tree_are_one_level():
    spec = {"structure": {"components": [{"type": "Label", "id": "a"}, {"type": "Label", "id": "b"}], "layout": {}}}
    assert [r[3] for r in build_doc(spec, [], [], IMPL)["components"]] == [0, 0]
    root_only = {"structure": {"components": [{"type": "Label", "id": "a"}, {"type": "View", "id": "r"}],
                               "layout": {"children": ["r", {"id": "a"}]}}}
    assert [(r[1], r[3]) for r in build_doc(root_only, [], [], IMPL)["components"]] == [("r", 0), ("a", 0)]
