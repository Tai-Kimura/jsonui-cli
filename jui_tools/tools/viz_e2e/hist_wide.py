"""The wide 応答の履歴, end to end (2.3.4, requester 10-19).

"チャットが狭いから見づらい 左にロボット一人分くらいの余裕を残して残りをチャットの表示にしてほしい" /
"チャット広げた時はカメラの位置移動もしてね 選んでるボットが左の余白の部分に来るように".

The real `jui viz serve` in a throwaway HOME with two sessions (two rooms); session A's transcript has a wide table, a
long code line and two pictures (hist_images.py reads those). Arms: 広げる — the card runs from the left margin to the
right edge over the side panel and the site's header (issue #35), its head one row (the name left, the buttons right: issue
#36), and the camera flies so the robot's on-screen box (its visible meshes) is inside the
margin, waited on the camera tween's end, never on time; ← → bring the next robot into the margin too; the table
scrolls sideways; the prompt box is there; the pane follows a new answer; Esc goes back to the card's width and to the
camera's place before; the choice is kept in localStorage (a reload opens it wide) and the page works with
localStorage throwing; at 390 px it is the whole screen. Screenshots (light and dark, 1440 and 390) are for the eye.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import re
import struct
import subprocess
import sys
import time
import zlib

from common import ISOLATE, DESKTOP, LAUNCH_ARGS, PHONE, Watch, ago, dump, new_page, ready, stamp

A = "e2e00000-0000-4000-8000-0000000000c1"
B = "e2e00000-0000-4000-8000-0000000000c2"
CWD_A = "/work/wide-app"
CWD_B = "/work/wide-other"


def png(w, h, rgb):
    """A real PNG, a checkerboard (stdlib only)."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    rows = []
    for y in range(h):
        row = bytearray(b"\x00")
        for x in range(w):
            row += bytes(rgb) if (x // 20 + y // 20) % 2 == 0 else bytes(255 - c for c in rgb)
        rows.append(bytes(row))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))


PIC1 = png(320, 200, (220, 60, 60))
PIC2 = png(200, 300, (40, 120, 220))
GONE = "/nonexistent-e2e-viz/images/1.png"
TABLE = "\n".join(["| " + " | ".join(f"列{i}" for i in range(14)) + " |", "|" + "---|" * 14,
                   "| " + " | ".join(f"値{i}-とても長いセルの中身" for i in range(14)) + " |"])
CODE = "```\n" + "x = '" + "長い行" * 80 + "'\n```"

# The transcript's times go through stamp() (common.py): an hour before the run, not a fixed day (ticket
# 2026-10-20-jui-viz-hist-wide-robot-margin-red-on-integrate — from 02:00 JST on 10-20 the robots of a fixed 10-19 09:00Z
# were 8 hours old, drawn tired, and the margin arms went red: what was checked depended on the clock).


