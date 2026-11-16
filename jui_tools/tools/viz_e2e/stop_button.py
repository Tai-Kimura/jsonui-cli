"""停止 in the robot card's 応答の履歴 tab, end to end (2.3.20, ticket 2026-10-22-viz-no-way-to-stop-a-session-from-the-page).
Runs with `--only stop-button`.

The real `jui viz serve` in a throwaway HOME on a free port and the real forward.py for the hooks, the --stop one
included. Two working sessions: one whose --stop hook has been heard (jui-viz 1.3.0), one whose hook never was (an
older plugin). Neither has the relay, so the prompt box is disabled: the stop button does not need it.

Checked: the button shows beside 送信 while the session works and not once it is idle; a press asks the server
(stopAt) and the line says it stops once the tool now running has finished; a second press takes it back and the hook
then prints nothing; asked again, the session's next --stop hook prints {"continue": false}, and so does every later
one of that turn, the server ends the turn at that call's PostToolUse (no Stop hook comes), and the line says when it
stopped; the next prompt's synchronous --stop takes the stop away, so the new turn's first tool is not stopped; a
subagent's card has no stop button (its box says to write to the main); the session whose hook was never heard is
asked all the same and the line says it may not stop. Dark and 390 px; no console error; nothing outside the server.
"""

from __future__ import annotations

import http.client
import json
import os
import pathlib
import re
import subprocess
import sys
import time

from common import DESKTOP, ISOLATE, LAUNCH_ARGS, PHONE, T, T_head, T_pattern, Watch, dump, new_page, ready

S_NEW = "e2e00000-0000-4000-8000-0000000000f1"
S_OLD = "e2e00000-0000-4000-8000-0000000000f2"
CWD = "/work/stop-button"


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


STOP = """() => { const b = document.querySelector('[data-h-compose] [data-h-stop]'), s = document.querySelector('[data-h-compose] [data-h-stop-state]');
  return { shown: !!b && !b.hidden && b.offsetParent !== null, text: b ? b.textContent : '', disabled: !!b && b.disabled,
    line: s && !s.hidden ? s.textContent : '', phase: s ? s.dataset.hStopPhase || '' : '',
    boxOff: document.querySelector('[data-h-compose] [data-h-text]').disabled }; }"""


