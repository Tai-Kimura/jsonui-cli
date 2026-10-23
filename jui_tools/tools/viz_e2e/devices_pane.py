"""The デバイス button and pane (ticket 2026-10-20-jui-viz-device-panel-machine-load-and-emulators). Runs with
`--only devices`.

The requester: 「ヘッダのメニューにデバイスボタン用意してそれ押すとサイドのボードの位置くらいに全部出る 負荷に応じてボタンの色合いが
変わる」「デバイスの担当セッションわかる時はクリックでそのロボット選択状態にして欲しい 部屋の移動」.

The real `jui viz serve` in a throwaway HOME, with stand-in `xcrun` and `adb` first on its PATH (they only print a
device list: no real device is started, stopped or asked), and the real forward.py. Three sessions in two projects
(A: a1; B: b1, b2); three devices: a simulator a1's running test names (test), an emulator b2's last command names
(command), a phone a process names under p1's session process (process: a stand-in session process whose child's
arguments hold the phone's serial, tied by a session file), and a second phone nobody named (unknown).
Checked:
  * the button: shown, the device count, its data-load the server's level, a colour per level, the level in its label;
  * the pane where the side panel is: the load, the three kinds with their counts, the rows and how each was told,
    the unknown row not a button;
  * b1 picked in B, then a1 in A; b2's row pressed → B, b2 picked (not b1, the room's last picked), the pane closed;
  * Escape closes the pane, the focus back on the button;
  * the demo page: no button.
No console error; nothing outside the server.
"""

from __future__ import annotations

import json
import os
import pathlib
import stat
import subprocess
import sys
import time

from common import DESKTOP, ISOLATE, LAUNCH_ARGS, T, T_pattern, Watch, dump, new_page, ready

SIDS = {"a1": "e2e00000-0000-4000-8000-0000000000d1", "b1": "e2e00000-0000-4000-8000-0000000000d2",
        "p1": "e2e00000-0000-4000-8000-0000000000d4",
        "b2": "e2e00000-0000-4000-8000-0000000000d3"}
