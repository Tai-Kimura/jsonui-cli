"""An iOS image asset converted from the same SVG is the same PDF, and is left alone.

Through 1.8.111 both converters stamped the wall clock into the PDF's
/CreationDate, so `jui build --clean` rewrote every iOS image asset on every
run with different bytes — 123 files on one face, identical but for that
date (jui-build-rewrites-ios-pdf-assets-with-a-fresh-creation-date-every-run).

The date is now pinned (SOURCE_DATE_EPOCH when set, else the epoch), and a
conversion replaces the asset only when the bytes differ, so an unchanged SVG
leaves both the PDF and its Contents.json untouched — mtime included.

The arms that need a converter binary skip BY NAME when it is absent (the CI
image has neither rsvg-convert nor, usually, cairosvg); the pin and the
replace-only-if-different rule are covered without one.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import time
import unittest
import zlib
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jui_cli.core import image_converter as ic  # noqa: E402

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
       '<rect width="10" height="10" fill="#c00"/></svg>')


def _creation_dates(pdf: bytes) -> set:
    chunks = [pdf]
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S):
        try:
            chunks.append(zlib.decompress(m.group(1)))
        except zlib.error:
            pass
    return set(re.findall(rb"/CreationDate\s*\(([^)]*)\)", b"\n".join(chunks)))


def _has_cairosvg() -> bool:
    try:
        import cairocffi  # noqa: F401
        import cairosvg  # noqa: F401
    except (ImportError, OSError):
        return False
    return True


class _Workspace(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.svg = self.dir / "icon.svg"
        self.svg.write_text(SVG, encoding="utf-8")
        self.xcassets = self.dir / "Assets.xcassets"
        self._env = mock.patch.dict(os.environ)
        self._env.start()
        os.environ.pop("SOURCE_DATE_EPOCH", None)

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def convert(self):
        return ic.ImageConverter.convert_ios(self.svg, self.xcassets)


class TheCreationDateIsPinned(_Workspace):
    def test_the_epoch_when_nothing_is_set(self):
        self.assertEqual(0, ic._pdf_creation_epoch())

    def test_source_date_epoch_when_it_is(self):
        os.environ["SOURCE_DATE_EPOCH"] = "1700000000"
        self.assertEqual(1700000000, ic._pdf_creation_epoch())

    def test_an_invalid_pin_falls_back_to_the_epoch_not_the_clock(self):
        os.environ["SOURCE_DATE_EPOCH"] = "yesterday"
        self.assertEqual(0, ic._pdf_creation_epoch())


class AnUnchangedAssetIsLeftAlone(_Workspace):
    """With a converter that emits fixed bytes — no binary needed."""

    def _fake(self, payload):
        def convert(svg_path, pdf_path, epoch):
            pdf_path.write_bytes(payload)
            return True
        return mock.patch.object(ic, "_convert_svg_to_pdf", side_effect=convert)

    def test_same_bytes_keep_the_pdf_and_contents_json_mtime(self):
        with self._fake(b"%PDF-same"):
            imageset = self.convert()
            pdf, contents = imageset / "icon.pdf", imageset / "Contents.json"
            before = (pdf.stat().st_mtime_ns, contents.stat().st_mtime_ns)
            time.sleep(0.02)
            self.convert()
        self.assertEqual(before, (pdf.stat().st_mtime_ns, contents.stat().st_mtime_ns))
        self.assertEqual(b"%PDF-same", pdf.read_bytes())

    def test_different_bytes_replace_the_pdf(self):
        with self._fake(b"%PDF-one"):
            imageset = self.convert()
        with self._fake(b"%PDF-two"):
            self.convert()
        self.assertEqual(b"%PDF-two", (imageset / "icon.pdf").read_bytes())

    def test_a_failed_conversion_leaves_no_scratch_file_and_no_asset(self):
        with mock.patch.object(ic, "_convert_svg_to_pdf", return_value=False), \
                mock.patch("builtins.print"):
            self.assertIsNone(self.convert())
        imageset = self.xcassets / "icon.imageset"
        self.assertEqual([], [p.name for p in imageset.iterdir()])


@unittest.skipUnless(shutil.which("rsvg-convert"), "rsvg-convert not on PATH (brew install librsvg)")
class RsvgConvertRoute(_Workspace):
    def test_two_conversions_a_second_apart_are_identical(self):
        pdf = self.convert() / "icon.pdf"
        first = pdf.read_bytes()
        pdf.unlink()
        time.sleep(1.1)
        self.convert()
        self.assertEqual(first, pdf.read_bytes())
        self.assertEqual({b"19700101000000+00'00'"},
                         {d.lstrip(b"D:") for d in _creation_dates(first)})


@unittest.skipUnless(_has_cairosvg(), "cairosvg / cairocffi not importable (pip install cairosvg)")
class CairosvgRoute(_Workspace):
    """rsvg-convert made unavailable, so the fallback converts."""

    def setUp(self):
        super().setUp()
        real_run = ic.subprocess.run

        def no_rsvg(cmd, *args, **kwargs):
            if cmd and cmd[0] == "rsvg-convert":
                raise FileNotFoundError(cmd[0])
            return real_run(cmd, *args, **kwargs)
        self._no_rsvg = mock.patch.object(ic.subprocess, "run", side_effect=no_rsvg)
        self._no_rsvg.start()

    def tearDown(self):
        self._no_rsvg.stop()
        super().tearDown()

    def test_two_conversions_a_second_apart_are_identical(self):
        pdf = self.convert() / "icon.pdf"
        first = pdf.read_bytes()
        pdf.unlink()
        time.sleep(1.1)
        self.convert()
        self.assertEqual(first, pdf.read_bytes())

    def test_source_date_epoch_reaches_the_pdf(self):
        os.environ["SOURCE_DATE_EPOCH"] = "1700000000"
        pdf = self.convert() / "icon.pdf"
        dates = {d.lstrip(b"D:") for d in _creation_dates(pdf.read_bytes())}
        self.assertTrue(any(d.startswith(b"20231114221320") for d in dates), dates)


if __name__ == "__main__":
    unittest.main()
