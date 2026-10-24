"""The whole text of a line cut to one, on hover and on focus (2.3.6, requester 10-19: "これテストのパスが見えないからホバーで
全部表示されるようにしてほしい"). Runs with `--only fulltext`.

The real `jui viz serve` in a throwaway HOME on a free port, the real forward.py for the hooks, a JsonUI project in that
HOME with one spec whose name is long. Robot A runs a test with a long command (its card's テスト実行 row), works on a long
path, and has a subagent with a long type reading a long path; its transcript has a tool with a long MCP name and a long
description (the 応答の履歴 tab). Robot B runs a test with a short command.

Checked (57-fulltext.js, one component for the family — the table is in the ticket):
  * A's テスト実行 row (a ~2000-char command), hovered: the floating tag shows the whole command, wrapped, just left of the
    card — inside the window and the 3D left free by the card, 0-16 px from the card's left edge, on neither the card nor its
    line's host, not at the 3D's left edge (2.3.8's place, inverted), its top level with the row, readable width (PLACE_JS;
    10-20 requester: 「ホバーで横に出す件だけど、今度は遠すぎる ボードのすぐ横に出て欲しい」); the pointer crossing to it keeps
    it; its text selected and copied comes out of the clipboard whole; the pointer leaving hides it (also downwards inside
    the card). The same at 1440x900 and 2000x1100, with the card at its width and widened (広げる).
  * B's short row: not cut, not focusable, no tag on hover.
  * Tab to A's row: the tag shows, the row points at it (aria-describedby); Esc hides it and the card stays open.
  * one row of every other member of the family (the card's subagent act, the history's head and tool name, the panel's
    act, subagent name, spec name and project summary): cut, hovered → the whole text, just left of the open card, level
    with its own row.
  * the log strip's line (no board beside it): 2.3.8's place, the 3D's left edge above the strip, clear of the centre.
    A member the scene does not cut by itself is narrowed for the arm (style max-width on that element), named in the
    results ("narrowed"): the component, not the length of a test string, is what is checked.
Waits are on page state (waits.until); a hover's effect is synchronous, read right after the pointer moved.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import time

from common import DESKTOP, ISOLATE, LAUNCH_ARGS, T, Watch, dump, new_page, ready, stamp
from waits import WaitTimeout, until

SID_A = "a1f00000-0000-4000-8000-0000000000f1"
SID_B = "b2f00000-0000-4000-8000-0000000000f2"
SUB = "a1fsub0000000001"
LONG_CMD = ("S=/private/tmp/e2e-hover/-Users-someone-resource-JsonUI-Agents/6376a1cb-5b86-497f-b8aa-880b2bc9bd52/scratchpad "
            "&& npx playwright test tests/screens/a-very-long-folder-name/and-a-long-screen-name.test.json --reporter=line"
            # 10-20: the requester's board was filled by a ~2000-char command (the server keeps 2000, ingest.TEST_COMMAND_MAX)
            + "".join(f" && npx playwright test tests/screens/a-very-long-folder-name/screen-number-{i:02d}.test.json --reporter=line" for i in range(16)))
SHORT_CMD = "npx playwright test t.json"
# The log strip (2.3.6): a prompt that came as a message from another session — the line the requester saw cut (23:07).
PEER_PROMPT = ("Another session sent a message: <cross-session-message from=\"uds:/tmp/e2e-hover.sock\" from-name=\"jsonui-dd\"> "
               "2.3.6 の票を振りました。ログの帯の行もホバーとフォーカスで全文が読めるかを確かめるための、わざと長くした文です。"
               "</cross-session-message>")
# Where the tag is (10-20 afternoon, requester: 「ホバーで横に出す件だけど、今度は遠すぎる ボードのすぐ横に出て欲しい」).
# The board beside it: the robot card when it is open at the side (widened too), else, for a side-panel line, the panel.
# With a board — placed: inside the window and the free box (the scene less the card), its right edge 0-16 px left of the
# board's left edge (nextTo), on neither the open card nor its line's host (clear), not at the free box's left edge
# (offLeftEdge: 2.3.8's arm "16 px in from the 3D's left", inverted), its top level with the line's top kept inside the
# free box and the line's middle inside the tag's height (level), and — when it wraps — at least min(420, 40% of the free
# box's width) wide. A card or panel line with no board found is not placed.
# 2.3.8's "clear of the 3D's centre" is dropped for these (the requester allows the tag on the 3D and a robot): measured
# only (coversMid). No board (the log strip): 2.3.8's arm as it was — 16 px in from the free box's left, clear of its centre.
# robotCovered: how much of the selected robot's box on screen (its shown meshes, the desk left out) it covers (measured).
PLACE_JS = """const place = (tb, line) => { if (!tb) return null;
    const s = document.getElementById('scene').getBoundingClientRect(), card = document.getElementById('rb');
    const f = { l: Math.max(s.left, 0), t: Math.max(s.top, 0), r: Math.min(s.right, innerWidth), b: Math.min(s.bottom, innerHeight) };
    if (card && !card.hidden) { const c = card.getBoundingClientRect(); if (c.left > f.l + (f.r - f.l) * 0.25) f.r = Math.min(f.r, c.left); else f.b = Math.min(f.b, c.top); }
    const d = window.__dbg, rid = d.board().robot, R = rid && d.robots.find((x) => x.def.id === rid);
    let robot = null;
    if (R) { const box = new d.THREE.Box3(), part = new d.THREE.Box3(), v = new d.THREE.Vector3(), cv = document.getElementById('scene-canvas').getBoundingClientRect();
      R.robot.root.updateMatrixWorld(true);
      const walk = (o) => { if (!o.visible || o === R.robot.desk) return; if (o.isMesh && o.geometry) { if (!o.geometry.boundingBox) o.geometry.computeBoundingBox(); box.union(part.copy(o.geometry.boundingBox).applyMatrix4(o.matrixWorld)); } o.children.forEach(walk); };
      walk(R.robot.root);
      robot = { l: 1e9, t: 1e9, r: -1e9, b: -1e9 };
      for (let i = 0; i < 8; i++) { v.set(i & 1 ? box.max.x : box.min.x, i & 2 ? box.max.y : box.min.y, i & 4 ? box.max.z : box.min.z).project(d.camera);
        const x = cv.left + (v.x + 1) / 2 * cv.width, y = cv.top + (1 - v.y) / 2 * cv.height;
        robot.l = Math.min(robot.l, x); robot.r = Math.max(robot.r, x); robot.t = Math.min(robot.t, y); robot.b = Math.max(robot.b, y); } }
    const w = f.r - f.l, minW = Math.min(420, w * 0.4);
    const holds = (x, y) => x >= tb.left && x <= tb.right && y >= tb.top && y <= tb.bottom;
    const overlaps = (b) => !!b && Math.min(tb.right, b.right) - Math.max(tb.left, b.left) > 0.5 && Math.min(tb.bottom, b.bottom) - Math.max(tb.top, b.top) > 0.5;
    const tag = document.getElementById('fulltext'), wraps = tb.height > 40;   // one line is 32 px (18 + padding + border)
    const inWin = tb.left >= -0.5 && tb.top >= -0.5 && tb.right <= innerWidth + 0.5 && tb.bottom <= innerHeight + 0.5;
    const inFree = tb.left >= f.l - 0.5 && tb.right <= f.r + 0.5 && tb.top >= f.t - 0.5 && tb.bottom <= f.b + 0.5;
    const wide = !wraps || tb.width >= minW - 1;
    const coversMid = holds((f.l + f.r) / 2, (f.t + f.b) / 2) || holds((s.left + s.right) / 2, (s.top + s.bottom) / 2);
    const host = line ? ['#rb', '#side'].map((q) => document.querySelector(q)).find((h) => h && h.contains(line)) : null;
    const cardBox = card && !card.hidden ? card.getBoundingClientRect() : null;
    let board = null;
    if (host) { const bb = cardBox || (host.id === 'side' ? host.getBoundingClientRect() : null); if (bb && bb.left >= f.r - 1 && bb.left > f.l) board = bb; }
    let robotCovered = null;
    if (robot) { const ox = Math.max(0, Math.min(tb.right, robot.r) - Math.max(tb.left, robot.l)), oy = Math.max(0, Math.min(tb.bottom, robot.b) - Math.max(tb.top, robot.t));
      robotCovered = Math.round(100 * ox * oy / Math.max(1, (robot.r - robot.l) * (robot.b - robot.t))) + '%'; }
    const r1 = (x) => Math.round(x);
    const at = { inWin, inFree, wide, minW: r1(minW), robotCovered, coversMid, beside: host ? (host.id === 'rb' ? 'card' : 'panel') : 'none',
      scrolls: !!tag && tag.scrollHeight > tag.clientHeight + 1,
      tag: [r1(tb.left), r1(tb.top), r1(tb.width), r1(tb.height)], free: [r1(f.l), r1(f.t), r1(f.r), r1(f.b)], robot: robot && [r1(robot.l), r1(robot.t), r1(robot.r), r1(robot.b)] };
    if (host) {
      const lb = line.getBoundingClientRect(), gap = board ? board.left - tb.right : null;
      const nextTo = gap !== null && gap >= -0.5 && gap <= 16.5;
      const clear = !overlaps(cardBox) && !overlaps(host.getBoundingClientRect());
      const offLeftEdge = tb.left > f.l + 16 + 1.5;
      const wantTop = Math.max(f.t + 16, Math.min(lb.top, f.b - 16 - tb.height)), mid = (lb.top + lb.bottom) / 2;
      const level = Math.abs(tb.top - wantTop) <= 1.5 && mid >= tb.top - 0.5 && mid <= tb.bottom + 0.5;
      return Object.assign(at, { placed: !!board && inWin && inFree && nextTo && clear && offLeftEdge && level && wide, board: board && [r1(board.left), r1(board.top), r1(board.right), r1(board.bottom)],
        gap: gap === null ? null : r1(gap), nextTo, clear, offLeftEdge, level, row: [r1(lb.top), r1(lb.bottom)], wantTop: r1(wantTop) });
    }
    const atLeft = Math.abs(tb.left - (f.l + 16)) <= 1.5, clearMid = !coversMid;
    return Object.assign(at, { placed: inWin && inFree && atLeft && clearMid && wide, atLeft, clearMid }); };"""
# One strip line (by its text) and the tag: inside the viewport and above the line.
STRIP_JS = """(want) => { """ + PLACE_JS + """ const line = [...document.querySelectorAll('#ticker .what')].find((x) => x.textContent.includes(want));
  const tag = document.getElementById('fulltext');
  if (!line) return null;
  const lb = line.getBoundingClientRect(), tb = tag && !tag.hidden ? tag.getBoundingClientRect() : null;
  return { cut: line.scrollWidth > line.clientWidth + 1, text: line.textContent, tabindex: line.getAttribute('tabindex'),
    shown: !!tb, tagText: tag && !tag.hidden ? tag.textContent : '', described: line.getAttribute('aria-describedby'),
    inView: !!tb && tb.left >= -0.5 && tb.top >= -0.5 && tb.right <= innerWidth + 0.5 && tb.bottom <= innerHeight + 0.5,
    above: !!tb && tb.bottom <= lb.top + 0.5, focused: document.activeElement === line, at: place(tb) }; }"""
TITLE = "とても長いセッションの名前：テストのパスがホバーで全部見えるかを確かめるための、わざと長くした名前"
SUB_TYPE = "a-subagent-type-with-a-name-long-enough-to-be-cut-in-the-session-list"
SPEC_NAME = "わざと長くした画面の名前：浮き札でカードやパネルの 1 行で切れた文の全文が読めるかを確かめる画面"
MCP_TOOL = "mcp__a_server_with_a_long_name__and_a_tool_with_an_even_longer_name_for_the_summary"
DESC = "長い説明: 応答の履歴の折りたたんだ行の頭で切れる文が、ホバーとフォーカスで全文になるかを確かめるための説明文"

# The state of one line and of the tag, from the page.
LINE_JS = """([sel, i]) => { """ + PLACE_JS + """ const line = document.querySelectorAll(sel)[i || 0]; const tag = document.getElementById('fulltext');
  if (!line) return null;
  const tb = tag && !tag.hidden ? tag.getBoundingClientRect() : null;
  const owner = line.closest('button, summary, a[href]') || line;
  return { cut: line.scrollWidth > line.clientWidth + 1, text: line.textContent, tabindex: line.getAttribute('tabindex'),
    shown: !!tb, tagText: tag && !tag.hidden ? tag.textContent : '', described: owner.getAttribute('aria-describedby'),
    at: place(tb, line), placed: !!(tb && place(tb, line).placed),
    wraps: !!tb && tb.height > 30, select: tag ? getComputedStyle(tag).userSelect : '' }; }"""
TAG_SHOWN = "() => { const t = document.getElementById('fulltext'); return !!t && !t.hidden; }"
TAG_HIDDEN = "() => { const t = document.getElementById('fulltext'); return !t || t.hidden; }"
NARROW_JS = """([sel, i]) => { const line = document.querySelectorAll(sel)[i || 0];
  if (!line || line.scrollWidth > line.clientWidth + 1) return false;
  line.style.maxWidth = '70px'; if (getComputedStyle(line).display === 'inline') line.style.display = 'inline-block'; return true; }"""
FAMILY = [   # (name, selector, where: the card's tab or the panel)
    ("card · サブエージェントの act", "#rb .rb-subs .act", "now"),
    ("panel · セッションの act", "#sessions .act", "panel"),
    ("panel · サブエージェントの名前", "#sessions .subs .who-btn > span:last-child", "panel"),
    ("panel · spec の名前", "#spec-list .spec-row .nm", "panel"),
    ("panel · プロジェクトのまとめ", "#sessions .pg-toggle small", "panel"),
    ("card · 応答の履歴の頭", "#rb .h-tool .h-head", "history"),
    ("card · 応答の履歴のツール名", "#rb .h-tool summary > b", "history"),
]


def check(failures, cond, text):
    if not cond:
        failures.append(f"fulltext: {text}")


async def run_fulltext(pw, out, failures, jt=None, shots_only=False):
    from run import free_port
    name = "fulltext-before" if shots_only else "fulltext"
    out = pathlib.Path(out) / name
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    proj = home / "work" / "hover-app"
    (proj / "docs" / "screens" / "json").mkdir(parents=True, exist_ok=True)
    (proj / "jui.config.json").write_text(json.dumps({"spec_directory": "docs/screens/json"}))
    (proj / "docs" / "screens" / "json" / "long_name.spec.json").write_text(json.dumps(
        {"type": "screen_spec", "version": "1.0", "metadata": {"name": "LongName", "displayName": SPEC_NAME, "description": "d"},
         "structure": {"components": [{"type": "Label", "id": "title"}], "layout": {}}}, ensure_ascii=False))
    transcript = home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(proj)) / f"{SID_A}.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [
        {"type": "user", "timestamp": stamp("2026-10-19T09:00:00Z"), "message": {"role": "user", "content": "テストを走らせて"}},
        {"type": "assistant", "timestamp": stamp("2026-10-19T09:00:01Z"), "message": {"id": "m1", "role": "assistant", "content": [
            {"type": "tool_use", "id": "toolu_ft", "name": MCP_TOOL, "input": {"description": DESC, "query": "x"}}]}},
        {"type": "user", "timestamp": stamp("2026-10-19T09:00:02Z"), "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_ft", "content": "ok"}]}},
        {"type": "assistant", "timestamp": stamp("2026-10-19T09:00:03Z"), "message": {"id": "m2", "role": "assistant", "content": [{"type": "text", "text": "走らせました"}]}},
    ]) + "\n")
    jt = pathlib.Path(jt) if jt else pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE + ("PYTHONPATH",)}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {"family": {}}

    def hook(sid, **payload):
        body = {"session_id": sid, "cwd": str(proj), "transcript_path": str(transcript) if sid == SID_A else f"/nowhere/{sid}.jsonl",
                "permission_mode": "default", **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body, ensure_ascii=False).encode(),
                       capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)

    async def line(page, sel, i=0):
        return await page.evaluate(LINE_JS, [sel, i])

    async def open_card(page, label):
        await page.evaluate("(l) => document.querySelector(`#sessions [data-robot-open=\"${l}\"]`).click()", label)
        await until(page, "(l) => (document.querySelector('#rb .rb-badge') || {}).textContent === l && !!document.querySelector('#rb .rb-run-file')",
                    f"{label}'s card with its test row", arg=label)
        await until(page, "() => getComputedStyle(document.getElementById('rb')).opacity === '1'", f"{label}'s card faded in")

    async def set_wide(page, on):   # 広げる (the choice is kept: put back at the end of the arm)
        want = "true" if on else "false"
        if await page.evaluate("() => document.querySelector('#rb [data-rb-wide]').getAttribute('aria-pressed')") != want:
            await page.click("#rb [data-rb-wide]")
        await until(page, "(w) => document.getElementById('rb').classList.contains('rb-wide') === (w === 'true')", f"the card {'widened' if on else 'at its width'}", arg=want)

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
        context = await browser.new_context(**DESKTOP)
        await context.grant_permissions(["clipboard-read", "clipboard-write"], origin=url)
        page = await context.new_page()
        watch.attach(page, name)
        await page.emulate_media(color_scheme="light")
        await page.goto(url + "/")
        await ready(page)
        await until(page, "() => document.querySelector('.chip.demo').dataset.net === 'connected'", "connected")
        hook(SID_A, hook_event_name="SessionStart", source="startup", session_title=TITLE)
        hook(SID_B, hook_event_name="SessionStart", source="startup")
        hook(SID_A, hook_event_name="UserPromptSubmit", prompt=PEER_PROMPT)   # before the tools: A's act stays the long one
        hook(SID_A, hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="run-a", tool_input={"command": LONG_CMD})
        hook(SID_B, hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="run-b", tool_input={"command": SHORT_CMD})
        hook(SID_A, hook_event_name="PreToolUse", tool_name="Read", tool_use_id="sub-r", agent_id=SUB, agent_type=SUB_TYPE,
             tool_input={"file_path": f"{proj}/docs/screens/json/a-very-long-folder-name/and-a-long-screen-name.spec.json"})
        await until(page, "() => document.querySelectorAll('#sessions [data-robot-open]').length >= 3", "the two sessions and the subagent", timeout=30000)
        await page.click("#spec-filter [data-f='all']")
        await until(page, "() => document.querySelectorAll('#spec-list .spec-row').length >= 1", "the spec listed", timeout=30000)
        labels = await page.evaluate("""() => { const s = [...document.querySelectorAll('#sessions .session')];
          return s.map((x) => x.querySelector('[data-robot-open]').dataset.robotOpen); }""")
        lab_a = await page.evaluate("(t) => [...document.querySelectorAll('#sessions .session')].find((x) => x.textContent.includes(t)).querySelector('[data-robot-open]').dataset.robotOpen", TITLE[:10])
        lab_b = next(x for x in labels if x != lab_a)
        res["labels"] = {"a": lab_a, "b": lab_b}

        await open_card(page, lab_a)
        if not shots_only:
            await until(page, "() => document.querySelector('#rb .rb-run-file').getAttribute('tabindex') === '0'", "A's cut row made focusable",
                        why="() => { const l = document.querySelector('#rb .rb-run-file'); return { sw: l.scrollWidth, cw: l.clientWidth, tab: l.getAttribute('tabindex') }; }")
        if shots_only:
            await page.hover("#rb .rb-run-file")
            for scheme in ("light", "dark"):
                await page.emulate_media(color_scheme=scheme)
                await page.screenshot(path=str(out / f"before-card-{scheme}.png"))
            return
        # 1. A's long test row (~2000 chars), hovered: the whole command, wrapped, in the 3D's left column (PLACE_JS); the
        #    pointer crossing the card and the 3D to the tag keeps it; copied whole; gone when the pointer leaves
        r = res["longBefore"] = await line(page, "#rb .rb-run-file")
        check(failures, r and r["cut"] and r["tabindex"] == "0" and not r["shown"], f"A's test row is cut and focusable, no tag yet: {r}")
        res["rowHit"] = await page.evaluate("""() => { const l = document.querySelector('#rb .rb-run-file'); l.scrollIntoView({ block: 'nearest' }); const b = l.getBoundingClientRect();
          const at = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2); return { box: [b.left, b.top, b.width, b.height], at: at && (at.id || at.className || at.tagName) }; }""")
        await page.hover("#rb .rb-run-file")
        await until(page, TAG_SHOWN, "the tag on hover")
        r = res["longHover"] = await line(page, "#rb .rb-run-file")
        check(failures, r["shown"] and r["tagText"] == LONG_CMD and r["placed"] and r["wraps"] and r["described"] == "fulltext" and r["select"] in ("text", "auto"),
              f"hovered: the whole command, wrapped, just left of the card (0-16 px, not on it), level with the row, readable width, the row points at it: {r}")
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await page.screenshot(path=str(out / f"after-card-{scheme}.png"))
        await page.emulate_media(color_scheme="light")
        box = await page.evaluate("() => { const b = document.getElementById('fulltext').getBoundingClientRect(); return [b.left + 8, b.top + 8]; }")
        await page.mouse.move(*box, steps=12)   # across the card and the 3D into the tag: it stays (to select in it)
        await page.wait_for_timeout(900)        # longer than the time given to cross (FULLTEXT_TRAVEL_MS)
        stays = res["staysInTag"] = (await line(page, "#rb .rb-run-file"))["shown"]
        check(failures, stays, "the pointer crossed the card and the 3D from the row into the tag: the tag stays")
        await page.evaluate("() => { const t = document.getElementById('fulltext'), r = document.createRange(); r.selectNodeContents(t); const s = getSelection(); s.removeAllRanges(); s.addRange(r); }")
        await page.keyboard.press("ControlOrMeta+c")
        copied = res["copied"] = await page.evaluate("() => navigator.clipboard.readText()")
        check(failures, copied == LONG_CMD, f"the tag's text selected and copied comes out whole: {copied!r}")
        await page.mouse.move(5, 5)
        await until(page, TAG_HIDDEN, "the tag gone when the pointer left")
        # 1b. the pointer leaving the row downwards, inside the card (10-20: the tag covered the card, so the pointer stayed
        #     "in the tag" and the tag stayed): gone
        await page.hover("#rb .rb-run-file")
        await until(page, TAG_SHOWN, "the tag on hover again")
        row = await page.evaluate("() => { const b = document.querySelector('#rb .rb-run-file').getBoundingClientRect(); return [b.left + 20, b.top + b.height / 2]; }")
        await page.mouse.move(row[0], row[1] + 200, steps=5)
        try:
            await until(page, TAG_HIDDEN, "the tag gone when the pointer left downwards in the card", timeout=3000)
            res["leftDown"] = "hidden"
        except WaitTimeout as e:
            res["leftDown"] = str(e)
            check(failures, False, f"the pointer left the row downwards inside the card: the tag stays: {e}")
        await page.mouse.move(5, 5)
        # 1c. the card at its width and widened (広げる, 2.3.4), at 1440x900 and 2000x1100: the tag just left of the card,
        #     level with the row (ticket 2026-10-20-jui-viz-fulltext-float-next-to-the-card)
        res["sizes"] = {}
        for vw, vh in ((1440, 900), (2000, 1100)):
            await page.set_viewport_size({"width": vw, "height": vh})
            for wide in (False, True):
                await set_wide(page, wide)
                await page.mouse.move(5, 5)
                await until(page, TAG_HIDDEN, "no tag before the hover")
                await until(page, "() => document.querySelector('#rb .rb-run-file').getAttribute('tabindex') === '0'", "A's row cut")
                await page.hover("#rb .rb-run-file")
                await until(page, TAG_SHOWN, "the tag on hover")
                key = f"{vw}x{vh} {'wide' if wide else 'normal'}"
                r = res["sizes"][key] = await line(page, "#rb .rb-run-file")
                check(failures, r["shown"] and r["tagText"] == LONG_CMD and r["placed"],
                      f"{key} card: the tag just left of the card (0-16 px, not on it), level with the row: {r['at']}")
        await page.mouse.move(5, 5)
        await page.set_viewport_size(DESKTOP["viewport"])
        await set_wide(page, False)
        await until(page, TAG_HIDDEN, "no tag after the sizes")
        # 2. B's short row: not cut, not focusable, no tag
        await open_card(page, lab_b)
        await page.hover("#rb .rb-run-file")
        r = res["short"] = await line(page, "#rb .rb-run-file")
        check(failures, r and not r["cut"] and r["tabindex"] is None and not r["shown"] and r["text"] == SHORT_CMD, f"a short row: no tag, not focusable: {r}")
        await page.mouse.move(5, 5)
        # 3. Tab to A's row: shown; Esc: hidden, the card stays
        await open_card(page, lab_a)
        await until(page, "() => document.querySelector('#rb .rb-run-file').getAttribute('tabindex') === '0'", "A's row focusable again")
        # the keyboard: Tab on 今の様子 selects 応答の履歴 (2.3.4), so the 今の様子 body is reached backwards, from the panel
        await page.focus("#side [data-fold]")
        reached, path = False, []
        for _ in range(60):
            await page.keyboard.press("Shift+Tab")
            here = await page.evaluate("() => { const a = document.activeElement; return a ? (a.dataset && a.dataset.fk) || a.className || a.tagName : null; }")
            path.append(here)
            if await page.evaluate("() => !!document.activeElement && document.activeElement.matches('#rb .rb-run-file')"):
                reached = True
                break
        res["tabPath"] = path
        r = res["focus"] = await line(page, "#rb .rb-run-file")
        check(failures, reached and r["shown"] and r["tagText"] == LONG_CMD and r["described"] == "fulltext" and r["placed"], f"Tab reaches the row and shows the tag: reached {reached}, {r}")
        await page.keyboard.press("Escape")
        r = res["esc"] = await line(page, "#rb .rb-run-file")
        card_open = await page.evaluate("() => !document.getElementById('rb').hidden")
        check(failures, r and not r["shown"] and r["described"] is None and card_open, f"Esc hides the tag, the card stays: {r} card {card_open}")
        # 4. one row of every other member of the family
        for fname, sel, where in FAMILY:
            if where == "history" and await page.evaluate("() => document.querySelector('[data-rb-hist]').hidden"):
                await page.click('#rb [data-rb-tab="history"]')
                await until(page, "() => !!document.querySelector('#rb .h-tool')", "the history's tool item", timeout=30000)
            if where == "now" and not await page.evaluate("() => document.querySelector('[data-rb-hist]').hidden"):
                await page.click('#rb [data-rb-tab="now"]')
            try:
                await until(page, "(sel) => !!document.querySelector(sel)", f"{fname}: the row", arg=sel, timeout=30000)
            except WaitTimeout as e:
                check(failures, False, f"{fname}: {e}")
                continue
            res["family"].setdefault("_seen", {})[fname] = await page.evaluate("""(sel) => { const l = document.querySelector(sel); const b = l.getBoundingClientRect();
              return { text: l.textContent.slice(0, 40), w: b.width, h: b.height, display: getComputedStyle(l).display }; }""", sel)
            narrowed = await page.evaluate(NARROW_JS, [sel, 0])
            await page.hover(sel)
            r = await line(page, sel)
            res["family"][fname] = dict(r, narrowed=narrowed)
            check(failures, r["cut"] and r["shown"] and r["tagText"] == r["text"] and r["placed"] and r["described"] == "fulltext",
                  f"{fname}: cut, hovered → the whole text just left of the open card, level with its row: {r} (narrowed for the arm: {narrowed})")
            if fname == "panel · セッションの act":
                await page.screenshot(path=str(out / "after-panel-light.png"))
            await page.mouse.move(5, 5)
            await until(page, TAG_HIDDEN, f"{fname}: the tag gone")
        # 5. the log strip (2.3.6): a long line hovered → the whole text, upward, inside the viewport; a short line nothing;
        #    the keyboard reaches the long line (backwards from ログを全画面で見る) and shows it; closed, the strip does nothing
        await page.click("#rb-close")
        await until(page, "() => document.getElementById('rb').hidden", "the card closed")
        head = PEER_PROMPT[:16]
        await until(page, "(w) => [...document.querySelectorAll('#ticker .what')].some((x) => x.textContent.includes(w) && x.getAttribute('tabindex') === '0')",
                    "the strip's long line, cut and focusable", arg=head,
                    why="() => [...document.querySelectorAll('#ticker .what')].map((x) => [x.textContent.slice(0, 30), x.scrollWidth, x.clientWidth, x.getAttribute('tabindex')])")
        await page.hover(f"#ticker .what:has-text('{head}')")
        r = res["stripLong"] = await page.evaluate(STRIP_JS, head)
        check(failures, r and r["cut"] and r["shown"] and r["tagText"] == r["text"] and "</cross-session-message>" in r["tagText"] and r["inView"] and r["above"] and r["described"] == "fulltext" and r["at"]["placed"],
              f"the strip's long line hovered: the whole text, above the line, inside the viewport, at the 3D's left edge (no board beside the strip), clear of the centre: {r}")
        await page.screenshot(path=str(out / "after-strip-light.png"))
        await page.mouse.move(5, 5)
        await until(page, TAG_HIDDEN, "the strip's tag gone")
        clock_in = T("ev.clock_in", source="").strip()
        await page.hover(f"#ticker .what:has-text({json.dumps(clock_in, ensure_ascii=False)})")   # 出勤 as itself, not \u51fa\u52e4
        r = res["stripShort"] = await page.evaluate(STRIP_JS, clock_in)
        check(failures, r and not r["cut"] and not r["shown"] and r["tabindex"] is None, f"a short strip line: no tag, not focusable: {r}")
        await page.mouse.move(5, 5)
        await page.focus("#btn-log")
        reached = False
        for _ in range(12):
            await page.keyboard.press("Shift+Tab")
            r = await page.evaluate(STRIP_JS, head)
            if r and r["focused"]:
                reached = True
                break
        res["stripFocus"] = r
        check(failures, reached and r["shown"] and r["inView"] and r["above"], f"the keyboard reaches the strip's long line and shows the tag: reached {reached}, {r}")
        await page.keyboard.press("Escape")
        await until(page, TAG_HIDDEN, "the strip's tag gone on Esc")
        await page.emulate_media(color_scheme="dark")
        await page.hover(f"#ticker .what:has-text('{head}')")
        await until(page, TAG_SHOWN, "the strip's tag, dark")
        await page.screenshot(path=str(out / "after-strip-dark.png"))
        await page.emulate_media(color_scheme="light")
        await page.mouse.move(5, 5)
        await page.click("#btn-strip-close")
        await until(page, "() => document.querySelector('.app').classList.contains('log-closed')", "the strip closed")
        await until(page, "() => !document.querySelector('#ticker [tabindex]')", "no strip line focusable while closed",
                    why="() => [...document.querySelectorAll('#ticker [tabindex]')].length")
        r = res["stripClosed"] = await page.evaluate("() => ({ focusable: document.querySelectorAll('#ticker [tabindex]').length, tag: !document.getElementById('fulltext').hidden })")
        check(failures, r == {"focusable": 0, "tag": False}, f"the strip closed: nothing: {r}")
        await page.close()
        for l in watch.console:
            failures.append(f"fulltext: console: {l}")
        for u in watch.foreign:
            failures.append(f"fulltext: request outside the server: {u}")
    except Exception as e:   # a wait that ran out is a FAIL line with what was seen
        failures.append(f"fulltext: {type(e).__name__}: {str(e).splitlines()[0]}")
        res["error"] = str(e)[:4000]
    finally:
        await browser.close()
        srv.terminate()   # our own child
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        (out / "fulltext-results.json").write_text(dump(res) + "\n")
    print(f"  {name}: {time.monotonic() - t0:.0f}s", flush=True)
