"""A shadow field left out takes its declared default on every face.

The defaults were each face's own until 2026-11-07: radius 5 on iOS and the web
and 4 on Android, offsetY 0 on iOS and Android and 2 on the web, and a default
colour of SwiftUI's 33% black, Compose's opaque black, and the web's 10% (20% on
a TextField, 25% on a CircleView). They are declared now
(attribute_definitions common.shadow, iOS's values) and each generator holds
them as a constant this reads back, so a generator that drifts from the
declaration is red here before it draws a different shadow
(ticket 2026-11-07-declared-binding-slots-and-dynamic-shadow).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DECLARED = json.loads((REPO / "shared/core/attribute_definitions.json").read_text(encoding="utf-8"))[
    "common"]["shadow"]["properties"]


def _source(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def test_every_numeric_field_declares_a_default_and_takes_a_binding():
    for field in ("radius", "offsetX", "offsetY", "opacity"):
        assert "default" in DECLARED[field], field
        assert "binding" in DECLARED[field]["type"], field
    assert "binding" in DECLARED["color"]["type"]
    assert (DECLARED["offsetX"]["default"], DECLARED["offsetY"]["default"], DECLARED["opacity"]["default"]) == (0, 0, 1)


def test_ios_codegen_holds_the_declared_defaults():
    body = _source("sjui_tools/lib/swiftui/views/base_view_converter.rb")
    builder = body[body.index("def build_shadow_modifier"):]
    builder = builder[:builder.index("\n        end\n")]
    assert f"number_slot(shadow['radius'] || {DECLARED['radius']['default']})" in builder
    assert f"number_slot(shadow['offsetX'] || {DECLARED['offsetX']['default']})" in builder
    assert f"number_slot(shadow['offsetY'] || {DECLARED['offsetY']['default']})" in builder
    # No colour: SwiftUI's own default shadow colour (black at 33%), opacity not applied.
    assert '".shadow(radius: #{radius}, x: #{x}, y: #{y})"' in builder


def test_android_codegen_holds_the_declared_defaults():
    body = _source("kjui_tools/lib/compose/helpers/modifier_builder.rb")
    assert re.search(rf"SHADOW_DEFAULT_RADIUS = {DECLARED['radius']['default']}\b", body)
    assert "SHADOW_DEFAULT_COLOR = 'Color.Black.copy(alpha = 0.33f)'" in body
    assert "shadow['radius'] || SHADOW_DEFAULT_RADIUS" in body
    assert "if shadow['opacity'] && shadow['color']" in body


def test_web_holds_the_declared_defaults():
    mapper = _source("rjui_tools/lib/react/tailwind_mapper.rb")
    assert re.search(rf"SHADOW_DEFAULT_RADIUS = {DECLARED['radius']['default']}\b", mapper)
    assert "SHADOW_DEFAULT_COLOR = 'rgba(0,0,0,0.33)'" in mapper
    for rel in ("rjui_tools/lib/react/tailwind_mapper.rb", "rjui_tools/lib/react/converters/base_converter.rb",
                "rjui_tools/lib/react/converters/circle_view_converter.rb",
                "rjui_tools/lib/react/converters/text_field_converter.rb"):
        body = _source(rel)
        # No face-local default left: an offset other than the declared 0, a
        # radius literal, or a colour of its own.
        assert not re.search(r"shadow\[?'offsetY'\]?\s*\|\|\s*[1-9]", body), rel
        assert not re.search(r"'radius'\]\s*\|\|\s*\d", body), rel
        assert "shadow['color'] || 'rgba(" not in body, rel
        assert "rgba(0,0,0,0.2)" not in body and "rgba(0,0,0,0.25)" not in body, rel