CWDS = {"a1": "/work/devices-a", "b1": "/work/devices-b", "b2": "/work/devices-b", "p1": "/work/devices-a"}
PHONE, PHONE2 = "R58M12345678", "R58N99999999"
UDID = "D0D0D0D0-1111-4222-8333-444455556666"
XCRUN = """#!/bin/sh
# stand-in for xcrun (the e2e only): one booted simulator, nothing else does anything
if [ "$1" = simctl ] && [ "$2" = list ]; then
  printf '%s\\n' '{"devices":{"com.apple.CoreSimulator.SimRuntime.iOS-26-2":[{"udid":"UDID","name":"iPhone 16","state":"Booted"}]}}'
fi
exit 0
""".replace("UDID", UDID)
ADB = """#!/bin/sh
# stand-in for adb (the e2e only): an emulator and two phones attached, nothing else does anything
if [ "$1" = devices ]; then
  printf 'List of devices attached\\nemulator-5554          device product:sdk model:sdk_gphone64_arm64 device:emu64a transport_id:1\\nR58M12345678           device product:x model:SM_S918B device:x transport_id:2\\nR58N99999999           device product:y model:SM_A546E device:y transport_id:3\\n\\n'
fi
exit 0
"""
STATE = "() => window.__dbg.devState()"


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def run_devices_pane(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "devices"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    sessions_dir = home / ".claude" / "sessions"   # watched by the server from its start: made before it
    sessions_dir.mkdir(parents=True, exist_ok=True)
    fake = out / "bin"
    fake.mkdir(exist_ok=True)
    for name, text in (("xcrun", XCRUN), ("adb", ADB)):
        (fake / name).write_text(text)
        (fake / name).chmod((fake / name).stat().st_mode | stat.S_IXUSR)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    srv_env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1", PATH=f"{fake}{os.pathsep}{base_env.get('PATH', '')}")
    srv_env.pop("ANDROID_HOME", None)
    srv_env.pop("ANDROID_SDK_ROOT", None)
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log,
                           stderr=subprocess.STDOUT, env=srv_env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def check(cond, text):
        if not cond:
            failures.append(f"devices: {text}")

    def hook(k, **payload):
        subprocess.run([sys.executable, "-I", "-S", str(forward)], timeout=10, capture_output=True, env=dict(base_env, HOME=str(home)),
                       input=json.dumps({"session_id": SIDS[k], "cwd": CWDS[k], "transcript_path": "/work/none.jsonl",
                                         "permission_mode": "default", **payload}).encode())

    # p1's session process (a stand-in, its own process group) with a child whose arguments name the phone
    stand_in = subprocess.Popen([sys.executable, "-c", "import subprocess, sys, time; subprocess.Popen([sys.executable, "
                                 f"'-c', 'import time; time.sleep(900)', '{PHONE}']); time.sleep(900)"],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
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
        for k in SIDS:
            hook(k, hook_event_name="SessionStart", source="startup")
        (sessions_dir / f"{stand_in.pid}.json").write_text(json.dumps({"pid": stand_in.pid, "sessionId": SIDS["p1"], "cwd": CWDS["p1"],
                                                                       "kind": "interactive", "entrypoint": "cli", "status": "idle",
                                                                       "procStart": f"t{stand_in.pid}"}))
        hook("a1", hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="dev-test-1",
             tool_input={"command": f"xcodebuild test -scheme App -destination id={UDID}"})
        hook("b2", hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="dev-cmd-1",
             tool_input={"command": "adb -s emulator-5554 shell input tap 10 10"})
        hook("b2", hook_event_name="PostToolUse", tool_name="Bash", tool_use_id="dev-cmd-1",
             tool_input={"command": "adb -s emulator-5554 shell input tap 10 10"}, tool_response={"stdout": ""})
        watch = Watch(origin=url)
        page = await new_page(browser, watch, "devices", **DESKTOP)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelectorAll('#sessions [data-robot-open]').length >= 4", label="four sessions")
        who = await page.evaluate("(sids) => Object.fromEntries(Object.entries(sids).map(([k, sid]) => [k, window.__dbg.labelOfSession(sid)]))", SIDS)
        proj = await page.evaluate("(ls) => Object.fromEntries(Object.entries(ls).map(([k, l]) => [k, window.__dbg.robotProject(l)]))", who)
        res["who"], res["proj"] = who, proj
        A, B = proj["a1"], proj["b1"]
        check(A and B and A != B and proj["b2"] == B, f"two projects: {proj}")

        # the button: the count and the server's level
        await wait(page, f"() => {{ const b = document.getElementById('btn-devices'); return !b.hidden && b.textContent === {json.dumps(T('dev.button.count', count=4))} && !!b.dataset.load; }}",
                   timeout=30000, label="the button with four devices and a level")
        btn = res["button"] = await page.evaluate("""() => { const b = document.getElementById('btn-devices'), m = window.__dbg.devMachine() || {};
          return { load: b.dataset.load, level: m.level, label: b.getAttribute('aria-label'), colours: window.__dbg.devColours(), cpus: m.cpus, hasLoad: Array.isArray(m.load) }; }""")
        check(btn["load"] == btn["level"] and btn["level"] in ("ok", "busy", "high") and btn["hasLoad"] and btn["cpus"],
              f"the button's colour is the server's level: {btn}")
        check(len(set(btn["colours"].values())) == 3, f"a colour per level: {btn['colours']}")
        check(btn["label"] == T("dev.button.aria", level=T(f"dev.level.{btn['level']}"), n=4),
              f"the level and the count in the button's label: {btn['label']}")

        # b1 picked in B, then a1 in A: B's last picked robot is b1
        await page.evaluate("(l) => window.__dbg.openRobot(l)", who["b1"])
        await wait(page, "(l) => window.__dbg.devState().robot === l", arg=who["b1"], label="b1 picked")
        await page.evaluate("(p) => window.__dbg.setProject(p)", A)
        await page.evaluate("(l) => window.__dbg.openRobot(l)", who["a1"])
        await wait(page, "(l) => window.__dbg.devState().robot === l", arg=who["a1"], label="a1 picked in A")
        await page.wait_for_timeout(700)
        check(await page.evaluate("([p, l]) => window.__dbg.lastRobot(p) === l", [B, who["b1"]]), "B remembers b1 before the press")

        # the pane
        await page.click("#btn-devices")
        await wait(page, "() => !document.getElementById('dev-pane').hidden && document.querySelectorAll('#dev-pane .dev-row').length === 4 && (document.querySelector(`#dev-pane .dev-row[data-dev-id='R58M12345678']`) || {}).tagName === 'BUTTON'",
                   timeout=40000, label="the pane's four rows, the phone told by p1's process (the next device scan)")
        pane = res["pane"] = await page.evaluate("""() => { const P = document.getElementById('dev-pane'), side = document.getElementById('side').getBoundingClientRect(), r = P.getBoundingClientRect();
          const row = (id) => { const e = P.querySelector(`.dev-row[data-dev-id="${CSS.escape(id)}"]`); return e ? { button: e.tagName === 'BUTTON', robot: e.dataset.devRobot || null, text: e.textContent } : null; };
          return { kinds: [...P.querySelectorAll('.dev-group h3')].map((h) => h.textContent), load: !!P.querySelector('[data-dev-load]'), loadText: (P.querySelector('[data-dev-load]') || {}).textContent || '',
            right: Math.round(window.innerWidth - r.right), overSide: r.left <= side.left + 2 && r.width >= side.width - 2, focus: document.activeElement && document.activeElement.id,
            underHeader: r.top >= Math.round(document.querySelector('.topbar').getBoundingClientRect().bottom) - 1,
            buttonSeen: (() => { const b = document.getElementById('btn-devices').getBoundingClientRect(); const e = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2); return !!e && e.closest('#btn-devices') !== null; })(),
            sim: row('UDID'), emu: row('emulator-5554'), phone: row('R58M12345678'), phone2: row('R58N99999999') }; }""".replace("UDID", UDID))
        check(pane["kinds"] == [T("dev.group.title", kind=T("dev.kind.ios"), n=1), T("dev.group.title", kind=T("dev.kind.emulator"), n=1),
                                T("dev.group.title", kind=T("dev.kind.phone"), n=2)], f"the three kinds and counts: {pane['kinds']}")
        check(pane["load"] and T_pattern("dev.cpu.head").search(pane["loadText"]) and T_pattern("dev.mem.head").search(pane["loadText"]), f"the load: {pane['loadText']}")
        # the load box as a person reads it (the requester, 10-23: 「load のところが何を表してるか分かりづらい」): the page's
        # own machine slice set to two known states and the box read in the same call (the server's next push would
        # write the real one over it): the CPU's busyness in per cent with what 100 % means, the three averages in a
        # line with the way they go, the free memory, the colour rule in words. Stills of both, and of a phone's width.
        LOADS = {"high": {"load": [18.83, 23.39, 29.37], "cpus": 18, "memTotal": 128 * 2 ** 30, "memFreePct": 90, "level": "high"},
                 "ok": {"load": [4.1, 3.2, 2.0], "cpus": 18, "memTotal": 128 * 2 ** 30, "memFreePct": 62, "level": "ok"}}
        BOX = """(m) => { window.__dbg.devMachineSet(m);
          const B = document.querySelector('#dev-pane [data-dev-load]'), t = (q) => (B.querySelector(q) || {}).textContent || null;
          const bar = (k) => { const e = B.querySelector(`.dev-bar[data-bar="${k}"]`); if (!e) return null; const f = e.querySelector('.dev-bar-fill'), mk = e.querySelector('.dev-bar-mark');
            return { tone: e.dataset.tone, fill: f.style.width, mark: mk ? mk.style.left : null, colour: getComputedStyle(f).backgroundColor }; };
          return { cpu: t('[data-dev-cpu] span'), what: t('[data-dev-what]'), recent: t('[data-dev-recent]'), mem: t('[data-dev-mem] span'), rule: t('[data-dev-rule]'),
            cpuBar: bar('cpu'), memBar: bar('mem'), load: B.dataset.load }; }"""
        # each kind's heading apart from what is above it, the load box or the kind before (the requester, 10-23: the
        # iOS simulators' heading sat on the load box's lower edge)
        GAPS = """() => [...document.querySelectorAll('#dev-body > .dev-group')].map((g) => { const h = g.querySelector('h3').getBoundingClientRect(),
          prev = g.previousElementSibling.getBoundingClientRect(); return { kind: g.dataset.devKind, gap: Math.round(h.top - prev.bottom) }; })"""
        for key, mach in LOADS.items():
            box = res[f"box-{key}"] = await page.evaluate(BOX, mach)
            pct = round(mach["load"][0] / mach["cpus"] * 100)
            trend = T("dev.load.trend.down") if key == "high" else T("dev.load.trend.up")
            check(box["cpu"] == T("dev.cpu.head", pct=pct) and box["what"] == T("dev.cpu.what", cpus=18)
                  and box["recent"] == T("dev.load.recent", a=f"{mach['load'][0]:.1f}", b=f"{mach['load'][1]:.1f}", c=f"{mach['load'][2]:.1f}", trend=trend)
                  and box["mem"] == T("dev.mem.head", pct=mach["memFreePct"]) + T("dev.mem.of", total="128 GiB")
                  and box["rule"] == T("dev.load.rule", cb=70, ch=100, mb=25, mh=10),
                  f"{key}: the CPU in per cent and what 100 % means, the three averages and their way, the memory, the rule: {box}")
            check(box["cpuBar"] and box["cpuBar"]["tone"] == ("high" if pct >= 100 else "busy" if pct >= 70 else "ok") and box["cpuBar"]["mark"] == "50%"
                  and box["memBar"] and box["memBar"]["tone"] == "ok" and box["memBar"]["fill"] == f"{mach['memFreePct']}%",
                  f"{key}: the bars, the CPU's marked at 100 %, coloured by the rule: {box['cpuBar']} {box['memBar']}")
            gaps = res[f"gaps-{key}"] = await page.evaluate(GAPS)
            check(len(gaps) == 3 and all(g["gap"] >= 8 for g in gaps), f"{key}: each kind's heading 8 px or more under the box before it: {gaps}")
            await page.screenshot(path=str(out / f"load-{key}.png"))
        check(res["box-high"]["cpuBar"]["colour"] != res["box-ok"]["cpuBar"]["colour"], f"the CPU bar's colour follows its tone: {res['box-high']['cpuBar']} {res['box-ok']['cpuBar']}")
        await page.set_viewport_size({"width": 390, "height": 844})
        res["box-390"] = await page.evaluate(BOX, LOADS["high"])
        check(res["box-390"]["cpu"] == T("dev.cpu.head", pct=105), f"390: the box drawn at a phone's width: {res['box-390']}")
        gaps = res["gaps-390"] = await page.evaluate(GAPS)
        check(len(gaps) == 3 and all(g["gap"] >= 8 for g in gaps), f"390: each kind's heading 8 px or more under the box before it: {gaps}")
        await page.screenshot(path=str(out / "load-390.png"))
        await page.set_viewport_size(DESKTOP["viewport"])
        check(pane["right"] == 0 and pane["overSide"], f"where the side panel is: {pane}")
        check(pane["underHeader"] and pane["buttonSeen"], f"under the header, the デバイス button not covered (it closes the pane): {pane}")
        check(pane["focus"] == "dev-close", f"the focus in the pane: {pane['focus']}")
        sim, emu, phone, phone2 = pane["sim"] or {}, pane["emu"] or {}, pane["phone"] or {}, pane["phone2"] or {}
        check(sim.get("button") and sim.get("robot") == who["a1"] and T("dev.how.test") in sim.get("text", ""), f"the simulator: a1's test: {sim}")
        check(emu.get("button") and emu.get("robot") == who["b2"] and T_pattern("dev.how.command").search(emu.get("text", "")), f"the emulator: b2's command, estimated: {emu}")
        check(phone.get("button") and phone.get("robot") == who["p1"] and T("dev.how.process") in phone.get("text", ""),
              f"the phone: p1's process, estimated: {phone}")
        check(phone2 and not phone2.get("button") and T("dev.who.unknown") in phone2.get("text", ""), f"the second phone: unknown, not a button: {phone2}")
        await page.screenshot(path=str(out / "pane.png"))

        # b2's row: B, b2 picked (the press wins over B's last picked b1), the pane closed
        await page.click("#dev-pane .dev-row[data-dev-id='emulator-5554']")
        await wait(page, "([l, p]) => { const s = window.__dbg.devState(); return s.robot === l && s.project === p && s.card; }", arg=[who["b2"], B], timeout=15000, label="B, b2 picked")
        await page.wait_for_timeout(900)
        got = res["afterPress"] = await page.evaluate(STATE)
        check(got == {"robot": who["b2"], "project": B, "card": True, "pane": False}, f"after the press: {got}")
        await page.screenshot(path=str(out / "pressed.png"))

        # Escape closes the pane, the focus back on the button
        await page.click("#btn-devices")
        await wait(page, "() => !document.getElementById('dev-pane').hidden", label="the pane again")
        await page.keyboard.press("Escape")
        await wait(page, "() => document.getElementById('dev-pane').hidden", label="Escape closes the pane")
        res["focusAfterEscape"] = await page.evaluate("() => document.activeElement && document.activeElement.id")
        check(res["focusAfterEscape"] == "btn-devices", f"the focus back on the button: {res['focusAfterEscape']}")
        await page.close()

        demo = await new_page(browser, watch, "devices-demo", **DESKTOP)
        await demo.goto(url + "/?demo=1")
        await ready(demo)
        await demo.wait_for_timeout(1500)
        res["demoButton"] = await demo.evaluate("() => !document.getElementById('btn-devices').hidden")
        check(res["demoButton"] is False, "the demo has no デバイス button")
        await demo.close()
        for line in watch.console:
            failures.append(f"devices: console: {line}")
        for u in watch.foreign:
            failures.append(f"devices: request outside the server: {u}")
    except Exception as e:
        failures.append(f"devices: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        try:
            os.killpg(stand_in.pid, 9)   # the stand-in and its child
        except ProcessLookupError:
            pass
        stand_in.wait()
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  devices: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "devices-results.json").write_text(dump(res) + "\n")
