"""The robot card's layout with its tabs (2.3.1, requester 10-18: "応答の履歴のタブの表示壊れてない？").

2.3.0 added the tab row as a third child of .rb, whose grid had two rows (the head, then the body): the body took an
implicit row of its own height and nothing scrolled. The real `jui viz serve` in a throwaway HOME on a free port,
a session with a long transcript and many turns, so both tabs overflow. For each tab, light and dark, a short wide
window and 390 px: the tab row ends at or above where the shown body begins, the body is inside the card, and the
body scrolls (scrollTop moves). Screenshots for docs/bugs/evidence/.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import time

from common import ISOLATE, LAUNCH_ARGS, Watch, dump, new_page, ready, stamp

SID = "e2e00000-0000-4000-8000-0000000000d4"
CWD = "/work/rb-layout-app"
SHORT = {"viewport": {"width": 1280, "height": 620}, "device_scale_factor": 1}
PHONE = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 2, "is_mobile": True, "has_touch": True}

MEASURE = """() => {
  const rb = document.getElementById('rb');
  const tabs = rb.querySelector('.rb-tabs');
  const body = [...rb.querySelectorAll('.rb-body')].find((b) => !b.hidden);
  const r = (el) => { const x = el.getBoundingClientRect(); return { top: Math.round(x.top), bottom: Math.round(x.bottom), height: Math.round(x.height) }; };
  const keep = body.scrollTop;
  body.scrollTop = 0;
  const before = body.scrollTop;
  body.scrollTop = 400;
  const after = body.scrollTop;
  body.scrollTop = keep;
  return { card: r(rb), tabs: r(tabs), body: r(body), rows: getComputedStyle(rb).gridTemplateRows,
           which: body.dataset.rbHist !== undefined ? 'history' : 'now',
           overflow: body.scrollHeight - body.clientHeight, scrolled: after - before };
}"""


def check(failures, cond, text):
    if not cond:
        failures.append(f"rb-layout: {text}")


async def wait(page, js, timeout=20000, label=""):
    try:
        await page.wait_for_function(js, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def run_rb_layout(pw, out, failures, shots: pathlib.Path | None = None):
    from run import free_port
    out = pathlib.Path(out) / "rb-layout"
    out.mkdir(parents=True, exist_ok=True)
    shots = shots or out
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    transcript = home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", CWD) / f"{SID}.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for n in range(30):
        lines.append({"type": "user", "timestamp": stamp("2026-10-18T09:00:00Z"), "message": {"role": "user", "content": f"指示 {n}"}})
        lines.append({"type": "assistant", "timestamp": stamp("2026-10-18T09:00:01Z"),
                      "message": {"id": f"m{n}", "role": "assistant", "content": [{"type": "text", "text": f"## 応答 {n}\n- 一行目\n- 二行目"}]}})
    transcript.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines))
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}
    base = {"session_id": SID, "cwd": CWD, "transcript_path": str(transcript), "permission_mode": "default"}

    def hook(payload):
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(payload).encode(),
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
        hook(dict(base, hook_event_name="SessionStart", source="startup"))
        for n in range(14):    # turns: the 今の様子 tab's task list grows past the card
            hook(dict(base, hook_event_name="UserPromptSubmit", prompt=f"指示 {n} の題"))
            hook(dict(base, hook_event_name="Stop"))
        watch = Watch(origin=url)
        for label, size in (("wide", SHORT), ("phone", PHONE)):
            for scheme in ("light", "dark"):
                page = await new_page(browser, watch, f"rb-{label}-{scheme}", **size)
                await page.emulate_media(color_scheme=scheme)
                await page.goto(url + "/")
                await ready(page)
                await wait(page, "() => !!document.querySelector('#sessions [data-robot-open]')", label="the robot")
                await page.evaluate("() => document.querySelector('#sessions [data-robot-open]').click()")
                await wait(page, "() => !!document.querySelector('#rb .rb-tabs') && !document.getElementById('rb').hidden", label="the card")
                await page.wait_for_timeout(700)
                for tab in ("now", "history"):
                    # the tab must take a real click (2.3.0: covered by the body, it timed out)
                    try:
                        await page.click(f'#rb [data-rb-tab="{tab}"]', timeout=5000)
                        clickable = True
                    except Exception:
                        clickable = False
                        await page.evaluate("(t) => document.querySelector(`#rb [data-rb-tab=\"${t}\"]`).click()", tab)
                    if tab == "history":
                        await wait(page, "() => document.querySelectorAll('[data-rb-hist] .h-item').length >= 20", label="the history")
                    await page.wait_for_timeout(500)
                    m = await page.evaluate(MEASURE)
                    key = f"{label}-{scheme}-{tab}"
                    m["clickable"] = clickable
                    res[key] = m
                    check(failures, clickable, f"{key}: the {tab} tab takes a click")
                    await page.screenshot(path=str(shots / f"{key}.png"))
                    check(failures, m["which"] == tab, f"{key}: the {tab} body is the one shown ({m['which']})")
                    check(failures, m["tabs"]["bottom"] <= m["body"]["top"], f"{key}: the tabs end at or above the body (tabs {m['tabs']}, body {m['body']})")
                    check(failures, m["body"]["bottom"] <= m["card"]["bottom"] + 1, f"{key}: the body ends inside the card (body {m['body']}, card {m['card']})")
                    check(failures, m["overflow"] > 0 and m["scrolled"] > 0, f"{key}: the body overflows and scrolls (overflow {m['overflow']}, scrolled {m['scrolled']})")
                await page.close()
        for line in watch.console:
            failures.append(f"rb-layout: console: {line}")
        for u in watch.foreign:
            failures.append(f"rb-layout: request outside the server: {u}")
    except Exception as e:
        failures.append(f"rb-layout: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  rb-layout/tabs: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "rb-layout-results.json").write_text(dump(res) + "\n")
