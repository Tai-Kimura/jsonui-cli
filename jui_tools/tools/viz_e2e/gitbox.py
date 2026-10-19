"""The cardboard box: git push / pull (2.3.4, requester 10-19).

The real `jui viz serve` in a throwaway HOME on a free port, the real forward.py, and a git repository made here
(neutral names) as the session's folder: the push reports carry its real commits, so the server counts the range
itself (gitbox.count_range, read-only). In the room up close: the desk with its box stands in the room and overlaps
nothing; a push walks there with a stack as thick as its lines and comes back empty, the box fills; a pull goes empty
and comes back with a stack, the box empties a little; nothing to pull comes back empty; a rejected push comes back
with its stack; an instruction and a permission prompt stop a trip at once. The line over the robot, the robot card and
the log carry the label. On the floor (no room up close) no robot walks, the line still shows. Light and dark.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

from common import ISOLATE, LAUNCH_ARGS, Watch, dump, new_page, ready
from waits import frame_log_js

# Frames SLOW_MS apart (the e2e's own requestAnimationFrame wrapper) for one trip: its time at the box starts in the
# frame it arrives (it waited a frame for gitTick: ticket 2026-10-20-jui-viz-arrivals-and-rolls-wait-for-frames).
# window.__fastFrames() ends the slow frames at once: the frame already waiting its 3 s runs now (else that one late
# frame carried the whole 1.4 s at the box and the walk back, and the arm after it never saw the trip going back).
SLOW_RAF = """(() => { const raf = window.requestAnimationFrame.bind(window), held = new Map();
  window.requestAnimationFrame = (cb) => { const ms = window.__slowFrameMs || 0; if (!ms) return raf(cb);
    const h = setTimeout(() => { held.delete(h); raf(cb); }, ms); held.set(h, cb); return h; };
  window.__fastFrames = () => { window.__slowFrameMs = 0; for (const [h, cb] of held) { clearTimeout(h); raf(cb); } held.clear(); return true; }; })()"""
SLOW_MS = 3000
TRIP_LOG_JS = frame_log_js(
    "(id) => { const w = window.__dbg.gitBox().why[id] || {}; return { git: w.git, path: w.path }; }",
    "(id) => (window.__dbg.gitBox().why[id] || {}).git === 'at'")

DESKTOP = {"viewport": {"width": 1440, "height": 900}, "device_scale_factor": 1}
SID = "9b000000-0000-4000-8000-0000000000a1"
MORE = [f"9b000000-0000-4000-8000-0000000000{k:02x}" for k in range(0xa2, 0xa8)]   # six more sessions in the folder: the room grows


def check(failures, cond, text):
    if not cond:
        failures.append(f"gitbox: {text}")


async def wait(page, js, arg=None, timeout=20000, label=""):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=100)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


def git(repo, *args):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env).stdout.strip()


def make_repo(repo: pathlib.Path) -> dict:
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "-b", "main")
    (repo / "a.txt").write_text("one\n")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-q", "-m", "first")
    base = git(repo, "rev-parse", "--short", "HEAD")
    (repo / "a.txt").write_text("one\ntwo\n")
    git(repo, "commit", "-q", "-am", "small")
    small = git(repo, "rev-parse", "--short", "HEAD")
    (repo / "b.txt").write_text("".join(f"line {i}\n" for i in range(400)))
    git(repo, "add", "b.txt")
    git(repo, "commit", "-q", "-m", "big")
    big = git(repo, "rev-parse", "--short", "HEAD")
    return {"base": base, "small": small, "big": big}


TRIP = """(id) => { const b = window.__dbg.gitBox(); return { phase: (b.trips[id] || {}).phase || null, sheets: (b.trips[id] || {}).sheets,
  look: (b.trips[id] || {}).look, said: b.said[id], fill: b.fill, ends: b.ends }; }"""


async def follow(page, rid, seconds=25):
    """The trip's phases as they come, with the stack and the look seen in each."""
    seen, t0 = [], time.monotonic()
    while time.monotonic() - t0 < seconds:
        s = await page.evaluate(TRIP, rid)
        key = (s["phase"], s["sheets"] if s["phase"] else None, s["look"])
        if not seen and s["phase"] is None:
            await page.wait_for_timeout(100)     # the trip has not reached the page yet
            continue
        if not seen or seen[-1][:3] != key:
            seen.append((*key, round(time.monotonic() - t0, 1)))
        if s["phase"] is None and len(seen) > 1:
            break
        await page.wait_for_timeout(100)
    return seen


