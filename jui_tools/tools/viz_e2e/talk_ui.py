"""トーク: a robot's SendMessage conversations as a chat, the page side (2.3.6, requester 10-20). Runs with `--only talk-ui`.

The demo page (fake_server.py, ?demo=1&talkhold=1): its stand-in server (30-source-demo.js talkStandIn) answers the page's
talk.* requests from the demo data (31-talk-demo-data.js, generated frames): robot a0's talks with 4f (a long name), b4
(a long foldable body with a <script> in it), a peer outside this machine (undelivered), its subagent a3, and d8 (ended,
within the grace). The data's script — a new message (20 s), a read (30 s), a removal (45 s) — is played by the suite
(talkDemo.play). At 1440 px, light and dark; at 390 px, the detail fits.

Checked:
  * the chat button on the card shows the unread total of talk.badges (2 for a0);
  * the list: one row a peer, newest first, the unread count on a row, an ended peer marked;
  * no send UI anywhere in the talk (no input, textarea, select, editable, form, nothing that says 送), and every request
    the page sent is one of talk.open / talk.get / talk.seen / talk.close and conforms (talk_contract.validate);
  * the detail: the peer's bubbles left, a0's right, 既読 / 届いた / 届かなかった, a long text folded to three lines and
    opened / folded again by a press on the text;
  * a <script> in a body is text, never an element;
  * seen: the unread on screen go out as talk.seen, and the badge falls to what is left (2 → 1);
  * a new message while at the end shows at the bottom and is seen; a read turns 届いた into 既読;
  * paging: reading up asks talk.get with `before` and the older messages come in above;
  * the header: a long name is one line cut with …, its hover shows the whole name (57-fulltext.js); pressed, the card
    switches to that robot with the same talk open; a peer outside the machine is not a button and says この機械の外の相手;
  * a remove op takes the talk off the list (and out of the detail, with a note);
  * the received bubble's colours (2.3.8, ticket 2026-10-20-jui-viz-talk-bubble-colours; requester: 「相手側ね」), light and
    dark, from the computed styles: its text, a link in it (an <a> put into its rendered text), 全文を表示 and `code` (on
    the code's ground) 4.5:1 or more on it; the time under it 4.5:1 or more on what is behind it; the bubble 3:1 or more
    on the talk's ground, by its fill or its solid edge; apart from the sent bubble by its fill or its edge (ΔE2000 >=
    IN_OUT_DE on either; red only when both are close);
  * the sent bubble as it was (SENT, per theme), and the undelivered one still dashed in --bad;
  * the peers' marks (2.3.7, ticket 2026-10-20-jui-viz-talk-pill-contrast-and-version-comments), in the list and the
    header: each the pill's pair of its robot's role (as pill() draws it, __dbg.rolePills), white on main's #0369a1,
    every one 4.5:1 or more; and the demo phones' headers (drawPhoneUI, drawCartUI) per role: the pill's pair, >= 4.5:1.
Waits are on page state (waits.until); nothing is sampled on the wall clock.
"""

from __future__ import annotations

import json
import pathlib
import sys
import time

from common import DESKTOP, PHONE, LAUNCH_ARGS, Watch, new_page, ready
from waits import WaitTimeout, until
from workwear import contrast, de2000

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from jui_cli.viz import talk_contract  # noqa: E402

LONG_NAME = 'jsonui-agents-for-claude-4f-library-orchestrator-for-the-2.3.7-train'
SUB_NAME = 'サブエージェント a3（jsonui-define）'
T = "() => window.__dbg.talk()"
CARD = "(l) => (document.querySelector('#rb .rb-badge') || {}).textContent === l && !document.getElementById('rb').hidden && getComputedStyle(document.getElementById('rb')).opacity === '1' && !!document.querySelector('#rb [data-rb-talk]')"
SEND_UI = """() => { const t = document.querySelector('#rb [data-talk]'); if (!t) return null;
  return { fields: t.querySelectorAll('input, textarea, select, form, [contenteditable=""], [contenteditable="true"]').length,
    sendWords: [...t.querySelectorAll('button')].filter((b) => /送/.test(b.textContent + (b.getAttribute('aria-label') || ''))).map((b) => b.textContent),
    compose: [...document.querySelectorAll('#rb .h-compose')].filter((b) => b.getClientRects().length).length }; }"""
