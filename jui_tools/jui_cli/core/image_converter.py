"""Convert SVG images to platform-specific formats.

- iOS: Create .imageset in *.xcassets with PDF (preserves-vector-representation),
  or the PNG/JPEG itself when the SVG is only one embedded raster covering it
- Android: Convert SVG to Android Vector Drawable XML (or extract raster
  PNG/JPEG when the SVG only wraps a base64 data URI)
- Web: Copy SVG as-is to public/images/
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ImageConverter:
    """Convert SVG files to platform-specific image assets."""

    # ------------------------------------------------------------------ #
    #  iOS — .imageset with PDF
    # ------------------------------------------------------------------ #

    @staticmethod
    def convert_ios(
        svg_path: Path,
        xcassets_dir: Path,
        name: str | None = None,
    ) -> Path | None:
        """Create an .imageset inside *xcassets_dir* with a PDF converted from SVG.

        An SVG that is nothing but one embedded PNG/JPEG covering its canvas
        (`_whole_canvas_raster`) is written as that PNG/JPEG instead.

        Conversion priority:
        1. ``rsvg-convert`` (Homebrew: ``brew install librsvg``)
        2. ``cairosvg`` Python package (``pip install cairosvg``)

        *name* is the asset's name (default: the file's stem). A mode's own
        picture (``ic_star.dark.svg``) is written as ``ic_star__dark``.

        Returns the imageset directory path, or None on error.
        """
        name = name or svg_path.stem
        imageset_dir = xcassets_dir / f"{name}.imageset"
        imageset_dir.mkdir(parents=True, exist_ok=True)

        raster = _whole_canvas_raster(svg_path)
        if raster is not None:
            # A picture that is only one embedded PNG/JPEG goes in as that
            # file, as on Android: through rsvg-convert the JPEG came out
            # re-encoded and about 7x larger (151,386 bytes -> a 1,145,847
            # byte PDF; ticket jui-ios-raster-only-svg-inflates-as-pdf).
            ext, data, scale = raster
            filename = f"{name}.{ext}"
            _write_if_changed(imageset_dir / filename, data)
            image: dict[str, Any] = {"filename": filename, "idiom": "universal"}
            if scale > 1:
                # pixels / canvas, so the asset keeps the SVG's size in points
                image["scale"] = f"{scale}x"
            properties: dict[str, Any] = {"template-rendering-intent": "original"}
        else:
            filename = f"{name}.pdf"
            if not _svg_to_pdf(svg_path, imageset_dir / filename):
                return None
            image = {"filename": filename, "idiom": "universal"}
            properties = {
                "preserves-vector-representation": True,
                "template-rendering-intent": "original",
            }

        # The other form's file from an earlier build (the SVG changed between
        # vector and raster) would sit in the set unreferenced.
        for ext in _IOS_ASSET_EXTS:
            stale = imageset_dir / f"{name}.{ext}"
            if stale.name != filename:
                stale.unlink(missing_ok=True)

        # Write Contents.json
        contents = {
            "images": [image],
            "info": {"author": "jui", "version": 1},
            "properties": properties,
        }
        contents_path = imageset_dir / "Contents.json"
        _write_if_changed(contents_path, (json.dumps(contents, indent=2) + "\n").encode("utf-8"))

        return imageset_dir

    # ------------------------------------------------------------------ #
    #  Android — Vector Drawable XML
    # ------------------------------------------------------------------ #

    @staticmethod
    def convert_android(
        svg_path: Path,
        drawable_dir: Path,
        name: str | None = None,
    ) -> Path | None:
        """Convert an SVG to Android Vector Drawable XML.

        *name* stands for the file's stem (``ic_star__dark`` for
        ``ic_star.dark.svg``); it is spelled as a resource name either way.

        Returns the output XML path, or None on error.
        """
        try:
            tree = ET.parse(svg_path)
        except ET.ParseError:
            return None

        root = tree.getroot()
        ns = {"svg": "http://www.w3.org/2000/svg"}

        # Extract viewBox or width/height
        viewbox = root.get("viewBox", "")
        if viewbox:
            parts = viewbox.split()
            if len(parts) == 4:
                vb_width, vb_height = parts[2], parts[3]
            else:
                vb_width = root.get("width", "24")
                vb_height = root.get("height", "24")
        else:
            vb_width = _strip_unit(root.get("width", "24"))
            vb_height = _strip_unit(root.get("height", "24"))

        width_dp = vb_width
        height_dp = vb_height

        # Collect path data
        paths: list[dict[str, str]] = []
        _collect_paths(root, ns, paths)

        lost = _android_loses(root, paths)
        if lost:
            print(f"  WARNING: {svg_path.name}: Android {lost}")

        if not paths:
            # SVG with no drawable paths — fall back to raster extraction
            # for AI-generated illustrations that wrap a base64 PNG/JPEG in
            # an <image> tag. Without this the file was silently dropped.
            raster = _extract_raster_image(root)
            if raster is not None:
                out = _write_raster_drawable(svg_path, drawable_dir, raster, name)
                _remove_other_drawables(drawable_dir, out)
                return out
            return None

        # Build Vector Drawable XML
        drawable_dir.mkdir(parents=True, exist_ok=True)
        name = android_resource_name(name or svg_path.stem)
        out_path = drawable_dir / f"{name}.xml"

        lines = [
            '<?xml version="1.0" encoding="utf-8"?>',
            "<vector",
            '    xmlns:android="http://schemas.android.com/apk/res/android"',
            f'    android:width="{width_dp}dp"',
            f'    android:height="{height_dp}dp"',
            f'    android:viewportWidth="{vb_width}"',
            f'    android:viewportHeight="{vb_height}">',
        ]

        for p in paths:
            fill = p.get("fill", "#000000")
            if fill == "none":
                fill_attr = ""
            else:
                fill_attr = f'\n        android:fillColor="{fill}"'

            stroke = p.get("stroke", "")
            stroke_attr = ""
            if stroke and stroke != "none":
                stroke_attr = f'\n        android:strokeColor="{stroke}"'
                sw = p.get("stroke-width", "1")
                stroke_attr += f'\n        android:strokeWidth="{sw}"'
                linecap = p.get("stroke-linecap")
                if linecap in ("butt", "round", "square"):
                    stroke_attr += f'\n        android:strokeLineCap="{linecap}"'
                linejoin = p.get("stroke-linejoin")
                if linejoin in ("miter", "round", "bevel"):
                    stroke_attr += f'\n        android:strokeLineJoin="{linejoin}"'
                miter = p.get("stroke-miterlimit")
                if miter:
                    stroke_attr += f'\n        android:strokeMiterLimit="{miter}"'
                # opacity (the element's and every enclosing group's, multiplied) is on the line as on the fill
                stroke_alpha = _opacity(p.get("stroke-opacity")) * p["_opacity"]
                if stroke_alpha != 1:
                    stroke_attr += f'\n        android:strokeAlpha="{_alpha(stroke_alpha)}"'

            alpha_attr = ""
            fill_alpha = _opacity(p.get("fill-opacity")) * p["_opacity"]
            if fill != "none" and fill_alpha != 1:
                alpha_attr = f'\n        android:fillAlpha="{_alpha(fill_alpha)}"'

            lines.append("    <path")
            lines.append(f'        android:pathData="{p["d"]}"'
                         f"{fill_attr}{stroke_attr}{alpha_attr} />")

        lines.append("</vector>")
        lines.append("")

        out_path.write_text("\n".join(lines), encoding="utf-8")
        _remove_other_drawables(drawable_dir, out_path)
        return out_path

    # ------------------------------------------------------------------ #
    #  Web — copy SVG as-is
    # ------------------------------------------------------------------ #

    @staticmethod
    def convert_web(
        svg_path: Path,
        images_dir: Path,
    ) -> Path | None:
        """Copy SVG to *images_dir*."""
        images_dir.mkdir(parents=True, exist_ok=True)
        dest = images_dir / svg_path.name
        shutil.copy2(svg_path, dest)
        return dest


# ====================================================================== #
#  Helpers
# ====================================================================== #


def android_resource_name(stem: str) -> str:
    """The drawable's resource name for a file stem, as it always was."""
    return stem.replace("-", "_").lower()

