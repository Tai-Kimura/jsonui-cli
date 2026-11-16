"""`jsonui-test validate` says nothing about a `notVisible` on a decorative
image, wherever the image is.

Until 1.9.29 this file pinned where the decorative-not-visible INFO was
judged (the test's screen, a flow step's screen, an include, a cell, iOS
platforms only). The INFO is retired: from jsonui-test-runner-ios 9a191dd
`notVisible` is the exact negation of `visible`, and a decorative image on
screen is visible on iOS as on Android, so the assertion can fail. The
shapes that used to be named are kept here, each now required to be silent
end to end, beside a control that the run still prints what it validates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from jsonui_test_cli import cli
from jsonui_test_cli.validation import element_ids, screen_ids

DECORATIVE = {"type": "Image", "id": "headerLogoImage", "src": "logo"}


def _screen(image) -> dict:
    return {"type": "View", "id": "root", "child": [
        {"type": "View", "id": "header", "child": [image]},
        {"type": "Label", "id": "title", "text": "t"},
    ]}


def _screen_test(steps) -> dict:
    return {"type": "screen", "source": {"layout": "../layouts/detail.json"},
            "metadata": {"name": "detail"},
            "cases": [{"name": "c", "description": "d", "steps": steps}]}


@pytest.fixture(autouse=True)
def _clean():
    yield
    element_ids.set_run_project()
    screen_ids.clear_cache()


def _run(root: Path, monkeypatch, capsys, layouts: dict, tests: dict,
         platforms=("ios", "android")) -> str:
    """The whole stdout of one validate run."""
    config: dict = {"layouts_directory": "layouts", "styles_directory": "styles"}
    if platforms is not None:
        config["platforms"] = {p: {} for p in platforms}
    files = {"jui.config.json": config}
    files.update({f"layouts/{k}.json": v for k, v in layouts.items()})
    files.update({f"tests/{k}": v for k, v in tests.items()})
    for rel, data in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(json.dumps(data), encoding="utf-8")
    (root / "styles").mkdir(exist_ok=True)
    monkeypatch.chdir(root)
    cli.cmd_validate(argparse.Namespace(
        files=["tests"], verbose=False, quiet=False, config=None,
        no_mock_check=True, no_install=True, strict=False))
    return capsys.readouterr().out


def _silent_about(out: str, image_id: str) -> bool:
    return "cannot fail on iOS" not in out and "decorative" not in out and image_id not in out


def test_a_decorative_image_on_the_tests_screen(tmp_path, monkeypatch, capsys):
    out = _run(tmp_path, monkeypatch, capsys, {"detail": _screen(DECORATIVE)},
               {"detail.test.json": _screen_test([{"assert": "notVisible", "id": "headerLogoImage"}])})
    assert _silent_about(out, "headerLogoImage"), out


def test_a_flow_step_on_a_screen_with_a_decorative_image(tmp_path, monkeypatch, capsys):
    flow = {"type": "flow", "metadata": {"name": "f"},
            "steps": [{"screen": "detail", "assert": "notVisible", "id": "headerLogoImage"}]}
    out = _run(tmp_path, monkeypatch, capsys, {"detail": _screen(DECORATIVE)},
               {"f.test.json": flow})
    assert _silent_about(out, "headerLogoImage"), out


def test_a_decorative_image_in_a_cell_of_the_screen(tmp_path, monkeypatch, capsys):
    layouts = {
        "detail": {"type": "View", "id": "root", "child": [
            {"type": "Collection", "id": "list", "cellClasses": ["detail_cell"]}]},
        "detail_cell": {"type": "View", "id": "cell_root", "child": [
            {"type": "Image", "id": "cellIcon", "src": "icon"}]},
    }
    out = _run(tmp_path, monkeypatch, capsys, layouts,
               {"detail.test.json": _screen_test([{"assert": "notVisible", "id": "cellIcon"}])})
    assert _silent_about(out, "cellIcon"), out


@pytest.mark.parametrize("platforms", [("ios",), ("ios", "android"), None], ids=["ios", "both", "none"])
def test_whatever_the_project_builds(tmp_path, monkeypatch, capsys, platforms):
    out = _run(tmp_path, monkeypatch, capsys, {"detail": _screen(DECORATIVE)},
               {"detail.test.json": _screen_test([{"assert": "notVisible", "id": "headerLogoImage"}])},
               platforms=platforms)
    assert _silent_about(out, "headerLogoImage"), out


def test_control_the_run_still_names_an_id_the_screen_does_not_carry(tmp_path, monkeypatch, capsys):
    # Same harness, same screen: a step on an id the layout lacks is named,
    # so the silence above is the retired INFO, not a run that printed nothing.
    out = _run(tmp_path, monkeypatch, capsys, {"detail": _screen(DECORATIVE)},
               {"detail.test.json": _screen_test([
                   {"assert": "notVisible", "id": "headerLogoImage"},
                   {"assert": "visible", "id": "no_such_view"}])})
    assert "no_such_view" in out, out
    assert _silent_about(out, "headerLogoImage"), out
