"""Android draws an SVG's pictures, and a build removes only its own stale image files.

Ticket jui-android-svg-image-dropped-silently (2026-11-10): Android's
drawable lost a picture that iOS (PDF) and the web (the SVG itself) draw: a
WebP data URI wrote nothing, shapes over a picture became a vector without
it, two pictures kept the first, a moved or transformed picture was written
whole. Now:
- one PNG/JPEG/WebP filling the canvas is written as it is,
  drawable-nodpi/<name>.<ext>;
- every other SVG with a picture is drawn as a PNG three times its size,
  drawable-xxhdpi/<name>.png (rsvg-convert, then cairosvg), so it keeps its
  size in dp; without a converter it is what it was, with a WARNING;
- an <image> whose href points outside the SVG is a WARNING on all three
  platforms, saying what each does (output unchanged).

A PNG is handled as the iOS PDF is: the same converter gives the same bytes,
an unchanged drawing leaves the file (and its mtime) alone, the scratch file
is replaced only when the bytes differ, and the PNG carries no date or text
chunk. Two converters, or two rsvg-convert versions, give different bytes
(measured 2026-11-10), as with the PDFs.

Ticket jui-ios-imageset-stale-removal-deletes-unowned-1x (2026-11-10): the
2.5.22 removal of "the other form's file" went by name, taking a project's
own x.png from an imageset (and leaving its x@2x.png / x@3x.png), a project's
x.jpg from an Xcode-made set, and a project's drawable-nodpi/x.png or
drawable/x.xml on Android. Now iOS removes only what jui's own Contents.json
named, and says when it overwrites a Contents.json jui did not write;
Android removes only what `.jsonui-cli/image-outputs.json` records jui wrote
(no record: nothing).
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import io
import json
import os
import shutil
import struct
import sys
import tempfile
import time
import unittest
import zlib
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jui_cli.commands import build_cmd  # noqa: E402
from jui_cli.core import image_converter as ic  # noqa: E402
from jui_cli.core.config_manager import ConfigManager  # noqa: E402
from jui_cli.core.image_converter import ImageConverter, ImageOutputs  # noqa: E402


def _png(width: int, height: int, rgb=(200, 10, 10)) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _jpeg(width: int, height: int) -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof0 = b"\xff\xc0" + struct.pack(">HBHHB", 17, 8, height, width, 3) + b"\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    return b"\xff\xd8" + app0 + sof0 + b"\xff\xda\xff\xd9"


WEBP = b"RIFF\x1a\x00\x00\x00WEBPVP8L\x0d\x00\x00\x00\x2f\x00\x00\x00\x10\x07\x10\x11\x11\x88\x88\xfe\x07\x00"


def _uri(mime: str, data: bytes) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def _image(href: str, w=24, h=24, x=0, y=0, extra="") -> str:
    return f'<image href="{href}" x="{x}" y="{y}" width="{w}" height="{h}"{extra}/>'


def _svg(body: str, w=24, h=24) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'viewBox="0 0 {w} {h}" width="{w}" height="{h}">{body}</svg>')


PATH = '<path d="M2 2 L22 2 L12 22 Z" fill="#00f"/>'
VECTOR = _svg(PATH)
JPEG_WHOLE = _svg(_image(_uri("image/jpeg", _jpeg(72, 72))))
STUB_PNG = b"\x89PNG\r\n\x1a\nstub"


def _stub_png(svg_path: Path, png_path: Path, zoom: int = 3) -> bool:
    png_path.write_bytes(STUB_PNG + svg_path.name.encode())
    return True


class _Tmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.src = self.root / "src"
        self.src.mkdir()
        self.res = self.root / "app/res"
        self.drawable = self.res / "drawable"
        self.xcassets = self.root / "Assets.xcassets"

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name: str, text: str) -> Path:
        path = self.src / f"{name}.svg"
        path.write_text(text, encoding="utf-8")
        return path

    def android(self, svg: Path, outputs=None):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = ImageConverter.convert_android(svg, self.drawable, None, outputs)
        return out, [l.strip() for l in buf.getvalue().splitlines() if "WARNING" in l]

    def files(self, stem: str):
        return sorted(str(p.relative_to(self.res)) for p in self.res.rglob(f"{stem}.*"))


class AndroidDrawsThePicture(_Tmp):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(ic, "_svg_to_png", side_effect=_stub_png)
        self.png = patcher.start()
        self.addCleanup(patcher.stop)

    def assertDrawnAsPng(self, name: str, text: str):
        out, warnings = self.android(self.write(name, text))
        self.assertEqual(out, self.res / "drawable-xxhdpi" / f"{name}.png")
        self.assertTrue(out.read_bytes().startswith(STUB_PNG))
        self.assertEqual(warnings, [])
        self.assertEqual(self.files(name), [f"drawable-xxhdpi/{name}.png"])

    def test_a_webp_filling_the_canvas_is_written_as_it_is(self):
        out, warnings = self.android(self.write("w", _svg(_image(_uri("image/webp", WEBP)))))
        self.assertEqual(out, self.res / "drawable-nodpi" / "w.webp")
        self.assertEqual(out.read_bytes(), WEBP)
        self.assertEqual(warnings, [])
        self.png.assert_not_called()

    def test_a_png_or_jpeg_filling_the_canvas_is_written_as_it_is(self):
        data = _png(3, 3)
        out, warnings = self.android(self.write("p", _svg(_image(_uri("image/png", data)))))
        self.assertEqual((out.parent.name, out.read_bytes()), ("drawable-nodpi", data))
        out, _ = self.android(self.write("j", JPEG_WHOLE))
        self.assertEqual(out.parent.name, "drawable-nodpi")
        self.png.assert_not_called()

    def test_shapes_over_a_picture(self):
        self.assertDrawnAsPng("mixed", _svg(_image(_uri("image/jpeg", _jpeg(72, 72))) + PATH))

    def test_shapes_over_a_webp(self):
        self.assertDrawnAsPng("wmixed", _svg(_image(_uri("image/webp", WEBP)) + PATH))

    def test_two_pictures(self):
        body = _image(_uri("image/jpeg", _jpeg(36, 72)), w=12) + _image(_uri("image/png", _png(36, 72)), w=12, x=12)
        self.assertDrawnAsPng("two", _svg(body))

    def test_a_moved_resized_unsized_or_transformed_picture(self):
        uri = _uri("image/jpeg", _jpeg(72, 72))
        self.assertDrawnAsPng("moved", _svg(_image(uri, x=4)))
        self.assertDrawnAsPng("small", _svg(_image(uri, w=12, h=12)))
        self.assertDrawnAsPng("unsized", _svg(f'<image href="{uri}"/>'))
        self.assertDrawnAsPng("turned", _svg(f'<g transform="rotate(5)">{_image(uri)}</g>'))

    def test_a_vector_stays_a_vector(self):
        out, warnings = self.android(self.write("v", VECTOR))
        self.assertEqual(out, self.drawable / "v.xml")
        self.png.assert_not_called()

    def test_only_an_external_picture_writes_nothing_and_says_so(self):
        out, warnings = self.android(self.write("ext", _svg(_image("side.png"))))
        self.assertIsNone(out)
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn("ext.svg: Android: an <image> href is a file (side.png)", warnings[0])
        self.assertIn("nothing is written", warnings[0])
        self.png.assert_not_called()

    def test_an_external_picture_beside_shapes_is_in_the_png_and_said(self):
        out, warnings = self.android(self.write("extm", _svg(_image("side.png") + PATH)))
        self.assertEqual(out.parent.name, "drawable-xxhdpi")
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn("in the PNG only through rsvg-convert", warnings[0])


class WithoutAConverter(_Tmp):
    """No rsvg-convert, no cairosvg: the drawable it always was, and the loss said."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(ic, "_svg_to_png", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def assertFallback(self, name, text, words, where):
        out, warnings = self.android(self.write(name, text))
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn(words, warnings[0])
        self.assertIn("neither rsvg-convert nor cairosvg", warnings[0])
        self.assertEqual(out.parent.name if out else None, where)
        self.assertFalse((self.res / "drawable-xxhdpi").exists())

    def test_shapes_over_a_picture_draw_the_shapes(self):
        self.assertFallback("m", _svg(_image(_uri("image/jpeg", _jpeg(72, 72))) + PATH), "1 <image> dropped", "drawable")

    def test_two_pictures_keep_the_first(self):
        body = _image(_uri("image/jpeg", _jpeg(36, 72)), w=12) + _image(_uri("image/png", _png(36, 72)), w=12, x=12)
        self.assertFallback("t", _svg(body), "first PNG/JPEG of 2", "drawable-nodpi")

    def test_a_moved_picture_is_written_whole(self):
        self.assertFallback("o", _svg(_image(_uri("image/jpeg", _jpeg(72, 72)), x=3)), "not kept", "drawable-nodpi")


