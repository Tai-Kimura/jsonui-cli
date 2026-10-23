"""What the person types is kept through a redraw, and a card's questions fold (2.3.21; requester 10-23: 「質問の回答書い
てる途中でこの履歴が更新されると書いてる内容が消える気がする」 and 「あとカードで質問の表示を閉じる機能も欲しい / 質問きてると
上のチャットが見えないから上のチャット確認して返事したい時にこまる」). Runs with `--only typed-kept`.

The family (every field the person types in that a redraw can draw again), each typed into, then drawn again — by a
new question, a new permission, or every keyed box drawn again at once (__dbg.redrawTyped, as a new record or a new
order draws them) — the box rebuilt (the field is a new element), and its text, cursor, focus and what was picked
still there:

  * the question card in the panel (#questions): a free answer typed, the cursor inside it; a new question comes
  * the same question on the task board's strip (#q-strip): what was typed in the panel is there; drawn again
  * the same question in the robot's card (応答の履歴, the box of cards): drawn again; a permission for the same session
  * the prompt box: typed for one robot, another robot's card, back: the text is back (a card that went and came back)
  * the price editor (単価): a new row's numbers typed, the focus elsewhere, drawn again
  * a permission's reason (the demo page: the live page shows it only with the relay): typed, drawn again

The fold (the robot's card, 応答の履歴): ▼ folds the box of cards to its bar — the history above gets taller, the bar
says what waits — and what was typed stays in the folded card; a new wait while folded keeps it folded with the new
count and moves the bar once; ▲ opens it, as it was. Stills: the card with its question open and folded, light and dark.
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

CWD = "/work/typed-kept-app"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
SID = {k: f"e2e00000-0000-4000-8000-0000000008{i:02d}" for i, k in enumerate(("a", "b", "c"), 1)}
QUESTION = {"questions": [{"question": "Which colour for the header?", "header": "Colour", "multiSelect": False,
                           "options": [{"label": "Red", "description": "warm"}, {"label": "Blue", "description": "cool"}]}]}
TYPED = "a half-typed answer"
# a field's state: its text, cursor, whether it has the focus, the other radio, the send button, and whether it is the
# element marked before the redraw (a redraw makes a new one)
FIELD = """(sel) => { const el = document.querySelector(sel); if (!el) return null;
  const card = el.closest('[data-qcard]'), other = card ? card.querySelector('input[data-qk="other"]') : null, send = card ? card.querySelector('[data-qsend]') : null;
  return { text: el.value, sel: [el.selectionStart, el.selectionEnd], focused: document.activeElement === el,
    other: other ? other.checked : null, send: send ? !send.disabled : null, marked: !!el._typedMark }; }"""
MARK = "(sel) => { const el = document.querySelector(sel); if (el) el._typedMark = true; return !!el; }"


def check(failures, cond, text):
    if not cond:
        failures.append(f"typed-kept: {text}")


async def type_in(page, sel, text, left=3):
    """Typed with the keyboard into ``sel``, the cursor then ``left`` characters back from the end."""
    await page.click(sel)
    await page.evaluate("(s) => { const el = document.querySelector(s); el.setSelectionRange(el.value.length, el.value.length); }", sel)   # after what is there
    await page.keyboard.type(text)
    for _ in range(left):
        await page.keyboard.press("ArrowLeft")


async def kept(page, failures, sel, label, redraw, want_text, want_focus=True, other=True):
    """Mark the field, draw it again (``redraw``), and compare."""
    before = await page.evaluate(FIELD, sel)
    await page.evaluate(MARK, sel)
    await redraw()
    try:
        after = await until(page, f"(s) => {{ const f = ({FIELD})(s); return f && !f.marked ? f : null; }}", f"{label}: drawn again", arg=sel,
                            timeout=15000, why=f"(s) => ({FIELD})(s)")
    except WaitTimeout as e:
        failures.append(f"typed-kept: {e}")
        return None
    ok = after["text"] == want_text and (not want_focus or (after["focused"] and after["sel"] == before["sel"])) and (not other or (after["other"] and after["send"]))
    check(failures, ok, f"{label}: drawn again, what was typed kept (text, cursor, focus, the picked choice): before {before}, after {after}")
    return after


async def run_typed_kept(pw, out, failures, Server, jt=None):
    from run import free_port
    name = "typed-kept"
    out = pathlib.Path(out) / name
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    (home / ".local" / "state" / "jui-viz" / "config.json").write_text(json.dumps({"askWaitSec": 600, "askMaxSec": 900}))
    sessions_dir = home / ".claude" / "sessions"   # watched by the server from its start
    sessions_dir.mkdir(parents=True, exist_ok=True)
    jt = pathlib.Path(jt) if jt else pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT,
                           env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"
    res: dict = {}
    browser, asks, demo, stand_ins = None, [], None, []
    t0 = time.monotonic()
    try:
        def hook(k, ask=False, **payload):
            body = {"session_id": SID[k], "cwd": CWD, "transcript_path": f"{home}/t-{k}.jsonl", "permission_mode": "default", **payload}
            p = subprocess.Popen([sys.executable, "-I", "-S", str(forward)] + (["--ask"] if ask else []), stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(base_env, HOME=str(home)))
            p.stdin.write(json.dumps(body).encode())
            p.stdin.close()
            p.stdin = None
            if ask:
                asks.append(p)
                return p
            p.wait(timeout=10)
            return None

        def question(k, use_id):
            pre = dict(hook_event_name="PreToolUse", tool_name="AskUserQuestion", tool_use_id=use_id, tool_input=QUESTION)
            hook(k, **pre)
            hook(k, ask=True, **pre)

        browser = await pw.chromium.launch(args=LAUNCH_ARGS)
        watch = Watch(origin=url)
        import http.client
        import urllib.request
        for _ in range(400):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        page = await new_page(browser, watch, name, **DESKTOP)
        await page.emulate_media(color_scheme="light", reduced_motion="no-preference")
        await page.goto(url + "/")
        await ready(page)
        await until(page, "() => document.querySelector('.chip.demo').dataset.net === 'connected'", "connected")
        # a and c can be sent a prompt (the prompt box enabled): each a running session with the channel, said hello
        for k in ("a", "c"):
            proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(900)", "--dangerously-load-development-channels", "plugin:jui-viz@jsonui"],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            stand_ins.append(proc)
            (sessions_dir / f"{proc.pid}.json").write_text(json.dumps({"pid": proc.pid, "sessionId": SID[k], "cwd": CWD, "kind": "interactive",
                                                                      "entrypoint": "cli", "status": "idle", "procStart": f"t{proc.pid}"}))
        for k in SID:
            hook(k, hook_event_name="SessionStart", source="startup")
        await until(page, "() => window.__dbg.robots.length >= 3", "three robots", timeout=40000, why="() => window.__dbg.settleInfo()")
        ids = await page.evaluate("() => Object.fromEntries(window.__dbg.robots.map((R) => [R.def.sessionId, R.def.id]))")
        rid = {k: ids[SID[k]] for k in SID}
        res["ids"] = rid
        token = json.loads((home / ".local" / "state" / "jui-viz" / "server.json").read_text())["token"]
        for k in ("a", "c"):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            conn.request("POST", "/channel/hello", body=json.dumps({"ppid": 1, "cwd": "/", "sessionId": SID[k], "version": "2", "accepts": ["prompt"], "via": "plugin"}),
                         headers={"X-Jui-Viz-Token": token, "Content-Type": "application/json"})
            r = conn.getresponse()
            res.setdefault("hello", {})[k] = [r.status, r.read().decode()[:200]]
            conn.close()
        await page.wait_for_timeout(5500)   # one presence report after the page is up (the hook waits for a page)

        # 1. the panel's card: typed, then a new question (another session) draws the list again
        question("a", "toolu_tk1")
        await until(page, "() => !!document.querySelector('#questions .qcard.q-open .qother-text')", "a's open question in the panel", timeout=20000)
        qa = await page.evaluate("() => document.querySelector('#questions .qcard.q-open').dataset.qcard")
        panel = f"#questions [data-qcard='{qa}'] .qother-text"
        await type_in(page, panel, TYPED)
        res["panel"] = await kept(page, failures, panel, "the panel's card, a new question", lambda: _q(question, "b", "toolu_tk2"), TYPED)

        # 2. the board's strip: the same question, what was typed in the panel already there
        await page.click("#chip-ask")
        await until(page, "() => window.__dbg.board().open", "the board")
        await until(page, "(q) => !!document.querySelector(`#q-strip [data-ps-go=\"q:${q}\"]`)", "the strip's line of the question", arg=qa, timeout=15000)
        await page.click(f"#q-strip [data-ps-go='q:{qa}']")   # the strips come folded: the line opens them
        strip = f"#q-strip [data-qcard='{qa}'] .qother-text"
        await until(page, "(s) => !!document.querySelector(s)", "the question on the board's strip", arg=strip, timeout=15000)
        s = await page.evaluate(FIELD, strip)
        check(failures, s and s["text"] == TYPED and s["other"], f"the board's strip: the same question has what was typed in the panel: {s}")
        await type_in(page, strip, " more", left=1)
        res["strip"] = await kept(page, failures, strip, "the board's strip, drawn again", lambda: page.evaluate("() => window.__dbg.redrawTyped()"), TYPED + " more")
        await page.evaluate("() => window.__dbg.closeTaskBoard()")
        await until(page, "() => !window.__dbg.board().open", "the board closed")
        await settled(page, "the board's zoom back")

        # 3. the robot's card, 応答の履歴: the same question in its box of cards
        await page.evaluate("(id) => window.__dbg.openRobot(id)", rid["a"])
        await until(page, "(id) => window.__dbg.board().robot === id && getComputedStyle(document.getElementById('rb')).opacity === '1'", "a's card", arg=rid["a"])
        await page.click("#rb [data-rb-tab='history']")
        hist = f"[data-h-cards] [data-qcard='{qa}'] .qother-text"
        await until(page, "(s) => !!document.querySelector(s)", "the question in the card's box", arg=hist, timeout=15000)
        await type_in(page, hist, " again", left=2)
        res["hist"] = await kept(page, failures, hist, "the card's box, drawn again", lambda: page.evaluate("() => window.__dbg.redrawTyped()"), TYPED + " more again")
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await settled(page, f"{scheme}")
            await page.locator("#rb").screenshot(path=str(out / f"card-question-open-{scheme}.png"))
        await page.emulate_media(color_scheme="light")

        # 4. the fold: ▼ the history taller, the card kept; a new wait while folded; ▲ as it was
        f0 = res["fold0"] = await page.evaluate("() => window.__dbg.histFold()")
        await page.click("[data-h-cards] [data-h-fold='close']")
        f1 = res["fold1"] = await until(page, "() => { const f = window.__dbg.histFold(); return f.folded ? f : null; }", "folded", timeout=10000)
        hidden = await page.evaluate("(s) => { const el = document.querySelector(s); return el ? [el.value, el.getClientRects().length] : null; }", hist)
        check(failures, f1["cardsH"] <= f0["cardsH"] - 20 and f1["histH"] >= f0["histH"] + (f0["cardsH"] - f1["cardsH"]) - 4 and hidden == [TYPED + " more again", 0],
              f"folded: the history taller ({f0['histH']} -> {f1['histH']}), the box one line ({f0['cardsH']} -> {f1['cardsH']}), the card hidden with what was typed: {hidden}")
        check(failures, f1["bar"] and "1" in f1["bar"] and "Which colour" in f1["bar"] and not f1["fresh"], f"folded: the bar says what waits, nothing new yet: {f1}")
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await settled(page, f"folded {scheme}")
            await page.locator("#rb").screenshot(path=str(out / f"card-question-folded-{scheme}.png"))
        await page.emulate_media(color_scheme="light")
        hook("a", hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="toolu_tk_make", tool_input={"command": "make"})
        hook("a", hook_event_name="PermissionRequest", tool_name="Bash", tool_input={"command": "make"})
        f2 = res["fold2"] = await until(page, "(w) => { const f = window.__dbg.histFold(); return !f.folded || (f.bar && f.bar.includes(w)) ? f : null; }",
                                        "folded, the new wait counted", arg=await page.evaluate("() => window.__dbg.tl('hist.fold.p', { n: 1 })"), timeout=15000, why="() => window.__dbg.histFold()")
        check(failures, f2["folded"] and f2["fresh"], f"a new wait while folded: still folded (the person is reading), the new count, marked: {f2}")
        await page.click("[data-h-cards] [data-h-fold='open']")
        f3 = res["fold3"] = await until(page, "() => { const f = window.__dbg.histFold(); return !f.folded ? f : null; }", "opened", timeout=10000)
        back = await page.evaluate(FIELD, hist)
        check(failures, abs(f3["histH"] - f0["histH"]) <= 80 and back and back["text"] == TYPED + " more again" and back["other"],
              f"opened: the history as before ({f0['histH']} -> {f3['histH']}), what was typed and picked there: {back}")

        # 4b. nothing waits any more: the fold is forgotten, the next wait comes open
        await page.click("[data-h-cards] [data-h-fold='close']")
        await until(page, "() => window.__dbg.histFold().folded", "folded again", timeout=10000)
        hook("a", hook_event_name="PostToolUse", tool_name="AskUserQuestion", tool_use_id="toolu_tk1", tool_input=QUESTION, tool_response={"answers": {}})
        hook("a", hook_event_name="PostToolUse", tool_name="Bash", tool_use_id="toolu_tk_make", tool_input={"command": "make"}, tool_response={"stdout": ""})
        res["cleared"] = await until(page, "() => { const f = window.__dbg.histFold(); return !f.bar ? f : null; }", "nothing waits on a any more", timeout=20000,
                                     why="() => window.__dbg.histFold()")
        hook("a", hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="toolu_tk_test", tool_input={"command": "make test"})
        hook("a", hook_event_name="PermissionRequest", tool_name="Bash", tool_input={"command": "make test"})
        f5 = res["fold5"] = await until(page, "() => { const f = window.__dbg.histFold(); return f.bar ? f : null; }", "a new wait on a", timeout=20000,
                                        why="() => window.__dbg.histFold()")
        check(failures, not f5["folded"] and f5["bar"] == await page.evaluate("() => window.__dbg.tl('hist.fold.close')"),
              f"folded, then nothing waited, then a new wait: the box comes open (the fold forgotten): {f5}")

        # 5. the prompt box: typed for a, another robot, back to a
        area = "#rb [data-h-text]"
        await until(page, "(s) => { const a = document.querySelector(s); return !!a && !a.disabled; }", "a's prompt box takes text", arg=area, timeout=20000,
                    why="() => { const w = document.querySelector('#rb [data-h-why]'); return w ? w.textContent : null; }")
        await page.click(area)
        await page.keyboard.type("a prompt for a")
        await page.evaluate("(id) => window.__dbg.openRobot(id)", rid["c"])
        await until(page, "(id) => window.__dbg.board().robot === id", "c's card", arg=rid["c"])
        other_text = await until(page, "() => { const a = document.querySelector('#rb [data-h-text]'); return a ? [a.value] : null; }", "c's prompt box", timeout=10000)
        await page.evaluate("(id) => window.__dbg.openRobot(id)", rid["a"])
        await until(page, "(id) => window.__dbg.board().robot === id", "a's card again", arg=rid["a"])
        res["prompt"] = back = await until(page, "() => { const a = document.querySelector('#rb [data-h-text]'); return a ? [a.value] : null; }", "a's prompt box", timeout=10000)
        check(failures, other_text == [""] and back == ["a prompt for a"],
              f"the prompt box: typed for a, c's card, back to a: c's box {other_text}, a's box {back} (the text typed for a, kept)")

        # 6. the price editor: a new row's numbers, the focus elsewhere, drawn again
        await page.click("#rb-close")
        await page.evaluate("() => window.__dbg.openPrices()")
        await until(page, "() => !!document.querySelector('[data-pr-add=\"\"]')", "the price editor", timeout=10000)
        await page.click("[data-pr-add='']")
        await page.click("[data-pr-in='model']")
        await page.keyboard.type("my-model-x")
        await page.click("[data-pr-in='input']")
        await page.keyboard.type("1.25")
        await page.evaluate("() => document.activeElement.blur()")
        await page.evaluate("() => { document.querySelector('[data-pr-in=\"input\"]')._typedMark = true; window.__dbg.pricesRedraw(); }")
        pr = res["prices"] = await page.evaluate("""() => { const m = document.querySelector('[data-pr-in="model"]'), i = document.querySelector('[data-pr-in="input"]');
          return m && i ? { model: m.value, input: i.value, rebuilt: !i._typedMark } : null; }""")
        check(failures, pr and pr["rebuilt"] and pr["model"] == "my-model-x" and pr["input"] == "1.25", f"the price editor, drawn again: the numbers typed kept: {pr}")
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))

        # 7. a permission's reason, on the demo page
        demo = Server()
        dpage = await new_page(browser, Watch(origin=demo.url), f"{name}-demo", **DESKTOP)
        await dpage.goto(f"{demo.url}/?demo=1")
        await ready(dpage)
        pid = await until(dpage, "() => { const p = window.__dbg.pendingPerms(); return p.length ? p[0] : null; }", "a demo permission", timeout=30000)
        await dpage.click("#btn-play")   # the demo's clock still: the permission stays
        await dpage.evaluate("(id) => window.__dbg.openTaskBoard('perm:' + id)", pid)
        reason = "#tb-detail .tbd-reason input"
        await until(dpage, "(s) => !!document.querySelector(s)", "the permission's reason field", arg=reason, timeout=15000)
        await type_in(dpage, reason, "not on main", left=4)
        res["reason"] = await kept(dpage, failures, reason, "a permission's reason, drawn again", lambda: dpage.evaluate("() => window.__dbg.redrawTyped()"), "not on main", other=False)
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    finally:
        for p in stand_ins:
            p.kill()   # our own session stand-ins
            p.wait(timeout=5)
        for p in asks:
            if p.poll() is None:
                p.kill()   # our own forward.py --ask
                p.wait(timeout=5)
        if browser is not None:
            await browser.close()
        if demo is not None:
            demo.stop()
        srv.terminate()   # our own child (started above)
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
            srv.wait()
    print(f"  typed-kept: {time.monotonic() - t0:.0f}s", flush=True)


async def _q(question, k, use_id):
    question(k, use_id)
