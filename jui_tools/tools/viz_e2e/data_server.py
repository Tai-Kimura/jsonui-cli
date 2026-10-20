"""The data server (requester, 10-19; 2.3.5): a rack in a JsonUI room with API / DB specifications, pressed for them.

The real `jui viz serve` in a throwaway HOME on a free port, two real JsonUI rooms made here: one with docs/api (an
OpenAPI with paths, its title carrying <b>) and docs/db (two tables, an enum, and docs/db/analytics/ as a database of
its own), one with neither. Up close, the first has the rack (its built box crossing no desk and no other prop), the
second none. Pressing the rack opens the sheet: API 仕様書 with the endpoints, a row opening its parameters, request
and responses; DB 仕様書 with an ER diagram per database (Mermaid, strict) and the tables' columns. The <b> stays
text. Removing the specifications takes the rack away and putting them back brings it (the file watcher); a changed
title shows on opening again. Mermaid is read from the server; nothing is asked outside. Light and dark pictures, before (`--jt`) and after.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import threading
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, desk_pins_js, new_page, ready
from waits import settled, until

ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
SID_A = "e2e00000-0000-4000-8000-000000000601"
SID_B = "e2e00000-0000-4000-8000-000000000602"
# The first room's desk (floor-view room coordinates), clear of the rack's line of sight from the usual view: the drawn
# desk depended on --out (the room's id is the sha1 of its root), and a desk in front of the rack takes the press
# (measured: pinned at [1.91, 1.6], in front of the rack, the press opened no sheet: "waiting for the sheet" timed out). Ticket
# 2026-10-20-jui-viz-e2e-callbell-dialog-wait-flaky (the family); the product's side: 2026-10-20-jui-viz-callbell-bell-hidden-behind-a-desk.
DESK_A = [6.4, 4.6]
# The press to the sheet read (openDataDocs runs in the pointerup, then the server reads the documents): the cap as it
# was (20 s), not measured under load for the read; a press that opened nothing says so with the page's state.
OPENED_MS = 20000
SHEET_JS_OPEN = "() => { const d = window.__dbg.dataServer(); return d.open && !d.loading; }"
WHY_PRESS = "() => ({ rack: window.__dbg.dataServer(), view: window.__dbg.view() })"
API = {"openapi": "3.0.0", "info": {"title": "Users API <b>bold</b>", "version": "1.2", "description": "ユーザーの API"},
       "paths": {"/users/{id}": {"parameters": [{"name": "id", "in": "path", "required": True, "description": "利用者の ID", "schema": {"type": "string"}}],
                                 "get": {"summary": "一人を取る", "responses": {"200": {"description": "見つかった", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/User"}}}},
                                                                             "404": {"description": "いない"}}},
                                 "delete": {"summary": "消す", "responses": {"204": {"description": "消した"}}}},
                 "/users": {"post": {"summary": "作る", "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/User"}}}},
                                     "responses": {"201": {"description": "作った"}}}}},
       "components": {"schemas": {"User": {"type": "object", "properties": {"id": {"type": "string"}, "email": {"type": "string"}}}}}}
USERS = {"openapi": "3.0.0", "info": {"title": "users", "version": "1", "x-table-name": "users"},
         "components": {"schemas": {"User": {"type": "object", "description": "利用者", "required": ["id", "email"],
                                             "properties": {"id": {"type": "integer", "x-primary-key": True, "x-auto-increment": True},
                                                            "email": {"type": "string", "maxLength": 255, "x-unique": True, "description": "連絡先"},
                                                            "team_id": {"type": "integer", "x-foreign-key": {"table": "teams", "column": "id"}}}},
                                    "Role": {"type": "string", "enum": ["admin", "member"]}}}}
TEAMS = {"openapi": "3.0.0", "info": {"title": "teams", "version": "1", "x-table-name": "teams"},
         "components": {"schemas": {"Team": {"type": "object", "properties": {"id": {"type": "integer", "x-primary-key": True}, "name": {"type": "string"}}}}}}
EVENTS = {"openapi": "3.0.0", "info": {"title": "events", "version": "1", "x-table-name": "events"},
          "components": {"schemas": {"Event": {"type": "object", "properties": {"id": {"type": "integer", "x-primary-key": True}}}}}}

SHEET_JS = """() => { const b = document.getElementById('ds-body'); return { open: !document.getElementById('ds').hidden,
  tabs: [...document.querySelectorAll('#ds-tabs [data-ds-tab]')].map((x) => [x.dataset.dsTab, x.getAttribute('aria-selected')]),
  titles: [...b.querySelectorAll('.ds-doc h3')].map((x) => x.textContent), bold: b.querySelectorAll('h3 b').length,
  eps: [...b.querySelectorAll('.ds-ep')].map((x) => x.textContent), detail: (b.querySelector('.ds-detail') || {}).textContent || '',
  erds: [...b.querySelectorAll('[data-erd]')].map((x) => !!x.querySelector('svg')), tables: [...b.querySelectorAll('.ds-tbl h4')].map((x) => x.textContent),
  cells: [...b.querySelectorAll('.ds-table tbody tr')].slice(0, 40).map((r) => [...r.cells].map((c) => c.textContent)), text: b.textContent.slice(0, 400) }; }"""


def check(failures, cond, text):
    if not cond:
        failures.append(f"data-server: {text}")


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


def _room(root: pathlib.Path, docs: bool):
    (root / "docs" / "screens" / "json").mkdir(parents=True, exist_ok=True)
    (root / "jui.config.json").write_text(json.dumps({"spec_directory": "docs/screens/json"}))
    if docs:
        (root / "docs" / "api").mkdir(parents=True, exist_ok=True)
        (root / "docs" / "api" / "users.json").write_text(json.dumps(API, ensure_ascii=False))
        (root / "docs" / "db" / "analytics").mkdir(parents=True, exist_ok=True)
        (root / "docs" / "db" / "users.json").write_text(json.dumps(USERS, ensure_ascii=False))
        (root / "docs" / "db" / "teams.json").write_text(json.dumps(TEAMS))
        (root / "docs" / "db" / "analytics" / "events.json").write_text(json.dumps(EVENTS))


async def run_data_server(pw, out, failures, jt=None, shots_only=False):
    from run import free_port
    out = pathlib.Path(out) / ("data-server-before" if shots_only else "data-server")
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    room_a, room_b = home / "work" / "spec-app", home / "work" / "plain-app"
    _room(room_a, True)
    _room(room_b, False)
    jt = pathlib.Path(jt) if jt else pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def hook(sid, cwd, **payload):
        body = {"session_id": sid, "cwd": str(cwd), "permission_mode": "default", **payload}
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
        page = await new_page(browser, watch, "data-server", **DESKTOP)
        asked = []
        page.on("request", lambda r: asked.append(r.url))
        await page.emulate_media(color_scheme="light", reduced_motion="no-preference")
        await page.add_init_script(desk_pins_js([(room_a, SID_A, DESK_A)]))
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", label="connected")
        hook(SID_A, room_a, hook_event_name="SessionStart", source="startup")
        hook(SID_B, room_b, hook_event_name="SessionStart", source="startup")
        await wait(page, "() => window.__dbg.robots.length >= 2 && window.__dbg.robots.every((R) => !R.path.length)", timeout=30000, label="seated")
        ids = await page.evaluate("() => Object.fromEntries(window.__dbg.robots.map((R) => [R.def.sessionId, R.def.room]))")
        pa, pb = ids[SID_A], ids[SID_B]

        async def up_close(pid):
            if await page.evaluate("() => window.__dbg.solo()"):
                await page.click("#room-back")
                await wait(page, "() => window.__dbg.solo() === null", label="back to the floor")
            await page.click(f".tag.room[data-set-project='{pid}']")
            await wait(page, f"() => window.__dbg.solo() === '{pid}'", label="one room")
            await wait(page, "() => window.__dbg.robots.every((R) => !R.path.length)", timeout=30000, label="settled up close")
            await page.wait_for_timeout(800)

        if shots_only:   # another tree (--jt): the room with specifications up close, as it was
            await up_close(pa)
            for scheme in ("light", "dark"):
                await page.emulate_media(color_scheme=scheme)
                await page.wait_for_timeout(900)
                await page.screenshot(path=str(out / f"before-room-{scheme}.png"))
            return

        # the room with no specification: no rack
        await up_close(pb)
        b = res["plain"] = await page.evaluate("() => window.__dbg.dataServer()")
        check(failures, b["room"] == pb and not b["built"] and b["wanted"] is False, f"a room without docs/api or docs/db: no rack: {b}")

        # the room with them: the rack, clear of the desks and the other props
        await up_close(pa)
        await wait(page, "() => window.__dbg.dataServer().built", label="the rack")
        a = res["rack"] = await page.evaluate("() => window.__dbg.dataServer()")
        brk = await page.evaluate("() => { const b = window.__dbg.brk(); return { boxes: b.meshBoxes, desks: b.deskBoxes }; }")
        hit = lambda p, q: p and q and p[0] < q[1] and q[0] < p[1] and p[2] < q[3] and q[2] < p[3]
        crossed = [n for n, m in brk["boxes"].items() if n != "dataServer" and hit(a["box"], m)] + [d[0] for d in brk["desks"] if hit(a["box"], d[1])]
        check(failures, not crossed, f"the rack crosses no desk and no other prop: {crossed} rack {a['box']}")
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await wait(page, "() => window.__dbg.dataServer().built", label=f"the rack, {scheme}")
            await page.wait_for_timeout(900)
            await page.screenshot(path=str(out / f"after-room-{scheme}.png"))
        await page.emulate_media(color_scheme="light")
        await wait(page, "() => window.__dbg.dataServer().built", label="the rack again")
        a = await page.evaluate("() => window.__dbg.dataServer()")

        seat = res["seatA"] = await page.evaluate("(sid) => { const R = window.__dbg.robots.find((x) => x.def.sessionId === sid); return R ? window.__dbg.seats()[R.def.id] : null; }", SID_A)
        check(failures, seat and [seat.get("dx"), seat.get("dz")] == DESK_A, f"the first room's desk is where the arm put it {DESK_A}: {seat}")

        # pressed: the sheet, API first
        await settled(page, "the room before the press on the rack")
        await until(page, "() => !window.__dbg.view().tween", "the camera still before the press on the rack", timeout=20000)
        a = await page.evaluate("() => window.__dbg.dataServer()")
        await page.mouse.click(*a["screen"])
        await until(page, SHEET_JS_OPEN, "the sheet", timeout=OPENED_MS, why=WHY_PRESS)
        s = res["api"] = await page.evaluate(SHEET_JS)
        check(failures, s["tabs"] == [["api", "true"], ["db", "false"]], f"two tabs, API first: {s['tabs']}")
        check(failures, s["titles"] == ["Users API <b>bold</b>v1.2docs/api/users.json"] or (s["titles"] and s["titles"][0].startswith("Users API <b>bold</b>")),
              f"the API document, its <b> as text: {s['titles']}")
        check(failures, s["bold"] == 0, "no <b> element from the title")
        check(failures, len(s["eps"]) == 3 and "GET/users/{id}一人を取る" in s["eps"], f"three endpoints: {s['eps']}")
        await page.click("#ds-body .ds-ep:has-text('一人を取る')")
        await page.wait_for_timeout(300)
        s = res["apiOpen"] = await page.evaluate(SHEET_JS)
        check(failures, all(w in s["detail"] for w in ("利用者の ID", "200", "見つかった", "404", "User", "email")),
              f"a row opens its parameters, request and responses (the $ref followed): {s['detail'][:300]}")
        await page.screenshot(path=str(out / "after-api-light.png"))
        await page.click("#ds-tabs [data-ds-tab='db']")
        await wait(page, "() => document.querySelectorAll('#ds-body [data-erd] svg').length === 2", timeout=30000, label="two ER diagrams")
        s = res["db"] = await page.evaluate(SHEET_JS)
        check(failures, s["erds"] == [True, True] and set(s["tables"]) >= {"User", "Team", "Event", "Role enum"},
              f"DB: an ER diagram per database, the tables: {s['erds']} {s['tables']}")
        check(failures, any(c[:2] == ["id", "integer"] and "PRI" in c[4] and "auto_increment" in c[5] for c in s["cells"]),
              f"columns as the schema page shows them: {s['cells']}")
        await page.screenshot(path=str(out / "after-db-light.png"))
        await page.emulate_media(color_scheme="dark")
        await page.wait_for_timeout(300)
        await page.click("#ds-tabs [data-ds-tab='api']")
        await page.click("#ds-tabs [data-ds-tab='db']")
        await wait(page, "() => [...document.querySelectorAll('#ds-body [data-erd]')].every((x) => x.dataset.theme === 'dark' && x.querySelector('svg'))", label="dark ER")
        await page.screenshot(path=str(out / "after-db-dark.png"))
        await page.emulate_media(color_scheme="light")
        await page.keyboard.press("Escape")
        await wait(page, "() => !window.__dbg.dataServer().open && document.getElementById('ds').hidden", label="closed with Escape")

        # a changed title shows on opening again
        changed = {**API, "info": {**API["info"], "title": "Users API v2"}}
        (room_a / "docs" / "api" / "users.json").write_text(json.dumps(changed, ensure_ascii=False))
        await settled(page, "the room before the press on the rack again")
        await until(page, "() => !window.__dbg.view().tween", "the camera still before the press on the rack again", timeout=20000)
        a = await page.evaluate("() => window.__dbg.dataServer()")
        await page.mouse.click(*a["screen"])
        await until(page, SHEET_JS_OPEN, "the sheet again", timeout=OPENED_MS, why=WHY_PRESS)
        s = await page.evaluate(SHEET_JS)
        check(failures, s["titles"] and s["titles"][0].startswith("Users API v2"), f"opening again reads the changed file: {s['titles']}")
        await page.click("#ds-close")
        await wait(page, "() => document.getElementById('ds').hidden", label="closed")

        # 200 documents of 1 MB (200 MB) written and rewritten three times while the rack is pressed again and again
        # (dd's review, 10-19: counted on the event loop for each watcher event, with no total cap, and the press read
        # on it too, /health was held for seconds): the server answers within 1 s all along, and the count (up to
        # its 8 MB) shows on the page
        bulk = room_a / "docs" / "api" / "bulk"
        bulk.mkdir(exist_ok=True)
        pad = list(range(150_000))   # about 1 MB of small numbers: slow to parse, as real documents are
        lat, stop = [], threading.Event()

        def probe():
            while not stop.is_set():
                t = time.monotonic()
                try:
                    urllib.request.urlopen(f"{url}/health", timeout=30).read()
                except OSError:
                    pass
                lat.append(time.monotonic() - t)
                time.sleep(0.1)

        def write_all():
            for rnd in range(3):
                for i in range(200):
                    (bulk / f"api-{i:03}.json").write_text(json.dumps({**API, "info": {"title": f"bulk {i} r{rnd}", "version": "1"}, "x-pad": pad}))
        token = await page.evaluate("() => document.querySelector('meta[name=jui-viz-token]').content")
        reads = []

        def press():   # the rack pressed again and again meanwhile (the page's own request)
            own = f"127.0.0.1:{port}"
            body = json.dumps({"projectId": pa}).encode()
            while not stop.is_set():
                rq = urllib.request.Request(f"{url}/api/data-docs", data=body, method="POST",
                                            headers={"Host": own, "Origin": f"http://{own}", "X-Jui-Viz-Token": token, "Content-Type": "application/json"})
                t = time.monotonic()
                try:
                    urllib.request.urlopen(rq, timeout=60).read()
                except OSError:
                    pass
                reads.append(time.monotonic() - t)
        th = threading.Thread(target=probe, daemon=True)
        th.start()
        th2 = threading.Thread(target=press, daemon=True)
        th2.start()
        writer = threading.Thread(target=write_all)
        writer.start()
        while writer.is_alive():
            await page.wait_for_timeout(200)
        await wait(page, "() => { const d = window.__dbg.dataServer(); return d.docs && d.docs.api > 1; }", timeout=120000, label="the new documents counted")
        await page.wait_for_timeout(2000)   # a little more of the probe after the count
        stop.set()
        th.join()
        th2.join()
        res["health"] = {"n": len(lat), "max": round(max(lat), 3), "p95": round(sorted(lat)[int(len(lat) * 0.95)], 3),
                         "reads": len(reads), "readMax": round(max(reads), 3) if reads else None}
        check(failures, len(lat) >= 10 and max(lat) < 1.0, f"/health within 1 s while 200 documents (200 MB) are written three times and the rack is read: {res['health']}")
        shutil.rmtree(bulk)

        # the files go: the rack goes; they come back: so does it (the watcher)
        shutil.move(str(room_a / "docs" / "api"), str(out / "api-away"))
        shutil.move(str(room_a / "docs" / "db"), str(out / "db-away"))
        await wait(page, "() => !window.__dbg.dataServer().built", timeout=30000, label="the rack gone with the files")
        shutil.move(str(out / "api-away"), str(room_a / "docs" / "api"))
        await wait(page, "() => window.__dbg.dataServer().built", timeout=30000, label="the rack back with docs/api")
        res["mermaidAsked"] = [u for u in asked if "mermaid" in u]
        check(failures, res["mermaidAsked"] == [f"{url}/vendor/mermaid-11.17.2/mermaid.min.js"], f"Mermaid read once, from the server: {res['mermaidAsked']}")
        check(failures, not watch.console and not watch.foreign and not watch.csp,
              f"no console error, nothing outside the server: {watch.console[:3]} {watch.foreign[:3]}")
        await page.close()
    except Exception as e:
        failures.append(f"data-server: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        await browser.close()
        srv.terminate()  # our own child (started above)
        try:
            srv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            srv.kill()
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"  data-server: {time.monotonic() - t0:.0f}s", flush=True)
