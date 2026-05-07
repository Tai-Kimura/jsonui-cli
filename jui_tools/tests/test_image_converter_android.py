"""Tests for `ImageConverter.convert_android`'s vector + raster-fallback paths.

Focus on the raster-only SVG case (AI-generated illustrations that just wrap
a `<image href="data:image/png;base64,…">` tag) — the original implementation
silently dropped those, producing invalid `painterResource(R.drawable.x)`
references on Android.
"""
from __future__ import annotations

import base64
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from jui_cli.core.image_converter import ImageConverter


def _minimal_png_bytes() -> bytes:
    """Build a valid 1x1 grey PNG. Tiny but real enough for byte assertions."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        length = struct.pack(">I", len(data))
        crc = struct.pack(">I", zlib.crc32(tag + data))
        return length + tag + data + crc

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
    raw = b"\x00\xff"  # filter byte + one grey pixel
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return signature + ihdr + idat + iend


def _write_svg(path: Path, body: str) -> None:
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="0 0 24 24" width="24" height="24">{body}</svg>',
        encoding="utf-8",
    )


class ConvertAndroidTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.drawable_dir = self.root / "drawable"

    def tearDown(self):
        self._tmp.cleanup()

    # ---- vector path ---------------------------------------------------- #

    def test_vector_svg_produces_xml_in_drawable(self):
        svg = self.root / "ic_check.svg"
        _write_svg(svg, '<path d="M0 0 L24 24" fill="#000000"/>')

        out = ImageConverter.convert_android(svg, self.drawable_dir)

        self.assertIsNotNone(out)
        self.assertEqual(out.name, "ic_check.xml")
        self.assertEqual(out.parent, self.drawable_dir)
        self.assertIn("<vector", out.read_text())

    # ---- raster fallback ------------------------------------------------ #

    def test_raster_png_svg_emits_drawable_nodpi_png(self):
        png_bytes = _minimal_png_bytes()
        b64 = base64.b64encode(png_bytes).decode("ascii")
        svg = self.root / "ic_taste_fruity.svg"
        _write_svg(svg, f'<image href="data:image/png;base64,{b64}"/>')

        out = ImageConverter.convert_android(svg, self.drawable_dir)

        self.assertIsNotNone(out)
        self.assertEqual(out.parent.name, "drawable-nodpi")
        self.assertEqual(out.name, "ic_taste_fruity.png")
        self.assertEqual(out.read_bytes(), png_bytes)

    def test_raster_png_svg_uses_xlink_href_attribute(self):
        # Inkscape/Illustrator typically write xlink:href instead of href.
        png_bytes = _minimal_png_bytes()
        b64 = base64.b64encode(png_bytes).decode("ascii")
        svg = self.root / "ic_taste_malty.svg"
        _write_svg(
            svg,
            f'<image xlink:href="data:image/png;base64,{b64}"/>',
        )

        out = ImageConverter.convert_android(svg, self.drawable_dir)
        self.assertIsNotNone(out)
        self.assertEqual(out.suffix, ".png")
        self.assertEqual(out.read_bytes(), png_bytes)

    def test_raster_jpeg_svg_emits_jpg_extension(self):
        # JPEG data URIs are also common — treat them the same as PNG.
        fake_jpeg = b"\xff\xd8\xff\xe0fake-jpeg"
        b64 = base64.b64encode(fake_jpeg).decode("ascii")
        svg = self.root / "ic_photo.svg"
        _write_svg(svg, f'<image href="data:image/jpeg;base64,{b64}"/>')

        out = ImageConverter.convert_android(svg, self.drawable_dir)
        self.assertIsNotNone(out)
        self.assertEqual(out.suffix, ".jpg")
        self.assertEqual(out.read_bytes(), fake_jpeg)

    def test_kebab_case_filename_becomes_snake_case(self):
        png_bytes = _minimal_png_bytes()
        b64 = base64.b64encode(png_bytes).decode("ascii")
        svg = self.root / "ic-taste-fruity.svg"
        _write_svg(svg, f'<image href="data:image/png;base64,{b64}"/>')

        out = ImageConverter.convert_android(svg, self.drawable_dir)
        self.assertIsNotNone(out)
        self.assertEqual(out.name, "ic_taste_fruity.png")

    # ---- guard: legitimately empty SVGs still return None -------------- #

    def test_empty_svg_without_image_still_returns_none(self):
        svg = self.root / "blank.svg"
        _write_svg(svg, "")
        self.assertIsNone(
            ImageConverter.convert_android(svg, self.drawable_dir)
        )


if __name__ == "__main__":
    unittest.main()
