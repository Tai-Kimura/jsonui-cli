"""A migration plan played in the server room (ticket 2026-10-22-viz-infra-migration-plan).

The real `jui viz serve` in a throwaway HOME, the real forward.py, the boundary's three-tier example with a plan
written next to it (docs/infra/migrations/move: one node added in a group of its own with an edge to it, one
replaced, one removed with its edge, one edge removed alone) and a second plan with an error; a room with no plan.
What is drawn is read from the 3D (__dbg.srMig: each changed node's size from its instance matrix, each changed
edge's length from the line's positions), never from the plan's own lists alone.

  * the board lists the plans; the one with an error says it in words (its file and place) and cannot be played
  * opened: the old model drawn — the node to come at size 0, its edge at length 0, its group's floor not drawn
  * add: the node grows, then its edge is drawn from its start with the flows' light at its head; after it, both
    whole, no light left, the new floor drawn
  * replace: the old version shrinks (its spec still the old one), then the new one (the new spec) grows
  * remove: its edge shrinks to its middle, then the node shrinks away; the edge removed alone goes at the last step
  * the end: what is drawn is the new model, node for node and edge for edge
  * a step builds nothing (a replaced node's new version is drawn from the start at size 0): the camera and each
    frame's colours hold through a replace; played through, the steps come back to back (no frame without one)
  * a step that moves the month: the amount counts to the new one in the step's colour, a tag with its own difference
    floats over each node that moved (fn-a goes and fn-b, Lambda's free requests now its, moves too), the player lists
    them; the tags always name the step the player shows; paused, nothing moves (the step, the amount, the tags); a
    step taken alone keeps its tags until the next
  * the cost: 旧 → 今 → 新 on the player from the engine's months, the step shown with its own difference, the changed
    nodes with no price said; the コスト view's 旧 · 新 · 差 table (rows with no price marked) and its big number said
    to be the old model's, with the month at the step the player is at
  * back to the start: the old model again; stop: the room's own model (its flows offered again)
  * a room with no plan: no plan on the board
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, T, Watch, new_page, ready
from waits import until

ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
MIG = "() => window.__dbg.srMig()"
CHANGES = {"version": 0, "order": ["cache-prod", "db-prod", "mailer"],
           "groups": [{"id": "cache-subnet", "kind": "subnet", "parent": "vpc-prod"}],
           "nodes": [{"id": "db-prod", "category": "database.relational", "service": "rds.mysql", "group": "private-prod",
                      "engine": "mysql 8.4", "environments": ["production"],
                      "spec": [{"key": "instance_class", "value": "db.r6g.xlarge"}, {"key": "storage_gb", "value": "200"}]},
                     {"id": "cache-prod", "category": "cache", "service": "elasticache.redis", "group": "cache-subnet",
                      "environments": ["production"]}],
           "edges": [{"from": "api-prod", "to": "cache-prod", "protocol": "redis"}]}
REMOVALS = {"version": 0, "nodes": ["mailer", "fn-a"], "edges": [{"from": "cdn", "to": "assets"}]}
# two functions of one account: Lambda's free requests go to the first in the model, so removing fn-a moves fn-b's month
# in the same step (a neighbour that moved: its own tag, and the player's list of what moved)
FUNCTIONS = {"version": 0, "nodes": [
    {"id": f"fn-{x}", "category": "compute.function", "service": "lambda", "group": "private-prod", "environments": ["production"],
     "spec": [{"key": "memory_mb", "value": "512"}]} for x in "ab"],
    "edges": [{"from": "api-prod", "to": "fn-a"}, {"from": "api-prod", "to": "fn-b"}]}
FUNCTION_LOAD = {"requests": {"amount": 0.6, "per": "second"}, "duration_ms": 200, "memory_mb": 512}


FLAT = {"on": False}   # the same arms in 2D (server_room.py FLAT)


def check(failures, cond, text):
    if not cond:
        failures.append(f"{'sr-migration-2d' if FLAT['on'] else 'sr-migration'}: {text}")


class Sampler:
    """__dbg.srMig() read every 40 ms while a step plays (what the player and the tags say at the same moments)."""

    def __init__(self, page):
        self.page, self.seen, self.on = page, [], True

    async def run(self):
        while self.on:
            try:
                self.seen.append(await self.page.evaluate(MIG))
            except Exception:  # noqa: BLE001 - the page between two frames: the next read
                pass
            await asyncio.sleep(0.04)


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


async def run_sr_migration(pw, out, failures, flat=False):
    from run import free_port
    FLAT["on"] = flat
    out = pathlib.Path(out) / ("sr-migration-2d" if flat else "sr-migration")
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    ex = _examples(jt)
    work = home / "work"
    rooms = {"plan": _write(work, ex, "aws-three-tier", "sr-plan"), "none": _write(work, ex, "multi-provider", "sr-noplan")}
    (rooms["plan"] / "docs" / "infra" / "functions.json").write_text(json.dumps(FUNCTIONS), encoding="utf-8")
    for f in (rooms["plan"] / "docs" / "infra" / "load").glob("*.json"):
        doc = json.loads(f.read_text(encoding="utf-8"))
        doc["loads"] += [{"node": n, "quantities": FUNCTION_LOAD} for n in ("fn-a", "fn-b")]
        f.write_text(json.dumps(doc), encoding="utf-8")
    mig = rooms["plan"] / "docs" / "infra" / "migrations"
    (mig / "move").mkdir(parents=True)
    (mig / "move" / "changes.json").write_text(json.dumps(CHANGES), encoding="utf-8")
    (mig / "move" / "removals.json").write_text(json.dumps(REMOVALS), encoding="utf-8")
    (mig / "broken").mkdir()
    (mig / "broken" / "removals.json").write_text(json.dumps({"version": 0, "nodes": ["nowhere"]}), encoding="utf-8")
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT,
                           env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"
    browser = None
    try:   # from the serve's start: whatever stops the suite, the serve stops with it (one was left running, 10-22)
        # the engine's months, as `jsonui-doc cost infra --migration` gives them (the page must say these), with the
        # server's own price cache (its throwaway viz home)
        sys.path.insert(0, str(jt))
        from jui_cli.core.document_tools_import import load_document_tools_module
        _code, cli = load_document_tools_module("infra.cost.diff")[0].reply(rooms["plan"], "move", env={"JUI_VIZ_HOME": str(home / ".local" / "state" / "jui-viz")})
        check(failures, cli.get("ok") and cli["diff"]["usd"] != 0, f"the plan moves the month (the arm needs it): {json.dumps(cli)[:300]}")
        browser = await pw.chromium.launch(args=LAUNCH_ARGS)
        import urllib.request
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        sids = {}
        for i, (name, root) in enumerate(rooms.items()):
            sids[name] = f"5e000000-0000-4000-8000-{i + 100:012d}"
            body = {"session_id": sids[name], "cwd": str(root), "permission_mode": "default", "hook_event_name": "SessionStart", "source": "startup"}
            subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(), capture_output=True,
                           env=dict(base_env, HOME=str(home)), timeout=10)
        page = await new_page(browser, Watch(origin=url), "sr-migration-2d" if flat else "sr-migration", **DESKTOP)
        if flat:
            from server_room import SR_FLAT_INIT
            await page.add_init_script(SR_FLAT_INIT)
        # dark: the washed-out frame showed there (the glow adds to what is behind it), as in the video
        await page.emulate_media(color_scheme="dark", reduced_motion="no-preference")
        await page.goto(url + "/")
        await ready(page)
        await until(page, f"() => window.__dbg.robots.length >= {len(rooms)}", "the rooms", timeout=60000)
        pid = await page.evaluate("() => Object.fromEntries(window.__dbg.robots.map((R) => [R.def.sessionId, R.def.room]))")
        pid = {name: pid[sid] for name, sid in sids.items()}

        # a room with no plan: none on the board
        await page.evaluate(f"() => window.__dbg.srEnter('{pid['none']}')")
        await until(page, "() => window.__dbg.sr().open", "the room with no plan", timeout=30000)
        none = await page.evaluate(MIG)
        heads = await page.evaluate("() => [...document.querySelectorAll('#sr-board h3')].map((h) => h.textContent)")
        check(failures, none["plans"] == [] and T("sr.mig.board.title") not in heads, f"a room with no plan lists none: {none['plans']} {heads}")
        await page.click("#sr-back")
        await until(page, "() => !window.__dbg.sr().open", "closed")

        await page.evaluate(f"() => window.__dbg.srEnter('{pid['plan']}')")
        await until(page, "() => window.__dbg.sr().open", "the room with plans", timeout=30000)
        flows_before = (await page.evaluate("() => window.__dbg.srFlow()"))["starts"]
        got = await page.evaluate(MIG)
        plans = {p["name"]: p for p in got["plans"]}
        check(failures, set(plans) == {"move", "broken"} and plans["move"]["ok"] and not plans["broken"]["ok"], f"both plans listed, one usable: {got['plans']}")
        words = T("srv.room.migration", where="docs/infra/migrations/broken/removals.json", path="/nodes/0",
                  why=T("srv.room.migration.remove_missing"), code="migration.remove_missing")
        board = await page.inner_text("#sr-board")
        check(failures, words in board, f"the broken plan's problem in words on the board: {words!r} not in the board")
        check(failures, await page.is_disabled("#sr-board [data-sr-mig='broken']") and not await page.is_disabled("#sr-board [data-sr-mig='move']"),
              "the plan with an error cannot be played")

        await page.click("#sr-board [data-sr-mig='move']")
        await until(page, "() => window.__dbg.srMig().open && window.__dbg.srMig().cost", "the plan open, its cost read", timeout=30000)
        m = await page.evaluate(MIG)
        res = {"open": m}
        check(failures, m["k"] == 0 and m["sizes"].get("cache-prod") == 0 and m["sizes"].get("mailer") == 1 and m["sizes"].get("db-prod") == 1,
              f"opened: the old model — the node to come at size 0, the others whole: {m['sizes']}")
        check(failures, m["lengths"].get("api-prod->cache-prod") == 0 and m["lengths"].get("api-prod->mailer") == 1,
              f"opened: the edge to come at length 0, the one to go whole: {m['lengths']}")
        check(failures, "cache-subnet" not in m["floors"] and "private-prod" in m["floors"], f"the new group's floor waits for its node: {m['floors']}")
        check(failures, m["specs"]["db-prod"].startswith("db.r6g.large"), f"the replaced node drawn as the old one: {m['specs']}")
        usd = lambda v: page.evaluate("(v) => window.__dbg.srMigUsd(v)", v)  # noqa: E731
        signed = lambda v: page.evaluate("(v) => window.__dbg.srMigSigned(v)", v)  # noqa: E731
        unpriced = T("sr.mig.unpriced.bar", n=len(cli["unpricedChanged"]))
        check(failures, cli["unpricedChanged"] and unpriced in await page.inner_text("#sr-mplayer"),
              f"a changed node with no price is said on the player: {cli['unpricedChanged']} {unpriced!r}")
        async def bar_text(now_usd):
            return f'{T("sr.mig.cost.old", old=await usd(cli["old"]["usd"]))} → {await usd(now_usd)} → {T("sr.mig.cost.new", new=await usd(cli["new"]["usd"]))}'
        bar_old = await bar_text(cli["old"]["usd"])
        check(failures, m["bar"].startswith(bar_old), f"the player's cost is the engine's old and new: {m['bar']!r} vs {bar_old!r}")

        await page.evaluate("() => window.__dbg.srMigSpeed(0.5)")
        # add: the node grows, then its edge is drawn with a light at its head
        await page.click("#sr-mplayer [data-sr-mp='step']")
        await until(page, "() => { const m = window.__dbg.srMig(); return m.sizes['cache-prod'] > 0.05 && m.sizes['cache-prod'] < 0.95; }", "the node growing", timeout=20000)
        await until(page, "() => { const m = window.__dbg.srMig(); const l = m.lengths['api-prod->cache-prod']; return l > 0.1 && l < 0.9 && m.lights >= 1; }", "the edge drawn with its light", timeout=20000)
        res["adding"] = await page.evaluate(MIG)
        # built again while the light draws the edge (a theme or an environment changed then): no frame in other colours
        # (a new renderer per build drew that first frame washed out — floors white, models pale: the video, 10-22)
        await page.evaluate("() => window.__dbg.srPixTrail(true)")
        await page.wait_for_timeout(150)
        await page.evaluate("() => window.__dbg.srRebuildHere()")
        await page.wait_for_timeout(300)
        pix = await page.evaluate("() => window.__dbg.srPixTrail(false)")
        jumps = [i for i in range(1, len(pix)) if max(abs(a - b) for a, b in zip(pix[i], pix[i - 1])) > 15]
        check(failures, len(pix) > 10 and not jumps, f"built again mid-step, every frame keeps its colours: {len(pix)} frames, jumps {[(i, pix[i - 1], pix[i]) for i in jumps[:3]]}")
        await until(page, "() => { const m = window.__dbg.srMig(); return m.k === 1 && !m.anim; }", "step 1 done", timeout=20000)
        m = await page.evaluate(MIG)
        check(failures, m["sizes"]["cache-prod"] == 1 and m["lengths"]["api-prod->cache-prod"] == 1 and m["lights"] == 0 and "cache-subnet" in m["floors"],
              f"added: the node and its edge whole, no light left, its floor drawn: {m['sizes']} {m['lengths']} {m['lights']} {m['floors']}")

        # replace: the old one shrinks (old spec), then the new one grows (new spec); the room drawn again on the way
        # with the camera where it was, not one frame from elsewhere (the fit view flashed for two frames: the video)
        # moved in on the node first: the fit camera is then somewhere else (at the fit view the two are one place)
        await page.evaluate("() => window.__dbg.srSelect('db-prod')")
        await page.click("#sr-board [data-sr-act='focus']")
        await page.wait_for_timeout(300)
        builds = (await page.evaluate(MIG))["builds"]
        sampler = Sampler(page)
        sampling = asyncio.create_task(sampler.run())
        await page.evaluate("() => { window.__dbg.srCamTrail(true); window.__dbg.srPixTrail(true); }")
        await page.click("#sr-mplayer [data-sr-mp='step']")
        await until(page, "() => { const m = window.__dbg.srMig(); return m.anim && m.anim.t > 0.1 && m.anim.t < 0.45 && m.sizes['db-prod'] < 0.9; }", "the old one shrinking", timeout=20000)
        m = await page.evaluate(MIG)
        check(failures, m["specs"]["db-prod"].startswith("db.r6g.large"), f"shrinking, it is the old one: {m['specs']}")
        check(failures, m["vers"]["db-prod"].get("old", 0) < 1 and m["vers"]["db-prod"].get("new") == 0, f"first half: the old version shrinking, the new not yet: {m['vers']}")
        await until(page, "() => { const m = window.__dbg.srMig(); return m.anim && m.anim.t > 0.55 && m.sizes['db-prod'] < 0.9; }", "the new one growing", timeout=20000)
        m = await page.evaluate(MIG)
        check(failures, m["specs"]["db-prod"].startswith("db.r6g.xlarge"), f"growing, it is the new one: {m['specs']}")
        check(failures, m["vers"]["db-prod"].get("old") == 0 and 0 < m["vers"]["db-prod"].get("new", 0) < 1, f"second half: the new version growing, the old gone: {m['vers']}")
        await until(page, "() => { const m = window.__dbg.srMig(); return m.k === 2 && !m.anim; }", "step 2 done", timeout=20000)
        sampler.on = False
        await sampling
        seen = [x for x in sampler.seen if x.get("open")]
        # the month moved: over the step the amount counts to the new one in the step's colour; over each node whose
        # month moved in the step, a tag with that node's own difference, standing while the player shows that step
        frm, to = cli["steps"][0]["usd"], cli["steps"][1]["usd"]
        nows = [x["now"] for x in seen if x["now"]]
        between = [s for s in nows if min(frm, to) + 0.01 < float(s.replace("$", "").replace(",", "")) < max(frm, to) - 0.01]
        final = (await page.evaluate(MIG))
        check(failures, frm != to and between and final["now"] == await usd(to), f"the amount counts from {frm} to {to}: {nows[:3]} … {final['now']}")
        want_cls = "sr-up" if to > frm else "sr-down"
        check(failures, want_cls in final["nowClass"], f"the amount in the step's colour ({want_cls}): {final['nowClass']!r}")
        tags = {(tg["node"], tg["text"], tg["up"]) for x in seen for tg in x["tags"]}
        want_tags = set()
        for mv in cli["steps"][1]["moved"]:
            if mv["node"] in final["drawnNodes"] or mv["node"] in final["sizes"]:
                want_tags.add((mv["node"], await signed(mv["diff"]), mv["diff"] > 0))
        check(failures, want_tags and want_tags <= tags, f"a tag over each node that moved, its own difference: {sorted(want_tags)} vs {sorted(tags)}")
        off = [(x["barStep"], [tg["step"] for tg in x["tags"]]) for x in seen if any(tg["step"] != x["barStep"] for tg in x["tags"])]
        check(failures, not off, f"the tags stand for the step the player shows: {off[:3]}")
        trail = await page.evaluate("() => window.__dbg.srCamTrail(false)")
        pix = await page.evaluate("() => window.__dbg.srPixTrail(false)")
        jumps = [i for i in range(1, len(pix)) if max(abs(a - b) for a, b in zip(pix[i], pix[i - 1])) > 15]
        check(failures, len(pix) > 10 and not jumps, f"no frame in other colours through the replace: {len(pix)} frames, jumps at {[(i, pix[i - 1], pix[i]) for i in jumps[:3]]}")
        check(failures, (await page.evaluate(MIG))["builds"] == builds, f"a step builds nothing: {builds} builds before, {(await page.evaluate(MIG))['builds']} after")
        moved = [i for i, c in enumerate(trail) if max(abs(a - b) for a, b in zip(c, trail[0])) > 1e-6]
        fit = await page.evaluate("() => { const t = window.__dbg.srFitCamera(); return t; }")
        check(failures, max(abs(a - b) for a, b in zip(fit, trail[0])) > 1.0, f"the arm stands away from the fit camera: {fit} vs {trail[0]}")
        check(failures, len(trail) > 10 and not moved, f"the camera held through the replace's redraw: {len(trail)} frames, moved at {moved[:5]} {trail[moved[0]] if moved else ''} vs {trail[0] if trail else ''}")
        m = await page.evaluate(MIG)
        check(failures, m["sizes"]["db-prod"] == 1 and m["lengths"].get("api-prod->db-prod", 1) == 1, f"replaced: whole, its edges kept: {m['sizes']} {m['lengths']}")

        # remove: its edge shrinks to its middle, then the node goes; the bar's difference is this step's
        sent_before = (await page.evaluate(MIG))["sent"]["api-prod->mailer"]
        await page.click("#sr-mplayer [data-sr-mp='step']")
        await until(page, "() => { const l = window.__dbg.srMig().lengths['api-prod->mailer']; return l > 0.05 && l < 0.95; }", "the edge going", timeout=20000)
        m = await page.evaluate(MIG)
        check(failures, m["sent"]["api-prod->mailer"] > sent_before,   # the cables' ends written are drawn: handed to the GPU
              f"the edge going is handed to the GPU as it shrinks: {sent_before} -> {m['sent']['api-prod->mailer']}")
        step_diff = T("sr.mig.cost.step", diff=await signed(cli["steps"][2]["diff"]))
        check(failures, step_diff in m["bar"], f"the bar's difference is the step played: {m['bar']!r} lacks {step_diff!r}")
        await until(page, "() => { const s = window.__dbg.srMig().sizes['mailer']; return s > 0.05 && s < 0.95; }", "the node shrinking away", timeout=20000)
        await until(page, "() => { const m = window.__dbg.srMig(); return m.k === 3 && !m.anim; }", "step 3 done", timeout=20000)
        m = await page.evaluate(MIG)
        check(failures, m["sizes"]["mailer"] == 0 and m["lengths"]["api-prod->mailer"] == 0 and m["lengths"]["cdn->assets"] == 1,
              f"removed: the node and its edge gone, the edge removed alone still there: {m['sizes']} {m['lengths']}")

        # fn-a goes: fn-b moves in the same step (Lambda's free requests now its): a tag over each with its own difference,
        # and the player lists both
        step4 = next(s for s in cli["steps"] if s["node"] == "fn-a")
        moved4 = {m["node"]: m["diff"] for m in step4["moved"]}
        check(failures, set(moved4) == {"fn-a", "fn-b"}, f"the arm needs a neighbour that moves: {step4['moved']}")
        sampler = Sampler(page)
        sampling = asyncio.create_task(sampler.run())
        await page.click("#sr-mplayer [data-sr-mp='step']")
        await until(page, "() => { const m = window.__dbg.srMig(); return m.k === 4 && !m.anim; }", "step 4 done", timeout=20000)
        sampler.on = False
        await sampling
        tags4 = {(tg["node"], tg["text"]) for x in sampler.seen if x.get("open") for tg in x["tags"] if tg["step"] == 4}
        want4 = set()
        for n, d in moved4.items():
            want4.add((n, await signed(d)))
        check(failures, want4 <= tags4, f"a tag over each node that moved, the neighbour too: {sorted(want4)} vs {sorted(tags4)}")
        # stepped one at a time, the tags stay to be read until the next step
        await page.wait_for_timeout(1500)
        kept = [tg for tg in (await page.evaluate(MIG))["tags"] if tg["step"] == 4]
        check(failures, len(kept) == len(want4) and all(tg["opacity"] == 1 for tg in kept), f"a stepped step's tags stay, whole: {kept}")
        listed = [x["moved"] for x in sampler.seen if x.get("open") and x["barStep"] == 4 and x["moved"]]
        want_list = T("sr.mig.moved", list=" · ".join([f"{m['node']} {await signed(m['diff'])}" for m in step4["moved"][:4]]))
        check(failures, listed and listed[0] == want_list, f"the player lists what moved in the step: {listed[:1]} vs {want_list!r}")

        # the rest played: the end is the new model
        await page.evaluate("() => window.__dbg.srMigSpeed(3)")
        builds = (await page.evaluate(MIG))["builds"]
        await page.click("#sr-mplayer [data-sr-mp='toggle']")
        await until(page, "() => { const m = window.__dbg.srMig(); return m.state === 'done' && !m.anim; }", "played to the end", timeout=30000)
        m = await page.evaluate(MIG)
        check(failures, m["idle"] == 0 and m["builds"] == builds, f"played through: no frame without a step, nothing built: idle {m['idle']}, builds {builds} → {m['builds']}")
        res["end"] = m
        check(failures, m["drawnNodes"] == m["newNodes"] and m["drawnEdges"] == m["newEdges"],
              f"the end is the new model: nodes {sorted(set(m['drawnNodes']) ^ set(m['newNodes']))} edges {sorted(set(m['drawnEdges']) ^ set(m['newEdges']))}")
        check(failures, m["lengths"]["cdn->assets"] == 0 and m["specs"]["db-prod"].startswith("db.r6g.xlarge"), f"the end: {m['lengths']} {m['specs']}")
        bar_new = await bar_text(cli["new"]["usd"])
        check(failures, m["bar"].startswith(bar_new), f"at the end now is the new month: {m['bar']!r} vs {bar_new!r}")
        await page.screenshot(path=str(out / "end.png"))

        # built again where it stands: no frame in other colours (a new renderer per build drew its first frame washed out)
        await page.evaluate("() => window.__dbg.srPixTrail(true)")
        await page.wait_for_timeout(300)
        await page.evaluate("() => window.__dbg.srRebuildHere()")
        await page.wait_for_timeout(500)
        pix = await page.evaluate("() => window.__dbg.srPixTrail(false)")
        jumps = [i for i in range(1, len(pix)) if max(abs(a - b) for a, b in zip(pix[i], pix[i - 1])) > 15]
        check(failures, len(pix) > 10 and not jumps, f"a build where it stands keeps every frame's colours: {len(pix)} frames, jumps {[(i, pix[i - 1], pix[i]) for i in jumps[:3]]}")

        # the cost view: 旧 · 新 · 差 by node
        await page.click("#sr-mode-cost")
        await until(page, "() => !!document.querySelector('[data-src-mig]')", "the cost view's columns", timeout=30000)
        row = await page.evaluate("() => [...document.querySelectorAll('[data-src-mig-nodes] [data-sr-mig-row=\"db-prod\"] td')].map((c) => c.textContent)")
        want = next(r for r in cli["byNode"] if r["node"] == "db-prod")
        want_row = [await usd(want["old"]), await usd(want["new"]), await signed(want["diff"])]
        check(failures, row == want_row, f"the cost view's db-prod row is the engine's: {row} vs {want_row}")
        cells = await page.evaluate("() => [...document.querySelectorAll('[data-src-mig] td')].map((c) => c.textContent)")
        import re
        odd = [c for c in cells if not re.fullmatch(r"[+−]?\$[\d,]+\.\d{2}|[+−]?\(?< \$0\.01\)?", c)]   # usdText: to the cent, under it "< $0.01"
        check(failures, cells and not odd, f"the cost view's amounts in dollars and cents: {odd[:5]}")
        small = await usd(0.2349)
        check(failures, small == "$0.23", f"under a dollar too, two places (the cost view's other screens): {small!r}")
        marked = await page.evaluate("() => [...document.querySelectorAll('[data-src-mig-nodes] [data-src-mig-unpriced]')].map((s) => s.closest('[data-sr-mig-row]').dataset.srMigRow).sort()")
        want_marked = sorted(r["node"] for r in cli["byNode"] if r["unpriced"] and (r["old"] or r["new"] or r["change"] != "same"))[:15]
        check(failures, marked == want_marked and set(cli["unpricedChanged"]) <= set(marked), f"the rows with no price are marked: {marked} vs {want_marked}")
        now = await page.inner_text("[data-src-mig-now]")
        want_now = T("sr.mig.total.old") + " · " + T("sr.mig.total.now", k=m["n"], n=m["n"], usd=await usd(cli["new"]["usd"]))
        check(failures, now == want_now, f"the big number says it is the old model's, and the month now: {now!r} vs {want_now!r}")
        await page.click("#sr-mode-3d")

        # back to the start, then stop
        await page.click("#sr-mplayer [data-sr-mp='reset']")
        await until(page, "() => window.__dbg.srMig().k === 0", "back to the start", timeout=20000)
        m = await page.evaluate(MIG)
        check(failures, m["sizes"]["cache-prod"] == 0 and m["sizes"]["mailer"] == 1 and m["lengths"]["cdn->assets"] == 1 and m["specs"]["db-prod"].startswith("db.r6g.large"),
              f"back to the start: the old model again: {m['sizes']} {m['lengths']} {m['specs']}")
        # played through from the start: the steps back to back (no frame without one), nothing built, the end the new model
        builds = m["builds"]
        await page.evaluate("() => window.__dbg.srMigSpeed(1)")
        sampler = Sampler(page)
        sampling = asyncio.create_task(sampler.run())
        await page.click("#sr-mplayer [data-sr-mp='toggle']")
        # paused in the middle of the step that moves db-prod: the step, the amount and its tags stand still
        await until(page, "() => { const m = window.__dbg.srMig(); return m.anim && m.anim.i === 2 && m.anim.t > 0.3 && m.tags.length; }", "playing step 2 with its tag", timeout=30000)
        await page.click("#sr-mplayer [data-sr-mp='toggle']")
        await page.wait_for_timeout(100)
        held = await page.evaluate(MIG)
        await page.wait_for_timeout(900)
        later = await page.evaluate(MIG)
        same = held["state"] == "pause" and held["anim"] == later["anim"] and held["now"] == later["now"] and \
            [(tg["node"], tg["opacity"], tg["transform"]) for tg in held["tags"]] == [(tg["node"], tg["opacity"], tg["transform"]) for tg in later["tags"]]
        check(failures, same and held["tags"], f"paused, nothing moves: {held['anim']} {held['now']} {held['tags']} → {later['anim']} {later['now']} {later['tags']}")
        await page.click("#sr-mplayer [data-sr-mp='toggle']")
        await until(page, "() => { const m = window.__dbg.srMig(); return m.state === 'done' && !m.anim; }", "played through from the start", timeout=30000)
        sampler.on = False
        await sampling
        off = [(x["barStep"], [tg["step"] for tg in x["tags"]]) for x in sampler.seen if x.get("open") and any(tg["step"] != x["barStep"] for tg in x["tags"])]
        check(failures, not off and any(x.get("tags") for x in sampler.seen), f"played through, the tags stand for the step the player shows: {off[:3]}")
        m = await page.evaluate(MIG)
        check(failures, m["idle"] == 0 and m["builds"] == builds and m["drawnNodes"] == m["newNodes"] and m["drawnEdges"] == m["newEdges"],
              f"played through from the start: idle frames {m['idle']}, builds {builds} → {m['builds']}, the end the new model {m['drawnNodes'] == m['newNodes'] and m['drawnEdges'] == m['newEdges']}")
        await page.click("#sr-mplayer [data-sr-mp='stop']")
        await until(page, "() => !window.__dbg.srMig().open", "stopped", timeout=20000)
        after = (await page.evaluate("() => window.__dbg.srFlow()"))["starts"]
        check(failures, after == flows_before and await page.is_hidden("#sr-mplayer"), f"stopped: the room's own model, its flows offered again: {after} vs {flows_before}")
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    finally:
        if browser is not None:
            await browser.close()
        srv.terminate()   # our own child (started above)
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
            srv.wait()
