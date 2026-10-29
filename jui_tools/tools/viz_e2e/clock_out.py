"""退勤 from the robot card, end to end (ticket 2026-10-19-jui-viz-clock-out-button). Runs with `--only clock-out`.

The real `jui viz serve` in a throwaway HOME on a free port, PATH cut to /usr/bin:/bin (no `claude agents` poll), and
~/.claude/sessions entries written by this suite for stand-in processes it starts itself: a symlink called `claude` to
/bin/sleep. No claude runs; nothing outside this suite's own processes can be signalled (the server reads only this
HOME's entries). The stand-ins are reaped after the server stops.

Sessions: one started in a terminal (entrypoint cli), one in VS Code, one in the desktop app, and a subagent of the
terminal one. Checked: the 退勤 button above 「← 3D に戻る」; enabled only for the terminal session; disabled with the
reason for VS Code, the desktop app and the subagent; the dialog names the robot, the session's title, the folder and
the client, with やめる focused; やめる and Escape send nothing; 退勤させる ends the stand-in with SIGTERM, the session
goes ended and the robot walks out past its room's front wall and is gone; the event log has the line; the
session-recovery ledger of this HOME is marked. Light, dark and 390 px; no console error; nothing outside the server.

A Codex session (ticket 2026-10-29-viz-codex-clock-out-button), from a stand-in Codex daemon this suite serves on a Unix
socket at this HOME's ~/.codex (no codex runs): its button is enabled, the dialog says Codex and what leaving means, and
退勤させる unsubscribes from the thread (no process signalled) — the session ends, the robot walks out, and while the
daemon still lists the thread it is not subscribed to again.
"""

from __future__ import annotations

import json
import os
import pathlib
import signal
import subprocess
import sys
import time

from common import DESKTOP, ISOLATE, LAUNCH_ARGS, PHONE, T, T_head, T_pattern, Watch, dump, new_page, ready

S_TERM = "e2e00000-0000-4000-8000-0000000000e1"
S_VSC = "e2e00000-0000-4000-8000-0000000000e2"
S_DESK = "e2e00000-0000-4000-8000-0000000000e3"
SUB = "e2e-sub-clock-0001"
S_CODEX = "e2e00000-0000-4000-8000-0000000000e4"
CODEX_TITLE = "退勤テスト（Codex）"
ENTRY = {S_TERM: "cli", S_VSC: "claude-vscode", S_DESK: "claude-desktop"}
CWDS = {S_TERM: "/work/clock-term", S_VSC: "/work/clock-vscode", S_DESK: "/work/clock-desktop"}
TITLES = {S_TERM: "退勤テスト（ターミナル）", S_VSC: "退勤テスト（VS Code）", S_DESK: "退勤テスト（デスクトップ）"}

CARD = """() => {
  const b = document.querySelector('#rb [data-rb-clock]'), w = document.querySelector('#rb [data-rb-clock-why]'), c = document.getElementById('rb-close');
  if (!b) return null;
  const br = b.getBoundingClientRect(), cr = c.getBoundingClientRect();
  return { text: b.textContent, disabled: b.disabled, why: w.hidden ? '' : w.textContent, above: br.bottom <= cr.top + 1,
    nearX: Math.abs(br.right - cr.right) < 4, title: document.getElementById('rb-title').textContent };
}"""
DIALOG = """() => {
  const d = document.querySelector('.clock-confirm');
  if (!d) return null;
  const q = (k) => (d.querySelector(`[data-${k}]`) || {}).textContent || '';
  return { title: d.querySelector('h3').textContent, robot: q('clk-robot'), session: q('clk-title'), cwd: q('clk-cwd'), client: q('clk-client'),
    focus: document.activeElement && document.activeElement.hasAttribute('data-clk-cancel'), role: d.getAttribute('role') };
}"""


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def codex_daemon(home: pathlib.Path, calls: list):
    """A stand-in for the Codex app-server daemon: JSON-RPC over a WebSocket on a Unix socket, one idle thread. The
    socket lives in a short /tmp folder (a Unix socket's path has a length limit) and ~/.codex's control path links to
    it, as Codex does for a long home. Every call is kept; the thread stays loaded after an unsubscribe (the daemon's
    unload delay). Returns (runner, folder)."""
    import tempfile
    from aiohttp import web

    async def rpc(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for frame in ws:
            msg = json.loads(frame.data)
            if "id" not in msg:
                continue
            method, params = msg.get("method"), msg.get("params") or {}
            calls.append((method, params.get("threadId")))
            result: dict = {}
            if method == "thread/loaded/list":
                result = {"data": [S_CODEX]}
            elif method == "thread/resume":
                result = {"thread": {"id": S_CODEX, "cwd": "/work/clock-codex", "name": CODEX_TITLE, "source": "vscode",
                                     "status": {"type": "idle"}, "model": "e2e-model"}}
            elif method == "thread/unsubscribe":
                result = {"status": "unsubscribed"}
            elif method == "thread/read":
                result = {"thread": {"id": S_CODEX, "status": {"type": "idle"}}}
            await ws.send_str(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}))
        return ws

    app = web.Application()
    app.router.add_get("/", rpc)
    runner = web.AppRunner(app)
    await runner.setup()
    folder = pathlib.Path(tempfile.mkdtemp(prefix="jvco", dir="/tmp"))
    await web.UnixSite(runner, str(folder / "s.sock")).start()
    control = home / ".codex" / "app-server-control"
    control.mkdir(parents=True, exist_ok=True)
    link = control / "app-server-control.sock"
    if link.is_symlink():
        link.unlink()
    link.symlink_to(folder / "s.sock")
    return runner, folder


