"""A project switched while a robot is picked moves to the robot last picked there (ticket
2026-10-20-jui-viz-project-switch-keeps-last-robot-per-project). Runs with `--only project-switch`.

The requester: 「ロボット選択状態でプロジェクト切り替えた先のロボットに切り替えて欲しい。各プロジェクトで最後に選択してた
ロボット覚えといて、それがいたらそれを選択、いなかったら未選択で部屋表示」.

The real `jui viz serve` in a throwaway HOME on a free port and the real forward.py: three sessions in two projects
(A: a1; B: b1, b2). Robots are opened from the panel's session list and projects switched from the header's
project picker, as a person does. Checked, in order:
  * A with a1 picked → B (nothing picked there before): nothing picked, B shown
  * b2 picked → A: a1 → B: b2
  * b2 closed with Escape → A, a1 picked → B: nothing picked (Escape is closing by hand too)
  * a1 closed by hand (← 3D に戻る) → B with nothing picked: nothing opens (only a picked robot carries over)
  * b2 picked → A: nothing picked (closed by hand is remembered)
  * a1 picked again → B (b2) → a1's session ends and its robot walks out → A: nothing picked
  * with a robot picked → すべて: nothing picked
No console error; nothing outside the server.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, ISOLATE, LAUNCH_ARGS, Watch, dump, new_page, ready

SIDS = {"a1": "e2e00000-0000-4000-8000-0000000000a1", "b1": "e2e00000-0000-4000-8000-0000000000b1",
        "b2": "e2e00000-0000-4000-8000-0000000000b2"}
CWDS = {"a1": "/work/switch-a", "b1": "/work/switch-b", "b2": "/work/switch-b"}
STATE = "() => ({ robot: window.__dbg.board().robot, project: window.__dbg.project(), card: !document.getElementById('rb').hidden })"


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def run_project_switch(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "project-switch"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log,
                           stderr=subprocess.STDOUT, env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"
    res: dict = {"steps": []}

    def check(cond, text):
        if not cond:
            failures.append(f"project-switch: {text}")

    def hook(k, **payload):
        subprocess.run([sys.executable, "-I", "-S", str(forward)], timeout=10, capture_output=True, env=dict(base_env, HOME=str(home)),
                       input=json.dumps({"session_id": SIDS[k], "cwd": CWDS[k], "transcript_path": "/work/none.jsonl",
                                         "permission_mode": "default", **payload}).encode())

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
        for k in SIDS:
            hook(k, hook_event_name="SessionStart", source="startup")
        watch = Watch(origin=url)
        page = await new_page(browser, watch, "project-switch", **DESKTOP)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelectorAll('#sessions [data-robot-open]').length >= 3", label="three sessions")
        # the labels and the projects, as the page has them
        who = await page.evaluate("(sids) => Object.fromEntries(Object.entries(sids).map(([k, sid]) => [k, window.__dbg.labelOfSession(sid)]))", SIDS)
        proj = await page.evaluate("(ls) => Object.fromEntries(Object.entries(ls).map(([k, l]) => [k, window.__dbg.robotProject(l)]))", who)
        res["who"], res["proj"] = who, proj
        A, B = proj["a1"], proj["b1"]
        check(A and B and A != B and proj["b2"] == B, f"two projects: a1 in one, b1 and b2 in the other: {proj}")

        async def pick_project(pid):
            await page.click("[data-scope-btn]")
            await page.click(f"#pop [data-pick-project='{pid}']")
            await wait(page, "(p) => window.__dbg.project() === p", arg=pid, label=f"project {pid}")
            await page.wait_for_timeout(700)   # the switch's own camera and card work settle

        async def open_robot(k):
            await page.click(f"#sessions [data-robot-open='{who[k]}']")
            await wait(page, "(l) => window.__dbg.board().robot === l && !document.getElementById('rb').hidden", arg=who[k], label=f"{k}'s card")

        async def state(step, want_robot, want_project):
            got = await page.evaluate(STATE)
            res["steps"].append({"step": step, **got})
            want = {"robot": who[want_robot] if want_robot else None, "project": want_project, "card": bool(want_robot)}
            check(got == want, f"{step}: {want} expected, got {got}")

        await pick_project(A)
        await open_robot("a1")
        await pick_project(B)
        await state("A with a1 picked → B (nothing picked there yet): nothing picked", None, B)
        await open_robot("b2")
        await pick_project(A)
        await state("b2 picked → A: a1", "a1", A)
        await page.screenshot(path=str(out / "back-to-a1.png"))
        await pick_project(B)
        await state("→ B: b2", "b2", B)
        await page.keyboard.press("Escape")     # b2 closed by hand, with the keyboard
        await wait(page, "() => !window.__dbg.board().robot", label="b2 closed with Escape")
        await pick_project(A)
        await open_robot("a1")
        await pick_project(B)
        await state("a1 picked → B, where b2 was closed with Escape: nothing picked", None, B)
        await pick_project(A)
        await open_robot("a1")
        await page.click("#rb [data-rb-close]")   # closed by hand
        await wait(page, "() => !window.__dbg.board().robot", label="a1 closed by hand")
        await pick_project(B)
        await state("nothing picked → B: nothing opens", None, B)
        await open_robot("b2")
        await pick_project(A)
        await state("b2 picked → A, where a1 was closed by hand: nothing picked", None, A)
        await open_robot("a1")
        await pick_project(B)
        await state("a1 picked → B: b2", "b2", B)
        hook("a1", hook_event_name="SessionEnd", reason="other")
        await wait(page, "(l) => !Object.keys(window.__dbg.robotState()).includes(l) || !document.querySelector(`#sessions [data-robot-open='${l}']`)",
                   arg=who["a1"], timeout=40000, label="a1 gone")
        await page.wait_for_timeout(1500)
        await pick_project(A)
        await state("a1's session ended → A: nothing picked", None, A)
        await page.screenshot(path=str(out / "a-unpicked.png"))
        await pick_project(B)
        await open_robot("b1")
        await pick_project("all")
        await state("with b1 picked → すべて: nothing picked", None, "all")
        await page.close()
        for line in watch.console:
            failures.append(f"project-switch: console: {line}")
        for u in watch.foreign:
            failures.append(f"project-switch: request outside the server: {u}")
    except Exception as e:
        failures.append(f"project-switch: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  project-switch: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "project-switch-results.json").write_text(dump(res) + "\n")
