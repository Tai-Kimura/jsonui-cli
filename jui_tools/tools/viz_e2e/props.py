"""The room up close (requester, 10-18): a water server, a robot vacuum and a wooden floor in the one-room view.

The real `jui viz serve` in a throwaway HOME on a free port; sessions are made with the real forward.py. With 3
robots in a room picked alone: both props are there and the floor carries the plank texture; the vacuum, watched for
a while, never enters a robot's or a desk's box, the server's corner or the front aisle (doors, play spot, easel).
Back to the floor: nothing left (scene children as before, no floor map). Five times in and out: three's geometry and
texture counts do not grow. An 11th robot in the room: the props go. Frame times on the floor and up close are
printed. Screenshots of the building, the floor and the room, light and dark (`--jt` takes them from another tree,
for the before / after pictures). No console error, nothing requested outside the server.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from rooms import SEG_JS
from waits import settled, until
from common import DESKTOP, LAUNCH_ARGS, Watch, new_page, ready

CWD = "/work/props-app"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
SID = "e2e00000-0000-4000-8000-0000000001{:02x}"

# The vacuum's centre against every box it keeps clear of (each grown by its radius), sampled every 100 ms.
WATCH_JS = """(ms) => new Promise((done) => {
  const out = { samples: 0, hits: [], aisle: 0, moved: 0, start: null };
  const t0 = performance.now();
  const tick = () => {
    const p = window.__dbg.props();
    if (p.vac) {
      out.samples++;
      if (!out.start) out.start = p.vac;
      out.moved = Math.max(out.moved, Math.hypot(p.vac[0] - out.start[0], p.vac[1] - out.start[1]));
      for (const [x0, x1, z0, z1] of p.boxes) if (p.vac[0] > x0 - p.radius && p.vac[0] < x1 + p.radius && p.vac[1] > z0 - p.radius && p.vac[1] < z1 + p.radius) out.hits.push([p.vac, [x0, x1, z0, z1]]);
      if (p.vac[1] > p.area.z1 + 1e-6 || p.vac[0] < p.area.x0 - 1e-6 || p.vac[0] > p.area.x1 + 1e-6 || p.vac[1] < p.area.z0 - 1e-6) out.aisle++;
    }
    if (performance.now() - t0 < ms) setTimeout(tick, 100); else done(out);
  };
  tick();
})"""

# The mean and the 95th percentile of the time between frames, over ms.
FRAMES_JS = """(ms) => new Promise((done) => {
  const d = []; let last = performance.now(); const t0 = last;
  const f = (t) => { d.push(t - last); last = t; if (t - t0 < ms) requestAnimationFrame(f); else { d.sort((a, b) => a - b);
    done({ n: d.length, mean: +(d.reduce((a, b) => a + b, 0) / d.length).toFixed(1), p95: +d[Math.floor(d.length * 0.95)].toFixed(1) }); } };
  requestAnimationFrame(f);
})"""


def check(failures, cond, text):
    if not cond:
        failures.append(f"props: {text}")


# Frames SLOW_MS apart (the e2e's own requestAnimationFrame wrapper): a busy machine, made sure. "ten again" waits for a
# robot to walk out of the room; that walk must take about its real time however far apart the frames are (2.3.5,
# ticket 2026-10-19-jui-viz-walk-stretches-with-frame-gaps: 30.6 s at 3 s a frame before, ~9.5 s normally).
SLOW_RAF = """(() => { const raf = window.requestAnimationFrame.bind(window);
  window.requestAnimationFrame = (cb) => { const ms = window.__slowFrameMs || 0; return ms ? setTimeout(() => raf(cb), ms) : raf(cb); }; })()"""
SLOW_MS = 3000
TEN_MAX_SEC = 20
# Two animation frames: the page's own frame has run once after this was called.
NEXT_FRAME = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))"


# What the page looked like when a wait ran out (waits.py): which robots had not arrived, and why.
WHY = "() => ({ props: window.__dbg.props().room, solo: window.__dbg.solo(), robots: window.__dbg.settleInfo() })"


async def wait(page, js, timeout=20000, label=""):
    """Checked on every animation frame (waits.until), named; a timeout carries the page's state (WHY)."""
    await until(page, js, label or js[:90], timeout=timeout, why=WHY)


