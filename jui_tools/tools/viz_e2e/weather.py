"""The season and the near weather outside the building, end to end (requester, 10-18).

The real `jui viz serve` in a throwaway HOME on a free port, Open-Meteo replaced by a stand-in on 127.0.0.1
(JUI_VIZ_WEATHER_URL, honoured by the e2e build only). Checked:
- opening the page asks for no position (getCurrentPosition is counted) and requests nothing outside the server;
- the four seasons in light and dark (trees, cicadas, snow on the roof and the plaza, petals and leaves); the
  petals fall, and stand still on a page opened with reduced motion;
- six kinds of weather by day and by night over a season (the page's own forcing hook);
- the switch: with the position granted, the page sends it rounded to two decimals (the frame on the socket is
  read), the server asks the stand-in once with the rounded position, the page shows the answer, and still nothing
  outside the server is requested from the page; off removes the position; a denied position leaves it off.
No console error.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from common import DESKTOP, LAUNCH_ARGS, T, T_pattern, Watch, dump, new_page, ready

ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
LAT, LON = 35.681236, 139.767125
GEO_COUNT = """(() => {
  window.__geoCalls = 0;
  const geo = navigator.geolocation, real = geo && geo.getCurrentPosition.bind(geo);
  if (real) geo.getCurrentPosition = (...a) => { window.__geoCalls += 1; return real(...a); };
})();"""


def check(failures, cond, text):
    if not cond:
        failures.append(f"weather: {text}")


async def wait(page, js, timeout=20000, label=""):
    try:
        await page.wait_for_function(js, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


class Meteo:
    def __init__(self):
        self.queries: list[str] = []
        self.status = 200
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                outer.queries.append(self.path)
                body = json.dumps({"current": {"weather_code": 61, "temperature_2m": 14.2, "is_day": 1, "precipitation": 0.6, "cloud_cover": 96}}).encode()
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass
        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


async def run_weather(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "weather"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    port, meteo = free_port(), Meteo()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1", JUI_VIZ_WEATHER_URL=f"http://127.0.0.1:{meteo.port}/v1/forecast")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port), "--no-agents-poll"],
                           stdout=open(out / "serve.log", "w"), stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    cfg = home / ".local" / "state" / "jui-viz" / "config.json"
    res: dict = {}
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
        forward = jt / "jui_cli" / "viz" / "forward.py"
        for i in range(7):   # seven rooms: the building view needs two floors (six rooms a floor)
            body = {"session_id": f"e2e00000-0000-4000-8000-0000000000e{i}", "cwd": f"/work/weather-app-{i}", "permission_mode": "default",
                    "hook_event_name": "SessionStart", "source": "startup"}
            subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(), capture_output=True,
                           env=dict(base_env, HOME=str(home)), timeout=10)
        watch = Watch(origin=url)
        page = await new_page(browser, watch, "weather", **DESKTOP)
        await page.add_init_script(GEO_COUNT)
        sent: list[str] = []
        page.on("websocket", lambda ws: ws.on("framesent", lambda payload: sent.append(payload if isinstance(payload, str) else "")))
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').dataset.net === 'connected'", label="connected")
        await wait(page, "() => window.__dbg.floors().floors.length >= 2", label="two floors")
        await page.evaluate("() => window.__dbg.tower(true)")
        await page.wait_for_timeout(2500)
        # 1. opened: no position asked, nothing outside, the switch off
        r = res["opened"] = await page.evaluate("""() => ({ geo: window.__geoCalls, shown: !document.getElementById('tower-weather').hidden,
          checked: document.getElementById('weather-switch').getAttribute('aria-checked'), note: document.getElementById('weather-note').textContent,
          outside: window.__dbg.outside() })""")
        check(failures, r["geo"] == 0, f"opening the page asks for no position: {r['geo']} call(s)")
        check(failures, r["shown"] and r["checked"] == "false" and T("scene.weather.off") in r["note"], f"the switch shows, off: {r}")
        check(failures, r["outside"]["weather"] is None, f"no weather while off: {r['outside']}")
        check(failures, meteo.queries == [] and watch.foreign == [], f"nothing asked of anyone while off: {meteo.queries} {watch.foreign}")
        await page.screenshot(path=str(out / "opened.png"))
        # 2. the four seasons, light and dark
        want = {"spring": dict(fall="petal", branches=False, cicadas=0, roofSnow=False),
                "summer": dict(fall=None, branches=False, cicadas=6, roofSnow=False),
                "autumn": dict(fall="leaf", branches=False, cicadas=0, roofSnow=False),
                "winter": dict(fall=None, branches=True, cicadas=0, roofSnow=True)}
        res["seasons"] = {}
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            for season, w in want.items():
                await page.evaluate("(s) => window.__dbg.outside({ season: s })", season)
                await page.wait_for_timeout(600)
                o = await page.evaluate("() => window.__dbg.outside()")
                res["seasons"][f"{season}-{scheme}"] = o
                got = dict(fall=o["fall"]["kind"] if o["fall"] else None, branches=o["branches"], cicadas=o["cicadas"], roofSnow=o["roofSnow"])
                check(failures, got == w and o["built"] == f"{season}:", f"{season} ({scheme}): {got} (built {o['built']})")
                await page.screenshot(path=str(out / f"season-{season}-{scheme}.png"))
        crowns = {k: v["crown"] for k, v in res["seasons"].items() if v["crown"]}
        check(failures, len({crowns.get('spring-light'), crowns.get('summer-light'), crowns.get('autumn-light')}) == 3,
              f"spring, summer and autumn trees differ: {crowns}")
        # reduced motion: the petals stand still; otherwise they fall
        await page.emulate_media(color_scheme="light")
        await page.evaluate("() => window.__dbg.outside({ season: 'spring' })")
        await page.wait_for_timeout(400)
        a = (await page.evaluate("() => window.__dbg.outside()"))["fallY"]
        await page.wait_for_timeout(800)
        b = (await page.evaluate("() => window.__dbg.outside()"))["fallY"]
        check(failures, a != b, f"petals fall: {a} -> {b}")
        # 3. six kinds of weather, day and night, over summer
        res["weathers"] = {}
        expect_fall = {"clear": None, "cloudy": None, "fog": None, "rain": "rain", "snow": "snow", "thunder": "rain"}
        for kind, fall in expect_fall.items():
            for day in (True, False):
                await page.evaluate("([k, d]) => window.__dbg.outside({ season: 'summer', weather: { kind: k, isDay: d } })", [kind, day])
                await page.wait_for_timeout(600)
                o = await page.evaluate("() => window.__dbg.outside()")
                res["weathers"][f"{kind}-{'day' if day else 'night'}"] = o
                ok = ((o["fall"]["kind"] if o["fall"] else None) == fall and o["fog"] == (kind == "fog") and o["roofSnow"] == (kind == "snow")
                      and o["sky"].startswith("night") == (not day) and o["sky"].endswith(f":{kind}"))
                check(failures, ok, f"{kind} {'day' if day else 'night'}: {o}")
                await page.screenshot(path=str(out / f"weather-{kind}-{'day' if day else 'night'}.png"))
        await page.evaluate("() => window.__dbg.outside({ season: null, weather: null })")
        # 4. the switch: granted -> rounded on the socket, one query, the answer shown; nothing outside from the page
        ctx = page.context
        await ctx.grant_permissions(["geolocation"], origin=url)
        await ctx.set_geolocation({"latitude": LAT, "longitude": LON})
        await page.click("#weather-switch")
        await wait(page, f"() => document.getElementById('weather-switch').getAttribute('aria-checked') === 'true' && document.getElementById('weather-note').textContent.includes({json.dumps(T('scene.weather.rain'))})",
                   label="on, with the answer")
        frames = [f for f in sent if '"weather.set"' in f]
        res["frames"] = frames
        on_frames = [json.loads(f) for f in frames if '"on":true' in f.replace(" ", "")]
        check(failures, len(on_frames) == 1 and on_frames[0].get("lat") == 35.68 and on_frames[0].get("lon") == 139.77 and not any("35.681" in f for f in frames),
              f"the page sends the position rounded: {frames}")
        check(failures, len(meteo.queries) == 1 and "latitude=35.68&" in meteo.queries[0] and "35.681" not in meteo.queries[0], f"one query, rounded: {meteo.queries}")
        check(failures, "35.681" not in cfg.read_text() and json.loads(cfg.read_text())["weather"]["lat"] == 35.68, f"stored rounded: {cfg.read_text()}")
        r = res["on"] = await page.evaluate("() => ({ geo: window.__geoCalls, note: document.getElementById('weather-note').textContent, outside: window.__dbg.outside() })")
        check(failures, r["geo"] == 1 and r["outside"]["weather"] == {"kind": "rain", "isDay": True} and r["outside"]["fall"]["kind"] == "rain", f"the weather is drawn: {r}")
        check(failures, watch.foreign == [], f"the page asked nobody outside: {watch.foreign}")
        await page.screenshot(path=str(out / "switch-on.png"))
        # off: the position removed, the switch off
        await page.click("#weather-switch")
        await wait(page, "() => document.getElementById('weather-switch').getAttribute('aria-checked') === 'false'", label="off again")
        check(failures, json.loads(cfg.read_text())["weather"] == {"on": False}, f"off removes the position: {cfg.read_text()}")
        await page.close()
        # 5. denied: stays off, says why, asks nobody
        ctx2 = await browser.new_context(reduced_motion="reduce", **DESKTOP)   # read once when the page loads (10-robot-core.js)
        page2 = await ctx2.new_page()
        watch.attach(page2, "weather-denied")
        await page2.goto(url + "/")
        await ready(page2)
        await wait(page2, "() => document.querySelector('.chip.demo').dataset.net === 'connected'", label="connected (2)")
        await wait(page2, "() => window.__dbg.floors().floors.length >= 2", label="two floors (2)")
        await page2.evaluate("() => window.__dbg.tower(true)")
        await page2.wait_for_timeout(800)
        # reduced motion: the petals stand still
        await page2.evaluate("() => window.__dbg.outside({ season: 'spring' })")
        await page2.wait_for_timeout(400)
        a = (await page2.evaluate("() => window.__dbg.outside()"))["fallY"]
        await page2.wait_for_timeout(800)
        b = (await page2.evaluate("() => window.__dbg.outside()"))["fallY"]
        check(failures, len(a) == 5 and a == b, f"petals still under reduced motion: {a} -> {b}")
        await page2.evaluate("() => window.__dbg.outside({ season: null })")
        await page2.click("#weather-switch")
        await wait(page2, f"() => document.getElementById('weather-note').textContent.includes({json.dumps(T('scene.weather.stays', why=''))})", label="denied")
        r = res["denied"] = await page2.evaluate("() => ({ checked: document.getElementById('weather-switch').getAttribute('aria-checked'), note: document.getElementById('weather-note').textContent })")
        check(failures, r["checked"] == "false" and len(meteo.queries) == 1, f"a denied position leaves it off: {r} {meteo.queries}")
        await page2.screenshot(path=str(out / "denied.png"))
        await ctx2.close()
        for line in watch.console:
            failures.append(f"weather: console: {line}")
        for u in watch.foreign:
            failures.append(f"weather: request outside the server: {u}")
        res["console"] = len(watch.console)
        res["queries"] = meteo.queries
    except Exception as e:
        failures.append(f"weather: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        srv.terminate()  # our own child
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
        meteo.close()
    print(f"  weather/seasons-switch: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "weather-results.json").write_text(dump(res) + "\n")


async def run_weather_few(pw, out, failures):
    """Fewer than seven rooms: no building view, so the switch is the side panel's 設定 (the orchestrator's ruling, 10-18). It turns
    the weather on, the position is asked only inside that click, and the state shows: when it was last read, and
    why it failed (the stand-in answers 500 after an off and on)."""
    from run import free_port
    out = pathlib.Path(out) / "weather-few"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    port, meteo = free_port(), Meteo()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1", JUI_VIZ_WEATHER_URL=f"http://127.0.0.1:{meteo.port}/v1/forecast")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port), "--no-agents-poll"],
                           stdout=open(out / "serve.log", "w"), stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}
    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    t0 = time.monotonic()
    note = "() => document.getElementById('weather-note-panel').textContent"
    try:
        import urllib.request
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        forward = jt / "jui_cli" / "viz" / "forward.py"
        body = {"session_id": "e2e00000-0000-4000-8000-0000000000f1", "cwd": "/work/one-room", "permission_mode": "default",
                "hook_event_name": "SessionStart", "source": "startup"}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(), capture_output=True,
                       env=dict(base_env, HOME=str(home)), timeout=10)
        watch = Watch(origin=url)
        page = await new_page(browser, watch, "weather-few", **DESKTOP)
        await page.add_init_script(GEO_COUNT)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').dataset.net === 'connected'", label="connected")
        await page.wait_for_timeout(1500)
        r = res["opened"] = await page.evaluate("""() => ({ floors: window.__dbg.floors().floors.length, geo: window.__geoCalls,
          tower: !document.getElementById('tower-weather').hidden, panel: !document.getElementById('sec-settings').hidden,
          checked: document.getElementById('weather-switch-panel').getAttribute('aria-checked'), note: document.getElementById('weather-note-panel').textContent })""")
        check(failures, r["floors"] < 2 and not r["tower"], f"few rooms: no building view: {r}")
        check(failures, r["panel"] and r["checked"] == "false" and T("scene.weather.off") in r["note"] and r["geo"] == 0, f"the panel's switch, off, nothing asked: {r}")
        check(failures, meteo.queries == [] and watch.foreign == [], f"nothing outside while off: {meteo.queries} {watch.foreign}")
        await page.locator("#sec-settings").screenshot(path=str(out / "panel-off.png"))
        ctx = page.context
        await ctx.grant_permissions(["geolocation"], origin=url)
        await ctx.set_geolocation({"latitude": LAT, "longitude": LON})
        await page.click("#weather-switch-panel")
        await wait(page, f"() => document.getElementById('weather-switch-panel').getAttribute('aria-checked') === 'true' && new RegExp({json.dumps(T_pattern('scene.weather.at', stale=re.compile('.*?')).pattern)}).test(document.getElementById('weather-note-panel').textContent)",
                   label="on, with the time it was read")
        r = res["on"] = await page.evaluate(f"() => ({{ geo: window.__geoCalls, note: ({note})() }})")
        check(failures, r["geo"] == 1 and T("scene.weather.rain") in r["note"], f"on from the panel, one position asked: {r}")
        check(failures, len(meteo.queries) == 1 and "latitude=35.68&" in meteo.queries[0], f"one query, rounded: {meteo.queries}")
        await page.locator("#sec-settings").screenshot(path=str(out / "panel-on.png"))
        # a failure shows its reason: off, the stand-in breaks, on again
        await page.click("#weather-switch-panel")
        await wait(page, "() => document.getElementById('weather-switch-panel').getAttribute('aria-checked') === 'false'", label="off")
        meteo.status = 500
        await page.click("#weather-switch-panel")
        await wait(page, f"() => [{json.dumps(T_pattern('scene.weather.failed').pattern)}, {json.dumps(T_pattern('scene.weather.none').pattern)}].some((p) => new RegExp(p).test(document.getElementById('weather-note-panel').textContent))", label="the failure's reason")
        r = res["failed"] = await page.evaluate(f"() => ({{ note: ({note})(), checked: document.getElementById('weather-switch-panel').getAttribute('aria-checked') }})")
        check(failures, r["checked"] == "true" and "HTTPError" in r["note"] and "500" in r["note"], f"the failure's reason shows: {r}")
        await page.locator("#sec-settings").screenshot(path=str(out / "panel-failed.png"))
        check(failures, watch.foreign == [], f"the page asked nobody outside: {watch.foreign}")
        await page.close()
        for line in watch.console:
            failures.append(f"weather-few: console: {line}")
        res["queries"] = meteo.queries
    except Exception as e:
        failures.append(f"weather-few: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        srv.terminate()  # our own child
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
        meteo.close()
    print(f"  weather/few-rooms-panel: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "weather-few-results.json").write_text(dump(res) + "\n")
