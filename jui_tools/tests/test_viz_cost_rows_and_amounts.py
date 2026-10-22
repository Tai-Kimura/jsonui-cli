"""The cost view's day rows and the page's one rule for an amount (the requester 10-23: 「長い文章だと棒グラフの中に入り切らずに
...になってる / 全文見るために広げるのボタンが欲しい」「文字とグラフは縦並びにして」; the amounts' digits made one rule).

usdText (20-core.js), srcUsd and srcRow (56-server-cost.js) and billMoney (54-bills.js) are cut out of the page and run
in node with the page's state stood in. The e2e (tools/viz_e2e/cost_rows.py) draws a room's day: the words cut at two
lines, 広げる by the keyboard, the page's width at 390.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

from tests.test_viz_bundle import _match, web_text

STAND_IN = """
const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
const SRC = { open: new Set(), fill: {} };
const SRC_PER = { second: 'sec', minute: 'min', hour: 'h', day: 'day', month: 'mo' };
const SRC_COLORS = ['#4e79a7', '#f28e2b', '#59a14f', '#e15759'];
const srcNum = (v) => String(v);
const srcRate = (rate) => (rate ? `${srcNum(rate.value)}/${SRC_PER[rate.per] || rate.per}` : '');
const srcRunning = () => '';
const seg = (label, usd, value) => ({ label, usd, rate: { value, per: 'day' } });
const NODE = { node: 'llm', label: 'Anthropic', hours: [{ usd: 15.87, segments: [
  seg('リクエスト', 0, 294110), seg('入力トークン（claude-haiku-5-5）', 1.2234, 291679360),
  seg('入力トークン（claude-haiku-5-5-batch）', 0.0007, 280592000), seg('出力トークン（claude-haiku-5-5）', null, 89675840)] }] };
"""


def _cut(src: str, name: str) -> str:
    start = re.search(rf"\nfunction {name}\(", src).start() + 1
    return src[start:_match(src, src.index("{", start)) + 1]


def _run(body: str):
    node = shutil.which("node")
    assert node, "node is needed (the jui_tools job has it; a skip would hide the arm)"
    core, cost, bills = web_text("js", "20-core.js"), web_text("js", "56-server-cost.js"), web_text("js", "54-bills.js")
    ja = web_text("i18n", "ja.json")
    tl = f"const JA = {ja};\nconst tl = (k, p = {{}}) => JA[k].replace(/\\{{(\\w+)\\}}/g, (m, n) => (n in p ? String(p[n]) : m));\n"
    parts = [_cut(core, "usdText"), _cut(cost, "srcUsd"), _cut(cost, "srcSegText"), _cut(cost, "srcRow"), _cut(bills, "billMoney")]
    out = subprocess.run([node, "-"], input=tl + STAND_IN + "\n".join(parts) + f"\nprocess.stdout.write(JSON.stringify({body}));",
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_an_amount_is_to_the_cent_and_under_a_cent_says_so():
    got = _run("[15.87, 0.7852, 0.4374, 0.0828, 0.02, 0.013, 0.0061, 0.0007, 0, 0.995, 1234.5].map((v) => usdText(v))")
    assert got == ["$15.87", "$0.79", "$0.44", "$0.08", "$0.02", "$0.01", "< $0.01", "< $0.01", "$0.00", "$1.00", "$1,234.50"]


def test_a_difference_keeps_its_sign_under_a_cent_too():
    got = _run("[[-0.25, true], [0.25, true], [-0.0007, true], [0.0007, true], [0, true], [-0.0007, false], [-3, false]].map(([v, s]) => usdText(v, s))")
    assert got == ["−$0.25", "+$0.25", "−(< $0.01)", "+(< $0.01)", "$0.00", "−(< $0.01)", "−$3.00"]


def test_the_cost_view_and_the_bill_use_the_one_rule():
    got = _run("{ cost: [0.7852, 0.0007, 0, null].map(srcUsd), bill: [0.004, 0.7852, 12.345, 150.4].map(billMoney) }")
    assert got["cost"] == ["$0.79", "< $0.01", "$0.00", "単価なし"]
    assert got["bill"] == ["< $0.01", "≈ $0.79", "≈ $12.35", "≈ $150"]


def test_a_row_is_its_bar_over_every_meters_words_folded_with_its_button():
    got = _run("""(() => { const folded = srcRow(NODE, 0, 20, 3); SRC.open.add('llm'); const open = srcRow(NODE, 0, 20, 3);
      return { folded, open }; })()""")
    for html in got.values():
        bar = re.search(r'<div class="src-bar">(.*?)</div>', html).group(1)
        assert re.sub(r"<[^>]+>", "", bar) == "", f"the bar holds no words: {bar}"
        assert bar.count('class="src-seg"') == 4
        parts = re.search(r'<div class="src-parts[^"]*" id="src-parts-3" data-src-parts>(.*?)</div>', html).group(1)
        words = re.sub(r"<[^>]+>", "", parts)
        assert words.index("リクエスト") < words.index("claude-haiku-5-5）") < words.index("batch") < words.index("出力トークン")
        assert "単価なし" in words and "&lt; $0.01" in words and "$1.22" in words, words
        assert html.index('class="src-bar"') < html.index("data-src-parts") < html.index('<button type="button" class="src-more"'), \
            "the bar over its words, the button on their lower edge"
    # the row's bar is its amount against the hour's dearest (max 20 here), its meters share the row's own length
    fill = re.search(r'class="src-fill src-some" data-src-fill="([\d.]+)"', got["folded"])
    assert fill and abs(float(fill.group(1)) - 15.87 / 20 * 100) < 1e-3, fill and fill.group(1)
    widths = [float(w) for w in re.findall(r'class="src-seg"[^>]*style="width:([\d.]+)%', got["folded"])]
    assert abs(widths[1] - 1.2234 / 15.87 * 100) < 1e-3 and widths[0] == 0 and widths[3] == 0, widths
    assert 'class="src-parts" ' in got["folded"] and 'aria-expanded="false"' in got["folded"] and ">▼ 内訳を全部見る</button>" in got["folded"]
    assert re.search(r'data-src-more="llm" aria-controls="src-parts-3" aria-expanded="false" hidden>', got["folded"]), \
        "folded, the button waits for the words to be measured as cut"
    assert 'class="src-parts open"' in got["open"] and 'aria-expanded="true">▲ 内訳をたたむ</button>' in got["open"]


def test_the_folded_words_are_two_lines_and_the_room_fits_a_phone():
    css = web_text("app.css")
    folded = re.search(r"\n\.src-parts \{([^}]*)\}", css).group(1)
    assert "-webkit-line-clamp: 2" in folded and "overflow: hidden" in folded
    assert "-webkit-line-clamp: unset" in re.search(r"\n\.src-parts\.open \{([^}]*)\}", css).group(1)
    assert "grid-template-columns: minmax(0, 1fr)" in re.search(r"\n\.srm \{([^}]*)\}", css).group(1), \
        "the server room is the page's width (a phone: its header's longest select made it 629 on 390)"
