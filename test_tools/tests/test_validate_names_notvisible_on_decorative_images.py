"""`jsonui-test validate` no longer names a `notVisible` on a decorative image.

From 1.9.0 to 1.9.29 it did, as an INFO: a decorative image (no alt,
operates nothing) is hidden from VoiceOver on iOS, and the iOS driver read
an element that is not hittable as not visible, so `notVisible` on one held
while it was on screen and could not fail. From jsonui-test-runner-ios
9a191dd `notVisible` is the exact negation of `visible` (in the viewport),
and a decorative image on screen is visible — Android's answer, the
baseline. The assertion can fail on every platform, so nothing is named.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jsonui_test_cli.validation import element_ids
from jsonui_test_cli.validator import TestValidator as Validator


def _write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


LAYOUT = {"type": "View", "id": "root", "child": [
    {"type": "Image", "id": "hero_image", "src": "hero"},
    {"type": "View", "id": "menu_button", "onClick": "@{onMenu}", "child": [
        {"type": "Image", "id": "menu_icon", "src": "menu"}]},
    {"type": "Image", "id": "logo", "src": "logo", "alt": "logo_label"},
]}


@pytest.fixture(autouse=True)
def _clean():
    yield
    element_ids.set_run_project()


def _validate(root: Path, steps):
    cfg = _write(root / "app/jui.config.json", {"layouts_directory": "layouts"})
    _write(root / "app/layouts/detail.json", LAYOUT)
    element_ids.set_run_project(json.loads(cfg.read_text()), cfg)
    test = _write(root / "tests/detail.test.json", {
        "type": "screen", "source": {"layout": "../app/layouts/detail.json"},
        "metadata": {"name": "detail"},
        "cases": [{"name": "c", "description": "d", "steps": steps}]})
    return Validator().validate_file(test)


def _messages(result):
    return [m.message for m in result.infos + result.warnings + result.errors]


def test_not_visible_on_a_decorative_image_is_not_named(tmp_path):
    result = _validate(tmp_path, [
        {"assert": "notVisible", "id": "hero_image"},
        {"action": "tap", "id": "logo", "when": {"notVisible": "hero_image"}},
        {"action": "repeat", "times": 2, "while": {"notVisible": "hero_image"},
         "steps": [{"action": "tap", "id": "logo"}]},
    ])
    assert [m for m in result.infos if m.kind == "decorative-not-visible"] == []
    assert not any("hero_image" in m or "cannot fail" in m for m in _messages(result)), _messages(result)
    assert result.warnings == [] and result.errors == []


def test_control_the_same_file_still_names_an_id_the_layout_does_not_carry(tmp_path):
    # The validation that ran beside the retired one still speaks: a step on
    # an id the layout lacks is named, so the silence above is not a check
    # that did not run.
    result = _validate(tmp_path, [
        {"assert": "notVisible", "id": "hero_image"},
        {"assert": "visible", "id": "no_such_view"},
    ])
    assert any("no_such_view" in m for m in _messages(result)), _messages(result)
    assert not any("hero_image" in m for m in _messages(result)), _messages(result)
