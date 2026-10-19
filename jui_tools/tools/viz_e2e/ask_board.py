"""The 質問 / 許可待ち chips open the board of what waits for an answer, end to end (2.3.5, requester 10-19: "このヘッダーの
許可のチップクリックでボード表示してほしい").

The real `jui viz serve` in a throwaway HOME and the real forward.py. Two sessions each ask a question (the synchronous
`forward.py --ask` waits) and a third asks for a permission (`forward.py --decide` waits). With the side panel closed:

  - Enter on the 質問 chip opens the board; it shows every waiting question and permission, none twice (the board's
    cards are the panel's cards, from the same list), and the count matches the chips;
  - a question answered on the board: its hook gets the answer, the card leaves the waiting state on the board and in
    the panel, the chip counts one less, and that robot stops waiting; the permission allowed on the board likewise;
  - Esc closes the board and the focus goes back to the chip; Space on the 許可待ち chip opens it as well;
  - nothing waiting: no chip (the chips hide; there is nothing to press).
Then with the panel open, the chip opens the same board. No console error, nothing requested outside the server.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import ISOLATE, DESKTOP, LAUNCH_ARGS, Watch, dump, new_page, ready

Q = {"questions": [{"question": "どちらにしますか", "header": "選択", "multiSelect": False,
                    "options": [{"label": "左", "description": "左にする"}, {"label": "右", "description": "右にする"}]}]}
SIDS = {"a": "e2e00000-0000-4000-8000-0000000000e1", "b": "e2e00000-0000-4000-8000-0000000000e2", "c": "e2e00000-0000-4000-8000-0000000000e3"}

BOARD = """() => { const tb = document.getElementById('tb'), side = document.querySelector('.main');
  const ids = [...tb.querySelectorAll('[data-qcard]')].map((c) => c.dataset.qcard);
  const pend = [...tb.querySelectorAll('[data-qcard].q-open')].map((c) => c.dataset.qcard);
  const perms = [...tb.querySelectorAll('#perm-strip .pcard [data-do="allow"]')].map((b) => b.dataset.perm);
  return { open: !tb.hidden && tb.classList.contains('show'), sideClosed: side.classList.contains('side-closed'), ids, pend, perms,
    panelPend: [...document.querySelectorAll('#questions [data-qcard].q-open')].map((c) => c.dataset.qcard),
    chipAsk: document.getElementById('chip-ask').hidden ? null : document.getElementById('chip-ask').textContent,
    chipPerm: document.getElementById('chip-perm').hidden ? null : document.getElementById('chip-perm').textContent,
    focus: document.activeElement ? (document.activeElement.id || document.activeElement.tagName) : null }; }"""
ROBOTS = "() => Object.fromEntries(Object.entries(window.__dbg.robotState()).map(([k, v]) => [k, v.state]))"


def check(failures, cond, text):
    if not cond:
        failures.append(f"ask-board: {text}")


async def wait(page, js, timeout=20000, label=""):
    try:
        await page.wait_for_function(js, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def run_ask_board(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "ask-board"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    (home / ".local" / "state" / "jui-viz" / "config.json").write_text(json.dumps({"askWaitSec": 60, "askMaxSec": 120}))
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT,
                           env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"
    res: dict = {}
    waiting: list = []

    def body(k, **payload):
        return {"session_id": SIDS[k], "cwd": f"/work/board-{k}", "transcript_path": "/work/home/t.jsonl", "permission_mode": "default", **payload}

    def hook(payload, flag=None):
        args = [sys.executable, "-I", "-S", str(forward)] + ([flag] if flag else [])
        p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(base_env, HOME=str(home)))
        p.stdin.write(json.dumps(payload).encode())
        p.stdin.close()
        p.stdin = None
        if flag:
            waiting.append(p)
            return p
        p.wait(timeout=10)
        return None

    def ask(k, use_id):
        pre = body(k, hook_event_name="PreToolUse", tool_name="AskUserQuestion", tool_use_id=use_id, tool_input=Q)
        hook(pre)
        return hook(pre, "--ask")

    def perm(k):
        req = body(k, hook_event_name="PermissionRequest", tool_name="Bash", tool_input={"command": "ls -la /tmp", "description": "一覧"})
        hook(body(k, hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="bash-1", tool_input={"command": "ls -la /tmp"}))
        hook(req)
        return hook(req, "--decide")

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
        page = await new_page(browser, watch, "ask-board", **DESKTOP)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", label="connected")
        for k in SIDS:
            hook(body(k, hook_event_name="SessionStart", source="startup"))
        await wait(page, "() => window.__dbg.robots.length === 3", label="three robots")
        await page.wait_for_timeout(5500)   # one presence report after the page is up (the --ask hooks wait only for a visible page)
        qa, qb, pc = ask("a", "ask-a"), ask("b", "ask-b"), perm("c")
        await wait(page, "() => document.querySelectorAll('#questions .qcard.q-open').length === 2 && !document.getElementById('chip-perm').hidden", timeout=20000, label="two questions and a permission")
        res["robotsBefore"] = before = await page.evaluate(ROBOTS)
        # the panel closed
        await page.click("#btn-side")
        await wait(page, "() => document.querySelector('.main').classList.contains('side-closed')", label="the panel closed")
        await page.screenshot(path=str(out / "chips-panel-closed.png"))
        # Enter on the 質問 chip
        await page.focus("#chip-ask")
        await page.keyboard.press("Enter")
        await wait(page, "() => { const tb = document.getElementById('tb'); return !tb.hidden && tb.classList.contains('show'); }", label="the board opens")
        await page.wait_for_timeout(500)
        b = res["opened"] = await page.evaluate(BOARD)
        check(failures, b["open"] and b["sideClosed"], f"Enter on the 質問 chip opens the board with the panel closed: {b}")
        check(failures, sorted(b["pend"]) == sorted(set(b["pend"])) and len(b["pend"]) == 2 and len(b["ids"]) == len(set(b["ids"])), f"every waiting question once: {b['ids']} {b['pend']}")
        check(failures, b["chipAsk"] == f"質問 {len(b['pend'])}" and b["chipPerm"] == f"許可待ち {len(b['perms'])}" and len(b["perms"]) == 1 and len(set(b["perms"])) == 1,
              f"the board's counts are the chips': {b}")
        check(failures, set(b["pend"]) == set(b["panelPend"]), f"the board's questions are the panel's: {b['pend']} vs {b['panelPend']}")
        await page.screenshot(path=str(out / "board-light.png"))
        await page.emulate_media(color_scheme="dark")
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(out / "board-dark.png"))
        await page.emulate_media(color_scheme="light")
        # answer the first question on the board
        first = b["pend"][0]
        await page.click(f"#q-strip [data-qcard='{first}'] label:has-text('右')")
        await page.click(f"#q-strip [data-qcard='{first}'] [data-qsend]")
        outs = {}
        for k, p in (("a", qa), ("b", qb)):
            try:
                o, _ = p.communicate(timeout=3 if outs else 30)
                if o:
                    outs[k] = o
            except subprocess.TimeoutExpired:
                pass
        answered = [json.loads(o) for o in outs.values() if o]
        # what Claude Code does next with the hook's answer: the tool runs and PostToolUse comes (as ask.py does)
        for k in outs:
            hook(body(k, hook_event_name="PostToolUse", tool_name="AskUserQuestion", tool_use_id=f"ask-{k}",
                      tool_input={**Q, "answers": {"どちらにしますか": "右"}}, tool_response={"answers": {"どちらにしますか": "右"}}))
        res["hookAnswer"] = answered
        ans = (((answered[0] if answered else {}).get("hookSpecificOutput") or {}).get("updatedInput") or {}).get("answers")
        check(failures, len(answered) == 1 and ans == {"どちらにしますか": "右"}, f"the hook got the board's answer: {answered}")
        await wait(page, f"() => !document.querySelector('#tb [data-qcard=\"{first}\"].q-open') && !document.querySelector('#questions [data-qcard=\"{first}\"].q-open')", timeout=15000, label="the answered card leaves the waiting state")
        await page.wait_for_timeout(1500)
        b2 = res["afterAnswer"] = await page.evaluate(BOARD)
        rob = res["robotsAfterAnswer"] = await page.evaluate(ROBOTS)
        check(failures, first not in b2["pend"] and first not in b2["panelPend"] and b2["chipAsk"] == "質問 1", f"answered on the board: gone from the board and the panel, the chip counts 1: {b2}")
        changed = [k for k in rob if before.get(k) == "waiting" and rob[k] != "waiting"]
        check(failures, len(changed) >= 1, f"the robot that asked stops waiting: {before} -> {rob}")
        # allow the permission on the board
        await page.click(f"#perm-strip [data-do='allow'][data-perm='{b['perms'][0]}']")
        try:
            o, _ = pc.communicate(timeout=30)
            res["permHook"] = json.loads(o) if o else None
        except subprocess.TimeoutExpired:
            res["permHook"] = "timeout"
        decision = ((res["permHook"] or {}).get("hookSpecificOutput") or {}).get("decision") if isinstance(res["permHook"], dict) else None
        check(failures, isinstance(decision, dict) and decision.get("behavior") == "allow", f"the permission hook got allow from the board: {res['permHook']}")
        hook(body("c", hook_event_name="PostToolUse", tool_name="Bash", tool_use_id="bash-1", tool_input={"command": "ls -la /tmp"}, tool_response={"stdout": ""}))
        await wait(page, "() => document.getElementById('chip-perm').hidden", timeout=15000, label="the 許可待ち chip goes")
        # Esc: the board closes, the focus is back on the chip
        await page.keyboard.press("Escape")
        await wait(page, "() => document.getElementById('tb').hidden", label="Esc closes the board")
        await page.wait_for_timeout(900)
        res["focusAfterEsc"] = await page.evaluate("() => document.activeElement && document.activeElement.id")
        check(failures, res["focusAfterEsc"] == "chip-ask", f"the focus goes back to the chip: {res['focusAfterEsc']}")
        check(failures, await page.evaluate("() => document.querySelectorAll('#tb [data-qcard]').length") == 0, "a closed board keeps no copy of the cards")
        # the panel open: the chip opens the same board; then the last question answered there
        await page.click("#btn-side")
        await wait(page, "() => !document.querySelector('.main').classList.contains('side-closed')", label="the panel open")
        await page.click("#chip-ask")
        await wait(page, "() => { const tb = document.getElementById('tb'); return !tb.hidden && tb.classList.contains('show'); }", label="the board, panel open")
        await page.wait_for_timeout(500)
        b3 = res["panelOpen"] = await page.evaluate(BOARD)
        check(failures, b3["open"] and not b3["sideClosed"] and len(b3["pend"]) == 1 and set(b3["pend"]) == set(b3["panelPend"]), f"with the panel open, the same board: {b3}")
        last = b3["pend"][0] if b3["pend"] else None
        if last:
            await page.click(f"#q-strip [data-qcard='{last}'] label:has-text('左')")
            await page.click(f"#q-strip [data-qcard='{last}'] [data-qsend]")
            for k, p in (("a", qa), ("b", qb)):
                if p.poll() is None:
                    try:
                        o, _ = p.communicate(timeout=30)
                    except subprocess.TimeoutExpired:
                        o = b""
                    if o:
                        hook(body(k, hook_event_name="PostToolUse", tool_name="AskUserQuestion", tool_use_id=f"ask-{k}",
                                  tool_input={**Q, "answers": {"どちらにしますか": "左"}}, tool_response={"answers": {"どちらにしますか": "左"}}))
            await wait(page, "() => document.getElementById('chip-ask').hidden", timeout=20000, label="nothing waits: the chip goes")
            b4 = res["nothing"] = await page.evaluate(BOARD)
            note = await page.evaluate("() => document.getElementById('q-strip').textContent")
            res["noneNote"] = note
            check(failures, b4["chipAsk"] is None and b4["chipPerm"] is None and b4["pend"] == [] and "答えを待っている質問はない" in note,
                  f"nothing waiting: no chip, the board says so: {b4} {note[:80]!r}")
            await page.screenshot(path=str(out / "board-nothing.png"))
        # Space on the 許可待ち chip: a new permission, the panel closed
        await page.keyboard.press("Escape")
        await wait(page, "() => document.getElementById('tb').hidden", label="closed again")
        pc2 = perm("c")
        await wait(page, "() => !document.getElementById('chip-perm').hidden", timeout=20000, label="the 許可待ち chip again")
        await page.focus("#chip-perm")
        await page.keyboard.press(" ")
        await wait(page, "() => { const tb = document.getElementById('tb'); return !tb.hidden && tb.classList.contains('show'); }", label="Space opens the board")
        b5 = res["space"] = await page.evaluate(BOARD)
        check(failures, b5["open"] and len(b5["perms"]) == 1, f"Space on the 許可待ち chip opens the board with the permission: {b5}")
        await page.click(f"#perm-strip [data-do='deny'][data-perm='{b5['perms'][0]}']")
        try:
            pc2.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            pass
        await page.close()
        for line in watch.console:
            failures.append(f"ask-board: console: {line}")
        for u in watch.foreign:
            failures.append(f"ask-board: request outside the server: {u}")
    except Exception as e:
        failures.append(f"ask-board: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        for p in waiting:
            if p.poll() is None:
                p.kill()
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  ask-board: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "ask-board-results.json").write_text(dump(res) + "\n")