def _pdf_creation_epoch() -> int:
    """The creation date every converted PDF carries, as a Unix time.

    Left alone, both converters stamp the wall clock into the PDF, so the
    same SVG became a different PDF on every build: on one face
    `jui build --clean` rewrote all 123 iOS image assets each run, identical
    but for /CreationDate (reported 2026-09-24). The date says nothing about
    the image, so it is pinned: SOURCE_DATE_EPOCH when the run sets one —
    read through the generation manifest's pin, so the variable has one
    reader in this package — and otherwise the epoch itself. (The manifest's
    `generatedAt` falls back to the wall clock instead; that stamp records
    when a build ran, this one records nothing.)
    """
    from . import generation_manifest

    pinned = generation_manifest.pinned_build_time() if generation_manifest.AVAILABLE else None
    return int(pinned.timestamp()) if pinned else 0


def _write_if_changed(path: Path, data: bytes) -> bool:
    """Write *data* unless *path* already holds exactly that. True if written.

    Byte-identical output left in place keeps its mtime, so an unchanged
    asset does not look changed to Xcode's incremental build.
    """
    try:
        if path.read_bytes() == data:
            return False
    except OSError:
        pass
    path.write_bytes(data)
    return True


def _svg_to_pdf(svg_path: Path, pdf_path: Path) -> bool:
    """Convert SVG to PDF. Try rsvg-convert first, then cairosvg.

    The conversion goes to a scratch file beside *pdf_path* and replaces it
    only when the bytes differ; with the creation date pinned
    (`_pdf_creation_epoch`), an unchanged SVG leaves its PDF untouched.
    """
    epoch = _pdf_creation_epoch()
    fd, scratch_name = tempfile.mkstemp(prefix=".jui-", suffix=".pdf", dir=pdf_path.parent)
    os.close(fd)
    scratch = Path(scratch_name)
    try:
        if not _convert_svg_to_pdf(svg_path, scratch, epoch):
            print(
                f"  WARNING: Cannot convert {svg_path.name} to PDF. "
                "Install rsvg-convert (brew install librsvg) or cairosvg (pip install cairosvg)."
            )
            return False
        _write_if_changed(pdf_path, scratch.read_bytes())
        return True
    finally:
        scratch.unlink(missing_ok=True)


