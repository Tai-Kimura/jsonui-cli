"""The live view against fake_server.py (scenarios.py), checked against plan P3's acceptance list.

Each check appends a readable line to `failures` when it does not hold, and the measured values go to
<out>/live-results.json. Step the scenario with POST /_fake/step?to=<mark>; read the page through window.__dbg.
"""

from __future__ import annotations

import json
import pathlib
import time
import urllib.request

import hooks
import scenarios
from common import DESKTOP, LAUNCH_ARGS, PHONE, Watch, dump, new_page, ready

ROOM_OF = """(id) => { const R = window.__dbg.robots.find((x) => x.def.id === id); if (!R) return null;
  const p = R.robot.root.position; return { x: p.x, z: p.z, state: R.robot.state, room: R.def.room,
  tag: R.tag.textContent, desk: R.robot.desk ? R.robot.desk.visible : null }; }"""


def step(srv, mark):
    req = urllib.request.Request(f"{srv.url}/_fake/step?to={mark}", method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def fake_state(srv):
    with urllib.request.urlopen(f"{srv.url}/_fake/state", timeout=5) as r:
        return json.loads(r.read())


async def robot(page, rid):
    return await page.evaluate(ROOM_OF, rid)


async def rooms(page):
    return await page.evaluate("""() => [...document.querySelectorAll('.tag.room')].map((t) => t.textContent)""")


async def wait(page, js, arg=None, timeout=20000, polling="raf", label=""):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=polling)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


def check(failures, cond, text):
    if not cond:
        failures.append(f"live: {text}")


