"""The SVG's opacity on Android's vector drawable (ticket jui-svg-opacity-not-applied-to-stroke): an element's or a
group's ``opacity`` was moved to fillAlpha only (a line drawn with ``fill="none"`` came out opaque), and a group's
``opacity`` was replaced by a child's instead of multiplied with it; ``style`` was not read at all.

As SVG draws it: fillAlpha = fill-opacity × opacity, strokeAlpha = stroke-opacity × opacity, where opacity is the
element's own times every enclosing group's, and fill-opacity / stroke-opacity are inherited (a child's own value
replaces its parent's). A property in ``style`` wins over the attribute. One sample per way of writing it, and the
shape of bar's ic_import_box.svg (a stroke-only group with opacity, a stroke-only polyline with opacity).
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest

from jui_cli.core.image_converter import ImageConverter


def _paths(body: str) -> list[dict[str, str]]:
    """Each <path> of the drawable the SVG body converts to, as {attribute (android: left off): value}."""
    with tempfile.TemporaryDirectory() as tmp:
        svg = Path(tmp) / "ic_t.svg"
        svg.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{body}</svg>', encoding="utf-8")
        out = ImageConverter.convert_android(svg, Path(tmp) / "drawable")
        xml = out.read_text(encoding="utf-8")
    return [dict(re.findall(r'android:(\w+)="([^"]*)"', block)) for block in xml.split("<path")[1:]]


def _alphas(body: str) -> list[tuple[str | None, str | None]]:
    return [(p.get("fillAlpha"), p.get("strokeAlpha")) for p in _paths(body)]


L = '<line x1="0" y1="0" x2="9" y2="9" stroke="#123456"{}/>'
R = '<rect width="4" height="4" fill="#ff0000" stroke="#00ff00"{}/>'
L_HALF, R_08, R_09 = L.format(' opacity="0.5"'), R.format(' opacity="0.8"'), R.format(' fill-opacity="0.9"')

CASES = {   # how it is written: (svg body, [(fillAlpha, strokeAlpha)] per path)
    "opacity on a stroke-only element": (L.format(' opacity="0.7"'), [(None, "0.7")]),
    "opacity on fill and stroke": (R.format(' opacity="0.5"'), [("0.5", "0.5")]),
    "fill-opacity alone": (R.format(' fill-opacity="0.4"'), [("0.4", None)]),
    "stroke-opacity alone": (R.format(' stroke-opacity="0.3"'), [(None, "0.3")]),
    "opacity × fill-opacity × stroke-opacity": (R.format(' opacity="0.5" fill-opacity="0.4" stroke-opacity="0.6"'),
                                                [("0.2", "0.3")]),
    "group opacity over a stroke-only child": (f'<g opacity="0.55">{L.format("")}</g>', [(None, "0.55")]),
    "group opacity × child opacity": (f'<g opacity="0.5">{L_HALF}</g>', [(None, "0.25")]),
    "groups nested three deep": (f'<g opacity="0.5"><g opacity="0.5"><g>{R_08}</g></g></g>',
                                 [("0.2", "0.2")]),
    "group fill-opacity is inherited, a child's replaces it": (
        f'<g fill-opacity="0.2">{R.format("")}{R_09}</g>', [("0.2", None), ("0.9", None)]),
    "style opacity": (L.format(' style="opacity: 0.7"'), [(None, "0.7")]),
    "style fill-opacity and stroke-opacity": (R.format(' style="fill-opacity:0.4;stroke-opacity:0.6"'), [("0.4", "0.6")]),
    "style wins over the attribute": (R.format(' opacity="0.9" style="opacity:0.5"'), [("0.5", "0.5")]),
    "style on a group": (f'<g style="opacity:0.5">{L.format("")}</g>', [(None, "0.5")]),
    "a percentage": (L.format(' opacity="70%"'), [(None, "0.7")]),
    "opacity 1 writes nothing": (R.format(' opacity="1"'), [(None, None)]),
    "opacity 0": (L.format(' opacity="0"'), [(None, "0")]),
    "out of range is clamped": (L.format(' opacity="1.5"'), [(None, None)]),
    "no fill, no fillAlpha": ('<polyline points="0,0 9,9" fill="none" stroke="#8A5A2E" opacity="0.7"/>', [(None, "0.7")]),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_the_alphas_are_svgs(case):
    body, want = CASES[case]
    assert _alphas(body) == want


def test_style_paints_are_read_too():
    """The paint in style (fill, stroke, stroke-width) was not read: a red style fill came out black."""
    p = _paths('<rect width="4" height="4" style="fill:#ff0000; stroke:#00ff00; stroke-width:2"/>')[0]
    assert (p.get("fillColor"), p.get("strokeColor"), p.get("strokeWidth")) == ("#ff0000", "#00ff00", "2")


def test_bars_import_box_shape():
    """ic_import_box.svg (bar), made small: the group of three highlight lines at opacity 0.55, the fold line at 0.7,
    the handle hole (a fill) at 0.85 and the shadow ellipse at 0.28 — each alpha on the paint it has."""
    body = ('<ellipse cx="60" cy="110" rx="42" ry="6" fill="#000" opacity="0.28"/>'
            '<g stroke="#F3C77A" stroke-width="1.2" stroke-linecap="round" opacity="0.55">'
            '<line x1="44.5" y1="33" x2="44.5" y2="44"/><line x1="60.5" y1="25" x2="60.5" y2="38"/></g>'
            '<polyline points="20,60 60,80 100,60" fill="none" stroke="#8A5A2E" stroke-width="1" opacity="0.7"/>'
            '<polygon points="31,70 45,77 45,81 31,74" fill="#5A3818" opacity="0.85"/>')
    assert _alphas(body) == [("0.28", None), (None, "0.55"), (None, "0.55"), (None, "0.7"), ("0.85", None)]
