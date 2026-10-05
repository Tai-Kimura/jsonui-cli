"""A vertical ScrollView whose content is shorter than the ScrollView.

attribute_semantics gravityDefaults: the default content gravity is
top|start on every container, a ScrollView's content included. Every
vertical ScrollView in the sweep holds a 600-high content in a 200-high
box, so the content always overflows and where a SHORT content starts was
never drawn: SwiftJsonUI laid the content in a frame of at least the
viewport's height with the default (centre) alignment and drew a short one
in the vertical middle, where Android and web draw it at the top. A
consumer found it on a device (2026-10-05; ticket
sjui-vertical-scrollview-centres-a-short-content).

One fixture, one control. The fixture: a 200x200 vertical ScrollView whose
content (a vertical View, matchParent x wrapContent) holds one 150x80 box —
80 of the 200, so a centring platform draws it at 60 and the frames say so.
The control: the same tree with the box 200 high, filling the ScrollView,
where a centring and a top-aligned platform draw the same picture. Both
``class: visual``; the frame-parity gate reads the box's frame on every
platform.
"""
from __future__ import annotations

from . import rules
from ..core.generated_marker import json_marker

GENERATOR_NAME = "jui conformance generate"
TEST_GENERATED_BY = "@generated jui conformance generate — DO NOT EDIT"

_PLATFORMS = ["ios", "android", "web"]

CASE = "content__short"
CONTROL_STEM = "ScrollView__content-fills"

_BOX = 200
_SHORT = 80


def _marker(source_label: str) -> dict:
    return json_marker(source=source_label, generator=GENERATOR_NAME)


def _layout(source_label: str, box_height: int) -> dict:
    return {
        "_generated": _marker(source_label),
        "type": "View",
        "id": "root",
        "width": "matchParent",
        "height": "matchParent",
        "child": [
            {
                "type": "ScrollView",
                "id": "target",
                "width": _BOX,
                "height": _BOX,
                "background": "#DDDDDD",
                "child": [
                    {
                        "type": "View",
                        "id": "content",
                        "orientation": "vertical",
                        "width": "matchParent",
                        "height": "wrapContent",
                        "child": [
                            {"type": "View", "id": "box", "width": 150, "height": box_height,
                             "background": "#FF0000"}
                        ],
                    }
                ],
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
            "tags": ["conformance", "ScrollView"],
        },
        "platform": "all",
        "cases": [
            {
                "name": name,
                "description": description,
                "steps": [
                    {"action": "waitFor", "id": "root"},
                    {"action": "screenshot", "name": f"ScrollView_{name}"},
                ],
            }
        ],
    }


def build_scroll_content_fixtures(
    source_label: str,
) -> tuple[list[tuple[str, dict]], list[dict]]:
    """``(files, manifest entries)`` for the short-content ScrollView and its control."""
    files: list[tuple[str, dict]] = []
    entries: list[dict] = []
    companions = list(rules.BASE_COMPANIONS.get("ScrollView", []))

    control_id = f"__control/{CONTROL_STEM}"
    control_layout = f"fixtures/__control/{CONTROL_STEM}.layout.json"
    control_test = f"fixtures/__control/{CONTROL_STEM}.test.json"
    files.append((control_layout, _layout(source_label, _BOX)))
    files.append((control_test, _test(
        CONTROL_STEM,
        "Control for the short-content ScrollView: the same 200x200 vertical ScrollView with its "
        "box 200 high, filling it — a centring and a top-aligned platform draw the same picture.",
        control_layout)))
    entries.append({
        "id": control_id,
        "component": "__control",
        "attribute": None,
        "case": CONTROL_STEM,
        "class": rules.CLASS_VISUAL,
        "host": "ScrollView",
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

    layout_rel = f"fixtures/ScrollView/{CASE}.layout.json"
    test_rel = f"fixtures/ScrollView/{CASE}.test.json"
    files.append((layout_rel, _layout(source_label, _SHORT)))
    files.append((test_rel, _test(
        CASE,
        "A 200x200 vertical ScrollView whose content holds one 150x80 box: the content starts at "
        "the ScrollView's top (gravityDefaults top|start), the box at y 0. A platform that centres "
        "a short content draws the box at y 60.",
        layout_rel)))
    entries.append({
        "id": f"ScrollView/{CASE}",
        "component": "ScrollView",
        "attribute": "child",
        "case": CASE,
        "class": rules.CLASS_VISUAL,
        "host": "ScrollView",
        "writtenKey": "child",
        "aliasOf": None,
        "value": None,
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