def _convert_svg_to_pdf(svg_path: Path, pdf_path: Path, epoch: int) -> bool:
    # 1. rsvg-convert (brew install librsvg). It stamps SOURCE_DATE_EPOCH as
    #    the creation date when the variable is set (measured: rsvg-convert
    #    2.62.1 / cairo 1.18.4), so the pin is handed to it that way.
    try:
        result = subprocess.run(
            ["rsvg-convert", "-f", "pdf", "-o", str(pdf_path), str(svg_path)],
            capture_output=True,
            env={**os.environ, "SOURCE_DATE_EPOCH": str(epoch)},
        )
        if result.returncode == 0 and pdf_path.exists() and pdf_path.stat().st_size:
            return True
    except FileNotFoundError:
        pass

    # 2. cairosvg (pip install cairosvg). cairo itself ignores
    #    SOURCE_DATE_EPOCH (measured: two conversions a second apart differ
    #    with it set), so the date goes onto the PDF surface directly.
    try:
        import cairocffi  # type: ignore[import-untyped]
        from cairosvg.surface import PDFSurface  # type: ignore[import-untyped]
    except ImportError:
        return False
    stamp = datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    class _PinnedPDFSurface(PDFSurface):
        def _create_surface(self, width, height):
            surface, width, height = super()._create_surface(width, height)
            surface.set_metadata(cairocffi.PDF_METADATA_CREATE_DATE, stamp)
            return surface, width, height

    _PinnedPDFSurface.convert(url=str(svg_path), write_to=str(pdf_path))
    return pdf_path.exists() and pdf_path.stat().st_size > 0


