"""What background work looks like (2.3.5, requester 10-19: "バックグラウンドで作業中のロボットの動作がないから少しただの待機との
見分けがつきにくい バックグランドで作業の場合はヘッドセットつけて、音符出してる状態で机の上でパソコンをゆるめにいじってほしい。").

The real `jui viz serve` in a throwaway HOME on a free port, the real forward.py for three sessions in one room: one idle,
one typing (an Edit under way), one waiting on background work (a Stop with background_tasks). Measured from the page's
own objects (window.__dbg.bgLook / poseStats):

  - the headset and the notes only on the background robot, the laptop under its hands; none on the idle or the typing one;
  - the notes rise (their positions change) and there are never more than NOTE_MAX sprites a robot, however long it runs;
  - its keystrokes: a swing above zero and below typing's, fewer strokes a second than typing's; its arm moves on screen;
  - it never starts a game, a nap, a bento or a break, while the idle robot in the same room does (the same rules let it);
  - when the background work ends (a Stop without it), the headset and the notes are gone;
  - under reduced motion the notes stand still (still shown: a still picture tells it apart).

Screenshots (light and dark): the room up close with the three side by side, and the background robot's own view.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, dump, new_page, ready

IDLE = "e2e00000-0000-4000-8000-0000000002a1"
WORK = "e2e00000-0000-4000-8000-0000000002a2"
BACK = "e2e00000-0000-4000-8000-0000000002a3"
CWD = "/work/bg-look"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
NOTE_MAX = 3
BG_TASKS = [{"id": "bash_1", "type": "bash"}]
LOOK = "() => window.__dbg.bgLook()"
# The background robot's left arm on every frame for `dur` ms (what is on screen, not the pose function).
ARM = """async ([id, dur]) => { const R = window.__dbg.robots.find((x) => x.def.id === id), out = [], t0 = performance.now();
  while (performance.now() - t0 < dur) { await new Promise((r) => requestAnimationFrame(r)); out.push(R.robot.armL.rotation.x); }
  return out; }"""


def check(failures, cond, text):
    if not cond:
        failures.append(f"bg-look: {text}")


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=100)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def run_bg_look(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "bg-look"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT,
                           env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def hook(sid, **payload):
        body = {"session_id": sid, "cwd": CWD, "permission_mode": "default", **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(),
                       capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)

    def to_background():
        hook(BACK, hook_event_name="UserPromptSubmit", prompt="ビルドを裏で回す")
        hook(BACK, hook_event_name="Stop", background_tasks=BG_TASKS)

    async def labels(page):
        return await page.evaluate("(ids) => Object.fromEntries(ids.map((s) => [s, (window.__dbg.robots.find((R) => R.def.sessionId === s) || { def: {} }).def.id]))",
                                   [IDLE, WORK, BACK])

    def of(look, label):
        return next((x for x in look if x["id"] == label), None)

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
        page = await new_page(browser, watch, "bg-look", **DESKTOP)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", label="connected")
        for sid in (IDLE, WORK, BACK):
            hook(sid, hook_event_name="SessionStart", source="startup")
        await wait(page, "() => window.__dbg.play().robots.length >= 3", label="three robots")
        await wait(page, "() => window.__dbg.play().robots.every((x) => x.path === 0 && x.x === x.seat[0] && x.z === x.seat[1])", timeout=30000, label="seated")
        await page.evaluate("() => { window.__dbg.play({ p: 0, solo: { p: 0 } }); window.__dbg.brk({ p: { smoke: 0, vend: 0 } }); }")
        ids = res["ids"] = await labels(page)
        hook(WORK, hook_event_name="UserPromptSubmit", prompt="直して")
        hook(WORK, hook_event_name="PreToolUse", tool_name="Edit", tool_use_id="toolu_bg_edit", tool_input={"file_path": f"{CWD}/a.py", "old_string": "a", "new_string": "b"})
        to_background()
        await wait(page, "(i) => { const L = window.__dbg.bgLook(); return L.find((x) => x.id === i.b).state === 'background' && L.find((x) => x.id === i.w).state === 'typing'; }",
                   arg={"b": ids[BACK], "w": ids[WORK]}, label="one typing, one in the background")
        await page.wait_for_timeout(800)
        look = res["on"] = await page.evaluate(LOOK)
        b, w, i = of(look, ids[BACK]), of(look, ids[WORK]), of(look, ids[IDLE])
        check(failures, b["headset"] and b["laptop"] and 1 <= len(b["notes"]) <= NOTE_MAX and b["noteSprites"] == NOTE_MAX,
              f"the background robot wears the headset, has notes over it and a laptop: {b}")
        check(failures, not w["headset"] and not w["notes"] and not i["headset"] and not i["notes"],
              f"the typing and the idle robot have no headset and no notes: {w} {i}")
        # the notes rise
        later = of(await page.evaluate(LOOK), ids[BACK])
        await page.wait_for_timeout(1200)
        later2 = of(await page.evaluate(LOOK), ids[BACK])
        check(failures, later["notes"] != later2["notes"], f"the notes move: {later['notes']} -> {later2['notes']}")
        # the keystrokes: looser than typing, but there
        stats = res["poseStats"] = await page.evaluate("() => ({ bg: window.__dbg.poseStats('background'), typing: window.__dbg.poseStats('typing') })")
        check(failures, 0 < stats["bg"]["swing"] < stats["typing"]["swing"] * 0.6 and 0 < stats["bg"]["strokesPerSec"] < stats["typing"]["strokesPerSec"] * 0.6,
              f"background typing is smaller and slower than typing, and not still: {stats}")
        arm = await page.evaluate(ARM, [ids[BACK], 3000])
        res["armRange"] = round(max(arm) - min(arm), 4) if arm else None
        check(failures, arm and max(arm) - min(arm) > 0.005, f"its arm moves on screen: range {res['armRange']} over {len(arm)} frames")

        # no game, nap, bento or break while in the background; the idle robot in the room does go (the same rules let it)
        await page.evaluate("() => { window.__dbg.play({ idleMs: 500, p: 1, restMinSec: 0, restMaxSec: 0, solo: { p: 1, minSec: 3, maxSec: 3 } }); "
                            "window.__dbg.brk({ p: { smoke: 1, vend: 1 }, restMinSec: 0, restMaxSec: 0 }); }")
        seen, idle_went = [], False
        for _ in range(24):
            await page.wait_for_timeout(500)
            L = await page.evaluate(LOOK)
            bb, ii = of(L, ids[BACK]), of(L, ids[IDLE])
            seen.append(bb["play"] or bb["brk"] or bb["solo"])
            idle_went = idle_went or ii["play"] or ii["brk"] or ii["solo"]
        res["noPlay"] = {"bgWent": any(seen), "idleWent": idle_went}
        check(failures, not any(seen), f"the background robot never goes to a game, a nap, a bento or a break: {seen}")
        check(failures, idle_went, "the idle robot in the same room does go (else the arm above proves nothing)")
        await page.evaluate("() => { window.__dbg.play({ p: 0, endAll: true, solo: { p: 0 } }); window.__dbg.brk({ p: { smoke: 0, vend: 0 }, endAll: true }); }")
        await wait(page, "() => window.__dbg.play().robots.every((x) => !x.back && x.path === 0 && !x.solo)", timeout=60000, label="everyone back at a desk")

        # the cap: still NOTE_MAX sprites a robot after a while, and no stray note in the scene
        await page.wait_for_timeout(2000)
        cap = res["cap"] = await page.evaluate("""() => { const D = window.__dbg, scene = D.robots[0].robot.root.parent; let n = 0;
          scene.traverse((o) => { if (o.isSprite && o.parent && o.parent.userData.notes) n += 1; });
          return { sprites: n, perRobot: D.bgLook().map((x) => x.noteSprites) }; }""")
        check(failures, cap["sprites"] <= NOTE_MAX * sum(1 for x in cap["perRobot"] if x) and max(cap["perRobot"]) == NOTE_MAX,
              f"never more than {NOTE_MAX} note sprites a robot: {cap}")

        # pictures: the room up close, the three side by side; the background robot's own view
        room = await page.evaluate("(i) => window.__dbg.robots.find((R) => R.def.id === i).def.room", ids[BACK])
        await page.click(f".tag.room[data-set-project='{room}']")
        await wait(page, f"() => window.__dbg.solo() === '{room}'", label="the room up close")
        await page.wait_for_timeout(1500)
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await page.wait_for_timeout(700)
            await page.screenshot(path=str(out / f"room-{scheme}.png"))
        await page.emulate_media(color_scheme="light")
        await page.evaluate("(i) => window.__dbg.openRobot(i)", ids[BACK])
        await wait(page, "() => { const f = window.__dbg.focus(); return f.zoomed && !f.tween; }", label="the camera on the background robot")
        await page.wait_for_timeout(2500)
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await page.wait_for_timeout(700)
            await page.screenshot(path=str(out / f"closeup-{scheme}.png"))
        await page.emulate_media(color_scheme="light")
        await page.keyboard.press("Escape")
        await wait(page, "() => !window.__dbg.focus().zoomed && !window.__dbg.focus().tween", label="back from the robot")
        await page.click("#room-back")

        # the background work ends: off with the headset and the notes
        hook(BACK, hook_event_name="Stop")
        await wait(page, "(i) => window.__dbg.bgLook().find((x) => x.id === i).state !== 'background'", arg=ids[BACK], label="the background work over")
        await page.wait_for_timeout(600)
        off = res["off"] = of(await page.evaluate(LOOK), ids[BACK])
        check(failures, not off["headset"] and not off["notes"], f"after the background work: no headset, no notes: {off}")

        # reduced motion: the notes stand still (and are shown)
        quiet = await new_page(browser, watch, "bg-look-reduced", reduced_motion="reduce", **DESKTOP)
        await quiet.goto(url + "/")
        await ready(quiet)
        to_background()
        await wait(quiet, "(i) => { const x = window.__dbg.bgLook().find((y) => y.id === i); return x && x.state === 'background' && x.notes.length > 0; }",
                   arg=ids[BACK], timeout=30000, label="background again, reduced motion")
        n1 = of(await quiet.evaluate(LOOK), ids[BACK])
        await quiet.wait_for_timeout(1500)
        n2 = of(await quiet.evaluate(LOOK), ids[BACK])
        res["reduced"] = {"before": n1["notes"], "after": n2["notes"], "headset": n2["headset"]}
        check(failures, n2["headset"] and n1["notes"] and n1["notes"] == n2["notes"], f"reduced motion: the notes are shown and stand still: {res['reduced']}")
        await quiet.close()
        await page.close()
        for line in watch.console:
            failures.append(f"bg-look: console: {line}")
        for u in watch.foreign:
            failures.append(f"bg-look: request outside the server: {u}")
    except Exception as e:
        failures.append(f"bg-look: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  bg-look: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "bg-look-results.json").write_text(dump(res) + "\n")
