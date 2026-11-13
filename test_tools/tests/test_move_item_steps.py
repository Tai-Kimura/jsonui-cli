"""moveItem: what validate says before a run (ticket jui-collection-drag-to-reorder).

The drivers refuse a move before anything moves when its two rows are the same, or when it is in a section other
than 0 (v1 moves within one section); validate says so without a device, in the drivers' words. The step's floor is
keyed by the step (action:moveItem), the drivers that first know it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.schema import KEY_DRIVER_REQUIREMENTS  # noqa: E402
from jsonui_test_cli.validator import TestValidator as Validator  # noqa: E402


def _validate(tmp_path: Path, steps) -> tuple[list[str], list[str]]:
    path = tmp_path / "a.test.json"
    path.write_text(json.dumps({
        "type": "screen", "source": {"layout": "layouts/a.json"},
        "metadata": {"name": "a"},
        "cases": [{"name": "c", "description": "d", "steps": steps}],
    }), encoding="utf-8")
    result = Validator().validate_file(path)
    return [m.message for m in result.errors], [m.message for m in result.warnings]


def test_a_written_move_is_clean(tmp_path):
    errors, _ = _validate(tmp_path, [
        {"action": "moveItem", "id": "stops", "from": 0, "to": 2},
        {"action": "moveItem", "id": "stops", "from": 3, "to": 0, "section": 0, "timeout": 8000},
        {"action": "moveItem", "id": "stops", "from": 1, "to": 4, "handle": "grip"},
    ])
    assert errors == []


@pytest.mark.parametrize("step, said", [
    ({"from": 1, "to": 1}, "'from' and 'to' are the same row (1)"),
    ({"from": 0, "to": 2, "section": 1}, "moves within section 0"),
    ({"from": -1, "to": 2}, "'from' on moveItem must be a row index"),
    ({"from": 0, "to": "2"}, "'to' on moveItem must be a row index"),
    ({"from": True, "to": 2}, "'from' on moveItem must be a row index"),
])
def test_what_the_drivers_refuse_is_said_up_front(tmp_path, step, said):
    errors, _ = _validate(tmp_path, [{"action": "moveItem", "id": "stops", **step}])
    assert any(said in e for e in errors), errors


def test_from_and_to_are_required(tmp_path):
    errors, _ = _validate(tmp_path, [{"action": "moveItem", "id": "stops", "from": 0}])
    assert any("'to'" in e for e in errors), errors


def test_index_is_not_a_move_items_key(tmp_path):
    errors, _ = _validate(tmp_path, [{"action": "moveItem", "id": "stops", "from": 0, "to": 1, "index": 0}])
    assert errors, "index is tapItem's, selectTab's and selectOption's only"


def test_the_floor_is_keyed_by_the_step():
    assert KEY_DRIVER_REQUIREMENTS["action:moveItem"] == {"android": "1.23.0", "ios": "2.4.0", "web": "1.20.0"}
