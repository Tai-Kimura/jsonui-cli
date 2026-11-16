"""Composite max-bound fixtures the generic per-attribute sweep cannot reach.

The sweep probes ``maxWidth`` / ``maxHeight`` on a target of FIXED size, so
every ruling about how a bound interacts with a SIZING MODE is invisible to
it. Two such rulings have now cost a released defect each, and this module
holds one fixture family per ruling.

**clamp-fill** (33 track). ``matchParent`` + a max bound resolves to
``min(parent extent, bound)`` — the bound clamps the fill (canonical
``size.maxBoundsClampFill``, ``shared/core/attribute_semantics.json``). KJUI
dynamic ignored the bound entirely (fillMaxWidth before widthIn) and no
fixture could see it. One composite fixture per axis — a filling target WITH
the bound — plus the matching filled controls WITHOUT it. A platform that
clamps renders the target visibly smaller than its control (active); a
platform that ignores the bound renders identically (inert).

**wrap-bound** (51 track). ``wrapContent`` + a max bound means the CONTENT
reflows inside the bound; the bound does not become an ideal size. SwiftUI
expresses that as ``.frame(maxWidth: N)`` with ``.fixedSize(horizontal:
false, vertical: true)`` — horizontal fixing is applied when the axis wraps
and has NO max (sjui ``frame_helper.rb`` 104-117). SwiftJsonUI's dynamic
path had the condition inverted (it fixed the axis *because* a max was
present, ``f8fc559``), so a wrapping bubble laid its text out at single-line
ideal width and the text escaped the bubble on device.

The sweep's own ``maxWidth`` fixtures are a 200pt box of 40pt children:
fixing that axis changes nothing anyone can see, which is why the whole
10.14.2 batch left the iOS visual baseline at 720/720. The defect is only
observable on REFLOWING CONTENT, so this family's target is a Label of text
long enough to wrap, and the control is the same Label without the bound.
"""
from __future__ import annotations

from typing import Any

from . import rules
from ..core.generated_marker import json_marker

GENERATOR_NAME = "jui conformance generate"
TEST_GENERATED_BY = "@generated jui conformance generate — DO NOT EDIT"

#: (axis key, fixture attribute, bound value, control shape suffix)
_AXES = (
    ("width", "maxWidth", 120, "fill-w"),
    ("height", "maxHeight", 120, "fill-h"),
)

#: Case name of the wrap-bound family, and the bound it declares. 150pt is
#: narrower than the text's single-line width by a wide margin, so a platform
#: that lays the text out at its ideal width overflows the box visibly rather
#: than by a hairline.
_WRAP_CASE = "wrap"
_WRAP_BOUND = 150
_WRAP_SHAPE = "wrap-max"

_PLATFORMS = ["ios", "android", "web"]


def _marker(source_label: str) -> dict:
    return json_marker(source=source_label, generator=GENERATOR_NAME)


def _target(axis: str, bound_attr: str | None, bound: int | None) -> dict:
    # The filling axis is the one under test; the cross axis stays small so
    # the clamp difference is a fat visible bar, not a subtle edge.
    target: dict[str, Any] = {
        "type": "View",
        "id": "target",
        "width": "matchParent" if axis == "width" else 60,
        "height": "matchParent" if axis == "height" else 60,
        "background": "#FF0000",
    }
    if bound_attr:
        target[bound_attr] = bound
    return target


