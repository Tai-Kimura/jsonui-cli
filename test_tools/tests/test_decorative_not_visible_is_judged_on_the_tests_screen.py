"""The decorative-not-visible INFO judges the id on the screen the step runs
on, and only where the step can run on iOS.

It was keyed by id across the whole project: every layout walked in name
order, the first decorative image with that id kept. An id five layouts
carry was named in the alphabetically first of them, not in the test's
screen; an id with an alt on the test's screen was still named when some
other layout had it without one; and a project that builds no iOS app got
an INFO whose premise is iOS.

Every arm runs `jsonui-test validate` end to end, from the config beside
the invocation, so the platforms reach the check the way a run reads them.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from jsonui_test_cli import cli
from jsonui_test_cli.validation import decorative_images, element_ids, screen_ids

MARK = "cannot fail on iOS"

DECORATIVE = {"type": "Image", "id": "headerLogoImage", "src": "logo"}
WITH_ALT = dict(DECORATIVE, alt="logo_label")
TAPPED = dict(DECORATIVE, onClick="@{onLogo}")

#: Five screens with the same header image; the test's screen is `detail`,
#: which is not the first of them by name.
SCREENS = ("album", "cart", "checkout", "detail", "search")


def _screen(image) -> dict:
    return {"type": "View", "id": "root", "child": [
        {"type": "View", "id": "header", "child": [image]},
        {"type": "Label", "id": "title", "text": "t"},
    ]}


def _five(detail_image, others=WITH_ALT, first=DECORATIVE) -> dict:
    layouts = {name: _screen(others) for name in SCREENS}
    layouts["album"] = _screen(first)
    layouts["detail"] = _screen(detail_image)
    return layouts


def _screen_test(steps, **top) -> dict:
    return dict({"type": "screen", "source": {"layout": "../layouts/detail.json"},
                 "metadata": {"name": "detail"},
                 "cases": [{"name": "c", "description": "d", "steps": steps}]}, **top)


NOT_VISIBLE = [{"assert": "notVisible", "id": "headerLogoImage"}]


@pytest.fixture(autouse=True)
def _clean():
    decorative_images.clear_cache()
    yield
    element_ids.set_run_project()
    screen_ids.clear_cache()
    decorative_images.clear_cache()


def _run(root: Path, monkeypatch, capsys, layouts: dict, tests: dict,
         platforms=("ios", "android"), styles: dict | None = None) -> list:
    """The decorative-not-visible INFO lines of one validate run."""
    config: dict = {"layouts_directory": "layouts", "styles_directory": "styles"}
    if platforms is not None:
        config["platforms"] = {p: {} for p in platforms}
    files = {"jui.config.json": config}
    files.update({f"layouts/{k}.json": v for k, v in layouts.items()})
    files.update({f"styles/{k}.json": v for k, v in (styles or {}).items()})
    files.update({f"tests/{k}": v for k, v in tests.items()})
    for rel, data in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(json.dumps(data), encoding="utf-8")
    (root / "styles").mkdir(exist_ok=True)
    monkeypatch.chdir(root)
    cli.cmd_validate(argparse.Namespace(
        files=["tests"], verbose=False, quiet=False, config=None,
        no_mock_check=True, no_install=True, strict=False))
    out = capsys.readouterr().out
    return [line.strip() for line in out.splitlines() if MARK in line]


# ------------------------------------------------ judged on the test's screen


@pytest.mark.parametrize("detail_image", [WITH_ALT, TAPPED], ids=["alt", "tap"])
def test_decorative_only_on_another_screen_says_nothing(tmp_path, monkeypatch, capsys,
                                                        detail_image):
    # `album` sorts first and has the image with no alt; on `detail`, the
    # screen this test runs, it is read (alt) or operates something (tap).
    lines = _run(tmp_path, monkeypatch, capsys, _five(detail_image),
                 {"detail.test.json": _screen_test(NOT_VISIBLE)})
    assert lines == []


def test_decorative_on_the_tests_screen_is_named_in_that_layout(tmp_path, monkeypatch, capsys):
    # Decorative on `album` (first by name) AND on `detail`: the layout
    # named is the test's screen.
    lines = _run(tmp_path, monkeypatch, capsys, _five(DECORATIVE),
                 {"detail.test.json": _screen_test(NOT_VISIBLE)})
    assert len(lines) == 1, lines
    assert ".cases[0].steps[0]" in lines[0]
    assert "a decorative image in detail.json" in lines[0]
    assert "album.json" not in lines[0]


def test_an_id_the_tests_screen_does_not_carry_says_nothing(tmp_path, monkeypatch, capsys):
    # The step may be on another screen by then (a screen test moves), and
    # nothing says which: not judged.
    layouts = _five(WITH_ALT)
    layouts["detail"] = {"type": "View", "id": "root", "child": [
        {"type": "Label", "id": "title", "text": "t"}]}
    lines = _run(tmp_path, monkeypatch, capsys, layouts,
                 {"detail.test.json": _screen_test(NOT_VISIBLE)})
    assert lines == []


def _where(line: str) -> str:
    return line.split(": ", 1)[0].split(".test.json", 1)[1]


def test_a_flow_step_is_judged_on_the_screen_it_names(tmp_path, monkeypatch, capsys):
    # Decorative on `detail` only. A block's steps are not judged: the
    # drivers run them without a screen (the one a step inside writes is
    # not read), on whatever screen the flow has reached.
    layouts = _five(DECORATIVE, others=WITH_ALT, first=WITH_ALT)
    flow = {"type": "flow", "metadata": {"name": "f"}, "steps": [
        {"screen": "cart", "assert": "notVisible", "id": "headerLogoImage"},
        {"screen": "detail", "assert": "notVisible", "id": "headerLogoImage"},
        {"screen": "detail", "action": "repeat", "times": 2, "steps": NOT_VISIBLE},
        {"block": "b", "steps": [
            {"screen": "detail", "assert": "notVisible", "id": "headerLogoImage"}]},
    ]}
    lines = _run(tmp_path, monkeypatch, capsys, layouts, {"f.test.json": flow})
    assert [_where(l) for l in lines] == [".steps[1]", ".steps[2].steps[0]"], lines
    assert all("a decorative image in detail.json" in l for l in lines)


# ------------------------------------------ as iOS resolves the screen's layout


def test_an_image_inside_an_include_is_judged_by_the_id_ios_gives_it(tmp_path, monkeypatch,
                                                                     capsys):
    # Native prefixes an id inside an include that has an id: `top` +
    # `logo_image` -> `topLogoImage`. The partial on its own has the old
    # spelling only.
    layouts = {
        "detail": {"type": "View", "id": "root", "child": [
            {"include": "header_part", "id": "top"}]},
        "header_part": {"type": "View", "id": "part_root", "partial": True, "child": [
            {"type": "Image", "id": "logo_image", "src": "logo"}]},
    }
    lines = _run(tmp_path, monkeypatch, capsys, layouts, {"detail.test.json": _screen_test([
        {"assert": "notVisible", "id": "topLogoImage"},
        {"assert": "notVisible", "id": "logo_image"},
    ])})
    assert len(lines) == 1, lines
    assert "'topLogoImage'" in lines[0] and "detail.json" in lines[0]


def test_an_alt_a_style_gives_is_read(tmp_path, monkeypatch, capsys):
    layouts = {"detail": _screen(dict(DECORATIVE, style="described"))}
    lines = _run(tmp_path, monkeypatch, capsys, layouts,
                 {"detail.test.json": _screen_test(NOT_VISIBLE)},
                 styles={"described": {"alt": "logo_label"}})
    assert lines == []


def test_the_screen_is_resolved_for_ios(tmp_path, monkeypatch, capsys):
    # An alt only iOS gets is read there; one only Android gets is not; an
    # image only Android draws is not on iOS at all.
    image = {"type": "Image", "src": "logo"}
    layouts = {"detail": {"type": "View", "id": "root", "child": [
        dict(image, id="iosAlt", platform={"ios": {"alt": "logo_label"}}),
        dict(image, id="androidAlt", platform={"android": {"alt": "logo_label"}}),
        dict(image, id="androidOnly", platform="android"),
    ]}}
    lines = _run(tmp_path, monkeypatch, capsys, layouts, {"detail.test.json": _screen_test([
        {"assert": "notVisible", "id": i} for i in ("iosAlt", "androidAlt", "androidOnly")])})
    assert [_where(l) for l in lines] == [".cases[0].steps[1]"], lines


def test_an_image_in_a_cell_of_the_screen_is_named_in_the_cell(tmp_path, monkeypatch, capsys):
    layouts = {
        "detail": {"type": "View", "id": "root", "child": [
            {"type": "Collection", "id": "list", "cellClasses": ["detail_cell"]}]},
        "detail_cell": {"type": "View", "id": "cell_root", "child": [
            {"type": "Image", "id": "cellIcon", "src": "icon"}]},
    }
    lines = _run(tmp_path, monkeypatch, capsys, layouts, {"detail.test.json": _screen_test([
        {"assert": "notVisible", "id": "cellIcon"}])})
    assert len(lines) == 1, lines
    assert "a decorative image in detail_cell.json" in lines[0]


def test_an_id_the_screen_gives_to_more_than_decorative_images_says_nothing(
        tmp_path, monkeypatch, capsys):
    # `icon`: decorative in one cell, read in the other. `badge`: a view on
    # the screen, a decorative image in a cell. `plain`: decorative in both
    # cells — the control.
    layouts = {
        "detail": {"type": "View", "id": "root", "child": [
            {"type": "View", "id": "badge"},
            {"type": "Collection", "id": "list", "cellClasses": ["cell_a", "cell_b"]}]},
        "cell_a": {"type": "View", "id": "a_root", "child": [
            {"type": "Image", "id": "icon", "src": "i"},
            {"type": "Image", "id": "badge", "src": "b"},
            {"type": "Image", "id": "plain", "src": "p"}]},
        "cell_b": {"type": "View", "id": "b_root", "child": [
            {"type": "Image", "id": "icon", "src": "i", "alt": "icon_label"},
            {"type": "Image", "id": "plain", "src": "p"}]},
    }
    lines = _run(tmp_path, monkeypatch, capsys, layouts, {"detail.test.json": _screen_test([
        {"assert": "notVisible", "id": i} for i in ("icon", "badge", "plain")])})
    assert [_where(l) for l in lines] == [".cases[0].steps[2]"], lines


def test_a_screen_id_two_layouts_share_says_nothing(tmp_path, monkeypatch, capsys):
    # Which of them the screen is cannot be told (the screen check and
    # `jui build` stop on it); control: the same with one of them renamed.
    for other, named in (("detail", 0), ("detail_old", 1)):
        root = tmp_path / other
        root.mkdir()
        lines = _run(root, monkeypatch, capsys, {
            f"a/{other}": _screen(DECORATIVE), "b/detail": _screen(DECORATIVE)},
            {"detail.test.json": _screen_test(NOT_VISIBLE, source={
                "layout": "../layouts/b/detail.json"})})
        decorative_images.clear_cache()
        assert len(lines) == named, (other, lines)


# ------------------------------------------------------- only where iOS runs


@pytest.mark.parametrize("platforms,named", [
    (("web",), 0),
    (("android", "web"), 0),
    (("ios",), 1),
    (("ios", "web"), 1),
    (None, 1),              # no platforms declared: as before the key was read
], ids=["web", "android+web", "ios", "ios+web", "undeclared"])
def test_a_project_that_builds_no_ios_app_gets_no_info(tmp_path, monkeypatch, capsys,
                                                       platforms, named):
    lines = _run(tmp_path, monkeypatch, capsys, _five(DECORATIVE),
                 {"detail.test.json": _screen_test(NOT_VISIBLE)}, platforms=platforms)
    assert len(lines) == named, lines


@pytest.mark.parametrize("test,named", [
    (_screen_test(NOT_VISIBLE, platform="web"), 0),
    (_screen_test(NOT_VISIBLE, platform=["android", "web"]), 0),
    (_screen_test(NOT_VISIBLE, platform="all"), 1),
    (_screen_test(NOT_VISIBLE, platform=["ios"]), 1),
    ({**_screen_test([]), "cases": [
        {"name": "c", "description": "d", "platform": "web", "steps": NOT_VISIBLE}]}, 0),
    ({**_screen_test([]), "cases": [
        {"name": "c", "description": "d", "platform": ["ios", "web"], "steps": NOT_VISIBLE}]}, 1),
    (_screen_test([{"assert": "notVisible", "id": "headerLogoImage",
                    "when": {"platform": "android"}}]), 0),
    (_screen_test([{"assert": "notVisible", "id": "headerLogoImage",
                    "when": {"platform": "web", "visible": "title"}}]), 0),
    (_screen_test([{"action": "repeat", "times": 2, "when": {"platform": "web"},
                    "steps": NOT_VISIBLE}]), 0),
    (_screen_test([{"assert": "notVisible", "id": "headerLogoImage",
                    "when": {"platform": "all"}}]), 1),
], ids=["test-web", "test-android-web", "test-all", "test-ios", "case-web", "case-ios-web",
        "step-android", "gated-with-a-condition", "around-web", "step-all"])
def test_a_step_ios_never_runs_gets_no_info(tmp_path, monkeypatch, capsys, test, named):
    lines = _run(tmp_path, monkeypatch, capsys, _five(DECORATIVE), {"detail.test.json": test})
    assert len(lines) == named, lines
