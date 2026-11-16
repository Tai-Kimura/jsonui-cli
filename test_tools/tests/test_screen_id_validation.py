"""Screen-id validation against a project's layout vocabulary.

Rules from ``shared/core/screen_identity.json``: screen-unknown,
screen-not-a-screen and the app-owned escape hatch. These tests build
throwaway projects because the rule depends on the layout tree, which is
exactly the part that used to be unverifiable.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jsonui_test_cli.validation.screen_ids import clear_cache
from jsonui_test_cli.validator import TestValidator


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


def _write(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _project(root: Path, *, layouts: dict, config_extra: dict | None = None) -> Path:
    """A minimal project: jui.config.json + a layout tree + tests/."""
    config = {"layouts_directory": "Layouts"}
    if config_extra:
        config.update(config_extra)
    _write(root / "jui.config.json", config)
    for rel, payload in layouts.items():
        _write(root / "Layouts" / rel, payload)
    return root


def _flow(root: Path, steps: list[dict], name: str = "nav") -> Path:
    return _write(
        root / "tests" / "flows" / f"{name}.test.json",
        {"type": "flow", "metadata": {"name": name}, "steps": steps},
    )


def _messages(result) -> str:
    return " | ".join(m.message for m in result.errors)


def test_known_screen_passes(tmp_path):
    root = _project(tmp_path, layouts={"login.json": {"type": "View"}, "mypage.json": {"type": "View"}})
    flow = _flow(root, [
        {"screen": "login", "action": "tap", "id": "sign_in"},
        {"screen": "mypage", "assert": "visible", "id": "title"},
    ])
    result = TestValidator().validate_file(flow)
    assert not result.errors, _messages(result)


def test_unknown_screen_is_an_error(tmp_path):
    root = _project(tmp_path, layouts={"login.json": {"type": "View"}})
    flow = _flow(root, [{"screen": "typo_screen", "action": "tap", "id": "x"}])
    result = TestValidator().validate_file(flow)
    assert any("screen-unknown" in m.message for m in result.errors), _messages(result)


def test_cell_used_as_a_screen_is_an_error(tmp_path):
    root = _project(
        tmp_path,
        layouts={
            "chat.json": {"type": "Collection", "cellClasses": ["chat/message_cell"]},
            "chat/message_cell.json": {"type": "View"},
        },
    )
    flow = _flow(root, [{"screen": "message_cell", "action": "tap", "id": "chip"}])
    result = TestValidator().validate_file(flow)
    assert any("screen-not-a-screen" in m.message for m in result.errors), _messages(result)


def test_nested_layout_is_a_valid_screen(tmp_path):
    # Layout collection is recursive: a sheet one level deep is a screen.
    root = _project(
        tmp_path,
        layouts={"mypage.json": {"type": "View"}, "mypage/change_email_sheet.json": {"type": "View"}},
    )
    flow = _flow(root, [{"screen": "change_email_sheet", "action": "tap", "id": "save"}])
    result = TestValidator().validate_file(flow)
    assert not result.errors, _messages(result)


def test_app_owned_screen_must_be_declared(tmp_path):
    root = _project(tmp_path, layouts={"product_page.json": {"type": "View"}})
    flow = _flow(root, [{"screen": "tokushoho", "assert": "visible", "id": "tokushohoTitle"}])
    result = TestValidator().validate_file(flow)
    assert any("screen-unknown" in m.message for m in result.errors), _messages(result)


def test_declared_app_owned_screen_passes(tmp_path):
    root = _project(
        tmp_path,
        layouts={"product_page.json": {"type": "View"}},
        config_extra={"test": {"appOwnedScreens": ["tokushoho"]}},
    )
    flow = _flow(root, [{"screen": "tokushoho", "assert": "visible", "id": "tokushohoTitle"}])
    result = TestValidator().validate_file(flow)
    assert not result.errors, _messages(result)


def test_multi_app_project_finds_its_sibling_config(tmp_path):
    # tests/<app>/... beside <app>/jui.config.json — the config is a sibling
    # of the test tree, never an ancestor.
    app_root = tmp_path / "user"
    _write(app_root / "jui.config.json", {
        "layouts_directory": "../docs/user/layouts",
        "test": {"appOwnedScreens": ["licenses"]},
    })
    _write(tmp_path / "docs" / "user" / "layouts" / "product_page.json", {"type": "View"})
    flow = _write(
        tmp_path / "tests" / "user" / "flows" / "footer.test.json",
        {"type": "flow", "metadata": {"name": "footer"}, "steps": [
            {"screen": "product_page", "action": "tap", "id": "licenses_link"},
            {"screen": "licenses", "assert": "visible", "id": "licensesTitle"},
            {"screen": "ghost", "assert": "visible", "id": "x"},
        ]},
    )
    result = TestValidator().validate_file(flow)
    assert any("screen-unknown" in m.message and "ghost" in m.message for m in result.errors)
    assert not any("licenses" in m.message for m in result.errors), _messages(result)


def test_project_without_locatable_layouts_is_skipped(tmp_path):
    # No config anywhere: the validator also runs on trees it knows nothing
    # about, and inventing errors there would block their pipeline.
    flow = _write(
        tmp_path / "tests" / "flows" / "nav.test.json",
        {"type": "flow", "metadata": {"name": "nav"}, "steps": [
            {"screen": "whatever", "action": "tap", "id": "x"},
        ]},
    )
    result = TestValidator().validate_file(flow)
    assert not result.errors, _messages(result)


def test_screen_assertion_target_is_validated(tmp_path):
    root = _project(tmp_path, layouts={"login.json": {"type": "View"}})
    flow = _flow(root, [{"screen": "login", "assert": "screen", "name": "not_a_screen"}])
    result = TestValidator().validate_file(flow)
    assert any("screen-unknown" in m.message for m in result.errors), _messages(result)


def test_screen_assertion_accepts_a_known_target(tmp_path):
    root = _project(tmp_path, layouts={"login.json": {"type": "View"}, "mypage.json": {"type": "View"}})
    flow = _flow(root, [{"screen": "login", "assert": "screen", "name": "mypage", "timeout": 10000}])
    result = TestValidator().validate_file(flow)
    assert not result.errors, _messages(result)


def test_screen_assertion_requires_its_target(tmp_path):
    root = _project(tmp_path, layouts={"login.json": {"type": "View"}})
    flow = _flow(root, [{"screen": "login", "assert": "screen"}])
    result = TestValidator().validate_file(flow)
    assert any("Missing required parameter 'name'" in m.message for m in result.errors), _messages(result)
