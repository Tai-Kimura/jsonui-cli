"""Collection cell-address fixtures the generic per-attribute sweep cannot reach.

Test drivers reach a Collection's cells as ``{collectionId}_item_{index}`` —
``tapItem`` and ``waitFor`` resolve nothing else. The sweep's Collection
fixtures are all ``class: visual`` ([waitFor root, screenshot]), and the
Android suite skips ``waitFor`` for visual fixtures outright, so nothing in
the corpus has ever asked whether a cell CAN be addressed. Two things hid
behind that:

* the static codegens had two layout arms (flow, non-lazy horizontal) that
  emitted no cell address at all — jsonui-cli ``b7124797`` — and every
  fixture runs through the dynamic renderers, which emitted none on ANY
  layout until SwiftJsonUI 10.19.0 / KotlinJsonUI 2.26.0;
* on iOS, a Collection rendered without a scroll container (``lazy:
  "none"``) is not an accessibility element, so its bare identifier is
  pushed down onto every cell and renames them to the collection's id —
  ``waitFor target_item_0`` times out while ``assert visible target`` passes
  against a renamed cell. The sweep's ``layout__flow`` declares no ``lazy``,
  so it exercises the ScrollView shape only and could not see this.

One family: ``flow`` × {default lazy, ``lazy: "none"``} × {1 cell, 2 cells},
each ``class: assertable`` with a ``waitFor`` per cell address. One cell is
the shape that merges a container into its only child; two is the shape
that showed every cell wearing the collection's id. No negative control
ships here — a fixture that must fail is a probe instrument, not corpus.
"""
from __future__ import annotations

from . import rules
from ..core.generated_marker import json_marker

GENERATOR_NAME = "jui conformance generate"
TEST_GENERATED_BY = "@generated jui conformance generate — DO NOT EDIT"

_PLATFORMS = ["ios", "android", "web"]

#: (case suffix, `lazy` value or None for undeclared) — the container shape.
_SHAPES = (("scroll", None), ("none", "none"))
#: cell counts — one merges, two showed the rename.
_COUNTS = (1, 2)


def _marker(source_label: str) -> dict:
    return json_marker(source=source_label, generator=GENERATOR_NAME)


def _layout(source_label: str, lazy: str | None, count: int) -> dict:
    target = {
        "type": "Collection",
        "id": "target",
        "width": 150,
        "height": 200,
        "background": "#DDDDDD",
        "sections": [{"cell": "conformance_cell"}],
        "items": "@{items}",
        "layout": "flow",
    }
    if lazy is not None:
        target["lazy"] = lazy
    return {
        "_generated": _marker(source_label),
        "type": "View",
        "id": "root",
        "width": "matchParent",
        "height": "matchParent",
        "child": [target],
        "data": [
            {
                "name": "items",
                "class": "CollectionDataSource",
                "defaultValue": [{"title": f"Cell {i}"} for i in range(count)],
            }
        ],
    }


def _test(name: str, description: str, layout_rel: str, count: int) -> dict:
    steps = [{"action": "waitFor", "id": "root"}]
    steps += [{"action": "waitFor", "id": f"target_item_{i}"} for i in range(count)]
    return {
        "type": "screen",
        "source": {"layout": layout_rel},
        "metadata": {
            "name": f"conformance {name}",
            "description": description,
            "generatedBy": TEST_GENERATED_BY,
            "tags": ["conformance", "Collection"],
        },
        "platform": "all",
        "cases": [{"name": name, "description": description, "steps": steps}],
    }


def build_collection_address_fixtures(
    source_label: str,
) -> tuple[list[tuple[str, dict]], list[dict]]:
    """``(files, manifest entries)`` for the cell-address family."""
    files: list[tuple[str, dict]] = []
    entries: list[dict] = []
    for shape, lazy in _SHAPES:
        for count in _COUNTS:
            case = f"cellAddress__{shape}_{count}"
            fid = f"Collection/{case}"
            layout_rel = f"fixtures/Collection/{case}.layout.json"
            test_rel = f"fixtures/Collection/{case}.test.json"
            description = (
                f"Every cell of a flow Collection ({'no scroll container' if lazy else 'default container'}, "
                f"{count} cell{'s' if count > 1 else ''}) is addressable as target_item_N."
            )
            files.append((layout_rel, _layout(source_label, lazy, count)))
            files.append((test_rel, _test(case, description, layout_rel, count)))
            entries.append({
                "id": fid,
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
                # Assertable: the fixture states its own expectation.
                "control": None,
                "companions": list(rules.BASE_COMPANIONS["Collection"]),
            })

    files.extend(_no_items_files(source_label))
    entries.append(_no_items_entry())
    return files, entries


