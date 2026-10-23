"""A wait's project chosen on the way to the board (ticket 2026-10-24-viz-wait-to-board-keeps-the-wrong-project). Runs
with `--only wait-project`.

The requester: 「質問系でボードに移動する時はその質問をしてるプロジェクト選択状態にして、他のプロジェクト開いてる時だと遷移した
のに質問がない変な状態になる。」 and 「複数プロジェクト待ちの時は全てのプロジェクト選択状態にして」.

The real `jui viz serve` in a throwaway HOME and the real forward.py: three sessions in three projects — a1 (A, nothing
waits), b1 (B, a question), c1 (C, a permission, then a stopped call). From A every way from a wait to the board or the
panel is taken, as a person takes it, and the project it lands on is checked with what is on screen:
  * the header's 質問 chip (B's only): B chosen, b1's question on the board;
  * the 許可待ち chip (C's only): C chosen, c1's permission on the board's strip;
  * the 止められた操作 chip (C's only): C chosen, c1's stopped call on the board;
  * the sum of the block beside a1's open card (b1 and c1 wait: two projects): すべて chosen, both on the board;
  * a question's notification clicked (notifyOpen; an OS notification cannot be pressed from a page): B, the question;
  * b1's bubble over its robot, from すべて: B chosen, its question card in the panel.
With `video`, the 質問 chip and the block's sum recorded.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, ISOLATE, LAUNCH_ARGS, Watch, new_page, ready
from waits import WaitTimeout, settled, until

SIDS = {"a1": "e2e00000-0000-4000-8000-0000000009a1", "b1": "e2e00000-0000-4000-8000-0000000009b1",
        "c1": "e2e00000-0000-4000-8000-0000000009c1"}
CWDS = {"a1": "/work/wp-alpha", "b1": "/work/wp-bravo", "c1": "/work/wp-charlie"}
QUESTION = {"questions": [{"question": "Which flavour?", "header": "Flavour", "multiSelect": False,
                           "options": [{"label": "Peat", "description": "p"}, {"label": "Sherry", "description": "s"}]}]}
BOARD = """() => { const b = window.__dbg.board(), q = document.getElementById('q-strip'), p = document.getElementById('perm-strip'),
  d = document.getElementById('denied-strip');
  return { open: b.open, project: window.__dbg.project(),
    q: q && !q.hidden ? q.textContent.includes('Which flavour?') : false,
    perm: p && !p.hidden ? p.textContent.includes('npm run deploy') : false,
    denied: d && !d.hidden ? d.textContent.includes('rm -rf dist') : false }; }"""
PANEL_Q = "() => !!document.querySelector('#questions .qcard') && document.getElementById('questions').textContent.includes('Which flavour?')"


def check(failures, cond, text):
    if not cond:
        failures.append(f"wait-project: {text}")


async def run_wait_project(pw, out, failures, video: pathlib.Path | None = None):
    from run import free_port
    out = pathlib.Path(out) / "wait-project"
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
    res: dict = {}

    def hook(k, **payload):
        subprocess.run([sys.executable, "-I", "-S", str(forward)], timeout=10, capture_output=True, env=dict(base_env, HOME=str(home)),
                       input=json.dumps({"session_id": SIDS[k], "cwd": CWDS[k], "transcript_path": f"{home}/t-{k}.jsonl",
                                         "permission_mode": "default", **payload}).encode())

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
        if video:
            ctx = await browser.new_context(**dict(DESKTOP, record_video_dir=str(video), record_video_size=DESKTOP["viewport"]))
            page = await ctx.new_page()
            watch.attach(page, "wait-project")
        else:
            page = await new_page(browser, watch, "wait-project", **DESKTOP)
        pause = (lambda ms: page.wait_for_timeout(ms)) if video else (lambda ms: page.wait_for_timeout(0))
        await page.goto(url + "/")
        await ready(page)
        await until(page, "() => document.querySelector('.chip.demo').dataset.net === 'connected'", "connected")
        for k in SIDS:
            hook(k, hook_event_name="SessionStart", source="startup")
        await until(page, "() => document.querySelectorAll('#sessions [data-robot-open]').length >= 3", "three sessions", timeout=40000)
        who = res["who"] = await page.evaluate("(sids) => Object.fromEntries(Object.entries(sids).map(([k, sid]) => [k, window.__dbg.labelOfSession(sid)]))", SIDS)
        proj = res["proj"] = await page.evaluate("(ls) => Object.fromEntries(Object.entries(ls).map(([k, l]) => [k, window.__dbg.robotProject(l)]))", who)
        A, B, C = proj["a1"], proj["b1"], proj["c1"]
        check(failures, len({A, B, C}) == 3 and all((A, B, C)), f"three sessions in three projects: {proj}")

        async def press(sel, **kw):   # a click, the element named when it is not there to press
            try:
                await page.wait_for_selector(sel, state="visible", timeout=10000)
            except Exception as e:
                raise RuntimeError(f"{sel} not visible to press: {str(e).splitlines()[0]}") from None
            await page.click(sel, **kw)

        async def pick(pid):   # as a person: the header's project picker
            await press("[data-scope-btn]")
            await press(f"#pop [data-pick-project='{pid}']")
            await until(page, "(p) => window.__dbg.project() === p", f"project {pid}", arg=pid)
            await settled(page, f"project {pid} settled")

        async def board_closed():
            if (await page.evaluate("() => window.__dbg.board().open")):
                await page.evaluate("() => window.__dbg.closeTaskBoard()")
                await until(page, "() => !window.__dbg.board().open", "the board closed")
                await settled(page, "the board's zoom back done")

        async def landed(label, want_project, **want):
            js = f"(w) => {{ const b = ({BOARD})(); return b.open && b.project === w.p && Object.entries(w.s).every(([k, v]) => b[k] === v) ? b : null; }}"
            try:
                got = await until(page, js, label, arg={"p": want_project, "s": want}, timeout=15000, why=BOARD)
            except WaitTimeout as e:
                failures.append(f"wait-project: {e}")
                got = await page.evaluate(BOARD)
            res[label] = got
            return got

        # b1 asks; from A, the 質問 chip
        hook("b1", hook_event_name="UserPromptSubmit", prompt="ask")
        hook("b1", hook_event_name="PreToolUse", tool_name="AskUserQuestion", tool_use_id="toolu_wpq", tool_input=QUESTION)
        await until(page, "() => !document.getElementById('chip-ask').hidden", "the 質問 chip", timeout=20000)
        await pick(A)
        await pause(1500)
        await press("#chip-ask")
        got = await landed("the 質問 chip: B and its question", B, q=True)
        check(failures, got.get("project") == B and got.get("q"), f"the 質問 chip from A: B chosen, b1's question on the board: {got}")
        await page.screenshot(path=str(out / "wait-project-ask-chip.png"))
        await pause(2500)
        await board_closed()

        # c1 waits on a permission; from A, the 許可待ち chip
        hook("c1", hook_event_name="UserPromptSubmit", prompt="deploy")
        hook("c1", hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="toolu_wpp", tool_input={"command": "npm run deploy"})
        hook("c1", hook_event_name="PermissionRequest", tool_name="Bash", tool_input={"command": "npm run deploy"})
        await until(page, "() => !document.getElementById('chip-perm').hidden", "the 許可待ち chip", timeout=20000)
        await pick(A)
        await press("#chip-perm")
        got = await landed("the 許可待ち chip: C and its permission", C, perm=True)
        check(failures, got.get("project") == C and got.get("perm"), f"the 許可待ち chip from A: C chosen, c1's permission on the board: {got}")
        await board_closed()

        # the block beside a1's card: b1 and c1 wait, two projects: すべて
        await pick(A)
        await press(f"#sessions [data-robot-open='{who['a1']}']")
        await until(page, "(l) => window.__dbg.board().robot === l && !document.getElementById('rb').hidden && !document.getElementById('rb-waits').hidden",
                    "a1's card and the block beside it", arg=who["a1"], timeout=20000)
        await pause(2000)
        await press("#rb-waits [data-rbw-board]")
        got = await landed("the block's sum: すべて and both", "all", q=True, perm=True)
        check(failures, got.get("project") == "all" and got.get("q") and got.get("perm"), f"the block's sum (two projects): すべて chosen, both waits on the board: {got}")
        await page.screenshot(path=str(out / "wait-project-block-sum.png"))
        await pause(2500)
        await board_closed()

        # a question's notification, clicked
        await pick(A)
        qid = await page.evaluate("(l) => { const q = window.__dbg.questions().find((x) => x.who === l && x.status === 'pending'); return q ? q.id : null; }", who["b1"])
        await page.evaluate("([id, w]) => window.__dbg.notifyOpen('ask', { id, who: w })", [qid, who["b1"]])
        got = await landed("a question's notification: B and its question", B, q=True)
        check(failures, got.get("project") == B and got.get("q"), f"a question's notification from A: B chosen, its question on the board: {got}")
        await board_closed()

        # c1's call stopped by auto mode; from A, the 止められた操作 chip
        hook("c1", hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="toolu_wpd", tool_input={"command": "rm -rf dist"}, permission_mode="auto")
        hook("c1", hook_event_name="PermissionDenied", tool_name="Bash", tool_use_id="toolu_wpd", tool_input={"command": "rm -rf dist"},
             permission_mode="auto", reason="auto mode classifier")
        await until(page, "() => !document.getElementById('chip-denied').hidden", "the 止められた操作 chip", timeout=20000)
        await pick(A)
        await press("#chip-denied")
        got = await landed("the 止められた操作 chip: C and its stopped call", C, denied=True)
        check(failures, got.get("project") == C and got.get("denied"), f"the 止められた操作 chip from A: C chosen, the stopped call on the board: {got}")
        await board_closed()

        # b1's bubble, from すべて: B, its question card in the panel
        await pick("all")
        await until(page, "(l) => { const b = document.querySelector(`.wait-bubble[data-wait-robot=\"${l}\"]`); return b && !b.hidden; }", "b1's bubble", arg=who["b1"], timeout=20000)
        await press(f".wait-bubble[data-wait-robot='{who['b1']}']", force=True)
        try:
            await until(page, f"(p) => window.__dbg.project() === p && ({PANEL_Q})()", "b1's bubble: B and its question in the panel", arg=B, timeout=15000)
        except WaitTimeout as e:
            failures.append(f"wait-project: {e}")
        res["bubble"] = got = await page.evaluate(f"() => ({{ project: window.__dbg.project(), panel: ({PANEL_Q})(), picked: window.__dbg.waitPicked() }})")
        check(failures, got["project"] == B and got["panel"] and (got["picked"] or {}).get("found"), f"b1's bubble from すべて: B chosen, its question card found in the panel: {got}")
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    finally:
        if video and ctx is not None:
            await ctx.close()   # the video is written whole only when its context closes
        await browser.close()
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        log.close()
        print(f"  wait-project: {time.monotonic() - t0:.0f}s", flush=True)
    for line in watch.console:
        failures.append(f"wait-project: console: {line}")
