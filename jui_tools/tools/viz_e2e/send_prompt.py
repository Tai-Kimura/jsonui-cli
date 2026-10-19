"""A prompt from the robot card's 応答の履歴 tab, end to end (requester, 10-19). Runs with `--only history`.

The real `jui viz serve` in a throwaway HOME on a free port, the real forward.py for the hooks, and a stand-in for
channel.py: this suite says hello on /channel/hello (with and without ``accepts: ["prompt"]``) and takes what the
server queued through /channel/poll, as channel.py does — no claude, no real session.

Three sessions: one whose channel can deliver (jui-viz 1.2.0), one on an old plugin (relay, no prompts) and one
without relay. Checked: the box under the history; Enter is a new line and sends nothing; 送信… opens a confirmation
naming the robot and the session, やめる keeps the text, Ctrl+Enter opens it too, only its button sends; the channel gets
the text exactly; 「送信中」 (never "arrived") until the prompt shows in the receiver's transcript, then 「届いた」, and
「届いていない」 when it does not (2.3.4); the event log line has the head only; what is
typed survives a rebuild of the card with the focus kept; the old plugin and the relay-less session get the box
disabled with the reason, and so do a session started without the channels flag and the VS Code extension's (2.3.4:
the CLI drops the text unless the channel was named at launch; each session's "process" here is a sleeping python
whose argv carries the flags, named by a session file). Dark and 390 px; no console error; nothing outside the server.
"""

from __future__ import annotations

import http.client
import json
import os
import pathlib
import re
import subprocess
import sys
import time

from common import DESKTOP, ISOLATE, LAUNCH_ARGS, PHONE, Watch, dump, new_page, ready, stamp

