"""A small tappable element is named on a build that builds iOS, as INFO.

On iOS a small tappable element can lose its taps to a larger one behind it —
SwiftUI's own hit testing, measured on an iPhone 17 simulator: 8 pt took none
of nine points, 16 pt four, 20 pt eight, 22 pt and up all nine (ticket
swiftjsonui-nested-relative-small-child-tap-falls-through). The library is not
changed; the build says where to look (core/small_tap_info.py). It names an
element with onClick whose width or height is a number under 26 pt, with its
style merged, and nothing whose size it does not know.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jui_cli.commands import build_cmd  # noqa: E402
from jui_cli.core import small_tap_info as info  # noqa: E402


def _tap(extra):
    return {"type": "View", "id": "b", "onClick": "@{onB}", **extra}


@pytest.mark.parametrize("extra, named", [
    ({"width": 16, "height": 16}, ("16", "16")),
    ({"width": 25.5, "height": 40}, ("25.5", "40")),
    ({"width": "wrapContent", "height": 24}, ("?", "24")),
    ({"width": 26, "height": 26}, None),                  # the mark itself is not under it
    ({"width": 44, "height": 30}, None),
    ({"width": "wrapContent", "height": "wrapContent"}, None),
    ({"width": "matchParent", "height": "matchParent"}, None),
    ({}, None),                                           # no size: not known here
    ({"width": "@{w}", "height": "@{h}"}, None),          # bound: not known here
])
def test_which_sizes_are_named(extra, named):
    assert info.small_tap(_tap(extra)) == named


def test_only_a_tappable_element_is_named():
    assert info.small_tap({"type": "View", "id": "v", "width": 8, "height": 8}) is None
    assert info.small_tap({"type": "View", "id": "v", "width": 8, "height": 8, "onClick": ""}) is None


def test_the_line_says_where_what_and_that_it_varies(tmp_path):
    layouts, styles = tmp_path / "layouts", tmp_path / "styles"
    (layouts / "sub").mkdir(parents=True)
    styles.mkdir()
    (styles / "small_icon.json").write_text(json.dumps({"width": 18, "height": 18}), encoding="utf-8")
    (layouts / "sub" / "row.json").write_text(json.dumps({
        "type": "View", "id": "root", "width": "matchParent", "height": 60, "onClick": "@{onRow}",
        "child": [{"type": "Image", "id": "close", "style": "small_icon", "onClick": "@{onClose}"},
                  {"type": "View", "id": "big", "width": 44, "height": 44, "onClick": "@{onBig}"},
                  {"type": "View", "id": "wrap", "onClick": "@{onWrap}"}]}), encoding="utf-8")
    lines = info.directory_lines(layouts, styles)
    assert lines == [
        "INFO [ios-tap]: sub/row.json: 'close' (Image) is a small tappable element (18 x 18 pt). On iOS a larger "
        "element behind it can take its taps (roughly when a side is under 26 pt; it varies with the device and "
        "the OS). If it does not respond to taps, suspect this."]


def test_the_line_is_not_a_warning_to_the_gates_that_count_them():
    line = info.tree_lines(_tap({"width": 8, "height": 8}), "a.json")[0]
    # the shapes build_cmd's warning tally and the consumers' gates count (build_cmd: `warning \[|warning:|\[warn|⚠`)
    assert not re.search(r"warning \[|warning:|\[warn|⚠|error", line, re.IGNORECASE)


def _project(root: Path, platforms: dict) -> Path:
    (root / "docs" / "screens" / "layouts").mkdir(parents=True)
    (root / "docs" / "screens" / "layouts" / "home.json").write_text(json.dumps({
        "type": "View", "id": "root", "width": "matchParent", "height": "matchParent", "onClick": "@{onCard}",
        "child": [{"type": "View", "id": "help", "width": 16, "height": 16, "onClick": "@{onHelp}",
                   "alignTop": True, "alignRight": True}]}), encoding="utf-8")
    for p in platforms.values():
        (root / p["root"]).mkdir(parents=True, exist_ok=True)
    (root / "jui.config.json").write_text(json.dumps({
        "layouts_directory": "docs/screens/layouts", "platforms": platforms}), encoding="utf-8")
    return root


@pytest.fixture
def build(monkeypatch, tmp_path):
    """The real cmd_build; the platform tools are stand-ins that succeed."""
    def make(platforms, **flags):
        root = _project(tmp_path, platforms)
        monkeypatch.chdir(root)
        monkeypatch.setattr(build_cmd, "_run_tool", lambda _cmd, _cwd: True)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = build_cmd.cmd_build(argparse.Namespace(
                clean=False, ios_only=flags.get("ios_only", False), android_only=flags.get("android_only", False),
                web_only=False, platform=None, lint_strings=False, normalize_layouts=None))
        return rc, out.getvalue()
    return make


IOS = {"root": "ios", "layoutsDir": "Layouts"}
ANDROID = {"root": "android", "layoutsDir": "app/src/main/assets/Layouts"}
WEB = {"root": "web", "layoutsDir": "src/Layouts"}


def test_a_build_that_builds_ios_names_it_once_and_exits_as_before(build):
    rc, out = build({"ios": IOS, "web": WEB})
    assert rc == 0, out
    named = [line for line in out.splitlines() if line.startswith("INFO [ios-tap]")]
    assert len(named) == 1 and "home.json: 'help' (View) is a small tappable element (16 x 16 pt)" in named[0]
    assert out.index("INFO [ios-tap]") < out.index("--- Building iOS")


def test_control_a_build_that_does_not_build_ios_names_nothing(build):
    rc, out = build({"android": ANDROID, "web": WEB})
    assert rc == 0, out
    assert "INFO [ios-tap]" not in out


def test_control_an_android_only_build_of_an_ios_project_names_nothing(build):
    rc, out = build({"ios": IOS, "android": ANDROID}, android_only=True)
    assert rc == 0, out
    assert "INFO [ios-tap]" not in out
