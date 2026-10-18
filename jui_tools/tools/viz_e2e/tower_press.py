"""A window pressed in the building opens THAT room, on the real `jui viz serve --replay` (requester, 10-18).

The report: "ビルの窓タップした時に部屋に移動するけど、タップした部屋じゃなくてその前に開いてた部屋になる".
towerHit kept the floor and dropped the bay, and towerLeave flew to the room picked before.

Fed hooks.tower_rooms(): seven rooms, so the building has two floors. With room A open, the building is entered
and a window is pressed with the mouse (a real pointerdown / pointerup on the canvas, at a point where the canvas is
the element on top): room B on the other floor, room C on A's floor, and an empty window (the whole floor).
"""

from __future__ import annotations

import json
import pathlib

import hooks
from common import DESKTOP, LAUNCH_ARGS, Watch, new_page, ready


def check(failures, cond, text):
    if not cond:
        failures.append(f"tower: {text}")


async def wait(page, js, timeout=30000, label=""):
    try:
        await page.wait_for_function(js, timeout=timeout, polling=100)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


# The point of the canvas, scanned over a grid, where the building shows the window wanted (a project id, or
# null for an empty window on floor k), the canvas being the element on top there.
FIND_JS = """([want, floor]) => {
  const c = document.getElementById('scene-canvas'), r = c.getBoundingClientRect();
  const hits = [];
  for (let y = r.top + 6; y < r.bottom - 6; y += 6) for (let x = r.left + 6; x < r.right - 6; x += 6) {
    const h = window.__dbg.towerAt(x, y);
    if (!h || (floor !== null && h.k !== floor) || h.project !== want) continue;
    if (document.elementFromPoint(x, y) !== c) continue;
    hits.push([x, y]);
  }
  if (!hits.length) return null;
  return hits[Math.floor(hits.length / 2)];
}"""

IN_TOWER = "() => window.__dbg.floors().tower === true"
STILL = """() => { const p = window.__dbg.camera.position; const k = [p.x, p.y, p.z].map((v) => v.toFixed(2)).join();
  const same = window.__still === k; window.__still = k; return same; }"""


async def press(page, want, floor, label, failures):
    await page.evaluate("() => window.__dbg.tower(true)")
    await wait(page, IN_TOWER, label=f"{label}: in the building")
    await page.wait_for_timeout(300)
    await wait(page, STILL, label=f"{label}: the camera has stopped")
    point = await page.evaluate(FIND_JS, [want, floor])
    check(failures, point is not None, f"{label}: no window of {want!r} on floor {floor} to press")
    if point is None:
        return False
    await page.mouse.click(point[0], point[1])
    await wait(page, "() => window.__dbg.floors().tower === false", label=f"{label}: out of the building")
    await page.wait_for_timeout(300)
    await wait(page, STILL, label=f"{label}: the camera has stopped")
    return True


async def run_tower_press(pw, out, failures, RealServer):
    out = pathlib.Path(out) / "tower"
    out.mkdir(parents=True, exist_ok=True)
    rec = hooks.write(hooks.tower_rooms(), out / "tower.record.jsonl")
    res: dict = {}
    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    srv = None
    try:
        srv = RealServer(rec, out / "home", speed=1.0)
        page = await new_page(browser, Watch(origin=srv.url), "tower", **DESKTOP)
        await page.goto(srv.url + "/")
        await ready(page)
        await wait(page, "() => window.__dbg.floors().floors.length >= 2 && window.__dbg.floors().floors[1].length >= 1",
                   label="two floors")
        floors = (await page.evaluate("() => window.__dbg.floors()"))["floors"]
        a, c = floors[0][0], floors[0][1]
        b = floors[1][0]
        res["floors"] = [len(f) for f in floors]

        await page.click(f'[data-set-project="{a}"] >> nth=0')
        await wait(page, f"() => window.__dbg.solo() === '{a}'", label="room A alone")

        if await press(page, b, 1, "B on 2F", failures):
            got = await page.evaluate("() => [window.__dbg.project(), window.__dbg.solo(), window.__dbg.floors().floor]")
            res["pressB"] = got
            check(failures, got == [b, b, 1], f"pressing room B's window on 2F opened {got}, not [{b}, {b}, 1] (A was {a})")
            await page.screenshot(path=str(out / "pressed-b.png"))

        if await press(page, c, 0, "C on 1F", failures):
            got = await page.evaluate("() => [window.__dbg.project(), window.__dbg.solo(), window.__dbg.floors().floor]")
            res["pressC"] = got
            check(failures, got == [c, c, 0], f"pressing room C's window on 1F opened {got}, not [{c}, {c}, 0]")

        if await press(page, None, 1, "empty on 2F", failures):
            got = await page.evaluate("() => [window.__dbg.project(), window.__dbg.solo(), window.__dbg.floors().floor]")
            res["pressEmpty"] = got
            check(failures, got == ["all", None, 1], f"pressing an empty window on 2F opened {got}, not ['all', None, 1]")
            await page.screenshot(path=str(out / "pressed-empty.png"))
    finally:
        if srv is not None:
            srv.stop()
        await browser.close()
    (out / "tower-results.json").write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n")
    return res