async def run_stop_button(pw, out, failures, video: pathlib.Path | None = None):
    from run import free_port
    out = pathlib.Path(out) / "stop-button"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    state = home / ".local" / "state" / "jui-viz"
    state.mkdir(parents=True, exist_ok=True)
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}
    pause = (lambda ms: page.wait_for_timeout(ms)) if video else None

    def check(cond, text):
        if not cond:
            failures.append(f"stop-button: {text}")

    def hook(sid, payload, flag=None) -> bytes:
        args = [sys.executable, "-I", "-S", str(forward)] + ([flag] if flag else [])
        p = subprocess.run(args, input=json.dumps({"session_id": sid, "cwd": CWD, "permission_mode": "default", **payload}).encode(),
                           capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)
        return p.stdout

    def tool(sid, kind, use_id, command="npm test"):
        return hook(sid, {"hook_event_name": kind, "tool_name": "Bash", "tool_use_id": use_id, "tool_input": {"command": command}})

    def stop_hook(sid, kind, use_id, command="npm test") -> bytes:
        return hook(sid, {"hook_event_name": kind, "tool_name": "Bash", "tool_use_id": use_id, "tool_input": {"command": command}}, "--stop")

    def snapshot_session(sid):
        token = json.loads((state / "server.json").read_text())["token"]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request("GET", "/api/snapshot", headers={"X-Jui-Viz-Token": token})
            snap = json.loads(conn.getresponse().read())
        finally:
            conn.close()
        return next(s for s in snap["slices"]["sessions"] if s["id"] == sid)

    async def open_robot(page, sid):
        label = snapshot_session(sid)["label"]
        await page.evaluate("(l) => document.querySelector(`#sessions [data-robot-open=\"${l}\"]`).click()", label)
        await wait(page, "(l) => document.getElementById('rb-title') && document.getElementById('rb-title').textContent.startsWith(l)", arg=label, label="the card")
        if await page.evaluate("() => document.querySelector('[data-rb-hist]').hidden"):
            await page.click('#rb [data-rb-tab="history"]')
        await wait(page, "() => !!document.querySelector('[data-h-compose]') && !document.querySelector('[data-h-compose]').hidden", label="the box")
        return label

    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    t0 = time.monotonic()
    try:
        import urllib.request
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        for sid, prompt in ((S_NEW, "画面のテストを直して"), (S_OLD, "ログを読んで")):
            hook(sid, {"hook_event_name": "SessionStart", "source": "startup"})
            hook(sid, {"hook_event_name": "UserPromptSubmit", "prompt": prompt})
        # S_NEW's plugin has the hook: one call heard through it. S_OLD's calls go only through the async forward.
        tool(S_NEW, "PreToolUse", "n0", "ls")
        check(stop_hook(S_NEW, "PreToolUse", "n0", "ls") == b"", "nothing asked: the hook prints nothing")
        tool(S_NEW, "PostToolUse", "n0", "ls")
        tool(S_NEW, "PreToolUse", "n1")   # npm test: running while the page asks
        hook(S_NEW, {"hook_event_name": "SubagentStart", "agent_id": "agent-stop-sub", "agent_type": "Explore"})
        tool(S_OLD, "PreToolUse", "o1", "cat app.log")
        res["heard"] = {"new": snapshot_session(S_NEW).get("stopHook"), "old": snapshot_session(S_OLD).get("stopHook")}
        check(res["heard"] == {"new": True, "old": None}, f"the hook heard from one session only: {res['heard']}")

        watch = Watch(origin=url)
        opts = dict(DESKTOP, record_video_dir=str(video), record_video_size=DESKTOP["viewport"]) if video else DESKTOP
        context = await browser.new_context(**opts)
        page = await context.new_page()
        watch.attach(page, "stop-button")
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelectorAll('#sessions [data-robot-open]').length >= 2", label="the sessions")
        await open_robot(page, S_NEW)
        if pause:
            await pause(2500)

        # 1. working: the button beside 送信, though the prompt box is off (no relay)
        r = res["working"] = await page.evaluate(STOP)
        check(r["shown"] and r["text"] == T("hist.stop") and not r["disabled"] and r["line"] == "" and r["boxOff"],
              f"a working session: 停止 shows, the box is off: {r}")
        res["title"] = await page.evaluate("() => document.querySelector('[data-h-stop]').title")
        check(res["title"] == T("hist.stop.title"), f"the button's title says where it stops: {res['title']!r}")
        await page.screenshot(path=str(out / "working.png"))
        # a subagent's card: the same box (it says to write to the main), no stop button
        sub = await page.evaluate("() => window.__dbg.robots.find((R) => R.def.kind === 'sub')?.def.id || null")
        check(sub is not None, "the subagent's robot")
        if sub:
            await page.evaluate("(i) => window.__dbg.openRobot(i)", sub)
            await wait(page, "(w) => { const c = document.querySelector('[data-h-compose]'); return !!c && !c.hidden && c.textContent.includes(w); }",
                       arg=T_head("hist.why.sub", "main"), label="the subagent's box")
            r = res["sub"] = await page.evaluate(STOP)
            check(not r["shown"] and r["line"] == "", f"a subagent's card: no stop button: {r}")
            await page.keyboard.press("Escape")
            await open_robot(page, S_NEW)

        # 2. a press asks; a second press takes it back, and the hook prints nothing
        await page.click("[data-h-stop]")
        await wait(page, f"() => ({STOP})().phase === 'waiting'", label="the waiting line")
        r = res["asked"] = await page.evaluate(STOP)
        check(r["line"] == T("hist.stop.waiting") and r["text"] == T("hist.stop.cancel"), f"asked: the line and 取り消す: {r}")
        check(snapshot_session(S_NEW).get("stopAt", 0) > 0, "the server keeps the request")
        await page.screenshot(path=str(out / "asked.png"))
        if pause:
            await pause(2500)
        await page.click("[data-h-stop]")
        await wait(page, f"() => ({STOP})().phase === ''", label="taken back")
        check("stopAt" not in snapshot_session(S_NEW), "taken back on the server")
        check(stop_hook(S_NEW, "PostToolUse", "n1") == b"", "taken back: the hook prints nothing")
        if pause:
            await pause(1500)

        # 3. asked again: the next boundary stops it, and every later one of the turn; the server ends the turn
        await page.click("[data-h-stop]")
        await wait(page, f"() => ({STOP})().phase === 'waiting'", label="asked again")
        if pause:
            await pause(3000)
        tool(S_NEW, "PostToolUse", "n1")
        got = stop_hook(S_NEW, "PreToolUse", "n2", "npm run build")
        res["handedOut"] = got.decode()
        check(json.loads(got or b"{}") == {"continue": False, "stopReason": T("stop.reason")}, f"the hook stops the session: {got!r}")
        check(stop_hook(S_NEW, "PreToolUse", "n2", "npm run build") == got, "the same answer at the turn's next boundary")
        tool(S_NEW, "PreToolUse", "n2", "npm run build")
        tool(S_NEW, "PostToolUse", "n2", "npm run build")   # the call still runs (measured), then the turn has ended
        # stoppedAt (the hook) and the idle status (that call's PostToolUse) may reach the page in two pushes
        await wait(page, f"() => {{ const r = ({STOP})(); return r.phase === 'done' && !r.shown; }}", label="the stopped line, the button gone")
        r = res["stopped"] = await page.evaluate(STOP)
        s = snapshot_session(S_NEW)
        check(s["status"] == "idle" and s.get("stoppedAt", 0) > 0 and "stopAt" not in s, f"the turn ended on the server: {s.get('status')}")
        check(not r["shown"] and T_pattern("hist.stop.done", time=re.compile(r"\d\d:\d\d(?:\s[AP]M)?")).fullmatch(r["line"]),   # HH:MM in the page's locale (en-US: 09:09 AM)
              f"stopped: the button is gone, the line says when: {r}")
        await page.screenshot(path=str(out / "stopped.png"))
        if pause:
            await pause(3000)
        # the next prompt: its synchronous --stop takes the stop away before the new turn's first tool asks
        check(hook(S_NEW, {"hook_event_name": "UserPromptSubmit", "prompt": "続けて"}, "--stop") == b"", "the prompt's hook prints nothing")
        check(stop_hook(S_NEW, "PreToolUse", "n3", "npm test") == b"", "the new turn's first tool is not stopped")
        check(not ({"stopAt", "stopTurn"} & set(snapshot_session(S_NEW))), "the stop is gone with the new prompt")

        # 4. a session whose hook was never heard: asked all the same, the line says it may not stop
        await open_robot(page, S_OLD)
        await page.click("[data-h-stop]")
        await wait(page, f"() => ({STOP})().phase === 'old'", label="the old plugin's line")
        r = res["old"] = await page.evaluate(STOP)
        check(r["line"] == T("hist.stop.old"), f"an older plugin: the line says so: {r}")
        await page.screenshot(path=str(out / "old.png"))
        if pause:
            await pause(3000)
        await page.click("[data-h-stop]")   # taken back: the dark and phone shots start from a plain button
        await wait(page, f"() => ({STOP})().phase === ''", label="taken back (old)")

        await page.emulate_media(color_scheme="dark")
        await page.click("[data-h-stop]")
        await wait(page, f"() => ({STOP})().phase === 'old'", label="asked in dark")
        await page.screenshot(path=str(out / "dark.png"))
        phone = await new_page(browser, watch, "stop-button-phone", **PHONE)
        await phone.goto(url + "/")
        await ready(phone)
        await wait(phone, "() => document.querySelectorAll('#sessions [data-robot-open]').length >= 2", label="the phone's sessions")
        await open_robot(phone, S_OLD)
        await wait(phone, f"() => ({STOP})().phase === 'old'", label="the phone's line")
        r = res["phone"] = await phone.evaluate("""() => { const b = document.querySelector('[data-h-stop]').getBoundingClientRect();
          return { hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                   inside: b.left >= 0 && b.right <= document.documentElement.clientWidth }; }""")
        await phone.screenshot(path=str(out / "phone.png"))
        check(r == {"hscroll": False, "inside": True}, f"390 px: the button fits, no horizontal scroll: {r}")
        await phone.close()
        await page.close()
        await context.close()
        for line in watch.console:
            failures.append(f"stop-button: console: {line}")
        for u in watch.foreign:
            failures.append(f"stop-button: request outside the server: {u}")
    except Exception as e:
        failures.append(f"stop-button: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  stop-button: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "stop-button-results.json").write_text(dump(res) + "\n")
