"""A flow Collection whose sections declare a header and a footer.

Ruling (4f, 2026-09-26, round 7): a section's declared header and footer are
drawn on a flow too, as full-width rows of their own — the header above the
section's wrap, the footer below it — on every path (sjui / kjui / rjui
codegen, SwiftJsonUI and KotlinJsonUI Dynamic, lazy and ``lazy: "none"``).
Until jsonui-cli 1.9.0 the codegens and the lazy Dynamic flows drew neither
and rjui drew them inside the wrap, as items on the cells' line. The corpus
held no Collection with a section header at all, on any layout, so no
picture could show it.

It could not have: the fixture data channel (INTERACTIVE_HOST_CONTRACT.md
§4) carried each section's cells only. The explicit shape now carries a
section's ``header`` / ``footer`` data too, and the renderers draw a header
only when its section has data — so the fixture's data declares both.

One fixture, one control. The fixture: two sections, the first with a
header, three cells (two lines in the 150-wide box of 60-wide cells) and a
footer, the second with a header and two cells. Header and footer are the
companion cell with titles of their own — 60 wide, so a row drawn full width
shows the view at the row's start, not stretched and not centred. The
control: the same box and the same data with the two sections declaring
cells only — the flow's section blocks without their edges. A platform that
ignores a flow section's header and footer renders the fixture like its
control, and the control-diff verdict names it.
"""
from __future__ import annotations

from . import rules
from ..core.generated_marker import json_marker

GENERATOR_NAME = "jui conformance generate"
TEST_GENERATED_BY = "@generated jui conformance generate — DO NOT EDIT"

_PLATFORMS = ["ios", "android", "web"]

CASE = "flowSections__headerFooter"
CONTROL_STEM = "Collection__flow-sections-cells-only"

_CELL = "conformance_cell"

#: The fixture's sections: section 0 header / cells / footer, section 1
#: header / cells. The control's are the same without the edges.
_SECTIONS = [
    {"cell": _CELL, "header": _CELL, "footer": _CELL},
    {"cell": _CELL, "header": _CELL},
]
_CONTROL_SECTIONS = [{"cell": _CELL}, {"cell": _CELL}]

#: The data, in the explicit shape with each section's header / footer data.
_ITEMS = {
    "sections": [
        {
            "cell": _CELL,
            "header": {"title": "Header 0"},
            "cells": [{"title": "A0"}, {"title": "A1"}, {"title": "A2"}],
            "footer": {"title": "Footer 0"},
        },
        {
            "cell": _CELL,
            "header": {"title": "Header 1"},
            "cells": [{"title": "B0"}, {"title": "B1"}],
        },
    ]
}


def _marker(source_label: str) -> dict:
    return json_marker(source=source_label, generator=GENERATOR_NAME)


def _layout(source_label: str, sections: list[dict]) -> dict:
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
                # Two 60-wide cells to a line; the rows (28 each: header, two
                # lines, footer, header, one line) come to 168 of the 200.
                "width": 150,
                "height": 200,
                "background": "#DDDDDD",
                "sections": [dict(s) for s in sections],
                "items": "@{items}",
                "layout": "flow",
            }
        ],
        "data": [
            {
                "name": "items",
                "class": "CollectionDataSource",
                "defaultValue": _ITEMS,
            }
        ],
    }


def _test(name: str, description: str, layout_rel: str) -> dict:
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
        "cases": [
            {
                "name": name,
                "description": description,
                "steps": [
                    {"action": "waitFor", "id": "root"},
                    {"action": "screenshot", "name": f"Collection_{name}"},
                ],
            }
        ],
    }


def build_flow_section_edge_fixtures(
    source_label: str,
) -> tuple[list[tuple[str, dict]], list[dict]]:
    """``(files, manifest entries)`` for the flow section header / footer pair."""
    files: list[tuple[str, dict]] = []
    entries: list[dict] = []
    companions = list(rules.BASE_COMPANIONS["Collection"])

    control_id = f"__control/{CONTROL_STEM}"
    control_layout = f"fixtures/__control/{CONTROL_STEM}.layout.json"
    control_test = f"fixtures/__control/{CONTROL_STEM}.test.json"
    files.append((control_layout, _layout(source_label, _CONTROL_SECTIONS)))
    files.append((control_test, _test(
        CONTROL_STEM,
        "Control for the flow section header / footer fixture: the same flow Collection "
        "and the same data, its two sections declaring cells only.",
        control_layout,
    )))
    entries.append({
        "id": control_id,
        "component": "__control",
        "attribute": None,
        "case": CONTROL_STEM,
        "class": rules.CLASS_VISUAL,
        "host": "Collection",
        "writtenKey": None,
        "aliasOf": None,
        "value": None,
        "platforms": list(_PLATFORMS),
        "mode": None,
        "deprecated": None,
        "layout": control_layout,
        "test": control_test,
        "state": None,
        "promotedFrom": None,
        "control": None,
        "isControl": True,
        "companions": list(companions),
    })

    layout_rel = f"fixtures/Collection/{CASE}.layout.json"
    test_rel = f"fixtures/Collection/{CASE}.test.json"
    description = (
        "A flow Collection of two sections: the first declares a header, three cells and a "
        "footer, the second a header and two cells. Each header is a full-width row above its "
        "section's wrap and the footer a row below it, the 60-wide view at the row's start — "
        "not an item on the cells' line. A platform that draws no flow section header or "
        "footer renders this like its control."
    )
    files.append((layout_rel, _layout(source_label, _SECTIONS)))
    files.append((test_rel, _test(CASE, description, layout_rel)))
    entries.append({
        "id": f"Collection/{CASE}",
        "component": "Collection",
        "attribute": "sections",
        "case": CASE,
        "class": rules.CLASS_VISUAL,
        "host": "Collection",
        "writtenKey": "sections",
        "aliasOf": None,
        "value": [dict(s) for s in _SECTIONS],
        "platforms": list(_PLATFORMS),
        "mode": None,
        "deprecated": None,
        "layout": layout_rel,
        "test": test_rel,
        "state": None,
        "promotedFrom": None,
        "peerGroup": None,
        "control": control_id,
        "companions": list(companions),
    })
    return files, entries
