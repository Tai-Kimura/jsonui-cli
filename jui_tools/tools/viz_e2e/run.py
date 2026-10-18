"""Browser tests for `jui viz` (plan 10 §6). Outside pytest: they need Playwright and a Chromium.

    python tools/viz_e2e/run.py --out /tmp/viz-e2e                 # demo + live against fake_server.py
    python tools/viz_e2e/run.py --out /tmp/viz-e2e --only demo
    python tools/viz_e2e/run.py --out /tmp/x --record-demo URL     # record expect_demo.json from the prototype

Demo: every suite in demo.py, whose results must equal expect_demo.json (recorded from the prototype page, so a
difference means the port stopped behaving like the prototype). Live: live.py against fake_server.py and its
scenarios (scenarios/*.jsonl). Rooms (rooms.py): doors, desks and the one-room view on the real server (`--only rooms` runs it alone).
Both: no console errors, no request to anywhere but the server, no CSP violation.

Exit status 0 only when every check passed; each failed check is printed on its own line with FAIL.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import socket
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from playwright.async_api import async_playwright  # noqa: E402

import demo  # noqa: E402
from common import ISOLATE, LAUNCH_ARGS, Watch, dump, progress_count, progress_grew  # noqa: E402

EXPECT_DEMO = HERE / "expect_demo.json"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    """fake_server.py in a child process (stand-in for `jui viz serve`; see its PROTOCOL table)."""

    def __init__(self, scenario: pathlib.Path | None = None, token: str | None = None, port: int | None = None):
        self.port, self.scenario, self.token = port or free_port(), scenario, token
        self.url = f"http://127.0.0.1:{self.port}"
        self.start()

    def start(self):
        cmd = [sys.executable, str(HERE / "fake_server.py"), "--port", str(self.port), "--e2e"]
        if self.scenario:
            cmd += ["--scenario", str(self.scenario)]
        if self.token:
            cmd += ["--token", self.token]
        for attempt in range(20):   # the port may still be held for a moment after a stop
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            line = self.proc.stdout.readline()
            if line.startswith("READY"):
                return
            self.proc.wait()
            time.sleep(0.25)
        raise RuntimeError(f"fake_server did not start: {line}{self.proc.stdout.read()}")

    def restart(self):
        """Stop and start on the same port: a new token (unless fixed) and the scenario from its start."""
        self.stop()
        self.start()

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()  # our own child (started above)
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


class RealServer:
    """`jui viz serve --replay FILE` from this checkout, in a throwaway HOME, with the e2e hook (JUI_VIZ_E2E=1).

    JUI_VIZ_E2E_SERVE overrides the command (default: `<python> <jui_tools>/bin/jui`)."""

    def __init__(self, replay: pathlib.Path, home: pathlib.Path, speed: float = 1.0):
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        home.mkdir(parents=True, exist_ok=True)
        self.home, self.replay, self.speed = home, replay, speed
        self.log = open(home / "serve.log", "w")
        self._start()

    def _start(self):
        base = os.environ.get("JUI_VIZ_E2E_SERVE", "").split() or [sys.executable, str(HERE.parents[1] / "bin" / "jui")]
        env = dict({k: v for k, v in os.environ.items() if k not in ISOLATE}, HOME=str(self.home), JUI_VIZ_E2E="1")
        self.proc = subprocess.Popen(base + ["viz", "serve", "--port", str(self.port), "--replay", str(self.replay), "--speed", str(self.speed)],
                                     stdout=self.log, stderr=subprocess.STDOUT, env=env)
        import urllib.request
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{self.url}/health", timeout=1).read()
                return
            except OSError:
                if self.proc.poll() is not None:
                    break
                time.sleep(0.1)
        self.stop()
        raise RuntimeError(f"jui viz serve did not start: {(self.home / 'serve.log').read_text()[-500:]}")

    def _end(self):
        if self.proc.poll() is None:
            self.proc.terminate()  # our own child
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def restart(self):
        """Stop the server and start it again on the same port: a new process, so a new token."""
        self._end()
        self._start()

    def token(self) -> str:
        import re
        import urllib.request
        html = urllib.request.urlopen(f"{self.url}/", timeout=2).read().decode()
        m = re.search(r'<meta name="jui-viz-token" content="([^"]*)">', html)
        return m.group(1) if m else ""

    def stop(self):
        self._end()
        self.log.close()


def diff(a, b, path="") -> list[str]:
    """Readable differences between two JSON-like values."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append(f"{path}/{k}: only in actual: {json.dumps(b[k], ensure_ascii=False)[:200]}")
            elif k not in b:
                out.append(f"{path}/{k}: missing (expected {json.dumps(a[k], ensure_ascii=False)[:200]})")
            else:
                out += diff(a[k], b[k], f"{path}/{k}")
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff(x, y, f"{path}[{i}]")
        return out
    return [] if a == b else [f"{path}: expected {json.dumps(a, ensure_ascii=False)[:300]} got {json.dumps(b, ensure_ascii=False)[:300]}"]


async def run_demo(pw, url, out, suites, record_google_fonts=None):
    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    origin = url.split("/", 3)
    watch = Watch(origin=f"{origin[0]}//{origin[2]}")
    if record_google_fonts:
        ctx_route = record_google_fonts
        orig_new_page = browser.new_page

        async def new_page_with_fonts(**opts):
            page = await orig_new_page(**opts)
            css = "".join(f'@font-face {{ font-family: "JetBrains Mono"; font-weight: {w}; font-display: swap; '
                          f'src: url("{ctx_route}/fonts/JetBrainsMono-{n}.woff2") format("woff2"); }}\n'
                          for w, n in ((500, "Medium"), (700, "Bold")))
            await page.route("https://fonts.googleapis.com/**",
                             lambda r: r.fulfill(status=200, content_type="text/css", body=css))
            await page.route("https://fonts.gstatic.com/**", lambda r: r.abort())
            return page
        browser.new_page = new_page_with_fonts
    results = {}
    for name in suites:
        d = pathlib.Path(out) / "demo" / name
        d.mkdir(parents=True, exist_ok=True)
        t0 = time.monotonic()
        results[name] = await demo.SUITES[name](browser, url, watch, str(d))
        print(f"  demo/{name}: {time.monotonic() - t0:.0f}s", flush=True)
    await browser.close()
    return results, watch


