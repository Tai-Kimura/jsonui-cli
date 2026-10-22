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
  * replace redraws the room with the camera held: no frame from the fit camera between
  * the cost: 旧 → 今 → 新 on the player from the engine's months, the step shown with its own difference, the changed
    nodes with no price said; the コスト view's 旧 · 新 · 差 table (rows with no price marked) and its big number said
    to be the old model's, with the month at the step the player is at
  * back to the start: the old model again; stop: the room's own model (its flows offered again)
  * a room with no plan: no plan on the board
"""
from __future__ import annotations

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
REMOVALS = {"version": 0, "nodes": ["mailer"], "edges": [{"from": "cdn", "to": "assets"}]}


def check(failures, cond, text):
    if not cond:
        failures.append(f"sr-migration: {text}")


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


async def run_sr_migration(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "sr-migration"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    ex = _examples(jt)
    work = home / "work"
    rooms = {"plan": _write(work, ex, "aws-three-tier", "sr-plan"), "none": _write(work, ex, "multi-provider", "sr-noplan")}
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
    # the engine's months, as `jsonui-doc cost infra --migration` gives them (the page must say these), with the
    # server's own price cache (its throwaway viz home)
    sys.path.insert(0, str(jt))
    from jui_cli.core.document_tools_import import load_document_tools_module
    _code, cli = load_document_tools_module("infra.cost.diff")[0].reply(rooms["plan"], "move", env={"JUI_VIZ_HOME": str(home / ".local" / "state" / "jui-viz")})
    check(failures, cli.get("ok") and cli["diff"]["usd"] != 0, f"the plan moves the month (the arm needs it): {json.dumps(cli)[:300]}")
    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
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
            sids[name] = f"5e000000-0000-4000-8000-{i + 100:012d}"
            body = {"session_id": sids[name], "cwd": str(root), "permission_mode": "default", "hook_event_name": "SessionStart", "source": "startup"}
            subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(), capture_output=True,
                           env=dict(base_env, HOME=str(home)), timeout=10)
        page = await new_page(browser, Watch(origin=url), "sr-migration", **DESKTOP)
        await page.emulate_media(color_scheme="light", reduced_motion="no-preference")
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
        usd = lambda v: page.evaluate("(v) => window.__dbg.srcUsd(v)", v)  # noqa: E731
        unpriced = T("sr.mig.unpriced.bar", n=len(cli["unpricedChanged"]))
        check(failures, cli["unpricedChanged"] and unpriced in await page.inner_text("#sr-mplayer"),
              f"a changed node with no price is said on the player: {cli['unpricedChanged']} {unpriced!r}")
        bar_old = T("sr.mig.cost", old=await usd(cli["old"]["usd"]), now=await usd(cli["old"]["usd"]), new=await usd(cli["new"]["usd"]))
        check(failures, m["bar"].startswith(bar_old), f"the player's cost is the engine's old and new: {m['bar']!r} vs {bar_old!r}")

        await page.evaluate("() => window.__dbg.srMigSpeed(0.5)")
        # add: the node grows, then its edge is drawn with a light at its head
        await page.click("#sr-mplayer [data-sr-mp='step']")
        await until(page, "() => { const m = window.__dbg.srMig(); return m.sizes['cache-prod'] > 0.05 && m.sizes['cache-prod'] < 0.95; }", "the node growing", timeout=20000)
        await until(page, "() => { const m = window.__dbg.srMig(); const l = m.lengths['api-prod->cache-prod']; return l > 0.1 && l < 0.9 && m.lights >= 1; }", "the edge drawn with its light", timeout=20000)
        res["adding"] = await page.evaluate(MIG)
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
        await page.evaluate("() => window.__dbg.srCamTrail(true)")
        await page.click("#sr-mplayer [data-sr-mp='step']")
        await until(page, "() => { const m = window.__dbg.srMig(); return m.anim && m.anim.t > 0.1 && m.anim.t < 0.45 && m.sizes['db-prod'] < 0.9; }", "the old one shrinking", timeout=20000)
        m = await page.evaluate(MIG)
        check(failures, m["specs"]["db-prod"].startswith("db.r6g.large"), f"shrinking, it is the old one: {m['specs']}")
        await until(page, "() => { const m = window.__dbg.srMig(); return m.anim && m.anim.t > 0.55 && m.sizes['db-prod'] < 0.9; }", "the new one growing", timeout=20000)
        m = await page.evaluate(MIG)
        check(failures, m["specs"]["db-prod"].startswith("db.r6g.xlarge"), f"growing, it is the new one: {m['specs']}")
        await until(page, "() => { const m = window.__dbg.srMig(); return m.k === 2 && !m.anim; }", "step 2 done", timeout=20000)
        trail = await page.evaluate("() => window.__dbg.srCamTrail(false)")
        moved = [i for i, c in enumerate(trail) if max(abs(a - b) for a, b in zip(c, trail[0])) > 1e-6]
        fit = await page.evaluate("() => { const t = window.__dbg.srFitCamera(); return t; }")
        check(failures, max(abs(a - b) for a, b in zip(fit, trail[0])) > 1.0, f"the arm stands away from the fit camera: {fit} vs {trail[0]}")
        check(failures, len(trail) > 10 and not moved, f"the camera held through the replace's redraw: {len(trail)} frames, moved at {moved[:5]} {trail[moved[0]] if moved else ''} vs {trail[0] if trail else ''}")
        m = await page.evaluate(MIG)
        check(failures, m["sizes"]["db-prod"] == 1 and m["lengths"].get("api-prod->db-prod", 1) == 1, f"replaced: whole, its edges kept: {m['sizes']} {m['lengths']}")

        # remove: its edge shrinks to its middle, then the node goes; the bar's difference is this step's
        await page.click("#sr-mplayer [data-sr-mp='step']")
        await until(page, "() => { const l = window.__dbg.srMig().lengths['api-prod->mailer']; return l > 0.05 && l < 0.95; }", "the edge going", timeout=20000)
        m = await page.evaluate(MIG)
        step_diff = T("sr.mig.cost.step", diff=("+" if cli["steps"][2]["diff"] >= 0 else "−") + await usd(abs(cli["steps"][2]["diff"])))
        check(failures, step_diff in m["bar"], f"the bar's difference is the step played: {m['bar']!r} lacks {step_diff!r}")
        await until(page, "() => { const s = window.__dbg.srMig().sizes['mailer']; return s > 0.05 && s < 0.95; }", "the node shrinking away", timeout=20000)
        await until(page, "() => { const m = window.__dbg.srMig(); return m.k === 3 && !m.anim; }", "step 3 done", timeout=20000)
        m = await page.evaluate(MIG)
        check(failures, m["sizes"]["mailer"] == 0 and m["lengths"]["api-prod->mailer"] == 0 and m["lengths"]["cdn->assets"] == 1,
              f"removed: the node and its edge gone, the edge removed alone still there: {m['sizes']} {m['lengths']}")

        # the rest played: the end is the new model
        await page.evaluate("() => window.__dbg.srMigSpeed(3)")
        await page.click("#sr-mplayer [data-sr-mp='toggle']")
        await until(page, "() => { const m = window.__dbg.srMig(); return m.state === 'done' && !m.anim; }", "played to the end", timeout=30000)
        m = await page.evaluate(MIG)
        res["end"] = m
        check(failures, m["drawnNodes"] == m["newNodes"] and m["drawnEdges"] == m["newEdges"],
              f"the end is the new model: nodes {sorted(set(m['drawnNodes']) ^ set(m['newNodes']))} edges {sorted(set(m['drawnEdges']) ^ set(m['newEdges']))}")
        check(failures, m["lengths"]["cdn->assets"] == 0 and m["specs"]["db-prod"].startswith("db.r6g.xlarge"), f"the end: {m['lengths']} {m['specs']}")
        bar_new = T("sr.mig.cost", old=await usd(cli["old"]["usd"]), now=await usd(cli["new"]["usd"]), new=await usd(cli["new"]["usd"]))
        check(failures, m["bar"].startswith(bar_new), f"at the end now is the new month: {m['bar']!r} vs {bar_new!r}")
        await page.screenshot(path=str(out / "end.png"))

        # the cost view: 旧 · 新 · 差 by node
        await page.click("#sr-mode-cost")
        await until(page, "() => !!document.querySelector('[data-src-mig]')", "the cost view's columns", timeout=30000)
        row = await page.evaluate("() => [...document.querySelectorAll('[data-src-mig-nodes] [data-sr-mig-row=\"db-prod\"] td')].map((c) => c.textContent)")
        want = next(r for r in cli["byNode"] if r["node"] == "db-prod")
        want_row = [await usd(want["old"]), await usd(want["new"]), ("+" if want["diff"] >= 0 else "−") + await usd(abs(want["diff"]))]
        check(failures, row == want_row, f"the cost view's db-prod row is the engine's: {row} vs {want_row}")
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
        await page.click("#sr-mplayer [data-sr-mp='stop']")
        await until(page, "() => !window.__dbg.srMig().open", "stopped", timeout=20000)
        after = (await page.evaluate("() => window.__dbg.srFlow()"))["starts"]
        check(failures, after == flows_before and await page.is_hidden("#sr-mplayer"), f"stopped: the room's own model, its flows offered again: {after} vs {flows_before}")
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    finally:
        await browser.close()
        srv.terminate()
        srv.wait(10)
