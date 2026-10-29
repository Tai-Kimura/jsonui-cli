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
from common import DESKTOP, LAUNCH_ARGS, PHONE, T, T_head, T_pattern, Watch, dump, new_page, ready

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
    await wait(page, "() => document.querySelector('.chip.demo').dataset.net === 'connected'")
    await wait(page, "() => document.querySelectorAll('.tag.room').length === 2 && window.__dbg.robots.length === 3")
    await page.wait_for_timeout(1500)
    res["rooms"] = await rooms(page)
    res["robots"] = {rid: await robot(page, rid) for rid in ("a0", "b4", "4f")}
    res["chips"] = await page.evaluate("() => [...document.querySelectorAll('.chips .chip')].filter((c) => !c.hidden).map((c) => c.textContent)")
    res["controls"] = await page.evaluate("() => ['btn-play', 'btn-speed'].map((id) => document.getElementById(id).hidden)")
    res["sessions"] = await page.evaluate("() => [...document.querySelectorAll('#sessions .pg-toggle')].map((b) => b.textContent)")
    check(failures, res["rooms"] == ["shop-app/", "jsonui-cli/"], f"two rooms in order, got {res['rooms']}")
    check(failures, res["controls"] == [True, True], "play / speed hidden in the live view")
    check(failures, "127.0.0.1" in " ".join(res["chips"]) and T("page.chip.demo") not in res["chips"], f"chips name the server, not the demo: {res['chips']}")
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

    # Back to the floor (a project picked shows its room alone, 10-18), then: the server goes away and comes back with
    # a new token: "reconnecting", then back, same page.
    await page.click("#room-back")
    srv.stop()
    await wait(page, "() => document.querySelector('.chip.demo').dataset.net === 'reconnecting'", timeout=15000)
    res["reconnecting"] = True
    srv.restart()   # same port, a new token, the scenario from the start
    step(srv, "start")
    await wait(page, "() => document.querySelector('.chip.demo').dataset.net === 'connected'", timeout=30000)
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
    check(failures, s1 and "#2" in s1["text"] and s2 and T_pattern("panel.task.session.none").search(s2["text"]), "work: the prompt is on its owner's task only")
    # allow from the view: perm.decide goes out, the card turns "sent" (the strips open wide first: folded is the default)
    await page.click("#tb-wide[aria-expanded='false']")
    await page.click('#perm-strip [data-do="allow"][data-perm="perm-1"]')
    await wait(page, f"() => [...document.querySelectorAll('#perm-strip .pcard')].some((c) => c.textContent.includes({json.dumps(T_head('panel.perm.sent', 'what'))}))", label="perm-1 sent")
    res["decisions"] = fake_state(srv)["decisions"]
    check(failures, res["decisions"] == [{"permId": "perm-1", "behavior": "allow", "always": None, "reason": None}], f"work: perm.decide sent {res['decisions']}")
    await page.screenshot(path=f"{out}/work-sent.png")
    # P6: "from now on" asks first — the rules and where they go, one box each; Esc sends nothing
    await page.click('#perm-strip [data-do="always"][data-perm="perm-3"]')
    await wait(page, "() => !!document.querySelector('.perm-confirm')", label="the from-now-on dialog")
    res["confirm"] = await page.evaluate("() => [...document.querySelectorAll('.pcf-list li')].map((l) => l.textContent.replace(/\\s+/g, ' '))")
    await page.screenshot(path=f"{out}/work-always-confirm.png")
    check(failures, len(res["confirm"]) == 2 and "Bash(npm test:*)" in res["confirm"][0] and "settings.local.json" in res["confirm"][0]
          and "Bash(npm:*)" in res["confirm"][1] and T("panel.dest.project") in res["confirm"][1], f"work: the dialog lists the rules and where: {res['confirm']}")
    await page.keyboard.press("Escape")
    await wait(page, "() => !document.querySelector('.perm-confirm')", label="Esc closes the dialog")
    check(failures, len(fake_state(srv)["decisions"]) == 1, "work: Esc sent nothing")
    await page.click('#perm-strip [data-do="always"][data-perm="perm-3"]')
    await wait(page, "() => !!document.querySelector('.perm-confirm')", label="the dialog again")
    await page.click('.perm-confirm [data-pcf="1"]')        # keep only the narrow rule
    await page.click('.perm-confirm [data-pcf-ok]')
    await wait(page, f"() => [...document.querySelectorAll('#perm-strip .pcard')].some((c) => c.textContent.includes({json.dumps(T('panel.sent.rules', n=1) + T('panel.sent.via', via=T('panel.sent.hook')))}))", label="perm-3 sent with one rule")
    res["perm4Buttons"] = await page.evaluate("() => [...document.querySelectorAll('#perm-strip [data-perm=\"perm-4\"]')].map((b) => b.dataset.do)")
    check(failures, res["perm4Buttons"] == ["allow", "deny"], f"work: no suggestions, no 今後も許可: {res['perm4Buttons']}")
    # P6: a reason goes with deny, from the detail drawer
    await page.click('#perm-strip [data-open="perm:perm-4"]')
    await wait(page, "() => !!document.getElementById('tbd-reason')", label="the reason box")
    await page.fill('#tbd-reason', 'ビルドの成果物は消さないで <b>x</b>')
    await page.click('#tb-detail [data-do="deny"]')
    await wait(page, f"() => [...document.querySelectorAll('#perm-strip .pcard')].some((c) => c.textContent.includes({json.dumps(T('panel.sent.deny') + T('panel.sent.reason'))}))", label="perm-4 denied with a reason")
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
    check(failures, res["sheet"]["writing"] == [T("core.sec.state")] and res["sheet"]["components"] == 5 and res["sheet"]["escaped"] and not res["sheet"]["injected"], f"work: sheet {res['sheet']}")
    await page.keyboard.press("Escape")
    await page.wait_for_function("() => document.getElementById('wb').hidden")
    # progress: task 2 done, task 3 free; the run ends failed
    step(srv, "progress")
    await wait(page, "() => window.__dbg.model().tasks.find((t) => t.id === '3').col === 'todo' && window.__dbg.model().tasks.find((t) => t.id === '2').col === 'done'", label="task 2 done, 3 to do")
    await wait(page, "() => document.getElementById('tests').textContent.includes('2 passed, 1 failed')", label="the run's summary")
    res["afterProgress"] = await page.evaluate("() => ({ tests: document.getElementById('tests').textContent.replace(/\\s+/g, ' ').slice(0, 120), links: !!(window.__dbg.links().a3 && window.__dbg.model().specs[0].by) })")
    step(srv, "terminal")
    await wait(page, f"() => document.getElementById('chip-perm').textContent === {json.dumps(T('panel.count.waiting', n=1))}", label="one prompt left (the sent one)")
    # a project that is not JsonUI: no spec, no test
    await page.click('.tag.room[data-set-project="p-cli"]')
    await page.wait_for_timeout(2500)
    res["cli"] = await page.evaluate("() => ({ specs: document.getElementById('spec-list').textContent, tests: document.getElementById('tests').textContent })")
    check(failures, T_pattern("panel.spec.none.scope").search(res["cli"]["specs"]) and (T("tests.none") in res["cli"]["tests"] or T("tests.status.none") in res["cli"]["tests"]), f"work: non-JsonUI room {res['cli']}")
    await page.screenshot(path=f"{out}/work-cli.png")
    await page.close()
    for line in watch.console:
        failures.append(f"live/work: console: {line}")
    for u in watch.foreign:
        failures.append(f"live/work: request outside the server: {u}")


