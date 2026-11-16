"""Where a vertical ScrollView puts a child narrower than itself.

common.gravity is the CONTENT gravity of the view that declares it
("Content gravity/alignment"; gravityDefaults: top|start). So a ScrollView's
own gravity places its content, and a child's gravity places the child's
own content, not the child. Neither was drawn: every ScrollView in the sweep
holds content as wide as it, or declares no gravity. Read from the
generators on 2026-10-05, the four faces split three ways — sjui codegen
placed a single child by the CHILD's gravity (centre / right), web placed it
by the ScrollView's own gravity, and SwiftJsonUI Dynamic and KotlinJsonUI
read neither.

Two fixtures and one control, each a 200x200 vertical ScrollView holding one
40x40 box:

* ``gravity__centerHorizontal`` — the ScrollView declares centerHorizontal:
  the box at x 80.
* ``childGravity__right`` — the box declares gravity right (its own content,
  of which it has none): the box stays at x 0. A platform that places the
  child by its gravity draws it at x 160.
* the control — no gravity anywhere: the box at x 0.

A second pair holds the child's own gravity in place: the ScrollView holds
one matchParent-wide View declaring gravity center, which holds the 40x40
box —

* ``childContentGravity__center`` — the box at x 80, centred by its parent's
  content gravity. A platform that overwrote the child's alignment with the
  ScrollView's (start) would draw it at 0.
* its control — the same tree without the gravity: the box at x 0.

The 2026-10-05 sjui change that made the ScrollView's own gravity place its
content left this shape as it was (measured: a 72 box at x 159 of 390 before
and after, in the layout that raised the question); the pair fixes that.

All ``class: visual``; the frame-parity gate reads the box on every
platform.
"""
from __future__ import annotations

from . import rules
from ..core.generated_marker import json_marker

GENERATOR_NAME = "jui conformance generate"
TEST_GENERATED_BY = "@generated jui conformance generate — DO NOT EDIT"

_PLATFORMS = ["ios", "android", "web"]

SCROLL_GRAVITY_CASE = "gravity__centerHorizontal"
CHILD_GRAVITY_CASE = "childGravity__right"
CONTROL_STEM = "ScrollView__narrow-child"
CHILD_CONTENT_CASE = "childContentGravity__center"
CHILD_CONTENT_CONTROL_STEM = "ScrollView__matchparent-child"

_BOX = 200
_CHILD = 40


def _marker(source_label: str) -> dict:
    return json_marker(source=source_label, generator=GENERATOR_NAME)


def _layout(source_label: str, scroll_gravity=None, child_gravity=None) -> dict:
    child = {"type": "View", "id": "box", "width": _CHILD, "height": _CHILD, "background": "#FF0000"}
    if child_gravity:
        child["gravity"] = child_gravity
    scroll = {
        "type": "ScrollView",
        "id": "target",
        "width": _BOX,
        "height": _BOX,
        "background": "#DDDDDD",
        "child": [child],
    }
    if scroll_gravity:
        scroll["gravity"] = scroll_gravity
    return {
        "_generated": _marker(source_label),
        "type": "View",
        "id": "root",
        "width": "matchParent",
        "height": "matchParent",
        "child": [scroll],
    }


