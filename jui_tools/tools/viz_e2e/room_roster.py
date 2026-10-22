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
  - a subagent follows its main session's check, and its wait alone marks the main's row;
  - a robot's spirit's bubble goes with it; a game it plays ends for its partner too;
  - every board drawn over the 3D (the whiteboard, the task board, the bills, the data server, the server room) hides
    the list while it is open, the header's waiting chip staying; closed, the list is back;
  - the list lies on no control of the page (the floor buttons, the name box, a robot's card...) and keeps off the
    source's error line, inside the 3D, at 1920, 1440, 1280, 1024 and 390 px wide: seven sessions in other folders
    make eight rooms, two floors, so the floor buttons are up in the room's view as on a real machine (the gate,
    10-23: the list's fold button lay on them).
Stills for the requester: all shown and some hidden, at each width.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

from common import LAUNCH_ARGS, PHONE, Watch, new_page, ready
from data_server import _room
from server_room import _examples, _write
from waits import until

SUB = "agent-roster-sub-1"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
N = 9
# each its own first letter, so the numbers the page gives them are short ones (the last one comes later)
SID = [f"{c}0e20000-0000-4000-8000-{0x7000 + i:012x}" for i, c in enumerate("123456789a")]
OTHER = [f"b{i}e20000-0000-4000-8000-{0x7100 + i:012x}" for i in range(7)]   # one session each in seven other folders
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
    # a real folder: an API and a database to read (the data server's rack), a model of servers (the server room's door)
    CWD = home / "work" / "roster-app"
    _room(CWD, True)
    _write(home / "work", _examples(jt), "aws-three-tier", "roster-app")
    # a spirit with a bubble for code-review, always: the two bundled spirits are drawn by weight and gear-giant has no
    # bubble, so half the runs had none to look at (the gate, 10-23). A model naming the skill is the one taken
    # (spiritPick); the person's own models live here (as spirits.py makes them)
    own = home / ".local" / "state" / "jui-viz" / "spirits" / "scholar"
    shutil.copytree(jt / "jui_cli" / "viz" / "web" / "spirits" / "ink-scholar", own)
    spec = json.loads((own / "spirit.json").read_text(encoding="utf-8"))
    spec["skills"] = ["code-review"]
    (own / "spirit.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    # the sources' error line down: the session files' folder there, and an adb that sees no device. The line holds the
    # 3D's top right, as the floor buttons do, and taller: up, keeping off it kept the list off them too, and the arm for
    # the floor buttons proved nothing (the gate met them with the line down). It is brought up later for its own arm.
    (home / ".claude" / "sessions").mkdir(parents=True, exist_ok=True)
    adb = home / "Library" / "Android" / "sdk" / "platform-tools" / "adb"
    adb.parent.mkdir(parents=True, exist_ok=True)
    adb.write_text("#!/bin/sh\nprintf 'List of devices attached\\n\\n'\n")
    adb.chmod(0o755)
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT,
                           env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def hook(i, **payload):
        body = {"session_id": SID[i], "cwd": str(CWD), "transcript_path": f"{home}/t-{i}.jsonl", "permission_mode": "default", **payload}
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
        await page.emulate_media(color_scheme="light", reduced_motion="no-preference")   # a game starts only with motion
        await page.goto(url + "/")
        await ready(page)
        await until(page, "() => document.querySelector('.chip.demo').dataset.net === 'connected'", "connected")
        for i in range(N):
            hook(i, hook_event_name="SessionStart", source="startup")
        for i, sid in enumerate(OTHER):
            body = {"session_id": sid, "cwd": f"/work/roster-other-{i}", "transcript_path": f"{home}/o-{i}.jsonl", "permission_mode": "default",
                    "hook_event_name": "SessionStart", "source": "startup"}
            subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(), capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)
        # the room's robots (a robot is built for the floor drawn only: the other folders' may be on another floor), and the
        # building on two floors
        await until(page, f"(sids) => sids.every((s) => window.__dbg.robots.some((R) => R.def.sessionId === s)) && window.__dbg.floors().floors.length >= 2",
                    f"{N} robots, two floors", arg=SID[:N], timeout=60000, why="() => ({ floors: window.__dbg.floors(), settle: window.__dbg.settleInfo() })")
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

        async def enter():   # as the project menu does: the room may be on another floor than the one shown
            await page.evaluate("(id) => window.__dbg.setProject(id)", room)
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

        # 2b. a board over the 3D hides the list (requester 10-23: 「ボード出してる時はbotの切り替えの表示も消していいよ」); closed,
        # it is back; the header's chip still says a robot waits
        # the bills: the settings' 単価 button (the header's chip shows only while a model has no price)
        OPEN = {"wb": "#btn-specboard", "tb": "#chip-perm", "pr": "() => { const b = document.getElementById('prices-open'); if (!b) return false; b.click(); return true; }",
                "ds": "() => window.__dbg.pressRack()", "sr": f"() => window.__dbg.srEnter('{room}')",
                # the page-wide dialogs (aria-modal): the full-screen log, the room's call
                "log-overlay": "#btn-log", "call": "#room-call"}
        await until(page, "() => window.__dbg.props && window.__dbg.props().uses.dataServer && window.__dbg.sr().door", "the room's rack and door", timeout=20000,
                    why="() => ({ props: window.__dbg.props && window.__dbg.props(), sr: window.__dbg.sr() })")
        for board, opener in OPEN.items():
            if opener.startswith("#"):
                await page.click(opener)
            else:
                check(failures, await page.evaluate(opener) is not False, f"{board}: opened")
            await until(page, f"() => !document.getElementById('{board}').hidden", f"the {board} board open", timeout=20000)
            s = res[f"board-{board}"] = await until(page, "() => { const s = window.__dbg.roster(); return s.shown ? null : s; }", f"the list hidden under {board}", timeout=5000, why=RO)
            check(failures, not s["shown"] and s["permChip"], f"{board} open: the list hidden, the header still says a robot waits: {s['shown']} {s['permChip']}")
            if board == "wb":
                await page.screenshot(path=str(out / "1920-board.png"))
            await page.keyboard.press("Escape")
            s = res[f"board-{board}-closed"] = await until(page, "() => { const s = window.__dbg.roster(); return s.shown ? s : null; }", f"the list back after {board}", timeout=8000, why=RO)
            check(failures, s["shown"] and len(s["rows"]) == N, f"{board} closed: the list back: {s['shown']}")

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

        # 6b. a subagent: hidden with its main; its wait alone marks the main's row
        hook(5, hook_event_name="SubagentStart", agent_id=SUB, agent_type="general-purpose")
        await until(page, f"() => window.__dbg.roster().bots.some((b) => b.main === '{rid[5]}')", "the subagent in the room", timeout=20000, why=RO)
        await page.click(f"#roster-list [data-roster-check='{SID[5]}']")
        s = res["subHidden"] = await until(page, f"() => {{ const s = window.__dbg.roster(); const b = s.bots.filter((x) => x.id === '{rid[5]}' || x.main === '{rid[5]}'); return b.length === 2 && b.every((x) => !x.root) ? s : null; }}",
                                           "the main and its subagent hidden", timeout=5000, why=RO)
        check(failures, not next(r for r in s["rows"] if r["id"] == rid[5])["alert"], f"hidden, not waiting: no mark yet: {s['rows']}")
        sub_in = {"command": "rm -rf build"}
        hook(5, hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="toolu_sub5", tool_input=sub_in, agent_id=SUB, agent_type="general-purpose")
        hook(5, hook_event_name="PermissionRequest", tool_name="Bash", tool_input=sub_in, agent_id=SUB, agent_type="general-purpose")
        s = res["subWaiting"] = await until(page, f"() => {{ const s = window.__dbg.roster(); const r = s.rows.find((x) => x.id === '{rid[5]}'); return r && r.alert ? s : null; }}",
                                            "the subagent's wait marks its main's row", timeout=15000, why=RO)
        row = next(r for r in s["rows"] if r["id"] == rid[5])
        check(failures, row["alert"] and row["wait"] == "perm" and all(not b["root"] for b in s["bots"] if b["id"] == rid[5] or b["main"] == rid[5]),
              f"a hidden main's subagent waiting: the main's row marked, both still hidden: {row}")
        idle_lamp = next(r["lamp"] for r in s["rows"] if r["id"] == rid[7])   # an idle main's lamp, as the page draws it
        check(failures, row["lamp"] == idle_lamp, f"the row is the main's: its own lamp (idle), the subagent's wait marked beside it: {row['lamp']} vs idle {idle_lamp}")
        await page.click(f"#roster-list [data-roster-check='{SID[5]}']")

        # 6c. a spirit's bubble: placed hidden while its robot is hidden, and its time runs from the frame it is first drawn
        # (the gate, 10-23: it ran from the spirit standing, so a bubble that could not be drawn then - its robot hidden,
        # the spirit far or off the page - was gone before anyone saw it). The model read is slowed (3 s, a loaded machine),
        # the robot hidden, the skill called; the spirit stands and 5 s pass, more than a bubble's 4; shown again, the
        # bubble must be drawn, and stay about 4 s from then. Every write the page makes to the bubble is kept with its
        # time (a MutationObserver on the tags), so the arm reads what was drawn, not a sample of it.
        await page.evaluate("() => window.__dbg.spiritLoadDelay(3000)")
        await page.click(f"#roster-list [data-roster-check='{SID[6]}']")
        await until(page, f"() => {{ const b = window.__dbg.roster().bots.find((x) => x.id === '{rid[6]}'); return b && !b.root; }}", "the spirit's robot hidden", timeout=5000, why=RO)
        await page.evaluate("""(id) => { window.__spiritLog = [];
          const note = (t) => window.__spiritLog.push({ t: performance.now(), vis: t.style.visibility || '', hidden: t.hidden });
          window.__spiritObs = new MutationObserver((ms) => { for (const m of ms) {
            const els = m.type === 'childList' ? [...m.addedNodes] : [m.target];
            for (const t of els) if (t.dataset && t.dataset.spiritBubble === id) note(t); } });
          window.__spiritObs.observe(document.getElementById('tags'), { subtree: true, childList: true, attributes: true, attributeFilter: ['style', 'hidden'] }); }""", rid[6])
        hook(6, hook_event_name="PreToolUse", tool_name="Skill", tool_input={"skill": "code-review", "args": ""}, tool_use_id="toolu_sk6")
        await until(page, f"() => {{ const s = window.__dbg.spirit('{rid[6]}'); return s && s.phase === 'shown'; }}", "the hidden robot's spirit standing", timeout=60000,
                    why=f"() => window.__dbg.spirit('{rid[6]}')")
        sp = res["spiritModel"] = await page.evaluate(f"() => window.__dbg.spirit('{rid[6]}')")
        check(failures, sp["model"] == "own/scholar", f"the spirit is the one with a bubble (else the arms below prove nothing): {sp['model']}")
        await page.wait_for_timeout(5000)
        log = res["spiritHiddenLog"] = await page.evaluate("() => window.__spiritLog.slice()")
        drawn = [e for e in log if e["vis"] == "visible" and not e["hidden"]]
        check(failures, any(e["vis"] == "hidden" for e in log) and not drawn, f"its robot hidden, the spirit's bubble is placed hidden and never drawn: {log[:6]}")
        await page.click(f"#roster-list [data-roster-check='{SID[6]}']")
        await until(page, "() => window.__spiritLog.some((e) => e.vis === 'visible' && !e.hidden)", "the bubble drawn once its robot is back", timeout=15000,
                    why=f"() => ({{ spirit: window.__dbg.spirit('{rid[6]}'), log: window.__spiritLog.slice(-4) }})")
        await until(page, "() => { const L = window.__spiritLog, i = L.findIndex((e) => e.vis === 'visible' && !e.hidden); return i >= 0 && L.slice(i).some((e) => e.hidden); }",
                    "the bubble's time over", timeout=20000, why="() => window.__spiritLog.slice(-4)")
        life = res["spiritLife"] = await page.evaluate("""() => { window.__spiritObs.disconnect(); const L = window.__spiritLog, i = L.findIndex((e) => e.vis === 'visible' && !e.hidden);
          const end = L.slice(i).find((e) => e.hidden); return { drawnFor: Math.round(end.t - L[i].t), events: L.length }; }""")
        check(failures, 3500 <= life["drawnFor"] <= 7000, f"shown again, the bubble is drawn about 4 s from its first drawn frame: {life}")
        await page.evaluate("() => window.__dbg.spiritLoadDelay(0)")

        # 6d. a game: one player hidden ends it for the other too
        await page.evaluate("() => window.__dbg.play({ p: 1, idleMs: 0, restMaxSec: 0, solo: { p: 0 } })")
        s = await until(page, "() => { const s = window.__dbg.roster(); return s.bots.filter((b) => b.play).length >= 2 ? s : null; }", "a game in the room", timeout=60000,
                        why="() => window.__dbg.play()")
        players = [b["id"] for b in s["bots"] if b["play"]][:2]
        await page.evaluate("() => window.__dbg.play({ p: 0 })")   # no new game while this one is watched
        hide = SID[rid.index(players[0])] if players[0] in rid else next(b["sid"] for b in s["bots"] if b["id"] == players[0])
        await page.click(f"#roster-list [data-roster-check='{hide}']")
        s = res["play"] = await until(page, f"() => {{ const s = window.__dbg.roster(); return s.bots.filter((b) => {json.dumps(players)}.includes(b.id) && b.play).length === 0 ? s : null; }}",
                                      "the game over for both", timeout=8000, why="() => window.__dbg.play()")
        check(failures, all(next(b for b in s["bots"] if b["id"] == p_)["play"] is None for p_ in players) and next(b for b in s["bots"] if b["id"] == players[1])["root"],
              f"one player hidden: the game is over for its partner too, who stays shown: {players}")
        await page.evaluate("() => window.__dbg.play({ p: 0, endAll: true })")
        await page.click("[data-roster-bulk='all']")

        # 7. the place on the page: on no control (the floor buttons up: two floors), off the error line, inside the 3D,
        # at each width; with a robot's card open on a wide page, beside it
        for i in (0, 3):
            await page.click(f"#roster-list [data-roster-check='{SID[i]}']")

        async def placed(pg, label, card=False):
            await pg.wait_for_timeout(600)   # rosterPlace runs each quarter second
            s = res[f"place-{label}"] = await pg.evaluate(RO)
            check(failures, s["shown"] and s["hits"] == [] and _apart(s["rect"], s["err"]) and _apart(s["rect"], s["soloBox"]) and _apart(s["rect"], s["floorNav"])
                  and _inside(s["rect"], s["scene"]) and (not card or s["card"]),
                  f"{label}: the list on no control, off the error line, inside the 3D: rect {s['rect']} hits {s['hits']} floors {s['floorNav']} name {s['soloBox']} err {s['err']} card {s['card']}")
            return s
        await until(page, "() => !window.__dbg.roster().err", "the sources' error line down", timeout=30000, why=RO)
        s = await placed(page, "1920")
        check(failures, s["floorNav"] is not None and s["err"] is None,
              f"1920: the floor buttons up and the error line down in the room's view (else the arm above proves nothing): {s['floorNav']} {s['err']}")
        await page.screenshot(path=str(out / "1920-floors.png"))
        await page.click(f"#roster-list [data-roster-open='{rid[1]}']")
        await until(page, "() => window.__dbg.roster().card", "a robot's card", timeout=8000, why=RO)
        await placed(page, "1920-card", card=True)
        await page.screenshot(path=str(out / "1920-card.png"))
        await page.keyboard.press("Escape")
        for w, h in ((1440, 900), (1280, 800), (1024, 768)):
            await page.set_viewport_size({"width": w, "height": h})
            # the floor buttons come back once the card's camera has returned: measured with them up
            await until(page, "() => window.__dbg.roster().floorNav", f"{w}: the floor buttons up", timeout=10000, why=RO)
            await placed(page, str(w))
            await page.screenshot(path=str(out / f"{w}-some-hidden.png"))
        # the error line up: a server's sources say what they lack once, when it starts, so a second server with a HOME
        # lacking both (no session files' folder, no adb) shows it; two sessions in this room, the list keeps off it
        home2 = out / "home-error-line"
        (home2 / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
        port2 = free_port()
        srv2 = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port2)], stdout=open(out / "serve2.log", "w"),
                                stderr=subprocess.STDOUT, env=dict(base_env, HOME=str(home2), JUI_VIZ_E2E="1"))
        try:
            for _ in range(400):
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port2}/health", timeout=1).read()
                    break
                except OSError:
                    time.sleep(0.1)
            for i in (0, 1):
                body = {"session_id": SID[i], "cwd": str(CWD), "transcript_path": f"{home2}/t-{i}.jsonl", "permission_mode": "default",
                        "hook_event_name": "SessionStart", "source": "startup"}
                subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(), capture_output=True, env=dict(base_env, HOME=str(home2)), timeout=10)
            page2 = await new_page(browser, Watch(origin=f"http://127.0.0.1:{port2}"), f"{name}-error-line", **WIDE)
            await page2.goto(f"http://127.0.0.1:{port2}/")
            await ready(page2)
            await until(page2, "() => window.__dbg.robots.length >= 2", "two robots on the second server", timeout=40000)
            room2 = await page2.evaluate("() => window.__dbg.robots[0].def.room")
            await page2.evaluate("(id) => window.__dbg.setProject(id)", room2)
            await until(page2, "() => { const s = window.__dbg.roster(); return s.shown && s.err; }", "the list and the error line up", timeout=30000, why=RO)
            s = await placed(page2, "1920-error-line")
            check(failures, s["err"] is not None, f"1920: the error line is up (else the arm above proves nothing): {s['err']}")
            await page2.screenshot(path=str(out / "1920-error-line.png"))
            await page2.close()
        finally:
            srv2.send_signal(2)
            try:
                srv2.wait(10)
            except subprocess.TimeoutExpired:
                srv2.kill()
        await page.set_viewport_size(MID["viewport"])
        await page.click("[data-roster-bulk='all']")
        await page.wait_for_timeout(300)
        await page.screenshot(path=str(out / "1440-all.png"))

        phone = await new_page(browser, Watch(origin=url), f"{name}-phone", **PHONE)
        await phone.goto(url + "/")
        await ready(phone)
        await until(phone, f"() => window.__dbg.robots.length >= {N}", "robots on the phone", timeout=40000)
        await phone.evaluate("(id) => window.__dbg.setProject(id)", room)
        await until(phone, "() => window.__dbg.roster().shown", "the list on the phone", timeout=10000)
        s = await placed(phone, "390-folded")
        check(failures, s["folded"] and s["rect"] and s["rect"][3] - s["rect"][1] < 60, f"390: opens folded to its head: {s['rect']}")
        await phone.screenshot(path=str(out / "390-folded.png"))
        await phone.click("#roster-fold")
        s = await placed(phone, "390-open")
        check(failures, not s["folded"], f"390: opened: {s['folded']}")
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