async def scenario_two_projects(browser, srv, out, failures, res):
    watch = Watch(origin=srv.url)
    step(srv, "start")   # 2 projects, 3 sessions — already there when the page opens
    page = await new_page(browser, watch, "live", **DESKTOP)
    await page.goto(srv.url + "/")
    await ready(page)
    await page.evaluate("() => { window.__marker = 'same page'; }")
    await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'")
    await wait(page, "() => document.querySelectorAll('.tag.room').length === 2 && window.__dbg.robots.length === 3")
    await page.wait_for_timeout(1500)
    res["rooms"] = await rooms(page)
    res["robots"] = {rid: await robot(page, rid) for rid in ("a0", "b4", "4f")}
    res["chips"] = await page.evaluate("() => [...document.querySelectorAll('.chips .chip')].filter((c) => !c.hidden).map((c) => c.textContent)")
    res["controls"] = await page.evaluate("() => ['btn-play', 'btn-speed'].map((id) => document.getElementById(id).hidden)")
    res["sessions"] = await page.evaluate("() => [...document.querySelectorAll('#sessions .pg-toggle')].map((b) => b.textContent)")
    check(failures, res["rooms"] == ["shop-app/", "jsonui-cli/"], f"two rooms in order, got {res['rooms']}")
    check(failures, res["controls"] == [True, True], "play / speed hidden in the live view")
    check(failures, "127.0.0.1" in " ".join(res["chips"]) and "デモ（実データではない）" not in res["chips"], f"chips name the server, not the demo: {res['chips']}")
    rb = res["robots"]
    check(failures, all(rb[r] and rb[r]["state"] in ("idle", "command") for r in rb), f"robots seated with their states: {rb}")
    check(failures, rb["a0"]["room"] == rb["b4"]["room"] == "p-shop" and rb["4f"]["room"] == "p-cli", "robots in their sessions' rooms")
    await page.screenshot(path=f"{out}/live-start.png")

    # A tool call: the robot's state and "now doing" within 1 s of the server sending it. Measured twice:
    # the model (polled every 50 ms, independent of the frame rate) and the drawn robot and its tag (polled per
    # frame — the headless renderer draws 1–3 frames a second, so this one is reported, not judged).
    t0 = time.monotonic()
    step(srv, "tool")
    await wait(page, "() => { const s = window.__dbg.robotState().a0; return s && s.state === 'typing' && s.act === 'Write docs/screens/json/login.spec.json'; }",
               timeout=5000, polling=50, label="a0 typing in the model")
    res["toolLatencyMs"] = round((time.monotonic() - t0) * 1000)
    await wait(page, "() => { const R = window.__dbg.robots.find((x) => x.def.id === 'a0'); return R && R.robot.state === 'typing' && R.tag.textContent.includes('Write docs/screens/json/login.spec.json'); }",
               timeout=10000, label="a0 typing on screen")
    res["toolOnScreenMs"] = round((time.monotonic() - t0) * 1000)
    res["headlessFrameMs"] = await page.evaluate("() => new Promise((ok) => { const t = performance.now(); requestAnimationFrame(() => requestAnimationFrame(() => ok(Math.round((performance.now() - t) / 2)))); })")
    check(failures, res["toolLatencyMs"] <= 1000, f"tool call in the model within 1 s (took {res['toolLatencyMs']} ms)")
    await wait(page, "() => [...document.querySelectorAll('#ticker li')].some((l) => l.textContent.includes('login.spec.json'))", label="the Write event in the ticker")
    res["ticker"] = await page.evaluate("() => [...document.querySelectorAll('#ticker li')].map((l) => l.textContent)")
    check(failures, any("Write" in x and "login.spec.json" in x for x in res["ticker"]), f"the tool event in the ticker: {res['ticker']}")
    # the log row opens the (escaped) input
    await page.click("#btn-log")
    await page.click("#log-rows tr.ev")
    res["logPayload"] = await page.evaluate("() => (document.querySelector('#log-rows tr.payload pre') || {}).textContent || ''")
    res["logInjected"] = await page.evaluate("() => !!document.querySelector('#log-rows script')")
    check(failures, "<script>alert(1)</script>" in res["logPayload"] and not res["logInjected"], "the input shows as text, not markup")
    await page.keyboard.press("Escape")

    # A subagent comes in through the door and walks to a seat near its parent.
    step(srv, "sub-enter")
    await wait(page, "() => window.__dbg.robots.some((x) => x.def.id === 'a3')")
    first = await robot(page, "a3")
    await page.wait_for_timeout(400)
    walking = await robot(page, "a3")
    await wait(page, "() => { const R = window.__dbg.robots.find((x) => x.def.id === 'a3'); return R && !R.path.length && R.robot.state !== 'carry'; }", label="a3 seated")
    seated = await robot(page, "a3")
    res["subEnter"] = {"first": first, "walking": walking, "seated": seated}
    check(failures, walking and walking["state"] == "carry" and walking["desk"] is False, f"walking in: {walking}")
    check(failures, seated and seated["state"] == "reading" and seated["desk"] is True, f"seated and reading: {seated}")
    check(failures, first and seated and abs(first["z"] - seated["z"]) + abs(first["x"] - seated["x"]) > 1.0, "it walked from the door to its seat")
    a0 = await robot(page, "a0")
    res["subNearParent"] = round(((a0["x"] - seated["x"]) ** 2 + (a0["z"] - seated["z"]) ** 2) ** 0.5, 2)
    await page.screenshot(path=f"{out}/live-sub.png")

    # Done, then out through the door, then gone.
    step(srv, "sub-done")
    await wait(page, "() => { const R = window.__dbg.robots.find((x) => x.def.id === 'a3'); return R && R.robot.state === 'done'; }", label="a3 done")
    step(srv, "sub-gone")
    await wait(page, "() => { const R = window.__dbg.robots.find((x) => x.def.id === 'a3'); return !R || R.robot.state === 'carry'; }")
    await wait(page, "() => !window.__dbg.robots.some((x) => x.def.id === 'a3')", timeout=30000)
    res["subLeft"] = True

    # A session moves to the other project: its robot walks door to door.
    step(srv, "move")
    before = await robot(page, "4f")
    await wait(page, "() => { const R = window.__dbg.robots.find((x) => x.def.id === '4f'); return R && R.robot.state === 'carry'; }")
    await wait(page, "() => { const R = window.__dbg.robots.find((x) => x.def.id === '4f'); return R && !R.path.length && R.def.room === 'p-shop' && R.robot.state !== 'carry'; }", timeout=40000, label="4f seated in shop-app/")
    after = await robot(page, "4f")
    res["move"] = {"before": before, "after": after}
    check(failures, after["room"] == "p-shop" and abs(after["x"] - before["x"]) > 2, f"4f walked to shop-app/: {before} → {after}")

    # A third project: a room more, without reloading.
    step(srv, "third")
    await wait(page, "() => document.querySelectorAll('.tag.room').length === 3 && window.__dbg.robots.length === 4")
    step(srv, "broken")
    res["rooms3"] = await rooms(page)
    await page.wait_for_timeout(1500)
    await page.screenshot(path=f"{out}/live-three-rooms.png")
    await wait(page, "() => !document.getElementById('live-error').hidden")
    res["error"] = await page.evaluate("() => document.getElementById('live-error').textContent")
    check(failures, "agents_cli" in res["error"], f"source failure shown: {res['error']}")
    step(srv, "mended")
    await wait(page, "() => document.getElementById('live-error').hidden")

    # Boards and robots respond to clicks: the room's project board opens its spec board ("まだ無い").
    await page.click('.tag.room[data-set-project="p-cli"]')
    await page.wait_for_timeout(2500)
    res["scoped"] = await page.evaluate("() => document.getElementById('scope-top').textContent")
    await page.click("#btn-specboard")
    await page.wait_for_function("() => { const el = document.getElementById('wb'); return !el.hidden && el.classList.contains('show'); }")
    res["specBoardEmpty"] = await page.evaluate("() => document.getElementById('wb-code').textContent.replace(/\\s+/g, ' ').slice(0, 120)")
    await page.screenshot(path=f"{out}/live-specboard-empty.png")
    await page.keyboard.press("Escape")
    await page.wait_for_function("() => document.getElementById('wb').hidden")
    await page.click("#btn-taskboard")
    await page.wait_for_function("() => { const el = document.getElementById('tb'); return !el.hidden && el.classList.contains('show'); }")
    res["taskBoardEmpty"] = await page.evaluate("() => document.getElementById('kanban').textContent.replace(/\\s+/g, ' ').slice(0, 120)")
    await page.keyboard.press("Escape")
    await page.wait_for_function("() => document.getElementById('tb').hidden")
    res["panelEmpty"] = await page.evaluate("() => ({ specs: document.getElementById('spec-list').textContent, tests: document.getElementById('tests').textContent, tasks: document.getElementById('tasks').textContent })")

    # The server goes away and comes back with a new token: "reconnecting", then back, same page.
    srv.stop()
    await wait(page, "() => document.querySelector('.chip.demo').textContent === '再接続中…'", timeout=15000)
    res["reconnecting"] = True
    srv.restart()   # same port, a new token, the scenario from the start
    step(srv, "start")
    await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", timeout=30000)
    res["sameAfterReconnect"] = await page.evaluate("() => window.__marker")
    await wait(page, "() => window.__dbg.robots.length === 3")
    check(failures, res["sameAfterReconnect"] == "same page", "reconnected without reloading the page")
    st = fake_state(srv)
    res["rejectedAfterRestart"] = st["rejected"]
    await page.close()
    for line in watch.console:
        failures.append(f"live: console: {line}")
    for u in watch.foreign:
        failures.append(f"live: request outside the server: {u}")
    return watch


