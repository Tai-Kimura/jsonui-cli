"""What background work looks like (2.3.5, requester 10-19: "バックグラウンドで作業中のロボットの動作がないから少しただの待機との
見分けがつきにくい バックグランドで作業の場合はヘッドセットつけて、音符出してる状態で机の上でパソコンをゆるめにいじってほしい。").

The real `jui viz serve` in a throwaway HOME on a free port, the real forward.py for three sessions in one room: one idle,
one typing (an Edit under way), one waiting on background work (a Stop with background_tasks). Measured from the page's
own objects (window.__dbg.bgLook / poseStats / notesAt), never by sampling frames on the wall clock (waits.py: every
wait is checked each frame and named; a value that animates is read once the robot has settled):

  - the headset and the notes only on the background robot, the laptop under its hands; none on the idle or the typing one;
  - the notes rise (their places at two pose times differ) and there are never more than NOTE_MAX sprites a robot;
  - its keystrokes: a swing above zero and below typing's, fewer strokes a second than typing's; its arm moves on screen;
  - it never starts a game, a nap, a bento or a break (watched every frame), while the idle robot in the same room does;
  - on a call (it phones the idle session, then waits on background work while it rings): no headset, no notes, the
    handset instead; the call over and still in the background: the headset and the notes back;
  - when the background work ends (a Stop without it), the headset and the notes are gone;
  - under reduced motion the notes stand still (their places at two pose times are the same; still shown).

Screenshots (light and dark): the room up close with the three side by side, and the background robot's own view.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, dump, new_page
from waits import settled, until

IDLE = "e2e00000-0000-4000-8000-0000000002a1"
WORK = "e2e00000-0000-4000-8000-0000000002a2"
BACK = "e2e00000-0000-4000-8000-0000000002a3"
CWD = "/work/bg-look"
NAMES = {IDLE: "bg-look-idle", BACK: "bg-look-back"}
# The background session's "process": the server ends background work whose process has no shell left under it
# (sources/processes.py), so its session file names a sleeping stand-in with such a shell under it.
STAND_IN = ("import subprocess, time; subprocess.Popen(['/bin/sh', '-c', 'sleep 900; true # shell-snapshots/snapshot-e2e-bg-look']); "
            "time.sleep(900)")
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
NOTE_MAX = 3
BG_TASKS = [{"id": "bash_1", "type": "bash"}]
LOOK = "() => window.__dbg.bgLook()"
READY = "() => !!(window.__dbg && window.__dbg.robots && document.body.dataset.mode === 'live')"
WHY = "() => ({ look: window.__dbg.bgLook(), settle: window.__dbg.settleInfo() })"
BODY = "ビルドが終わったら教えて"


def check(failures, cond, text):
    if not cond:
        failures.append(f"bg-look: {text}")


async def wait(page, js, label, arg=None, timeout=20000):
    await until(page, js, label, arg=arg, timeout=timeout, why=WHY)


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
    # session files (their names: the call) and transcripts (where the call is read), as calls.py
    proj = home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", CWD)
    proj.mkdir(parents=True, exist_ok=True)
    sessions = home / ".claude" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    transcripts = {}
    import signal
    stand_in = subprocess.Popen([sys.executable, "-c", STAND_IN], start_new_session=True,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pids = {IDLE: 92000, BACK: stand_in.pid}
    for n, sid in enumerate((IDLE, WORK, BACK)):
        transcripts[sid] = proj / f"{sid}.jsonl"
        transcripts[sid].write_text(json.dumps({"type": "user", "timestamp": "2026-10-19T09:00:00Z", "message": {"role": "user", "content": "start"}}) + "\n")
        if sid in NAMES:
            (sessions / f"{pids[sid]}.json").write_text(json.dumps({
                "pid": pids[sid], "sessionId": sid, "cwd": CWD, "name": NAMES[sid], "nameSource": "derived", "status": "idle",
                "messagingSocketPath": f"/tmp/e2e/{sid[-2:]}.sock", "entrypoint": "cli"}))
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT,
                           env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def hook(sid, **payload):
        body = {"session_id": sid, "cwd": CWD, "permission_mode": "default", "transcript_path": str(transcripts[sid]), **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(),
                       capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)

    def append(sid, rec):
        with open(transcripts[sid], "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

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
        await until(page, READY, "the page is up", timeout=30000)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", "connected")
        for sid in (IDLE, WORK, BACK):
            hook(sid, hook_event_name="SessionStart", source="startup")
        await wait(page, "() => window.__dbg.play().robots.length >= 3", "three robots")
        await settled(page, "the three at their desks", timeout=30000)
        await page.evaluate("() => { window.__dbg.play({ p: 0, solo: { p: 0 } }); window.__dbg.brk({ p: { smoke: 0, vend: 0 } }); }")
        ids = res["ids"] = await labels(page)
        hook(WORK, hook_event_name="UserPromptSubmit", prompt="直して")
        hook(WORK, hook_event_name="PreToolUse", tool_name="Edit", tool_use_id="toolu_bg_edit", tool_input={"file_path": f"{CWD}/a.py", "old_string": "a", "new_string": "b"})
        to_background()
        await wait(page, "(i) => { const L = window.__dbg.bgLook(); return L.find((x) => x.id === i.b).state === 'background' && L.find((x) => x.id === i.w).state === 'typing'; }",
                   "one typing, one in the background", arg={"b": ids[BACK], "w": ids[WORK]})
        await settled(page, "the typing and the background robot in their poses", ids=[ids[BACK], ids[WORK]])
        look = res["on"] = await page.evaluate(LOOK)
        b, w, i = of(look, ids[BACK]), of(look, ids[WORK]), of(look, ids[IDLE])
        check(failures, b["headset"] and b["laptop"] and 1 <= len(b["notes"]) <= NOTE_MAX and b["noteSprites"] == NOTE_MAX,
              f"the background robot wears the headset, has notes over it and a laptop: {b}")
        check(failures, not w["headset"] and not w["notes"] and not i["headset"] and not i["notes"],
              f"the typing and the idle robot have no headset and no notes: {w} {i}")
        # the notes rise: their places at two pose times differ (reduced motion: the same; below)
        at = res["notesAt"] = await page.evaluate("(i) => window.__dbg.notesAt(i, [0, 1.3])", ids[BACK])
        check(failures, at[0] != at[1], f"the notes move: {at}")
        # the keystrokes: looser than typing, but there; and its arm moves on screen (a later frame, another angle)
        stats = res["poseStats"] = await page.evaluate("() => ({ bg: window.__dbg.poseStats('background'), typing: window.__dbg.poseStats('typing') })")
        check(failures, 0 < stats["bg"]["swing"] < stats["typing"]["swing"] * 0.6 and 0 < stats["bg"]["strokesPerSec"] < stats["typing"]["strokesPerSec"] * 0.6,
              f"background typing is smaller and slower than typing, and not still: {stats}")
        arm0 = b["armL"]
        await wait(page, "(a) => Math.abs(window.__dbg.bgLook().find((x) => x.id === a.id).armL - a.v) > 0.002", "its arm moves on screen",
                   arg={"id": ids[BACK], "v": arm0})

        # no game, nap, bento or break while in the background (watched every frame); the idle robot in the room does go
        await page.evaluate("(ids) => window.__dbg.watchOuting(ids)", [ids[BACK], ids[IDLE]])
        await page.evaluate("() => { window.__dbg.play({ idleMs: 500, p: 1, restMinSec: 0, restMaxSec: 0, solo: { p: 1, minSec: 3, maxSec: 3 } }); "
                            "window.__dbg.brk({ p: { smoke: 1, vend: 1 }, restMinSec: 0, restMaxSec: 0 }); }")
        await wait(page, "(i) => window.__outing[i]", "the idle robot in the same room goes (the rules let it)", arg=ids[IDLE], timeout=30000)
        outing = res["outing"] = await page.evaluate("() => ({ ...window.__outing })")
        check(failures, not outing[ids[BACK]], f"the background robot never goes to a game, a nap, a bento or a break: {outing}")
        await page.evaluate("() => { window.__outing = null; window.__dbg.play({ p: 0, endAll: true, solo: { p: 0 } }); window.__dbg.brk({ p: { smoke: 0, vend: 0 }, endAll: true }); }")
        await wait(page, "() => window.__dbg.play().robots.every((x) => !x.back && x.path === 0 && !x.solo)", "everyone back at a desk", timeout=60000)

        # the cap: NOTE_MAX sprites a robot, and no stray note in the scene
        cap = res["cap"] = await page.evaluate("""() => { const D = window.__dbg, scene = D.robots[0].robot.root.parent; let n = 0;
          scene.traverse((o) => { if (o.isSprite && o.parent && o.parent.userData.notes) n += 1; });
          return { sprites: n, perRobot: D.bgLook().map((x) => x.noteSprites) }; }""")
        check(failures, cap["sprites"] <= NOTE_MAX * sum(1 for x in cap["perRobot"] if x) and max(cap["perRobot"]) == NOTE_MAX,
              f"never more than {NOTE_MAX} note sprites a robot: {cap}")

        # pictures: the room up close, the three side by side; the background robot's own view
        room = await page.evaluate("(i) => window.__dbg.robots.find((R) => R.def.id === i).def.room", ids[BACK])
        await page.click(f".tag.room[data-set-project='{room}']")
        await wait(page, f"() => window.__dbg.solo() === '{room}'", "the room up close")
        await settled(page, "the room up close, robots at rest")
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await settled(page, f"the room, {scheme}")
            await page.screenshot(path=str(out / f"room-{scheme}.png"))
        await page.emulate_media(color_scheme="light")
        await page.evaluate("(i) => window.__dbg.openRobot(i)", ids[BACK])
        await wait(page, "() => { const f = window.__dbg.focus(); return f.zoomed && !f.tween; }", "the camera on the background robot")
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await settled(page, f"the background robot up close, {scheme}", ids=[ids[BACK]])
            await page.screenshot(path=str(out / f"closeup-{scheme}.png"))
        await page.emulate_media(color_scheme="light")
        await page.keyboard.press("Escape")
        await wait(page, "() => !window.__dbg.focus().zoomed && !window.__dbg.focus().tween", "back from the robot")
        await page.click("#room-back")

        # a call while in the background: it phones the idle session, then waits on background work while it rings
        hook(BACK, hook_event_name="UserPromptSubmit", prompt="終わったら伝えて")
        hook(BACK, hook_event_name="PreToolUse", tool_name="SendMessage", tool_use_id="toolu_bg_call",
             tool_input={"to": NAMES[IDLE], "summary": "x", "message": BODY})
        hook(BACK, hook_event_name="PostToolUse", tool_name="SendMessage", tool_use_id="toolu_bg_call",
             tool_input={"to": NAMES[IDLE], "message": BODY}, tool_response={"success": True})
        hook(BACK, hook_event_name="Stop", background_tasks=BG_TASKS)
        await wait(page, "(i) => { const x = window.__dbg.bgLook().find((y) => y.id === i); return x.state === 'background' && x.onLine; }",
                   "on the phone while in the background", arg=ids[BACK])
        c = res["onCall"] = of(await page.evaluate(LOOK), ids[BACK])
        check(failures, c["handset"] and not c["headset"] and not c["notes"], f"on a call: the handset, no headset, no notes: {c}")
        # the idle session reads it: picked up; the call over, still in the background: the headset and the notes back
        xmsg = (f'<cross-session-message from="uds:/tmp/e2e/{BACK[-2:]}.sock" from-name="{NAMES[BACK]}" from-mode="prompting">\n'
                f"{BODY}\n</cross-session-message>")
        append(IDLE, {"type": "queue-operation", "operation": "enqueue", "timestamp": "2026-10-19T09:00:05Z", "sessionId": IDLE, "content": xmsg})
        append(IDLE, {"type": "user", "isMeta": True, "timestamp": "2026-10-19T09:00:06Z",
                      "message": {"role": "user", "content": "Another Claude session sent a message:\n" + xmsg}})
        await wait(page, "(i) => { const x = window.__dbg.bgLook().find((y) => y.id === i); return x.state === 'background' && !x.call && x.headset; }",
                   "the call over, the headset back", arg=ids[BACK], timeout=30000)
        c = res["afterCall"] = of(await page.evaluate(LOOK), ids[BACK])
        check(failures, c["headset"] and c["notes"] and not c["handset"], f"the call over, still in the background: the headset and the notes back: {c}")

        # the background work ends: off with the headset and the notes
        hook(BACK, hook_event_name="Stop")
        await wait(page, "(i) => window.__dbg.bgLook().find((x) => x.id === i).state !== 'background'", "the background work over", arg=ids[BACK])
        off = res["off"] = of(await page.evaluate(LOOK), ids[BACK])
        check(failures, not off["headset"] and not off["notes"], f"after the background work: no headset, no notes: {off}")

        # reduced motion: the notes stand still (and are shown)
        quiet = await new_page(browser, watch, "bg-look-reduced", reduced_motion="reduce", **DESKTOP)
        await quiet.goto(url + "/")
        await until(quiet, READY, "the reduced-motion page is up", timeout=30000)
        to_background()
        await until(quiet, "(i) => { const x = window.__dbg.bgLook().find((y) => y.id === i); return x && x.state === 'background' && x.notes.length > 0; }",
                    "background again, reduced motion", arg=ids[BACK], timeout=30000, why=WHY)
        n2 = of(await quiet.evaluate(LOOK), ids[BACK])
        at = await quiet.evaluate("(i) => window.__dbg.notesAt(i, [0, 1.3])", ids[BACK])
        res["reduced"] = {"notesAt": at, "headset": n2["headset"], "shown": len(n2["notes"])}
        check(failures, n2["headset"] and n2["notes"] and at[0] == at[1], f"reduced motion: the notes are shown and stand still: {res['reduced']}")
        await quiet.close()
        await page.close()
        for line in watch.console:
            failures.append(f"bg-look: console: {line}")
        for u in watch.foreign:
            failures.append(f"bg-look: request outside the server: {u}")
    except Exception as e:
        failures.append(f"bg-look: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        try:
            os.killpg(stand_in.pid, signal.SIGTERM)   # the stand-in and its shell, both this suite's own
        except ProcessLookupError:
            pass
        stand_in.wait()
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  bg-look: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "bg-look-results.json").write_text(dump(res) + "\n")