class ExternalHrefsAreSaidOnEveryPlatform(_Tmp):
    def setUp(self):
        super().setUp()
        for target in ("_svg_to_pdf", "_svg_to_png"):
            patcher = mock.patch.object(ic, target, side_effect=lambda s, d, *a: d.write_bytes(b"x") or True)
            patcher.start()
            self.addCleanup(patcher.stop)

    def warnings(self, svg: Path):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ImageConverter.convert_ios(svg, self.xcassets)
            ImageConverter.convert_android(svg, self.drawable)
            ImageConverter.convert_web(svg, self.root / "web")
        return [l.strip() for l in buf.getvalue().splitlines() if "WARNING" in l]

    def test_a_url(self):
        lines = self.warnings(self.write("u", _svg(_image("https://example.com/a.jpg"))))
        self.assertEqual([l.split(": ")[2] for l in lines], ["iOS", "Android", "web"])
        for line in lines:
            self.assertIn("is a URL (https://example.com/a.jpg), which no platform fetches", line)
            self.assertIn("embed it as a data URI", line)

    def test_a_file_beside_the_svg(self):
        ios, android, web = self.warnings(self.write("f", _svg('<image xlink:href="pics/side.png" width="24" height="24"/>')))
        self.assertIn("iOS: an <image> href is a file (pics/side.png): rsvg-convert draws it", ios)
        self.assertIn("cairosvg (used where rsvg-convert is missing, as on a Linux CI) leaves it blank", ios)
        self.assertIn("Android: an <image> href is a file", android)
        self.assertIn("web: an <image> href is a file", web)
        self.assertIn("loads no external file", web)

    def test_embedded_pictures_and_plain_vectors_say_nothing(self):
        self.assertEqual(self.warnings(self.write("e", JPEG_WHOLE)), [])
        self.assertEqual(self.warnings(self.write("v", VECTOR)), [])