OVERLAP_JS = """() => { const vis = (el) => { if (!el || el.closest('[hidden]')) return false; const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const mine = ['floor-nav', 'tower-legend', 'roster'].map((id) => document.getElementById(id)).filter(vis);   // roster: a room's robot list (53-roster.js)
  const others = [...document.querySelectorAll('button, input, select, textarea, a[href], [role="option"], [role="dialog"], [tabindex]:not([tabindex="-1"])')]
    .filter((el) => vis(el) && !mine.some((m) => m.contains(el)) && !el.closest('.tags'));
  const hits = [];
  for (const m of mine) { const a = m.getBoundingClientRect();
    for (const o of others) { const b = o.getBoundingClientRect();
      if (a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom) hits.push(`${m.id} x ${o.id || o.className || o.tagName}`); } }
  return { shown: mine.map((m) => m.id), hits }; }"""
FRAMES_JS = """(ms) => new Promise((done) => { const d = []; let last = performance.now(); const t0 = last;
  const tick = (now) => { d.push(now - last); last = now; if (now - t0 < ms) requestAnimationFrame(tick); else { d.sort((a, b) => a - b);
    done({ frames: d.length, median: +d[Math.floor(d.length / 2)].toFixed(1), p95: +d[Math.floor(d.length * 0.95)].toFixed(1) }); } };
  requestAnimationFrame(tick); })"""