async def run_gitbox(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "gitbox"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    repo = out / "box-app"
    shutil.rmtree(repo, ignore_errors=True)      # a run before left its commits: start from an empty folder
    revs = make_repo(repo)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {"revs": revs}
    n = {"use": 0}

    def hook(payload):
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps({"session_id": SID, "cwd": str(repo), **payload}).encode(),
                       capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)

    def bash(command, stdout="", stderr=""):
        n["use"] += 1
        use = f"toolu_box{n['use']}"
        hook({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_use_id": use, "tool_input": {"command": command}})
        hook({"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_use_id": use, "tool_input": {"command": command},
              "tool_response": {"stdout": stdout, "stderr": stderr}})

    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    t0 = time.monotonic()
    try:
        import urllib.request
        for _ in range(150):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        hook({"hook_event_name": "SessionStart", "source": "startup"})
        watch = Watch(origin=url)
        page = await new_page(browser, watch, "gitbox", **DESKTOP)
        await page.add_init_script(SLOW_RAF)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => Object.keys(window.__dbg.robotState()).length >= 1", timeout=30000, label="the robot")
        rid = (await page.evaluate("() => Object.keys(window.__dbg.robotState())"))[0]

        # 0. on the floor: no desk, no walk, the line shows
        bash("git push", stderr=f"To example.invalid:team/box-app.git\n   {revs['base']}..{revs['small']}  main -> main\n")
        await wait(page, "(id) => (window.__dbg.gitBox().said[id] || '').startsWith('↑ push main')", arg=rid, label="the line on the floor")
        floor = res["floor"] = await page.evaluate(TRIP, rid)
        check(failures, floor["phase"] is None and not (await page.evaluate("() => window.__dbg.gitBox().desk")),
              f"on the floor: no desk and no trip, the line only: {floor}")

        # no game, nap, bento or break unless an arm asks (2.3.3's breaks start on their own after a while idle)
        await page.evaluate("() => { window.__dbg.play({ p: 0, solo: { p: 0 } }); window.__dbg.brk({ p: { smoke: 0, vend: 0 } }); }")

        # the room up close
        await page.click("#scope-top")
        await page.evaluate("() => [...document.querySelectorAll('#pop [data-pick-project]')].find((x) => x.textContent.includes('box-app')).click()")
        await wait(page, "() => window.__dbg.gitBox().desk", label="the box's desk in the room up close")
        await page.wait_for_timeout(1500)
        g = res["desk"] = await page.evaluate("() => window.__dbg.gitBox()")
        ov = g["overlaps"]
        check(failures, ov and ov["inRoom"] and ov["overlaps"] == [], f"the desk stands in the room and overlaps nothing: {ov}")
        await page.screenshot(path=str(out / "desk-light.png"))

        # 1. a small push, then a big one: the stack grows with the lines; the box fills
        fill0 = g["fill"]
        bash("cd . && git push origin main", stderr=f"To example.invalid:team/box-app.git\n   {revs['base']}..{revs['small']}  main -> main\n")
        small = res["smallPush"] = await follow(page, rid)
        await page.wait_for_timeout(300)
        fill1 = (await page.evaluate("() => window.__dbg.gitBox().fill"))
        bash("git -C . push", stderr=f"To example.invalid:team/box-app.git\n   {revs['small']}..{revs['big']}  main -> main\n")
        await wait(page, "(id) => window.__dbg.gitBox().trips[id] && window.__dbg.gitBox().trips[id].phase === 'going'", arg=rid, label="the big push going")
        s0 = await page.evaluate(TRIP, rid)   # the walk can be short: keep what it carried on the way before the screenshot
        await page.screenshot(path=str(out / "push-going-light.png"))
        big = await follow(page, rid)
        if s0["phase"] == "going" and (not big or big[0][0] != "going"):
            big.insert(0, ("going", s0["sheets"], s0["look"], 0.0))
        res["bigPush"] = big
        fill2 = (await page.evaluate("() => window.__dbg.gitBox().fill"))
        said = res["saidAfterPush"] = (await page.evaluate(TRIP, rid))["said"]
        # on the way out (going, or at the box when the walk was too short to sample): the stack it carries
        going = lambda seen: [s for s in seen if s[0] in ("going", "at")][:1]
        phases = lambda seen: [p for p in (s[0] for s in seen) if p]
        check(failures, phases(small)[-2:] == ["at", "back"] and phases(small)[0] in ("going", "at")
              and phases(big)[:3] == ["going", "at", "back"], f"a push goes to the box, stops there, comes back: small {small}, big {big}")
        check(failures, going(small) and going(big) and going(small)[0][2] == "carry" and going(big)[0][2] == "carry"
              and going(big)[0][1] > going(small)[0][1] >= 1, f"the stack grows with the lines: small {going(small)}, big {going(big)}")
        back_big = [s for s in big if s[0] == "back"]
        check(failures, back_big and back_big[0][2] == "stroll", f"back from a push with empty hands: {back_big}")
        check(failures, fill2 > fill1 > fill0, f"the box fills: {fill0} -> {fill1} -> {fill2}")
        check(failures, said == "↑ push main 1 コミット +400 −0", f"the line over the robot: {said!r}")

        # 2. a pull: there empty, back with a stack; the box empties a little
        bash("git pull", stdout=f"From example.invalid:team/box-app\n * branch            main       -> FETCH_HEAD\nUpdating {revs['small']}..{revs['big']}\n"
                                "Fast-forward\n b.txt | 400 ++++\n 1 file changed, 400 insertions(+)\n")
        pull = res["pull"] = await follow(page, rid)
        fill3 = (await page.evaluate("() => window.__dbg.gitBox().fill"))
        gp = [s for s in pull if s[0] in ("going", "at")][:1]     # out: empty-handed (at the box when the walk was short)
        bp = [s for s in pull if s[0] == "back"]
        check(failures, gp and gp[0][2] != "carry" and bp and bp[0][2] == "carry" and bp[0][1] >= 4 and fill3 < fill2,
              f"a pull goes empty and comes back with a stack, the box empties: {pull}, fill {fill2} -> {fill3}")

        # 3. nothing to pull: back empty; 4. a rejected push: back with its stack
        bash("git pull", stdout="Already up to date.\n")
        upd = res["upToDate"] = await follow(page, rid)
        check(failures, all(s[2] != "carry" for s in upd if s[0]), f"nothing to pull: no stack either way: {upd}")
        bash("git push", stderr=f" ! [rejected]        main -> main (fetch first)\nerror: failed to push some refs\n")
        rej = res["rejected"] = await follow(page, rid)
        br = [s for s in rej if s[0] == "back"]
        check(failures, br and br[0][2] == "carry", f"a rejected push comes back with its stack: {rej}")

        # 5. stopped at once: an instruction, a permission prompt
        for name, stop in (("instruction", {"hook_event_name": "UserPromptSubmit", "prompt": "next"}),
                           ("permission", {"hook_event_name": "Notification", "notification_type": "permission_prompt", "message": "permission"})):
            bash("git push", stderr=f"   {revs['base']}..{revs['big']}  main -> main\n")
            await wait(page, "(id) => window.__dbg.gitBox().trips[id] && window.__dbg.gitBox().trips[id].phase === 'going'", arg=rid, label=f"going before the {name}")
            hook(stop)
            await wait(page, "(id) => { const t = window.__dbg.gitBox().trips[id]; return !t || t.phase === 'back'; }", arg=rid, timeout=8000, label=f"turned back by the {name}")
            ends = (await page.evaluate("() => window.__dbg.gitBox().ends"))
            res[f"stop_{name}"] = ends[-1]
            check(failures, ends[-1]["why"] in (("cleared",) if name == "instruction" else ("waiting",)) and ends[-1]["phase"] == "going",
                  f"a trip stops at once on {name}: {ends[-1]}")
            await wait(page, "(id) => !window.__dbg.gitBox().trips[id]", arg=rid, timeout=15000, label="home again")
            hook({"hook_event_name": "UserPromptSubmit", "prompt": "go on"})

        # 5b. a trip and a break never share the robot (2.3.4 on 2.3.3). A push during a cigarette: the Bash call ends the
        # break, the trip follows. A break that would start on the way to the box (its rest reset at once) waits for the
        # trip to end. A trip that comes during a break (poked on the page) waits for the break to end.
        SAMPLE = """([id, ms, stopOn]) => new Promise((done) => {
          const out = { samples: 0, both: [], brk: 0, trip: 0, brkAfter: 0 }, t0 = performance.now();
          const tick = () => {
            const r = window.__dbg.brk().robots.find((x) => x.id === id) || {}, t = window.__dbg.gitBox().trips[id];
            out.samples++;
            if (r.kind && t) out.both.push([r.kind, t.phase, Math.round(performance.now() - t0)]);
            if (r.kind && !out.trip) out.brk++;
            if (t) out.trip++;
            if (r.kind && out.trip && !t) out.brkAfter++;
            if (performance.now() - t0 < ms && !(stopOn && out.brkAfter)) setTimeout(tick, 100); else done(out);
          };
          tick();
        })"""
        smoking = "(id) => { const r = window.__dbg.brk().robots.find((x) => x.id === id); return r && r.kind === 'smoke' && r.at; }"
        await page.evaluate("() => { window.__dbg.play({ idleMs: 500 }); window.__dbg.brk({ p: { smoke: 1, vend: 0 }, smokeMinSec: 30, smokeMaxSec: 30, restMinSec: 0, restMaxSec: 0 }); }")
        await wait(page, smoking, arg=rid, timeout=40000, label="a cigarette in the booth")
        bash("git push", stderr=f"To example.invalid:team/box-app.git\n   {revs['base']}..{revs['small']}  main -> main\n")
        hook({"hook_event_name": "Stop"})   # the turn ends: idle again (else the session goes on thinking and ends any break)
        await wait(page, "(id) => !!window.__dbg.gitBox().trips[id]", arg=rid, timeout=30000, label="the trip after the break")
        await page.evaluate("() => window.__dbg.brk({ restMinSec: 0, restMaxSec: 0 })")   # rested: a break would start now
        tb = res["tripThenBreak"] = await page.evaluate(SAMPLE, [rid, 40000, True])
        check(failures, not tb["both"] and tb["trip"] > 0 and tb["brkAfter"] > 0,
              f"no break starts on the way to the box; one starts after it: {tb}")
        try:
            await wait(page, smoking, arg=rid, timeout=40000, label="the cigarette after the trip")
        except RuntimeError:
            res["brkWhy"] = await page.evaluate("(id) => { const b = window.__dbg.brk(); return { ends: b.ends, me: b.robots.find((x) => x.id === id) }; }", rid)
            raise
        await page.evaluate("(id) => window.__dbg.gitPoke(id, { id: 'poke-1', branch: 'main', label: '↑ push main' })", rid)
        bt = res["breakThenTrip"] = await page.evaluate(SAMPLE, [rid, 4000, False])
        check(failures, not bt["both"] and bt["trip"] == 0 and bt["brk"] > 30, f"a trip that comes during a break waits: {bt}")
        await page.evaluate("() => { window.__dbg.brk({ p: { smoke: 0, vend: 0 }, endAll: true }); window.__dbg.play({ idleMs: 60000 }); }")
        await wait(page, "(id) => !!window.__dbg.gitBox().trips[id]", arg=rid, timeout=30000, label="the waiting trip goes once the break ends")
        await wait(page, "(id) => !window.__dbg.gitBox().trips[id] && !(window.__dbg.brk().robots.find((x) => x.id === id) || {}).kind", arg=rid,
                   timeout=30000, label="home from the box and the booth")
        await wait(page, "() => window.__dbg.robots.every((R) => !R.path.length)", timeout=30000, label="seated again")

        # 5c. a trip and the shredder's errand never share the robot either (2.3.4 on feat/viz-shredder). A deletion at the
        # box waits for the trip to end, then goes (within SHRED.waitSec). A trip that comes on the way to the shredder
        # (poked on the page: a real Bash call would end the errand first) waits for the errand to end, then goes.
        SAMPLE2 = """([id, ms, until]) => new Promise((done) => {
          const out = { samples: 0, both: [], shred: 0, trip: 0, shredAfterTrip: 0, tripAfterShred: 0 }, t0 = performance.now();
          const tick = () => {
            const r = window.__dbg.shred().robots.find((x) => x.id === id) || {}, t = window.__dbg.gitBox().trips[id];
            out.samples++;
            if (r.phase && t) out.both.push([r.phase, t.phase, Math.round(performance.now() - t0)]);
            if (r.phase) out.shred++;
            if (t) out.trip++;
            if (r.phase && out.trip && !t) out.shredAfterTrip++;
            if (t && out.shred && !r.phase) out.tripAfterShred++;
            if (performance.now() - t0 < ms && !(until && out[until])) setTimeout(tick, 100); else done(out);
          };
          tick();
        })"""
        bash("git push", stderr=f"To example.invalid:team/box-app.git\n   {revs['base']}..{revs['small']}  main -> main\n")
        hook({"hook_event_name": "Stop"})
        await wait(page, "(id) => (window.__dbg.gitBox().trips[id] || {}).phase === 'at'", arg=rid, timeout=30000, label="at the box")
        bash("rm -f old-notes.txt")
        hook({"hook_event_name": "Stop"})
        ts = res["tripThenShred"] = await page.evaluate(SAMPLE2, [rid, 25000, "shredAfterTrip"])
        check(failures, not ts["both"] and ts["trip"] > 0 and ts["shredAfterTrip"] > 0,
              f"a deletion at the box waits for the trip, then goes to the shredder: {ts}")
        await wait(page, "(id) => { const x = window.__dbg.shred().robots.find((y) => y.id === id); return x.phase === null && x.path === 0; }",
                   arg=rid, timeout=30000, label="back from the shredder")
        bash("rm -f older-notes.txt")
        hook({"hook_event_name": "Stop"})
        # once the turn's done -> idle has come (a state from the server rebuilds the page's robot state, poke and all),
        # still on the errand
        await wait(page, "(id) => window.__dbg.robotState()[id].state === 'done'", arg=rid, timeout=20000, label="the turn done")
        await wait(page, "(id) => window.__dbg.robotState()[id].state === 'idle' && window.__dbg.shred().robots.find((y) => y.id === id).phase !== null",
                   arg=rid, timeout=20000, label="idle, on the errand to the shredder")
        await page.evaluate("(id) => window.__dbg.gitPoke(id, { id: 'poke-2', branch: 'main', label: '↑ push main' })", rid)
        st2 = res["shredThenTrip"] = await page.evaluate(SAMPLE2, [rid, 30000, "tripAfterShred"])
        check(failures, not st2["both"] and st2["shred"] > 0 and st2["tripAfterShred"] > 0,
              f"a trip on the way to the shredder waits for the errand, then goes: {st2}")
        await wait(page, "(id) => !window.__dbg.gitBox().trips[id] && window.__dbg.shred().robots.find((y) => y.id === id).phase === null", arg=rid,
                   timeout=30000, label="home from the box")
        await wait(page, "() => window.__dbg.robots.every((R) => !R.path.length)", timeout=30000, label="seated again")

        # 5d. the room grows on the way to the box (six more sessions in the folder: past roomSize's six, the one-room
        # view is laid out again, the robot's seat and the box's desk move): the trip stops ('relaid', a jump to the new
        # seat, as a break does) and never stands where the box was (docs/bugs/2026-10-19-jui-viz-git-trip-walks-to-the-
        # old-box-when-the-room-grows.md). Measured 10-19: the seat moves only when the room grows, never with five or fewer.
        POS = """(id) => { const b = window.__dbg.gitBox(), R = window.__dbg.robots.find((x) => x.def.id === id), p = R.robot.root.position;
          return { phase: (b.trips[id] || {}).phase || null, pos: [+p.x.toFixed(2), +p.z.toFixed(2)], seat: R.def.pos, stand: b.spot && b.spot.stand,
                   room: b.overlaps && b.overlaps.room, path: R.path.length, end: b.ends.filter((e) => e.id === id).slice(-1)[0] || null }; }"""
        before = await page.evaluate(POS, rid)
        bash("git push", stderr=f"To example.invalid:team/box-app.git\n   {revs['base']}..{revs['small']}  main -> main\n")
        hook({"hook_event_name": "Stop"})
        # this push's own trip (a poke above leaves an older real trip unseen: it may go first, and be replaced)
        mine = f"toolu_box{n['use']}"
        await wait(page, "([id, t]) => { const x = window.__dbg.gitBox().trips[id]; return !!x && x.id === t && x.phase === 'going'; }", arg=[rid, mine],
                   timeout=30000, label="this push going to the box")
        going = await page.evaluate(POS, rid)
        n_ends = await page.evaluate("(id) => { window.__dbg.robots.find((x) => x.def.id === id).__mark = 1; return window.__dbg.gitBox().ends.length; }", rid)
        for sid in MORE:
            hook({"hook_event_name": "SessionStart", "source": "startup", "session_id": sid})
        seen = res["relaidPhases"] = await page.evaluate("""(id) => new Promise((done) => {
          const out = [], t0 = performance.now();
          const tick = () => { const b = window.__dbg.gitBox(), t = b.trips[id], R = window.__dbg.robots.find((x) => x.def.id === id), p = R.robot.root.position;
            const ph = t ? t.phase : null;
            if (!out.length || out[out.length - 1][0] !== ph) out.push([ph, [+p.x.toFixed(2), +p.z.toFixed(2)], b.spot && b.spot.stand, Math.round(performance.now() - t0), R.def.room, b.room]);
            if ((ph === null && out.length > 1) || performance.now() - t0 > 30000) done(out); else setTimeout(tick, 50); };
          tick(); })""", rid)
        await wait(page, "(id) => window.__dbg.robots.find((x) => x.def.id === id).path.length === 0", arg=rid, timeout=30000, label="settled after the room grew")
        after = await page.evaluate(POS, rid)
        res["relaidEnds"] = await page.evaluate("([id, n]) => ({ ends: window.__dbg.gitBox().ends.slice(n), same: window.__dbg.robots.find((x) => x.def.id === id).__mark === 1, seen: window.__dbg.robots.find((x) => x.def.id === id).gitSeen })", [rid, n_ends])
        dist = lambda a, b: ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
        res["relaid"] = {"before": before, "going": going, "after": after}
        check(failures, after["room"] != before["room"] and after["seat"] != before["seat"], f"the room grew and the seat moved (else this arm proves nothing): {res['relaid']}")
        check(failures, (after["end"] or {}).get("why") == "relaid" and not any(p[0] == "at" for p in seen) and dist(after["pos"], after["seat"]) < 0.3,
              f"the trip stops when the room grows, never at the old box, and it is at its new seat: {seen}, {after}")
        for sid in MORE:
            hook({"hook_event_name": "SessionEnd", "reason": "exit", "session_id": sid})
        await wait(page, "() => window.__dbg.robots.length === 1 && window.__dbg.robots.every((R) => !R.path.length)", timeout=90000, label="one robot again, seated")

        # 6. the card and the log
        await page.evaluate("(id) => window.__dbg.openRobot(id)", rid)
        await wait(page, "() => { const el = document.querySelector('[data-rb-git]'); return !!el && !el.hidden; }",
                   label="the card's git line")
        res["card"] = await page.evaluate("() => document.querySelector('[data-rb-git]').textContent")
        check(failures, res["card"].startswith("最近の git: ↑ push main"), f"the card says the last push: {res['card']!r}")
        # the whole log, not the ticker (it shows the last 5 only)
        res["log"] = await page.evaluate("() => window.__dbg.gitLog()")
        check(failures, any("↑ push main 1 コミット +400 −0" in t for t in res["log"]) and any("↓ pull main" in t for t in res["log"]),
              f"the log has the pushes and the pulls: {res['log'][:6]}")
        await page.keyboard.press("Escape")
        await page.emulate_media(color_scheme="dark")
        await page.evaluate(f"() => {{ window.__slowFrameMs = {SLOW_MS}; }}")
        await page.evaluate(TRIP_LOG_JS, rid)
        bash("git push", stderr=f"   {revs['base']}..{revs['big']}  main -> main\n")
        await wait(page, "(id) => window.__dbg.gitBox().trips[id] && window.__dbg.gitBox().trips[id].phase === 'at'", arg=rid, timeout=40000, label="at the box (dark)")
        await page.evaluate("() => window.__fastFrames()")
        rows = res["tripRows"] = await page.evaluate("() => window.__frameRows")
        waited = [r for r in rows if r.get("git") == "going" and r.get("path") == 0]
        walked = [r for r in rows if r.get("git") == "going" and r.get("path")]
        # a trip shorter than one 3 s step goes and arrives in one frame (no "going" row): that is the same claim
        check(failures, rows and rows[-1].get("git") == "at" and not waited,
              f"with frames {SLOW_MS} ms apart, the time at the box starts in the frame it arrives: {len(waited)} frames between, {len(walked)} walking")
        await page.screenshot(path=str(out / "at-box-dark.png"))
        await page.emulate_media(color_scheme="light")
        await wait(page, "(id) => window.__dbg.gitBox().trips[id] && window.__dbg.gitBox().trips[id].phase === 'back'", arg=rid, timeout=20000, label="back")
        await page.screenshot(path=str(out / "back-light.png"))
        await page.close()
        for line in watch.console:
            failures.append(f"gitbox: console: {line}")
        for u in watch.foreign:
            failures.append(f"gitbox: request outside the server: {u}")
    except Exception as e:
        failures.append(f"gitbox: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  gitbox/box: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "gitbox-results.json").write_text(dump(res) + "\n")
