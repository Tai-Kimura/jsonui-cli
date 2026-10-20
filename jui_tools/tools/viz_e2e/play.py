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
from waits import settled, until
from rooms import SEG_JS

A = "e2e00000-0000-4000-8000-0000000000da"
B = "e2e00000-0000-4000-8000-0000000000db"
CWD = "/work/play-app"
THIRD = "e2e00000-0000-4000-8000-0000000000dc"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")


def check(failures, cond, text):
    if not cond:
        failures.append(f"play: {text}")


# Every wait here is on page state, checked each animation frame (waits.until, 2.3.5): on a busy machine the page
# draws a few frames a second, and a wait that polled on the clock could read between them. A timeout says the play
# state and every robot's settle state at that moment.
PLAY_WHY = "() => ({ play: window.__dbg.play(), settle: window.__dbg.settleInfo() })"


async def wait(page, js, timeout=20000, label="", arg=None):
    return await until(page, js, label or js[:90], arg=arg, timeout=timeout, why=PLAY_WHY)


# One game until what the arm looks for shows, or the game is over (state, every frame): the ball's heights (four
# different ones, more than 0.3 m apart; gathered in window.__playYs as the frames come), or a hand over a head.
GAME_SEEN_JS = """(kind) => {
  const p = window.__dbg.play(), g = p.list.find((x) => x.kind === kind && x.started);
  const ys = window.__playYs || (window.__playYs = []);
  if (!g) return { ended: true, shown: false, ys };
  if (kind === 'rps') return p.robots.some((x) => x.rps) ? { ended: false, shown: true, ys } : false;
  if (g.ball) ys.push(g.ball[1]);
  return new Set(ys).size >= 4 && Math.max(...ys) - Math.min(...ys) > 0.3 ? { ended: false, shown: true, ys } : false;
}"""



