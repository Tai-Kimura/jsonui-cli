"""← → between the rooms of a floor, ↑ ↓ between the floors (2.3.5, requester 10-19: "部屋の状態で左右キー押したら左右の部屋に
移動したい それと階全体表示で上下押したら上下の階に移動したい"; rulings: the floor's layout read like text, and it wraps on
the floor).
Runs with `--only arrows-rooms`.

The real `jui viz serve` in a throwaway HOME on a free port, the real forward.py for the hooks. Eight projects: 1F holds
six rooms (3 by 2), 2F two. Two of them (r2, r5) are busy, so 1F's layout order is not the project list's order, nor
a rotation of it (the busy rooms take the first slots) — an order taken from the list instead of the layout goes red. The expected order is read from
the rooms' places in the scene on the whole floor (back row before front row, left before right), not from the page's
own order. Every step waits for the camera's flight to end (no tween left), never for time.

Checked: on the whole floor ↑ ↓ go up and down (as ▲ ▼; the ends stop), ← → do nothing; in a room → five times walks
the six rooms in order (the back row's right end, then the front row's left end), a sixth → is the first room again
and ← from the first room is the last (wrapped, the floor unchanged), ↑ ↓ do nothing; four quick → land on the fifth
room; with the card open ← → switch robots and the
room stays, ↑ ↓ do nothing; a focused input / textarea / contenteditable, an IME composing, a modifier and the spec
help dialog take the keys from neither.
Also (ticket 2026-10-21-jui-viz-3d-zoom-lost-after-project-switch): with no card, on 1F's whole floor, a robot of a 2F room
picked from outside the view (selectRobot: a talk's ロボットへ移る, a notification) — its room shown on 2F, its card open,
the camera on it once the scene has put it there, and closing goes back to that room, not to 1F's whole floor.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import ISOLATE, LAUNCH_ARGS, Watch, dump, new_page, ready

DESKTOP = {"viewport": {"width": 1440, "height": 900}, "device_scale_factor": 1}
CWDS = [f"/work/r{k}-app" for k in range(1, 9)]
SIDS = [f"a{k}000000-0000-4000-8000-0000000000{k:02d}" for k in range(1, 9)]
EXTRA = "b9000000-0000-4000-8000-000000000099"   # a second robot in r2-app/, the first room of 1F's layout (the card's ← →)
# r2, r5: working, so they take 1F's first slots: 1F's layout is r2 r5 r1 / r3 r4 r6, and the project list's order on it
# (r1 r2 r3 r4 r5 r6) is not even a rotation of it — a walk in the list's order cannot pass by wrapping round.
BUSY = (1, 4)

SETTLED = "() => window.__dbg.focus().tween === false"
STATE = """() => { const f = window.__dbg.floors(), ids = f.floors[f.floor] || [];
  const shown = ids.filter((id) => window.__dbg.room(id).shown);
  return { floor: f.floor, floors: f.floors.length, shown, scope: document.getElementById('scope-top').textContent,
    badge: (document.querySelector('#rb .rb-badge') || {}).textContent || '', card: !document.getElementById('rb').hidden }; }"""
# The whole floor's rooms in the order the eye reads them: the back row (smaller z) first, left (smaller x) first.
LAYOUT = """() => { const f = window.__dbg.floors(), ids = [...(f.floors[f.floor] || [])];
  const g = Object.fromEntries(ids.map((id) => [id, window.__dbg.room(id)]));
  const rows = [...new Set(ids.map((id) => g[id].z0))].sort((a, b) => a - b);
  return ids.sort((a, b) => rows.indexOf(g[a].z0) - rows.indexOf(g[b].z0) || g[a].x0 - g[b].x0)
    .map((id) => ({ id, row: rows.indexOf(g[id].z0), x0: g[id].x0 })); }"""


def check(failures, cond, text):
    if not cond:
        failures.append(f"arrows-rooms: {text}")


async def wait(page, js, timeout=30000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=100)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def run_arrows_rooms(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "arrows-rooms"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE + ("PYTHONPATH",)}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def hook(sid, cwd, event, **kw):
        subprocess.run([sys.executable, "-I", "-S", str(forward)],
                       input=json.dumps({"session_id": sid, "cwd": cwd, "transcript_path": f"/nowhere/{sid}.jsonl",
                                         "permission_mode": "default", "hook_event_name": event, **kw}).encode(),
                       capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)

    async def state(page):
        return await page.evaluate(STATE)

    async def key(page, k, settle=True):
        await page.keyboard.press(k)
        if settle:
            await wait(page, SETTLED, label=f"the camera after {k}")

    async def pick(page, pid):
        await page.click("#scope-top")
        await page.click(f'#pop [data-pick-project="{pid}"]')
        await wait(page, "(id) => window.__dbg.room(id).shown && window.__dbg.floors().floors[window.__dbg.floors().floor].filter((x) => window.__dbg.room(x).shown).length === 1",
                   arg=pid, label=f"the room {pid} alone")
        await wait(page, SETTLED, label="the camera in the room")

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
        for sid, cwd in zip(SIDS, CWDS):
            hook(sid, cwd, "SessionStart", source="startup")
        hook(EXTRA, CWDS[1], "SessionStart", source="startup")
        for k in BUSY:
            hook(SIDS[k], CWDS[k], "UserPromptSubmit", prompt="作業中")
            hook(SIDS[k], CWDS[k], "PreToolUse", tool_name="Read", tool_input={"file_path": f"{CWDS[k]}/a.txt"}, tool_use_id=f"t-{k}")   # a tool running: an active room
        watch = Watch(origin=url)
        page = await new_page(browser, watch, "arrows-rooms", **DESKTOP)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => window.__dbg.floors().floors.length === 2 && window.__dbg.floors().floors[0].length === 6", label="two floors, six rooms on 1F")
        await wait(page, SETTLED, label="the first camera")
        await page.click("#scene-canvas", position={"x": 5, "y": 5})   # the page has the focus, not a field
        layout = res["layout"] = await page.evaluate(LAYOUT)
        order = [x["id"] for x in layout]
        check(failures, [x["row"] for x in layout] == [0, 0, 0, 1, 1, 1], f"1F is three by two: {layout}")
        menu = res["menu"] = await page.evaluate("""async () => { document.getElementById('scope-top').click();
          await new Promise((r) => requestAnimationFrame(r));
          const ids = [...document.querySelectorAll('#pop [data-pick-project]')].map((b) => b.dataset.pickProject).filter((x) => x !== 'all');
          document.getElementById('scope-top').click(); return ids; }""")
        on_floor = [x for x in menu if x in order]
        res["listOrder"] = on_floor
        rotations = [on_floor[k:] + on_floor[:k] for k in range(len(on_floor))]
        check(failures, sorted(on_floor) == sorted(order) and order not in rotations, f"1F's layout order is not the project list's order, nor a rotation of it: {order} vs {on_floor}")
        res["floors"] = (await state(page))["floors"]

        # the whole floor: ← → nothing; ↑ ↓ the floors (the ends stop); the same as ▲ ▼
        s0 = await state(page)
        await key(page, "ArrowRight")
        await key(page, "ArrowLeft")
        s = await state(page)
        check(failures, (s["floor"], s["scope"], len(s["shown"])) == (0, s0["scope"], 6), f"whole floor: ← → do nothing: {s}")
        await key(page, "ArrowDown")
        check(failures, (await state(page))["floor"] == 0, "↓ on the lowest floor stays")
        await key(page, "ArrowUp")
        s = await state(page)
        check(failures, s["floor"] == 1, f"↑ goes up: {s}")
        await page.screenshot(path=str(out / "floor-2.png"))
        await key(page, "ArrowUp")
        check(failures, (await state(page))["floor"] == 1, "↑ on the top floor stays")
        await key(page, "ArrowDown")
        check(failures, (await state(page))["floor"] == 0, "↓ comes down")
        await page.click("#floor-up")
        await wait(page, SETTLED, label="▲")
        by_button = (await state(page))["floor"]
        await page.click("#floor-down")
        await wait(page, SETTLED, label="▼")
        check(failures, by_button == 1 and (await state(page))["floor"] == 0, "▲ ▼ do what ↑ ↓ did")

        # a room: → walks the layout, the ends stop, ↑ ↓ nothing
        await pick(page, order[0])
        await page.click("#scene-canvas", position={"x": 5, "y": 5})
        seen = [(await state(page))["shown"]]
        for _ in range(5):
            await key(page, "ArrowRight")
            seen.append((await state(page))["shown"])
        res["walk"] = seen
        check(failures, seen == [[x] for x in order], f"→ walks 1F's layout, back row then front row: {seen} vs {order}")
        check(failures, seen[3] == [order[3]] and layout[2]["row"] == 0 and layout[3]["row"] == 1, "after the back row's right end comes the front row's left end")
        await page.screenshot(path=str(out / "room-last.png"))
        for k in ("ArrowUp", "ArrowDown"):
            await key(page, k)
            s = await state(page)
            check(failures, s["shown"] == [order[5]] and s["floor"] == 0, f"{k} in a room does nothing: {s}")
        await key(page, "ArrowRight")
        s = res["wrapRight"] = await state(page)
        check(failures, s["shown"] == [order[0]] and s["floor"] == 0, f"→ at the last room (front right) wraps to the first (back left), same floor: {s}")
        await key(page, "ArrowLeft")
        s = res["wrapLeft"] = await state(page)
        check(failures, s["shown"] == [order[5]] and s["floor"] == 0, f"← at the first room wraps to the last, same floor: {s}")
        back = []
        for _ in range(5):
            await key(page, "ArrowLeft")
            back.append((await state(page))["shown"])
        check(failures, back == [[x] for x in reversed(order[:5])], f"← walks back: {back}")

        # four quick → (no wait between): it lands on the fifth room once the camera is done
        for _ in range(4):
            await page.keyboard.press("ArrowRight")
        await wait(page, SETTLED, label="the camera after the quick presses")
        s = res["quick"] = await state(page)
        check(failures, s["shown"] == [order[4]], f"four quick → land on the fifth room: {s}")
        for _ in range(4):
            await page.keyboard.press("ArrowLeft")
        await wait(page, SETTLED, label="back")
        await wait(page, "(id) => window.__dbg.room(id).shown", arg=order[0], label="back in the first room")

        # what takes the keys from neither: fields, an IME, modifiers, the spec help dialog
        for tag, html in (("input", "<input id='e2e-field'>"), ("textarea", "<textarea id='e2e-field'></textarea>"),
                          ("contenteditable", "<div id='e2e-field' contenteditable='true'>x</div>")):
            await page.evaluate("(h) => { const d = document.createElement('div'); d.id = 'e2e-host'; d.innerHTML = h; d.style.cssText = 'position:fixed;left:4px;bottom:4px;z-index:99'; document.body.append(d); document.getElementById('e2e-field').focus(); }", html)
            await key(page, "ArrowRight", settle=False)
            await key(page, "ArrowUp", settle=False)
            s = await state(page)
            check(failures, s["shown"] == [order[0]] and s["floor"] == 0, f"a focused {tag} keeps its arrows: {s}")
            await page.evaluate("() => document.getElementById('e2e-host').remove()")
        await page.click("#scene-canvas", position={"x": 5, "y": 5})
        await page.evaluate("() => document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', isComposing: true, bubbles: true, cancelable: true }))")
        for k in ("Alt+ArrowRight", "Control+ArrowRight", "Meta+ArrowRight", "Shift+ArrowRight"):
            await key(page, k, settle=False)
        s = await state(page)
        check(failures, s["shown"] == [order[0]], f"an IME composing and modifiers do nothing: {s}")
        await page.click("#spec-help-panel")
        await wait(page, "() => !!document.getElementById('spec-help')", label="the spec help")
        await key(page, "ArrowRight", settle=False)
        s = await state(page)
        check(failures, s["shown"] == [order[0]], f"with the spec help open, → does nothing: {s}")
        await page.keyboard.press("Escape")
        await wait(page, "() => !document.getElementById('spec-help')", label="the spec help closed")

        # the card: ← → switch robots, the room stays; ↑ ↓ nothing (also from the whole floor)
        await page.evaluate("() => document.querySelector('#sessions [data-robot-open]').click()")
        await wait(page, "() => !!(document.querySelector('#rb .rb-badge') || {}).textContent", label="the card")
        await wait(page, SETTLED, label="the camera at the robot")
        b0 = (await state(page))["badge"]
        await key(page, "ArrowRight")
        s = res["card"] = await state(page)
        check(failures, s["card"] and s["badge"] and s["badge"] != b0 and s["shown"] == [order[0]], f"card open: → switches the robot, the room stays: {b0} -> {s}")
        await page.screenshot(path=str(out / "card.png"))
        await page.click("#rb-close")
        await wait(page, "() => document.getElementById('rb').hidden", label="the card closed")
        await wait(page, SETTLED, label="the camera back")
        await page.click("#room-back")
        await wait(page, "() => { const f = window.__dbg.floors(); return f.floors[f.floor].every((id) => window.__dbg.room(id).shown); }", label="the whole floor")
        await wait(page, SETTLED, label="the camera on the whole floor")
        await page.evaluate("() => document.querySelector('#sessions [data-robot-open]').click()")
        await wait(page, "() => !document.getElementById('rb').hidden", label="the card on the whole floor")
        await wait(page, SETTLED, label="the camera at the robot")
        await key(page, "ArrowUp")
        s = await state(page)
        check(failures, s["floor"] == 0 and s["card"], f"card open on the whole floor: ↑ does nothing: {s}")
        # no card, 1F's whole floor: a robot of a 2F room picked from outside the view
        await page.click("#rb-close")
        await wait(page, "() => document.getElementById('rb').hidden", label="the card closed (2)")
        await wait(page, SETTLED, label="the camera back on the whole floor")
        far = await page.evaluate("""() => { const f = window.__dbg.floors(), up = f.floors[1] || [];
          return Object.keys(window.__dbg.robotState()).find((l) => up.includes(window.__dbg.robotProject(l))) || null; }""")
        check(failures, bool(far), f"a robot in a 2F room: {far}")
        if far:
            await page.evaluate("(l) => window.__dbg.selectRobot(l)", far)
            await wait(page, "(l) => window.__dbg.board().robot === l && !document.getElementById('rb').hidden", arg=far, label="the 2F robot's card")
            await wait(page, "() => { const c = window.__dbg.camOn(); return !c.tween && !c.waitFor && c.zoomed; }", label="the camera at the 2F robot")
            got = res["far"] = {"floor": (await page.evaluate("() => window.__dbg.floors()"))["floor"], "project": await page.evaluate("() => window.__dbg.project()"),
                                "robotProject": await page.evaluate("(l) => window.__dbg.robotProject(l)", far), "cam": await page.evaluate("() => window.__dbg.camOn()")}
            cam = got["cam"]
            check(failures, got["floor"] == 1 and got["project"] == got["robotProject"] and cam["inScene"] and cam["toRobot"] is not None and cam["toRobot"] < 1.5,
                  f"no card, 1F: a 2F robot picked: 2F, its room, the camera on it: {got}")
            check(failures, cam["returnToRoom"] is not None and cam["returnToRoom"] < 0.5, f"no card, 1F: closing goes back to the 2F room, not 1F's floor: {got}")
            await page.click("#rb-close")
            await wait(page, "() => document.getElementById('rb').hidden", label="the 2F robot's card closed")
            await wait(page, "() => { const c = window.__dbg.camOn(); return !c.tween && !c.zoomed; }", label="the camera back from the 2F robot")
            back = res["farBack"] = await page.evaluate("() => window.__dbg.camOn()")
            check(failures, back["toRoom"] < 0.5, f"the 2F robot's card closed: the camera on its room: {back}")
        await page.close()
        for line in watch.console:
            failures.append(f"arrows-rooms: console: {line}")
        for u in watch.foreign:
            failures.append(f"arrows-rooms: request outside the server: {u}")
    except Exception as e:
        failures.append(f"arrows-rooms: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        srv.terminate()   # our own child
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  arrows-rooms: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "arrows-rooms-results.json").write_text(dump(res) + "\n")