async def scenario_empty(browser, srv, out, failures, res):
    watch = Watch(origin=srv.url)
    for label, opts in (("light", dict(DESKTOP)), ("dark", dict(DESKTOP, color_scheme="dark")), ("phone", dict(PHONE))):
        page = await new_page(browser, watch, f"empty-{label}", **opts)
        await page.goto(srv.url + "/")
        await ready(page)
        if label == "light":
            step(srv, "start")
        await wait(page, "() => !document.getElementById('live-empty').hidden")
        res[f"empty-{label}"] = await page.evaluate("() => ({ text: document.getElementById('live-empty').textContent.replace(/\\s+/g, ' ').trim(), sw: document.documentElement.scrollWidth })")
        await page.screenshot(path=f"{out}/live-empty-{label}.png")
        if label == "phone":
            check(failures, res[f"empty-{label}"]["sw"] <= 390, f"no horizontal scroll at 390 px: {res[f'empty-{label}']}")
        await page.close()
    for line in watch.console:
        failures.append(f"live/empty: console: {line}")
    for u in watch.foreign:
        failures.append(f"live/empty: request outside the server: {u}")


async def scenario_themes(browser, srv, out, failures, res):
    """Three rooms, light / dark / 390 px: no horizontal scroll, no console error."""
    watch = Watch(origin=srv.url)
    step(srv, "third")
    for label, opts in (("light", dict(DESKTOP)), ("dark", dict(DESKTOP, color_scheme="dark")), ("phone", dict(PHONE)), ("phone-dark", dict(PHONE, color_scheme="dark"))):
        page = await new_page(browser, watch, f"themes-{label}", **opts)
        await page.goto(srv.url + "/")
        await ready(page)
        await wait(page, "() => document.querySelectorAll('.tag.room').length === 3")
        await page.wait_for_timeout(2500)
        res[f"themes-{label}"] = await page.evaluate("() => ({ sw: document.documentElement.scrollWidth, w: window.innerWidth })")
        await page.screenshot(path=f"{out}/live-{label}.png")
        if label.startswith("phone"):
            await page.click('#sessions [data-robot-open="a0"]')
            await page.wait_for_function("() => { const el = document.getElementById('rb'); return !el.hidden && el.classList.contains('show'); }")
            await page.wait_for_timeout(1200)
            await page.screenshot(path=f"{out}/live-{label}-robot.png")
            res[f"themes-{label}-robot"] = await page.evaluate("() => ({ sw: document.documentElement.scrollWidth, title: document.getElementById('rb-title').textContent })")
        sw = res[f"themes-{label}"]["sw"]
        check(failures, sw <= res[f"themes-{label}"]["w"], f"{label}: horizontal scroll (scrollWidth {sw})")
        await page.close()
    for line in watch.console:
        failures.append(f"live/themes: console: {line}")
    for u in watch.foreign:
        failures.append(f"live/themes: request outside the server: {u}")


