"""The walls' colour comes from one place: the --wall token of app.css (light and dark, 10-18 warmer walls).

The scene reads the token (40-scene.js); the only literal of it in the scripts is the fallback for a page without the
stylesheet, and it is the light value. A wall colour written anywhere else would not follow the theme.
"""
from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "jui_cli" / "viz" / "web"


def _walls():
    css = (WEB / "app.css").read_text(encoding="utf-8")
    return re.findall(r"--wall:\s*(#[0-9a-fA-F]{6})\s*;", css)


def test_the_token_is_defined_for_light_and_both_dark_rules_and_is_warm():
    values = _walls()
    assert len(values) == 3, values                     # :root, the dark media query, [data-theme=dark]
    light, dark1, dark2 = values
    assert dark1 == dark2 and light != dark1

    def rgb(h):
        return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
    for h in values:
        r, g, b = rgb(h)
        assert r >= b, f"{h} leans blue; the walls are warm now"
    assert sum(rgb(light)) < sum(rgb("#f7f9fc")) and sum(rgb(dark1)) > sum(rgb("#2c384b"))   # lighter dark, darker light


def test_the_scene_reads_the_token_and_writes_the_colour_nowhere_else():
    values = {v.lower() for v in _walls()} | {"#f7f9fc", "#2c384b"}   # today's and the old ones
    scripts = {p.name: p.read_text(encoding="utf-8") for p in (WEB / "js").glob("*.js")}
    scene = scripts["40-scene.js"]
    assert scene.count("readToken('--wall', WALL_FALLBACK)") == 2
    fallback = re.search(r"const WALL_FALLBACK = '(#[0-9a-fA-F]{6})';", scene)
    assert fallback and fallback.group(1).lower() == _walls()[0].lower()
    stray = [(name, m.group(0)) for name, text in scripts.items() for m in re.finditer(r"#[0-9a-fA-F]{6}\b", text)
             if m.group(0).lower() in values and not (name == "40-scene.js" and m.start() == fallback.start(1))
             and not text[max(0, m.start() - 7):m.start()] == "tile: '"]   # the spec board's tile, not a wall
    assert not stray, stray