def _layout(source_label: str, axis: str, bound_attr: str | None, bound: int | None) -> dict:
    return {
        "_generated": _marker(source_label),
        "type": "View",
        "id": "root",
        "width": "matchParent",
        "height": "matchParent",
        "child": [_target(axis, bound_attr, bound)],
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


def _wrap_target(bound: int | None) -> dict:
    # The background is what makes the defect visible: the box is drawn at the
    # bound, the text is drawn by the layout pass, and the failing mode puts
    # the second outside the first. Without a background both renders are
    # black text on white and the overflow reads as a line break moving.
    target: dict[str, Any] = {
        "type": "Label",
        "id": "target",
        "width": "wrapContent",
        "height": "wrapContent",
        "text": rules.LONG_TEXT,
        "background": "#DDDDDD",
        "fontColor": "#000000",
    }
    if bound is not None:
        target["maxWidth"] = bound
    return target


def _wrap_layout(source_label: str, bound: int | None) -> dict:
    return {
        "_generated": _marker(source_label),
        "type": "View",
        "id": "root",
        "width": "matchParent",
        "height": "matchParent",
        "child": [_wrap_target(bound)],
    }


def build_bounds_fixtures(source_label: str) -> tuple[list[tuple[str, dict]], list[dict]]:
    """Return ``(files, manifest_entries)`` — deterministic."""
    files: list[tuple[str, dict]] = []
    entries: list[dict] = []

    for axis, bound_attr, bound, shape in _AXES:
        control_id = f"__control/View__{shape}"
        control_stem = f"View__{shape}"
        control_layout_rel = f"fixtures/__control/{control_stem}.layout.json"
        control_test_rel = f"fixtures/__control/{control_stem}.test.json"
        files.append((control_layout_rel, _layout(source_label, axis, None, None)))
        files.append((
            control_test_rel,
            _test(
                control_stem,
                f"control_{control_stem}",
                f"Control for the {bound_attr} clamp-fill fixture: the same "
                f"filling target WITHOUT the bound.",
                control_layout_rel,
            ),
        ))
        entries.append({
            "id": control_id,
            "component": "__control",
            "attribute": None,
            "case": f"View__{shape}",
            "class": "visual",
            "host": "View",
            "writtenKey": None,
            "aliasOf": None,
            "value": None,
            "platforms": list(_PLATFORMS),
            "mode": None,
            "deprecated": None,
            "layout": control_layout_rel,
            "test": control_test_rel,
            "state": None,
            "promotedFrom": None,
            "control": None,
            "isControl": True,
        })

        fixture_case = "fill_clamp"
        fixture_stem = f"{bound_attr}__{fixture_case}"
        layout_rel = f"fixtures/common/{fixture_stem}.layout.json"
        test_rel = f"fixtures/common/{fixture_stem}.test.json"
        description = (
            f"matchParent {axis} + {bound_attr} {bound}: the bound clamps the "
            f"fill to min(parent, {bound}) — canonical size.maxBoundsClampFill. "
            "A platform that ignores the bound renders identically to the "
            "filled control."
        )
        files.append((layout_rel, _layout(source_label, axis, bound_attr, bound)))
        files.append((
            test_rel,
            _test(fixture_stem, f"common_{fixture_stem}", description, layout_rel),
        ))
        entries.append({
            "id": f"common/{fixture_stem}",
            "component": "common",
            "attribute": bound_attr,
            "case": fixture_case,
            "class": "visual",
            "host": "View",
            "writtenKey": bound_attr,
            "aliasOf": None,
            "value": bound,
            "platforms": list(_PLATFORMS),
            "mode": None,
            "deprecated": None,
            "layout": layout_rel,
            "test": test_rel,
            "state": None,
            "promotedFrom": None,
            "control": control_id,
        })

    # --- wrap-bound (51 track) -------------------------------------------- #
    wrap_control_id = f"__control/Label__{_WRAP_SHAPE}"
    wrap_control_stem = f"Label__{_WRAP_SHAPE}"
    wrap_control_layout_rel = f"fixtures/__control/{wrap_control_stem}.layout.json"
    wrap_control_test_rel = f"fixtures/__control/{wrap_control_stem}.test.json"
    files.append((wrap_control_layout_rel, _wrap_layout(source_label, None)))
    files.append((
        wrap_control_test_rel,
        _test(
            wrap_control_stem,
            f"control_{wrap_control_stem}",
            "Control for the maxWidth wrap-bound fixture: the same wrapping "
            "Label WITHOUT the bound.",
            wrap_control_layout_rel,
        ),
    ))
    entries.append({
        "id": wrap_control_id,
        "component": "__control",
        "attribute": None,
        "case": wrap_control_stem,
        "class": "visual",
        "host": "Label",
        "writtenKey": None,
        "aliasOf": None,
        "value": None,
        "platforms": list(_PLATFORMS),
        "mode": None,
        "deprecated": None,
        "layout": wrap_control_layout_rel,
        "test": wrap_control_test_rel,
        "state": None,
        "promotedFrom": None,
        "control": None,
        "isControl": True,
    })

    wrap_stem = f"maxWidth__{_WRAP_CASE}"
    wrap_layout_rel = f"fixtures/common/{wrap_stem}.layout.json"
    wrap_test_rel = f"fixtures/common/{wrap_stem}.test.json"
    wrap_description = (
        f"wrapContent width + maxWidth {_WRAP_BOUND} on reflowing text: the "
        "bound reflows the CONTENT, it does not become an ideal size. A "
        "platform that fixes the axis because the bound is present lays the "
        "text out at single-line width and it escapes the box."
    )
    files.append((wrap_layout_rel, _wrap_layout(source_label, _WRAP_BOUND)))
    files.append((
        wrap_test_rel,
        _test(wrap_stem, f"common_{wrap_stem}", wrap_description, wrap_layout_rel),
    ))
    entries.append({
        "id": f"common/{wrap_stem}",
        "component": "common",
        "attribute": "maxWidth",
        "case": _WRAP_CASE,
        "class": "visual",
        "host": "Label",
        "writtenKey": "maxWidth",
        "aliasOf": None,
        "value": _WRAP_BOUND,
        "platforms": list(_PLATFORMS),
        "mode": None,
        "deprecated": None,
        "layout": wrap_layout_rel,
        "test": wrap_test_rel,
        "state": None,
        "promotedFrom": None,
        "control": wrap_control_id,
    })

    return files, entries
