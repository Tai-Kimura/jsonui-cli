"""The Slack sorting factory (docs/plans/2026-11-02-viz-slack-intake-design.md §5–§7). Runs with `--only slack-room`.

The real `jui viz serve` in a throwaway HOME on a free port, its slack.json naming a folder in that HOME, the folder
filled by hand as stage 1 would fill it (projects/<id>/*.json, tasks/*.json); the real forward.py for the hooks, and
a stand-in for channel.py (hello, then /channel/poll), as send_prompt.py does — no claude, no Slack, no network.
Sessions: BOT (cwd in the folder: the factory's robot), DEV (a project's, started with --channels) and PLAIN (started
naming no channel); each "process" a sleeping python whose argv carries the flags, named by a session file.
Checked:
  * the header's Slack button, after デバイス, its count the tasks waiting on a person; the demo page has none;
  * the robot's room is no floor's (the rooms the 3D has) and BOT is the factory's robot;
  * the room over the whole page (the floors' 3D not drawn under it): the 3D with the robot and a bin per project, the
    robot's line, what was sorted, the whiteboard's six lanes (やり取り中 first) with each note in its lane;
  * a talking note shows the exchange so far; 下書きに上げる raises it; a note's id is copied by its button;
  * a later task tied to an ended one (relatedTaskId): 追加の連絡あり on the earlier note, の続き on the later;
  * a prompt saved by hand is marked; a message the robot adds after it is shown as come after;
  * a message put in projects/ → BOT's channel gets the task prompt with its path and DEV's id; it rides the belt;
  * what is typed on a draft survives the task file changing under it and the push after it; 保存 writes it;
  * 開始待ちにする, then on the ready note DEV chosen (PLAIN's option disabled with why), 開始: DEV's channel gets the
    prompt exactly, the note moves to 作業中; DEV busy then idle → 作業終了 by itself; 完了 → 完了;
  * ロボットに直しを頼む → BOT's channel; the box to tell the robot → BOT's channel;
  * the prompts dialog: the config's words in it; saved → slack.json has them, its other keys as they were, 0600;
  * the copy of the start command when no session fits; Esc closes the dialog, then the room, the focus back;
  * stills: light, dark, and a phone's width (nothing sideways).
No console error; nothing outside the server.
"""

from __future__ import annotations

import http.client
import json
import os
import pathlib
import stat
import subprocess
import sys
import time

from common import DESKTOP, ISOLATE, LAUNCH_ARGS, PHONE, T, Watch, dump, new_page, ready, shot

BOT = "e2e00000-0000-4000-8000-0000000000f1"
DEV = "e2e00000-0000-4000-8000-0000000000f2"
PLAIN = "e2e00000-0000-4000-8000-0000000000f3"
CHANNELS = ["--channels", "plugin:jui-viz@jsonui"]
STATE = "() => window.__dbg.sfState()"
CONTRAST = """() => {
  // WCAG contrast of every piece of text on every note: the text's colour (its alpha and the opacities above it) over the
  // first background under it, made opaque over the note's own colour
  const rgb = (c) => { const m = c.match(/[\\d.]+/g).map(Number); return { r: m[0], g: m[1], b: m[2], a: m.length > 3 ? m[3] : 1 }; };
  const over = (f, b) => ({ r: f.r * f.a + b.r * (1 - f.a), g: f.g * f.a + b.g * (1 - f.a), b: f.b * f.a + b.b * (1 - f.a), a: 1 });
  const lum = (c) => { const ch = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * ch(c.r) + 0.7152 * ch(c.g) + 0.0722 * ch(c.b); };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const rows = [];
  for (const note of document.querySelectorAll('#sf-wb .sf-note')) {
    const paper = rgb(getComputedStyle(note).backgroundColor);
    const walker = document.createTreeWalker(note, NodeFilter.SHOW_TEXT);
    for (let t = walker.nextNode(); t; t = walker.nextNode()) {
      const el = t.parentElement;
      if (!t.textContent.trim() || el.closest('option, select') && el.tagName === 'OPTION' || !el.getClientRects().length) continue;
      let bg = null, op = 1;
      for (let e = el; e && e !== note.parentElement; e = e.parentElement) {
        const cs = getComputedStyle(e); op *= Number(cs.opacity);
        if (!bg) { const c = rgb(cs.backgroundColor); if (c.a > 0) bg = e === note ? paper : over(c, paper); }
      }
      const fg = rgb(getComputedStyle(el).color); fg.a *= op;
      rows.push({ status: note.dataset.status, cls: el.className || el.tagName, size: getComputedStyle(el).fontSize, ratio: Math.round(ratio(over(fg, bg || paper), bg || paper) * 100) / 100 });
    }
  }
  return rows;
}"""


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


