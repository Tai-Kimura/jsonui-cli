"""One count of the tests a spec needs, everywhere it is shown (ticket 2026-10-23-viz-test-tally-and-worktrees).

The requester saw one spec as 実装・テスト完了 on the whiteboard's head and list and テスト 2/29 on its 分岐 tab: done
counted the test file's cases, the tab the spec's branches. Done is now every case and as many as the branches passed
(requester 10-23: 「分岐も全部で完了」), and the tab, the panel's row and the whiteboard's list count against that one
number (the server's tests.needed).

The real `jui viz serve` in a throwaway HOME on a free port, its saved results folder holding one run (the driver's
shape), one session in a project made here with two specs, each with its Layout (implemented):
- 少ない分岐: 2 cases (both passed) and 3 branches: 2/3 on the tab, the row and the list; not done;
- 多いケース: 5 cases (4 passed) and 3 branches: 4/5 everywhere (the tab said 3/3); not done.
Picture: 多いケース's sheet with the 分岐 tab.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time
from datetime import datetime, timezone

from common import DESKTOP, LAUNCH_ARGS, Watch, new_page, ready

ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
SID = "e2e00000-0000-4000-8000-000000000b01"
RUN = "6f2a1b4c-0d5e-4f60-8a71-92b3c4d5e6f7"
SPECS = {"few": ("少ない分岐", 2, 3, 2), "many": ("多いケース", 5, 3, 4)}   # stem: (name, cases, branches, passed)

ROWS_JS = """() => Object.fromEntries([...document.querySelectorAll('#spec-list .spec-row')].map((b) =>
  [b.querySelector('.nm').textContent.trim(), { status: b.querySelector('.stx').textContent, cls: b.className }]))"""
SHEET_JS = """() => ({ title: document.getElementById('wb-title').textContent,
  tab: (document.querySelector('#wb-nav button[data-sec="6"] small') || {}).textContent || '',
  list: Object.fromEntries([...document.querySelectorAll('#wb-side-list .ws-item:not(.ws-all)')].map((b) =>
    [b.querySelector('.nm').textContent.trim(), b.querySelector('small').textContent])) })"""


def check(failures, cond, text):
    if not cond:
        failures.append(f"test-tally: {text}")


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


def make_project(proj: pathlib.Path, results: pathlib.Path) -> None:
    for d in ("docs/screens/json", "docs/screens/layouts", "tests/screens"):
        (proj / d).mkdir(parents=True, exist_ok=True)
    (proj / "jui.config.json").write_text("{}")
    suites = []
    for stem, (name, cases, branches, passed) in SPECS.items():
        spec = {"type": "screen_spec", "metadata": {"name": stem.title(), "displayName": name, "description": "d",
                                                    "platforms": ["ios"], "layoutFile": stem},
                "branchContracts": {"methods": {"onAppear": {"branches": [{"when": {"k": i}, "then": {"v": i}} for i in range(branches)]}}}}
        (proj / "docs/screens/json" / f"{stem}.spec.json").write_text(json.dumps(spec, ensure_ascii=False))
        (proj / "docs/screens/layouts" / f"{stem}.json").write_text(json.dumps({"type": "View", "id": f"{stem}_root"}))
        names = [f"case_{i}" for i in range(cases)]
        (proj / "tests/screens" / f"{stem}.test.json").write_text(json.dumps(
            {"source": {"layout": f"docs/screens/layouts/{stem}.json"}, "cases": [{"name": n} for n in names]}))
        suites.append({"suiteName": stem, "file": f"screens/{stem}.test.json", "results": [
            {"testName": stem, "caseName": n, "status": "passed" if i < passed else "skipped", "durationMs": 1}
            for i, n in enumerate(names)]})
    app = results / "ios" / "dev.app.UITests.xctrunner"
    app.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%f")[:-3]
    (app / f"{stamp}Z-{RUN}.json").write_text(json.dumps(
        {"format": "jsonui-test-results", "version": 1, "platform": "ios", "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "run": RUN, "app": "dev.app.UITests.xctrunner", "suites": suites}))


async def run_test_tally(pw, out, failures, jt=None, shots_only=False):
    from run import free_port
    name = "test-tally-before" if shots_only else "test-tally"
    out = pathlib.Path(out) / name
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    proj = home / "work" / "tally-app"
    make_project(proj, home / ".local" / "state" / "jsonui-test" / "results")
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
        await page.emulate_media(color_scheme="light")
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').dataset.net === 'connected'", label="connected")
        hook(hook_event_name="SessionStart", source="startup")
        await page.click("#spec-filter [data-f='all']")
        await wait(page, "() => [...document.querySelectorAll('#spec-list .spec-row')].filter((b) => b.classList.contains('b-done') || /\\d+\\/\\d+/.test(b.querySelector('.stx').textContent)).length >= 2",
                   timeout=30000, label="both specs with their results")
        await page.wait_for_timeout(500)
        rows = res["rows"] = await page.evaluate(ROWS_JS)
        await page.click("#spec-list .spec-row:has-text('多いケース')")
        await wait(page, "() => { const c = document.getElementById('wb-close'); return !!(c && c.offsetParent) && document.getElementById('wb-title').textContent === '多いケース'; }",
                   timeout=20000, label="多いケース's sheet shown")
        await page.wait_for_timeout(900)
        await page.screenshot(path=str(out / (("before" if shots_only else "after") + "-sheet.png")))
        if shots_only:
            return
        many = res["many"] = await page.evaluate(SHEET_JS)
        await page.click("#wb-side-list [data-idx]:has-text('少ない分岐')")
        await wait(page, "() => document.getElementById('wb-title').textContent === '少ない分岐'", timeout=20000, label="少ない分岐's sheet")
        await page.wait_for_timeout(500)
        few = res["few"] = await page.evaluate(SHEET_JS)
        for stem, sheet in (("few", few), ("many", many)):
            nm, cases, branches, passed = SPECS[stem]
            want = f"{passed}/{max(cases, branches)}"
            check(failures, want in sheet["tab"], f"{nm}: the 分岐 tab says {want}: {sheet['tab']!r}")
            check(failures, want in rows.get(nm, {}).get("status", ""), f"{nm}: the panel's row says {want}: {rows.get(nm)}")
            check(failures, want in sheet["list"].get(nm, ""), f"{nm}: the whiteboard's list says {want}: {sheet['list']}")
            check(failures, "b-done" not in rows.get(nm, {}).get("cls", "b-done"), f"{nm}: not done ({want}): {rows.get(nm)}")
        check(failures, not watch.console and not watch.foreign and not watch.csp,
              f"no console error, nothing outside the server: {watch.console[:3]} {watch.foreign[:3]}")
        await page.close()
    except Exception as e:
        failures.append(f"test-tally: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        await browser.close()
        srv.terminate()  # our own child (started above)
        try:
            srv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            srv.kill()
        log.close()
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"  {name}: {time.monotonic() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    import argparse
    import asyncio

    from playwright.async_api import async_playwright

    import e2e_lock

    ap = argparse.ArgumentParser(description="the sheet's picture from another checkout (the before picture)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--jt", required=True, help="that checkout's jui_tools")
    ap.add_argument("--shots-only", action="store_true")
    a = ap.parse_args()
    e2e_lock.hold(only=["test-tally"])
    fails: list = []

    async def go():
        async with async_playwright() as pw:
            await run_test_tally(pw, a.out, fails, jt=a.jt, shots_only=a.shots_only)

    asyncio.run(go())
    for f in fails:
        print("FAIL", f)
    print("ok" if not fails else f"{len(fails)} failure(s)")
    sys.exit(1 if fails else 0)
