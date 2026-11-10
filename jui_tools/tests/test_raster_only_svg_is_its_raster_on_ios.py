"""An SVG that is only one embedded PNG/JPEG goes into the iOS asset as that file.

Ticket jui-ios-raster-only-svg-inflates-as-pdf (2026-11-10): Android took the
embedded JPEG out as drawable-nodpi/<name>.jpg, while iOS always ran the SVG
through rsvg-convert, which re-encoded the JPEG into a PDF about 7x larger
(151,386 bytes -> 1,145,847, no DCTDecode left). Now iOS writes the PNG/JPEG
itself, with a raster Contents.json (no preserves-vector-representation) and
a scale that keeps the SVG's size in points, but only for the shape that
loses nothing: no shapes, one <image> at 0,0 filling the canvas, no
transform, PNG/JPEG data URI, pixels 1/2/3 times the canvas within a pixel.
Everything else stays the PDF it was.

The same build also:
- removes the other form's file when an SVG changes between vector and
  raster, on iOS ({name}.pdf / .jpg / .png in the set) and on Android
  (drawable/<name>.xml / drawable-nodpi/<name>.png|jpg), where both used to
  stay side by side;
- says so in a WARNING when Android's drawable loses an <image> (WebP, an
  external href, shapes over an image, two images, a moved or transformed
  image) instead of losing it silently. The output there is unchanged
  (ticket jui-android-svg-image-dropped-silently carries the real fix).

The PDF arms do not need a converter: `_svg_to_pdf` is replaced by a stub.
"""
from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import struct
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jui_cli.core import image_converter as ic  # noqa: E402
from jui_cli.core.image_converter import ImageConverter  # noqa: E402


def _jpeg(width: int, height: int, tag: bytes = b"") -> bytes:
    """A JPEG's header with the given size (SOF0), enough for the size reader and byte checks."""
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof0 = b"\xff\xc0" + struct.pack(">HBHHB", 17, 8, height, width, 3) + b"\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    return b"\xff\xd8" + app0 + sof0 + b"\xff\xda" + tag + b"\xff\xd9"


def _png(width: int, height: int) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr + b"\x00\x00\x00\x00"


def _uri(mime: str, data: bytes) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def _image(href: str, w, h, x=0, y=0, attr="href", extra=' preserveAspectRatio="none"') -> str:
    return f'<image {attr}="{href}" x="{x}" y="{y}" width="{w}" height="{h}"{extra}/>'


def _svg(w, h, body: str, viewbox: str | None = None) -> str:
    vb = viewbox if viewbox is not None else f"0 0 {w} {h}"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="{vb}" width="{w}" height="{h}">{body}</svg>'
    )


def _fake_pdf(svg_path: Path, pdf_path: Path) -> bool:
    pdf_path.write_bytes(b"%PDF-stub " + svg_path.name.encode())
    return True


VECTOR = _svg(24, 24, '<path d="M2 2 L22 2 L12 22 Z" fill="#f00"/>')


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.src = self.root / "src"
        self.src.mkdir()
        self.xcassets = self.root / "Assets.xcassets"
        self.drawable = self.root / "res" / "drawable"
        patcher = mock.patch.object(ic, "_svg_to_pdf", side_effect=_fake_pdf)
        self.pdf_stub = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name: str, text: str) -> Path:
        path = self.src / f"{name}.svg"
        path.write_text(text, encoding="utf-8")
        return path

    def ios(self, svg: Path, name: str | None = None):
        out = ImageConverter.convert_ios(svg, self.xcassets, name)
        self.assertIsNotNone(out)
        contents = json.loads((out / "Contents.json").read_text())
        files = sorted(p.name for p in out.iterdir() if p.name != "Contents.json")
        return out, contents, files


