"""`jsonui-test validate` names a `notVisible` on a decorative image — it
cannot fail on iOS (INFO).

A decorative image (no alt, operates nothing) is hidden from VoiceOver on
iOS, and the iOS driver reads an element hidden from VoiceOver as not
visible even while it is on screen: measured on an iOS 18 simulator, the
same element satisfies both `visible` and `notVisible`. The rule that makes
an image decorative is shared/core/image_accessibility.py — the fifth
implementation of it, so it runs the shared table the other four run.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jsonui_test_cli.validation import decorative_images, element_ids
from jsonui_test_cli.validator import TestValidator as Validator

SHARED_CORE = Path(__file__).resolve().parents[2] / "shared" / "core"


def _rule():
    # This tree's jui_cli, as the check itself takes it: run first, or alone,
    # this otherwise read an installed jui_cli whose shared/core predates the
    # rule (and passed only after another module had put this tree's first).
    from jsonui_test_cli.validation.screen_ids import _prefer_sibling_jui_cli
    _prefer_sibling_jui_cli()
    from jui_cli.core import shared_core
    return shared_core.load("image_accessibility")


def _ids(node, rule, out):
    for image, role in rule.roles(node):
        out[image["id"]] = role
    return out


def test_every_case_of_the_shared_table_gets_its_roles():
    rule = _rule()
    assert rule is not None, "shared/core/image_accessibility.py did not load"
    cases = json.loads((SHARED_CORE / "image_accessibility_vectors.json").read_text(encoding="utf-8"))["cases"]
    assert cases
    seen = set()
    for vector in cases:
        assert _ids(vector["layout"], rule, {}) == vector["roles"], vector["name"]
        seen |= set(vector["roles"].values())
    assert seen == {"label", "decorative", "control"}


# ------------------------------------------------------------ validate


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
    decorative_images.clear_cache()
    yield
    element_ids.set_run_project()
    decorative_images.clear_cache()


def _validate(root: Path, steps):
    cfg = _write(root / "app/jui.config.json", {"layouts_directory": "layouts"})
    _write(root / "app/layouts/detail.json", LAYOUT)
    element_ids.set_run_project(json.loads(cfg.read_text()), cfg)
    test = _write(root / "tests/detail.test.json", {
        "type": "screen", "source": {"layout": "../app/layouts/detail.json"},
        "metadata": {"name": "detail"},
        "cases": [{"name": "c", "description": "d", "steps": steps}]})
    return Validator().validate_file(test)


def _named(result):
    return [(m.path, m.message) for m in result.infos if m.kind == "decorative-not-visible"]


def test_not_visible_on_a_decorative_image_is_named_with_both_fixes(tmp_path):
    result = _validate(tmp_path, [{"assert": "notVisible", "id": "hero_image"}])
    named = _named(result)
    assert len(named) == 1
    where, message = named[0]
    assert where.endswith(".cases[0].steps[0]")
    assert "notVisible on 'hero_image' cannot fail on iOS" in message
    assert "detail.json" in message
    assert "the id of the view around it" in message and "give the image an alt" in message
    assert result.warnings == [] and result.errors == []


def test_a_condition_waiting_on_it_is_not_named(tmp_path):
    # A `when` / `while` notVisible is the driver's !isInstantlyVisible, which
    # reads a decorative image on screen as visible (measured with the driver
    # itself, SwiftJsonUI ConformanceHost -decorativeImageProbe): it can fail.
    # The assertion on the same image, in the same test, is the control.
    result = _validate(tmp_path, [
        {"action": "tap", "id": "logo", "when": {"notVisible": "hero_image"}},
        {"action": "repeat", "times": 2, "while": {"notVisible": "hero_image"},
         "steps": [{"action": "tap", "id": "logo"}]},
        {"assert": "notVisible", "id": "hero_image"},
    ])
    named = _named(result)
    assert [where.rsplit(".", 1)[-1] for where, _ in named] == ["steps[2]"], named


def test_control_the_same_assertion_on_images_that_stay_readable_says_nothing(tmp_path):
    # menu_icon is the only content of a tappable with no text (a control:
    # never hidden); logo has an alt (read); visible on the decorative one
    # still holds on iOS.
    result = _validate(tmp_path, [
        {"assert": "notVisible", "id": "menu_icon"},
        {"assert": "notVisible", "id": "logo"},
        {"assert": "visible", "id": "hero_image"},
        {"assert": "notVisible", "id": "menu_button"},
    ])
    assert _named(result) == []
