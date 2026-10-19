"""What animates takes its real time, however far apart the frames are (2.3.5; ticket
2026-10-19-jui-viz-walk-stretches-with-frame-gaps). On a busy machine the page draws a frame every second or more; with
the frames made 3 s apart here (the e2e's own requestAnimationFrame wrapper), each of these must end within a couple of
frames, not after the dozens of frames a per-frame step needed:

  - a pose blending into the next (0.4 s): it took 8 frames, 24 s;
  - a name tag easing to its spot (35 % of the way each 1/60 s): about 10 frames, 30 s;
  - the camera following a robot (8 % each 1/60 s): about 50 frames;
  - a game: its clock starts in the frame the second player reaches its spot (it took two frames more: one to say
    'playing', one for the game's clock; ticket 2026-10-20-jui-viz-arrivals-and-rolls-wait-for-frames), counted in
    frames (waits.frame_log_js).

The walk is measured in props.py and breaks.py ("ten again").
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, dump, new_page
from waits import frame_log_js, settled, until

A = "e2e00000-0000-4000-8000-0000000005a1"
PLAYERS = ("e2e00000-0000-4000-8000-0000000005a2", "e2e00000-0000-4000-8000-0000000005a3")
CWD = "/work/frame-gaps"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
SLOW_RAF = """(() => { const raf = window.requestAnimationFrame.bind(window);
  window.requestAnimationFrame = (cb) => { const ms = window.__slowFrameMs || 0; return ms ? setTimeout(() => raf(cb), ms) : raf(cb); }; })()"""
SLOW_MS = int(os.environ.get("FG_SLOW_MS", "3000"))   # the arm runs at 3 s; set FG_SLOW_MS to measure at other gaps
MAX_SEC = 12          # a few frames at 3 s; the per-frame steps took 24 s and more
READY = "() => !!(window.__dbg && window.__dbg.robots && document.body.dataset.mode === 'live')"
PLAY_LOG_JS = frame_log_js(
    "() => { const p = window.__dbg.play(), g = p.list[0]; return { started: !!(g && g.started),"
    " paths: g ? g.players.map((id) => (p.robots.find((x) => x.id === id) || {}).path) : null }; }",
    "() => window.__dbg.play().list.some((g) => g.started)")
WHY = "() => ({ settle: window.__dbg.settleInfo(), cam: window.__dbg.camFollowGap() })"


def check(failures, cond, text):
    if not cond:
        failures.append(f"frame-gaps: {text}")


async def run_frame_gaps(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "frame-gaps"
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

    def hook(sid=A, **payload):
        body = {"session_id": sid, "cwd": CWD, "permission_mode": "default", **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(),
                       capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)

    async def timed(page, js, name, arg=None):
        """Seconds until `js` holds, with the frames SLOW_MS apart (the wait's own cap is 60 s)."""
        t = time.monotonic()
        await until(page, js, name, arg=arg, timeout=60000, why=WHY)
        return round(time.monotonic() - t, 1)

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
        page = await new_page(browser, watch, "frame-gaps", **DESKTOP)
        await page.add_init_script(SLOW_RAF)
        await page.goto(url + "/")
        await until(page, READY, "the page is up", timeout=30000)
        hook(hook_event_name="SessionStart", source="startup")
        await until(page, "() => window.__dbg.robots.length === 1", "the robot", why=WHY)
        await settled(page, "the robot at its desk", timeout=30000)
        rid = await page.evaluate("() => window.__dbg.robots[0].def.id")

        # 1. a pose blending into the next
        await page.evaluate(f"() => {{ window.__slowFrameMs = {SLOW_MS}; }}")
        t = time.monotonic()
        hook(hook_event_name="UserPromptSubmit", prompt="直して")
        hook(hook_event_name="PreToolUse", tool_name="Edit", tool_use_id="toolu_fg", tool_input={"file_path": f"{CWD}/a.py", "old_string": "a", "new_string": "b"})
        await until(page, "(i) => { const x = window.__dbg.settleInfo([i])[0]; return x.state === 'typing' && x.blend >= 1; }", "typing, the pose blended in",
                    arg=rid, timeout=60000, why=WHY)
        res["blendSec"] = round(time.monotonic() - t, 1)
        check(failures, res["blendSec"] < MAX_SEC, f"with frames {SLOW_MS} ms apart, a pose blends in about its real time: {res['blendSec']} s")

        # 2. a name tag easing to its spot (moved 40 px off it)
        await page.evaluate("() => { const R = window.__dbg.robots[0]; R.tagDy = (R.tagTarget || 0) + 40; }")
        res["tagSec"] = await timed(page, "(i) => window.__dbg.settleInfo([i])[0].tag === 0", "the tag back at its spot", arg=rid)
        check(failures, res["tagSec"] < MAX_SEC, f"with frames {SLOW_MS} ms apart, a tag eases to its spot in about its real time: {res['tagSec']} s")

        # 3. the camera following the robot (turned away from it)
        await page.evaluate("() => { window.__slowFrameMs = 0; }")
        await page.evaluate("(i) => window.__dbg.openRobot(i)", rid)
        await until(page, "() => { const f = window.__dbg.focus(); return f.zoomed && !f.tween; }", "the camera on the robot", why=WHY)
        await until(page, "() => window.__dbg.camFollowGap() < 0.05", "the camera settled on the robot", timeout=30000, why=WHY)
        await page.evaluate(f"() => {{ window.__slowFrameMs = {SLOW_MS}; const b = window.__dbg.focusBase(); window.__dbg.focusSet({{ az: b.az + 1.2, el: b.el }}); }}")
        res["gapBefore"] = await page.evaluate("() => window.__dbg.camFollowGap()")
        res["camSec"] = await timed(page, "() => window.__dbg.camFollowGap() < 0.05", "the camera caught up")
        check(failures, res["gapBefore"] > 1 and res["camSec"] < MAX_SEC,
              f"with frames {SLOW_MS} ms apart, the camera follows in about its real time: {res['camSec']} s (from {res['gapBefore']})")
        await page.evaluate("() => { window.__slowFrameMs = 0; }")

        # 4. a game: two idle robots walk to their spots; it starts in the frame the second arrives
        for sid in PLAYERS:
            hook(sid, hook_event_name="SessionStart", source="startup")
        await until(page, "() => window.__dbg.robots.length === 3", "the two players", why=WHY)
        await settled(page, "the players at their desks", timeout=30000)
        await page.evaluate(f"() => {{ window.__slowFrameMs = {SLOW_MS}; }}")
        await page.evaluate(PLAY_LOG_JS, None)
        await page.evaluate("() => window.__dbg.play({ kinds: ['ball'], p: 1, idleMs: 0, restMinSec: 0, restMaxSec: 0, minSec: 60, maxSec: 60 })")
        await until(page, "() => window.__dbg.play().list.some((g) => g.started)", "the game started", timeout=60000, why=WHY)
        await page.evaluate("() => { window.__slowFrameMs = 0; }")
        rows = res["playRows"] = await page.evaluate("() => window.__frameRows")
        waited = [r for r in rows if r["paths"] and all(x == 0 for x in r["paths"]) and not r["started"]]
        walked = [r for r in rows if r["paths"] and any(x for x in r["paths"])]
        check(failures, walked and not waited and rows[-1]["started"],
              f"with frames {SLOW_MS} ms apart, the game starts in the frame the players arrive: {len(waited)} frames between, {len(walked)} walking")
        await page.evaluate("() => window.__dbg.play({ p: 0, endAll: true })")
        await page.close()
        for line in watch.console:
            failures.append(f"frame-gaps: console: {line}")
        for u in watch.foreign:
            failures.append(f"frame-gaps: request outside the server: {u}")
    except Exception as e:
        failures.append(f"frame-gaps: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  frame-gaps: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "frame-gaps-results.json").write_text(dump(res) + "\n")