class IosTakesTheRaster(_Base):
    def assertRaster(self, svg: Path, data: bytes, ext: str, scale: str | None, name: str | None = None):
        stem = name or svg.stem
        out, contents, files = self.ios(svg, name)
        self.assertEqual(files, [f"{stem}.{ext}"])
        self.assertEqual((out / f"{stem}.{ext}").read_bytes(), data)
        image = {"filename": f"{stem}.{ext}", "idiom": "universal"}
        if scale:
            image["scale"] = scale
        self.assertEqual(contents["images"], [image])
        self.assertNotIn("preserves-vector-representation", contents["properties"])
        self.assertEqual(contents["properties"]["template-rendering-intent"], "original")
        self.pdf_stub.assert_not_called()

    def test_the_tickets_shape_840x1280_on_280x427_is_3x_one_pixel_short(self):
        data = _jpeg(840, 1280)
        svg = self.write("img_paper", _svg(280, 427, _image(_uri("image/jpeg", data), 280, 427)))
        self.assertRaster(svg, data, "jpg", "3x")

    def test_1024_on_a_1024_canvas_with_preserve_aspect_ratio_none_is_1x(self):
        data = _jpeg(1024, 1024)
        svg = self.write("photo_default", _svg(1024, 1024, _image(_uri("image/jpeg", data), 1024, 1024)))
        self.assertRaster(svg, data, "jpg", None)

    def test_1024_on_a_512_canvas_is_2x(self):
        data = _jpeg(1024, 1024)
        svg = self.write("b512", _svg(512, 512, _image(_uri("image/jpeg", data), 512, 512)))
        self.assertRaster(svg, data, "jpg", "2x")

    def test_1024_on_a_341_point_33_canvas_is_3x(self):
        data = _jpeg(1024, 1024)
        for size in ("341.33", "341.3333", "341.333333"):
            with self.subTest(size=size):
                svg = self.write("b341", _svg(size, size, _image(_uri("image/jpeg", data), size, size)))
                self.assertRaster(svg, data, "jpg", "3x")

    def test_a_png_by_xlink_href_without_preserve_aspect_ratio(self):
        data = _png(64, 64)
        svg = self.write("p", _svg(64, 64, _image(_uri("image/png", data), 64, 64, attr="xlink:href", extra="")))
        self.assertRaster(svg, data, "png", None)

    def test_a_jpg_mime_spelling(self):
        data = _jpeg(200, 100)
        svg = self.write("j", _svg(100, 50, _image(_uri("image/jpg", data), 100, 50)))
        self.assertRaster(svg, data, "jpg", "2x")

    def test_a_colour_modes_own_picture_keeps_its_name(self):
        data = _jpeg(96, 96)
        svg = self.write("hero.dark", _svg(32, 32, _image(_uri("image/jpeg", data), 32, 32)))
        self.assertRaster(svg, data, "jpg", "3x", name="hero__dark")

    def test_an_unchanged_raster_is_left_alone(self):
        data = _jpeg(96, 96)
        svg = self.write("same", _svg(32, 32, _image(_uri("image/jpeg", data), 32, 32)))
        out, _, _ = self.ios(svg)
        past = time.time() - 100
        for p in out.iterdir():
            os.utime(p, (past, past))
        self.ios(svg)
        for p in out.iterdir():
            self.assertEqual(p.stat().st_mtime, past, p.name)


