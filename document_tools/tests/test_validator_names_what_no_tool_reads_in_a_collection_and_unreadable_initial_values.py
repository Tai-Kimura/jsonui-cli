"""The spec validator names two things no tool carries out (jsonui-cli 1.9.0).

1. A key a Collection — or one of its sections — does not declare, as a
   WARNING: no tool reads it, so what it asks for does not happen. Measured
   2026-09-26 on the faces: cells (3), parent (1), sections[].headerData (1)
   and five keys of their own name (section2, image_grid, ...), each holding
   a cell's description. The keys the faces write for the reader
   (description, notes, a section's index) are declared, documentation only,
   and not named.
2. A uiVariable's initial value that does not read as a value of its declared
   type (Int / Double / Bool / Array / Object): INFO below
   INITIAL_VALUE_TYPE_GATE_FROM ("1.9.1", jui verify's release too) with one
   line naming it, WARNING from it. On the faces: 3, all prose written as an
   Array's initial value (2 in default, 1 in defaultValue). A JSON literal
   in a string ("0", "false", "[]") is that literal, as the platform tools
   read it.
"""
from __future__ import annotations

import pytest

from jsonui_doc_cli.spec_doc import validator as validator_mod
from jsonui_doc_cli.spec_doc.validator import SpecValidator


def _spec(collection=None, variables=None, collections=None):
    structure = {"components": [], "layout": {"root": "r", "children": []}}
    if collection is not None:
        structure["collection"] = collection
    if collections is not None:
        structure["collections"] = collections
    return {
        "type": "screen_spec", "version": "1.0",
        "metadata": {"name": "Home", "displayName": "H", "description": "d"},
        "structure": structure,
        "stateManagement": {"uiVariables": variables or []},
    }


COLLECTION = {
    "id": "items", "cell": {"root": "c", "layoutFile": "home/cell"},
    "description": "the list", "notes": "n", "insets": [8, 0, 8, 0],
    "cells": [{"viewName": "ItemCellView"}], "parent": "HeroSection", "item_grid": {"cellFile": "x.json"},
    "sections": [{"index": 0, "cell": "home/cell", "header": None, "description": "d", "notes": "n",
                  "headerData": {"headerTitle": "T"}, "columns": 2}],
}


def test_every_undeclared_collection_or_section_key_is_named_as_a_warning():
    result = SpecValidator().validate_data(_spec(COLLECTION))
    named = sorted(m.path for m in result.warnings if "is not a key" in m.message)
    assert named == ["structure.collection.cells", "structure.collection.item_grid",
                     "structure.collection.parent", "structure.collection.sections[0].headerData"], named
    by_path = {m.path: m.message for m in result.warnings}
    assert "cellClasses is the list of cell layouts the tools read" in by_path["structure.collection.cells"]
    assert "a section declares" in by_path["structure.collection.sections[0].headerData"]
    assert "data source" in by_path["structure.collection.sections[0].headerData"]


def test_a_collection_in_collections_is_held_the_same():
    result = SpecValidator().validate_data(_spec(collections=[{"id": "b", "cellClasses": ["home/row"],
                                                               "cells": []}]))
    assert [m.path for m in result.warnings if "is not a key" in m.message] == ["structure.collections[0].cells"]


def _var(value, type_="Array(String)", spelling="defaultValue"):
    return {"name": "items", "type": type_, "description": "d", spelling: value}


@pytest.mark.parametrize("variable", [
    _var("[a, b]（labels）"), _var("the last thirty years"), _var("x", "Int"), _var("yes", "Bool"),
    _var({"a": 1}, "[String]"), _var(1.5, "Int"), _var([1], "Dictionary<String, Any>"),
    _var("prose", spelling="default"),
], ids=["prose in an Array", "prose", "a word for an Int", "a word for a Bool", "an object for an Array",
        "a fraction for an Int", "an array for a Dictionary", "prose in default"])
def test_an_initial_value_that_is_not_a_value_of_its_type_is_named(variable):
    result = SpecValidator().validate_data(_spec(variables=[variable]))
    named = [m for m in result.infos if "is not a value of" in m.message]
    assert len(named) == 1 and named[0].path.startswith("stateManagement.uiVariables[0]."), result.infos
    assert any("from jsonui-cli 1.9.1, an initial value" in m.message for m in result.infos)
    assert not [m for m in result.warnings if "is not a value of" in m.message]


@pytest.mark.parametrize("variable", [
    _var("[]"), _var(["a"]), _var('["a", "b"]'), _var("0", "Int"), _var(0, "Int"), _var("false", "Bool"),
    _var(True, "Bool?"), _var("1.5", "Double"), _var("anything", "String"), _var("x", "ItemRow"),
    _var(None), _var("{}", "Dictionary<String, Any>"),
], ids=["[] in a string", "a list", "a JSON list in a string", "0 in a string", "0", "false in a string",
        "an optional Bool", "a number in a string", "a String", "a custom type", "null", "{} in a string"])
def test_a_value_of_its_type_in_any_spelling_is_not(variable):
    result = SpecValidator().validate_data(_spec(variables=[variable]))
    assert not [m for m in result.infos + result.warnings if "is not a value of" in m.message]


def test_a_cells_initial_values_are_checked_too():
    coll = {"id": "items", "cell": {"root": "c", "layoutFile": "home/cell",
                                    "uiVariables": [_var("some words")]}}
    result = SpecValidator().validate_data(_spec(coll))
    assert [m.path for m in result.infos if "is not a value of" in m.message] == [
        "structure.collection.cell.uiVariables[0].defaultValue"]


def test_from_the_release_it_is_a_warning_and_withdrawn_never(monkeypatch):
    monkeypatch.setattr(validator_mod, "INITIAL_VALUE_TYPE_GATE_FROM", "0.0.1")
    result = SpecValidator().validate_data(_spec(variables=[_var("prose")]))
    assert [m.level for m in result.warnings if "is not a value of" in m.message] == ["warning"]
    assert not any("from jsonui-cli" in m.message for m in result.infos)
    monkeypatch.setattr(validator_mod, "INITIAL_VALUE_TYPE_GATE_FROM", "withdrawn")
    result = SpecValidator().validate_data(_spec(variables=[_var("prose")]))
    assert [m.level for m in result.infos if "is not a value of" in m.message] == ["info"]
    assert not any("from jsonui-cli" in m.message for m in result.infos)


def test_the_release_is_the_one_jui_verify_counts_from():
    assert validator_mod.INITIAL_VALUE_TYPE_GATE_FROM == "1.9.1"
