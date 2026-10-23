"""What is selected looks selected (2.3.20, requester 10-22: 「トークのタブどっち選択してるのかわからない」「メニューのコストと3Dも
今どっちが選択されてるかわからない」). Runs with `--only selected-look`.

The family: every control of the page that shows a state of its own by aria-pressed, aria-selected, aria-checked or
aria-current (MEMBERS; test_viz_selected_look.py keeps the list whole against the page's sources). On the demo page,
light and dark, each is read in place where the page has it (the talk's tabs with the talk open, the card's with the
card open) and, where the demo does not draw it (the cost page's account pair, the room's legend, the spec board's
lists and the data sheet's tabs, the project list), made once with the page's own classes inside the part of the page it
lives in. Its state is set to on and to off, and the computed styles of both are compared:

  * on and off apart: the fills (each over what is behind it) SELECT_MIN:1 or more apart, or the on state has a mark of
    its own (an edge or an inset ring at least MARK_PX wide) SELECT_MIN:1 or more on its fill — WCAG 1.4.11's 3:1 for
    a state shown without text;
  * the on state readable: its text TEXT_MIN:1 or more on its fill;
  * a switch (role=switch) by its knob (::before): on and off SELECT_MIN:1 apart.

And the state the page sets is the state drawn: the talk's ロボット一覧 pressed moves aria-selected and the on look with
it; the room's コスト pressed moves aria-pressed and the on look from 3D to コスト, and 3D moves them back.

A browser that kept an old app.css (10-22: the requester's ran 2.3.19's app.js with 2.3.13's app.css — the tabs alike,
the cost page dark, measured by the lane that looked into the cost page): the real server (make_app, in this process),
its page in a browser that answers the plain /app.css with 2.3.13's (as a kept copy would be answered). The page must
not use it: the cost page (.sr-cost, from 2.3.14) laid over the stage and the talk's tabs drawn as tabs.
"""
from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, new_page, ready
from talk_ui import open_card, open_talk
from waits import WaitTimeout, until

SELECT_MIN = 3.0
TEXT_MIN = 4.5
MARK_PX = 2.0

