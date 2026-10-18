"""The usage limits in the header, end to end (requester, 10-18).

The real `jui viz serve` in a throwaway HOME on a free port, fed by the real statusline.py with made-up status JSON
(Claude Code 2.1.302's shape). Before any value: 上限の値なし. Then 0 / 50 / 99 %: the hue of the number falls as the
share grows (interpolated, not steps), and the number and the % have one colour. 100 % (and 120, capped): no number and
no %, 上限到達 in the inactive colour, the time to the reset still there. The time counts down; a value 20 minutes old
says 20分前の値. Light and dark. No console error, nothing requested outside the server.
"""

from __future__ import annotations

import colorsys
import json
import os
import pathlib
import re
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, new_page, ready

ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")


def check(failures, cond, text):
    if not cond:
        failures.append(f"usage: {text}")


async def wait(page, js, timeout=20000, label=""):
    try:
        await page.wait_for_function(js, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


def _lum(rgb):
    def c(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (c(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(css: str, bg_hex: str) -> float:
    """WCAG contrast of an rgb() colour against a #rrggbb background, computed here (not by the page)."""
    fg = [int(x) for x in re.findall(r"\d+", css)[:3]]
    bg = [int(bg_hex.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    a, b = _lum(fg), _lum(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def hue(css: str) -> float:
    r, g, b = (int(x) / 255 for x in re.findall(r"\d+", css)[:3])
    return colorsys.rgb_to_hls(r, g, b)[0] * 360


async def run_usage(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "usage"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    script = jt / "jui_cli" / "viz" / "statusline.py"
    port = free_port()
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}
    now = int(time.time())

    def feed(five, week, five_reset=now + 2 * 3600 + 13 * 60, week_reset=now + 4 * 86400 + 6 * 3600 + 30):
        limits = {}
        if five is not None:
            limits["five_hour"] = {"used_percentage": five, "resets_at": five_reset}
        if week is not None:
            limits["seven_day"] = {"used_percentage": week, "resets_at": week_reset}
        body = json.dumps({"model": {"display_name": "Opus"}, "rate_limits": limits}).encode()
        subprocess.run([sys.executable, "-I", "-S", str(script)], input=body, capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)

    usage = "() => window.__dbg.usage()"
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
        page = await new_page(browser, watch, "usage", **DESKTOP)
        await page.emulate_media(color_scheme="light")
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", label="connected")
        await wait(page, "() => window.__dbg.usage().length === 1", label="the chip")
        r = res["none"] = await page.evaluate(usage)
        check(failures, r[0]["text"] == "上限の値なし" and r[0]["window"] is None, f"no value yet: {r}")
        check(failures, "VS Code 拡張とデスクトップアプリからは届きません" in r[0]["title"], f"where the value comes from: {r[0]['title']}")
        ink = await page.evaluate("() => window.__dbg.inkSoft()")

        hues = {}
        for pct in (0, 50, 99):
            feed(pct, 18)
            await wait(page, f"() => (window.__dbg.usage()[0] || {{}}).text.startsWith('5時間 {pct}%')", label=f"{pct}%")
            r = await page.evaluate(usage)
            five = r[0]
            check(failures, five["num"] and five["num"] == five["pc"], f"{pct}%: the number and the % share one colour: {five}")
            hues[pct] = hue(five["num"])
            check(failures, not five["limit"] and "（あと 2:1" in five["text"], f"{pct}%: the time to the reset: {five}")
        res["hues"] = hues
        check(failures, hues[0] > hues[50] > hues[99] and 100 < hues[0] <= 125 and hues[99] < 8 and 45 < hues[50] < 75,
              f"the hue falls with the share, green to red, in between not a step: {hues}")
        # contrast (reviewed 10-18): every share 0-99, light and dark, at least 4.5 against the chip (12 px bold: AA)
        async def contrast_sweep(scheme):
            await page.emulate_media(color_scheme=scheme)
            await page.wait_for_timeout(300)
            bg = await page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--chip').trim()")
            cols = await page.evaluate("() => Array.from({ length: 100 }, (_, p) => window.__dbg.usageColor(p))")
            ratios = [contrast(c, bg) for c in cols]
            hs = [hue(c) for c in cols]
            return {"bg": bg, "min": round(min(ratios), 2), "at": ratios.index(min(ratios)), "hues": [round(h) for h in hs[::11]],
                    "falls": all(hs[i] >= hs[i + 1] - 0.5 for i in range(99))}
        for scheme in ("light", "dark"):
            c = res[f"contrast-{scheme}"] = await contrast_sweep(scheme)
            check(failures, c["min"] >= 4.5, f"{scheme}: every share 0-99 at 4.5:1 or more: lowest {c['min']} at {c['at']}%")
            check(failures, c["falls"] and c["hues"][0] > 100 and c["hues"][-1] < 10, f"{scheme}: still green to red, continuously: {c['hues']}")
        await page.emulate_media(color_scheme="light")
        await wait(page, "() => window.__dbg.usage()[0].num === window.__dbg.usageColor(99)", label="the chip repainted for light")
        shown = await page.evaluate("() => [window.__dbg.usage()[0].num, window.__dbg.usageColor(99)]")
        check(failures, shown[0] == shown[1], f"the chip shows the colour the sweep measured: {shown}")
        r = res["week"] = await page.evaluate(usage)
        check(failures, r[1]["window"] == "sevenDay" and r[1]["text"].startswith("週 18%") and "あと 4日 6時間" in r[1]["text"], f"the week: {r}")
        await page.screenshot(path=str(out / "header-light.png"), clip={"x": 0, "y": 0, "width": 1440, "height": 60})
        for pct in (100, 120):
            feed(pct, 18)
            await wait(page, "() => window.__dbg.usage()[0].limit", label=f"{pct}%: limit")
            five = (await page.evaluate(usage))[0]
            res[f"limit{pct}"] = five
            check(failures, five["num"] is None and five["pc"] is None and "100" not in five["text"] and five["text"].startswith("5時間 上限到達"),
                  f"{pct}%: 上限到達 in place of the number: {five}")
            check(failures, five["limitColor"] == ink and "（あと 2:1" in five["text"], f"{pct}%: inactive colour, the reset still shown: {five} vs {ink}")
        await page.screenshot(path=str(out / "header-limit-light.png"), clip={"x": 0, "y": 0, "width": 1440, "height": 60})
        # 99.7 right after the limit (so the wait cannot pass on an older 99): floored, a number, not the limit
        feed(99.7, 18)
        await wait(page, "() => !window.__dbg.usage()[0].limit", label="99.7% arrived")
        five = res["99.7"] = (await page.evaluate(usage))[0]
        check(failures, five["text"].startswith("5時間 99%") and five["num"], f"99.7%: 99%, not 100 and not the limit: {five}")
        # the time counts down; an old value says how old
        feed(42, 18)
        await wait(page, "() => window.__dbg.usage()[0].text.startsWith('5時間 42%')", label="42%")
        later = await page.evaluate("() => { window.__dbg.setClock(Date.now() + 20 * 60 * 1000); return new Promise((ok) => setTimeout(() => ok(window.__dbg.usage()), 1500)); }")
        res["later"] = later
        check(failures, "あと 1:5" in later[0]["text"] and later[0]["note"] == " · 20分前の値" and later[1]["note"] == " · 20分前の値",
              f"20 minutes on: the time counts down and the value says its age: {later}")
        await page.evaluate("() => window.__dbg.setClock(null)")
        await wait(page, "() => window.__dbg.usage()[0].note === ''", label="fresh again")
        # past a window's reset with no newer value: no share (it is not this window's any more)
        feed(42, 18, five_reset=int(time.time()) + 60)
        await wait(page, "() => window.__dbg.usage()[0].text.startsWith('5時間 42%')", label="42%, resets in a minute")
        gone = res["reset"] = await page.evaluate("() => { window.__dbg.setClock(Date.now() + 3 * 60 * 1000); return new Promise((ok) => setTimeout(() => ok(window.__dbg.usage()), 1500)); }")
        check(failures, gone[0]["text"].startswith("5時間 リセット済み") and gone[0]["num"] is None and "あと" not in gone[0]["text"] and "42" not in gone[0]["text"],
              f"past the reset: リセット済み, no old share: {gone[0]}")
        await page.evaluate("() => window.__dbg.setClock(null)")
        feed(42, 18)
        await wait(page, "() => window.__dbg.usage()[0].text.startsWith('5時間 42%')", label="42% again")
        await page.emulate_media(color_scheme="dark")
        await page.wait_for_timeout(1500)
        dark = res["dark"] = await page.evaluate(usage)
        check(failures, dark[0]["num"] == dark[0]["pc"] and 50 < hue(dark[0]["num"]) < 90, f"dark: the same hue rule: {dark}")
        await page.screenshot(path=str(out / "header-dark.png"), clip={"x": 0, "y": 0, "width": 1440, "height": 60})
        check(failures, not watch.console and not watch.foreign and not watch.csp, f"no console error, nothing outside the server: {watch.console[:3]} {watch.foreign[:3]}")
        await page.close()
    finally:
        await browser.close()
        srv.terminate()  # our own child (started above)
        try:
            srv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            srv.kill()
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"  usage/header: {time.monotonic() - t0:.0f}s hues {res.get('hues')}", flush=True)
