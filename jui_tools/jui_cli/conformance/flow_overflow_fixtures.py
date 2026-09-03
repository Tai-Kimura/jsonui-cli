"""Flow Collection overflow fixtures the generic per-attribute sweep cannot reach.

Ruling (2026-09-03): a flow Collection with ``lazy`` in effect (undeclared,
or any value but ``"none"``) scrolls vertically inside its own bounds;
``lazy: "none"`` only wraps, and the parent must scroll. The rule is only
visible when the cells do not fit — a scrolling container clips them at the
Collection's height, a wrapping one lets them spill past it — and the
sweep's ``layout__flow`` holds three 60×28 cells in a 150×200 box, which
never overflows on any platform. So the platform that ignored the rule
(kjui emitted a bare FlowRow on every ``lazy`` value, jsonui-cli
``21ff76b1``) rendered its ``layout__flow`` identically to the platforms
that honour it, and no picture in the corpus could tell them apart.

One family: the same overflowing flow Collection twice — a 150×100 box
holding twelve cells, two per row, six rows (~168pt) against a 100pt
height — with ``lazy`` undeclared (``scroll``: clipped at the box) and
``lazy: "none"`` (``none``: cells spill below the box). Both ``class:
visual``; each platform's baseline pins its own picture of the rule.

Controls, in the bounds_fixtures shape (every visual fixture names an
``isControl`` entry that differs from it in the attribute under test): the
same box with the OTHER ``lazy`` shape. ``none`` is compared against the
default body — inert when a platform scrolls regardless of ``lazy`` — and
``scroll`` against the ``lazy: "none"`` body — inert when a platform never
scrolls a flow Collection, the defect above. The two comparisons look at
the same pair of pictures from either side; what they buy over one is that
each fixture's inert verdict names the direction its platform is wrong in.
"""
from __future__ import annotations

from . import rules
from ..core.generated_marker import json_marker

GENERATOR_NAME = "jui conformance generate"
TEST_GENERATED_BY = "@generated jui conformance generate — DO NOT EDIT"

_PLATFORMS = ["ios", "android", "web"]

#: The box. Width admits two 60pt cells per row and not three; the height
#: admits three 28pt rows and not four, so both the clip and the spill are
#: whole rows, not hairlines.
_BOX_WIDTH = 150
_BOX_HEIGHT = 100
#: Twelve cells → six rows → ~168pt of content against the 100pt box.
_ITEM_COUNT = 12

#: (case suffix, `lazy` value or None for undeclared).
_SHAPES = (("scroll", None), ("none", "none"))


def _marker(source_label: str) -> dict:
    return json_marker(source=source_label, generator=GENERATOR_NAME)


def _layout(source_label: str, lazy: str | None) -> dict:
    target = {
        "type": "Collection",
        "id": "target",
        "width": _BOX_WIDTH,
        "height": _BOX_HEIGHT,
        # The box is what the cells are clipped to or spill past; without a
        # background the spill reads as a taller Collection.
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
                "defaultValue": [{"title": f"Cell {i}"} for i in range(_ITEM_COUNT)],
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


def build_flow_overflow_fixtures(
    source_label: str,
) -> tuple[list[tuple[str, dict]], list[dict]]:
    """``(files, manifest entries)`` for the flow-overflow family."""
    files: list[tuple[str, dict]] = []
    entries: list[dict] = []
    # One control per shape, holding that shape's body; each fixture names
    # the control of the OTHER shape.
    control_ids: dict[str, str] = {}
    for shape, lazy in _SHAPES:
        control_stem = f"Collection__flow-overflow-{shape}"
        control_id = f"__control/{control_stem}"
        control_ids[shape] = control_id
        control_layout_rel = f"fixtures/__control/{control_stem}.layout.json"
        control_test_rel = f"fixtures/__control/{control_stem}.test.json"
        files.append((control_layout_rel, _layout(source_label, lazy)))
        files.append((
            control_test_rel,
            _test(
                control_stem,
                "Control for the flow-overflow family: the same overflowing flow "
                f"Collection with lazy {'undeclared' if lazy is None else repr(lazy)}.",
                control_layout_rel,
            ),
        ))
        entries.append({
            "id": control_id,
            "component": "__control",
            "attribute": None,
            "case": control_stem,
            "class": rules.CLASS_VISUAL,
            "host": "Collection",
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
            "companions": list(rules.BASE_COMPANIONS["Collection"]),
        })

    for shape, lazy in _SHAPES:
        case = f"flowOverflow__{shape}"
        layout_rel = f"fixtures/Collection/{case}.layout.json"
        test_rel = f"fixtures/Collection/{case}.test.json"
        other = "none" if lazy is None else "scroll"
        if lazy is None:
            description = (
                f"A flow Collection with lazy in effect (undeclared) holding {_ITEM_COUNT} "
                f"cells in a {_BOX_WIDTH}x{_BOX_HEIGHT} box scrolls inside its own bounds: "
                "the cells are clipped at the box."
            )
        else:
            description = (
                f"A flow Collection with lazy \"none\" holding {_ITEM_COUNT} cells in a "
                f"{_BOX_WIDTH}x{_BOX_HEIGHT} box only wraps: the cells spill past the box. "
                "A platform that scrolls regardless of lazy renders this identically to "
                "flowOverflow__scroll."
            )
        files.append((layout_rel, _layout(source_label, lazy)))
        files.append((test_rel, _test(case, description, layout_rel)))
        entries.append({
            "id": f"Collection/{case}",
            "component": "Collection",
            "attribute": "lazy",
            "case": case,
            "class": rules.CLASS_VISUAL,
            "host": "Collection",
            "writtenKey": None if lazy is None else "lazy",
            "aliasOf": None,
            "value": lazy,
            "platforms": list(_PLATFORMS),
            "mode": None,
            "deprecated": None,
            "layout": layout_rel,
            "test": test_rel,
            "state": None,
            "promotedFrom": None,
            "peerGroup": None,
            # The other shape's body — see the module docstring.
            "control": control_ids[other],
            "companions": list(rules.BASE_COMPANIONS["Collection"]),
        })
    return files, entries
