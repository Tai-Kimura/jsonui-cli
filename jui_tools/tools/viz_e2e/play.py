"""Play, end to end (requester, 10-18): robots idle for long in one room play together and go back to their desks.

The real `jui viz serve` in a throwaway HOME on a free port, the real forward.py for two sessions in one room. The
times are shortened through window.__dbg.play (the real defaults stay in 40-scene.js). A robot waiting for a
permission never plays; two idle robots walk to the front aisle and play with the idle lamp; an instruction for one
stops it at once (its lamp is its real state while it walks back) and the other, alone, walks back too; the two rest
before another game. Then a ball game (the ball flies) and じゃんけん (a hand over a head). No console error, nothing
requested outside the server.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, dump, new_page, ready
from rooms import SEG_JS

A = "e2e00000-0000-4000-8000-0000000000da"
B = "e2e00000-0000-4000-8000-0000000000db"
CWD = "/work/play-app"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")


def check(failures, cond, text):
    if not cond:
        failures.append(f"play: {text}")


async def wait(page, js, timeout=20000, label=""):
    try:
        await page.wait_for_function(js, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None



async def run_play(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "play"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def hook(sid, **payload):
        body = {"session_id": sid, "cwd": CWD, "permission_mode": "default", **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(),
                       capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)

    play = "() => window.__dbg.play()"
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
        watch = Watch(origin=url)
        page = await new_page(browser, watch, "play", **DESKTOP)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", label="connected")
        await page.evaluate(SEG_JS)                      # every robot's step against the walls (rooms.py)
        for sid in (A, B):
            hook(sid, hook_event_name="SessionStart", source="startup")
        await wait(page, "() => window.__dbg.play().robots.length >= 2", label="two robots")
        # new robots walk in from the corridor: wait until both sit, then count steps from here
        await wait(page, "() => window.__dbg.play().robots.every((x) => x.path === 0 && x.x === x.seat[0] && x.z === x.seat[1])", label="both seated")
        await page.evaluate("() => { window.__walk.steps = 0; window.__walk.hits = []; }")
        # B waits for a permission: no game, whatever the chance
        hook(B, hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="tb1", tool_input={"command": "rm -rf build", "description": "片付け"})
        hook(B, hook_event_name="PermissionRequest", tool_name="Bash", tool_input={"command": "rm -rf build"})
        await page.wait_for_timeout(1500)
        await page.evaluate("() => window.__dbg.play({ idleMs: 1000, p: 1, minSec: 6, maxSec: 6, restMinSec: 600, restMaxSec: 600 })")
        await page.wait_for_timeout(4000)
        r = res["waiting"] = await page.evaluate(play)
        check(failures, r["list"] == [] and all(x["play"] is None for x in r["robots"]), f"a robot waiting for permission does not play: {r}")
        # not even for a moment: both stayed at their desks the whole time (a game started and stopped at once would walk)
        check(failures, all(x["path"] == 0 and [x["x"], x["z"]] == x["seat"] and x["vis"] not in ("carry", "stroll") for x in r["robots"])
              and await page.evaluate("() => window.__walk.steps") == 0, f"nobody left a desk: {r}")
        # B is idle again: the two play
        hook(B, hook_event_name="PostToolUse", tool_name="Bash", tool_use_id="tb1", tool_input={"command": "rm -rf build"}, tool_response={"stdout": ""})
        hook(B, hook_event_name="Stop")                  # the turn ends (a busy session quiet for a while is 考え中, not idle)
        await wait(page, "() => window.__dbg.play().list.some((g) => g.started)", timeout=20000, label="a game starts")
        r = res["playing"] = await page.evaluate(play)
        G = r["list"][0]
        rob = {x["id"]: x for x in r["robots"]}
        check(failures, len(G["players"]) == 2 and all(rob[i]["play"] == "playing" for i in G["players"]), f"both at the spot: {r}")
        check(failures, all([rob[i]["x"], rob[i]["z"]] != rob[i]["seat"] for i in G["players"]), "they left their desks")
        check(failures, all(rob[i]["lamp"] == "idle" and rob[i]["pose"] == G["kind"] for i in G["players"]), f"lamp idle, the game's pose: {r}")
        res["kind"] = G["kind"]
        await page.screenshot(path=str(out / "playing.png"))
        # an instruction alone for A (the server keeps it idle until its first tool): it stops at once, and B, alone,
        # walks back too; then its first tool: its lamp is its real state while it walks back
        hook(A, hook_event_name="UserPromptSubmit", prompt="次の作業")
        t1 = time.monotonic()
        await wait(page, "() => window.__dbg.play().list.length === 0", timeout=5000, label="the game stops on the instruction alone")
        res["stopSec"] = round(time.monotonic() - t1, 1)
        r = res["stopping"] = await page.evaluate(play)
        check(failures, all(x["play"] is None for x in r["robots"]) and all(x["back"] or x["path"] == 0 for x in r["robots"]), f"nobody plays on: {r}")
        hook(A, hook_event_name="PreToolUse", tool_name="Read", tool_use_id="ta1", tool_input={"file_path": "/work/play-app/a.txt"})
        # while it is still walking back (not once it sits: a sitting robot's lamp is its state anyway)
        await wait(page, "() => window.__dbg.play().robots.some((x) => x.back && x.vis === 'stroll' && x.lamp === 'reading')", timeout=5000,
                   label="A's lamp is reading while it walks back")
        await wait(page, "() => window.__dbg.play().robots.every((x) => !x.back && x.x === x.seat[0] && x.z === x.seat[1])", timeout=20000, label="both at their desks")
        res["back"] = await page.evaluate(play)
        # the same pair does not start again at once (rest)
        await page.wait_for_timeout(3000)
        r = await page.evaluate(play)
        check(failures, r["list"] == [], f"they rest before another game: {r['list']}")
        # the other games draw too: a ball in the air between them, a hand over the head for じゃんけん
        hook(A, hook_event_name="PostToolUse", tool_name="Read", tool_use_id="ta1", tool_input={"file_path": "/work/play-app/a.txt"})
        hook(A, hook_event_name="Stop")
        for kind in ("ball", "rps"):
            await page.evaluate(f"() => window.__dbg.play({{ kinds: ['{kind}'], restMinSec: 0, restMaxSec: 0, minSec: 8, maxSec: 8 }})")
            await wait(page, "() => window.__dbg.play().list.some((g) => g.started)", timeout=20000, label=f"a {kind} game")
            seen = []
            for _ in range(8):
                await page.wait_for_timeout(450)
                seen.append(await page.evaluate(play))
            if kind == "ball":
                ys = [s["list"][0]["ball"][1] for s in seen if s["list"] and s["list"][0]["ball"]]
                res["ballY"] = ys
                check(failures, len(ys) >= 4 and max(ys) - min(ys) > 0.3, f"the ball flies: {ys}")
            else:
                shown = [any(x["rps"] for x in s["robots"]) for s in seen]
                res["rps"] = shown
                check(failures, any(shown), f"a hand shows over a head: {shown}")
            await wait(page, "() => window.__dbg.play().list.length === 0 && window.__dbg.play().robots.every((x) => !x.back)", timeout=40000, label=f"the {kind} game ends")
            await page.evaluate("() => window.__dbg.play({ restMinSec: 0, restMaxSec: 0 })")
        await page.screenshot(path=str(out / "after.png"))
        # its desk moves to another room in the middle of a game (cd): it walks back through the doors, never a wall
        await page.evaluate("() => window.__dbg.play({ kinds: ['highfive'], restMinSec: 0, restMaxSec: 0, minSec: 30, maxSec: 30 })")
        await wait(page, "() => window.__dbg.play().list.some((g) => g.started)", timeout=20000, label="a game before the move")
        r = await page.evaluate(play)
        a_room = r["robots"][0]["room"]
        # seven robots already in the other room put A's new desk where a straight line would cross a wall
        # (jsonuidocument-96, 10-18: with three, the straight line happened to pass the door's height)
        for k in range(7):
            hook(f"e2e00000-0000-4000-8000-00000000f0{k:02d}", hook_event_name="SessionStart", source="startup", cwd="/work/play-other")
        await wait(page, "() => window.__dbg.play().robots.length >= 9 && window.__dbg.play().robots.every((x) => x.path === 0)", timeout=30000, label="the other room seated")
        await page.evaluate("() => { window.__walk.hits = []; window.__walk.rooms = {}; }")
        # the move alone (no instruction first): the stop and the new desk come in the same frame, so the walk back is
        # playStop's own (an instruction first would stop it in the old room and leave the route to livePlan)
        hook(A, hook_event_name="CwdChanged", cwd="/work/play-other")
        await wait(page, "() => window.__dbg.play().robots.filter((x) => x.room === '" + a_room + "').length === 1", timeout=10000, label="A's desk in another room")
        await wait(page, "() => window.__dbg.play().robots.every((x) => !x.back && x.path === 0)", timeout=30000, label="both at their desks again")
        walk = res["move"] = await page.evaluate("() => ({ hits: window.__walk.hits.length, rooms: window.__walk.rooms })")
        check(failures, walk["hits"] == 0, f"no step through a wall: {walk}")
        check(failures, any(len(v) >= 2 for v in walk["rooms"].values()), f"one robot did go to another room (else the check above says nothing): {walk}")
        # the one change the server makes without moving updatedAt: a busy session quiet for THINKING_AFTER_MS (30 s)
        # turns 考え中. Every robot in the other room gets an instruction (busy, still idle), a pair plays, and the
        # state alone must stop it when they turn 考え中.
        others = [f"e2e00000-0000-4000-8000-00000000f0{k:02d}" for k in range(7)]
        await page.evaluate("() => window.__dbg.play({ p: 0, endAll: true })")   # no game until every instruction is in
        await wait(page, "() => window.__dbg.play().list.length === 0", label="no game before the instructions")
        for sid in [A, *others]:
            hook(sid, hook_event_name="UserPromptSubmit", prompt="考える", cwd="/work/play-other")
        await page.wait_for_timeout(1500)
        await page.evaluate("() => window.__dbg.play({ p: 1, kinds: ['ball'], restMinSec: 0, restMaxSec: 0, minSec: 120, maxSec: 120 })")
        await wait(page, "() => window.__dbg.play().list.some((g) => g.started)", timeout=20000, label="a game among the busy-but-idle robots")
        t2 = time.monotonic()
        await wait(page, "() => window.__dbg.play().list.length === 0", timeout=60000, label="the game stops when they turn 考え中")
        res["thinkingStopSec"] = round(time.monotonic() - t2, 1)
        r = await page.evaluate("() => window.__dbg.robotState()")
        check(failures, any(v["state"] == "thinking" for v in r.values()), f"it stopped because they turned 考え中: {r}")
        await page.close()
        for line in watch.console:
            failures.append(f"play: console: {line}")
        for u in watch.foreign:
            failures.append(f"play: request outside the server: {u}")
        res["console"] = len(watch.console)
    except Exception as e:
        failures.append(f"play: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  play/idle-play-stop: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "play-results.json").write_text(dump(res) + "\n")
