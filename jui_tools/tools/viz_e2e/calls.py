"""Phone calls, end to end (requester, 10-18): a SendMessage between two sessions rings and is picked up.

The real `jui viz serve` in a throwaway HOME on a free port: its ~/.claude/sessions holds two session files with
their messaging names, its ~/.claude/projects their transcripts; the real forward.py sends the hooks. Session A
sends to B by name: A holds a handset and B's phone rings over its head, both name tags say so with the other's
number. B's transcript gets the enqueue (still ringing), then the isMeta record (it read it): B picks up, both on
the line, then both back to work. The message's text is nowhere on the page's tags. No console error, nothing
requested outside the server.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, dump, new_page, ready

A = "e2e00000-0000-4000-8000-0000000000ca"
B = "e2e00000-0000-4000-8000-0000000000cb"
CWD = "/work/call-app"
NAMES = {A: "call-app-a1", B: "call-app-b2"}
BODY = "CALL-BODY-5d1e"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")


def check(failures, cond, text):
    if not cond:
        failures.append(f"calls: {text}")


async def wait(page, js, timeout=20000, label=""):
    try:
        await page.wait_for_function(js, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


def _xmsg():
    return (f'<cross-session-message from="uds:/tmp/e2e/{A[-2:]}.sock" from-name="{NAMES[A]}" from-mode="prompting">\n'
            f"{BODY}\n</cross-session-message>")


async def run_calls(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "calls"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    proj = home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", CWD)
    proj.mkdir(parents=True, exist_ok=True)
    sessions = home / ".claude" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    transcripts = {}
    for n, sid in enumerate((A, B)):
        transcripts[sid] = proj / f"{sid}.jsonl"
        transcripts[sid].write_text(json.dumps({"type": "user", "timestamp": "2026-10-18T09:00:00Z", "message": {"role": "user", "content": "start"}}) + "\n")
        (sessions / f"{90000 + n}.json").write_text(json.dumps({
            "pid": 90000 + n, "sessionId": sid, "cwd": CWD, "name": NAMES[sid], "nameSource": "derived", "status": "idle",
            "messagingSocketPath": f"/tmp/e2e/{sid[-2:]}.sock", "entrypoint": "cli"}))
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def hook(sid, **payload):
        body = {"session_id": sid, "cwd": CWD, "transcript_path": str(transcripts[sid]), "permission_mode": "default", **payload}
        p = subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(),
                           capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)
        return p.returncode

    def append(sid, rec):
        with open(transcripts[sid], "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    calls_js = "() => Object.fromEntries(window.__dbg.calls().map((c) => [c.id, c]))"
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
        page = await new_page(browser, watch, "calls", **DESKTOP)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", label="connected")
        for sid in (A, B):
            hook(sid, hook_event_name="SessionStart", source="startup")
        await wait(page, "() => window.__dbg.calls().length >= 2", label="two robots")
        labels = await page.evaluate("() => window.__dbg.calls().map((c) => c.id)")
        await page.wait_for_timeout(2500)          # the transcripts' first read (from their end) happens on a 2 s tick
        # A dials B by name (with a [ref], as a listing may show it)
        hook(A, hook_event_name="PreToolUse", tool_name="SendMessage", tool_use_id="toolu_call1",
             tool_input={"to": f"{NAMES[B]} [abc123]", "summary": "x", "message": BODY})
        await wait(page, "() => window.__dbg.calls().some((c) => c.ring)", timeout=10000, label="B's phone rings")
        r = res["ringing"] = await page.evaluate(calls_js)
        caller = next((c for c in r.values() if c["call"] and c["call"]["role"] == "caller"), None)
        callee = next((c for c in r.values() if c["call"] and c["call"]["role"] == "callee"), None)
        check(failures, caller and caller["handset"] and not caller["ring"], f"the caller holds a handset: {caller}")
        check(failures, callee and callee["ring"] and not callee["handset"], f"the callee's phone rings: {callee}")
        check(failures, caller and callee and caller["tag"] == f"☎ 呼び出し中 {callee['id']}" and callee["tag"] == f"☎ 着信 {caller['id']}",
              f"the name tags: {caller and caller['tag']!r} / {callee and callee['tag']!r}")
        await page.screenshot(path=str(out / "ringing.png"))
        hook(A, hook_event_name="PostToolUse", tool_name="SendMessage", tool_use_id="toolu_call1",
             tool_input={"to": f"{NAMES[B]} [abc123]", "message": BODY}, tool_response={"success": True})
        # it arrives: still ringing
        append(B, {"type": "queue-operation", "operation": "enqueue", "timestamp": "2026-10-18T09:00:05Z", "sessionId": B, "content": _xmsg()})
        await page.wait_for_timeout(3500)
        r = res["arrived"] = await page.evaluate(calls_js)
        check(failures, any(c["ring"] for c in r.values()), f"arrived, not read: it still rings: {r}")
        # it is read (the receiver was idle): picked up, both on the line
        append(B, {"type": "user", "isMeta": True, "timestamp": "2026-10-18T09:00:05Z",
                   "message": {"role": "user", "content": "Another Claude session sent a message:\n" + _xmsg()}})
        t1 = time.monotonic()
        await wait(page, "() => window.__dbg.calls().filter((c) => c.handset).length === 2", timeout=10000, label="both on the line")
        res["pickUpSec"] = round(time.monotonic() - t1, 1)
        r = res["answered"] = await page.evaluate(calls_js)
        check(failures, not any(c["ring"] for c in r.values()) and all(c["tag"].startswith("☎ 通話中") for c in r.values()),
              f"picked up: no ring, both 通話中: {r}")
        await page.screenshot(path=str(out / "answered.png"))
        tags = await page.evaluate("() => document.getElementById('tags').textContent")
        check(failures, BODY not in tags, "the message's text is not on a name tag")
        # then both back to work
        await wait(page, "() => window.__dbg.calls().every((c) => !c.handset && !c.ring && !c.tag)", timeout=12000, label="back to work")
        res["after"] = await page.evaluate(calls_js)
        lamps = await page.evaluate("() => window.__dbg.calls().map((c) => c.state)")
        check(failures, "waiting" not in lamps, f"a call never changes a robot's state: {lamps}")
        await page.close()
        for line in watch.console:
            failures.append(f"calls: console: {line}")
        for u in watch.foreign:
            failures.append(f"calls: request outside the server: {u}")
        res["labels"] = labels
        res["console"] = len(watch.console)
    except Exception as e:
        failures.append(f"calls: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  calls/ring-pick-up: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "calls-results.json").write_text(dump(res) + "\n")
