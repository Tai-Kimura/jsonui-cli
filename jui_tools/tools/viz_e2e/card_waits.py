"""The other sessions' waits beside an open card (2.3.21; requester 10-23: 「質問や許可まちがカード開いてると見えないので、開いて
るときはカードの左側の上の方に許可が来たのがわかるようにしてほしい」). Runs with `--only card-waits`.

The real `jui viz serve` in a throwaway HOME and the real forward.py; five sessions in one room: host (whose card is
open), perm (a Bash call waiting on its permission), ask (an AskUserQuestion), den (auto mode stopped a call) and own
(a permission waiting on the host's own session is not in the block — its card says it; host itself waits too).

Checked, with host's card open at 1440 px:
  * nothing waits: no block;
  * a permission comes: the block shows beside the card — out of it, its right edge left of the card's left edge, its
    top at the card's top — with 許可 1 and perm's mark, and it moved once (rbw-arrive), not under reduced motion;
  * a question and a stopped call come: 許可 1 · 質問 1 · 止められた操作 1, the robots perm, ask, den; the host's own
    permission is not counted;
  * a press on perm's mark opens its waits in a pane under the block (out of the card), the robot's card stays;
  * a press on the sum opens the task board's waiting strip;
  * at 390 px (the card a sheet the page's width): no block; the card's head row has 待ち 3, which opens the pane with
    the robots listed; its ボードで見る opens the board;
  * answered where listed (ticket 2026-10-24-viz-card-waits-answer-in-place; qa, qb and pa held by `forward.py --ask` /
    `--decide`): qa's row opens its question in the pane, beside the card and under the block; Red and 送る reach the
    waiting hook, and the row and the pane go, the card staying; pa's permission allowed there reaches its hook; qb
    answered in the panel's card goes from the open pane too; the row again, and Esc, close the pane, the card staying.
    Stills of the open pane (1440 and 390, light and dark); with `video`, the presses recorded.
  * at 1920 px: the block beside the card again.
Stills (out/card-waits/*.png) at 1920, 1440 and 390, light and dark.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, new_page, ready
from waits import WaitTimeout, settled, until

CWD = "/work/card-waits-app"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
SID = {k: f"e2e00000-0000-4000-8000-0000000007{i:02d}" for i, k in enumerate(("host", "perm", "ask", "den", "m1", "m2", "m3", "m4", "m5", "m6", "qa", "qb", "pa"), 1)}
MORE = ("m1", "m2", "m3", "m4", "m5", "m6")   # with perm, ask and den: nine robots waiting, past the six listed
QUESTION = {"questions": [{"question": "Which colour?", "header": "Colour", "multiSelect": False,
                           "options": [{"label": "Red", "description": "a"}, {"label": "Blue", "description": "b"}]}]}
BLOCK = """() => { const b = document.getElementById('rb-waits'), rb = document.getElementById('rb');
  if (!b || b.hidden) return { shown: false };
  const r = b.getBoundingClientRect(), c = rb.getBoundingClientRect();
  return { shown: true, sum: (b.querySelector('[data-rbw-board]') || {}).textContent || '',
    robots: [...b.querySelectorAll('[data-rbw-robot]')].map((x) => x.dataset.rbwRobot).sort(),
    right: r.right, top: r.top, left: r.left, cardLeft: c.left, cardTop: c.top, arrive: b.classList.contains('rbw-arrive'),
    anim: getComputedStyle(b).animationName }; }"""
BADGE = "() => { const b = document.querySelector('#rb [data-rbw-slot] [data-rbw-pane]'); return b ? b.textContent : null; }"
QUESTION_B = {"questions": [{"question": "Which size?", "header": "Size", "multiSelect": False,
                             "options": [{"label": "Small", "description": "s"}, {"label": "Large", "description": "l"}]}]}
PANE = """() => { const p = document.getElementById('rb-wait-pane');
  if (!p || p.hidden) return { shown: false };
  const r = p.getBoundingClientRect(), c = document.getElementById('rb').getBoundingClientRect(), b = document.getElementById('rb-waits').getBoundingClientRect();
  return { shown: true, q: [...p.querySelectorAll('.rbwp-items [data-qcard]')].map((x) => x.dataset.qcard),
    perm: [...p.querySelectorAll('.rbwp-items [data-perm-box]')].map((x) => x.dataset.permBox), send: !!p.querySelector('[data-qsend]'),
    allow: !!p.querySelector('[data-do="allow"]'), robots: [...p.querySelectorAll('[data-rbwp-robot]')].map((x) => x.dataset.rbwpRobot).sort(),
    left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, cardLeft: c.left, blockBottom: b.bottom, blockShown: !document.getElementById('rb-waits').hidden,
    focusIn: p.contains(document.activeElement), vw: innerWidth, vh: innerHeight,
    hit: (() => { const e = document.elementFromPoint(r.left + r.width / 2, r.top + Math.min(r.height / 2, 40)); return !!e && p.contains(e); })() }; }"""
CARD_ON = "(id) => window.__dbg.board().robot === id && !document.getElementById('rb').hidden && getComputedStyle(document.getElementById('rb')).opacity === '1'"


def check(failures, cond, text):
    if not cond:
        failures.append(f"card-waits: {text}")


async def run_card_waits(pw, out, failures, jt=None, video: pathlib.Path | None = None):
    from run import free_port
    name = "card-waits"
    out = pathlib.Path(out) / name
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    jt = pathlib.Path(jt) if jt else pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    sessions = home / ".claude" / "sessions"   # watched by the server from its start: perm's name, renamed below
    sessions.mkdir(parents=True, exist_ok=True)

    def name_perm(title):
        (sessions / "93001.json").write_text(json.dumps({"pid": 93001, "sessionId": SID["perm"], "cwd": CWD, "status": "idle", "entrypoint": "cli",
                                                         "name": title, "nameSource": "user"}))
    name_perm("Perm lane")
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT,
                           env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"
    res: dict = {}
    browser = None
    t0 = time.monotonic()
    try:
        def hook(k, **payload):
            body = {"session_id": SID[k], "cwd": CWD, "transcript_path": f"{home}/t-{k}.jsonl", "permission_mode": "default", **payload}
            subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(), capture_output=True,
                           env=dict(base_env, HOME=str(home)), timeout=10)

        browser = await pw.chromium.launch(args=LAUNCH_ARGS)
        watch = Watch(origin=url)
        import urllib.request
        for _ in range(400):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        if video:   # the presses recorded, for showing (the arms are the same)
            ctx = await browser.new_context(**dict(DESKTOP, record_video_dir=str(video), record_video_size=DESKTOP["viewport"]))
            page = await ctx.new_page()
            watch.attach(page, name)
        else:
            page = await new_page(browser, watch, name, **DESKTOP)
        pause = (lambda ms: page.wait_for_timeout(ms)) if video else (lambda ms: page.wait_for_timeout(0))
        await page.emulate_media(color_scheme="light", reduced_motion="no-preference")
        await page.goto(url + "/")
        await ready(page)
        await until(page, "() => document.querySelector('.chip.demo').dataset.net === 'connected'", "connected")
        for k in SID:
            if k not in MORE:
                hook(k, hook_event_name="SessionStart", source="startup")
        await until(page, "(n) => window.__dbg.robots.length >= n", "a robot for each session", arg=len([k for k in SID if k not in MORE]),
                    timeout=40000, why="() => window.__dbg.settleInfo()")
        ids = await page.evaluate("() => Object.fromEntries(window.__dbg.robots.map((R) => [R.def.sessionId, R.def.id]))")
        rid = {k: ids[SID[k]] for k in SID if k not in MORE}
        res["ids"] = rid

        async def open_host():
            await page.evaluate("(id) => window.__dbg.openRobot(id)", rid["host"])
            await until(page, "(id) => window.__dbg.board().robot === id && !document.getElementById('rb').hidden && getComputedStyle(document.getElementById('rb')).opacity === '1'",
                    "host's card, opened through", arg=rid["host"])

        async def close_board():   # and its zoom back done: a card opened before it ends is closed by it
            await page.evaluate("() => window.__dbg.closeTaskBoard()")
            await until(page, "() => !window.__dbg.board().open", "the board closed")
            await settled(page, "the board's zoom back done")

        async def block(label, want=None, timeout=15000):
            try:
                if want is None:
                    return await until(page, f"() => {{ const b = ({BLOCK})(); return b.shown ? b : null; }}", label, timeout=timeout, why=BLOCK)
                return await until(page, f"(w) => {{ const b = ({BLOCK})(); return b.shown && JSON.stringify(b.robots) === JSON.stringify(w) ? b : null; }}",
                                   label, arg=sorted(want), timeout=timeout, why=BLOCK)
            except WaitTimeout as e:
                failures.append(f"card-waits: {e}")
                return await page.evaluate(BLOCK)

        await open_host()
        await settled(page, "the card open")
        res["none"] = await page.evaluate(BLOCK)
        check(failures, not res["none"]["shown"], f"nothing waits: no block: {res['none']}")

        # a permission comes
        hook("perm", hook_event_name="UserPromptSubmit", prompt="build")
        hook("perm", hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="toolu_cw1", tool_input={"command": "make clean"})
        hook("perm", hook_event_name="PermissionRequest", tool_name="Bash", tool_input={"command": "make clean"})
        b = res["perm"] = await block("the block with perm", [rid["perm"]])
        check(failures, b.get("shown") and b["sum"] == await page.evaluate("() => window.__dbg.tl('rbw.sum.perm', { n: 1 })")
              and b["right"] <= b["cardLeft"] - 4 and abs(b["top"] - b["cardTop"]) <= 2 and b["left"] >= 0,
              f"a permission: the block beside the card, out of it at its top-left, 許可 1: {b}")
        check(failures, b.get("arrive") and b.get("anim") == "rbw-arrive", f"a permission come: the block moves once: {b}")

        # a question, a stopped call, and the host's own permission
        hook("ask", hook_event_name="UserPromptSubmit", prompt="ask me")
        hook("ask", hook_event_name="PreToolUse", tool_name="AskUserQuestion", tool_use_id="toolu_cw2", tool_input=QUESTION)
        hook("den", hook_event_name="UserPromptSubmit", prompt="deploy", permission_mode="auto")
        hook("den", hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="toolu_cw3", tool_input={"command": "rm -rf build"}, permission_mode="auto")
        hook("den", hook_event_name="PermissionDenied", tool_name="Bash", tool_use_id="toolu_cw3", tool_input={"command": "rm -rf build"},
             permission_mode="auto", reason="auto mode classifier")
        hook("host", hook_event_name="UserPromptSubmit", prompt="own")
        hook("host", hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="toolu_cw4", tool_input={"command": "ls"})
        hook("host", hook_event_name="PermissionRequest", tool_name="Bash", tool_input={"command": "ls"})
        await until(page, "(id) => (window.__dbg.robotState()[id] || {}).state === 'waiting'", "host waits too", arg=rid["host"])
        b = res["all"] = await block("the block with perm, ask, den", [rid["perm"], rid["ask"], rid["den"]])
        want = await page.evaluate("() => [['rbw.sum.perm', 1], ['rbw.sum.ask', 1], ['rbw.sum.denied', 1]].map(([k, n]) => window.__dbg.tl(k, { n })).join(' · ')")
        check(failures, b.get("shown") and b["sum"] == want and rid["host"] not in b["robots"],
              f"three waits: {want!r}, the host's own left out: {b}")
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await settled(page, f"{scheme}: settled")
            await page.screenshot(path=str(out / f"card-waits-1440-{scheme}.png"))

        # a press on perm's mark: its waits in the pane, the robot's card stays
        await page.click(f"#rb-waits [data-rbw-robot='{rid['perm']}']")
        p = res["press"] = await until(page, f"() => {{ const p = ({PANE})(); return p.shown && p.perm.length ? p : null; }}",
                                       "perm's mark opens the pane", timeout=10000, why=PANE)
        check(failures, p.get("shown") and len(p["perm"]) == 1 and p["right"] <= p["cardLeft"] - 4 and p["top"] >= p["blockBottom"],
              f"perm's mark: its permission in the pane, out of the card and under the block: {p}")
        check(failures, await page.evaluate(CARD_ON, rid["host"]), "perm's mark: the host's card stays")
        await page.click(f"#rb-waits [data-rbw-robot='{rid['perm']}']")   # the row again: closed
        res["pressAgain"] = again = await until(page, f"() => {{ const p = ({PANE})(); return p.shown ? null : p; }}", "the row again closes the pane", timeout=10000, why=PANE)
        check(failures, not again.get("shown"), f"the row again: the pane closed: {again}")
        # a press on the sum: the task board's waiting strip
        await page.click("#rb-waits [data-rbw-board]")
        tb = res["board"] = await until(page, "() => { const b = window.__dbg.board(); return b.open ? b : null; }", "the sum opens the board", timeout=10000)
        check(failures, tb["waitView"] and not tb["robot"], f"the sum: the board's waiting strip, the card closed: {tb}")
        res["boardBlock"] = await page.evaluate(BLOCK)
        check(failures, not res["boardBlock"]["shown"], f"no card, no block: {res['boardBlock']}")

        # wide: 1920
        await page.set_viewport_size({"width": 1920, "height": 1080})
        await close_board()
        await open_host()
        b = res["1920"] = await block("1920: the block", [rid["perm"], rid["ask"], rid["den"]])
        check(failures, b.get("shown") and b["right"] <= b["cardLeft"] - 4, f"1920: the block beside the card: {b}")
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await settled(page, f"1920 {scheme}")
            await until(page, "(id) => window.__dbg.board().robot === id && getComputedStyle(document.getElementById('rb')).opacity === '1'",
                        f"1920 {scheme}: the card still on screen", arg=rid["host"], timeout=10000,
                        why="() => { const r = document.getElementById('rb'); return [window.__dbg.board(), r.hidden, r.className, getComputedStyle(r).opacity]; }")
            await page.screenshot(path=str(out / f"card-waits-1920-{scheme}.png"))

        # a phone: the badge in the card's head
        await page.set_viewport_size({"width": 390, "height": 844})
        await until(page, "() => { const b = document.getElementById('rb-waits'); return b.hidden; }", "390: no block", timeout=10000)
        badge = res["badge"] = await until(page, BADGE, "390: the head's badge", timeout=10000, why=BADGE)
        check(failures, badge == await page.evaluate("() => window.__dbg.tl('rbw.badge', { n: 3 })"), f"390: 待ち 3 in the card's head: {badge!r}")
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await settled(page, f"390 {scheme}")
            await page.screenshot(path=str(out / f"card-waits-390-{scheme}.png"))
        await page.click("#rb [data-rbw-slot] [data-rbw-pane]")
        p = res["390pane"] = await until(page, f"() => {{ const p = ({PANE})(); return p.shown && p.robots.length ? p : null; }}", "390: the badge opens the pane", timeout=10000, why=PANE)
        check(failures, p.get("shown") and p["robots"] == sorted([rid["perm"], rid["ask"], rid["den"]]) and p["left"] >= 0 and p["right"] <= p["vw"]
              and p["hit"] and p["bottom"] <= p["vh"],
              f"390: the badge's pane lists the three robots, on the page and in front (what is at its middle is the pane): {p}")
        check(failures, await page.evaluate(CARD_ON, rid["host"]), "390: the host's card stays")
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await settled(page, f"390 pane {scheme}")
            await page.screenshot(path=str(out / f"card-waits-pane-390-{scheme}.png"))
        await page.click("#rb-wait-pane [data-rbw-board]")
        tb = await until(page, "() => { const b = window.__dbg.board(); return b.open ? b : null; }", "390: the pane's ボードで見る opens the board", timeout=10000)
        check(failures, tb["waitView"], f"390: the pane's ボードで見る opens the board's waiting strip: {tb}")

        # reduced motion: a new wait does not move it
        await page.set_viewport_size({"width": 1440, "height": 900})
        await page.emulate_media(color_scheme="light", reduced_motion="reduce")
        await close_board()
        await open_host()
        b = res["reduced"] = await block("reduced motion: the block")
        check(failures, b.get("anim") == "none", f"reduced motion: no movement: {b}")

        # a rename while the block shows: its row and title say the new name
        named = res["named"] = await page.evaluate("(id) => { const b = document.querySelector(`#rb-waits [data-rbw-robot=\"${id}\"]`); return b ? [b.title, b.textContent] : null; }", rid["perm"])
        check(failures, named and "Perm lane" in named[0] and "Perm lane" in named[1], f"the block names perm's session: {named}")
        name_perm("Renamed lane")
        res["renamed"] = r = await until(page, "(id) => { const b = document.querySelector(`#rb-waits [data-rbw-robot=\"${id}\"]`); return b && b.title.includes('Renamed lane') && b.textContent.includes('Renamed lane') ? [b.title, b.textContent] : null; }",
                                         "the block says perm's new name", arg=rid["perm"], timeout=20000,
                                         why="(id) => { const b = document.querySelector(`#rb-waits [data-rbw-robot=\"${id}\"]`); return b ? [b.title, b.textContent] : null; }")
        check(failures, "Perm lane" not in r[0] and "Perm lane" not in r[1], f"renamed: no old name left in the block: {r}")

        # ---- answered where listed (ticket 2026-10-24-viz-card-waits-answer-in-place)
        await page.emulate_media(color_scheme="light", reduced_motion="no-preference")
        held: dict = {}

        def hold(k, flag, **payload):   # a hook that waits for the page's answer
            body = {"session_id": SID[k], "cwd": CWD, "transcript_path": f"{home}/t-{k}.jsonl", "permission_mode": "default", **payload}
            p = subprocess.Popen([sys.executable, "-I", "-S", str(forward), flag], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, env=dict(base_env, HOME=str(home)))
            p.stdin.write(json.dumps(body).encode())
            p.stdin.close()
            p.stdin = None
            held[k] = p

        def heard(k, timeout=30):
            o, _ = held[k].communicate(timeout=timeout)
            return json.loads(o) if o else None

        await page.wait_for_timeout(5500)   # a presence report from the page (the waiting hooks wait only for a visible page)
        for k, q, use in (("qa", QUESTION, "toolu_qa"), ("qb", QUESTION_B, "toolu_qb")):
            pre = dict(hook_event_name="PreToolUse", tool_name="AskUserQuestion", tool_use_id=use, tool_input=q)
            hook(k, hook_event_name="UserPromptSubmit", prompt="ask")
            hook(k, **pre)
            hold(k, "--ask", **pre)
        req = dict(hook_event_name="PermissionRequest", tool_name="Bash", tool_input={"command": "npm test"})
        hook("pa", hook_event_name="UserPromptSubmit", prompt="test")
        hook("pa", hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="toolu_pa", tool_input={"command": "npm test"})
        hook("pa", **req)
        hold("pa", "--decide", **req)
        await block("qa, qb and pa in the block", [rid[k] for k in ("perm", "ask", "den", "qa", "qb", "pa")], timeout=30000)
        await until(page, "() => document.querySelectorAll('#questions .qcard.q-open [data-qsend]').length >= 2", "the two held questions open", timeout=20000)
        await pause(1200)
        # qa: its question in the pane; Red, 送る
        await page.click(f"#rb-waits [data-rbw-robot='{rid['qa']}']")
        p = res["qaPane"] = await until(page, f"() => {{ const p = ({PANE})(); return p.shown && p.send ? p : null; }}", "qa's question in the pane", timeout=10000, why=PANE)
        check(failures, p.get("shown") and len(p["q"]) == 1 and p["send"] and p["focusIn"] and p["right"] <= p["cardLeft"] - 4 and p["top"] >= p["blockBottom"] and p["left"] >= 0
              and p["hit"],
              f"qa's row: its question (choices, 送る) in the pane, focused, beside the card and under the block: {p}")
        exp = res["qaExpanded"] = await page.evaluate("(id) => document.querySelector(`#rb-waits [data-rbw-robot=\"${id}\"]`).getAttribute('aria-expanded')", rid["qa"])
        check(failures, exp == "true", f"qa's row says the pane is open: {exp}")
        check(failures, await page.evaluate(CARD_ON, rid["host"]), "qa's row: the host's card stays")
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await settled(page, f"1440 pane {scheme}")
            await page.screenshot(path=str(out / f"card-waits-pane-1440-{scheme}.png"))
        await page.emulate_media(color_scheme="light")
        await pause(1500)
        await page.click("#rb-wait-pane label:has-text('Red')")
        await pause(800)
        await page.click("#rb-wait-pane [data-qsend]")
        got = res["qaHook"] = heard("qa")
        ans = (((got or {}).get("hookSpecificOutput") or {}).get("updatedInput") or {}).get("answers")
        check(failures, ans == {"Which colour?": "Red"}, f"qa: the answer from the pane reaches the waiting hook: {got}")
        hook("qa", hook_event_name="PostToolUse", tool_name="AskUserQuestion", tool_use_id="toolu_qa",
             tool_input={**QUESTION, "answers": ans or {}}, tool_response={"answers": ans or {}})
        await block("qa answered: its row gone", [rid[k] for k in ("perm", "ask", "den", "qb", "pa")], timeout=20000)
        p = res["qaAfter"] = await until(page, f"() => {{ const p = ({PANE})(); return p.shown ? null : p; }}", "qa answered: the pane closed", timeout=10000, why=PANE)
        check(failures, not p.get("shown"), f"qa answered: the pane closed: {p}")
        check(failures, await page.evaluate(CARD_ON, rid["host"]), "qa answered: the host's card stays")
        await pause(1500)
        # pa: its permission in the pane, 許可
        await page.click(f"#rb-waits [data-rbw-robot='{rid['pa']}']")
        p = res["paPane"] = await until(page, f"() => {{ const p = ({PANE})(); return p.shown && p.allow ? p : null; }}", "pa's permission in the pane", timeout=10000, why=PANE)
        check(failures, p.get("shown") and len(p["perm"]) == 1 and p["allow"], f"pa's row: its permission (allow / deny) in the pane: {p}")
        await pause(1500)
        await page.click("#rb-wait-pane [data-do='allow']")
        got = res["paHook"] = heard("pa")
        decision = ((got or {}).get("hookSpecificOutput") or {}).get("decision")
        check(failures, isinstance(decision, dict) and decision.get("behavior") == "allow", f"pa: allowed in the pane, the hook got allow: {got}")
        await block("pa allowed: its row gone", [rid[k] for k in ("perm", "ask", "den", "qb")], timeout=20000)
        p = res["paAfter"] = await until(page, f"() => {{ const p = ({PANE})(); return p.shown ? null : p; }}", "pa allowed: the pane closed", timeout=10000, why=PANE)
        check(failures, await page.evaluate(CARD_ON, rid["host"]), "pa allowed: the host's card stays")
        await pause(1500)
        # qb: open in the pane, answered in the panel's card: gone from the pane too (one state)
        await page.click(f"#rb-waits [data-rbw-robot='{rid['qb']}']")
        await until(page, f"() => {{ const p = ({PANE})(); return p.shown && p.send ? p : null; }}", "qb's question in the pane", timeout=10000, why=PANE)
        res["qbPanel"] = await page.evaluate("""() => { const c = [...document.querySelectorAll('#questions .qcard.q-open')].find((x) => x.textContent.includes('Which size?'));
          if (!c) return false; const l = [...c.querySelectorAll('label')].find((x) => x.textContent.includes('Large')); l.querySelector('input').click();
          c.querySelector('input[data-qk]').dispatchEvent(new Event('input', { bubbles: true })); const s = c.querySelector('[data-qsend]'); s.click(); return true; }""")
        got = res["qbHook"] = heard("qb")
        ans = (((got or {}).get("hookSpecificOutput") or {}).get("updatedInput") or {}).get("answers")
        check(failures, res["qbPanel"] and ans == {"Which size?": "Large"}, f"qb answered in the panel's card: {got}")
        p = res["qbAfter"] = await until(page, f"() => {{ const p = ({PANE})(); return p.shown ? null : p; }}", "qb answered elsewhere: the pane closed", timeout=15000, why=PANE)
        check(failures, not p.get("shown"), f"qb answered in the panel: gone from the pane too: {p}")
        # Esc closes the pane, the card stays
        await page.click(f"#rb-waits [data-rbw-robot='{rid['perm']}']")
        await until(page, f"() => {{ const p = ({PANE})(); return p.shown ? p : null; }}", "perm's pane again", timeout=10000, why=PANE)
        await pause(1000)
        await page.keyboard.press("Escape")
        p = res["esc"] = await until(page, f"() => {{ const p = ({PANE})(); return p.shown ? null : p; }}", "Esc closes the pane", timeout=10000, why=PANE)
        check(failures, not p.get("shown") and await page.evaluate(CARD_ON, rid["host"]), f"Esc: the pane closed, the host's card stays: {p}")
        await pause(1500)

        # nine robots waiting: six listed, the rest said as ほか N
        for k in MORE:
            hook(k, hook_event_name="SessionStart", source="startup")
            hook(k, hook_event_name="UserPromptSubmit", prompt="go")
            hook(k, hook_event_name="PreToolUse", tool_name="Bash", tool_use_id=f"toolu_{k}", tool_input={"command": "ls"})
            hook(k, hook_event_name="PermissionRequest", tool_name="Bash", tool_input={"command": "ls"})
        want_more = await page.evaluate("() => window.__dbg.tl('rbw.more', { n: 3 })")
        more = res["more"] = await until(page, "(w) => { const b = document.getElementById('rb-waits'), m = b.querySelector('.rbw-more');"
                                         " return m && m.textContent === w ? [b.querySelectorAll('[data-rbw-robot]').length, m.textContent] : null; }",
                                         "nine waiting: six and ほか 3", arg=want_more, timeout=30000,
                                         why="() => { const b = document.getElementById('rb-waits'); return [b.querySelectorAll('[data-rbw-robot]').length, (b.querySelector('.rbw-more') || {}).textContent || null]; }")
        check(failures, more[0] == 6, f"nine waiting: six robots listed and {want_more!r}: {more}")
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    finally:
        if browser is not None:
            await browser.close()
        srv.terminate()   # our own child (started above)
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
            srv.wait()
    for line in watch.console:
        failures.append(f"card-waits: console: {line}")
    print(f"  card-waits: {time.monotonic() - t0:.0f}s", flush=True)