ROWS = """() => [...document.querySelectorAll('#rb .talk-row')].map((b) => ({ id: b.dataset.tkConv, name: b.querySelector('.talk-row-name').textContent,
  unread: (b.querySelector('[data-tk-unread]') || {}).textContent || '', gone: (b.querySelector('.talk-row-gone-note') || {}).textContent || '' }))"""
BUBBLES = """() => [...document.querySelectorAll('#rb [data-tk-msg]')].map((n) => { const r = n.querySelector('.talk-bubble').getBoundingClientRect();
  return { id: n.dataset.tkMsg, dir: n.classList.contains('talk-out') ? 'out' : 'in', l: Math.round(r.left), r: Math.round(r.right),
    state: (n.querySelector('[data-tk-state]') || {}).textContent || '' }; })"""
BADGE = "() => { const b = document.querySelector('#rb [data-rb-talk-n]'); return b ? (b.hidden ? '' : b.textContent) : null; }"
HEAD = """() => { const n = document.querySelector('#rb .talk-peer-name'), p = document.querySelector('#rb .talk-peer');
  if (!n) return null; const cs = getComputedStyle(n), r = n.getBoundingClientRect();
  return { text: n.textContent, cut: n.scrollWidth > n.clientWidth + 1, lines: Math.round(r.height / (parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.4)),
    button: p ? p.tagName === 'BUTTON' : false, switchable: !!document.querySelector('#rb [data-tk-peer]') }; }"""
FOLD = """() => { const t = [...document.querySelectorAll('#rb [data-tk-text]')].find((x) => x._long); if (!t) return null;
  return { folded: t.classList.contains('talk-folded'), h: Math.round(t.getBoundingClientRect().height), more: !t.parentNode.querySelector('[data-tk-more]').hidden }; }"""
COLORS = """() => { const o = document.querySelector('#rb .talk-out .talk-bubble'), i = document.querySelector('#rb .talk-in .talk-bubble');
  return { body: getComputedStyle(document.body).backgroundColor, out: o && getComputedStyle(o).backgroundColor, in: i && getComputedStyle(i).backgroundColor,
    ink: i && getComputedStyle(i).color }; }"""


BUBBLE_PAINT = """() => {
  const back = (el) => { for (let e = el; e; e = e.parentElement) { const c = getComputedStyle(e).backgroundColor; if (c && c !== 'rgba(0, 0, 0, 0)' && c !== 'transparent') return c; } return getComputedStyle(document.body).backgroundColor; };
  const one = (dir) => {
    const all = [...document.querySelectorAll(`#rb .talk-${dir} .talk-bubble:not(.talk-undelivered)`)];
    const n = all.find((x) => x.querySelector('.h-md code')) || all[0]; if (!n) return null;
    const cs = getComputedStyle(n), md = n.querySelector('.h-md');
    const a = document.createElement('a'); a.href = '#probe'; a.textContent = 'link'; md.appendChild(a); const link = getComputedStyle(a).color; a.remove();
    const code = n.querySelector('.h-md code'), more = n.querySelector('.talk-more'), at = n.parentElement.querySelector('.talk-at');
    return { bg: cs.backgroundColor, ink: cs.color, edge: cs.borderTopColor, edgeStyle: cs.borderTopStyle, edgeWidth: cs.borderTopWidth, back: back(n.parentElement), link,
      code: code ? { bg: getComputedStyle(code).backgroundColor, fg: getComputedStyle(code).color } : null,
      more: more ? getComputedStyle(more).color : null, at: at ? { fg: getComputedStyle(at).color, back: back(at) } : null };
  };
  const und = document.querySelector('#rb .talk-out .talk-bubble.talk-undelivered');
  return { in: one('in'), out: one('out'), undelivered: und ? { style: getComputedStyle(und).borderTopStyle, color: getComputedStyle(und).borderTopColor, bg: getComputedStyle(und).backgroundColor } : null };
}"""
# ΔE2000 between the received and the sent bubbles, on the fills or on the edges (either is enough). The fills alone
# were the first rule; the requester then picked light's sample A by name (#e8ecf1, 「ライトはAでいいよ」), 5.9 from the
# sent fill, and 8 was our own guide, so its grey edge against the sent blue edge (14.1) keeps them apart. Before the
# fix: fills 3.6 light, 4.2 dark. Dark's sample C (ticket 2026-10-20-jui-viz-talk-bubble-dark-v2): fills 3.8 apart by
# design (a navy a little deeper than the sent one), the violet edge against the sent blue 16.0.
IN_OUT_DE = 8.0
# the sent bubble, unchanged by the received bubble's colours (2.3.8): fill, text, edge, link, per theme
SENT = {"light": ("#dde8fb", "#13233a", "#2a62c9", "#2a62c9"), "dark": ("#15305a", "#e4ecf8", "#86b8ff", "#86b8ff")}
BAD = {"light": "#c62f3c", "dark": "#ff8590"}