def _strip_unit(value: str) -> str:
    """Remove CSS units like 'px', 'pt', 'em' from a numeric string."""
    return re.sub(r"(px|pt|em|rem|%)", "", value).strip()


def _collect_paths(
    element: ET.Element,
    ns: dict[str, str],
    out: list[dict[str, str]],
    parent_attrs: dict[str, str] | None = None,
) -> None:
    """Recursively collect <path> elements with their attributes.

    The paint properties are inherited (a child's own value replaces its parent's), read from the presentation
    attribute or from ``style`` (which wins, as in SVG). ``opacity`` is not inherited but applies to everything inside:
    an element's ``_opacity`` is its own times every enclosing group's (ticket jui-svg-opacity-not-applied-to-stroke).
    """
    tag = _local_tag(element.tag)
    attrs = dict(parent_attrs or {})
    attrs.setdefault("_opacity", 1.0)
    style = _style_props(element)

    # Inherit fill/stroke from parent
    for attr in (
        "fill",
        "stroke",
        "stroke-width",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-miterlimit",
        "fill-opacity",
        "stroke-opacity",
    ):
        val = style.get(attr) or element.get(attr)
        if val:
            attrs[attr] = val
    own = style.get("opacity") or element.get("opacity")
    if own:
        attrs["_opacity"] = attrs["_opacity"] * _opacity(own)

    if tag == "path":
        d = element.get("d", "")
        if d:
            entry = dict(attrs)
            entry["d"] = d
            out.append(entry)

    elif tag == "circle":
        cx = element.get("cx", "0")
        cy = element.get("cy", "0")
        r = element.get("r", "0")
        d = f"M{cx},{_float_sub(cy, r)} A{r},{r},0,1,1,{cx},{_float_add(cy, r)} A{r},{r},0,1,1,{cx},{_float_sub(cy, r)}Z"
        entry = dict(attrs)
        entry["d"] = d
        out.append(entry)

    elif tag == "rect":
        x = float(element.get("x", "0"))
        y = float(element.get("y", "0"))
        w = float(element.get("width", "0"))
        h = float(element.get("height", "0"))
        rx = float(element.get("rx", "0"))
        ry = float(element.get("ry", str(rx)))
        if rx == 0 and ry == 0:
            d = f"M{x},{y} L{x + w},{y} L{x + w},{y + h} L{x},{y + h} Z"
        else:
            d = (
                f"M{x + rx},{y} L{x + w - rx},{y} "
                f"Q{x + w},{y},{x + w},{y + ry} L{x + w},{y + h - ry} "
                f"Q{x + w},{y + h},{x + w - rx},{y + h} L{x + rx},{y + h} "
                f"Q{x},{y + h},{x},{y + h - ry} L{x},{y + ry} "
                f"Q{x},{y},{x + rx},{y} Z"
            )
        entry = dict(attrs)
        entry["d"] = d
        out.append(entry)

    elif tag == "ellipse":
        cx = element.get("cx", "0")
        cy = element.get("cy", "0")
        rx = element.get("rx", "0")
        ry = element.get("ry", "0")
        d = f"M{cx},{_float_sub(cy, ry)} A{rx},{ry},0,1,1,{cx},{_float_add(cy, ry)} A{rx},{ry},0,1,1,{cx},{_float_sub(cy, ry)}Z"
        entry = dict(attrs)
        entry["d"] = d
        out.append(entry)

    elif tag == "line":
        x1 = element.get("x1", "0")
        y1 = element.get("y1", "0")
        x2 = element.get("x2", "0")
        y2 = element.get("y2", "0")
        entry = dict(attrs)
        entry["d"] = f"M{x1},{y1} L{x2},{y2}"
        if "fill" not in entry:
            entry["fill"] = "none"
        out.append(entry)

    elif tag == "polygon":
        d = _points_to_path(element.get("points", ""), close=True)
        if d:
            entry = dict(attrs)
            entry["d"] = d
            out.append(entry)

    elif tag == "polyline":
        d = _points_to_path(element.get("points", ""), close=False)
        if d:
            entry = dict(attrs)
            entry["d"] = d
            if "fill" not in entry:
                entry["fill"] = "none"
            out.append(entry)

    # Recurse into children (g, svg, defs, etc.)
    for child in element:
        _collect_paths(child, ns, out, attrs)


