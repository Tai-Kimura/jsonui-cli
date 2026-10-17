"""The live view against fake_server.py (scenarios.py), checked against plan P3's acceptance list.

Each check appends a readable line to `failures` when it does not hold, and the measured values go to
<out>/live-results.json. Step the scenario with POST /_fake/step?to=<mark>; read the page through window.__dbg.
"""

from __future__ import annotations

import json
import pathlib
import time
import urllib.request

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


async def run(pw, out, failures, Server):
    out = pathlib.Path(out) / "live"
    out.mkdir(parents=True, exist_ok=True)
    res = {}
    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    try:
        for name, build, fn in (("two-projects", scenarios.two_projects, scenario_two_projects),
                                ("themes", scenarios.two_projects, scenario_themes),
                                ("empty", scenarios.empty, scenario_empty)):
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