async def scenario_floors(browser, srv, out, failures, res):
    """The building: six rooms to a floor, the active rooms on 1F, floor buttons, the building view, the menu."""
    watch = Watch(origin=srv.url)
    step(srv, "start")
    page = await new_page(browser, watch, "floors", **DESKTOP)
    await page.goto(srv.url + "/")
    await ready(page)
    await wait(page, "() => { const f = window.__dbg.floors(); return f && f.floors.length === 3 && Object.keys(window.__dbg.live3d().rooms).length === 6; }", label="three floors, six rooms drawn")
    f = await page.evaluate("() => window.__dbg.floors()")
    res["floors"] = f["floors"]
    check(failures, {"p13", "p17"} <= set(f["floors"][0]) and len(f["floors"][0]) == 6, f"floors: the waiting and the working room are on 1F: {f['floors']}")
    await wait(page, "() => !document.getElementById('floor-nav').hidden", label="the floor buttons shown")   # the chrome refreshes every 250 ms
    nav = await page.evaluate("() => ({ hidden: document.getElementById('floor-nav').hidden, label: document.getElementById('floor-label').textContent, down: document.getElementById('floor-down').disabled })")
    check(failures, nav == {"hidden": False, "label": "1F / 3F", "down": True}, f"floors: the floor buttons {nav}")
    # 1F is full; then the room on 3F starts working: it comes to 1F, the two active rooms keep their slots
    first = f["floors"][0]
    step(srv, "later")
    await wait(page, "() => window.__dbg.floors().floors[0].includes('p16')", label="the room that started later is on 1F")
    after = (await page.evaluate("() => window.__dbg.floors()"))["floors"][0]
    res["later"] = after
    check(failures, after.index("p13") == first.index("p13") and after.index("p17") == first.index("p17") and len(after) == 6,
          f"floors: the rooms that stayed kept their slots {first} -> {after}")
    await page.wait_for_timeout(800)
    res["floorView"] = {"render": await page.evaluate("() => window.__dbg.renderInfo()"), "frames": await page.evaluate(FRAMES_JS, 2000)}
    await page.screenshot(path=f"{out}/floors-1f.png")
    # up to 2F: its rooms are drawn; 1F has the waiting room, so the down button carries the mark
    await page.click("#floor-up")
    await wait(page, "() => { const f = window.__dbg.floors(); const ids = Object.keys(window.__dbg.live3d().rooms).sort(); return f.floor === 1 && JSON.stringify(ids) === JSON.stringify([...f.floors[1]].sort()); }", label="2F drawn")
    await wait(page, "() => document.getElementById('floor-label').textContent === '2F / 3F'", label="the 2F label")
    mark = await page.evaluate("() => ({ down: document.getElementById('floor-down').hasAttribute('data-alert'), up: document.getElementById('floor-up').hasAttribute('data-alert'), label: document.getElementById('floor-label').textContent })")
    check(failures, mark == {"down": True, "up": False, "label": "2F / 3F"}, f"floors: 2F shows the mark toward 1F {mark}")
    # the menu: a room on 3F — the floor changes and the camera goes there (it threw a ReferenceError before)
    target = (await page.evaluate("() => window.__dbg.floors()"))["floors"][2][-1]   # a room on 3F now
    await page.click("#scope-top")
    await page.click(f'[data-pick-project="{target}"]')
    await wait(page, f"() => {{ const f = window.__dbg.floors(); return f.floor === 2 && !!window.__dbg.live3d().rooms['{target}']; }}", label="the picked room's floor")
    await page.wait_for_timeout(1500)
    await page.screenshot(path=f"{out}/floors-picked.png")
    # the picked room fills most of the view (it showed the whole floor before)
    res["picked"] = await page.evaluate(f"""() => {{ const T = window.__dbg.THREE, cam = window.__dbg.camera, c = document.getElementById('scene-canvas').getBoundingClientRect();
      const r = window.__dbg.model && window.__dbg.room('{target}'); const xs = [[r.x0, r.z0], [r.x1, r.z0], [r.x0, r.z1], [r.x1, r.z1]].map(([x, z]) => new T.Vector3(x, 0, z).project(cam).x);
      return +((Math.max(...xs) - Math.min(...xs)) / 2).toFixed(2); }}""")
    check(failures, res["picked"] >= 0.6, f"floors: the picked room fills most of the width: {res['picked']}")
    # the building: from the button, then a floor pressed goes down to it
    await page.click("#floor-building")
    await wait(page, "() => window.__dbg.floors().tower", label="the building")
    await page.wait_for_timeout(1200)
    res["building"] = {"render": await page.evaluate("() => window.__dbg.renderInfo()"), "frames": await page.evaluate(FRAMES_JS, 2000),
                       "tags": await page.evaluate("() => document.getElementById('tags').hidden")}
    await page.screenshot(path=f"{out}/floors-building.png")
    check(failures, res["building"]["tags"] is True, "floors: the building hides the robots' and rooms' tags")
    pt = await page.evaluate("""() => { const T = window.__dbg.THREE, cam = window.__dbg.camera, c = document.getElementById('scene-canvas').getBoundingClientRect();
      const v = new T.Vector3(0, 1.5, 4.5).project(cam); return [c.left + (v.x + 1) / 2 * c.width, c.top + (1 - v.y) / 2 * c.height]; }""")
    await page.mouse.click(pt[0], pt[1])
    await wait(page, "() => { const f = window.__dbg.floors(); return !f.tower && f.floor === 0; }", label="down to 1F from the building")
    # the wheel past the farthest distance shows the building again: zoom out step by step, as a person would
    await page.wait_for_timeout(1500)                        # the flight down has landed
    box = await page.evaluate("() => { const r = document.getElementById('scene-canvas').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }")
    await page.mouse.move(box[0], box[1])
    for _ in range(60):
        if await page.evaluate("() => window.__dbg.floors().tower"):
            break
        await page.mouse.wheel(0, 300)
        await page.wait_for_timeout(80)
    await wait(page, "() => window.__dbg.floors().tower", label="the wheel out shows the building")
    # the floor buttons and the legend never sit on another control (10-18: they covered the spec board's header):
    # panel open / closed, floor / building, 1280 / 1024 / 768 px; hidden while a board or the log is open
    res["overlap"] = {}
    for width in (1280, 1024, 768):
        await page.set_viewport_size({"width": width, "height": 800})
        for side in ("open", "closed"):
            if await page.evaluate("() => document.body.classList.contains('side-closed') || document.querySelector('.main').classList.contains('side-closed')") != (side == "closed"):
                await page.click("#btn-side")
            for view in ("floor", "building"):
                await page.evaluate("(on) => window.__dbg.tower(on)", view == "building")
                await page.wait_for_timeout(500)
                o = await page.evaluate(OVERLAP_JS)
                res["overlap"][f"{width}-{side}-{view}"] = o
                check(failures, o["hits"] == [] and "floor-nav" in o["shown"] and (view == "floor" or "tower-legend" in o["shown"]),
                      f"floors: the floor buttons overlap nothing at {width}px, panel {side}, {view} view: {o}")
    await page.set_viewport_size(DESKTOP["viewport"])
    if await page.evaluate("() => document.querySelector('.main').classList.contains('side-closed')"):
        await page.click("#btn-side")                        # the boards open from the side panel
    await page.evaluate("() => window.__dbg.tower(false)")
    await page.wait_for_timeout(500)
    opened = {"spec board": "!document.getElementById('wb').hidden", "task board": "document.getElementById('tb').classList.contains('show')",
              "log": "!document.getElementById('log-overlay').hidden"}
    for opener, closer, name in (("#btn-specboard", "#wb-close", "spec board"), ("#btn-taskboard", "#tb-close", "task board"), ("#btn-log", None, "log")):
        await page.click(opener)
        await wait(page, f"() => {opened[name]}", label=f"the {name} open")
        await page.wait_for_timeout(600)                     # the chrome refreshes every 250 ms
        o = await page.evaluate(OVERLAP_JS)
        res["overlap"][name] = o
        check(failures, o["shown"] == [], f"floors: the floor buttons are hidden while the {name} is open: {o}")
        if closer:
            await page.click(closer)
        else:
            await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
    await page.close()
    for line in watch.console:
        failures.append(f"live/floors: console: {line}")
    for u in watch.foreign:
        failures.append(f"live/floors: request outside the server: {u}")


