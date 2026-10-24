"""Who a SendMessage went to, in the 応答の履歴, and a click on the name switches to that robot (2.3.6; requester 10-20:
「SendMessageは閉じた状態でも誰宛かわかるようにして、その宛先クリックでそのロボットの表示に切り替えることできる？」;
ticket 2026-10-20-jui-viz-history-sendmessage-recipient).

On the stage of hist_wide.py (the real server, sessions A and B), with the names the CLI gives in
~/.claude/sessions/<pid>.json (A: wide-app-a, B: wide-other-b, each with its socket), A's transcript gets four
SendMessage calls and B's a message from A:

  - matched by name with a ref (`wide-other-b [ab12cd]`) and by a uds address in another folder (only the pid in
    the file name matches): the folded row shows → and the name as a button, then the summary;
  - unmatched (`far-away-zz`): the name is plain text, not focusable, titled この viz にいないセッション;
  - the long summary is cut on one line and shows whole in the whole-text tag on hover;
  - a click on the matched name switches the card to B (the 応答の履歴 tab stays), without opening the fold;
  - in B's history, 「wide-app-a から」 is a button too, and takes the card back to A.

Waits are on page state (waits.until). Screenshots (light and dark) are for the eye.
"""

from __future__ import annotations

import json
import pathlib
import time

from common import T, dump, stamp
from hist_wide import A, B, CWD_A, CWD_B, Stage, check as _check
from waits import until

SUITE = "hist-peers"
NAME_A, NAME_B = "wide-app-a", "wide-other-b"
LONG = "請求の件: " + "とても長い要約の文。" * 12
ROWS = """() => [...document.querySelectorAll('[data-rb-hist] details.h-tool')].filter((d) => d.querySelector('summary > b').textContent === 'SendMessage').map((d) => {
  const s = d.querySelector('summary'), to = s.querySelector('.h-to'), link = to && to.querySelector('[data-h-go]'), name = to && to.querySelector('.h-peername');
  const head = s.querySelector('.h-head');
  return { to: to ? to.textContent : null, link: link ? link.dataset.hGo : null, linkTag: link ? link.tagName : null,
    plain: name ? { tag: name.tagName, tabIndex: name.tabIndex, title: name.title } : null, head: head ? head.textContent : null,
    headCut: head ? head.scrollWidth > head.clientWidth + 1 : null, open: d.open }; })"""
FROM = """() => [...document.querySelectorAll('[data-rb-hist] details.h-peer')].map((d) => { const b = d.querySelector('summary > b');
  const l = b.querySelector('[data-h-go]'); return { text: b.textContent, link: l ? l.dataset.hGo : null, tag: l ? l.tagName : null }; })"""
CARD = "() => ({ id: window.__dbg.focus().id, tab: document.querySelector('#rb [data-rb-tab=\"history\"]').getAttribute('aria-selected'), text: document.querySelector('[data-rb-hist]').textContent.slice(0, 80) })"


def check(failures, cond, text):
    _check(failures, cond, text, SUITE)


def send(use_id, to, summary, ts):
    return {"type": "assistant", "timestamp": ts, "message": {"id": use_id, "role": "assistant", "content": [
        {"type": "tool_use", "id": use_id, "name": "SendMessage", "input": {"to": to, "summary": summary, "message": "本文\n二行目"}}]}}


def setup(st):
    sessions = st.home / ".claude" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    for pid, sid, cwd, name in ((4241, A, CWD_A, NAME_A), (4242, B, CWD_B, NAME_B)):
        (sessions / f"{pid}.json").write_text(json.dumps({"pid": pid, "sessionId": sid, "cwd": cwd, "name": name, "status": "idle",
                                                          "messagingSocketPath": f"/tmp/cc-socks/{pid}.sock"}))
    # after the stage's own records (hist_wide's last is 09:47:50 on its clock), with their gaps: through stamp()
    with open(st.paths[A], "a") as f:
        for r in (send("sm1", f"{NAME_B} [ab12cd]", LONG, stamp("2026-10-19T09:50:00Z")),
                  send("sm2", "far-away-zz", "届かない宛先", stamp("2026-10-19T09:50:01Z")),
                  send("sm3", "uds:/tmp/cc-socks-elsewhere/4242.sock", "pid で見つかる宛先", stamp("2026-10-19T09:50:02Z"))):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(st.paths[B], "a") as f:
        f.write(json.dumps({"type": "user", "timestamp": stamp("2026-10-19T09:50:05Z"), "message": {"role": "user", "content":
                f'Another Claude session sent a message:\n<cross-session-message from="uds:/tmp/cc-socks/4241.sock" from-name="{NAME_A}">\nB へ\n</cross-session-message>'}},
                ensure_ascii=False) + "\n")


