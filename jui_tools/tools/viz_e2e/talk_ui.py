"""トーク: a robot's SendMessage conversations as a chat, the page side (2.3.7, requester 10-20). Runs with `--only talk-ui`.

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
  * a remove op takes the talk off the list (and out of the detail, with a note).
Waits are on page state (waits.until); nothing is sampled on the wall clock.
"""

from __future__ import annotations

import json
import pathlib
import sys
import time

from common import DESKTOP, PHONE, LAUNCH_ARGS, Watch, new_page, ready
from waits import WaitTimeout, until

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
    check(failures, rows[-1]["gone"].startswith("終了"), f"{scheme}: the ended peer is marked: {rows[-1]['gone']!r}")
    no_send = r["noSend"] = await page.evaluate(SEND_UI)
    check(failures, no_send == {"fields": 0, "sendWords": [], "compose": 0}, f"{scheme}: no send UI in the talk: {no_send}")
    await page.screenshot(path=str(out / f"ui-after-list-{scheme}.png"))

    # the detail with b4: sides, states, the fold, the escaped <script>, seen
    await open_row(page, "shop-app-signup", 4)
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
