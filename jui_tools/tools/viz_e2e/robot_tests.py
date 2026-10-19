"""A robot's own test runs on its card (requester, 10-18: "ロボットのパネルにもテストの経過表示できない？").

The real `jui viz serve` in a throwaway HOME on a free port, the real forward.py for the hooks, and the runner's
progress records written into that HOME's test-progress folder. Two robots run one test command each: robot A's run
ends with ten cases, eight failed; robot B's is still running. A's card shows A's run only, its failed cases by name
up to FAILED_SHOWN and the rest as a count; B's card shows B's run only. The card's section sits on the 今の様子 tab.

The environment the server and the hooks get has no JSONUI_TEST_PROGRESS_DIR (nor JUI_VIZ_HOME / XDG_STATE_HOME): a
runner started from here would otherwise write into the real server's folder (driver web's jest wrote 480 files
there, 10-18). run.py checks that folder's count after this suite.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request
import uuid

from common import ISOLATE, DESKTOP, LAUNCH_ARGS, Watch, dump, new_page, ready, stamp

SID_A = "aaaa0000-0000-4000-8000-0000000000c1"
SID_B = "bbbb0000-0000-4000-8000-0000000000c2"
CWD = "/work/runs-app"
FAILED_SHOWN = 5
A_CASES = [(f"a-case-{n}", "failed" if n < 8 else "passed") for n in range(10)]


def check(failures, cond, text):
    if not cond:
        failures.append(f"robot-tests: {text}")


async def wait(page, js, timeout=20000, label=""):
    try:
        await page.wait_for_function(js, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


CARD = """() => {
  const sec = document.querySelector('#rb [data-rb-tests]');
  const runs = sec ? [...sec.querySelectorAll('[data-rb-run]')] : [];
  return { inNowTab: !!(sec && sec.closest('.rb-body:not([data-rb-hist])')),
           runs: runs.map((r) => r.dataset.rbRun), head: runs.map((r) => r.querySelector('.rb-run-head').textContent),
           fails: [...(sec ? sec.querySelectorAll('.rb-fails li:not(.rb-fail-more)') : [])].map((n) => n.textContent),
           more: ((sec && sec.querySelector('.rb-fail-more')) || {}).textContent || '', text: sec ? sec.textContent : '' };
}"""


def rec(run, event, **fields):
    return {"v": 1, "t": int(time.time() * 1000), "platform": "web", "run": run, "event": event, **fields}


async def run_robot_tests(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "robot-tests"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    progress = home / ".local" / "state" / "jui-viz" / "test-progress"
    progress.mkdir(parents=True, exist_ok=True)
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")

    def serve():
        return subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)

    def stop(p):
        p.terminate()
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()

    srv = serve()
    url = f"http://127.0.0.1:{port}"
    results = home / ".local" / "state" / "jsonui-test" / "results" / "web" / "runs-app"   # the drivers' default folder

    def saved(run, cases):
        """A driver's results file for run (B's shape: run, app, suites[].file), named by now."""
        results.mkdir(parents=True, exist_ok=True)
        name_at = time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + ".000"
        doc = {"format": "jsonui-test-results", "version": 1, "platform": "web", "generatedAt": stamp("2026-10-18T09:00:00Z"),
               "run": run, "app": "runs-app", "suites": [{"suiteName": "a", "file": "tests/a.test.json", "results": [
                   {"testName": "a", "caseName": c, "status": st, "durationMs": 1} for c, st in cases]}]}
        (results / f"{name_at}Z-{run}.json").write_text(json.dumps(doc))
    res: dict = {}

    def hook(payload):
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(payload).encode(),
                       capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)

    def base(sid):
        return {"session_id": sid, "cwd": CWD, "transcript_path": f"/nowhere/{sid}.jsonl", "permission_mode": "default"}

    def write(run, records):
        with open(progress / f"{run}.jsonl", "a") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    t0 = time.monotonic()
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        watch = Watch(origin=url)
        page = await new_page(browser, watch, "robot-tests", **DESKTOP)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", label="connected")
        for sid in (SID_A, SID_B):
            hook(dict(base(sid), hook_event_name="SessionStart", source="startup"))
        await wait(page, "() => document.querySelectorAll('#sessions [data-robot-open]').length >= 2", label="two robots")

        # A: a run that ends, eight of ten cases failed
        run_a = str(uuid.uuid4())
        hook(dict(base(SID_A), hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="run-a",
                  tool_input={"command": "npx playwright test tests/a.test.json"}))
        await page.wait_for_timeout(600)
        write(run_a, [rec(run_a, "run_start", files=1)])
        for name, status in A_CASES:
            write(run_a, [rec(run_a, "case_start", file="tests/a.test.json", test="a", case=name, attempt=1),
                          rec(run_a, "case_end", file="tests/a.test.json", test="a", case=name, attempt=1, status=status, durationMs=5)])
        write(run_a, [rec(run_a, "run_end", passed=2, failed=8, skipped=0)])
        await page.wait_for_timeout(2500)
        hook(dict(base(SID_A), hook_event_name="PostToolUse", tool_name="Bash", tool_use_id="run-a",
                  tool_input={"command": "npx playwright test tests/a.test.json"}, tool_response={"stdout": "2 passed, 8 failed", "stderr": ""}))
        # B: a run still going
        run_b = str(uuid.uuid4())
        hook(dict(base(SID_B), hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="run-b",
                  tool_input={"command": "npx playwright test tests/b.test.json"}))
        await page.wait_for_timeout(600)
        write(run_b, [rec(run_b, "run_start", files=1),
                      rec(run_b, "case_start", file="tests/b.test.json", test="b", case="b-running-case", attempt=1)])
        await page.wait_for_timeout(2500)

        cards = {}
        for key, prefix in (("A", "aaaa"), ("B", "bbbb")):
            await page.evaluate("(p) => [...document.querySelectorAll('#sessions [data-robot-open]')].find((b) => b.textContent.includes(p)).click()", prefix)
            await wait(page, "() => !!document.querySelector('#rb [data-rb-tests] [data-rb-run]')", label=f"robot {key}'s runs")
            await page.wait_for_timeout(400)
            cards[key] = await page.evaluate(CARD)
            await page.screenshot(path=str(out / f"robot-{key}.png"))
        res["cards"] = cards
        a, b = cards["A"], cards["B"]
        check(failures, a["inNowTab"] and b["inNowTab"], "the section is on the 今の様子 tab")
        check(failures, a["runs"] == ["run-a"] and b["runs"] == ["run-b"], f"each card shows its own run only: A {a['runs']} B {b['runs']}")
        check(failures, a["fails"] == [n for n, s in A_CASES if s == "failed"][:FAILED_SHOWN] and a["more"] == f"ほか {8 - FAILED_SHOWN} 件",
              f"A's failed cases by name, at most {FAILED_SHOWN}: {a['fails']} {a['more']!r}")
        check(failures, "b-running-case" not in a["text"] and "a-case-" not in b["text"], "no case of the other robot's run")
        check(failures, b["fails"] == [] and "実行中" in b["head"][0], f"B is running, nothing failed: {b['head']} {b['fails']}")
        check(failures, "失敗" in a["head"][0], f"A failed: {a['head']}")

        # The server restarts. A's first run is saved now, from before this server started: it is no robot's run here.
        # A runs again; the live progress has two cases, the saved file three — the card shows the saved outcome.
        saved(run_a, A_CASES)
        await page.close()
        stop(srv)
        srv = serve()
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        page = await new_page(browser, watch, "robot-tests-restart", **DESKTOP)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", label="connected again")
        hook(dict(base(SID_A), hook_event_name="SessionStart", source="resume"))
        await wait(page, "() => !!document.querySelector('#sessions [data-robot-open]')", label="robot A again")
        run_c = str(uuid.uuid4())
        hook(dict(base(SID_A), hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="run-c",
                  tool_input={"command": "npx playwright test tests/a.test.json"}))
        await page.wait_for_timeout(600)
        write(run_c, [rec(run_c, "run_start", files=1)])
        for name in ("c-1", "c-2"):
            write(run_c, [rec(run_c, "case_start", file="tests/a.test.json", test="a", case=name, attempt=1),
                          rec(run_c, "case_end", file="tests/a.test.json", test="a", case=name, attempt=1, status="passed", durationMs=5)])
        await page.wait_for_timeout(1500)
        saved(run_c, [("c-1", "passed"), ("c-2", "failed"), ("c-3", "failed")])
        await page.evaluate("(p) => [...document.querySelectorAll('#sessions [data-robot-open]')].find((b) => b.textContent.includes(p)).click()", "aaaa")
        await wait(page, "() => (document.querySelector('#rb [data-rb-tests]') || {}).textContent && document.querySelector('#rb [data-rb-tests]').textContent.includes('保存された結果')",
                   timeout=15000, label="the saved result on A's card")
        res["restart"] = r = await page.evaluate(CARD)
        await page.screenshot(path=str(out / "robot-A-restart.png"))
        check(failures, r["runs"] == ["run-c"], f"after the restart, A's card has the run this server saw only: {r['runs']}")
        check(failures, r["fails"] == ["c-2", "c-3"] and "a-case-" not in r["text"],
              f"the saved outcome per case, and nothing of the run from before the start: {r['fails']}")
        await page.close()
        for line in watch.console:
            failures.append(f"robot-tests: console: {line}")
        for u in watch.foreign:
            failures.append(f"robot-tests: request outside the server: {u}")
    except Exception as e:
        failures.append(f"robot-tests: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        stop(srv)
        await browser.close()
    print(f"  robot-tests/card: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "robot-tests-results.json").write_text(dump(res) + "\n")
