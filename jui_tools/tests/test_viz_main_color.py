"""The main robot's colour is sky blue (2.3.5, requester 10-19: 「スカイブルーにしようか」): ROLES.main, its pill (2.3.6: a
darker #0369a1 with white text, the old dark ink gone, every role's pill pair measured), and no #ff7a3d left for the main robot anywhere in the page's code (the orange stays only for the confetti and
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


MAIN = "#0ea5e9"
MAIN_PILL = "#0369a1"   # 2.3.6 (ticket 2026-10-20-jui-viz-main-pill-text-contrast): the pill one step darker, white text 5.93:1
OLD_INK = "#082f49"     # the dark ink on the sky-blue pill (2.3.5): the requester found it hard to read
# Every role's body colour, which the pills must not change (requester 10-20: 「全部直す」 is the pills only).
BODIES = {"main": MAIN, "define": "#7d5cff", "ground": "#b07a52", "implement": "#3b5bdb", "navigation": "#10a693",
          "test": "#3fae4a", "debug": "#f0b400", "other": "#8a9bb0"}
E2E = Path(__file__).resolve().parents[1] / "tools" / "viz_e2e" / "main_color.py"


def _roles() -> dict:
    core = (WEB / "js" / "10-robot-core.js").read_text()
    body = core[core.index("const ROLES = {"):core.index("};", core.index("const ROLES = {"))]
    out = {}
    for m in re.finditer(r"^\s*(\w+): \{ name: '[^']*', color: '(#[0-9a-f]{6})'(?:, pill: '(#[0-9a-f]{6})')? \}", body, re.M):
        out[m.group(1)] = (m.group(2), m.group(3))
    return out


def _ink() -> dict:
    m = re.search(r"const ROLE_INK = \{([^}]*)\}", (WEB / "js" / "20-core.js").read_text())
    return dict(re.findall(r"(\w+): '(#[0-9a-f]{6})'", m.group(1)))


def test_the_main_colour_is_sky_blue_and_its_pill_reads():
    roles, ink = _roles(), _ink()
    assert roles["main"] == (MAIN, MAIN_PILL), roles["main"]   # the body stays sky blue; the pill is its own, darker
    assert "main" not in ink, ink                               # white text on the main pill, no dark ink
    assert _contrast("#ffffff", MAIN_PILL) >= 4.5


def test_the_old_dark_ink_does_not_come_back():
    hits = [f"{p.name}:{n}" for p in sorted(WEB.rglob("*")) if p.is_file() and p.suffix in (".js", ".css", ".html")
            and "vendor" not in p.parts for n, line in enumerate(p.read_text(errors="replace").splitlines(), 1)
            if OLD_INK in line.lower()]
    assert hits == [], hits


def test_every_pill_reads_and_every_body_stays():
    roles, ink = _roles(), _ink()
    assert {r: color for r, (color, _) in roles.items()} == BODIES, roles
    ratios = {r: round(_contrast(pill or color, ink.get(r, "#ffffff")), 2) for r, (color, pill) in roles.items()}
    assert all(c >= 4.5 for c in ratios.values()), ratios


def test_no_role_is_let_off_the_contrast():
    """The 4.5:1 arms name no role to skip (2.3.6: five were, until the requester said 「全部直す」). A set of roles let off,
    or an `or` on the contrast check, is red here even while the e2e would pass with it."""
    for path in (Path(__file__), E2E):
        text = path.read_text()
        assert ("KNOWN" + "_BELOW") not in text and ("BELOW" + " =") not in text, path.name   # split so this line is not a hit
    e2e = E2E.read_text()
    assert e2e.count("c >= INK_CONTRAST") == 1 and "c >= INK_CONTRAST," in e2e, "the e2e's contrast check is bare"


def test_every_pill_takes_the_one_source():
    core = (WEB / "js" / "20-core.js").read_text()
    assert "--c:${ROLES[role].pill || ROLES[role].color};--t:${ROLE_INK[role] || '#ffffff'}" in core
    assert "const pillBg = (role) => ROLES[role].pill || ROLES[role].color;" in core
    scene = (WEB / "js" / "40-scene.js").read_text()
    # the canvas pills are drawRolePill's; no other canvas fills a pill with the role's colour and inks it
    calls = len(re.findall(r"(?<!function )drawRolePill\(ctx, role, ", scene))
    assert "ROLE_INK" not in scene and calls == 2, calls


def test_no_old_orange_is_left_for_the_main_robot():
    hits = []
    for path in sorted(WEB.rglob("*")):
        if path.is_file() and path.suffix in (".js", ".css", ".html") and "vendor" not in path.parts:
            for n, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                if "ff7a3d" in line.lower() and "confetti" not in line and "G.ball" not in line:
                    hits.append(f"{path.name}:{n}: {line.strip()[:120]}")
    assert hits == [], hits
