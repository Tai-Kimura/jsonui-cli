"""The layout facts a screen spec declares reach what `jui g project` writes.

Measured 2026-09-26 (round 5 of ticket
generate-commands-overwrite-edited-files-and-ignore-their-flags): of the
fields the spec schema declares, these were read by jsonui-doc and the
validator only — no generated layout carried them:

- structure.embeds[] -> an Embed node per regionId: where the layout tree
  names it, else appended to the root container (every declared region is in
  the layout, as the pack's implement agent requires).
- structure.layout.root -> the container of the layout's children: that
  structure.components entry (type, style, bindings) when declared, else a
  View, with the id.
- A Collection's cell / header / footer with generateCellLayout: its own
  Layout JSON, from an object root (the component tree) or a string root with
  the layoutNode form's children / overlay / zIndex under it; its
  uiVariables / eventHandlers give the data section. Only the cell was
  written before, and only for an object root — the pack's documented form
  (a string root) wrote nothing.
- The Collection's section names the layout the entry declares or generates
  (layoutFile, else <collection id>_<kind>), not the root id: sjui resolves a
  section's name to the cell view class and Dynamic mode loads it as a file.
- A spec with no structure.layout still gets its Collection (and embeds).
- structure.components[].platform -> the node's `platform` directive.

Plus two guards of the same family: `jui g project` does not overwrite an
entry's layout whose data section holds entries the spec does not declare,
and those entries are found wherever the layout declares `data`.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path

import pytest

from jui_cli.core.spec_extractor import extract_screen_spec
from jui_cli.core.type_mapper import TypeMapper
from jui_cli.generators.cell_layout_generator import CellLayoutGenerator
from jui_cli.generators.layout_generator import LayoutGenerator

REPO = Path(__file__).resolve().parents[2]


def _spec(structure: dict, ui_variables: list | None = None) -> dict:
    return {
        "type": "screen_spec", "version": "1.0",
        "metadata": {"name": "Probe", "displayName": "Probe", "description": "d"},
        "structure": {"components": [], **structure},
        "stateManagement": {"uiVariables": ui_variables or []},
    }


def _layout(structure: dict) -> dict:
    return LayoutGenerator(TypeMapper()).generate(extract_screen_spec(_spec(structure)))


def _nodes(tree, pred=lambda n: True) -> list[dict]:
    out = []

    def walk(n):
        if isinstance(n, dict):
            if pred(n):
                out.append(n)
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
    walk(tree)
    return out


def _container(layout: dict) -> dict:
    """The node holding the layout's children."""
    return next(n for n in _nodes(layout) if isinstance(n.get("children"), list))


C = [{"id": "title", "type": "Label", "description": "t"},
     {"id": "root_view", "type": "SafeAreaView", "description": "r", "style": {"background": "bg"}}]
EMBED = {"regionId": "detailPane", "screen": "order_detail", "params": {"orderId": "@{selectedOrderId}"},
         "events": {"onOrderUpdated": "handleOrderUpdated"}, "navigationMode": "delegate"}


# ---- structure.embeds -------------------------------------------------------

def test_an_embed_the_layout_tree_names_is_an_embed_node_there():
    layout = _layout({"components": C, "layout": {"root": "r", "children": ["title", "detailPane"]},
                      "embeds": [EMBED]})
    children = _container(layout)["children"]
    assert [c["id"] for c in children] == ["title", "detailPane"]
    assert children[1] == {"type": "Embed", "id": "detailPane", "screen": "order_detail",
                           "params": {"orderId": "@{selectedOrderId}"},
                           "events": {"onOrderUpdated": "handleOrderUpdated"}, "navigationMode": "delegate"}


def test_an_embed_the_tree_does_not_name_is_appended_and_given_keys_only():
    layout = _layout({"components": C, "layout": {"root": "r", "children": ["title"]},
                      "embeds": [{"regionId": "sidePane", "screen": "side"}]})
    assert _container(layout)["children"][-1] == {"type": "Embed", "id": "sidePane", "screen": "side"}