# key, words, where it is (a selector in the page), its state, the part of the page a made one goes in, the made one
MEMBERS = [
    ("talk-tab", "トーク: トーク履歴・ロボット一覧", "#rb .talk-tab", "aria-selected", None, None),
    ("sr-mode", "サーバールーム: 3D・コスト", "#sr-mode-cost", "aria-pressed", None, None),
    ("sr-acct", "コスト: アカウント全体・この環境だけ", None, "aria-pressed", "#sr",
     '<span class="sr-ctl sr-mode"><button type="button" class="wb-btn">x</button><button type="button" class="wb-btn">y</button></span>'),
    ("sr-board", "サーバールーム: ボード", "#sr-board-btn", "aria-pressed", None, None),
    ("sr-log", "サーバールーム: ログ", "#sr-log-btn", "aria-pressed", None, None),
    ("sr-boxzoom", "サーバールーム: 範囲で寄る", "#sr-boxzoom", "aria-pressed", None, None),
    ("sr-reach", "サーバールーム: つながっている物を全部見せる", None, "aria-pressed", "#sr-board",
     '<p class="sr-acts"><button type="button" class="wb-btn sr-reach">x</button></p>'),
    ("sr-mig", "サーバールーム: 移管計画の再生", None, "aria-pressed", "#sr-board",
     '<ul><li><button type="button" class="wb-btn" data-sr-mig="x">x</button></li></ul>'),
    ("sr-prov", "サーバールーム: 凡例のクラウド", None, "aria-pressed", "#sr-board",
     '<ul class="sr-legend"><li><button type="button" class="sr-prov">aws</button></li></ul>'),
    ("seg-sess", "セッションの絞り込み", "#sess-filter button", "aria-pressed", None, None),
    ("seg-spec", "spec の進み具合の絞り込み", "#spec-filter button", "aria-pressed", None, None),
    ("log-cat", "ログの種類", "#log-cats .fbtn", "aria-pressed", None, None),
    ("rb-tab", "カード: 今・応答の履歴", "#rb .rb-tabs [data-rb-tab]", "aria-selected", None, None),
    ("rb-talk", "カード: トーク", "#rb [data-rb-talk]", "aria-pressed", None, None),
    ("rb-wide", "カード: 広げる", "#rb [data-rb-wide]", "aria-pressed", None, None),
    ("floor", "ビル全体", "#floor-building.fn-btn", "aria-pressed", None, None),
    ("weather", "近所の天気（スイッチ）", "#weather-switch.tw-switch", "aria-checked", None, None),
    ("weather-panel", "近所の天気（パネルのスイッチ）", "#weather-switch-panel", "aria-checked", None, None),
    ("bill", "お札（スイッチ）", "#bill-switch", "aria-checked", None, None),
    ("play", "デモ: 一時停止", ".controls #btn-play", "aria-pressed", None, None),
    ("pop-option", "プロジェクトの一覧", None, "aria-selected", "body",
     '<div class="pop" style="visibility:hidden"><ul class="pop-list"><li role="option">x</li></ul></div>'),
    ("roster-row", "この部屋のロボット: 今選んでいるロボット", None, "aria-current", "#roster",
     '<ul class="roster-list"><li class="roster-row"><input type="checkbox" class="roster-check" checked>'
     '<button type="button" class="roster-name"><span class="roster-nm">x</span></button><span class="roster-lamp"></span></li></ul>'),
    ("ws-item", "spec ボード: 一覧の今の spec", None, "aria-current", "#wb-side",
     '<button type="button" class="ws-item"><span class="dot"></span><span class="nm">x</span><span></span></button>'),
    ("ws-apps", "spec ボード: アプリの絞り込み", None, "aria-pressed", "#wb-side",
     '<div class="seg-filter ws-apps"><button type="button">x</button></div>'),
    ("ds-tab", "API・DB の札: タブ", None, "aria-selected", "#wb-body",
     '<button type="button" role="tab" class="ds-tab">x<b>1</b></button>'),
    ("flow-zoom", "データの流れ: 合わせる・実寸", None, "aria-pressed", "#wb-body",
     '<div class="flow-mmd-wrap"><div class="flow-mmd-bar"><button type="button" class="wb-btn" data-flow-zoom>x</button></div></div>'),
]

# Where the page gives each member its state: every line of index.html and web/js/ that sets aria-pressed, -selected,
# -checked or -current holds one of these (test_viz_selected_look.py), and each of these is on such a line.
SOURCES = {
    "talk-tab": ["TALK.tab === k"],
    "sr-mode": ["sr-mode-3d", "sr-mode-cost"],
    "sr-acct": ['data-src-act="acct-on"'],
    "sr-board": ["sr-board-btn", "$(btn).setAttribute('aria-pressed'"],
    "sr-log": ["sr-log-btn"],
    "sr-boxzoom": ["sr-boxzoom"],
    "sr-reach": ['data-sr-act="reach"'],
    "sr-prov": ['class="sr-prov"'],
    "sr-mig": ['data-sr-mig="${esc(m.name)}"'],
    "seg-sess": ["sessFilter"],
    "seg-spec": ["specFilter"],
    "log-cat": ['class="fbtn"', "function toggleIn(set, key, btn)"],
    "rb-tab": ["b.dataset.rbTab === HIST.tab", 'data-rb-tab="now"'],
    "rb-talk": ["data-rb-talk", "String(TALK.on)"],
    "rb-wide": ["data-rb-wide", "String(HIST.wide)"],
    "floor": ["floor-building", "TOWER.on"],
    "weather": ['id="weather-switch"', "w.on ? 'true'"],
    "weather-panel": ["weather-switch-panel"],
    "bill": ["bill-switch", "BILL.on"],
    "play": ["btn-play"],
    "pop-option": ['<li role="option"'],
    "ws-item": ['class="ws-item'],
    "roster-row": ["r.key === current"],
    "ws-apps": ["seg-filter ws-apps"],
    "ds-tab": ['class="ds-tab"'],
    "flow-zoom": ["data-flow-zoom", "String(wb.flowFit)"],
}
# lines that read a state and set none
READS = ["popEl.querySelector('[role=\"option\"][aria-selected=\"true\"]')",
         # the side list finds the open spec's row to bring it into view (wbSideShowOpen): its look is .ws-item's
         "wbSideList.querySelector('.ws-item[aria-current=\"true\"]')",
         # the room's list finds the selected robot's row to bring it into view (rosterShowCurrent): its look is the row's
         "list.querySelector('.roster-row[aria-current=\"true\"]')"]