def _lstart(pid: int) -> str:
    out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, env=dict(os.environ, LC_ALL="C", LANG="C", TZ="UTC"))
    return " ".join(out.stdout.split())


async def run_clock_out(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "clock-out"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    sessions_dir = home / ".claude" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    sr = home / ".claude" / "session-recovery"
    sr.mkdir(parents=True, exist_ok=True)
    (sr / "active.json").write_text(json.dumps([{"session_id": sid, "name": TITLES[sid]} for sid in ENTRY], ensure_ascii=False, indent=2))
    bindir = out / "bin"
    bindir.mkdir(exist_ok=True)
    claude = bindir / "claude"
    if not claude.exists():
        os.symlink("/bin/sleep", claude)
    stand = {}
    for sid in ENTRY:
        p = subprocess.Popen([str(claude), "900"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        stand[sid] = p
        (sessions_dir / f"{p.pid}.json").write_text(json.dumps({"pid": p.pid, "sessionId": sid, "cwd": CWDS[sid], "kind": "interactive", "entrypoint": ENTRY[sid],
                                                                 "procStart": _lstart(p.pid), "status": "idle", "name": TITLES[sid], "startedAt": int(time.time() * 1000)}, ensure_ascii=False))
    jt = pathlib.Path(__file__).resolve().parents[2]
    port = free_port()
    env = dict({k: v for k, v in os.environ.items() if k not in ISOLATE + ("PYTHONPATH", "CLAUDE_CONFIG_DIR")}, HOME=str(home), JUI_VIZ_E2E="1", PATH="/usr/bin:/bin")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    state = home / ".local" / "state" / "jui-viz"
    res: dict = {}

    def check(cond, text):
        if not cond:
            failures.append(f"clock-out: {text}")

    def local(method, path, body=None):
        import http.client
        token = json.loads((state / "server.json").read_text())["token"]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            headers = {"X-Jui-Viz-Token": token}
            data = None
            if body is not None:
                data = json.dumps(body).encode()
                headers["Content-Type"] = "application/json"
            conn.request(method, path, body=data, headers=headers)
            r = conn.getresponse()
            raw = r.read()
            return r.status, json.loads(raw) if raw.strip() else None
        finally:
            conn.close()

    def label_of(sid):
        _, snap = local("GET", "/api/snapshot")
        return next(s["label"] for s in snap["slices"]["sessions"] if s["id"] == sid)

    def attempts():
        path = state / "clock-out.log"
        return path.read_text().splitlines() if path.exists() else []

    async def open_robot(page, label):
        await page.evaluate("(l) => document.querySelector(`#sessions [data-robot-open=\"${l}\"]`).click()", label)
        await wait(page, "(l) => document.getElementById('rb-title') && document.querySelector('#rb [data-rb-clock]') && (document.querySelector('#rb .rb-badge') || {}).textContent === l",
                   arg=label, label=f"the card of {label}")

    codex_calls: list = []
    daemon, daemon_dir = await codex_daemon(home, codex_calls)
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
        status, _ = local("POST", "/hook", {"hook_event_name": "PreToolUse", "session_id": S_TERM, "cwd": CWDS[S_TERM], "agent_id": SUB, "agent_type": "Explore",
                                            "tool_name": "Read", "tool_input": {"file_path": "/work/clock-term/a.txt"}, "tool_use_id": "t-clock-1"})
        check(status == 204, f"the subagent's hook: {status}")
        labels = {sid: label_of(sid) for sid in ENTRY}
        _, snap = local("GET", "/api/snapshot")
        res["clients"] = {s["id"]: s.get("client") for s in snap["slices"]["sessions"] if s["id"] in ENTRY}
        check(res["clients"] == {S_TERM: "terminal", S_VSC: "vscode", S_DESK: "desktop"}, f"the sessions' clients: {res['clients']}")
        sub_label = next(a["label"] for a in snap["slices"]["agents"] if a["id"] == SUB)
        watch = Watch(origin=url)
        page = await new_page(browser, watch, "clock-out", **DESKTOP)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelectorAll('#sessions [data-robot-open]').length >= 3", label="three sessions")

        # VS Code and the desktop app: the button is there, disabled, with the reason
        for sid, words, name in ((S_VSC, T("panel.clk.why.vscode"), "vscode"), (S_DESK, T("panel.clk.why.desktop"), "desktop")):
            await open_robot(page, labels[sid])
            await page.wait_for_timeout(600)
            r = res[name] = await page.evaluate(CARD)
            check(r and r["disabled"] and words in r["why"] and r["above"] and r["nearX"], f"{name}: disabled with the reason, above 「← 3D に戻る」: {r}")
            await page.click("#rb [data-rb-clock]", force=True)
            check(await page.evaluate(DIALOG) is None, f"{name}: a disabled button opens nothing")
            await page.screenshot(path=str(out / f"{name}-disabled.png"))
        # the subagent: disabled, with the reason (its card, as the 3D view opens it)
        await page.evaluate("(l) => window.__dbg.openRobot(l)", sub_label)
        await wait(page, "(l) => (document.querySelector('#rb .rb-badge') || {}).textContent === l", arg=sub_label, label="the subagent's card")
        await page.wait_for_timeout(400)
        r = res["sub"] = await page.evaluate(CARD)
        check(r and r["disabled"] and T_pattern("panel.clk.why.sub").search(r["why"]), f"a subagent: disabled with the reason: {r}")
        await page.screenshot(path=str(out / "sub-disabled.png"))

        # the terminal session: enabled; the dialog; やめる and Escape send nothing
        await open_robot(page, labels[S_TERM])
        await page.wait_for_timeout(600)
        r = res["terminal"] = await page.evaluate(CARD)
        check(r and not r["disabled"] and r["why"] == "" and r["above"] and r["nearX"] and r["text"] == T("panel.clk.button"), f"terminal: enabled, above 「← 3D に戻る」: {r}")
        await page.screenshot(path=str(out / "terminal-card-light.png"))
        await page.click("#rb [data-rb-clock]")
        r = res["dialog"] = await page.evaluate(DIALOG)
        check(r and r["focus"] and labels[S_TERM] in r["robot"] and r["session"] == TITLES[S_TERM] and "clock-term" in r["cwd"] and r["client"] == T("panel.client.terminal")
              and r["role"] == "alertdialog", f"the dialog names the robot, the session, the folder and the client, with やめる focused: {r}")
        await page.screenshot(path=str(out / "dialog-light.png"))
        await page.keyboard.press("Enter")   # the focused button is やめる
        check(await page.evaluate(DIALOG) is None, "Enter on the default button (やめる) closes it")
        await page.click("#rb [data-rb-clock]")
        await page.keyboard.press("Escape")
        check(await page.evaluate(DIALOG) is None, "Escape closes it")
        await page.click("#rb [data-rb-clock]")
        await page.click(".clock-confirm [data-clk-cancel]")
        check(await page.evaluate(DIALOG) is None, "やめる closes it")
        await page.wait_for_timeout(800)
        res["afterCancel"] = {"alive": stand[S_TERM].poll() is None, "attempts": len(attempts()),
                              "ended": next(s["status"] for s in local("GET", "/api/snapshot")[1]["slices"]["sessions"] if s["id"] == S_TERM) == "ended"}
        check(res["afterCancel"] == {"alive": True, "attempts": 0, "ended": False}, f"cancel sends nothing: {res['afterCancel']}")
        # dark: the card and the dialog
        await page.emulate_media(color_scheme="dark")
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(out / "terminal-card-dark.png"))
        await page.click("#rb [data-rb-clock]")
        await page.wait_for_timeout(300)
        await page.screenshot(path=str(out / "dialog-dark.png"))
        await page.keyboard.press("Escape")
        await open_robot(page, labels[S_VSC])
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(out / "vscode-disabled-dark.png"))
        await page.emulate_media(color_scheme="light")
        await open_robot(page, labels[S_TERM])

        # 退勤させる: the stand-in ends with SIGTERM, the session ends, the robot walks out of the door
        lbl = labels[S_TERM]
        await page.evaluate("""(l) => { window.__clk = { samples: [], out: false, gone: false };
          const tick = () => { const R = window.__dbg.robots.find((x) => x.def.id === l);
            if (!R) { window.__clk.gone = true; return; }
            if (R.out) window.__clk.out = true;
            const p = R.robot.root.position; window.__clk.samples.push([+p.x.toFixed(2), +p.z.toFixed(2), !!R.out]);
            setTimeout(tick, 150); };
          tick(); }""", lbl)
        room = await page.evaluate("(l) => window.__dbg.room(window.__dbg.robots.find((x) => x.def.id === l).def.room)", lbl)
        await page.click("#rb [data-rb-clock]")
        await page.wait_for_timeout(500)
        await page.click(".clock-confirm [data-clk-go]")
        try:
            code = stand[S_TERM].wait(timeout=15)
        except subprocess.TimeoutExpired:
            code = None
        check(code == -signal.SIGTERM, f"the terminal stand-in ended by SIGTERM: {code}")
        check(all(stand[s].poll() is None for s in (S_VSC, S_DESK)), "the other stand-ins are untouched")
        await wait(page, "(l) => { const R = window.__dbg.robots.find((x) => x.def.id === l); return !R || R.exitAt > 0 || R.out; }", arg=lbl, label="leaving")
        await page.wait_for_timeout(900)
        await page.screenshot(path=str(out / "leaving.png"))
        await wait(page, "() => window.__clk.gone", timeout=90000, label="the robot walked out and is gone")
        clk = res["walk"] = await page.evaluate("() => ({ out: window.__clk.out, n: window.__clk.samples.length, last: window.__clk.samples.slice(-3) })")
        last = clk["last"][-1] if clk["last"] else None
        check(clk["out"] and last and room and last[1] > room["z1"], f"it walked out past its room's front wall (z1 {room and room['z1']}) and was then removed: {clk}")
        _, snap = local("GET", "/api/snapshot")
        s = next(x for x in snap["slices"]["sessions"] if x["id"] == S_TERM)
        check(s["status"] == "ended" and s.get("clockedOut"), f"the session is ended: {s.get('status')}")
        head = T_head("ev.clockout", "label", pid="", how="", why="")   # "Clock-out signal → " / "退勤の合図 → "
        res["log"] = await page.evaluate("(head) => [...document.querySelectorAll('body *')].map((n) => n.childElementCount ? '' : n.textContent).find((t) => t.includes(head)) || ''", head)
        check(f"{head}{lbl}" in res["log"] and T("ev.clockout.ended") in res["log"], f"the event log has the line: {res['log']!r}")
        ledger = {e["session_id"]: e.get("ended_reason") for e in json.loads((sr / "active.json").read_text())}
        res["ledger"] = ledger
        check(ledger == {S_TERM: "clocked-out", S_VSC: None, S_DESK: None}, f"the ledger: {ledger}")
        recs = [json.loads(x) for x in attempts()]
        res["attempts"] = [(r["result"], r["status"]) for r in recs]
        check(res["attempts"] == [("ended", 200)], f"one attempt, ended: {res['attempts']}")
        await page.screenshot(path=str(out / "after-gone.png"))

        # a Codex session: enabled; the dialog says Codex; 退勤させる unsubscribes from its thread and signals nothing
        for _ in range(100):   # the link connects to the stand-in daemon and polls it (POLL_SEC 3)
            if any(x["id"] == S_CODEX for x in local("GET", "/api/snapshot")[1]["slices"]["sessions"]):
                break
            await page.wait_for_timeout(200)
        codex_label = label_of(S_CODEX)
        await wait(page, "(l) => !!document.querySelector(`#sessions [data-robot-open=\"${l}\"]`)", arg=codex_label, label="the Codex session's row")
        await open_robot(page, codex_label)
        await page.wait_for_timeout(600)
        r = res["codex"] = await page.evaluate(CARD)
        check(r and not r["disabled"] and r["why"] == "" and r["above"] and r["nearX"], f"codex: enabled, above 「← 3D に戻る」: {r}")
        await page.screenshot(path=str(out / "codex-card-light.png"))
        await page.click("#rb [data-rb-clock]")
        r = res["codexDialog"] = await page.evaluate(DIALOG)
        note = await page.evaluate("() => (document.getElementById('clk-note') || {}).textContent || ''")
        check(r and r["focus"] and r["session"] == CODEX_TITLE and "clock-codex" in r["cwd"] and r["client"] == T("panel.client.codex")
              and note == T("panel.clk.note.codex"), f"codex: the dialog says Codex and what leaving means: {r} {note!r}")
        await page.screenshot(path=str(out / "codex-dialog-light.png"))
        await page.emulate_media(color_scheme="dark")
        await page.wait_for_timeout(400)
        await page.screenshot(path=str(out / "codex-dialog-dark.png"))
        await page.emulate_media(color_scheme="light")
        resumes = [c for c in codex_calls if c[0] == "thread/resume"]
        await page.click(".clock-confirm [data-clk-go]")
        await wait(page, "(t) => (document.getElementById('toast') || {}).textContent === t", arg=T("panel.clk.done.codex_held", id=codex_label),
                   label="the Codex clock-out toast")
        await page.screenshot(path=str(out / "codex-toast.png"))
        await wait(page, "(l) => !window.__dbg.robots.find((x) => x.def.id === l)", arg=codex_label, timeout=90000, label="the Codex robot walked out and is gone")
        _, snap = local("GET", "/api/snapshot")
        s = next(x for x in snap["slices"]["sessions"] if x["id"] == S_CODEX)
        check(s["status"] == "ended" and s.get("clockedOut"), f"codex: the session is ended: {s.get('status')}")
        await page.wait_for_timeout(7000)   # two of the link's polls: the daemon still lists the thread
        res["codexCalls"] = {"unsubscribe": [c[1] for c in codex_calls if c[0] == "thread/unsubscribe"],
                             "resumesAfter": len([c for c in codex_calls if c[0] == "thread/resume"]) - len(resumes)}
        check(res["codexCalls"] == {"unsubscribe": [S_CODEX], "resumesAfter": 0}, f"codex: unsubscribed once, not subscribed to again: {res['codexCalls']}")
        recs = [json.loads(x) for x in attempts()]
        res["attempts"] = [(r["result"], r["status"], r.get("cli")) for r in recs]
        check(res["attempts"] == [("ended", 200, None), ("ended", 200, "codex")], f"two attempts, both ended: {res['attempts']}")
        check(all(stand[s].poll() is None for s in (S_VSC, S_DESK)), "codex: the other stand-ins are untouched")
        want = T("ev.clockout.codex", label=codex_label, how=T("ev.clockout.ended"), why="")
        res["codexLog"] = await page.evaluate("(w) => [...document.querySelectorAll('body *')].map((n) => n.childElementCount ? '' : n.textContent).find((t) => t.includes(w)) || ''", want)
        signal_head = T_head("ev.clockout", "label", pid="", how="", why="")
        check(res["codexLog"] and signal_head not in res["codexLog"], f"codex: the event log says no signal was sent: {res['codexLog']!r}")
        # 390 px: the card with the button, no horizontal scroll
        phone = await new_page(browser, watch, "clock-out-phone", **PHONE)
        await phone.goto(url + "/")
        await ready(phone)
        await wait(phone, "() => document.querySelectorAll('#sessions [data-robot-open]').length >= 2", label="the phone's sessions")
        await open_robot(phone, labels[S_VSC])
        await phone.wait_for_timeout(500)
        r = res["phone"] = await phone.evaluate("() => ({ hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth, why: !document.querySelector('#rb [data-rb-clock-why]').hidden })")
        await phone.screenshot(path=str(out / "phone.png"))
        check(r == {"hscroll": False, "why": True}, f"390 px: the reason shows, no horizontal scroll: {r}")
        await phone.close()
        await page.close()
        for line in watch.console:
            failures.append(f"clock-out: console: {line}")
        for u in watch.foreign:
            failures.append(f"clock-out: request outside the server: {u}")
    except Exception as e:
        failures.append(f"clock-out: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
        await daemon.cleanup()
        import shutil
        shutil.rmtree(daemon_dir, ignore_errors=True)   # the folder this suite made for the stand-in daemon's socket
        for p in stand.values():   # our own stand-ins, reaped after the server stopped
            if p.poll() is None:
                p.kill()
            p.wait(timeout=10)
    print(f"  clock-out: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "clock-out-results.json").write_text(dump(res) + "\n")
