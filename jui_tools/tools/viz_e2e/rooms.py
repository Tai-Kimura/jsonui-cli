"""Rooms, doors, desks and the one-room view on the real `jui viz serve --replay` (requester, 10-18).

Fed hooks.rooms_doors(): four rooms on one floor, robots moving between the back and the front row, prompts and
Stops (the turn cards), a permission request. Checks:
  * no robot ever walks through a wall: every step between two frames (a segment, so a slow frame rate cannot step
    over a wall) is tested against the wall pieces the page builds (__dbg.walls(), door gaps cut out). The same test
    must catch a straight line through a wall and pass a line through a door (the controls, in the same page).
  * robots that changed rooms went through a door gap;
  * desks do not overlap, and a reload puts every desk back where it was; a robot leaving moves no other desk —
    also in a fresh browser (no remembered desks) when nobody left: the seeded draw alone;
  * picking a room shows it alone and wider, the way back returns to the floor;
  * the turn cards: a working card per prompt (the wrapper stripped), done at Stop, 待ち while a permission waits;
  * dark mode and 390 px with no horizontal scroll; no console error.
"""

from __future__ import annotations

import json
import pathlib
import time

import hooks
from common import DESKTOP, LAUNCH_ARGS, PHONE, Watch, dump, new_page, ready

# A segment against the wall rectangles (each grown by PAD, the robot's half width): Liang–Barsky clipping.
SEG_JS = """
window.__segHits = (a, b, walls, pad) => {
  const hits = [];
  for (const w of walls) {
    const x0 = w.x0 - pad, x1 = w.x1 + pad, z0 = w.z0 - pad, z1 = w.z1 + pad;
    const dx = b[0] - a[0], dz = b[1] - a[1];
    let t0 = 0, t1 = 1, ok = true;
    for (const [p, q] of [[-dx, a[0] - x0], [dx, x1 - a[0]], [-dz, a[1] - z0], [dz, z1 - a[1]]]) {
      if (p === 0) { if (q < 0) { ok = false; break; } continue; }
      const r = q / p;
      if (p < 0) { if (r > t1) { ok = false; break; } if (r > t0) t0 = r; }
      else { if (r < t0) { ok = false; break; } if (r < t1) t1 = r; }
    }
    if (ok && t0 <= t1) hits.push(w);
  }
  return hits;
};
window.__walk = { hits: [], steps: 0, rooms: {}, doorPass: {} };
const PAD = 0.15;
const last = new Map();
function sample() {
  const walls = window.__dbg.walls() || [];
  for (const R of window.__dbg.robots) {
    const p = R.robot.root.position, here = [p.x, p.z], id = R.def.id;
    const prev = last.get(R);
    if (prev && prev.jumps === (R.jumps || 0)) {
      if (Math.hypot(here[0] - prev.at[0], here[1] - prev.at[1]) > 1e-6) {
        window.__walk.steps += 1;
        for (const w of window.__segHits(prev.at, here, walls, PAD)) window.__walk.hits.push({ id, from: prev.at, to: here, wall: w });
      }
    }
    last.set(R, { at: here, jumps: R.jumps || 0 });
    const room = (window.__dbg.walls && (() => { for (const k of Object.keys(window.__dbg.live3d().rooms)) { const r = window.__dbg.room(k); if (r && r.shown && p.x > r.x0 && p.x < r.x1 && p.z > r.z0 && p.z < r.z1) return k; } return null; })());
    const seen = window.__walk.rooms[id] || (window.__walk.rooms[id] = []);
    if (room && seen[seen.length - 1] !== room) seen.push(room);
  }
  requestAnimationFrame(sample);
}
requestAnimationFrame(sample);
"""


def check(failures, cond, text):
    if not cond:
        failures.append(f"rooms: {text}")


