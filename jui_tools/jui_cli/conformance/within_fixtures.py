"""`within`: one cell's child, looked up inside the cell.

Every cell of a Collection repeats the same child ids, so a step on a child
id alone reads the first cell's. A step's `within` names the cell
(`{collectionId}_item_{n}`) and the id is looked up among its descendants.
These fixtures render three cells whose titles differ and assert on the
SECOND and THIRD cell's child: a driver that ignores `within` reads
"Cell 0" and fails, so the cases cannot pass on the unscoped lookup.

* ``cells3`` — id-less root, three children: the title, a drawn badge and a
  child that is `visibility: gone`. `count` inside a cell is 1 where the
  screen holds 3; `hidden` inside a cell holds on the gone child (on iOS the
  first measurement of whether a gone child leaves XCUITest's tree, which
  is what the iOS driver's `hidden` takes as "not drawn").
* ``single`` — id-less root, ONE child: the single-child merge could put the
  cell's address on the child and leave nothing under the address.
* ``tap`` — a clickable cell root: a clickable node can merge its children
  into itself (Compose), which would leave no child to find inside it.

The probe these come from (Dynamic, both mobile platforms, 2026-10-24) is
the measurement that a cell's children are its descendants in the
accessibility / semantics tree; these fixtures carry it to both faces.
"""
from __future__ import annotations

from . import rules
from ..core.generated_marker import json_marker

GENERATOR_NAME = "jui conformance generate"
TEST_GENERATED_BY = "@generated jui conformance generate — DO NOT EDIT"

_PLATFORMS = ["ios", "android", "web"]

_TITLES = ["Cell 0", "Cell 1", "Cell 2"]


def _steps_cells3() -> list[dict]:
    return [
        {"action": "waitFor", "id": "root"},
        {"action": "waitFor", "id": "target_item_2"},
        {"assert": "text", "id": "within_title", "within": "target_item_1", "equals": "Cell 1"},
        {"assert": "text", "id": "within_title", "within": "target_item_2", "equals": "Cell 2"},
        {"assert": "count", "id": "within_title", "equals": 3},
        {"assert": "count", "id": "within_title", "within": "target_item_1", "equals": 1},
        {"assert": "visible", "id": "within_badge", "within": "target_item_1"},
        {"assert": "hidden", "id": "within_gone", "within": "target_item_1"},
    ]


def _steps_single() -> list[dict]:
    return [
        {"action": "waitFor", "id": "root"},
        {"action": "waitFor", "id": "target_item_2"},
        {"assert": "text", "id": "within_only", "within": "target_item_1", "equals": "Cell 1"},
        {"assert": "count", "id": "within_only", "within": "target_item_2", "equals": 1},
    ]


def _steps_tap() -> list[dict]:
    return [
        {"action": "waitFor", "id": "root"},
        {"action": "waitFor", "id": "target_item_2"},
        {"assert": "text", "id": "within_tap_title", "within": "target_item_1", "equals": "Cell 1"},
        {"assert": "visible", "id": "within_tap_badge", "within": "target_item_2"},
    ]


#: (case suffix, cell layout basename, steps, description)
_CASES = (
    ("cells3", "conformance_cell_within", _steps_cells3,
     "The second and third cell's children are read inside their cells: the title, "
     "a count of 1 where the screen holds 3, a drawn badge, and a gone child hidden."),
    ("single", "conformance_cell_within_single", _steps_single,
     "A cell with one child still has that child under its item address."),
    ("tap", "conformance_cell_within_tap", _steps_tap,
     "A clickable cell's children are still found inside the cell."),
)


def _layout(source_label: str, cell_name: str) -> dict:
    return {
        "_generated": json_marker(source=source_label, generator=GENERATOR_NAME),
        "type": "View",
        "id": "root",
        "width": "matchParent",
        "height": "matchParent",
        "child": [
            {
                "type": "Collection",
                "id": "target",
                "width": 200,
                "height": 200,
                "background": "#DDDDDD",
                "sections": [{"cell": cell_name}],
                "items": "@{items}",
                "layout": "flow",
            }
        ],
        "data": [
            {
                "name": "items",
                "class": "CollectionDataSource",
                "defaultValue": [{"title": t} for t in _TITLES],
            }
        ],
    }


def _test(name: str, description: str, layout_rel: str, steps: list[dict]) -> dict:
    return {
        "type": "screen",
        "source": {"layout": layout_rel},
        "metadata": {
            "name": f"conformance {name}",
            "description": description,
            "generatedBy": TEST_GENERATED_BY,
            "tags": ["conformance", "Collection", "within"],
        },
        "platform": "all",
        "cases": [{"name": name, "description": description, "steps": steps}],
    }


def build_within_fixtures(source_label: str) -> tuple[list[tuple[str, dict]], list[dict]]:
    """``(files, manifest entries)`` for the `within` family."""
    files: list[tuple[str, dict]] = []
    entries: list[dict] = []
    for suffix, cell_name, steps, description in _CASES:
        case = f"within__{suffix}"
        layout_rel = f"fixtures/Collection/{case}.layout.json"
        test_rel = f"fixtures/Collection/{case}.test.json"
        files.append((layout_rel, _layout(source_label, cell_name)))
        files.append((test_rel, _test(case, description, layout_rel, steps())))
        entries.append({
            "id": f"Collection/{case}",
            "component": "Collection",
            "attribute": "layout",
            "case": case,
            "class": rules.CLASS_ASSERTABLE,
            "host": "Collection",
            "writtenKey": "layout",
            "aliasOf": None,
            "value": "flow",
            "platforms": list(_PLATFORMS),
            "mode": None,
            "deprecated": None,
            "layout": layout_rel,
            "test": test_rel,
            "state": None,
            "promotedFrom": None,
            "peerGroup": None,
            "control": None,
            # The family's own cell rides on its entries only, so no other
            # Collection entry moves.
            "companions": list(rules.BASE_COMPANIONS["Collection"]) + [
                f"fixtures/Collection/__cells/{cell_name}.layout.json"
            ],
        })
    return files, entries