class PngIsHandledAsThePdfIs(_Tmp):
    def test_an_unchanged_drawing_leaves_the_file_and_its_mtime(self):
        svg = self.write("m", _svg(_image(_uri("image/jpeg", _jpeg(72, 72))) + PATH))
        with mock.patch.object(ic, "_convert_svg_to_png", side_effect=lambda s, d, z: d.write_bytes(b"same") or True):
            out, _ = self.android(svg)
            past = time.time() - 100
            os.utime(out, (past, past))
            self.android(svg)
        self.assertEqual(out.stat().st_mtime, past)

    def test_different_bytes_replace_it_and_no_scratch_is_left(self):
        svg = self.write("m", _svg(_image(_uri("image/jpeg", _jpeg(72, 72))) + PATH))
        with mock.patch.object(ic, "_convert_svg_to_png", side_effect=lambda s, d, z: d.write_bytes(b"one") or True):
            out, _ = self.android(svg)
        with mock.patch.object(ic, "_convert_svg_to_png", side_effect=lambda s, d, z: d.write_bytes(b"two") or True):
            self.android(svg)
        self.assertEqual(out.read_bytes(), b"two")
        self.assertEqual(sorted(p.name for p in out.parent.iterdir()), ["m.png"])

    def test_a_failed_drawing_leaves_no_scratch_and_no_png(self):
        svg = self.write("m", _svg(_image(_uri("image/jpeg", _jpeg(72, 72))) + PATH))
        with mock.patch.object(ic, "_convert_svg_to_png", return_value=False):
            self.android(svg)
        self.assertFalse((self.res / "drawable-xxhdpi").exists())


