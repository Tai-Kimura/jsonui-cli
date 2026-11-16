"""An empty View with nothing to give it a size, and what it does to the next child.

A View with no children whose size is wrapContent (declared, or a declared 0)
has nothing to be the size of: the SSoT makes such a box 0 on that axis, and
SwiftJsonUI Dynamic and KotlinJsonUI draw it at 0. sjui codegen drew it as
`Color.clear` until jsonui-cli 1.9.18 — any width / height KEY was enough —
and Color.clear takes all the space it is offered: measured on iOS 26.5, an
empty wrapContent View with margins drew 370 x 314.3 (ticket sjui-codegen-
an-empty-view-fills-the-offered-space-and-its-id-box-includes-the-margin).

The empty box itself paints nothing either way, so the per-attribute sweep
cannot see it: what changes is where the NEXT child lands. Each fixture here
is a column of [the empty View with a 12pt top margin, a Label `after`]; a
platform that draws the empty View at 0 puts `after` 12pt down, one that
fills pushes it off. The frame-parity gate compares `after` across the
faces, and the visual gate sees the column. The control is the same column
with the empty View sized 8 x 8 — a spacer that does take its size — so
`after` sits 8pt lower there and the fixture is ACTIVE against it on every
face.

Not here: an empty View with a background (Dynamic fills that one the same
way — a separate ruling) and one with a single axis sized (Dynamic makes it
Color.clear too). A fixture of either would only record the shared defect.
"""
from __future__ import annotations

from . import rules
from ..core.generated_marker import json_marker

GENERATOR_NAME = "jui conformance generate"
TEST_GENERATED_BY = "@generated jui conformance generate — DO NOT EDIT"

_PLATFORMS = ["ios", "android", "web"]
_CONTROL_STEM = "View__empty-view-sized-8"
_CONTROL_SIZE = {"width": 8, "height": 8}
_CONTROL_ID = f"__control/{_CONTROL_STEM}"

#: (case, written size of the empty View, its value) — the two spellings that
#: reached Color.clear in codegen and EmptyView in Dynamic.
_CASES = (
    ("emptyView__wrapContent", {"width": "wrapContent", "height": "wrapContent"}, "wrapContent"),
    ("emptyView__zero", {"width": 0, "height": 0}, 0),
)

_AFTER = {"type": "Label", "id": "after", "width": "wrapContent", "height": "wrapContent", "text": "After", "fontColor": "#000000", "background": "#FFDD00"}


def _marker(source_label: str) -> dict:
    return json_marker(source=source_label, generator=GENERATOR_NAME)


def _layout(source_label: str, empty_size: dict) -> dict:
    children = [
        {"type": "View", "id": "target", "orientation": "vertical", "topMargin": 12, **empty_size},
        dict(_AFTER),
    ]
    return {
        "_generated": _marker(source_label),
        "type": "View",
        "id": "root",
        "width": "matchParent",
        "height": "matchParent",
        "orientation": "vertical",
        "child": children,
    }


def _test(name: str, shot: str, description: str, layout_rel: str) -> dict:
    return {
        "type": "screen",
        "source": {"layout": layout_rel},
        "metadata": {
            "name": f"conformance {name}",
            "description": description,
            "generatedBy": TEST_GENERATED_BY,
            "tags": ["conformance", "View"],
        },
        "platform": "all",
        "cases": [{
            "name": name,
            "description": description,
            "steps": [
                {"action": "waitFor", "id": "root"},
                {"action": "screenshot", "name": shot},
            ],
        }],
    }


def _entry(**fields) -> dict:
    base = {
        "class": rules.CLASS_VISUAL,
        "host": "View",
        "aliasOf": None,
        "platforms": list(_PLATFORMS),
        "mode": None,
        "deprecated": None,
        "state": None,
        "promotedFrom": None,
        "companions": list(rules.BASE_COMPANIONS.get("View", [])),
    }
    base.update(fields)
    return base


def build_empty_view_fixtures(source_label: str) -> tuple[list[tuple[str, dict]], list[dict]]:
    """``(files, manifest entries)`` for the empty-View family."""
    files: list[tuple[str, dict]] = []
    entries: list[dict] = []

    control_layout = f"fixtures/__control/{_CONTROL_STEM}.layout.json"
    control_test = f"fixtures/__control/{_CONTROL_STEM}.test.json"
    files.append((control_layout, _layout(source_label, _CONTROL_SIZE)))
    files.append((control_test, _test(
        _CONTROL_STEM, f"control_{_CONTROL_STEM}",
        "Control for the empty-View family: the same column with the empty View sized 8 x 8, "
        "a spacer that takes its size, so `after` sits 8pt lower than in the fixtures.",
        control_layout,
    )))
    entries.append(_entry(
        id=_CONTROL_ID, component="__control", attribute=None, case=_CONTROL_STEM,
        writtenKey=None, value=None, layout=control_layout, test=control_test,
        control=None, isControl=True,
    ))

    for case, size, value in _CASES:
        layout_rel = f"fixtures/View/{case}.layout.json"
        test_rel = f"fixtures/View/{case}.test.json"
        description = (
            f"An empty View sized {value!r} on both axes, with a 12pt top margin, above a Label "
            "`after`. It has nothing to be the size of, so it is 0 and `after` sits 12pt down; "
            "a platform that draws it filling the space pushes `after` off."
        )
        files.append((layout_rel, _layout(source_label, size)))
        files.append((test_rel, _test(case, f"View_{case}", description, layout_rel)))
        entries.append(_entry(
            id=f"View/{case}", component="View", attribute="width", case=case,
            writtenKey="width", value=value, layout=layout_rel, test=test_rel,
            peerGroup=None, control=_CONTROL_ID,
        ))
    return files, entries
