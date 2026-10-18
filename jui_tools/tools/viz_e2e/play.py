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
        for sid in (A, B):
            hook(sid, hook_event_name="SessionStart", source="startup")
        await wait(page, "() => window.__dbg.play().robots.length >= 2", label="two robots")
        # B waits for a permission: no game, whatever the chance
        hook(B, hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="tb1", tool_input={"command": "rm -rf build", "description": "片付け"})
        hook(B, hook_event_name="PermissionRequest", tool_name="Bash", tool_input={"command": "rm -rf build"})
        await page.wait_for_timeout(1500)
        await page.evaluate("() => window.__dbg.play({ idleMs: 1000, p: 1, minSec: 6, maxSec: 6, restMinSec: 600, restMaxSec: 600 })")
        await page.wait_for_timeout(4000)
        r = res["waiting"] = await page.evaluate(play)
        check(failures, r["list"] == [] and all(x["play"] is None for x in r["robots"]), f"a robot waiting for permission does not play: {r}")
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
        # an instruction for A: it stops at once, walks back with its real lamp; B, alone, walks back too
        a_label = next(x["id"] for x in r["robots"] if x["id"] in G["players"])
        hook(A, hook_event_name="UserPromptSubmit", prompt="次の作業")
        hook(A, hook_event_name="PreToolUse", tool_name="Read", tool_use_id="ta1", tool_input={"file_path": "/work/play-app/a.txt"})
        t1 = time.monotonic()
        await wait(page, "() => window.__dbg.play().list.length === 0", timeout=10000, label="the game stops")
        res["stopSec"] = round(time.monotonic() - t1, 1)
        r = res["stopping"] = await page.evaluate(play)
        check(failures, all(x["play"] is None for x in r["robots"]), f"nobody plays on: {r}")
        lamps = {x["id"]: x["lamp"] for x in r["robots"]}
        check(failures, "reading" in lamps.values(), f"A's lamp is its real state at once: {lamps}")
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