def _chunks(png: bytes) -> list[bytes]:
    out, i = [], 8
    while i + 8 <= len(png):
        length = struct.unpack(">I", png[i:i + 4])[0]
        out.append(png[i + 4:i + 8])
        i += 12 + length
    return out


def _has_cairosvg() -> bool:
    try:
        import cairosvg  # noqa: F401
    except (ImportError, OSError):
        return False
    return True


class _RealConverter(_Tmp):
    """The arms a converter binary is needed for skip BY NAME when it is absent."""

    def draw_twice(self):
        svg = self.write("m", _svg(_image(_uri("image/png", _png(72, 72))) + PATH))
        a, b = self.root / "a.png", self.root / "b.png"
        self.assertTrue(ic._convert_svg_to_png(svg, a, 3))
        self.assertTrue(ic._convert_svg_to_png(svg, b, 3))
        return a.read_bytes(), b.read_bytes()

    def assertSameAndUndated(self):
        a, b = self.draw_twice()
        self.assertEqual(a, b)
        self.assertEqual(struct.unpack(">II", a[16:24]), (72, 72))
        self.assertFalse({b"tIME", b"tEXt", b"iTXt", b"zTXt"} & set(_chunks(a)), _chunks(a))


@unittest.skipUnless(shutil.which("rsvg-convert"), "rsvg-convert not on PATH (brew install librsvg)")
class RsvgPng(_RealConverter):
    def test_the_same_bytes_twice_and_no_date_or_text(self):
        self.assertSameAndUndated()


@unittest.skipUnless(_has_cairosvg(), "cairosvg not importable (pip install cairosvg, and libcairo)")
class CairosvgPng(_RealConverter):
    def setUp(self):
        super().setUp()
        real = ic.subprocess.run

        def no_rsvg(cmd, *a, **k):
            if cmd and cmd[0] == "rsvg-convert":
                raise FileNotFoundError(cmd[0])
            return real(cmd, *a, **k)
        patcher = mock.patch.object(ic.subprocess, "run", side_effect=no_rsvg)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_same_bytes_twice_and_no_date_or_text(self):
        self.assertSameAndUndated()


