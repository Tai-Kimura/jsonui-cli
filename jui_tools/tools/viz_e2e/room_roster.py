"""The room's robot list (ticket 2026-10-23-viz-room-robot-list-show-hide; requester: 「botが多くなると全体が見づらいので部屋の中の時は
3dの右側にbotの名前とチェックを表示してチェックしてないbotは消して欲しい。」).

The real `jui viz serve` in a throwaway HOME and the real forward.py; nine sessions in one room. Checked, from the page
(window.__dbg.roster) and the 3D (each robot's root, so its desk, and its tag):

  - in the room's view the list is there, a row per session with its number and name; on the floor it is not;
  - a robot unchecked leaves the 3D with its desk and tag, the others stay; checked again it is back;
  - the check is kept per room in this browser: a reload brings the same robots back hidden;
  - a hidden robot that comes to wait on the person (a permission) marks its row, and the list's head says so;
  - なし hides all, 全部 brings all back, 作業中だけ keeps the busy and the waiting only;
  - a session new to the room comes in shown;
  - the list keeps off the room's name box, inside the 3D, at 1920, 1440 and 390 px wide; with a robot's card open on a
    wide page it sits left of the card.
Stills for the requester: all shown and some hidden, at each width.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import LAUNCH_ARGS, PHONE, Watch, new_page, ready
from waits import until

CWD = "/work/roster-app"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
N = 9
# each its own first letter, so the numbers the page gives them are short ones (the last one comes later)
SID = [f"{c}0e20000-0000-4000-8000-{0x7000 + i:012x}" for i, c in enumerate("123456789a")]
RO = "() => window.__dbg.roster()"
WIDE = {"viewport": {"width": 1920, "height": 1080}, "device_scale_factor": 1}
MID = {"viewport": {"width": 1440, "height": 900}, "device_scale_factor": 1}


def check(failures, cond, text):
    if not cond:
        failures.append(f"room-roster: {text}")


def _apart(a, b):
    """Two page boxes [l, t, r, b] that do not overlap (a missing one overlaps nothing)."""
    return not a or not b or a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]


def _inside(a, b):
    return bool(a) and bool(b) and a[0] >= b[0] - 1 and a[1] >= b[1] - 1 and a[2] <= b[2] + 1 and a[3] <= b[3] + 1


async def run_room_roster(pw, out, failures, jt=None):
    from run import free_port
    name = "room-roster"
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
    res: dict = {}

    def hook(i, **payload):
        body = {"session_id": SID[i], "cwd": CWD, "transcript_path": f"{home}/t-{i}.jsonl", "permission_mode": "default", **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(), capture_output=True,
                       env=dict(base_env, HOME=str(home)), timeout=10)

    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    t0 = time.monotonic()
    try:
        import urllib.request
        for _ in range(400):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        context = await browser.new_context(**WIDE)   # one context: the reload keeps this browser's storage
        watch = Watch(origin=url)
        page = await new_page(context, watch, name)
        await page.emulate_media(color_scheme="light", reduced_motion="reduce")
        await page.goto(url + "/")
        await ready(page)
        await until(page, "() => document.querySelector('.chip.demo').dataset.net === 'connected'", "connected")
        for i in range(N):
            hook(i, hook_event_name="SessionStart", source="startup")
        await until(page, f"() => window.__dbg.robots.length >= {N}", f"{N} robots", timeout=40000, why="() => window.__dbg.settleInfo()")
        ids = await page.evaluate("() => Object.fromEntries(window.__dbg.robots.map((R) => [R.def.sessionId, R.def.id]))")
        rid = [ids[s] for s in SID[:N]]
        room = await page.evaluate("(id) => window.__dbg.robots.find((R) => R.def.id === id).def.room", rid[0])
        # two at work, each with a call running (作業中だけ keeps these); a prompt alone leaves a robot idle
        hook(1, hook_event_name="UserPromptSubmit", prompt="build")
        hook(1, hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="toolu_b1", tool_input={"command": "make"})
        hook(2, hook_event_name="UserPromptSubmit", prompt="read")
        hook(2, hook_event_name="PreToolUse", tool_name="Read", tool_use_id="toolu_r2", tool_input={"file_path": "/work/roster-app/README.md"})

        # 0. on the floor: no list
        s = res["floor"] = await page.evaluate(RO)
        check(failures, not s["shown"], f"on the floor the list is not shown: {s['shown']}")

        async def enter():
            await page.click(f".tag.room[data-set-project='{room}']")
            await until(page, f"() => window.__dbg.solo() === '{room}'", "the room's view")
            await until(page, f"() => window.__dbg.roster().rows.length >= {N}", "a row per session", timeout=15000, why=RO)
        await enter()
        s = res["all"] = await page.evaluate(RO)
        check(failures, s["shown"] and [r["id"] for r in s["rows"]] == sorted(rid, key=lambda x: (len(x), x)) and all(r["on"] for r in s["rows"]) and all(r["name"] for r in s["rows"]),
              f"in the room: a checked row per session, with its name: {s['rows']}")
        check(failures, all(b["root"] for b in s["bots"]), f"all shown at first: {s['bots']}")
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(out / "1920-all.png"))

        def bot(st, i):
            return next(b for b in st["bots"] if b["id"] == rid[i])

        # 1. three unchecked: gone from the 3D with desk and tag, the rest stay
        for i in (0, 3, 4):
            await page.click(f"#roster-list [data-roster-check='{SID[i]}']")
        s = res["three"] = await until(page, "() => { const s = window.__dbg.roster(); return s.bots.filter((b) => !b.root).length === 3 ? s : null; }", "three hidden", timeout=5000, why=RO)
        hidden = {rid[i] for i in (0, 3, 4)}
        check(failures, all((not b["root"]) == (b["id"] in hidden) for b in s["bots"]) and all(b["tag"] == "hidden" for b in s["bots"] if b["id"] in hidden),
              f"the unchecked leave the 3D (root, so desk) and their tags; the rest stay: {s['bots']}")
        check(failures, [r["on"] for r in s["rows"] if r["id"] in hidden] == [False] * 3 and s["count"] == f"{N - 3} / {N}", f"their rows unchecked, the head counts: {s['count']}")
        check(failures, sorted(json.loads(s["saved"] or "[]")) == sorted(SID[i] for i in (0, 3, 4)), f"kept in this browser for the room: {s['saved']}")
        await page.wait_for_timeout(400)
        await page.screenshot(path=str(out / "1920-some-hidden.png"))

        # 2. one of them comes to wait on a permission: its row is marked, the head says so
        hook(3, hook_event_name="UserPromptSubmit", prompt="clean")
        hook(3, hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="toolu_p3", tool_input={"command": "make clean"})
        hook(3, hook_event_name="PermissionRequest", tool_name="Bash", tool_input={"command": "make clean"})
        s = res["waiting"] = await until(page, f"() => {{ const s = window.__dbg.roster(); const r = s.rows.find((x) => x.id === '{rid[3]}'); return r && r.alert ? s : null; }}",
                                         "the hidden robot's wait marked", timeout=15000, why=RO)
        row = next(r for r in s["rows"] if r["id"] == rid[3])
        check(failures, row["alert"] and row["wait"] == "perm" and not bot(s, 3)["root"] and s["alert"], f"a hidden robot waiting: its row marked, the head says it, it stays hidden: {row} {s['alert']}")
        check(failures, not any(r["alert"] for r in s["rows"] if r["id"] != rid[3]), f"only its row is marked: {s['rows']}")
        await page.screenshot(path=str(out / "1920-hidden-waiting.png"))

        # 3. kept: a reload, the room again, the same three hidden
        await page.reload()
        await ready(page)
        await until(page, f"() => window.__dbg.robots.length >= {N}", "robots after the reload", timeout=40000)
        if await page.evaluate("() => window.__dbg.solo()") != room:
            await enter()
        s = res["reload"] = await until(page, "() => { const s = window.__dbg.roster(); return s.rows.length && s.bots.filter((b) => !b.root).length === 3 ? s : null; }",
                                        "the same three hidden after a reload", timeout=15000, why=RO)
        check(failures, {b["id"] for b in s["bots"] if not b["root"]} == hidden and {r["id"] for r in s["rows"] if not r["on"]} == hidden, f"a reload keeps them hidden: {s['rows']}")

        # 4. checked again: back
        await page.click(f"#roster-list [data-roster-check='{SID[0]}']")
        s = res["back"] = await until(page, f"() => {{ const s = window.__dbg.roster(); const b = s.bots.find((x) => x.id === '{rid[0]}'); return b && b.root ? s : null; }}",
                                      "checked again: back", timeout=5000, why=RO)
        check(failures, bot(s, 0)["root"] and not bot(s, 3)["root"] and not bot(s, 4)["root"], f"checked again, it is back; the others stay hidden: {s['bots']}")

        # 5. at once: なし, 作業中だけ, 全部
        await page.click("[data-roster-bulk='none']")
        s = res["none"] = await until(page, "() => { const s = window.__dbg.roster(); return s.bots.every((b) => !b.root) ? s : null; }", "none shown", timeout=5000, why=RO)
        check(failures, not any(r["on"] for r in s["rows"]), f"なし: all unchecked: {s['rows']}")
        await page.click("[data-roster-bulk='busy']")
        busy = {rid[1], rid[2], rid[3]}
        s = res["busy"] = await until(page, "() => { const s = window.__dbg.roster(); return s.bots.some((b) => b.root) ? s : null; }", "the busy shown", timeout=5000, why=RO)
        check(failures, {b["id"] for b in s["bots"] if b["root"]} == busy, f"作業中だけ: the working and the waiting ({sorted(busy)}): {[(b['id'], b['root']) for b in s['bots']]}")
        await page.click("[data-roster-bulk='all']")
        s = res["allAgain"] = await until(page, "() => { const s = window.__dbg.roster(); return s.bots.every((b) => b.root) ? s : null; }", "all shown again", timeout=5000, why=RO)
        check(failures, all(r["on"] for r in s["rows"]) and json.loads(s["saved"] or "[]") == [], f"全部: all checked, nothing kept hidden: {s['saved']}")

        # 6. a new session in the room comes in shown, while others are hidden
        await page.click(f"#roster-list [data-roster-check='{SID[5]}']")
        hook(N, hook_event_name="SessionStart", source="startup")
        s = res["newcomer"] = await until(page, f"() => {{ const s = window.__dbg.roster(); return s.rows.length >= {N + 1} ? s : null; }}", "the newcomer's row", timeout=20000, why=RO)
        new = next(r for r in s["rows"] if r["key"] == SID[N])
        check(failures, new["on"] and next(b for b in s["bots"] if b["sid"] == SID[N])["root"], f"a newcomer is shown: {new}")
        await page.click("[data-roster-bulk='all']")

        # 7. the place on the page: off the name box, inside the 3D; left of a robot's card on a wide page
        for i in (0, 3):
            await page.click(f"#roster-list [data-roster-check='{SID[i]}']")
        await page.wait_for_timeout(400)
        s = res["place1920"] = await page.evaluate(RO)
        check(failures, _apart(s["rect"], s["soloBox"]) and _apart(s["rect"], s["err"]) and _inside(s["rect"], s["scene"]),
              f"1920: the list off the name box and the source's error line, inside the 3D: {s['rect']} {s['soloBox']} {s['err']} {s['scene']}")
        await page.click(f"#roster-list [data-roster-open='{rid[1]}']")
        s = res["card1920"] = await until(page, "() => { const s = window.__dbg.roster(); return s.card ? s : null; }", "a robot's card", timeout=8000, why=RO)
        await page.wait_for_timeout(400)
        s = res["card1920"] = await page.evaluate(RO)
        check(failures, _apart(s["rect"], s["card"]) and _inside(s["rect"], s["scene"]), f"1920 with a card open: the list beside it: {s['rect']} {s['card']}")
        await page.screenshot(path=str(out / "1920-card.png"))
        await page.keyboard.press("Escape")
        await page.set_viewport_size(MID["viewport"])
        await page.wait_for_timeout(500)
        s = res["place1440"] = await page.evaluate(RO)
        check(failures, s["shown"] and _apart(s["rect"], s["soloBox"]) and _apart(s["rect"], s["err"]) and _inside(s["rect"], s["scene"]),
              f"1440: off the name box and the error line, inside the 3D: {s['rect']} {s['soloBox']} {s['err']} {s['scene']}")
        await page.screenshot(path=str(out / "1440-some-hidden.png"))
        await page.click("[data-roster-bulk='all']")
        await page.wait_for_timeout(300)
        await page.screenshot(path=str(out / "1440-all.png"))

        phone = await new_page(browser, Watch(origin=url), f"{name}-phone", **PHONE)
        await phone.goto(url + "/")
        await ready(phone)
        await until(phone, f"() => window.__dbg.robots.length >= {N}", "robots on the phone", timeout=40000)
        await phone.evaluate("(id) => window.__dbg.setProject(id)", room)
        await until(phone, "() => window.__dbg.roster().shown", "the list on the phone", timeout=10000)
        await phone.wait_for_timeout(500)
        s = res["fold390"] = await phone.evaluate(RO)
        check(failures, s["folded"] and s["rect"] and s["rect"][3] - s["rect"][1] < 60 and _apart(s["rect"], s["soloBox"]) and _inside(s["rect"], s["scene"]),
              f"390: opens folded to its head, off the name box, inside the 3D: {s['rect']} {s['soloBox']} {s['scene']}")
        await phone.screenshot(path=str(out / "390-folded.png"))
        await phone.click("#roster-fold")
        await phone.wait_for_timeout(300)
        s = res["place390"] = await phone.evaluate(RO)
        check(failures, not s["folded"] and _apart(s["rect"], s["soloBox"]) and _inside(s["rect"], s["scene"]), f"390 opened: off the name box, inside the 3D: {s['rect']} {s['soloBox']} {s['scene']}")
        await phone.screenshot(path=str(out / "390-open.png"))
        res["seconds"] = round(time.monotonic() - t0, 1)
    finally:
        await browser.close()
        srv.send_signal(2)
        try:
            srv.wait(10)
        except subprocess.TimeoutExpired:
            srv.kill()
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
