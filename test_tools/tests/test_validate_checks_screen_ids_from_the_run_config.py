"""`jsonui-test validate` checks a step's screen values against the layouts
of the config the run read — test-validate-screen-ids-finds-config-by-
walking-up-and-skips-split-trees.

The screen index used to come from a walk up from the test file. Where the
tests sit beside the app rather than under it (a split tree: the app's
layouts declared in `<app>/jui.config.json`), the walk found no config, or
one that declares no layouts, and the whole check stood down — every
`screen-unknown` passed and the run said nothing. It now takes the config
the run read, as the element-id check does (element_ids.set_run_project),
and counts what it could not check.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path

import pytest

from jsonui_test_cli.validation import screen_ids
from jsonui_test_cli.validator import TestValidator as Validator


def _write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


LAYOUTS = {
    "detail": {"type": "View", "id": "root", "child": [
        {"type": "Collection", "id": "rows", "cellClasses": ["row_cell"]}]},
    "row_cell": {"type": "View", "id": "rowTitle"},
    "catalog": {"type": "View", "id": "catalogRoot"},
}


def _face(root: Path, config=None) -> Path:
    cfg = _write(root / "app/jui.config.json",
                 config if config is not None else {"layouts_directory": "layouts"})
    for name, tree in LAYOUTS.items():
        _write(root / f"app/layouts/{name}.json", tree)
    return cfg


def _test(path: Path, screens) -> Path:
    return _write(path, {
        "type": "screen", "source": {"layout": "detail"},
        "metadata": {"name": "detail"},
        "cases": [{"name": "c", "description": "d",
                   "steps": [{"assert": "screen", "name": s} for s in screens]}]})


SCREENS = ["detail", "catalog", "ghost", "row_cell"]


def _errors(result):
    return sorted(m.message.split(" (")[0] for m in result.errors)


@pytest.fixture(autouse=True)
def _clean():
    screen_ids.clear_cache()
    yield
    screen_ids.clear_cache()


def test_a_test_beside_the_app_is_checked_against_the_config_the_run_read(tmp_path):
    cfg = _face(tmp_path)
    screen_ids.set_run_config(json.loads(cfg.read_text()), cfg)
    result = Validator().validate_file(_test(tmp_path / "tests/detail.test.json", SCREENS))
    assert dict(result.screen_ids) == {"checked": 4}
    assert _errors(result) == ["'row_cell' is a cell, not a screen", "Unknown screen 'ghost'"]


def test_control_walking_up_from_that_test_checks_none_of_them(tmp_path):
    # The shape before: no run config, so the walk from tests/ reaches no
    # jui.config.json — nothing is checked, and now that is counted.
    _face(tmp_path)
    result = Validator().validate_file(_test(tmp_path / "tests/detail.test.json", SCREENS))
    assert dict(result.screen_ids) == {"not_checked": 4}
    assert _errors(result) == []
    assert result.screen_ids_unchecked_why == \
        "no jui.config.json above the test file, and the run read none"


def test_control_a_config_above_the_tests_that_declares_no_layouts(tmp_path):
    # The split tree measured on a real project: the repository root has a
    # config, the apps below it declare the layouts. The walk stops at the
    # root one.
    _face(tmp_path)
    _write(tmp_path / "jui.config.json", {"project_name": "root"})
    result = Validator().validate_file(_test(tmp_path / "tests/detail.test.json", SCREENS))
    assert dict(result.screen_ids) == {"not_checked": 4}
    assert result.screen_ids_unchecked_why.endswith("declares no layouts directory that exists")

    screen_ids.clear_cache()
    cfg = tmp_path / "app/jui.config.json"
    screen_ids.set_run_config(json.loads(cfg.read_text()), cfg)
    result = Validator().validate_file(_test(tmp_path / "tests/detail.test.json", SCREENS))
    assert dict(result.screen_ids) == {"checked": 4}


def test_the_same_test_is_checked_the_same_inside_the_app_and_beside_it(tmp_path):
    cfg = _face(tmp_path)
    inside = Validator().validate_file(_test(tmp_path / "app/tests/detail.test.json", SCREENS))

    screen_ids.clear_cache()
    screen_ids.set_run_config(json.loads(cfg.read_text()), cfg)
    beside = Validator().validate_file(_test(tmp_path / "tests/detail.test.json", SCREENS))

    assert inside.screen_ids == beside.screen_ids == {"checked": 4}
    assert _errors(inside) == _errors(beside)


def test_a_run_config_with_no_layouts_says_so(tmp_path):
    cfg = _face(tmp_path, config={"project_name": "no layouts here"})
    screen_ids.set_run_config(json.loads(cfg.read_text()), cfg)
    result = Validator().validate_file(_test(tmp_path / "tests/detail.test.json", SCREENS))
    assert dict(result.screen_ids) == {"not_checked": 4}
    assert result.screen_ids_unchecked_why == \
        f"{cfg.resolve()} declares no layouts directory that exists"


# ------------------------------------------------------------- the printed run

def _cli(tmp_path, config=None):
    cfg = _face(tmp_path, config)
    _test(tmp_path / "tests/detail.test.json", ["detail", "catalog"])
    from jsonui_test_cli.cli import main
    argv, cwd = sys.argv, os.getcwd()
    out = io.StringIO()
    try:
        os.chdir(cfg.parent)
        sys.argv = ["jsonui-test", "validate", "../tests", "--no-install", "--no-mock-check",
                    "--no-coverage-check"]
        with contextlib.redirect_stdout(out):
            rc = main()
    finally:
        sys.argv = argv
        os.chdir(cwd)
    return rc, out.getvalue(), cfg


def test_the_run_says_how_many_screen_values_it_checked(tmp_path):
    rc, out, _ = _cli(tmp_path)
    assert rc == 0
    assert "[INFO] screen ids: 2 named in the steps — 2 checked, 0 not checked" in out


def test_a_run_that_could_check_none_says_how_many_and_why(tmp_path):
    rc, out, cfg = _cli(tmp_path, config={"project_name": "no layouts here"})
    assert "[INFO] screen ids: 2 named in the steps — 0 checked, 2 not checked" in out
    assert (f"[INFO] screen ids: 2 not checked — {cfg.resolve()} declares no layouts "
            "directory that exists") in out
