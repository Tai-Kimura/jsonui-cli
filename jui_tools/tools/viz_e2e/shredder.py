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


# Hold the page's frames (requestAnimationFrame) and let them go again: what happens in between lands in one frame.
HOLD_JS = """() => { const F = window.__frames || (window.__frames = { raf: window.requestAnimationFrame.bind(window), held: [], on: false });
  F.on = true; window.requestAnimationFrame = (cb) => { if (F.on) { F.held.push(cb); return 0; } return F.raf(cb); }; }"""
RELEASE_JS = """() => { const F = window.__frames; F.on = false; window.requestAnimationFrame = F.raf; const cbs = F.held.splice(0); cbs.forEach((cb) => F.raf(cb)); }"""
# From the first frame on: is the robot ever on a break / at a game / napping while on the errand; does it feed the
# shredder; how many samples saw the other (break, game or nap) holding it while the errand waited (the old way).
WINDOW_JS = """async ([id, ms]) => { const out = { samples: 0, both: [], feeding: 0, held: 0, phases: [] }, t0 = performance.now();
  while (performance.now() - t0 < ms) {
    const R = window.__dbg.robots.find((x) => x.def.id === id);
    if (!R) break;
    const other = R.brk ? 'break' : R.play ? 'game' : R.solo ? 'nap' : null, phase = R.shred ? R.shred.phase : null;
    out.samples++;
    if (other && phase) out.both.push([other, phase]);
    if (other && !phase && R.shredPending) out.held++;
    if (phase === 'feeding') out.feeding++;
    if (out.phases[out.phases.length - 1] !== phase) out.phases.push(phase);
    if (out.feeding && !phase) break;
    await new Promise((r) => setTimeout(r, 50));
  }
  out.both = out.both.slice(0, 5); return out; }"""


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
        await wait(page, "() => document.querySelector('.chip.demo').dataset.net === 'connected'", label="connected")
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

        # breaks (2.3.3) and the shredder never take each other's path
        await page.evaluate("() => window.__dbg.play({ p: 0, solo: { p: 0 }, idleMs: 0, restMinSec: 0, restMaxSec: 0 })")
        await page.evaluate("() => window.__dbg.brk({ p: { smoke: 1, vend: 0 }, joinP: 0, smokeMinSec: 60, smokeMaxSec: 60, restMinSec: 0, restMaxSec: 0 })")
        await wait(page, f"() => window.__dbg.brk().robots.some((x) => x.id === '{b}' && x.kind === 'smoke' && x.at)", timeout=40000, label="b on a break")
        await page.evaluate("() => window.__dbg.brk({ p: { smoke: 0, vend: 0 } })")   # no new break from here
        # deleting while on a break: the Bash is work, which ends the break (2.3.3's rule); from there it takes the papers
        # to the shredder — never both at once
        seen = []
        bash(sids[b], "rm on-break.txt")
        for _ in range(40):
            k = next(x for x in (await page.evaluate("() => window.__dbg.brk()"))["robots"] if x["id"] == b)
            r = next(x for x in (await page.evaluate(shred))["robots"] if x["id"] == b)
            seen.append([k["kind"], r["phase"]])
            if r["phase"] == "feeding":
                break
            await page.wait_for_timeout(250)
        res["onBreak"] = seen
        check(failures, not any(kind and phase for kind, phase in seen), f"a break and the errand never at once: {seen}")
        check(failures, seen[-1][1] == "feeding", f"after the break it takes the papers to the shredder: {seen}")
        await page.evaluate("() => window.__dbg.brk({ endAll: true })")
        await wait(page, f"() => {{ const x = window.__dbg.shred().robots.find((y) => y.id === '{b}'); return x.phase === null && x.path === 0 && Math.abs(x.x - x.seat[0]) < 0.01; }}", timeout=30000, label="b back from the shredder")
        bash(sids[a], "rm -f errand.txt")   # on the way to the shredder: a break may not start, even at p = 1
        await wait(page, f"() => window.__dbg.shred().robots.find((x) => x.id === '{a}').phase === 'going'", label="a goes")
        await page.evaluate("() => window.__dbg.brk({ p: { smoke: 1, vend: 1 }, joinP: 1, smokeMinSec: 60, smokeMaxSec: 60, restMinSec: 0, restMaxSec: 0 })")
        took = []
        for _ in range(60):   # to the end of the errand: on the way (a path) and feeding (no path), where a break could start
            k = next(x for x in (await page.evaluate("() => window.__dbg.brk()"))["robots"] if x["id"] == a)
            r = next(x for x in (await page.evaluate(shred))["robots"] if x["id"] == a)
            took.append([r["phase"], k["kind"]])
            if took[-1][0] is None and any(t[0] == "feeding" for t in took):
                break
            await page.wait_for_timeout(250)
        res["errandThenBreak"] = took
        check(failures, any(t[0] == "feeding" for t in took) and all(not kind for phase, kind in took if phase),
              f"no break starts on the way to the shredder or while feeding it: {took}")
        await page.evaluate("() => window.__dbg.brk({ p: { smoke: 0, vend: 0 }, endAll: true })")
        await wait(page, f"() => window.__dbg.shred().robots.find((x) => x.id === '{a}').phase === null", timeout=20000, label="a done")

        # A break, a game or a nap begun in the very frame the deletion lands (2.3.4): brkTick / playTick / soloTick run
        # before shredTick and could start one with the since the deletion brought. The window is made on purpose: the
        # frames are held, the deletion arrives, the knob goes to 1, and the frames go on — the first one is that frame.
        # The deletion ends it (work ends it) and the errand goes; never both at once, never dropped.
        await wait(page, "() => window.__dbg.robots.every((R) => !R.path.length && !R.brk && !R.play && !R.solo)", timeout=30000, label="all seated for the window")
        await page.evaluate("() => { window.__dbg.brk({ p: { smoke: 0, vend: 0 }, endAll: true }); window.__dbg.play({ p: 0, solo: { p: 0 }, idleMs: 0, restMinSec: 0, restMaxSec: 0, endAll: true }); }")
        c = labels[2]
        busy = {"n": 0}

        def hold_busy(sid):   # a tool under way: the robot is not idle (no break, game or nap for it)
            busy["n"] += 1
            hook(sid, hook_event_name="PreToolUse", tool_name="Read", tool_use_id=f"busy{busy['n']}", tool_input={"file_path": f"/work/shred-app/busy-{busy['n']}.json"})
            return f"busy{busy['n']}"

        def free(sid, uid):
            hook(sid, hook_event_name="PostToolUse", tool_name="Read", tool_use_id=uid, tool_input={"file_path": "/work/shred-app/x.json"}, tool_response={})

        for kind, knob, others_busy in (
            ("break", "() => { window.__dbg.brk({ p: { smoke: 1, vend: 0 }, joinP: 0, smokeMinSec: 60, smokeMaxSec: 60, restMinSec: 0, restMaxSec: 0 }); }", (b, c)),
            ("game", "() => { window.__dbg.play({ p: 1, minSec: 60, maxSec: 60, restMinSec: 0, restMaxSec: 0, idleMs: 0 }); }", (c,)),
            ("nap", "() => { window.__dbg.play({ p: 0, solo: { p: 1, minSec: 60, maxSec: 60 }, restMinSec: 0, restMaxSec: 0, idleMs: 0 }); }", (b, c)),
        ):
            held = [(x, hold_busy(sids[x])) for x in others_busy]
            await wait(page, f"() => {{ const s = window.__dbg.robotState(); return {json.dumps(list(others_busy))}.every((id) => s[id].state !== 'idle'); }}", label=f"{kind}: the others busy")
            before = await page.evaluate(f"() => (window.__dbg.robotState()['{a}'].shred || {{}}).at || 0")
            await page.evaluate(HOLD_JS)
            await wait(page, "() => window.__frames.held.length > 0", label=f"{kind}: frames held")
            bash(sids[a], f"rm -f window-{kind}.txt", stop=False)
            await wait(page, f"() => {{ const s = window.__dbg.robotState()['{a}']; return s.state === 'idle' && s.shred && s.shred.at > {before}; }}", label=f"{kind}: the deletion arrived, frames held")
            await page.evaluate(knob)
            await page.evaluate(f"() => {{ window.__dbg.robots.forEach((R) => {{ R.restUntil = R.def.id === '{a}' || ('{kind}' === 'game' && R.def.id === '{b}') ? 0 : 1e12; }}); }}")
            await page.evaluate(RELEASE_JS)
            got = res[f"window-{kind}"] = await page.evaluate(WINDOW_JS, [a, 20000])
            ends = await page.evaluate("() => ({ brk: window.__dbg.brk().ends, play: window.__dbg.play().ends })")
            if kind == "break":
                hit = any(e["who"] == a and e["reason"] == "shred" for e in ends["brk"]) or got["held"] > 0
            elif kind == "game":
                hit = any(a in e["players"] and len(e["players"]) == 2 for e in ends["play"]) or got["held"] > 0
            else:
                hit = any(e["players"] == [a] and e["reason"] == "shred" for e in ends["play"]) or got["held"] > 0
            got["hit"] = hit
            check(failures, hit, f"{kind}: the window was made (one began in the frame the deletion landed): {got} {ends}")
            check(failures, not got["both"] and got["feeding"] > 0,
                  f"{kind} begun in the deletion's frame: the deletion ends it and the errand goes, never both at once: {got}")
            await page.evaluate("() => { window.__dbg.brk({ p: { smoke: 0, vend: 0 }, endAll: true }); window.__dbg.play({ p: 0, solo: { p: 0 }, endAll: true }); }")
            await page.evaluate("() => window.__dbg.robots.forEach((R) => { if (R.solo) { R.solo = null; R.robot.solo = null; } })")
            for x, uid in held:
                free(sids[x], uid)
            await wait(page, f"() => {{ const x = window.__dbg.shred().robots.find((y) => y.id === '{a}'); return x.phase === null && x.path === 0; }}", timeout=30000, label=f"{kind}: a back")
            await wait(page, "() => window.__dbg.robots.every((R) => !R.path.length && !R.brk && !R.play && !R.solo)", timeout=30000, label=f"{kind}: all seated again")
        await page.evaluate("() => window.__dbg.play({ p: 0, solo: { p: 0 }, idleMs: 60000 })")

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