S_OK = "e2e00000-0000-4000-8000-0000000000d1"
S_OLD = "e2e00000-0000-4000-8000-0000000000d2"
S_NONE = "e2e00000-0000-4000-8000-0000000000d3"
S_PLAIN = "e2e00000-0000-4000-8000-0000000000d4"
S_IDE = "e2e00000-0000-4000-8000-0000000000d5"
CWDS = {S_OK: "/work/prompt-ok", S_OLD: "/work/prompt-old", S_NONE: "/work/prompt-none", S_PLAIN: "/work/prompt-plain", S_IDE: "/work/prompt-ide"}
DEV = "--dangerously-load-development-channels"
LINE1 = "一行目のテスト依頼"
LINE2 = '二行目 <b>太字ではない</b> "引用" ' + "続く" * 20 + " 末尾TAILX"
TEXT = f"{LINE1}\n{LINE2}"


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def run_send_prompt(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "send-prompt"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    state = home / ".local" / "state" / "jui-viz"
    state.mkdir(parents=True, exist_ok=True)
    transcripts = {}
    for sid, cwd in CWDS.items():
        t = home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", cwd) / f"{sid}.jsonl"
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text(json.dumps({"type": "user", "timestamp": stamp("2026-10-19T09:00:00Z"), "message": {"role": "user", "content": "最初の依頼"}}, ensure_ascii=False) + "\n"
                     + json.dumps({"type": "assistant", "timestamp": stamp("2026-10-19T09:00:01Z"), "message": {"id": "a1", "role": "assistant", "content": [{"type": "text", "text": "最初の応答"}]}}, ensure_ascii=False) + "\n")
        transcripts[sid] = t
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    sessions_dir = home / ".claude" / "sessions"   # watched by the server from its start
    sessions_dir.mkdir(parents=True, exist_ok=True)
    stand_ins: list = []

    def session_process(sid, *args, entrypoint="cli"):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(900)", *args],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        stand_ins.append(proc)
        (sessions_dir / f"{proc.pid}.json").write_text(json.dumps({"pid": proc.pid, "sessionId": sid, "cwd": CWDS[sid], "kind": "interactive",
                                                                  "entrypoint": entrypoint, "status": "idle", "procStart": f"t{proc.pid}"}))
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def check(cond, text):
        if not cond:
            failures.append(f"send-prompt: {text}")

    def hook(sid, **payload):
        subprocess.run([sys.executable, "-I", "-S", str(forward)], timeout=10, capture_output=True, env=dict(base_env, HOME=str(home)),
                       input=json.dumps({"session_id": sid, "cwd": CWDS[sid], "transcript_path": str(transcripts[sid]), "permission_mode": "default", **payload}).encode())

    def local(method, path, body=None, timeout=5):
        """The stand-in for channel.py: token, no Origin."""
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

    async def open_robot(page, sid):
        _, snap = local("GET", "/api/snapshot")
        label = next(s["label"] for s in snap["slices"]["sessions"] if s["id"] == sid)
        await page.evaluate("(l) => document.querySelector(`#sessions [data-robot-open=\"${l}\"]`).click()", label)
        await wait(page, "(l) => document.getElementById('rb-title') && document.getElementById('rb-title').textContent.startsWith(l)", arg=label, label=f"the card of {label}")
        if await page.evaluate("() => document.querySelector('[data-rb-hist]').hidden"):
            await page.click('#rb [data-rb-tab="history"]')
        await wait(page, "() => document.querySelector('[data-rb-hist]').textContent.includes('最初の応答')", label=f"{label}'s history")
        return label

    COMPOSE = """() => {
      const b = document.querySelector('[data-h-compose]');
      if (!b) return null;
      const q = (k) => b.querySelector(`[data-${k}]`);
      return { shown: !b.hidden && b.getBoundingClientRect().height > 0, disabled: q('h-text').disabled, why: q('h-why').hidden ? '' : q('h-why').textContent,
        value: q('h-text').value, state: q('h-state').textContent, confirm: !q('h-confirm').hidden, to: q('h-to').textContent,
        preview: q('h-preview').textContent, sendDisabled: q('h-send').disabled, focus: document.activeElement === q('h-text') };
    }"""

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
        for sid in CWDS:
            hook(sid, hook_event_name="SessionStart", source="startup")
        # the channels: 1.2.0 for S_OK, 1.1.0 (no accepts) for S_OLD, none for S_NONE
        session_process(S_OK, DEV, "plugin:jui-viz@jsonui")
        session_process(S_OLD, DEV, "plugin:jui-viz@jsonui")
        session_process(S_PLAIN)                                            # `claude` as typed
        session_process(S_IDE, "--output-format", "stream-json", entrypoint="claude-vscode")
        for sid in (S_PLAIN, S_IDE):
            local("POST", "/channel/hello", {"ppid": 1, "cwd": "/", "sessionId": sid, "version": "2", "accepts": ["prompt"], "via": "plugin"})
        status, hello = local("POST", "/channel/hello", {"ppid": 1, "cwd": "/", "sessionId": S_OK, "version": "2", "accepts": ["prompt"], "via": "plugin"})
        check(status == 200, f"hello: {status}")
        ok_channel = hello["channelId"]
        local("POST", "/channel/hello", {"ppid": 1, "cwd": "/", "sessionId": S_OLD})
        for _ in range(100):
            _, snap = local("GET", "/api/snapshot")
            launches = {s["id"]: s.get("launch") for s in snap["slices"]["sessions"]}
            if launches.get(S_OK) == "dev" and launches.get(S_PLAIN) == "no-flag" and launches.get(S_IDE) == "vscode":
                break
            time.sleep(0.1)
        res["launches"] = {CWDS[k].rsplit("-", 1)[1]: v for k, v in launches.items()}
        check(res["launches"] == {"ok": "dev", "old": None, "none": None, "plain": "no-flag", "ide": "vscode"}, f"the launches: {res['launches']}")
        watch = Watch(origin=url)
        page = await new_page(browser, watch, "send-prompt", **DESKTOP)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelectorAll('#sessions [data-robot-open]').length >= 5", label="five sessions")
        label = await open_robot(page, S_OK)
        r = res["open"] = await page.evaluate(COMPOSE)
        check(r and r["shown"] and not r["disabled"] and r["why"] == "" and r["sendDisabled"], f"the box shows under the history, empty: {r}")
        # Enter is a new line, nothing sent
        await page.click("[data-h-text]")
        await page.keyboard.type(LINE1)
        await page.keyboard.press("Enter")
        await page.keyboard.type(LINE2)
        r = res["typed"] = await page.evaluate(COMPOSE)
        check(r["value"] == TEXT and not r["confirm"], f"Enter is a new line and opens nothing: {r}")
        # a rebuild of the card (a task of the robot) keeps the text and the focus
        await page.evaluate("() => { document.querySelector('[data-rb-hist]').__mark = 1; }")
        hook(S_OK, hook_event_name="TaskCreated", task_id="1", task_subject="作業-1")
        await wait(page, "() => !document.querySelector('[data-rb-hist]').__mark", timeout=10000, label="the card rebuilt")
        r = res["rebuilt"] = await page.evaluate(COMPOSE)
        check(r["value"] == TEXT and r["focus"] and r["shown"], f"a rebuilt card keeps what is typed and the focus: {r}")
        # 送信… → the confirmation names the robot and the session; やめる keeps the text
        await page.click("[data-h-send]")
        r = res["confirm"] = await page.evaluate(COMPOSE)
        check(r["confirm"] and label in r["to"] and "メインセッション" in r["to"] and "prompt-ok" in r["to"] and r["preview"] == TEXT,
              f"the confirmation names the robot and the session and shows the text: {r}")
        await page.screenshot(path=str(out / "confirm.png"))
        await page.click("[data-h-back]")
        r = res["back"] = await page.evaluate(COMPOSE)
        check(not r["confirm"] and r["value"] == TEXT, f"やめる closes it and keeps the text: {r}")
        _, polled = local("GET", f"/channel/poll?channelId={ok_channel}", timeout=30)
        check(polled["prompts"] == [], f"nothing was sent before the confirmation: {polled}")
        # Ctrl+Enter opens it too; only its button sends
        await page.focus("[data-h-text]")
        await page.keyboard.press("Control+Enter")
        r = await page.evaluate(COMPOSE)
        check(r["confirm"], f"Ctrl+Enter opens the confirmation: {r}")
        await page.wait_for_timeout(500)
        await page.click("[data-h-go]")
        await wait(page, "() => document.querySelector('[data-h-compose] [data-h-state]').textContent.startsWith('送信中')", label="送信中")
        r = res["sent"] = await page.evaluate(COMPOSE)
        check(r["value"] == "" and not r["confirm"] and "まだ届いたとは言えない" in r["state"] and "届いた（" not in r["state"],
              f"sent: the box is empty again, and the page says 送信中, not arrived: {r}")
        _, polled = local("GET", f"/channel/poll?channelId={ok_channel}", timeout=30)
        check(polled["prompts"] == [{"text": TEXT}], f"the channel got the text exactly: {polled}")
        await page.screenshot(path=str(out / "sent.png"))
        # the event log: when, to whom, the head
        await wait(page, "() => document.body.textContent.includes('ブラウザからプロンプトを送信')", timeout=10000, label="the event log line")
        res["log"] = await page.evaluate("() => [...document.querySelectorAll('body *')].map((n) => n.childElementCount ? '' : n.textContent).find((t) => t.includes('ブラウザからプロンプトを送信')) || ''")
        check(LINE1 in res["log"] and "TAILX" not in res["log"], f"the log line has the head only: {res['log']!r}")
        # the same words typed by hand are not the channel's record: still 送信中
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with open(transcripts[S_OK], "a") as f:
            f.write(json.dumps({"type": "user", "timestamp": now_iso, "message": {"role": "user", "content": TEXT}}, ensure_ascii=False) + "\n")
        await wait(page, "() => document.querySelector('[data-rb-hist]').textContent.includes('末尾TAILX')", timeout=15000, label="the hand-typed copy")
        await page.wait_for_timeout(3500)
        res["handTyped"] = await page.evaluate(COMPOSE)
        check(res["handTyped"]["state"].startswith("送信中"), f"the same words typed by hand are not an arrival: {res['handTyped']}")
        # the CLI's own record of the channel text, in the shape seen on a real receiver (10-19 09:20): 届いた
        with open(transcripts[S_OK], "a") as f:
            f.write(json.dumps({"type": "user", "isMeta": True, "promptSource": "system", "timestamp": now_iso,
                                "origin": {"kind": "channel", "server": "plugin:jui-viz:jui-viz"}, "userType": "external", "entrypoint": "cli",
                                "message": {"role": "user", "content": f'<channel source="plugin:jui-viz:jui-viz" sender="jui_viz_page">\n{TEXT}\n</channel>'}},
                               ensure_ascii=False) + "\n")
        await wait(page, "() => document.querySelector('[data-h-compose] [data-h-state]').textContent.startsWith('届いた')", timeout=15000, label="届いた once it shows in the transcript")
        res["arrived"] = await page.evaluate(COMPOSE)
        await page.screenshot(path=str(out / "arrived.png"))
        # a prompt that never shows in the transcript: 届いていない (the waits shortened through the e2e hook)
        await page.evaluate("() => { window.__dbg.promptWait.notArrivedMs = 2500; window.__dbg.promptWait.quietMs = 1000; }")
        await page.click("[data-h-text]")
        await page.keyboard.type("届かない確認")
        await page.click("[data-h-send]")
        await page.wait_for_timeout(500)
        await page.click("[data-h-go]")
        await wait(page, "() => document.querySelector('[data-h-compose] [data-h-state]').textContent.startsWith('送信中')", label="送信中 again")
        res["sending2"] = await page.evaluate(COMPOSE)
        await wait(page, "() => document.querySelector('[data-h-compose] [data-h-state]').textContent.startsWith('届いていない')", timeout=15000, label="届いていない")
        res["missing"] = await page.evaluate(COMPOSE)
        check("候補" in res["missing"]["state"], f"届いていない names the likely causes: {res['missing']}")
        await page.screenshot(path=str(out / "missing.png"))
        await page.evaluate("() => { window.__dbg.promptWait.notArrivedMs = 60000; window.__dbg.promptWait.quietMs = 30000; }")
        local("GET", f"/channel/poll?channelId={ok_channel}", timeout=30)   # the stand-in takes it
        # started without the flag, or in the VS Code extension: disabled, with the reason and how to start
        await open_robot(page, S_PLAIN)
        r = res["plain"] = await page.evaluate(COMPOSE)
        check(r["disabled"] and "起動に channel の指定が無い" in r["why"] and "claude --dangerously-load-development-channels plugin:jui-viz@jsonui" in r["why"]
              and r["sendDisabled"], f"no flag: disabled, with the reason and the command: {r}")
        await page.screenshot(path=str(out / "no-flag.png"))
        await open_robot(page, S_IDE)
        r = res["ide"] = await page.evaluate(COMPOSE)
        check(r["disabled"] and "VS Code 拡張" in r["why"] and r["sendDisabled"], f"the VS Code extension: disabled, with the reason: {r}")
        # the old plugin and the relay-less session: disabled, with the reason
        await open_robot(page, S_OLD)
        r = res["old"] = await page.evaluate(COMPOSE)
        check(r["disabled"] and "古い" in r["why"] and "1.2.0" in r["why"] and r["sendDisabled"], f"an old plugin: disabled, with the reason: {r}")
        await page.screenshot(path=str(out / "old-plugin.png"))
        await open_robot(page, S_NONE)
        r = res["none"] = await page.evaluate(COMPOSE)
        check(r["disabled"] and "中継" in r["why"] and r["sendDisabled"] and r["value"] == "", f"relay: false: disabled, with the reason: {r}")
        await page.screenshot(path=str(out / "no-relay.png"))
        await page.emulate_media(color_scheme="dark")
        await open_robot(page, S_OK)
        await page.click("[data-h-text]")
        await page.keyboard.type("暗い色の確認")
        await page.click("[data-h-send]")
        await page.wait_for_timeout(300)
        await page.screenshot(path=str(out / "confirm-dark.png"))
        await page.click("[data-h-back]")
        phone = await new_page(browser, watch, "send-prompt-phone", **PHONE)
        await phone.goto(url + "/")
        await ready(phone)
        await wait(phone, "() => document.querySelectorAll('#sessions [data-robot-open]').length >= 5", label="the phone's sessions")
        await open_robot(phone, S_OK)
        r = res["phone"] = await phone.evaluate("() => ({ hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth, box: !!document.querySelector('[data-h-compose]:not([hidden])') })")
        await phone.screenshot(path=str(out / "phone.png"))
        check(r == {"hscroll": False, "box": True}, f"390 px: the box shows, no horizontal scroll: {r}")
        await phone.close()
        await page.close()
        for line in watch.console:
            failures.append(f"send-prompt: console: {line}")
        for u in watch.foreign:
            failures.append(f"send-prompt: request outside the server: {u}")
    except Exception as e:
        failures.append(f"send-prompt: {type(e).__name__}: {str(e).splitlines()[0]}")
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
    print(f"  history/send-prompt: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "send-prompt-results.json").write_text(dump(res) + "\n")