def _style_props(element: ET.Element) -> dict[str, str]:
    """An element's ``style="a: b; c: d"`` as {a: b, c: d} (names lower-cased; ``!important`` dropped)."""
    out: dict[str, str] = {}
    for decl in (element.get("style") or "").split(";"):
        name, sep, value = decl.partition(":")
        value = value.replace("!important", "").strip()
        if sep and name.strip() and value:
            out[name.strip().lower()] = value
    return out


def _opacity(value: str | None) -> float:
    """An SVG opacity (``0.5`` or ``50%``), clamped to 0..1; missing or unreadable: 1."""
    if not value:
        return 1.0
    v = value.strip()
    try:
        x = float(v[:-1]) / 100 if v.endswith("%") else float(v)
    except ValueError:
        return 1.0
    return min(1.0, max(0.0, x)) if x == x else 1.0


def _alpha(x: float) -> str:
    """An alpha for the vector drawable: at most 4 decimals, no trailing zeros (0.55, 0.385, 0)."""
    return format(round(x, 4), "g")


def _local_tag(tag: str) -> str:
    """Strip namespace from tag name."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _float_add(a: str, b: str) -> str:
    return str(float(a) + float(b))


def _float_sub(a: str, b: str) -> str:
    return str(float(a) - float(b))


_RASTER_DATA_URI_RE = re.compile(
    r"data:image/(?P<fmt>png|jpeg|jpg);base64,(?P<b64>[A-Za-z0-9+/=\s]+)",
    re.IGNORECASE,
)

_POINT_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _extract_raster_image(root: ET.Element) -> tuple[str, bytes] | None:
    """Return ``(ext, bytes)`` for the first base64 raster in an SVG <image>.

    Some SVGs — especially AI-generated illustrations — are just a single
    ``<image href="data:image/png;base64,…">`` wrapper with no vector paths.
    VectorDrawable can't represent that, so we hand the caller the raw
    raster bytes to write as ``drawable-nodpi/<name>.{png,jpg}``.
    """
    xlink_href_attr = "{http://www.w3.org/1999/xlink}href"
    for element in root.iter():
        if _local_tag(element.tag) != "image":
            continue
        href = element.get(xlink_href_attr) or element.get("href") or ""
        if not href:
            continue
        match = _RASTER_DATA_URI_RE.match(href.strip())
        if not match:
            continue
        fmt = match.group("fmt").lower()
        ext = "jpg" if fmt in ("jpeg", "jpg") else "png"
        try:
            data = base64.b64decode(match.group("b64"), validate=False)
        except (ValueError, TypeError):
            continue
        if not data:
            continue
        return ext, data
    return None


_IOS_ASSET_EXTS = ("pdf", "png", "jpg")
_PIXEL_SLACK = 1.0


def _whole_canvas_raster(svg_path: Path) -> tuple[str, bytes, int] | None:
    """``(ext, bytes, scale)`` when the SVG is one embedded PNG/JPEG filling its canvas.

    Only the shape that loses nothing when the SVG is dropped for the raster:
    no drawable shapes, exactly one ``<image>``, its ``href``/``xlink:href`` a
    PNG or JPEG data URI, at 0,0 and the canvas's size, with no transform on
    it or around it, and the canvas (``width``/``height``, which must agree
    with the ``viewBox``) 1/2/3 times smaller than the pixels on both axes,
    to within a pixel, so ``scale`` keeps the asset the SVG's size in points. Anything else
    (WebP, which an asset catalog does not take; an external href; two
    images; a picture drawn over the image) is None and stays a PDF.
    """
    try:
        root = ET.parse(svg_path).getroot()
    except (ET.ParseError, OSError):
        return None
    shapes: list[dict[str, str]] = []
    _collect_paths(root, {}, shapes)
    if shapes:
        return None
    images = _images(root)
    if len(images) != 1 or not _fills_canvas(root, images[0]):
        return None
    image = images[0]
    cw, ch = _canvas_size(root)  # type: ignore[misc]  # _fills_canvas read it
    raster = _extract_raster_image(image)
    if raster is None:
        return None
    ext, data = raster
    pixels = _raster_pixel_size(ext, data)
    if pixels is None:
        return None
    pw, ph = pixels
    scale = round(pw / cw)
    if scale not in (1, 2, 3) or round(ph / ch) != scale:
        return None
    # Within a pixel on each axis: an export rounds the canvas or the pixels
    # (280x427 drawn from 840x1280 is 1 px short of 3x; a 341.33 canvas for
    # 1024 px is 0.01 over), and a pixel is not a difference anyone sees.
    if abs(pw - cw * scale) > _PIXEL_SLACK or abs(ph - ch * scale) > _PIXEL_SLACK:
        return None
    return ext, data, scale


def _images(root: ET.Element) -> list[ET.Element]:
    return [e for e in root.iter() if _local_tag(e.tag) == "image"]


def _fills_canvas(root: ET.Element, image: ET.Element) -> bool:
    """True when *image* sits at 0,0 at the canvas's size and nothing in the SVG is transformed."""
    if any(e.get("transform") for e in root.iter()):
        return False
    canvas = _canvas_size(root)
    if canvas is None:
        return False
    try:
        x = float(_strip_unit(image.get("x", "0")) or 0)
        y = float(_strip_unit(image.get("y", "0")) or 0)
        iw = float(_strip_unit(image.get("width", "")))
        ih = float(_strip_unit(image.get("height", "")))
    except ValueError:
        return False
    return (x, y, iw, ih) == (0, 0, canvas[0], canvas[1])


