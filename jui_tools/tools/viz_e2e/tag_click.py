"""A robot's tag selects the robot (ticket 2026-10-20-jui-viz-robot-name-tag-click-selects, 2.3.6).

The real `jui viz serve` in a throwaway HOME on a free port, four sessions in one room through the real forward.py (the
first named through ~/.claude/sessions as Claude Code writes it, the others with no name) and a subagent. With real
mouse clicks on the page:

- every part of every kind of tag a robot carries selects that robot, as a click on its body does (the same card,
  rbState and its title): a named tag's name and its act, an unnamed tag's two-letter mark, a subagent's mark, the
  break's mark on a tag (タバコ休憩, the call / break / play span) and the bill over a robot;
- the cursor is a pointer on each and the hover rings the tag;
- two tags on each other (kept apart turned off): the nearer robot's takes the click, both ways round;
- a drag from empty space turns the camera and selects nothing; a drag that starts on a tag does the same (the
  decision in the ticket); the wheel over a tag zooms the camera;
- the rooms' signs stay over the robots' tags.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, new_page, ready
from waits import settled, until

CWD = "/work/click-app"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
SID = "e2e00000-0000-4000-8000-0000000004{:02x}"
NAME = "タグを押すと選べるかを確かめるための長い名前のセッション"
SUB = "a0sub0000000tag1"

# Move robot i to (x, z) relative to robot 0's spot and keep it there; every tag's target forgotten (see name_tags.py).
MOVE_JS = """([moves]) => { const rs = window.__dbg.robots; const a = rs[0].robot.root.position;
  const base = [a.x, a.z]; moves.forEach(([i, dx, dz]) => { const R = rs[i]; R.path = []; R.robot.root.position.x = base[0] + dx; R.robot.root.position.z = base[1] + dz; });
  rs.forEach((R) => { R.tagTarget = NaN; }); return true; }"""
# A part of robot `id`'s tag (or its bill) on the page: its centre, what the page has at that point, cursor and the rest.
PART_JS = """([id, sel]) => { const R = window.__dbg.robots.find((x) => x.def.id === id); if (!R) return null;
  const el = sel === '.bill' ? R.bill : sel ? R.tag.querySelector(sel) : R.tag; if (!el) return null;
  const b = el.getBoundingClientRect(), x = (b.left + b.right) / 2, y = (b.top + b.bottom) / 2;
  const at = document.elementFromPoint(x, y), owner = at && at.closest('[data-robot]');
  return { x, y, w: b.width, h: b.height, visible: b.width > 0 && getComputedStyle(el).display !== 'none' && (sel === '.bill' ? el : R.tag).style.visibility !== 'hidden',
    text: el.textContent, at: at ? (at.id || at.className || at.tagName) : null, owner: owner ? owner.dataset.robot : null,
    cursor: getComputedStyle(at || el).cursor, pe: getComputedStyle(el).pointerEvents }; }"""
VIEW_MOVE_JS = """(k) => { const rs = window.__dbg.robots, a = rs[0].robot.root.position, c = window.__dbg.camera.position;
  let dx = c.x - a.x, dz = c.z - a.z; const n = Math.hypot(dx, dz) || 1; dx /= n; dz /= n;
  const R = rs[1]; R.path = []; R.robot.root.position.x = a.x + dx * k - dz * 0.1; R.robot.root.position.z = a.z + dz * k + dx * 0.1;
  rs.forEach((Q) => { Q.tagTarget = NaN; }); return true; }"""
CARD_JS = """() => { const rb = document.getElementById('rb'), t = document.getElementById('rb-title');
  return { robot: window.__dbg.board().robot, open: !!rb && !rb.hidden, title: t ? t.textContent : null }; }"""
BACK_JS = """() => window.__dbg.board().robot === null && !window.__dbg.focus().zoomed && !window.__dbg.focus().tween && !document.getElementById('tags').hidden"""
CAM_JS = """() => window.__dbg.camera.position.toArray()"""


def check(failures, cond, text):
    if not cond:
        failures.append(f"tag-click: {text}")


async def run_tag_click(pw, out, failures, jt=None):
    from run import free_port
    name = "tag-click"
    out = pathlib.Path(out) / name
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(jt) if jt else pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    sessions = home / ".claude" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    for i in range(4):
        row = {"pid": 93000 + i, "sessionId": SID.format(i), "cwd": CWD, "status": "idle", "entrypoint": "cli"}
        if i == 0:
            row.update(name=NAME, nameSource="user")
        (sessions / f"{93000 + i}.json").write_text(json.dumps(row, ensure_ascii=False))
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {"clicks": {}, "family": {}}

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
        await page.emulate_media(color_scheme="light", reduced_motion="no-preference")
        await page.goto(url + "/")
        await ready(page)
        await until(page, "() => document.querySelector('.chip.demo').dataset.net === 'connected'", "connected")
        for i in range(4):
            hook(SID.format(i), hook_event_name="SessionStart", source="startup")
            hook(SID.format(i), hook_event_name="PreToolUse", tool_name="Read", tool_use_id=f"r{i}",
                 tool_input={"file_path": f"/work/click-app/docs/screens/json/screen-{i}.spec.json"})
        hook(SID.format(0), hook_event_name="SubagentStart", agent_id=SUB, agent_type="Explore")
        hook(SID.format(0), hook_event_name="PreToolUse", agent_id=SUB, agent_type="Explore", tool_name="Grep", tool_use_id="g0",
             tool_input={"pattern": "tag"})
        await until(page, "() => window.__dbg.robots.length >= 5 && window.__dbg.robots.every((R) => !R.path.length)", "seated", timeout=40000,
                    why="() => window.__dbg.settleInfo()")
        labels = await page.evaluate("() => Object.fromEntries(window.__dbg.robots.map((R) => [R.def.kind === 'main' ? R.def.sessionId : 'sub', R.def.id]))")
        lab = {i: labels[SID.format(i)] for i in range(4)}
        sub = labels.get("sub")
        room_id = await page.evaluate("() => window.__dbg.robots[0].def.room")
        await until(page, "(id) => { const R = window.__dbg.robots.find((x) => x.def.id === id); return R && R.tag.classList.contains('named'); }",
                    "the first robot's tag shows its name", arg=lab[0])
        # the robots apart, so no tag sits on another and no tag on another robot's body
        await page.evaluate(MOVE_JS, [[(1, 3.0, 0.0), (2, -3.0, 0.0), (3, 0.0, 2.5)] + ([(4, 1.5, 2.5)] if sub else [])])
        await settled(page, "robots apart")

        async def close_card(label):
            await page.click("#rb-close")
            await until(page, BACK_JS, f"{label}: back to the 3D view", why="() => window.__dbg.focus()")
            await settled(page, f"{label}: tags back")

        async def click_part(label, rid, sel):
            p = await page.evaluate(PART_JS, [rid, sel])
            res["clicks"][label] = {"part": p}
            if not p or not p["visible"]:
                check(failures, False, f"{label}: the part {sel!r} of {rid}'s tag is on the page: {p}")
                return None
            check(failures, p["owner"] == rid, f"{label}: the page has {rid}'s tag at the part's centre: {p}")
            check(failures, p["cursor"] == "pointer", f"{label}: the cursor is a pointer there: {p['cursor']}")
            await page.mouse.click(p["x"], p["y"])
            try:
                card = await until(page, f"() => {{ const c = ({CARD_JS})(); return c.open && c.robot ? c : null; }}", f"{label}: a card opens", timeout=15000)
            except Exception as e:  # noqa: BLE001
                check(failures, False, f"{label}: a click on the tag opened no card: {str(e)[:200]}")
                return None
            res["clicks"][label]["card"] = card
            check(failures, card["robot"] == rid, f"{label}: the click selects {rid}: {card}")
            await close_card(label)
            return card

        # the same robot's body: the card a click on the tag must give
        body = await page.evaluate("""(id) => { const R = window.__dbg.robots.find((x) => x.def.id === id); const T = window.__dbg.THREE;
          const v = R.robot.root.position.clone().add(new T.Vector3(0, 1.0 * (R.robot.size || 1), 0)).project(window.__dbg.camera);
          const r = document.getElementById('scene-canvas').getBoundingClientRect();
          const x = r.left + (v.x + 1) / 2 * r.width, y = r.top + (1 - v.y) / 2 * r.height, at = document.elementFromPoint(x, y);
          return { x, y, at: at ? at.id || at.className : null }; }""", lab[0])
        check(failures, body["at"] == "scene-canvas", f"the first robot's body is bare canvas on the page: {body}")
        await page.mouse.click(body["x"], body["y"])
        body_card = await until(page, f"() => {{ const c = ({CARD_JS})(); return c.open && c.robot ? c : null; }}", "a click on the body opens the card")
        res["body"] = body_card
        await close_card("body")

        named = await click_part("named tag: its name", lab[0], ".nm")
        check(failures, named is not None and named == body_card, f"the card from the tag is the card from the body: {named} vs {body_card}")
        await click_part("named tag: its act", lab[0], "span:last-child")
        await click_part("unnamed tag: its mark", lab[1], ".pill")
        await click_part("unnamed tag: its act", lab[2], "span:last-child")
        if sub:
            await click_part("subagent's tag: its mark", sub, ".pill")
        else:
            check(failures, False, "a subagent's robot came in")

        # the bill over a robot
        shown = await page.evaluate("([id]) => window.__dbg.billShow(id, 0.12)", [lab[3]])
        check(failures, shown, "a bill over the fourth robot")
        await until(page, "(id) => { const R = window.__dbg.robots.find((x) => x.def.id === id); return R.bill && !R.bill.hidden && R.bill.style.visibility === 'visible'; }",
                    "the bill shows", arg=lab[3])
        await page.wait_for_timeout(300)
        await click_part("the bill", lab[3], ".bill")

        # the hover rings the tag
        p = await page.evaluate(PART_JS, [lab[1], ""])
        before = await page.evaluate("(id) => getComputedStyle(window.__dbg.robots.find((x) => x.def.id === id).tag).boxShadow", lab[1])
        await page.mouse.move(p["x"], p["y"])
        after = await page.evaluate("(id) => getComputedStyle(window.__dbg.robots.find((x) => x.def.id === id).tag).boxShadow", lab[1])
        res["hover"] = {"before": before, "after": after}
        check(failures, before != after, f"the hover changes the tag's look: {before} -> {after}")

        # the rooms' signs over every robot's tag
        z = await page.evaluate("""() => ({ room: getComputedStyle(document.querySelector('.tag.room')).zIndex,
          bots: window.__dbg.robots.map((R) => getComputedStyle(R.tag).zIndex) })""")
        res["zIndex"] = z
        check(failures, all(int(b) < int(z["room"]) for b in z["bots"] if b != "auto"), f"rooms' signs over the robots' tags: {z}")

        # a drag from empty space turns the camera and selects nothing
        # rid: the drag starts on that robot's tag, read again once the camera is at rest (the tag moves with the camera;
        # The independent check's mutation N1, 10-20: the press read before the rest landed on the bare canvas, so no tag ever had it)
        async def drag(label, x, y, rid=None):
            await page.mouse.move(x, y)
            still = 1e9
            for _ in range(20):   # the camera at rest first (the damping of an earlier drag runs on for a while)
                c0 = await page.evaluate(CAM_JS)
                await page.wait_for_timeout(300)
                c1 = await page.evaluate(CAM_JS)
                still = max(abs(a - b) for a, b in zip(c0, c1))
                if still < 0.001:
                    break
            if rid:
                p = await page.evaluate(PART_JS, [rid, ".pill"])
                x, y = p["x"], p["y"]
                await page.mouse.move(x, y)
            await page.evaluate("""() => { window.__pressOn = undefined; window.addEventListener('pointerdown', (e) => {
              const o = e.target.closest && e.target.closest('[data-robot]'); window.__pressOn = o ? o.dataset.robot : null; }, { capture: true, once: true }); }""")
            await page.mouse.down()
            press_on = await page.evaluate("() => window.__pressOn")
            for k in range(1, 9):
                await page.mouse.move(x + 20 * k, y + 4 * k)
            await page.mouse.up()
            await page.wait_for_timeout(600)
            c2 = await page.evaluate(CAM_JS)
            card = await page.evaluate(CARD_JS)
            moved = max(abs(a - b) for a, b in zip(c1, c2))
            res[label] = {"still": still, "moved": moved, "card": card, "pressOn": press_on}
            check(failures, press_on == rid, f"{label}: the press lands on {rid or 'the bare canvas'}: {press_on}")
            check(failures, still < 0.01 and moved > 0.3, f"{label}: the camera turns (still {still:.3f}, moved {moved:.3f})")
            check(failures, card["robot"] is None and not card["open"], f"{label}: selects nothing: {card}")

        empty = await page.evaluate("""() => { const r = document.getElementById('scene-canvas').getBoundingClientRect();
          for (let y = r.top + 60; y < r.bottom - 60; y += 30) for (let x = r.left + 60; x < r.left + r.width / 2; x += 30) {
            const at = document.elementFromPoint(x, y); if (at && at.id === 'scene-canvas') return { x, y }; } return null; }""")
        check(failures, empty is not None, "a bare point of the canvas")
        if empty:
            await drag("drag from empty space", empty["x"], empty["y"])
        await settled(page, "after the drag")
        p = await page.evaluate(PART_JS, [lab[2], ".pill"])
        check(failures, p and p["owner"] == lab[2], f"the third robot's tag under the pointer for the drag: {p}")
        if p:
            await drag("drag from a tag", p["x"], p["y"], lab[2])
        # the wheel over a tag zooms
        await settled(page, "before the wheel")
        p = await page.evaluate(PART_JS, [lab[1], ".pill"])
        d0 = await page.evaluate("() => window.__dbg.camera.position.length()")
        await page.mouse.move(p["x"], p["y"])
        await page.mouse.wheel(0, -300)
        await page.wait_for_timeout(700)
        d1 = await page.evaluate("() => window.__dbg.camera.position.length()")
        res["wheel"] = {"at": p, "d0": d0, "d1": d1}
        check(failures, p["owner"] == lab[1] and abs(d1 - d0) > 0.3, f"the wheel over a tag zooms: {d0:.2f} -> {d1:.2f} at {p and p['owner']}")

        # two tags on each other: the nearer robot's takes the click, both ways round
        await page.evaluate("() => window.__dbg.tagsApart(false)")
        ids = await page.evaluate("() => window.__dbg.robots.map((R) => R.def.id)")
        for label, k, front, back in (("overlap: 1 behind 0", -0.12, ids[0], ids[1]),
                                      ("overlap: 1 in front of 0", 0.12, ids[1], ids[0])):
            # robot 1 put k m from robot 0 towards the camera (on the floor), a little to the side: the two tags on each other
            await page.evaluate(VIEW_MOVE_JS, k)
            await settled(page, label)
            got = await page.evaluate("""([a, b]) => { const rs = window.__dbg.robots, cam = window.__dbg.camera.position;
              const A = rs.find((x) => x.def.id === a), B = rs.find((x) => x.def.id === b);
              const ra = A.tag.getBoundingClientRect(), rb = B.tag.getBoundingClientRect();
              const x0 = Math.max(ra.left, rb.left), x1 = Math.min(ra.right, rb.right), y0 = Math.max(ra.top, rb.top), y1 = Math.min(ra.bottom, rb.bottom);
              const x = (x0 + x1) / 2, y = (y0 + y1) / 2, at = document.elementFromPoint(x, y), o = at && at.closest('[data-robot]');
              return { overlap: x1 - x0 > 4 && y1 - y0 > 4, x, y, owner: o ? o.dataset.robot : null,
                nearer: A.robot.root.position.distanceTo(cam) < B.robot.root.position.distanceTo(cam), dom: [...A.tag.parentNode.children].indexOf(A.tag) < [...B.tag.parentNode.children].indexOf(B.tag) ? 'front first' : 'back first' }; }""",
                                    [front, back])
            res[label] = got
            check(failures, got["overlap"] and got["nearer"], f"{label}: the two tags are on each other, {front} the nearer: {got}")
            check(failures, got["owner"] == front, f"{label}: the page has the nearer robot's tag on top: {got}")
            if not got["overlap"]:
                continue
            await page.mouse.click(got["x"], got["y"])
            card = await until(page, f"() => {{ const c = ({CARD_JS})(); return c.open && c.robot ? c : null; }}", f"{label}: a card opens", timeout=15000)
            res[label]["card"] = card
            check(failures, card["robot"] == front, f"{label}: the click selects the nearer robot {front}, not {back}: {card}")
            await close_card(label)
        await page.evaluate("() => window.__dbg.tagsApart(true)")
        await page.evaluate(MOVE_JS, [[(1, 3.0, 0.0)]])
        await settled(page, "apart again")

        # the break's mark (the span a call, a nap, a game and a break share) in the one-room view
        await page.evaluate("() => window.__dbg.play({ p: 0, solo: { p: 0 }, endAll: true, idleMs: 0, restMinSec: 0, restMaxSec: 0 })")
        for i in range(4):
            hook(SID.format(i), hook_event_name="Stop")
        # the room's sign may be out of the view the drags and the wheel left: pressed through the page
        await page.evaluate("(id) => document.querySelector(`.tag.room[data-set-project='${id}']`).click()", room_id)
        await until(page, f"() => window.__dbg.solo() === '{room_id}'", "one room")
        await until(page, "() => window.__dbg.robots.every((R) => !R.path.length)", "settled up close", timeout=30000)
        await page.evaluate("() => window.__dbg.brk({ p: { smoke: 1, vend: 0 }, joinP: 0, smokeMinSec: 60, smokeMaxSec: 60, restMinSec: 0, restMaxSec: 0 })")
        smoker = await until(page, "() => { const b = window.__dbg.brk().robots.find((x) => x.kind === 'smoke' && x.at); return b ? b.id : null; }",
                             "one in the booth", timeout=40000, why="() => window.__dbg.brk().robots")
        await page.evaluate("() => window.__dbg.brk({ p: { smoke: 0, vend: 0 } })")
        await settled(page, "in the booth", ids=[smoker])
        mark = await page.evaluate(PART_JS, [smoker, ".call-mark"])
        check(failures, mark and "休憩" in mark["text"], f"the smoker's tag shows its break: {mark}")
        await click_part("break mark on the tag", smoker, ".call-mark")
        res["family"] = await page.evaluate("""() => [...document.getElementById('tags').children].reduce((m, el) => {
          const k = el.classList.contains('bill') ? 'bill' : el.classList.contains('room') ? 'room sign' : el.classList.contains('tray') ? 'tray' : el.classList.contains('bot') ? 'robot tag' : el.className;
          m[k] = { pointerEvents: getComputedStyle(el).pointerEvents, cursor: getComputedStyle(el).cursor, robot: !!el.dataset.robot }; return m; }, {})""")
        await page.evaluate("() => window.__dbg.brk({ p: { smoke: 0, vend: 0 }, endAll: true })")
        check(failures, not watch.console and not watch.foreign and not watch.csp, f"no console error, nothing outside the server: {watch.console[:3]} {watch.foreign[:3]}")
        await page.close()
    except Exception as e:   # a wait that ran out is a FAIL line with what was seen, not a traceback that ends run.py
        failures.append(f"tag-click: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        await browser.close()
        srv.terminate()  # our own child (started above)
        try:
            srv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            srv.kill()
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"  {name}: {time.monotonic() - t0:.0f}s", flush=True)
