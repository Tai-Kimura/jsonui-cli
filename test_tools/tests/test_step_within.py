"""`within`: a step's (and a condition's) id looked up among one element's
descendants — the n-th cell's child is `"within": "<collectionId>_item_<n>"`.

What validate says about it, what `index` means where it is not tapItem's,
selectTab's or selectOption's, and where the driver floor reads it from.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.schema import KEY_DRIVER_REQUIREMENTS  # noqa: E402
from jsonui_test_cli.validation import element_ids  # noqa: E402
from jsonui_test_cli.validation.runtime_support import collect_declared_keys  # noqa: E402
from jsonui_test_cli.validator import TestValidator as Validator  # noqa: E402

CELL = "list_item_1"


def _validate(tmp_path: Path, steps, **case) -> tuple[list[str], list[str]]:
    path = tmp_path / "a.test.json"
    path.write_text(json.dumps({
        "type": "screen", "source": {"layout": "layouts/a.json"},
        "metadata": {"name": "a"},
        "cases": [{"name": "c", "description": "d", "steps": steps, **case}],
    }), encoding="utf-8")
    result = Validator().validate_file(path)
    return ([m.message for m in result.errors],
            [m.message for m in result.warnings])


def _about(messages, word):
    return [m for m in messages if word in m]


# ------------------------------------------------------- where it is taken

ID_STEPS = [
    {"action": "tap", "id": "title"},
    {"action": "doubleTap", "id": "title"},
    {"action": "longPress", "id": "title"},
    {"action": "input", "id": "field", "value": "x"},
    {"action": "clear", "id": "field"},
    {"action": "scroll", "id": "title", "direction": "down"},
    {"action": "scrollUntilVisible", "id": "title"},
    {"action": "swipe", "id": "title", "direction": "left"},
    {"action": "waitFor", "id": "title"},
    {"action": "waitForAny", "ids": ["title", "badge"]},
    {"action": "selectOption", "id": "picker", "value": "a"},
    {"action": "tapItem", "id": "inner", "index": 0},
    {"action": "selectTab", "id": "tabs", "index": 0},
    {"action": "readText", "id": "title", "variable": "v"},
    {"assert": "visible", "id": "title"},
    {"assert": "notVisible", "id": "title"},
    {"assert": "hidden", "id": "badge"},
    {"assert": "enabled", "id": "title"},
    {"assert": "disabled", "id": "title"},
    {"assert": "text", "id": "title", "equals": "B"},
    {"assert": "count", "id": "badge", "equals": 0},
    {"assert": "screenshot", "name": "cell", "cropId": "title"},
]


@pytest.mark.parametrize("step", ID_STEPS, ids=lambda s: s.get("action") or s.get("assert"))
def test_every_step_that_targets_an_id_takes_within(tmp_path, step):
    errors, warnings = _validate(tmp_path, [{**step, "within": CELL}])
    assert _about(errors + warnings, "within") == []


@pytest.mark.parametrize("step", [
    {"action": "wait", "ms": 10},
    {"action": "back"},
    {"assert": "state", "path": "a", "equals": 1},
], ids=lambda s: s.get("action") or s.get("assert"))
def test_within_on_a_step_that_targets_no_id_is_an_error(tmp_path, step):
    errors, _ = _validate(tmp_path, [{**step, "within": CELL}])
    assert any("'within' does nothing on" in m for m in errors), errors


@pytest.mark.parametrize("value", ["", "  ", 1, None, ["a"]])
def test_within_is_a_non_empty_id(tmp_path, value):
    errors, _ = _validate(tmp_path, [{"assert": "text", "id": "title", "equals": "B",
                                      "within": value}])
    assert any("'within' must be a non-empty element id string" in m for m in errors), errors


# ----------------------------------------------------------------- index

@pytest.mark.parametrize("step", [
    {"assert": "text", "id": "title", "equals": "B", "index": 1},
    {"action": "tap", "id": "title", "index": 2},
    {"assert": "visible", "id": "title", "index": 0},
], ids=lambda s: s.get("action") or s.get("assert"))
def test_index_where_it_is_not_tapItem_selectTab_or_selectOption_is_an_error(tmp_path, step):
    # The drivers read the first element with the id; the n-th one a writer
    # meant is compared against the first, so it is named, with the key that
    # does it.
    errors, _ = _validate(tmp_path, [step])
    named = _about(errors, "'index' does nothing on")
    assert len(named) == 1, errors
    assert '"within": "<collectionId>_item_<n>"' in named[0]


@pytest.mark.parametrize("step", [
    {"action": "tapItem", "id": "list", "index": 1},
    {"action": "selectTab", "id": "tabs", "index": 1},
    {"action": "selectOption", "id": "picker", "index": 1},
], ids=lambda s: s["action"])
def test_index_where_it_means_something_is_not_named(tmp_path, step):
    errors, warnings = _validate(tmp_path, [step])
    assert _about(errors + warnings, "'index'") == []


def test_another_key_the_kind_does_not_take_is_a_warning(tmp_path):
    # Read by no driver, but not the opposite of what was written: a warning.
    errors, warnings = _validate(tmp_path, [
        {"action": "input", "id": "field", "value": "x", "text": "x"},
        {"assert": "screenshot", "name": "s", "path": "a.png"}])
    assert _about(errors, "is not a key of") == []
    assert len(_about(warnings, "is not a key of")) == 2, warnings


# ------------------------------------------------------------- conditions

def test_a_condition_takes_within_beside_visible_notVisible_or_hidden(tmp_path):
    errors, warnings = _validate(tmp_path, [
        {"assert": "visible", "id": "title", "when": {"visible": "badge", "within": CELL}},
        {"action": "repeat", "times": 2, "while": {"hidden": "badge", "within": CELL},
         "steps": [{"action": "tap", "id": "more"}]}])
    assert _about(errors + warnings, "within") == []


def test_a_condition_with_only_within_is_an_error(tmp_path):
    errors, _ = _validate(tmp_path, [
        {"assert": "visible", "id": "title", "when": {"within": CELL}},
        {"assert": "visible", "id": "title", "when": {"platform": "ios", "within": CELL}}])
    assert len(_about(errors, "the condition has none of them")) == 2, errors


def test_a_conditions_within_is_a_non_empty_id(tmp_path):
    errors, _ = _validate(tmp_path, [
        {"assert": "visible", "id": "title", "when": {"visible": "badge", "within": ""}}])
    assert any("Condition 'within' must be a non-empty" in m for m in errors), errors


# ------------------------------------------------------------ element ids

def test_within_is_one_of_the_ids_a_step_names():
    refs = element_ids.test_element_ids({"type": "screen", "cases": [{"name": "c", "steps": [
        {"assert": "text", "id": "title", "equals": "B", "within": CELL},
        {"assert": "visible", "id": "title", "when": {"visible": "badge", "within": "list_item_2"}},
    ]}]}, "t")
    assert ("t.cases[0].steps[0].within", CELL) in refs, refs
    assert ("t.cases[0].steps[1].when.within", "list_item_2") in refs, refs


# ---------------------------------------------------------------- floors

def _file(tmp_path: Path, name: str, data) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_the_driver_floor_reads_within_on_a_step_however_nested(tmp_path):
    keys = set(KEY_DRIVER_REQUIREMENTS)
    files = [
        _file(tmp_path, "case.test.json", {"type": "screen", "cases": [{"name": "c", "steps": [
            {"assert": "text", "id": "t", "equals": "B", "within": CELL}]}]}),
        _file(tmp_path, "setup.test.json", {"type": "screen", "setup": [
            {"action": "tap", "id": "t", "within": CELL}], "cases": []}),
        _file(tmp_path, "nested.test.json", {"type": "screen", "cases": [{"name": "c", "steps": [
            {"action": "repeat", "times": 1, "steps": [
                {"action": "retry", "steps": [{"assert": "visible", "id": "t", "within": CELL}]}]}]}]}),
        _file(tmp_path, "cond.test.json", {"type": "screen", "cases": [{"name": "c", "steps": [
            {"assert": "visible", "id": "t", "when": {"visible": "b", "within": CELL}}]}]}),
        _file(tmp_path, "flow.test.json", {"type": "flow", "steps": [
            {"screen": "a", "assert": "visible", "id": "t", "within": CELL}]}),
        _file(tmp_path, "none.test.json", {"type": "screen", "cases": [{"name": "c", "steps": [
            {"assert": "text", "id": "t", "equals": "B"}]}]}),
    ]
    found = collect_declared_keys(files, keys)
    assert sorted(p.name for p in found.get("within", [])) == [
        "case.test.json", "cond.test.json", "flow.test.json", "nested.test.json", "setup.test.json"]


def test_a_step_key_is_not_read_as_a_file_or_case_key(tmp_path):
    # `within` at the top of a file or on a case is not a declaration a
    # driver reads; only a step's (or a condition's) is.
    files = [_file(tmp_path, "top.test.json", {"type": "screen", "within": CELL,
                                               "cases": [{"name": "c", "within": CELL, "steps": []}]})]
    assert "within" not in collect_declared_keys(files, set(KEY_DRIVER_REQUIREMENTS))


def test_the_floor_is_the_release_each_driver_first_reads_it():
    assert KEY_DRIVER_REQUIREMENTS["within"] == {"web": "1.18.0", "ios": "2.2.0", "android": "1.20.0"}
