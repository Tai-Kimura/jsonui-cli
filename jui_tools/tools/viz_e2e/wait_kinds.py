"""A robot waiting on the person, told apart in 3D (ticket 2026-10-20-jui-viz-3d-waiting-kinds-question-permission-input;
requester: 「今こっちの返答や許可待ちになってるbotが3dの見た目でもわかるようにしてほしい。質問、許可、入力待ちでそれぞれUI用意して」,
「ボットの頭に追加の吹き出し用意して、そこからボード遷移もできるといい」).

The real `jui viz serve` in a throwaway HOME and the real forward.py; four sessions in one room:

  perm   a Bash call waiting on its permission (PermissionRequest)
  ask    an AskUserQuestion of three choices
  input  a turn ended and nobody answered (Stop, then Notification idle_prompt)
  both   auto mode stopped a call (PermissionDenied), then the turn ended unanswered: a permission's and an input's wait

Checked: each robot's wait kind, lamp, pose and bubble (window.__dbg.waitLook) and the three differ; `both` shows the
permission's only (perm > ask > input); the room's window in the building goes input → asking → waiting as the waits
come; the bubble sits over the name tag, not on it, and its text is 4.5:1 on its ground in light and dark; a real
click on each bubble opens its card in the panel (the question's, the permission's, the stopped call's) or, for
input, the robot's card with its talk, after which the input bubble is gone (seen); a new idle_prompt brings it back
and the next prompt clears it. The lamp's colour is read from the robot itself (lampMat), so an older page without
waitLook still reports what its 3D showed.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, dump, new_page, ready
from waits import settled, until

CWD = "/work/wait-kinds-app"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
SID = {"perm": "e2e00000-0000-4000-8000-0000000005a1", "ask": "e2e00000-0000-4000-8000-0000000005a2",
       "input": "e2e00000-0000-4000-8000-0000000005a3", "both": "e2e00000-0000-4000-8000-0000000005a4"}
QUESTION = {"questions": [{"question": "どの色にしますか？", "header": "色", "multiSelect": False,
                           "options": [{"label": "赤", "description": "a"}, {"label": "青", "description": "b"}, {"label": "緑", "description": "c"}]}]}
IDLE = {"hook_event_name": "Notification", "notification_type": "idle_prompt", "message": "Claude is waiting for your input"}

# What 3D shows of robot `id`: the lamp read off the robot (any version), and waitLook where the page has it.
LOOK_JS = """(id) => { const R = window.__dbg.robots.find((x) => x.def.id === id); if (!R) return null;
  const w = window.__dbg.waitLook ? window.__dbg.waitLook(id) : null;
  return { state: R.robot.state, lampHex: '#' + R.robot.lampMat.color.getHexString(), kind: w ? w.kind : null, lamp: w ? w.lamp : null,
    pose: w ? w.pose : null, bubble: w ? w.bubble : null, shown: w ? w.bubbleShown : false,
    bubbles: document.querySelectorAll('[data-wait-robot]').length }; }"""
# The bubble of robot `id` and its name tag on the page: boxes, the colours of its text and ground.
BOX_JS = """(id) => { const R = window.__dbg.robots.find((x) => x.def.id === id); const b = R && R.waitEl; if (!b || b.hidden) return null;
  const r = b.getBoundingClientRect(), t = R.tag.getBoundingClientRect(), cs = getComputedStyle(b);
  const at = document.elementFromPoint((r.left + r.right) / 2, (r.top + r.bottom) / 2);
  return { bubble: [r.left, r.top, r.right, r.bottom], tag: [t.left, t.top, t.right, t.bottom], fg: cs.color, bg: cs.backgroundColor,
    onTop: !!at && (at === b || b.contains(at)), cursor: cs.cursor }; }"""
CARD_JS = """() => { const rb = document.getElementById('rb');
  return { robot: window.__dbg.board().robot, open: !!rb && !rb.hidden, talk: window.__dbg.talk().on, picked: window.__dbg.waitPicked ? window.__dbg.waitPicked() : null }; }"""


def check(failures, cond, text):
    if not cond:
        failures.append(f"wait-kinds: {text}")


def _lum(rgb: str) -> float:
    vals = [int(float(x)) for x in rgb[rgb.index("(") + 1:rgb.index(")")].split(",")[:3]]
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in vals)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: str, bg: str) -> float:
    a, b = sorted((_lum(fg), _lum(bg)), reverse=True)
    return round((a + 0.05) / (b + 0.05), 2)


async def run_wait_kinds(pw, out, failures, jt=None):
    from run import free_port
    name = "wait-kinds"
    out = pathlib.Path(out) / name
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    jt = pathlib.Path(jt) if jt else pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT,
                           env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"
    res: dict = {"looks": {}, "tower": {}, "boxes": {}, "press": {}}

    def hook(k, **payload):
        body = {"session_id": SID[k], "cwd": CWD, "transcript_path": f"{home}/t-{k}.jsonl", "permission_mode": "default", **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(), capture_output=True,
                       env=dict(base_env, HOME=str(home)), timeout=10)

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
        page = await new_page(browser, watch, name, **DESKTOP)
        await page.emulate_media(color_scheme="light", reduced_motion="no-preference")
        await page.goto(url + "/")
        await ready(page)
        await until(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", "connected")
        for k in SID:
            hook(k, hook_event_name="SessionStart", source="startup")
        await until(page, "() => window.__dbg.robots.length >= 4", "four robots", timeout=40000, why="() => window.__dbg.settleInfo()")
        ids = await page.evaluate("() => Object.fromEntries(window.__dbg.robots.map((R) => [R.def.sessionId, R.def.id]))")
        rid = {k: ids[SID[k]] for k in SID}
        res["ids"] = rid
        room = await page.evaluate("(id) => window.__dbg.robots.find((R) => R.def.id === id).def.room", rid["perm"])
        tower = "(room) => window.__dbg.towerStateOf ? window.__dbg.towerStateOf(room) : null"

        async def look(k):
            return await page.evaluate(LOOK_JS, rid[k])

        # input first: the turn's end, then idle_prompt 60 s later in real life
        hook("input", hook_event_name="UserPromptSubmit", prompt="go")
        hook("input", hook_event_name="Stop")
        hook("input", **IDLE)
        await until(page, "(id) => (window.__dbg.robotState()[id] || {}).state === 'idle'", "input: its robot idle after the turn", arg=rid["input"])
        await until(page, "(id) => { const w = window.__dbg.waitLook && window.__dbg.waitLook(id); return !window.__dbg.waitLook || (w && w.kind === 'input'); }",
                    "input: its wait", arg=rid["input"], timeout=15000, why="(id) => window.__dbg.waitLook && window.__dbg.waitLook(id)")
        res["tower"]["input"] = await page.evaluate(tower, room)
        check(failures, res["tower"]["input"] == "input", f"the room's window with an input's wait only: input: {res['tower']['input']}")

        hook("ask", hook_event_name="UserPromptSubmit", prompt="ask me")
        hook("ask", hook_event_name="PreToolUse", tool_name="AskUserQuestion", tool_use_id="toolu_ask1", tool_input=QUESTION)
        await until(page, "(id) => (window.__dbg.robotState()[id] || {}).state === 'waiting'", "ask: its robot waits", arg=rid["ask"])
        res["tower"]["ask"] = await page.evaluate(tower, room)
        check(failures, res["tower"]["ask"] == "asking", f"the room's window with a question's wait (and an input's): asking: {res['tower']['ask']}")

        hook("perm", hook_event_name="UserPromptSubmit", prompt="build")
        hook("perm", hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="toolu_perm1", tool_input={"command": "make clean"})
        hook("perm", hook_event_name="PermissionRequest", tool_name="Bash", tool_input={"command": "make clean"})
        hook("both", hook_event_name="UserPromptSubmit", prompt="deploy", permission_mode="auto")
        hook("both", hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="toolu_den1", tool_input={"command": "rm -rf build"}, permission_mode="auto")
        hook("both", hook_event_name="PermissionDenied", tool_name="Bash", tool_use_id="toolu_den1", tool_input={"command": "rm -rf build"},
             reason="destructive", permission_mode="auto")
        hook("both", hook_event_name="Stop", permission_mode="auto")
        hook("both", **IDLE, permission_mode="auto")
        await until(page, "(id) => (window.__dbg.robotState()[id] || {}).state === 'waiting'", "perm: its robot waits", arg=rid["perm"])
        # idle after its turn's 完了 (3 s), not the idle of the denial before it (act 拒否 …)
        await until(page, "(id) => { const s = window.__dbg.robotState()[id] || {}; return s.state === 'idle' && !String(s.act || '').startsWith('拒否'); }",
                    "both: its robot idle after the turn", arg=rid["both"], timeout=15000, why="(id) => window.__dbg.robotState()[id]")
        await until(page, "() => document.querySelectorAll('[data-dcard]').length >= 1", "the stopped call's card", timeout=15000)
        res["tower"]["perm"] = await page.evaluate(tower, room)
        check(failures, res["tower"]["perm"] == "waiting", f"the room's window with a permission's wait (and the others): waiting: {res['tower']['perm']}")
        await settled(page, "the four at their desks")
        for k in SID:
            res["looks"][k] = await look(k)
        L = res["looks"]
        want = {"perm": ("perm", "waiting", "waiting", "!"), "ask": ("ask", "asking", "asking", "? 3"),
                "input": ("input", "idle", "leanBack", "…"), "both": ("perm", "idle", "idle", "!")}
        for k, (kind, lamp, pose, bubble) in want.items():
            got = (L[k]["kind"], L[k]["lamp"], L[k]["pose"], L[k]["bubble"])
            check(failures, got == (kind, lamp, pose, bubble), f"{k}: (wait kind, lamp, pose, bubble) is {(kind, lamp, pose, bubble)}: {got}")
            check(failures, L[k]["shown"], f"{k}: its bubble is on screen: {L[k]}")
        check(failures, L["perm"]["lampHex"] != L["ask"]["lampHex"], f"a question's lamp is not a permission's: {L['perm']['lampHex']} / {L['ask']['lampHex']}")
        check(failures, len({L[k]["bubble"] for k in ("perm", "ask", "input")}) == 3 and len({L[k]["pose"] for k in ("perm", "ask", "input")}) == 3,
              f"the three waits differ in bubble and pose: {L}")

        # the bubble over the tag, not on it; its text 4.5:1 on its ground, light and dark
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await settled(page, f"{scheme}: tags at their spots")
            res["boxes"][scheme] = {}
            for k in ("perm", "ask", "input"):
                b = await page.evaluate(BOX_JS, rid[k])
                res["boxes"][scheme][k] = b
                if not b:
                    check(failures, False, f"{scheme} {k}: no bubble")
                    continue
                b["contrast"] = contrast(b["fg"], b["bg"])
                check(failures, b["contrast"] >= 4.5, f"{scheme} {k}: the bubble's text 4.5:1 on its ground: {b['contrast']}")
                check(failures, b["bubble"][3] <= b["tag"][1] + 0.5, f"{scheme} {k}: the bubble above its name tag, not on it: {b['bubble']} / {b['tag']}")
                check(failures, b["onTop"] and b["cursor"] == "pointer", f"{scheme} {k}: the bubble takes a press (on top, a pointer): {b}")
            await page.screenshot(path=str(out / f"wait-kinds-{scheme}.png"))
        await page.emulate_media(color_scheme="light")

        # a real click on each bubble: its card in the panel
        async def press(k):
            await settled(page, f"{k}: before the press")
            await page.click(f"[data-wait-robot='{rid[k]}']")
            return await until(page, f"() => {{ const c = ({CARD_JS})(); return c.picked && c.picked.id === '{rid[k]}' ? c : null; }}",
                               f"{k}: the press picked its card", timeout=10000, why=CARD_JS)
        # the robot's card names the lamp and shows its colour: the question's violet, both (the independent verification)
        swatch = {}
        for k, name in (("perm", "黄（許可待ち）"), ("ask", "紫（質問に回答待ち）")):
            await page.evaluate("(id) => window.__dbg.openRobot(id)", rid[k])
            await until(page, "(id) => window.__dbg.board().robot === id", f"{k}: its card", arg=rid[k])
            # the card is filled after it opens: its lamp's name first, then the swatch read
            await until(page, "(t) => { const n = document.querySelector('#rb [data-rb-lampname]'); return !!n && n.textContent === t; }",
                        f"{k}: its card names the lamp", arg=name, timeout=10000,
                        why="() => { const n = document.querySelector('#rb [data-rb-lampname]'); return n ? n.textContent : null; }")
            swatch[k] = await page.evaluate("""() => { const l = document.querySelector('#rb [data-rb-lamp]'), n = document.querySelector('#rb [data-rb-lampname]');
              return [l ? getComputedStyle(l).backgroundColor : null, n ? n.textContent : null]; }""")
            await page.click("#rb-close")
            await until(page, "() => !window.__dbg.board().robot", f"{k}: its card closed")
        res["swatch"] = swatch
        check(failures, swatch["ask"] == ["rgb(180, 140, 255)", "紫（質問に回答待ち）"] and swatch["perm"] == ["rgb(255, 176, 32)", "黄（許可待ち）"],
              f"the card's lamp swatch is the colour its name says: {swatch}")
        c = await press("ask")
        q = await page.evaluate("(id) => { const e = document.querySelector('.wait-picked'); return e ? [e.dataset.qcard || null, document.activeElement && e.contains(document.activeElement)] : null; }", rid["ask"])
        res["press"]["ask"] = {"card": c, "el": q}
        check(failures, c["picked"]["kind"] == "ask" and c["picked"]["found"] and q and q[0] and q[1] and not c["open"],
              f"ask: the bubble opens the question's card (picked, focused), not the robot's card: {res['press']['ask']}")
        c = await press("perm")
        res["press"]["perm"] = c
        check(failures, c["picked"]["kind"] == "perm" and c["picked"]["found"] and str(c["picked"]["card"]).startswith("perm:"),
              f"perm: the bubble opens the permission's card: {c}")
        c = await press("both")
        res["press"]["both"] = c
        check(failures, c["picked"]["kind"] == "perm" and c["picked"]["found"] and str(c["picked"]["card"]).startswith("denied:"),
              f"both: the bubble opens the stopped call's card: {c}")
        c = await press("input")
        res["press"]["input"] = c
        check(failures, c["picked"]["kind"] == "input" and c["robot"] == rid["input"] and c["open"] and c["talk"],
              f"input: the bubble opens the robot's card with its talk: {c}")
        await page.click("#rb-close")
        await until(page, "() => !window.__dbg.board().robot", "the card closed")
        after = await look("input")
        res["looks"]["inputSeen"] = after
        check(failures, after["kind"] is None and after["bubble"] is None, f"input: seen on the page, its bubble gone: {after}")

        # a new idle_prompt brings it back; the next prompt clears it
        hook("input", hook_event_name="UserPromptSubmit", prompt="again")
        hook("input", hook_event_name="Stop")
        hook("input", **IDLE)
        back = await until(page, "(id) => { const w = window.__dbg.waitLook(id); return w && w.kind === 'input' ? w : null; }",
                           "input: a new idle_prompt brings its bubble back", arg=rid["input"], timeout=15000,
                           why="(id) => window.__dbg.waitLook(id)")
        res["looks"]["inputAgain"] = back
        hook("input", hook_event_name="UserPromptSubmit", prompt="next")
        gone = await until(page, "(id) => { const w = window.__dbg.waitLook(id); return w && w.kind === null ? w : null; }",
                           "input: the next prompt clears it", arg=rid["input"], timeout=15000, why="(id) => window.__dbg.waitLook(id)")
        res["looks"]["inputNextPrompt"] = gone
    finally:
        (out / "wait-kinds-results.json").write_text(dump(res) + "\n")   # also when the suite stopped
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  wait-kinds: {time.monotonic() - t0:.0f}s", flush=True)
    from run import check_watch
    check_watch(watch, name, failures)