def _android_loses(root: ET.Element, paths: list[dict[str, str]]) -> str | None:
    """What of an SVG's ``<image>`` the Android drawable does not carry, said for a WARNING; None when nothing.

    The output itself is unchanged (a vector drawable draws no images; the
    raster fallback takes the first PNG/JPEG data URI whole); this only stops
    the loss being silent (ticket jui-android-svg-image-dropped-silently).
    """
    images = _images(root)
    if not images:
        return None
    if paths:
        return f"draws only the shapes: {len(images)} <image> dropped (a vector drawable has no images)"
    raster = _extract_raster_image(root)
    if raster is None:
        kinds = sorted({_image_kind(e) for e in images})
        return f"writes nothing: the <image> is {' / '.join(kinds)} (only an embedded PNG/JPEG is taken)"
    if len(images) > 1:
        return f"writes only the first PNG/JPEG of {len(images)} <image>"
    if not _fills_canvas(root, images[0]):
        return "writes the embedded picture whole: its position, size or transform in the SVG is not kept"
    return None


def _image_kind(image: ET.Element) -> str:
    href = (image.get("{http://www.w3.org/1999/xlink}href") or image.get("href") or "").strip()
    if not href:
        return "without an href"
    m = re.match(r"data:([^;,]*)", href, re.IGNORECASE)
    if m:
        return f"a {m.group(1) or 'data'} data URI"
    return "an external file"


