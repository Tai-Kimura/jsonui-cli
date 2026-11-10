"""A colour mode's own picture: ``<name>.<mode>.svg`` beside ``<name>.svg`` (ticket jui-images-no-per-color-mode-variants).

jui build wrote one imageset / drawable / file from ``<name>.svg`` and nothing chose another, so an icon could not
follow the colour mode. Now each mode of colors.json may have its own picture: written as ``<name>__<mode>`` on iOS and
Android and as the file itself on the web, with the table ``image_modes.json`` beside colors.json on each face. An
image with no mode's picture is drawn as it always was, and a project with none gets no table.

The build stops on a picture it cannot draw: a mode's picture with no ``<name>.svg``, a ``<name>.<x>.svg`` beside
``<name>.svg`` whose ``x`` is no mode, two pictures one face would write under one name.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "jui_tools"))

from jui_cli.commands import build_cmd  # noqa: E402
from jui_cli.core import image_modes  # noqa: E402
from jui_cli.core.config_manager import ConfigManager  # noqa: E402

SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"><rect width="4" height="4"/></svg>\n'
COLORS = {"modes": ["light", "dark", "sepia"], "fallback_mode": "light",
          "systemModeMapping": {"light": "light", "dark": "dark"},
          "light": {"ink": "#000000"}, "dark": {"ink": "#FFFFFF"}, "sepia": {"ink": "#4A3420"}}


def _paths(*names: str) -> list[Path]:
    return [Path(f"/x/{n}.svg") for n in names]


class TestTheModes:
    def test_a_themed_file_names_its_modes(self, tmp_path):
        f = tmp_path / "colors.json"
        f.write_text(json.dumps(COLORS))
        assert image_modes.read_modes(f) == ["light", "dark", "sepia"]

    def test_settings_and_notes_are_no_mode(self, tmp_path):
        # colorSchemes (the web's color-scheme for a mode) is a setting like
        # systemModeMapping, and a `_` key is a note: first in the file, neither
        # made the file read as flat (light only).
        f = tmp_path / "colors.json"
        f.write_text(json.dumps({"colorSchemes": {"sepia": "dark"}, "_comment": "a note",
                                 "light": {"ink": "#000000"}, "sepia": {"ink": "#4A3420"}}))
        assert image_modes.read_modes(f) == ["light", "sepia"]
        f.write_text(json.dumps({"_comment": "a note", "light": {"ink": "#000000"}, "dark": {"ink": "#FFFFFF"}}))
        assert image_modes.read_modes(f) == ["light", "dark"]

    def test_a_flat_file_or_none_is_light_only(self, tmp_path):
        f = tmp_path / "colors.json"
        f.write_text(json.dumps({"ink": "#000000"}))
        assert image_modes.read_modes(f) == ["light"]
        assert image_modes.read_modes(tmp_path / "absent.json") == ["light"]


class TestTheSort:
    MODES = ["light", "dark", "sepia"]

    def test_a_mode_picture_beside_its_base(self):
        images, variants, errors = image_modes.split(_paths("ic", "ic.dark", "ic.sepia", "plain"), self.MODES)
        assert sorted(images) == ["ic", "plain"]
        assert {n: sorted(m) for n, m in variants.items()} == {"ic": ["dark", "sepia"]}
        assert errors == []

    def test_a_dotted_name_with_no_base_is_an_image_as_before(self):
        images, variants, errors = image_modes.split(_paths("logo.v2"), self.MODES)
        assert list(images) == ["logo.v2"] and variants == {} and errors == []

    def test_a_mode_picture_without_its_base_stops(self):
        _, _, errors = image_modes.split(_paths("ic.dark"), self.MODES)
        assert len(errors) == 1 and "there is no ic.svg" in errors[0]

    def test_a_suffix_that_is_no_mode_beside_its_base_stops(self):
        _, _, errors = image_modes.split(_paths("ic", "ic.drak"), self.MODES)
        assert len(errors) == 1 and "'drak' is not a mode" in errors[0]

    def test_two_pictures_written_under_one_name_stop(self):
        _, _, errors = image_modes.split(_paths("ic", "ic.High-Contrast", "ic.high_contrast"),
                                         ["light", "High-Contrast", "high_contrast"])
        assert len(errors) == 1 and "'ic__high_contrast'" in errors[0]

    def test_the_names(self):
        assert image_modes.asset_name("ic", "dark") == "ic__dark"
        assert image_modes.asset_name("ic", "High-Contrast") == "ic__high_contrast"


class TestTheTable:
    def test_no_mode_picture_is_no_file_and_takes_an_old_one_away(self, tmp_path):
        assert image_modes.write_table(tmp_path, {}) is False
        assert not (tmp_path / image_modes.TABLE_NAME).exists()
        image_modes.write_table(tmp_path, {"ic": {"dark": Path("ic.dark.svg")}})
        assert image_modes.write_table(tmp_path, {}) is True
        assert not (tmp_path / image_modes.TABLE_NAME).exists()

    def test_the_table_names_each_picture_and_is_written_once(self, tmp_path):
        variants = {"ic": {"sepia": Path("ic.sepia.svg"), "dark": Path("ic.dark.svg")}}
        assert image_modes.write_table(tmp_path, variants) is True
        assert json.loads((tmp_path / image_modes.TABLE_NAME).read_text()) == {
            "version": 1, "images": {"ic": {"dark": "ic__dark", "sepia": "ic__sepia"}}}
        assert image_modes.write_table(tmp_path, variants) is False


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path
    (root / "docs/screens/layouts/Resources").mkdir(parents=True)
    (root / "docs/screens/layouts/Resources/colors.json").write_text(json.dumps(COLORS))
    (root / "docs/screens/images").mkdir(parents=True)
    (root / "ios/App/Assets.xcassets").mkdir(parents=True)
    (root / "android").mkdir()
    (root / "web").mkdir()
    platforms = {"ios": {"root": "ios", "layoutsDir": "App/Layouts"},
                 "android": {"root": "android", "layoutsDir": "app/src/main/assets/Layouts"},
                 "web": {"root": "web", "layoutsDir": "src/Layouts"}}
    (root / "jui.config.json").write_text(json.dumps({"layouts_directory": "docs/screens/layouts",
                                                      "images_directory": "docs/screens/images", "platforms": platforms}))
    monkeypatch.chdir(root)
    written = []

    def record(face):
        def convert(svg, dest, name=None, outputs=None):
            written.append((face, svg.name, name))
            return dest / (name or svg.stem)
        return convert

    def copy(svg, dest):
        written.append(("web", svg.name, None))
        return dest / svg.name

    monkeypatch.setattr(build_cmd.ImageConverter, "convert_ios", staticmethod(record("ios")))
    monkeypatch.setattr(build_cmd.ImageConverter, "convert_android", staticmethod(record("android")))
    monkeypatch.setattr(build_cmd.ImageConverter, "convert_web", staticmethod(copy))

    def run(*names):
        for n in names:
            (root / "docs/screens/images" / f"{n}.svg").write_text(SVG)
        cm = ConfigManager(root / "jui.config.json")
        args = argparse.Namespace(ios_only=False, android_only=False, web_only=False)
        return build_cmd._distribute_images(cm, cm.load(), platforms, args)

    return root, run, written


class TestTheBuild:
    def test_each_face_writes_each_picture_under_its_name_and_the_table(self, project):
        root, run, written = project
        assert run("ic", "ic.dark", "ic.sepia", "plain") is True
        for face in ("ios", "android"):
            # (the file, the name it is written as; None is the file's own name)
            assert sorted((s, str(n)) for f, s, n in written if f == face) == [
                ("ic.dark.svg", "ic__dark"), ("ic.sepia.svg", "ic__sepia"), ("ic.svg", "None"), ("plain.svg", "None")]
        assert sorted(s for f, s, _ in written if f == "web") == ["ic.dark.svg", "ic.sepia.svg", "ic.svg", "plain.svg"]
        for resources in ("ios/App/Layouts/Resources", "android/app/src/main/assets/Layouts/Resources", "web/src/Layouts/Resources"):
            table = json.loads((root / resources / "image_modes.json").read_text())
            assert table["images"] == {"ic": {"dark": "ic__dark", "sepia": "ic__sepia"}}

    def test_a_project_without_a_mode_picture_writes_no_table(self, project):
        root, run, written = project
        assert run("ic", "plain") is True
        assert all(n is None for _, _, n in written)
        assert not list(root.rglob("image_modes.json"))

    def test_a_picture_the_build_cannot_draw_stops_it_before_anything_is_written(self, project, capsys):
        root, run, written = project
        assert run("ic.dark") is False
        assert written == [] and not list(root.rglob("image_modes.json"))
        assert "ERROR [image-modes]" in capsys.readouterr().out

    def test_cmd_build_halts_on_it(self):
        source = Path(build_cmd.__file__).read_text(encoding="utf-8")
        assert "images_ok = _distribute_images(" in source
        assert "if images_ok is False:\n            return _halt(1)" in source
