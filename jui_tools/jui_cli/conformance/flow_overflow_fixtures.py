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

Two members share one overflowing flow Collection — a 150×100 box holding
twelve cells, two per row, six rows (~168pt) against a 100pt height — with
``lazy`` undeclared (``scroll``: clipped at the box) and ``lazy: "none"``
(``none``: cells spill below the box). Both ``class: visual``; each
platform's baseline pins its own picture of the rule.

Controls, in the bounds_fixtures shape (every visual fixture names an
``isControl`` entry that differs from it in the attribute under test): the
same box with the OTHER ``lazy`` shape. ``none`` is compared against the
default body — inert when a platform scrolls regardless of ``lazy`` — and
``scroll`` against the ``lazy: "none"`` body — inert when a platform never
scrolls a flow Collection, the defect above. The two comparisons look at
the same pair of pictures from either side; what they buy over one is that
each fixture's inert verdict names the direction its platform is wrong in.

The third member, ``wrap``, is the shape the first two could not see: a
``wrapContent`` flow Collection inside a vertical ScrollView. "Its own
bounds" is literal — a node without bounds of its own has nothing to scroll
inside, the parent scrolls — and on Android it is also the crash: Compose
throws when a vertically scrollable node is measured with an infinite max
height, which is what a scrolling parent hands a wrapping child. A
consumer's tree had it (a flow inside a LazyColumn cell) while the corpus
held only the fixed box. Its control is the same tree with the Collection
self-bounded at 100pt: the control clips at the box, the fixture lays every
row out at content height and the ScrollView scrolls — and a renderer that
scrolls the wrapping node instead of the parent either crashes (Android)
or renders the fixture like its control.
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

_WRAP_CASE = "wrap"


def _marker(source_label: str) -> dict:
    return json_marker(source=source_label, generator=GENERATOR_NAME)


def _collection(lazy: str | None, height) -> dict:
    target = {
        "type": "Collection",
        "id": "target",
        "width": _BOX_WIDTH,
        "height": height,
        # The box is what the cells are clipped to or spill past; without a
        # background the spill reads as a taller Collection.
        "background": "#DDDDDD",
        "sections": [{"cell": "conformance_cell"}],
        "items": "@{items}",
        "layout": "flow",
    }
    if lazy is not None:
        target["lazy"] = lazy
    return target


def _items() -> list[dict]:
    return [
        {
            "name": "items",
            "class": "CollectionDataSource",
            "defaultValue": [{"title": f"Cell {i}"} for i in range(_ITEM_COUNT)],
        }
    ]


def _layout(source_label: str, lazy: str | None) -> dict:
    return {
        "_generated": _marker(source_label),
        "type": "View",
        "id": "root",
        "width": "matchParent",
        "height": "matchParent",
        "child": [_collection(lazy, _BOX_HEIGHT)],
        "data": _items(),
    }


def _scrolling_parent_layout(source_label: str, height) -> dict:
    # The root IS the scrolling parent: what a wrapping child is measured
    # against is the ScrollView's infinite max height.
    return {
        "_generated": _marker(source_label),
        "type": "ScrollView",
        "id": "root",
        "width": "matchParent",
        "height": "matchParent",
        "child": [_collection(None, height)],
        "data": _items(),
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


def _control_entry(control_id: str, stem: str, layout_rel: str, test_rel: str) -> dict:
    return {
        "id": control_id,
        "component": "__control",
        "attribute": None,
        "case": stem,
        "class": rules.CLASS_VISUAL,
        "host": "Collection",
        "writtenKey": None,
        "aliasOf": None,
        "value": None,
        "platforms": list(_PLATFORMS),
        "mode": None,
        "deprecated": None,
        "layout": layout_rel,
        "test": test_rel,
        "state": None,
        "promotedFrom": None,
        "control": None,
        "isControl": True,
        "companions": list(rules.BASE_COMPANIONS["Collection"]),
    }


def _fixture_entry(case: str, attribute: str, written_key, value, layout_rel: str,
                   test_rel: str, control_id: str) -> dict:
    return {
        "id": f"Collection/{case}",
        "component": "Collection",
        "attribute": attribute,
        "case": case,
        "class": rules.CLASS_VISUAL,
        "host": "Collection",
        "writtenKey": written_key,
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
        "companions": list(rules.BASE_COMPANIONS["Collection"]),
    }


def build_flow_overflow_fixtures(
    source_label: str,
) -> tuple[list[tuple[str, dict]], list[dict]]:
    """``(files, manifest entries)`` for the flow-overflow family."""
    files: list[tuple[str, dict]] = []
    entries: list[dict] = []

    # --- the fixed box, twice: one control per shape, each fixture names
    # --- the control of the OTHER shape.
    control_ids: dict[str, str] = {}
    for shape, lazy in _SHAPES:
        stem = f"Collection__flow-overflow-{shape}"
        control_id = f"__control/{stem}"
        control_ids[shape] = control_id
        layout_rel = f"fixtures/__control/{stem}.layout.json"
        test_rel = f"fixtures/__control/{stem}.test.json"
        files.append((layout_rel, _layout(source_label, lazy)))
        files.append((test_rel, _test(
            stem,
            "Control for the flow-overflow family: the same overflowing flow "
            f"Collection with lazy {'undeclared' if lazy is None else repr(lazy)}.",
            layout_rel,
        )))
        entries.append(_control_entry(control_id, stem, layout_rel, test_rel))

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
        entries.append(_fixture_entry(
            case, "lazy", None if lazy is None else "lazy", lazy,
            layout_rel, test_rel, control_ids[other],
        ))

    # --- the wrapping child of a scrolling parent, and its self-bounded twin.
    wrap_stem = "Collection__flow-overflow-wrap"
    wrap_control_id = f"__control/{wrap_stem}"
    wrap_control_layout_rel = f"fixtures/__control/{wrap_stem}.layout.json"
    wrap_control_test_rel = f"fixtures/__control/{wrap_stem}.test.json"
    files.append((wrap_control_layout_rel, _scrolling_parent_layout(source_label, _BOX_HEIGHT)))
    files.append((wrap_control_test_rel, _test(
        wrap_stem,
        "Control for the flow-overflow wrap fixture: the same flow Collection inside "
        f"the same ScrollView, self-bounded at {_BOX_HEIGHT}pt (it clips at the box).",
        wrap_control_layout_rel,
    )))
    entries.append(_control_entry(wrap_control_id, wrap_stem, wrap_control_layout_rel, wrap_control_test_rel))

    wrap_case = f"flowOverflow__{_WRAP_CASE}"
    wrap_layout_rel = f"fixtures/Collection/{wrap_case}.layout.json"
    wrap_test_rel = f"fixtures/Collection/{wrap_case}.test.json"
    wrap_description = (
        f"A wrapContent flow Collection with lazy in effect, holding {_ITEM_COUNT} cells "
        "inside a vertical ScrollView, has no bounds of its own: every row is laid out at "
        "content height and the ScrollView scrolls. A renderer that scrolls the wrapping "
        "node instead of the parent renders this like its 100pt control — or, on Android, "
        "throws (a vertically scrollable node measured with an infinite max height)."
    )
    files.append((wrap_layout_rel, _scrolling_parent_layout(source_label, "wrapContent")))
    files.append((wrap_test_rel, _test(wrap_case, wrap_description, wrap_layout_rel)))
    entries.append(_fixture_entry(
        wrap_case, "height", "height", "wrapContent",
        wrap_layout_rel, wrap_test_rel, wrap_control_id,
    ))
    return files, entries