def records(who):
    def user(content, ts):
        return {"type": "user", "timestamp": ts, "message": {"role": "user", "content": content}}

    def asst(text, mid, ts):
        return {"type": "assistant", "timestamp": ts, "message": {"id": mid, "role": "assistant", "content": [{"type": "text", "text": text}]}}
    pic = lambda data: {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(data).decode()}}  # noqa: E731
    # B's session began 9 hours ago, so its robot is drawn tired (a wider pose): the → arm below keeps a tired robot inside
    # the margin too (ticket 2026-10-20-jui-viz-wide-history-tired-robot-leans-out-of-the-margin). A's began an hour ago.
    out = [user(f"{who} 最初の指示", stamp("2026-10-19T09:00:00Z") if who == "A" else ago(hours=9))]
    if who == "A":   # long bodies next to the labels (hist_labels.py: the time and the names must not fold)
        out.append(user("Another Claude session sent a message:\n<cross-session-message from=\"uds:/tmp/x.sock\" from-name=\"jsonui-agents-for-claude-dd\">\n"
                        + "もう 1 本お願いします（dd から）。" + "とても長い知らせの本文。" * 30 + "\n</cross-session-message>", stamp("2026-10-19T09:47:00Z")))
        out.append({"type": "assistant", "timestamp": stamp("2026-10-19T09:47:10Z"), "message": {"id": "mt", "role": "assistant", "content": [
            {"type": "tool_use", "id": "tu-long", "name": "Bash", "input": {"command": "cat " + "/very/long/path/segment" * 20 + " | head -n 200"}}]}})
        out.append({"type": "user", "timestamp": stamp("2026-10-19T09:47:11Z"), "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "tu-long", "content": "ok"}]}})
        out.append(user("依頼者の長い指示。" * 60, stamp("2026-10-19T09:47:20Z")))
        out.append({"type": "user", "timestamp": stamp("2026-10-19T09:47:30Z"), "isMeta": True, "message": {"role": "user", "content": "<system-reminder>\n" + "ハーネスの長い注記。" * 40 + "\n</system-reminder>"}})
        out.append({"type": "assistant", "timestamp": stamp("2026-10-19T09:47:40Z"), "message": {"id": "mt2", "role": "assistant", "content": [
            {"type": "tool_use", "id": "tu-err", "name": "mcp__long-tool-server__a_tool_with_a_rather_long_name_indeed", "input": {"description": "長い説明。" * 30}}]}})
        out.append({"type": "user", "timestamp": stamp("2026-10-19T09:47:41Z"), "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "tu-err", "content": "failed", "is_error": True}]}})
        out.append({"type": "assistant", "timestamp": stamp("2026-10-19T09:47:50Z"), "message": {"id": "mt3", "role": "assistant", "content": [
            {"type": "tool_use", "id": "tu-run", "name": "Bash", "input": {"command": "sleep 100 && " + "echo running " * 40}}]}})
    for k in range(6):
        out.append(asst(f"応答 {k}: " + "本文。" * 40, f"m{k}", stamp(f"2026-10-19T09:00:{10 + k:02d}Z")))
    if who == "A":
        out.append(user([pic(PIC1), pic(PIC2), {"type": "text", "text": f"[Image: source: {GONE}, original 640x480]\nこの 2 枚を見て"}], stamp("2026-10-19T09:01:00Z")))
        out.append(asst("## 表\n\n" + TABLE + "\n\n" + CODE, "m9", stamp("2026-10-19T09:01:10Z")))
    return out


def check(failures, cond, text, suite="hist-wide"):
    if not cond:
        failures.append(f"{suite}: {text}")


async def wait(page, js, timeout=20000, label=""):
    try:
        await page.wait_for_function(js, timeout=timeout, polling=100)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


SETTLED = "() => window.__dbg.focus().tween === false"
# The robot's box on the screen: the visible meshes under its root, eight corners each, projected; page pixels.
ROBOT_BOX = """(id) => {
  const D = window.__dbg, T = D.THREE, R = D.robots.find((x) => x.def.id === id);
  if (!R) return null;
  const c = document.getElementById('scene-canvas').getBoundingClientRect();
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  R.robot.root.updateMatrixWorld(true);
  R.robot.root.traverse((o) => {
    if (!o.isMesh) return;
    for (let x = o; x; x = x.parent) if (!x.visible) return;
    const b = new T.Box3().setFromObject(o);
    for (const x of [b.min.x, b.max.x]) for (const y of [b.min.y, b.max.y]) for (const z of [b.min.z, b.max.z]) {
      const v = new T.Vector3(x, y, z).project(D.camera);
      const px = c.left + (v.x + 1) / 2 * c.width, py = c.top + (1 - v.y) / 2 * c.height;
      x0 = Math.min(x0, px); x1 = Math.max(x1, px); y0 = Math.min(y0, py); y1 = Math.max(y1, py);
    }
  });
  return { x0: Math.round(x0), x1: Math.round(x1), y0: Math.round(y0), y1: Math.round(y1) };
}"""
CARD = """() => { const rb = document.getElementById('rb'), r = rb.getBoundingClientRect(), pane = rb.querySelector('[data-rb-hist]');
  const box = rb.querySelector('[data-h-compose]'), wrap = pane && pane.querySelector('.h-tablewrap');
  const btn = rb.querySelector('[data-rb-wide]');
  return { left: Math.round(r.left), right: Math.round(r.right), top: Math.round(r.top), bottom: Math.round(r.bottom),
    wide: rb.classList.contains('rb-wide'), btn: btn ? { hidden: btn.hidden, pressed: btn.getAttribute('aria-pressed'), text: btn.textContent } : null,
    compose: !!box && !box.hidden && box.getBoundingClientRect().height > 0 && rb.contains(box),
    tableScroll: wrap ? wrap.scrollWidth - wrap.clientWidth : null,
    atEnd: pane ? pane.scrollHeight - pane.scrollTop - pane.clientHeight < 30 : null,
    title: (document.getElementById('rb-title') || {}).textContent || '', vw: innerWidth, vh: innerHeight,
    headerBottom: Math.round(document.querySelector('.topbar').getBoundingClientRect().bottom),
    onTop: rb.contains(document.elementFromPoint(r.left + 40, r.top + 8)),
    titleLines: (() => { const t = document.getElementById('rb-title'); if (!t) return 0; const cs = getComputedStyle(t); return Math.round(t.getBoundingClientRect().height / (parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.3)); })() }; }"""
HEAD = """() => { const rb = document.getElementById('rb');
  const b = (sel) => { const e = rb.querySelector(sel); if (!e) return null; const r = e.getBoundingClientRect(); return { l: Math.round(r.left), r: Math.round(r.right), t: Math.round(r.top), b: Math.round(r.bottom) }; };
  return { name: b('#rb-title'), prev: b('[data-rb-step="-1"]'), next: b('[data-rb-step="1"]'), back: b('[data-rb-close]'), clock: b('[data-rb-clock]') }; }"""
TO_END = """() => { const pane = document.querySelector('[data-rb-hist]'); pane.scrollTop = pane.scrollHeight; pane.dispatchEvent(new Event('scroll')); }"""


class Stage:
    """The server, the two sessions and a browser, for this suite and hist_images.py."""

    async def start(self, pw, out, name):
        from run import free_port
        self.out = pathlib.Path(out) / name
        self.out.mkdir(parents=True, exist_ok=True)
        home = self.out / "home"
        home.mkdir(exist_ok=True)
        jt = pathlib.Path(__file__).resolve().parents[2]
        self.forward = jt / "jui_cli" / "viz" / "forward.py"
        port = free_port()
        (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
        self.paths = {}
        for sid, cwd, who in ((A, CWD_A, "A"), (B, CWD_B, "B")):
            t = home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", cwd) / f"{sid}.jsonl"
            t.parent.mkdir(parents=True, exist_ok=True)
            t.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records(who)))
            self.paths[sid] = t
        self.home = home
        self.base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
        self.log = open(self.out / "serve.log", "w")
        self.srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=self.log,
                                    stderr=subprocess.STDOUT, env=dict(self.base_env, HOME=str(home), JUI_VIZ_E2E="1"))
        self.url = f"http://127.0.0.1:{port}"
        self.browser = await pw.chromium.launch(args=LAUNCH_ARGS)
        self.watch = Watch(origin=self.url)
        import urllib.request
        for _ in range(400):
            try:
                urllib.request.urlopen(f"{self.url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        self.hook(A, CWD_A, hook_event_name="SessionStart", source="startup")
        self.hook(B, CWD_B, hook_event_name="SessionStart", source="startup")
        return self

    def hook(self, sid, cwd, **payload):
        body = {"session_id": sid, "cwd": cwd, "transcript_path": str(self.paths[sid]), "permission_mode": "default", **payload}
        subprocess.run([sys.executable, "-I", "-S", str(self.forward)], input=json.dumps(body).encode(),
                       capture_output=True, env=dict(self.base_env, HOME=str(self.home)), timeout=10)

    async def page(self, label, init=None, **opts):
        page = await new_page(self.browser, self.watch, label, **(opts or DESKTOP))
        if init:
            await page.add_init_script(init)
        await page.goto(self.url + "/")
        await ready(page)
        await wait(page, "() => window.__dbg.robots.length >= 2 && window.__dbg.robots.every((R) => R.path.length === 0)", timeout=30000, label="two robots seated")
        return page

    async def open_a(self, page):
        """A's card on its 応答の履歴 tab, the camera at A; returns A's label."""
        ra = await page.evaluate("() => window.__dbg.robots[0].def.id")
        await page.evaluate("(id) => window.__dbg.openRobot(id)", ra)
        await wait(page, "() => { const el = document.getElementById('rb'); return !el.hidden && !!el.querySelector('[data-rb-tab=\"history\"]'); }", label="the card")
        if await page.evaluate("() => document.querySelector('[data-rb-tab=\"history\"]').getAttribute('aria-selected')") != "true":
            await page.click('#rb [data-rb-tab="history"]')
        await wait(page, "() => document.querySelectorAll('[data-rb-hist] .h-item').length >= 3", label="the history")
        if "A 最初の指示" not in await page.evaluate("() => document.querySelector('[data-rb-hist]').textContent"):
            await page.click('#rb [data-rb-step="1"]')   # the other robot is A's
            await wait(page, "() => document.querySelector('[data-rb-hist]').textContent.includes('A 最初の指示')", label="A's history")
            ra = await page.evaluate("() => window.__dbg.focus().id")
        await wait(page, SETTLED, label="the camera at the robot")
        return ra

    async def stop(self, failures, suite):
        for line in self.watch.console:
            failures.append(f"{suite}: console: {line}")
        for u in self.watch.foreign:
            failures.append(f"{suite}: request outside the server: {u}")
        self.srv.terminate()
        try:
            self.srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.srv.kill()
        await self.browser.close()


async def run_hist_wide(pw, out, failures):
    t0 = time.monotonic()
    st = Stage()
    res: dict = {}
    try:
        await st.start(pw, out, "hist-wide")
        out = st.out
        page = await st.page("hist-wide")
        ra = await st.open_a(page)
        await page.evaluate(TO_END)
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await page.wait_for_timeout(500)
            await page.screenshot(path=str(out / f"narrow-1440-{scheme}.png"))
        await page.emulate_media(color_scheme="light")
        before_cam = await page.evaluate("() => window.__dbg.camera.position.toArray().map((v) => +v.toFixed(2))")
        res["narrow"] = await page.evaluate(CARD)
        res["headNarrow"] = await page.evaluate(HEAD)
        check(failures, (res["narrow"]["tableScroll"] or 0) > 0, f"at the card's width too, a many-column table scrolls sideways (cells keep their width): {res['narrow']['tableScroll']}")
        wbtn = page.locator("#rb [data-rb-wide]")
        if not (await wbtn.count() and await wbtn.is_visible()):
            check(failures, False, "a 広げる button on the history tab")
            return
        await wbtn.click()
        await wait(page, "() => document.getElementById('rb').classList.contains('rb-wide')", label="wide")
        await wait(page, SETTLED, label="the camera's flight to the margin")
        c = res["wide"] = await page.evaluate(CARD)
        margin = c["left"]
        box = res["wideRobot"] = await page.evaluate(ROBOT_BOX, ra)
        check(failures, 250 <= margin <= 460 and c["right"] >= c["vw"] - 20, f"the card runs from a margin of one robot to the right edge: {c}")
        check(failures, box and box["x0"] >= 0 and box["x1"] <= margin and box["y0"] >= c["top"] - 80 and box["y1"] <= c["bottom"],
              f"the robot is inside the left margin: {box} margin {margin}")
        check(failures, c["top"] < c["headerBottom"] and c["onTop"] and res["narrow"]["top"] >= res["narrow"]["headerBottom"],
              f"wide, the card goes over the site's header (issue #35); at the card's width it stays below: wide {c}, narrow {res['narrow']}")
        hn, hw = res["headNarrow"], res["headWide"] = res.get("headNarrow"), await page.evaluate(HEAD)
        mid = lambda x: (x["t"] + x["b"]) / 2
        check(failures, all(hw.values()) and all(abs(mid(hw[k]) - mid(hw["back"])) < 12 for k in ("prev", "next", "clock"))
              and hw["name"]["r"] <= hw["prev"]["l"] and hw["prev"]["r"] <= hw["next"]["l"] <= hw["back"]["l"] <= hw["clock"]["l"],
              f"wide, the head is one row: the name left, then ‹ › 「← 3D に戻る」 退勤 on the right (issue #36): {hw}")
        check(failures, hn and all(hn.values()) and hn["clock"]["b"] <= hn["back"]["t"] and hn["name"]["b"] <= hn["clock"]["t"],
              f"at the card's width the head stays stacked: the name, 退勤, then ‹ › and 「← 3D に戻る」: {hn}")
        check(failures, c["compose"], f"the prompt box is in the wide card: {c}")
        check(failures, (c["tableScroll"] or 0) > 0, f"the wide table scrolls sideways: {c['tableScroll']}")
        check(failures, c["btn"] and c["btn"]["pressed"] == "true" and c["btn"]["text"] == "元の幅に戻す", f"the button says it is pressed: {c['btn']}")
        check(failures, res["narrow"]["titleLines"] <= 2 and c["titleLines"] <= 2, f"the card's title stays readable (2 lines at most): narrow {res['narrow']['titleLines']}, wide {c['titleLines']}")
        await page.evaluate(TO_END)
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await page.wait_for_timeout(500)
            await page.screenshot(path=str(out / f"wide-1440-{scheme}.png"))
        await page.emulate_media(color_scheme="light")
        # follows a new answer while wide (the reader at the bottom)
        with open(st.paths[A], "a") as f:
            f.write(json.dumps({"type": "assistant", "timestamp": stamp("2026-10-19T09:02:00Z"),
                                "message": {"id": "m20", "role": "assistant", "content": [{"type": "text", "text": "広げたまま届いた応答"}]}}, ensure_ascii=False) + "\n")
        await wait(page, "() => document.querySelector('[data-rb-hist]').textContent.includes('広げたまま届いた応答')", timeout=10000, label="a new answer while wide")
        await page.wait_for_timeout(300)
        res["follow"] = (await page.evaluate(CARD))["atEnd"]
        check(failures, res["follow"], "the wide pane follows a new answer")
        # ← → : the next robot in the margin too, and back
        await page.focus("#rb [data-rb-wide]")
        await page.keyboard.press("ArrowRight")
        await wait(page, f"() => window.__dbg.focus().id !== '{ra}'", label="the next robot")
        await wait(page, SETTLED, label="the camera's flight to the next robot")
        rb_id = await page.evaluate("() => window.__dbg.focus().id")
        c2 = await page.evaluate(CARD)
        box2 = res["wideNext"] = await page.evaluate(ROBOT_BOX, rb_id)
        tired = res["tired"] = {"A": (await page.evaluate("(id) => window.__dbg.condition(id).tired", ra)),
                                "next": (await page.evaluate("(id) => window.__dbg.condition(id).tired", rb_id))}
        check(failures, tired == {"A": False, "next": True}, f"A is fresh and the next robot (B, 9 hours) is tired, as the scene means: {tired}")
        check(failures, c2["wide"] and box2 and box2["x0"] >= 0 and box2["x1"] <= c2["left"], f"→: the next robot is inside the margin too: {box2} margin {c2['left']}")
        await page.keyboard.press("ArrowLeft")
        await wait(page, f"() => window.__dbg.focus().id === '{ra}'", label="back to A")
        await wait(page, SETTLED, label="the camera back at A")
        # Esc: the card's width and the camera where it was
        await page.keyboard.press("Escape")
        await wait(page, "() => !document.getElementById('rb').classList.contains('rb-wide')", label="narrow again")
        await wait(page, SETTLED, label="the camera back")
        after_cam = res["camBack"] = await page.evaluate("() => window.__dbg.camera.position.toArray().map((v) => +v.toFixed(2))")
        c3 = res["narrowAgain"] = await page.evaluate(CARD)
        check(failures, not c3["wide"] and abs(c3["left"] - res["narrow"]["left"]) <= 2 and not await page.evaluate("() => document.getElementById('rb').hidden"),
              f"Esc: back to the card's width, the card still open: {c3}")
        res["camBefore"] = before_cam
        check(failures, max(abs(a - b) for a, b in zip(before_cam, after_cam)) < 0.05, f"Esc: the camera is back where it was: {before_cam} -> {after_cam}")
        # kept: wide again, a reload opens the history wide
        await wbtn.click()
        await wait(page, SETTLED, label="wide again")
        res["pref"] = await page.evaluate("() => { try { return localStorage.getItem('agent-view:hist-wide'); } catch (e) { return 'blocked'; } }")
        check(failures, res["pref"] == "on", f"the choice is kept: {res['pref']}")
        await page.reload()
        await ready(page)
        await wait(page, "() => window.__dbg.robots.length >= 2 && window.__dbg.robots.every((R) => R.path.length === 0)", timeout=30000, label="robots after the reload")
        await st.open_a(page)
        res["keptWide"] = (await page.evaluate(CARD))["wide"]
        check(failures, res["keptWide"], "after a reload the history opens wide (localStorage)")
        # 2.3.7 (requester 10-20): 今の様子 widens too, and the width is one state for both tabs, kept across a switch
        tab = lambda name: page.click(f'#rb [data-rb-tab="{name}"]')
        shown = "(t) => document.querySelector(`#rb [data-rb-tab=\"${t}\"]`).getAttribute('aria-selected') === 'true'"
        await page.keyboard.press("Escape")
        await wait(page, "() => !document.getElementById('rb').classList.contains('rb-wide')", label="narrow before the tabs")
        await wait(page, SETTLED, label="the camera back before the tabs")
        await tab("now")
        await page.wait_for_function(shown, arg="now")
        t1 = res["nowNarrow"] = await page.evaluate(CARD)
        check(failures, not t1["wide"] and t1["btn"] and not t1["btn"]["hidden"] and t1["btn"]["text"] == "広げる",
              f"今の様子 has the 広げる button too, narrow while the history was narrowed: {t1}")
        await wbtn.click()
        await wait(page, "() => document.getElementById('rb').classList.contains('rb-wide')", label="wide on 今の様子")
        await wait(page, SETTLED, label="the camera's flight (今の様子)")
        t2 = res["nowWide"] = await page.evaluate(CARD)
        box_now = res["nowWideRobot"] = await page.evaluate(ROBOT_BOX, ra)
        check(failures, t2["wide"] and 250 <= t2["left"] <= 460 and t2["btn"]["pressed"] == "true" and box_now and box_now["x1"] <= t2["left"],
              f"広げる on 今の様子: the card wide, the robot in the margin: {t2} {box_now}")
        await page.screenshot(path=str(out / "now-wide-1440.png"))
        await tab("history")
        await page.wait_for_function(shown, arg="history")
        t3 = res["histAfterNowWide"] = await page.evaluate(CARD)
        check(failures, t3["wide"] and t3["btn"]["pressed"] == "true", f"widened on 今の様子, 応答の履歴 is wide too: {t3}")
        await wbtn.click()
        await wait(page, "() => !document.getElementById('rb').classList.contains('rb-wide')", label="narrow on 応答の履歴")
        await wait(page, SETTLED, label="the camera back (応答の履歴)")
        await tab("now")
        await page.wait_for_function(shown, arg="now")
        t4 = res["nowAfterHistNarrow"] = await page.evaluate(CARD)
        check(failures, not t4["wide"] and t4["btn"]["pressed"] == "false", f"narrowed on 応答の履歴, 今の様子 is narrow too: {t4}")
        res["prefAfterTabs"] = await page.evaluate("() => localStorage.getItem('agent-view:hist-wide')")
        check(failures, res["prefAfterTabs"] == "off", f"one kept choice for both tabs: {res['prefAfterTabs']}")
        await page.close()
        # localStorage throwing: it still widens (and narrows)
        p3 = await st.page("hist-wide-nostorage", init="Object.defineProperty(window, 'localStorage', { get() { throw new Error('blocked'); } });")
        await st.open_a(p3)
        await p3.click("#rb [data-rb-wide]")
        await wait(p3, SETTLED, label="wide (no storage)")
        w3 = (await p3.evaluate(CARD))["wide"]
        await p3.keyboard.press("Escape")
        await wait(p3, SETTLED, label="narrow (no storage)")
        n3 = not (await p3.evaluate(CARD))["wide"]
        res["noStorage"] = [w3, n3]
        check(failures, w3 and n3, f"wide and back with localStorage throwing: {res['noStorage']}")
        await p3.close()
        # 390 px: the whole screen
        for scheme in ("light", "dark"):
            ph = await st.page(f"hist-wide-phone-{scheme}", **dict(PHONE, color_scheme=scheme))
            await st.open_a(ph)
            await ph.evaluate(TO_END)
            await ph.wait_for_timeout(400)
            await ph.screenshot(path=str(out / f"narrow-390-{scheme}.png"))
            await ph.click("#rb [data-rb-wide]")
            await wait(ph, SETTLED, label="wide (phone)")
            await ph.evaluate(TO_END)
            await ph.wait_for_timeout(400)
            c = res[f"phone-{scheme}"] = await ph.evaluate(CARD)
            check(failures, c["wide"] and c["left"] == 0 and c["top"] == 0 and c["right"] == c["vw"] and c["bottom"] == c["vh"] and c["compose"],
                  f"390 px {scheme}: the whole screen, the prompt box there: {c}")
            check(failures, not await ph.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth"), f"390 px {scheme}: no horizontal scroll")
            check(failures, c["titleLines"] <= 2, f"390 px {scheme}: the card's title stays readable: {c['titleLines']} lines")
            await ph.screenshot(path=str(out / f"wide-390-{scheme}.png"))
            await ph.close()
    except Exception as e:
        failures.append(f"hist-wide: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        if getattr(st, "srv", None) is not None:
            await st.stop(failures, "hist-wide")
        print(f"  hist-wide: {time.monotonic() - t0:.0f}s", flush=True)
        (pathlib.Path(st.out if hasattr(st, "out") else out) / "hist-wide-results.json").write_text(dump(res) + "\n")
