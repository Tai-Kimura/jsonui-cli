"""Browser notifications and the question window (2.3.6; tickets 2026-10-19-jui-viz-notify-done-ask-permission and
2026-10-19-jui-viz-question-window-too-short).

The real `jui viz serve` in a throwaway HOME on a free port, the real forward.py (--decide and --ask as Claude Code runs
them), two tabs of one browser context (one localStorage, one set of Web Locks, as two tabs of one Chrome profile), and
window.Notification replaced by a stand-in that starts as "default" and logs every notification to a list both tabs
share. Waits are on state (wait_for_function), never on time.

  * nothing is asked on load; the settings' button asks once and the permission is granted
  * a main robot's turn end, a waiting permission and a waiting question ring once each in all — never twice, not
    once per tab; the text names the session and, for a question, how long it waits
  * a click on each opens the robot's card, the board on that permission, the questions
  * a reload rings nothing again; a kind turned off in one tab rings from neither
  * a hidden page with question notifications on holds a question for the page; turned off, the question goes back
    at once and the card says the page went out of sight
  * the question window chosen in the settings is the header's chip and the server's from then on
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, ISOLATE, LAUNCH_ARGS, T, T_pattern, Watch, dump, new_page, ready

SID = "a0000000-0000-4000-8000-0000000000c1"
Q = {"questions": [{"question": "どちらにしますか", "header": "選択", "multiSelect": False,
                    "options": [{"label": "左", "description": "左にする"}, {"label": "右", "description": "右にする"}]}]}

# A stand-in for the browser's Notification: "default" until requestPermission (the grant is kept in localStorage,
# so both tabs see it, as two tabs of one profile do); each one made is logged to localStorage (shared) and kept in
# window.__shown (this tab's, with its onclick).
STUB = r"""(() => {
  const read = () => { try { return localStorage.getItem('e2e-perm') || 'default'; } catch (e) { return 'default'; } };
  window.__shown = []; window.__asked = 0;
  class FakeNotification {
    constructor(title, opts) {
      this.title = title; this.body = (opts && opts.body) || ''; this.tag = (opts && opts.tag) || ''; this.onclick = null;
      window.__shown.push(this);
      try { const a = JSON.parse(localStorage.getItem('e2e-shown') || '[]'); a.push({ tag: this.tag, body: this.body, title: this.title }); localStorage.setItem('e2e-shown', JSON.stringify(a)); } catch (e) {}
    }
    close() {}
  }
  Object.defineProperty(FakeNotification, 'permission', { get: read });
  FakeNotification.requestPermission = () => { window.__asked += 1; try { localStorage.setItem('e2e-perm', 'granted'); } catch (e) {} return Promise.resolve('granted'); };
  window.Notification = FakeNotification;
  // a stand-in AudioContext: "running" after resume unless the test says 'suspended'; each chime starts two tones,
  // logged to localStorage (shared by the tabs)
  class FakeAudioContext {
    constructor() { this.state = 'suspended'; this.currentTime = 0; this.destination = {}; window.__ac = this; }
    // Chromium's rule: a context runs only after a press on the page since it loaded (sticky user activation); the
    // test can also hold it suspended ('e2e-ac'); it settles a moment later, as a real one does
    // 'gesture': a stricter browser's rule — resume only while the page is being pressed (transient activation, read
    // at the call), so only a press can bring a context back
    resume() {
      const mode = window.__acMode || localStorage.getItem('e2e-ac') || 'running', ua = navigator.userActivation;   // __acMode: this tab only
      const may = mode === 'running' ? !!(ua && ua.hasBeenActive) : mode === 'gesture' ? !!(ua && ua.isActive) : false;
      return new Promise((done) => setTimeout(() => { if (may) this.state = 'running'; done(); }, 20));
    }
    createOscillator() { return { type: '', frequency: { setValueAtTime() {} }, connect() {}, stop() {},
      start() { try { localStorage.setItem('e2e-tones', String(Number(localStorage.getItem('e2e-tones') || 0) + 1)); } catch (e) {} } }; }
    // the peak a chime's tones reach (the volume setting), kept shared
    createGain() { return { gain: { setValueAtTime() {}, exponentialRampToValueAtTime(v) { if (v > 0.001) try { localStorage.setItem('e2e-peak', String(v)); } catch (e) {} } }, connect() {} }; }
  }
  window.AudioContext = FakeAudioContext;
})();"""
CHIMES = "() => Number(localStorage.getItem('e2e-tones') || 0) / 2"
SHOWN = "() => JSON.parse(localStorage.getItem('e2e-shown') || '[]')"


def check(failures, cond, text):
    if not cond:
        failures.append(f"notify: {text}")


async def wait(page, js, arg=None, timeout=20000, label=""):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=100)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def run_notify(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "notify"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    state = home / ".local" / "state" / "jui-viz"
    state.mkdir(parents=True, exist_ok=True)
    (state / "config.json").write_text(json.dumps({"askPingSec": 1}))
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT,
                           env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"
    res: dict = {}
    held: list = []

    def body(**payload):
        return {"session_id": SID, "cwd": "/work/notify-app", "transcript_path": "/work/home/t.jsonl", "permission_mode": "default", **payload}

    def hook(payload, flag=None):
        args = [sys.executable, "-I", "-S", str(forward)] + ([flag] if flag else [])
        p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(base_env, HOME=str(home)))
        p.stdin.write(json.dumps(payload).encode())
        p.stdin.close()
        p.stdin = None
        if flag:
            held.append(p)
            return p
        p.wait(timeout=10)
        return None

    def turn():
        hook(body(hook_event_name="UserPromptSubmit", prompt="go"))
        hook(body(hook_event_name="Stop"))

    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    watch = Watch(origin=url)
    t0 = time.monotonic()
    try:
        import urllib.request
        for _ in range(400):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        hook(body(hook_event_name="SessionStart", source="startup"))
        ctx = await browser.new_context(**DESKTOP)
        await ctx.add_init_script(STUB)
        a = await ctx.new_page()
        watch.attach(a, "notify-a")
        await a.goto(url + "/")
        await ready(a)
        await wait(a, "() => Object.keys(window.__dbg.robotState()).length >= 1", timeout=30000, label="the robot")
        rid = (await a.evaluate("() => Object.keys(window.__dbg.robotState())"))[0]

        # 1. nothing asked on load; the settings' button asks once
        await wait(a, "() => !document.getElementById('btn-notify').hidden && !document.getElementById('chip-askwait').hidden", label="the settings' button and chip")
        res["chip"] = await a.evaluate("() => document.getElementById('chip-askwait').textContent")
        check(failures, res["chip"] == T("panel.ask.chip", wait=T("srv.ask.min", n="3")), f"the chip says the default window: {res['chip']!r}")
        check(failures, await a.evaluate("() => window.__asked") == 0, "nothing is asked on load")
        await a.click("#btn-notify")
        await wait(a, "() => !document.getElementById('notify-ask-perm').hidden", label="the permission button")
        # the OS's own switch (the orchestrator and the requester, 10-19: off, nothing showed, and the question still waited in viz)
        res["osNote"] = await a.evaluate("() => { const e = document.getElementById('notify-os-note'); return e && e.offsetParent !== null ? e.textContent : null; }")
        check(failures, bool(res["osNote"]) and T("page.notify.os.note") in res["osNote"],
              f"the settings say the Mac's own switch for Chrome: {res['osNote']!r}")
        await a.screenshot(path=str(out / "settings-light.png"))
        await a.click("#notify-ask-perm")
        await wait(a, f"() => document.getElementById('notify-perm-state').textContent.includes({json.dumps(T('panel.nt.granted'))})", label="granted")
        check(failures, await a.evaluate("() => window.__asked") == 1, "asked once, from the button")
        await a.keyboard.press("Escape")

        b = await ctx.new_page()
        watch.attach(b, "notify-b")
        await b.goto(url + "/")
        await ready(b)
        await wait(b, "() => Object.keys(window.__dbg.robotState()).length >= 1", timeout=30000, label="tab b's robot")
        # a press in tab b too (a tab nobody has pressed in cannot make a sound: the browser's rule)
        await b.mouse.click(5, 880)
        for p, name in ((a, "a"), (b, "b")):
            await wait(p, "() => window.__dbg.notifyAudio() === 'running'", label=f"tab {name}'s sound woken")

        async def shown_after(n, label):
            await wait(a, f"() => JSON.parse(localStorage.getItem('e2e-shown') || '[]').length >= {n}", label=label)
            for p in (a, b):   # every tab has taken its look at the event (none rings late)
                try:
                    await wait(p, f"() => window.__dbg.notifySeen().length >= {n}", label=f"{label}: every tab saw it")
                except RuntimeError:
                    seen = [await q.evaluate("() => ({ seen: window.__dbg.notifySeen(), based: window.__dbg.notifyBased(), qs: window.__dbg.questions() })") for q in (a, b)]
                    raise RuntimeError(f"{label}: a tab did not see it: a={seen[0]} b={seen[1]}") from None
            return await a.evaluate(SHOWN)

        async def owner_of(tag):
            for p in (a, b):
                if await p.evaluate("(t) => window.__shown.some((n) => n.tag === t)", tag):
                    return p
            return None

        # 2. done, permission, question: once each in all
        turn()
        shown = await shown_after(1, "the turn end's notification")
        res["done"] = shown[-1]
        check(failures, len(shown) == 1 and T_pattern("panel.nt.done").fullmatch(shown[0]["body"]) and ":done:" in shown[0]["tag"], f"the turn end rings once: {shown}")
        perm_p = hook(body(hook_event_name="PermissionRequest", tool_name="Bash", tool_input={"command": "ls -la /tmp", "description": "一覧"}), "--decide")
        shown = await shown_after(2, "the permission's notification")
        res["perm"] = shown[-1]
        check(failures, len(shown) == 2 and T_pattern("panel.nt.perm", tool="Bash").search(shown[1]["body"]) and "ls -la" not in shown[1]["body"],
              f"the permission rings once, the tool's name and not the command: {shown}")
        # the two hooks of a question in the order that sent the text to the terminal: the async one first, seen by the
        # page before --ask (ticket 2026-10-20-jui-viz-notify-ask-says-terminal-while-viz-waits)
        hook(body(hook_event_name="PreToolUse", tool_name="AskUserQuestion", tool_use_id="ask-1", tool_input=Q))
        await wait(a, "() => window.__dbg.questions().some((q) => q.status === 'pending' && !q.hookWaiting)", label="the card before --ask")
        ask_p = hook(body(hook_event_name="PreToolUse", tool_name="AskUserQuestion", tool_use_id="ask-1", tool_input=Q), "--ask")
        shown = await shown_after(3, "the question's notification")
        res["ask"] = shown[-1]
        check(failures, len(shown) == 3 and T_pattern("panel.nt.ask", how=T("panel.nt.left", wait=T("srv.ask.min", n="3"))).search(shown[2]["body"]),
              f"the question rings once and says how long it waits (--ask after the card): {shown}")
        res["perTab"] = [len(await p.evaluate("() => window.__shown")) for p in (a, b)]
        check(failures, sum(res["perTab"]) == 3, f"three in all, not three per tab: {res['perTab']}")
        # a question with the async hook only (no --ask installed): after the wait for --ask, once, to the terminal
        Q2 = {"questions": [{**Q["questions"][0], "question": "上と下のどちら"}]}
        hook(body(hook_event_name="PreToolUse", tool_name="AskUserQuestion", tool_use_id="ask-nohook", tool_input=Q2))
        shown = await shown_after(4, "the question without --ask")
        res["askNoHook"] = shown[3:]
        check(failures, len(shown) == 4 and T("panel.nt.terminal") in shown[3]["body"], f"a question with no --ask: once, to the terminal: {shown[3:]}")
        hook(body(hook_event_name="PostToolUse", tool_name="AskUserQuestion", tool_use_id="ask-nohook", tool_input=Q2, tool_response={"answers": {}}))
        await wait(a, "() => window.__dbg.questions().filter((q) => q.status === 'pending').length <= 1", label="the second question answered")
        try:
            await wait(a, "() => Number(localStorage.getItem('e2e-tones') || 0) / 2 >= 4", timeout=5000, label="four chimes")
        except RuntimeError:
            pass
        res["chimes"] = await a.evaluate(CHIMES)
        check(failures, res["chimes"] == 4, f"one chime per notification (four), from the tab that showed it: {res['chimes']}")

        # 3. a click opens what it is about
        for kind, js, label in (("done", "(id) => window.__dbg.board().robot === id", "the robot's card"),
                                ("perm", "() => { const s = window.__dbg.board(); return s.open && !!s.detail && (s.detail.startsWith('perm:') || s.detail.includes('#')); }", "the board on the permission"),
                                ("ask", "() => { const s = window.__dbg.board(); return s.open && s.waitView; }", "the board's questions")):
            tag = res[kind]["tag"]
            p = await owner_of(tag)
            check(failures, p is not None, f"{kind}: a tab made it")
            if p is None:
                continue
            await p.evaluate("(t) => window.__shown.find((n) => n.tag === t).onclick()", tag)
            try:
                await wait(p, js, arg=rid, label=f"a click on the {kind} notification opens {label}")
                res.setdefault("opened", []).append(kind)
            except RuntimeError as e:
                check(failures, False, str(e))
            await p.keyboard.press("Escape")
            await p.keyboard.press("Escape")
        await a.screenshot(path=str(out / "board-light.png"))

        # the first question goes back to the terminal (the card's button) and the permission's hook is let go
        await a.evaluate("() => window.__dbg.questions().filter((q) => q.hookWaiting).forEach((q) => window.__dbg.questionRelease(q.id))")
        ask_p.wait(timeout=10)
        perm_p.kill()
        perm_p.wait(timeout=10)

        # 3b. the chime turned off: the notification shows, no sound
        n0, c0 = len(await a.evaluate(SHOWN)), await a.evaluate(CHIMES)
        await a.evaluate("() => window.__dbg.notifySet({ chime: false })")
        await wait(b, "() => window.__dbg.notifyOn().chime === false", label="the chime's switch reaches tab b")
        turn()
        await shown_after(n0 + 1, "a turn end with the chime off")
        res["chimeOff"] = [len(await a.evaluate(SHOWN)) - n0, await a.evaluate(CHIMES) - c0]
        check(failures, res["chimeOff"] == [1, 0], f"the chime off: the notification, no sound: {res['chimeOff']}")
        await a.evaluate("() => window.__dbg.notifySet({ chime: true })")
        await wait(b, "() => window.__dbg.notifyOn().chime === true", label="the chime back on in tab b")
        # 3c. a sound the browser keeps suspended: the notification still shows, without sound, and nothing breaks
        n0, c0 = len(await a.evaluate(SHOWN)), await a.evaluate(CHIMES)
        for p in (a, b):
            await p.evaluate("() => { localStorage.setItem('e2e-ac', 'suspended'); window.__ac.state = 'suspended'; }")
        for p, name in ((a, "a"), (b, "b")):   # each has heard the other say its sound no longer runs
            await wait(p, "() => !window.__dbg.notifyPeers().includes(true)", timeout=8000, label=f"tab {name} hears no tab can sound")
        turn()
        await shown_after(n0 + 1, "a turn end with the sound suspended")
        res["suspended"] = [len(await a.evaluate(SHOWN)) - n0, await a.evaluate(CHIMES) - c0]
        check(failures, res["suspended"] == [1, 0], f"a suspended sound: the notification, no sound: {res['suspended']}")
        owner = await owner_of((await a.evaluate(SHOWN))[-1]["tag"])
        if owner:   # the try is kept once the resume has had its time (NOTIFY_RESUME_MS)
            await wait(owner, "() => (window.__dbg.notifyLastChime() || {}).noTab !== undefined && window.__dbg.notifyLastChime().before === 'suspended'",
                       timeout=5000, label="the chime's try kept")
            await owner.evaluate("() => window.__dbg.notifyPanel()")
            res["noTab"] = [await owner.evaluate("() => (window.__dbg.notifyLastChime() || {}).noTab"),
                            await owner.evaluate("() => document.getElementById('notify-chime-note').textContent")]
            await owner.keyboard.press("Escape")
        check(failures, bool(res.get("noTab")) and res["noTab"][0] is True and T("panel.chime.notab").strip() in res["noTab"][1],
              f"no tab can sound: the settings say so: {res.get('noTab')}")
        for p in (a, b):
            await p.evaluate("() => { localStorage.setItem('e2e-ac', 'running'); window.__ac.state = 'running'; }")

        # 3d. the context gone back to suspended (a press there was): the chime asks it to resume first and sounds —
        # before 2.3.6's fix it gave up, and the real check heard nothing (10-20)
        n0, c0 = len(await a.evaluate(SHOWN)), await a.evaluate(CHIMES)
        for p in (a, b):
            await p.evaluate("() => { window.__ac.state = 'suspended'; }")
        turn()
        await shown_after(n0 + 1, "a turn end with the sound gone back to suspended")
        await wait(a, f"() => Number(localStorage.getItem('e2e-tones') || 0) / 2 >= {c0 + 1}", timeout=5000, label="the chime after a resume")
        owner = await owner_of((await a.evaluate(SHOWN))[-1]["tag"])
        res["resumed"] = {"chimes": await a.evaluate(CHIMES) - c0, "last": await owner.evaluate("() => window.__dbg.notifyLastChime()") if owner else None,
                          "note": await owner.evaluate("() => document.getElementById('notify-chime-note').textContent") if owner else None}
        last = res["resumed"]["last"] or {}
        check(failures, res["resumed"]["chimes"] == 1 and last.get("before") == "suspended" and last.get("after") == "running" and last.get("played") is True,
              f"a suspended context is resumed before the chime, and the try is kept: {res['resumed']}")

        # 3e. a press wakes the sound again: back to suspended where only a press can resume it, the page pressed once
        # more — it runs again (with the press handled once only, the first press long gone: still suspended)
        await a.evaluate("() => { localStorage.setItem('e2e-ac', 'gesture'); window.__ac.state = 'suspended'; }")
        await a.mouse.click(5, 880)
        try:
            await wait(a, "() => window.__dbg.notifyAudio() === 'running'", timeout=5000, label="a press brings the sound back")
            res["pressWakes"] = "running"
        except RuntimeError:
            res["pressWakes"] = await a.evaluate("() => window.__dbg.notifyAudio()")
        check(failures, res["pressWakes"] == "running", f"a later press wakes a context gone back to suspended: {res['pressWakes']}")
        await a.evaluate("() => localStorage.setItem('e2e-ac', 'running')")
        for p in (a, b):
            await p.evaluate("() => { window.__ac.state = 'running'; }")

        # 3g. the volume (requester 10-20: 「音が少し小さいね」): 中 by default, and 小・中・大 reach the tones' peak
        res["volume"] = {"default": await a.evaluate("() => window.__dbg.notifyVolume()")}
        for vol in ("mid", "low", "high"):
            if vol != "mid":
                await b.click("#btn-notify")
                await b.select_option("#notify-volume", vol)
                await b.keyboard.press("Escape")
                await wait(a, "(v) => window.__dbg.notifyVolume() === v", arg=vol, label=f"the volume {vol} reaches tab a")
            n0, c0 = len(await a.evaluate(SHOWN)), await a.evaluate(CHIMES)
            await a.evaluate("() => localStorage.removeItem('e2e-peak')")
            turn()
            await shown_after(n0 + 1, f"a turn end at volume {vol}")
            await wait(a, f"() => Number(localStorage.getItem('e2e-tones') || 0) / 2 >= {c0 + 1}", timeout=5000, label=f"the chime at {vol}")
            owner = await owner_of((await a.evaluate(SHOWN))[-1]["tag"])
            res["volume"][vol] = [float(await a.evaluate("() => localStorage.getItem('e2e-peak')") or 0),
                                  await owner.evaluate("() => (window.__dbg.notifyLastChime() || {}).peak") if owner else None]
        v = res["volume"]
        check(failures, v["default"] == "mid" and v["mid"] == [0.2, 0.2] and v["low"] == [0.1, 0.1] and v["high"] == [0.35, 0.35],
              f"the volume: 中 by default, each setting the peak the tones reach: {v}")
        await b.click("#btn-notify")
        await b.select_option("#notify-volume", "mid")
        await b.keyboard.press("Escape")
        await wait(a, "() => window.__dbg.notifyVolume() === 'mid'", label="the volume back to 中")

        # 3f. the real check 2 (10-20): a tab whose sound never started took the event first and showed it silently,
        # while another tab could sound. Here tab a cannot sound and takes events first (tab b is held back 800 ms):
        # it leaves the event to b, which shows it once and sounds; a shows nothing
        await a.evaluate("() => { window.__acMode = 'suspended'; window.__ac.state = 'suspended'; }")
        await b.evaluate("() => window.__dbg.notifyDelay(800)")
        await wait(a, "() => window.__dbg.notifyPeers().includes(true)", timeout=8000, label="tab a hears that tab b can sound")
        # and tab b says nothing more for 7 s (a hidden tab's timers can run once a minute): its last word still holds
        await b.evaluate("() => window.__dbg.notifySayStop()")
        t7 = await a.evaluate("() => performance.now()")
        await wait(a, "(t) => performance.now() > t + 7000", arg=t7, timeout=15000, label="7 s of tab a's clock")
        n0, c0 = len(await a.evaluate(SHOWN)), await a.evaluate(CHIMES)
        a0, b0 = len(await a.evaluate("() => window.__shown")), len(await b.evaluate("() => window.__shown"))
        turn()
        await shown_after(n0 + 1, "a turn end, only tab b can sound")
        try:
            await wait(a, f"() => Number(localStorage.getItem('e2e-tones') || 0) / 2 >= {c0 + 1}", timeout=5000, label="the chime from tab b")
        except RuntimeError:
            pass
        res["yield"] = {"a": len(await a.evaluate("() => window.__shown")) - a0, "b": len(await b.evaluate("() => window.__shown")) - b0,
                        "shown": len(await a.evaluate(SHOWN)) - n0, "chimes": await a.evaluate(CHIMES) - c0}
        check(failures, res["yield"] == {"a": 0, "b": 1, "shown": 1, "chimes": 1},
              f"the tab that can sound rings it, the one that cannot leaves it: {res['yield']}")

        # 3h. quiet in the tab that can sound (the independent check, 10-20): b in front, showing that robot's card, takes the event without a
        # ring; a left it to b, and a moment later finds it taken — neither shows it, no sound
        await b.bring_to_front()
        await b.evaluate("(id) => window.__dbg.openRobot(id)", rid)
        await wait(b, "(id) => window.__dbg.board().robot === id", arg=rid, label="tab b shows the robot's card")
        res["quietB"] = {"focus": await b.evaluate("() => [document.visibilityState, document.hasFocus()]")}
        n0, c0 = len(await a.evaluate(SHOWN)), await a.evaluate(CHIMES)
        seen_a = await a.evaluate("() => window.__dbg.notifySeen()")
        turn()
        await wait(a, "(before) => window.__dbg.notifySeen().some((k) => k.includes(':done:') && !before.includes(k))", arg=seen_a, label="tab a saw the quiet turn end")
        t0 = await a.evaluate("() => performance.now()")
        await wait(a, "(t) => performance.now() > t + 2500", arg=t0, timeout=8000, label="past tab a's wait to take it back")
        res["quietB"].update({"shown": len(await a.evaluate(SHOWN)) - n0, "chimes": await a.evaluate(CHIMES) - c0})
        check(failures, res["quietB"] == {"focus": ["visible", True], "shown": 0, "chimes": 0},
              f"quiet in the tab that can sound: the other tab does not show it either: {res['quietB']}")
        await b.keyboard.press("Escape")
        await a.bring_to_front()

        # 3i. the tab that said it can sound never takes the event (it takes events 5 s late here; it could have gone
        # without a good-bye): a shows it itself once its wait is over — the notification is never lost
        await b.evaluate("() => window.__dbg.notifyDelay(5000)")
        n0, c0 = len(await a.evaluate(SHOWN)), await a.evaluate(CHIMES)
        a0, b0 = len(await a.evaluate("() => window.__shown")), len(await b.evaluate("() => window.__shown"))
        t0 = await a.evaluate("() => performance.now()")
        turn()
        try:
            await wait(a, f"() => JSON.parse(localStorage.getItem('e2e-shown') || '[]').length >= {n0 + 1}", timeout=4500, label="tab a takes it back")
        except RuntimeError:
            pass
        res["takeBack"] = {"a": len(await a.evaluate("() => window.__shown")) - a0, "b": len(await b.evaluate("() => window.__shown")) - b0,
                           "within": round(await a.evaluate("() => performance.now()") - t0)}
        await wait(b, "() => window.__dbg.notifySeen().length >= " + str(len(await b.evaluate("() => window.__dbg.notifySeen()")) + 1), timeout=15000, label="tab b took it, late")
        res["takeBack"]["shown"] = len(await a.evaluate(SHOWN)) - n0
        res["takeBack"]["bAfter"] = len(await b.evaluate("() => window.__shown")) - b0
        check(failures, res["takeBack"]["a"] == 1 and res["takeBack"]["b"] == 0 and res["takeBack"]["shown"] == 1 and res["takeBack"]["bAfter"] == 0,
              f"the tab that said it can sound never took it: the other shows it once, after its wait: {res['takeBack']}")

        # 4. a reload rings nothing again — with the list of rung keys cleared first (a fresh profile), so it is the
        # page's own "nothing from before it was loaded" that holds, not the other tabs' record
        before = len(await a.evaluate(SHOWN))
        await a.evaluate("() => localStorage.removeItem('jui-viz-notify-rung')")
        await a.reload()
        await ready(a)
        await wait(a, "() => window.__dbg.notifySeen().length >= 1 || Object.keys(window.__dbg.robotState()).length >= 1", timeout=30000, label="reloaded")
        await wait(a, "() => window.__dbg.notifyBased()", timeout=20000, label="the first look after the reload")
        res["afterReload"] = [len(await a.evaluate(SHOWN)), len(await a.evaluate("() => window.__shown"))]
        res["afterReloadNew"] = (await a.evaluate(SHOWN))[before:]
        check(failures, res["afterReload"] == [before, 0], f"a reload rings nothing again: {res['afterReload']} (before {before})")

        # 5. a kind turned off in one tab rings from neither
        await b.click("#btn-notify")
        await b.uncheck("[data-notify-kind='done']")
        await b.keyboard.press("Escape")
        await wait(a, "() => window.__dbg.notifyOn().done === false", label="the switch reaches the other tab")
        n0 = len(await a.evaluate(SHOWN))
        seen5 = {name: await p.evaluate("() => window.__dbg.notifySeen()") for p, name in ((a, "a"), (b, "b"))}
        turn()
        # each tab has looked at this turn end: a done key it had not seen (after a reload the replayed keys are seen
        # already — waiting for "any other done key" let this event reach tab a later, once done was on again)
        for p, name in ((a, "a"), (b, "b")):
            await wait(p, "(before) => window.__dbg.notifySeen().some((k) => k.includes(':done:') && !before.includes(k))", arg=seen5[name],
                       label=f"the turn end with done off seen by tab {name}")
        res["offDone"] = len(await a.evaluate(SHOWN)) - n0
        check(failures, res["offDone"] == 0, f"a kind turned off rings from neither tab: {res['offDone']}")

        # 6. the question window: hidden with question notifications on, the question waits; turned off, it goes back
        await b.close()
        # 5b. quiet: the page in front, focused, showing that robot's card — no notification, no sound
        await a.bring_to_front()
        await a.evaluate("() => window.__dbg.notifySet({ done: true })")
        # the reloaded tab, never pressed: no context yet, and the settings say so
        await a.evaluate("() => window.__dbg.notifyPanel()")
        res["noContext"] = await a.evaluate("() => [window.__dbg.notifyAudio(), document.getElementById('notify-chime-note').textContent]")
        check(failures, res["noContext"][0] is None and T("panel.chime.none") in res["noContext"][1], f"a reloaded tab never pressed: no sound yet, and it says so: {res['noContext']}")
        await a.keyboard.press("Escape")
        await a.mouse.click(5, 880)   # wakes the reloaded tab's sound (a press), so a ring would sound
        await wait(a, "() => window.__dbg.notifyAudio() === 'running'", label="tab a's sound woken again")
        await a.evaluate("(id) => window.__dbg.openRobot(id)", rid)
        await wait(a, "(id) => window.__dbg.board().robot === id", arg=rid, label="the robot's card open")
        res["focus"] = await a.evaluate("() => [document.visibilityState, document.hasFocus()]")
        n0, c0 = len(await a.evaluate(SHOWN)), await a.evaluate(CHIMES)
        seen0 = await a.evaluate("() => window.__dbg.notifySeen()")
        turn()
        await wait(a, "(before) => window.__dbg.notifySeen().some((k) => k.includes(':done:') && !before.includes(k))", arg=seen0, label="the quiet turn end seen")
        res["quiet"] = [len(await a.evaluate(SHOWN)) - n0, await a.evaluate(CHIMES) - c0]
        check(failures, res["focus"] == ["visible", True] and res["quiet"] == [0, 0],
              f"quiet while that card is on screen: no notification, no sound: {res['quiet']} (visibility, focus {res['focus']})")
        await a.keyboard.press("Escape")
        await a.evaluate("() => { Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' }); document.dispatchEvent(new Event('visibilitychange')); }")
        await a.evaluate("() => window.__dbg.notifyPresenceSay()")
        hook(body(hook_event_name="PreToolUse", tool_name="AskUserQuestion", tool_use_id="ask-2", tool_input=Q))
        ask2 = hook(body(hook_event_name="PreToolUse", tool_name="AskUserQuestion", tool_use_id="ask-2", tool_input=Q), "--ask")
        await wait(a, "() => window.__dbg.questions().filter((q) => q.status === 'pending' && q.hookWaiting).length === 1",
                   label="hidden, notifications on: the question waits for the page")
        # the server asks a hidden page again only while its hook waits (askPingSec 1 here): two asks, still waiting
        p0 = await a.evaluate("() => window.__dbg.notifyPings()")
        await wait(a, f"() => window.__dbg.notifyPings() >= {p0 + 2}", label="the waiting hook asks the hidden page twice")
        res["hiddenHeld"] = ask2.poll() is None
        check(failures, res["hiddenHeld"], "hidden with notifications on: the hook still waits")
        await a.evaluate("() => { window.__dbg.notifySet({ ask: false }); }")
        try:
            ask2.wait(timeout=10)
            res["hiddenOff"] = "returned"
        except subprocess.TimeoutExpired:
            res["hiddenOff"] = "still waiting"
        check(failures, res["hiddenOff"] == "returned", f"notifications off on a hidden page: the question goes back at once: {res['hiddenOff']}")
        hidden_said = T("panel.q.end.hidden", at="\x00").split("\x00")[0]   # its words up to when
        await wait(a, f"() => document.body.textContent.includes({json.dumps(hidden_said)})", label="the card says why")
        res["reasons"] = await a.evaluate("() => window.__dbg.questions().map((q) => q.waitEndReason)")
        await a.evaluate("() => { delete document.visibilityState; document.dispatchEvent(new Event('visibilitychange')); }")

        # 7. the window chosen in the settings
        await a.click("#btn-notify")
        # ticket 2026-10-20: every window offered ends before the hook's timeout; "until answered" says its longest
        res["offered"] = await a.evaluate("() => [...document.querySelectorAll('#ask-wait option')].map((o) => [Number(o.value), o.textContent])")
        check(failures, [v for v, _ in res["offered"]] == [20, 60, 180, 600, 1800, 0],
              f"the offered windows: {res['offered']}")
        check(failures, any(v == 0 and t == T("panel.ask.until.most", most=T("panel.ask.hours", n=24)) for v, t in res["offered"]),
              f"until answered says how long at most: {res['offered']}")
        # the hook (forward.py --ask) reads how long to wait from server.json, rewritten on every choice
        await a.select_option("#ask-wait", "1800")
        await wait(a, f"() => document.getElementById('chip-askwait').textContent === {json.dumps(T('panel.ask.chip', wait=T('srv.ask.min', n='30')))}", label="the chip says 30 min")
        res["hookWait1800"] = json.loads((state / "server.json").read_text()).get("askHookWaitSec")
        check(failures, res["hookWait1800"] == 1800, f"30 min: server.json tells the hook 1800 s: {res['hookWait1800']}")
        await a.select_option("#ask-wait", "20")
        await wait(a, f"() => document.getElementById('chip-askwait').textContent === {json.dumps(T('panel.ask.chip', wait=T('srv.ask.sec', n=20)))}", label="the chip follows the choice")
        res["chip20"] = await a.evaluate("() => document.getElementById('chip-askwait').textContent")
        res["saved"] = json.loads((state / "config.json").read_text()).get("askWaitSec")
        check(failures, res["saved"] == 20, f"the choice is saved in config.json: {res['saved']}")
        res["hookWait20"] = json.loads((state / "server.json").read_text()).get("askHookWaitSec")
        check(failures, res["hookWait20"] == 300, f"20 s: the hook still waits askMaxSec for holds: {res['hookWait20']}")
        await a.screenshot(path=str(out / "settings-chosen-light.png"))
        await a.emulate_media(color_scheme="dark")
        await a.wait_for_timeout(600)
        await a.screenshot(path=str(out / "settings-chosen-dark.png"))
        for p in held:
            if p.poll() is None:
                p.kill()
                p.wait(timeout=10)
    finally:
        for p in held:
            if p.poll() is None:
                p.kill()
                p.wait(timeout=10)
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  notify: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "notify-results.json").write_text(dump(res) + "\n")
