"""A robot's card open, then another screen, then back: the 3D takes input again (ticket
2026-10-20-jui-viz-data-server-from-robot-card-freezes-3d; requester 10-20: 「ボット選択状態でデータサーバークリックすると3Dに戻った時に
何もできなくなる」).

The real `jui viz serve` in a throwaway HOME, the data-server suite's two JsonUI rooms (one with docs/api and docs/db,
so its rack stands up close). For each screen that can open over an open card — the data server's sheet (closed by its
button and by Escape), the 単価 sheet, the spec board, the task board, the log, the 「?」 dialog, the history tab, talk,
the next robot (›) — the card is opened by a click on the robot, the screen is opened, and while it is open the 3D stays
held (zoomed, the orbit off: nothing reaches the 3D under it); closed (and the card too, when it stays), the 3D takes
input: a drag turns the camera, a click on a robot opens its card, → moves to the next room. No console error, nothing
requested outside the server.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

import data_server as DS
from common import DESKTOP, LAUNCH_ARGS, Watch, new_page, ready
from waits import until

VIEW = "() => window.__dbg.view()"
# name: (how it opens, how it closes, whether the card stays open under it)
SCREENS = {
    "data-server-button": ("rack", "#ds-close", False),
    "data-server-escape": ("rack", "Escape", False),
    "prices": ("#prices-open", "#pr-close", False),
    "spec-board": ("#btn-specboard", "#wb-close", False),
    "task-board": ("#btn-taskboard", "#tb-close", False),
    "log": ("#btn-log", "#log-close", True),
    "spec-help": ("#spec-help-panel", "Escape", True),
    "history-tab": ("[data-rb-tab='history']", None, True),
    "talk": ("[data-rb-talk]", "[data-rb-talk]", True),
    "next-robot": ("[data-rb-step='1']", None, True),
}


def check(failures, cond, text):
    if not cond:
        failures.append(f"card-screens: {text}")


async def run_card_screens(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "card-screens"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    room_a, room_b = home / "work" / "spec-app", home / "work" / "plain-app"
    DS._room(room_a, True)
    DS._room(room_b, False)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in DS.ISOLATE}
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)],
                           stdout=open(out / "serve.log", "w"), stderr=subprocess.STDOUT,
                           env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def hook(sid, cwd, **payload):
        body = {"session_id": sid, "cwd": str(cwd), "permission_mode": "default", **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(),
                       capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)

    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    t0 = time.monotonic()
    watch = Watch(origin=url)
    try:
        import urllib.request
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        started = False
        for name, (opener, closer, card_stays) in SCREENS.items():
            page = await new_page(browser, watch, f"card-screens-{name}", **DESKTOP)
            await page.emulate_media(color_scheme="light", reduced_motion="no-preference")
            await page.goto(url + "/")
            await ready(page)
            await until(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", "connected")
            if not started:
                hook(DS.SID_A, room_a, hook_event_name="SessionStart", source="startup")
                hook(DS.SID_B, room_b, hook_event_name="SessionStart", source="startup")
                started = True
            await until(page, "() => window.__dbg.robots.length >= 2 && window.__dbg.robots.every((R) => !R.path.length)",
                        "two robots seated", timeout=30000)
            pa = await page.evaluate(f"() => window.__dbg.robots.find((R) => R.def.sessionId === '{DS.SID_A}').def.room")
            rid = await page.evaluate(f"() => window.__dbg.robots.find((R) => R.def.sessionId === '{DS.SID_A}').def.id")
            await page.click(f".tag.room[data-set-project='{pa}']")
            await until(page, f"() => window.__dbg.solo() === '{pa}' && window.__dbg.dataServer().built && "
                              "window.__dbg.robots.every((R) => !R.path.length) && !window.__dbg.view().tween",
                        f"{name}: the room up close with its rack", timeout=30000)
            await page.mouse.click(*await page.evaluate("(id) => window.__dbg.robotXY(id)", rid))
            await until(page, "() => { const v = window.__dbg.view(); return v.card && v.open.rb && !v.tween; }",
                        f"{name}: the card by a click on the robot", timeout=15000, why=VIEW)
            r = res[name] = {}
            if opener == "rack":
                await page.wait_for_timeout(500)    # the rack's spot on the screen is taken a frame after the camera stops
                # pressed for real when the camera (framing the robot) shows the rack bare; else the same call the
                # press makes (where the robot sits decides whether the rack is in view at all)
                spot = (await page.evaluate("() => window.__dbg.dataServer()"))["screen"]
                bare = await page.evaluate("([x, y]) => { const e = document.elementFromPoint(x, y); return !!e && e.tagName === 'CANVAS'; }", spot)
                r["rack"] = "click" if bare else "hook"
                if bare:
                    await page.mouse.click(*spot)
                else:
                    await page.evaluate("() => window.__dbg.pressRack()")
                await until(page, "() => window.__dbg.view().open.ds", f"{name}: the sheet over the card", why=VIEW)
            else:
                await page.click(opener)
            await page.wait_for_timeout(1200)
            held = r["held"] = await page.evaluate(VIEW)
            check(failures, held["zoomed"] and not held["controls"],
                  f"{name}: while it is open the 3D stays held (zoomed, the orbit off): {held}")
            if closer == "Escape":
                await page.keyboard.press("Escape")
            elif closer:
                await page.click(closer)
            if card_stays:
                await until(page, "() => window.__dbg.view().card", f"{name}: the card still there", why=VIEW)
                await page.wait_for_timeout(400)
                await page.keyboard.press("Escape")
            back = r["back"] = await until(page, "() => { const v = window.__dbg.view(); return !v.card && !v.tween && "
                                                 "!Object.values(v.open).some(Boolean) ? v : null; }",
                                           f"{name}: back to the 3D", timeout=15000, why=VIEW)
            check(failures, not back["zoomed"] and back["controls"] and back["held"] == [],
                  f"{name}: back in the 3D, nothing holds it (not zoomed, the orbit on, VIEW_HOLD empty): {back}")
            # a drag turns the camera
            cam0 = await page.evaluate("() => window.__dbg.focus().cam")
            box = await page.locator("canvas").first.bounding_box()
            x, y = box["x"] + box["width"] * 0.3, box["y"] + box["height"] * 0.7
            await page.mouse.move(x, y)
            await page.mouse.down()
            await page.mouse.move(x + 200, y - 40, steps=8)
            await page.mouse.up()
            await page.wait_for_timeout(500)
            r["drag"] = cam0 != await page.evaluate("() => window.__dbg.focus().cam")
            check(failures, r["drag"], f"{name}: back in the 3D, a drag turns the camera")
            # a click on a robot opens its card, Escape closes it
            await page.mouse.click(*await page.evaluate("(id) => window.__dbg.robotXY(id)", rid))
            got = await until(page, "() => window.__dbg.view().card", f"{name}: a click on the robot opens its card again",
                              timeout=10000, why=VIEW)
            r["click"] = bool(got)
            await page.keyboard.press("Escape")
            await until(page, "() => { const v = window.__dbg.view(); return !v.card && !v.tween && v.controls; }",
                        f"{name}: the card closed again", timeout=15000, why=VIEW)
            # → moves to the next room
            await page.keyboard.press("ArrowRight")
            r["key"] = await until(page, f"() => window.__dbg.solo() && window.__dbg.solo() !== '{pa}'",
                                   f"{name}: → moves to the next room", timeout=10000)
            await page.close()
        check(failures, not watch.console and not watch.foreign and not watch.csp,
              f"no console error, nothing outside the server: {watch.console[:3]} {watch.foreign[:3]}")
    except Exception as e:
        failures.append(f"card-screens: {type(e).__name__}: {str(e).splitlines()[0][:400]}")
    finally:
        await browser.close()
        srv.terminate()  # our own child (started above)
        try:
            srv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            srv.kill()
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"  card-screens: {time.monotonic() - t0:.0f}s", flush=True)