def test_no_embeds_no_embed_node():
    layout = _layout({"components": C, "layout": {"root": "r", "children": ["title", "detailPane"]}})
    assert not _nodes(layout, lambda n: n.get("type") == "Embed")
    assert {"type": "View", "id": "detailPane"} in _container(layout)["children"]


# ---- structure.layout.root --------------------------------------------------

def test_the_layout_root_is_the_declared_component_holding_the_children():
    inner = _container(_layout({"components": C, "layout": {"root": "root_view", "children": ["title"]}}))
    assert (inner["type"], inner["id"], inner["background"]) == ("SafeAreaView", "root_view", "bg")
    assert inner["orientation"] == "vertical"
    assert [c["id"] for c in inner["children"]] == ["title"]


def test_an_undeclared_root_is_a_view_with_its_id_and_overlay_stacks():
    inner = _container(_layout({"components": C, "layout": {"root": "stack", "overlay": True,
                                                              "children": ["title"]}}))
    assert (inner["type"], inner["id"]) == ("View", "stack")
    assert "orientation" not in inner


def test_a_root_id_the_tree_already_uses_is_not_written_twice():
    layout = _layout({"components": C, "layout": {"root": "title", "children": ["title"]}})
    assert len(_nodes(layout, lambda n: n.get("id") == "title")) == 1


def test_a_layout_with_no_children_carries_the_root_id_itself():
    assert _layout({"components": C, "layout": {"root": "only_root", "children": []}}).get("id") == "only_root"


def test_no_root_no_id():
    inner = _container(_layout({"components": C, "layout": {"children": ["title"]}}))
    assert "id" not in inner


# ---- a spec without structure.layout ----------------------------------------

def test_a_collection_without_structure_layout_is_still_in_the_layout():
    layout = _layout({"collection": {"id": "items", "cell": {"root": "item_root"}}, "embeds": [EMBED]})
    types = [c["type"] for c in _container(layout)["children"]]
    assert types == ["Embed", "Collection"], types


# ---- components[].platform --------------------------------------------------

@pytest.mark.parametrize("platform", ["ios", {"web": {"hidden": True}}], ids=["string", "map"])
def test_a_components_platform_reaches_its_node(platform):
    comps = [{"id": "title", "type": "Label", "description": "t", "platform": platform}]
    title = _nodes(_layout({"components": comps, "layout": {"root": "r", "children": ["title"]}}),
                   lambda n: n.get("id") == "title")[0]
    assert title["platform"] == platform


# ---- cell / header / footer -------------------------------------------------

def _slots(collection: dict, components=None):
    s = extract_screen_spec(_spec({"components": components or C, "collection": collection}))
    lg = LayoutGenerator(TypeMapper())
    lg.generate(s)
    cg = CellLayoutGenerator(lg)
    coll = s.collections[0]
    return {slot.kind: (cg.generate_slot(slot, s), cg.slot_output_path(coll, slot, Path("L")))
            for slot in cg.slots_to_generate(coll)}, coll


def test_a_string_root_cell_is_written_with_its_children():
    out, _ = _slots({"id": "items", "cell": {
        "root": "item_cell_root", "layoutFile": "item_list/item_cell", "generateCellLayout": True,
        "children": ["title", {"id": "badge", "zIndex": 2}],
        "uiVariables": [{"name": "itemName", "type": "String", "description": "d", "defaultValue": "x"}]}})
    cell, path = out["cell"]
    assert path == Path("L/item_list/item_cell.json")
    assert (cell["type"], cell["id"], cell["orientation"]) == ("View", "item_cell_root", "vertical")
    assert cell["children"] == [{"type": "Label", "id": "title"}, {"type": "View", "id": "badge", "zIndex": 2}]
    assert cell["data"] == [{"name": "itemName", "class": "String", "defaultValue": "x", "description": "d"}]


def test_an_overlay_cell_stacks():
    out, _ = _slots({"id": "items", "cell": {"root": "r", "generateCellLayout": True, "overlay": True,
                                              "children": ["title"]}})
    assert "orientation" not in out["cell"][0]


