"""shared/core/font_scale_vectors.json against its rule, written once in Python (shared/core/font_scale_rule.py).

The vectors are the contract the three runtimes read for fontScaling / maxFontScale (ticket
sjui-label-font-size-ignores-dynamic-type, ruling 2026-11-13): the size a component's text is drawn at, and the
Dynamic Type step an iOS cap rounds down to. They are hand-written; the reference here is a second statement of the
same rule, so a vector that contradicts the rule text is red where it is written, not first on a device.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jui_cli.core import shared_core

VECTORS = Path(__file__).resolve().parents[2] / "shared" / "core" / "font_scale_vectors.json"
DEFINITIONS = Path(__file__).resolve().parents[2] / "shared" / "core" / "attribute_definitions.json"
DATA = json.loads(VECTORS.read_text(encoding="utf-8"))
RULE = shared_core.load("font_scale_rule")


def _named(rows):
    return [pytest.param(v, id=v["name"]) for v in rows]


def test_the_rule_loads_and_every_section_has_vectors():
    assert RULE is not None, "shared/core/font_scale_rule.py did not load"
    assert DATA["drawn"] and DATA["iosCap"]["cases"]
    assert set(DATA["rule"]) == {"follows", "drawn", "partial", "noFontSize", "iosCap"}


@pytest.mark.parametrize("v", _named(DATA["drawn"]))
def test_drawn(v):
    got = RULE.drawn(v["size"], v["scale"], v.get("declared"), v.get("max"), v.get("appDefault", True))
    assert got == pytest.approx(v["drawn"])


@pytest.mark.parametrize("v", _named(DATA["iosCap"]["cases"]))
def test_ios_cap_step(v):
    assert RULE.ios_cap_step(v["max"], DATA["iosCap"]["ratios"]) == v["step"]


def test_the_ios_steps_grow_from_the_standard_size():
    ratios = list(DATA["iosCap"]["ratios"].values())
    assert ratios[0] == 1.0 and ratios == sorted(ratios)


def test_every_component_with_a_font_size_declares_both_attributes():
    """fontScaling / maxFontScale sit on every component that declares fontSize, on the same platforms."""
    definitions = json.loads(DEFINITIONS.read_text(encoding="utf-8"))
    with_size = [c for c, attrs in definitions.items() if isinstance(attrs, dict) and "fontSize" in attrs]
    assert with_size
    for component in with_size:
        attrs = definitions[component]
        for name in ("fontScaling", "maxFontScale"):
            assert name in attrs, f"{component}.{name}"
            assert attrs[name].get("platform") == attrs["fontSize"].get("platform"), f"{component}.{name}"
        assert attrs["fontScaling"]["type"] == "boolean"
        assert attrs["maxFontScale"]["type"] == "number" and attrs["maxFontScale"]["min"] == 1