READ = """([sel, attr, home, made]) => {
  let el = sel ? document.querySelector(sel) : null, wrap = null;
  if (!el && made) {
    wrap = document.createElement('div'); wrap.dataset.e2eMade = ''; wrap.innerHTML = made;
    (document.querySelector(home) || document.body).appendChild(wrap);
    el = wrap.querySelector('[data-flow-zoom], .sr-prov, [role=option], .ws-item, .ds-tab, .roster-row, button');
  }
  if (!el) return null;
  const parse = (s) => { const m = s.match(/rgba?\\(([^)]+)\\)/); if (!m) return [0, 0, 0, 0]; const v = m[1].split(/[ ,\\/]+/).filter(Boolean).map(Number); return [v[0], v[1], v[2], v.length > 3 ? v[3] : 1]; };
  const over = (top, under) => { const a = top[3]; return [0, 1, 2].map((i) => top[i] * a + under[i] * (1 - a)).concat(1); };
  const ground = (n) => { const stack = []; for (let x = n; x; x = x.parentElement) { const c = parse(getComputedStyle(x).backgroundColor); if (c[3] > 0) stack.push(c); if (c[3] >= 1) break; }
    let g = parse(getComputedStyle(document.body).backgroundColor); if (g[3] < 1) g = [255, 255, 255, 1];
    for (let i = stack.length - 1; i >= 0; i--) g = over(stack[i], g); return g; };
  const isSwitch = el.getAttribute('role') === 'switch';
  const was = el.getAttribute(attr), out = {};
  for (const v of ['true', 'false']) {
    el.setAttribute(attr, v);
    const cs = getComputedStyle(el), k = isSwitch ? getComputedStyle(el, '::before') : null;
    const behind = ground(el.parentElement || document.body), fill = over(parse(cs.backgroundColor), behind);
    const marks = [];
    for (const side of ['Top', 'Right', 'Bottom', 'Left']) { const w = parseFloat(cs['border' + side + 'Width']) || 0; if (w > 0 && cs['border' + side + 'Style'] !== 'none') marks.push({ at: side, w, c: over(parse(cs['border' + side + 'Color']), fill) }); }
    for (const part of (cs.boxShadow === 'none' ? [] : cs.boxShadow.split(/,(?![^(]*\\))/))) {
      if (!/inset/.test(part)) continue; const c = parse(part); const px = (part.replace(/rgba?\\([^)]*\\)/, '').match(/-?[\\d.]+px/g) || []).map((x) => Math.abs(parseFloat(x)));
      marks.push({ at: 'inset', w: Math.max(px[0] || 0, px[1] || 0, px[3] || 0), c: over(c, fill) });
    }
    out[v] = { fill, ink: over(parse(cs.color), fill), weight: cs.fontWeight, marks,
      knob: k ? over(parse(k.backgroundColor), fill) : null };
  }
  if (was === null) el.removeAttribute(attr); else el.setAttribute(attr, was);
  if (wrap) wrap.remove();
  return { made: !!wrap, switch: isSwitch, ...out };
}"""


def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def contrast(a, b):
    la, lb = (0.2126 * _lin(x[0]) + 0.7152 * _lin(x[1]) + 0.0722 * _lin(x[2]) for x in (a, b))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def judge(r: dict) -> dict:
    """The numbers for one member: on/off apart (fill, mark, knob), the on text on its fill."""
    on, off = r["true"], r["false"]
    fill = contrast(on["fill"], off["fill"])
    off_marks = {(m["at"], round(m["w"], 1), tuple(round(x) for x in m["c"][:3])) for m in off["marks"]}
    mark = max([contrast(m["c"], on["fill"]) for m in on["marks"]
                if m["w"] >= MARK_PX and (m["at"], round(m["w"], 1), tuple(round(x) for x in m["c"][:3])) not in off_marks] or [1.0])
    knob = contrast(on["knob"], off["knob"]) if r["switch"] else None
    apart = knob if r["switch"] else max(fill, mark)
    return {"fill": round(fill, 2), "mark": round(mark, 2), "knob": None if knob is None else round(knob, 2),
            "apart": round(apart, 2), "text": round(contrast(on["ink"], on["fill"]), 2), "made": r["made"]}


