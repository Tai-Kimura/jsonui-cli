"""shared/core/reorder_vectors.json against its rule, written once in Python (shared/core/reorder_rule.py).

The vectors are the contract the three runtimes read for a reorderable Collection (ticket
jui-collection-drag-to-reorder, ruling B 2026-11-13): which `to` a drag means, what onReorder's (from, to) does to the
order, iOS onMove's destination as `to`, and the screen reader's move up / move down. They are hand-written; the
reference here is a second statement of the same rule, so a vector that contradicts the rule text is red where it is
written, not first on a device.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jui_cli.core import shared_core

VECTORS = Path(__file__).resolve().parents[2] / "shared" / "core" / "reorder_vectors.json"
DATA = json.loads(VECTORS.read_text(encoding="utf-8"))
RULE = shared_core.load("reorder_rule")


def _named(rows):
    return [pytest.param(v, id=v.get("name") or json.dumps(v)) for v in rows]


def test_the_rule_loads_and_every_section_has_vectors():
    assert RULE is not None, "shared/core/reorder_rule.py did not load"
    for section in ("drop", "drag", "iosOnMove", "a11y", "release", "autoScroll", "itemsChange", "callbacks"):
        assert DATA[section], section
    assert set(DATA["rule"]) == {"to", "drag", "locked", "fixed", "iosOnMove", "a11y", "a11yNames", "release",
                                 "autoScroll", "itemsChange", "callbacks"}


@pytest.mark.parametrize("v", _named(DATA["drop"]))
def test_drop(v):
    got = RULE.drop(v["rows"], v["from"], v["to"], v.get("locked", []), v.get("fixed", []))
    assert got == (v["refused"] if "refused" in v else v["order"])


@pytest.mark.parametrize("v", _named(DATA["drag"]))
def test_drag(v):
    assert RULE.drag_to(v["heights"], v["from"], v["dy"], v.get("locked", []), v.get("fixed", [])) == v["to"]


@pytest.mark.parametrize("v", _named(DATA["iosOnMove"]))
def test_ios_on_move(v):
    assert RULE.ios_on_move(v["from"], v["destination"]) == v["to"]


@pytest.mark.parametrize("v", _named(DATA["a11y"]))
def test_a11y(v):
    assert RULE.a11y(v["rows"], v["from"], v["action"], v.get("locked", []), v.get("fixed", [])) == v["to"]


def test_a_drag_lands_where_its_drop_is_accepted():
    """Every drag that names a `to` other than its start names one the drop accepts: the two halves agree."""
    for v in DATA["drag"]:
        if v["to"] is None or v["to"] == v["from"]:
            continue
        rows = list(range(len(v["heights"])))
        assert isinstance(RULE.drop(rows, v["from"], v["to"], v.get("locked", []), v.get("fixed", [])), list), v["name"]


@pytest.mark.parametrize("v", _named(DATA["release"]))
def test_release(v):
    got = RULE.release(v["heights"], v["from"], v["grabAt"], v["dy"], v.get("locked", []), v["header"], v["footer"],
                       v.get("fixed", []))
    assert got == (None if v.get("cancelled") else v["to"])


@pytest.mark.parametrize("v", _named(DATA["autoScroll"]))
def test_auto_scroll(v):
    assert RULE.auto_scroll(v["viewport"], v["fingerY"]) == pytest.approx(v["speed"])


def test_every_section_with_rows_has_a_fixed_example():
    """fixed (ticket jui-collection-reorder-fixed-row-vs-barrier-row): each face's runtime reads these sections."""
    for section in ("drop", "drag", "a11y", "release"):
        assert any("fixed" in v for v in DATA[section]), section
    passed = [v for v in DATA["drop"] if v.get("fixed") and "order" in v]
    assert passed, "no drop moves a row past a fixed one"


@pytest.mark.parametrize("v", _named(DATA["itemsChange"]))
def test_items_change(v):
    """A drag let go after the rows changed under it (rule.itemsChange): cancelled, or committed as it would."""
    assert RULE.items_changed(v["start"], v["release"]) is v["cancelled"]


def test_items_change_has_both_outcomes():
    outcomes = {v["cancelled"] for v in DATA["itemsChange"]}
    assert outcomes == {True, False}


@pytest.mark.parametrize("v", _named(DATA["callbacks"]))
def test_callbacks(v):
    """rule.callbacks: a drag that began is start .. end with at most one reorder between; one never picked up, none."""
    ev = v["events"]
    if not ev:
        assert v["how"] == "drag" and v["from"] in v.get("locked", []) + v.get("fixed", [])
        return
    assert ev[0] == ["start", 0, v["from"]] and ev[-1] == ["end", 0]
    middle = ev[1:-1]
    assert len(middle) <= 1
    moved = v["how"] == "a11y" or (not v.get("cancelled") and v.get("to") != v["from"])
    assert bool(middle) is moved
    if middle:
        to = v["to"] if v["how"] == "drag" else v["from"] + (-1 if v["action"] == "up" else 1)
        assert middle[0] == ["reorder", 0, v["from"], to]
