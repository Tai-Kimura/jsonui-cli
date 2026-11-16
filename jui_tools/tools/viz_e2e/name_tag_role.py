"""A session's name on its robot's tag (requester, 10-19): /rename or `claude -n` names the robot.

The real `jui viz serve` in a throwaway HOME on a free port; four sessions through the real forward.py, their names
from ~/.claude/sessions/<pid>.json as Claude Code writes them: a short Japanese name, a long one, one with markup and
signs, and none; one subagent. The tag over a named robot shows the name alone (no two-letter mark), cut at its end
with "…" when it does not fit, and never wider than a tag was; the unnamed session and the subagent keep the mark.
The session list, the robot's card and the whiteboard's writer show the whole name with the mark. A rename (the
file rewritten) shows on the tag and the panels. The name is text: `<b>` stays `<b>`. Light and dark pictures, before
(`--jt` takes them from another tree) and after.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from waits import WaitTimeout, settled, until
from common import DESKTOP, LAUNCH_ARGS, T, T_head, Watch, new_page, ready

CWD = "/work/name-app"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
SID = "e2e00000-0000-4000-8000-0000000004{:02x}"
SHORT = "管理画面の担当"
LONG = "agents-lane-37 ログの帯と名札とシュレッダーを見ている長い名前のセッション"
MARKUP = '<b>太字</b> & "記号" <img src=x>'
RENAMED = "名前を変えた 2"
NAMES = {0: SHORT, 1: LONG, 2: MARKUP}   # 3: no name

# Each robot's tag as drawn: its text, whether the mark shows, the name's box and whether the name is cut.
TAGS_JS = """() => window.__dbg.robots.map((R) => { const nm = R.tag.querySelector('.nm'), pillEl = R.tag.querySelector('.pill');
  const b = R.tag.getBoundingClientRect();
  return { id: R.def.id, kind: R.def.kind, title: R.def.title || '', text: R.tag.innerText,   // what shows (a hidden mark is not read)
    pill: !!pillEl && getComputedStyle(pillEl).display !== 'none', name: nm ? nm.textContent : '', nameShown: !!nm && getComputedStyle(nm).display !== 'none',
    cut: !!nm && nm.scrollWidth > nm.clientWidth + 1, nameW: nm ? nm.getBoundingClientRect().width : 0, w: b.width,
    elements: [...R.tag.querySelectorAll('*')].map((e) => e.tagName.toLowerCase()) }; })"""
PANEL_JS = """(id) => { const li = [...document.querySelectorAll('#sessions .session')].find((x) => x.querySelector(`[data-robot-open="${id}"]`));
  const n = li && li.querySelector('.srow .sname');
  return li ? { text: li.querySelector('.srow').textContent, pill: !!li.querySelector('.srow .pill'), b: li.querySelectorAll('.srow b').length, cut: !!n && n.scrollWidth > n.clientWidth + 1 } : null; }"""


def check(failures, cond, text):
    if not cond:
        failures.append(f"name-tag-role: {text}")


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def run_name_tag_role(pw, out, failures, jt=None, shots_only=False):
    from run import free_port
    name = "name-tag-role-before" if shots_only else "name-tag-role"
    out = pathlib.Path(out) / name
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(jt) if jt else pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    sessions = home / ".claude" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)

    def session_file(i, title):
        row = {"pid": 92000 + i, "sessionId": SID.format(i), "cwd": CWD, "status": "idle", "entrypoint": "cli"}
        if title is not None:
            row.update(name=title, nameSource="user")
        (sessions / f"{92000 + i}.json").write_text(json.dumps(row, ensure_ascii=False))

    for i in range(4):
        session_file(i, NAMES.get(i))
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def hook(sid, **payload):
        body = {"session_id": sid, "cwd": CWD, "permission_mode": "default", **payload}
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
        page = await new_page(browser, watch, name, **DESKTOP)
        await page.emulate_media(color_scheme="light", reduced_motion="no-preference")
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').dataset.net === 'connected'", label="connected")
        for i in range(4):
            hook(SID.format(i), hook_event_name="SessionStart", source="startup")
            hook(SID.format(i), hook_event_name="PreToolUse", tool_name="Read", tool_use_id=f"r{i}",
                 tool_input={"file_path": f"/work/name-app/docs/screens/json/screen-{i}.spec.json"})
        hook(SID.format(0), hook_event_name="SubagentStart", agent_id="a0sub00000000000", agent_type="Explore")
        await wait(page, "() => window.__dbg.robots.length >= 5 && window.__dbg.robots.every((R) => !R.path.length)", timeout=30000, label="seated")
        room_id = await page.evaluate("() => window.__dbg.robots[0].def.room")
        labels = await page.evaluate("() => Object.fromEntries(window.__dbg.robots.filter((R) => R.def.kind === 'main').map((R) => [R.def.sessionId, R.def.id]))")
        lab = {i: labels[SID.format(i)] for i in range(4)}

        async def shots(tag):
            for scheme in ("light", "dark"):
                await page.emulate_media(color_scheme=scheme)
                await page.click(f".tag.room[data-set-project='{room_id}']")
                await wait(page, f"() => window.__dbg.solo() === '{room_id}'", label=f"one room, {scheme}")
                await wait(page, "() => window.__dbg.robots.every((R) => !R.path.length)", timeout=30000, label="settled up close")
                if tag == "before":   # another tree, maybe without __dbg.settle: a picture only
                    await page.wait_for_timeout(600)
                else:
                    await settled(page, f"up close, {scheme}: the tags for the picture")
                await page.screenshot(path=str(out / f"{tag}-room-{scheme}.png"))
                await page.click("#room-back")
                await wait(page, "() => window.__dbg.solo() === null", label="back")
                await wait(page, "() => window.__dbg.robots.every((R) => !R.path.length)", timeout=30000, label="settled on the floor")
                await page.screenshot(path=str(out / f"{tag}-floor-{scheme}.png"))
            await page.emulate_media(color_scheme="light")

        if shots_only:
            await shots("before")
            return

        await wait(page, f"() => window.__dbg.robots.filter((R) => R.def.title).length === 3", label="three named robots")
        tags = {t["id"]: t for t in await page.evaluate(TAGS_JS)}
        res["tags"] = tags
        sub = next(t for t in tags.values() if t["kind"] == "sub")
        for i, title in NAMES.items():
            t = tags[lab[i]]
            check(failures, t["title"] == title and t["name"] == title and t["nameShown"] and not t["pill"] and t["text"].startswith(title),
                  f"{i}: the tag shows the name alone, no mark: {t}")
            check(failures, t["w"] <= 251, f"{i}: the tag is no wider than a tag was (250 px): {t['w']}")
        check(failures, not tags[lab[0]]["cut"], f"a short name is whole: {tags[lab[0]]}")
        check(failures, tags[lab[1]]["cut"] and tags[lab[1]]["nameW"] < tags[lab[1]]["w"], f"a long name is cut at its end (…): {tags[lab[1]]}")
        check(failures, "b" not in tags[lab[2]]["elements"] and "img" not in tags[lab[2]]["elements"], f"the name is text, not HTML: {tags[lab[2]]['elements']}")
        for t in (tags[lab[3]], sub):
            check(failures, t["pill"] and not t["nameShown"] and t["text"].startswith(t["id"]), f"no name (or a subagent): the two-letter mark as before: {t}")

        # the panels: the whole name with the mark
        for i, title in NAMES.items():
            row = await page.evaluate(PANEL_JS, lab[i])
            check(failures, row and title in row["text"] and row["pill"] and row["text"].startswith(lab[i]) and not row["cut"],
                  f"{i}: the session row shows the mark and the whole name, not cut: {row}")
        row = await page.evaluate(PANEL_JS, lab[3])
        check(failures, row and row["text"].startswith(lab[3]) and T_head("live.session.head", "id").strip() in row["text"], f"no name: the row as before: {row}")
        check(failures, (await page.evaluate(PANEL_JS, lab[2]))["b"] == 0, "the session row's name is text, not HTML")
        await page.click(f"#sessions [data-robot-open='{lab[1]}']")
        await wait(page, "() => !document.getElementById('rb').hidden && document.getElementById('rb-title')", label="the robot's card")
        await until(page, "(name) => document.getElementById('rb-title').textContent === name", "the card shows the long name", arg=LONG,
                    why="() => document.getElementById('rb-title').textContent")
        card = res["card"] = await page.evaluate("() => ({ nameBox: (({ top, bottom, left, right }) => ({ top, bottom, left, right }))(document.getElementById('rb-title').getBoundingClientRect()), navBox: (({ top, bottom, left, right }) => ({ top, bottom, left, right }))(document.querySelector('.rb-nav').getBoundingClientRect()), headBox: (({ left, right }) => ({ left, right }))(document.querySelector('.rb-head').getBoundingClientRect()), name: document.getElementById('rb-title').textContent, sub: document.querySelector('.rb-sub').textContent, badge: document.querySelector('.rb-badge').textContent, badgeShown: getComputedStyle(document.querySelector('.rb-badge')).display !== 'none' })")
        check(failures, card["name"] == LONG and card["badge"] == lab[1] and card["badgeShown"] and lab[1] in card["sub"],
              f"the robot's card: the whole name, and its mark (requester: the id stays on the robot's panel): {card}")
        check(failures, card["navBox"]["top"] >= card["nameBox"]["bottom"] - 1 and card["nameBox"]["right"] > card["headBox"]["right"] - 40,
              f"the card's controls sit below the name, which takes the card's width (requester 10-19): {card}")
        await page.screenshot(path=str(out / "after-card-light.png"))
        await page.click("#rb-close")
        await wait(page, "() => document.getElementById('rb').hidden", label="card closed")

        # a rename: the file rewritten (as /rename does) — the tag and the panels follow
        session_file(0, RENAMED)
        await wait(page, f"() => window.__dbg.robots.find((R) => R.def.id === '{lab[0]}').def.title === '{RENAMED}'", label="renamed")
        # the tag's name is written in a frame (liveTagName), the session list on its own beat: wait for each to show
        # the new name, never for time (ticket 2026-10-19-jui-viz-e2e-name-tags-few-frames-flaky; 2.3.4 read once after
        # 0.6 s and, at load ~123, still saw the old name). A timeout fails the arms below with what was shown.
        try:
            await until(page, "([id, name]) => { const R = window.__dbg.robots.find((x) => x.def.id === id); const nm = R && R.tag.querySelector('.nm'); return !!nm && nm.textContent === name; }",
                        "the tag shows the new name", arg=[lab[0], RENAMED],
                        why="([id]) => { const R = window.__dbg.robots.find((x) => x.def.id === id); return R ? R.tag.textContent : null; }")
            await until(page, f"([id, name]) => {{ const row = ({PANEL_JS})(id); return !!row && row.text.includes(name); }}", "the session list shows the new name",
                        arg=[lab[0], RENAMED], why=f"([id]) => ({PANEL_JS})(id)")
        except WaitTimeout:
            pass
        t = next(x for x in await page.evaluate(TAGS_JS) if x["id"] == lab[0])
        row = await page.evaluate(PANEL_JS, lab[0])
        res["renamed"] = {"tag": t, "row": row}
        check(failures, t["name"] == RENAMED and not t["pill"], f"a rename shows on the tag: {t}")
        check(failures, row and RENAMED in row["text"] and SHORT not in row["text"], f"a rename shows in the session list: {row}")

        await shots("after")
        check(failures, not watch.console and not watch.foreign and not watch.csp, f"no console error, nothing outside the server: {watch.console[:3]} {watch.foreign[:3]}")
        await page.close()
    except Exception as e:
        failures.append(f"name-tag-role: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        await browser.close()
        srv.terminate()  # our own child (started above)
        try:
            srv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            srv.kill()
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"  {name}: {time.monotonic() - t0:.0f}s", flush=True)
