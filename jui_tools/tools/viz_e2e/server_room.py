"""The server room (ticket 2026-10-20-jui-viz-server-room, part B).

The real `jui viz serve` in a throwaway HOME on a free port, the real forward.py, and rooms made of the boundary's
examples (document_tools' make_examples.py, written into this run's folder) plus rooms that cannot be read: one
broken JSON, one against the schema, one with a secret-shaped value. Waits are on the page's state (waits.until),
never on time; the server's reply is held back by the network route where an arm needs the read to take a while.

  * a room opened up close has its door; nothing is read (no POST /api/infra-docs) until the door is pressed
  * pressed (a real click on the door): while the reply is held the keypad's * grow and the bubble says it reads;
    then the server room opens, the model drawn (nodes, cables, floors)
  * Esc while it reads: the bubble goes, and the reply that comes later opens nothing
  * a room that cannot be read (broken JSON, the schema, a secret-shaped value): the keypad turns red, the bubble
    names the file and what is wrong — never a value — and the room stays
  * the large example (2,000 nodes, 5,000 edges, four providers): drawn, its frame times kept for the ticket; zoomed
    out the top groups become boxes and the labels thin out, zoomed in they come back
  * provider-crossing cables drawn apart (dashed); the environments switch (never overlaid); the folded ones out
    until asked for; the room's icons on their nodes; Esc back to the room
  * with reduced motion the * stand still and the bubble still shows
"""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import statistics
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, dump, new_page, ready
from waits import until

ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
SR = "() => window.__dbg.sr()"
#: a frame of the large model must come within this (ms; the slowest tenth of the frames, software GL)
FRAME_P90_MAX_MS = 250


