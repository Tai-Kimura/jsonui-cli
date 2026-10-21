"""Reading the web: a dictionary on the desk, its pages flipped (ticket 2026-10-20-jui-viz-webfetch-dictionary; requester
10-20: "WebFetchの時は机で辞書をペラペラめくるアニメーションにして欲しい", and "WebSeachも同様").

The real `jui viz serve` in a throwaway HOME on a free port, the real forward.py for three sessions in one room: one
running WebFetch, one WebSearch, one Read; later a subagent in its work clothes running WebFetch. Measured from the
page's own objects (window.__dbg.webLook / dictAt / looks / markDict), every wait checked each frame and named
(waits.py), anything that animates read once the robots have settled:

  - WebFetch and WebSearch: the dictionary on the desk, no book in the hands; Read: the book, no dictionary;
  - the pages turn: a page's turn read from the robot differs from the one read before and a page is drawn mid-turn
    (each of WebFetch and WebSearch on its own), and the right hand moves with it;
  - with the work clothes (a subagent's WebFetch) and with heavy work's look (forced 'tokens': the red face) the
    dictionary is there and its pages still turn;
  - the tool over (PostToolUse): no dictionary; background work after it: the headset, no dictionary;
  - never away from the desk: a robot on a break when its WebFetch starts shows no dictionary on any frame until it
    is back at its desk (watched every frame), then shows it;
  - taking the robot down (SessionEnd, it walks out) disposes each geometry and material of its dictionary;
  - under reduced motion the dictionary is open and no page turns (the turns at two pose times are 0, no page drawn).

Screenshots (light and dark): the room up close, and the WebFetch robot's own view.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, dump, new_page, stamp
from waits import settled, until

FETCH = "e2e00000-0000-4000-8000-0000000003d1"
SEARCH = "e2e00000-0000-4000-8000-0000000003d2"
READ = "e2e00000-0000-4000-8000-0000000003d3"
CWD = "/work/web-dict"
SUB, SUB_TYPE = "agent-web-dict-1", "general-purpose"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
PAGES = 3
LOOK = "() => window.__dbg.webLook()"
READY = "() => !!(window.__dbg && window.__dbg.robots && document.body.dataset.mode === 'live')"
WHY = "() => ({ look: window.__dbg.webLook(), settle: window.__dbg.settleInfo() })"
FETCH_IN = {"url": "https://example.com/docs", "prompt": "要点をまとめて"}
SEARCH_IN = {"query": "three.js dispose geometry"}
READ_IN = {"file_path": f"{CWD}/README.md"}
# a page of robot i.id drawn mid-turn, and its turns not those read before (i.p)
TURNED = ("(i) => { const x = window.__dbg.webLook().find((y) => y.id === i.id); "
          "return x && x.dict && x.pagesShown > 0 && x.pages.some((a) => a > 0.05 && a < 3.09) && JSON.stringify(x.pages) !== JSON.stringify(i.p); }")


def check(failures, cond, text):
    if not cond:
        failures.append(f"web-dict: {text}")


async def wait(page, js, label, arg=None, timeout=20000):
    await until(page, js, label, arg=arg, timeout=timeout, why=WHY)


def of(look, label):
    return next((x for x in look if x["id"] == label), None)


async def run_web_dict(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "web-dict"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    proj = home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", CWD)
    proj.mkdir(parents=True, exist_ok=True)
    transcripts = {}
    for sid in (FETCH, SEARCH, READ):
        transcripts[sid] = proj / f"{sid}.jsonl"
        transcripts[sid].write_text(json.dumps({"type": "user", "timestamp": stamp("2026-10-20T09:00:00Z"), "message": {"role": "user", "content": "start"}}) + "\n")
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

    def pre(sid, tool, tool_input, use, **extra):
        hook(sid, hook_event_name="PreToolUse", tool_name=tool, tool_input=tool_input, tool_use_id=use, **extra)

    def post(sid, tool, tool_input, use, **extra):
        hook(sid, hook_event_name="PostToolUse", tool_name=tool, tool_input=tool_input, tool_use_id=use, tool_response="ok", **extra)

    async def labels(page):
        return await page.evaluate("(ids) => Object.fromEntries(ids.map((s) => [s, (window.__dbg.robots.find((R) => R.def.sessionId === s && R.def.kind === 'main') || { def: {} }).def.id]))",
                                   [FETCH, SEARCH, READ])

    async def turns(page, label, name):
        """The pages of robot `label` turn on screen: read, then wait for a page mid-turn at other turns."""
        x = of(await page.evaluate(LOOK), label)
        await wait(page, TURNED, f"{name}: a page turns", arg={"id": label, "p": x["pages"]}, timeout=30000)
        y = of(await page.evaluate(LOOK), label)
        return {"before": x["pages"], "after": y["pages"], "shown": y["pagesShown"]}

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
        page = await new_page(browser, watch, "web-dict", **DESKTOP)
        await page.goto(url + "/")
        await until(page, READY, "the page is up", timeout=30000)
        await wait(page, "() => document.querySelector('.chip.demo').dataset.net === 'connected'", "connected")
        for sid in (FETCH, SEARCH, READ):
            hook(sid, hook_event_name="SessionStart", source="startup")
        await wait(page, "() => window.__dbg.play().robots.length >= 3", "three robots")
        await settled(page, "the three at their desks", timeout=30000)
        await page.evaluate("() => { window.__dbg.play({ p: 0, solo: { p: 0 } }); window.__dbg.brk({ p: { smoke: 0, vend: 0 } }); }")
        ids = res["ids"] = await labels(page)
        f, s, r = ids[FETCH], ids[SEARCH], ids[READ]

        # WebFetch, WebSearch and Read at once: the dictionary for the first two, the book for Read
        for sid in (FETCH, SEARCH, READ):
            hook(sid, hook_event_name="UserPromptSubmit", prompt="調べて")
        pre(FETCH, "WebFetch", FETCH_IN, "toolu_wd_fetch")
        pre(SEARCH, "WebSearch", SEARCH_IN, "toolu_wd_search")
        pre(READ, "Read", READ_IN, "toolu_wd_read")
        await wait(page, "(i) => { const L = window.__dbg.webLook(); return [i.f, i.s, i.r].every((id) => L.find((x) => x.id === id).state === 'reading'); }",
                   "the three reading", arg={"f": f, "s": s, "r": r})
        await settled(page, "the three in their reading poses", ids=[f, s, r])
        look = res["on"] = await page.evaluate(LOOK)
        for label, tool in ((f, "WebFetch"), (s, "WebSearch")):
            x = of(look, label)
            check(failures, x["readKind"] == "web" and x["dict"] and not x["book"],
                  f"{tool}: the dictionary on the desk, no book in the hands: {x}")
        x = of(look, r)
        check(failures, x["readKind"] is None and x["book"] and not x["dict"], f"Read: the book as before, no dictionary: {x}")
        res["fetchTurns"] = await turns(page, f, "WebFetch")
        res["searchTurns"] = await turns(page, s, "WebSearch")
        at = res["dictAt"] = await page.evaluate("() => window.__dbg.dictAt([0, 0.3, 0.6, 1.9])")
        check(failures, len({json.dumps(a) for a in at}) > 1 and all(len(a) == PAGES for a in at), f"the turns change with pose time: {at}")
        arm0 = of(look, f)["armRz"]
        await wait(page, "(a) => Math.abs(window.__dbg.webLook().find((x) => x.id === a.id).armRz - a.v) > 0.01", "the turning hand moves",
                   arg={"id": f, "v": arm0}, timeout=30000)
        tag = res["tag"] = await page.evaluate("(i) => { const R = window.__dbg.robots.find((x) => x.def.id === i); return { act: R.text.textContent, shown: getComputedStyle(R.tag).display !== 'none' }; }", f)
        check(failures, tag["shown"] and "WebFetch" in tag["act"], f"the name tag and its act as before: {tag}")

        # heavy work's look over it (forced): the red face, and the dictionary still turning
        await page.evaluate("(i) => window.__dbg.force(i, { heavy: ['tokens'] })", f)
        await wait(page, "(i) => window.__dbg.webLook().find((x) => x.id === i).look === 'fired'", "heavy work's look on the WebFetch robot", arg=f)
        res["heavyTurns"] = await turns(page, f, "WebFetch under heavy work")
        h = res["heavy"] = of(await page.evaluate(LOOK), f)
        check(failures, h["dict"] and not h["book"] and h["look"] == "fired", f"heavy work: the red look and the dictionary: {h}")
        await page.evaluate("(i) => window.__dbg.force(i, null)", f)

        # a subagent in its work clothes runs WebFetch: the dictionary on its desk too
        hook(SEARCH, hook_event_name="SubagentStart", agent_id=SUB, agent_type=SUB_TYPE)
        await wait(page, "() => window.__dbg.robots.some((R) => R.def.kind === 'sub')", "the subagent's robot")
        sub = await page.evaluate("() => window.__dbg.robots.find((R) => R.def.kind === 'sub').def.id")
        pre(SEARCH, "WebFetch", FETCH_IN, "toolu_wd_sub", agent_id=SUB, agent_type=SUB_TYPE)
        await wait(page, "(i) => { const x = window.__dbg.webLook().find((y) => y.id === i); return x.state === 'reading' && x.readKind === 'web'; }",
                   "the subagent reads the web", arg=sub, timeout=30000)
        await settled(page, "the subagent at its desk", ids=[sub], timeout=60000)
        res["subTurns"] = await turns(page, sub, "the subagent's WebFetch")
        wear = res["subWear"] = next(x for x in await page.evaluate("() => window.__dbg.wear()") if x["id"] == sub)
        check(failures, wear["cap"] and of(await page.evaluate(LOOK), sub)["dict"], f"the subagent: its work cap and the dictionary: {wear}")

        # pictures: the room up close; the WebFetch robot's own view
        room = await page.evaluate("(i) => window.__dbg.robots.find((R) => R.def.id === i).def.room", f)
        await page.click(f".tag.room[data-set-project='{room}']")
        await wait(page, f"() => window.__dbg.solo() === '{room}'", "the room up close")
        await settled(page, "the room up close, robots at rest", timeout=60000)
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await settled(page, f"the room, {scheme}")
            await page.screenshot(path=str(out / f"room-{scheme}.png"))
        await page.emulate_media(color_scheme="light")
        await page.evaluate("(i) => window.__dbg.openRobot(i)", f)
        await wait(page, "() => { const fo = window.__dbg.focus(); return fo.zoomed && !fo.tween; }", "the camera on the WebFetch robot")
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await settled(page, f"the WebFetch robot up close, {scheme}", ids=[f])
            await page.screenshot(path=str(out / f"closeup-{scheme}.png"))
        await page.emulate_media(color_scheme="light")
        await page.keyboard.press("Escape")
        await wait(page, "() => !window.__dbg.focus().zoomed && !window.__dbg.focus().tween", "back from the robot")

        # the tools over: no dictionary
        post(FETCH, "WebFetch", FETCH_IN, "toolu_wd_fetch")
        post(SEARCH, "WebSearch", SEARCH_IN, "toolu_wd_search")
        post(SEARCH, "WebFetch", FETCH_IN, "toolu_wd_sub", agent_id=SUB, agent_type=SUB_TYPE)
        post(READ, "Read", READ_IN, "toolu_wd_read")
        await wait(page, "(i) => i.every((id) => window.__dbg.webLook().find((x) => x.id === id).state !== 'reading')", "the tools over", arg=[f, s, sub, r])
        await settled(page, "back from reading", ids=[f, s, r])
        look = res["off"] = await page.evaluate(LOOK)
        check(failures, not any(of(look, x)["dict"] for x in (f, s, sub)) and not of(look, r)["book"], f"the tools over: no dictionary, no book: {look}")

        # background work after a WebFetch: the headset, no dictionary
        hook(FETCH, hook_event_name="UserPromptSubmit", prompt="裏で回して")
        pre(FETCH, "WebFetch", FETCH_IN, "toolu_wd_fetch2")
        await wait(page, "(i) => window.__dbg.webLook().find((x) => x.id === i).dict", "the dictionary again", arg=f)
        post(FETCH, "WebFetch", FETCH_IN, "toolu_wd_fetch2")
        hook(FETCH, hook_event_name="Stop", background_tasks=[{"id": "bash_1", "type": "bash"}])
        await wait(page, "(i) => window.__dbg.webLook().find((x) => x.id === i).state === 'background'", "in the background", arg=f)
        await settled(page, "the background pose", ids=[f])
        b = res["background"] = of(await page.evaluate(LOOK), f)
        check(failures, b["headset"] and not b["dict"], f"background work: the headset, no dictionary: {b}")
        hook(FETCH, hook_event_name="Stop")
        await wait(page, "(i) => window.__dbg.webLook().find((x) => x.id === i).state !== 'background'", "the background work over", arg=f)

        # away from the desk: on a break when its WebFetch starts, no dictionary on any frame until it is back
        await page.evaluate("() => { window.__dbg.play({ idleMs: 500, p: 0, solo: { p: 0 } }); window.__dbg.brk({ p: { smoke: 1, vend: 1 }, restMinSec: 0, restMaxSec: 0 }); }")
        await wait(page, "(i) => window.__dbg.webLook().find((x) => x.id === i).brk", "the WebFetch robot on a break", arg=f, timeout=60000)
        await page.evaluate("() => window.__dbg.brk({ p: { smoke: 0, vend: 0 } })")
        await page.evaluate("""(i) => { window.__away = { frames: 0, bad: 0, rows: [] };
          window.__dbg.afterFrame(() => { const R = window.__dbg.robots.find((x) => x.def.id === i); if (!R) return;
            const x = window.__dbg.webLook().find((y) => y.id === i), away = !!(R.brk || R.play || R.solo || R.playBack || R.path.length);
            if (away) { window.__away.frames += 1; if (x.dict) { window.__away.bad += 1; window.__away.rows.push(x); } } }); }""", f)
        hook(FETCH, hook_event_name="UserPromptSubmit", prompt="調べて")
        pre(FETCH, "WebFetch", FETCH_IN, "toolu_wd_fetch3")
        await wait(page, "(i) => { const x = window.__dbg.webLook().find((y) => y.id === i); return x.state === 'reading' && !x.brk && !x.walking && x.dict; }",
                   "back at its desk with the dictionary", arg=f, timeout=60000)
        away = res["away"] = await page.evaluate("() => { window.__dbg.afterFrame(null); const a = window.__away; window.__away = null; return { frames: a.frames, bad: a.bad, rows: a.rows.slice(0, 3) }; }")
        check(failures, away["frames"] > 0 and away["bad"] == 0, f"away from the desk (a break, the walk back): no dictionary on any frame: {away}")
        await page.click("#room-back")

        # taking the robot down disposes its dictionary's own geometries and materials
        marked = res["marked"] = await page.evaluate("(i) => window.__dbg.markDict(i)", f)
        check(failures, marked >= 4, f"the dictionary has geometries and materials of its own to dispose: {marked}")
        hook(FETCH, hook_event_name="SessionEnd", reason="other")
        await wait(page, "(i) => !window.__dbg.robots.some((R) => R.def.id === i)", "the WebFetch robot taken down", arg=f, timeout=90000)
        marks = res["disposed"] = {k: v for k, v in (await page.evaluate("() => window.__dbg.disposedMarks()")).items() if k.startswith("dict:")}
        check(failures, len(marks) == marked and all(v >= 1 for v in marks.values()), f"each of the dictionary's own geometries and materials disposed: {marks}")

        # reduced motion: the dictionary open, no page turning
        quiet = await new_page(browser, watch, "web-dict-reduced", reduced_motion="reduce", **DESKTOP)
        await quiet.goto(url + "/")
        await until(quiet, READY, "the reduced-motion page is up", timeout=30000)
        hook(SEARCH, hook_event_name="UserPromptSubmit", prompt="調べて")
        pre(SEARCH, "WebSearch", SEARCH_IN, "toolu_wd_search2")
        await until(quiet, "(i) => { const x = window.__dbg.webLook().find((y) => y.id === i); return x && x.state === 'reading' && x.dict; }",
                    "the dictionary, reduced motion", arg=s, timeout=30000, why=WHY)
        await settled(quiet, "reduced motion, at rest", ids=[s])
        q1 = of(await quiet.evaluate(LOOK), s)
        at = await quiet.evaluate("() => window.__dbg.dictAt([0, 0.3, 0.6, 1.9])")
        await settled(quiet, "reduced motion, a later frame", ids=[s])
        q2 = of(await quiet.evaluate(LOOK), s)
        res["reduced"] = {"first": q1, "later": q2, "dictAt": at}
        check(failures, q1["reduced"] and q1["dict"] and q1["pagesShown"] == 0 and q2["pagesShown"] == 0 and q1["pages"] == q2["pages"]
              and all(a == [0] * PAGES for a in at) and q1["armRz"] == q2["armRz"],
              f"reduced motion: the dictionary open, no page turning, the hand still: {res['reduced']}")
        post(SEARCH, "WebSearch", SEARCH_IN, "toolu_wd_search2")
        await quiet.close()
        await page.close()
        for line in watch.console:
            failures.append(f"web-dict: console: {line}")
        for u in watch.foreign:
            failures.append(f"web-dict: request outside the server: {u}")
    except Exception as e:
        failures.append(f"web-dict: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  web-dict: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "web-dict-results.json").write_text(dump(res) + "\n")
