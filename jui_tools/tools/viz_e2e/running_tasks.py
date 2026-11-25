"""What each session runs in the background, under its row (ticket 2026-11-25-viz-show-running-tasks-of-local-sessions;
requester: 「claudeのスマホアプリで見れる実行中のタスクってvizに表示する機能つけれる？」). Runs with `--only running-tasks`.

The real `jui viz serve` in a throwaway HOME: one session file (a stand-in process) and its transcript under
~/.claude/projects, written by the test in the shapes measured on a live machine (viz/running.py). Checked:
  * what was open before the server started (the transcript's past) shows: a background command, a background
    subagent, a monitor — each with its kind, its description (never the command line) and its time;
  * one more started after (the tail): it shows; a notice ends the command: it shows as ended, faded;
  * the subagent "waiting on its own background work" stays, with that note;
  * Stop without background_tasks closes nothing; with a list it closes the subagent it does not name, never the monitor;
  * stills: light and dark.
No console error; nothing outside the server."""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import DESKTOP, ISOLATE, LAUNCH_ARGS, T, Watch, dump, ready  # noqa: E402

MAIN = "7a5c0000-0000-4000-8000-0000000000b2"
CWD = "/work/run-app"


def check(failures, cond, text):
    if not cond:
        failures.append(f"running-tasks: {text}")


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


