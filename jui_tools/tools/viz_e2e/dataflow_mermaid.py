"""The data flow on a spec's whiteboard as the spec page's Mermaid diagram (requester, 10-19; 2.3.5).

The real `jui viz serve` in a throwaway HOME on a free port, one session in a real JsonUI project made here (a
jui.config.json and two specs: an 二要素認証 screen with a ViewModel, a UseCase, a Repository and two endpoints, its
display name carrying a <script>; and one without a data flow). Its whiteboard's データの流れ draws document_tools'
diagram (the same text the generated spec page holds): an svg with its six nodes, the boxes (持つ値, Repository, API)
still under it, the <script> neither an element nor run (strict drops it), the theme following the page (light / dark),
at the sheet's text size with a scroll bar (幅に合わせる fits it). The spec without a data flow keeps the boxes. Mermaid is read once from the
server; nothing is asked outside. Pictures before (`--jt`) and after.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, new_page, ready

ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
SID = "e2e00000-0000-4000-8000-000000000501"
TWOFA = {
    "type": "screen_spec", "version": "1.0",
    "metadata": {"name": "TwoFactor", "displayName": "二要素認証 <script>window.__pwned = 1</script>", "description": "コードを確かめる",
                 "platforms": ["ios", "android"], "layoutFile": "two_factor"},
    "structure": {"components": [{"type": "TextField", "id": "code", "description": "6 桁"}], "layout": {}},
    "dataFlow": {
        "viewModel": {"methods": [{"name": "verify", "description": "確かめる"}, "resend()"], "vars": [{"name": "code", "type": "String"}]},
        "useCases": [{"name": "VerifyCodeUseCase", "repositories": ["AuthRepository"], "methods": [{"name": "run", "calls": ["AuthRepository.verify"]}]}],
        "repositories": [{"name": "AuthRepository", "methods": [{"name": "verify", "endpoint": "POST /auth/2fa"}]}],
        "apiEndpoints": [{"method": "POST", "path": "/auth/2fa", "summary": "コードを確かめる"}, {"method": "GET", "path": "/auth/2fa/resend"}],
    },
}
PLAIN = {"type": "screen_spec", "version": "1.0", "metadata": {"name": "About", "displayName": "このアプリについて", "description": "d"},
         "structure": {"components": [{"type": "Label", "id": "title"}], "layout": {}}}

STATE_JS = """() => { const sec = document.getElementById('wb-sec-3'); if (!sec) return null;
  const box = sec.querySelector('[data-flow-mmd]'), svg = box && box.querySelector('svg'), wrap = sec.querySelector('.flow-mmd');
  return { diagram: !!box, svg: !!svg, nodes: box ? box.querySelectorAll('g.node').length : 0, theme: box ? box.dataset.theme || null : null,
    text: svg ? svg.textContent.replace(/#mmd-\\d+[^]*?}\\s*(?=[^{}]*$)/, '') : '', scripts: box ? box.querySelectorAll('script').length : 0,
    boxes: sec.querySelectorAll('.flow .fbox').length, vars: (sec.querySelector('.fb-vars') || {}).textContent || '',
    apis: [...sec.querySelectorAll('.flow li.api')].map((x) => x.textContent), svgW: svg ? svg.getBoundingClientRect().width : 0,
    scroll: wrap ? [wrap.scrollWidth, wrap.clientWidth] : null, zoom: (sec.querySelector('[data-flow-zoom]') || {}).textContent || null }; }"""


def check(failures, cond, text):
    if not cond:
        failures.append(f"dataflow-mermaid: {text}")


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def run_dataflow_mermaid(pw, out, failures, jt=None, shots_only=False):
    from run import free_port
    name = "dataflow-mermaid-before" if shots_only else "dataflow-mermaid"
    out = pathlib.Path(out) / name
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    proj = home / "work" / "twofa-app"
    (proj / "docs" / "screens" / "json").mkdir(parents=True, exist_ok=True)
    (proj / "docs" / "screens" / "layouts").mkdir(parents=True, exist_ok=True)
    (proj / "jui.config.json").write_text(json.dumps({"spec_directory": "docs/screens/json", "layouts_directory": "docs/screens/layouts"}))
    (proj / "docs" / "screens" / "json" / "two_factor.spec.json").write_text(json.dumps(TWOFA, ensure_ascii=False))
    (proj / "docs" / "screens" / "json" / "about.spec.json").write_text(json.dumps(PLAIN, ensure_ascii=False))
    jt = pathlib.Path(jt) if jt else pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def hook(**payload):
        body = {"session_id": SID, "cwd": str(proj), "permission_mode": "default", **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(),
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
        watch = Watch(origin=url)
        page = await new_page(browser, watch, name, **DESKTOP)
        asked = []
        page.on("request", lambda r: asked.append(r.url))
        await page.emulate_media(color_scheme="light")
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", label="connected")
        hook(hook_event_name="SessionStart", source="startup")
        await page.click("#spec-filter [data-f='all']")   # the list shows the specs being worked on by default
        await wait(page, "() => document.querySelectorAll('#spec-list .spec-row').length >= 2", timeout=30000, label="the two specs listed")
        await page.click("#spec-list .spec-row:has-text('二要素認証')")
        await wait(page, "() => !document.getElementById('wb').hidden && document.getElementById('wb-sec-3')", label="the whiteboard")

        async def shots(tag):
            for scheme in ("light", "dark"):
                await page.emulate_media(color_scheme=scheme)
                await page.wait_for_timeout(1200)
                await page.evaluate("() => document.getElementById('wb-sec-3').scrollIntoView({ block: 'start' })")
                await page.wait_for_timeout(300)
                await page.screenshot(path=str(out / f"{tag}-dataflow-{scheme}.png"))
            await page.emulate_media(color_scheme="light")

        if shots_only:
            await shots("before")
            return

        await wait(page, "() => { const b = document.querySelector('#wb-sec-3 [data-flow-mmd] svg'); return !!b; }", timeout=30000, label="the diagram")
        st = res["light"] = await page.evaluate(STATE_JS)
        check(failures, st["svg"] and st["nodes"] == 6, f"the spec page's diagram: an svg with its 6 nodes (View, ViewModel, UseCase, Repository, 2 endpoints): {st}")
        check(failures, st["theme"] == "default", f"light: the default theme: {st['theme']}")
        # Mermaid's sanitizer (strict) drops a <script> with what it holds; the rest of the label stays
        check(failures, st["text"].startswith("二要素認証") and "__pwned" not in st["text"] and st["scripts"] == 0,
              f"the <script> in the display name is neither an element nor run (strict drops it), the name stays: {st['text'][:160]} scripts={st['scripts']}")
        check(failures, st["boxes"] >= 3 and "code" in st["vars"] and len(st["apis"]) == 2, f"the boxes stay under it (持つ値, Repository, API): {st}")
        pwned = await page.evaluate("() => window.__pwned === undefined ? null : window.__pwned")
        check(failures, pwned is None, f"nothing ran: {pwned}")
        # at the sheet's text size (0.75 of its own): this flow is still wider than the section, so a scroll bar; 幅に合わせる fits it, and back
        check(failures, st["scroll"][0] > st["scroll"][1] and st["zoom"] == "幅に合わせる",
              f"its own size, a scroll bar: svg {st['svgW']} scroll {st['scroll']} button {st['zoom']}")
        await page.click("#wb-sec-3 [data-flow-zoom]")
        await page.wait_for_timeout(400)
        z = res["fitted"] = await page.evaluate(STATE_JS)
        check(failures, z["svgW"] < st["svgW"] * 0.8 and z["scroll"][0] <= z["scroll"][1] + 1 and z["zoom"] == "実際の大きさ",
              f"幅に合わせる: within the section, no scroll bar: {st['svgW']} -> {z['svgW']} scroll {z['scroll']} button {z['zoom']}")
        await page.click("#wb-sec-3 [data-flow-zoom]")
        await page.wait_for_timeout(300)
        await shots("after")
        await page.emulate_media(color_scheme="dark")
        await wait(page, "() => { const b = document.querySelector('#wb-sec-3 [data-flow-mmd]'); return b && b.dataset.theme === 'dark' && b.querySelector('svg'); }", label="dark diagram")
        res["dark"] = await page.evaluate(STATE_JS)
        await page.emulate_media(color_scheme="light")

        # the spec without a data flow: no diagram
        await page.click("#wb-side-list [data-idx]:has-text('このアプリについて')")
        await page.wait_for_timeout(1500)
        plain = res["plain"] = await page.evaluate(STATE_JS)
        check(failures, plain is None or not plain["diagram"], f"no data flow: no diagram: {plain}")

        res["mermaidAsked"] = [u for u in asked if "mermaid" in u]
        check(failures, res["mermaidAsked"] == [f"{url}/vendor/mermaid-11.17.2/mermaid.min.js"], f"Mermaid read once, from the server: {res['mermaidAsked']}")
        check(failures, not watch.console and not watch.foreign and not watch.csp,
              f"no console error, nothing outside the server: {watch.console[:3]} {watch.foreign[:3]}")
        await page.close()
    except Exception as e:
        failures.append(f"dataflow-mermaid: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        await browser.close()
        srv.terminate()  # our own child (started above)
        try:
            srv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            srv.kill()
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"  {name}: {time.monotonic() - t0:.0f}s", flush=True)