class IosRemovesOnlyWhatItsOwnContentsNamed(_Tmp):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(ic, "_svg_to_pdf", side_effect=lambda s, d: d.write_bytes(b"%PDF") or True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_set(self, author: str, named: list, files: list) -> Path:
        s = self.xcassets / "x.imageset"
        s.mkdir(parents=True)
        (s / "Contents.json").write_text(json.dumps({
            "images": [{"filename": f, "idiom": "universal"} for f in named], "info": {"author": author, "version": 1}}))
        for f in files:
            (s / f).write_bytes(b"project")
        return s

    def ios(self, text: str):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = ImageConverter.convert_ios(self.write("x", text), self.xcassets)
        return out, sorted(p.name for p in out.iterdir()), [l.strip() for l in buf.getvalue().splitlines() if "WARNING" in l]

    def test_files_its_contents_did_not_name_stay(self):
        # the reported shape: a jui set naming the PDF, the project's three PNGs beside it
        self.make_set("jui", ["x.pdf"], ["x.pdf", "x.png", "x@2x.png", "x@3x.png"])
        _, files, warnings = self.ios(VECTOR)
        self.assertEqual(files, ["Contents.json", "x.pdf", "x.png", "x@2x.png", "x@3x.png"])
        self.assertEqual(warnings, [])

    def test_the_file_its_contents_named_goes_when_the_form_changes(self):
        self.make_set("jui", ["x.pdf"], ["x.pdf", "x@2x.png"])
        _, files, _ = self.ios(JPEG_WHOLE)
        self.assertEqual(files, ["Contents.json", "x.jpg", "x@2x.png"])
        _, files, _ = self.ios(VECTOR)
        self.assertEqual(files, ["Contents.json", "x.pdf", "x@2x.png"])

    def test_an_xcode_made_set_keeps_its_files_and_the_overwrite_is_said(self):
        self.make_set("xcode", ["x.jpg"], ["x.jpg"])
        out, files, warnings = self.ios(VECTOR)
        self.assertEqual(files, ["Contents.json", "x.jpg", "x.pdf"])
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn("x.svg: iOS overwrote x.imageset/Contents.json, whose author is 'xcode', not jui", warnings[0])
        self.assertEqual(json.loads((out / "Contents.json").read_text())["info"]["author"], "jui")

    def test_an_unreadable_contents_is_said_and_nothing_is_removed(self):
        s = self.xcassets / "x.imageset"
        s.mkdir(parents=True)
        (s / "Contents.json").write_text("{not json")
        (s / "x.png").write_bytes(b"project")
        _, files, warnings = self.ios(VECTOR)
        self.assertEqual(files, ["Contents.json", "x.pdf", "x.png"])
        self.assertIn("'(unreadable)'", warnings[0])

    def test_a_name_outside_the_set_is_not_followed(self):
        outside = self.xcassets / "keep.pdf"
        self.xcassets.mkdir(parents=True)
        outside.write_bytes(b"project")
        self.make_set("jui", ["../keep.pdf"], [])
        self.ios(JPEG_WHOLE)
        self.assertTrue(outside.exists())

    def test_a_first_build_writes_no_warning(self):
        _, files, warnings = self.ios(VECTOR)
        self.assertEqual((files, warnings), (["Contents.json", "x.pdf"], []))


class AndroidRemovesOnlyWhatItRecorded(_Tmp):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(ic, "_svg_to_png", side_effect=_stub_png)
        patcher.start()
        self.addCleanup(patcher.stop)

    def build(self, name: str, text: str, outputs: ImageOutputs | None = None):
        outputs = outputs or ImageOutputs.load(self.root)
        svg = self.src / f"{name}.svg"
        svg.write_text(text, encoding="utf-8")
        out, _ = self.android(svg, outputs)
        outputs.save(["android"])
        return out

    def record(self):
        return json.loads(ImageOutputs.path_for(self.root).read_text())

    def test_without_a_record_nothing_is_removed_and_the_record_is_made(self):
        (self.res / "drawable-nodpi").mkdir(parents=True)
        (self.res / "drawable-nodpi/x.jpg").write_bytes(b"left by 2.5.22 or the project")
        self.build("x", VECTOR)
        self.assertEqual(self.files("x"), ["drawable-nodpi/x.jpg", "drawable/x.xml"])
        self.assertEqual(self.record()["platforms"], {"android": {"x": ["app/res/drawable/x.xml"]}})

    def test_vector_raster_drawn_vector(self):
        self.build("x", VECTOR)
        self.build("x", JPEG_WHOLE)
        self.assertEqual(self.files("x"), ["drawable-nodpi/x.jpg"])
        self.build("x", _svg(_image(_uri("image/jpeg", _jpeg(72, 72))) + PATH))
        self.assertEqual(self.files("x"), ["drawable-xxhdpi/x.png"])
        self.build("x", _svg(_image(_uri("image/webp", WEBP))))
        self.assertEqual(self.files("x"), ["drawable-nodpi/x.webp"])
        self.build("x", VECTOR)
        self.assertEqual(self.files("x"), ["drawable/x.xml"])

    def test_the_projects_own_file_of_the_same_name_stays(self):
        self.build("x", VECTOR)
        (self.res / "drawable-nodpi").mkdir(parents=True)
        (self.res / "drawable-nodpi/x.png").write_bytes(b"project")
        self.build("x", JPEG_WHOLE)
        self.assertEqual(self.files("x"), ["drawable-nodpi/x.jpg", "drawable-nodpi/x.png"])

    def test_without_outputs_nothing_is_removed(self):
        svg = self.write("x", VECTOR)
        self.android(svg)
        svg.write_text(JPEG_WHOLE)
        self.android(svg)
        self.assertEqual(self.files("x"), ["drawable-nodpi/x.jpg", "drawable/x.xml"])

    def test_nothing_written_keeps_the_entry_for_a_later_build(self):
        self.build("x", VECTOR)
        self.build("x", _svg(_image("side.png")))      # writes nothing
        self.assertEqual(self.record()["platforms"]["android"], {"x": ["app/res/drawable/x.xml"]})
        self.build("x", JPEG_WHOLE)
        self.assertEqual(self.files("x"), ["drawable-nodpi/x.jpg"])

    def test_a_platform_not_built_keeps_its_section_and_an_unchanged_record_is_left(self):
        path = ImageOutputs.path_for(self.root)
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"platforms": {"other": {"y": ["y.bin"]}}}))
        self.build("x", VECTOR)
        self.assertEqual(self.record()["platforms"]["other"], {"y": ["y.bin"]})
        past = time.time() - 100
        os.utime(path, (past, past))
        self.build("x", VECTOR)
        self.assertEqual(path.stat().st_mtime, past)

    def test_an_unreadable_record_is_no_record(self):
        path = ImageOutputs.path_for(self.root)
        path.parent.mkdir(parents=True)
        path.write_text("{oops")
        self.assertIsNone(ImageOutputs.load(self.root).previous)