async def run_props(pw, out, failures, jt=None, shots_only=False):
    from run import free_port
    name = "props-before" if shots_only else "props"
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

    def hook(sid, **payload):
        body = {"session_id": sid, "cwd": CWD, "permission_mode": "default", **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(),
                       capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)

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
        await page.add_init_script(SLOW_RAF)
        await page.emulate_media(color_scheme="light", reduced_motion="no-preference")
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", label="connected")
        for i in range(3):
            hook(SID.format(i), hook_event_name="SessionStart", source="startup")
        await wait(page, "() => window.__dbg.robots.length >= 3", label="three robots")
        await wait(page, "() => window.__dbg.robots.every((R) => !R.path.length)", timeout=30000, label="seated")
        room_id = await page.evaluate("() => window.__dbg.robots[0].def.room")

        async def shots(tag):
            for scheme in ("light", "dark"):
                await page.emulate_media(color_scheme=scheme)
                await page.wait_for_timeout(700)
                await page.evaluate("() => window.__dbg.tower(true)")
                await page.wait_for_timeout(1500)
                await page.screenshot(path=str(out / f"{tag}-building-{scheme}.png"))
                await page.evaluate("() => window.__dbg.tower(false)")
                await page.wait_for_timeout(1500)
                await page.screenshot(path=str(out / f"{tag}-floor-{scheme}.png"))
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

        floor = await page.evaluate("() => window.__dbg.props()")
        check(failures, floor["room"] is None and not floor["floorMap"], f"nothing on the floor view: {floor}")
        res["framesFloor"] = await page.evaluate(FRAMES_JS, 3000)
        # up close, 3 robots
        await page.click(f".tag.room[data-set-project='{room_id}']")
        await wait(page, f"() => window.__dbg.solo() === '{room_id}' && window.__dbg.props().room === '{room_id}'", label="props placed")
        p = res["placed"] = await page.evaluate("() => window.__dbg.props()")
        check(failures, p["server"] and p["vac"] and p["wood"], f"water server, vacuum and wooden floor: {p}")
        res["framesRoom"] = await page.evaluate(FRAMES_JS, 3000)
        w = res["watch"] = await page.evaluate(WATCH_JS, 12000)
        check(failures, w["samples"] >= 60 and not w["hits"], f"the vacuum never enters a robot's, a desk's or the server's box: {w['samples']} samples, hits {w['hits'][:3]}")
        check(failures, w["aisle"] == 0, f"the vacuum stays out of the front aisle and off the walls: {w}")
        check(failures, w["moved"] > 0.3, f"the vacuum moves: {w['moved']}")
        # a robot walks in and sits down (a 4th session): still clear
        hook(SID.format(3), hook_event_name="SessionStart", source="startup")
        w = res["watchArrive"] = await page.evaluate(WATCH_JS, 10000)
        check(failures, not w["hits"], f"clear while a robot walks in and sits down: {w['hits'][:3]}")
        await page.click("#room-back")
        await wait(page, "() => window.__dbg.solo() === null && window.__dbg.props().room === null", label="props gone")
        back = res["back"] = await page.evaluate("() => window.__dbg.props()")
        check(failures, not back["floorMap"] and back["sceneChildren"] == floor["sceneChildren"],
              f"back on the floor nothing is left: children {floor['sceneChildren']} -> {back['sceneChildren']}, floor map {back['floorMap']}")
        # five times in and out: no growth
        mem = []
        for _ in range(5):
            await page.click(f".tag.room[data-set-project='{room_id}']")
            await wait(page, f"() => window.__dbg.props().room === '{room_id}'", label="in")
            await page.wait_for_timeout(300)
            await page.click("#room-back")
            await wait(page, "() => window.__dbg.props().room === null", label="out")
            await page.wait_for_timeout(300)
            mem.append((await page.evaluate("() => window.__dbg.props()"))["memory"])
        res["memory"] = mem
        check(failures, mem[-1]["geometries"] <= mem[0]["geometries"] and mem[-1]["textures"] <= mem[0]["textures"],
              f"geometries and textures do not grow over five visits: {mem}")
        # 11 robots in the room: no props, even up close; back to 10: they come back
        for i in range(4, 11):
            hook(SID.format(i), hook_event_name="SessionStart", source="startup")
        await wait(page, "() => window.__dbg.robots.filter((R) => R.def.room === window.__dbg.robots[0].def.room).length >= 11", timeout=30000, label="eleven robots")
        await page.click(f".tag.room[data-set-project='{room_id}']")
        await wait(page, f"() => window.__dbg.solo() === '{room_id}'", label="up close with eleven")
        await page.wait_for_timeout(1500)
        many = res["eleven"] = await page.evaluate("() => window.__dbg.props()")
        check(failures, many["room"] is None and not many["floorMap"], f"eleven robots: no props, no wood: {many}")
        # everyone at the seat the eleven-robot layout gave it first (a robot leaves only from its desk): the wait below then
        # covers the exit and the walk out alone
        await settled(page, "eleven seated before one leaves", timeout=60000)
        await page.evaluate(f"() => {{ window.__slowFrameMs = {SLOW_MS}; }}")   # the walk out, with frames 3 s apart
        t_ten = time.monotonic()
        hook(SID.format(10), hook_event_name="SessionEnd", reason="exit")
        await wait(page, f"() => window.__dbg.props().room === '{room_id}'", timeout=30000, label="ten again: props back")
        res["tenSec"] = round(time.monotonic() - t_ten, 1)
        await page.evaluate("() => { window.__slowFrameMs = 0; }")
        check(failures, res["tenSec"] < TEN_MAX_SEC, f"with frames {SLOW_MS} ms apart, the walk out takes about its real time: {res['tenSec']} s")
        await page.click("#room-back")
        await wait(page, "() => window.__dbg.props().room === null", label="out")
        for i in range(3, 10):
            hook(SID.format(i), hook_event_name="SessionEnd", reason="exit")
        await wait(page, "() => window.__dbg.robots.length <= 3", timeout=30000, label="back to three")
        # a hidden tab (rAF stopped, then minutes between two frames): a robot walking in is at its desk on the next
        # frame, along its path (no jump), and one walking out is gone
        hook(SID.format(11), hook_event_name="SessionStart", source="startup")
        await wait(page, "() => window.__dbg.robots.length === 4 && window.__dbg.robots.some((R) => R.path.length > 1)", label="a robot walking in")
        jumps0 = await page.evaluate("() => Object.fromEntries(window.__dbg.robots.map((R) => [R.def.id, R.jumps || 0]))")
        await page.evaluate(SEG_JS)       # the walls watcher of rooms.py, along the path (walkTrail)
        await page.evaluate(NEXT_FRAME)
        from0 = await page.evaluate("() => Object.fromEntries(window.__dbg.robots.map((R) => [R.def.id, [R.robot.root.position.x, R.robot.root.position.z]]))")
        await page.evaluate("() => { window.__walk.hits = []; window.__walk.steps = 0; }")
        await page.evaluate("() => window.__dbg.walkGap(300)")
        await page.evaluate(NEXT_FRAME)   # the frame after the gap: everyone has arrived in it
        await page.evaluate(NEXT_FRAME)   # and the watcher has sampled it
        # the whole walk in one frame, around the door's corners: never a wall hit along the path, though one straight
        # line from where it was to its seat may cross a wall (ticket 2026-10-20-jui-viz-e2e-wall-watch-joins-frames-not-the-path)
        res["gapWalls"] = await page.evaluate("""(from0) => ({ hits: window.__walk.hits.map((h) => ({ id: h.id, from: h.from, to: h.to })),
          straight: window.__dbg.robots.filter((R) => from0[R.def.id]).map((R) => ({ id: R.def.id,
            walls: window.__segHits(from0[R.def.id], [R.robot.root.position.x, R.robot.root.position.z], window.__dbg.walls() || [], 0.15).length })) })""", from0)
        check(failures, not res["gapWalls"]["hits"], f"after a gap of minutes, the walk in went along its path, through no wall: {res['gapWalls']}")
        res["arrivedInOneFrame"] = await page.evaluate("() => window.__dbg.robots.every((R) => !R.path.length)")
        check(failures, res["arrivedInOneFrame"], "after a gap of minutes, every walk ends in the next frame")
        gap = res["gapIn"] = await page.evaluate("() => window.__dbg.robots.map((R) => ({ id: R.def.id, at: [+R.robot.root.position.x.toFixed(3), +R.robot.root.position.z.toFixed(3)], seat: R.def.pos, jumps: R.jumps || 0 }))")
        check(failures, all(abs(g["at"][0] - g["seat"][0]) < 1e-3 and abs(g["at"][1] - g["seat"][1]) < 1e-3 and g["jumps"] == jumps0.get(g["id"], 0) for g in gap),
              f"after a gap of minutes: every robot at its seat, walked there (no jump): {gap}")
        hook(SID.format(11), hook_event_name="SessionEnd", reason="exit")
        await wait(page, "() => window.__dbg.robots.some((R) => R.path.length > 0)", label="the robot walking out")
        await page.evaluate("() => window.__dbg.walkGap(300)")
        await page.evaluate(NEXT_FRAME)
        res["goneInOneFrame"] = await page.evaluate("() => window.__dbg.robots.length === 3")
        check(failures, res["goneInOneFrame"], "after a gap of minutes, the robot walking out is gone in the next frame")
        await wait(page, "() => window.__dbg.robots.length === 3", label="the robot walking out gone")
        await page.wait_for_timeout(1500)
        await shots("after")
        # reduced motion: placed, not driven
        await page.emulate_media(reduced_motion="reduce")
        await page.reload()
        await ready(page)
        await wait(page, "() => window.__dbg.robots.length >= 3 && window.__dbg.robots.every((R) => !R.path.length)", timeout=30000, label="reloaded, seated")
        await page.click(f".tag.room[data-set-project='{room_id}']")
        await wait(page, f"() => window.__dbg.props().room === '{room_id}'", label="props, reduced motion")
        w = res["reduced"] = await page.evaluate(WATCH_JS, 3000)
        check(failures, w["moved"] == 0 and not w["hits"], f"reduced motion: the vacuum stays put: {w}")
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
    print(f"  {name}: {time.monotonic() - t0:.0f}s floor {res.get('framesFloor')} room {res.get('framesRoom')}", flush=True)
