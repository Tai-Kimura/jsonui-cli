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
import re
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
#: the tasks' times: a few hours before the run (tests/test_viz_e2e_fixture_times.py: no fixed date in a fixture)
T0 = int(time.time() * 1000) - 5 * 3_600_000
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


def message(orch, project, name, text, user="U1", channel="C1", thread=None):
    path = orch / "projects" / project / name
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = name.split("-")[0]
    path.write_text(json.dumps({"workspace": "tanosys", "channel": channel, "user": user, "ts": ts, "threadTs": thread or ts, "text": text,
                                "permalink": f"https://acme.slack.com/archives/{channel}/p{ts}", "removedFiles": 0, "redactions": 0,
                                "router": {"adapter": "haiku", "choice": project, "confidence": 0.92}}, ensure_ascii=False))
    return f"projects/{project}/{name}"


def task(orch, tid, status, title, prompt, project="shop", sources=(), **extra):
    data = {"id": tid, "title": title, "projectId": project, "sources": list(sources), "prompt": prompt,
            "target": {"sessionName": "", "sessionId": None}, "launchCommand": None, "status": status, "createdAt": T0, **extra}
    (orch / "tasks" / f"{tid}.json").write_text(json.dumps(data, ensure_ascii=False))


def read_task(orch, tid):
    return json.loads((orch / "tasks" / f"{tid}.json").read_text())