async def run_hist_peers(pw, out, failures):
    t0 = time.monotonic()
    st = Stage()
    res: dict = {}
    try:
        # the folder before the server starts: it watches ~/.claude/sessions only when the folder is there
        (pathlib.Path(out) / SUITE / "home" / ".claude" / "sessions").mkdir(parents=True, exist_ok=True)
        await st.start(pw, out, SUITE)
        setup(st)
        out = st.out
        for scheme in ("light", "dark"):
            r = res[scheme] = {}
            page = await st.page(f"{SUITE}-{scheme}", color_scheme=scheme, viewport={"width": 1440, "height": 900})
            # the session files were read: the session list says both names
            await until(page, f"() => document.body.textContent.includes('{NAME_A}') && document.body.textContent.includes('{NAME_B}')",
                        f"{scheme}: the names from the session files")
            ra = await st.open_a(page)
            await until(page, "() => document.querySelectorAll('[data-rb-hist] .h-to').length >= 3", f"{scheme}: the SendMessage rows")
            rows = r["rows"] = await page.evaluate(ROWS)
            byname, far, bypid = rows[0], rows[1], rows[2]
            rb = byname["link"]
            check(failures, byname["to"] == f"→ {NAME_B} [ab12cd]" and byname["linkTag"] == "BUTTON" and rb and byname["head"] == LONG,
                  f"{scheme}: a name with a ref is linked to B, the summary beside it: {byname}")
            check(failures, bypid["link"] == rb, f"{scheme}: a uds address found by the pid in its file name links to B too: {bypid}")
            check(failures, far["link"] is None and far["plain"] and far["plain"]["tag"] == "SPAN" and far["plain"]["tabIndex"] == -1
                  and far["plain"]["title"] == T("hist.peer.unseen"), f"{scheme}: an unmatched name is plain and not focusable: {far}")
            # the long summary: cut, whole in the tag on hover
            check(failures, byname["headCut"], f"{scheme}: the long summary is cut to one line: {byname}")
            head = page.locator("[data-rb-hist] details.h-tool .h-to:has([data-h-go]) ~ .h-head").first
            await head.scroll_into_view_if_needed()
            await head.hover()
            await until(page, "() => { const t = document.getElementById('fulltext'); return !!t && !t.hidden; }", f"{scheme}: the summary's whole-text tag")
            r["tag"] = await page.evaluate("() => document.getElementById('fulltext').textContent")
            check(failures, r["tag"] == LONG, f"{scheme}: the tag shows the whole summary: {r['tag'][:40]!r}")
            await page.screenshot(path=str(out / f"peers-a-{scheme}.png"))
            # click the name: B's card, still on the history, the fold not opened
            await page.mouse.move(0, 0)
            await page.locator("[data-rb-hist] .h-to [data-h-go]").first.click()
            await until(page, "(id) => window.__dbg.focus().id === id", f"{scheme}: the card on B", arg=rb, why=CARD)
            card = r["onB"] = await page.evaluate(CARD)
            check(failures, card["tab"] == "true", f"{scheme}: the 応答の履歴 tab stays: {card}")
            await until(page, "() => document.querySelectorAll('[data-rb-hist] details.h-peer').length >= 1", f"{scheme}: B's history")
            frm = r["from"] = await page.evaluate(FROM)
            check(failures, frm and frm[-1]["text"] == f"{T('hist.peer.from.pre')}{NAME_A}{T('hist.peer.from')}" and frm[-1]["tag"] == "BUTTON" and frm[-1]["link"] == ra,
                  f"{scheme}: in B's history the sender is a link back to A: {frm}")
            await page.screenshot(path=str(out / f"peers-b-{scheme}.png"))
            await page.locator("[data-rb-hist] details.h-peer [data-h-go]").last.click()
            await until(page, "(id) => window.__dbg.focus().id === id", f"{scheme}: back on A", arg=ra, why=CARD)
            await page.close()
    except Exception as e:
        failures.append(f"{SUITE}: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        if getattr(st, "srv", None) is not None:
            await st.stop(failures, SUITE)
        print(f"  {SUITE}: {time.monotonic() - t0:.0f}s", flush=True)
        if hasattr(st, "out"):
            (pathlib.Path(st.out) / f"{SUITE}-results.json").write_text(dump(res) + "\n")