class IosKeepsThePdf(_Base):
    """Shapes the raster would not carry whole stay the PDF they were."""

    def assertPdf(self, name: str, text: str):
        svg = self.write(name, text)
        out, contents, files = self.ios(svg)
        self.assertEqual(files, [f"{name}.pdf"])
        self.assertEqual(contents["images"], [{"filename": f"{name}.pdf", "idiom": "universal"}])
        self.assertIs(contents["properties"]["preserves-vector-representation"], True)

    def test_a_vector(self):
        self.assertPdf("vec", VECTOR)

    def test_webp(self):
        self.assertPdf("w", _svg(64, 64, _image(_uri("image/webp", b"RIFF....WEBPVP8 "), 64, 64)))

    def test_shapes_over_the_image(self):
        body = _image(_uri("image/jpeg", _jpeg(300, 300)), 100, 100) + '<path d="M0 0 L9 9" stroke="#000"/>'
        self.assertPdf("mixed", _svg(100, 100, body))

    def test_two_images(self):
        body = _image(_uri("image/jpeg", _jpeg(150, 300)), 50, 100) + _image(_uri("image/png", _png(150, 300)), 50, 100, x=50)
        self.assertPdf("two", _svg(100, 100, body))

    def test_an_external_href(self):
        self.assertPdf("ext", _svg(64, 64, _image("https://example.com/a.jpg", 64, 64)))
        self.assertPdf("rel", _svg(64, 64, _image("side.png", 64, 64)))

    def test_moved_resized_or_unsized(self):
        uri = _uri("image/jpeg", _jpeg(300, 300))
        self.assertPdf("moved", _svg(100, 100, _image(uri, 100, 100, x=10)))
        self.assertPdf("small", _svg(100, 100, _image(uri, 80, 80)))
        self.assertPdf("unsized", _svg(100, 100, f'<image href="{uri}"/>'))

    def test_a_transform_on_the_image_or_around_it(self):
        uri = _uri("image/jpeg", _jpeg(300, 300))
        self.assertPdf("t1", _svg(100, 100, f'<g transform="rotate(10 50 50)">{_image(uri, 100, 100)}</g>'))
        self.assertPdf("t2", _svg(100, 100, _image(uri, 100, 100, extra=' transform="scale(1)"')))

    def test_a_ratio_that_is_not_1_2_or_3(self):
        self.assertPdf("r25", _svg(100, 100, _image(_uri("image/jpeg", _jpeg(250, 250)), 100, 100)))
        self.assertPdf("r4", _svg(100, 100, _image(_uri("image/jpeg", _jpeg(400, 400)), 100, 100)))

    def test_more_than_a_pixel_off(self):
        self.assertPdf("off2", _svg(100, 100, _image(_uri("image/jpeg", _jpeg(302, 300)), 100, 100)))

    def test_different_scales_on_the_two_axes(self):
        self.assertPdf("aspect", _svg(100, 100, _image(_uri("image/jpeg", _jpeg(300, 200)), 100, 100)))

    def test_a_viewbox_that_disagrees_with_the_size(self):
        uri = _uri("image/jpeg", _jpeg(300, 300))
        self.assertPdf("vb", _svg(100, 100, _image(uri, 50, 50), viewbox="0 0 50 50"))
        self.assertPdf("vbo", _svg(100, 100, _image(uri, 100, 100), viewbox="10 0 100 100"))

    def test_bytes_that_are_not_the_named_format(self):
        self.assertPdf("liar", _svg(100, 100, _image(_uri("image/jpeg", _png(300, 300)), 100, 100)))


class TheOtherFormIsRemoved(_Base):
    def test_ios_vector_then_raster_then_vector(self):
        data = _jpeg(72, 72)
        raster = _svg(24, 24, _image(_uri("image/jpeg", data), 24, 24))
        svg = self.write("x", VECTOR)
        self.assertEqual(self.ios(svg)[2], ["x.pdf"])
        svg.write_text(raster)
        self.assertEqual(self.ios(svg)[2], ["x.jpg"])
        svg.write_text(_svg(24, 24, _image(_uri("image/png", _png(72, 72)), 24, 24)))
        self.assertEqual(self.ios(svg)[2], ["x.png"])
        svg.write_text(VECTOR)
        self.assertEqual(self.ios(svg)[2], ["x.pdf"])

    def test_ios_leaves_files_that_are_not_its_own(self):
        svg = self.write("x", VECTOR)
        out, _, _ = self.ios(svg)
        (out / "x@2x.png").write_bytes(b"hand")
        (out / "y.pdf").write_bytes(b"other")
        self.ios(svg)
        self.assertTrue((out / "x@2x.png").exists())
        self.assertTrue((out / "y.pdf").exists())

    def android_files(self, name: str):
        res = self.drawable.parent
        return sorted(str(p.relative_to(res)) for p in res.rglob(f"{name}.*"))

    def test_android_vector_then_raster_then_vector(self):
        svg = self.write("x-y", VECTOR)
        ImageConverter.convert_android(svg, self.drawable)
        self.assertEqual(self.android_files("x_y"), ["drawable/x_y.xml"])
        svg.write_text(_svg(24, 24, _image(_uri("image/jpeg", _jpeg(72, 72)), 24, 24)))
        ImageConverter.convert_android(svg, self.drawable)
        self.assertEqual(self.android_files("x_y"), ["drawable-nodpi/x_y.jpg"])
        svg.write_text(_svg(24, 24, _image(_uri("image/png", _png(72, 72)), 24, 24)))
        ImageConverter.convert_android(svg, self.drawable)
        self.assertEqual(self.android_files("x_y"), ["drawable-nodpi/x_y.png"])
        svg.write_text(VECTOR)
        ImageConverter.convert_android(svg, self.drawable)
        self.assertEqual(self.android_files("x_y"), ["drawable/x_y.xml"])

    def test_android_nothing_written_removes_nothing(self):
        svg = self.write("z", VECTOR)
        ImageConverter.convert_android(svg, self.drawable)
        svg.write_text(_svg(64, 64, _image("https://example.com/a.jpg", 64, 64)))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(ImageConverter.convert_android(svg, self.drawable))
        self.assertEqual(self.android_files("z"), ["drawable/z.xml"])


