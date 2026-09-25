"""`jsonui-test validate` reports screen-id-collision on the step that names
an ambiguous screen id — test-validate-screen-id-collision-is-defined-but-
never-reported.

The rule was declared an error (shared/core/screen_identity.json,
screenId.uniquenessNote) and its message had a helper, but nothing called
it: the index keeps one of the colliding layouts, so the id read as known
and the step passed. A collision no step names is left to `jui build`,
which stops on a duplicated layout basename on every face.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jsonui_test_cli.validation import screen_ids
from jsonui_test_cli.validator import TestValidator as Validator


def _write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _project(root: Path) -> None:
    cfg = _write(root / "app/jui.config.json", {"layouts_directory": "layouts"})
    _write(root / "app/layouts/detail.json", {"type": "View", "id": "root"})
    _write(root / "app/layouts/archive/detail.json", {"type": "View", "id": "oldRoot"})
    _write(root / "app/layouts/catalog.json", {"type": "View", "id": "catalogRoot"})
    screen_ids.set_run_config(json.loads(cfg.read_text()), cfg)


def _validate(root: Path, screen: str):
    return Validator().validate_file(_write(root / "tests/t.test.json", {
        "type": "screen", "source": {"layout": "catalog"}, "metadata": {"name": "t"},
        "cases": [{"name": "c", "description": "d",
                   "steps": [{"assert": "screen", "name": screen}]}]}))


@pytest.fixture(autouse=True)
def _clean():
    screen_ids.clear_cache()
    yield
    screen_ids.clear_cache()


def test_a_step_naming_an_ambiguous_screen_id_is_an_error(tmp_path):
    _project(tmp_path)
    result = _validate(tmp_path, "detail")
    messages = [m.message for m in result.errors]
    assert len(messages) == 1
    assert "(screen-id-collision): archive/detail.json, detail.json under " in messages[0]
    assert messages[0].startswith("Screen id 'detail' is ambiguous")


def test_control_a_step_naming_another_screen_of_that_project_passes(tmp_path):
    _project(tmp_path)
    result = _validate(tmp_path, "catalog")
    assert result.errors == []
    assert dict(result.screen_ids) == {"checked": 1}
