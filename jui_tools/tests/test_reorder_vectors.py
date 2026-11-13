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
    for section in ("drop", "drag", "iosOnMove", "a11y", "release", "autoScroll"):
        assert DATA[section], section
    assert set(DATA["rule"]) == {"to", "drag", "locked", "iosOnMove", "a11y", "release", "autoScroll"}


@pytest.mark.parametrize("v", _named(DATA["drop"]))
def test_drop(v):
    got = RULE.drop(v["rows"], v["from"], v["to"], v.get("locked", []))
    assert got == (v["refused"] if "refused" in v else v["order"])


@pytest.mark.parametrize("v", _named(DATA["drag"]))
def test_drag(v):
    assert RULE.drag_to(v["heights"], v["from"], v["dy"], v.get("locked", [])) == v["to"]


@pytest.mark.parametrize("v", _named(DATA["iosOnMove"]))
def test_ios_on_move(v):
    assert RULE.ios_on_move(v["from"], v["destination"]) == v["to"]


@pytest.mark.parametrize("v", _named(DATA["a11y"]))
def test_a11y(v):
    assert RULE.a11y(v["rows"], v["from"], v["action"], v.get("locked", [])) == v["to"]


def test_a_drag_lands_where_its_drop_is_accepted():
    """Every drag that names a `to` other than its start names one the drop accepts: the two halves agree."""
    for v in DATA["drag"]:
        if v["to"] is None or v["to"] == v["from"]:
            continue
        rows = list(range(len(v["heights"])))
        assert isinstance(RULE.drop(rows, v["from"], v["to"], v.get("locked", [])), list), v["name"]


@pytest.mark.parametrize("v", _named(DATA["release"]))
def test_release(v):
    got = RULE.release(v["heights"], v["from"], v["grabAt"], v["dy"], v.get("locked", []), v["header"], v["footer"])
    assert got == (None if v.get("cancelled") else v["to"])


@pytest.mark.parametrize("v", _named(DATA["autoScroll"]))
def test_auto_scroll(v):
    assert RULE.auto_scroll(v["viewport"], v["fingerY"]) == pytest.approx(v["speed"])
