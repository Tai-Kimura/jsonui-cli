"""The open card's robot moves to another room, and the view follows it (ticket
2026-10-21-jui-viz-camera-does-not-follow-robot-walking-rooms). Runs with `--only camera-follow`.

The real `jui viz serve` in a throwaway HOME on a free port and the real forward.py: three sessions in two projects
(A: a1, a2, a3; B: b1). A session moves with a CwdChanged hook, as Claude Code sends it. Checked, in order:
  * A shown (one room), a1's card open, a1 moves to B: B shown, a1's card open, the camera on a1, and a toast says so
  * right after a switch by hand (a2 picked while B is shown, as a talk's ロボットへ移る does), a2 moves to B: nothing moves — A shown, a2's card open with the
    mark "… へ移った"; its button goes to B, the camera on a2
  * A shown, a3's card open, a3 — the last robot in A — moves to B: A closes, the floor is shown (30-source-live.js), B
    is in view there, so nothing more moves: a3's card open, the camera on it, no mark
  * the whole floor shown, b1's card open, b1 moves to A (a room in view): the floor still shown, no toast of its own,
    the camera on b1 where it walked, and the card names its new room
No console error; nothing outside the server.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, ISOLATE, LAUNCH_ARGS, T, T_pattern, Watch, dump, new_page, ready

SIDS = {"a1": "e2e00000-0000-4000-8000-0000000000f1", "a2": "e2e00000-0000-4000-8000-0000000000f2",
        "a3": "e2e00000-0000-4000-8000-0000000000f4", "b1": "e2e00000-0000-4000-8000-0000000000f3"}
CWD_A, CWD_B = "/work/follow-a", "/work/follow-b"
CWDS = {"a1": CWD_A, "a2": CWD_A, "a3": CWD_A, "b1": CWD_B}
HAND_MS = 3000   # 50-panel.js FOLLOW_HAND_MS
STATE = "() => ({ robot: window.__dbg.board().robot, project: window.__dbg.project(), card: !document.getElementById('rb').hidden })"
ON_ROBOT = "() => { const c = window.__dbg.camOn(); return !c.tween && !c.waitFor && c.zoomed && c.inScene && c.toRobot !== null && c.toRobot < 1.5; }"


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def run_camera_follow(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "camera-follow"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log,
                           stderr=subprocess.STDOUT, env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"
    res: dict = {"steps": []}

    def check(cond, text):
        if not cond:
            failures.append(f"camera-follow: {text}")

    def hook(k, cwd=None, **payload):
        subprocess.run([sys.executable, "-I", "-S", str(forward)], timeout=10, capture_output=True, env=dict(base_env, HOME=str(home)),
                       input=json.dumps({"session_id": SIDS[k], "cwd": cwd or CWDS[k], "transcript_path": "/work/none.jsonl",
                                         "permission_mode": "default", **payload}).encode())

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
        for k in SIDS:
            hook(k, hook_event_name="SessionStart", source="startup")
        watch = Watch(origin=url)
        page = await new_page(browser, watch, "camera-follow", **DESKTOP)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelectorAll('#sessions [data-robot-open]').length >= 4", label="four sessions")
        who = await page.evaluate("(sids) => Object.fromEntries(Object.entries(sids).map(([k, sid]) => [k, window.__dbg.labelOfSession(sid)]))", SIDS)
        proj = await page.evaluate("(ls) => Object.fromEntries(Object.entries(ls).map(([k, l]) => [k, window.__dbg.robotProject(l)]))", who)
        res["who"], res["proj"] = who, proj
        A, B = proj["a1"], proj["b1"]
        check(A and B and A != B and proj["a2"] == A and proj["a3"] == A, f"two projects: a1, a2 and a3 in one, b1 in the other: {proj}")
        name = await page.evaluate("(ids) => ids.map((id) => window.__dbg.projectName(id))", [A, B])

        async def pick_project(pid):
            await page.click("[data-scope-btn]")
            await page.click(f"#pop [data-pick-project='{pid}']")
            await wait(page, "(p) => window.__dbg.project() === p", arg=pid, label=f"project {pid}")
            await page.wait_for_timeout(700)

        async def open_robot(k):
            await page.click(f"#sessions [data-robot-open='{who[k]}']")
            await wait(page, "(l) => window.__dbg.board().robot === l && !document.getElementById('rb').hidden", arg=who[k], label=f"{k}'s card")

        async def moved_to(k, cwd):
            hook(k, cwd=cwd, hook_event_name="CwdChanged")
            want = B if cwd == CWD_B else A
            await wait(page, "([l, p]) => window.__dbg.robotProject(l) === p", arg=[who[k], want], label=f"{k} in {want}")

        async def step(label, want_robot, want_project):
            got = await page.evaluate(STATE)
            fol = await page.evaluate("() => window.__dbg.follow()")
            cam = await page.evaluate("() => window.__dbg.camOn()")
            res["steps"].append({"step": label, **got, "follow": fol, "cam": cam})
            want = {"robot": who[want_robot], "project": want_project, "card": True}
            check(got == want, f"{label}: {want} expected, got {got}")
            return fol, cam

        # B: the one-room view of A, a1's card open, a1 moves to B (out of the view)
        await pick_project(A)
        await open_robot("a1")
        await wait(page, ON_ROBOT, label="the camera on a1")
        await page.wait_for_timeout(HAND_MS + 500)   # longer ago than a switch by hand
        await moved_to("a1", CWD_B)
        await wait(page, "(p) => window.__dbg.project() === p", arg=B, label="the view follows a1 to B")
        await wait(page, ON_ROBOT, label="the camera on a1 in B")
        fol, cam = await step("one room A, a1's card open, a1 moves to B: B, a1, the camera on it", "a1", B)
        check(fol["toast"] == T("panel.rb.follow.moved.toast", id=who['a1'], room=name[1]), f"the toast says it followed: {fol['toast']!r}")
        check(not fol["moved"] and not await page.locator("#rb [data-rb-moved]").count(), f"no mark when it followed: {fol}")
        await page.screenshot(path=str(out / "followed-to-b.png"))

        # right after a switch by hand: the card is marked, nothing moves; its button goes there. a2 is picked while B is
        # shown (as a talk's ロボットへ移る does: selectRobot), so the view switches to A by hand, and a2 moves at once
        await page.evaluate("(l) => window.__dbg.selectRobot(l)", who["a2"])
        await wait(page, "([l, p]) => window.__dbg.board().robot === l && window.__dbg.project() === p", arg=[who["a2"], A], label="a2's card in A")
        hook("a2", cwd=CWD_B, hook_event_name="CwdChanged")
        try:
            await wait(page, "() => !!document.querySelector('#rb [data-rb-moved]')", label="a2's card marked")
        finally:
            res["afterHand"] = {**await page.evaluate(STATE), "follow": await page.evaluate("() => window.__dbg.follow()"),
                                "sinceHand": await page.evaluate("() => Date.now() - window.__dbg.follow().handAt")}
        fol, cam = await step("A picked by hand just before, a2 moves to B: A still, a2's card marked", "a2", A)
        mark = (await page.locator("#rb [data-rb-moved]").inner_text()).strip()
        check(mark.startswith(T("panel.rb.follow.moved", room=name[1])), f"the mark names where it went: {mark!r}")
        check(not T_pattern("panel.rb.follow.moved.toast").search(fol["toast"] or ""), f"no follow toast: {fol['toast']!r}")
        await page.click("#rb [data-rb-moved-go]")
        await wait(page, "(p) => window.__dbg.project() === p", arg=B, label="the mark's button goes to B")
        await wait(page, ON_ROBOT, label="the camera on a2 in B")
        await step("the mark's button: B, a2, the camera on it", "a2", B)
        check(not await page.locator("#rb [data-rb-moved]").count(), "the mark is gone after going there")

        # the last robot leaves the room shown: the room closes, the floor is shown and B is in view there
        await pick_project(A)
        await open_robot("a3")
        await wait(page, ON_ROBOT, label="the camera on a3")
        await page.wait_for_timeout(HAND_MS + 500)
        await moved_to("a3", CWD_B)
        await wait(page, "() => window.__dbg.project() === 'all'", label="A closed: the floor shown")
        await wait(page, "([l, p]) => { const r = window.__dbg.robotAt(l); return !!r && r.room === p && !r.walking; }",
                   arg=[who["a3"], B], timeout=30000, label="a3 at its seat in B")
        await wait(page, ON_ROBOT, timeout=30000, label="the camera on a3 after its walk")
        fol, cam = await step("A shown, a3 (the last in A) moves to B: the floor, a3's card, the camera on it", "a3", "all")
        check(not fol["moved"], f"no mark: B is in view on the floor: {fol}")

        # A: the whole floor, b1's card open, b1 moves to A (a room in view): it walks there and the camera follows
        await pick_project("all")
        await open_robot("b1")
        await wait(page, ON_ROBOT, label="the camera on b1")
        await page.wait_for_timeout(HAND_MS + 500)
        toast_before = (await page.evaluate("() => window.__dbg.follow()"))["toast"]
        await moved_to("b1", CWD_A)
        # it walks through the doors to its seat in A
        await wait(page, "([l, p]) => { const r = window.__dbg.robotAt(l); return !!r && r.room === p && !r.walking; }",
                   arg=[who["b1"], A], timeout=30000, label="b1 at its seat in A")
        await wait(page, ON_ROBOT, timeout=30000, label="the camera on b1 after its walk")
        fol, cam = await step("the floor, b1's card open, b1 moves to A: the floor still, the camera on b1", "b1", "all")
        check(fol["toast"] == toast_before, f"no toast of its own when it stays in view: {fol['toast']!r}")
        sub = (await page.locator("#rb .rb-sub").inner_text()).strip()
        check(sub.endswith(name[0]), f"the card names its new room {name[0]}: {sub!r}")
        await page.screenshot(path=str(out / "floor-b1-in-a.png"))
        await page.close()
        for line in watch.console:
            failures.append(f"camera-follow: console: {line}")
        for u in watch.foreign:
            failures.append(f"camera-follow: request outside the server: {u}")
    except Exception as e:
        failures.append(f"camera-follow: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  camera-follow: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "camera-follow-results.json").write_text(dump(res) + "\n")