class TheBuildKeepsTheRecord(unittest.TestCase):
    """`_distribute_images` end to end, with converters that need no binary (vector, whole raster)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "docs/screens/layouts/Resources").mkdir(parents=True)
        (self.root / "docs/screens/images").mkdir(parents=True)
        (self.root / "android").mkdir()
        self.platforms = {"android": {"root": "android", "layoutsDir": "app/src/main/assets/Layouts"}}
        (self.root / "jui.config.json").write_text(json.dumps({
            "layouts_directory": "docs/screens/layouts", "images_directory": "docs/screens/images",
            "platforms": self.platforms}))
        self._cwd = os.getcwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def run_build(self, text: str, **only):
        (self.root / "docs/screens/images/ic.svg").write_text(text)
        cm = ConfigManager(self.root / "jui.config.json")
        args = argparse.Namespace(ios_only=False, android_only=False, web_only=False, **only)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(build_cmd._distribute_images(cm, cm.load(), self.platforms, args))

    def test_two_builds_switch_the_form_and_leave_one_file(self):
        res = self.root / "android/app/src/main/res"
        self.run_build(VECTOR)
        record = json.loads((self.root / ".jsonui-cli/image-outputs.json").read_text())
        self.assertEqual(record["platforms"], {"android": {"ic": ["android/app/src/main/res/drawable/ic.xml"]}})
        self.run_build(JPEG_WHOLE)
        self.assertEqual(sorted(str(p.relative_to(res)) for p in res.rglob("ic.*")), ["drawable-nodpi/ic.jpg"])


if __name__ == "__main__":
    unittest.main()
