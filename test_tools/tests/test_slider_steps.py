"""setSliderValue and the `value` assertion: what validate says before a run.

The drivers refuse a value outside the slider's bounds or off its step grid
before they move anything (Android would clamp or snap it in silence, the
browser would sanitise the DOM and leave the app's state behind, iOS has no
exact placement at all). When the test writes `range` / `step`, validate says
the same thing — in the drivers' sentences — without a device. iOS reads no
bounds from a slider, so a step without `range` is warned about there; and
the two steps carry driver floors keyed by the step, not by a key.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.schema import KEY_DRIVER_REQUIREMENTS  # noqa: E402
from jsonui_test_cli.validation.runtime_support import (  # noqa: E402
    check_declarations, collect_declared_keys)
from jsonui_test_cli.validator import TestValidator as Validator  # noqa: E402

FLOOR = {"android": "1.22.0", "ios": "2.3.0", "web": "1.19.0"}


def _validate(tmp_path: Path, steps, **case) -> tuple[list[str], list[str]]:
    path = tmp_path / "a.test.json"
    path.write_text(json.dumps({
        "type": "screen", "source": {"layout": "layouts/a.json"},
        "metadata": {"name": "a"},
        "cases": [{"name": "c", "description": "d", "steps": steps, **case}],
    }), encoding="utf-8")
    result = Validator().validate_file(path)
    return [m.message for m in result.errors], [m.message for m in result.warnings]


def test_a_written_slider_step_is_clean(tmp_path):
    errors, warnings = _validate(tmp_path, [
        {"action": "setSliderValue", "id": "rating", "value": 9, "range": [1, 10], "step": 1},
        {"action": "setSliderValue", "id": "rating", "value": 9.5, "range": [1, 10]},
        {"action": "setSliderValue", "id": "rating", "value": "@{v}", "range": [1, 10]},
        {"assert": "value", "id": "rating", "equals": 9, "range": [1, 10], "step": 1},
        {"assert": "value", "id": "rating", "equals": 9, "tolerance": 0.25},
    ], args={"v": 9})
    assert errors == [], errors
    assert [w for w in warnings if "slider" in w or "value" in w] == [], warnings


@pytest.mark.parametrize("step, sentence", [
    ({"value": 0, "range": [1, 10]},
     "0 is below the slider's range [1, 10]; the nearest value it can take is 1"),
    ({"value": 11, "range": [1, 10]},
     "11 is above the slider's range [1, 10]; the nearest value it can take is 10"),
    ({"value": 9.4, "range": [1, 10], "step": 1},
     "9.4 is not on the slider's steps (1 + k * 1); the nearest values are 9 and 10"),
    ({"value": 0.25, "range": [0, 1], "step": 0.1},
     "0.25 is not on the slider's steps (0 + k * 0.1); the nearest values are 0.2 and 0.3"),
    ({"value": 9.5, "range": [1, 10], "step": 2},
     "9.5 is not on the slider's steps (1 + k * 2); the nearest values are 9 and 10"),
])
def test_what_the_drivers_refuse_is_an_error_in_their_sentence(tmp_path, step, sentence):
    errors, _ = _validate(tmp_path, [{"action": "setSliderValue", "id": "rating", **step}])
    assert sentence in errors, errors


@pytest.mark.parametrize("step, word", [
    ({"action": "setSliderValue", "id": "r", "value": "nine", "range": [1, 10]}, "'value' on setSliderValue must be a number"),
    ({"action": "setSliderValue", "id": "r", "value": 5, "range": [10, 1]}, "minimum < maximum"),
    ({"action": "setSliderValue", "id": "r", "value": 5, "range": [1]}, "'range' must be [minimum, maximum]"),
    ({"action": "setSliderValue", "id": "r", "value": 5, "range": [1, 10], "step": 0}, "'step' must be a number greater than 0"),
    ({"assert": "value", "id": "r", "equals": "9", "range": [1, 10]}, "'equals' on value must be a number"),
    ({"assert": "value", "id": "r", "equals": 9, "tolerance": -1}, "'tolerance' must be a number of 0 or more"),
])
def test_the_numbers_are_checked(tmp_path, step, word):
    errors, _ = _validate(tmp_path, [step])
    assert any(word in e for e in errors), errors


def test_missing_value_and_equals_are_missing(tmp_path):
    errors, _ = _validate(tmp_path, [{"action": "setSliderValue", "id": "r"}, {"assert": "value", "id": "r"}])
    assert "Missing required parameter 'value' for action 'setSliderValue'" in errors
    assert any("'equals'" in e for e in errors), errors


def test_ios_without_range_is_warned_and_a_gate_off_ios_is_not(tmp_path):
    _, warnings = _validate(tmp_path, [
        {"action": "setSliderValue", "id": "r", "value": 5},
        {"assert": "value", "id": "r", "equals": 5},
    ])
    assert any(w.startswith("setSliderValue without 'range'") for w in warnings), warnings
    assert any(w.startswith("value without 'range', 'step' or 'tolerance' fails on iOS") for w in warnings), warnings
    _, gated = _validate(tmp_path, [
        {"action": "setSliderValue", "id": "r", "value": 5, "when": {"platform": "android"}},
        {"assert": "value", "id": "r", "equals": 5, "when": {"platform": ["android", "web"]}},
    ])
    assert not [w for w in gated if "iOS" in w], gated


def test_tolerance_does_nothing_on_set_slider_value(tmp_path):
    _, warnings = _validate(tmp_path, [{"action": "setSliderValue", "id": "r", "value": 5, "range": [1, 10], "tolerance": 1}])
    assert any("tolerance" in w for w in warnings), warnings


def test_the_floors_are_keyed_by_the_step():
    assert KEY_DRIVER_REQUIREMENTS["action:setSliderValue"] == FLOOR
    assert KEY_DRIVER_REQUIREMENTS["assert:value"] == FLOOR
    # `value` the key (input's text) carries no floor.
    assert "value" not in KEY_DRIVER_REQUIREMENTS
    from jsonui_test_cli.validation.runtime_support import describe_requirement_key, step_kind_key
    assert step_kind_key({"action": "setSliderValue"}) == "action:setSliderValue"
    assert step_kind_key({"assert": "value"}) == "assert:value"
    assert describe_requirement_key("action:setSliderValue") == "the action 'setSliderValue'"
    assert describe_requirement_key("within") == "'within'"


def test_a_file_with_the_step_is_collected_however_nested(tmp_path):
    nested = tmp_path / "nested.test.json"
    nested.write_text(json.dumps({"type": "screen", "cases": [{"name": "c", "steps": [
        {"action": "retry", "steps": [{"action": "setSliderValue", "id": "r", "value": 3}]}]}]}), encoding="utf-8")
    other = tmp_path / "other.test.json"
    other.write_text(json.dumps({"type": "screen", "cases": [{"name": "c", "steps": [
        {"action": "input", "id": "f", "value": "3"}, {"assert": "text", "id": "f", "equals": "3"}]}]}), encoding="utf-8")
    found = collect_declared_keys([nested, other], set(KEY_DRIVER_REQUIREMENTS))
    assert found.get("action:setSliderValue") == [nested]
    assert "assert:value" not in found and "value" not in found


def test_an_older_driver_is_an_error_naming_the_step(tmp_path, monkeypatch):
    project = tmp_path / "p"
    (project / "node_modules" / "jsonui-test-runner-web").mkdir(parents=True)
    (project / "node_modules" / "jsonui-test-runner-web" / "package.json").write_text('{"version": "1.18.1"}')
    test = project / "a.test.json"
    test.write_text(json.dumps({"type": "screen", "platform": "web", "cases": [{"name": "c", "steps": [
        {"action": "setSliderValue", "id": "r", "value": 3, "range": [1, 10]}]}]}), encoding="utf-8")
    errors, _ = check_declarations(collect_declared_keys([test], {"action:setSliderValue"}),
                                   {"action:setSliderValue": {"web": "1.19.0"}}, project)
    assert len(errors) == 1, errors
    assert errors[0].startswith("the action 'setSliderValue' requires the web driver 1.19.0 or newer, but 1.18.1 is installed")
    assert "fails it as unknown" in errors[0]
