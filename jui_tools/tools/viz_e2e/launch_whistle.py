"""Calling a subagent blows a whistle (ticket 2026-10-20-jui-viz-agent-launch-whistle; requester 10-20: "サブエージェント
呼ぶのは笛鳴らそうか").

Everything is read from the robots themselves (window.__dbg.launchLook) with the shared waits (waits.until, every frame):

  The demo (the fake server, the script frozen at chosen times): its three beats, b4 and a0 calling in the foreground
  and a0 in the background (DEMO_BEATS.launch, launchSec):
  - before a beat: no whistle; inside it (just after the start and just before its end): the whistle at the mouth,
    「ピーッ！」, the squeezed face; just after its fixed length: all gone; a robot without a beat never whistles.

  The live view (the real `jui viz serve`, the real forward.py):
  - Read: no whistle;
  - a foreground Agent call that keeps running: the whistle shows, and is gone after the fixed length while the call
    is still open (the robot back to its look: carrying, then waiting); the length on screen is about the fixed one;
  - a background Agent call that ends at once (PostToolUse right after): the whistle all the same, for its length;
  - with heavy work's whistle (3+ subagents, forced) at the same time: 「ピーッ！」 in place of 「ピッ！」 for the launch,
    then 「ピッ！」 and the sweat go on;
  - never away from the desk: a session that calls a subagent at once, its robot still walking in from the door,
    shows no whistle on any frame it walks inside the whistle's time (and such frames do occur);
  - under reduced motion: the whistle at the mouth, the arm not raised and still.

Screenshots: a0's launch up close in the demo (light and dark), and the live room.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, dump, freeze, new_page, ready, stamp
from waits import settled, until

MAIN = "e2e00000-0000-4000-8000-0000000004e1"
NEW = "e2e00000-0000-4000-8000-0000000004e2"   # a session that calls a subagent at once, its robot still walking in
CWD = "/work/launch-whistle"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
LEN_MS = 2500           # robots.LAUNCH_WHISTLE_MS (test_viz_launch_whistle.py keeps the demo's launchSec equal to it)
SLACK_MS = 1500         # a hook's way to the page (forward.py, the server, the slice) on a busy machine
RAISED = -1.8           # armR.rotation.z of the arm waving up beside the head (heavy_looks.py)
LOOK = "() => window.__dbg.launchLook()"
READY = "() => !!(window.__dbg && window.__dbg.robots && document.body.dataset.mode === 'live')"
WHY = "() => window.__dbg.launchLook()"
CALL = {"description": "画面を作る", "prompt": "作って", "subagent_type": "jsonui-implement"}
# robot i's whistle on (i.on true) or off, with what it shows; returns its record and the page's clock
ROBOT_IS = ("(i) => { const L = window.__dbg.launchLook(), x = L.robots.find((y) => y.id === i.id); if (!x) return false; "
            "const on = x.launch && x.whistle && x.pipiLong && !x.pipi && x.face === 'whistle'; "
            "const off = !x.launch && !x.pipiLong && (i.heavy ? x.whistle && x.pipi : !x.whistle && !x.pipi); "
            "return (i.on ? on : off) && { ...x, now: L.now, t: L.t }; }")


def check(failures, cond, text):
    if not cond:
        failures.append(f"launch-whistle: {text}")
    return cond


def of(look, label):
    return next((x for x in look["robots"] if x["id"] == label), None)


async def is_on(page, rid, on, name, heavy=False, timeout=20000):
    return await until(page, ROBOT_IS, name, arg={"id": rid, "on": on, "heavy": heavy}, timeout=timeout, why=WHY)


async def run_demo_part(browser, watch, srv_url, out, failures, res):
    page = await new_page(browser, watch, "launch-whistle-demo", **DESKTOP)
    await page.goto(f"{srv_url}/?demo=1")
    await ready(page)
    beats = res["beats"] = await page.evaluate("() => window.__dbg.launchBeats()")
    check(failures, beats and beats["sec"] * 1000 == LEN_MS and {b[2] for b in beats["beats"]} == {"fg", "bg"},
          f"the demo has foreground and background beats of the fixed length: {beats}")
    sec = beats["sec"]
    for at, who, how in beats["beats"]:
        row = res.setdefault("demo", {}).setdefault(f"{who}@{at}", {})
        for name, t, on in (("before", at - 0.3, False), ("start", at + 0.3, True), ("end", at + sec - 0.25, True), ("after", at + sec + 0.25, False)):
            await freeze(page, t)
            x = await is_on(page, who, on, f"demo {who} {how} at {t:.2f}: whistle {'on' if on else 'off'}")
            row[name] = {k: x[k] for k in ("t", "launch", "whistle", "pipiLong", "face", "state")}
        if who == "a0" and how == "fg":
            await freeze(page, at + 1)
            await page.evaluate("() => window.__dbg.faceCam('a0', 4.2)")
            for scheme in ("light", "dark"):
                await page.emulate_media(color_scheme=scheme)
                await is_on(page, who, True, f"a0 whistling up close, {scheme}")
                await page.wait_for_timeout(300)   # the camera's flyTo (0 s) and one frame drawn
                await page.screenshot(path=str(out / f"demo-a0-{scheme}.png"))
            await page.emulate_media(color_scheme="light")
    # a robot without a beat never whistles at any of those times
    await freeze(page, 21)
    look = await page.evaluate(LOOK)
    others = [x for x in look["robots"] if x["id"] not in {b[1] for b in beats["beats"]} and (x["launch"] or x["pipiLong"])]
    check(failures, not others, f"no robot without a beat whistles for a launch: {others}")
    await page.close()


async def run_live_part(browser, watch, out, failures, res):
    from run import free_port
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    proj = home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", CWD)
    proj.mkdir(parents=True, exist_ok=True)
    transcript = proj / f"{MAIN}.jsonl"
    transcript.write_text(json.dumps({"type": "user", "timestamp": stamp("2026-10-20T09:00:00Z"), "message": {"role": "user", "content": "start"}}) + "\n")
    transcript_new = proj / f"{NEW}.jsonl"
    transcript_new.write_text(json.dumps({"type": "user", "timestamp": stamp("2026-10-20T09:00:01Z"), "message": {"role": "user", "content": "start"}}) + "\n")
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT,
                           env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"

    def hook(sid=MAIN, **payload):
        body = {"session_id": sid, "cwd": CWD, "permission_mode": "default", "transcript_path": str(transcript if sid == MAIN else transcript_new), **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(),
                       capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)

    def pre(tool, tool_input, use):
        hook(hook_event_name="PreToolUse", tool_name=tool, tool_input=tool_input, tool_use_id=use)

    def post(tool, tool_input, use):
        hook(hook_event_name="PostToolUse", tool_name=tool, tool_input=tool_input, tool_use_id=use, tool_response="ok")

    try:
        import urllib.request
        for _ in range(400):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError(f"the server did not answer /health in 40 s: {(out / 'serve.log').read_text()[-400:]}")
        page = await new_page(browser, watch, "launch-whistle-live", **DESKTOP)
        await page.goto(url + "/")
        await until(page, READY, "the page is up", timeout=30000)
        hook(hook_event_name="SessionStart", source="startup")
        await until(page, "() => window.__dbg.robots.length >= 1", "the robot", why=WHY)
        await settled(page, "the robot at its desk", timeout=30000)
        await page.evaluate("() => { window.__dbg.play({ p: 0, solo: { p: 0 } }); window.__dbg.brk({ p: { smoke: 0, vend: 0 } }); }")
        rid = res["id"] = await page.evaluate("(s) => window.__dbg.robots.find((R) => R.def.sessionId === s).def.id", MAIN)
        hook(hook_event_name="UserPromptSubmit", prompt="頼む")

        # another tool: no whistle
        pre("Read", {"file_path": f"{CWD}/a.txt"}, "toolu_lw_read")
        await until(page, "(i) => window.__dbg.launchLook().robots.find((x) => x.id === i).state === 'reading'", "reading", arg=rid, why=WHY)
        await settled(page, "reading", ids=[rid])
        x = res["read"] = of(await page.evaluate(LOOK), rid)
        check(failures, not x["launch"] and not x["whistle"] and not x["pipiLong"], f"Read: no whistle: {x}")
        post("Read", {"file_path": f"{CWD}/a.txt"}, "toolu_lw_read")

        # a foreground call that keeps running: the whistle, then gone after its length while the call is open
        pre("Agent", CALL, "toolu_lw_fg")
        on = await is_on(page, rid, True, "foreground: the whistle on")
        off = await is_on(page, rid, False, "foreground: the whistle off after its length", timeout=30000)
        res["fg"] = {"on": on, "off": off, "shownMs": off["now"] - on["now"]}
        check(failures, LEN_MS - SLACK_MS <= off["now"] - on["now"] <= LEN_MS + 200,
              f"foreground: shown for about the fixed length ({LEN_MS} ms): {res['fg']['shownMs']} ms")
        await until(page, "(i) => { const x = window.__dbg.launchLook().robots.find((y) => y.id === i); return x.until === null && x; }",
                    "foreground: the server's whistle over too", arg=rid, why=WHY)
        x = res["fgAfter"] = of(await page.evaluate(LOOK), rid)
        check(failures, x["state"] in ("carry", "idle", "thinking") and not x["whistle"] and not x["launch"],
              f"foreground, the call still running: back to its look, no whistle: {x}")
        post("Agent", CALL, "toolu_lw_fg")

        # a background call, over at once: the whistle all the same, for its length
        bg = {**CALL, "run_in_background": True}
        pre("Agent", bg, "toolu_lw_bg")
        post("Agent", bg, "toolu_lw_bg")
        on = await is_on(page, rid, True, "background: the whistle on")
        off = await is_on(page, rid, False, "background: the whistle off after its length", timeout=30000)
        res["bg"] = {"on": on, "off": off, "shownMs": off["now"] - on["now"]}
        check(failures, LEN_MS - SLACK_MS <= off["now"] - on["now"] <= LEN_MS + 200,
              f"background: shown for about the fixed length though the call ended at once: {res['bg']['shownMs']} ms")

        # with heavy work's whistle at once: 「ピーッ！」 for the launch, then 「ピッ！」 and the sweat go on
        edit = {"file_path": f"{CWD}/a.py", "old_string": "a", "new_string": "b"}
        pre("Edit", edit, "toolu_lw_edit1")
        await page.evaluate("(i) => window.__dbg.force(i, { heavy: ['subagents'] })", rid)
        await until(page, "(i) => { const x = window.__dbg.launchLook().robots.find((y) => y.id === i); return x.look === 'whistle' && x.pipi && x.sweat; }",
                    "heavy work's whistle", arg=rid, why=WHY)
        pre("Agent", bg, "toolu_lw_bg2")
        post("Agent", bg, "toolu_lw_bg2")
        pre("Edit", edit, "toolu_lw_edit2")
        on = await is_on(page, rid, True, "both: the launch's 「ピーッ！」", heavy=True)
        off = await is_on(page, rid, False, "both: back to heavy work's 「ピッ！」", heavy=True, timeout=30000)
        res["both"] = {"on": on, "off": off}
        check(failures, off["sweat"] and off["look"] == "whistle", f"both: heavy work's whistle and sweat go on after the launch: {off}")
        await page.evaluate("(i) => window.__dbg.force(i, null)", rid)
        post("Edit", edit, "toolu_lw_edit1")
        post("Edit", edit, "toolu_lw_edit2")
        await page.click(f".tag.room[data-set-project='{await page.evaluate('(i) => window.__dbg.robots.find((R) => R.def.id === i).def.room', rid)}']")
        pre("Agent", bg, "toolu_lw_bg3")
        await is_on(page, rid, True, "the room up close, whistling")
        await page.screenshot(path=str(out / "live-room.png"))
        post("Agent", bg, "toolu_lw_bg3")
        await is_on(page, rid, False, "the room up close, the whistle over", timeout=30000)
        await page.click("#room-back")

        # away from the desk: a new session calls a subagent at once, while its robot still walks in from the door. On
        # every frame it walks (a path left) inside the whistle's time, no whistle; then, at its desk, none either
        # (its time is over by then or it shows there). Probed 10-20: the walk in takes longer than the 2.5 s.
        await page.evaluate("""(sid) => { const W = window.__walkWhistle = { frames: 0, due: 0, bad: 0, rows: [] };
          window.__dbg.afterFrame(() => { const R = window.__dbg.robots.find((x) => x.def.sessionId === sid); if (!R) return;
            const st = window.__dbg.robotState()[R.def.id] || {}, due = !!(st.whistle && Date.now() < st.whistle.until);
            const shown = !!(R.robot.launch || (R.robot.whistle && R.robot.whistle.visible) || (R.robot.pipiLong && R.robot.pipiLong.visible));
            if (!R.path.length) return;
            W.frames += 1; if (due) W.due += 1;
            if (shown) { W.bad += 1; if (W.rows.length < 3) W.rows.push({ path: R.path.length, state: R.robot.state, launch: !!R.robot.launch }); } }); }""", NEW)
        hook(NEW, hook_event_name="SessionStart", source="startup")
        hook(NEW, hook_event_name="UserPromptSubmit", prompt="すぐ頼む")
        hook(NEW, hook_event_name="PreToolUse", tool_name="Agent", tool_input=bg, tool_use_id="toolu_lw_walk")
        hook(NEW, hook_event_name="PostToolUse", tool_name="Agent", tool_input=bg, tool_use_id="toolu_lw_walk", tool_response="ok")
        await until(page, "(sid) => { const R = window.__dbg.robots.find((x) => x.def.sessionId === sid); const st = R && window.__dbg.robotState()[R.def.id]; "
                    "return !!R && !R.path.length && st && !st.whistle; }", "the new robot at its desk, its whistle's time over", arg=NEW, timeout=60000, why=WHY)
        walk = res["walkIn"] = await page.evaluate("() => { window.__dbg.afterFrame(null); const W = window.__walkWhistle; window.__walkWhistle = null; return W; }")
        check(failures, walk["due"] > 0 and walk["bad"] == 0,
              f"walking in (a path left) inside the whistle's time: no whistle on any frame (due frames > 0 shows it reaches): {walk}")

        # reduced motion: the whistle at the mouth, no waving
        quiet = await new_page(browser, watch, "launch-whistle-reduced", reduced_motion="reduce", **DESKTOP)
        await quiet.goto(url + "/")
        await until(quiet, READY, "the reduced-motion page is up", timeout=30000)
        await until(quiet, "(i) => window.__dbg.robots.some((R) => R.def.id === i)", "the robot, reduced motion", arg=rid, why=WHY)
        await settled(quiet, "reduced motion, at rest", ids=[rid])
        pre("Agent", bg, "toolu_lw_bg4")
        await is_on(quiet, rid, True, "reduced motion: the whistle on")
        await settled(quiet, "reduced motion: the pose blended", ids=[rid])   # read the arm once the pose has blended
        a = await is_on(quiet, rid, True, "reduced motion: still whistling, settled")
        await quiet.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
        b = of(await quiet.evaluate(LOOK), rid)
        res["reduced"] = {"first": a, "later": b}
        check(failures, a["reduced"] and b["whistle"] and a["armRz"] > RAISED + 0.6 and a["armRz"] == b["armRz"],
              f"reduced motion: the whistle, the arm not raised and still: {res['reduced']}")
        post("Agent", bg, "toolu_lw_bg4")
        await quiet.close()
        await page.close()
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()


async def run_launch_whistle(pw, out, failures, Server):
    out = pathlib.Path(out) / "launch-whistle"
    out.mkdir(parents=True, exist_ok=True)
    res: dict = {}
    t0 = time.monotonic()
    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    srv = Server()
    try:
        watch = Watch(origin=srv.url)
        try:
            await run_demo_part(browser, watch, srv.url, out, failures, res)
        except Exception as e:
            failures.append(f"launch-whistle: demo: {type(e).__name__}: {str(e).splitlines()[0]}")
        for line in watch.console:
            failures.append(f"launch-whistle: demo console: {line}")
        for u in watch.foreign:
            failures.append(f"launch-whistle: demo request outside the server: {u}")
    finally:
        srv.stop()
    try:
        watch = Watch(origin="http://127.0.0.1")
        try:
            await run_live_part(browser, watch, out, failures, res)
        except Exception as e:
            failures.append(f"launch-whistle: live: {type(e).__name__}: {str(e).splitlines()[0]}")
        for line in watch.console:
            failures.append(f"launch-whistle: live console: {line}")
        for u in watch.foreign:
            failures.append(f"launch-whistle: live request outside the server: {u}")
    finally:
        await browser.close()
    print(f"  launch-whistle: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "launch-whistle-results.json").write_text(dump(res) + "\n")