class AndroidSaysWhatItLoses(_Base):
    def android(self, name: str, text: str):
        svg = self.write(name, text)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = ImageConverter.convert_android(svg, self.drawable)
        return out, [l for l in buf.getvalue().splitlines() if "WARNING" in l]

    def assertWarns1(self, name: str, text: str, words: str):
        out, warnings = self.android(name, text)
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn(f"{name}.svg", warnings[0])
        self.assertIn(words, warnings[0])
        return out

    def test_webp_writes_nothing(self):
        out = self.assertWarns1("w", _svg(64, 64, _image(_uri("image/webp", b"RIFF"), 64, 64)), "image/webp")
        self.assertIsNone(out)

    def test_an_external_href_writes_nothing(self):
        out = self.assertWarns1("e", _svg(64, 64, _image("side.png", 64, 64)), "external file")
        self.assertIsNone(out)

    def test_shapes_over_an_image_drop_the_image(self):
        body = _image(_uri("image/jpeg", _jpeg(300, 300)), 100, 100) + '<path d="M0 0 L9 9" stroke="#000"/>'
        out = self.assertWarns1("m", _svg(100, 100, body), "1 <image> dropped")
        self.assertEqual(out.suffix, ".xml")

    def test_two_images_keep_the_first(self):
        first = _jpeg(150, 300, b"first")
        body = _image(_uri("image/jpeg", first), 50, 100) + _image(_uri("image/png", _png(150, 300)), 50, 100, x=50)
        out = self.assertWarns1("t", _svg(100, 100, body), "first PNG/JPEG of 2")
        self.assertEqual(out.read_bytes(), first)

    def test_a_moved_or_transformed_image_is_written_whole(self):
        uri = _uri("image/jpeg", _jpeg(300, 300))
        self.assertWarns1("o", _svg(100, 100, _image(uri, 80, 80, x=10, y=10)), "not kept")
        self.assertWarns1("g", _svg(100, 100, f'<g transform="rotate(5)">{_image(uri, 100, 100)}</g>'), "not kept")

    def test_no_warning_for_a_vector_or_a_whole_canvas_raster(self):
        self.assertEqual(self.android("v", VECTOR)[1], [])
        uri = _uri("image/jpeg", _jpeg(840, 1280))
        self.assertEqual(self.android("r", _svg(280, 427, _image(uri, 280, 427)))[1], [])
        # a ratio iOS keeps as a PDF loses nothing on Android: no warning
        self.assertEqual(self.android("q", _svg(100, 100, _image(_uri("image/jpeg", _jpeg(250, 250)), 100, 100)))[1], [])


class PixelSizeReader(unittest.TestCase):
    def test_png_and_jpeg(self):
        self.assertEqual(ic._raster_pixel_size("png", _png(7, 9)), (7, 9))
        self.assertEqual(ic._raster_pixel_size("jpg", _jpeg(840, 1280)), (840, 1280))

    def test_a_progressive_jpeg(self):
        data = _jpeg(30, 20).replace(b"\xff\xc0", b"\xff\xc2", 1)
        self.assertEqual(ic._raster_pixel_size("jpg", data), (30, 20))

    def test_garbage_is_none(self):
        self.assertIsNone(ic._raster_pixel_size("png", b"nope"))
        self.assertIsNone(ic._raster_pixel_size("jpg", b"\xff\xd8\x00"))
        self.assertIsNone(ic._raster_pixel_size("jpg", b""))


if __name__ == "__main__":
    unittest.main()
