"""A crowded room up close keeps the things with a use (2.3.10, requester 10-20: 「遊び以外の意味があるオブジェクト
（シュレッダー、呼び鈴、段ボール箱など）は残すように」; ticket 2026-10-20-jui-viz-functional-props-gone-in-a-crowded-room).

The real `jui viz serve` in a throwaway HOME on a free port, the real forward.py, one room made here: a git repository
(gitbox.make_repo) with docs/api (the data server's rack) and docs/infra (the server room's door). Up close:
- 10 robots: both sets (the looks: wood, the water server, the vacuum, the booth, the machine; the things with a use:
  the shredder, the git box's desk, the call bell, the rack, the door).
- an 11th: the looks go, the things with a use stay. The room grows at the same count (roomSize: 10 robots or fewer,
  then 11+), and a room laid out again builds its props again (its geometry; a trip stops 'relaid'): so at 10 -> 11 the
  group may be new only when the room's rect changed, and that is printed.
- 12 (the same room size): the same group, not built again; a push walks to the box and back (before: no box, no
  trip); a deletion carries the papers to the shredder; the bell, the rack and the door open what they open when
  pressed on the page. 12 -> 11: the same group again.
- 10 again: the looks come back with the things with a use.
No console error, nothing requested outside the server.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, ISOLATE, LAUNCH_ARGS, Watch, desk_pins_js, new_page, ready
from waits import settled, until

SID = "e2e00000-0000-4000-8000-0000000003{:02x}"
PROPS = "() => window.__dbg.props()"
WHY = """() => { const s = window.__dbg.sr();
  return { view: window.__dbg.view(), sr: { phase: s.phase, open: s.open, built: s.built, door: s.door, bubble: s.bubble, log: s.log },
    call: !document.getElementById('call').hidden, ds: window.__dbg.dataServer().open, solo: window.__dbg.solo(), git: window.__dbg.gitBox().trips,
    uses: window.__dbg.props().uses, fun: window.__dbg.props().fun }; }"""
# the one trip under way (one robot pushes at a time here): its robot and phase, and the trips' ends
TRIP = """() => { const b = window.__dbg.gitBox(), t = Object.entries(b.trips).find(([, x]) => x && x.phase);
  return { id: t ? t[0] : null, phase: t ? t[1].phase : null, ends: b.ends, desk: b.desk }; }"""
# what lies under a page point: the 3D (nearest first) and the element on top there (a tag or a bubble takes the press
# before the canvas does)
UNDER = """(p) => { const e = document.elementFromPoint(p[0], p[1]);
  return { scene: window.__dbg.under(p), top: e ? `${e.tagName.toLowerCase()}#${e.id}.${[...e.classList].join('.')}` : null,
    canvas: e === document.querySelector('canvas') }; }"""
# a page point near p where the thing is what a press takes: the canvas is on top there and the 3D's pick is it (as
# liveFirstHit: the nearest hit, or the first fixture behind a robot in front) (in
# a crowded room a robot, its desk or its tag can stand in front of part of it; the seats come from the room's id,
# which moves with --out). Rings out to 40 px; null when it is hidden at every point (then the arm says so).
FIND = """([p, kind]) => { const PICK = (u) => { u = u || []; const fx = ['bell', 'rack', 'door']; return u[0] && u[0].startsWith('robot:') ? (u.find((k) => fx.includes(k)) || u[0]) : u[0]; }; for (let r = 0; r <= 40; r += 4) for (let a = 0; a < (r ? 16 : 1); a++) {
    const q = [Math.round(p[0] + r * Math.cos(a * Math.PI / 8)), Math.round(p[1] + r * Math.sin(a * Math.PI / 8))];
    const e = document.elementFromPoint(q[0], q[1]);
    if (e === document.querySelector('canvas') && PICK(window.__dbg.under(q)) === kind) return q; }
  return null; }"""
# A robot's tag over a thing to press (ticket 2026-10-20-jui-viz-robot-tag-covers-a-fixture-in-a-crowded-room; the ruling
# of 10-20: the press goes through to the thing): the points inside a visible tag where the 3D's nearest is `kind`. The
# robots' desks are pinned (TAG_PINS, the page's desk memory) so a tag stands over the bell in every run.
COVER = """(kind) => { const PICK = (u) => { u = u || []; const fx = ['bell', 'rack', 'door']; return u[0] && u[0].startsWith('robot:') ? (u.find((k) => fx.includes(k)) || u[0]) : u[0]; }; const out = [];
  for (const t of window.__dbg.tags()) for (let x = Math.ceil(t.x0) + 2; x < t.x1 - 2; x += 3) for (let y = Math.ceil(t.y0) + 2; y < t.y1 - 2; y += 3) {
    if (PICK(window.__dbg.under([x, y])) === kind) { out.push({ id: t.id, q: [x, y], text: t.text }); break; } }
  return out; }"""
# (session index, [dx, dz]) in the floor room's coordinates (30-source-live.js seatPos): measured in a run where that
# robot's tag stood over the bell (crowded-props calibration, below)
TAG_PINS = [(0, [2.3, 3.1])]   # the middle of 104 spots __dbg.tagPinsOver gave at 20:31 (12 robots, 1440 x 900)
# Where to pin a desk so its robot's tag covers the bell's point: every floor-room spot (0.1 apart) whose tag, as
# placeRobotTags draws it (the robot's position + TAG_UP, projected; a tag's size as one drawn now), holds that point
USES = {"shredder": True, "gitDesk": True, "bell": True, "dataServer": True, "serverDoor": True}
NO_LOOKS = {"booth": False, "vend": False, "vac": False, "server": False}


def check(failures, cond, text):
    if not cond:
        failures.append(f"crowded-props: {text}")


async def wait(page, js, timeout=20000, label="", arg=None):
    await until(page, js, label or js[:90], arg=arg, timeout=timeout, why=WHY)


async def run_crowded_props(pw, out, failures):
    from run import free_port
    from gitbox import make_repo
    from data_server import _room as data_room
    import server_room
    out = pathlib.Path(out) / "crowded-props"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    repo = out / "work" / "crowd-app"
    revs = make_repo(repo)
    server_room._write(out / "work", server_room._examples(jt), "aws-three-tier", "crowd-app")   # docs/infra: the door
    data_room(repo, True)   # a JsonUI room (jui.config.json) with docs/api and docs/db: the rack
    port = free_port()
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log,
                           stderr=subprocess.STDOUT, env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"
    res: dict = {"revs": revs}
    n = {"use": 0}

    def hook(sid, **payload):
        body = {"session_id": sid, "cwd": str(repo), "permission_mode": "default", **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(),
                       capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)

    def bash(sid, command, stdout="", stderr="", stop=False):
        n["use"] += 1
        use = f"toolu_crowd{n['use']}"
        hook(sid, hook_event_name="PreToolUse", tool_name="Bash", tool_use_id=use, tool_input={"command": command})
        hook(sid, hook_event_name="PostToolUse", tool_name="Bash", tool_use_id=use, tool_input={"command": command},
             tool_response={"stdout": stdout, "stderr": stderr})
        if stop:
            hook(sid, hook_event_name="Stop")

    def push(sid):
        bash(sid, "git push", stderr=f"To example.invalid:team/crowd-app.git\n   {revs['base']}..{revs['big']}  main -> main\n")

    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    t0 = time.monotonic()
    try:
        import urllib.request
        for _ in range(150):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        watch = Watch(origin=url)
        page = await new_page(browser, watch, "crowded-props", **DESKTOP)
        if TAG_PINS:
            await page.add_init_script(desk_pins_js([(str(repo), SID.format(i), spot) for i, spot in TAG_PINS]))
        await page.emulate_media(color_scheme="light", reduced_motion="no-preference")
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", label="connected")
        for i in range(10):
            hook(SID.format(i), hook_event_name="SessionStart", source="startup")
        await wait(page, "() => window.__dbg.robots.length === 10", timeout=30000, label="ten robots")
        # no game, nap, bento or break: a robot on one would not take a trip or an errand when the arm wants it
        await page.evaluate("() => { window.__dbg.play({ p: 0, solo: { p: 0 } }); window.__dbg.brk({ p: { smoke: 0, vend: 0 } }); }")
        room_id = await page.evaluate("() => window.__dbg.robots[0].def.room")
        count = f"() => window.__dbg.robots.filter((R) => R.def.room === '{room_id}').length"
        await page.click(f".tag.room[data-set-project='{room_id}']")
        await wait(page, f"() => window.__dbg.solo() === '{room_id}' && window.__dbg.props().room === '{room_id}' && window.__dbg.props().uses.dataServer && window.__dbg.props().uses.serverDoor",
                   timeout=30000, label="ten up close, the rack and the door")
        await settled(page, "ten seated up close", timeout=60000)

        # ---- 10: both sets ----
        p10 = res["ten"] = await page.evaluate(PROPS)
        group = p10["groupId"]
        check(failures, p10["fun"] and p10["wood"] and all(p10["looks"].values()) and p10["uses"] == USES,
              f"ten robots: the looks and the things with a use: fun {p10['fun']} wood {p10['wood']} looks {p10['looks']} uses {p10['uses']}")

        # ---- an 11th: the looks go, the things with a use stay ----
        rect = f"() => {{ const r = window.__dbg.room('{room_id}'); return [r.x0, r.z0, r.x1, r.z1]; }}"
        rect10 = res["rectTen"] = await page.evaluate(rect)
        hook(SID.format(10), hook_event_name="SessionStart", source="startup")
        await wait(page, f"() => ({count})() === 11 && !window.__dbg.props().fun && window.__dbg.props().uses.serverDoor", timeout=30000, label="eleven: the looks gone")
        p11 = res["eleven"] = await page.evaluate(PROPS)
        rect11 = res["rectEleven"] = await page.evaluate(rect)
        check(failures, p11["room"] == room_id and not p11["wood"] and p11["looks"] == NO_LOOKS and p11["uses"] == USES,
              f"eleven robots: no looks, every thing with a use: room {p11['room']} wood {p11['wood']} looks {p11['looks']} uses {p11['uses']}")
        check(failures, p11["groupId"] == group or rect11 != rect10,
              f"ten to eleven: the things with a use built again only with the room laid out again: group {group} -> {p11['groupId']}, rect {rect10} -> {rect11}")
        res["tenToElevenRebuilt"] = p11["groupId"] != group
        group = p11["groupId"]

        # ---- 12: a push, a deletion, three presses ----
        hook(SID.format(11), hook_event_name="SessionStart", source="startup")
        await wait(page, f"() => ({count})() === 12", timeout=30000, label="twelve")
        await settled(page, "twelve seated", timeout=60000)
        p12 = res["twelve"] = await page.evaluate(PROPS)
        check(failures, p12["groupId"] == group and p12["uses"] == USES and not p12["fun"] and await page.evaluate(rect) == rect11,
              f"eleven to twelve (the same room): the same things with a use, no looks: {group} -> {p12['groupId']} {p12['uses']} fun {p12['fun']}")
        brk = await page.evaluate("() => window.__dbg.brk().built")
        check(failures, not brk["booth"] and not brk["vend"], f"twelve: no booth, no machine: {brk}")

        push(SID.format(1))
        seen = []
        for _ in range(200):
            t = await page.evaluate(TRIP)
            if t["phase"] and (not seen or seen[-1] != t["phase"]):
                seen.append(t["phase"])
            if seen and not t["phase"]:
                break
            await page.wait_for_timeout(100)
        res["pushTwelve"] = seen
        end = (await page.evaluate(TRIP))["ends"][-1:]
        check(failures, seen[:1] == ["going"] and "back" in seen and end and end[0].get("why") == "done",
              f"twelve: a push walks to the box, empties its stack there and comes back: {seen} {end}")

        bash(SID.format(2), "rm stale.log", stop=True)
        await wait(page, "() => window.__dbg.shred().robots.some((x) => x.phase)", timeout=20000, label="twelve: an errand to the shredder")
        phases = set()
        for _ in range(200):
            ph = [x["phase"] for x in (await page.evaluate("() => window.__dbg.shred()"))["robots"] if x["phase"]]
            phases.update(ph)
            if not ph:
                break
            await page.wait_for_timeout(100)
        res["shredTwelve"] = sorted(phases)
        check(failures, "feeding" in phases, f"twelve: the papers go into the shredder: {sorted(phases)}")

        await settled(page, "twelve before the presses", timeout=60000)
        await until(page, "() => !window.__dbg.view().tween", "the camera still", timeout=20000)
        b = res["bell"] = await page.evaluate("() => window.__dbg.bell()")
        check(failures, b["built"] and b["inView"], f"twelve: the bell in view: {b}")
        at = res["bellAt"] = await page.evaluate(FIND, [b["screen"], "bell"])
        check(failures, at, f"twelve: the bell can be pressed somewhere, not covered at every point (a robot's tag: ticket 2026-10-20-jui-viz-robot-tag-covers-a-fixture-in-a-crowded-room): {await page.evaluate(UNDER, b['screen'])}")
        if at:
            await page.mouse.click(*at)
            await wait(page, "() => !document.getElementById('call').hidden", label="twelve: the bell opens the call dialog")
            await page.keyboard.press("Escape")
            await wait(page, "() => document.getElementById('call').hidden", label="the call dialog closed")
            await until(page, "() => !window.__dbg.view().tween", "the camera still after the bell", timeout=20000)
        d = res["rack"] = await page.evaluate("() => window.__dbg.dataServer()")
        # what lies under the points pressed, nearest first (a bigger room: the camera is farther, the bell and the rack closer on the page)
        res["under"] = {"bell": await page.evaluate(UNDER, b["screen"]),
                        "rack": await page.evaluate(UNDER, d["screen"])}
        at = res["rackAt"] = await page.evaluate(FIND, [d["screen"], "rack"])
        check(failures, at, f"twelve: the rack can be pressed somewhere (ticket 2026-10-20-jui-viz-robot-tag-covers-a-fixture-in-a-crowded-room): {res['under']['rack']}")
        if at:
            await page.mouse.click(*at)
            await wait(page, "() => { const d = window.__dbg.dataServer(); return d.open && !d.loading; }", label="twelve: the rack opens the sheet")
            await page.keyboard.press("Escape")
            await wait(page, "() => !window.__dbg.dataServer().open && document.getElementById('ds').hidden", label="the sheet closed")
            await until(page, "() => !window.__dbg.view().tween", "the camera still after the rack", timeout=20000)
        s = res["door"] = await page.evaluate("() => window.__dbg.sr()")
        res["under"]["door"] = await page.evaluate(UNDER, s["door"])
        at = res["doorAt"] = await page.evaluate(FIND, [s["door"], "door"])
        check(failures, at, f"twelve: the door can be pressed somewhere (ticket 2026-10-20-jui-viz-robot-tag-covers-a-fixture-in-a-crowded-room): {res['under']['door']}")
        if at:   # covered at every point: said above, and nothing to press
            await page.mouse.click(*at)
            await wait(page, "() => window.__dbg.sr().open", timeout=20000, label="twelve: the door opens the server room")
            await page.keyboard.press("Escape")
            await wait(page, "() => !window.__dbg.sr().open", label="the server room closed")
        await page.screenshot(path=str(out / "twelve-light.png"))

        # ---- a robot's tag over the bell: the press goes to the bell; a tag over nothing selects its robot ----
        await settled(page, "twelve before the tags", timeout=60000)
        await until(page, "() => !window.__dbg.view().tween", "the camera still before the tags", timeout=20000)
        # tags kept apart push the pinned robot's tag up off the bell when a nearer robot's tag stands below it (the
        # other desks move with --out: 22:02, the pinned tag was over the rack): off for this arm (tag-click does the
        # same, __dbg.tagsApart), on again after
        await page.evaluate("() => window.__dbg.tagsApart(false)")
        await settled(page, "the tags where their robots are", timeout=30000)
        covers = res["covers"] = {k: await page.evaluate(COVER, k) for k in ("bell", "rack", "door")}
        res["seats"] = await page.evaluate("() => Object.fromEntries(window.__dbg.robots.map((R) => [R.def.realId || R.def.id, window.__dbg.seats()[R.def.id]]))")
        for i, spot in TAG_PINS:   # a pin that did not take is a failure, not a quiet draw (common.desk_pins_js)
            got = res["seats"].get(SID.format(i)) or {}
            check(failures, [got.get("dx"), got.get("dz")] == spot, f"session {i}'s desk is where the arm pinned it {spot}: {got}")
        if not covers["bell"]:   # where a pin would put a tag over the bell (TAG_PINS was chosen from this)
            res["pinCandidates"] = await page.evaluate("(p) => window.__dbg.tagPinsOver(p)", (await page.evaluate("() => window.__dbg.bell()"))["screen"])
        check(failures, covers["bell"], f"a robot's tag stands over the bell (TAG_PINS; candidates {res.get('pinCandidates')}): covers {covers}")
        if covers["bell"]:
            c = covers["bell"][0]
            res["tagOverBell"] = {"id": c["id"], "q": c["q"], "top": await page.evaluate(UNDER, c["q"])}
            await page.mouse.click(*c["q"])
            await page.wait_for_timeout(600)
            got = res["tagOverBellPressed"] = await page.evaluate("() => ({ call: !document.getElementById('call').hidden, card: window.__dbg.view().card })")
            check(failures, got["call"] and not got["card"], f"a press on {c['id']}'s tag over the bell opens the call dialog, not the robot's card: {got} at {c['q']}")
            await page.keyboard.press("Escape")
            await wait(page, "() => document.getElementById('call').hidden && !window.__dbg.view().card", label="closed after the tag over the bell")
            await until(page, "() => !window.__dbg.view().tween && !window.__dbg.view().zoomed", "the camera back after the tag over the bell", timeout=20000)
        # the wait's bubble over that tag (a permission prompt): by its own box (40-scene.js placeRobotTags) — faint and let
        # through only when it crosses a thing to press itself; the tag under it stays let through
        if covers["bell"]:
            lab = covers["bell"][0]["id"]
            rid = (await page.evaluate("(l) => window.__dbg.overFixture(l)", lab))["realId"]
            hook(rid, hook_event_name="Notification", notification_type="permission_prompt", message="permission")
            await wait(page, "(l) => { const o = window.__dbg.overFixture(l); return o && o.waitBox; }", label="the wait's bubble over the tag", arg=lab)
            await settled(page, "the bubble placed", timeout=30000)
            o = res["bubble"] = await page.evaluate("(l) => window.__dbg.overFixture(l)", lab)
            fx = res["fixRects"] = await page.evaluate("() => window.__dbg.fixRects()")
            wb = o["waitBox"]
            crosses = any(wb[0] < f[1] and f[0] < wb[1] and wb[2] < f[3] and f[2] < wb[3] for f in fx)
            centre = [round((wb[0] + wb[1]) / 2), round((wb[2] + wb[3]) / 2)]
            top = res["bubbleTop"] = await page.evaluate("(p) => { const e = document.elementFromPoint(p[0], p[1]); return e ? e.className : null; }", centre)
            res["bubbleCrosses"] = crosses
            check(failures, o["tag"], f"the tag under the bubble is still let through over the bell: {o}")
            check(failures, o["wait"] == crosses, f"the bubble is let through exactly when its own box crosses a thing to press: crosses {crosses}, class {o['wait']}, {wb} {fx}")
            check(failures, ("wait-bubble" in (top or "")) != crosses, f"the bubble takes a press at its centre only when it crosses nothing: top {top!r}, crosses {crosses}")
            hook(rid, hook_event_name="UserPromptSubmit", prompt="next")
            hook(rid, hook_event_name="Stop")
            await wait(page, "(l) => { const o = window.__dbg.overFixture(l); return o && !o.waitBox; }", label="the bubble gone", arg=lab)
        over = {x["id"] for k in covers for x in covers[k]}
        free = await page.evaluate("""(over) => window.__dbg.tags().filter((t) => !over.includes(t.id)).map((t) => {
            const q = [Math.round((t.x0 + t.x1) / 2), Math.round((t.y0 + t.y1) / 2)], e = document.elementFromPoint(q[0], q[1]);
            return { id: t.id, q, onTag: !!(e && e.closest('[data-robot]')) }; }).filter((t) => t.onTag)""", sorted(over))
        res["freeTag"] = free[:1]
        check(failures, free, f"a tag over nothing to press, to press: {free}")
        if free:
            await page.mouse.click(*free[0]["q"])
            await wait(page, f"() => window.__dbg.view().card === '{free[0]['id']}'", label="a tag over nothing selects its robot")
            await page.keyboard.press("Escape")
            await wait(page, "() => !window.__dbg.view().card", label="the card closed")
            await until(page, "() => !window.__dbg.view().tween && !window.__dbg.view().zoomed", "the camera back after the card", timeout=20000)

        await page.evaluate("() => window.__dbg.tagsApart(true)")

        # ---- 12 -> 11: the same group; -> 10: the looks back ----
        await settled(page, "twelve before one leaves", timeout=60000)
        hook(SID.format(11), hook_event_name="SessionEnd", reason="exit")
        await wait(page, f"() => ({count})() === 11 && window.__dbg.robots.length === 11", timeout=30000, label="eleven again")
        p11b = res["elevenAgain"] = await page.evaluate(PROPS)
        check(failures, p11b["groupId"] == group and p11b["uses"] == USES and not p11b["fun"],
              f"twelve to eleven: the same things with a use, no looks: {group} -> {p11b['groupId']} {p11b['uses']} fun {p11b['fun']}")
        await settled(page, "eleven before one leaves", timeout=60000)
        hook(SID.format(10), hook_event_name="SessionEnd", reason="exit")
        await wait(page, "() => window.__dbg.props().fun", timeout=40000, label="ten again: the looks back")
        p10b = res["tenAgain"] = await page.evaluate(PROPS)
        check(failures, p10b["uses"] == USES and p10b["wood"] and all(p10b["looks"].values()),
              f"ten again: the looks back with the things with a use: {p10b['uses']} wood {p10b['wood']} looks {p10b['looks']}")
        await page.screenshot(path=str(out / "ten-again-light.png"))
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
    print(f"  crowded-props: {time.monotonic() - t0:.0f}s", flush=True)
