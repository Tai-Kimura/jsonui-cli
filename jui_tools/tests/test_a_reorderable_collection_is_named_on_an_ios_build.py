"""A reorderable Collection on iOS's stack paths is named on a build that builds iOS, as INFO, when the app's minimum iOS
is below 27 (ticket jui-collection-drag-to-reorder, ruling B 2026-11-13; core/reorder_info.py).

SwiftUI reorders a stack with reorderable() from iOS 27; below it the library drags by itself, so such an app runs two
drags. The user asked for that to be said as INFO, not as a warning. The minimum iOS is read from jui.config.json's
platforms.ios.minimumOS, the Xcode project's IPHONEOS_DEPLOYMENT_TARGET or Package.swift, in that order.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
from pathlib import Path

import pytest

from jui_cli.commands import build_cmd
from jui_cli.core import reorder_info as info

ROWS = {"type": "Collection", "id": "stops", "reorderable": True, "onReorder": "@{onMoveStop}",
        "cellIdProperty": "cellId", "items": "@{stops}", "cellClasses": ["StopCell"], "lazy": "none"}


def _ios(tmp_path: Path, pbxproj: str | None = None, package: str | None = None, sjui_name: str = "App") -> Path:
    root = tmp_path / "ios"
    root.mkdir(parents=True, exist_ok=True)
    (root / "sjui.config.json").write_text(json.dumps({"project_file_name": sjui_name}), encoding="utf-8")
    if pbxproj is not None:
        (root / "App.xcodeproj").mkdir()
        (root / "App.xcodeproj" / "project.pbxproj").write_text(pbxproj, encoding="utf-8")
    if package is not None:
        (root / "Package.swift").write_text(package, encoding="utf-8")
    return root


TARGETS = "\t\t\t\tIPHONEOS_DEPLOYMENT_TARGET = 18.0;\n\t\t\t\tIPHONEOS_DEPLOYMENT_TARGET = 17.0;\n" \
          "\t\t\t\tIPHONEOS_DEPLOYMENT_TARGET = 26.2;\n"


def test_the_minimum_ios_is_the_smallest_deployment_target(tmp_path):
    _ios(tmp_path, pbxproj=TARGETS)
    assert info.minimum_ios(tmp_path, {"root": "ios"}) == (17.0, "App.xcodeproj/project.pbxproj IPHONEOS_DEPLOYMENT_TARGET")


def test_jui_config_minimum_os_comes_first(tmp_path):
    _ios(tmp_path, pbxproj=TARGETS)
    assert info.minimum_ios(tmp_path, {"root": "ios", "minimumOS": "27.0"}) == (27.0, "jui.config.json platforms.ios.minimumOS")


@pytest.mark.parametrize("package, version", [
    ('platforms: [.iOS(.v17)]', 17.0), ('platforms: [.iOS(.v16_4)]', 16.4), ('platforms: [.iOS("27.0")]', 27.0)])
def test_package_swift_when_there_is_no_xcode_project(tmp_path, package, version):
    _ios(tmp_path, package=package)
    assert info.minimum_ios(tmp_path, {"root": "ios"}) == (version, "Package.swift .iOS(...)")


def test_the_only_xcode_project_when_sjui_config_names_none(tmp_path):
    _ios(tmp_path, pbxproj=TARGETS, sjui_name="")
    assert info.minimum_ios(tmp_path, {"root": "ios"})[0] == 17.0


def test_none_when_nothing_says(tmp_path):
    _ios(tmp_path)
    minimum, why = info.minimum_ios(tmp_path, {"root": "ios"})
    assert minimum is None and "platforms.ios.minimumOS" in why


SECTIONS = {"sections": [{"cell": "StopCell"}], "lazy": "lazy"}


@pytest.mark.parametrize("extra, named", [
    ({}, True),                                          # lazy none (A6's shape): a VStack
    ({"reorderable": "@{editing}"}, True),
    ({"reorderable": False}, False),
    ({"reorderable": "false"}, False),
    ({"listStyle": "plain"}, True),                      # lazy none: a VStack even with a listStyle
    ({"lazy": "lazy"}, False),                           # no sections, lazy: the List path (onMove on every iOS)
    ({"lazy": "eager"}, False),
    (SECTIONS, True),                                    # sections, no listStyle: CollectionStackView
    (dict(SECTIONS, lazy="eager"), True),
    (dict(SECTIONS, listStyle="plain"), False),          # sections and a listStyle: the List path
    ({"reorderHandle": "grip"}, False),                  # a handle: the library's drag on every iOS
    ({"reorderLockedProperty": "isDivider"}, False),     # locked rows: the library's drag on every iOS
    ({"columns": 2}, False),                             # v1 reorders one vertical column only
    ({"orientation": "horizontal"}, False),
    ({"type": "View"}, False),
])
def test_which_collections_are_named(extra, named):
    lines = info.tree_lines({"type": "View", "child": [dict(ROWS, **extra)]}, "a.json", 17.0, "x")
    assert bool(lines) is named


def test_the_line_names_the_place_both_drags_and_where_the_floor_came_from():
    assert info.tree_lines(ROWS, "event/visit_order.json", 17.0, "App.xcodeproj/project.pbxproj IPHONEOS_DEPLOYMENT_TARGET") == [
        "INFO [ios-reorder]: event/visit_order.json: 'stops' (Collection) is reorderable: from iOS 27 it uses SwiftUI's "
        "standard reordering (reorderable / reorderContainer), and on iOS 17 to 26 the library's own drag; the app's "
        "minimum iOS is 17 (App.xcodeproj/project.pbxproj IPHONEOS_DEPLOYMENT_TARGET)."]


def test_an_app_from_ios_27_is_not_named():
    assert info.tree_lines(ROWS, "a.json", 27.0, "x") == []


def test_an_unread_minimum_says_so_and_how_to_set_it():
    line = info.tree_lines(ROWS, "a.json", None, "no IPHONEOS_DEPLOYMENT_TARGET")[0]
    assert "could not be read" in line and "platforms.ios.minimumOS" in line and "below iOS 27" in line


def test_the_line_is_not_a_warning_to_the_gates_that_count_them():
    line = info.tree_lines(ROWS, "a.json", 17.0, "x")[0]
    # the shapes build_cmd's warning tally and the consumers' gates count (build_cmd: `warning \[|warning:|\[warn|⚠`)
    assert not re.search(r"warning \[|warning:|\[warn|⚠|error", line, re.IGNORECASE)


def _project(root: Path, platforms: dict, minimum: str = "17.0") -> Path:
    (root / "docs" / "screens" / "layouts").mkdir(parents=True)
    (root / "docs" / "screens" / "layouts" / "order.json").write_text(json.dumps({
        "type": "View", "id": "root", "child": [ROWS]}), encoding="utf-8")
    for p in platforms.values():
        (root / p["root"]).mkdir(parents=True, exist_ok=True)
    if "ios" in platforms:
        (root / "ios" / "App.xcodeproj").mkdir()
        (root / "ios" / "App.xcodeproj" / "project.pbxproj").write_text(
            f"IPHONEOS_DEPLOYMENT_TARGET = {minimum};\n", encoding="utf-8")
    (root / "jui.config.json").write_text(json.dumps({
        "layouts_directory": "docs/screens/layouts", "platforms": platforms}), encoding="utf-8")
    return root


@pytest.fixture
def build(monkeypatch, tmp_path):
    """The real cmd_build; the platform tools are stand-ins that succeed."""
    def make(platforms, minimum="17.0", **flags):
        root = _project(tmp_path, platforms, minimum)
        monkeypatch.chdir(root)
        monkeypatch.setattr(build_cmd, "_run_tool", lambda _cmd, _cwd: True)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = build_cmd.cmd_build(argparse.Namespace(
                clean=False, ios_only=False, android_only=flags.get("android_only", False),
                web_only=False, platform=None, lint_strings=False, normalize_layouts=None))
        return rc, out.getvalue()
    return make


IOS = {"root": "ios", "layoutsDir": "Layouts"}
ANDROID = {"root": "android", "layoutsDir": "app/src/main/assets/Layouts"}


def test_a_build_that_builds_ios_names_it_once_and_exits_as_before(build):
    rc, out = build({"ios": IOS})
    assert rc == 0, out
    named = [line for line in out.splitlines() if line.startswith("INFO [ios-reorder]")]
    assert len(named) == 1 and "order.json: 'stops' (Collection) is reorderable" in named[0], out
    assert "minimum iOS is 17 (App.xcodeproj/project.pbxproj" in named[0]
    assert out.index("INFO [ios-reorder]") < out.index("--- Building iOS")


def test_control_an_app_from_ios_27_names_nothing(build):
    rc, out = build({"ios": IOS}, minimum="27.0")
    assert rc == 0, out
    assert "INFO [ios-reorder]" not in out


def test_control_an_android_build_names_nothing(build):
    rc, out = build({"ios": IOS, "android": ANDROID}, android_only=True)
    assert rc == 0, out
    assert "INFO [ios-reorder]" not in out
