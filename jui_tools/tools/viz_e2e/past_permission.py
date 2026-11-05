"""A permission that has passed leaves every count (ticket 2026-11-05-viz-past-permission-stays-on-the-card; the requester:
「過ぎ去った許可がずって消えない」). Runs with `--only past-perm`.

The real `jui viz serve` in a throwaway HOME, the hooks replayed through forward.py, the child's transcript written at
subagents/workflows/<run>/agent-<id>.jsonl as the CLI writes it. A workflow's child asks for a Bash and starts a second
call beside it (so its robot no longer says waiting: the state the sessions' filter read). While it really waits: the
header, the card's bar, the waits beside the card and the sessions' filter all say 1, and the end of the other call
closes nothing. Then the safety check's result, with no hook: all 0, the card gone. A second child's card: its
SubagentStop, no result: all 0. Stop with background work leaves a third child's card that waits. Past the stale time
(JUI_VIZ_STALE_MS here, 10 minutes in use) a card and a question stay, counted, say they are old and can be closed by hand:
nothing goes to the receiver, what comes later finds no card, a reload and a restart bring none back, a phone has the buttons. Shown narrowed to one
project, the header's number stays all the projects' and its words say how many lie outside, on a phone too."""
from __future__ import annotations

import http.client
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import DESKTOP, ISOLATE, LAUNCH_ARGS, PHONE, T, Watch, dump, ready  # noqa: E402

SID = "e2e00000-0000-4000-8000-0000000000f9"
KIDS = ("a0411e1b020482601", "a0411e1b020482602", "a0411e1b020482603", "a0411e1b020482604", "a0411e1b020482605")
OTHER = "e2e00000-0000-4000-8000-0000000000fa"
OTHER_CWD = "/work/other-app"
STALE_MS = 25_000
QUESTION = {"questions": [{"question": "どちらにしますか?", "header": "案", "multiSelect": False, "options": [{"label": "A", "description": "a"}, {"label": "B", "description": "b"}]}]}
CWD = "/work/past-app"
SAFETY = ("Permission for this command was denied by a built-in Claude Code safety check, not by the user. Only a person may approve "
          "such a removal, and no person did (the permission prompt timed out, or none was shown).")
COUNTS = """() => {
  const chip = document.getElementById('chip-perm');
  const filter = document.querySelector('#sess-filter [data-sf="waiting"]').lastElementChild.textContent;
  const bar = document.querySelector('#rb [data-h-fold]');
  const waits = document.getElementById('rb-waits');
  return { header: chip.hidden ? '' : chip.textContent, filter, bar: bar ? bar.textContent : '', waits: waits.hidden ? '' : waits.textContent,
           listed: [...document.querySelectorAll('#sessions [data-sst]')].map((n) => n.textContent) };
}"""


STALE = """() => { const chip = document.getElementById('chip-perm'), has = (sel, w) => [...document.querySelectorAll(sel)].some((n) => n.textContent.includes(w));
  return { perm: has('#tasks [data-perm-box]', %s), question: has('#questions', %s), permNote: has('#tasks [data-perm-box]', %s), questionNote: has('#questions', %s),
           permButtons: document.querySelectorAll('#tasks [data-dismiss="perm"]').length, questionButtons: document.querySelectorAll('#questions [data-dismiss="q"]').length,
           header: chip.hidden ? '' : chip.textContent }; }""" % tuple(json.dumps(T(k)) for k in ("panel.perm.stale", "panel.q.stale", "panel.perm.dismiss.note", "panel.q.dismiss.note"))


