"""The spec validator names what no tool carries out (jsonui-cli 1.9.0).

1. A key a Collection — or one of its sections — does not declare, as a
   WARNING: no tool reads it, so what it asks for does not happen. Measured
   2026-09-26 on the faces: cells (3), parent (1), sections[].headerData (1)
   and five keys of their own name (section2, image_grid, ...), each holding
   a cell's description. The keys the faces write for the reader
   (description, notes, a section's index) are declared, documentation only,
   and not named.
"""
from __future__ import annotations

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