async def scenario_building(browser, srv, out, failures, res):
    """The building's look: light and dark, everyone idle / working and waiting mixed / a floor with empty bays;
    the legend; the robots in the windows match the rooms' states; a 10-second recording."""
    watch = Watch(origin=srv.url)
    step(srv, "idle")
    page = await new_page(browser, watch, "building", **DESKTOP)
    await page.goto(srv.url + "/")
    await ready(page)
    await wait(page, "() => { const f = window.__dbg.floors(); return f && f.floors.length === 2 && f.floors[1].length === 4; }", label="two floors, 2F with four rooms")
    shots = {}

    async def theme(name):
        await page.evaluate("(t) => { document.documentElement.dataset.theme = t; }", name)
        await page.wait_for_timeout(900)

    async def shot(name):
        path = f"{out}/building-{name}.png"
        await page.screenshot(path=path)
        shots[name] = path

    await page.evaluate("() => window.__dbg.tower(true)")
    await wait(page, "() => window.__dbg.floors().tower", label="the building")
    await page.wait_for_timeout(1500)
    legend = await page.evaluate("() => !document.getElementById('tower-legend').hidden")
    check(failures, legend, "building: the legend is shown next to the building")
    idle = await page.evaluate("() => window.__dbg.towerActors()")
    res["actorsIdle"] = idle
    check(failures, idle["shadow"] == 20 and sum(v for k, v in idle.items() if k != "shadow") == 0,
          f"building: everyone idle — only shadows in dark rooms (2 per room) {idle}")
    for t in ("light", "dark"):
        await theme(t)
        await shot(f"{t}-idle")
    step(srv, "mixed")
    await wait(page, "() => { const a = window.__dbg.towerActors(); return a && a.raise > 0 && a.type > 0; }", label="the mixed state in the windows")
    await page.wait_for_timeout(1200)
    mixed = await page.evaluate("() => window.__dbg.towerActors()")
    res["actorsMixed"] = mixed
    check(failures, mixed["raise"] == 1 and mixed["point"] == 3 and mixed["walkA"] + mixed["walkB"] == 3 and mixed["think"] == 1 and mixed["shadow"] == 10,
          f"building: three working rooms, one thinking, one waiting (all lit), five idle {mixed}")
    texts = await page.evaluate("""() => ({ legend: document.getElementById('tower-legend').textContent,
      card: [...document.querySelectorAll('#sessions .session')].map((c) => c.textContent.replace(/\\s+/g, ' ')).find((t) => t.includes('b9')) || '' })""")
    check(failures, T("status.thinking") in texts["legend"], "building: the legend has 考え中")
    check(failures, T("status.thinking") in texts["card"] and T("status.busy") not in texts["card"], f"building: the thinking session's card says 考え中, not 作業中: {texts['card']}")
    wraps = await page.evaluate("() => ['tea-finder-agent', 'aurora_base_android2', 'nimbus_android', 'a-very-long-project-name-that-goes-on-and-on-and-on'].map((n) => window.__dbg.towerLines(n))")
    res["wraps"] = wraps
    check(failures, wraps[0] == [30, "tea-finder-", "agent"] and wraps[1][1:] == ["aurora_base_", "android2"] and wraps[1][0] < 30
          and wraps[2] == [30, "nimbus_", "android"] and wraps[3][0] == 22 and len(wraps[3]) == 3 and wraps[3][2].endswith("…"),
          f"building: names break after - and _, a smaller size before '…', '…' only past two lines {wraps}")
    # the sky follows the local hour: dawn, day, dusk, night
    skies = {}
    for hour in (6, 12, 17.5, 23):
        was = await page.evaluate("() => window.__dbg.sky()")
        await page.evaluate("(h) => { const d = new Date(); d.setHours(Math.floor(h), (h % 1) * 60, 0, 0); window.__dbg.setClock(d.getTime()); }", hour)
        # the sky is drawn on the page's next frame (skySync): waited for to change, not 250 ms (a busy machine read the
        # hour before's); one that stays (6 when the machine's own hour is dawn) is read after the wait and judged below
        try:
            await page.wait_for_function("(was) => { const s = window.__dbg.sky(); return s.phase !== was.phase || s.background !== was.background; }",
                                         arg=was, timeout=5000, polling="raf")
        except Exception:   # noqa: BLE001 - the arm below says what was read
            pass
        skies[hour] = await page.evaluate("() => window.__dbg.sky()")
    res["skies"] = skies
    check(failures, [skies[h]["phase"] for h in (6, 12, 17.5, 23)] == ["dawn", "day", "dusk", "night"] and len({v["background"] for v in skies.values()}) == 4,
          f"building: four skies for four hours {skies}")
    for t in ("light", "dark"):
        await theme(t)
        await shot(f"{t}-night")
    await page.evaluate("() => window.__dbg.setClock(null)")
    think = await page.evaluate("""() => { const R = window.__dbg.robots.find((x) => x.def.id === 'b9'); const pr = R && R.robot.props.thinking;
      return { state: R && R.robot.state, bubble: !!(pr && pr.group.visible), badge: window.__dbg.robotState().b9.state }; }""")
    res["thinking"] = think
    check(failures, think == {"state": "thinking", "bubble": True, "badge": "thinking"}, f"building: the thinking robot has its own state and bubble {think}")
    dist = await page.evaluate("() => window.__dbg.towerDistance()")
    check(failures, abs(dist["at"] - dist["want"]) < 2, f"building: a regrouped floor did not move the camera off the building {dist}")
    for t in ("dark", "light"):
        await theme(t)
        await shot(f"{t}-mixed")
    await page.evaluate("() => window.__dbg.towerLook(1)")
    await page.wait_for_timeout(900)
    for t in ("light", "dark"):
        await theme(t)
        await shot(f"{t}-empty-bays")
    res["buildingShots"] = shots
    # 8 hours: b0, b1 and b6 have a start 9 h ago, b2 1 h ago, the others none (never tired, not guessed)
    await page.evaluate("() => window.__dbg.tower(false)")
    await page.wait_for_timeout(5000)
    g = {x["id"]: x for x in await page.evaluate("() => window.__dbg.gestures()")}
    res["tired"] = {k: (v["tired"], v["drinks"]) for k, v in g.items()}
    check(failures, all(g[k]["tired"] for k in ("b1",) if k in g) and not any(g[k]["tired"] for k in ("b2", "b3", "b4", "b8", "b9") if k in g),
          f"building: tired from 8 hours of its own start, never without one {res['tired']}")
    await page.wait_for_timeout(5000)                        # still tired: no second drink
    g2 = {x["id"]: x for x in await page.evaluate("() => window.__dbg.gestures()")}
    check(failures, all(g2[k]["drinks"] == g[k]["drinks"] for k in g if k in g2)
          and all(g[k]["drinks"] >= 1 for k in g if g[k]["tired"] and g[k]["state"] in ("idle", "typing", "reading", "command"))
          and all(g[k]["drinks"] == 0 for k in g if not g[k]["tired"]),
          f"building: a drink when it got tired, none again while it stays tired, none if never tired {res['tired']}")
    hv = {k: (v["heavy"], v["sweat"], v["state"]) for k, v in g2.items()}
    res["heavy"] = hv
    check(failures, hv.get("b1", (0, 0, 0))[:2] == (True, True) and hv.get("b6", (0, 0, 0))[:2] == (True, False)
          and not any(v[1] for k, v in hv.items() if k not in ("b1",)),
          f"building: a heavy session's working robot types fast and sweats; a heavy one waiting does not {hv}")
    await page.evaluate("() => window.__dbg.openRobot('b1')")
    await wait(page, "() => { const el = document.querySelector('[data-rb-cond]'); return !!el && !el.hidden; }", label="the robot card's condition line")
    card = await page.evaluate("() => { const el = document.querySelector('[data-rb-cond]'); return el && !el.hidden ? el.textContent : ''; }")
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(500)
    res["card"] = card
    check(failures, T("panel.rb.tired", n=9) in card and T("panel.heavy", why=T("panel.heavy.tokens", n="3,200")) in card,
          f"building: the robot card says it is tired and why the work is heavy: {card!r}")
    empty = [k for k, v in g2.items() if not v["act"] and v["actShown"]]
    check(failures, empty == [], f"building: a robot with nothing to say shows no empty bubble {empty}")
    # coffee and meals: a fixed seed, never on a robot waiting / thinking / done, at most half of them at once
    # first with no cap at all, so every robot gets its turn — a waiting or thinking one included (with a cap the
    # first robots filled it and the waiting one was never asked: a mutation letting it eat passed)
    await page.evaluate("() => window.__dbg.snack({ seed: 7, p: 1, share: 1 })")
    wrong = []
    for _ in range(8):
        await page.wait_for_timeout(300)
        rows = await page.evaluate("() => window.__dbg.gestures()")
        wrong += [x for x in rows if x["gesture"] and x["state"] in ("waiting", "thinking", "done")]
    await page.evaluate("() => window.__dbg.snack({ seed: 7, p: 1, share: 0.5 })")
    await page.wait_for_timeout(5500)                      # the uncapped ones finish
    worst, seen = 0, set()
    for _ in range(16):
        await page.wait_for_timeout(300)
        rows = await page.evaluate("() => window.__dbg.gestures()")
        snacks = [x for x in rows if x["gesture"] in ("coffee", "meal")]
        worst = max(worst, len(snacks)); seen |= {x["gesture"] for x in snacks}
    cap = max(1, len(rows) // 2)
    res["snacks"] = {"worst": worst, "cap": cap, "seen": sorted(seen), "wrong": wrong}
    check(failures, wrong == [] and 0 < worst <= cap and seen, f"building: coffee and meals within the cap, never while waiting or thinking {res['snacks']}")
    await page.evaluate("() => window.__dbg.snack({ seed: 20261018, p: 1 / 90, share: 0.15 })")
    await page.close()
    # ten seconds of the building, everyone working and one waiting (a webm the requester can watch)
    ctx = await browser.new_context(record_video_dir=out, record_video_size={"width": 1280, "height": 800}, viewport={"width": 1280, "height": 800})
    vp = await ctx.new_page()
    await vp.goto(srv.url + "/")
    await ready(vp)
    await wait(vp, "() => { const f = window.__dbg.floors(); return f && f.floors.length === 2; }", label="video: floors")
    await vp.evaluate("() => { const d = new Date(); d.setHours(21, 0, 0, 0); window.__dbg.setClock(d.getTime()); window.__dbg.tower(true); }")
    await vp.wait_for_timeout(4500)
    await vp.evaluate("() => { window.__dbg.tower(false); window.__dbg.snack({ seed: 3, p: 0.35, share: 0.5 }); }")
    await vp.click("#scope-top")
    await vp.click('[data-pick-project="b01"]')        # a tired robot at work
    await vp.wait_for_timeout(3000)
    # close up: the tired robot working hard (fast typing, sweat), then a tired idle one; snacks come often here
    await vp.evaluate("() => { window.__dbg.snack({ seed: 11, p: 1, share: 0.5 }); window.__dbg.openRobot('b1'); }")
    await vp.wait_for_timeout(4500)
    await vp.keyboard.press("Escape")
    await vp.evaluate("() => window.__dbg.openRobot('b0')")
    await vp.wait_for_timeout(4500)
    video = vp.video
    await ctx.close()
    res["buildingVideo"] = str(await video.path()) if video else None
    for line in watch.console:
        failures.append(f"live/building: console: {line}")
    for u in watch.foreign:
        failures.append(f"live/building: request outside the server: {u}")


async def scenario_demo_show(browser, srv, out, failures, res):
    """The demo plays every effect once a loop (requester, 10-18), at the beats its script declares (DEMO_BEATS):
    the building by day (out, 2F, back, down) and by night, thinking, heavy work, the 8-hour tiredness with its drink,
    coffee and meals, a fist pump on a granted permission, the sky by the demo clock. A touch on the 3D view holds the
    camera beats back. Ends with a recording of one whole loop."""
    watch = Watch(origin=srv.url)
    page = await new_page(browser, watch, "demo-show", **DESKTOP)
    await page.goto(srv.url + "/?demo=1")
    await ready(page)
    B = await page.evaluate("() => window.__dbg.beats()")
    show = {}

    # The demo's clock advances 0.05 s a frame at most, so on a slow renderer (7 fps here) it runs slow: wait on the
    # script's own time, not on seconds. at(t, lead) jumps to t - lead and plays until t + 0.4.
    async def at(t, lead=1.0, after=0.4, settle=700):
        await page.evaluate("(t) => window.__dbg.setSim(t)", t - lead)
        # between the target and two seconds past it: right after a jump back the model still holds the old time
        await page.wait_for_function("(t) => { const m = window.__dbg.model().t; return m >= t && m < t + 2; }", arg=t + after, timeout=60000)
        await page.wait_for_timeout(settle)

    async def robot(id_):
        return await page.evaluate("(id) => window.__dbg.gestures().find((x) => x.id === id)", id_)

    await at(B["towerOut"])
    show["out"] = await page.evaluate("() => window.__dbg.floors()")
    await page.screenshot(path=f"{out}/demo-building-day.png")
    await at(B["look2F"], 0.6)
    show["look2F"] = await page.evaluate("() => ({ look: window.__dbg.floors().look, label: document.getElementById('floor-label').textContent })")
    await at(B["look1F"], 0.6)
    show["look1F"] = (await page.evaluate("() => window.__dbg.floors()"))["look"]
    await at(B["towerIn"], 0.6)
    show["in"] = (await page.evaluate("() => window.__dbg.floors()"))["tower"]
    check(failures, show["out"]["tower"] and show["look2F"] == {"look": 1, "label": "2F / 2F"} and show["look1F"] == 0 and show["in"] is False,
          f"demo: the building by day — out, up to 2F, back, down {show}")
    await at(B["thinking"][0] + 4)
    show["thinking"] = await page.evaluate("(id) => { const R = window.__dbg.robots.find((x) => x.def.id === id); return { state: R.robot.state, bubble: !!(R.robot.props.thinking && R.robot.props.thinking.group.visible) }; }", B["thinking"][2])
    await at(B["heavy"][0] + 4)
    show["heavy"] = await robot(B["heavy"][2])
    await at(B["snacks"][1][0], 0.5)
    show["snack"] = (await robot(B["snacks"][1][1]))["gesture"]
    await at(44, 0.5, 0.02, 0)                              # 4f's permission ends at 44; the pump lasts 1.6 s of real time
    show["cheer"] = (await robot("4f"))["gesture"]
    tired_at = (17 - 5) / 18 * 84                           # 17:00 on the demo clock (b4 began at 9:00)
    await at(tired_at - 1.5, 0.5)
    before = await robot(B["tired"]["session"])
    await at(tired_at + 0.3, 0.5)
    after = await robot(B["tired"]["session"])
    show["tired"] = [before["tired"], after["tired"], after["drinks"]]
    show["card"] = await page.evaluate("(id) => window.__dbg.condition(id)", B["tired"]["session"])
    check(failures, show["thinking"] == {"state": "thinking", "bubble": True} and show["heavy"]["sweat"] and show["snack"] == "coffee"
          and show["cheer"] == "cheer" and show["tired"] == [False, True, 1] and show["card"]["tired"],
          f"demo: thinking, sweat, coffee, a fist pump, tired at 17:00 with one drink {show}")
    skies = {}
    for t in (3, 20, 60, 72):
        await at(t, 0.3)
        skies[t] = (await page.evaluate("() => window.__dbg.sky()"))["phase"]
    show["skies"] = skies
    show["clock"] = await page.evaluate("() => document.getElementById('demo-clock').textContent")
    check(failures, list(skies.values()) == ["dawn", "day", "dusk", "night"] and T_head("demo.clock", "time") in show["clock"],
          f"demo: the sky by the demo clock, which says it is one {show['skies']} {show['clock']}")
    await at(B["nightOut"])
    show["night"] = (await page.evaluate("() => window.__dbg.floors()"))["tower"]
    await page.screenshot(path=f"{out}/demo-building-night.png")
    await at(B["nightIn"], 0.5)
    # a touch on the 3D view holds the camera back
    box = await page.evaluate("() => { const r = document.getElementById('scene-canvas').getBoundingClientRect(); return [r.left + r.width / 3, r.top + r.height / 2]; }")
    # a small wheel toward the office: a touch that opens nothing (a click hit a board and held the camera for that)
    await page.mouse.move(box[0], box[1])
    await page.mouse.wheel(0, -60)
    await at(B["towerOut"])
    show["touchOpened"] = await page.evaluate("() => !document.getElementById('wb').hidden || !document.getElementById('rb').hidden")
    show["heldBack"] = not (await page.evaluate("() => window.__dbg.floors()"))["tower"]
    check(failures, show["night"] and show["heldBack"] and not show["touchOpened"], f"demo: the building at night; a touch holds the camera back {show}")
    res["demoShow"] = show
    await page.close()
    # one whole loop, from where the demo opens
    ctx = await browser.new_context(record_video_dir=out, record_video_size={"width": 1280, "height": 800}, viewport={"width": 1280, "height": 800})
    vp = await ctx.new_page()
    await vp.goto(srv.url + "/?demo=1")
    await ready(vp)
    # at the demo's ×3 the 0.05 s-a-frame clock runs about real time on this renderer (7 fps): one loop is ~80 s
    await vp.click("#btn-speed")
    await vp.evaluate("() => window.__dbg.setSim(0)")
    # the loop's number, not its last 0.5 s: t >= 83.5 holds for about 3 frames a loop, and the 500 ms poll missed it
    # for whole loops (2.3.8 measured: the loop 0 and loop 1 windows came, the wait ended at loop 2; 2.3.9 gate 2 timed
    # out at 400 s; ticket 2026-10-20-jui-viz-e2e-demo-show-video-wait-misses-the-loop-end)
    await vp.wait_for_function("() => window.__dbg.model().loop >= 1", timeout=400_000, polling=500)
    video = vp.video
    await ctx.close()
    res["demoVideo"] = str(await video.path()) if video else None
    for line in watch.console:
        failures.append(f"demo-show: console: {line}")


async def run(pw, out, failures, Server):
    out = pathlib.Path(out) / "live"
    out.mkdir(parents=True, exist_ok=True)
    res = {}
    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    try:
        for name, build, fn in (("two-projects", scenarios.two_projects, scenario_two_projects),
                                ("themes", scenarios.two_projects, scenario_themes),
                                ("empty", scenarios.empty, scenario_empty),
                                ("work", scenarios.work, scenario_work),
                                ("floors", scenarios.floors, scenario_floors),
                                ("building", scenarios.building, scenario_building),
                                ("demo-show", scenarios.empty, scenario_demo_show)):
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
        await wait(page, "() => document.querySelector('.chip.demo').dataset.net === 'connected'", label="connected")
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
        # The server goes away and comes back on the same port with a new token (the independent check's P3 review): the page shows
        # 再接続中…, fetches the new token itself and is connected again — the same page, never reloaded.
        await page.evaluate("() => { window.__notReloaded = true; }")
        before = srv.token()
        srv.restart()
        res["restart"] = {"newToken": bool(before) and srv.token() != before}
        await wait(page, "() => document.querySelector('.chip.demo').dataset.net === 'reconnecting'", polling=50, label="reconnecting after the restart")
        await wait(page, "() => document.querySelector('.chip.demo').dataset.net === 'connected'", timeout=40000, label="connected again")
        await wait(page, "() => document.querySelectorAll('.tag.room').length === 2", label="the rooms after the restart")
        res["restart"]["sameTab"] = await page.evaluate("() => window.__notReloaded === true")
        res["restart"]["metaKeptOld"] = await page.evaluate("(t) => document.querySelector('meta[name=\"jui-viz-token\"]').content === t", before)
        check(failures, res["restart"] == {"newToken": True, "sameTab": True, "metaKeptOld": True}, f"real: reconnect after a restart {res['restart']}")
        await page.close()
        # The demo from the real server: same files, the server's CSP and static routes.
        page = await new_page(browser, watch, "real-demo", **DESKTOP)
        await page.goto(srv.url + "/?demo=1")
        await ready(page)
        res["demoChips"] = await page.evaluate("() => [...document.querySelectorAll('.chips .chip')].slice(0, 3).map((c) => c.textContent)")
        check(failures, res["demoChips"][0] == T("page.chip.demo"), f"real: ?demo=1 is the demo: {res['demoChips']}")
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
            p.stdin = None   # closed already: 3.11's communicate() flushes a closed stdin and raises ValueError
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
        await wait(page, "() => document.querySelector('.chip.demo').dataset.net === 'connected'", label="connected")
        hook(dict(base, hook_event_name="SessionStart", source="startup"))
        await wait(page, "() => window.__dbg.robots.length === 1", label="the session's robot")
        await page.wait_for_timeout(5500)   # one presence report after the page is up
        for n, (cmd, answer) in enumerate((("npm test -- --progress", "always"), ("rm -rf build", "deny"))):
            req = dict(base, hook_event_name="PermissionRequest", tool_name="Bash", tool_input={"command": cmd, "description": "run"},
                       permission_suggestions=sugg)
            hook(req)                       # the async forward reports it first
            # The card is drawn before --decide arrives (nothing allowed yet: answer in the terminal); --decide then
            # allows the buttons on the same card — a card cached on its id and status alone would keep that note.
            await wait(page, "(cmd) => [...document.querySelectorAll('#tasks li')].some((li) => li.textContent.includes(cmd) && li.querySelector('.perm-relay'))", arg=cmd,
                       timeout=15000, label=f"the card for {cmd} before --decide")
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
        # The independent check's shapes (P4–P6 review): a 2,500-character command whose tail is the part that matters, runs of spaces
        # and a line break — the card shows it verbatim (whitespace kept, the box scrolls); past 20,000 characters the
        # browser gets no buttons; a long Write says how much of its content is shown.
        long_cmd = "echo start" + "   x  y" * 350 + "\n  && echo two  spaces; rm -rf ~/tail-hidden"
        req = dict(base, hook_event_name="PermissionRequest", tool_name="Bash", tool_input={"command": long_cmd, "description": "run"},
                   permission_suggestions=sugg)
        hook(req)
        waiting = hook(req, decide=True)
        exact_js = "(cmd) => [...document.querySelectorAll('#tasks .perm-exact .pe-v')].find((el) => el.textContent === cmd)"
        await wait(page, f"(cmd) => {{ const el = ({exact_js})(cmd); return !!el && !!el.closest('li').querySelector('[data-do=\"deny\"]'); }}",
                   arg=long_cmd, timeout=15000, label="the long command, verbatim, with buttons")
        res["verbatim"] = await page.evaluate(f"""(cmd) => {{ const el = ({exact_js})(cmd), box = el.closest('.perm-exact');
            return {{ whiteSpace: getComputedStyle(box).whiteSpace, scrolls: box.scrollHeight > box.clientHeight, length: el.textContent.length }}; }}""", long_cmd)
        await page.evaluate(f"(cmd) => ({exact_js})(cmd).closest('li').querySelector('[data-do=\"deny\"]').click()", long_cmd)
        outp, err = waiting.communicate(timeout=40)
        res["longDeny"] = _json.loads(outp) if outp else None
        check(failures, res["verbatim"] == {"whiteSpace": "pre-wrap", "scrolls": True, "length": len(long_cmd)},
              f"real-decide: the long command is shown verbatim: {res['verbatim']}")
        check(failures, (res["longDeny"] or {}).get("hookSpecificOutput", {}).get("decision", {}).get("behavior") == "deny",
              f"real-decide: the long command's deny reached the hook: {res['longDeny']}")
        huge = "echo " + "z" * 20_001
        req = dict(base, hook_event_name="PermissionRequest", tool_name="Bash", tool_input={"command": huge}, permission_suggestions=sugg)
        hook(req)
        waiting = hook(req, decide=True)
        try:
            await wait(page, f"() => [...document.querySelectorAll('#tasks li')].some((li) => li.textContent.includes({json.dumps(T('panel.perm.toolong'))}))",
                       timeout=15000, label="the too-long card")
            res["tooLong"] = await page.evaluate("""(w) => { const li = [...document.querySelectorAll('#tasks li')].find((x) => x.textContent.includes(w));
                return { buttons: li.querySelectorAll('[data-do]').length }; }""", T("panel.perm.toolong"))
        finally:
            if waiting.poll() is None:
                waiting.terminate()   # our own child: the browser cannot answer it, the terminal would
                waiting.wait(timeout=10)
        check(failures, res["tooLong"] == {"buttons": 0}, f"real-decide: a command past 20,000 characters has no buttons: {res['tooLong']}")
        hook(dict(base, hook_event_name="PermissionRequest", tool_name="Write", tool_input={"file_path": "/work/notes.txt", "content": "c" * 3000}))
        await wait(page, f"() => [...document.querySelectorAll('#tasks .pe-note')].some((el) => el.textContent === {json.dumps(T('panel.exact.cut', shown=2000, all=3000))})",
                   timeout=15000, label="the Write card's content note")
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
