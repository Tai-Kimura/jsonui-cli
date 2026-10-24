"""Browser tests for `jui viz` (plan 10 §6). Outside pytest: they need Playwright and a Chromium.

    python tools/viz_e2e/run.py --out /tmp/viz-e2e                 # demo + live against fake_server.py
    python tools/viz_e2e/run.py --out /tmp/viz-e2e --only demo
    python tools/viz_e2e/run.py --out /tmp/x --record-demo URL     # record expect_demo.json from the prototype

Demo: every suite in demo.py, whose results must equal expect_demo.json (recorded from the prototype page, so a
difference means the port stopped behaving like the prototype). Live: live.py against fake_server.py and its
scenarios (scenarios/*.jsonl). Rooms (rooms.py): doors, desks and the one-room view on the real server (`--only rooms` runs it alone).
Both: no console errors, no request to anywhere but the server, no CSP violation.

Exit status 0 only when every check passed; each failed check is printed on its own line with FAIL. A suite that
stops on an exception (a wait's timeout, or anything else) is one FAIL line, its traceback is written next to its
results (<suite>-traceback.txt), and the next suite runs (common.suite_guard; ticket
2026-10-20-jui-viz-e2e-one-suite-exception-stops-the-run). `--only` may be given more than once.
One run at a time on the machine: run.py waits for /tmp/jui-viz-e2e-<uid>.lock first, in the order asked (a ticket
in its queue; --priority: the integration's check goes first; e2e_lock.py).
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
from common import E2E_MARKS, ISOLATE, LAUNCH_ARGS, Watch, dump, expect_demo_file, progress_count, progress_grew, suite_guard  # noqa: E402

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
    ap.add_argument("--only", action="append", choices=["demo", "live", "en-reps", "rooms", "ask", "history", "robot-tests", "rb-layout", "rb-arrows", "focus-cam", "tower", "calls", "play", "play-look", "props", "crowded-props", "breaks", "spec-help", "spec-colors", "weather", "usage", "name-tags", "shredder", "gitbox", "log-strip", "hist-wide", "hist-labels", "hist-images", "name-tag-role", "clock-out", "arrows-rooms", "ask-board", "callbell", "mermaid", "dataflow-mermaid", "data-server", "fulltext", "notify", "heavy-looks", "frame-gaps", "cost-bill", "bg-look", "workwear", "main-color", "hist-fold", "hist-peers", "talk", "talk-ui", "web-dict", "launch-whistle", "card-screens", "card-note", "tag-click", "spec-nest", "spec-worktrees", "test-tally", "server-room", "project-switch", "denied", "spec-sheet-layout", "spec-tables", "spec-branch-json", "attach", "waiting-input", "wait-kinds", "room-roster", "hist-cards", "stop-button", "devices", "camera-follow", "spirits", "lang-checks", "selected-look", "cost-rows", "sr-migration", "card-waits", "typed-kept", "server-room-2d", "sr-migration-2d", "wait-project"],
                    help="run one half (en-reps: the English representatives, one suite per family of the page — demo, live, history, talk-ui, server-room, cost-bill, ask, notify, denied, data-server, usage, devices — and lang-checks, the gate's English step with --lang en, ticket 2026-10-21-viz-english-screen-checks §5; server-room: only the server room's door, keypad and 3D; sr-migration: only a migration plan played in the server room; talk-ui: only the talk view's page side, on the demo; talk: only the talk view's server side (talk.* over the WebSocket); hist-peers: only a SendMessage's recipient linked to its robot; hist-fold: only a history fold closing on a click in its body; rooms: only the rooms/doors suite; ask: only the question card suite; history: only the 応答の履歴 tab; robot-tests: only a robot card's test runs; calls: only the phone calls; play: only idle robots playing; play-look: only what a game looks like (tags, the ball, the slap, the bubble); spec-help: only the 「?」 dialog of spec の進み具合; spec-colors: only the spec sheet's colours; weather: only the season and the near weather outside; name-tags: only robots' name tags kept apart; hist-wide: only the wide history; hist-labels: only the history's labels on one line; hist-images: only the pictures in the history; name-tag-role: only a session's name on its robot's tag; clock-out: only the 退勤 button; arrows-rooms: only ← → between rooms and ↑ ↓ between floors; ask-board: only the 質問 / 許可待ち chips' board; mermaid: only the vendored Mermaid (strict, nothing outside); dataflow-mermaid: only a spec's data flow as a diagram; data-server: only the rack and its API / DB sheet; heavy-looks: only heavy work's three looks (red, blue, the whistle); cost-bill: only the bill over a robot and the 単価 sheet; bg-look: only background work's headset, notes and laptop; web-dict: only WebFetch / WebSearch's dictionary on the desk; launch-whistle: only the whistle when a subagent is called (demo and live); card-note: only the × of the note over the card's prompt box; tag-click: only a click on a robot's tag (or its bill) selecting the robot; spec-nest: only the spec sheet's 構造 as a tree (the list's indent and lines, nested boxes); spec-sheet-layout: only the spec sheet in one column, nothing sideways (long text everywhere, 1440 and 390 px); spec-tables: only イベント and 操作 as one table; spec-branch-json: only 分岐's when / then as formatted JSON; waiting-input: only the 入力待ち notification (the hooks replayed); devices: only the デバイス button and pane; selected-look: only every control's on state set apart from its off state, light and dark; cost-rows: only the cost view's day rows (the bar over its words, ▼ / ▲, 390 wide); card-waits: only the other sessions' waits beside an open card; typed-kept: only what is typed kept through a redraw, and a card's questions folded; server-room-2d / sr-migration-2d: the same two from straight above (2D); wait-project: only a wait's project chosen on the way to the board; lang-checks: only the page as read in the run's language (keys shown as themselves; shots for lang_sheet.py); "
                         "tower: only the building's window press)")
    ap.add_argument("--lang", metavar="CODE",
                    help="the language every server of the run shows (JUI_VIZ_LANGUAGE; default: ja, which the checks were "
                         "written on). The gate's English step: --lang en --only en-reps --group-ok")
    ap.add_argument("--suite", action="append", help="demo suite(s) to run (default: all)")
    ap.add_argument("--group-ok", action="store_true",
                    help="run an --only that is a group (live, demo: most of the e2e); without it such a name stops "
                         "the run, after saying the suites it holds (only_groups.py)")
    ap.add_argument("--priority", action="store_true",
                    help="the integration's check: its ticket goes before every unmarked one in the machine's line "
                         "(e2e_lock.py; JUI_VIZ_E2E_PRIORITY=1 says the same). Only the integration uses it")
    ap.add_argument("--record-demo", metavar="URL",
                    help="run the demo suites against URL (the prototype's agent-test.html) and write expect_demo.json")
    a = ap.parse_args(argv)
    import only_groups
    lines, stop = only_groups.check(a.only, a.group_ok)   # before the line: a group is said, and stops without --group-ok
    for line in lines:
        print(line, flush=True)
    if stop:
        return 2
    # The checks wait on the page's Japanese words: every server these suites start (they pass this environment on)
    # shows Japanese, whatever the default language (viz/i18n.py). JUI_VIZ_LANGUAGE=en runs them on the English words.
    # --lang says it outright (the gate's English step, ticket 2026-10-21-viz-english-screen-checks §5).
    if a.lang:
        os.environ["JUI_VIZ_LANGUAGE"] = a.lang
    os.environ.setdefault("JUI_VIZ_LANGUAGE", "ja")
    print(f"language: {os.environ['JUI_VIZ_LANGUAGE']}", flush=True)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    E2E_MARKS.update({str(out), str(out.resolve())})   # every throwaway HOME is under it: a path of one in a record is this run's
    failures: list[str] = []
    suites = a.suite or list(demo.SUITES)

    def want(*names):
        """This block runs: no --only, or one of the --only values names it (--only may be given more than once)."""
        return not a.only or any(n in a.only for n in names)

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
            if want("en-reps", "demo"):
                with suite_guard("demo", failures, out):
                    srv = Server()
                    try:
                        res, watch = await run_demo(pw, f"{srv.url}/?demo=1", out, suites)
                    finally:
                        srv.stop()
                    (out / "demo-results.json").write_text(dump(res) + "\n")
                    expect_file = expect_demo_file(os.environ.get("JUI_VIZ_LANGUAGE", ""))
                    if not expect_file.is_file():
                        raise RuntimeError(f"no expected demo results for this language: {expect_file.name} (check "
                                           f"{out / 'demo-results.json'} by eye, then copy it there)")
                    expect = json.loads(expect_file.read_text())
                    for name in suites:
                        for line in diff(expect.get(name), res.get(name), f"demo/{name}"):
                            failures.append(line)
                    check_watch(watch, "demo", failures)
                    for key in ("shots", "perm", "scope", "phone"):
                        r = res.get(key) or {}
                        for k, v in r.items():
                            if isinstance(v, dict) and isinstance(v.get("sw"), int) and v["sw"] > 390:
                                failures.append(f"demo/{key}/{k}: horizontal scroll at 390 px (scrollWidth {v['sw']})")
                failures.extend(demo.CHECKS)   # the port's own checks, beside the prototype's recording (also when the suite stopped)
            if want("live", "spec-colors"):
                with suite_guard("spec-colors", failures, out):
                    import spec_colors
                    await spec_colors.run_spec_colors(pw, out, failures, Server)
            if want("demo", "spec-help"):
                with suite_guard("spec-help", failures, out):
                    import spec_help
                    await spec_help.run_spec_help(pw, out, failures, Server)
            if want("demo", "heavy-looks"):
                with suite_guard("heavy-looks", failures, out):
                    import heavy_looks
                    await heavy_looks.run_heavy_looks(pw, out, failures, Server)
            if want("en-reps", "live"):
                with suite_guard("live", failures, out):
                    import live
                    await live.run(pw, out, failures, Server)
                    await live.run_real(pw, out, failures, RealServer)
                    await live.run_real_decide(pw, out, failures)
            if want("live", "en-reps", "ask"):
                with suite_guard("ask", failures, out):
                    import ask
                    await ask.run_ask(pw, out, failures)
            if want("live", "en-reps", "notify"):
                with suite_guard("notify", failures, out):
                    import notify
                    await notify.run_notify(pw, out, failures)
            if want("live", "waiting-input"):
                with suite_guard("waiting-input", failures, out):
                    import waiting_input
                    await waiting_input.run_waiting_input(pw, out, failures)
            if want("live", "wait-kinds"):
                with suite_guard("wait-kinds", failures, out):
                    import wait_kinds
                    await wait_kinds.run_wait_kinds(pw, out, failures)
            if want("live", "card-waits"):
                with suite_guard("card-waits", failures, out):
                    import card_waits
                    await card_waits.run_card_waits(pw, out, failures)
            if want("live", "wait-project"):
                with suite_guard("wait-project", failures, out):
                    import wait_project
                    await wait_project.run_wait_project(pw, out, failures)
            if want("live", "typed-kept"):
                with suite_guard("typed-kept", failures, out):
                    import typed_kept
                    await typed_kept.run_typed_kept(pw, out, failures, Server)
            if want("live", "room-roster"):
                with suite_guard("room-roster", failures, out):
                    import room_roster
                    await room_roster.run_room_roster(pw, out, failures)
            if want("live", "ask-board"):
                with suite_guard("ask-board", failures, out):
                    import ask_board
                    await ask_board.run_ask_board(pw, out, failures)
            if want("live", "en-reps", "history"):
                with suite_guard("history", failures, out):
                    import history
                    before = progress_count()
                    await history.run_history(pw, out, failures)
                    await history.run_history_scroll(pw, out, failures)
                    import send_prompt
                    await send_prompt.run_send_prompt(pw, out, failures)
                    failures.extend(m for m in [progress_grew("history", before)] if m)
            if want("live", "hist-wide"):
                with suite_guard("hist-wide", failures, out):
                    import hist_wide
                    before = progress_count()
                    await hist_wide.run_hist_wide(pw, out, failures)
                    failures.extend(m for m in [progress_grew("hist-wide", before)] if m)
            if want("live", "card-note"):
                with suite_guard("card-note", failures, out):
                    import card_note
                    await card_note.run_card_note(pw, out, failures)
            if want("live", "hist-labels"):
                with suite_guard("hist-labels", failures, out):
                    import hist_labels
                    await hist_labels.run_hist_labels(pw, out, failures)
            if want("live", "hist-fold"):
                with suite_guard("hist-fold", failures, out):
                    import hist_fold
                    await hist_fold.run_hist_fold(pw, out, failures)
            if want("live", "hist-peers"):
                with suite_guard("hist-peers", failures, out):
                    import hist_peers
                    await hist_peers.run_hist_peers(pw, out, failures)
            if want("live", "hist-images"):
                with suite_guard("hist-images", failures, out):
                    import hist_images
                    before = progress_count()
                    await hist_images.run_hist_images(pw, out, failures)
                    failures.extend(m for m in [progress_grew("hist-images", before)] if m)
            if want("live", "rb-layout"):
                with suite_guard("rb-layout", failures, out):
                    import rb_layout
                    before = progress_count()
                    await rb_layout.run_rb_layout(pw, out, failures)
                    failures.extend(m for m in [progress_grew("rb-layout", before)] if m)
            if want("live", "focus-cam"):
                with suite_guard("focus-cam", failures, out):
                    import focus_cam
                    before = progress_count()
                    await focus_cam.run_focus_cam(pw, out, failures)
                    failures.extend(m for m in [progress_grew("focus-cam", before)] if m)
            if want("live", "rb-arrows"):
                with suite_guard("rb-arrows", failures, out):
                    import rb_arrows
                    before = progress_count()
                    await rb_arrows.run_rb_arrows(pw, out, failures)
                    failures.extend(m for m in [progress_grew("rb-arrows", before)] if m)
            if want("live", "robot-tests"):
                with suite_guard("robot-tests", failures, out):
                    import robot_tests
                    before = progress_count()
                    await robot_tests.run_robot_tests(pw, out, failures)
                    failures.extend(m for m in [progress_grew("robot-tests", before)] if m)
            if want("live", "calls"):
                with suite_guard("calls", failures, out):
                    import calls
                    await calls.run_calls(pw, out, failures)
            if want("live", "play"):
                with suite_guard("play", failures, out):
                    import play
                    await play.run_play(pw, out, failures)
            if want("live", "play-look"):
                with suite_guard("play-look", failures, out):
                    import play_look
                    await play_look.run_play_look(pw, out, failures)
            if want("live", "frame-gaps"):
                with suite_guard("frame-gaps", failures, out):
                    import frame_gaps
                    await frame_gaps.run_frame_gaps(pw, out, failures)
            if want("live", "props"):
                with suite_guard("props", failures, out):
                    import props
                    await props.run_props(pw, out, failures)
            if want("live", "breaks"):
                with suite_guard("breaks", failures, out):
                    import breaks
                    await breaks.run_breaks(pw, out, failures)
            if want("live", "callbell"):
                with suite_guard("callbell", failures, out):
                    import callbell
                    await callbell.run_callbell(pw, out, failures)
            if want("live", "weather"):
                with suite_guard("weather", failures, out):
                    import weather
                    await weather.run_weather(pw, out, failures)
                    await weather.run_weather_few(pw, out, failures)
            if want("live", "en-reps", "usage"):
                with suite_guard("usage", failures, out):
                    import usage_header
                    await usage_header.run_usage(pw, out, failures)
            if want("live", "name-tags"):
                with suite_guard("name-tags", failures, out):
                    import name_tags
                    await name_tags.run_name_tags(pw, out, failures)
            if want("live", "tag-click"):
                with suite_guard("tag-click", failures, out):
                    import tag_click
                    await tag_click.run_tag_click(pw, out, failures)
            if want("live", "shredder"):
                with suite_guard("shredder", failures, out):
                    import shredder
                    await shredder.run_shredder(pw, out, failures)
            if want("live", "gitbox"):
                with suite_guard("gitbox", failures, out):
                    import gitbox
                    before = progress_count()
                    await gitbox.run_gitbox(pw, out, failures)
                    failures.extend(m for m in [progress_grew("gitbox", before)] if m)
            if want("live", "log-strip"):
                with suite_guard("log-strip", failures, out):
                    import log_strip
                    await log_strip.run_log_strip(pw, out, failures)
            if want("live", "name-tag-role"):
                with suite_guard("name-tag-role", failures, out):
                    import name_tag_role
                    await name_tag_role.run_name_tag_role(pw, out, failures)
            if want("live", "clock-out"):
                with suite_guard("clock-out", failures, out):
                    import clock_out
                    before = progress_count()
                    await clock_out.run_clock_out(pw, out, failures)
                    failures.extend(m for m in [progress_grew("clock-out", before)] if m)
            if want("live", "bg-look"):
                with suite_guard("bg-look", failures, out):
                    import bg_look
                    await bg_look.run_bg_look(pw, out, failures)
            if want("demo", "live", "launch-whistle"):
                with suite_guard("launch-whistle", failures, out):
                    import launch_whistle
                    await launch_whistle.run_launch_whistle(pw, out, failures, Server)
            if want("live", "web-dict"):
                with suite_guard("web-dict", failures, out):
                    import web_dict
                    await web_dict.run_web_dict(pw, out, failures)
            if want("live", "workwear"):
                with suite_guard("workwear", failures, out):
                    import workwear
                    await workwear.run_workwear(pw, out, failures)
            if want("live", "main-color"):
                with suite_guard("main-color", failures, out):
                    import main_color
                    await main_color.run_main_color(pw, out, failures)
            if want("live", "arrows-rooms"):
                with suite_guard("arrows-rooms", failures, out):
                    import arrows_rooms
                    await arrows_rooms.run_arrows_rooms(pw, out, failures)
            if want("live", "mermaid"):
                with suite_guard("mermaid", failures, out):
                    import mermaid_vendor
                    await mermaid_vendor.run_mermaid(pw, out, failures)
            if want("live", "dataflow-mermaid"):
                with suite_guard("dataflow-mermaid", failures, out):
                    import dataflow_mermaid
                    await dataflow_mermaid.run_dataflow_mermaid(pw, out, failures)
            if want("live", "spec-nest"):
                with suite_guard("spec-nest", failures, out):
                    import spec_nest
                    await spec_nest.run_spec_nest(pw, out, failures)
            if want("live", "spec-worktrees"):
                with suite_guard("spec-worktrees", failures, out):
                    import spec_worktrees
                    await spec_worktrees.run_spec_worktrees(pw, out, failures)
            if want("live", "test-tally"):
                with suite_guard("test-tally", failures, out):
                    import test_tally
                    await test_tally.run_test_tally(pw, out, failures)
            if want("live", "spec-sheet-layout"):
                with suite_guard("spec-sheet-layout", failures, out):
                    import spec_sheet_layout
                    await spec_sheet_layout.run_spec_sheet_layout(pw, out, failures, Server)
            if want("live", "spec-tables"):
                with suite_guard("spec-tables", failures, out):
                    import spec_tables
                    await spec_tables.run_spec_tables(pw, out, failures, Server)
            if want("live", "spec-branch-json"):
                with suite_guard("spec-branch-json", failures, out):
                    import spec_branch_json
                    await spec_branch_json.run_spec_branch_json(pw, out, failures, Server)
            if want("live", "en-reps", "server-room"):
                with suite_guard("server-room", failures, out):
                    import server_room
                    await server_room.run_server_room(pw, out, failures)
            if want("live", "sr-migration"):
                with suite_guard("sr-migration", failures, out):
                    import sr_migration
                    await sr_migration.run_sr_migration(pw, out, failures)
            if want("live", "server-room-2d"):   # the same arms from straight above (ticket 2026-10-23-viz-server-room-2d-mode)
                with suite_guard("server-room-2d", failures, out):
                    import server_room
                    await server_room.run_server_room(pw, out, failures, flat=True)
            if want("live", "sr-migration-2d"):
                with suite_guard("sr-migration-2d", failures, out):
                    import sr_migration
                    await sr_migration.run_sr_migration(pw, out, failures, flat=True)
            if want("live", "crowded-props"):
                with suite_guard("crowded-props", failures, out):
                    import crowded_props
                    await crowded_props.run_crowded_props(pw, out, failures)
            if want("live", "en-reps", "data-server"):
                with suite_guard("data-server", failures, out):
                    import data_server
                    await data_server.run_data_server(pw, out, failures)
            if want("live", "attach"):
                with suite_guard("attach", failures, out):
                    import attach
                    await attach.run_attach(pw, out, failures)
            if want("live", "card-screens"):
                with suite_guard("card-screens", failures, out):
                    import card_screens
                    await card_screens.run_card_screens(pw, out, failures)
            if want("live", "fulltext"):
                with suite_guard("fulltext", failures, out):
                    import fulltext
                    await fulltext.run_fulltext(pw, out, failures)
            if want("live", "en-reps", "cost-bill"):
                with suite_guard("cost-bill", failures, out):
                    import cost_bill
                    await cost_bill.run_cost_bill(pw, out, failures)
            if want("demo", "selected-look"):
                with suite_guard("selected-look", failures, out):
                    import selected_look
                    await selected_look.run_selected_look(pw, out, failures, Server)
            if want("live", "cost-rows"):
                with suite_guard("cost-rows", failures, out):
                    import cost_rows
                    await cost_rows.run_cost_rows(pw, out, failures)
            if want("demo", "en-reps", "talk-ui"):
                with suite_guard("talk-ui", failures, out):
                    import talk_ui
                    await talk_ui.run_talk_ui(pw, out, failures, Server)
            if want("demo", "en-reps", "lang-checks"):
                with suite_guard("lang-checks", failures, out):
                    import lang_checks
                    await lang_checks.run_lang_checks(pw, out, failures, Server)
            if want("live", "en-reps", "denied"):
                with suite_guard("denied", failures, out):
                    import denied
                    await denied.run_denied(pw, out, failures)
            if want("live", "project-switch"):
                with suite_guard("project-switch", failures, out):
                    import project_switch
                    await project_switch.run_project_switch(pw, out, failures)
            if want("live", "camera-follow"):
                with suite_guard("camera-follow", failures, out):
                    import camera_follow
                    await camera_follow.run_camera_follow(pw, out, failures)
            if want("live", "spirits"):
                with suite_guard("spirits", failures, out):
                    import spirits
                    await spirits.run_spirits(pw, out, failures)
            if want("live", "hist-cards"):
                with suite_guard("hist-cards", failures, out):
                    import hist_cards
                    await hist_cards.run_hist_cards(pw, out, failures)
            if want("live", "stop-button"):
                with suite_guard("stop-button", failures, out):
                    import stop_button
                    await stop_button.run_stop_button(pw, out, failures)
            if want("live", "en-reps", "devices"):
                with suite_guard("devices", failures, out):
                    import devices_pane
                    await devices_pane.run_devices_pane(pw, out, failures)
            if want("live", "talk"):
                with suite_guard("talk", failures, out):
                    import talk_view
                    before = progress_count()
                    await talk_view.run_talk(pw, out, failures)
                    failures.extend(m for m in [progress_grew("talk", before)] if m)
            if want("live", "rooms"):
                with suite_guard("rooms", failures, out):
                    import rooms
                    await rooms.run_rooms(pw, out, failures, RealServer)
            if want("live", "tower"):
                with suite_guard("tower", failures, out):
                    import tower_press
                    await tower_press.run_tower_press(pw, out, failures, RealServer)

    import e2e_lock
    # one viz e2e at a time on the machine, in the order asked; let go when this process exits (e2e_lock.py)
    held = e2e_lock.hold(only=a.only or [], priority=True if a.priority else None)
    asyncio.run(go())
    if a.record_demo:
        return 0
    for f in failures:
        print("FAIL", f)
    print("ok" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