def check(failures, cond, text):
    if not cond:
        failures.append(f"selected-look: {text}")


async def read_all(page, stage_keys) -> dict:
    out = {}
    for key, _, sel, attr, home, made in MEMBERS:
        if key not in stage_keys:
            continue
        r = await page.evaluate(READ, [sel, attr, home, made])
        out[key] = None if r is None else {**judge(r), "raw": r}
    return out


OLD_CSS_TAG = "v2.3.13"
FRESH = """() => { const c = getComputedStyle(document.getElementById('sr-cost'));
  const t = document.createElement('button'); t.className = 'talk-tab'; document.body.appendChild(t); const r = getComputedStyle(t).borderTopLeftRadius; t.remove();
  return { cost: c.position, tab: r, css: [...document.querySelectorAll('link[rel=stylesheet]')].map((l) => new URL(l.href).pathname + new URL(l.href).search) }; }"""


async def stale_css(browser, watch, out, failures):
    """The page served by the real server, in a browser holding 2.3.13's app.css under the plain name."""
    from aiohttp import web
    jt = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(jt))
    from jui_cli.viz.config import VizConfig
    from jui_cli.viz.server import ServerContext, make_app
    from jui_cli.viz.state import VizState
    old = subprocess.run(["git", "-C", str(jt), "show", f"{OLD_CSS_TAG}:jui_tools/jui_cli/viz/web/app.css"],
                         capture_output=True, text=True, check=True).stdout
    check(failures, ".sr-cost {" not in old and ".talk-tab {" not in old, f"{OLD_CSS_TAG}'s app.css is the one before the cost page and the tabs")
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        port = so.getsockname()[1]
    ctx = ServerContext(config=VizConfig(), port=port, token="s" * 43, version="e2e", state=VizState(50))
    runner = web.AppRunner(make_app(ctx))
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()
    page = await browser.new_page(color_scheme="dark", **DESKTOP)
    try:
        held = []
        async def kept(route):
            held.append(route.request.url)
            await route.fulfill(status=200, content_type="text/css", body=old)
        await page.route(lambda u: u.endswith("/app.css"), kept)   # the plain name: what a kept copy answers
        await page.goto(f"http://127.0.0.1:{port}/")
        await page.wait_for_function("() => document.readyState === 'complete'")
        got = await page.evaluate(FRESH)
        check(failures, not held and got["cost"] == "absolute" and got["tab"] == "999px",
              f"a browser holding {OLD_CSS_TAG}'s app.css: the page used it ({got}, answered from the kept copy: {held})")
        return got
    finally:
        await page.close()
        await runner.cleanup()


ON = "(sel) => { const e = document.querySelector(sel); return e ? getComputedStyle(e).backgroundColor : null; }"