def bubbles_read(paint, scheme, failures):
    i, o = paint.get("in"), paint.get("out")
    check(failures, bool(i and o), f"{scheme}: a received and a sent bubble to measure: {paint}")
    if not (i and o):
        return {}
    h = {k: rgb_hex(i[k]) for k in ("bg", "ink", "edge", "back", "link", "more")}
    m = {"text": contrast(h["ink"], h["bg"]), "link": contrast(h["link"], h["bg"]), "more": contrast(h["more"], h["bg"]),
         "code": contrast(rgb_hex(i["code"]["fg"]), rgb_hex(i["code"]["bg"])) if i["code"] else None,
         "time": contrast(rgb_hex(i["at"]["fg"]), rgb_hex(i["at"]["back"])) if i["at"] else None,
         "fill": contrast(h["bg"], h["back"]), "edge": contrast(h["edge"], h["back"]) if i["edgeStyle"] == "solid" and i["edgeWidth"] != "0px" else 0,
         "dE": de2000(h["bg"], rgb_hex(o["bg"])),
         "dEedge": de2000(h["edge"], rgb_hex(o["edge"])) if i["edgeStyle"] == "solid" and i["edgeWidth"] != "0px" else 0}
    m = {k: (round(v, 2) if v is not None else None) for k, v in m.items()}
    for k in ("text", "link", "more", "code", "time"):
        check(failures, m[k] is not None and m[k] >= 4.5, f"{scheme}: the received bubble's {k} reads: {m[k]}:1 ({h})")
    check(failures, max(m["fill"], m["edge"]) >= 3.0, f"{scheme}: the received bubble stands off the talk's ground: fill {m['fill']}:1, edge {m['edge']}:1 ({h})")
    check(failures, max(m["dE"], m["dEedge"]) >= IN_OUT_DE, f"{scheme}: the received bubble is apart from the sent one by its fill or its edge:"
          f" ΔE2000 fill {m['dE']} ({h['bg']} vs {rgb_hex(o['bg'])}), edge {m['dEedge']} ({h['edge']} vs {rgb_hex(o['edge'])})")
    sent = (rgb_hex(o["bg"]), rgb_hex(o["ink"]), rgb_hex(o["edge"]), rgb_hex(o["link"]))
    check(failures, sent == SENT[scheme], f"{scheme}: the sent bubble is as it was {SENT[scheme]}: {sent}")
    return m


def rgb_hex(css):
    nums = [int(float(x)) for x in css[css.index("(") + 1:css.index(")")].split(",")[:3]]
    return "#" + "".join(f"{n:02x}" for n in nums)


async def marks_read(page, scheme, r, failures, where, at_least):
    # every talk mark on the card now: its role's pill pair, 4.5:1 or more
    pairs = (await page.evaluate("() => window.__dbg.rolePills()"))["html"]
    marks = r.setdefault("marks", {})[where] = await page.evaluate("() => window.__dbg.talkMarks()")
    check(failures, len(marks) >= at_least and all(m["role"] for m in marks), f"{scheme}: {where}: the peers' marks ({len(marks)}): {marks}")
    for m in marks:
        if not m["role"]:
            continue
        want = (rgb_hex(pairs[m["role"]]["bg"]), rgb_hex(pairs[m["role"]]["fg"]))
        got = (rgb_hex(m["bg"]), rgb_hex(m["fg"]))
        m["contrast"] = round(contrast(got[1], got[0]), 2)
        check(failures, got == want, f"{scheme}: {where}: {m['label']}'s mark is its role's pill {want}: {got}")
        check(failures, m["contrast"] >= 4.5, f"{scheme}: {where}: {m['label']}'s mark reads: {m['contrast']}:1 {got}")
        if m["role"] == "main":
            check(failures, got == ("#0369a1", "#ffffff"), f"{scheme}: {where}: a main mark is #0369a1 / white: {got}")


