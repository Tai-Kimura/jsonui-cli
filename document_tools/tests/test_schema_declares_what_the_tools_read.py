"""The screen spec schema declares the fields the tools read.

Measured 2026-09-26 by running the Python tools' spec commands on a spec
synthesized from this schema, every key asked recorded: these were read and
not declared — the uiVariable initial value (`jui g project`, `jui verify`),
structure.collections (every tool), a repository's description (g project),
a tab's icon / selectedIcon / iconType and the older `view` (g project), a
Collection's cellClasses and sections (the validator, jsonui-doc),
canonicalDivergence's omitted / wrapped / added (the canon — and the schema's
additionalProperties: false called them invalid), metadata.group (the flow
diagram), a component's platform (jsonui-doc; now g project too). A field the
tools ask authors to write belongs in the declaration first.

Where a second declaration of the same thing exists, the arm reads it rather
than restating it: the canon's own tuple of divergence fields, and the Layout
JSON's TabView tabs and Collection sections in attribute_definitions.json.
"""
from __future__ import annotations

import json

import pytest

from jsonui_doc_cli import shared_core
from jsonui_doc_cli.spec_doc.screen_spec_schema import SCREEN_SPEC_SCHEMA as SCHEMA

DEFS = SCHEMA["$defs"]


def _props(name: str) -> dict:
    return DEFS[name]["properties"]


def _attribute_definitions() -> dict:
    core = shared_core.shared_core_dir()
    if core is None:
        pytest.skip("shared/core is not beside document_tools")
    return json.loads((core / "attribute_definitions.json").read_text(encoding="utf-8"))


def test_a_ui_variable_declares_both_spellings_of_its_initial_value():
    assert {"default", "defaultValue"} <= set(_props("uiVariable"))


def test_structure_declares_collections_as_more_collections():
    assert _props("structure")["collections"] == {
        "type": "array", "items": {"$ref": "#/$defs/collectionStructure"},
        "description": _props("structure")["collections"]["description"]}


def test_a_repository_declares_its_description():
    assert _props("repository")["description"]["type"] == "string"


def test_divergence_fields_are_the_canons_own():
    canon = shared_core.load("openapi_canonical")
    if canon is None:
        pytest.skip("shared/core is not beside document_tools")
    declared = set(_props("repositoryMethod")["canonicalDivergence"]["properties"])
    assert declared == set(canon._DIVERGENCE_FIELDS), (declared, canon._DIVERGENCE_FIELDS)


def test_a_tab_declares_what_the_layouts_tabview_tab_takes_from_it():
    layout_tab = _attribute_definitions()["TabView"]["tabs"]["items"]["properties"]
    tab = _props("tab")
    for key in ("icon", "selectedIcon", "iconType", "view"):
        assert key in tab and key in layout_tab, key
    assert tab["iconType"]["enum"] == layout_tab["iconType"]["enum"]
    assert tab["view"].get("deprecated") is True


def test_a_collection_declares_cell_classes_and_sections_like_the_layouts():
    coll = _props("collectionStructure")
    layout_sections = _attribute_definitions()["Collection"]["sections"]["items"]["properties"]
    assert coll["cellClasses"]["items"] == {"type": "string"}
    # A section holds the Layout's keys, plus three the faces write for the
    # reader (jsonui-cli 1.9.0) — documentation only, so nothing reads them.
    spec_sections = coll["sections"]["items"]["properties"]
    assert set(layout_sections) <= set(spec_sections)
    for key in set(spec_sections) - set(layout_sections):
        assert "Documentation only" in spec_sections[key]["description"], key
    assert set(spec_sections) - set(layout_sections) == {"index", "description", "notes"}
    # insets: the Layout Collection's, written onto it by jui g project.
    assert coll["insets"]["type"] == _attribute_definitions()["Collection"]["insets"]["type"]
    # `cell` is one of three ways to name the cells (the validator's rule).
    assert DEFS["collectionStructure"]["required"] == ["id"]


def test_a_cell_entry_declares_the_layout_node_forms_tree():
    cell_node = _props("cellNode")
    assert {"children", "overlay", "generateCellLayout", "layoutFile"} <= set(cell_node)
    for slot in ("cell", "header", "footer"):
        assert "anyOf" in _props("collectionStructure")[slot], slot


def test_metadata_declares_the_flow_diagrams_group_and_a_component_its_platform():
    assert "group" in _props("metadata")
    assert "platform" in _props("component")
