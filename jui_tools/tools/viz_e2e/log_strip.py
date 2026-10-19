"""The log strip can be closed (requester, 10-19): 「閉じる」 beside 「ログを全画面で見る」; closed, the scene and the panel
reach the bottom of the view and only 「ログを開く」 floats at the bottom right.

The real `jui viz serve` in a throwaway HOME on a free port, a session through the real forward.py. At 1440 px: closing
takes the strip away and the scene's and the panel's bottoms reach the view's; 「ログを開く」 is what a press at its
centre hits (elementFromPoint) and crosses no button, card, row or hint; an event that comes while it is closed is in
the strip once it opens; a reload keeps it closed (and open); with storage that throws, it still closes and opens. At
390 px the page scrolls, so 「ログを開く」 is a row of its own after the page and crosses nothing. Light and dark
pictures (`--jt` takes the before ones from another tree).
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, new_page, ready

CWD = "/work/strip-app"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
SID = "e2e00000-0000-4000-8000-0000000004{:02x}"
PHONE = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 1}

LAYOUT_JS = """() => { const r = (sel) => { const e = document.querySelector(sel); if (!e) return null; const b = e.getBoundingClientRect();
    return { x0: b.left, x1: b.right, y0: b.top, y1: b.bottom, shown: !!(e.offsetWidth || e.offsetHeight) && getComputedStyle(e).display !== 'none' }; };
  return { vh: window.innerHeight, scene: r('.scene'), side: r('.side'), strip: r('#ticker-strip'), open: r('#btn-strip-open'),
    closed: document.querySelector('.app').classList.contains('log-closed'),
    closeExpanded: document.getElementById('btn-strip-close').getAttribute('aria-expanded'), openExpanded: document.getElementById('btn-strip-open').getAttribute('aria-expanded') }; }"""
# What 「ログを開く」 covers: the element a press at its centre hits, and every visible button, card, row, text or hint it
# crosses where that element is the one seen (something scrolled under the panel's opaque foot is not seen there).
COVER_JS = """(id) => { const o = document.getElementById(id || 'btn-strip-open'); const b = o.getBoundingClientRect();
  const hit = document.elementFromPoint((b.left + b.right) / 2, (b.top + b.bottom) / 2);
  const crossed = [...document.querySelectorAll('button, a, input, select, li, p, .spec-row, .task, .scene-hint, .chip, .floor-nav, h2')]
    .filter((e) => e !== o && !o.contains(e) && !e.contains(o) && (e.offsetWidth || e.offsetHeight) && getComputedStyle(e).visibility !== 'hidden')
    .map((e) => [e, e.getBoundingClientRect()]).filter(([e, r]) => r.left < b.right && b.left < r.right && r.top < b.bottom && b.top < r.bottom)
    // seen where it crosses: a press at the middle of the crossing hits that element (not the foot's band over it)
    // seen where it crosses: the first thing under the button there (the button's own parts skipped, the panel's opaque
    // foot band counted as covering) is that element; text that scrolls under the band is not seen there
    .filter(([e, r]) => { const x = (Math.max(r.left, b.left) + Math.min(r.right, b.right)) / 2, y = (Math.max(r.top, b.top) + Math.min(r.bottom, b.bottom)) / 2;
      const at = document.elementsFromPoint(x, y).find((q) => q !== o && !o.contains(q)); return !!at && (at === e || e.contains(at)); })
    .map(([e]) => (e.id ? '#' + e.id : e.tagName.toLowerCase() + '.' + [...e.classList].join('.')));
  return { hitIsIt: hit === o || o.contains(hit), crossed }; }"""


def check(failures, cond, text):
    if not cond:
        failures.append(f"log-strip: {text}")


async def wait(page, js, timeout=20000, label=""):
    try:
        await page.wait_for_function(js, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def run_log_strip(pw, out, failures, jt=None, shots_only=False):
    from run import free_port
    name = "log-strip-before" if shots_only else "log-strip"
    out = pathlib.Path(out) / name
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(jt) if jt else pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}
    n = {"i": 0}

    def hook(**payload):
        body = {"session_id": SID.format(0), "cwd": CWD, "permission_mode": "default", **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(),
                       capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)

    def read(path):
        n["i"] += 1
        hook(hook_event_name="PreToolUse", tool_name="Read", tool_use_id=f"r{n['i']}", tool_input={"file_path": f"/work/strip-app/{path}"})

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
        ctx = await browser.new_context(**DESKTOP)
        page = await ctx.new_page()
        watch.attach(page, name)
        await page.emulate_media(color_scheme="light")
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", label="connected")
        hook(hook_event_name="SessionStart", source="startup")
        read("first.json")
        await wait(page, "() => document.getElementById('ticker').textContent.includes('first.json')", label="an event in the strip")

        if shots_only:
            for scheme in ("light", "dark"):
                await page.emulate_media(color_scheme=scheme)
                await page.wait_for_timeout(600)
                await page.screenshot(path=str(out / f"before-1440-{scheme}.png"))
            return

        # a fresh page with nothing stored: the strip is open (the default), checked before any button is touched
        stored = res["storedAtFirst"] = await page.evaluate("() => localStorage.getItem('agent-view:logStrip')")
        before = res["open"] = await page.evaluate(LAYOUT_JS)
        check(failures, stored is None and before["strip"]["shown"] and not before["closed"] and before["open"]["shown"] is False,
              f"a fresh page, nothing stored: the strip is open and 「ログを開く」 is not shown: stored {stored!r} {before}")
        for scheme in ("light", "dark"):   # the strip open with its new button, for the pictures
            await page.emulate_media(color_scheme=scheme)
            await page.wait_for_timeout(500)
            await page.screenshot(path=str(out / f"after-open-1440-{scheme}.png"))
        await page.emulate_media(color_scheme="light")
        await page.click("#btn-strip-close")
        await page.wait_for_timeout(500)
        closed = res["closed"] = await page.evaluate(LAYOUT_JS)
        check(failures, closed["closed"] and not closed["strip"]["shown"] and closed["open"]["shown"], f"closed: the strip goes, 「ログを開く」 shows: {closed}")
        check(failures, abs(closed["scene"]["y1"] - closed["vh"]) <= 1 and abs(closed["side"]["y1"] - closed["vh"]) <= 1,
              f"the scene and the panel reach the bottom of the view: scene {closed['scene']['y1']} side {closed['side']['y1']} view {closed['vh']}")
        check(failures, closed["scene"]["y1"] - before["scene"]["y1"] >= before["strip"]["y1"] - before["strip"]["y0"] - 1,
              f"they grew by the strip's height: {before['scene']['y1']} -> {closed['scene']['y1']} (strip {before['strip']['y1'] - before['strip']['y0']})")
        check(failures, closed["closeExpanded"] == "false" and closed["openExpanded"] == "false", f"aria-expanded says closed: {closed}")
        cover = res["cover1440"] = await page.evaluate(COVER_JS)
        check(failures, cover["hitIsIt"] and not cover["crossed"], f"「ログを開く」 is pressed where it is and crosses nothing: {cover}")
        focused = await page.evaluate("() => document.activeElement && document.activeElement.id")
        check(failures, focused == "btn-strip-open", f"the focus moves to 「ログを開く」: {focused}")
        # the panel closed too: 「ログを開く」 floats over the scene's corner, clear of its hint
        await page.click("#btn-side")
        await page.wait_for_timeout(500)
        fl = res["float"] = await page.evaluate("""() => { const f = document.getElementById('btn-strip-open-float'), b = f.getBoundingClientRect(), sc = document.querySelector('.scene').getBoundingClientRect();
          return { shown: !!f.offsetWidth, foot: !document.getElementById('side-foot').hidden, side: !!document.querySelector('.side').offsetWidth, y1: b.bottom, x1: b.right, vw: innerWidth, vh: innerHeight, scene: [sc.right, sc.bottom] }; }""")
        check(failures, not fl["side"] and fl["scene"][0] >= fl["vw"] - 1 and fl["scene"][1] >= fl["vh"] - 1, f"panel closed: the panel is gone and the scene fills the view: {fl}")
        cover = res["coverFloat"] = await page.evaluate(COVER_JS, "btn-strip-open-float")
        check(failures, fl["shown"] and not fl["foot"] and fl["vh"] - fl["y1"] < 40 and fl["vw"] - fl["x1"] < 40, f"panel closed: it floats at the bottom right: {fl}")
        check(failures, cover["hitIsIt"] and not cover["crossed"], f"panel closed: the floating one crosses nothing: {cover}")
        await page.screenshot(path=str(out / "after-closed-nopanel-1440-light.png"))
        await page.click("#btn-side")
        await page.wait_for_timeout(500)
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await page.wait_for_timeout(500)
            await page.screenshot(path=str(out / f"after-closed-1440-{scheme}.png"))
        await page.emulate_media(color_scheme="light")
        # closed, events still come; a reload keeps it closed
        read("while-closed.json")
        await page.wait_for_timeout(1500)
        await page.reload()
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", label="connected again")
        again = res["reloadClosed"] = await page.evaluate(LAYOUT_JS)
        check(failures, again["closed"] and again["open"]["shown"], f"a reload keeps it closed: {again}")
        read("after-reload.json")
        await page.wait_for_timeout(1500)
        await page.keyboard.press("Tab")   # keyboard: it can be reached and pressed
        await page.focus("#btn-strip-open")
        await page.keyboard.press("Enter")
        await wait(page, "() => !document.querySelector('.app').classList.contains('log-closed')", label="opened by the keyboard")
        text = await page.evaluate("() => document.getElementById('ticker').textContent")
        check(failures, "after-reload.json" in text, f"what came while closed is in the strip once open: {text[:200]}")
        opened = res["reopened"] = await page.evaluate(LAYOUT_JS)
        check(failures, opened["strip"]["shown"] and abs(opened["scene"]["y1"] - before["scene"]["y1"]) <= 1 and not opened["open"]["shown"], f"open again: as before: {opened}")
        await page.reload()
        await ready(page)
        kept = await page.evaluate(LAYOUT_JS)
        check(failures, not kept["closed"], f"a reload keeps it open too: {kept}")
        # storage that throws: it still closes and opens
        await page.close()
        bad = await ctx.new_page()
        watch.attach(bad, name + "-nostorage")
        await bad.add_init_script("Object.defineProperty(window, 'localStorage', { get() { throw new Error('blocked'); } });")
        await bad.goto(url + "/")
        await ready(bad)
        first = res["noStorageFirst"] = await bad.evaluate(LAYOUT_JS)
        check(failures, first["strip"]["shown"] and not first["closed"], f"storage blocked: open at first: {first}")
        await bad.click("#btn-strip-close")
        await bad.wait_for_timeout(300)
        nb = res["noStorage"] = await bad.evaluate(LAYOUT_JS)
        check(failures, nb["closed"] and nb["open"]["shown"], f"storage blocked: still closes: {nb}")
        await bad.click("#btn-strip-open")
        await bad.wait_for_timeout(300)
        check(failures, not (await bad.evaluate(LAYOUT_JS))["closed"], "storage blocked: still opens")
        await bad.close()
        # 390 px
        phone = await new_page(browser, watch, name + "-phone", **PHONE)
        for scheme in ("light", "dark"):
            await phone.emulate_media(color_scheme=scheme)
            await phone.goto(url + "/")
            await ready(phone)
            if scheme == "light":
                await phone.click("#btn-strip-close")
            await phone.wait_for_timeout(500)
            await phone.evaluate("() => document.getElementById('btn-strip-open').scrollIntoView({ block: 'center' })")
            await phone.wait_for_timeout(300)
            p = res[f"phone-{scheme}"] = await phone.evaluate(LAYOUT_JS)
            cover = res[f"cover390-{scheme}"] = await phone.evaluate(COVER_JS)
            check(failures, p["closed"] and p["open"]["shown"] and not p["strip"]["shown"], f"390 {scheme}: closed: {p}")
            check(failures, cover["hitIsIt"] and not cover["crossed"], f"390 {scheme}: 「ログを開く」 crosses nothing: {cover}")
            check(failures, p["open"]["x1"] <= 390 and p["open"]["x0"] >= 0, f"390 {scheme}: inside the width: {p['open']}")
            await phone.screenshot(path=str(out / f"after-closed-390-{scheme}.png"))
        await phone.click("#btn-strip-open")
        await phone.wait_for_timeout(300)
        check(failures, not (await phone.evaluate(LAYOUT_JS))["closed"], "390: opens")
        await phone.close()
        check(failures, not watch.console and not watch.foreign and not watch.csp, f"no console error, nothing outside the server: {watch.console[:3]} {watch.foreign[:3]}")
    except Exception as e:   # a step that cannot run (a button not there, a wait that ran out) is a FAIL line, not a stop
        failures.append(f"log-strip: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        await browser.close()
        srv.terminate()  # our own child (started above)
        try:
            srv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            srv.kill()
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"  {name}: {time.monotonic() - t0:.0f}s", flush=True)
