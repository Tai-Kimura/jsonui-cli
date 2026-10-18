"""Breaks, end to end (requester, 10-19): a smoking booth and a vending machine in a room with few robots, and idle
robots that go for a cigarette or a drink and come back.

The real `jui viz serve` in a throwaway HOME on a free port, the real forward.py for the sessions. The times are
shortened through window.__dbg.brk / play (the real defaults stay in 40-scene.js).
- Where: for every room size the layout makes (1, 7 and 11+ robots on the floor, the one-room view's growth) and every
  door combination, the booth, the water server, the vending machine, the machine's customer and the two ways in keep
  clear of every desk the one-room view can place, the front aisle (the play spots, the entrance), the back and left
  doors, the walk in from the entrance, and each other (propsPlace, box against box). In the real rooms (one robot,
  three robots, a room with a back door) the built meshes against the real desks, and the vacuum, watched, never
  enters the booth's, the server's or the machine's box.
- A room alone (1 robot): it smokes in the booth (tag タバコ休憩, the robot card too, a cigarette, smoke under its cap)
  and comes back; it buys a drink (tag 飲み物を買いに, a can) and comes back; an instruction stops a break at once.
- A room of three: two smoke together, never three; one at the machine at most; never at a game, a nap or a bento at
  the same time; a phone call stops a break at once.
- 11 robots: no booth, no machine, nobody on a break; 10 again: back. The floor view: none.
- Reduced motion: the booth stands, nobody goes, no smoke.
- Screenshots up close and of the floor, light and dark, with robots smoking and one with a drink (`--jt` takes the
  "before" pictures from another tree). No console error, nothing requested outside the server.
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

ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
ONE = "e2e00000-0000-4000-8000-0000000001a0"            # alone in its room
MANY = [f"e2e00000-0000-4000-8000-0000000001b{k}" for k in range(3)]
EXTRA = [f"e2e00000-0000-4000-8000-0000000001c{k}" for k in range(8)]
ROW2 = [f"e2e00000-0000-4000-8000-0000000001d{k}" for k in range(2)]   # two more rooms: the 4th has a back door
CWD_ONE, CWD_MANY = "/work/brk-one", "/work/brk-many"
CWD_ROW2 = ["/work/brk-third", "/work/brk-fourth"]
NAMES = {ONE: "brk-one-a1", MANY[0]: "brk-many-b0"}
BODY = "BRK-CALL-77"

# propsPlace for every size and door combination against the zones it must keep clear of (see the docstring)
GEOM_JS = """() => {
  const D = window.__dbg, G = D.seatGeom(), S = G.SEAT, F = S.foot, out = { configs: 0, bad: [], sizes: [] };
  const hit = (a, b) => a[0] < b[1] - 1e-6 && b[0] < a[1] - 1e-6 && a[2] < b[3] - 1e-6 && b[2] < a[3] - 1e-6;
  const box = (x, z, r) => [x - r, x + r, z - r, z + r];
  for (const [bw, bd] of G.roomSize) {
    const w = +(bw * G.SOLO_GROW).toFixed(3), d = +(bd * G.SOLO_GROW).toFixed(3);
    out.sizes.push([w, d]);
    for (const back of [false, true]) for (const left of [false, true]) {
      const r = { x0: -w / 2, x1: w / 2, z0: -d / 2, z1: d / 2, doors: { back: back ? 'b' : null, left: left ? 'l' : null, front: true } };
      const P = D.propsPlace(r); out.configs++;
      const props = { booth: [P.booth.x0, P.booth.x1, P.booth.z0, P.booth.z1], server: box(P.server.x, P.server.z, P.server.half),
        vend: [P.vend.x0, P.vend.x1, P.vend.z0, P.vend.z1], customer: box(P.vend.spot[0], P.vend.spot[1], 0.5),
        boothWay: box(P.booth.way[0][0], P.booth.way[0][1], 0.5), vendWay: box(P.vend.way[0][0], P.vend.way[0][1], 0.5),
        gitDesk: P.git.rect, gitStand: box(P.git.stand[0], P.git.stand[1], 0.5),
        shredder: P.shredder.box, shredSpot: box(P.shredder.spot[0], P.shredder.spot[1], 0.5) };   // the shredder and its feeder's spot (10-19)   // the git box's desk and its stand (2.3.4)
      const sx0 = r.x0 + S.left + F.l + G.SEAT_SOLO.left, sx1 = r.x1 - S.aisleR - F.r - G.SEAT_SOLO.right, sz0 = r.z0 + S.back + F.b, sz1 = r.z1 - S.aisleF - F.f;
      const da = { leftZ: r.z1 + G.doorAt.leftZ, backX: r.x1 + G.doorAt.backX, frontX: r.x1 + G.doorAt.frontX }, h = G.DOOR_W / 2;
      const zones = { desks: [sx0 - Math.max(F.l, 0.5), sx1 + Math.max(F.r, 0.5), sz0 - F.b, sz1 + F.f], frontAisle: [r.x0, r.x1, r.z1 - S.aisleF, r.z1],
        play0: box((r.x0 + r.x1) / 2 - 0.8, r.z1 - 0.9, 0.6), play1: box((r.x0 + r.x1) / 2 + 0.8, r.z1 - 0.9, 0.6),
        entrance: [da.frontX - h, da.frontX + h, r.z1 - S.aisleF, r.z1] };
      if (back) zones.backDoor = [da.backX - h, da.backX + h, r.z0, r.z0 + 1.2];
      if (left) zones.leftDoor = [r.x0, r.x0 + 1.2, da.leftZ - h, da.leftZ + h];
      const E = [da.frontX, r.z1 - 0.7];
      for (const [cx, cz] of [[sx0, sz0], [sx1, sz0], [sx0, sz1], [sx1, sz1]]) for (let k = 0; k <= 24; k++)
        zones[`walkIn(${cx.toFixed(1)},${cz.toFixed(1)})#${k}`] = box(E[0] + (cx - E[0]) * k / 24, E[1] + (cz - E[1]) * k / 24, 0.5);
      const tag = `${w}x${d}${back ? ' back' : ''}${left ? ' left' : ''}`;
      for (const [pn, pb] of Object.entries(props)) {
        if (pb[0] < r.x0 - 1e-6 || pb[1] > r.x1 + 1e-6 || pb[2] < r.z0 - 1e-6 || pb[3] > r.z1 + 1e-6) out.bad.push(`${tag}: ${pn} outside the room`);
        for (const [zn, zb] of Object.entries(zones)) if (hit(pb, zb)) out.bad.push(`${tag}: ${pn} x ${zn}`);
      }
      const names = Object.keys(props);
      // the customer's spot and the point in front of it are one walk, by design: every other pair must be apart
      for (let i = 0; i < names.length; i++) for (let j = i + 1; j < names.length; j++) if (`${names[i]},${names[j]}` !== 'customer,vendWay' && hit(props[names[i]], props[names[j]])) out.bad.push(`${tag}: ${names[i]} x ${names[j]}`);
      // a robot's walk to the git box (straight, from any desk corner) passes no solid prop (2.3.4)
      for (const [cx, cz] of [[sx0, sz0], [sx1, sz0], [sx0, sz1], [sx1, sz1]]) for (let k = 0; k <= 24; k++) {
        const q = box(cx + (P.git.stand[0] - cx) * k / 24, cz + (P.git.stand[1] - cz) * k / 24, 0.35);
        for (const pn of ['booth', 'vend', 'server', 'gitDesk', 'shredder']) if (hit(q, props[pn])) { out.bad.push(`${tag}: the walk to the git box from (${cx.toFixed(1)},${cz.toFixed(1)}) x ${pn}`); break; }
      }
      // the requester's ruling (10-19): the booth in the back-left corner, the machine beside the server on its back line
      if (Math.abs(P.booth.x0 - r.x0) > 0.01 || Math.abs(P.booth.z0 - r.z0) > 0.01) out.bad.push(`${tag}: the booth is not in the back-left corner`);
      const gap = props.server[0] - props.vend[1];
      if (!(gap >= 0 && gap <= 0.2) || Math.abs(props.vend[2] - props.server[2]) > 0.2) out.bad.push(`${tag}: the machine is not beside the server (gap ${gap.toFixed(2)}, back ${props.vend[2].toFixed(2)} / ${props.server[2].toFixed(2)})`);
      // the booth's spots inside the booth, the customer in front of the machine
      for (const s of P.booth.spots) if (!(s[0] > P.booth.x0 && s[0] < P.booth.x1 && s[1] > P.booth.z0 && s[1] < P.booth.z1)) out.bad.push(`${tag}: a booth spot outside the booth`);
    }
  }
  return out;
}"""

# the built meshes against the real robots at their desks and against each other
REAL_JS = """() => {
  const b = window.__dbg.brk(), M = b.meshBoxes, out = { bad: [], desks: b.deskBoxes.length, boxes: M, backDoor: b.place && b.place.backDoor };
  const hit = (a, c) => a && c && a[0] < c[1] && c[0] < a[1] && a[2] < c[3] && c[2] < a[3];
  for (const [n, m] of Object.entries(M)) { if (!m) out.bad.push(`${n} not built`); for (const [id, d] of b.deskBoxes) if (hit(m, d)) out.bad.push(`${n} x desk of ${id}`); }
  if (hit(M.booth, M.vend) || hit(M.booth, M.server) || hit(M.vend, M.server)) out.bad.push('props overlap each other');
  // the ruling on the built meshes: the booth at the room's back-left corner, the machine beside the server, same back line
  const r = window.__dbg.room(window.__dbg.props().room);
  if (M.booth && (Math.abs(M.booth[0] - r.x0) > 0.01 || Math.abs(M.booth[2] - r.z0) > 0.01)) out.bad.push(`the booth is not in the back-left corner: ${M.booth} room ${r.x0},${r.z0}`);
  if (M.vend && M.server) { const gap = M.server[0] - M.vend[1]; if (!(gap >= 0 && gap <= 0.2) || Math.abs(M.vend[2] - M.server[2]) > 0.2) out.bad.push(`the machine is not beside the server: gap ${gap.toFixed(3)} back ${M.vend[2]} / ${M.server[2]}`); }
  return out;
}"""

# the vacuum against the three props' boxes (each grown by its radius), every 100 ms
VAC_JS = """(ms) => new Promise((done) => {
  const out = { samples: 0, hits: [] }, t0 = performance.now();
  const tick = () => {
    const p = window.__dbg.props(), M = window.__dbg.brk().meshBoxes;
    if (p.vac) { out.samples++; for (const [n, b] of Object.entries(M)) if (b && p.vac[0] > b[0] - p.radius && p.vac[0] < b[1] + p.radius && p.vac[1] > b[2] - p.radius && p.vac[1] < b[3] + p.radius) out.hits.push([n, p.vac]); }
    if (performance.now() - t0 < ms) setTimeout(tick, 100); else done(out);
  };
  tick();
})"""

FRAMES_JS = """(ms) => new Promise((done) => {
  const d = []; let last = performance.now(); const t0 = last;
  const f = (t) => { d.push(t - last); last = t; if (t - t0 < ms) requestAnimationFrame(f); else { d.sort((a, b) => a - b);
    done({ n: d.length, mean: +(d.reduce((a, b) => a + b, 0) / d.length).toFixed(1), p95: +d[Math.floor(d.length * 0.95)].toFixed(1) }); } };
  requestAnimationFrame(f);
})"""

BRK = "() => window.__dbg.brk()"


def check(failures, cond, text):
    if not cond:
        failures.append(f"breaks: {text}")


async def wait(page, js, timeout=20000, label=""):
    try:
        await page.wait_for_function(js, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def run_breaks(pw, out, failures, jt=None, shots_only=False):
    from run import free_port
    name = "breaks-before" if shots_only else "breaks"
    out = pathlib.Path(out) / name
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(jt) if jt else pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    # session files and transcripts for the two that make a phone call (as calls.py)
    sessions = home / ".claude" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    transcripts = {}
    for n, (sid, cwd) in enumerate(((ONE, CWD_ONE), (MANY[0], CWD_MANY))):
        proj = home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", cwd)
        proj.mkdir(parents=True, exist_ok=True)
        transcripts[sid] = proj / f"{sid}.jsonl"
        transcripts[sid].write_text(json.dumps({"type": "user", "timestamp": "2026-10-19T09:00:00Z", "message": {"role": "user", "content": "start"}}) + "\n")
        (sessions / f"{91000 + n}.json").write_text(json.dumps({
            "pid": 91000 + n, "sessionId": sid, "cwd": cwd, "name": NAMES[sid], "nameSource": "derived", "status": "idle",
            "messagingSocketPath": f"/tmp/e2e/{sid[-2:]}.sock", "entrypoint": "cli"}))
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def hook(sid, cwd, **payload):
        body = {"session_id": sid, "cwd": cwd, "permission_mode": "default", **payload}
        if sid in transcripts:
            body["transcript_path"] = str(transcripts[sid])
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(),
                       capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)

    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    t0 = time.monotonic()
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
        watch = Watch(origin=url)
        page = await new_page(browser, watch, name, **DESKTOP)
        await page.emulate_media(color_scheme="light", reduced_motion="no-preference")
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", label="connected")
        hook(ONE, CWD_ONE, hook_event_name="SessionStart", source="startup")
        await wait(page, "() => window.__dbg.robots.length >= 1", label="one robot")
        for sid in MANY:
            hook(sid, CWD_MANY, hook_event_name="SessionStart", source="startup")
        await wait(page, "() => window.__dbg.robots.length >= 4", label="four robots")
        await wait(page, "() => window.__dbg.robots.every((R) => !R.path.length)", timeout=30000, label="seated")
        rooms = await page.evaluate("() => { const m = {}; for (const R of window.__dbg.robots) (m[R.def.room] = m[R.def.room] || []).push(R.def.id); return m; }")
        one_room = next(k for k, v in rooms.items() if len(v) == 1)
        many_room = next(k for k, v in rooms.items() if len(v) == 3)
        one_id = rooms[one_room][0]
        has_brk = await page.evaluate("() => typeof window.__dbg.brk === 'function'")
        if not shots_only:
            await page.evaluate("() => window.__dbg.play({ p: 0, solo: { p: 0 } })")   # no game, nap or bento unless an arm asks
            await page.evaluate("() => window.__dbg.brk({ p: { smoke: 0, vend: 0 } })")

        async def solo(room):
            await page.click(f".tag.room[data-set-project='{room}']")
            await wait(page, f"() => window.__dbg.solo() === '{room}' && window.__dbg.props().room === '{room}'", label=f"{room} up close with its props")
            await wait(page, "() => window.__dbg.robots.every((R) => !R.path.length)", timeout=30000, label="seated up close")

        async def back():
            await page.click("#room-back")
            await wait(page, "() => window.__dbg.solo() === null", label="back to the floor")

        async def shoot(tag, room):
            for scheme in ("light", "dark"):
                await page.emulate_media(color_scheme=scheme)
                await page.wait_for_timeout(1200)
                if has_brk and not shots_only:
                    try:   # the theme builds the props again: wait for the smoke to be out again
                        await page.wait_for_function("() => window.__dbg.brk().smoke >= 5", timeout=8000, polling=100)
                    except Exception:
                        pass
                await page.screenshot(path=str(out / f"{tag}-room-{scheme}.png"))
            await back()
            for scheme in ("light", "dark"):
                await page.emulate_media(color_scheme=scheme)
                await page.wait_for_timeout(1200)
                await page.screenshot(path=str(out / f"{tag}-floor-{scheme}.png"))
            await page.emulate_media(color_scheme="light")

        if shots_only or not has_brk:
            # the "before" pictures: the same rooms up close and the floor, nothing to drive
            await solo(many_room)
            await shoot("before", many_room)
            return

        # ---- where: every size and door combination (propsPlace) ----
        g = res["geometry"] = await page.evaluate(GEOM_JS)
        check(failures, g["configs"] == 12 and not g["bad"], f"no prop overlaps a desk, a door, the aisles, the play spots or another prop: {g['configs']} configs, {g['bad'][:6]}")
        floor = await page.evaluate(BRK)
        check(failures, floor["place"] is None and not floor["built"]["booth"] and not floor["built"]["vend"], f"the floor view: no booth, no machine: {floor['built']}")

        # ---- a room alone (1 robot) ----
        await solo(one_room)
        r = res["realOne"] = await page.evaluate(REAL_JS)
        check(failures, not r["bad"] and r["desks"] == 1, f"1 robot: the built props clear of the desk and each other: {r}")
        res["framesRoom"] = await page.evaluate(FRAMES_JS, 3000)
        v = res["vacOne"] = await page.evaluate(VAC_JS, 6000)
        check(failures, v["samples"] >= 30 and not v["hits"], f"the vacuum keeps clear of the booth, the server and the machine: {v['samples']} samples {v['hits'][:3]}")
        await page.evaluate("() => window.__dbg.play({ idleMs: 1000 })")
        await page.evaluate("() => window.__dbg.brk({ p: { smoke: 1, vend: 0 }, smokeMinSec: 10, smokeMaxSec: 10, restMinSec: 0, restMaxSec: 0 })")
        await wait(page, f"() => window.__dbg.brk().robots.some((x) => x.id === '{one_id}' && x.kind === 'smoke' && x.at)", timeout=40000, label="the lone robot smokes")
        await page.wait_for_timeout(3500)          # past the first puff: the smoke out of the mouth
        b = res["oneSmoke"] = await page.evaluate(BRK)
        me = next(x for x in b["robots"] if x["id"] == one_id)
        bx = b["place"]["booth"]
        check(failures, me["tag"] == "タバコ休憩" and me["hand"] == "smoke" and not me["desk"] and me["lamp"] == "idle",
              f"1 robot smokes: the tag タバコ休憩, a cigarette, no desk, the idle lamp: {me}")
        check(failures, bx["x0"] < me["x"] < bx["x1"] and bx["z0"] < me["z"] < bx["z1"], f"it is in the booth: {me} {bx}")
        check(failures, 0 < b["smoke"] <= b["smokeMax"] <= 10, f"smoke, under its cap: {b['smoke']} of {b['smokeMax']}")
        await page.evaluate(f"() => window.__dbg.openRobot('{one_id}')")
        try:
            await page.wait_for_function("() => { const e = document.querySelector('[data-rb-cond]'); return e && !e.hidden && e.textContent.includes('タバコ休憩'); }", timeout=6000, polling=200)
        except Exception:
            pass
        cond = res["cardSmoke"] = await page.evaluate("() => { const e = document.querySelector('[data-rb-cond]'); return e && !e.hidden ? e.textContent : ''; }")
        check(failures, "タバコ休憩" in cond, f"the robot card says it too: {cond!r}")
        await page.click("#rb-close")
        await page.wait_for_timeout(1200)
        try:   # the picture right after a puff, while the smoke is out
            await page.wait_for_function("() => window.__dbg.brk().smoke >= 5", timeout=8000, polling=100)
        except Exception:
            pass
        await page.screenshot(path=str(out / "one-smoking.png"))
        await wait(page, f"() => window.__dbg.brk().robots.some((x) => x.id === '{one_id}' && !x.kind && !x.back && x.path === 0 && x.x === x.seat[0] && x.z === x.seat[1])",
                   timeout=40000, label="back at its desk after smoking")
        e = (await page.evaluate(BRK))["ends"][-1]
        check(failures, e["kind"] == "smoke" and e["reason"] == "done" and e["atSec"] >= 9.5, f"it smoked its whole time: {e}")
        # a drink
        await page.evaluate("() => window.__dbg.brk({ p: { smoke: 0, vend: 1 }, drinkMinSec: 6, drinkMaxSec: 6, restMinSec: 0, restMaxSec: 0 })")
        await wait(page, f"() => window.__dbg.brk().robots.some((x) => x.id === '{one_id}' && x.kind === 'vend' && x.at)", timeout=40000, label="the lone robot at the machine")
        b = await page.evaluate(BRK)
        me = next(x for x in b["robots"] if x["id"] == one_id)
        check(failures, me["tag"] == "飲み物を買いに" and not me["desk"], f"1 robot at the machine: the tag 飲み物を買いに: {me}")
        await page.wait_for_timeout(3000)          # past buySec: the can in its hand
        b = res["oneDrink"] = await page.evaluate(BRK)
        me = next(x for x in b["robots"] if x["id"] == one_id)
        sp = b["place"]["vend"]["spot"]
        check(failures, me["hand"] == "vend" and abs(me["x"] - sp[0]) < 0.05 and abs(me["z"] - sp[1]) < 0.05, f"a can in its hand, in front of the machine: {me} spot {sp}")
        # the machine is taller than the robot standing in front of it (requester, 10-19), both measured in the scene
        hv = b["heights"]
        rob = next((h for i, h, desk in hv["robots"] if i == one_id), None)
        res["heights"] = {"vend": hv["vend"], "robot": rob}
        check(failures, hv["vend"] and rob and (hv["vend"][1] - hv["vend"][0]) > (rob[1] - rob[0]) + 0.1,
              f"the vending machine is clearly taller than a robot: machine {hv['vend']} robot {rob}")
        await page.screenshot(path=str(out / "one-drink.png"))
        await wait(page, f"() => window.__dbg.brk().robots.some((x) => x.id === '{one_id}' && !x.kind && !x.back && x.path === 0 && x.x === x.seat[0] && x.z === x.seat[1])",
                   timeout=40000, label="back at its desk after the drink")
        e = (await page.evaluate(BRK))["ends"][-1]
        check(failures, e["kind"] == "vend" and e["reason"] == "done", f"it drank its whole time: {e}")
        # an instruction stops a break at once
        await page.evaluate("() => window.__dbg.brk({ p: { smoke: 1, vend: 0 }, smokeMinSec: 60, smokeMaxSec: 60 })")
        await wait(page, f"() => window.__dbg.brk().robots.some((x) => x.id === '{one_id}' && x.kind === 'smoke' && x.at)", timeout=40000, label="smoking before the instruction")
        await page.evaluate("() => window.__dbg.brk({ p: { smoke: 0, vend: 0 } })")
        hook(ONE, CWD_ONE, hook_event_name="UserPromptSubmit", prompt="次の作業")
        t1 = time.monotonic()
        await wait(page, f"() => window.__dbg.brk().robots.some((x) => x.id === '{one_id}' && !x.kind && x.back)", timeout=5000, label="the break stops on the instruction")
        res["stopSec"] = round(time.monotonic() - t1, 1)
        b = res["stopped"] = await page.evaluate(BRK)
        e = b["ends"][-1]
        me = next(x for x in b["robots"] if x["id"] == one_id)
        check(failures, e["reason"] == "updated" and me["tag"] == "" and me["hand"] is None, f"stopped by the instruction, no tag, nothing in its hand: {e} {me}")
        await wait(page, f"() => window.__dbg.brk().robots.some((x) => x.id === '{one_id}' && !x.back && x.x === x.seat[0] && x.z === x.seat[1])", timeout=20000, label="back at its desk")
        hook(ONE, CWD_ONE, hook_event_name="Stop")
        # the same at the machine, once the turn's end has settled (完了, then idle again three seconds later)
        await page.wait_for_timeout(4500)
        await page.evaluate("() => window.__dbg.brk({ p: { smoke: 0, vend: 1 }, drinkMinSec: 60, drinkMaxSec: 60, restMinSec: 0, restMaxSec: 0 })")
        await wait(page, f"() => window.__dbg.brk().robots.some((x) => x.id === '{one_id}' && x.kind === 'vend' && x.at)", timeout=40000, label="at the machine before the instruction")
        await page.evaluate("() => window.__dbg.brk({ p: { smoke: 0, vend: 0 } })")
        hook(ONE, CWD_ONE, hook_event_name="UserPromptSubmit", prompt="次の作業")
        t1 = time.monotonic()
        await wait(page, f"() => window.__dbg.brk().robots.some((x) => x.id === '{one_id}' && !x.kind && x.back)", timeout=5000, label="the drink stops on the instruction")
        res["vendStopSec"] = round(time.monotonic() - t1, 1)
        e = (await page.evaluate(BRK))["ends"][-1]
        check(failures, e["kind"] == "vend" and e["reason"] == "updated", f"the drink stopped by the instruction: {e}")
        await wait(page, f"() => window.__dbg.brk().robots.some((x) => x.id === '{one_id}' && !x.back && x.x === x.seat[0] && x.z === x.seat[1])", timeout=20000, label="back at its desk")
        hook(ONE, CWD_ONE, hook_event_name="Stop")
        await back()

        # ---- a room of three ----
        await solo(many_room)
        r = res["realMany"] = await page.evaluate(REAL_JS)
        check(failures, not r["bad"] and r["desks"] == 3, f"3 robots: the built props clear of the desks and each other: {r}")
        await page.evaluate("() => window.__dbg.brk({ p: { smoke: 1, vend: 0 }, joinP: 1, smokeMinSec: 50, smokeMaxSec: 50, restMinSec: 0, restMaxSec: 0 })")
        await wait(page, f"() => window.__dbg.brk().robots.filter((x) => x.room === '{many_room}' && x.kind === 'smoke' && x.at).length >= 2",
                   timeout=40000, label="two in the booth")
        # games, naps and bentos may start now too: never on a robot that is on a break
        await page.evaluate("() => window.__dbg.play({ p: 1, minSec: 2, maxSec: 2, solo: { p: 1, minSec: 2, maxSec: 2 } })")
        seen = []
        for _ in range(8):
            seen.append(await page.evaluate(BRK))
            await page.wait_for_timeout(500)
        await page.evaluate("() => window.__dbg.play({ p: 0, solo: { p: 0 }, endAll: true, restMinSec: 0, restMaxSec: 0 })")
        b = res["manySmoke"] = seen[0]
        smokers = [x for x in b["robots"] if x["room"] == many_room and x["kind"] == "smoke" and x["at"]]
        check(failures, len(smokers) == 2 and all(x["tag"] == "タバコ休憩" for x in smokers), f"two smoke together: {[(x['id'], x['kind'], x['at']) for x in b['robots']]}")
        both = [x for s in seen for x in s["robots"] if x["kind"] and (x["play"] or x["solo"])]
        check(failures, not both, f"never a break and a game, a nap or a bento at once: {both[:3]}")
        most = max(sum(1 for x in s["robots"] if x["kind"] == "smoke") for s in seen)
        check(failures, most <= 2, f"never more than two in the booth: {most}")
        await page.wait_for_timeout(1500)
        res["framesSmoking"] = await page.evaluate(FRAMES_JS, 3000)
        # the third one buys a drink meanwhile (the picture: two smoking, one with a drink)
        await wait(page, "() => window.__dbg.play().list.length === 0 && window.__dbg.play().robots.every((x) => !x.solo)", timeout=20000, label="no game, no nap")
        await page.evaluate("() => window.__dbg.brk({ p: { smoke: 0, vend: 1 }, drinkMinSec: 20, drinkMaxSec: 20 })")
        await wait(page, "() => window.__dbg.brk().robots.some((x) => x.kind === 'vend' && x.at)", timeout=20000, label="the third at the machine")
        await page.wait_for_timeout(2600)
        b = await page.evaluate(BRK)
        check(failures, sum(1 for x in b["robots"] if x["kind"] == "vend") <= 1, f"one at the machine at most: {b['robots']}")
        if sum(1 for x in b["robots"] if x["kind"] == "smoke" and x["at"]) >= 2:
            try:
                await page.wait_for_function("() => window.__dbg.brk().smoke >= 6", timeout=8000, polling=100)
            except Exception:
                pass
            await shoot("after", many_room)
            await solo(many_room)
        else:
            failures.append("breaks: the two smokers were gone before the pictures (raise smokeMinSec)")
        # a phone call stops a break at once: MANY[0] at the booth, ONE calls it
        await page.evaluate("() => window.__dbg.brk({ p: { smoke: 0, vend: 0 }, endAll: true })")
        await wait(page, "() => window.__dbg.brk().robots.every((x) => !x.kind && !x.back && x.path === 0)", timeout=60000, label="everyone back")
        callee = await page.evaluate(f"() => window.__dbg.robots.find((R) => R.def.realId === '{MANY[0]}' || R.def.sessionId === '{MANY[0]}')?.def.id || null")
        if not callee:
            callee = await page.evaluate("(room) => window.__dbg.robots.filter((R) => R.def.room === room).map((R) => R.def.id).sort()[0]", many_room)
        res["callee"] = callee
        await page.evaluate("() => window.__dbg.brk({ p: { smoke: 1, vend: 0 }, joinP: 0, smokeMinSec: 60, smokeMaxSec: 60 })")
        await wait(page, f"() => window.__dbg.brk().robots.some((x) => x.id === '{callee}' && x.kind === 'smoke' && x.at)", timeout=60000, label="the callee smokes")
        await page.evaluate("() => window.__dbg.brk({ p: { smoke: 0, vend: 0 } })")
        await page.wait_for_timeout(2500)
        hook(ONE, CWD_ONE, hook_event_name="PreToolUse", tool_name="SendMessage", tool_use_id="toolu_brk1",
             tool_input={"to": NAMES[MANY[0]], "summary": "x", "message": BODY})
        t2 = time.monotonic()
        await wait(page, f"() => window.__dbg.brk().robots.some((x) => x.id === '{callee}' && !x.kind)", timeout=8000, label="the call stops the break")
        res["callStopSec"] = round(time.monotonic() - t2, 1)
        e = (await page.evaluate(BRK))["ends"][-1]
        check(failures, e["who"] == callee and e["reason"] == "call", f"stopped by the call: {e}")
        hook(ONE, CWD_ONE, hook_event_name="PostToolUse", tool_name="SendMessage", tool_use_id="toolu_brk1",
             tool_input={"to": NAMES[MANY[0]], "message": BODY}, tool_response={"success": True})
        hook(ONE, CWD_ONE, hook_event_name="Stop")

        # ---- 11 robots: none; 10: back ----
        await page.evaluate("() => window.__dbg.brk({ p: { smoke: 1, vend: 0 }, joinP: 1, smokeMinSec: 120, smokeMaxSec: 120 })")
        await wait(page, "() => window.__dbg.brk().robots.some((x) => x.kind === 'smoke' && x.at)", timeout=60000, label="someone smokes before the room fills")
        for sid in EXTRA:
            hook(sid, CWD_MANY, hook_event_name="SessionStart", source="startup")
        await wait(page, f"() => window.__dbg.robots.filter((R) => R.def.room === '{many_room}').length >= 11", timeout=30000, label="eleven robots")
        await page.wait_for_timeout(2500)
        b = res["eleven"] = await page.evaluate(BRK)
        check(failures, b["place"] is None and not b["built"]["booth"] and not b["built"]["vend"] and not any(x["kind"] for x in b["robots"]),
              f"eleven robots: no booth, no machine, nobody on a break: {b['built']} {[x for x in b['robots'] if x['kind']]}")
        e = [x for x in b["ends"] if x["reason"] in ("relaid", "props")]
        check(failures, bool(e), f"the smoker went back when the room filled: {b['ends'][-3:]}")
        hook(EXTRA[-1], CWD_MANY, hook_event_name="SessionEnd", reason="exit")
        await wait(page, "() => window.__dbg.brk().built.booth && window.__dbg.brk().built.vend", timeout=30000, label="ten again: booth and machine back")
        r = res["realTen"] = await page.evaluate(REAL_JS)
        await page.evaluate("() => window.__dbg.brk({ p: { smoke: 0, vend: 0 }, endAll: true })")
        await back()
        for sid in EXTRA[:-1]:
            hook(sid, CWD_MANY, hook_event_name="SessionEnd", reason="exit")

        # ---- a room with a back door (the 4th room on a floor of three columns) ----
        for sid, cwd in zip(ROW2, CWD_ROW2):
            hook(sid, cwd, hook_event_name="SessionStart", source="startup")
        await wait(page, "() => window.__dbg.robots.length <= 6 && window.__dbg.robots.length >= 6", timeout=40000, label="six robots in four rooms")
        await wait(page, "() => window.__dbg.robots.every((R) => !R.path.length)", timeout=30000, label="seated")
        bd = await page.evaluate("() => { const ids = [...new Set(window.__dbg.robots.map((R) => R.def.room))]; return ids.find((id) => { const r = window.__dbg.room(id); return r && r.doors && r.doors.back; }) || null; }")
        check(failures, bool(bd), "a room with a back door")
        if bd:
            await solo(bd)
            r = res["realBackDoor"] = await page.evaluate(REAL_JS)
            check(failures, r["backDoor"] and not r["bad"], f"a back-door room: the server and the machine in front of the door, clear of the desks: {r}")
            rm = await page.evaluate(f"() => window.__dbg.room('{bd}')")
            sv = r["boxes"]["server"]
            check(failures, sv and sv[2] >= rm["z0"] + 1.2, f"the server keeps the back door's apron clear: {sv} {rm}")
            await back()

        # ---- reduced motion: the booth stands, nobody goes ----
        await page.emulate_media(reduced_motion="reduce")
        await page.reload()
        await ready(page)
        await wait(page, "() => window.__dbg.robots.length >= 6 && window.__dbg.robots.every((R) => !R.path.length)", timeout=30000, label="reloaded, seated")
        await solo(one_room)
        await page.evaluate("() => window.__dbg.play({ idleMs: 1000, p: 0, solo: { p: 0 } })")
        await page.evaluate("() => window.__dbg.brk({ p: { smoke: 1, vend: 1 }, restMinSec: 0, restMaxSec: 0 })")
        await page.wait_for_timeout(4000)
        b = res["reduced"] = await page.evaluate(BRK)
        check(failures, b["built"]["booth"] and not any(x["kind"] for x in b["robots"]) and b["smoke"] == 0, f"reduced motion: the booth stands, nobody goes, no smoke: {b['built']} {b['smoke']}")
        await page.close()
        for line in watch.console:
            failures.append(f"breaks: console: {line}")
        for u in watch.foreign:
            failures.append(f"breaks: request outside the server: {u}")
        res["console"] = len(watch.console)
    except Exception as e:
        failures.append(f"breaks: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        await browser.close()
        srv.terminate()  # our own child (started above)
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        (out / "result.json").write_text(dump(res) + "\n")
    print(f"  {name}: {time.monotonic() - t0:.0f}s room {res.get('framesRoom')} smoking {res.get('framesSmoking')} stop {res.get('stopSec')}s call {res.get('callStopSec')}s", flush=True)
