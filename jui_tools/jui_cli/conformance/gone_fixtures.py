"""A constraint that names a gone element — the fixture the sweep cannot reach.

The sweep's ``visibility__gone`` puts the value on a lone container and asks
only that it is not visible, so what gone does to LAYOUT is invisible to it:
a face that keeps the element's place passes as well as one that collapses
it. The ruling (canonical ``visibility.goneModel``,
``shared/core/attribute_semantics.json``) says gone takes no size and no
position, and a constraint that names a gone element does not apply. That
needs two elements — an anchor that is gone and a sibling constrained to it —
which is outside a one-attribute sweep.

The target draws the two shapes measured when the ruling was made (ticket
kjui-align-to-view-in-visibility-wrapper-and-margin-sign), each in its own
100pt frame: a 20pt anchor centred in the frame with ``visibility: gone``,
and a 10pt child with ``alignTopView`` + ``topMargin 10`` / with
``alignBottomOfView``. The control is the same frames with the same children
and no anchor. A face that collapses draws the target identically to the
control (inert); one that keeps the anchor in place draws the child at the
anchor's edge (active) — ios sjui did, at (0,50) / (0,60).
"""
from __future__ import annotations

from typing import Any

from ..core.generated_marker import json_marker

GENERATOR_NAME = "jui conformance generate"
TEST_GENERATED_BY = "@generated jui conformance generate — DO NOT EDIT"

_PLATFORMS = ["ios", "android", "web"]

_CASE = "gone_anchor"
_SHAPE = "gone-anchor"

#: (frame id, anchor id, child id, the child's constraint and margin)
_SHAPES = (
    ("frame_top", "anchor_top", "child_top", {"alignTopView": "anchor_top", "topMargin": 10}),
    ("frame_below", "anchor_below", "child_below", {"alignBottomOfView": "anchor_below"}),
)


def _marker(source_label: str) -> dict:
    return json_marker(source=source_label, generator=GENERATOR_NAME)


def _frame(frame_id: str, anchor_id: str, child_id: str, constraint: dict, with_anchor: bool) -> dict:
    child: dict[str, Any] = {"type": "View", "id": child_id, "width": 10, "height": 10, "background": "#FF0000"}
    if with_anchor:
        child.update(constraint)
    elif "topMargin" in constraint:
        # Without the anchor the constraint is gone with it; the margin stays.
        child["topMargin"] = constraint["topMargin"]
    children = [child]
    if with_anchor:
        children.insert(0, {"type": "View", "id": anchor_id, "width": 20, "height": 20,
                            "background": "#0000FF", "centerInParent": True, "visibility": "gone"})
    return {"type": "View", "id": frame_id, "width": 100, "height": 100, "background": "#DDDDDD",
            "child": children}


def _layout(source_label: str, with_anchor: bool) -> dict:
    # `target` is the element the fixture and its control are compared on,
    # as in every visual pair; it holds the two frames.
    return {
        "_generated": _marker(source_label),
        "type": "View",
        "id": "root",
        "width": "matchParent",
        "height": "matchParent",
        "child": [{
            "type": "View",
            "id": "target",
            "width": "wrapContent",
            "height": "wrapContent",
            "orientation": "vertical",
            "child": [_frame(*shape, with_anchor) for shape in _SHAPES],
        }],
    }


def _test(name: str, screenshot: str, description: str, layout_rel: str) -> dict:
    return {
        "type": "screen",
        "source": {"layout": layout_rel},
        "metadata": {
            "name": f"conformance {name}",
            "description": description,
            "generatedBy": TEST_GENERATED_BY,
            "tags": ["conformance"],
        },
        "platform": "all",
        "cases": [
            {
                "name": name,
                "description": description,
                "steps": [
                    {"action": "waitFor", "id": "root"},
                    {"action": "screenshot", "name": screenshot},
                ],
            }
        ],
    }


def _entry(**fields: Any) -> dict:
    entry = {
        "class": "visual",
        "host": "View",
        "aliasOf": None,
        "platforms": list(_PLATFORMS),
        "mode": None,
        "deprecated": None,
        "state": None,
        "promotedFrom": None,
    }
    entry.update(fields)
    return entry


def build_gone_fixtures(source_label: str) -> tuple[list[tuple[str, dict]], list[dict]]:
    """Return ``(files, manifest_entries)`` — deterministic."""
    control_stem = f"View__{_SHAPE}"
    control_id = f"__control/{control_stem}"
    control_layout_rel = f"fixtures/__control/{control_stem}.layout.json"
    control_test_rel = f"fixtures/__control/{control_stem}.test.json"

    stem = f"visibility__{_CASE}"
    layout_rel = f"fixtures/common/{stem}.layout.json"
    test_rel = f"fixtures/common/{stem}.test.json"
    description = (
        "A constraint that names a gone element does not apply — canonical "
        "visibility.goneModel. The children aligned to a gone anchor "
        "(alignTopView + topMargin 10, alignBottomOfView) are placed as they "
        "are with no anchor: a face that keeps the anchor in place draws them "
        "at its edge, unlike the control."
    )

    files = [
        (control_layout_rel, _layout(source_label, with_anchor=False)),
        (control_test_rel, _test(
            control_stem, f"control_{control_stem}",
            "Control for the gone-anchor fixture: the same frames and children with no anchor.",
            control_layout_rel)),
        (layout_rel, _layout(source_label, with_anchor=True)),
        (test_rel, _test(stem, f"common_{stem}", description, layout_rel)),
    ]
    entries = [
        _entry(id=control_id, component="__control", attribute=None, case=control_stem, writtenKey=None,
               value=None, layout=control_layout_rel, test=control_test_rel, control=None, isControl=True),
        _entry(id=f"common/{stem}", component="common", attribute="visibility", case=_CASE,
               writtenKey="visibility", value="gone", layout=layout_rel, test=test_rel, control=control_id),
    ]
    return files, entries