def _remove_other_drawables(drawable_dir: Path, written: Path) -> None:
    """Remove the other form's file for the same name (drawable/<name>.xml or drawable-nodpi/<name>.png|jpg).

    Both forms otherwise stay side by side when an SVG changes between vector
    and raster, and aapt2 links the pair without complaint, so a device could
    show the old picture.
    """
    stem = written.stem
    candidates = [drawable_dir / f"{stem}.xml"] + [
        drawable_dir.parent / "drawable-nodpi" / f"{stem}.{ext}" for ext in ("png", "jpg")
    ]
    for path in candidates:
        if path != written:
            path.unlink(missing_ok=True)


def _canvas_size(root: ET.Element) -> tuple[float, float] | None:
    """The SVG's size in points: ``width``/``height`` and ``viewBox`` agreeing (either alone is enough)."""
    try:
        size = None
        if root.get("width") and root.get("height"):
            size = (float(_strip_unit(root.get("width"))), float(_strip_unit(root.get("height"))))
        viewbox = (root.get("viewBox") or "").replace(",", " ").split()
        if viewbox:
            if len(viewbox) != 4:
                return None
            vx, vy, vw, vh = (float(v) for v in viewbox)
            if (vx, vy) != (0, 0) or (size is not None and size != (vw, vh)):
                return None
            size = (vw, vh)
    except ValueError:
        return None
    if size is None or size[0] <= 0 or size[1] <= 0:
        return None
    return size


def _raster_pixel_size(ext: str, data: bytes) -> tuple[int, int] | None:
    """A PNG's or JPEG's width and height in pixels, read from its header."""
    if ext == "png":
        if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
            return None
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker == 0xFF:
            i += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = int.from_bytes(data[i + 2:i + 4], "big")
        # SOF0..SOF15 except DHT (C4), JPG (C8), DAC (CC)
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            if i + 9 > len(data):
                return None
            h = int.from_bytes(data[i + 5:i + 7], "big")
            w = int.from_bytes(data[i + 7:i + 9], "big")
            return (w, h) if w and h else None
        i += 2 + length
    return None


def _write_raster_drawable(
    svg_path: Path,
    drawable_dir: Path,
    raster: tuple[str, bytes],
    name: str | None = None,
) -> Path:
    """Write decoded raster bytes to ``drawable-nodpi/<name>.{png,jpg}``.

    ``drawable-nodpi`` is used so the Android resource system doesn't
    rescale the image based on device density — these are authored at
    fixed pixel sizes and scaling them produces blurry icons.
    """
    ext, data = raster
    dest_dir = drawable_dir.parent / "drawable-nodpi"
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = android_resource_name(name or svg_path.stem)
    out_path = dest_dir / f"{name}.{ext}"
    out_path.write_bytes(data)
    return out_path


def _points_to_path(points: str, *, close: bool) -> str:
    """Convert an SVG ``points`` attribute to a VectorDrawable ``pathData`` string.

    SVG accepts points as any mix of whitespace and commas between numbers
    (``"16 17 21 12"`` or ``"16,17 21,12"`` or ``"16,17,21,12"``). Each
    number is an x/y component, not an ``x,y`` pair, so splitting on
    whitespace alone drops the pairing and emits ``M16 L17 L21 L12`` instead
    of ``M16,17 L21,12``.
    """
    if not points:
        return ""
    nums = _POINT_NUM_RE.findall(points)
    if len(nums) < 4 or len(nums) % 2 != 0:
        return ""
    coords = [f"{nums[i]},{nums[i + 1]}" for i in range(0, len(nums), 2)]
    segments = [f"M{coords[0]}"] + [f"L{c}" for c in coords[1:]]
    if close:
        segments.append("Z")
    return " ".join(segments)