def check_watch(watch: Watch, label: str, failures: list, allow_foreign=False):
    for line in watch.console:
        failures.append(f"{label}: console: {line}")
    if not allow_foreign:
        for u in watch.foreign:
            failures.append(f"{label}: request outside the server: {u}")
    for c in watch.csp:
        failures.append(f"{label}: CSP violation: {c}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="jui viz browser tests")
    ap.add_argument("--out", required=True, help="where screenshots and results go")
    ap.add_argument("--only", choices=["demo", "live", "rooms", "ask", "history", "robot-tests", "rb-layout", "rb-arrows", "focus-cam", "tower", "calls", "play", "props", "weather", "usage"],
                    help="run one half (rooms: only the rooms/doors suite; ask: only the question card suite; history: only the 応答の履歴 tab; robot-tests: only a robot card's test runs; calls: only the phone calls; play: only idle robots playing; weather: only the season and the near weather outside; "
                         "tower: only the building's window press)")
    ap.add_argument("--suite", action="append", help="demo suite(s) to run (default: all)")
    ap.add_argument("--record-demo", metavar="URL",
                    help="run the demo suites against URL (the prototype's agent-test.html) and write expect_demo.json")
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    suites = a.suite or list(demo.SUITES)

    async def go():
        async with async_playwright() as pw:
            if a.record_demo:
                base = a.record_demo.rsplit("/", 1)[0]
                res, watch = await run_demo(pw, a.record_demo, out, suites, record_google_fonts=base)
                prev = json.loads(EXPECT_DEMO.read_text()) if EXPECT_DEMO.exists() else {}
                prev.update(res)
                EXPECT_DEMO.write_text(dump(prev) + "\n")
                (out / "record-console.txt").write_text("\n".join(watch.console))
                print(f"recorded {', '.join(res)} into {EXPECT_DEMO.name}; console lines: {len(watch.console)}")
                return
            if a.only in (None, "demo"):
                srv = Server()
                try:
                    res, watch = await run_demo(pw, f"{srv.url}/?demo=1", out, suites)
                finally:
                    srv.stop()
                (out / "demo-results.json").write_text(dump(res) + "\n")
                expect = json.loads(EXPECT_DEMO.read_text())
                for name in suites:
                    for line in diff(expect.get(name), res.get(name), f"demo/{name}"):
                        failures.append(line)
                check_watch(watch, "demo", failures)
                for key in ("shots", "perm", "scope", "phone"):
                    r = res.get(key) or {}
                    for k, v in r.items():
                        if isinstance(v, dict) and isinstance(v.get("sw"), int) and v["sw"] > 390:
                            failures.append(f"demo/{key}/{k}: horizontal scroll at 390 px (scrollWidth {v['sw']})")
            if a.only in (None, "live"):
                import live
                await live.run(pw, out, failures, Server)
                await live.run_real(pw, out, failures, RealServer)
                await live.run_real_decide(pw, out, failures)
            if a.only in (None, "live", "ask"):
                import ask
                await ask.run_ask(pw, out, failures)
            if a.only in (None, "live", "history"):
                import history
                before = progress_count()
                await history.run_history(pw, out, failures)
                failures.extend(m for m in [progress_grew("history", before)] if m)
            if a.only in (None, "live", "rb-layout"):
                import rb_layout
                before = progress_count()
                await rb_layout.run_rb_layout(pw, out, failures)
                failures.extend(m for m in [progress_grew("rb-layout", before)] if m)
            if a.only in (None, "live", "focus-cam"):
                import focus_cam
                before = progress_count()
                await focus_cam.run_focus_cam(pw, out, failures)
                failures.extend(m for m in [progress_grew("focus-cam", before)] if m)
            if a.only in (None, "live", "rb-arrows"):
                import rb_arrows
                before = progress_count()
                await rb_arrows.run_rb_arrows(pw, out, failures)
                failures.extend(m for m in [progress_grew("rb-arrows", before)] if m)
            if a.only in (None, "live", "robot-tests"):
                import robot_tests
                before = progress_count()
                await robot_tests.run_robot_tests(pw, out, failures)
                failures.extend(m for m in [progress_grew("robot-tests", before)] if m)
            if a.only in (None, "live", "calls"):
                import calls
                await calls.run_calls(pw, out, failures)
            if a.only in (None, "live", "play"):
                import play
                await play.run_play(pw, out, failures)
            if a.only in (None, "live", "props"):
                import props
                await props.run_props(pw, out, failures)
            if a.only in (None, "live", "weather"):
                import weather
                await weather.run_weather(pw, out, failures)
                await weather.run_weather_few(pw, out, failures)
            if a.only in (None, "live", "usage"):
                import usage_header
                await usage_header.run_usage(pw, out, failures)
            if a.only in (None, "live", "rooms"):
                import rooms
                await rooms.run_rooms(pw, out, failures, RealServer)
            if a.only in (None, "live", "tower"):
                import tower_press
                await tower_press.run_tower_press(pw, out, failures, RealServer)

    asyncio.run(go())
    if a.record_demo:
        return 0
    for f in failures:
        print("FAIL", f)
    print("ok" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