def test_a_header_and_a_footer_are_written_like_the_cell():
    out, _ = _slots({"id": "items", "cell": {"root": "c"},
                     "header": {"root": {"id": "hdr", "type": "View", "children": [
                         {"id": "hdr_title", "type": "Label", "description": "t"}]},
                         "generateCellLayout": True,
                         "uiVariables": [{"name": "headerTitle", "type": "String", "description": "d"}],
                         "eventHandlers": [{"name": "onHeaderTap", "description": "d"}]},
                     "footer": {"root": "ftr", "layoutFile": "items/footer", "generateCellLayout": True,
                                "children": ["title"]}})
    assert set(out) == {"header", "footer"}, "the cell does not opt in"
    header, hpath = out["header"]
    assert hpath == Path("L/items_header.json")
    assert (header["id"], header["child"]) == ("hdr", [{"type": "Label", "id": "hdr_title"}])
    assert [e["name"] for e in header["data"]] == ["headerTitle", "onHeaderTap"]
    footer, fpath = out["footer"]
    assert fpath == Path("L/items/footer.json") and footer["children"] == [{"type": "Label", "id": "title"}]


def test_an_entry_without_generate_cell_layout_is_not_written():
    out, _ = _slots({"id": "items", "cell": {"root": {"id": "c", "type": "View"}, "children": ["title"]},
                     "header": {"root": "h", "layoutFile": "x/h"}})
    assert out == {}


@pytest.mark.parametrize("entry,want", [
    ({"root": "item_cell_root", "layoutFile": "item_list/item_cell"}, "item_list/item_cell"),
    ({"root": "item_cell_root", "layout": "item_list/item_cell.json"}, "item_list/item_cell"),
    ({"root": {"id": "item_cell_root", "type": "View"}, "generateCellLayout": True}, "items_cell"),
    ({"root": "item_cell_root"}, "item_cell_root"),
], ids=["layoutFile", "the deprecated layout", "generated default", "neither: the root id"])
def test_the_section_names_the_layout_the_entry_declares_or_generates(entry, want):
    _, coll = _slots({"id": "items", "cell": entry, "header": dict(entry)})
    assert coll.sections == [{"cell": want, "header": want.replace("_cell", "_header")
                              if want == "items_cell" else want}]


def test_build_counts_a_generated_header_as_a_cell_layout(tmp_path):
    from jui_cli.commands.build_cmd import _spec_cell_layout_stems
    from jui_cli.core.config_manager import ConfigManager
    (tmp_path / "specs").mkdir()
    (tmp_path / "jui.config.json").write_text(json.dumps({"spec_directory": "specs"}))
    (tmp_path / "specs/p.spec.json").write_text(json.dumps(_spec({"collection": {
        "id": "items", "cell": {"root": "c"}, "header": {"root": "h", "generateCellLayout": True}}})))
    assert "items_header" in _spec_cell_layout_stems(ConfigManager(tmp_path / "jui.config.json"))


# ---- through the command ----------------------------------------------------

@pytest.fixture
def project(tmp_path):
    (tmp_path / "docs/screens/json").mkdir(parents=True)
    (tmp_path / "docs/screens/layouts").mkdir(parents=True)
    (tmp_path / "jui.config.json").write_text(json.dumps({
        "spec_directory": "docs/screens/json", "layouts_directory": "docs/screens/layouts",
        "platforms": {"web": {"root": "web"}}}))
    (tmp_path / "web").mkdir()
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(cwd)


def _g_project(project: Path, structure: dict, *args: str) -> str:
    from jui_cli.cli import main
    (project / "docs/screens/json/probe.spec.json").write_text(json.dumps(_spec(structure)))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        main(["g", "project", *args])
    return out.getvalue()