def phone_heads_read(heads, pairs, failures, label, drawers):
    for name in drawers:
        check(failures, name in heads, f"{label}: the phone drawer {name} was probed: {list(heads)}")
        for role, h in heads.get(name, {}).items():
            want = (pairs[role]["bg"], pairs[role]["fg"])
            check(failures, (h.get("bg"), h.get("fg")) == want, f"{label}: {name}: {role}'s phone header is its pill's pair {want}: {h}")
            check(failures, bool(h.get("fg")) and contrast(h["fg"], h["bg"]) >= 4.5, f"{label}: {name}: {role}'s phone header reads: {h}")


def check(failures, cond, text):
    if not cond:
        failures.append(f"talk-ui: {text}")


async def run_talk_ui(pw, out, failures, Server):
    out = pathlib.Path(out) / "talk-ui"
    out.mkdir(parents=True, exist_ok=True)
    srv = Server()
    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    watch = Watch(origin=srv.url)
    res: dict = {}
    t0 = time.monotonic()
    try:
        for scheme in ("light", "dark"):
            r = res[scheme] = {}
            try:
                await one_scheme(browser, watch, srv.url, scheme, out, r, failures)
            except WaitTimeout as e:
                failures.append(f"talk-ui: {scheme}: {e}")
        try:
            await phone(browser, watch, srv.url, out, res, failures)
        except WaitTimeout as e:
            failures.append(f"talk-ui: phone: {e}")
        if res.get("light", {}).get("colors") and res.get("dark", {}).get("colors"):
            L, D = res["light"]["colors"], res["dark"]["colors"]
            check(failures, L["body"] != D["body"] and L["out"] != D["out"] and L["in"] != D["in"],
                  f"the bubbles follow the theme (light {L}, dark {D})")
    finally:
        await browser.close()
        srv.stop()
    for line in watch.console:
        failures.append(f"talk-ui: console: {line}")
    for u in watch.foreign:
        failures.append(f"talk-ui: request outside the server: {u}")
    (out / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    print(f"  talk-ui: {time.monotonic() - t0:.0f}s", flush=True)


async def open_card(page, label):
    await page.evaluate("(l) => document.querySelector(`#sessions [data-robot-open=\"${l}\"]`).click()", label)
    await until(page, CARD, f"{label}'s card", arg=label)


async def open_talk(page):
    await page.click("#rb [data-rb-talk]")
    await until(page, "() => { const t = window.__dbg.talk(); return t.on && Array.isArray(t.list) && document.querySelectorAll('#rb .talk-row').length === t.list.length && t.list.length > 0; }",
                "the talk list", why=T)


async def open_row(page, name, n_at_least=1):
    await page.evaluate("(n) => [...document.querySelectorAll('#rb .talk-row')].find((b) => b.querySelector('.talk-row-name').textContent === n).click()", name)
    await until(page, "([n, k]) => { const t = window.__dbg.talk(); const h = document.querySelector('#rb .talk-peer-name');"
                      " return t.conv && h && h.textContent === n && document.querySelectorAll('#rb [data-tk-msg]').length >= k; }",
                f"the talk with {name[:20]}", arg=[name, n_at_least], why=T)


async def one_scheme(browser, watch, url, scheme, out, r, failures):
    page = await new_page(browser, watch, f"talk-ui-{scheme}", color_scheme=scheme, **DESKTOP)
    await page.goto(f"{url}/?demo=1&talkhold=1")   # the demo data's script waits for talkDemo.play
    await ready(page)
    await page.click("#btn-play")   # the demo's script holds still; the talk does not depend on it
    await until(page, "() => window.__dbg.talk().badges.a0 === 2", "talk.badges on load (a0: 2)", why=T)
    await open_card(page, "a0")
    await until(page, "() => { const b = document.querySelector('#rb [data-rb-talk-n]'); return b && !b.hidden && b.textContent === '2'; }",
                "the chat button's badge 2", why=BADGE)
    r["badgeStart"] = await page.evaluate(BADGE)
    await page.screenshot(path=str(out / f"ui-after-card-{scheme}.png"))

    # the list
    await open_talk(page)
    rows = r["rows"] = await page.evaluate(ROWS)
    lst = (await page.evaluate(T))["list"]
    check(failures, [x["id"] for x in rows] == [x["id"] for x in lst] and len(rows) == 5, f"{scheme}: the rows are the list ({len(rows)})")
    names = [x["name"] for x in rows]
    check(failures, names == [LONG_NAME, "shop-app-signup", "cloud-reviewer", SUB_NAME, "shop-app-payment"], f"{scheme}: newest first: {names}")
    check(failures, [x["unread"] for x in rows] == ["1", "1", "", "", ""], f"{scheme}: unread on the rows: {[x['unread'] for x in rows]}")
    await marks_read(page, scheme, r, failures, "rows", 3)
    if scheme == "light":
        rp = await page.evaluate("() => window.__dbg.rolePills()")
        heads = r["phoneHeads"] = await page.evaluate("() => window.__dbg.phoneHeads()")
        phone_heads_read(heads, rp["canvas"], failures, f"{scheme}: demo", ("phoneUI", "cart"))
    check(failures, rows[-1]["gone"].startswith("終了"), f"{scheme}: the ended peer is marked: {rows[-1]['gone']!r}")
    no_send = r["noSend"] = await page.evaluate(SEND_UI)
    check(failures, no_send == {"fields": 0, "sendWords": [], "compose": 0}, f"{scheme}: no send UI in the talk: {no_send}")
    await page.screenshot(path=str(out / f"ui-after-list-{scheme}.png"))

    # the detail with b4: sides, states, the fold, the escaped <script>, seen
    await open_row(page, "shop-app-signup", 4)
    await marks_read(page, scheme, r, failures, "head", 1)
    bubbles = r["bubbles"] = await page.evaluate(BUBBLES)
    ins = [b for b in bubbles if b["dir"] == "in"]
    outs = [b for b in bubbles if b["dir"] == "out"]
    check(failures, len(ins) == 2 and len(outs) == 2, f"{scheme}: 2 in, 2 out: {len(ins)}, {len(outs)}")
    check(failures, ins and outs and max(b["l"] for b in ins) < min(b["l"] for b in outs) and max(b["r"] for b in ins) < max(b["r"] for b in outs),
          f"{scheme}: the peer's left, a0's right: {[(b['dir'], b['l'], b['r']) for b in bubbles]}")
    check(failures, outs and outs[0]["state"].startswith("既読") and outs[1]["state"] == "届いた", f"{scheme}: 既読 / 届いた: {[b['state'] for b in outs]}")
    await until(page, "() => { const t = [...document.querySelectorAll('#rb [data-tk-text]')].find((x) => x._long); return !!t; }", "the long text measured", why=FOLD)
    f1 = await page.evaluate(FOLD)
    await page.evaluate("() => { const t = [...document.querySelectorAll('#rb [data-tk-text]')].find((x) => x._long); t.querySelector('p, li').click(); }")
    f2 = await page.evaluate(FOLD)
    esc = r["escaped"] = await page.evaluate("() => { const t = document.querySelector('#rb [data-talk]'); return { scripts: t.querySelectorAll('script').length,"
                                             " text: [...t.querySelectorAll('[data-tk-text]')].some((x) => x.textContent.includes('<script>alert(1)</script>')) }; }")
    check(failures, esc == {"scripts": 0, "text": True}, f"{scheme}: a <script> in a body is text: {esc}")
    await page.evaluate("() => { const t = [...document.querySelectorAll('#rb [data-tk-text]')].find((x) => x._long); t.querySelector('p, li').click(); }")
    f3 = await page.evaluate(FOLD)
    r["fold"] = [f1, f2, f3]
    check(failures, f1 and f1["folded"] and f1["more"] and f2 and not f2["folded"] and f2["h"] > f1["h"] + 20 and f3 and f3["folded"] and f3["h"] == f1["h"],
          f"{scheme}: a long text folds to three lines and a press on it opens and folds it: {[f1, f2, f3]}")
    b4conv = (await page.evaluate(T))["conv"]
    await until(page, "(c) => window.__dbg.talk().sent.some((f) => f.type === 'talk.seen' && f.convId === c)", "talk.seen sent", arg=b4conv, why=T)
    await until(page, "() => { const b = document.querySelector('#rb [data-rb-talk-n]'); return b && !b.hidden && b.textContent === '1'; }",
                "the badge after seen (2 → 1)", why=BADGE)
    r["badgeAfterSeen"] = await page.evaluate(BADGE)
    r["colors"] = await page.evaluate(COLORS)
    r["paint"] = await page.evaluate(BUBBLE_PAINT)
    r["ratios"] = bubbles_read(r["paint"], scheme, failures)
    await page.screenshot(path=str(out / f"ui-after-detail-{scheme}.png"))

    # the script at 20 s: a new message while at the end shows at the bottom, and is seen
    await page.evaluate("() => window.__dbg.talkDemo.play(20)")
    await until(page, "() => document.querySelectorAll('#rb [data-tk-msg]').length === 5", "the new message", why=T)
    await until(page, "() => { const p = document.querySelector('#rb [data-tk-body]'); const last = [...p.querySelectorAll('[data-tk-msg]')].pop();"
                      " return last.textContent.includes('スクリーンショットを差し替えました') && p.scrollHeight - p.scrollTop - p.clientHeight < 30; }",
                "the new message in view at the bottom", why=T)
    await until(page, "() => (document.querySelector('#rb [data-rb-talk-n]') || {}).textContent === '1' && window.__dbg.talk().sent.filter((f) => f.type === 'talk.seen').length >= 2",
                "the new message seen (the badge back to 1)", why=T)
    # the script at 30 s: a0's message is read
    await page.evaluate("() => window.__dbg.talkDemo.play(30)")
    await until(page, "() => { const s = [...document.querySelectorAll('#rb .talk-out [data-tk-state]')].map((x) => x.textContent); return s.length === 2 && s.every((x) => x.startsWith('既読')); }",
                "既読 on the read message", why=BUBBLES)

    # the long name: one line with …, the whole on hover
    await page.click("#rb [data-tk-back]")
    await until(page, "() => document.querySelectorAll('#rb .talk-row').length === 5", "back on the list", why=T)
    await open_row(page, LONG_NAME, 1)
    head = r["longHead"] = await page.evaluate(HEAD)
    check(failures, head and head["cut"] and head["lines"] == 1 and head["button"], f"{scheme}: the long name is one line, cut: {head}")
    await page.hover("#rb .talk-peer-name")
    await until(page, "() => { const t = document.getElementById('fulltext'); return !!t && !t.hidden; }", "the hover tag on the long name")
    tag = await page.evaluate("() => document.getElementById('fulltext').textContent")
    check(failures, tag == LONG_NAME, f"{scheme}: the hover shows the whole name: {tag!r}")
    await page.screenshot(path=str(out / f"ui-after-longname-{scheme}.png"))
    await page.mouse.move(5, 5)

    # the script at 45 s: d8's talk is removed while it is open
    await page.click("#rb [data-tk-back]")
    await until(page, "() => document.querySelectorAll('#rb .talk-row').length === 5", "back on the list (2)", why=T)
    await open_row(page, "shop-app-payment", 2)
    d8conv = (await page.evaluate(T))["conv"]
    await page.evaluate("() => window.__dbg.talkDemo.play(45)")
    await until(page, "(c) => { const t = window.__dbg.talk(); return !t.conv && t.list.every((x) => x.id !== c) && document.querySelectorAll('#rb .talk-row').length === 4"
                      " && !!document.querySelector('#rb .talk-gone-note'); }", "the removed talk gone", arg=d8conv, why=T)
    r["removed"] = await page.evaluate(ROWS)
    await page.screenshot(path=str(out / f"ui-after-removed-{scheme}.png"))

    # a peer outside the machine: undelivered, not a button, said so
    await open_row(page, "cloud-reviewer", 1)
    ext = r["external"] = {"head": await page.evaluate(HEAD), "bubbles": await page.evaluate(BUBBLES),
                           "sub": await page.evaluate("() => document.querySelector('#rb .talk-peer-sub').textContent")}
    check(failures, ext["head"] and not ext["head"]["switchable"] and not ext["head"]["button"] and ext["bubbles"][0]["state"] == "届かなかった"
          and "この機械の外の相手" in ext["sub"], f"{scheme}: the outside peer: not a button, 届かなかった: {ext}")
    und = ext["undelivered"] = (await page.evaluate(BUBBLE_PAINT))["undelivered"]
    check(failures, bool(und) and und["style"] == "dashed" and rgb_hex(und["color"]) == BAD[scheme], f"{scheme}: an undelivered message keeps its red dashed edge: {und}")
    await page.click("#rb [data-tk-back]")
    await until(page, "() => document.querySelectorAll('#rb .talk-row').length === 4", "back on the list (3)", why=T)

    # paging: a page of one, read up → talk.get before
    await page.evaluate("() => window.__dbg.talkPage(1)")
    await open_row(page, SUB_NAME, 1)
    t = await page.evaluate(T)
    check(failures, t["msgs"] == 1 and t["more"] is True, f"{scheme}: the first page is 1 with more: {t['msgs']}, {t['more']}")
    await page.evaluate("() => { const p = document.querySelector('#rb [data-tk-body]'); p.scrollTop = 0; p.dispatchEvent(new Event('scroll')); }")
    await until(page, "() => window.__dbg.talk().msgs === 2 && document.querySelectorAll('#rb [data-tk-msg]').length === 2", "the older page", why=T)
    t = await page.evaluate(T)
    check(failures, any(f["type"] == "talk.get" and "before" in f for f in t["sent"]) and t["more"] is False, f"{scheme}: talk.get with before, then no more")
    await page.evaluate("() => window.__dbg.talkPage(30)")
    await page.click("#rb [data-tk-back]")
    await until(page, "() => document.querySelectorAll('#rb .talk-row').length === 4", "back on the list (4)", why=T)

    # the header: pressed, the card switches to the peer with the same talk
    await open_row(page, LONG_NAME, 1)
    conv = (await page.evaluate(T))["conv"]
    head = await page.evaluate(HEAD)
    check(failures, head and head["switchable"], f"{scheme}: the peer's name is a button: {head}")
    if head and head["switchable"]:
        await page.click("#rb [data-tk-peer]")
        try:
            await until(page, "(c) => { const t = window.__dbg.talk(); const h = document.querySelector('#rb .talk-peer-name');"
                              " return (document.querySelector('#rb .rb-badge') || {}).textContent === '4f' && t.owner === '4f' && t.conv === c && t.opened === '4f'"
                              " && h && h.textContent === 'shop-app-main' && document.querySelectorAll('#rb [data-tk-msg]').length === 1"
                              " && !!document.querySelector('#rb .talk-out'); }",
                        "switched to 4f on the same talk", arg=conv, why=T)
            await page.screenshot(path=str(out / f"ui-after-switched-{scheme}.png"))
        except WaitTimeout as e:
            failures.append(f"talk-ui: {scheme}: {e}")

    # every request the page sent: the four kinds only, each conforming to the contract
    sent = r["sent"] = (await page.evaluate(T))["sent"]
    kinds = sorted({f["type"] for f in sent})
    check(failures, set(kinds) <= {"talk.open", "talk.get", "talk.seen", "talk.close"} and {"talk.open", "talk.get", "talk.seen"} <= set(kinds),
          f"{scheme}: the requests sent: {kinds}")
    bad = [(f, p) for f in sent for p in [talk_contract.validate(f)] if p]
    check(failures, not bad, f"{scheme}: requests that break the contract: {bad[:3]}")
    await page.close()


async def phone(browser, watch, url, out, res, failures):
    page = await new_page(browser, watch, "talk-ui-phone", color_scheme="light", **PHONE)
    await page.goto(f"{url}/?demo=1&talkhold=1")
    await ready(page)
    await page.click("#btn-play")
    await open_card(page, "a0")
    await open_talk(page)
    await open_row(page, "shop-app-signup", 4)
    r = res["phone"] = {"sw": await page.evaluate("() => document.documentElement.scrollWidth"), "head": await page.evaluate(HEAD)}
    check(failures, r["sw"] <= 390, f"phone: no horizontal scroll ({r['sw']})")
    await page.screenshot(path=str(out / "ui-after-phone-light.png"))
    await page.close()
