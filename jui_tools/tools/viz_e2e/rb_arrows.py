"""← → on the robot card switch robots (2.3.1, requester 10-18: "この画面の時に左右キーとかでロボットを切り替えれるようにできる？").

The real `jui viz serve` in a throwaway HOME on a free port: three sessions in /work/alpha-app, one in
/work/beta-app. With alpha picked, → three times visits alpha's three robots in label order and comes back (the ends
wrap), ← goes the other way, beta's robot is never reached; the 応答の履歴 tab stays open across switches; a focused
text field keeps its arrow keys; the › button steps like →. Light and 390 px screenshots.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import ISOLATE, LAUNCH_ARGS, Watch, dump, new_page, ready

ALPHA = ["a1000000-0000-4000-8000-0000000000e1", "a2000000-0000-4000-8000-0000000000e2", "a3000000-0000-4000-8000-0000000000e3"]
BETA = "b1000000-0000-4000-8000-0000000000e4"
DESKTOP = {"viewport": {"width": 1440, "height": 900}, "device_scale_factor": 1}
PHONE = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 2, "is_mobile": True, "has_touch": True}

BADGE = "() => (document.querySelector('#rb .rb-badge') || {}).textContent || ''"
STATE = """() => ({ badge: (document.querySelector('#rb .rb-badge') || {}).textContent || '',
  tab: (document.querySelector('#rb [data-rb-tab][aria-selected="true"]') || {}).dataset ? document.querySelector('#rb [data-rb-tab][aria-selected="true"]').dataset.rbTab : '',
  histShown: !(document.querySelector('[data-rb-hist]') || { hidden: true }).hidden })"""


def check(failures, cond, text):
    if not cond:
        failures.append(f"rb-arrows: {text}")


async def wait(page, js, timeout=20000, label=""):
    try:
        await page.wait_for_function(js, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def run_rb_arrows(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "rb-arrows"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def hook(sid, cwd):
        subprocess.run([sys.executable, "-I", "-S", str(forward)],
                       input=json.dumps({"session_id": sid, "cwd": cwd, "transcript_path": f"/nowhere/{sid}.jsonl",
                                         "permission_mode": "default", "hook_event_name": "SessionStart", "source": "startup"}).encode(),
                       capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)

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
        for sid in ALPHA:
            hook(sid, "/work/alpha-app")
        hook(BETA, "/work/beta-app")
        watch = Watch(origin=url)
        page = await new_page(browser, watch, "rb-arrows", **DESKTOP)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelectorAll('#sessions [data-robot-open]').length >= 4", label="four robots")
        groups = await page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('#sessions .pgroup')].map((g) =>
          [g.querySelector('.pg-toggle b').textContent, [...g.querySelectorAll('[data-robot-open]')].map((b) => b.dataset.robotOpen)]))""")
        alpha = next(v for k, v in groups.items() if "alpha" in k)
        beta = next(v for k, v in groups.items() if "beta" in k)
        res["groups"] = groups
        # pick the alpha room
        await page.click("#scope-top")
        await page.evaluate("() => [...document.querySelectorAll('#pop [data-pick-project]')].find((x) => x.textContent.includes('alpha')).click()")
        await page.wait_for_timeout(1500)
        await page.evaluate("(id) => window.__dbg.openRobot(id)", alpha[0])
        await wait(page, f"() => ({BADGE})() === {json.dumps(alpha[0])}", label="alpha's first robot")
        await page.wait_for_timeout(800)

        # → three times: every alpha robot once, back to the first; ← the other way
        forward_seen = []
        for _ in range(3):
            await page.keyboard.press("ArrowRight")
            await page.wait_for_timeout(250)
            forward_seen.append(await page.evaluate(BADGE))
        back_seen = []
        for _ in range(3):
            await page.keyboard.press("ArrowLeft")
            await page.wait_for_timeout(250)
            back_seen.append(await page.evaluate(BADGE))
        want = sorted(alpha, key=lambda x: (len(x), x))
        res["forward"], res["back"], res["alpha"], res["beta"] = forward_seen, back_seen, alpha, beta
        start = alpha[0]
        i = want.index(start)
        check(failures, forward_seen == [want[(i + k) % 3] for k in (1, 2, 3)], f"→ visits alpha in label order and wraps: {forward_seen} (alpha {want})")
        check(failures, back_seen == [want[(i - k) % 3] for k in (1, 2, 3)], f"← goes the other way: {back_seen}")
        check(failures, not set(beta) & set(forward_seen + back_seen), f"never a robot outside the project picked: beta {beta}")

        # the tab stays across a switch
        await page.click('#rb [data-rb-tab="history"]')
        await page.wait_for_timeout(300)
        await page.keyboard.press("ArrowRight")
        await page.wait_for_timeout(400)
        res["tabKept"] = st = await page.evaluate(STATE)
        check(failures, st["tab"] == "history" and st["histShown"], f"the 応答の履歴 tab stays open: {st}")
        await page.screenshot(path=str(out / "switched-history.png"))

        # a focused text field keeps its arrow keys
        before = await page.evaluate(BADGE)
        await page.evaluate("() => { const i = document.createElement('input'); i.id = 'e2e-field'; i.value = 'abc'; document.body.append(i); i.focus(); i.setSelectionRange(0, 0); }")
        await page.keyboard.press("ArrowRight")   # one way only: → then ← would come back to the same robot either way
        await page.wait_for_timeout(300)
        caret = await page.evaluate("() => document.getElementById('e2e-field').selectionStart")
        res["typing"] = after = await page.evaluate(BADGE)
        check(failures, after == before and caret == 1, f"typing in a field does not switch robots, the caret moves: {before} -> {after}, caret {caret}")
        await page.evaluate("() => document.getElementById('e2e-field').remove()")

        # the › button steps like →
        await page.click('#rb [data-rb-step="1"]')
        await page.wait_for_timeout(300)
        res["button"] = b = await page.evaluate(BADGE)
        check(failures, b == want[(want.index(before) + 1) % 3], f"the › button steps forward: {before} -> {b}")
        await page.evaluate("() => document.querySelector('#rb [data-rb-tab=\"now\"]').click()")
        await page.screenshot(path=str(out / "switched-now.png"))
        await page.close()

        phone = await new_page(browser, watch, "rb-arrows-phone", **PHONE)
        await phone.goto(url + "/")
        await ready(phone)
        await wait(phone, "() => document.querySelectorAll('#sessions [data-robot-open]').length >= 4", label="the phone's robots")
        await phone.evaluate("(id) => window.__dbg.openRobot(id)", alpha[0])
        await wait(phone, "() => !!document.querySelector('#rb [data-rb-step]')", label="the phone's card")
        await phone.wait_for_timeout(800)
        res["phone"] = await phone.evaluate("() => ({ hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth, steps: document.querySelectorAll('#rb [data-rb-step]').length, labels: [...document.querySelectorAll('#rb [data-rb-step]')].map((b) => b.getAttribute('aria-label')) })")
        await phone.screenshot(path=str(out / "phone.png"))
        check(failures, res["phone"]["hscroll"] is False and res["phone"]["steps"] == 2 and all(res["phone"]["labels"]), f"390 px: the buttons, labelled, no horizontal scroll: {res['phone']}")
        await phone.close()
        for line in watch.console:
            failures.append(f"rb-arrows: console: {line}")
        for u in watch.foreign:
            failures.append(f"rb-arrows: request outside the server: {u}")
    except Exception as e:
        failures.append(f"rb-arrows: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  rb-arrows/keys: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "rb-arrows-results.json").write_text(dump(res) + "\n")
