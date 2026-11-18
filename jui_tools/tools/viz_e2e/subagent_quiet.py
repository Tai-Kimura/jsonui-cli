"""A subagent that stopped moving (ticket 2026-11-18-viz-notify-main-when-a-subagent-quiets; requester: 「サブエージェントに
作業依頼した後サブエージェントが止まってるのにメインエージェントが気づかないことがよくある。これ自動で検知してメインに通知するような
仕組み viz に入れれないかな？」). Runs with `--only subagent-quiet`.

The real `jui viz serve` in a throwaway HOME, its config.json with short limits (quiet 0.1 min, a person's answer
0.05 min: the 20 and 5 minutes of the default, a few seconds here); the hooks replayed through forward.py; a stand-in
for channel.py (hello, then /channel/poll for as long as it lives). One main session started with the channel, its turn
over with two background subagents: A goes quiet, B asks for a permission. Checked:
  * A: one notice in the main's channel (the srv.stall.quiet words with its type, id, last tool and transcript), not two
    while it stays quiet; its robot's bubble "zz"; one line in the event log;
  * A's transcript grows: the bubble goes; quiet again: a second notice;
  * B: the srv.stall.wait words (only a person can answer), its robot's permission bubble;
  * C, started inside a foreground Agent call: never the main's channel; one desktop notification (recorded, not shown,
    under JUI_VIZ_E2E) and its event line says so;
  * A stops (SubagentStop): no more notices after it;
  * stills: light and dark.
No console error; nothing outside the server."""
from __future__ import annotations

import http.client
import json
import os
import pathlib
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import DESKTOP, ISOLATE, LAUNCH_ARGS, T, Watch, dump, ready  # noqa: E402

MAIN = "5a110000-0000-4000-8000-0000000000a1"
A = "aa11c0ffee000a01"
B = "bb22d00d00000b02"
C = "cc33f00f00000c03"   # a foreground call: the main is inside it
CWD = "/work/stall-app"