async def wait(page, js, timeout=60000, label=""):
    try:
        await page.wait_for_function(js, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


# Desks in room coordinates (from the room's back-left corner): rooms can take other slots on the floor after a reload.
SEATS_JS = """() => { const s = window.__dbg.seats(); return Object.fromEntries(window.__dbg.robots.map((R) => [R.def.id, s[R.def.id] ? [s[R.def.id].room, s[R.def.id].dx, s[R.def.id].dz, !!s[R.def.id].standing] : null])); }"""
SETTLED_JS = """() => window.__dbg.robots.length > 0 && window.__dbg.robots.every((R) => !R.path.length)"""
NO_HSCROLL_JS = """() => document.documentElement.scrollWidth <= document.documentElement.clientWidth"""


def desks_clear(seats: dict) -> list:
    """Pairs of desks in one room that overlap (the page's SEAT.foot and its smallest gap)."""
    bad = []
    by_room: dict = {}
    for rid, s in seats.items():
        if not s.get("standing"):
            by_room.setdefault(s["room"], []).append((rid, s["dx"], s["dz"]))
    for room, ds in by_room.items():
        for i in range(len(ds)):
            for j in range(i + 1, len(ds)):
                a, b = ds[i], ds[j]
                if abs(a[1] - b[1]) < 1.2 + 0.3 and abs(a[2] - b[2]) < 1.4 + 0.3:
                    bad.append((room, a[0], b[0]))
    return bad


async def run_rooms(pw, out, failures, RealServer):
    out = pathlib.Path(out) / "rooms"
    out.mkdir(parents=True, exist_ok=True)
    rec = hooks.write(hooks.rooms_doors(), out / "rooms.record.jsonl")
    res: dict = {}
    t0 = time.monotonic()
    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    srv = None
    try:
        srv = RealServer(rec, out / "home", speed=1.0)
        watch = Watch(origin=srv.url)
        page = await new_page(browser, watch, "rooms", **DESKTOP)
        await page.goto(srv.url + "/")
        await ready(page)
        await page.evaluate(SEG_JS)
        await wait(page, "() => document.querySelectorAll('.tag.room').length === 4", label="four rooms")
        early = await page.evaluate(SEATS_JS)
        # 05 back to jsonui-cli/ (20 s) is the last move; then everyone sits
        await wait(page, """() => { const R = window.__dbg.robots.find((x) => x.def.id === '05'); return R && window.__walk.rooms['05'] && window.__walk.rooms['05'].length >= 3 && !R.path.length; }""", label="05 walked out and back")
        await wait(page, "() => !window.__dbg.robots.some((x) => x.def.id === '08') && window.__dbg.robots.some((x) => x.def.id === '0a')", label="08 left, 0a came in")
        await wait(page, SETTLED_JS, label="everyone seated")
        walk = await page.evaluate("() => window.__walk")
        res["walk"] = {"steps": walk["steps"], "hits": walk["hits"][:5], "rooms": {k: v for k, v in walk["rooms"].items() if len(v) > 1}}
        check(failures, walk["steps"] > 50, f"the wall check saw robots walk ({walk['steps']} steps)")
        check(failures, not walk["hits"], f"a robot walked through a wall: {walk['hits'][:3]}")
        moved = {k: v for k, v in walk["rooms"].items() if len(v) > 1}
        check(failures, {"04", "05"} <= set(moved), f"04 and 05 changed rooms on foot: {moved}")
        # shop-app/ (back row, left end) has no entrance of its own: leaving and coming in pass through a room next to
        # it that has one (the room in front or the one to the right; both are two doors away)
        home_room = walk["rooms"].get("08", [None])[0]
        entr = await page.evaluate("""() => Object.fromEntries(Object.keys(window.__dbg.live3d().rooms).map((k) => [k, !!(window.__dbg.room(k).doors || {}).front]))""")
        t08, t0a = walk["rooms"].get("08", []), walk["rooms"].get("0a", [])
        res["throughNext"] = {"home": home_room, "hasEntrance": entr, "08": t08, "0a": t0a}
        check(failures, home_room and not entr.get(home_room) and len(t08) == 2 and entr.get(t08[-1]) and len(t0a) == 2 and t0a[-1] == home_room and entr.get(t0a[0]),
              f"08 went out and 0a came in through the room next door: {res['throughNext']}")
        # the controls: the same test on a line through a wall, and on a line through a door
        ctl = await page.evaluate("""() => {
          const walls = window.__dbg.walls(), ids = Object.keys(window.__dbg.live3d().rooms), rs = ids.map((k) => [k, window.__dbg.room(k)]);
          const front = rs.find(([, r]) => r.doors && r.doors.back), back = front && window.__dbg.room(front[1].doors.back);
          const c = (r) => [(r.x0 + r.x1) / 2, (r.z0 + r.z1) / 2];
          const bx = front[1].x1 - 1.4;
          return { through: window.__segHits(c(front[1]), c(back), walls, 0.15).length,
                   door: window.__segHits([bx, front[1].z0 + 0.7], [bx, back.z1 - 0.7], walls, 0.15).length,
                   wallsN: walls.length };
        }""")
        res["controls"] = ctl
        check(failures, ctl["through"] > 0 and ctl["door"] == 0, f"the wall test catches a wall and passes a door: {ctl}")
        await page.screenshot(path=str(out / "floor.png"))

        # desks: clear of each other; a robot leaving the room moved no other desk; a reload puts them back
        seats = await page.evaluate("() => window.__dbg.seats()")
        res["overlap"] = desks_clear(seats)
        check(failures, not res["overlap"], f"desks overlap: {res['overlap']}")
        check(failures, desks_clear({"a": {"room": "r", "dx": 2, "dz": 2}, "b": {"room": "r", "dx": 2.5, "dz": 2.4}}) != [], "the overlap test catches an overlap")
        settled = await page.evaluate(SEATS_JS)
        stayed = [k for k in early if k in settled and early[k][0] == settled[k][0] and k not in moved]
        res["stayed"] = {k: [early[k], settled[k]] for k in stayed if early[k] != settled[k]}
        check(failures, len(stayed) >= 5 and not res["stayed"], f"desks did not move while robots came and went: {res['stayed']} ({len(stayed)} compared)")
        await page.reload()
        await ready(page)
        await wait(page, "() => document.querySelectorAll('.tag.room').length === 4", label="four rooms after the reload")
        await wait(page, SETTLED_JS + " && window.__dbg.robots.length === " + str(len(settled)), label="everyone seated after the reload")
        again = await page.evaluate(SEATS_JS)
        res["reload"] = {k: [settled.get(k), again.get(k)] for k in set(settled) | set(again) if settled.get(k) != again.get(k)}
        check(failures, not res["reload"], f"a reload put desks elsewhere: {res['reload']}")
        # a fresh browser (nothing remembered): in the rooms nobody left, the seeded draw alone gives the same desks
        left_from = {room for v in moved.values() for room in v[:-1]}
        fresh = await new_page(browser, watch, "rooms-fresh", **DESKTOP)
        await fresh.goto(srv.url + "/")
        await ready(fresh)
        await wait(fresh, SETTLED_JS + " && window.__dbg.robots.length === " + str(len(settled)), label="fresh page seated")
        anew = await fresh.evaluate(SEATS_JS)
        await fresh.close()
        same_rooms = [k for k, v in settled.items() if v and v[0] not in left_from]
        res["fresh"] = {"compared": len(same_rooms), "diff": {k: [settled[k], anew.get(k)] for k in same_rooms if settled[k] != anew.get(k)}}
        check(failures, len(same_rooms) >= 3 and not res["fresh"]["diff"], f"the seeded draw alone puts the desks back: {res['fresh']}")

        # the turn cards
        cards = await page.evaluate("""() => window.__dbg.model().tasks.filter((x) => x.source === 'turn').map((x) => [x.list, x.subject, x.col])""")
        res["turns"] = cards
        by = {c[0]: c for c in cards}
        check(failures, len(cards) >= 9 and by.get("03", [None, ""])[1] == "画面 3 を仕上げて", f"one card per prompt, the wrapper stripped: {cards[:3]}")
        check(failures, by.get("01", [0, 0, ""])[2] == "done" and by.get("02", [0, 0, ""])[2] == "wait" and by.get("00", [0, 0, ""])[2] == "doing",
              f"Stop → done, a permission → 待ち, working → 作業中: {[by.get(k) for k in ('00', '01', '02')]}")
        await page.click("#btn-taskboard")
        await page.wait_for_selector("#tb:not([hidden])")
        await page.wait_for_timeout(800)
        await page.screenshot(path=str(out / "taskboard.png"))
        await page.keyboard.press("Escape")
        await page.wait_for_selector("#tb", state="hidden")

        # one room: alone, wider; the way back
        room_id = await page.evaluate("() => Object.keys(window.__dbg.live3d().rooms)[0]")
        before = await page.evaluate("(id) => window.__dbg.room(id)", room_id)
        await page.click(f".tag.room[data-set-project='{room_id}']")
        await wait(page, f"() => window.__dbg.solo() === '{room_id}' && Object.keys(window.__dbg.live3d().rooms).length === 1", label="one room")
        await page.wait_for_timeout(1500)
        alone = await page.evaluate("(id) => ({ r: window.__dbg.room(id), back: !document.getElementById('room-solo').hidden, name: document.getElementById('room-solo-name').textContent })", room_id)
        res["solo"] = {"before": before, "alone": alone}
        wider = (alone["r"]["x1"] - alone["r"]["x0"]) > (before["x1"] - before["x0"]) * 1.3
        check(failures, wider and alone["back"], f"the room picked is shown alone and wider, with the way back: {res['solo']}")
        await wait(page, SETTLED_JS, label="seated in the wide room")
        res["soloOverlap"] = desks_clear(await page.evaluate("() => window.__dbg.seats()"))
        await page.screenshot(path=str(out / "room.png"))
        await page.click("#room-back")
        await wait(page, "() => window.__dbg.solo() === null && Object.keys(window.__dbg.live3d().rooms).length === 4", label="back to the floor")
        await wait(page, SETTLED_JS, label="seated on the floor again")
        back = await page.evaluate(SEATS_JS)
        res["afterSolo"] = {k: [again.get(k), back.get(k)] for k in back if again.get(k) != back.get(k)}
        check(failures, not res["afterSolo"], f"the desks are where they were after the one-room view: {res['afterSolo']}")
        # Escape leaves the one-room view too
        await page.click(f".tag.room[data-set-project='{room_id}']")
        await wait(page, f"() => window.__dbg.solo() === '{room_id}'", label="one room again")
        await page.keyboard.press("Escape")
        await wait(page, "() => window.__dbg.solo() === null", label="Escape back to the floor")

        # dark, and 390 px (floor and one room)
        await page.emulate_media(color_scheme="dark")
        await page.wait_for_timeout(800)
        await page.screenshot(path=str(out / "floor-dark.png"))
        await page.click(f".tag.room[data-set-project='{room_id}']")
        await wait(page, f"() => window.__dbg.solo() === '{room_id}'", label="one room, dark")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(out / "room-dark.png"))
        await page.close()
        phone = await new_page(browser, watch, "rooms-phone", **PHONE)
        await phone.goto(srv.url + "/")
        await ready(phone)
        await wait(phone, "() => window.__dbg.robots.length > 0", label="phone robots")
        await phone.wait_for_timeout(1500)
        res["phone"] = {"floor": await phone.evaluate(NO_HSCROLL_JS)}
        await phone.screenshot(path=str(out / "phone-floor.png"))
        # the phone opens with the room picked on the desktop (the choice is kept): back, then pick it again
        if await phone.evaluate("() => window.__dbg.solo() !== null"):
            await phone.click("#room-back")
        await phone.evaluate("(id) => document.querySelector(`.tag.room[data-set-project='${id}']`).click()", room_id)
        await wait(phone, f"() => window.__dbg.solo() === '{room_id}'", label="phone one room")
        await phone.wait_for_timeout(1500)
        res["phone"]["room"] = await phone.evaluate(NO_HSCROLL_JS)
        res["phone"]["backFits"] = await phone.evaluate("() => { const b = document.getElementById('room-solo').getBoundingClientRect(); return b.right <= window.innerWidth && b.left >= 0; }")
        await phone.screenshot(path=str(out / "phone-room.png"))
        check(failures, res["phone"] == {"floor": True, "room": True, "backFits": True}, f"390 px: no horizontal scroll: {res['phone']}")
        await phone.close()
        for line in watch.console:
            failures.append(f"rooms: console: {line}")
        for u in watch.foreign:
            failures.append(f"rooms: request outside the server: {u}")
        res["console"] = len(watch.console)
    except Exception as e:
        failures.append(f"rooms: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        if srv:
            srv.stop()
        await browser.close()
    print(f"  rooms/doors-desks-solo: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "rooms-results.json").write_text(dump(res) + "\n")