def _examples(jt: pathlib.Path) -> dict:
    spec = importlib.util.spec_from_file_location("infra_make_examples", jt.parent / "document_tools" / "tests" / "fixtures" / "infra" / "make_examples.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.all_examples()


def _write(base: pathlib.Path, examples: dict, name: str, dest: str) -> pathlib.Path:
    for rel, data in examples.items():
        if rel.split("/")[0] != name:
            continue
        path = base / dest / rel.split("/", 1)[1]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (base / dest / ".git").mkdir(parents=True, exist_ok=True)
    return base / dest


def check(failures, cond, text):
    if not cond:
        failures.append(f"server-room: {text}")


async def run_server_room(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "server-room"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    ex = _examples(jt)
    work = home / "work"
    rooms = {
        "three": _write(work, ex, "aws-three-tier", "sr-three"),
        "multi": _write(work, ex, "multi-provider", "sr-multi"),
        "large": _write(work, ex, "large-multi-provider", "sr-large"),
        "icons": _write(work, ex, "compose-and-cloud", "sr-icons"),
    }
    # one room for the three that cannot be read (seven rooms would turn the floor into the building): its prod.json is
    # written before each press
    secret_doc = ex["invalid/single/secret-connection-string.json"]
    BAD = {"broken": '{\n  "version": 0,\n  "nodes": [ {"id": "a" \n',
           "schema": json.dumps({"version": 0, "nodes": [{"id": "a", "category": "no.such.category"}]}),
           "secret": secret_doc if isinstance(secret_doc, str) else json.dumps(secret_doc)}
    bad = work / "sr-bad"
    (bad / "docs" / "infra").mkdir(parents=True, exist_ok=True)
    (bad / ".git").mkdir(exist_ok=True)
    (bad / "docs" / "infra" / "prod.json").write_text(BAD["broken"], encoding="utf-8")
    rooms["bad"] = bad
    secret_values = [v for v in json.dumps(ex["invalid/single/secret-connection-string.json"]).split('"') if "://" in v or "@" in v]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT,
                           env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def hook(sid, cwd, **payload):
        body = {"session_id": sid, "cwd": str(cwd), "permission_mode": "default", **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(), capture_output=True,
                       env=dict(base_env, HOME=str(home)), timeout=10)

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
        sids = {}
        for i, (name, root) in enumerate(rooms.items()):
            sids[name] = f"5e000000-0000-4000-8000-{i:012d}"
            hook(sids[name], root, hook_event_name="SessionStart", source="startup")
        watch = Watch(origin=url)
        page = await new_page(browser, watch, "server-room", **DESKTOP)
        asked: list = []
        page.on("request", lambda r: asked.append(r.url) if "/api/infra-docs" in r.url else None)
        await page.emulate_media(color_scheme="light", reduced_motion="no-preference")
        await page.goto(url + "/")
        await ready(page)
        await until(page, f"() => window.__dbg.robots.length >= {len(rooms)} && window.__dbg.robots.every((R) => !R.path.length)", "every room's robot seated", timeout=60000)
        pid = await page.evaluate("() => Object.fromEntries(window.__dbg.robots.map((R) => [R.def.sessionId, R.def.room]))")
        pid = {name: pid[sid] for name, sid in sids.items()}

        async def up_close(name):
            if await page.evaluate("() => !!window.__dbg.solo()"):
                await page.click("#room-back")
                await until(page, "() => window.__dbg.solo() === null", "back to the floor")
            await page.click(f".tag.room[data-set-project='{pid[name]}']")
            await until(page, f"() => window.__dbg.solo() === '{pid[name]}'", f"{name} up close")
            await until(page, "() => window.__dbg.sr().built && window.__dbg.sr().door", f"{name}'s server room door", timeout=20000)
            await until(page, "() => window.__dbg.robots.every((R) => !R.path.length)", "settled up close", timeout=30000)

        async def press_door():
            at = (await page.evaluate(SR))["door"]
            await page.mouse.click(at[0], at[1])

        # 1. up close: the door, and nothing read
        await up_close("three")
        res["door"] = await page.evaluate(SR)
        check(failures, res["door"]["built"] and not asked, f"a room up close has its door, and nothing is read before it is pressed: {len(asked)} reads")
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await until(page, "() => window.__dbg.sr().built", f"the door, {scheme}")
            await page.screenshot(path=str(out / f"door-{scheme}.png"))
        await page.emulate_media(color_scheme="light")
        await until(page, "() => window.__dbg.sr().built", "the door again")

        # 2. pressed, the reply held: the * grow, the bubble reads; then the server room
        held = {"n": 0}

        async def hold(route):
            held["n"] += 1
            await page.wait_for_timeout(2500)
            await route.continue_()
        await page.route("**/api/infra-docs", hold)
        await press_door()
        await until(page, "() => window.__dbg.sr().phase === 'loading'", "reading")
        stars = []
        for _ in range(6):
            s = await page.evaluate(SR)
            stars.append(s["stars"])
            await until(page, f"(n) => window.__dbg.sr().stars !== n || window.__dbg.sr().phase !== 'loading'", "the next *", arg=s["stars"], timeout=3000)
        res["stars"] = stars
        res["readingBubble"] = (await page.evaluate(SR))["bubble"]
        await page.screenshot(path=str(out / "keypad-light.png"))
        check(failures, len(set(stars)) >= 3, f"the keypad's * grow while it reads: {stars}")
        check(failures, (res["readingBubble"] or {}).get("text") == "サーバー構成を読み込んでいます", f"the bubble while it reads: {res['readingBubble']}")
        await until(page, "() => window.__dbg.sr().open", "the server room", timeout=15000)
        await page.unroute("**/api/infra-docs", hold)
        s = res["opened"] = await page.evaluate(SR)
        check(failures, s["bubble"] is None and (s["shown"] or {}).get("nodes", 0) > 0 and s["stats"]["edges"] > 0, f"open: the model drawn, the bubble gone: {s['shown']}")
        check(failures, s["lod"] == "near" and s["layers"] == {"near": True, "far": False}, f"open up close: the floors and shapes, not the far boxes over them: {s['lod']} {s['layers']}")
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await page.screenshot(path=str(out / f"room-{scheme}.png"))
        await page.emulate_media(color_scheme="light")

        # the environments switch, the folded ones come and go
        envs = await page.evaluate("() => [...document.querySelectorAll('#sr-env option')].map((o) => o.value)")
        res["envs"] = envs
        if len(envs) >= 2:
            before = (await page.evaluate(SR))["shown"]["nodes"]
            await page.select_option("#sr-env", envs[1])
            await until(page, f"(e) => window.__dbg.sr().env === e", "the other environment", arg=envs[1])
            res["envSwitch"] = [before, (await page.evaluate(SR))["shown"]["nodes"]]
        check(failures, len(envs) >= 2 and "envSwitch" in res, f"the environments are a switch: {envs}")
        folded = (await page.evaluate(SR))["shown"]
        await page.check("#sr-fold")
        await until(page, f"(n) => window.__dbg.sr().shown.nodes > n", "the folded ones shown", arg=folded["nodes"])
        res["fold"] = [folded["nodes"], (await page.evaluate(SR))["shown"]["nodes"], folded["folded"]]
        check(failures, folded["folded"] > 0 and res["fold"][1] == folded["nodes"] + folded["folded"] or res["fold"][1] > folded["nodes"],
              f"the folded ones are out until asked for: {res['fold']}")
        # the zoom buttons, a group closed into one box and opened again, moving in on it; the room's own 3D not drawn meanwhile
        px0 = (await page.evaluate(SR))["cellPx"]
        await page.click("#sr-zin")
        await until(page, "(p) => window.__dbg.sr().cellPx > p * 1.2", "+ moves in", arg=px0)
        await page.click("#sr-zout")
        await page.click("#sr-zout")
        await until(page, "(p) => window.__dbg.sr().cellPx < p", "- moves out", arg=px0)
        groups = await page.evaluate("() => window.__dbg.srGroups()")
        g = max(groups, key=lambda x: (x["nodes"] if x["nodes"] >= 2 else -1))
        before = (await page.evaluate(SR))["shown"]
        check(failures, await page.evaluate("(id) => window.__dbg.srSelectGroup(id)", g["id"]), f"a group picked has its close button: {g}")
        await page.click("#sr-board [data-sr-act='toggle']")
        await until(page, "() => window.__dbg.sr().shown.closed === 1", "the group closed")
        closed = (await page.evaluate(SR))["shown"]
        px1 = (await page.evaluate(SR))["cellPx"]
        await page.click("#sr-board [data-sr-act='focus']")
        await until(page, "(p) => window.__dbg.sr().cellPx > p", "moved in on the group", arg=px1)
        m0 = await page.evaluate("() => window.__dbg.mainFrames()")
        await page.evaluate("() => new Promise((r) => { let n = 0; const f = () => (++n < 20 ? requestAnimationFrame(f) : r()); requestAnimationFrame(f); })")
        m1 = await page.evaluate("() => window.__dbg.mainFrames()")
        await page.click("#sr-board [data-sr-act='toggle']")
        await until(page, "() => window.__dbg.sr().shown.closed === 0", "the group opened")
        reopened = (await page.evaluate(SR))["shown"]
        res["group"] = {"group": g, "before": before, "closed": closed, "reopened": reopened, "zoom": [px0, px1], "mainFrames": [m0, m1]}
        check(failures, closed["nodes"] == before["nodes"] - g["nodes"] and closed["inClosed"] == g["nodes"] and reopened["nodes"] == before["nodes"],
              f"a closed group is one box, opened it is all there again: {res['group']}")
        check(failures, m0 == m1, f"the room's 3D is not drawn under the server room: {m0} → {m1}")
        await page.keyboard.press("Escape")
        await until(page, "() => !window.__dbg.sr().open && window.__dbg.sr().phase === 'idle'", "back to the room")
        check(failures, (await page.evaluate("() => window.__dbg.solo()")) == pid["three"], "Esc goes back to the room")

        # 3. Esc while it reads: the late reply opens nothing
        import asyncio
        late = asyncio.Event()

        async def hold_late(route):
            await page.wait_for_timeout(2000)   # the reply held back (the network's stand-in), not a wait on state
            await route.continue_()
            late.set()
        await page.route("**/api/infra-docs", hold_late)
        await press_door()
        await until(page, "() => window.__dbg.sr().phase === 'loading' && !!window.__dbg.sr().bubble", "reading again")
        await page.keyboard.press("Escape")
        await until(page, "() => window.__dbg.sr().phase === 'idle' && !window.__dbg.sr().bubble", "the press dropped")
        await asyncio.wait_for(late.wait(), timeout=10)
        await page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
        res["afterEsc"] = await page.evaluate(SR)
        check(failures, late.is_set() and not res["afterEsc"]["open"] and res["afterEsc"]["phase"] == "idle", f"a reply after Esc opens nothing: {res['afterEsc']['phase']}, open {res['afterEsc']['open']}")
        await page.unroute("**/api/infra-docs", hold_late)

        # 4. rooms that cannot be read: red, the file named, the room stays, no value shown
        await up_close("bad")
        for name, want in (("broken", "prod.json"), ("schema", "prod.json"), ("secret", "prod.json")):
            (bad / "docs" / "infra" / "prod.json").write_text(BAD[name], encoding="utf-8")
            await press_door()
            await until(page, "() => window.__dbg.sr().phase === 'failed'", f"{name}: failed")
            s = res[f"fail-{name}"] = await page.evaluate(SR)
            text = ((s["bubble"] or {}).get("text") or "") + "\n" + ((s["bubble"] or {}).get("full") or "")
            check(failures, s["keypad"] == "failed" and (s["bubble"] or {}).get("kind") == "error" and want in text and not s["open"],
                  f"{name}: the keypad red, the bubble names the file, the room stays: {s['keypad']} {s['bubble']}")
            check(failures, (await page.evaluate("() => window.__dbg.solo()")) == pid["bad"], f"{name}: still in the room")
            if name == "secret":
                leaked = [v for v in secret_values if len(v) >= 6 and v in text]
                check(failures, not leaked, f"no secret-shaped value in the bubble or its whole text: {leaked}")
            if name == "broken":
                await page.hover("#sr-bubble")
                rect = (await page.evaluate(SR))["bubbleRect"]
                vw = await page.evaluate("() => window.innerWidth")
                check(failures, rect and rect[0] >= 0 and rect[1] >= 0 and rect[2] <= vw, f"the error bubble stays on the page: {rect} (width {vw})")
                await page.screenshot(path=str(out / "failed-light.png"))

        # 5. crossing cables; icons
        await up_close("multi")
        await press_door()
        await until(page, "() => window.__dbg.sr().open", "multi open", timeout=20000)
        s = res["multi"] = await page.evaluate("() => ({ ...window.__dbg.sr(), cross: window.__dbg.srCross() })")
        check(failures, s["shown"]["cross"] > 0 and s["cross"]["dashed"] and s["cross"]["drawn"] == s["shown"]["cross"],
              f"provider-crossing cables drawn apart, dashed: {s['shown']} {s['cross']}")
        check(failures, s["lod"] == "near" and s["layers"] == {"near": True, "far": False}, f"multi up close: no far box over the floors: {s['lod']} {s['layers']}")
        await page.screenshot(path=str(out / "multi-light.png"))
        await page.keyboard.press("Escape")
        await up_close("icons")
        await press_door()
        await until(page, "() => window.__dbg.sr().open", "icons open", timeout=20000)
        await until(page, "() => window.__dbg.sr().icons > 0", "the room's icons on their nodes", timeout=10000)
        res["icons"] = (await page.evaluate(SR))["icons"]
        await page.keyboard.press("Escape")

        # 6. the large model: drawn, frames kept, far and near
        await up_close("large")
        await press_door()
        await until(page, "() => window.__dbg.sr().open", "large open", timeout=60000)
        cdp = await page.context.new_cdp_session(page)
        await cdp.send("Performance.enable")

        async def frames(where):
            await page.evaluate("() => window.__dbg.srFramesReset()")
            await until(page, "() => window.__dbg.sr().frames.length >= 60", f"60 frames drawn ({where})", timeout=60000)
            s = await page.evaluate(SR)
            fr = sorted(s["frames"])
            heap = {m["name"]: m["value"] for m in (await cdp.send("Performance.getMetrics"))["metrics"]}
            return s, {"lod": s["lod"], "cellPx": s["cellPx"], "frameMedian": round(statistics.median(fr), 1), "frameP90": round(fr[int(len(fr) * 0.9)], 1),
                       "labels": s["labels"], "gpu": s["gpu"], "jsHeapUsedMB": round(heap.get("JSHeapUsedSize", 0) / 1e6, 1)}
        s, first = await frames("fit")
        res["large"] = {"stats": s["stats"], "fit": first}
        check(failures, s["stats"]["nodes"] >= 1500 and first["frameP90"] < FRAME_P90_MAX_MS, f"the large model is drawn and does not stall: {res['large']}")
        px_far = await page.evaluate("() => window.__dbg.srZoom(3)")
        await until(page, "() => window.__dbg.sr().lod === 'far'", "far", timeout=5000)
        await until(page, "() => window.__dbg.sr().labels > 0", "far labels", timeout=5000)
        far, res["large"]["far"] = await frames("far")
        await page.screenshot(path=str(out / "large-far-light.png"))
        px_near = await page.evaluate("() => window.__dbg.srZoom(0.05)")
        await until(page, "() => window.__dbg.sr().lod === 'near'", "near", timeout=5000)
        await until(page, "(n) => window.__dbg.sr().labels > n", "near labels", arg=far["labels"], timeout=5000)
        near, res["large"]["near"] = await frames("near")
        check(failures, max(res["large"]["far"]["frameP90"], res["large"]["near"]["frameP90"]) < FRAME_P90_MAX_MS, f"far and near do not stall: {res['large']}")
        await page.screenshot(path=str(out / "large-near-light.png"))
        res["lod"] = {"far": [px_far, far["labels"]], "near": [px_near, near["labels"]]}
        check(failures, far["lod"] == "far" and near["lod"] == "near" and far["labels"] < near["labels"],
              f"zoomed out the groups are boxes and the labels thin out: {res['lod']}")
        await page.keyboard.press("Escape")

        # 7. reduced motion: the * stand still, the bubble shows
        ctx2 = await browser.new_context(**DESKTOP, reduced_motion="reduce")
        p2 = await ctx2.new_page()
        watch.attach(p2, "server-room-reduced")
        await p2.goto(url + "/")
        await ready(p2)
        await until(p2, f"() => window.__dbg.robots.length >= {len(rooms)}", "the robots (reduced motion)", timeout=60000)
        await p2.click(f".tag.room[data-set-project='{pid['three']}']")
        await until(p2, "() => window.__dbg.sr().built && window.__dbg.sr().door", "the door (reduced motion)", timeout=20000)
        await until(p2, "() => window.__dbg.robots.every((R) => !R.path.length)", "settled (reduced motion)", timeout=30000)

        async def hold2(route):
            await p2.wait_for_timeout(1500)
            await route.continue_()
        await p2.route("**/api/infra-docs", hold2)
        at = (await p2.evaluate(SR))["door"]
        await p2.mouse.click(at[0], at[1])
        await until(p2, "() => window.__dbg.sr().phase === 'loading'", "reading (reduced motion)")
        a = await p2.evaluate("() => ({ ...window.__dbg.sr(), t: performance.now() })")
        await until(p2, "(t) => performance.now() > t + 600", "600 ms of the page's own clock", arg=a["t"])
        b = await p2.evaluate(SR)
        res["reduced"] = [a["stars"], b["stars"], (a["bubble"] or {}).get("text")]
        check(failures, a["stars"] == b["stars"] and (a["bubble"] or {}).get("text") == "サーバー構成を読み込んでいます",
              f"reduced motion: the * stand still and the bubble shows: {res['reduced']}")
        await until(p2, "() => window.__dbg.sr().open", "open (reduced motion)", timeout=15000)
        await ctx2.close()

        # 8. the demo (and so export-demo): shop-app/'s door opens the made-up layout, the IAM role and the alarm folded
        ctx3 = await browser.new_context(**DESKTOP)
        p3 = await ctx3.new_page()
        watch.attach(p3, "server-room-demo")
        await p3.goto(url + "/?demo=1")
        await ready(p3)
        await until(p3, "() => window.__dbg.sr().built && !!window.__dbg.sr().door", "the demo's door", timeout=30000)
        demo_door = (await p3.evaluate(SR))["door"]
        await p3.mouse.click(demo_door[0], demo_door[1])
        await until(p3, "() => window.__dbg.sr().phase === 'loading' && window.__dbg.sr().stars > 0", "the demo reads")
        await until(p3, "() => window.__dbg.sr().open", "the demo's server room", timeout=15000)
        s = res["demo"] = await p3.evaluate(SR)
        check(failures, s["shown"]["nodes"] > 0 and s["shown"]["folded"] == 2 and s["shown"]["cross"] > 0 and s["shown"]["external"] == 1
              and s["layers"] == {"near": True, "far": False}, f"the demo's made-up layout: {s['shown']} {s['layers']}")
        for scheme in ("light", "dark"):
            await p3.emulate_media(color_scheme=scheme)
            await p3.screenshot(path=str(out / f"demo-{scheme}.png"))
        # an edge only in staging, between two nodes in both: not in production, there in staging (the edge's own environments)
        prod_edges = await p3.evaluate("() => window.__dbg.srEdges()")
        await p3.select_option("#sr-env", "staging")
        await until(p3, "() => window.__dbg.sr().env === 'staging'", "the demo's staging")
        stg_edges = await p3.evaluate("() => window.__dbg.srEdges()")
        res["demoEdges"] = {"production": "worker>cache" in prod_edges, "staging": "worker>cache" in stg_edges}
        check(failures, res["demoEdges"] == {"production": False, "staging": True}, f"an edge is drawn in its own environments only: {res['demoEdges']}")
        await p3.keyboard.press("Escape")
        await until(p3, "() => !window.__dbg.sr().open", "the demo's office again")
        await ctx3.close()
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    import subprocess as _sp
    res["uptime"] = _sp.run(["uptime"], capture_output=True, text=True).stdout.strip()
    print(f"  server-room: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "server-room-results.json").write_text(dump(res) + "\n")
