"""A drawable that shares its name with the one jui wrote is named (ticket jui-android-drawable-same-name-two-extensions-after-first-record).

Since 2.5.23 a build removes only the drawables `.jsonui-cli/image-outputs.json`
records, and the first build has no record: an earlier build's output stayed
beside the new one. A face that swapped a JPEG picture for a PNG one got
drawable-nodpi/x.jpg and drawable-nodpi/x.png, and Android's build stopped.

Measured 2026-11-10 (aapt2 36.0.0 link; an Android 15 emulator reading which
file `getValue` resolves to at 120 to 640 dpi):
- two files of one name in one directory stop the build (aapt2: "conflicting
  value for configuration"): an ERROR, which does not stop jui build (iOS and
  web are still generated) and is a stage that did not complete, so the build
  exits 1 at its end;
- in two directories the build goes through and a device shows one by its
  density: a WARNING with the densities measured (drawable/ at 160 dpi and
  below against drawable-nodpi/ or drawable-xxhdpi/; drawable-nodpi/ at
  640 dpi against drawable-xxhdpi/);
- a project's own picture in two or more density directories is its choice
  and is not named (the WARNING; the same-directory ERROR still is).
Nothing is removed.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import io
import json
import os
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jui_cli.commands import build_cmd  # noqa: E402
from jui_cli.core.config_manager import ConfigManager  # noqa: E402
from jui_cli.core.image_converter import same_name_drawables  # noqa: E402



def _png(width: int, height: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    raw = b"".join(b"\x00" + b"\xc8\x0a\x0a" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _jpeg(width: int, height: int) -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof0 = b"\xff\xc0" + struct.pack(">HBHHB", 17, 8, height, width, 3) + b"\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    return b"\xff\xd8" + app0 + sof0 + b"\xff\xda\xff\xd9"


def _whole(mime: str, data: bytes) -> str:
    href = f"data:{mime};base64,{base64.b64encode(data).decode()}"
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">'
            f'<image href="{href}" x="0" y="0" width="24" height="24"/></svg>')


VECTOR = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">'
          '<path d="M2 2 L22 2 L12 22 Z" fill="#00f"/></svg>')
PNG_WHOLE = _whole("image/png", _png(72, 72))
JPEG_WHOLE = _whole("image/jpeg", _jpeg(72, 72))


class _Res(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.res = Path(self._tmp.name) / "res"

    def tearDown(self):
        self._tmp.cleanup()

    def put(self, *rel: str) -> list[Path]:
        paths = []
        for r in rel:
            p = self.res / r
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"x")
            paths.append(p)
        return paths

    def found(self, written: str, name="x"):
        return same_name_drawables(self.res, {name: (f"{name}.svg", self.res / written)})


class OneDirectoryIsAnError(_Res):
    def test_a_jpeg_beside_the_png_jui_wrote(self):
        # bar's shape: the picture became a PNG, the 2.5.22 x.jpg stayed.
        self.put("drawable-nodpi/x.jpg", "drawable-nodpi/x.png")
        [(level, line, summary)] = self.found("drawable-nodpi/x.png")
        self.assertEqual(level, "ERROR")
        self.assertIn("ERROR: x.svg: Android: drawable-nodpi/x.jpg and drawable-nodpi/x.png are one resource", line)
        self.assertIn("conflicting value for configuration", line)
        self.assertIn("jui wrote drawable-nodpi/x.png; remove drawable-nodpi/x.jpg", line)
        self.assertIn("remove drawable-nodpi/x.jpg", summary)

    def test_webp_and_a_png_written_into_drawable(self):
        for others, written in ((["drawable-nodpi/x.webp"], "drawable-nodpi/x.png"),
                                (["drawable/x.png"], "drawable/x.xml")):
            with self.subTest(written=written):
                self.put(*others, written)
                [(level, line, _)] = self.found(written)
                self.assertEqual(level, "ERROR")
                self.assertIn(f"remove {others[0]}", line)
                for p in self.res.rglob("x.*"):
                    p.unlink()

    def test_nothing_is_removed(self):
        self.put("drawable-nodpi/x.jpg", "drawable-nodpi/x.png")
        self.found("drawable-nodpi/x.png")
        self.assertEqual(sorted(p.name for p in self.res.rglob("x.*")), ["x.jpg", "x.png"])


class TwoDirectoriesAreAWarningWithTheDensities(_Res):
    CASES = [
        # (what jui wrote, what else is there, the densities that show the other)
        ("drawable-nodpi/x.png", "drawable/x.xml", "160 dpi and below"),
        ("drawable-xxhdpi/x.png", "drawable/x.xml", "160 dpi and below"),
        ("drawable/x.xml", "drawable-nodpi/x.jpg", "240 dpi and above"),
        ("drawable/x.xml", "drawable-xxhdpi/x.png", "240 dpi and above"),
        ("drawable-xxhdpi/x.png", "drawable-nodpi/x.png", "640 dpi"),
        ("drawable-nodpi/x.png", "drawable-xxhdpi/x.png", "480 dpi and below"),
    ]

    def test_each_measured_pair(self):
        for written, other, shown in self.CASES:
            with self.subTest(written=written, other=other):
                self.put(written, other)
                [(level, line, summary)] = self.found(written)
                self.assertEqual(level, "WARNING")
                self.assertIn(f"WARNING: x.svg: Android: {other} has the name of {written}, which jui wrote", line)
                self.assertIn(f"a device at {shown} shows {other}, not {written}", line)
                self.assertEqual(summary, "")
                for p in self.res.rglob("x.*"):
                    p.unlink()

    def test_a_directory_not_measured_says_the_configuration_decides(self):
        self.put("drawable/x.xml", "drawable-night/x.xml")
        [(level, line, _)] = self.found("drawable/x.xml")
        self.assertEqual(level, "WARNING")
        self.assertIn("drawable-night/x.xml", line)
        self.assertIn("Android shows one of them by the device's configuration", line)

    def test_one_density_directory_of_the_projects_is_still_named(self):
        self.put("drawable/x.xml", "drawable-hdpi/x.png")
        [(level, line, _)] = self.found("drawable/x.xml")
        self.assertEqual(level, "WARNING")
        self.assertIn("drawable-hdpi/x.png", line)


class AProjectsDensitySetIsNotNamed(_Res):
    def test_the_set_beside_jui_s_vector(self):
        # client's ic_x_white / ic_instagram_white on origin/main 2026-11-10.
        self.put("drawable/x.xml", *(f"drawable-{d}/x.png" for d in ("mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi")))
        self.assertEqual(self.found("drawable/x.xml"), [])

    def test_two_densities_are_a_set_and_a_nodpi_file_beside_it_is_still_named(self):
        self.put("drawable/x.xml", "drawable-hdpi/x.png", "drawable-xhdpi/x.png", "drawable-nodpi/x.png")
        found = self.found("drawable/x.xml")
        self.assertEqual([lvl for lvl, _, _ in found], ["WARNING"])
        self.assertIn("drawable-nodpi/x.png", found[0][1])

    def test_a_same_directory_pair_in_the_set_is_still_an_error(self):
        self.put("drawable/x.xml", "drawable-hdpi/x.png", "drawable-hdpi/x.webp", "drawable-xhdpi/x.png")
        found = self.found("drawable/x.xml")
        self.assertEqual([lvl for lvl, _, _ in found], ["ERROR"])
        self.assertIn("jui wrote drawable/x.xml, neither of these; keep one", found[0][1])


class OnlyWhatJuiWroteIsLookedAt(_Res):
    def test_alone_other_names_and_dotted_names(self):
        self.put("drawable/x.xml", "drawable-nodpi/y.png", "drawable-nodpi/xy.png", "drawable/x_dark.xml")
        self.assertEqual(self.found("drawable/x.xml"), [])

    def test_a_nine_patch_has_its_resource_name(self):
        self.put("drawable-nodpi/x.png", "drawable-nodpi/x.9.png")
        [(level, _, _)] = self.found("drawable-nodpi/x.png")
        self.assertEqual(level, "ERROR")

    def test_hidden_files_and_other_resource_types_are_not_drawables(self):
        self.put("drawable/x.xml", "drawable/.x.png", "mipmap-hdpi/x.png", "values/x.xml")
        self.assertEqual(self.found("drawable/x.xml"), [])

    def test_no_res_directory(self):
        self.assertEqual(same_name_drawables(self.res / "absent", {"x": ("x.svg", self.res / "drawable/x.xml")}), [])


class TheBuildSaysItAndExitsOne(unittest.TestCase):
    """`_distribute_images` end to end, the first build with no record."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "docs/screens/layouts/Resources").mkdir(parents=True)
        (self.root / "docs/screens/images").mkdir(parents=True)
        self.res = self.root / "android/app/src/main/res"
        self.platforms = {"android": {"root": "android", "layoutsDir": "app/src/main/assets/Layouts"}}
        (self.root / "jui.config.json").write_text(json.dumps({
            "layouts_directory": "docs/screens/layouts", "images_directory": "docs/screens/images",
            "platforms": self.platforms}))
        self._cwd = os.getcwd()
        os.chdir(self.root)
        self.ledger = self.root / "stage-failures.json"
        self._env = os.environ.get("JUI_STAGE_FAILURES")
        os.environ["JUI_STAGE_FAILURES"] = str(self.ledger)

    def tearDown(self):
        os.chdir(self._cwd)
        if self._env is None:
            os.environ.pop("JUI_STAGE_FAILURES", None)
        else:
            os.environ["JUI_STAGE_FAILURES"] = self._env
        self._tmp.cleanup()

    def build(self, text: str) -> str:
        (self.root / "docs/screens/images/ic.svg").write_text(text)
        cm = ConfigManager(self.root / "jui.config.json")
        args = argparse.Namespace(ios_only=False, android_only=False, web_only=False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertTrue(build_cmd._distribute_images(cm, cm.load(), self.platforms, args))
        return buf.getvalue()

    def earlier(self, rel: str):
        p = self.res / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"from 2.5.22")

    def test_bars_shape_is_an_error_a_stage_and_exit_1(self):
        self.earlier("drawable-nodpi/ic.jpg")
        out = self.build(PNG_WHOLE)
        self.assertIn("ERROR: ic.svg: Android: drawable-nodpi/ic.jpg and drawable-nodpi/ic.png are one resource", out)
        self.assertTrue((self.res / "drawable-nodpi/ic.jpg").exists())
        entries = build_cmd._stage_failures(self.ledger)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["stage"], "images: android")
        self.assertIn("remove drawable-nodpi/ic.jpg", entries[0]["message"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(build_cmd._exit_for_incomplete(entries, argparse.Namespace()), 1)

    def test_a_vector_left_beside_a_picture_is_a_warning_and_no_stage(self):
        self.earlier("drawable/ic.xml")
        out = self.build(PNG_WHOLE)
        self.assertIn("WARNING: ic.svg: Android: drawable/ic.xml has the name of drawable-nodpi/ic.png", out)
        self.assertIn("160 dpi and below", out)
        self.assertEqual(build_cmd._stage_failures(self.ledger), [])

    def test_with_the_record_the_old_file_is_removed_and_nothing_is_said(self):
        self.build(JPEG_WHOLE)
        out = self.build(PNG_WHOLE)
        self.assertEqual(sorted(p.name for p in self.res.rglob("ic.*")), ["ic.png"])
        self.assertNotIn("ERROR", out)
        self.assertNotIn("WARNING", out)
        self.assertEqual(build_cmd._stage_failures(self.ledger), [])

    def test_a_clean_build_says_nothing(self):
        out = self.build(VECTOR)
        self.assertNotIn("ERROR", out)
        self.assertNotIn("WARNING", out)

    def test_without_the_ledger_only_the_line_says_it(self):
        os.environ.pop("JUI_STAGE_FAILURES", None)
        self.earlier("drawable-nodpi/ic.jpg")
        out = self.build(PNG_WHOLE)
        self.assertIn("ERROR: ic.svg", out)
        self.assertFalse(self.ledger.exists())


if __name__ == "__main__":
    unittest.main()