def message(orch, project, name, text, user="U1", channel="C1"):
    path = orch / "projects" / project / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"workspace": "tanosys", "channel": channel, "user": user, "ts": name.split("-")[0], "text": text,
                                "permalink": "", "removedFiles": 0, "redactions": 0,
                                "router": {"adapter": "haiku", "choice": project, "confidence": 0.92}}, ensure_ascii=False))
    return f"projects/{project}/{name}"


def task(orch, tid, status, title, prompt, project="shop", sources=(), **extra):
    data = {"id": tid, "title": title, "projectId": project, "sources": list(sources), "prompt": prompt,
            "target": {"sessionName": "", "sessionId": None}, "launchCommand": None, "status": status, "createdAt": 1793500000000, **extra}
    (orch / "tasks" / f"{tid}.json").write_text(json.dumps(data, ensure_ascii=False))


def read_task(orch, tid):
    return json.loads((orch / "tasks" / f"{tid}.json").read_text())


async def run_sorting_factory(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "slack-room"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    state = home / ".local" / "state" / "jui-viz"
    state.mkdir(parents=True, exist_ok=True)
    orch = home / "slack-orchestration"
    (orch / "tasks").mkdir(parents=True, exist_ok=True)
    (orch / "_unsorted").mkdir(exist_ok=True)
    (orch / "_unsorted" / "1793500100-tanosys-C9.json").write_text("{}")
    cwds = {BOT: str(orch), DEV: "/work/shop-app", PLAIN: "/work/booking-site"}
    (state / "slack.json").write_text(json.dumps({
        # manual only and no workspace: stage 1's fetch (今すぐ取る) runs and reaches nothing outside
        "orchestrationDir": "~/slack-orchestration", "schedule": {"everyHours": 0, "at": "09:00"},
        "source": {"mode": "api", "workspaces": [], "_e2eKept": "x" + "oxp-e2e"},
        "router": {"adapter": "haiku", "confidenceMin": 0.6,
                   "prompt": {"instructions": "メッセージをプロジェクトに振り分ける", "projects": {"shop": "ショップのアプリ", "booking": "予約サイト"}, "chitchat": "あいさつや雑談"}},
        "taskPrompt": ""}, ensure_ascii=False))
    os.chmod(state / "slack.json", 0o600)
    m1 = message(orch, "shop", "1793500001-tanosys-C1.json", "カートの合計金額が税込みで表示されない。明日のリリースまでに直してほしい")
    message(orch, "shop", "1793500002-tanosys-C1.json", "上の件、iOS だけで起きています", user="U2")
    message(orch, "booking", "1793500003-tanosys-C2.json", "予約の確認メールの日付が 1 日ずれている")
    task(orch, "T-0001", "draft", "カートの税込み表示", "ショップのカート画面で、合計金額を税込みで出すように直してください。", sources=[m1])
    task(orch, "T-0003", "ready", "予約メールの日付", "予約の確認メールの日付が 1 日ずれる件を調べて直してください。", project="booking")
    task(orch, "T-0002", "draft", "ドキュメントの誤字", "ドキュメントサイトの誤字を直してください。", project="docs",
         target={"sessionName": "docs", "sessionId": None}, launchCommand="cd ~/work/docs && claude --channels plugin:jui-viz@jsonui")
    task(orch, "T-0004", "working", "商品一覧の並び順", "商品一覧の並び順を新しい順にしてください。", target={"sessionName": "shop", "sessionId": DEV},
         startedAt=1793500200000)
    t1 = message(orch, "booking", "1793500005-tanosys-C2.json", "決済画面の文言、どちらがいいか相談させてください")
    t2 = message(orch, "booking", "1793500006-tanosys-C2.json", "A 案の方が良さそうですが、もう少し考えます", user="U3")
    task(orch, "T-0009", "talking", "決済画面の文言の相談", "", project="booking", sources=[t1, t2], threads=["1793500005"])
    task(orch, "T-0010", "draft", "ログイン画面の文言（追加）", "ログイン画面の英語の文言も直してください。", relatedTaskId="T-0005")
    task(orch, "T-0005", "ended", "ログイン画面の文言", "ログイン画面の文言を直してください。", startedAt=1793500300000, endedAt=1793500400000,
         target={"sessionName": "shop", "sessionId": None})
    task(orch, "T-0006", "done", "フッターのリンク", "フッターのリンク切れを直してください。", startedAt=1, endedAt=2, doneAt=3,
         target={"sessionName": "shop", "sessionId": None})
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    sessions_dir = home / ".claude" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    stand_ins: list = []

    def session_process(sid, *args):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(900)", *args],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        stand_ins.append(proc)
        (sessions_dir / f"{proc.pid}.json").write_text(json.dumps({"pid": proc.pid, "sessionId": sid, "cwd": cwds[sid], "kind": "interactive",
                                                                  "entrypoint": "cli", "status": "idle", "procStart": f"t{proc.pid}"}))
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def check(cond, text):
        if not cond:
            failures.append(f"slack-room: {text}")

    def hook(sid, **payload):
        subprocess.run([sys.executable, "-I", "-S", str(forward)], timeout=10, capture_output=True, env=dict(base_env, HOME=str(home)),
                       input=json.dumps({"session_id": sid, "cwd": cwds[sid], "transcript_path": "/work/none.jsonl", "permission_mode": "default", **payload}).encode())

    def local(method, path, body=None, timeout=5):
        token = json.loads((state / "server.json").read_text())["token"]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
        try:
            headers = {"X-Jui-Viz-Token": token}
            data = None
            if body is not None:
                data = json.dumps(body).encode()
                headers["Content-Type"] = "application/json"
            conn.request(method, path, body=data, headers=headers)
            r = conn.getresponse()
            return r.status, json.loads(r.read() or b"null")
        finally:
            conn.close()

    def poll(channel, want=1, within=30):
        """What the server queued for a channel, as channel.py takes it (one poll may come back empty)."""
        got: list = []
        end = time.time() + within
        while len(got) < want and time.time() < end:
            _, polled = local("GET", f"/channel/poll?channelId={channel}", timeout=within + 5)
            got += [p["text"] for p in (polled or {}).get("prompts", [])]
        return got

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
        session_process(BOT, *CHANNELS)
        session_process(DEV, *CHANNELS)
        session_process(PLAIN)
        for sid in (BOT, DEV, PLAIN):
            hook(sid, hook_event_name="SessionStart", source="startup")
        channels = {}
        for sid in (BOT, DEV, PLAIN):
            status, hello = local("POST", "/channel/hello", {"ppid": 1, "cwd": "/", "sessionId": sid, "version": "2", "accepts": ["prompt"], "via": "plugin"})
            check(status == 200, f"hello {sid[-2:]}: {status}")
            channels[sid] = hello["channelId"]

        # the robot is told of the three messages no task names... (two: m1 is T-0001's)
        told = poll(channels[BOT])
        res["told"] = [t[:200] for t in told]
        check(len(told) == 1 and "projects/shop/1793500002-tanosys-C1.json" in told[0] and "projects/booking/1793500003-tanosys-C2.json" in told[0]
              and m1 not in told[0].split("\n\n")[1] and f"sessionId={DEV}" in told[0] and T("srv.slack.task_prompt") in told[0],
              f"the robot told of the two new messages with the sessions and the default task prompt: {res['told']}")

        watch = Watch(origin=url)
        page = await new_page(browser, watch, "slack-room", **DESKTOP)
        await page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=url)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => { const b = document.getElementById('btn-slack'); return b && !b.hidden; }", label="the Slack button")
        head = res["button"] = await page.evaluate("""() => { const b = document.getElementById('btn-slack'), d = document.getElementById('btn-devices');
          return { text: b.textContent, label: b.getAttribute('aria-label'), afterDevices: d.nextElementSibling === b }; }""")
        check(head["text"] == T("sf.button.count", count=5) and head["label"] == T("sf.button.aria", n=5) and head["afterDevices"],
              f"the button after デバイス, five tasks waiting on a person (three drafts, a ready one, an ended one; talking is the robot's): {head}")
        bot = await page.evaluate("(sid) => window.__dbg.labelOfSession(sid)", BOT)
        dev = await page.evaluate("(sid) => window.__dbg.labelOfSession(sid)", DEV)
        rooms = await page.evaluate("(ls) => ls.map((l) => window.__dbg.robotProject(l))", [bot, dev])
        st = await page.evaluate(STATE)
        res["rooms"] = {"bot": rooms[0], "dev": rooms[1], "floors": st["rooms"]}
        check(rooms[0] not in st["rooms"] and rooms[1] in st["rooms"], f"the robot's room is no floor's: {res['rooms']}")

        # the room
        await page.click("#btn-slack")
        await wait(page, "() => window.__dbg.sfState().open && window.__dbg.sfState().robot && window.__dbg.sfState().bins.length === 2", label="the room with its robot and two bins")
        st = res["open"] = await page.evaluate(STATE)
        check(st["covers"] and st["robot"] == bot and st["focus"] == "sf-back", f"over the page, BOT the robot, the focus on back: {st}")
        check(st["lanes"] == {"talking": ["T-0009"], "draft": ["T-0001", "T-0002", "T-0010"], "ready": ["T-0003"], "working": ["T-0004"], "ended": ["T-0005"], "done": ["T-0006"]},
              f"each note in its lane: {st['lanes']}")
        check(sorted((b["project"], b["n"]) for b in st["bins"]) == [("booking", 3), ("shop", 2)], f"a bin per project: {st['bins']}")
        texts = res["texts"] = await page.evaluate("""() => ({ lanes: [...document.querySelectorAll('#sf-wb .sf-lane h4')].map((h) => h.firstChild.textContent.trim()),
          flow: document.getElementById('sf-flow-body').textContent, robot: document.getElementById('sf-robot').textContent,
          seen: ['sf-canvas', 'sf-wb', 'sf-say'].map((id) => { const r = document.getElementById(id).getBoundingClientRect(); const e = document.elementFromPoint(r.left + r.width / 2, r.top + Math.min(r.height / 2, 30));
            return !!e && (e.id === id || !!e.closest('#' + id)); }) })""")
        check(texts["lanes"] == [T(f"sf.lane.{k}") for k in ("talking", "draft", "ready", "working", "ended", "done")], f"the lanes: {texts['lanes']}")
        check(T("sf.flow.counts", total=5, pending=0, unsorted=1) in texts["flow"] and "カートの合計金額" in texts["flow"] and bot in texts["robot"],
              f"what was sorted and the robot: {texts['flow'][:200]} / {texts['robot']}")
        lanes_in = res["lanes-in"] = await page.evaluate("() => { const b = document.querySelector('.sf-board'); return { scroll: b.scrollWidth, client: b.clientWidth }; }")
        check(lanes_in["scroll"] <= lanes_in["client"], f"the six lanes fit the board at 1440: {lanes_in}")
        check(all(texts["seen"]), f"the 3D, the board and the box are on the page, not under something: {texts['seen']}")
        marks = res["marks"] = await page.evaluate("""() => { const t = (id, q) => [...document.querySelectorAll(`#sf-wb [data-sf-task="${id}"] ${q}`)].map((e) => e.textContent);
          return { talk: t('T-0009', '.sf-src li'), talkOpen: document.querySelector('#sf-wb [data-sf-task="T-0009"] .sf-src').open,
            more: t('T-0005', '.sf-mark-more'), follows: t('T-0010', '.sf-mark'), id: t('T-0001', '.sf-id') }; }""")
        check(len(marks["talk"]) == 2 and "A 案の方が良さそう" in marks["talk"][1] and marks["talkOpen"], f"the talking note shows the exchange: {marks}")
        check(marks["more"] == [T("sf.note.more", id="T-0010", title="ログイン画面の文言（追加）")] and marks["follows"] == [T("sf.note.follows", id="T-0005", title="ログイン画面の文言")],
              f"the tie both ways: {marks}")
        # every lane and note inside the whiteboard's frame: the board scrolls in itself, the column around it does not
        INSIDE = """() => { const wb = document.getElementById('sf-wb'), b = wb.getBoundingClientRect(), col = document.querySelector('.sf-board');
          const out = [...wb.querySelectorAll('.sf-lane, .sf-note')].filter((e) => { const r = e.getBoundingClientRect(); return r.left < b.left - 1 || r.right > b.right + 1; }).map((e) => e.dataset.sfTask || e.dataset.sfLane);
          const hidden = [...wb.querySelectorAll('.sf-note')].filter((e) => { const r = e.getBoundingClientRect(); return r.bottom > b.bottom + 1 || r.top < b.top - 1; }).map((e) => e.dataset.sfTask);
          return { sideways: out, below: hidden, wbScrolls: wb.scrollHeight > wb.clientHeight, colScroll: col.scrollHeight - col.clientHeight, inPage: b.right <= window.innerWidth && b.bottom <= window.innerHeight + 1, zoom: wb.style.zoom }; }"""
        inside = res["inside"] = await page.evaluate(INSIDE)
        check(not inside["sideways"] and inside["colScroll"] <= 1 and inside["inPage"] and (not inside["below"] or inside["wbScrolls"]),
              f"the lanes and notes in the whiteboard, what is below scrolls in it: {inside}")
        async def contrast(theme):
            rows = await page.evaluate(CONTRAST)
            low = [r for r in rows if r["ratio"] < 4.5]
            by = {}
            for r in rows:
                k = f"{r['status']} {r['cls']}"
                by[k] = min(by.get(k, 99), r["ratio"])
            res[f"contrast-{theme}"] = by
            check(rows and not low, f"{theme}: every text on the notes at least 4.5:1: {low[:6]}")
        await contrast("light")
        await page.wait_for_timeout(800)
        await shot(page, "slack-room-light", out, failures)
        # the whole board at once: every note in view, Esc back to the room (not out of it)
        await page.click("#sf-full")
        await page.wait_for_timeout(400)
        full = res["full"] = await page.evaluate(INSIDE)
        left = await page.evaluate("() => getComputedStyle(document.querySelector('.sf-left')).display")
        check(not full["sideways"] and not full["below"] and left == "none" and await page.evaluate("() => document.getElementById('sf-full').getAttribute('aria-pressed') === 'true'"),
              f"the whole board: every note in view, the left side away: {full} {left}")
        await shot(page, "slack-room-full", out, failures)
        await page.keyboard.press("Escape")
        back = await page.evaluate("() => ({ open: window.__dbg.sfState().open, full: document.getElementById('sf').dataset.board, zoom: document.getElementById('sf-wb').style.zoom })")
        check(back == {"open": True, "full": "", "zoom": ""}, f"Esc leaves the whole board, the room stays: {back}")
        await page.wait_for_timeout(500)
        tag_rects = res["tags"] = await page.evaluate("() => [...document.querySelectorAll('#sf-labels .sf-tag')].filter((e) => !e.hidden).map((e) => { const r = e.getBoundingClientRect(); return [e.textContent, Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.bottom)]; })")
        overlap = len(tag_rects) >= 2 and any(a[1] < b[3] and b[1] < a[3] and a[2] < b[4] and b[2] < a[4] for i, a in enumerate(tag_rects) for b in tag_rects[i + 1:])
        check(len(tag_rects) >= 2 and not overlap, f"the bins' tags apart: {tag_rects}")
        await page.click('#sf-wb [data-sf-task="T-0001"] .sf-id')
        copied = await page.evaluate("() => navigator.clipboard.readText()")
        check(copied == "T-0001", f"the id copied: {copied!r}")
        await page.click('#sf-wb [data-sf-task="T-0009"] [data-sf-op="draft"]')
        await wait(page, "() => window.__dbg.sfState().lanes.draft.includes('T-0009')", label="T-0009 raised to a draft")
        check(read_task(orch, "T-0009")["status"] == "draft", "the file says draft")

        # stage 1's state and 今すぐ取る (POST /api/slack/fetch)
        await wait(page, f"() => document.getElementById('sf-intake').textContent.includes({json.dumps(T('sf.intake.manual'))})", label="the intake's line")
        await page.click("#sf-fetch")
        await wait(page, f"() => document.getElementById('sf-intake').textContent.startsWith({json.dumps(T('sf.intake.last', at='').strip())}) && !document.getElementById('sf-intake').textContent.includes({json.dumps(T('sf.intake.never'))})",
                   timeout=15000, label="the last fetch's time after 今すぐ取る")
        res["intake"] = await page.evaluate("() => document.getElementById('sf-intake').textContent")
        # a message comes: the robot is told of it, a parcel rides the belt
        hook(BOT, hook_event_name="UserPromptSubmit", prompt="x")
        hook(BOT, hook_event_name="Stop")
        m4 = message(orch, "shop", "1793500004-tanosys-C1.json", "商品詳細の画像が出ない")
        await wait(page, "() => window.__dbg.sfState().parcels.length > 0", timeout=15000, label="a parcel on its way")
        told = poll(channels[BOT])
        check(len(told) == 1 and m4 in told[0], f"the robot told of the new one only: {[t[:160] for t in told]}")
        await wait(page, "() => window.__dbg.sfState().parcels.length === 0 && window.__dbg.sfState().bins.find((b) => b.project === 'shop').n === 3",
                   timeout=20000, label="the parcel in shop's bin")

        # what is typed on a draft is kept
        note = '#sf-wb [data-sf-task="T-0001"]'
        await page.fill(f"{note} [data-sf-prompt]", "TYPED: 税込みで出す。テストも足す")
        t = read_task(orch, "T-0001")
        t["title"] = "カートの税込み表示（ロボットが直した）"
        (orch / "tasks" / "T-0001.json").write_text(json.dumps(t, ensure_ascii=False))
        await page.wait_for_timeout(3500)                     # the scan and its push
        check(await page.eval_on_selector(f"{note} [data-sf-prompt]", "(e) => e.value") == "TYPED: 税込みで出す。テストも足す", "typed text kept under the hand")
        await page.click("#sf-flow-h")                        # the hand off the note: it is drawn again with what was typed
        await wait(page, f"() => document.querySelector('{note} .sf-note-title').textContent.includes('ロボットが直した')", label="the note drawn again")
        check(await page.eval_on_selector(f"{note} [data-sf-prompt]", "(e) => e.value") == "TYPED: 税込みで出す。テストも足す", "typed text kept through the redraw")
        await page.click(f"{note} [data-sf-op='save']")
        await wait(page, f"() => document.querySelector('{note} .sf-note-said').textContent === {json.dumps(T('sf.said.save'))}", label="saved")
        t = read_task(orch, "T-0001")
        check(t["prompt"] == "TYPED: 税込みで出す。テストも足す" and t["promptEditedByUser"] is True and t["sourcesAtEdit"] == [m1], f"保存 wrote the prompt, marked by hand: {t}")
        await wait(page, f"() => document.querySelector('{note}').textContent.includes({json.dumps(T('sf.note.edited'))})", label="the hand-edited mark")
        t["sources"].append(m4)                                 # the robot adds a message to it, leaving the prompt
        (orch / "tasks" / "T-0001.json").write_text(json.dumps(t, ensure_ascii=False))
        await wait(page, f"() => (document.querySelector('{note} .sf-mark-late') || {{}}).textContent === {json.dumps(T('sf.note.late', n=1))} && document.querySelector('{note} .sf-late').textContent.includes('商品詳細の画像')",
                   label="what came after the hand's prompt shown")
        await page.click(f"{note} [data-sf-op='ready']")
        await wait(page, "() => window.__dbg.sfState().lanes.ready.includes('T-0001')", label="T-0001 ready")

        # start the ready one on DEV
        note = '#sf-wb [data-sf-task="T-0003"]'
        opts = res["options"] = await page.evaluate(f"""() => [...document.querySelectorAll('{note} [data-sf-target] option')].map((o) => ({{ v: o.value, d: o.disabled, t: o.textContent }}))""")
        check([o["v"] for o in opts] == ["", DEV, PLAIN] and not opts[1]["d"] and opts[2]["d"] and T("sf.target.cannot") in opts[2]["t"],
              f"DEV can be chosen, PLAIN not and says why: {opts}")
        await page.select_option(f"{note} [data-sf-target]", DEV)
        await page.click(f"{note} [data-sf-op='start']")
        got = poll(channels[DEV])
        check(got == ["予約の確認メールの日付が 1 日ずれる件を調べて直してください。"], f"DEV got the prompt exactly: {got}")
        await wait(page, "() => window.__dbg.sfState().lanes.working.includes('T-0003')", label="T-0003 working")
        t = read_task(orch, "T-0003")
        check(t["status"] == "working" and t["target"]["sessionId"] == DEV and t["startedAt"] > 0, f"the file says working on DEV: {t}")
        hook(DEV, hook_event_name="UserPromptSubmit", prompt="予約の確認メール")
        await page.wait_for_timeout(2600)
        check(read_task(orch, "T-0003")["status"] == "working", "still working while DEV works")
        hook(DEV, hook_event_name="Stop")
        await wait(page, "() => ['T-0003', 'T-0004'].every((id) => window.__dbg.sfState().lanes.ended.includes(id))", timeout=15000,
                   label="T-0003 and T-0004 (both on DEV) ended by themselves")
        await page.click("#sf-wb [data-sf-task='T-0003'] [data-sf-op='done']")
        await wait(page, "() => window.__dbg.sfState().lanes.done.includes('T-0003')", label="T-0003 done")
        t = read_task(orch, "T-0003")
        check(t["status"] == "done" and t["doneAt"] >= t["endedAt"] >= t["startedAt"], f"the times in order: {t}")

        # ask the robot to change a note; tell the robot something
        note = '#sf-wb [data-sf-task="T-0001"]'
        await page.click(f"{note} .sf-revise summary")
        await page.fill(f"{note} [data-sf-revise]", "テストの観点も書いて")
        await page.click(f"{note} [data-sf-op='revise']")
        got = poll(channels[BOT])
        check(len(got) == 1 and "tasks/T-0001.json" in got[0] and "テストの観点も書いて" in got[0], f"the robot asked: {got}")
        await page.fill("#sf-say", "今日は shop を優先して")
        await page.click("#sf-send")
        got = poll(channels[BOT])
        check(got == ["今日は shop を優先して"], f"the box to the robot: {got}")

        # the start command: on T-0002 (the robot found no fitting session and wrote one), none on T-0001 (DEV is there)
        COPY = """(id) => { const c = document.querySelector(`#sf-wb [data-sf-task="${id}"] .sf-copy [data-sf-copy]`); return c ? c.dataset.sfCopy : null; }"""
        lines = res["copy"] = [await page.evaluate(COPY, "T-0002"), await page.evaluate(COPY, "T-0001")]
        check(lines == ["cd ~/work/docs && claude --channels plugin:jui-viz@jsonui", None], f"the start command only where no session fits: {lines}")
        await page.click('#sf-wb [data-sf-task="T-0002"] .sf-copy [data-sf-copy]')
        await wait(page, f"""() => document.querySelector('#sf-wb [data-sf-task="T-0002"] .sf-copy [data-sf-copy]').textContent === {json.dumps(T('sf.copied'))}""",
                   label="copied")

        # the prompts
        await page.click("#sf-prompts-btn")
        await wait(page, "() => !document.getElementById('sf-prompts').hidden", label="the prompts dialog")
        shown = await page.evaluate("""() => ({ i: document.getElementById('sf-p-instructions').value, c: document.getElementById('sf-p-chitchat').value,
          p: [...document.querySelectorAll('#sf-p-projects .sf-proj')].map((li) => [li.querySelector('input').value, li.querySelector('textarea').value]) })""")
        check(shown == {"i": "メッセージをプロジェクトに振り分ける", "c": "あいさつや雑談", "p": [["shop", "ショップのアプリ"], ["booking", "予約サイト"]]}, f"the config's words: {shown}")
        await page.evaluate("() => document.querySelector('.sf-board').scrollTo(0, 0)")
        await shot(page, "slack-room-prompts", out, failures)
        await page.fill("#sf-p-task", "1 依頼 1 タスクで作る")
        await page.click("#sf-p-add")
        await page.fill("#sf-p-projects .sf-proj:last-child input", "docs")
        await page.fill("#sf-p-projects .sf-proj:last-child textarea", "ドキュメントサイト")
        await page.click("#sf-p-save")
        await wait(page, f"() => document.getElementById('sf-p-said').textContent === {json.dumps(T('sf.prompts.saved'))}", label="saved")
        cfg = json.loads((state / "slack.json").read_text())
        check(cfg["taskPrompt"] == "1 依頼 1 タスクで作る" and cfg["router"]["prompt"]["projects"]["docs"] == "ドキュメントサイト"
              and cfg["source"]["_e2eKept"] == "x" + "oxp-e2e" and cfg["schedule"]["everyHours"] == 0 and cfg["router"]["confidenceMin"] == 0.6
              and stat.S_IMODE((state / "slack.json").stat().st_mode) == 0o600, f"slack.json: {cfg.get('taskPrompt')}, {cfg['router']}")
        await page.keyboard.press("Escape")
        check(await page.evaluate("() => document.getElementById('sf-prompts').hidden && window.__dbg.sfState().open"), "Esc closes the dialog first")

        # dark, and a phone's width
        light_bg = (await page.evaluate(STATE))["bg"]
        await page.emulate_media(color_scheme="dark")
        await page.wait_for_timeout(600)
        dark_st = await page.evaluate(STATE)
        check(light_bg and dark_st["bg"] and dark_st["bg"] != light_bg and dark_st["robot"] == bot and len(dark_st["bins"]) == 2,
              f"the 3D built again in the dark colours, its robot and bins kept: {light_bg} -> {dark_st}")
        await contrast("dark")
        await page.evaluate("() => document.querySelector('.sf-board').scrollTo(0, 0)")
        await shot(page, "slack-room-dark", out, failures)
        await page.keyboard.press("Escape")
        st = await page.evaluate(STATE)
        check(not st["open"] and st["focus"] == "btn-slack" and not st["covers"], f"Esc closes the room, the focus on the button: {st}")
        phone = await new_page(browser, watch, "slack-room-phone", **PHONE)
        await phone.goto(url + "/")
        await ready(phone)
        await wait(phone, "() => { const b = document.getElementById('btn-slack'); return b && !b.hidden; }", label="the button on a phone")
        await phone.evaluate("() => document.getElementById('btn-slack').click()")
        await wait(phone, "() => window.__dbg.sfState().open", label="the room on a phone")
        await phone.wait_for_timeout(600)
        wide = res["phone"] = await phone.evaluate("() => ({ page: document.documentElement.scrollWidth, room: document.getElementById('sf').scrollWidth, w: window.innerWidth })")
        check(wide["page"] <= wide["w"] and wide["room"] <= wide["w"], f"nothing sideways at 390: {wide}")
        # nothing of the left column cut: the send button and what was sorted are reachable, not under the board
        cut = res["phone-cut"] = await phone.evaluate("""() => ['sf-send', 'sf-flow-h'].map((id) => { const e = document.getElementById(id); e.scrollIntoView({ block: 'center' });
          const r = e.getBoundingClientRect(), at = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return !!at && (at === e || e.contains(at)); })""")
        check(all(cut), f"the send button and 仕分けの様子 are seen on a phone: {cut}")
        await phone.evaluate("() => document.getElementById('sf-canvas').scrollIntoView({ block: 'start' })")
        await shot(phone, "slack-room-phone", out, failures)
        await phone.evaluate("() => document.getElementById('sf-board-h').scrollIntoView({ block: 'start' })")
        await phone.wait_for_timeout(300)
        pb = res["phone-board"] = await phone.evaluate("() => { const r = document.getElementById('sf-wb').getBoundingClientRect(), h = document.getElementById('sf-board-h').getBoundingClientRect(); return { headTop: Math.round(h.top), top: Math.round(r.top), height: Math.round(r.height), vh: window.innerHeight }; }")
        check(pb["headTop"] < 260 and pb["height"] >= 0.6 * pb["vh"] and pb["top"] + pb["height"] <= pb["vh"] + 1, f"the board reached and whole on a phone: {pb}")
        await shot(phone, "slack-room-phone-board", out, failures)

        demo = await new_page(browser, watch, "slack-room-demo", **DESKTOP)
        await demo.goto(url + "/?demo=1")
        await ready(demo)
        check(await demo.evaluate("() => document.getElementById('btn-slack').hidden"), "no Slack button on the demo")
        for e in watch.console:
            failures.append(f"slack-room: console: {e}")
        for e in watch.csp:
            failures.append(f"slack-room: CSP: {e}")
        for u in watch.foreign:
            failures.append(f"slack-room: request outside the server: {u}")
    except Exception as e:
        failures.append(f"slack-room: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        for proc in stand_ins:   # the session stand-ins this suite started
            proc.kill()
            proc.wait()
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  slack-room: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "slack-room-results.json").write_text(dump(res) + "\n")
