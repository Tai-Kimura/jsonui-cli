"""Robots' name tags kept apart (10-19): two robots close by must not hide each other's tag.

The real `jui viz serve` in a throwaway HOME on a free port, four sessions in one room through the real forward.py.
Two robots are moved next to each other (one behind the other, then side by side) on the floor view and in the room
up close, and two are sent to play (their spot is 1.6 m apart): every visible tag's screen rect crosses no other and
each still shows its robot's label. placeRobotTags' cost per frame is read and kept under budget. Pictures before /
after, light and dark (`--jt` takes the before ones from another tree; the robots are moved through window.__dbg.robots,
which both trees have).
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, new_page, ready

CWD = "/work/tags-app"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
SID = "e2e00000-0000-4000-8000-0000000003{:02x}"
BUDGET_MS = 1.0   # placeRobotTags per frame, mean (software GL machine)

# Move robot i to (x, z) and keep it there (no path); the room's seat of robot 0 is the anchor.
MOVE_JS = """([moves]) => { const rs = window.__dbg.robots; const a = rs[0].robot.root.position;
  const base = [a.x, a.z]; moves.forEach(([i, dx, dz]) => { const R = rs[i]; R.path = []; R.robot.root.position.x = base[0] + dx; R.robot.root.position.z = base[1] + dz; }); }"""
# Every visible robot tag's rect, from the page itself (works on a tree without __dbg.tags).
RECTS_JS = """() => window.__dbg.robots.filter((R) => R.tag.style.visibility !== 'hidden' && !R.tag.hidden && !document.getElementById('tags').hidden)
  .map((R) => { const b = R.tag.getBoundingClientRect(); return { id: R.def.id, text: R.tag.textContent, x0: b.left, x1: b.right, y0: b.top, y1: b.bottom }; })"""


def check(failures, cond, text):
    if not cond:
        failures.append(f"name-tags: {text}")


async def wait(page, js, timeout=20000, label=""):
    try:
        await page.wait_for_function(js, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


def crossings(rects):
    out = []
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            if a["x0"] < b["x1"] - 0.5 and b["x0"] < a["x1"] - 0.5 and a["y0"] < b["y1"] - 0.5 and b["y0"] < a["y1"] - 0.5:
                out.append((a["id"], b["id"]))
    return out


async def run_name_tags(pw, out, failures, jt=None, shots_only=False):
    from run import free_port
    name = "name-tags-before" if shots_only else "name-tags"
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
        await page.emulate_media(color_scheme="light", reduced_motion="no-preference")
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", label="connected")
        for i in range(4):
            hook(SID.format(i), hook_event_name="SessionStart", source="startup")
            hook(SID.format(i), hook_event_name="PreToolUse", tool_name="Read", tool_use_id=f"r{i}",
                 tool_input={"file_path": f"/work/tags-app/a-long-file-name-number-{i}.json"})   # a long act: wide tags
        await wait(page, "() => window.__dbg.robots.length >= 4 && window.__dbg.robots.every((R) => !R.path.length)", timeout=30000, label="seated")
        room_id = await page.evaluate("() => window.__dbg.robots[0].def.room")

        async def measure(label, moves, shot=None):
            await page.evaluate(MOVE_JS, [moves])
            await page.wait_for_timeout(900)   # the eased move settles
            rects = await page.evaluate(RECTS_JS)
            res[label] = {"rects": rects, "cross": crossings(rects)}
            if shot:
                await page.screenshot(path=str(out / shot))
            return rects

        close = [(1, 0.3, -1.0), (2, 0.9, 0.2), (3, -0.5, -0.4)]   # three robots within a metre or so of robot 0
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            tag = "before" if shots_only else "after"
            await measure(f"floor-{scheme}", close, f"{tag}-floor-{scheme}.png")
            await page.click(f".tag.room[data-set-project='{room_id}']")
            await wait(page, f"() => window.__dbg.solo() === '{room_id}'", label="one room")
            await wait(page, "() => window.__dbg.robots.every((R) => !R.path.length)", timeout=30000, label="settled up close")
            await measure(f"room-{scheme}", close, f"{tag}-room-{scheme}.png")
            await page.click("#room-back")
            await wait(page, "() => window.__dbg.solo() === null", label="back")
            await wait(page, "() => window.__dbg.robots.every((R) => !R.path.length)", timeout=30000, label="settled on the floor")
        if shots_only:
            return
        await page.emulate_media(color_scheme="light")

        for label in ("floor-light", "room-light", "floor-dark", "room-dark"):
            r = res[label]
            check(failures, len(r["rects"]) == 4 and not r["cross"], f"{label}: four tags, none crossing: {r['cross']} {[(x['id'], round(x['x0']), round(x['y0'])) for x in r['rects']]}")
            check(failures, all(x["text"].startswith(x["id"]) for x in r["rects"]), f"{label}: each tag still shows its robot: {[x['text'][:12] for x in r['rects']]}")
        # side by side, one exactly behind the other: the hardest two
        rects = await measure("behind", [(1, 0.0, -0.8), (2, 0.25, 0.0), (3, -0.25, 0.0)])
        check(failures, not res["behind"]["cross"], f"right behind / side by side: {res['behind']['cross']}")
        # at play: two robots at their spot
        hook(SID.format(0), hook_event_name="Stop")
        hook(SID.format(1), hook_event_name="Stop")
        await page.evaluate("() => window.__dbg.play({ idleMs: 0, p: 1, minSec: 30, maxSec: 30, restMinSec: 600, restMaxSec: 600 })")
        await wait(page, "() => window.__dbg.play().list.some((g) => g.started)", timeout=40000, label="a game")
        await page.wait_for_timeout(1200)
        rects = await page.evaluate(RECTS_JS)
        res["play"] = {"rects": rects, "cross": crossings(rects)}
        check(failures, not res["play"]["cross"], f"at play: {res['play']['cross']}")
        await page.screenshot(path=str(out / "after-play-light.png"))
        # the cost
        await page.evaluate("() => window.__dbg.tagStats(true)")
        await page.wait_for_timeout(3000)
        st = res["cost"] = await page.evaluate("() => window.__dbg.tagStats(false)")
        check(failures, st["frames"] > 20 and st["meanMs"] < BUDGET_MS, f"placeRobotTags under {BUDGET_MS} ms a frame on average: {st}")
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
    print(f"  {name}: {time.monotonic() - t0:.0f}s cost {res.get('cost')}", flush=True)
