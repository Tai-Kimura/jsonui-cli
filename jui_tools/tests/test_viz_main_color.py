"""The main robot's colour is sky blue (2.3.5, requester 10-19: 「スカイブルーにしようか」): ROLES.main, the ink on its
pill, and no #ff7a3d left for the main robot anywhere in the page's code (the orange stays only for the confetti and
the play ball, which are no role's colour)."""
from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "jui_cli" / "viz" / "web"


def _lum(h: str) -> float:
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(int(h[i:i + 2], 16)) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    x, y = sorted([_lum(a), _lum(b)])
    return (y + 0.05) / (x + 0.05)


def test_the_main_colour_is_sky_blue_and_its_pill_reads():
    core = (WEB / "js" / "10-robot-core.js").read_text()
    assert re.search(r"main: \{ name: 'メイン', color: '#0ea5e9' \}", core)
    ink = re.search(r"const ROLE_INK = \{[^}]*main: '(#[0-9a-f]{6})'", (WEB / "js" / "20-core.js").read_text())
    assert ink and _contrast(ink.group(1), "#0ea5e9") >= 4.5, ink


def test_no_old_orange_is_left_for_the_main_robot():
    hits = []
    for path in sorted(WEB.rglob("*")):
        if path.is_file() and path.suffix in (".js", ".css", ".html") and "vendor" not in path.parts:
            for n, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                if "ff7a3d" in line.lower() and "confetti" not in line and "G.ball" not in line:
                    hits.append(f"{path.name}:{n}: {line.strip()[:120]}")
    assert hits == [], hits