STRUCTURE = {"components": C, "layout": {"root": "root_view", "children": ["title"]},
             "collection": {"id": "items", "cell": {"root": "c", "layoutFile": "probe/cell",
                                                     "generateCellLayout": True},
                            "header": {"root": "h", "layoutFile": "probe/header", "generateCellLayout": True}}}


def test_g_project_writes_the_header_and_the_cell(project):
    said = _g_project(project, STRUCTURE)
    layouts = project / "docs/screens/layouts"
    assert (layouts / "probe/cell.json").is_file() and (layouts / "probe/header.json").is_file(), said
    screen = json.loads((layouts / "probe.json").read_text())
    coll = _nodes(screen, lambda n: n.get("type") == "Collection")[0]
    assert coll["sections"] == [{"cell": "probe/cell", "header": "probe/header"}]


def test_g_project_keeps_an_existing_entry_layout_that_differs(project):
    header = project / "docs/screens/layouts/probe/header.json"
    header.parent.mkdir(parents=True)
    kept = {"type": "View", "id": "h", "child": [{"data": [{"name": "handWritten", "class": "String"}]}]}
    header.write_text(json.dumps(kept))
    said = _g_project(project, STRUCTURE)
    assert json.loads(header.read_text()) == kept, said
    assert ("Kept existing header layout: docs/screens/layouts/probe/header.json (it differs from what the "
            "spec generates; --force replaces it)") in said, said


def test_force_does_not_replace_one_whose_nested_data_the_spec_does_not_declare(project):
    header = project / "docs/screens/layouts/probe/header.json"
    header.parent.mkdir(parents=True)
    kept = {"type": "View", "id": "h", "child": [{"data": [{"name": "handWritten", "class": "String"}]}]}
    header.write_text(json.dumps(kept))
    said = _g_project(project, STRUCTURE, "--force")
    assert json.loads(header.read_text()) == kept, said
    assert "existing header Layout JSON has data entries not declared" in said and "data.handWritten" in said


def test_a_hand_edited_screen_layout_is_kept_and_force_replaces_it(project):
    _g_project(project, STRUCTURE)
    screen = project / "docs/screens/layouts/probe.json"
    edited = json.loads(screen.read_text())
    edited["background"] = "#FF0000"
    screen.write_text(json.dumps(edited, indent=2))
    said = _g_project(project, STRUCTURE)
    assert json.loads(screen.read_text())["background"] == "#FF0000", said
    assert "Kept existing layout: docs/screens/layouts/probe.json" in said
    said = _g_project(project, STRUCTURE, "--force")
    assert "background" not in json.loads(screen.read_text()), said
    assert "Replaced: docs/screens/layouts/probe.json" in said


def test_a_layout_the_spec_generates_unchanged_is_not_rewritten(project):
    _g_project(project, STRUCTURE)
    screen = project / "docs/screens/layouts/probe.json"
    before = (screen.read_bytes(), screen.stat().st_mtime_ns)
    said = _g_project(project, STRUCTURE)
    assert (screen.read_bytes(), screen.stat().st_mtime_ns) == before
    assert "probe.json" not in said, said


def test_a_specs_cell_classes_sections_and_insets_reach_a_new_collection(project):
    _g_project(project, {"components": C, "layout": {"root": "root_view", "children": ["title"]},
                         "collection": {"id": "messages", "cellClasses": ["chat/message_cell", "chat/typing_cell"],
                                        "insets": [12, 0, 0, 0],
                                        "sections": [{"index": 0, "cell": "chat/message_cell",
                                                      "header": "chat/day_header", "description": "d"},
                                                     {"cell": "chat/typing_cell", "header": None, "columns": 2}]}})
    screen = json.loads((project / "docs/screens/layouts/probe.json").read_text())
    coll = _nodes(screen, lambda n: n.get("type") == "Collection")[0]
    assert coll["cellClasses"] == ["chat/message_cell", "chat/typing_cell"]
    assert coll["insets"] == [12, 0, 0, 0]
    assert coll["sections"] == [{"cell": "chat/message_cell", "header": "chat/day_header"},
                                {"cell": "chat/typing_cell", "columns": 2}]
