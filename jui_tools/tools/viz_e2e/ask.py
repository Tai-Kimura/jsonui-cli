"""AskUserQuestion answered from the page, end to end (requester, 10-18).

The real `jui viz serve` in a throwaway HOME and the real forward.py: the async forward reports the question, then
`forward.py --ask` (the synchronous PreToolUse hook) waits; the page answers on its question card — a single choice,
a multiple choice with a free answer, every question before the button allows sending — and the hook prints the
documented answer: allow, the input as it came, and ``answers`` keyed by the question's text. Also: a question that
cannot be shown in full gets no inputs; a page that is not visible lets the hook through at once; the terminal
answering first ends the wait with nothing printed. Dark mode and 390 px, no console error.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, PHONE, Watch, dump, new_page, ready

FRUIT = {"question": "好きな果物は？ <b>太字</b>", "header": "果物", "multiSelect": False,
         "options": [{"label": "りんご", "description": "赤くて丸い"},
                     {"label": "みかん", "description": "冬の果物", "preview": "## みかん\n- 甘い\n- <script>x</script>"}]}
COLOR = {"question": "好きな色は？", "header": "色", "multiSelect": True,
         "options": [{"label": "赤", "description": "情熱"}, {"label": "青", "description": "冷静"}, {"label": "緑", "description": "自然"}]}
INPUT = {"questions": [FRUIT, COLOR]}


def check(failures, cond, text):
    if not cond:
        failures.append(f"ask: {text}")


async def wait(page, js, arg=None, timeout=20000, label=""):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def run_ask(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "ask"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    # a short wait so "nobody answers" ends quickly here; holds from the card keep it open while the suite clicks
    # (paths.viz_home() under the fake HOME; nothing in the environment may point it at the real server's files)
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    (home / ".local" / "state" / "jui-viz" / "config.json").write_text(json.dumps({"askWaitSec": 8, "askMaxSec": 60}))
    base_env = {k: v for k, v in os.environ.items() if k not in ("JUI_VIZ_HOME", "XDG_STATE_HOME")}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}
    sid, cwd = "e2e00000-0000-4000-8000-0000000000a5", "/work/ask-app"
    base = {"session_id": sid, "cwd": cwd, "transcript_path": "/work/home/t.jsonl", "permission_mode": "default"}

    def hook(payload, ask=False):
        args = [sys.executable, "-I", "-S", str(forward)] + (["--ask"] if ask else [])
        p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(base_env, HOME=str(home)))
        p.stdin.write(json.dumps(payload).encode())
        p.stdin.close()
        p.stdin = None
        if ask:
            return p
        p.wait(timeout=10)
        return None

    def pre(use_id, tool_input=INPUT):
        return dict(base, hook_event_name="PreToolUse", tool_name="AskUserQuestion", tool_use_id=use_id, tool_input=tool_input)

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
        page = await new_page(browser, watch, "ask", **DESKTOP)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", label="connected")
        hook(dict(base, hook_event_name="SessionStart", source="startup"))
        await wait(page, "() => window.__dbg.robots.length === 1", label="the session's robot")
        await page.wait_for_timeout(5500)   # one presence report after the page is up

        # 1. answered on the page: one fruit, two colours and a free one
        hook(pre("ask-1"))
        waiting = hook(pre("ask-1"), ask=True)
        await wait(page, "() => !!document.querySelector('.qcard.q-open [data-qsend]')", timeout=15000, label="the open question card")
        res["card"] = await page.evaluate("""() => { const c = document.querySelector('.qcard.q-open');
          return { legends: [...c.querySelectorAll('legend')].map((l) => l.textContent), bold: !!c.querySelector('legend b'),
                   script: !!c.querySelector('script'), preview: (c.querySelector('.qprev') || {}).textContent || '',
                   chip: document.getElementById('chip-ask').textContent, robot: (window.__dbg.robotState()['e2'] || window.__dbg.robotState()[Object.keys(window.__dbg.robotState())[0]] || {}).state }; }""")
        check(failures, res["card"]["legends"][0].startswith("果物好きな果物は？ <b>太字</b>") and not res["card"]["bold"] and not res["card"]["script"]
              and "<script>x</script>" in res["card"]["preview"], f"the question shows as text, not markup: {res['card']}")
        check(failures, res["card"]["chip"] == "質問 1" and res["card"]["robot"] == "waiting", f"the chip counts it and the robot waits: {res['card']}")
        # a robot waiting on a question is not waiting for a permission: its own badge and filter (requester, 10-18)
        res["asking"] = await page.evaluate("""() => { const n = (k) => document.querySelector(`#sess-filter [data-sf="${k}"] b`).textContent;
          const badge = document.querySelector('#sessions [data-sst]'); return { waiting: n('waiting'), asking: n('asking'), badge: badge && badge.textContent,
          sum: (document.querySelector('#sessions [data-pgsum]') || {}).textContent || '' }; }""")
        check(failures, res["asking"]["waiting"] == "0" and res["asking"]["asking"] == "1" and res["asking"]["badge"] == "質問に回答待ち"
              and "許可待ち" not in res["asking"]["sum"] and "質問待ち 1" in res["asking"]["sum"], f"a question is not counted as a permission wait: {res['asking']}")
        res["countdown"] = await page.evaluate("() => (document.querySelector('.qcard.q-open [data-quntil]') || {}).textContent || ''")
        check(failures, res["countdown"].startswith("あと ") and res["countdown"].endswith("秒でターミナルに戻す"), f"the time left shows: {res['countdown']!r}")
        send = ".qcard.q-open [data-qsend]"
        steps = []
        await page.click(".qcard.q-open fieldset:nth-of-type(1) label:has-text('みかん')")
        steps.append(await page.evaluate("(s) => document.querySelector(s).disabled", send))          # the colours still open
        await page.click(".qcard.q-open fieldset:nth-of-type(2) label:has-text('赤')")
        await page.click(".qcard.q-open fieldset:nth-of-type(2) label:has-text('緑')")
        await page.click(".qcard.q-open fieldset:nth-of-type(2) .qother input[type='checkbox']")
        steps.append(await page.evaluate("(s) => document.querySelector(s).disabled", send))          # その他 ticked, nothing typed
        await page.fill(".qcard.q-open fieldset:nth-of-type(2) .qother-text", "金 と 銀")
        steps.append(await page.evaluate("(s) => document.querySelector(s).disabled", send))
        res["sendSteps"] = steps
        check(failures, steps == [True, True, False], f"the button waits for every answer: {steps}")
        await page.screenshot(path=str(out / "question.png"))
        await page.click(send)
        outp, _ = waiting.communicate(timeout=40)
        got = json.loads(outp) if outp else None
        res["hookOutput"] = got
        hso = (got or {}).get("hookSpecificOutput") or {}
        answers = (hso.get("updatedInput") or {}).get("answers")
        check(failures, hso.get("hookEventName") == "PreToolUse" and hso.get("permissionDecision") == "allow"
              and (hso.get("updatedInput") or {}).get("questions") == INPUT["questions"], f"the hook answers allow with the input as it came: {got}")
        check(failures, answers == {FRUIT["question"]: "みかん", COLOR["question"]: "赤, 緑, 金 と 銀"}, f"the answers: {answers}")
        hook(dict(base, hook_event_name="PostToolUse", tool_name="AskUserQuestion", tool_use_id="ask-1",
                  tool_input={**INPUT, "answers": answers or {}}, tool_response={"answers": answers or {}}))
        await wait(page, "() => [...document.querySelectorAll('.qcard .qdone')].some((p) => p.textContent.includes('ブラウザの答えが届いた'))", label="the card confirmed")
        res["log"] = await page.evaluate("() => [...document.querySelectorAll('#ticker li')].map((l) => l.textContent).filter((t) => t.includes('質問に回答'))")
        check(failures, any("ブラウザで質問に回答" in t and "果物: みかん" in t for t in res["log"]), f"the answer is in the log: {res['log']}")

        # 2. the terminal answers first: the waiting hook prints nothing
        hook(pre("ask-2"))
        waiting = hook(pre("ask-2"), ask=True)
        await wait(page, "() => !!document.querySelector('.qcard.q-open')", timeout=15000, label="the second card")
        hook(dict(base, hook_event_name="PostToolUse", tool_name="AskUserQuestion", tool_use_id="ask-2",
                  tool_input={**INPUT, "answers": {FRUIT["question"]: "りんご", COLOR["question"]: "青"}}, tool_response={}))
        outp, _ = waiting.communicate(timeout=20)
        res["terminalFirst"] = outp.decode()
        check(failures, res["terminalFirst"] == "", f"the terminal answered first: the hook printed {res['terminalFirst']!r}")
        await wait(page, "() => [...document.querySelectorAll('.qcard .qdone')].some((p) => p.textContent.includes('ターミナルで答えた'))", label="the terminal's answer shown")

        # 2b. 「ターミナルで答える」: the hook stops waiting at once and prints nothing
        hook(pre("ask-2b"))
        waiting = hook(pre("ask-2b"), ask=True)
        await wait(page, "() => !!document.querySelector('.qcard.q-open [data-qrelease]')", timeout=15000, label="the release button")
        t1 = time.monotonic()
        await page.click(".qcard.q-open [data-qrelease]")
        outp, _ = waiting.communicate(timeout=20)
        res["release"] = {"printed": outp.decode(), "sec": round(time.monotonic() - t1, 1)}
        await wait(page, "() => [...document.querySelectorAll('.qcard .qnote')].some((p) => p.textContent.includes('ターミナルで答えてください'))", label="the card says: the terminal")
        check(failures, res["release"]["printed"] == "" and res["release"]["sec"] < 5, f"the terminal button ends the wait: {res['release']}")

        # 2c. nobody answers: the hook gives the question back after askWaitSec (8 s here), nothing printed
        hook(pre("ask-2c"))
        t1 = time.monotonic()
        outp, _ = hook(pre("ask-2c"), ask=True).communicate(timeout=40)
        res["nobody"] = {"printed": outp.decode(), "sec": round(time.monotonic() - t1, 1)}
        check(failures, res["nobody"]["printed"] == "" and 7 <= res["nobody"]["sec"] < 14, f"nobody answers: back after the short wait: {res['nobody']}")

        # 2d. the card left behind cannot be answered here and says so first (requester, 10-18: the choices looked
        # pickable and the reason was one line at the bottom)
        await wait(page, "() => [...document.querySelectorAll('.qcard.q-closed .qwhy')].some((p) => p.textContent.includes('時間が過ぎました'))", label="the closed card's reason")
        res["closed"] = await page.evaluate("""() => { const c = [...document.querySelectorAll('.qcard.q-closed')].find((x) => x.querySelector('.qwhy').textContent.includes('時間が過ぎました'));
          const opt = c.querySelector('.qopt'), st = getComputedStyle(opt);
          return { afterHeader: c.children[1].classList.contains('qwhy'), live: c.querySelectorAll('input:not([disabled])').length,
                   inputs: c.querySelectorAll('input').length, cursor: st.cursor, opacity: Number(st.opacity), open: c.classList.contains('q-open') }; }""")
        check(failures, res["closed"]["afterHeader"] and res["closed"]["live"] == 0 and res["closed"]["inputs"] > 0 and res["closed"]["cursor"] == "not-allowed"
              and res["closed"]["opacity"] < 1 and not res["closed"]["open"], f"a card nobody waits on: the reason on top, choices not pickable: {res['closed']}")
        await page.screenshot(path=str(out / "question-closed.png"))

        # 2e. what the VS Code extension sent next (Claude Code 2.1.301, 10-18): a PermissionRequest for the question.
        # The waiting hook lets it through at once, and nothing goes on the permission board or into its count.
        ask_perm = dict(base, hook_event_name="PermissionRequest", tool_name="AskUserQuestion", tool_input=INPUT)
        hook(ask_perm)
        t1 = time.monotonic()
        dp = subprocess.run([sys.executable, "-I", "-S", str(forward), "--decide"], input=json.dumps(ask_perm).encode(),
                            capture_output=True, env=dict(base_env, HOME=str(home)), timeout=40)
        await page.wait_for_timeout(1500)
        res["askPerm"] = {"printed": dp.stdout.decode(), "sec": round(time.monotonic() - t1, 1),
                          **(await page.evaluate("""() => ({ chip: document.getElementById('chip-perm').hidden,
                             boxes: [...document.querySelectorAll('.perm-q b')].filter((b) => b.textContent === 'AskUserQuestion').length })"""))}
        check(failures, res["askPerm"]["printed"] == "" and res["askPerm"]["sec"] < 5 and res["askPerm"]["chip"] is True and res["askPerm"]["boxes"] == 0,
              f"a question's permission request is not a permission: {res['askPerm']}")

        # 3. a question that does not fit: no inputs, answer in the terminal (the hook lets it through at once)
        long = {"questions": [{**FRUIT, "options": [{"label": "りんご", "description": "x" * 5000}, FRUIT["options"][1]]}]}
        hook(pre("ask-3", long))
        t1 = time.monotonic()
        outp, _ = hook(pre("ask-3", long), ask=True).communicate(timeout=20)
        res["tooLong"] = {"printed": outp.decode(), "sec": round(time.monotonic() - t1, 1)}
        await wait(page, "() => [...document.querySelectorAll('.qcard .qnote')].some((p) => p.textContent.includes('全部をここに表示できない'))", label="the too-long note")
        res["tooLong"]["inputs"] = await page.evaluate("() => [...document.querySelectorAll('.qcard')].filter((c) => c.textContent.includes('全部をここに表示できない')).map((c) => c.querySelectorAll('input:not([disabled])').length)")
        check(failures, res["tooLong"]["printed"] == "" and res["tooLong"]["sec"] < 5 and res["tooLong"]["inputs"] == [0], f"a question not shown in full: {res['tooLong']}")

        # dark and 390 px with an open card
        hook(pre("ask-4"))
        dark_wait = hook(pre("ask-4"), ask=True)
        await wait(page, "() => !!document.querySelector('.qcard.q-open')", timeout=15000, label="a card for the screenshots")
        await page.emulate_media(color_scheme="dark")
        await page.wait_for_timeout(600)
        await page.screenshot(path=str(out / "question-dark.png"))
        phone = await new_page(browser, watch, "ask-phone", **PHONE)
        await phone.goto(url + "/")
        await ready(phone)
        await wait(phone, "() => !!document.querySelector('.qcard')", timeout=15000, label="the phone's card")
        await phone.click("#chip-ask")
        await phone.wait_for_timeout(600)
        res["phone"] = await phone.evaluate("() => ({ hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth })")
        await phone.screenshot(path=str(out / "question-phone.png"))
        check(failures, res["phone"] == {"hscroll": False}, f"390 px: no horizontal scroll: {res['phone']}")
        await phone.close()

        # 4. no visible page: the hook goes through at once (the page reports hidden)
        await page.evaluate("() => { Object.defineProperty(document, 'visibilityState', { get: () => 'hidden', configurable: true }); document.dispatchEvent(new Event('visibilitychange')); }")
        await page.wait_for_timeout(800)
        hook(pre("ask-5"))
        t1 = time.monotonic()
        outp, _ = hook(pre("ask-5"), ask=True).communicate(timeout=30)
        res["hidden"] = {"printed": outp.decode(), "sec": round(time.monotonic() - t1, 1)}
        check(failures, res["hidden"]["printed"] == "" and res["hidden"]["sec"] < 5, f"no visible page: the hook goes through at once: {res['hidden']}")
        dark_wait.kill()
        await page.close()
        for line in watch.console:
            failures.append(f"ask: console: {line}")
        for u in watch.foreign:
            failures.append(f"ask: request outside the server: {u}")
        res["console"] = len(watch.console)
    except Exception as e:
        failures.append(f"ask: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  ask/question-cards: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "ask-results.json").write_text(dump(res) + "\n")
