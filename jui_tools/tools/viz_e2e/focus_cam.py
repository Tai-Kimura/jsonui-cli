"""The camera on a robot (2.3.1, requester 10-18: "ズーム中も回転とか拡大縮小とかできるようにしたい",
"ロボットの場所によってはこんな感じになって見えない").

The real `jui viz serve` in a throwaway HOME on a free port: six rooms in two rows, a main session and two subagents
in each (their seats are fixed by their ids), so some robots in the back row sit behind the front row's walls and
boards from the usual direction. For the robot the usual direction sees worst: its card's camera picks a direction
from which nothing stands between the camera and the robot; a drag turns the camera around the robot, the wheel
moves it nearer; turned back to the usual direction, what stands in the way is drawn faint, and every faint thing
gets its own material back when the card closes (Esc). ← then picks the next robot's own view. Light and dark,
1440 and 390 px screenshots.
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
PHONE = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 2, "is_mobile": True, "has_touch": True}
FOCUS = "() => window.__dbg.focus()"
SETTLED = "() => { const f = window.__dbg.focus(); return f.zoomed && !f.tween; }"
# The camera is at its pose for the direction asked, and what is faint is exactly what stands between it and the robot
# there (the fade is synced with the card's refresh, a frame at most 4 times a second): the state the specimen search
# reads. It once waited 900 ms instead: the follow is a lerp a frame, so on a busy machine (frames slow) the camera was
# still 0.8–1.9 away from the pose asked and the search read the faint meshes of wherever it had got to — no specimen
# in 24 turns (focus-cam flake, 10-19: 2 runs in 8 under load).
AT_POSE = """() => { const d = window.__dbg.focusAt(), f = window.__dbg.focus();
  return d !== null && d < 1e-3 && f.blockersFaded === f.blockersNow && f.faded === f.blockersNow; }"""
# Frames SLOW_MS apart during the search (the e2e's own requestAnimationFrame wrapper; a busy machine, made sure): a
# search that reads before the camera is at its pose finds no specimen every time instead of now and then.
SLOW_RAF = """(() => { const raf = window.requestAnimationFrame.bind(window);
  window.requestAnimationFrame = (cb) => { const ms = window.__slowFrameMs || 0; return ms ? setTimeout(() => raf(cb), ms) : raf(cb); }; })()"""
SLOW_MS = 600


def check(failures, cond, text):
    if not cond:
        failures.append(f"focus-cam: {text}")


async def wait(page, js, arg=None, timeout=20000, label=""):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def settle(page, ms=2500):
    await wait(page, SETTLED, label="the camera on the robot")
    await page.wait_for_timeout(ms)   # the camera follows its orbit (a lerp a frame) and the card refreshes 4 times a second


async def run_focus_cam(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "focus-cam"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def hook(payload):
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(payload).encode(),
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
        for i in range(6):
            sid, cwd = f"c{i}000000-0000-4000-8000-0000000000f{i}", f"/work/cam-{i}"
            hook({"session_id": sid, "cwd": cwd, "hook_event_name": "SessionStart", "source": "startup"})
            for j in range(3):
                hook({"session_id": sid, "cwd": cwd, "hook_event_name": "SubagentStart", "agent_id": f"a{i}{j}0000000000", "agent_type": "Explore"})
        watch = Watch(origin=url)
        page = await new_page(browser, watch, "focus-cam", **DESKTOP)
        await page.add_init_script(SLOW_RAF)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => Object.keys(window.__dbg.robotState()).length >= 24", timeout=30000, label="24 robots")
        await page.wait_for_timeout(3000)
        ids = await page.evaluate("() => Object.keys(window.__dbg.robotState())")
        usual = {i: await page.evaluate("(i) => window.__dbg.usualBlockers(i)", i) for i in ids}
        res["usual"] = usual
        worst = max(ids, key=lambda i: (usual[i], i))
        check(failures, usual[worst] >= 1, f"the layout has a robot the usual direction cannot see (the specimen): {usual}")

        # 1. the view is chosen: nothing between the camera and the robot
        await page.evaluate("(i) => window.__dbg.openRobot(i)", worst)
        await settle(page)
        f = res["opened"] = await page.evaluate(FOCUS)
        check(failures, f["id"] == worst and f["chosen"]["usual"] == usual[worst] and f["chosen"]["blockers"] == 0 and f["blockersNow"] == 0,
              f"the card's camera picks a view nothing blocks ({worst}, usually {usual[worst]}): {f}")
        await page.screenshot(path=str(out / "chosen-light.png"))

        # 2. a drag turns the camera around the robot; 3. the wheel moves it nearer
        box = await page.evaluate("() => { const r = document.getElementById('scene-canvas').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }")
        x, y = box[0] + box[2] * 0.25, box[1] + box[3] * 0.55
        await page.mouse.move(x, y)
        await page.mouse.down()
        for k in range(1, 11):
            await page.mouse.move(x + 16 * k, y + 3 * k)
        await page.mouse.up()
        await page.wait_for_timeout(1500)
        g = res["dragged"] = await page.evaluate(FOCUS)
        moved = sum((a - b) ** 2 for a, b in zip(g["cam"], f["cam"])) ** 0.5
        check(failures, abs(g["az"] - f["az"]) > 0.5 and moved > 1 and g["zoomed"] and g["id"] == worst,
              f"a drag turns the camera around the robot: az {f['az']} -> {g['az']}, moved {moved:.2f}")
        await page.mouse.move(x, y)
        await page.mouse.wheel(0, -600)
        await page.wait_for_timeout(1500)
        h = res["wheeled"] = await page.evaluate(FOCUS)
        check(failures, h["dist"] < g["dist"] - 1 and h["zoomed"], f"the wheel moves nearer: {g['dist']} -> {h['dist']}")

        # 4. turned back to the usual direction: what stands in the way is faint; Esc gives every material back
        base = await page.evaluate("() => window.__dbg.focusBase()")
        await page.evaluate("(b) => window.__dbg.focusSet({ az: b.az, el: b.el, dist: 8 })", base)
        await page.evaluate("() => window.__dbg.focusSnap()")
        await wait(page, AT_POSE, label="the camera back at the usual direction and the fade synced to it")
        u = res["usualView"] = await page.evaluate(FOCUS)
        check(failures, u["blockersNow"] >= 1 and u["blockersFaded"] == u["blockersNow"] and u["fadedOpacity"] and max(u["fadedOpacity"]) < 0.5,
              f"what blocks the usual view is drawn faint: {u}")
        await page.screenshot(path=str(out / "usual-faint-light.png"))
        await page.emulate_media(color_scheme="dark")
        await page.wait_for_timeout(600)
        await page.screenshot(path=str(out / "usual-faint-dark.png"))
        await page.emulate_media(color_scheme="light")

        # 4b. the room of a faint wall is built again (more sessions: a bigger room): the faint meshes go with their
        # room, their own materials are disposed (a shared one is not), and nothing faint is left out of the scene
        # the specimen: a faint mesh whose own material no other mesh uses (shared with another wall, taking the room
        # down disposes it anyway through that wall, and nothing could leak); turn the camera until one is faint
        # Each direction is read with the camera put at its pose (focusSnap) and the fade synced to it (AT_POSE), and the
        # frames are slow during the search, so what is read is the direction asked, however fast the machine draws.
        await page.evaluate(f"() => {{ window.__slowFrameMs = {SLOW_MS}; }}")
        info = await page.evaluate("() => window.__dbg.fadedInfo()")
        tried = []
        for step in range(24):
            if any(x["room"] and x["exclusive"] and not x["shared"] for x in info):
                break
            await page.evaluate("(a) => window.__dbg.focusSet({ az: a.az + a.k * Math.PI / 12, el: a.el })", {**base, "k": step + 1})
            await page.evaluate("() => window.__dbg.focusSnap()")
            await wait(page, AT_POSE, label=f"the camera at turn {step + 1} and the fade synced to it")
            info = await page.evaluate("() => window.__dbg.fadedInfo()")
            tried.append(len(info))
        await page.evaluate("() => { window.__slowFrameMs = 0; }")
        res["specimenTurns"] = tried
        room = next((x["room"] for x in info if x["room"] and x["exclusive"] and not x["shared"]), None)
        path = await page.evaluate("(r) => window.__dbg.projectPath(r)", room) if room else None
        check(failures, room and path, f"a faint mesh of a room with a material of its own (the specimen): {info}")
        if room and path:
            old = await page.evaluate("() => window.__dbg.markOwnMaterials()")
            for k in range(3):
                sid = f"d{k}000000-0000-4000-8000-0000000000e{k}"
                hook({"session_id": sid, "cwd": path.replace("~", str(home)) if path.startswith("~") else path,
                      "hook_event_name": "SessionStart", "source": "startup"})
            await wait(page, "(u) => u.every((x) => !window.__dbg.inScene(x))", arg=old, timeout=30000, label="the room built again")
            await page.wait_for_timeout(1500)
            marks = await page.evaluate("() => window.__dbg.disposedMarks()")
            after = await page.evaluate("() => window.__dbg.fadedInfo()")
            res["rebuilt"] = {"room": room, "path": path, "faded": info, "disposed": marks, "after": after}
            own = [x for x in info if x["uuid"] in old and not x["shared"] and x["exclusive"]]
            shared = [x for x in info if x["uuid"] in old and x["shared"]]
            check(failures, own and all(marks.get(x["uuid"]) for x in own) and not any(marks.get(x["uuid"]) for x in shared),
                  f"taking the room down disposes the faint meshes' own materials (not a shared one): {res['rebuilt']}")
            check(failures, all(x["inScene"] for x in after), f"nothing faint is left out of the scene: {after}")
        await page.keyboard.press("Escape")
        await wait(page, "() => !window.__dbg.focus().zoomed && !window.__dbg.focus().tween", label="back from the robot")
        e = res["closed"] = await page.evaluate(FOCUS)
        check(failures, e["faded"] == 0 and e["id"] is None, f"Esc: back, and nothing stays faint: {e}")

        # 5. ← → : each robot gets its own view
        await page.evaluate("(i) => window.__dbg.openRobot(i)", worst)
        await settle(page, 1500)
        await page.keyboard.press("ArrowRight")
        await page.wait_for_timeout(2500)
        n = res["next"] = await page.evaluate(FOCUS)
        check(failures, n["id"] != worst and n["chosen"] is not None and n["chosen"]["blockers"] == 0 and n["blockersNow"] == 0,
              f"→: the next robot's own view, nothing in the way: {n}")
        await page.screenshot(path=str(out / "next-dark.png"))

        # 6. a robot showing a sprite (the "!" of a permission prompt): raycasting a sprite needs the camera
        await page.keyboard.press("Escape")
        await wait(page, "() => !window.__dbg.focus().zoomed && !window.__dbg.focus().tween", label="back again")
        hook({"session_id": "c1000000-0000-4000-8000-0000000000f1", "cwd": "/work/cam-1", "hook_event_name": "Notification",
              "notification_type": "permission_prompt", "message": "Claude needs your permission"})
        await wait(page, "() => window.__dbg.robotState()['c1'] && window.__dbg.robotState()['c1'].state === 'waiting'", label="c1 waiting")
        await page.wait_for_timeout(1500)
        errors_before = len(watch.console)
        await page.evaluate("() => window.__dbg.openRobot('c1')")
        await settle(page, 1500)
        w = res["waitingRobot"] = await page.evaluate(FOCUS)
        check(failures, w["id"] == "c1" and w["chosen"] is not None and len(watch.console) == errors_before,
              f"a robot with its '!' up gets the camera too: {w}, new console lines {watch.console[errors_before:]}")
        await page.close()

        phone = await new_page(browser, watch, "focus-cam-phone", **PHONE)
        await phone.goto(url + "/")
        await ready(phone)
        await wait(phone, "() => Object.keys(window.__dbg.robotState()).length >= 24", timeout=30000, label="the phone's robots")
        await phone.wait_for_timeout(2000)
        await phone.evaluate("(i) => window.__dbg.openRobot(i)", worst)
        await settle(phone)
        res["phone"] = p = await phone.evaluate(FOCUS)
        check(failures, p["chosen"]["blockers"] == 0 and p["blockersNow"] == 0, f"390 px: nothing in the way either: {p}")
        await phone.screenshot(path=str(out / "phone-light.png"))
        await phone.close()
        for line in watch.console:
            failures.append(f"focus-cam: console: {line}")
        for u2 in watch.foreign:
            failures.append(f"focus-cam: request outside the server: {u2}")
    except Exception as ex:
        failures.append(f"focus-cam: {type(ex).__name__}: {str(ex).splitlines()[0]}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  focus-cam/camera: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "focus-cam-results.json").write_text(dump(res) + "\n")