def _wrapped_layout(source_label: str, content_gravity=None) -> dict:
    content = {"type": "View", "id": "content", "orientation": "vertical", "width": "matchParent",
               "height": "wrapContent",
               "child": [{"type": "View", "id": "box", "width": _CHILD, "height": _CHILD, "background": "#FF0000"}]}
    if content_gravity:
        content["gravity"] = content_gravity
    return {
        "_generated": _marker(source_label),
        "type": "View",
        "id": "root",
        "width": "matchParent",
        "height": "matchParent",
        "child": [{"type": "ScrollView", "id": "target", "width": _BOX, "height": _BOX,
                   "background": "#DDDDDD", "child": [content]}],
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


def build_scroll_gravity_fixtures(
    source_label: str,
) -> tuple[list[tuple[str, dict]], list[dict]]:
    """``(files, manifest entries)`` for the two narrow-child ScrollViews and their control."""
    files: list[tuple[str, dict]] = []
    entries: list[dict] = []
    companions = list(rules.BASE_COMPANIONS.get("ScrollView", []))

    control_id = f"__control/{CONTROL_STEM}"
    control_layout = f"fixtures/__control/{CONTROL_STEM}.layout.json"
    control_test = f"fixtures/__control/{CONTROL_STEM}.test.json"
    files.append((control_layout, _layout(source_label)))
    files.append((control_test, _test(
        CONTROL_STEM,
        "Control for the narrow-child ScrollViews: a 200x200 vertical ScrollView holding one 40x40 "
        "box and no gravity anywhere — the box at x 0 (gravityDefaults top|start).",
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

    for case, attribute, value, layout, description in (
        (SCROLL_GRAVITY_CASE, "gravity", "centerHorizontal",
         _layout(source_label, scroll_gravity="centerHorizontal"),
         "A 200x200 vertical ScrollView declaring gravity centerHorizontal, holding one 40x40 box: "
         "the ScrollView's content gravity centres it, the box at x 80."),
        (CHILD_GRAVITY_CASE, "child", None,
         _layout(source_label, child_gravity="right"),
         "A 200x200 vertical ScrollView holding one 40x40 box that declares gravity right: the "
         "box's gravity is its own content's, so the box stays at x 0. A platform that places the "
         "child by its gravity draws it at x 160."),
    ):
        layout_rel = f"fixtures/ScrollView/{case}.layout.json"
        test_rel = f"fixtures/ScrollView/{case}.test.json"
        files.append((layout_rel, layout))
        files.append((test_rel, _test(case, description, layout_rel)))
        entries.append({
            "id": f"ScrollView/{case}",
            "component": "ScrollView",
            "attribute": attribute,
            "case": case,
            "class": rules.CLASS_VISUAL,
            "host": "ScrollView",
            "writtenKey": attribute,
            "aliasOf": None,
            "value": value,
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
    # The child's own content gravity, inside the ScrollView.
    cc_control_id = f"__control/{CHILD_CONTENT_CONTROL_STEM}"
    cc_control_layout = f"fixtures/__control/{CHILD_CONTENT_CONTROL_STEM}.layout.json"
    cc_control_test = f"fixtures/__control/{CHILD_CONTENT_CONTROL_STEM}.test.json"
    files.append((cc_control_layout, _wrapped_layout(source_label)))
    files.append((cc_control_test, _test(
        CHILD_CONTENT_CONTROL_STEM,
        "Control for the child-content-gravity ScrollView: a 200x200 vertical ScrollView holding one "
        "matchParent-wide View with no gravity, which holds a 40x40 box — the box at x 0.",
        cc_control_layout)))
    entries.append({**entries[0], "id": cc_control_id, "case": CHILD_CONTENT_CONTROL_STEM,
                    "layout": cc_control_layout, "test": cc_control_test})
    layout_rel = f"fixtures/ScrollView/{CHILD_CONTENT_CASE}.layout.json"
    test_rel = f"fixtures/ScrollView/{CHILD_CONTENT_CASE}.test.json"
    files.append((layout_rel, _wrapped_layout(source_label, content_gravity="center")))
    files.append((test_rel, _test(
        CHILD_CONTENT_CASE,
        "A 200x200 vertical ScrollView holding one matchParent-wide View declaring gravity center, "
        "which holds a 40x40 box: the View's content gravity centres the box at x 80, whatever the "
        "ScrollView's own gravity. A platform that overwrote the child's alignment would draw it at 0.",
        layout_rel)))
    entries.append({**entries[1], "id": f"ScrollView/{CHILD_CONTENT_CASE}", "attribute": "child",
                    "case": CHILD_CONTENT_CASE, "writtenKey": "child", "value": None,
                    "layout": layout_rel, "test": test_rel, "control": cc_control_id})
    return files, entries