#: A horizontal sectioned Collection that declares NO `items`.
#:
#: The sjui converter has an emit site for exactly this — `elsif cell_view_name`
#: inside the horizontal sections loop, taken when `extract_property_name`
#: returns nil — and the corpus had no declaration that reached it: every
#: Collection fixture carried `items`, so the branch emitted its cell address
#: under no gate at all. Measured over 288 generated shapes, this is one of two
#: that reach it (the other spells `items` as a non-binding literal, which is
#: the same nil through a different door).
#:
#: `declaration-only` rather than `assertable`: this Collection renders no
#: cells at all, so there is no `target_item_0` to assert.
#:
#: ⚠️ It was written believing the cells came from
#: `collectionDataSource.getCellData(for:)`, with a note that whether the host
#: supplies that had NOT been measured. Measured now: BOTH halves are absent.
#: No layout in the corpus or in either consuming iOS face declares
#: `collectionDataSource`, and `CollectionDataSource`'s public API is
#: `sections` / `init` / `reconfigured` — there is no lookup-by-cell-name
#: method and there never was. That branch emitted Swift which could not
#: compile, and this fixture was the first thing ever to reach it: the codegen
#: host failed the build on it. The branch is gone; the shape now emits no
#: cells and a build warning names the layout.
#:
#: So what this fixture pins is the opposite of what it was written to pin —
#: that a Collection naming cells with no `items` still COMPILES. That is
#: worth keeping: it is the only fixture with the shape, and the defect it
#: found was invisible to every unit spec because they asserted the emitted
#: TEXT, which no compiler had read.
_NO_ITEMS_CASE = "cellAddress__horizontalSectionsNoItems"


def _no_items_layout(source_label: str) -> dict:
    return {
        "_generated": _marker(source_label),
        "type": "View",
        "id": "root",
        "width": "matchParent",
        "height": "matchParent",
        "child": [{
            "type": "Collection",
            "id": "target",
            "width": 150,
            "height": 200,
            "background": "#DDDDDD",
            "layout": "horizontal",
            "sections": [{"cell": "conformance_cell"}],
        }],
    }


def _no_items_files(source_label: str) -> list[tuple[str, dict]]:
    layout_rel = f"fixtures/Collection/{_NO_ITEMS_CASE}.layout.json"
    test_rel = f"fixtures/Collection/{_NO_ITEMS_CASE}.test.json"
    description = (
        "A horizontal sectioned Collection declaring no items emits no cells "
        "and still compiles; the layout is named by a build warning."
    )
    test = _test(_NO_ITEMS_CASE, description, layout_rel, 0)
    return [(layout_rel, _no_items_layout(source_label)), (test_rel, test)]


def _no_items_entry() -> dict:
    layout_rel = f"fixtures/Collection/{_NO_ITEMS_CASE}.layout.json"
    return {
        "id": f"Collection/{_NO_ITEMS_CASE}",
        "component": "Collection",
        "attribute": "layout",
        "case": _NO_ITEMS_CASE,
        "class": rules.CLASS_DECLARATION_ONLY,
        "host": "Collection",
        "writtenKey": "layout",
        "aliasOf": None,
        "value": "horizontal",
        "platforms": list(_PLATFORMS),
        "mode": None,
        "deprecated": None,
        "layout": layout_rel,
        "test": f"fixtures/Collection/{_NO_ITEMS_CASE}.test.json",
        "state": None,
        "promotedFrom": None,
        "peerGroup": None,
        "control": None,
        "companions": list(rules.BASE_COMPANIONS["Collection"]),
    }