async def turn_over(page, rid, send_stop):
    """Send the turn's Stop and wait until the page has seen it end: done, then idle again (done -> idle comes 3 s
    later). A nap or a bento started before that done reaches the page ends at once ('state:done'): under load the
    done came late and the nap was gone before it was measured (docs/bugs/2026-10-19-jui-viz-e2e-play-nap-sometimes-
    never-starts.md). Waits on the states the page has seen, not on time."""
    await page.evaluate("""(id) => { clearInterval(window.__turnRec); window.__turnSeen = [];
      window.__turnRec = setInterval(() => { const st = window.__dbg.robotState()[id]; if (st && window.__turnSeen[window.__turnSeen.length - 1] !== st.state) window.__turnSeen.push(st.state); }, 20); }""", rid)
    send_stop()
    await wait(page, "(id) => window.__turnSeen.includes('done') && window.__dbg.robotState()[id].state === 'idle'", arg=rid, timeout=20000, label="the turn over: done, then idle")
    await page.evaluate("() => clearInterval(window.__turnRec)")


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

    async def settle(page):
        """No game in the way of the next step: end every game, nobody starts one, everyone back at a desk."""
        await page.evaluate("() => window.__dbg.play({ p: 0, endAll: true, solo: { p: 0 } })")
        await wait(page, "() => window.__dbg.play().list.length === 0 && window.__dbg.play().robots.every((x) => !x.back && x.path === 0 && !x.solo)",
                   timeout=60000, label="everyone back at a desk")
        return len((await page.evaluate(play))["ends"])
    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    t0 = time.monotonic()
    try:
        import urllib.request
        for _ in range(400):   # 40 s: under a load average of 30-40 the server took longer than the 10 s this waited (a library lane, 10-18)
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError(f"the server did not answer /health in 40 s: {(out / 'serve.log').read_text()[-400:]}")
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
            # an 8 s game, shorter than the wait for it (30 s): a game that ends before what the arm looks for shows is
            # red by its own branch ("ended"), never by a timeout. The players' pose takes its real time on a busy
            # machine since 8748dc3e (it took the whole of an 8 s game before, at a frame or two a second); the game is
            # ended here once it has been seen
            await page.evaluate(f"() => window.__dbg.play({{ kinds: ['{kind}'], restMinSec: 0, restMaxSec: 0, minSec: 8, maxSec: 8 }})")
            g = await wait(page, f"() => window.__dbg.play().list.find((g) => g.kind === '{kind}' && g.started) || false", timeout=20000, label=f"a {kind} game")
            await settled(page, f"the {kind} players at their spot", ids=g["players"])
            await page.evaluate("() => { window.__playYs = []; }")
            seen = await wait(page, GAME_SEEN_JS, timeout=30000, label=f"the {kind} game shows (or ends)", arg=kind)
            if kind == "ball":
                res["ballY"] = seen["ys"][:40]
                check(failures, seen["shown"], f"the ball flies, before the game ends: {seen['ended']} {seen['ys'][:20]}")
            else:
                res["rps"] = seen
                check(failures, seen["shown"], f"a hand shows over a head, before the game ends: {seen}")
            await page.evaluate("() => window.__dbg.play({ endAll: true })")
            await wait(page, "() => window.__dbg.play().list.length === 0 && window.__dbg.play().robots.every((x) => !x.back)", timeout=40000, label=f"the {kind} game ends")
            await page.evaluate("() => window.__dbg.play({ restMinSec: 0, restMaxSec: 0 })")
        await page.screenshot(path=str(out / "after.png"))
        # a game plays its whole length once both are there (requester, 10-18: "歩いて二人近づいただけで終わった"): the clock
        # starts when they meet, so a game shorter than the walk still plays (with the clock from the walk's start it
        # ended before they met)
        n0 = await settle(page)                                         # only the ends after this point
        await page.evaluate("() => window.__dbg.play({ p: 1, kinds: ['highfive'], restMinSec: 0, restMaxSec: 0, minSec: 2, maxSec: 2 })")
        await wait(page, f"() => window.__dbg.play().ends.length > {n0} && window.__dbg.play().list.length === 0",
                   timeout=40000, label="a short game that ends")
        e = res["shortGame"] = (await page.evaluate(play))["ends"][n0]
        check(failures, e["playedSec"] >= 1.9, f"it played its whole length after they met: {e}")
        # another session opens a new room in the middle of a game: the rooms are laid out again and the desks in this
        # one move, and the game goes on (before 2.3.1 a moved desk stopped it). A third robot in the same room does
        # not move the others' desks (measured): it takes a new one.
        await settle(page)
        await page.evaluate("() => window.__dbg.play({ p: 1, kinds: ['highfive'], restMinSec: 0, restMaxSec: 0, minSec: 12, maxSec: 12 })")
        await wait(page, "() => window.__dbg.play().list.some((g) => g.started)", timeout=20000, label="a game before the third robot")
        before = {x["id"]: x["seatKey"] for x in (await page.evaluate(play))["robots"]}
        n_ends = len((await page.evaluate(play))["ends"])
        hook(THIRD, hook_event_name="SessionStart", source="startup", cwd="/work/play-third")
        await wait(page, "() => window.__dbg.play().robots.length >= 3", label="the third robot")
        try:   # the room laid out again: a desk of the two moves (a state; the check below says so if it never did)
            await wait(page, "(before) => window.__dbg.play().robots.some((x) => x.id in before && x.seatKey !== before[x.id])",
                       timeout=20000, label="a desk moved for the third robot", arg=before)
        except RuntimeError:
            pass
        r = await page.evaluate(play)
        moved = [x["id"] for x in r["robots"] if x["id"] in before and x["seatKey"] != before[x["id"]]]
        check(failures, bool(moved), f"the room was laid out again and a desk moved (else this says nothing): {before} -> {[(x['id'], x['seatKey']) for x in r['robots']]}")
        check(failures, any(g["started"] for g in r["list"]), f"the game goes on after the desks moved: {r['list']} ends {r['ends'][n_ends:]}")
        await wait(page, "() => window.__dbg.play().list.length === 0", timeout=30000, label="that game ends")
        e = (await page.evaluate(play))["ends"][n_ends:]
        res["relaidGame"] = e
        check(failures, any(x["reason"] == "done" for x in e), f"it ended by itself, not by the move: {e}")
        hook(THIRD, hook_event_name="SessionEnd", reason="exit", cwd="/work/play-third")
        await wait(page, "() => window.__dbg.play().robots.length === 2 && window.__dbg.play().robots.every((x) => !x.play && !x.back && x.path === 0)",
                   timeout=60000, label="the third robot gone, both at their desks")
        # the same, while they are still walking to the spot: they still arrive there and play (the desks' move must
        # not take their path: in one run in three they walked to their new desks and "played" from there)
        await settle(page)
        n1 = len((await page.evaluate(play))["ends"])
        await page.evaluate("() => window.__dbg.play({ p: 1, kinds: ['highfive'], restMinSec: 0, restMaxSec: 0, minSec: 6, maxSec: 6 })")
        await wait(page, "() => window.__dbg.play().robots.filter((x) => x.play === 'going').length === 2", timeout=20000, label="both on their way")
        hook(THIRD, hook_event_name="SessionStart", source="startup", cwd="/work/play-third")
        await wait(page, "() => window.__dbg.play().list.some((g) => g.started) || window.__dbg.play().ends.length > " + str(n1), timeout=30000, label="they meet")
        r = await page.evaluate(play)
        res["goingMove"] = {"list": r["list"], "ends": r["ends"][n1:], "robots": [{k: x[k] for k in ("id", "x", "z", "seat", "play")} for x in r["robots"]]}
        players = [x for x in r["robots"] if x["play"] == "playing"]
        check(failures, len(players) == 2 and all(abs(x["z"] - players[0]["z"]) < 0.05 and [x["x"], x["z"]] != x["seat"] for x in players),
              f"they met at the spot, not at their desks: {res['goingMove']}")
        await wait(page, "() => window.__dbg.play().list.length === 0", timeout=30000, label="that game ends")
        hook(THIRD, hook_event_name="SessionEnd", reason="exit", cwd="/work/play-third")
        await wait(page, "() => window.__dbg.play().robots.length === 2 && window.__dbg.play().robots.every((x) => !x.play && !x.back && x.path === 0)",
                   timeout=60000, label="the third robot gone again, both at their desks")
        # its desk moves to another room in the middle of a game (cd): it walks back through the doors, never a wall
        await settle(page)
        await page.evaluate("() => window.__dbg.play({ p: 1, kinds: ['highfive'], restMinSec: 0, restMaxSec: 0, minSec: 30, maxSec: 30 })")
        await wait(page, "() => window.__dbg.play().list.some((g) => g.started)", timeout=20000, label="a game before the move")
        res["moveStart"] = await page.evaluate(play)
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
        # not playing, at the desk's coordinates: a robot still at play has an empty path and no walk back either, so the
        # looser test passed in the frame before playTick stopped the game (1 run in 4, read as a robot that never moved)
        # the two of the game only: the seven in the other room may be at a game of their own
        pair = json.dumps(res["moveStart"]["list"][0]["players"])
        await wait(page, "() => window.__dbg.play().robots.filter((x) => " + pair + ".includes(x.id)).every((x) => !x.play && !x.back && x.path === 0 && x.x === x.seat[0] && x.z === x.seat[1])",
                   timeout=30000, label="both at their desks again")
        walk = res["move"] = await page.evaluate("() => ({ hits: window.__walk.hits.length, rooms: window.__walk.rooms, steps: window.__walk.steps })")
        res["moveRobots"] = (await page.evaluate(play))["robots"]
        res["moveEnds"] = (await page.evaluate(play))["ends"][-3:]
        res["moveList"] = (await page.evaluate(play))["list"]
        check(failures, walk["hits"] == 0, f"no step through a wall: {walk}")
        check(failures, any(len(v) >= 2 for v in walk["rooms"].values()), f"one robot did go to another room (else the check above says nothing): {walk}")
        # B is alone in the old room now: it naps or eats a bento at its desk, and an instruction stops that at once
        await page.evaluate("() => window.__dbg.play({ restMinSec: 0, restMaxSec: 0, solo: { p: 1, minSec: 30, maxSec: 30 } })")
        await wait(page, "() => window.__dbg.play().robots.some((x) => x.room === '" + a_room + "' && x.solo)", timeout=20000, label="the one alone naps or eats")
        r = await page.evaluate(play)
        lone = next(x for x in r["robots"] if x["room"] == a_room and x["solo"])
        res["solo"] = lone
        check(failures, (lone["zzz"] if lone["solo"] == "nap" else lone["bento"]) and lone["desk"] and lone["path"] == 0 and lone["lamp"] == "idle",
              f"at its desk, the zzz or the bento shows, the lamp is idle: {lone}")
        await page.screenshot(path=str(out / f"solo-{lone['solo']}.png"))
        hook(B, hook_event_name="UserPromptSubmit", prompt="起きて")
        t3 = time.monotonic()
        await wait(page, "() => !window.__dbg.play().robots.some((x) => x.room === '" + a_room + "' && (x.solo || x.zzz || x.bento))", timeout=5000, label="it stops on the instruction")
        res["soloStopSec"] = round(time.monotonic() - t3, 1)
        await turn_over(page, lone["id"], lambda: hook(B, hook_event_name="Stop"))
        # both alone kinds, up close, light and dark (96, 10-18: the zzz was all but lost on the dark floor, the bento a few
        # pixels): the sprite and the box are there and big enough; the pictures are for the eye
        await wait(page, "() => window.__dbg.play().robots.every((x) => !x.solo && x.path === 0)", timeout=20000, label="B at rest")
        res["soloLook"] = {}
        for kind in ("nap", "bento"):
            await page.evaluate("() => window.__dbg.play({ restMinSec: 0, restMaxSec: 0, solo: { p: 1, minSec: 60, maxSec: 60, kinds: ['" + kind + "'] } })")
            await wait(page, "() => window.__dbg.play().robots.some((x) => x.room === '" + a_room + "' && x.solo === '" + kind + "')", timeout=30000, label=f"alone: {kind}")
            await page.click(f".tag.room[data-set-project='{a_room}']")
            await wait(page, f"() => window.__dbg.solo() === '{a_room}'", label="up close")
            for scheme in ("light", "dark"):
                await page.emulate_media(color_scheme=scheme)
                await settled(page, f"alone up close ({kind}, {scheme})", ids=[lone["id"]])
                await page.screenshot(path=str(out / f"solo-{kind}-{scheme}.png"))
            res.setdefault("soloTags", {})[kind] = next((x["tag"] for x in (await page.evaluate(play))["robots"] if x["solo"] == kind), None)
            res["soloLook"][kind] = await page.evaluate("""() => { const R = window.__dbg.robots.find((x) => x.solo); if (!R) return null;
              const o = R.robot.zzz && R.robot.zzz.visible ? R.robot.zzz : R.robot.bento; const b = new window.__dbg.THREE.Box3().setFromObject(o);
              const s = new window.__dbg.THREE.Vector3(); b.getSize(s); return { w: +s.x.toFixed(2), h: +s.y.toFixed(2), d: +s.z.toFixed(2) }; }""")
            if res["soloLook"][kind] is None:   # gone before it was measured: how it ended (docs/bugs/2026-10-19-jui-viz-e2e-play-nap-sometimes-never-starts.md)
                res.setdefault("soloGone", {})[kind] = (await page.evaluate(play))["ends"][-3:]
            await page.emulate_media(color_scheme="light")
            await page.click("#room-back")
            await wait(page, "() => window.__dbg.solo() === null", label="back")
            hook(B, hook_event_name="UserPromptSubmit", prompt="起きて")
            await wait(page, "() => !window.__dbg.play().robots.some((x) => x.solo)", timeout=5000, label="stops")
            await turn_over(page, lone["id"], lambda: hook(B, hook_event_name="Stop"))
        look = res["soloLook"]
        check(failures, look.get("nap") and look["nap"]["w"] >= 1.0 and look.get("bento") and look["bento"]["w"] >= 0.55,
              f"the zzz and the bento are big enough to see: {look}")
        check(failures, res.get("soloTags") == {"nap": "zzz 居眠り", "bento": "弁当"}, f"the name tag says it too: {res.get('soloTags')}")
        await page.evaluate("() => window.__dbg.play({ solo: { p: 0, kinds: ['nap', 'bento'] } })")
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