def check(failures, cond, text):
    if not cond:
        failures.append(f"subagent-quiet: {text}")


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def run_subagent_quiet(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "subagent-quiet"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    state = home / ".local" / "state" / "jui-viz"
    state.mkdir(parents=True, exist_ok=True)
    (state / "config.json").write_text(json.dumps({"subagentStallMin": 0.1, "subagentWaitMin": 0.05}))
    transcripts = home / "t"
    transcripts.mkdir(exist_ok=True)
    ta = transcripts / f"agent-{A}.jsonl"
    ta.write_text('{"type":"user"}\n')
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    sessions_dir = home / ".claude" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    stand_ins: list = []
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT,
                           env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def hook(**payload):
        body = {"session_id": MAIN, "cwd": CWD, "transcript_path": "/work/none.jsonl", "permission_mode": "default", **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(), capture_output=True,
                       env=dict(base_env, HOME=str(home)), timeout=10)

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

    inbox: list = []
    done = threading.Event()

    def keep_polling(channel):
        """channel.py's loop: it polls for as long as it lives (a channel not polled for 60 s is dead to the server)."""
        while not done.is_set():
            try:
                _, polled = local("GET", f"/channel/poll?channelId={channel}", timeout=35)
            except (OSError, ValueError, http.client.HTTPException):
                done.wait(0.2)
                continue
            inbox.extend(p["text"] for p in (polled or {}).get("prompts", []))

    def taken(want, within):
        end = time.time() + within
        while len(inbox) < want and time.time() < end:
            time.sleep(0.1)
        got = list(inbox)
        inbox.clear()
        return got

    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    watch = Watch(origin=url)
    ctx = None
    t0 = time.monotonic()
    try:
        import urllib.request
        for _ in range(400):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(900)", "--channels", "plugin:jui-viz@jsonui"],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        stand_ins.append(proc)
        (sessions_dir / f"{proc.pid}.json").write_text(json.dumps({"pid": proc.pid, "sessionId": MAIN, "cwd": CWD, "kind": "interactive",
                                                                  "entrypoint": "cli", "status": "idle", "procStart": f"t{proc.pid}"}))
        hook(hook_event_name="SessionStart", source="startup")
        status, hello = local("POST", "/channel/hello", {"ppid": 1, "cwd": "/", "sessionId": MAIN, "version": "2", "accepts": ["prompt"], "via": "plugin"})
        check(failures, status == 200, f"hello: {status}")
        threading.Thread(target=keep_polling, args=(hello["channelId"],), daemon=True).start()

        ctx = await browser.new_context(**DESKTOP)
        page = await ctx.new_page()
        watch.attach(page, "subagent-quiet")
        await page.goto(url + "/")
        await ready(page)

        hook(hook_event_name="UserPromptSubmit", prompt="調べてきて")
        hook(hook_event_name="SubagentStart", agent_id=A, agent_type="Explore", agent_transcript_path=str(ta))
        hook(hook_event_name="SubagentStart", agent_id=B, agent_type="general-purpose")
        hook(hook_event_name="PreToolUse", agent_id=A, agent_type="Explore", tool_name="Bash", tool_input={"command": "npm test"}, tool_use_id="ua1")
        hook(hook_event_name="PostToolUse", agent_id=A, agent_type="Explore", tool_name="Bash", tool_input={"command": "npm test"}, tool_use_id="ua1",
             tool_response={"stdout": "ok"})
        hook(hook_event_name="PreToolUse", agent_id=B, agent_type="general-purpose", tool_name="Write", tool_input={"file_path": "/work/stall-app/x.txt", "content": "x"}, tool_use_id="ub1")
        hook(hook_event_name="PermissionRequest", agent_id=B, agent_type="general-purpose", tool_name="Write", tool_input={"file_path": "/work/stall-app/x.txt", "content": "x"})
        hook(hook_event_name="Stop", background_tasks=[{"id": A, "type": "subagent", "status": "running", "description": "テストの失敗を調べる"},
                                                       {"id": B, "type": "subagent", "status": "running"}])   # the main's turn over, both in the background
        # the next turn: a foreground call; C starts inside it and goes quiet (the main waits on the call)
        hook(hook_event_name="UserPromptSubmit", prompt="もう一つ")
        hook(hook_event_name="PreToolUse", tool_name="Agent", tool_input={"subagent_type": "Plan", "prompt": "plan it"}, tool_use_id="fg1")
        hook(hook_event_name="SubagentStart", agent_id=C, agent_type="Plan")
        t_quiet = time.time()

        # B waits on a person: told after 3 s; A quiet: told after 6 s. Both, once.
        got = taken(2, 30)
        res["first"] = [g[:240] for g in got]
        head_line = T("srv.stall.wait", type="general-purpose", id=B[:8], since="", tool="Write", head="", path="-").split("\n")[0]   # 「jui viz からの知らせ…（ユーザーの指示ではありません）」
        quiet = [g for g in got if A[:8] in g]
        waits = [g for g in got if f"({B[:8]})" in g or f"（{B[:8]}）" in g]
        check(failures, len(got) == 2 and len(quiet) == 1 and len(waits) == 1 and not any(C[:8] in g for g in got),
              f"one notice each for A and B, none for the foreground C: {res['first']}")
        desk = state / "desktop-notices.e2e.jsonl"
        for _ in range(100):
            if desk.exists():
                break
            time.sleep(0.1)
        notes = res["desktop"] = [json.loads(l) for l in desk.read_text().splitlines()] if desk.exists() else []
        check(failures, len(notes) == 1 and notes[0]["title"] == T("wait.stall") and "Plan" in notes[0]["text"],
              f"C, in the foreground: one desktop notification, not the main's channel: {notes}")
        if quiet:
            check(failures, "npm test" in quiet[0] and str(ta) in quiet[0] and quiet[0].split("\n")[0] == head_line and "テストの失敗を調べる" in quiet[0],
                  f"A's notice: its last tool, its transcript, the not-a-user-instruction head: {quiet[0][:300]}")
        if waits:
            check(failures, "/work/stall-app/x.txt" in waits[0] and "Write" in waits[0], f"B's notice: the call it waits on: {waits[0][:300]}")
        res["told-after-s"] = round(time.time() - t_quiet, 1)
        la = await page.evaluate("(a) => window.__dbg.labelOfAgent(a)", A)
        lb = await page.evaluate("(a) => window.__dbg.labelOfAgent(a)", B)
        lc = await page.evaluate("(a) => window.__dbg.labelOfAgent(a)", C)
        await wait(page, "(id) => { const w = window.__dbg.waitLook(id); return w && w.kind === 'stall' && w.bubble === 'zz'; }", arg=la, label="A's zz bubble")
        await wait(page, "(id) => { const w = window.__dbg.waitLook(id); return w && w.kind === 'stall'; }", arg=lc, label="C's zz bubble")
        look = res["looks"] = await page.evaluate("(ids) => ids.map((id) => window.__dbg.waitLook(id))", [la, lb, lc])
        check(failures, look[0]["kind"] == "stall" and look[1]["kind"] == "perm" and look[2]["kind"] == "stall", f"A and C stalled, B's permission bubble: {look}")
        stalls = res["log"] = await page.evaluate("() => window.__dbg.logOf('SubagentStall')")
        check(failures, sorted(x["who"] for x in stalls) == sorted([la, lb, lc]) and any(x["who"] == lc and x["what"].endswith(T("ev.stall.desktop")) for x in stalls) and any(x["who"] == la and "npm test" not in x["what"] and "Bash" in x["what"] for x in stalls),
              f"one line each in the event log, A's naming its last tool: {stalls}")
        await page.wait_for_timeout(600)
        await page.screenshot(path=str(out / "stall-light.png"))
        await page.emulate_media(color_scheme="dark")
        await page.wait_for_timeout(900)
        await page.screenshot(path=str(out / "stall-dark.png"))
        await page.emulate_media(color_scheme="light")

        # still quiet: no second notice
        more = taken(1, 8)
        check(failures, more == [], f"no second notice while it stays quiet: {[m[:120] for m in more]}")

        # A's transcript grows: the bubble goes; then quiet again: a second notice
        with ta.open("a") as f:
            f.write('{"type":"assistant"}\n')
        await wait(page, "(id) => { const w = window.__dbg.waitLook(id); return w && w.kind !== 'stall'; }", arg=la, timeout=15000, label="A's bubble gone")
        again = taken(1, 20)
        check(failures, len(again) == 1 and A[:8] in again[0], f"quiet again: a second notice: {[a[:120] for a in again]}")

        # A stops: nothing more
        hook(hook_event_name="SubagentStop", agent_id=A, agent_type="Explore", last_assistant_message="done")
        hook(hook_event_name="SubagentStop", agent_id=B, agent_type="general-purpose", last_assistant_message="done")
        hook(hook_event_name="SubagentStop", agent_id=C, agent_type="Plan", last_assistant_message="done")
        after = taken(1, 10)
        check(failures, after == [], f"no notice after they stopped: {[a[:120] for a in after]}")
    finally:
        done.set()
        for p in stand_ins:
            p.kill()
            p.wait()
        if ctx:
            await ctx.close()
        await browser.close()
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        log.close()
    print(f"  subagent-quiet: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "subagent-quiet-results.json").write_text(dump(res) + "\n")
    from run import check_watch
    check_watch(watch, "subagent-quiet", failures)