async def run_selected_look(pw, out, failures, Server):
    out = pathlib.Path(out) / "selected-look"
    out.mkdir(parents=True, exist_ok=True)
    srv = Server()
    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    watch = Watch(origin=srv.url)
    res: dict = {}
    t0 = time.monotonic()
    talk_keys = {"talk-tab"}
    card_keys = {"rb-tab", "rb-talk", "rb-wide"}   # 下を広げる left the family in 2.3.20: a disclosure on the cards box's edge (aria-expanded)
    try:
        for scheme in ("light", "dark"):
            page = await new_page(browser, watch, f"selected-look-{scheme}", color_scheme=scheme, **DESKTOP)
            try:
                await page.goto(f"{srv.url}/?demo=1&talkhold=1")
                await ready(page)
                await page.click("#btn-play")
                got = await read_all(page, {m[0] for m in MEMBERS} - talk_keys - card_keys)
                await open_card(page, "a0")
                got.update(await read_all(page, card_keys))
                await open_talk(page)
                got.update(await read_all(page, talk_keys))
                await page.locator("#rb .talk-head").screenshot(path=str(out / f"talk-{scheme}.png"))
                await page.locator("#rb .rb-head").screenshot(path=str(out / f"card-head-{scheme}.png"))
                # the state the page sets is the state drawn: ロボット一覧 pressed
                await page.click("#rb .talk-tab[data-tk-tab='robots']")
                await until(page, "() => document.querySelector(\"#rb .talk-tab[data-tk-tab='robots']\").getAttribute('aria-selected') === 'true'", "ロボット一覧 selected")
                sel_bg = await page.evaluate(ON, "#rb .talk-tab[aria-selected='true']")
                talks_bg = await page.evaluate(ON, "#rb .talk-tab[data-tk-tab='talks']")
                robots_bg = await page.evaluate(ON, "#rb .talk-tab[data-tk-tab='robots']")
                check(failures, robots_bg == sel_bg and talks_bg != robots_bg,
                      f"{scheme}: ロボット一覧 pressed carries the on look (talks {talks_bg}, robots {robots_bg})")
                await page.locator("#rb .talk-head").screenshot(path=str(out / f"talk-robots-{scheme}.png"))
                # the room's 3D / コスト: the header alone (the demo has no room), the state set by a press
                await page.evaluate("() => { const s = document.getElementById('sr'); s.hidden = false; s.style.opacity = '1'; }")
                await page.evaluate("() => document.getElementById('sr-mode-cost').click()")
                st = await page.evaluate("() => ['sr-mode-3d', 'sr-mode-cost'].map((i) => [document.getElementById(i).getAttribute('aria-pressed'), getComputedStyle(document.getElementById(i)).backgroundColor])")
                check(failures, st[1][0] == "true" and st[0][0] == "false" and st[0][1] != st[1][1],
                      f"{scheme}: コスト pressed carries aria-pressed and the on look ({st})")
                await page.locator("#sr .sr-head").screenshot(path=str(out / f"sr-head-cost-{scheme}.png"))
                await page.evaluate("() => document.getElementById('sr-mode-3d').click()")
                st2 = await page.evaluate("() => ['sr-mode-3d', 'sr-mode-cost'].map((i) => [document.getElementById(i).getAttribute('aria-pressed'), getComputedStyle(document.getElementById(i)).backgroundColor])")
                check(failures, st2[0][0] == "true" and st2[1][0] == "false" and st2[0][1] == st[1][1] and st2[1][1] == st[0][1],
                      f"{scheme}: 3D pressed takes the on look back ({st2})")
                res[scheme] = got
            except WaitTimeout as e:
                failures.append(f"selected-look: {scheme}: {e}")
            finally:
                await page.close()
        try:
            res["stale"] = await stale_css(browser, watch, out, failures)
        except Exception as e:   # noqa: BLE001 — named in the failures, the suites after it still run
            failures.append(f"selected-look: stale css: {type(e).__name__}: {e}")
        for scheme, got in res.items():
            if scheme == "stale":
                continue
            for key, words, *_ in MEMBERS:
                r = got.get(key)
                check(failures, r is not None, f"{scheme}: {key} ({words}) is not on the page")
                if r is None:
                    continue
                check(failures, r["apart"] >= SELECT_MIN,
                      f"{scheme}: {key} ({words}): on and off {r['apart']}:1 apart (fill {r['fill']}, mark {r['mark']}, knob {r['knob']}) < {SELECT_MIN}")
                if not r["knob"]:
                    check(failures, r["text"] >= TEXT_MIN, f"{scheme}: {key} ({words}): the on text {r['text']}:1 on its fill < {TEXT_MIN}")
    finally:
        await browser.close()
        srv.stop()
    for line in watch.console:
        failures.append(f"selected-look: console: {line}")
    (out / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    print(f"  selected-look: {time.monotonic() - t0:.0f}s", flush=True)