async def scenario_work(browser, srv, out, failures, res):
    """P4 / P5: tasks, the big spec board and its links, the sheet, the test run, the permission cards."""
    watch = Watch(origin=srv.url)
    step(srv, "start")
    page = await new_page(browser, watch, "work", **DESKTOP)
    await page.goto(srv.url + "/")
    await ready(page)
    await wait(page, "() => window.__dbg.model().specs.length === 10 && window.__dbg.model().tasks.length === 3", label="specs and tasks")
    await page.wait_for_timeout(1500)
    await page.screenshot(path=f"{out}/work-main.png")
    # the big spec board, its tiles, and the line from the writing robot
    res["board"] = await page.evaluate("""() => { const L = window.__dbg.live3d(); const R = L && L.rooms['p-shop'];
      const ln = window.__dbg.links().a3; return { big: !!(R && R.pb.big), tiles: R ? R.pb.tiles.length : 0, easel: !!(R && R.tb), cli: !!(L && L.rooms['p-cli'] && !L.rooms['p-cli'].pb.big) }; }""")
    check(failures, res["board"] == {"big": True, "tiles": 10, "easel": True, "cli": True}, f"work: boards {res['board']}")
    # side panel: the test run (escaped case names) and the tasks
    res["tests"] = await page.evaluate("() => ({ text: document.getElementById('tests').textContent.replace(/\\s+/g, ' '), rows: document.querySelectorAll('#tests .cases li').length, injected: !!document.querySelector('#tests script') })")
    check(failures, res["tests"]["rows"] == 3 and "<script>x</script>" in res["tests"]["text"] and not res["tests"]["injected"], f"work: tests panel {res['tests']}")
    check(failures, "iPhone 16（iOS 26.2）" in res["tests"]["text"], "work: the run's device is named")
    # the task board: columns, the waiting task, the permission strip
    await page.click("#btn-taskboard")
    await page.wait_for_function("() => { const el = document.getElementById('tb'); return !el.hidden && el.classList.contains('show'); }")
    await page.wait_for_timeout(600)
    res["kanban"] = await page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('#kanban .kcol')].map((c) => [c.className.split(' ').find((x) => x.startsWith('k-')),
      [...c.querySelectorAll('.n-subj')].map((n) => n.textContent)]))""")
    check(failures, res["kanban"].get("k-todo") == ["文言を strings.json に登録"] and res["kanban"].get("k-doing") == ["Login 画面の spec を書く"]
          and res["kanban"].get("k-wait") == ["Login 画面を実装"], f"work: kanban columns {res['kanban']}")
    res["strip"] = await page.evaluate("""() => [...document.querySelectorAll('#perm-strip .pcard')].map((c) => ({ text: c.textContent.replace(/\\s+/g, ' '),
      buttons: [...c.querySelectorAll('[data-do]')].map((b) => b.dataset.do), relay: !!c.querySelector('.perm-relay') }))""")
    await page.screenshot(path=f"{out}/work-taskboard.png")
    s1 = next((x for x in res["strip"] if "login.spec.json" in x["text"]), None)
    s2 = next((x for x in res["strip"] if "xcodebuild" in x["text"]), None)
    check(failures, s1 and s1["buttons"] == ["allow", "deny"] and not s1["relay"], f"work: relay prompt has 許可 / 拒否 only: {s1}")
    check(failures, s2 and s2["buttons"] == [] and s2["relay"] and "jui viz relay install" in s2["text"], f"work: no-relay prompt guides instead: {s2}")
    check(failures, s1 and "#2" in s1["text"] and s2 and "タスクなし" in s2["text"], "work: the prompt is on its owner's task only")
    # allow from the view: perm.decide goes out, the card turns "sent"
    await page.click('#perm-strip [data-do="allow"][data-perm="perm-1"]')
    await wait(page, "() => [...document.querySelectorAll('#perm-strip .pcard')].some((c) => c.textContent.includes('送信済み'))", label="perm-1 sent")
    res["decisions"] = fake_state(srv)["decisions"]
    check(failures, res["decisions"] == [{"permId": "perm-1", "behavior": "allow", "always": None, "reason": None}], f"work: perm.decide sent {res['decisions']}")
    await page.screenshot(path=f"{out}/work-sent.png")
    # P6: "from now on" asks first — the rules and where they go, one box each; Esc sends nothing
    await page.click('#perm-strip [data-do="always"][data-perm="perm-3"]')
    await wait(page, "() => !!document.querySelector('.perm-confirm')", label="the from-now-on dialog")
    res["confirm"] = await page.evaluate("() => [...document.querySelectorAll('.pcf-list li')].map((l) => l.textContent.replace(/\\s+/g, ' '))")
    await page.screenshot(path=f"{out}/work-always-confirm.png")
    check(failures, len(res["confirm"]) == 2 and "Bash(npm test:*)" in res["confirm"][0] and "settings.local.json" in res["confirm"][0]
          and "Bash(npm:*)" in res["confirm"][1] and "共有" in res["confirm"][1], f"work: the dialog lists the rules and where: {res['confirm']}")
    await page.keyboard.press("Escape")
    await wait(page, "() => !document.querySelector('.perm-confirm')", label="Esc closes the dialog")
    check(failures, len(fake_state(srv)["decisions"]) == 1, "work: Esc sent nothing")
    await page.click('#perm-strip [data-do="always"][data-perm="perm-3"]')
    await wait(page, "() => !!document.querySelector('.perm-confirm')", label="the dialog again")
    await page.click('.perm-confirm [data-pcf="1"]')        # keep only the narrow rule
    await page.click('.perm-confirm [data-pcf-ok]')
    await wait(page, "() => [...document.querySelectorAll('#perm-strip .pcard')].some((c) => c.textContent.includes('ルール 1 件を追加・フック経由'))", label="perm-3 sent with one rule")
    res["perm4Buttons"] = await page.evaluate("() => [...document.querySelectorAll('#perm-strip [data-perm=\"perm-4\"]')].map((b) => b.dataset.do)")
    check(failures, res["perm4Buttons"] == ["allow", "deny"], f"work: no suggestions, no 今後も許可: {res['perm4Buttons']}")
    # P6: a reason goes with deny, from the detail drawer
    await page.click('#perm-strip [data-open="perm:perm-4"]')
    await wait(page, "() => !!document.getElementById('tbd-reason')", label="the reason box")
    await page.fill('#tbd-reason', 'ビルドの成果物は消さないで <b>x</b>')
    await page.click('#tb-detail [data-do="deny"]')
    await wait(page, "() => [...document.querySelectorAll('#perm-strip .pcard')].some((c) => c.textContent.includes('拒否・理由つき'))", label="perm-4 denied with a reason")
    res["decisionsP6"] = fake_state(srv)["decisions"][1:]
    check(failures, res["decisionsP6"] == [{"permId": "perm-3", "behavior": "allow", "always": [0], "reason": None},
                                           {"permId": "perm-4", "behavior": "deny", "always": None, "reason": "ビルドの成果物は消さないで <b>x</b>"}],
          f"work: P6 decisions {res['decisionsP6']}")
    if await page.evaluate("() => !document.getElementById('tb-detail').hidden"):
        await page.keyboard.press("Escape")
    await page.keyboard.press("Escape")
    await page.wait_for_function("() => document.getElementById('tb').hidden")
    await page.wait_for_timeout(2600)
    # the sheet of the spec being written
    await page.click("#btn-specboard")
    await page.wait_for_function("() => { const el = document.getElementById('wb'); return !el.hidden && el.classList.contains('show'); }")
    login = await page.evaluate("() => window.__dbg.model().specs.findIndex((x) => x.name === 'Login')")
    await page.click(f'.ov-card[data-idx="{login}"]')
    await wait(page, "() => document.querySelectorAll('#wb-code section.sc').length === 8", label="the sheet")
    res["sheet"] = await page.evaluate("""() => ({ title: document.getElementById('wb-title').textContent, writing: [...document.querySelectorAll('#wb-code .sc-writing h3')].map((h) => h.textContent),
      components: document.querySelectorAll('#wb-sec-1 .rows li').length, wf: document.querySelectorAll('#wb-sec-1 .wf').length,
      escaped: document.getElementById('wb-sec-1').textContent.includes('<b>escaped</b>'), injected: !!document.querySelector('#wb-sec-1 .rows b, #wb-sec-1 .wf-id b'),
      related: document.getElementById('wb-sec-7').textContent.replace(/\\s+/g, ' ') })""")
    await page.screenshot(path=f"{out}/work-sheet.png")
    check(failures, res["sheet"]["writing"] == ["状態"] and res["sheet"]["components"] == 5 and res["sheet"]["escaped"] and not res["sheet"]["injected"], f"work: sheet {res['sheet']}")
    await page.keyboard.press("Escape")
    await page.wait_for_function("() => document.getElementById('wb').hidden")
    # progress: task 2 done, task 3 free; the run ends failed
    step(srv, "progress")
    await wait(page, "() => window.__dbg.model().tasks.find((t) => t.id === '3').col === 'todo' && window.__dbg.model().tasks.find((t) => t.id === '2').col === 'done'", label="task 2 done, 3 to do")
    await wait(page, "() => document.getElementById('tests').textContent.includes('2 passed, 1 failed')", label="the run's summary")
    res["afterProgress"] = await page.evaluate("() => ({ tests: document.getElementById('tests').textContent.replace(/\\s+/g, ' ').slice(0, 120), links: !!(window.__dbg.links().a3 && window.__dbg.model().specs[0].by) })")
    step(srv, "terminal")
    await wait(page, "() => document.getElementById('chip-perm').textContent === '許可待ち 1'", label="one prompt left (the sent one)")
    # a project that is not JsonUI: no spec, no test
    await page.click('.tag.room[data-set-project="p-cli"]')
    await page.wait_for_timeout(2500)
    res["cli"] = await page.evaluate("() => ({ specs: document.getElementById('spec-list').textContent, tests: document.getElementById('tests').textContent })")
    check(failures, "spec がない" in res["cli"]["specs"] and "まだ無い" in res["cli"]["tests"], f"work: non-JsonUI room {res['cli']}")
    await page.screenshot(path=f"{out}/work-cli.png")
    await page.close()
    for line in watch.console:
        failures.append(f"live/work: console: {line}")
    for u in watch.foreign:
        failures.append(f"live/work: request outside the server: {u}")


async def run(pw, out, failures, Server):
    out = pathlib.Path(out) / "live"
    out.mkdir(parents=True, exist_ok=True)
    res = {}
    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    try:
        for name, build, fn in (("two-projects", scenarios.two_projects, scenario_two_projects),
                                ("themes", scenarios.two_projects, scenario_themes),
                                ("empty", scenarios.empty, scenario_empty),
                                ("work", scenarios.work, scenario_work)):
            path = scenarios.write(build(), out / f"{name}.jsonl")
            srv = Server(scenario=path)
            t0 = time.monotonic()
            try:
                await fn(browser, srv, str(out), failures, res)
            except Exception as e:  # a wait that timed out: record it and go on to the next scenario
                failures.append(f"live/{name}: {type(e).__name__}: {str(e).splitlines()[0]}")
            finally:
                srv.stop()
            print(f"  live/{name}: {time.monotonic() - t0:.0f}s", flush=True)
    finally:
        await browser.close()
    (out / "live-results.json").write_text(dump(res) + "\n")


async def run_real(pw, out, failures, RealServer):
    """The same view against the real `jui viz serve`, fed a recording (hooks.two_projects) with --replay."""
    out = pathlib.Path(out) / "real"
    out.mkdir(parents=True, exist_ok=True)
    rec = hooks.write(hooks.two_projects(), out / "two-projects.record.jsonl")
    res = {}
    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    t0 = time.monotonic()
    srv = None
    try:
        srv = RealServer(rec, out / "home", speed=1.0)
        watch = Watch(origin=srv.url)
        page = await new_page(browser, watch, "real", **DESKTOP)
        await page.goto(srv.url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", label="connected")
        await wait(page, "() => document.querySelectorAll('.tag.room').length === 2 && window.__dbg.robots.length >= 3", label="two rooms, three robots")
        res["rooms"] = await rooms(page)
        await wait(page, "() => { const s = window.__dbg.robotState().a0; return s && s.state === 'typing'; }", polling=50, label="a0 typing")
        await wait(page, "() => window.__dbg.robots.some((x) => x.def.id === 'a3')", label="the subagent comes in")
        res["sub"] = await robot(page, "a3")
        await wait(page, "() => !window.__dbg.robots.some((x) => x.def.id === 'a3')", timeout=40000, label="the subagent leaves")
        await wait(page, "() => { const R = window.__dbg.robots.find((x) => x.def.id === '4f'); return R && R.def.room === window.__dbg.robots.find((x) => x.def.id === 'a0').def.room && !R.path.length && R.robot.state !== 'carry'; }", timeout=40000, label="4f moved to shop-app/")
        res["moved"] = await robot(page, "4f")
        res["ticker"] = await page.evaluate("() => [...document.querySelectorAll('#ticker li')].map((l) => l.textContent)")
        await page.screenshot(path=f"{out}/real-end.png")
        check(failures, res["rooms"] == ["shop-app/", "jsonui-cli/"], f"real: rooms {res['rooms']}")
        await page.close()
        # The demo from the real server: same files, the server's CSP and static routes.
        page = await new_page(browser, watch, "real-demo", **DESKTOP)
        await page.goto(srv.url + "/?demo=1")
        await ready(page)
        res["demoChips"] = await page.evaluate("() => [...document.querySelectorAll('.chips .chip')].slice(0, 3).map((c) => c.textContent)")
        check(failures, res["demoChips"][0] == "デモ（実データではない）", f"real: ?demo=1 is the demo: {res['demoChips']}")
        await page.close()
        for line in watch.console:
            failures.append(f"real: console: {line}")
        for u in watch.foreign:
            failures.append(f"real: request outside the server: {u}")
    except Exception as e:
        failures.append(f"real: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        if srv:
            srv.stop()
        await browser.close()
    print(f"  real/two-projects: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "real-results.json").write_text(dump(res) + "\n")


async def run_real_decide(pw, out, failures):
    """P6 end to end on the real server: `jui viz serve` in a throwaway HOME, the real forward.py posting a
    session's tool call and a PermissionRequest (async) and waiting with --decide (the synchronous hook); the
    page answers "from now on" with one of two suggestions, then a reasoned deny; the hook prints them."""
    import json as _json
    import os
    import subprocess
    import sys as _sys
    out = pathlib.Path(out) / "real-decide"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    from run import free_port
    port = free_port()
    env = dict(os.environ, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([_sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res = {}

    def hook(payload, decide=False):
        args = [_sys.executable, "-I", "-S", str(forward)] + (["--decide"] if decide else [])
        p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(os.environ, HOME=str(home)))
        p.stdin.write(_json.dumps(payload).encode()); p.stdin.close()
        if decide:
            return p
        p.wait(timeout=10)
        return None

    sid, cwd = "e2e00000-0000-4000-8000-000000000001", "/work/decide-app"
    base = {"session_id": sid, "cwd": cwd, "transcript_path": "/work/home/t.jsonl", "permission_mode": "default"}
    sugg = [{"type": "addRules", "rules": [{"toolName": "Bash", "ruleContent": "npm test:*"}], "behavior": "allow", "destination": "localSettings"},
            {"type": "addRules", "rules": [{"toolName": "Bash", "ruleContent": "npm:*"}], "behavior": "allow", "destination": "projectSettings"}]
    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    t0 = time.monotonic()
    try:
        import urllib.request
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read(); break
            except OSError:
                time.sleep(0.1)
        watch = Watch(origin=url)
        page = await new_page(browser, watch, "real-decide", **DESKTOP)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", label="connected")
        hook(dict(base, hook_event_name="SessionStart", source="startup"))
        await wait(page, "() => window.__dbg.robots.length === 1", label="the session's robot")
        await page.wait_for_timeout(5500)   # one presence report after the page is up
        for n, (cmd, answer) in enumerate((("npm test -- --progress", "always"), ("rm -rf build", "deny"))):
            req = dict(base, hook_event_name="PermissionRequest", tool_name="Bash", tool_input={"command": cmd, "description": "run"},
                       permission_suggestions=sugg)
            hook(req)                       # the async forward reports it first
            waiting = hook(req, decide=True)
            await wait(page, "(cmd) => [...document.querySelectorAll('#tasks .perm-box, #tasks li')].some((li) => li.textContent.includes(cmd) && li.querySelector('[data-do]'))", arg=cmd,
                       timeout=15000, label=f"the card for {cmd}")
            if answer == "always":
                await page.click(f"#tasks li:has-text('{cmd}') [data-do='always']")
                await wait(page, "() => !!document.querySelector('.perm-confirm')", label="the dialog")
                await page.click('.perm-confirm [data-pcf="1"]')
                await page.click('.perm-confirm [data-pcf-ok]')
            else:
                await page.click(f"#tasks li:has-text('{cmd}') .task-open")
                await page.wait_for_function("() => { const el = document.getElementById('tb'); return !el.hidden && el.classList.contains('show'); }")
                await wait(page, "() => !!document.getElementById('tbd-reason')", label="the reason box")
                await page.fill("#tbd-reason", "成果物は残して")
                await page.click("#tb-detail [data-do='deny']")
            outp, err = waiting.communicate(timeout=40)
            res[answer] = _json.loads(outp) if outp else None
            if answer == "deny":
                await page.keyboard.press("Escape"); await page.keyboard.press("Escape")
        await page.screenshot(path=f"{out}/real-decide.png")
        want_always = {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow", "updatedPermissions": [sugg[0]]}}}
        want_deny = {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "deny", "message": "成果物は残して"}}}
        check(failures, res.get("always") == want_always, f"real-decide: from now on reached the hook: {res.get('always')}")
        check(failures, res.get("deny") == want_deny, f"real-decide: the reasoned deny reached the hook: {res.get('deny')}")
        await page.close()
        for line in watch.console:
            failures.append(f"real-decide: console: {line}")
        for u in watch.foreign:
            failures.append(f"real-decide: request outside the server: {u}")
    except Exception as e:
        failures.append(f"real-decide: {type(e).__name__}: {str(e).splitlines()[0]}")
        try:
            diag = await page.evaluate("() => ({ perms: window.__dbg.model().perms.map((p) => [p.id, p.who, p.status, JSON.stringify(p.can)]), tasks: document.getElementById('tasks').textContent.slice(0, 400), robots: window.__dbg.robots.map((R) => R.def.id) })")
            (out / "diag.json").write_text(dump(diag) + "\n")
        except Exception:
            pass
    finally:
        if srv.poll() is None:
            srv.terminate()   # our own child
            try:
                srv.wait(timeout=10)
            except subprocess.TimeoutExpired:
                srv.kill()
        log.close()
        await browser.close()
    print(f"  real/decide: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "real-decide-results.json").write_text(dump(res) + "\n")
