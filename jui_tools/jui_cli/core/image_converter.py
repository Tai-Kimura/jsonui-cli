"""Convert SVG images to platform-specific formats.

- iOS: Create .imageset in *.xcassets with PDF (preserves-vector-representation)
- Android: Convert SVG to Android Vector Drawable XML (or extract raster
  PNG/JPEG when the SVG only wraps a base64 data URI)
- Web: Copy SVG as-is to public/images/
"""
from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
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
    ) -> Path | None:
        """Create an .imageset inside *xcassets_dir* with a PDF converted from SVG.

        Conversion priority:
        1. ``rsvg-convert`` (Homebrew: ``brew install librsvg``)
        2. ``cairosvg`` Python package (``pip install cairosvg``)

        Returns the imageset directory path, or None on error.
        """
        name = svg_path.stem
        imageset_dir = xcassets_dir / f"{name}.imageset"
        imageset_dir.mkdir(parents=True, exist_ok=True)

        pdf_name = f"{name}.pdf"
        dest_pdf = imageset_dir / pdf_name

        if not _svg_to_pdf(svg_path, dest_pdf):
            return None

        # Write Contents.json
        contents = {
            "images": [
                {
                    "filename": pdf_name,
                    "idiom": "universal",
                }
            ],
            "info": {"author": "jui", "version": 1},
            "properties": {
                "preserves-vector-representation": True,
                "template-rendering-intent": "original",
            },
        }
        contents_path = imageset_dir / "Contents.json"
        with open(contents_path, "w", encoding="utf-8") as f:
            json.dump(contents, f, indent=2)
            f.write("\n")

        return imageset_dir

    # ------------------------------------------------------------------ #
    #  Android — Vector Drawable XML
    # ------------------------------------------------------------------ #

    @staticmethod
    def convert_android(
        svg_path: Path,
        drawable_dir: Path,
    ) -> Path | None:
        """Convert an SVG to Android Vector Drawable XML.

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

        if not paths:
            # SVG with no drawable paths — fall back to raster extraction
            # for AI-generated illustrations that wrap a base64 PNG/JPEG in
            # an <image> tag. Without this the file was silently dropped.
            raster = _extract_raster_image(root)
            if raster is not None:
                return _write_raster_drawable(svg_path, drawable_dir, raster)
            return None

        # Build Vector Drawable XML
        drawable_dir.mkdir(parents=True, exist_ok=True)
        name = svg_path.stem.replace("-", "_").lower()
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
                stroke_alpha = p.get("stroke-opacity")
                if stroke_alpha and stroke_alpha != "1":
                    stroke_attr += f'\n        android:strokeAlpha="{stroke_alpha}"'

            fill_alpha = p.get("fill-opacity", p.get("opacity", ""))
            alpha_attr = ""
            if fill_alpha and fill_alpha != "1":
                alpha_attr = f'\n        android:fillAlpha="{fill_alpha}"'

            lines.append("    <path")
            lines.append(f'        android:pathData="{p["d"]}"'
                         f"{fill_attr}{stroke_attr}{alpha_attr} />")

        lines.append("</vector>")
        lines.append("")

        out_path.write_text("\n".join(lines), encoding="utf-8")
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

def _svg_to_pdf(svg_path: Path, pdf_path: Path) -> bool:
    """Convert SVG to PDF. Try rsvg-convert first, then cairosvg."""
    # 1. rsvg-convert (brew install librsvg)
    try:
        result = subprocess.run(
            ["rsvg-convert", "-f", "pdf", "-o", str(pdf_path), str(svg_path)],
            capture_output=True,
        )
        if result.returncode == 0 and pdf_path.exists():
            return True
    except FileNotFoundError:
        pass

    # 2. cairosvg (pip install cairosvg)
    try:
        import cairosvg  # type: ignore[import-untyped]
        cairosvg.svg2pdf(url=str(svg_path), write_to=str(pdf_path))
        if pdf_path.exists():
            return True
    except ImportError:
        pass

    print(
        f"  WARNING: Cannot convert {svg_path.name} to PDF. "
        "Install rsvg-convert (brew install librsvg) or cairosvg (pip install cairosvg)."
    )
    return False


def _strip_unit(value: str) -> str:
    """Remove CSS units like 'px', 'pt', 'em' from a numeric string."""
    return re.sub(r"(px|pt|em|rem|%)", "", value).strip()


def _collect_paths(
    element: ET.Element,
    ns: dict[str, str],
    out: list[dict[str, str]],
    parent_attrs: dict[str, str] | None = None,
) -> None:
    """Recursively collect <path> elements with their attributes."""
    tag = _local_tag(element.tag)
    attrs = dict(parent_attrs or {})

    # Inherit fill/stroke from parent
    for attr in (
        "fill",
        "stroke",
        "stroke-width",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-miterlimit",
        "opacity",
        "fill-opacity",
        "stroke-opacity",
    ):
        val = element.get(attr)
        if val:
            attrs[attr] = val

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


def _write_raster_drawable(
    svg_path: Path,
    drawable_dir: Path,
    raster: tuple[str, bytes],
) -> Path:
    """Write decoded raster bytes to ``drawable-nodpi/<name>.{png,jpg}``.

    ``drawable-nodpi`` is used so the Android resource system doesn't
    rescale the image based on device density — these are authored at
    fixed pixel sizes and scaling them produces blurry icons.
    """
    ext, data = raster
    dest_dir = drawable_dir.parent / "drawable-nodpi"
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = svg_path.stem.replace("-", "_").lower()
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
