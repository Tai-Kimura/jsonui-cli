"""The session's cards on the 応答の履歴 tab (ticket 2026-10-20-jui-viz-approve-and-answer-from-history; plan A). Runs with
`--only hist-cards`.

The real `jui viz serve`, the real forward.py: --decide holds a permission prompt and --ask a question, as Claude
Code runs them; a PermissionDenied hook makes a stopped call's card. One session: the permission and the stopped call
are its main robot's, the question and a second permission are a subagent's (the cards are the session's). Checked:
  * the three cards show between the history and the prompt box (outside the history's frame), with the question's
    time left, both permissions, and no id on the page twice (two permission cards of one session: two reason boxes);
  * the question answered there reaches --ask's hook (updatedInput.answers); the permission denied there with a reason
    reaches --decide's hook with that reason, the subagent's (the second card) denied with its own reason reaches its
    own; the cards then say so in the panel too, with no button left to press twice;
  * the 今の様子 tab shows no cards box;
  * the stopped call's 実行してよいと伝える… opens its confirmation in the history's card only, not the panel's;
  * そのまま closes it everywhere.
  * × (ticket 2026-10-21-jui-viz-hist-answered-card-dismiss-and-expand): no card waiting on an answer has it, the two
    answered questions and the two closed stopped calls have it in the history's cards only; one pressed per kind, that
    card leaves the history's cards, the other of its kind stays, the panel still shows both, and a reload keeps it gone;
  * the history keeps its 120 px above the cards, not under them;
  * 下を広げる, on the history tab only: with the four cards (more than the card's height) the cards box grows, the
    prompt box's 送信 stays inside the card and a strip of the history above them; with the two answered cards (the
    requester's case) both show whole (they did not before: the control); the choice
    is kept over a reload; 元の高さに戻す: the history's height back.
No console error; nothing outside the server.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, ISOLATE, LAUNCH_ARGS, T, Watch, dump, new_page, ready

SID = "e2e00000-0000-4000-8000-0000000000f7"
CWD = "/work/hist-cards"
SUB = "agent-hc-sub-1"
Q = {"questions": [{"question": "どちらにしますか", "header": "選択", "multiSelect": False,
                    "options": [{"label": "左", "description": "左にする"}, {"label": "右", "description": "右にする"}]}]}
# a second question and a second stopped call: one × takes off its own card, not the other of its kind
Q2 = {"questions": [{"question": "どれにしますか", "header": "向き", "multiSelect": False,
                     "options": [{"label": "上", "description": "上にする"}, {"label": "下", "description": "下にする"}]}]}
CARDS = """() => { const c = document.querySelector('#rb [data-h-cards]'); if (!c) return null;
  const hist = document.querySelector('[data-rb-hist]'), box = document.querySelector('[data-h-compose]');
  return { shown: !c.hidden, histHeight: Math.round(hist.getBoundingClientRect().height), perm: c.querySelectorAll('.tbd-perm').length, question: c.querySelectorAll('[data-qcard]').length,
    denied: c.querySelectorAll('[data-dcard]').length, outside: !hist.contains(c), beforeBox: !!box && c.nextElementSibling === box,
    left: (c.querySelector('[data-quntil]') || {}).textContent || '' }; }"""
LOW = """() => { const rb = document.getElementById('rb').getBoundingClientRect(), c = document.querySelector('#rb [data-h-cards]');
  const send = document.querySelector('#rb [data-h-send]').getBoundingClientRect(), b = document.querySelector('#rb [data-rb-low]');
  // the handle is on the cards box's top edge (2.3.20, the family of 広げる): right above the box, touching it, in sight
  const edge = b.nextElementSibling === c && Math.abs(b.getBoundingClientRect().bottom - c.getBoundingClientRect().top) < 2 && b.getClientRects().length > 0;
  return { on: document.getElementById('rb').classList.contains('rb-low'), pressed: b.getAttribute('aria-expanded'), label: b.textContent, edge,
    cardsScroll: c.scrollHeight - c.clientHeight, cardsHeight: c.clientHeight, sendIn: send.height > 0 && send.top >= rb.top && send.bottom <= rb.bottom + 0.5,
    cardsBelowHist: c.getBoundingClientRect().top >= document.querySelector('[data-rb-hist]').getBoundingClientRect().bottom - 0.5,
    histHeight: Math.round(document.querySelector('[data-rb-hist]').getBoundingClientRect().height),
    answeredIn: (() => { const r = c.getBoundingClientRect(), xs = [...c.querySelectorAll('[data-qcard]:not(.q-open), [data-dcard]:not(.q-open)')];
      return xs.length > 0 && xs.every((x) => { const b = x.getBoundingClientRect(); return b.top >= r.top - 0.5 && b.bottom <= r.bottom + 0.5; }); })(),
    rows: getComputedStyle(document.getElementById('rb')).gridTemplateRows,
    kids: [...document.getElementById('rb').children].filter((k) => k.getClientRects().length).map((k) => `${k.className.split(' ')[0]}:${Math.round(k.getBoundingClientRect().height)}`) }; }"""
OFF = """() => ({ hist: [...document.querySelectorAll('#rb [data-h-cards] [data-h-off]')].map((b) => b.dataset.hOff),
  elsewhere: document.querySelectorAll('[data-h-off]').length - document.querySelectorAll('#rb [data-h-cards] [data-h-off]').length,
  histQ: document.querySelectorAll('#rb [data-h-cards] [data-qcard]').length, histD: document.querySelectorAll('#rb [data-h-cards] [data-dcard]').length,
  histText: [...document.querySelectorAll('#rb [data-h-cards] [data-qcard] .qtext, #rb [data-h-cards] [data-dcard] .dwhat code')].map((e) => e.textContent),
  panelQ: document.querySelectorAll('#questions [data-qcard]').length, panelD: document.querySelectorAll('#denied [data-dcard]').length })"""
DUP_IDS = "() => { const ids = [...document.querySelectorAll('[id]')].map((e) => e.id); return ids.filter((x, i) => ids.indexOf(x) !== i); }"
# a radio group's name in the history's cards that the panel's (or the board's) cards also use: the two would be one group
SHARED_NAMES = """() => { const here = new Set([...document.querySelectorAll('#rb [data-h-cards] input[type=radio]')].map((i) => i.name));
  return [...document.querySelectorAll('input[type=radio]')].filter((i) => !i.closest('[data-h-cards]') && here.has(i.name)).map((i) => i.name); }"""


def check(failures, cond, text):
    if not cond:
        failures.append(f"hist-cards: {text}")


async def press_low(page):
    """The cards box's handle pressed where it is drawn, as a pointer does (2.3.20: it sticks to the box's top edge, and
    page.click would first scroll the box to the handle's place in the flow — the top — which a person's press does not)."""
    r = await page.evaluate("() => { const b = document.querySelector('#rb [data-rb-low]').getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2]; }")
    await page.mouse.click(r[0], r[1])


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def run_hist_cards(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "hist-cards"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    sessions_dir = home / ".claude" / "sessions"   # watched by the server from its start: made before it
    sessions_dir.mkdir(parents=True, exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log,
                           stderr=subprocess.STDOUT, env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"
    res: dict = {}
    held: list = []

    def body(**payload):
        return {"session_id": SID, "cwd": CWD, "transcript_path": "/work/none.jsonl", "permission_mode": "default", **payload}

    def hook(payload, flag=None):
        args = [sys.executable, "-I", "-S", str(forward)] + ([flag] if flag else [])
        p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(base_env, HOME=str(home)))
        p.stdin.write(json.dumps(payload).encode())
        p.stdin.close()
        p.stdin = None
        if flag:
            held.append(p)
            return p
        p.wait(timeout=10)
        return None

    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    watch = Watch(origin=url)
    t0 = time.monotonic()
    try:
        import urllib.request
        for _ in range(400):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        hook(body(hook_event_name="SessionStart", source="startup"))
        hook(body(hook_event_name="SubagentStart", agent_id=SUB, agent_type="general-purpose"))
        # a session whose channel takes words from the page (as denied.py): started naming the channel, a hello
        stand_in = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(900)", "--dangerously-load-development-channels", "plugin:jui-viz@jsonui"],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        held.append(stand_in)
        (sessions_dir / f"{stand_in.pid}.json").write_text(json.dumps({"pid": stand_in.pid, "sessionId": SID, "cwd": CWD, "kind": "interactive",
                                                                       "entrypoint": "cli", "status": "idle", "procStart": f"t{stand_in.pid}"}))
        token = json.loads((home / ".local" / "state" / "jui-viz" / "server.json").read_text())["token"]
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("POST", "/channel/hello", body=json.dumps({"ppid": 1, "cwd": "/", "sessionId": SID, "version": "2", "accepts": ["prompt"], "via": "plugin"}),
                     headers={"X-Jui-Viz-Token": token, "Content-Type": "application/json"})
        check(failures, conn.getresponse().status == 200, "the channel's hello")
        conn.close()
        page = await new_page(browser, watch, "hist-cards", **DESKTOP)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => window.__dbg.robots.length >= 2", timeout=30000, label="the robots")
        await page.wait_for_timeout(5500)   # one presence report: the --ask hook waits only for a visible page
        main = await page.evaluate("(sid) => window.__dbg.labelOfSession ? window.__dbg.labelOfSession(sid) : window.__dbg.robots.find((R) => R.def.kind === 'main').def.id", SID)
        # the three: a permission (main), a question (the subagent), a stopped call (main)
        pre = body(hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="bash-1", tool_input={"command": "ls -la /tmp", "description": "一覧"})
        hook(pre)
        req = body(hook_event_name="PermissionRequest", tool_name="Bash", tool_input={"command": "ls -la /tmp", "description": "一覧"})
        hook(req)
        pc = hook(req, "--decide")
        await page.evaluate("(id) => window.__dbg.openRobot(id)", main)
        await page.click('#rb [data-rb-tab="history"]')
        # requester 10-29: 「許可の応答の履歴での表示は初期表示は開いた状態で閉じる押したら１行にして」. Before #64 the card came
        # large while its bar said 開く (or had no bar at all once sent) and it could not be folded: at every step the state,
        # the bar's word and the box's height must agree
        look = """() => {
          const c=document.querySelector('#rb [data-h-cards]'), b=c.querySelector('[data-h-fold]');
          return {folded:window.__dbg.histFold().folded, how:b&&b.dataset.hFold, expanded:b&&b.getAttribute('aria-expanded'),
            word:b?b.textContent:'', height:c.clientHeight, bar:b?b.getBoundingClientRect().height:0,
            cardVisible:c.querySelector('.tbd-perm').getClientRects().length>0, sw:document.documentElement.scrollWidth};
        }"""
        def agrees(st, folded, width):
            if folded:
                return (st['folded'] and st['how'] == 'open' and st['expanded'] == 'false' and st['word'].startswith('▲')
                        and not st['cardVisible'] and st['height'] <= 55 and st['bar'] <= 30 and st['sw'] <= width)
            return (not st['folded'] and st['how'] == 'close' and st['expanded'] == 'true' and st['word'].startswith('▼')
                    and '許可 1 件' in st['word'] and '質問' not in st['word'] and st['cardVisible'] and st['height'] > st['bar'] + 60
                    and st['sw'] <= width)
        await wait(page, "() => !!document.querySelector('#rb [data-h-fold]')", label="the permission's bar")
        for width in (1440, 390):
            await page.set_viewport_size({"width": width, "height": 1000})
            st = await page.evaluate(look)
            check(failures, agrees(st, False, width), f"a permission comes open, its bar says ▼ close, the box is the card's height at {width}px: {st}")
            await page.screenshot(path=str(out / f"permission-open-{width}.png"))
        await page.set_viewport_size({"width": 1440, "height": 1000})
        await page.click('#rb [data-h-fold=close]')
        await wait(page, "() => window.__dbg.histFold().folded", label="閉じる folds the permission")
        for width in (1440, 390):
            await page.set_viewport_size({"width": width, "height": 1000})
            st = await page.evaluate(look)
            check(failures, agrees(st, True, width), f"closed, the permission is one line whose bar says ▲ open at {width}px: {st}")
            await page.screenshot(path=str(out / f"permission-one-line-{width}.png"))
        await page.set_viewport_size({"width": 1440, "height": 1000})
        await page.click('#rb [data-h-fold=open]')
        await wait(page, "() => !window.__dbg.histFold().folded", label="permission opens on request")
        st = await page.evaluate(look)
        check(failures, agrees(st, False, 1440), f"opened again, state, word and height agree: {st}")
        await page.set_viewport_size({"width": DESKTOP['viewport']['width'], "height": DESKTOP['viewport']['height']})
        sub_in = {"command": "echo sub-perm", "description": "サブの許可"}
        hook(body(hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="bash-sub-1", tool_input=sub_in, agent_id=SUB, agent_type="general-purpose"))
        sub_req = body(hook_event_name="PermissionRequest", tool_name="Bash", tool_input=sub_in, agent_id=SUB, agent_type="general-purpose")
        hook(sub_req)
        sc = hook(sub_req, "--decide")
        ask_pre = body(hook_event_name="PreToolUse", tool_name="AskUserQuestion", tool_use_id="ask-1", tool_input=Q, agent_id=SUB, agent_type="general-purpose")
        hook(ask_pre)
        qc = hook(ask_pre, "--ask")
        hook(body(hook_event_name="PermissionDenied", permission_mode="auto", tool_name="Bash", tool_input={"command": "git push --force"},
                  tool_use_id="den-1", reason="[Irreversible Remote Destruction]"))
        hook(body(hook_event_name="PermissionDenied", permission_mode="auto", tool_name="Bash", tool_input={"command": "rm -rf build"},
                  tool_use_id="den-2", reason="[Destructive Delete]"))
        await page.evaluate("(id) => window.__dbg.openRobot(id)", main)
        await wait(page, "() => !document.getElementById('rb').hidden", label="the card")
        await page.click('#rb [data-rb-tab="history"]')
        await wait(page, f"() => {{ const c = ({CARDS})(); return c && c.perm === 2 && c.question === 1 && c.denied === 2 && !!c.left.trim(); }}", label="the cards on the history tab, the question's time left")
        await wait(page, "() => !!document.querySelector('#rb [data-h-cards] [data-dask]')", label="the stopped call's button (its session has a channel)")
        c = res["cards"] = await page.evaluate(CARDS)
        check(failures, c["shown"] and c["outside"] and c["beforeBox"] and c["histHeight"] >= 100,
              f"between the history and the prompt box, outside the history's frame, the history still seen: {c}")
        dups = res["dupIds"] = await page.evaluate(DUP_IDS)
        check(failures, dups == [], f"no id on the page twice: {dups}")
        shared = res["sharedNames"] = await page.evaluate(SHARED_NAMES)
        check(failures, shared == [], f"no radio group shared with the panel's cards: {shared}")
        await page.screenshot(path=str(out / "cards.png"))
        off = res["offWhileWaiting"] = await page.evaluate(OFF)
        check(failures, off["hist"] == [] and off["elsewhere"] == 0, f"no × on a card that waits on an answer: {off}")
        # 下を広げる: the four cards scroll in their box at first (the control), then all show with 送信 inside the card
        lo = res["lowBefore"] = await page.evaluate(LOW)
        check(failures, not lo["on"] and lo["pressed"] == "false" and lo["label"] == T("hist.low.on") and lo["edge"] and lo["cardsScroll"] > 0,
              f"before 下を広げる the cards box scrolls (the control), its handle on the box's top edge: {lo}")
        check(failures, lo["cardsBelowHist"] and lo["histHeight"] >= 119, f"the history keeps 120 px and does not run under the cards: {lo}")
        await press_low(page)
        lo = res["lowOn"] = await page.evaluate(LOW)
        check(failures, lo["on"] and lo["pressed"] == "true" and lo["label"] == T("hist.low.off") and lo["edge"] and lo["sendIn"] and lo["cardsBelowHist"]
              and lo["cardsHeight"] > res["lowBefore"]["cardsHeight"] and lo["histHeight"] >= 50,
              f"下を広げる with four cards: the cards box grows, 送信 inside the card, a strip of the history above: {lo}")
        await page.screenshot(path=str(out / "low.png"))
        await press_low(page)
        lo = res["lowOff"] = await page.evaluate(LOW)
        check(failures, not lo["on"] and lo["pressed"] == "false" and lo["histHeight"] >= res["lowBefore"]["histHeight"] - 1,
              f"元の高さに戻す: the history's height back: {lo}")
        # the 今の様子 tab: no cards box there (the box is the history tab's; the independent check's X4)
        await page.click('#rb [data-rb-tab="now"]')
        await page.wait_for_timeout(400)
        res["cardsOnNowTab"] = await page.evaluate("() => { const c = document.querySelector('#rb [data-h-cards]'); return !!c && !c.hidden && c.getClientRects().length > 0; }")
        check(failures, res["cardsOnNowTab"] is False, "the cards box is not shown on the 今の様子 tab")
        res["lowOnNowTab"] = await page.evaluate("() => { const b = document.querySelector('#rb [data-rb-low]'); return !!b && b.getClientRects().length > 0; }")
        check(failures, res["lowOnNowTab"] is False, "no 下を広げる on the 今の様子 tab")
        await page.click('#rb [data-rb-tab="history"]')
        await wait(page, f"() => {{ const c = ({CARDS})(); return c && c.shown && c.perm === 2; }}", label="the cards again on the history tab")
        # the question, answered in the history
        q1 = "#rb [data-h-cards] [data-qcard]:has-text('どちらにしますか')"
        await page.click(f"{q1} label.qopt >> nth=1")
        await page.click(f"{q1} [data-qsend]")
        o, _ = qc.communicate(timeout=30)
        got = res["askHook"] = json.loads(o) if o else None
        ans = (((got or {}).get("hookSpecificOutput") or {}).get("updatedInput") or {}).get("answers")
        check(failures, ans == {"どちらにしますか": "右"}, f"--ask got the history's answer: {got}")
        # the second question only now: a session's next question ends its open ones (questions.session_stopped)
        ask_pre2 = body(hook_event_name="PreToolUse", tool_name="AskUserQuestion", tool_use_id="ask-2", tool_input=Q2)
        hook(ask_pre2)
        qc2 = hook(ask_pre2, "--ask")
        q2 = "#rb [data-h-cards] [data-qcard]:has-text('どれにしますか')"
        await wait(page, "() => !!document.querySelector('#rb [data-h-cards] [data-qcard].q-open [data-qsend]')", label="the second question, open")
        await page.click(f"{q2} label.qopt >> nth=0")
        await page.click(f"{q2} [data-qsend]")
        o, _ = qc2.communicate(timeout=30)
        got = res["askHook2"] = json.loads(o) if o else None
        ans = (((got or {}).get("hookSpecificOutput") or {}).get("updatedInput") or {}).get("answers")
        check(failures, ans == {"どれにしますか": "上"}, f"the second --ask got its answer: {got}")
        # the subagent's permission first, denied with its own reason in the second card: the reason is the pressed
        # card's, not the first reason box on the page (the independent check's X3)
        sub = "#rb [data-h-cards] .tbd-perm:has-text('echo sub-perm')"
        await page.fill(f"{sub} .tbd-reason input", "サブを履歴から拒否")
        await page.click(f"{sub} [data-do='deny']")
        o, _ = sc.communicate(timeout=30)
        got = res["subPermHook"] = json.loads(o) if o else None
        dec = ((got or {}).get("hookSpecificOutput") or {}).get("decision") if isinstance(got, dict) else None
        check(failures, isinstance(dec, dict) and dec.get("behavior") == "deny" and "サブを履歴から拒否" in json.dumps(dec, ensure_ascii=False),
              f"the subagent's --decide got the second card's deny with its reason: {got}")
        # then the main robot's, denied with a reason
        mine = "#rb [data-h-cards] .tbd-perm:has-text('ls -la /tmp')"
        await page.fill(f"{mine} .tbd-reason input", "履歴から拒否")
        await page.click(f"{mine} [data-do='deny']")
        o, _ = pc.communicate(timeout=30)
        got = res["permHook"] = json.loads(o) if o else None
        dec = ((got or {}).get("hookSpecificOutput") or {}).get("decision") if isinstance(got, dict) else None
        check(failures, isinstance(dec, dict) and dec.get("behavior") == "deny" and "履歴から拒否" in json.dumps(dec, ensure_ascii=False)
              and "サブ" not in json.dumps(dec, ensure_ascii=False), f"--decide got the history's deny with its reason: {got}")
        await wait(page, "() => !document.querySelector('#tasks [data-do]') && !document.querySelector('#questions [data-qsend]:not([disabled])')", timeout=15000,
                   label="no button left in the panel to answer twice")
        # the stopped call: its confirmation opens in the history's card only
        d1 = "#rb [data-h-cards] [data-dcard]:has-text('git push')"
        await page.click(f"{d1} [data-dask]")
        conf = res["deniedConfirm"] = await page.evaluate("() => ({ here: !!document.querySelector('#rb [data-h-cards] [data-dgo]'), panel: !!document.querySelector('#denied [data-dgo]') })")
        check(failures, conf == {"here": True, "panel": False}, f"the stopped call's confirmation in the history's card only: {conf}")
        await page.click(f"{d1} [data-dback]")
        await page.click(f"{d1} [data-ddismiss]")
        await page.click("#rb [data-h-cards] [data-dcard]:has-text('rm -rf build') [data-ddismiss]")
        await wait(page, f"() => {{ const d = [...document.querySelectorAll('#denied [data-dcard]')]; return d.every((x) => x.textContent.includes({json.dumps(T('deny.done.dismissed'))})); }}", label="そのまま everywhere")
        await page.screenshot(path=str(out / "answered.png"))
        # × on the four answered cards, in the history's cards only; one pressed per kind: that card off there, the other
        # of its kind still there, the panel keeping all
        await wait(page, "() => document.querySelectorAll('#rb [data-h-cards] [data-h-off]').length === 4", label="× on the answered questions and the closed stopped calls")
        off = res["offAnswered"] = await page.evaluate(OFF)
        check(failures, sorted(k[0] for k in off["hist"]) == ["d", "d", "q", "q"] and off["elsewhere"] == 0, f"× on the four answered cards, the history's only: {off}")
        await page.click(f"{q1} [data-h-off]")
        await page.click(f"{d1} [data-h-off]")
        off = res["offPressed"] = await page.evaluate(OFF)
        check(failures, off["histQ"] == 1 and off["histD"] == 1 and sorted(off["histText"]) == ["rm -rf build", "どれにしますか"]
              and off["panelQ"] == 2 and off["panelD"] == 2,
              f"× takes its own card off the history's cards, the other of its kind stays, the panel keeps both: {off}")
        # 下を広げる with the two answered cards (the requester's case): all of them and 送信 at once
        lo = res["lowAnsweredBefore"] = await page.evaluate(LOW)
        await press_low(page)
        lo2 = res["lowAnswered"] = await page.evaluate(LOW)
        check(failures, not lo["answeredIn"], f"before 下を広げる the two answered cards do not show whole (the control): {lo}")
        check(failures, lo2["on"] and lo2["answeredIn"] and lo2["sendIn"] and lo2["cardsBelowHist"],
              f"下を広げる with the two answered cards: both whole and 送信 at once, the history above: {lo2}")
        await page.screenshot(path=str(out / "low-answered.png"))
        await page.reload()
        await ready(page)
        await wait(page, "() => document.querySelectorAll('#denied [data-dcard]').length === 2", label="the panel's stopped calls after the reload")
        await page.evaluate("(id) => window.__dbg.openRobot(id)", main)
        await wait(page, "() => !document.getElementById('rb').hidden", label="the card after the reload")
        await page.click('#rb [data-rb-tab="history"]')
        await page.wait_for_timeout(800)
        off = res["offReloaded"] = await page.evaluate(OFF)
        check(failures, off["histD"] == 1 and "rm -rf build" in off["histText"] and off["panelD"] == 2,
              f"after a reload the stopped call taken off stays off the history's cards, the other one stays (the panel has both): {off}")
        lo = res["lowReloaded"] = await page.evaluate(LOW)
        check(failures, lo["on"] and lo["pressed"] == "true", f"下を広げる is kept over a reload: {lo}")
        await page.close()
        for line in watch.console:
            failures.append(f"hist-cards: console: {line}")
        for u in watch.foreign:
            failures.append(f"hist-cards: request outside the server: {u}")
    except Exception as e:
        failures.append(f"hist-cards: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        for p in held:
            if p.poll() is None:
                p.kill()
                p.wait()
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  hist-cards: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "hist-cards-results.json").write_text(dump(res) + "\n")
