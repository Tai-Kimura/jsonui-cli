"""The shredder (requester, 10-19): a robot that deleted files carries them to the shredder and feeds them.

The real `jui viz serve` in a throwaway HOME on a free port; three sessions through the real forward.py. Up close
(the props' view): the shredder stands against the back wall clear of every other box (the water server, the robots'
desks) and of the front aisle; `rm -rf build a.txt` sends its robot there with the papers, bits fall (never more than
the cap), its act says what went, and it walks back to its seat. `git rm` does the same. A deletion that found nothing
(No such file): no errand, a tilt of the head. A new instruction mid-errand ends it at once. Not up close: no errand,
the act still names what went. A command that only mentions rm: nothing. Light and dark pictures. No console error,
nothing requested outside the server.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, new_page, ready

CWD = "/work/shred-app"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
SID = "e2e00000-0000-4000-8000-0000000002{:02x}"


def check(failures, cond, text):
    if not cond:
        failures.append(f"shredder: {text}")


async def wait(page, js, timeout=20000, label=""):
    try:
        await page.wait_for_function(js, timeout=timeout, polling=100)
    except Exception as e:
        now = await page.evaluate("() => window.__dbg.shred ? window.__dbg.shred().robots : null")
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]} — robots then: {now}") from None


def overlap(a, b):
    return a[0] < b[1] and b[0] < a[1] and a[2] < b[3] and b[2] < a[3]


async def run_shredder(pw, out, failures, jt=None, shots_only=False):
    from run import free_port
    name = "shredder-before" if shots_only else "shredder"
    out = pathlib.Path(out) / name
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(jt) if jt else pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}
    seq = {"n": 0}

    def hook(sid, **payload):
        body = {"session_id": sid, "cwd": CWD, "permission_mode": "default", **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(),
                       capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)

    def bash(sid, command, stderr="", failed=False, stop=True):
        seq["n"] += 1
        uid = f"tb{seq['n']}"
        hook(sid, hook_event_name="PreToolUse", tool_name="Bash", tool_use_id=uid, tool_input={"command": command})
        hook(sid, hook_event_name="PostToolUseFailure" if failed else "PostToolUse", tool_name="Bash", tool_use_id=uid,
             tool_input={"command": command}, tool_response={"stdout": "", "stderr": stderr})
        if stop:
            hook(sid, hook_event_name="Stop")   # the turn ends: the robot is done, the errand goes on

    shred = "() => window.__dbg.shred()"
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
        page = await new_page(browser, watch, name, **DESKTOP)
        await page.emulate_media(color_scheme="light", reduced_motion="no-preference")
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", label="connected")
        for i in range(3):
            hook(SID.format(i), hook_event_name="SessionStart", source="startup")
        await wait(page, "() => window.__dbg.robots.length >= 3 && window.__dbg.robots.every((R) => !R.path.length)", timeout=30000, label="seated")
        room_id = await page.evaluate("() => window.__dbg.robots[0].def.room")

        async def shots(tag):
            for scheme in ("light", "dark"):
                await page.emulate_media(color_scheme=scheme)
                await page.click(f".tag.room[data-set-project='{room_id}']")
                await wait(page, f"() => window.__dbg.solo() === '{room_id}'", label=f"one room, {scheme}")
                await page.wait_for_timeout(1800)
                await page.screenshot(path=str(out / f"{tag}-room-{scheme}.png"))
                await page.click("#room-back")
                await wait(page, "() => window.__dbg.solo() === null", label="back")
            await page.emulate_media(color_scheme="light")

        if shots_only:
            await shots("before")
            return

        def robot_of(r, sid_index):
            return next(x for x in r["robots"] if x["id"] == labels[sid_index])

        labels = await page.evaluate("() => window.__dbg.robots.map((R) => R.def.id)")
        sids = {}   # robot label -> session id, through the act of a marker command
        for i in range(3):
            bash(SID.format(i), f"echo marker-{i}", stop=False)
        await wait(page, "() => window.__dbg.robots.every((R) => R.act.includes('marker-'))", label="markers")
        for x in (await page.evaluate(shred))["robots"]:
            sids[x["id"]] = SID.format(int(x["act"].split("marker-")[1][0]))
        for i in range(3):
            hook(SID.format(i), hook_event_name="Stop")
        a, b = labels[0], labels[1]

        # not up close: the act names what went, no errand
        bash(sids[a], "rm stale.log")
        await wait(page, f"() => window.__dbg.shred().robots.find((x) => x.id === '{a}').act.includes('シュレッダー stale.log')", label="act, floor view")
        await page.wait_for_timeout(800)
        r = res["floor"] = await page.evaluate(shred)
        mine = next(x for x in r["robots"] if x["id"] == a)
        check(failures, r["shredder"] is None and mine["phase"] is None and mine["path"] == 0, f"not up close: no shredder, no errand: {mine}")

        # up close
        await page.click(f".tag.room[data-set-project='{room_id}']")
        await wait(page, "() => window.__dbg.shred().shredder !== null", label="the shredder")
        await wait(page, "() => window.__dbg.robots.every((R) => !R.path.length)", timeout=30000, label="settled up close")
        r = res["placed"] = await page.evaluate(shred)
        S = r["shredder"]
        others = [bx for bx in r["boxes"] if bx != S["box"]]
        hits = [bx for bx in others if overlap(S["box"], bx)]
        room = await page.evaluate(f"() => window.__dbg.room('{room_id}')")
        check(failures, not hits, f"the shredder's box crosses no other box (server, desks): {hits}")
        check(failures, S["box"] in r["boxes"], f"the vacuum keeps clear of the shredder (its box is in the props' boxes): {r['boxes']}")
        check(failures, S["box"][3] < room["z1"] - 1.7 and S["box"][2] >= room["z0"] - 1e-6 and room["x0"] < S["box"][0] and S["box"][1] < room["x1"],
              f"against the back wall, out of the front aisle: {S} in {room}")
        await page.screenshot(path=str(out / "after-room-light.png"))

        # rm -rf: the errand
        bash(sids[a], "cd /work/shred-app && rm -rf build a.txt")
        await wait(page, f"() => window.__dbg.shred().robots.find((x) => x.id === '{a}').phase === 'going'", label="goes")
        g = res["going"] = next(x for x in (await page.evaluate(shred))["robots"] if x["id"] == a)
        check(failures, g["held"] and "シュレッダー build、a.txt" in g["tag"], f"carries the papers, the name over its head: {g}")
        await wait(page, f"() => window.__dbg.shred().robots.find((x) => x.id === '{a}').phase === 'feeding'", timeout=20000, label="at the shredder")
        at = next(x for x in (await page.evaluate(shred))["robots"] if x["id"] == a)
        res["at"] = at
        check(failures, abs(at["x"] - S["spot"][0]) < 0.05 and abs(at["z"] - S["spot"][1]) < 0.05, f"stands at the shredder: {at} vs {S['spot']}")
        await page.wait_for_timeout(1200)
        await page.screenshot(path=str(out / "shredding-light.png"))
        bits = []
        for _ in range(20):
            bits.append((await page.evaluate(shred))["bits"])
            await page.wait_for_timeout(100)
        res["bits"] = bits
        check(failures, max(bits) > 0 and max(bits) <= 24, f"bits fall, never more than 24: {bits}")
        await wait(page, f"() => {{ const x = window.__dbg.shred().robots.find((y) => y.id === '{a}'); return x.phase === null && x.path === 0 && Math.abs(x.x - x.seat[0]) < 0.01 && Math.abs(x.z - x.seat[1]) < 0.01; }}",
                   timeout=20000, label="back at its seat")
        await wait(page, "() => window.__dbg.shred().bits === 0", timeout=5000, label="bits gone")

        # git rm: the same
        bash(sids[b], "git -C /work/shred-app rm src/old.py")
        await wait(page, f"() => window.__dbg.shred().robots.find((x) => x.id === '{b}').phase !== null", label="git rm goes")
        await wait(page, f"() => {{ const x = window.__dbg.shred().robots.find((y) => y.id === '{b}'); return x.phase === null && x.path === 0; }}", timeout=25000, label="git rm back")

        # nothing there: a tilt, no errand
        bash(sids[a], "rm nope.txt", stderr="rm: nope.txt: No such file or directory")
        await wait(page, f"() => window.__dbg.shred().robots.find((x) => x.id === '{a}').tilt", label="a tilt")
        r = next(x for x in (await page.evaluate(shred))["robots"] if x["id"] == a)
        res["nothing"] = r
        check(failures, r["phase"] is None and r["path"] == 0 and "削除できず nope.txt" in r["tag"], f"nothing there: no errand, 削除できず: {r}")

        # only mentions rm: nothing
        bash(sids[a], "grep -rn 'rm -rf' docs/ && echo rm")
        await page.wait_for_timeout(1000)
        r = next(x for x in (await page.evaluate(shred))["robots"] if x["id"] == a)
        check(failures, r["phase"] is None and "シュレッダー" not in r["tag"], f"a command that only mentions rm: {r}")

        # stopped at once by a new instruction
        bash(sids[a], "rm -f tmp.txt")
        await wait(page, f"() => window.__dbg.shred().robots.find((x) => x.id === '{a}').phase === 'going'", label="goes again")
        hook(sids[a], hook_event_name="UserPromptSubmit", prompt="次の作業")
        t1 = time.monotonic()
        await wait(page, f"() => {{ const x = window.__dbg.shred().robots.find((y) => y.id === '{a}'); return x.phase === null && !x.held; }}", timeout=5000, label="stops")
        res["stopSec"] = round(time.monotonic() - t1, 1)
        await wait(page, f"() => {{ const x = window.__dbg.shred().robots.find((y) => y.id === '{a}'); return x.path === 0 && Math.abs(x.x - x.seat[0]) < 0.01 && Math.abs(x.z - x.seat[1]) < 0.01; }}", timeout=20000, label="back after the stop")

        await page.click("#room-back")
        await wait(page, "() => window.__dbg.solo() === null && window.__dbg.shred().shredder === null", label="gone with the props")
        await page.emulate_media(color_scheme="dark")
        await page.click(f".tag.room[data-set-project='{room_id}']")
        await wait(page, "() => window.__dbg.shred().shredder !== null", label="dark")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(out / "after-room-dark.png"))
        check(failures, not watch.console and not watch.foreign and not watch.csp, f"no console error, nothing outside the server: {watch.console[:3]} {watch.foreign[:3]}")
        await page.close()
    finally:
        await browser.close()
        srv.terminate()  # our own child (started above)
        try:
            srv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            srv.kill()
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"  {name}: {time.monotonic() - t0:.0f}s stop {res.get('stopSec')}s bits {max(res.get('bits') or [0])}", flush=True)
