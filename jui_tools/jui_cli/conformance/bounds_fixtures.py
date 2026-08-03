"""maxBounds clamp-fill observability fixtures (33 track).

The generic per-attribute sweep probes ``maxWidth`` / ``maxHeight`` on a
FIXED-size target, which can never observe the ruling that matters:
``matchParent`` + a max bound resolves to ``min(parent extent, bound)`` —
the bound clamps the fill (canonical ``size.maxBoundsClampFill``,
``shared/core/attribute_semantics.json``). KJUI dynamic ignored the bound
entirely (fillMaxWidth before widthIn) and no fixture could see it.

This module emits one composite fixture per axis — a filling target WITH
the bound — plus the matching filled controls WITHOUT it. A platform that
clamps renders the target visibly smaller than its control (active); a
platform that ignores the bound renders identically (inert). The contract
asserts uniformly-active, so a regression fails the cross-effect gate.
"""
from __future__ import annotations

from typing import Any

from ..core.generated_marker import json_marker

GENERATOR_NAME = "jui conformance generate"
TEST_GENERATED_BY = "@generated jui conformance generate — DO NOT EDIT"

#: (axis key, fixture attribute, bound value, control shape suffix)
_AXES = (
    ("width", "maxWidth", 120, "fill-w"),
    ("height", "maxHeight", 120, "fill-h"),
)

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

    return files, entries
