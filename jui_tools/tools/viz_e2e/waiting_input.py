"""The waiting-for-input notification (ticket 2026-10-20-jui-viz-notify-waiting-for-input; requester: 「ステータスの中に
入力待ちってのがありそうなんだけど、検知できる？ … 検知出来るなら許可とかと同じように通知鳴らして欲しい」).

Claude Code says a session waits for the person with the Notification hook, notification_type idle_prompt. The page
shows it as permissions and questions are shown: one Web notification (「入力待ち: <session>」) and the chime, from
one tab, by the yield and quiet rules of the chime; its own switch in the settings; never a second ring for a turn
whose 完了 notification has already gone out (or was taken quietly).

Measured by the requester (10-20 10:36, an isolated real claude, plugin 1.2.1's Notification hook): Stop at 10:36:45,
then 60 s later {"message":"Claude is waiting for your input","notification_type":"idle_prompt"}. The ruling (cd): the
notification is a reminder — not rung when, since that Stop, the person clicked its 完了 notification or opened that
session on the page; otherwise once. The hooks are replayed here through forward.py in that shape.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import DESKTOP, ISOLATE, LAUNCH_ARGS, Watch, dump, ready  # noqa: E402
from notify import CHIMES, SHOWN, STUB, wait  # noqa: E402

SID = "1d1e0000-0000-4000-8000-00000000000a"


def check(failures, cond, text):
    if not cond:
        failures.append(f"waiting-input: {text}")


async def run_waiting_input(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "waiting-input"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT,
                           env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def body(**payload):
        return {"session_id": SID, "cwd": "/work/idle-app", "transcript_path": "/work/home/t.jsonl", "permission_mode": "default", **payload}

    def hook(payload):
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(payload).encode(), capture_output=True,
                       env=dict(base_env, HOME=str(home)), timeout=10)

    def turn_then_idle(idle=True):
        hook(body(hook_event_name="UserPromptSubmit", prompt="go"))
        hook(body(hook_event_name="Stop"))
        if idle:
            hook(body(hook_event_name="Notification", notification_type="idle_prompt", message="Claude is waiting for your input"))

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
        ctx = await browser.new_context(**DESKTOP)
        await ctx.add_init_script(STUB)
        a = await ctx.new_page()
        watch.attach(a, "waiting-input")
        await a.goto(url + "/")
        await ready(a)
        await wait(a, "() => Object.keys(window.__dbg.robotState()).length >= 1", timeout=30000, label="the robot")
        await a.click("#btn-notify")
        await a.click("#notify-ask-perm")
        await wait(a, "() => document.getElementById('notify-perm-state').textContent.includes('許可済み')", label="granted")
        res["switch"] = await a.evaluate("() => { const e = document.querySelector('[data-notify-kind=\"idle\"]'); return e ? [e.checked, e.closest('label').textContent.trim()] : null; }")
        check(failures, bool(res["switch"]) and res["switch"][0] is True, f"the settings have the waiting-for-input switch, on: {res['switch']}")
        await a.keyboard.press("Escape")
        await a.mouse.click(5, 880)   # a press: the sound may run (the browser's rule)
        await wait(a, "() => window.__dbg.notifyAudio() === 'running'", label="the sound woken")

        async def settle(n_events):
            await wait(a, f"() => window.__dbg.notifySeen().length >= {n_events}", label=f"{n_events} events seen")
            t = await a.evaluate("() => performance.now()")
            await wait(a, "(t) => performance.now() > t + 1200", arg=t, label="a moment for a ring")

        async def counts():
            shown = await a.evaluate(SHOWN)
            return {"idle": [s for s in shown if ":idle:" in s["tag"]], "done": [s for s in shown if ":done:" in s["tag"]], "chimes": await a.evaluate(CHIMES)}

        rid = (await a.evaluate("() => Object.keys(window.__dbg.robotState())"))[0]

        async def case(name, before_idle=None):
            b0 = await counts()
            seen0 = len(await a.evaluate("() => window.__dbg.notifySeen()"))
            turn_then_idle(idle=False)
            await settle(seen0 + 1)
            if before_idle:
                await before_idle()
            mid = await counts()
            hook(body(hook_event_name="Notification", notification_type="idle_prompt", message="Claude is waiting for your input"))
            await settle(seen0 + 2)
            b1 = await counts()
            res[name] = {"done": len(mid["done"]) - len(b0["done"]), "idle": len(b1["idle"]) - len(mid["idle"]), "chime": b1["chimes"] - mid["chimes"],
                         "text": [x["title"] + " / " + x["body"] for x in b1["idle"][len(mid["idle"]):]]}
            return res[name]

        # 1. nothing done since the turn's end: the waiting for input rings once, a reminder, with its chime
        c = await case("reminder")
        check(failures, c["done"] == 1 and c["idle"] == 1 and c["chime"] == 1 and "入力待ち" in c["text"][0],
              f"waiting for input after an unanswered turn end: one notification and its chime: {c}")

        # 2. its 完了 notification clicked: no second ring
        async def click_done():
            tag = (await counts())["done"][-1]["tag"]
            await a.evaluate("(t) => window.__shown.find((n) => n.tag === t).onclick()", tag)
            await a.keyboard.press("Escape")
            await a.keyboard.press("Escape")
        c = await case("clickedDone", click_done)
        check(failures, c["idle"] == 0 and c["chime"] == 0, f"the 完了 notification clicked: waiting for input not rung: {c}")

        # 3. the session opened on the page (its robot's card) since the turn's end, then closed: no ring
        async def open_card():
            await a.evaluate("(id) => window.__dbg.openRobot(id)", rid)
            await wait(a, "(id) => window.__dbg.board().robot === id", arg=rid, label="the robot's card")
            await a.keyboard.press("Escape")
            await wait(a, "() => !window.__dbg.board().robot", label="the card closed")
        c = await case("openedCard", open_card)
        check(failures, c["idle"] == 0 and c["chime"] == 0, f"the session opened on the page: waiting for input not rung: {c}")

        # 4. switched off in the settings (the page's own switch): nothing
        await a.click("#btn-notify")
        await a.uncheck("[data-notify-kind='idle']")
        await a.keyboard.press("Escape")
        c = await case("off")
        check(failures, c["idle"] == 0 and c["chime"] == 0, f"waiting for input switched off: no notification, no sound: {c}")
        await a.screenshot(path=str(out / "settings-light.png"))
    finally:
        (out / "waiting-input-results.json").write_text(dump(res) + "\n")   # also when the suite stopped
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  waiting-input: {time.monotonic() - t0:.0f}s", flush=True)
    from run import check_watch
    check_watch(watch, "waiting-input", failures)

