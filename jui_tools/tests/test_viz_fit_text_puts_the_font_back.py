"""40-scene.js's fitText draws words a language says longer smaller before it cuts them (shrinkToFit), and puts the
caller's font back after it draws: the next words on the same canvas are drawn at the size their drawer set, not at
the size the last fit reached (ticket 2026-10-21-viz-english-screen-checks). The functions cut out and run in node
with a stand-in context (a word's width: 0.6 of the font's px a letter)."""
from __future__ import annotations

from tests.test_viz_hist_card_off import _cut, _node

CTX = """const drawn = [];
const ctx = { font: 'bold 20px Body', fillText(t, x, y) { drawn.push([t, this.font]); },
  measureText(t) { return { width: [...t].length * 0.6 * Number(/(\\d+(?:\\.\\d+)?)px/.exec(this.font)[1]) }; } };"""


def _parts():
    return [CTX, _cut("40-scene.js", "shrinkToFit"), _cut("40-scene.js", "fitText")]


def test_words_that_fit_are_drawn_at_their_size():
    assert _node(_parts(), "(() => { fitText(ctx, 'Short', 0, 0, 200); return [drawn, ctx.font]; })()") == [
        [["Short", "bold 20px Body"]], "bold 20px Body"]


def test_longer_words_are_drawn_smaller_and_the_font_is_put_back():
    got = _node(_parts(), "(() => { fitText(ctx, 'Implemented, waiting', 0, 0, 200); const after = ctx.font;"
                          " ctx.fillText('next', 0, 0); return [drawn, after]; })()")
    (words, font), nxt = got[0][0], got[0][1]
    assert words == "Implemented, waiting" and font != "bold 20px Body" and font.startswith("bold ") and font.endswith("px Body")
    assert 15 <= int(font.split()[1][:-2]) < 20                       # smaller, not below 72% (15 of 20)
    assert got[1] == "bold 20px Body" and nxt == ["next", "bold 20px Body"]


def test_words_past_the_floor_are_cut_at_the_floor_and_the_font_is_put_back():
    got = _node(_parts(), "(() => { fitText(ctx, 'Written, waiting for implementation', 0, 0, 200); return [drawn, ctx.font]; })()")
    (words, font), = got[0]
    assert words.endswith("…") and font == "bold 15px Body" and got[1] == "bold 20px Body"