def check(failures, cond, text):
    if not cond:
        failures.append(f"past-perm: {text}")


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def run_past_permission(pw, out, failures):
    from run import check_watch, free_port
    out = pathlib.Path(out) / "past-perm"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    state = home / ".local" / "state" / "jui-viz"
    state.mkdir(parents=True, exist_ok=True)
    (state / "config.json").write_text(json.dumps({"decideWaitSec": 180}))   # a hook still waits when the card is closed
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT,
                           env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1", JUI_VIZ_STALE_MS=str(STALE_MS)))
    url = f"http://127.0.0.1:{port}"
    main = home / ".claude" / "projects" / "-work-past-app" / f"{SID}.jsonl"
    main.parent.mkdir(parents=True, exist_ok=True)
    main.write_text("")
    run_folder = main.parent / SID / "subagents" / "workflows" / "wf_e2e"
    run_folder.mkdir(parents=True)
    res: dict = {}

    def hook(sid=SID, **payload):
        body = {"session_id": sid, "cwd": CWD, "transcript_path": str(main) if sid == SID else "", "permission_mode": "default", **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(), capture_output=True,
                       env=dict(base_env, HOME=str(home)), timeout=10)

    def snap():
        token = json.loads((state / "server.json").read_text())["token"]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            conn.request("GET", "/api/snapshot", headers={"X-Jui-Viz-Token": token})
            return json.loads(conn.getresponse().read())["slices"]
        finally:
            conn.close()

    def card_statuses():
        return {c["agentId"]: c["status"] for c in snap()["perms"]}

    def result(kid, use_id, text, is_error=True):
        with open(run_folder / f"agent-{kid}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "user", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": use_id, "content": text, "is_error": is_error}]}}) + "\n")

    def asks(kid, use_id):
        (run_folder / f"agent-{kid}.jsonl").touch()
        who = {"agent_id": kid, "agent_type": "critic"}
        tool_input = {"command": f"rm -rf \"$OUT\"/{use_id}", "description": "一時の絵を消す"}
        hook(hook_event_name="SubagentStart", **who)
        hook(hook_event_name="PreToolUse", tool_name="Bash", tool_use_id=use_id, tool_input=tool_input, **who)
        hook(hook_event_name="PermissionRequest", tool_name="Bash", tool_input=tool_input, **who)

    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    watch = Watch(origin=url)
    t0 = time.monotonic()
    try:
        for _ in range(400):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        hook(hook_event_name="SessionStart", source="startup")
        hook(hook_event_name="UserPromptSubmit", prompt="批評を走らせて")
        ctx = await browser.new_context(**DESKTOP)
        page = await ctx.new_page()
        watch.attach(page, "past-perm")
        await page.goto(url + "/")
        await ready(page)
        label = next(s["label"] for s in snap()["sessions"] if s["id"] == SID)
        await wait(page, "(id) => !!window.__dbg.dazed(id)", arg=label, timeout=30000, label="the main robot")

        # 1. it really waits, its robot busy with a call beside it
        asks(KIDS[0], "toolu_A")
        hook(hook_event_name="PreToolUse", tool_name="Read", tool_use_id="toolu_B", tool_input={"file_path": "/work/past-app/a"}, agent_id=KIDS[0], agent_type="critic")
        await page.evaluate("(id) => window.__dbg.openRobot(id)", label)
        await wait(page, "() => !document.getElementById('rb').hidden", label="the card")
        await page.click('#rb [data-rb-tab="history"]')
        one = T("panel.count.waiting", n=1)
        await wait(page, f"() => {{ const c = ({COUNTS})(); return c.header === {json.dumps(one)} && !!c.bar; }}", label="the header and the bar say the card")
        time.sleep(3)   # the transcript's reader has had its first sight of the file
        result(KIDS[0], "toolu_B", "1\tline", False)   # the call beside it ends
        hook(hook_event_name="PostToolUse", tool_name="Read", tool_use_id="toolu_B", tool_input={"file_path": "/work/past-app/a"}, agent_id=KIDS[0], agent_type="critic")
        hook(hook_event_name="PreToolUse", tool_name="Read", tool_use_id="toolu_C", tool_input={"file_path": "/work/past-app/b"}, agent_id=KIDS[0], agent_type="critic")
        await page.wait_for_timeout(3000)
        c = res["waiting"] = await page.evaluate(COUNTS)
        check(failures, card_statuses().get(KIDS[0]) == "pending", f"the end of the call beside it closes nothing: {card_statuses()}")
        check(failures, c["header"] == one and c["filter"] == "1" and c["bar"], f"a card that really waits: header, bar and filter say it: {c}")
        check(failures, T("status.waiting") in c["listed"], f"the session's row says so: {c['listed']}")
        await page.screenshot(path=str(out / "really-waits.png"))
        await page.click('#sess-filter [data-sf="waiting"]')
        await wait(page, "() => document.querySelectorAll('#sessions [data-sst]').length === 1", label="the filter lists the session")
        await page.click('#sess-filter [data-sf="all"]')

        # 2. the incident: the safety check's prompt timed out, no hook, the child works on
        result(KIDS[0], "toolu_A", SAFETY)
        await wait(page, "() => document.getElementById('chip-perm').hidden", label="the header's count gone once the result is written")
        c = res["timedOut"] = await page.evaluate(COUNTS)
        check(failures, card_statuses().get(KIDS[0]) == "expired", f"the card is over: {card_statuses()}")
        check(failures, c["filter"] == "0" and not c["bar"] and not c["waits"], f"a past permission: nothing counts it: {c}")
        await page.screenshot(path=str(out / "past.png"))

        # 3. a child ends with its card open and no result written
        asks(KIDS[1], "toolu_D")
        await wait(page, "() => !document.getElementById('chip-perm').hidden", label="the second child's card")
        hook(hook_event_name="SubagentStop", agent_id=KIDS[1], agent_type="critic", agent_transcript_path=str(run_folder / f"agent-{KIDS[1]}.jsonl"))
        await wait(page, "() => document.getElementById('chip-perm').hidden", label="a child's end closes its card")
        c = res["childEnded"] = await page.evaluate(COUNTS)
        check(failures, c["filter"] == "0" and not c["bar"], f"the child's end: nothing counts it: {c}")

        # 4. the main session's Stop while the work goes on in the background: a child that waits still waits
        asks(KIDS[2], "toolu_E")
        await wait(page, "() => !document.getElementById('chip-perm').hidden", label="the third child's card")
        hook(hook_event_name="Stop", background_tasks=[{"id": "wf", "type": "workflow"}], last_assistant_message="待ちます")
        await page.wait_for_timeout(1500)
        c = res["background"] = await page.evaluate(COUNTS)
        check(failures, card_statuses().get(KIDS[2]) == "pending" and c["header"] == one and c["filter"] == "1", f"Stop with background work leaves the card: {card_statuses()} {c}")
        hook(hook_event_name="Stop", background_tasks=[], last_assistant_message="終わり")
        await wait(page, "() => document.getElementById('chip-perm').hidden", label="the last Stop closes it")

        # 5. time alone closes nothing: past the stale time (shortened here) a card and a question stay, and say so
        # (ticket 2026-11-05-viz-ten-minute-expiry-removes-a-permission-still-waiting), and can be closed by hand (the
        # requester, 11-05: 残して手で閉じる): nothing goes to the receiver
        asks(KIDS[3], "toolu_F")
        request_f = {"session_id": SID, "cwd": CWD, "transcript_path": str(main), "permission_mode": "default", "hook_event_name": "PermissionRequest", "tool_name": "Bash",
                     "tool_input": {"command": 'rm -rf "$OUT"/toolu_F', "description": "一時の絵を消す"}, "agent_id": KIDS[3], "agent_type": "critic"}
        decide = subprocess.Popen([sys.executable, "-I", "-S", str(forward), "--decide"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(base_env, HOME=str(home)))
        decide.stdin.write(json.dumps(request_f).encode())
        decide.stdin.close()
        decide.stdin = None
        asks(KIDS[4], "toolu_H")
        hook(hook_event_name="PreToolUse", tool_name="AskUserQuestion", tool_use_id="q-1", tool_input=QUESTION)
        await wait(page, "() => !document.getElementById('chip-ask').hidden && document.getElementById('chip-perm').textContent === %s" % json.dumps(T("panel.count.waiting", n=2)), label="two cards and a question")
        c = await page.evaluate(STALE)
        check(failures, not c["perm"] and not c["question"] and c["permButtons"] == 0 and c["questionButtons"] == 0, f"a new card and question: no word of their age, no 閉じる: {c}")
        await wait(page, f"() => ({STALE})().perm", timeout=STALE_MS + 20000, label="the card on the task board says it is old")
        await wait(page, f"() => ({STALE})().question", timeout=20000, label="the question's card says it is old")
        c = res["stale"] = await page.evaluate(STALE)
        s = snap()
        two = T("panel.count.waiting", n=2)
        check(failures, c["perm"] and c["question"] and c["permButtons"] > 0 and c["questionButtons"] > 0 and c["header"] == two and {x["status"] for x in s["perms"]} >= {"pending"}
              and [x["status"] for x in s["questions"]] == ["pending"], f"old, still there, still counted, 閉じる on each: {c}")
        check(failures, c["permNote"] and c["questionNote"], f"the words say nothing goes to the receiver: {c}")
        await page.screenshot(path=str(out / "stale.png"))
        await page.locator("#tasks [data-perm-box]").first.screenshot(path=str(out / "stale-perm-box.png"))
        await page.locator("#questions [data-qcard]").first.screenshot(path=str(out / "stale-question.png"))
        phone = await browser.new_context(**PHONE)
        pp = await phone.new_page()
        watch.attach(pp, "past-perm-phone")
        await pp.goto(url + "/")
        await ready(pp)
        await wait(pp, """() => !!document.querySelector('#questions [data-dismiss="q"]') && !!document.querySelector('#tasks [data-dismiss="perm"]')""", label="the buttons on a phone")
        for sel, name in (("#tasks [data-perm-box]", "phone-perm"), ("#questions [data-qcard]", "phone-question")):
            await pp.locator(sel).first.scroll_into_view_if_needed()
            await pp.locator(sel).first.screenshot(path=str(out / f"stale-{name}.png"))
        fit = res["phoneButtons"] = await pp.evaluate("""() => { const r = (s) => { const b = document.querySelector(s).getBoundingClientRect(); return [b.left, b.right, b.height]; };
          return { perm: r('#tasks [data-dismiss="perm"]'), q: r('#questions [data-dismiss="q"]'), width: innerWidth, sideways: document.documentElement.scrollWidth > document.documentElement.clientWidth }; }""")
        check(failures, all(0 <= b[0] and b[1] <= fit["width"] and b[2] >= 20 for b in (fit["perm"], fit["q"])) and not fit["sideways"], f"on a phone the buttons are on the page: {fit}")
        await phone.close()

        # 閉じる on the first card: gone, the other stays (the control), the waiting hook prints nothing
        first = next(x for x in snap()["perms"] if x["agentId"] == KIDS[3])
        check(failures, decide.poll() is None, "the --decide hook still waits before 閉じる")
        await page.click(f"#tasks [data-dismiss-id='{first['id']}']")
        await wait(page, "(w) => document.getElementById('chip-perm').textContent === w", arg=one, label="the header counts one less")
        got = decide.communicate(timeout=10)[0]
        check(failures, got == b"", f"the receiver's hook prints nothing, neither allow nor deny: {got!r}")
        c = res["closedOne"] = await page.evaluate(COUNTS)
        check(failures, c["header"] == one and first["id"] not in [x["id"] for x in snap()["perms"]], f"closed: out of the counts and the server: {c}")
        await page.reload()
        await ready(page)
        await wait(page, "(id) => !!window.__dbg.dazed(id)", arg=label, timeout=30000, label="the main robot after a reload")
        await page.evaluate("(id) => window.__dbg.openRobot(id)", label)
        await page.click('#rb [data-rb-tab="history"]')
        await wait(page, "(w) => document.getElementById('chip-perm').textContent === w", arg=one, label="after a reload the other card is there, the closed one is not")
        check(failures, await page.locator(f"[data-dismiss-id='{first['id']}']").count() == 0, "the closed card does not come back on a reload")
        # what comes later: the real result and the hook find no card
        result(KIDS[3], "toolu_F", SAFETY)
        hook(hook_event_name="PostToolUse", tool_name="Bash", tool_use_id="toolu_F", tool_input=request_f["tool_input"], agent_id=KIDS[3], agent_type="critic")
        await page.wait_for_timeout(3000)
        check(failures, first["id"] not in [x["id"] for x in snap()["perms"]] and await page.evaluate("() => document.getElementById('chip-perm').textContent") == one, "a result that comes later brings nothing back")
        # the last card and the question: every count is 0, and the robots no longer wait
        second = next(x for x in snap()["perms"] if x["agentId"] == KIDS[4])
        await page.click(f"#tasks [data-dismiss-id='{second['id']}']")
        await wait(page, "() => document.getElementById('chip-perm').hidden", label="the last card closed")
        question = snap()["questions"][0]
        await page.click(f"#questions [data-dismiss-id='{question['id']}']")
        await wait(page, "() => document.getElementById('chip-ask').hidden", label="the question closed")
        await page.wait_for_timeout(800)
        c = res["closedAll"] = await page.evaluate(COUNTS)
        s = snap()
        check(failures, c["filter"] == "0" and not c["bar"] and not c["waits"] and T("status.waiting") not in c["listed"], f"nothing counts them any more: {c}")
        still = [x["id"] for x in s["perms"] + s["questions"] if x["status"] in ("pending", "sent")]
        check(failures, not still and not [a["id"] for a in s["agents"] if a["state"] == "waiting"], f"no open card, no robot waiting: {still} {[(a['id'], a['state']) for a in s['agents']]}")
        await page.screenshot(path=str(out / "closed.png"))
        await page.reload()
        await ready(page)
        await page.wait_for_timeout(1500)
        check(failures, await page.evaluate("() => document.getElementById('chip-perm').hidden && document.getElementById('chip-ask').hidden"), "after a reload nothing is back")
        hook(hook_event_name="SubagentStop", agent_id=KIDS[3], agent_type="critic")
        hook(hook_event_name="SubagentStop", agent_id=KIDS[4], agent_type="critic")

        # a question a hook waits on: not old, no 閉じる, whatever the time (a page reports itself visible every 5 s)
        await page.wait_for_timeout(6000)
        ask = subprocess.Popen([sys.executable, "-I", "-S", str(forward), "--ask"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(base_env, HOME=str(home)))
        ask.stdin.write(json.dumps({"session_id": SID, "cwd": CWD, "transcript_path": str(main), "permission_mode": "default", "hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion", "tool_use_id": "q-hook", "tool_input": QUESTION}).encode())
        ask.stdin.close()
        ask.stdin = None
        res["hookQuestion"] = None
        try:
            await wait(page, "() => !!document.querySelector('#questions [data-qsend]')", label="the question a hook waits on")
        finally:
            res["hookQuestion"] = snap()["questions"][-1:]
        await page.wait_for_timeout(STALE_MS + 3000)
        c = res["hookWaits"] = await page.evaluate(STALE)
        q = snap()["questions"][-1]
        check(failures, q["hookWaiting"] and not q.get("stale") and c["questionButtons"] == 0 and ask.poll() is None, f"a question a hook waits on has no 閉じる: {q.get('stale')} {c}")
        hook(hook_event_name="Stop", background_tasks=[], last_assistant_message="終わり")
        ask.communicate(timeout=10)

        # 6. a restart: cards live in the server's memory, none comes back, the closed ones with them
        srv.terminate()
        srv.wait(timeout=10)
        srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT,
                               env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1", JUI_VIZ_STALE_MS=str(STALE_MS)))
        for _ in range(400):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        s = res["restarted"] = {"perms": snap()["perms"], "questions": snap()["questions"]}
        check(failures, s == {"perms": [], "questions": []}, f"after a restart no closed card is back: {s}")
        hook(hook_event_name="SessionStart", source="resume")
        await page.goto(url + "/")
        await ready(page)
        await page.wait_for_timeout(1000)
        check(failures, await page.evaluate("() => document.getElementById('chip-perm').hidden"), "the page after a restart says none waits")

        # 7. the header counts all the projects, the list the one shown: the words say so, the number stays
        # (ticket 2026-11-05-viz-header-permission-count-spans-all-projects)
        hook(OTHER, cwd=OTHER_CWD, hook_event_name="SessionStart", source="startup")
        hook(OTHER, cwd=OTHER_CWD, hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="toolu_G", tool_input={"command": "make"})
        hook(OTHER, cwd=OTHER_CWD, hook_event_name="PermissionRequest", tool_name="Bash", tool_input={"command": "make"})
        hook(OTHER, cwd=OTHER_CWD, hook_event_name="PreToolUse", tool_name="AskUserQuestion", tool_use_id="q-2", tool_input=QUESTION)
        await wait(page, "(w) => document.getElementById('chip-perm').textContent === w", arg=one, label="all the projects shown: the plain words")
        pid = next(x["projectId"] for x in snap()["sessions"] if x["id"] == SID)
        await page.click("[data-scope-btn]")
        await page.click(f"#pop [data-pick-project='{pid}']")
        words = T("panel.count.waiting.elsewhere", n=1, m=1)
        await wait(page, "(w) => document.getElementById('chip-perm').textContent === w", arg=words, label="the other project's permission said in the chip")
        c = res["elsewhere"] = await page.evaluate(COUNTS)
        ask = await page.evaluate("() => document.getElementById('chip-ask').textContent")
        res["elsewhereAsk"] = ask
        check(failures, c["filter"] == "0" and words == c["header"], f"the number stays, the list's is the project's, the words say why: {c}")
        check(failures, ask == T("panel.chip.ask.elsewhere", n=1, m=1), f"the question chip too: {ask!r}")
        await page.screenshot(path=str(out / "elsewhere.png"))
        phone = await browser.new_context(**PHONE)
        pp = await phone.new_page()
        watch.attach(pp, "past-perm-phone")
        await pp.goto(url + "/")
        await ready(pp)
        await pp.click("[data-scope-btn]")
        await pp.click(f"#pop [data-pick-project='{pid}']")
        await wait(pp, "(w) => document.getElementById('chip-perm').textContent === w", arg=words, label="the words on a phone")
        fit = res["phone"] = await pp.evaluate("() => { const r = document.getElementById('chip-perm').getBoundingClientRect(); return { left: r.left, right: r.right, width: innerWidth, sideways: document.documentElement.scrollWidth > document.documentElement.clientWidth }; }")
        check(failures, fit["left"] >= 0 and fit["right"] <= fit["width"] and not fit["sideways"], f"on a phone the chip stays on the page: {fit}")
        await pp.screenshot(path=str(out / "elsewhere-phone.png"))
        await phone.close()
        await ctx.close()
    finally:
        (out / "past-perm-results.json").write_text(dump(res) + "\n")
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  past-perm: {time.monotonic() - t0:.0f}s", flush=True)
    check_watch(watch, "past-perm", failures)
