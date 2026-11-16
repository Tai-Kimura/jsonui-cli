"""The talk's received bubble has its own colours (2.3.8, ticket 2026-10-20-jui-viz-talk-bubble-colours; requester 10-20:
「トークの吹き出しの色が背景とどうかしててわかりづらい」「相手側ね」), and the sent bubble is left as it was.

From app.css: every --talk-in-* token in the three theme places (:root, the dark media query, [data-theme=dark]), the
two dark ones equal; in each theme the received bubble's text, link and code 4.5:1 or more on their grounds, the bubble
3:1 or more on the panel by its fill or its edge, and apart from the sent bubble by its fill or its edge (ΔE2000 ≥ 8 on
either: light's fill is the requester's sample A, 5.9 from the sent fill, so its grey edge, 14.1 from the blue, does it). The sent and
the undelivered bubbles' rules are the base's, word for word. The rendered colours are measured by
tools/viz_e2e/talk_ui.py (--only talk-ui).
"""
from __future__ import annotations

import math
import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "jui_cli" / "viz" / "web"
CSS = (WEB / "app.css").read_text(encoding="utf-8")
NAMES = ("bg", "edge", "ink", "soft", "link", "code-bg", "line", "warn")
SENT_RULES = (
    ".talk-out .talk-bubble { border: 1px solid var(--info); border-top-right-radius: 4px; background: var(--info-bg); color: var(--ink); }",
    ".talk-out .talk-bubble.talk-undelivered { border: 1px dashed var(--bad); background: var(--bad-bg); }",
)
# the page's tokens the sent bubble and the panel read, per theme (light, dark) — the base's values
BASE = {"panel": ("#fbfcfe", "#111f34"), "info": ("#2a62c9", "#86b8ff"), "info-bg": ("#dde8fb", "#15305a"), "ink": ("#13233a", "#e4ecf8")}


def _lum(h):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(int(h[i:i + 2], 16)) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    x, y = sorted([_lum(a), _lum(b)])
    return (y + 0.05) / (x + 0.05)


def _lab(h):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(int(h[i:i + 2], 16)) for i in (1, 3, 5))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116   # noqa: E731
    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def _de2000(c1, c2):
    L1, a1, b1 = _lab(c1)
    L2, a2, b2 = _lab(c2)
    C1, C2 = math.hypot(a1, b1), math.hypot(a2, b2)
    Cb = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cb ** 7 / (Cb ** 7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p, h2p = math.degrees(math.atan2(b1, a1p)) % 360, math.degrees(math.atan2(b2, a2p)) % 360
    dL, dC = L2 - L1, C2p - C1p
    dh = 0 if C1p * C2p == 0 else (h2p - h1p if abs(h2p - h1p) <= 180 else h2p - h1p - 360 if h2p > h1p else h2p - h1p + 360)
    dH = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dh / 2))
    Lb, Cbp = (L1 + L2) / 2, (C1p + C2p) / 2
    hb = h1p + h2p if C1p * C2p == 0 else ((h1p + h2p) / 2 if abs(h1p - h2p) <= 180 else (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2)
    T = 1 - 0.17 * math.cos(math.radians(hb - 30)) + 0.24 * math.cos(math.radians(2 * hb)) + 0.32 * math.cos(math.radians(3 * hb + 6)) - 0.20 * math.cos(math.radians(4 * hb - 63))
    SL = 1 + 0.015 * (Lb - 50) ** 2 / math.sqrt(20 + (Lb - 50) ** 2)
    SC, SH = 1 + 0.045 * Cbp, 1 + 0.015 * Cbp * T
    RT = -2 * math.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7)) * math.sin(math.radians(60 * math.exp(-(((hb - 275) / 25) ** 2))))
    return math.sqrt((dL / SL) ** 2 + (dC / SC) ** 2 + (dH / SH) ** 2 + RT * (dC / SC) * (dH / SH))


def _token(name):
    return re.findall(rf"--{re.escape(name)}:\s*(#[0-9a-fA-F]{{6}})\s*;", CSS)


def _themes():
    out = {}
    for n in NAMES:
        v = _token(f"talk-in-{n}")
        assert len(v) == 3 and v[1] == v[2], (n, v)        # :root, the dark media query, [data-theme=dark]
        out[n] = (v[0].lower(), v[1].lower())
    return out


def test_the_received_bubble_reads_in_both_themes():
    t = _themes()
    for k in (0, 1):
        bg = t["bg"][k]
        assert _contrast(t["ink"][k], bg) >= 4.5 and _contrast(t["soft"][k], bg) >= 4.5 and _contrast(t["link"][k], bg) >= 4.5, (k, t)
        assert _contrast(t["ink"][k], t["code-bg"][k]) >= 4.5 and _contrast(t["warn"][k], t["code-bg"][k]) >= 4.5, (k, t)
        panel = BASE["panel"][k]
        assert max(_contrast(bg, panel), _contrast(t["edge"][k], panel)) >= 3.0, (k, bg, t["edge"][k])
        de_fill, de_edge = _de2000(bg, BASE["info-bg"][k]), _de2000(t["edge"][k], BASE["info"][k])
        assert max(de_fill, de_edge) >= 8.0, (k, bg, round(de_fill, 1), t["edge"][k], round(de_edge, 1))


def test_the_received_bubble_takes_the_tokens():
    assert ".talk-in .talk-bubble { border: 1px solid var(--talk-in-edge); border-top-left-radius: 4px; background: var(--talk-in-bg); color: var(--talk-in-ink); }" in CSS
    assert ".talk-in .talk-bubble .h-md a, .talk-in .talk-bubble .talk-more { color: var(--talk-in-link); }" in CSS
    assert ".talk-in .talk-bubble .h-md code, .talk-in .talk-bubble .h-code { background: var(--talk-in-code-bg); color: var(--talk-in-ink); }" in CSS


def test_the_sent_bubble_is_as_it_was():
    for rule in SENT_RULES:
        assert CSS.count(rule) == 1, rule
    assert not re.search(r"\.talk-out[^{]*\{[^}]*--talk-in", CSS)
    for name, want in BASE.items():
        got = tuple(v.lower() for v in _token(name))
        assert got == (want[0], want[1], want[1]), (name, got)


# The chosen values, per theme (light, dark). Dark went one step darker after the requester saw it (10-20: 「ダークモード
# もう少しくらい色がいいな」): #e5e7eb → slate-300 #cbd5e1, the link, soft text, code ground, lines and error with it.
# Light then took the requester's sample A (「ライトはAでいいよ」): #ffffff → #e8ecf1, the text #13233a, code #d5dbe3, the
# grey edge kept (the orchestrator).
# Dark then took the requester's sample C (ticket 2026-10-20-jui-viz-talk-bubble-dark-v2, 「トークのデザインはCで」): a navy a
# little deeper than the sent bubble, white text, a violet edge.
CHOSEN = {"bg": ("#e8ecf1", "#0f2747"), "edge": ("#6b7a90", "#c4b5fd"), "ink": ("#13233a", "#ffffff"),
          "soft": ("#4b5563", "#cbd5e1"), "link": ("#1d4ed8", "#93c5fd"), "code-bg": ("#d5dbe3", "#0a1a33"),
          "line": ("#c9d1dc", "#2f4a72"), "warn": ("#9a3412", "#fdba74")}


def test_the_tokens_are_the_chosen_ones():
    assert _themes() == CHOSEN, _themes()
