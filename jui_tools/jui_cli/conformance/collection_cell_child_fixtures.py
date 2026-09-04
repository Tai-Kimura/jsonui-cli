"""Cells whose ROOT declares no id — the shape the corpus never had.

``collection_address_fixtures`` asks whether a cell is addressable as
``{collectionId}_item_{index}``. It cannot ask what that address costs,
because every Collection fixture in the corpus renders the same cell,
``conformance_cell``, and that cell's root declares ``id: "cell_root"``.

That one declaration is why the suite was green through the defect. A
Collection wraps each cell with ``.accessibilityIdentifier`` and a plain
SwiftUI container is not an accessibility element, so the identifier is
pushed down onto the cell's own children — unless the root is already an
explicit container, which is exactly what declaring an id made it. Measured
2026-09-05 in a consumer: 8 of 8 cells explained by that discriminator, the
children of an id-less cell root answering to ``{id}_item_{N}`` instead of
their own identifiers while the generated code still showed the right
modifier and every gate stayed green.

So the corpus could not reproduce the defect: it only ever tried the safe
shape. These fixtures add the missing one.

* ``bare_2`` — id-less root, two identified children. The reported shape.
* ``bare_1`` — id-less root, ONE identified child. The single-child merge:
  SwiftUI collapses a container holding one accessibility child, which puts
  the wrapper's address back onto that child. The static side emits an
  anchor overlay to prevent it; the dynamic renderer has no input to decide
  that at the point it wraps a cell, so this fixture is what decides whether
  dynamic needs one. It is not a duplicate of ``bare_2``.
* ``tap`` — ``tapItem index: 0`` against the id-less cell, then a child.
  The corpus has exactly ONE ``tapItem`` step in total and it runs against
  the id-bearing cell, so nothing measured whether making a cell root an
  accessibility container changes what a tap resolves to. A repair that
  rescues the child identifiers and breaks item tapping would otherwise
  trade one silent failure for another.

The existing ``conformance_cell`` fixtures stay exactly as they are: they
are now the id-bearing control, and their passing on both faces is what
raises "a nested container behaves the same" from inference to measurement.
"""
from __future__ import annotations

from . import rules
from ..core.generated_marker import json_marker

GENERATOR_NAME = "jui conformance generate"
TEST_GENERATED_BY = "@generated jui conformance generate — DO NOT EDIT"

_PLATFORMS = ["ios", "android", "web"]

#: (case suffix, cell layout basename, child ids) — the cell shapes.
_CELLS = (
    ("bare_2", "conformance_cell_bare", ("cell_child_a", "cell_child_b")),
    ("bare_1", "conformance_cell_bare_single", ("cell_only_child",)),
)


def _marker(source_label: str) -> dict:
    return json_marker(source=source_label, generator=GENERATOR_NAME)


def _layout(source_label: str, cell_name: str) -> dict:
    return {
        "_generated": _marker(source_label),
        "type": "View",
        "id": "root",
        "width": "matchParent",
        "height": "matchParent",
        "child": [
            {
                "type": "Collection",
                "id": "target",
                "width": 150,
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
                "defaultValue": [{"title": "Cell 0"}],
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
            "tags": ["conformance", "Collection"],
        },
        "platform": "all",
        "cases": [{"name": name, "description": description, "steps": steps}],
    }


def build_collection_cell_child_fixtures(
    source_label: str,
) -> tuple[list[tuple[str, dict]], list[dict]]:
    """``(files, manifest entries)`` for the id-less cell-root family."""
    files: list[tuple[str, dict]] = []
    entries: list[dict] = []

    for suffix, cell_name, child_ids in _CELLS:
        for kind in ("addr", "tap"):
            if kind == "tap" and suffix != "bare_2":
                continue
            case = f"cellChild{'Tap' if kind == 'tap' else 'Address'}__{suffix}"
            layout_rel = f"fixtures/Collection/{case}.layout.json"
            test_rel = f"fixtures/Collection/{case}.test.json"

            # Both arms in one case: the wrapper still carries the address,
            # AND the children still answer to what they declared. Asserting
            # only the second would also pass if the address were deleted.
            steps: list[dict] = [
                {"action": "waitFor", "id": "root"},
                {"action": "waitFor", "id": "target_item_0"},
            ]
            if kind == "tap":
                steps.append({"action": "tapItem", "id": "target", "index": 0})
            steps += [{"action": "waitFor", "id": cid} for cid in child_ids]

            if kind == "tap":
                description = (
                    "A cell whose root declares no id is still tappable by its item "
                    "address, and the tap does not cost the children their identifiers."
                )
            else:
                description = (
                    f"A cell whose root declares no id keeps its {len(child_ids)} child "
                    f"identifier{'s' if len(child_ids) > 1 else ''}, while the cell is "
                    "addressable as target_item_0."
                )

            files.append((layout_rel, _layout(source_label, cell_name)))
            files.append((test_rel, _test(case, description, layout_rel, steps)))
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
                "companions": list(rules.BASE_COMPANIONS["Collection"]),
            })
    return files, entries