async def run_sorting_factory(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "slack-room"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    # this viz keeps its files in a folder of its own (JUI_VIZ_HOME): the start commands must name it (the trial, 11-02)
    state = home / "viz-other"
    state.mkdir(parents=True, exist_ok=True)
    orch = home / "a-long-folder-for-the-orchestration-of-the-slack-intake" / "slack-orchestration"
    (orch / "tasks").mkdir(parents=True, exist_ok=True)
    (orch / "_unsorted").mkdir(exist_ok=True)
    (orch / "_unsorted" / "1793500100-tanosys-C9.json").write_text("{}")
    cwds = {BOT: str(orch), DEV: "/work/shop-app", PLAIN: "/work/booking-site"}
    (state / "slack.json").write_text(json.dumps({
        # manual only and no workspace: stage 1's fetch (今すぐ取る) runs and reaches nothing outside
        "orchestrationDir": str(orch), "schedule": {"everyHours": 0, "at": "09:00"},
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
    long_prompt = "ドキュメントサイトの誤字を直してください。\n" + "\n".join(f"{k}. ページ {k} の見出しと本文の誤字を確かめて直す（表記ゆれも揃える）" for k in range(1, 13))
    task(orch, "T-0002", "draft", "ドキュメントの誤字", long_prompt, project="docs",
         target={"sessionName": "docs", "sessionId": None}, launchCommand="cd ~/work/docs && claude --channels plugin:jui-viz@jsonui")
    task(orch, "T-0004", "working", "商品一覧の並び順", "商品一覧の並び順を新しい順にしてください。", target={"sessionName": "shop", "sessionId": DEV},
         startedAt=T0 + 200_000)
    t1 = message(orch, "booking", "1793500005-tanosys-C2.json", "決済画面の文言、どちらがいいか相談させてください（B&amp;S の &lt;決済&gt; 画面、<@U7> さんにも）")   # as 2.4.0 kept it: Slack's escapes
    t2 = message(orch, "booking", "1793500006-tanosys-C2.json", "A 案の方が良さそうですが、もう少し考えます。\n理由は 2 つあります:\n- 短い\n- ボタンの文言と揃う", user="U3", thread="1793500005")
    task(orch, "T-0009", "talking", "決済画面の文言の相談", "", project="booking", sources=[t1, t2], threads=["1793500005"])
    task(orch, "T-0010", "draft", "ログイン画面の文言（追加）", "ログイン画面の英語の文言も直してください。", relatedTaskId="T-0005")
    task(orch, "T-0005", "ended", "ログイン画面の文言", "ログイン画面の文言を直してください。", startedAt=T0 + 300_000, endedAt=T0 + 400_000,
         target={"sessionName": "shop", "sessionId": None})
    task(orch, "T-0006", "done", "フッターのリンク", "フッターのリンク切れを直してください。", startedAt=1, endedAt=2, doneAt=int(time.time() * 1000) - 600_000,
         target={"sessionName": "shop", "sessionId": None})
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1", JUI_VIZ_HOME=str(state))
    sessions_dir = home / ".claude" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    stand_ins: list = []

    names = {BOT: T("page.sf.title")}   # what `claude -n` (the room's robotLaunch) writes into the session's registry row

    def session_process(sid, *args):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(900)", *args],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        stand_ins.append(proc)
        (sessions_dir / f"{proc.pid}.json").write_text(json.dumps({"pid": proc.pid, "sessionId": sid, "cwd": cwds[sid], "kind": "interactive",
                                                                  "entrypoint": "cli", "status": "idle", "procStart": f"t{proc.pid}",
                                                                  **({"name": names[sid]} if sid in names else {})}))
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def check(cond, text):
        if not cond:
            failures.append(f"slack-room: {text}")

    def hook(sid, **payload):
        subprocess.run([sys.executable, "-I", "-S", str(forward)], timeout=10, capture_output=True, env=dict(base_env, HOME=str(home), JUI_VIZ_HOME=str(state)),
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
            try:
                _, polled = local("GET", f"/channel/poll?channelId={channel}", timeout=within + 5)
            except TimeoutError:   # the server holds a poll longer than a short wait: nothing came
                polled = None
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
        texts = res["texts"] = await page.evaluate("""() => ({ lanes: [...document.querySelectorAll('#sf-wb .sf-lane-btn')].map((h) => h.firstChild.textContent.trim()),
          flow: document.getElementById('sf-flow-body').textContent, robot: document.getElementById('sf-robot').textContent,
          seen: ['sf-canvas', 'sf-wb', 'sf-say'].map((id) => { const r = document.getElementById(id).getBoundingClientRect(); const e = document.elementFromPoint(r.left + r.width / 2, r.top + Math.min(r.height / 2, 30));
            return !!e && (e.id === id || !!e.closest('#' + id)); }) })""")
        check(texts["lanes"] == [T(f"sf.lane.{k}") for k in ("talking", "draft", "ready", "working", "ended", "done")], f"the lanes: {texts['lanes']}")
        check(T("sf.flow.counts", total=5, pending=0, unsorted=1) in texts["flow"] and "カートの合計金額" in texts["flow"] and bot in texts["robot"],
              f"what was sorted and the robot: {texts['flow'][:200]} / {texts['robot']}")
        # the robot's session named as its start command names it (claude -n, the room's name by default): the box shows it
        rname = res["robot-name"] = await page.evaluate("() => (document.querySelector('#sf-robot .sf-robot-name') || {}).textContent")
        check(rname == T("page.sf.title"), f"the robot's session name on its line: {rname!r}")
        lanes_in = res["lanes-in"] = await page.evaluate("() => { const b = document.querySelector('.sf-board'); return { scroll: b.scrollWidth, client: b.clientWidth }; }")
        check(lanes_in["scroll"] <= lanes_in["client"], f"the six lanes fit the board at 1440: {lanes_in}")
        check(all(texts["seen"]), f"the 3D, the board and the box are on the page, not under something: {texts['seen']}")
        marks = res["marks"] = await page.evaluate("""() => { const t = (id, q) => [...document.querySelectorAll(`#sf-wb [data-sf-task="${id}"] ${q}`)].map((e) => e.textContent);
          return { talk: t('T-0009', '[data-sf-chat]'),
            more: t('T-0005', '.sf-mark-more'), follows: t('T-0010', '.sf-mark'), id: t('T-0001', '.sf-id') }; }""")
        check(marks["talk"] == [T("sf.note.sources", n=2)], f"the talking note's messages, to open beside the board: {marks}")
        # the note's parts in their order, a label over each field, the title cut at 3 lines, one row of actions with 開始 at its right
        lay = res["layout"] = await page.evaluate("""() => { const n = document.querySelector('#sf-wb [data-sf-task="T-0003"]'), r = (q) => n.querySelector(q).getBoundingClientRect();
          const acts = [...n.querySelectorAll('.sf-note-acts button')].map((b) => b.getBoundingClientRect());
          const labelGap = Math.round(r('[data-sf-target]').top - n.querySelector('[data-sf-target]').closest('label').querySelector('.sf-label').getBoundingClientRect().bottom);
          const title = n.querySelector('.sf-note-title'), lh = parseFloat(getComputedStyle(title).lineHeight);
          const st = n.querySelector('[data-sf-status]'), stFits = st.scrollWidth <= st.clientWidth + 1 && st.getBoundingClientRect().width >= 90;
          const inside = [...n.querySelectorAll('button, select, textarea, code')].every((e) => { const a = e.getBoundingClientRect(), b = n.getBoundingClientRect(); return a.left >= b.left - 1 && a.right <= b.right + 1; });
          const rev = n.querySelector('[data-sf-revise-open]'), rs = getComputedStyle(rev), revLines = Math.round((rev.getBoundingClientRect().height - ['paddingTop', 'paddingBottom', 'borderTopWidth', 'borderBottomWidth'].reduce((a, k) => a + parseFloat(rs[k]), 0)) / parseFloat(rs.lineHeight));
          const tg = n.querySelector('[data-sf-target]'), ctx = document.createElement('canvas').getContext('2d'), ts = getComputedStyle(tg);
          ctx.font = `${ts.fontWeight} ${ts.fontSize} ${ts.fontFamily}`;   // a select's scrollWidth ignores its cut text: the chosen words measured
          const tgFits = ctx.measureText(tg.options[tg.selectedIndex].text).width <= tg.clientWidth - parseFloat(ts.paddingLeft) - parseFloat(ts.paddingRight) - 20;
          return { labels: [...n.querySelectorAll('.sf-label')].map((e) => e.textContent), labelGap, stFits, inside, revLines, tgFits, oneRow: acts.every((b) => Math.abs(b.top - acts[0].top) < 2),
            startRight: n.querySelector('[data-sf-op="start"]').getBoundingClientRect().right >= Math.max(...acts.map((b) => b.right)) - 1,
            titleLines: Math.round(title.getBoundingClientRect().height / lh), state: n.querySelector('[data-sf-status]').value,
            scheme: getComputedStyle(n.querySelector('[data-sf-status]')).colorScheme }; }""")
        check(lay["labels"] == [T("sf.note.state.label"), T("sf.note.prompt"), T("sf.note.target")] and lay["stFits"] and lay["inside"] and lay["revLines"] <= 1 and lay["tgFits"] and 4 <= lay["labelGap"] <= 8 and lay["oneRow"] and lay["startRight"]
              and lay["state"] == "ready" and lay["titleLines"] <= 3 and lay["scheme"] == "light", f"the note's layout: {lay}")
        # nothing scrolls inside a note (the requester, 11-02): the prompt cut to its first lines, the start command whole
        flat = res["note-no-scroll"] = await page.evaluate("""() => {
          const scrolls = [...document.querySelectorAll('#sf-wb .sf-note, #sf-wb .sf-note *')].filter((e) => { const o = getComputedStyle(e).overflowY; return (o === 'auto' || o === 'scroll') && e.scrollHeight > e.clientHeight + 1; })
            .map((e) => (e.closest('.sf-note') || e).dataset.sfTask + ':' + e.tagName + '.' + e.className);
          const v = document.querySelector('#sf-wb [data-sf-task="T-0002"] [data-sf-prompt-open] .sf-prompt-text'), lh = parseFloat(getComputedStyle(v).lineHeight);
          const code = document.querySelector('#sf-wb [data-sf-task="T-0002"] .sf-copy code');
          return { scrolls, textareas: document.querySelectorAll('#sf-wb .sf-note textarea').length, lines: Math.round(v.getBoundingClientRect().height / lh), cut: v.scrollHeight > v.clientHeight + 1,
            codeWhole: code.scrollHeight <= code.clientHeight + 1 && code.textContent.endsWith("-n 'docs T-0002'") }; }""")
        check(not flat["scrolls"] and flat["textareas"] == 0 and flat["lines"] == 5 and flat["cut"] and flat["codeWhole"],
              f"no scroll inside a note: the prompt's first 5 lines, the start command whole: {flat}")
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
        # the header's folder: cut in the middle, the whole on hover; the robot's start command names this viz's folder
        head = res["head"] = await page.evaluate("() => ({ text: document.getElementById('sf-dir').textContent, title: document.getElementById('sf-dir').title })")
        check(head["title"] == "~/" + str(orch.relative_to(home)) and "…" in head["text"] and len(head["text"]) <= 60 and head["text"].endswith("slack-orchestration"),
              f"the folder cut in the middle, whole on hover: {head}")
        # what can be pressed shows the pointing hand (the id's copy cursor read as "+")
        cur = res["cursor"] = await page.evaluate("""() => { const q = [...document.querySelectorAll('#sf button:not(:disabled), #sf summary, #sf a[href]')].filter((e) => e.getClientRects().length);
          return { id: getComputedStyle(document.querySelector('#sf-wb .sf-id')).cursor, n: q.length, not: q.filter((e) => getComputedStyle(e).cursor !== 'pointer').map((e) => e.id || e.className) }; }""")
        check(cur["id"] == "pointer" and cur["n"] > 20 and not cur["not"], f"the pointing hand on the id and everything pressable: {cur}")
        # a task's messages as a chat beside the board: thread order, the reply set in, the whole text, its Slack link
        await page.click('#sf-wb [data-sf-task="T-0009"] [data-sf-chat]')
        await wait(page, "() => document.querySelectorAll('#sf-chat .sf-bubble').length === 2", label="the chat's two messages")
        chat = res["chat"] = await page.evaluate("""() => { const p = document.getElementById('sf-chat'), r = p.getBoundingClientRect();
          return { title: document.getElementById('sf-chat-title').textContent, focus: document.activeElement.id,
            rows: [...p.querySelectorAll('.sf-bubble')].map((b) => ({ reply: b.classList.contains('sf-reply'), who: b.querySelector('b').textContent, text: b.querySelector('.sf-bubble-text').textContent,
              link: (b.querySelector('a') || {}).href || '', target: (b.querySelector('a') || {}).target || '' })), right: Math.round(innerWidth - r.right), w: Math.round(r.width) }; }""")
        check(chat["title"] == "T-0009 決済画面の文言の相談" and chat["focus"] == "sf-chat-close" and [r["who"] for r in chat["rows"]] == ["U1", "U3"]
              and not chat["rows"][0]["reply"] and chat["rows"][1]["reply"] and "ボタンの文言と揃う" in chat["rows"][1]["text"]
              and "（B&S の <決済> 画面、@U7 さんにも）" in chat["rows"][0]["text"] and "&amp;" not in chat["rows"][0]["text"]
              and chat["rows"][0]["link"] == "https://acme.slack.com/archives/C1/p1793500005" and chat["rows"][0]["target"] == "_blank" and chat["right"] == 0,
              f"the chat: thread order, the reply set in, the whole text, the Slack link, at the side: {chat}")
        await shot(page, "slack-room-chat", out, failures)
        await page.keyboard.press("Escape")
        back_chat = await page.evaluate("() => ({ hidden: document.getElementById('sf-chat').hidden, open: window.__dbg.sfState().open, focus: !!document.activeElement.closest('[data-sf-task=\"T-0009\"]') })")
        check(back_chat == {"hidden": True, "open": True, "focus": True}, f"Esc closes the chat, the room stays, the focus back: {back_chat}")
        await page.click('#sf-wb [data-sf-task="T-0009"] [data-sf-chat]')
        await wait(page, "() => !document.getElementById('sf-chat').hidden", label="the chat again")
        await page.click("#sf-chat-close")
        check(await page.evaluate("() => document.getElementById('sf-chat').hidden"), "x closes the chat")
        # the whole board (the requester, 11-02): the six lanes over the room, nothing shrunk, sized to read; what is below
        # scrolls in the board
        READ = """() => { const px = (q) => [...document.querySelectorAll('#sf-wb .sf-lane:not([hidden]) ' + q)].filter((e) => e.getClientRects().length).map((e) => parseFloat(getComputedStyle(e).fontSize));
          const min = (a) => (a.length ? Math.min(...a) : 0);
          return { zoom: document.getElementById('sf-wb').style.zoom || getComputedStyle(document.getElementById('sf-wb')).zoom, title: min(px('.sf-note-title')), prompt: min(px('.sf-prompt-text')),
            select: min(px('.sf-note select')), button: min(px('.sf-note .wb-btn')), label: min(px('.sf-label')), lane: min(px('h4')),
            lanes: [...document.querySelectorAll('#sf-wb .sf-lane')].filter((l) => !l.hidden).map((l) => l.dataset.sfLane), board: document.getElementById('sf').dataset.board }; }"""
        await page.click("#sf-full")
        await page.wait_for_timeout(400)
        full = res["full"] = await page.evaluate(INSIDE)
        left = await page.evaluate("() => getComputedStyle(document.querySelector('.sf-left')).display")
        check(not full["sideways"] and (not full["below"] or full["wbScrolls"]) and left == "none" and await page.evaluate(f"() => document.getElementById('sf-full').textContent === {json.dumps(T('sf.full.back'))}"),
              f"the whole board: the six lanes side by side, what is below scrolls in it, the left side away: {full} {left}")
        rd = res["full-read"] = await page.evaluate(READ)
        check(rd["zoom"] in ("", "1") and rd["title"] >= 16 and rd["prompt"] >= 14 and rd["select"] >= 14 and rd["button"] >= 14 and rd["label"] >= 13 and rd["lane"] >= 20
              and len(rd["lanes"]) == 6, f"the whole board sized to read, not shrunk: {rd}")
        await shot(page, "slack-room-full", out, failures)
        # a lane's heading: that lane alone, its notes side by side
        await page.click('#sf-wb [data-sf-lane-open="draft"]')
        await page.wait_for_timeout(300)
        ln = res["lane"] = await page.evaluate("""() => { const tops = [...document.querySelectorAll('#sf-wb [data-sf-lane="draft"] .sf-note')].map((n) => Math.round(n.getBoundingClientRect().top));
          return { board: document.getElementById('sf').dataset.board, lanes: [...document.querySelectorAll('#sf-wb .sf-lane')].filter((l) => !l.hidden).map((l) => l.dataset.sfLane), tops }; }""")
        check(ln["board"] == "lane" and ln["lanes"] == ["draft"] and len(ln["tops"]) >= 3 and abs(ln["tops"][0] - ln["tops"][1]) <= 12,
              f"the draft lane alone, its notes side by side (a note's tilt moves its top a little): {ln}")
        check((await page.evaluate(READ))["prompt"] >= 14, "the lane sized to read")
        await shot(page, "slack-room-lane", out, failures)
        await page.click('#sf-wb [data-sf-lane-open="draft"]')                          # pressed again: the six lanes
        check(await page.evaluate("() => document.getElementById('sf').dataset.board") == "full", "the heading pressed again: back to the six lanes")
        # a note pressed (its own surface): its lane alone, the note selected; ↑ ↓ in the lane, ← → to the next lane's
        SEL = "() => ({ sel: [...document.querySelectorAll('#sf-wb .sf-note.is-selected')].map((n) => n.dataset.sfTask), board: document.getElementById('sf').dataset.board, lanes: [...document.querySelectorAll('#sf-wb .sf-lane')].filter((l) => !l.hidden).map((l) => l.dataset.sfLane), focus: document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.sfTask || document.activeElement.id : null })"
        await page.click('#sf-wb [data-sf-task="T-0001"] .sf-note-title')
        await page.wait_for_timeout(300)
        picked = res["picked"] = await page.evaluate(SEL)
        check(picked == {"sel": ["T-0001"], "board": "lane", "lanes": ["draft"], "focus": "T-0001"}, f"a note pressed: its lane alone, the note selected: {picked}")
        await shot(page, "slack-room-selected", out, failures)
        walk = []
        for key in ("ArrowDown", "ArrowDown", "ArrowUp", "ArrowRight", "ArrowRight", "ArrowLeft"):
            await page.keyboard.press(key)
            await page.wait_for_timeout(120)
            st_now = await page.evaluate(SEL)
            walk.append((key, st_now["sel"], st_now["lanes"]))
        res["walk"] = walk
        order = [n for n in ("T-0001", "T-0002", "T-0010")]
        check([w[1] for w in walk] == [[order[1]], [order[2]], [order[1]], ["T-0003"], ["T-0004"], ["T-0003"]] and [w[2] for w in walk][3:] == [["ready"], ["working"], ["ready"]],
              f"↓ ↓ ↑ in the lane, → → ← to the next lanes' first notes: {walk}")
        # a select keeps its arrows (they move its value, not the selection)
        kept = await page.evaluate("""() => { const s = document.querySelector('#sf-wb [data-sf-task="T-0003"] [data-sf-status]'); s.focus();
          s.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true, cancelable: true }));
          return [...document.querySelectorAll('#sf-wb .sf-note.is-selected')].map((n) => n.dataset.sfTask); }""")
        check(kept == ["T-0003"], f"an arrow on a select is the select's: {kept}")
        await page.evaluate("() => document.querySelector('#sf-wb [data-sf-task=\"T-0003\"]').focus()")
        # Esc a step back: the selection, the lane, the whole board, then the room's own board
        steps = []
        for _ in range(3):
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(150)
            st_now = await page.evaluate(SEL)
            steps.append((st_now["board"], st_now["sel"]))
        res["esc-steps"] = steps
        check(steps == [("lane", []), ("full", []), ("", [])], f"Esc a step back each time: {steps}")
        back = await page.evaluate("() => ({ open: window.__dbg.sfState().open, full: document.getElementById('sf').dataset.board, zoom: document.getElementById('sf-wb').style.zoom })")
        check(back == {"open": True, "full": "", "zoom": ""}, f"Esc leaves the whole board, the room stays: {back}")
        await page.wait_for_timeout(500)
        tag_rects = res["tags"] = await page.evaluate("() => [...document.querySelectorAll('#sf-labels .sf-tag')].filter((e) => !e.hidden).map((e) => { const r = e.getBoundingClientRect(); return [e.textContent, Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.bottom)]; })")
        overlap = len(tag_rects) >= 2 and any(a[1] < b[3] and b[1] < a[3] and a[2] < b[4] and b[2] < a[4] for i, a in enumerate(tag_rects) for b in tag_rects[i + 1:])
        check(len(tag_rects) >= 2 and not overlap, f"the bins' tags apart: {tag_rects}")
        await page.click('#sf-wb [data-sf-task="T-0001"] .sf-id')
        copied = await page.evaluate("() => navigator.clipboard.readText()")
        check(copied == "T-0001", f"the id copied: {copied!r}")
        mark = res["id-mark"] = await page.evaluate("""() => { const b = document.querySelector('#sf-wb [data-sf-task="T-0002"] .sf-id');
          return { after: getComputedStyle(b, '::after').content, label: b.getAttribute('aria-label'), title: !!b.title }; }""")
        check(mark["after"] == '"⧉"' and mark["label"] == T("sf.note.id.aria", id="T-0002") and mark["title"], f"the id says it copies: {mark}")
        await page.select_option('#sf-wb [data-sf-task="T-0009"] [data-sf-status]', "draft")
        await wait(page, "() => window.__dbg.sfState().lanes.draft.includes('T-0009')", label="T-0009 raised to a draft")
        check(read_task(orch, "T-0009")["status"] == "draft", "the file says draft")

        # stage 1's state and 今すぐ取る (POST /api/slack/fetch)
        await wait(page, f"() => document.getElementById('sf-intake').textContent.includes({json.dumps(T('sf.intake.manual'))})", label="the intake's line")
        await page.click("#sf-fetch")
        await wait(page, f"() => document.getElementById('sf-intake').textContent.startsWith({json.dumps(T('sf.intake.last', at='').strip())}) && !document.getElementById('sf-intake').textContent.includes({json.dumps(T('sf.intake.never'))})",
                   timeout=15000, label="the last fetch's time after 今すぐ取る")
        res["intake"] = await page.evaluate("() => document.getElementById('sf-intake').textContent")
        clean = res["after-fetch"] = await page.evaluate("() => [document.getElementById('sf-intake-err').hidden, document.getElementById('sf-mode-note').hidden, document.getElementById('sf-intake-err').textContent]")
        check(clean[:2] == [True, True], f"a fetch with no error and mode api: no error line, no connector note: {clean}")
        # the last fetch's errors (2026-11-02-viz-slack-fetch-errors-not-shown-in-room): the count, the first one's words, a
        # hint for missing_scope on a DM; a key-shaped word in it masked
        key = "xox" + "b-1111-2222-e2ekey"
        errs = [f"tanosys/D02HXM5RE: conversations.history: missing_scope (seen with {key})"] + [f"tanosys/D0{k}XM5RE: conversations.history: missing_scope" for k in range(4)]
        st_file = orch / ".state" / "status.json"
        st_data = json.loads(st_file.read_text())
        st_data["lastRun"] = {**st_data["lastRun"], "errors": errs}
        st_file.write_text(json.dumps(st_data))
        await wait(page, "() => !document.getElementById('sf-intake-err').hidden", timeout=15000, label="the fetch's errors in the room")
        er = res["fetch-errors"] = await page.evaluate("() => document.getElementById('sf-intake-err').textContent")
        check(er.startswith(T("sf.intake.errors", n=5, error="tanosys/D02HXM5RE: conversations.history: missing_scope")) and er.endswith(T("sf.intake.hint.im"))
              and key not in er and "…" in er, f"5 errors, the first's words, the DM's hint, the key masked: {er}")
        code, snap = local("GET", "/api/snapshot")
        slack_slice = (snap.get("slices") or {}).get("slack") if isinstance(snap, dict) else None
        res["snapshot-slack"] = slack_slice
        check(code == 200 and "missing_scope" in json.dumps(slack_slice, ensure_ascii=False) and key not in json.dumps(snap, ensure_ascii=False),
              f"the slack slice carries no key-shaped word: {code} {list(snap)[:8] if isinstance(snap, dict) else snap}")
        await page.evaluate("() => document.getElementById('sf-intake-err').scrollIntoView({ block: 'center' })")
        await page.wait_for_timeout(400)
        await shot(page, "slack-room-fetch-errors", out, failures)
        # the left column's two tabs (the requester, 11-02): one at a time with the column's height; the fetch bar fixed above
        TABS = """() => { const L = document.querySelector('.sf-left').getBoundingClientRect(), f = document.getElementById('sf-fetch').getBoundingClientRect();
          const pane = (id) => { const e = document.getElementById(id), r = e.getBoundingClientRect(); return { shown: !e.hidden && r.height > 0, bottom: Math.round(r.bottom), h: Math.round(r.height) }; };
          const at = document.elementFromPoint(f.left + f.width / 2, f.top + f.height / 2);
          let kept = null; try { kept = localStorage.getItem('jui-viz.sf.tab'); } catch (err) { kept = 'refused'; }
          return { talk: pane('sf-pane-talk'), flow: pane('sf-pane-flow'), leftBottom: Math.round(L.bottom), fetchTop: Math.round(f.top), fetchSeen: !!at && (at.id === 'sf-fetch' || !!at.closest('#sf-fetch')),
            selected: [...document.querySelectorAll('#sf .sf-tab')].filter((b) => b.getAttribute('aria-selected') === 'true').map((b) => b.dataset.sfTab), kept }; }"""
        tb0 = res["tabs-talk"] = await page.evaluate(TABS)
        check(tb0["selected"] == ["talk"] and tb0["talk"]["shown"] and not tb0["flow"]["shown"] and abs(tb0["talk"]["bottom"] - tb0["leftBottom"]) <= 2 and tb0["fetchSeen"],
              f"the talk tab first, down to the column's foot, the fetch bar in view: {tb0}")
        await page.evaluate("() => document.getElementById('sf-intake-err').scrollIntoView({ block: 'nearest' })")
        await shot(page, "slack-room-tab-talk", out, failures)
        await page.click("#sf-flow-h")
        await page.wait_for_timeout(200)
        tb1 = res["tabs-flow"] = await page.evaluate(TABS)
        check(tb1["selected"] == ["flow"] and tb1["flow"]["shown"] and not tb1["talk"]["shown"] and abs(tb1["flow"]["bottom"] - tb1["leftBottom"]) <= 2
              and tb1["fetchSeen"] and tb1["fetchTop"] == tb0["fetchTop"] and tb1["kept"] == "flow", f"the flow tab: the column's height, the fetch bar where it was, kept: {tb1}")
        await page.evaluate("() => { const p = document.getElementById('sf-pane-flow'); p.scrollTop = p.scrollHeight; }")
        tb2 = await page.evaluate(TABS)
        check(tb2["fetchSeen"] and tb2["fetchTop"] == tb0["fetchTop"], f"the fetch bar does not scroll away with the pane: {tb2}")
        await page.evaluate("() => { document.getElementById('sf-pane-flow').scrollTop = 0; }")
        await shot(page, "slack-room-tab-flow", out, failures)
        await page.keyboard.press("ArrowLeft")                                          # the tabs' own arrows (focus on the tab)
        check((await page.evaluate(TABS))["selected"] == ["talk"], "← on the tabs goes to the other tab")
        # the connector's warning (2026-11-02-viz-slack-connector-mode-note-not-shown-in-room): shown while mode is connector
        cfg_now = json.loads((state / "slack.json").read_text())
        def set_mode(mode):
            (state / "slack.json").write_text(json.dumps({**cfg_now, "source": {**cfg_now["source"], "mode": mode}}, ensure_ascii=False))
            os.chmod(state / "slack.json", 0o600)
        set_mode("connector")
        await wait(page, "() => !document.getElementById('sf-mode-note').hidden", timeout=15000, label="the connector's note")
        mn = res["mode-note"] = await page.evaluate("() => document.getElementById('sf-mode-note').textContent")
        check(mn == T("sf.intake.modeNote", note=T("srv.slack.modeNote")), f"the connector's note, in the page's language: {mn}")
        await shot(page, "slack-room-connector-note", out, failures)
        set_mode("api")
        await wait(page, "() => document.getElementById('sf-mode-note').hidden", timeout=15000, label="the note gone with mode api")
        # Socket Mode's status (the socket branch's slice: slack.socket per workspace), drawn from a status the suite gives
        app_key = "xapp" + "-1-A0E2E-123-abcdef"
        now_ms = int(time.time() * 1000)
        fake = await page.evaluate("() => window.__dbg.sfSlackGet()")
        fake.update({"mode": "socket", "socket": {
            "tanosys": {"connected": True, "since": now_ms - 3_600_000, "lastEventAt": now_ms - 60_000, "error": None, "errorAt": None},
            "acme": {"connected": False, "since": None, "lastEventAt": None, "error": f"apps.connections.open: invalid_auth ({app_key})", "errorAt": now_ms - 30_000}}})
        check(await page.evaluate("(k) => window.__dbg.sfSlackSet(k)", fake), "the suite's status drawn")
        sock = res["socket"] = await page.evaluate("() => ({ hidden: document.getElementById('sf-socket').hidden, rows: [...document.querySelectorAll('#sf-socket li')].map((li) => li.textContent) })")
        check(not sock["hidden"] and len(sock["rows"]) == 2 and sock["rows"][0].startswith("tanosys: ") and T("sf.socket.off", ws="acme") in sock["rows"][1]
              and T("sf.intake.hint.appToken") in sock["rows"][1] and app_key not in sock["rows"][1] and "invalid_auth" in sock["rows"][1],
              f"a line per workspace: connected since and the last message, or not, its error with the hint, the key masked: {sock}")
        await page.evaluate("() => document.getElementById('sf-socket').scrollIntoView({ block: 'nearest' })")
        await page.wait_for_timeout(600)                     # the 3D drawn again at the stage's new height
        await shot(page, "slack-room-socket", out, failures)
        await page.evaluate("(k) => window.__dbg.sfSlackSet(k)", {**fake, "mode": "api", "socket": None})
        check(await page.evaluate("() => document.getElementById('sf-socket').hidden"), "no socket lines with mode api")
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
        # (the prompt is typed in the large popup a press on the note's prompt opens: the requester, 11-02)
        note = '#sf-wb [data-sf-task="T-0001"]'
        await page.click(f"{note} [data-sf-prompt-open]")
        await wait(page, "() => !document.getElementById('sf-edit').hidden", label="the prompt's popup")
        pop = res["prompt-popup"] = await page.evaluate("""() => { const b = document.querySelector('#sf-edit .sf-modal-box').getBoundingClientRect(), t = document.getElementById('sf-edit-text');
          return { w: Math.round(b.width), th: Math.round(t.getBoundingClientRect().height), value: t.value, ro: t.readOnly, save: !document.getElementById('sf-edit-save').hidden,
            focus: document.activeElement.id, head: document.getElementById('sf-edit-h').textContent }; }""")
        check(pop["w"] >= 800 and pop["th"] >= 400 and pop["value"] == "ショップのカート画面で、合計金額を税込みで出すように直してください。" and not pop["ro"] and pop["save"]
              and pop["focus"] == "sf-edit-text" and pop["head"].startswith("T-0001"), f"the prompt large, whole, editable: {pop}")
        await page.fill("#sf-edit-text", "TYPED: 税込みで出す。テストも足す")
        t = read_task(orch, "T-0001")
        t["title"] = "カートの税込み表示（ロボットが直した）"
        (orch / "tasks" / "T-0001.json").write_text(json.dumps(t, ensure_ascii=False))
        await page.wait_for_timeout(3500)                     # the scan and its push
        check(await page.eval_on_selector("#sf-edit-text", "(e) => e.value") == "TYPED: 税込みで出す。テストも足す", "typed text kept in the popup")
        await page.keyboard.press("Escape")                   # closed unsaved: the note shows what was typed, the room stays
        await wait(page, f"() => document.getElementById('sf-edit').hidden && document.querySelector('{note} .sf-note-title').textContent.includes('ロボットが直した')", label="the note drawn again")
        check(await page.evaluate(f"() => window.__dbg.sfState().open && document.querySelector('{note} .sf-prompt-text').textContent") == "TYPED: 税込みで出す。テストも足す",
              "typed text kept through the redraw, on the note")
        await page.click(f"{note} [data-sf-op='save']")
        await wait(page, f"() => document.querySelector('{note} .sf-note-said').textContent === {json.dumps(T('sf.said.save'))}", label="saved")
        t = read_task(orch, "T-0001")
        check(t["prompt"] == "TYPED: 税込みで出す。テストも足す" and t["promptEditedByUser"] is True and t["sourcesAtEdit"] == [m1], f"保存 wrote the prompt, marked by hand: {t}")
        await wait(page, f"() => document.querySelector('{note}').textContent.includes({json.dumps(T('sf.note.edited'))})", label="the hand-edited mark")
        await page.click('#sf-wb [data-sf-task="T-0004"] [data-sf-prompt-open]')
        await wait(page, "() => !document.getElementById('sf-edit').hidden", label="a working task's prompt")
        ro = res["prompt-popup-read"] = await page.evaluate("() => ({ ro: document.getElementById('sf-edit-text').readOnly, save: !document.getElementById('sf-edit-save').hidden })")
        check(ro == {"ro": True, "save": False}, f"a sent task's prompt opens to read only: {ro}")
        await page.keyboard.press("Escape")
        await page.click('#sf-wb [data-sf-task="T-0002"] [data-sf-prompt-open]')
        await wait(page, "() => !document.getElementById('sf-edit').hidden", label="the long prompt large")
        check(await page.evaluate("() => document.getElementById('sf-edit-text').value") == long_prompt, "the long prompt whole in the popup")
        await page.wait_for_timeout(300)
        await shot(page, "slack-room-prompt-popup", out, failures)
        edited = long_prompt + "\n13. 用語集のページも見る"
        await page.fill("#sf-edit-text", edited)
        await page.click("#sf-edit-save")
        await wait(page, "() => document.getElementById('sf-edit').hidden", label="saved from the popup")
        t2_file = read_task(orch, "T-0002")
        check(t2_file["prompt"] == edited and t2_file.get("promptEditedByUser") is True, f"保存 in the popup writes the file: {t2_file.get('promptEditedByUser')}")
        long_prompt = edited
        t = read_task(orch, "T-0001")
        t["sources"].append(m4)                                 # the robot adds a message to it, leaving the prompt
        (orch / "tasks" / "T-0001.json").write_text(json.dumps(t, ensure_ascii=False))
        await wait(page, f"() => (document.querySelector('{note} .sf-mark-late') || {{}}).textContent === {json.dumps(T('sf.note.late', n=1))}",
                   label="what came after the hand's prompt shown")
        await page.select_option(f"{note} [data-sf-status]", "ready")
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
        await wait(page, "() => window.__dbg.sfState().lanes.ended.includes('T-0003')", timeout=15000, label="T-0003 (sent with 開始) ended by itself")
        check(read_task(orch, "T-0004")["status"] == "working", "T-0004 (working, never sent with 開始) is not followed")
        await page.select_option("#sf-wb [data-sf-task='T-0003'] [data-sf-status]", "done")
        await wait(page, "() => window.__dbg.sfState().lanes.done.includes('T-0003')", label="T-0003 done")
        purge = await page.evaluate("() => (document.querySelector('#sf-wb [data-sf-task=\"T-0003\"] .sf-mark-purge') || {}).textContent || null")
        check(purge in (T("sf.note.purge", n=60), T("sf.note.purge", n=59)), f"a done note says when it goes: {purge}")
        # a state chosen by hand sends nothing and is not followed: T-0010 made working, DEV busy then idle, it stays working
        await page.select_option("#sf-wb [data-sf-task='T-0010'] [data-sf-status]", "working")
        await wait(page, "() => window.__dbg.sfState().lanes.working.includes('T-0010')", label="T-0010 working by hand")
        check(poll(channels[DEV], within=3) == [], "nothing sent to DEV by a state chosen by hand")
        hook(DEV, hook_event_name="UserPromptSubmit", prompt="something else")
        hook(DEV, hook_event_name="Stop")
        await page.wait_for_timeout(4500)
        check(read_task(orch, "T-0010")["status"] == "working", f"a task made working by hand is not ended by the session: {read_task(orch, 'T-0010')['status']}")
        t = read_task(orch, "T-0003")
        check(t["status"] == "done" and t["doneAt"] >= t["endedAt"] >= t["startedAt"], f"the times in order: {t}")

        # ask the robot to change a note; tell the robot something
        note = '#sf-wb [data-sf-task="T-0001"]'
        await page.click(f"{note} [data-sf-revise-open]")
        await wait(page, "() => !document.getElementById('sf-revise').hidden", label="the revise popup")
        rv = res["revise"] = await page.evaluate("""() => { const b = document.querySelector('#sf-revise .sf-modal-box').getBoundingClientRect(), t = document.getElementById('sf-revise-text').getBoundingClientRect();
          return { focus: document.activeElement.id, head: document.getElementById('sf-revise-h').textContent, w: Math.round(t.width), h: Math.round(t.height), inView: b.left >= 0 && b.right <= innerWidth && b.top >= 0 && b.bottom <= innerHeight }; }""")
        check(rv["focus"] == "sf-revise-text" and rv["head"].startswith(T("sf.revise.head", id="T-0001", title="")[:7]) and "T-0001" in rv["head"] and rv["w"] >= 500 and rv["h"] >= 150 and rv["inView"],
              f"the popup: a wide box with the focus, which note at its head, in view: {rv}")
        await page.fill("#sf-revise-text", "テストの観点も書いて\n2 行目")
        await shot(page, "slack-room-revise", out, failures)
        await page.keyboard.press("Control+Enter")
        got = poll(channels[BOT])
        check(len(got) == 1 and "tasks/T-0001.json" in got[0] and "テストの観点も書いて\n2 行目" in got[0], f"the robot asked (Ctrl+Enter): {got}")
        await wait(page, f"() => document.getElementById('sf-revise').hidden && document.querySelector('{note} .sf-note-said').textContent === {json.dumps(T('sf.said.revise'))}",
                   label="the popup closed, the note says asked")
        check(await page.evaluate("() => document.activeElement && document.activeElement.matches('[data-sf-revise-open]')"), "the focus back on the note's button")
        # the robot rewrites the task (2.4.0: the note kept its old words while the focus sat on its button): the note
        # follows the file, the focus kept on the same button
        t = read_task(orch, "T-0001")
        t["title"], t["prompt"] = "カートの税込み表示（直しが入った）", "直した後のプロンプト: テストの観点も書いた"
        (orch / "tasks" / "T-0001.json").write_text(json.dumps(t, ensure_ascii=False))
        await wait(page, f"""() => document.querySelector('{note} .sf-note-title').textContent.includes('直しが入った')
          && document.querySelector('{note} .sf-prompt-text').textContent === '直した後のプロンプト: テストの観点も書いた'""", timeout=10000, label="the robot's rewrite on the note")
        check(await page.evaluate(f"() => !!document.activeElement.closest('{note}') && document.activeElement.matches('[data-sf-revise-open]')"), "the focus kept on the redrawn note's button")
        # typed and not saved, then the file changes: what was typed stays, the note says there is newer content; 読み直す takes it
        await page.click(f"{note} [data-sf-prompt-open]")
        await page.fill("#sf-edit-text", "DRAFT: まだ保存していない")
        await page.keyboard.press("Escape")
        t = read_task(orch, "T-0001")
        t["title"], t["prompt"] = "カートの税込み表示（もう一度直った）", "二度目の直し"
        (orch / "tasks" / "T-0001.json").write_text(json.dumps(t, ensure_ascii=False))
        await wait(page, f"() => document.querySelector('{note} .sf-note-title').textContent.includes('もう一度直った') && !!document.querySelector('{note} [data-sf-reload]')",
                   timeout=10000, label="the newer content said on the note")
        stale = res["stale"] = await page.evaluate(f"() => [document.querySelector('{note} .sf-prompt-text').textContent, document.querySelector('{note} [data-sf-reload]').textContent]")
        check(stale == ["DRAFT: まだ保存していない", T("sf.note.stale")], f"what was typed kept, the newer content said: {stale}")
        await page.click(f"{note} [data-sf-reload]")
        await wait(page, f"() => document.querySelector('{note} .sf-prompt-text').textContent === '二度目の直し' && !document.querySelector('{note} [data-sf-reload]')", label="読み直す")
        await page.click(f"{note} [data-sf-revise-open]")
        await page.keyboard.press("Escape")
        check(await page.evaluate("() => document.getElementById('sf-revise').hidden && window.__dbg.sfState().open"), "Esc closes the popup, not the room")
        await page.fill("#sf-say", "今日は shop を優先して")
        await page.click("#sf-send")
        got = poll(channels[BOT])
        check(got == ["今日は shop を優先して"], f"the box to the robot: {got}")

        # the start command: on T-0002 (the robot found no fitting session and wrote one), none on T-0001 (DEV is there)
        COPY = """(id) => { const c = document.querySelector(`#sf-wb [data-sf-task="${id}"] .sf-copy [data-sf-copy]`); return c ? c.dataset.sfCopy : null; }"""
        lines = res["copy"] = [await page.evaluate(COPY, "T-0002"), await page.evaluate(COPY, "T-0001")]
        pre = "JUI_VIZ_HOME=~/viz-other "                     # written from ~: the slices never carry the home's path
        check(lines == [f"cd ~/work/docs && {pre}claude --channels plugin:jui-viz@jsonui -n 'docs T-0002'", None], f"the start command only where no session fits, its session named: {lines}")
        await page.click('#sf-wb [data-sf-task="T-0002"] .sf-copy [data-sf-copy]')
        await wait(page, f"""() => document.querySelector('#sf-wb [data-sf-task="T-0002"] .sf-copy [data-sf-copy]').textContent === {json.dumps(T('sf.copied'))}""",
                   label="copied")

        # the prompts
        await page.click("#sf-prompts-btn")
        await wait(page, "() => !document.getElementById('sf-prompts').hidden", label="the prompts dialog")
        shown = await page.evaluate("""() => ({ i: document.getElementById('sf-p-instructions').value, c: document.getElementById('sf-p-chitchat').value,
          p: [...document.querySelectorAll('#sf-p-projects .sf-proj')].map((li) => [li.querySelector('input').value, li.querySelector('textarea').value]) })""")
        check(shown == {"i": "メッセージをプロジェクトに振り分ける", "c": "あいさつや雑談", "p": [["shop", "ショップのアプリ"], ["booking", "予約サイト"]]}, f"the config's words: {shown}")
        await page.evaluate("() => { document.querySelector('.sf-board').scrollTo(0, 0); document.getElementById('sf-wb').scrollTo(0, 0); }")
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
        await page.evaluate("() => { document.querySelector('.sf-board').scrollTo(0, 0); document.getElementById('sf-wb').scrollTo(0, 0); }")
        await shot(page, "slack-room-dark", out, failures)
        await page.keyboard.press("Escape")
        st = await page.evaluate(STATE)
        check(not st["open"] and st["focus"] == "btn-slack" and not st["covers"], f"Esc closes the room, the focus on the button: {st}")
        # the floors' arrow keys and the roster test for an open page-wide dialog by [aria-modal="true"]:not([hidden]):
        # nothing of the room's may answer it once the room is closed (2.4.0's arrows-rooms, room-roster, card-waits)
        await page.wait_for_timeout(600)                     # hideOverlay hides the room 240 ms after its fade
        modal = res["modal-after-close"] = await page.evaluate("""() => [...document.querySelectorAll('[aria-modal="true"]:not([hidden])')].map((e) => e.id || e.className)""")
        check(modal == [], f"no page-wide dialog is left open by the closed room: {modal}")
        code, snap = local("GET", "/api/snapshot")
        snap_text = json.dumps(snap, ensure_ascii=False)
        at = [snap_text[max(0, m.start() - 60):m.end() + 40] for m in re.finditer(re.escape(str(home)), snap_text)][:3]
        check(code == 200 and "slackRoom" in snap_text and not at, f"the snapshot carries no path under the home: {code} {at}")
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
        # the revise popup fits a phone: the box in view, the box to type in wide
        await phone.evaluate("() => document.querySelector('#sf-wb [data-sf-task=\"T-0002\"] [data-sf-revise-open]').click()")
        await wait(phone, "() => !document.getElementById('sf-revise').hidden", label="the popup on a phone")
        prv = res["phone-revise"] = await phone.evaluate("""() => { const b = document.querySelector('#sf-revise .sf-modal-box').getBoundingClientRect(), t = document.getElementById('sf-revise-text').getBoundingClientRect();
          return { left: Math.round(b.left), right: Math.round(b.right), top: Math.round(b.top), bottom: Math.round(b.bottom), w: innerWidth, h: innerHeight, text: Math.round(t.width), focus: document.activeElement.id }; }""")
        check(prv["left"] >= 0 and prv["right"] <= prv["w"] and prv["top"] >= 0 and prv["bottom"] <= prv["h"] and prv["text"] >= prv["w"] - 80 and prv["focus"] == "sf-revise-text",
              f"the popup fits a phone: {prv}")
        await shot(phone, "slack-room-phone-revise", out, failures)

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