def iso(ms: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def recs_bash(tid, at, desc, command="make check SECRET=do-not-show"):
    use = f"u-{tid}"
    return [{"type": "assistant", "timestamp": iso(at), "message": {"content": [{"type": "tool_use", "id": use, "name": "Bash",
             "input": {"command": command, "description": desc, "run_in_background": True}}]}},
            {"type": "user", "timestamp": iso(at), "toolUseResult": {"stdout": "", "stderr": "", "interrupted": False, "backgroundTaskId": tid},
             "message": {"content": [{"type": "tool_result", "tool_use_id": use, "content": "started"}]}}]


def recs_agent(aid, at, desc):
    use = f"u-{aid}"
    return [{"type": "assistant", "timestamp": iso(at), "message": {"content": [{"type": "tool_use", "id": use, "name": "Agent",
             "input": {"description": desc, "prompt": "...", "run_in_background": True}}]}},
            {"type": "user", "timestamp": iso(at), "toolUseResult": {"isAsync": True, "status": "async_launched", "agentId": aid, "description": desc},
             "message": {"content": [{"type": "tool_result", "tool_use_id": use, "content": "launched"}]}}]


def recs_monitor(tid, at, desc):
    use = f"u-{tid}"
    return [{"type": "assistant", "timestamp": iso(at), "message": {"content": [{"type": "tool_use", "id": use, "name": "Monitor",
             "input": {"description": desc, "command": "tail -f build.log"}}]}},
            {"type": "user", "timestamp": iso(at), "toolUseResult": {"taskId": tid, "timeoutMs": 1_800_000, "persistent": False},
             "message": {"content": [{"type": "tool_result", "tool_use_id": use, "content": "armed"}]}}]


def rec_notice(tid, at, status="completed", summary="done"):
    text = f"<task-notification>\n<task-id>{tid}</task-id>\n<status>{status}</status>\n<summary>{summary}</summary>\n</task-notification>"
    return {"type": "queue-operation", "operation": "enqueue", "timestamp": iso(at), "content": text}


def append(path: pathlib.Path, recs) -> None:
    with path.open("a", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")


ROWS = """(sid) => { const box = document.querySelector('[data-runs]'); if (!box) return null;
  return [...box.querySelectorAll('.run')].map((li) => ({ kind: li.querySelector('.run-kind').textContent,
    desc: li.querySelector('.run-desc').textContent, time: li.querySelector('.run-time').textContent,
    done: li.classList.contains('run-done'), note: [...li.querySelectorAll('.run-note')].map((n) => n.textContent).join('|') })); }"""


async def run_running_tasks(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "running-tasks"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    sessions_dir = home / ".claude" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    tdir = home / ".claude" / "projects" / "-work-run-app"
    tdir.mkdir(parents=True, exist_ok=True)
    transcript = tdir / f"{MAIN}.jsonl"
    now = int(time.time() * 1000)
    # the past: three open, one over
    append(transcript, [*recs_bash("bpast001", now - 25 * 60_000, "Run the full test suites"),
                        *recs_bash("bpast002", now - 40 * 60_000, "Build the docs"), rec_notice("bpast002", now - 30 * 60_000),
                        *recs_agent("apast0003", now - 11 * 60_000, "Write the login screen tests"),
                        *recs_monitor("mpast004", now - 5 * 60_000, "Watch the build log")])
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    log = open(out / "serve.log", "w")
    stand_ins: list = []
    res: dict = {}
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(900)"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    stand_ins.append(proc)
    (sessions_dir / f"{proc.pid}.json").write_text(json.dumps({"pid": proc.pid, "sessionId": MAIN, "cwd": CWD, "kind": "interactive",
                                                              "entrypoint": "cli", "status": "shell", "name": "run-lane",
                                                              "procStart": f"t{proc.pid}"}))
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT,
                           env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"

    def hook(**payload):
        body = {"session_id": MAIN, "cwd": CWD, "transcript_path": str(transcript), "permission_mode": "default", **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(), capture_output=True,
                       env=dict(base_env, HOME=str(home)), timeout=10)

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
        ctx = await browser.new_context(**DESKTOP)
        page = await ctx.new_page()
        watch.attach(page, "running-tasks")
        await page.goto(url + "/")
        await ready(page)

        await wait(page, f"(rows) => {{ const r = ({ROWS})(); return r && r.length === 3; }}", label="the three open from the past")
        rows = res["past"] = await page.evaluate(ROWS)
        kinds = [r["kind"] for r in rows]
        check(failures, kinds == [T("run.kind.bash"), T("run.kind.agent"), T("run.kind.monitor")], f"oldest first, each kind's word: {kinds}")
        check(failures, [r["desc"] for r in rows] == ["Run the full test suites", "Write the login screen tests", "Watch the build log"],
              f"the descriptions: {[r['desc'] for r in rows]}")
        check(failures, rows[0]["time"].startswith(T("panel.since.elapsed")) and rows[0]["time"].split()[-1].startswith("25:"),
              f"the command's elapsed time (25 min): {rows[0]['time']}")
        page_text = await page.evaluate("() => document.body.innerText")
        check(failures, "do-not-show" not in page_text and "Build the docs" not in page_text,
              "neither the command line nor what was over before is shown")
        badge = await page.evaluate("() => document.querySelector('#sessions [data-sst]').textContent")
        check(failures, badge == T("status.background"), f"idle with background work: the session's badge says so: {badge}")
        head = await page.evaluate("() => document.querySelector('[data-runs] .runs-head').textContent")
        check(failures, head == T("run.head", n=3), f"the head counts the running: {head}")

        # after the start: a new one; the command's notice; the subagent waits on its own work
        t1 = int(time.time() * 1000)
        append(transcript, [*recs_bash("bnew0005", t1, "Upload the screenshots"), rec_notice("bpast001", t1 + 10),
                            rec_notice("apast0003", t1 + 20, summary='Agent "x" is waiting on its own background work')])
        await wait(page, f"(rows) => {{ const r = ({ROWS})(); return r && r.length === 4 && r.some((x) => x.done); }}", label="the new one and the ended one")
        rows = res["tail"] = await page.evaluate(ROWS)
        check(failures, [(r["desc"], r["done"]) for r in rows] == [("Write the login screen tests", False), ("Watch the build log", False),
                                                                    ("Upload the screenshots", False), ("Run the full test suites", True)],
              f"running first, the ended one last and faded: {[(r['desc'], r['done']) for r in rows]}")
        check(failures, rows[-1]["time"] == T("run.state.done") and rows[0]["note"] == T("run.state.waiting"),
              f"the ended one says so, the waiting subagent too: {rows[-1]['time']} / {rows[0]['note']}")
        await page.wait_for_timeout(600)
        panel = page.locator("#sessions")
        await page.screenshot(path=str(out / "running-light.png"))
        await panel.screenshot(path=str(out / "running-panel-light.png"))
        await page.emulate_media(color_scheme="dark")
        await page.wait_for_timeout(900)
        await page.screenshot(path=str(out / "running-dark.png"))
        await panel.screenshot(path=str(out / "running-panel-dark.png"))
        await page.emulate_media(color_scheme="light")

        # Stop: without the key nothing closes; with a list, the subagent it does not name closes, the monitor stays
        hook(hook_event_name="Stop")
        await page.wait_for_timeout(2500)
        rows = await page.evaluate(ROWS)
        check(failures, sum(1 for r in rows if not r["done"]) == 3, f"Stop without background_tasks closes nothing: {rows}")
        hook(hook_event_name="Stop", background_tasks=[{"id": "bnew0005", "type": "shell", "status": "running", "description": "Upload the screenshots"}])
        await wait(page, f"(rows) => {{ const r = ({ROWS})(); return r && r.filter((x) => !x.done).length === 2; }}", label="Stop's list closes the subagent")
        rows = res["after-stop"] = await page.evaluate(ROWS)
        check(failures, sorted(r["desc"] for r in rows if not r["done"]) == ["Upload the screenshots", "Watch the build log"],
              f"the monitor and the listed command stay: {rows}")
    finally:
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
    print(f"  running-tasks: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "running-tasks-results.json").write_text(dump(res) + "\n")
    from run import check_watch
    check_watch(watch, "running-tasks", failures)
