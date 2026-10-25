"""Capture the viz chapters as numbered frames (ticket 2026-10-21-viz-promo-replay-and-capture-tool §1, §3, §5).

Per chapter: a throwaway HOME and rooms (rooms.py), the real `jui viz serve` of --jui-root on a free port in that
HOME (JUI_VIZ_E2E=1 for window.__dbg; PATH cut to the stand-ins' bin, /usr/bin and /bin and --no-agents-poll, as the
talk suite does: nothing here can start the agent CLI), Chromium at 1920x1080 (device scale 1), the chapter's prelude,
then one frame per 1/30 s of the video.

The clock. page.clock.install() before the page loads fakes Date, performance.now, the timers and
requestAnimationFrame, and pause_at() stops it (installed but not paused, it runs at the wall clock's pace: the first
capture did so), so the page draws only when the driver lets time pass: per frame, clock.run_for() with the
frame's share of a second (33 or 34 ms, summing to exactly 1000 ms every 30 frames). The 3D (40-scene.js, the
server room's own loop, the flow player, the cost day's play) all run from requestAnimationFrame and
performance.now, so they move by video time, not by how long a screenshot took. What does not follow the page's
clock: the server (its timestamps, its pushes every 200 ms, a Stop's idle after it) and the WebSocket — data arrives
in real time. So after an event fires the driver waits, in real time and without moving the clock, until the page
has taken it in (LIVE.seenSeq through __dbg.liveSeenSeq, or the event's `expect`), then takes the next frame.
Every wait polls from Python: wait_for_function's 'raf' polling would never run under a paused clock.

The page's presence report (every 5 s of its clock) would come once a minute of real time while frames are taken,
and the server drops a page's presence after 12 s — a question would go back to the terminal. The driver
re-sends it every PRESENCE_EVERY_SEC of real time through the page's own visibilitychange listener (25-net.js).

The cursor. Plan §2.6 shows the mouse: the driver injects one small arrow element (#promo-cursor, fixed,
pointer-events none, above everything) and moves it with the real mouse it drives (page.mouse), gliding GLIDE_SEC
to each press. It is an overlay drawn by this tool, the only element the app did not draw (README).
"""

from __future__ import annotations

import asyncio
import hashlib
import http.client
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

E2E = Path(__file__).resolve().parent.parent / "viz_e2e"
if str(E2E) not in sys.path:
    sys.path.append(str(E2E))   # after the rest: viz_e2e has a rooms.py and a run.py of its own

from common import ISOLATE, LAUNCH_ARGS, Watch, robot_point  # noqa: E402  (viz_e2e)
from viz_promo.rooms import cleanup, make_home, make_rooms, write_sessions  # noqa: E402
from viz_promo.timeline import FPS, SESSIONS, SUBAGENT, WORDS, frame_count, frame_time, session_id  # noqa: E402

VIEWPORT = {"width": 1920, "height": 1080}
GLIDE_SEC = 0.7
TARGET_LATE_SEC = 3.0      # how late a press may come while its target is not on the page yet
MIN_GAP_SEC = 0.6          # a press never follows the one before sooner (a `ready` that comes late does not bunch them)
PRESENCE_EVERY_SEC = 3.0
WAIT_SEC = 20.0            # the longest a frame waits for the page to take an event in
SETTLE_PAGE_SEC = 20.0     # the longest a prelude's settle lets the page's clock run

# A feature the chapter needs: the file in --jui-root's jui_tools that brings it, and what the page shows of it.
FEATURES = {
    "rooms": ("jui_cli/viz/rooms.py", None),
    "server_room": ("jui_cli/viz/web/js/56-server-room.js", "() => !!(window.__dbg && window.__dbg.sr)"),
    "flows": ("jui_cli/viz/web/js/59-sr-flows.js", "() => !!(window.__dbg && window.__dbg.srFlow)"),
    "cost": ("jui_cli/viz/web/js/56-server-cost.js",
             "() => !!(window.__dbg && window.__dbg.srCost) && !!document.getElementById('sr-mode-cost')"),
    "i18n": ("jui_cli/viz/i18n.py", None),
    "migration": ("jui_cli/viz/web/js/59-sr-migration.js", "() => !!(window.__dbg && window.__dbg.srMig)"),
    "sr2d": ("jui_cli/viz/web/js/56-server-room.js", "() => !!document.getElementById('sr-mode-2d')"),
    "roster": ("jui_cli/viz/web/js/53-roster.js", "() => !!document.getElementById('roster-sort')"),
    "spec_worktrees": ("jui_cli/viz/web/js/30-source-live.js", None),   # no mark of its own: the wait on the sheet's ⎇ head fails without it
}

# Math.random from a fixed seed (mulberry32): the page's idle choices (a robot's break, a game, a glance) are drawn
# from it, so two captures of a chapter make the same choices. What is drawn is the page's own; only the dice are set.
SEEDED_RANDOM_JS = """(() => { let a = 0x5eed1234; Math.random = () => { a |= 0; a = (a + 0x6d2b79f5) | 0;
  let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; })()"""

CURSOR_JS = """() => {
  if (document.getElementById('promo-cursor')) return true;
  const c = document.createElement('div');
  c.id = 'promo-cursor';
  c.setAttribute('aria-hidden', 'true');
  c.style.cssText = 'position:fixed;left:0;top:0;width:28px;height:28px;z-index:2147483647;pointer-events:none;transform:translate(960px,540px)';
  c.innerHTML = '<svg width="28" height="28" viewBox="0 0 28 28"><path d="M3 2 L3 22 L8.5 17 L12.5 26 L16 24.5 L12 15.8 L19.5 15.8 Z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  document.documentElement.appendChild(c);
  return true;
}"""

# where a target is on the screen: [x, y] of its centre, or null while it is not there
POINT_JS = """(t) => {
  const centre = (el) => { if (!el) return null; const r = el.getBoundingClientRect(); if (!r.width && !r.height) return null;
    return [Math.round(r.left + r.width / 2), Math.round(r.top + r.height / 2)]; };
  if (t.door) { const s = window.__dbg.sr(); return s.door || null; }
  if (t.cost_day) { const days = [...document.querySelectorAll('#sr-cost .src-day')]; if (!days.length) return null;
    return centre(days.find((d) => d.querySelector('.src-over')) || days[Math.floor(days.length / 2)]); }
  const all = [...document.querySelectorAll(t.css)];
  const el = t.text ? all.find((e) => e.textContent.includes(t.text)) : all[0];
  if (el && t.visible) {
    // the first point on the element a press lands on (a name tag partly under another one: en's long tags, 2.3.23)
    const r = el.getBoundingClientRect();
    for (let fy = 0.5; fy > 0.1; fy -= 0.2) for (let fx = 0.1; fx < 0.95; fx += 0.08) {
      const x = Math.round(r.left + r.width * fx), y = Math.round(r.top + r.height * fy), hit = document.elementFromPoint(x, y);
      if (hit && (hit === el || el.contains(hit))) return [x, y];
    }
    return null;
  }
  return centre(el);
}"""

# the target element pressed (its click()), found as POINT_JS finds it
CLICK_JS = """(t) => { const all = [...document.querySelectorAll(t.css)]; const el = t.text ? all.find((e) => e.textContent.includes(t.text)) : all[0];
  if (el) el.click(); return !!el; }"""

# the target is where a press there lands on it: on the screen and not under something else (choices drawn over a
# node off the screen took no press, 10-21)
HIT_JS = """(t) => { if (t.door) return !!window.__dbg.sr().door;
  let el = null;
  if (t.cost_day) { const days = [...document.querySelectorAll('#sr-cost .src-day')]; el = days.find((d) => d.querySelector('.src-over')) || days[Math.floor(days.length / 2)]; }
  else { const all = [...document.querySelectorAll(t.css)]; el = t.text ? all.find((e) => e.textContent.includes(t.text)) : all[0]; }
  if (!el) return false;
  const r = el.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
  if (!r.width || !r.height || x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) return false;
  const at = document.elementFromPoint(x, y); return !!at && (at === el || el.contains(at)); }"""

EXPECT = {
    "solo": "(pid) => window.__dbg.solo() === pid",
    "floor": "() => window.__dbg.solo() === null",
    "picked": "(l) => { const p = window.__dbg.waitPicked(); return !!p && p.id === l; }",
    "card": "(l) => window.__dbg.board().robot === l",
    "qcard": "() => window.__dbg.questions().some((q) => q.hookWaiting)",
    "qdone": "() => !window.__dbg.questions().some((q) => q.hookWaiting)",
    "dcard": None,   # the event's arrival (seenSeq) is the check
    "talk": "() => !!(window.__dbg.talk && window.__dbg.talk().on)",
    "flowlist": "(id) => !!document.querySelector(`#sr-board [data-sr-flow=\"${id}\"]`)",
    "flow": "(id) => window.__dbg.srFlow().playing === id",
    "cost_month": "() => { const c = window.__dbg.srCost(); return !!c.month && !c.error; }",
    "cost_day": "() => !!window.__dbg.srCost().day",
    "migopen": "() => window.__dbg.srMig().open",
    "roster_open": "() => !document.getElementById('roster').classList.contains('roster-folded')",
    "roster_folded": "() => document.getElementById('roster').classList.contains('roster-folded')",
    "roster_state": "() => { const r = document.querySelector('#roster-list .roster-row'); return document.getElementById('roster-sort').value === 'state' && !!r; }",
    # the sheet opened on a spec (its title is set at the press; the head's ⎇ branch comes with the page's next frame)
    "wbtitle": "(t) => document.getElementById('wb-title').textContent === t",
    # the spec's diff against its base open, full screen, read (2.3.23)
    "specdiff": "() => !document.getElementById('sd').hidden && !document.querySelector('#sd-body').textContent.includes('…')",
    "sr2d": "() => { const b = document.getElementById('sr-mode-2d'); return !!b && b.getAttribute('aria-pressed') === 'true'; }",
    "migcost": "() => { const m = window.__dbg.srMig(); return m.open && !!m.cost; }",
    "migtable": "() => !!document.querySelector('[data-src-mig]')",
    "board": "() => window.__dbg.view().open.wb && !!document.querySelector('#wb-code section.sc')",
}

# the spec's index in the page's spec list (its room, its file) + 1, or null while it is not there
FIND_SPEC_JS = """([pid, rel, path]) => { const i = window.__dbg.model().specs.findIndex((s) => s.project === pid
    && (s.file === rel || s.file.endsWith('/' + rel) || rel.endsWith('/' + s.file) || s.file === path));
  return i < 0 ? null : i + 1; }"""


class PromoError(RuntimeError):
    pass


def free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def missing_features(jui_root: Path, needs, lang: str) -> list:
    """The features of `needs` (and i18n for English) whose file is not in --jui-root."""
    jt = Path(jui_root) / "jui_tools"
    want = list(needs) + (["i18n"] if lang == "en" else [])
    return [f"{n} ({FEATURES[n][0]} is not in {jt})" for n in want if not (jt / FEATURES[n][0]).is_file()]


def room_of(key: str) -> str:
    return dict((k, room) for k, _, room in SESSIONS)[key]


class Stage:
    """The throwaway HOME, the rooms and the real server of one chapter."""

    def __init__(self, lang: str, jui_root: Path, demo_shop: Path, keep: bool = False, name: str = "x"):
        self.lang, self.keep = lang, keep
        # one fixed folder per language and chapter under /tmp (no user name in any path the page could show): a
        # room's id is the sha1 of its path and seeds where its desks stand, so a random folder moved the robots
        # between two captures of the same chapter
        # JUI_PROMO_BASE moves it (a capture's own scratch folder, where no other cleanup reaches); the page shows
        # the rooms as ~/work/<room> either way
        self.base = (Path(os.environ.get("JUI_PROMO_BASE") or "/tmp/jui-promo") / f"{lang}-{name}").resolve()
        cleanup(self.base)
        self.base.mkdir(parents=True)
        self.home = self.base / "home"
        self.paths = make_home(self.home)
        # the rooms under the server's HOME: the page writes a path there as ~/work/<room> (viz/rooms.py tilde),
        # never the temporary folder's
        self.rooms = {k: v.resolve() for k, v in make_rooms(self.home / "work", lang, demo_shop).items()}
        # each session's process: a stand-in started as the plugin's sessions are (Relay), its pid in the session file
        self.standins = {key: subprocess.Popen([sys.executable, *STANDIN_ARGV], stdin=subprocess.DEVNULL, start_new_session=True)
                         for key, _, _ in SESSIONS}
        try:
            self.pids = {key: p.pid for key, p in self.standins.items()}
            self.transcripts = write_sessions(self.paths, self.rooms, lang, self.pids)
            self.relay = Relay(self)
        except Exception:
            for p in self.standins.values():
                p.kill()   # our own stand-ins
            raise
        self.jt = Path(jui_root).resolve() / "jui_tools"
        self.forward = self.jt / "jui_cli" / "viz" / "forward.py"
        drop = ISOLATE + ("PYTHONPATH", "CLAUDE_CONFIG_DIR", "ANDROID_HOME", "ANDROID_SDK_ROOT")
        base_env = {k: v for k, v in os.environ.items() if k not in drop}
        self.hook_env = dict(base_env, HOME=str(self.home))
        self.serve_env = dict(base_env, HOME=str(self.home), JUI_VIZ_E2E="1", JUI_VIZ_LANGUAGE=lang,
                              PATH=f"{self.paths['bin']}:/usr/bin:/bin")
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.proc = None
        self.asks: dict = {}
        self.open_tools: dict = {}
        self.n = 0
        self.runs: dict = {}
        self.specs: dict = {}      # (room, rel) -> (the spec as demo-shop has it, the keys the file has now)
        self.worktrees: dict = {}  # name -> a worktree's folder (make_worktree)

    # ---- the server ----
    def start(self):
        self.log = open(self.base / "serve.log", "w")
        self.proc = subprocess.Popen([sys.executable, str(self.jt / "bin" / "jui"), "viz", "serve", "--port", str(self.port), "--no-agents-poll"],
                                     stdout=self.log, stderr=subprocess.STDOUT, env=self.serve_env)
        for _ in range(300):
            try:
                urllib.request.urlopen(f"{self.url}/health", timeout=1).read()
                return
            except OSError:
                if self.proc.poll() is not None:
                    break
                time.sleep(0.1)
        self.stop()
        raise PromoError(f"jui viz serve did not start: {(self.base / 'serve.log').read_text()[-800:]}")

    def stop(self):
        self.relay.close()
        for p in self.standins.values():
            p.kill()   # our own stand-ins
            p.wait(timeout=5)
        for p in self.asks.values():
            if p.poll() is None:
                p.kill()   # our own forward.py --ask
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(2)   # INT: the server ends as on Ctrl-C (our own child)
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if getattr(self, "log", None):
            self.log.close()
        if not self.keep:
            cleanup(self.base)

    # ---- hook bodies ----
    def path(self, value):
        """'@room/rel' -> that room's file."""
        if isinstance(value, str) and value.startswith("@"):
            room, _, rel = value[1:].partition("/")
            return str(self.rooms[room] / rel)
        if isinstance(value, dict):
            return {k: self.path(v) for k, v in value.items()}
        return value

    def body(self, key: str, event: str, **kw) -> dict:
        b = {"session_id": session_id(key), "cwd": str(self.rooms[room_of(key)]), "transcript_path": str(self.transcripts[key]),
             "hook_event_name": event, "permission_mode": kw.pop("permission_mode", "default")}
        b.update(kw)
        return b

    def send(self, body: dict):
        subprocess.run([sys.executable, "-I", "-S", str(self.forward)], input=json.dumps(body).encode(),
                       capture_output=True, env=self.hook_env, timeout=15)

    def use_id(self, key: str) -> str:
        self.n += 1
        return f"toolu_{key}{self.n:06d}"

    # ---- a git worktree of a room (2.3.21: the spec board lists the worktrees sessions work in) ----
    def make_worktree(self, room: str, branch: str, name: str, changes: dict):
        """A worktree of the room's copy on a new branch, outside the room (scratch/<name>, as the e2e makes one), with
        `changes` ({rel: the file's text, or {dotted key: value} edits of its copy there}) written in it and left
        uncommitted (work in progress)."""
        wt = self.home / "scratch" / name
        wt.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "worktree", "add", "-q", "-b", branch, str(wt)], cwd=self.rooms[room], check=True,
                       capture_output=True, env=self.hook_env)
        for rel, change in changes.items():
            path = wt / rel
            if isinstance(change, dict):   # {dotted key: value} edits of the worktree's own copy of the file
                data = json.loads(path.read_text(encoding="utf-8"))
                for key, value in change.items():
                    *head, last = key.split(".")
                    at = data
                    for k in head:
                        at = at[k]
                    at[last] = value
                change = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(change, encoding="utf-8")
        self.worktrees[name] = wt

    # ---- a spec written section by section (a board) ----
    def spec_reset(self, room: str, rel: str, keep: list):
        """The room's spec as demo-shop has it is kept; the file is left with the `keep` keys only."""
        path = self.rooms[room] / rel
        full = json.loads(path.read_text(encoding="utf-8"))
        self.specs[(room, rel)] = (full, [k for k in full if k in keep])
        path.write_text(self.spec_text(full, self.specs[(room, rel)][1]), encoding="utf-8")

    def spec_grow(self, room: str, rel: str, key: str):
        """The spec's text with `key` added to what it has: (its path, the text)."""
        full, has = self.specs[(room, rel)]
        if key not in full:
            raise PromoError(f"{rel} has no {key!r}")
        has.append(key)
        return str(self.rooms[room] / rel), self.spec_text(full, has)

    @staticmethod
    def spec_text(full: dict, keys: list) -> str:
        return json.dumps({k: full[k] for k in full if k in keys}, ensure_ascii=False, indent=2) + "\n"

    # ---- transcripts and progress records ----
    def append(self, key: str, *records):
        with open(self.transcripts[key], "a", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def run_id(self, name: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"jui-promo/{name}"))

    def progress(self, run: str, event: str, **fields):
        rec = {"v": 1, "t": int(time.time() * 1000), "platform": "web", "run": self.run_id(run), "event": event, **fields}
        with open(self.paths["progress"] / f"{self.run_id(run)}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# A session's process as the jui-viz plugin's sessions are started (sources/launch.py reads its argv): the flag that
# names the plugin's channel, so the page says a prompt from it reaches the session. It only sleeps.
STANDIN_ARGV = ["-I", "-S", "-c", "import time\nwhile True: time.sleep(3600)",
                "--dangerously-load-development-channels", "plugin:jui-viz@jsonui"]
CHANNEL_VERSION = "2"     # channel.py VERSION: takes prompts from the page
POLL_TIMEOUT_SEC = 35     # channel.py: the server holds a poll up to 25 s


class Relay:
    """Every session's jui-viz channel, connected as the plugin's channel.py connects it: POST /channel/hello (the
    session's id, its process as ppid, accepts prompt, via plugin), then a long poll on /channel/poll that keeps it
    alive (the server drops a channel not seen for 60 s), and a permission prompt as the CLI relays it, POST
    /channel/request (a 5-letter request id, the tool, the input as its preview). The page then shows the sessions as
    relay-connected, as it does for anyone with the plugin. Nothing is answered back to a session here."""

    def __init__(self, stage: "Stage"):
        self.stage = stage
        self.ids: dict = {}
        self.pending: list = []
        self.stopping = threading.Event()
        self.threads: list = []
        self.n = 0

    def _call(self, method: str, path: str, body: dict | None = None, timeout: float = 5):
        info = json.loads((self.stage.paths["viz"] / "server.json").read_text(encoding="utf-8"))
        conn = http.client.HTTPConnection("127.0.0.1", info["port"], timeout=timeout)
        try:
            headers = {"X-Jui-Viz-Token": str(info.get("token", "")), "Host": f"127.0.0.1:{info['port']}"}
            payload = None
            if body is not None:
                payload = json.dumps(body).encode("utf-8")
                headers["Content-Type"] = "application/json"
            conn.request(method, path, body=payload, headers=headers)
            res = conn.getresponse()
            return res.status, res.read()
        finally:
            conn.close()

    def connect(self):
        st = self.stage
        for key, _, room in SESSIONS:
            if key in self.ids:
                continue
            body = {"ppid": st.pids[key], "cwd": str(st.rooms[room]), "sessionId": session_id(key), "version": CHANNEL_VERSION,
                    "accepts": ["prompt"], "via": "plugin"}
            status, data = self._call("POST", "/channel/hello", body)
            if status != 200:
                raise PromoError(f"channel hello for {key}: HTTP {status}")
            self.ids[key] = json.loads(data.decode("utf-8"))["channelId"]
            t = threading.Thread(target=self._poll, args=(self.ids[key],), daemon=True)
            t.start()
            self.threads.append(t)
        for key, item in self.pending:
            self._call("POST", "/channel/request", dict(item, channelId=self.ids[key]))
        self.pending = []

    def _poll(self, channel_id: str):
        while not self.stopping.is_set():
            try:
                status, _ = self._call("GET", f"/channel/poll?channelId={channel_id}", timeout=POLL_TIMEOUT_SEC)
            except OSError:
                status = 0
            if status != 200:
                self.stopping.wait(1.0)

    def request(self, key: str, tool: str, tool_input: dict):
        self.n += 1
        rid = "".join("abcdefghijkmnopqrstuvwxyz"[(self.n * 7 + k * 11) % 25] for k in range(5))
        item = {"request_id": rid, "tool_name": tool, "description": tool_input.get("description") or tool,
                "input_preview": json.dumps(tool_input, ensure_ascii=False)}
        if key in self.ids:
            self._call("POST", "/channel/request", dict(item, channelId=self.ids[key]))
        else:
            self.pending.append((key, item))   # sent once the channel is connected (channel.py's outbox)

    def close(self):
        self.stopping.set()


class Driver:
    """One chapter's page: the prelude, then the frames."""

    def __init__(self, page, stage: Stage, lang: str, watch: Watch, sky_time: str | None, fake_clock: bool = True):
        self.page, self.stage, self.lang, self.watch = page, stage, lang, watch
        self.fake = fake_clock     # False: the page runs on its own clock (--measure-fps)
        self.w = WORDS[lang]
        self.labels: dict = {}
        self.cursor = [VIEWPORT["width"] / 2, VIEWPORT["height"] / 2]
        self.log: list = []
        self.warnings: list = []
        self.frames_done = 0
        self.last_press = -1e9
        self.sky_ms = None
        if sky_time:
            hh, mm = (int(x) for x in sky_time.split(":"))
            self.sky_ms = int(datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0).timestamp() * 1000)

    # ---- waiting without the page's clock (or with it, before frame 0) ----
    async def until(self, js: str, arg=None, what: str = "", advance: bool = False, timeout: float = WAIT_SEC):
        deadline = time.monotonic() + timeout
        while True:
            v = await self.page.evaluate(js, arg)
            if v:
                return v
            if time.monotonic() > deadline:
                raise PromoError(f"waiting for {what or js[:80]} ({timeout:.0f} s)")
            if advance and self.fake:
                await self.page.clock.run_for(100)
            await asyncio.sleep(0.05)

    async def seq(self) -> int:
        return int(await self.page.evaluate("() => window.__dbg.liveSeenSeq()") or 0)

    async def taken_in(self, before: int, advance: bool):
        """The page took in the events a hook made (seenSeq past `before`), then a push's worth more."""
        try:
            await self.until("(n) => window.__dbg.liveSeenSeq() > n", before, "the page to take the hook in", advance, timeout=10)
        except PromoError as e:
            self.warnings.append(str(e))
            return
        await asyncio.sleep(0.4)   # the slices of the same push (pushIntervalMs 200)

    async def label(self, key: str) -> str:
        if key not in self.labels:
            lab = await self.until("(sid) => window.__dbg.labelOfSession(sid)", session_id(key), f"{key}'s robot", advance=False)
            self.labels[key] = lab
        return self.labels[key]

    def project(self, room: str) -> str:
        """The room's id the server gives it (rooms.py: sha1 of its root, 12 hex)."""
        return hashlib.sha1(str(self.stage.rooms[room]).encode("utf-8")).hexdigest()[:12]

    # ---- boot and prelude ----
    async def boot(self, needs):
        await self.page.goto(self.stage.url + "/")
        await self.until("() => !!(window.__dbg && window.__dbg.robots)", what="the page's hook (JUI_VIZ_E2E)", advance=True, timeout=60)
        await self.until("() => { const c = document.querySelector('.chip.demo'); return !!c && c.dataset.conn === 'ok'; }",
                         what="connected", advance=True, timeout=60)
        for n in needs:
            js = FEATURES[n][1]
            if js and not await self.page.evaluate(js):
                raise PromoError(f"the page has no {n}: this tree's viz does not have the feature the chapter needs")
        await self.page.evaluate(CURSOR_JS)
        await self.place_cursor()

    async def prelude(self, events):
        for ev in events:
            await self.fire(ev, advance=True)
        # every session's channel, once its session is known to the server (a hello finds it by its id)
        await asyncio.get_running_loop().run_in_executor(None, self.stage.relay.connect)
        if self.sky_ms is not None:   # the sky's hour, before frame 0 so its change is not filmed
            await self.page.evaluate("(ms) => window.__dbg.setClock(ms)", self.sky_ms)
        await self.settle()

    async def settle(self):
        """Before frame 0: let the page's clock run until the robots have arrived (or SETTLE_PAGE_SEC of it)."""
        for _ in range(int(SETTLE_PAGE_SEC * 10)):
            if self.fake:
                await self.page.clock.run_for(100)
                await asyncio.sleep(0.02)
            else:
                await asyncio.sleep(0.1)
            if await self.page.evaluate("() => !window.__dbg.settle || window.__dbg.settle()"):
                break
        if self.fake:
            await self.page.clock.run_for(1000)
        else:
            await asyncio.sleep(1.0)

    # ---- the events ----
    async def fire(self, ev, advance: bool):
        a, k, st = ev.args, ev.kind, self.stage
        hook_kinds = {"start", "prompt", "tool", "tool_end", "perm", "ask_pending", "ask", "ask_answered", "denied", "idle",
                      "stop", "sub_start", "sub_stop", "tests_start", "tests_end", "spec_write", "wt_session"}
        before = await self.seq() if k in hook_kinds else 0
        now = int(time.time() * 1000)
        if k == "start":
            # a session began half an hour before the page's clock (the sky's hour when --sky-time sets it: the page
            # counts a session's hours on that clock, and one begun at 3 am showed tired under a 14:00 sky)
            began = (self.sky_ms if self.sky_ms is not None else now) - 1_800_000
            st.append(a["key"], {"type": "system", "subtype": "init", "timestamp": iso(began), "sessionId": session_id(a["key"]),
                                 "cwd": str(st.rooms[room_of(a["key"])]), "uuid": str(uuid.uuid4())})
            st.send(st.body(a["key"], "SessionStart", source="startup"))
        elif k == "prompt":
            st.append(a["key"], {"type": "user", "timestamp": iso(now), "uuid": str(uuid.uuid4()), "sessionId": session_id(a["key"]),
                                 "message": {"role": "user", "content": a["text"]}})
            st.send(st.body(a["key"], "UserPromptSubmit", prompt=a["text"]))
        elif k == "tool":
            uid = st.use_id(a["key"])
            inp = st.path(a["input"])
            st.open_tools[a["key"]] = (a["tool"], inp, uid)
            st.send(st.body(a["key"], "PreToolUse", tool_name=a["tool"], tool_input=inp, tool_use_id=uid))
        elif k == "tool_end":
            tool, inp, uid = st.open_tools.pop(a["key"])
            st.send(st.body(a["key"], "PostToolUse", tool_name=tool, tool_input=inp, tool_use_id=uid, tool_response={"ok": True}, duration_ms=800))
        elif k == "perm":
            inp = {"command": a["command"], "description": a["description"]}
            uid = st.use_id(a["key"])
            st.send(st.body(a["key"], "PreToolUse", tool_name="Bash", tool_input=inp, tool_use_id=uid))
            st.send(st.body(a["key"], "PermissionRequest", tool_name="Bash", tool_input=inp))
            st.relay.request(a["key"], "Bash", inp)   # the CLI's permission prompt, through the session's channel
        elif k in ("ask_pending", "ask"):
            q = dict(a["question"], multiSelect=False)
            pre = st.body(a["key"], "PreToolUse", tool_name="AskUserQuestion", tool_use_id=a["use_id"], tool_input={"questions": [q]})
            st.send(pre)
            if k == "ask":
                # the synchronous hook: it waits until the page answers (the driver presses the card)
                p = subprocess.Popen([sys.executable, "-I", "-S", str(st.forward), "--ask"], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=st.hook_env)
                p.stdin.write(json.dumps(pre).encode())
                p.stdin.close()
                p.stdin = None
                st.asks[a["use_id"]] = p
        elif k == "ask_answered":
            p = st.asks.pop(a["use_id"])
            out, _ = await asyncio.get_running_loop().run_in_executor(None, p.communicate, None, 60)
            got = json.loads(out) if out else {}
            upd = (got.get("hookSpecificOutput") or {}).get("updatedInput") or {}
            if not upd.get("answers"):
                self.warnings.append(f"ask {a['use_id']}: the hook printed no answer: {out[:200]!r}")
            st.send(st.body(a["key"], "PostToolUse", tool_name="AskUserQuestion", tool_use_id=a["use_id"],
                            tool_input=upd, tool_response={"answers": upd.get("answers", {})}))
        elif k == "denied":
            inp = {"command": a["command"]}
            uid = st.use_id(a["key"])
            st.send(st.body(a["key"], "PreToolUse", tool_name="Bash", tool_input=inp, tool_use_id=uid, permission_mode="auto"))
            st.send(st.body(a["key"], "PermissionDenied", tool_name="Bash", tool_input=inp, tool_use_id=uid, reason=a["reason"], permission_mode="auto"))
        elif k == "idle":
            st.send(st.body(a["key"], "Stop"))
            st.send(st.body(a["key"], "Notification", notification_type="idle_prompt"))
        elif k == "stop":
            st.send(st.body(a["key"], "Stop"))
        elif k == "sub_start":
            st.send(st.body(a["key"], "SubagentStart", agent_id=SUBAGENT[0], agent_type=SUBAGENT[1]))
        elif k == "sub_stop":
            st.send(st.body(a["key"], "SubagentStop", agent_id=SUBAGENT[0], agent_type=SUBAGENT[1],
                            last_assistant_message=self.w["sub_done"], stop_hook_active=False))
        elif k == "talk":
            self.talk(a["frm"], a["to"], a["text"], now - int(a.get("ago", 0) * 1000))
        elif k == "tests_start":
            uid = st.use_id(a["key"])
            inp = {"command": a["command"], "description": "tests"}
            st.open_tools[a["key"]] = ("Bash", inp, uid)
            st.send(st.body(a["key"], "PreToolUse", tool_name="Bash", tool_input=inp, tool_use_id=uid))
            await asyncio.sleep(0.3)   # the call is known before its run starts (robot_tests.py)
            st.progress(a["run"], "run_start", files=1)
            st.runs[a["run"]] = []
        elif k == "tests_case":
            # a case of the sample's own (cases[case]), or one named in full (Ta4: the screen tests chapter T-a ran)
            name = a.get("name") or self.w["cases"][a["case"]]
            f, test = a.get("file", "tests/unit/generated/cart.branches.test.ts"), a.get("test", "cart")
            st.progress(a["run"], "case_start", file=f, test=test, case=name, attempt=1)
            st.progress(a["run"], "case_end", file=f, test=test, case=name, attempt=1, status=a["status"], durationMs=40)
            st.runs[a["run"]].append(a["status"])
        elif k == "tests_end":
            res = st.runs[a["run"]]
            st.progress(a["run"], "run_end", passed=res.count("passed"), failed=res.count("failed"), skipped=0)
            tool, inp, uid = st.open_tools.pop(a["key"])
            st.send(st.body(a["key"], "PostToolUse", tool_name=tool, tool_input=inp, tool_use_id=uid,
                            tool_response={"stdout": f" Tests  {res.count('passed')} passed ({len(res)})", "stderr": ""}))
        elif k == "spec_reset":
            st.spec_reset(a["room"], a["rel"], a["keep"])
        elif k == "worktree":
            st.make_worktree(a["room"], a["branch"], a["name"], a["changes"])
        elif k == "wt_session":
            # a session working in the worktree (its cwd inside it): the board lists the worktree's specs, tagged
            wt = st.worktrees[a["name"]]
            body = {"session_id": a["sid"], "cwd": str(wt), "permission_mode": "default"}
            st.send(dict(body, hook_event_name="SessionStart", source="startup"))
            st.send(dict(body, hook_event_name="UserPromptSubmit", prompt=a["prompt"]))
            if a.get("edit"):
                st.send(dict(body, hook_event_name="PreToolUse", tool_name="Edit", tool_input={"file_path": str(wt / a["edit"])},
                             tool_use_id=st.use_id("w")))
        elif k == "spec_write":
            # a real Write of the real file: the hook before, the file with one more section, the hook after
            path, text = st.spec_grow(a["room"], a["rel"], a["add"])
            uid = st.use_id(a["key"])
            inp = {"file_path": path, "content": text}
            st.send(st.body(a["key"], "PreToolUse", tool_name="Write", tool_input=inp, tool_use_id=uid))
            Path(path).write_text(text, encoding="utf-8")
            st.send(st.body(a["key"], "PostToolUse", tool_name="Write", tool_input=inp, tool_use_id=uid,
                            tool_response={"type": "update", "filePath": path}, duration_ms=300))
        elif k == "settle":
            if advance:
                await self.settle()
        elif k == "door":
            await self.until("() => { const s = window.__dbg.sr(); return s.built && s.door; }", what="the server room's door", advance=True, timeout=60)
            at = (await self.page.evaluate("() => window.__dbg.sr()"))["door"]
            await self.move(at)
            await self.page.mouse.click(at[0], at[1])
            await self.until("() => window.__dbg.sr().open", what="the server room", advance=True, timeout=60)
        elif k == "dbg":
            await self.dbg(a)
        elif k in ("click", "hover", "select"):
            at = await self.point(a["target"], advance)
            await self.move(at)
            if k == "click" and a.get("js"):
                # the element itself pressed where the cursor is (a list drawn again while a session writes can swap
                # the row between the mouse's down and up, and the press then lands on the list, not the row)
                await self.page.evaluate(CLICK_JS, await self.resolved(a["target"]))
            elif k == "click":
                await self.page.mouse.click(at[0], at[1])
            elif k == "select":
                await self.page.select_option(a["target"]["css"], a["value"])
        elif k == "drag":
            # one drag across the page (p0 to p1: fractions of the viewport), e.g. the box 範囲で寄る draws
            vw, vh = self.page.viewport_size["width"], self.page.viewport_size["height"]
            x0, y0, x1, y1 = a["p0"][0] * vw, a["p0"][1] * vh, a["p1"][0] * vw, a["p1"][1] * vh
            await self.move([x0, y0])
            await self.page.mouse.down()
            for n in range(1, 11):
                await self.page.mouse.move(x0 + (x1 - x0) * n / 10, y0 + (y1 - y0) * n / 10)
            await self.page.mouse.up()
            self.cursor = [x1, y1]
        elif k in ("wheel", "dolly"):
            pass   # the frames move it (capture); a prelude has none
        else:
            raise PromoError(f"unknown event kind {k!r}")
        if k in hook_kinds:
            await self.taken_in(before, advance)
        await self.expect(a.get("expect"), advance)
        self.log.append({"kind": k, "at": ev.at})

    async def dbg(self, a):
        call = a["call"]
        if call == "setProject":
            await self.page.evaluate("(id) => window.__dbg.setProject(id)", self.project(a["room"]))
        elif call == "srSelectGroup":
            await self.until("(g) => window.__dbg.srGroups().some((x) => x.id === g)", a["group"], f"group {a['group']}", advance=True)
            await self.page.evaluate("(g) => window.__dbg.srSelectGroup(g)", a["group"])
        elif call == "srSelect":
            # the node chosen through the page's hook; the cursor goes to its tag on the way, as a press would
            tag = await self.page.evaluate("""(id) => { const n = window.__dbg.srTagOf(id); const el = [...document.querySelectorAll('#sr-labels .sr-label:not([hidden])')]
              .find((s) => n && s.textContent.trim() === String(n).trim()); if (!el) return null; const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }""", a["node"])
            if tag:
                await self.move(tag)
            await self.page.evaluate("(id) => window.__dbg.srSelect(id)", a["node"])
        elif call == "press":
            # a button pressed without the cursor (a board's set-up before frame 0: nothing filmed moves to it)
            await self.until("(c) => !!document.querySelector(c)", a["css"], f"the button {a['css']}", advance=True)
            await self.page.evaluate("(c) => document.querySelector(c).click()", a["css"])
        elif call == "openSpec":
            # the spec's sheet on the whiteboard, as a person opens it: the board's button, then the spec's card
            path = str(self.stage.rooms[a["room"]] / a["rel"])
            i = await self.until(FIND_SPEC_JS, [self.project(a["room"]), a["rel"], path], f"the spec {a['rel']}", advance=True) - 1
            await self.page.evaluate("() => document.getElementById('btn-specboard').click()")
            await self.until(f"() => !!document.querySelector('.ov-card[data-idx=\"{i}\"]')", what="the spec's card", advance=True)
            await self.page.evaluate(f"() => document.querySelector('.ov-card[data-idx=\"{i}\"]').click()")
        elif call == "rosterFold":
            # the room's robot list (2.3.20) folded with its own button, when the room shows it open
            await self.until("() => { const r = document.getElementById('roster'); return !!r && !r.hidden; }", what="the room's robot list", advance=True)
            await self.page.evaluate("() => { const b = document.getElementById('roster-fold'); if (b && b.getAttribute('aria-expanded') === 'true') b.click(); }")
            await self.until("() => document.getElementById('roster').classList.contains('roster-folded')", what="the robot list folded", advance=True)
        elif call == "scrollTo":
            # a panel scrolled so an element is in view (Ta4: the side panel's テスト実行, the run's cases by name)
            await self.page.evaluate("(css) => document.querySelector(css).scrollIntoView({block: 'center'})", a["css"])
        elif call == "noop":   # only its expect: a wait before frame 0
            pass
        elif call == "srMigSpeed":
            await self.page.evaluate("(s) => window.__dbg.srMigSpeed(s)", a["speed"])
        elif call == "srZoom":
            await self.page.evaluate("(k) => window.__dbg.srZoom(k)", a["factor"])
        elif call == "srFlowSpeed":
            await self.page.evaluate("(s) => window.__dbg.srFlowSpeed(s)", a["speed"])
        elif call == "srCostPlayMs":
            await self.page.evaluate("(ms) => window.__dbg.srCostPlayMs(ms)", a["ms"])
        else:
            raise PromoError(f"unknown __dbg call {call!r}")

    async def expect(self, spec, advance: bool):
        if not spec:
            return
        name, _, arg = spec.partition(":")
        js = EXPECT[name]
        if js is None:
            return
        if name == "solo":
            arg = self.project(arg)
        elif name in ("picked", "card"):
            arg = await self.label(arg)
        await self.until(js, arg or None, spec, advance)

    async def resolved(self, target: dict):
        """A target as POINT_JS takes it, or a point already ([x, y]) for a robot."""
        if "robot" in target:
            return {"css": "#scene-canvas"}
        t = dict(target)
        if "room_tag" in t:
            t = {"css": f".tag.room[data-set-project='{self.project(t['room_tag'])}']"}
        elif "bubble" in t:
            t = {"css": f"[data-wait-robot='{await self.label(t['bubble'])}']"}
        elif "session_row" in t:
            t = {"css": f"#sessions [data-robot-open='{await self.label(t['session_row'])}']"}
        elif "talk_row" in t:
            t = {"css": "#rb .talk-row", "text": self.w["names"][t["talk_row"]]}
        elif "robot_tag" in t:   # the robot's own name tag (a press on it selects the robot, as on its body), where it shows
            t = {"css": f"#tags .tag[data-robot='{await self.label(t['robot_tag'])}']", "visible": True}
        return t

    async def hittable(self, target: dict) -> bool:
        if "robot" in target:
            return True
        return bool(await self.page.evaluate(HIT_JS, await self.resolved(target)))

    async def point(self, target: dict, advance: bool):
        if "robot" in target:
            lab = await self.label(target["robot"])
            return [round(v) for v in await robot_point(self.page, lab)]
        return await self.until(POINT_JS, await self.resolved(target), f"the target {target}", advance)

    async def move(self, at):
        self.cursor = [float(at[0]), float(at[1])]
        await self.place_cursor()

    async def place_cursor(self):
        x, y = self.cursor
        await self.page.mouse.move(x, y)
        await self.page.evaluate("([x, y]) => { const c = document.getElementById('promo-cursor'); if (c) c.style.transform = `translate(${x}px, ${y}px)`; }", [x, y])

    def talk(self, frm: str, to: str, text: str, at: int):
        """A SendMessage from `frm` to `to` and its read on the other side, as the talk suite writes them."""
        st, w = self.stage, self.w
        use = st.use_id(frm)
        msg_id = f"promo-{use}"
        st.append(frm, {"type": "assistant", "timestamp": iso(at), "uuid": str(uuid.uuid4()),
                        "message": {"id": f"msg_{use}", "content": [{"type": "tool_use", "id": use, "name": "SendMessage",
                                                                     "input": {"to": w["names"][to], "message": text, "summary": text[:20]}}]}},
                  {"type": "user", "timestamp": iso(at + 100), "uuid": str(uuid.uuid4()),
                   "toolUseResult": {"success": True, "message": "ok", "msg_id": msg_id},
                   "message": {"content": [{"type": "tool_result", "tool_use_id": use, "content": "ok"}]}})
        origin = {"kind": "peer", "from": f"uds:/tmp/promo-socks/{st.pids[frm]}.sock", "verifiedPeerPid": st.pids[frm],
                  "msg_id": msg_id, "name": w["names"][frm], "fromMode": "prompting", "body": text}
        st.append(to, {"type": "user", "isMeta": True, "timestamp": iso(at + 800), "uuid": str(uuid.uuid4()), "origin": origin,
                       "message": {"content": f"<cross-session-message>\n{text}\n</cross-session-message>"}})

    # ---- the frames ----
    async def capture(self, events, start: float, end: float, out: Path) -> int:
        out.mkdir(parents=True, exist_ok=True)
        for old in out.glob("*.png"):
            old.unlink()
        n = frame_count(start, end)
        pending = sorted(events, key=lambda e: e.at)
        glides: dict = {}      # id(event) -> (t0, from, to)
        wheels: list = []      # [t0, t1, dy per frame, point]
        dollies: list = []     # [first frame, frames, the camera's whole distance factor] (the server room's camera, srZoom)
        stop = asyncio.Event()
        keeper = asyncio.create_task(self.keep_present(stop))
        # the prelude let the page's clock fall behind the server's: Date set to now (no timer fires), so the times
        # the server sends (a question's deadline, an event's time) read as they would in a browser
        await self.page.clock.set_system_time(time.time())
        try:
            for i in range(n):
                t = frame_time(start, i)
                if self.sky_ms is not None:
                    await self.page.evaluate("(ms) => window.__dbg.setClock(ms)", self.sky_ms + int((t - start) * 1000))
                # the cursor glides to the next press in the GLIDE_SEC before it
                for ev in pending:
                    if ev.kind in ("click", "hover", "select", "wheel") and t >= ev.at - GLIDE_SEC and id(ev) not in glides:
                        try:
                            to = await self.point(ev.args["target"], advance=False) if ev.kind != "wheel" or ev.args.get("target") else self.cursor
                        except PromoError:
                            continue   # not on the page yet: tried again next frame
                        glides[id(ev)] = (t, list(self.cursor), list(to))
                for ev in pending:
                    g = glides.get(id(ev))
                    if g and t < ev.at:
                        f = min(1.0, (t - g[0]) / max(1e-6, ev.at - g[0]))
                        f = f * f * (3 - 2 * f)
                        self.cursor = [g[1][0] + (g[2][0] - g[1][0]) * f, g[1][1] + (g[2][1] - g[1][1]) * f]
                # the events whose time has come (a press waits for its `ready`)
                fired = []
                for ev in pending:
                    if ev.at > t + 1e-9:
                        break
                    if ev.args.get("until") is not None and t > ev.args["until"]:
                        fired.append(ev)   # a press that was only needed if the page still asked for it by then
                        continue
                    page_event = ev.kind in ("click", "hover", "select", "dbg")
                    if page_event and t < self.last_press + MIN_GAP_SEC:
                        continue
                    if ev.args.get("ready") and not await self.page.evaluate(ev.args["ready"], ev.args.get("arg")):
                        continue
                    # a press waits for its target to be on the page (a card opens after the camera's flight), up to
                    # TARGET_LATE_SEC of video; past that it fires and fails with the target's name
                    if ev.kind in ("click", "hover", "select") and t < ev.at + TARGET_LATE_SEC \
                            and not await self.hittable(ev.args["target"]):
                        continue
                    if page_event:
                        self.last_press = t
                    if ev.kind == "dolly":
                        frames = max(1, int(round(ev.args["dur"] * FPS)))
                        dollies.append([i, frames, ev.args["factor"]])
                        self.log.append({"kind": "dolly", "at": ev.at, "frame": i})
                    elif ev.kind == "wheel":
                        frames = max(1, int(round(ev.args["dur"] * FPS)))
                        to = glides.get(id(ev), (0, 0, self.cursor))[2]
                        self.cursor = list(to)
                        wheels.append([t, t + ev.args["dur"], ev.args["dy"] / frames, to])
                        self.log.append({"kind": "wheel", "at": ev.at, "frame": i})
                    else:
                        await self.fire(ev, advance=False)
                        self.log[-1]["frame"] = i
                    fired.append(ev)
                for ev in fired:
                    if ev in pending:
                        pending.remove(ev)
                    if ev.args.get("ends"):   # the presses of that group are no longer wanted
                        pending = [p for p in pending if p.args.get("group") != ev.args["ends"]]
                await self.place_cursor()
                for wh in wheels:
                    if wh[0] <= t < wh[1]:
                        await self.page.mouse.wheel(0, wh[2])
                for first, frames, factor in dollies:   # eased: slow out of the wide shot and slow into the close one
                    j = i - first
                    if 0 <= j < frames:
                        ease = lambda x: x * x * (3 - 2 * x)  # noqa: E731
                        step = factor ** (ease((j + 1) / frames) - ease(j / frames))
                        await self.page.evaluate("(k) => window.__dbg.srZoom(k)", step)
                await self.page.screenshot(path=str(out / f"{i:05d}.png"))
                self.frames_done = i + 1
                # the page's clock: this frame's share of a second, exact over every 30 frames
                await self.page.clock.run_for(round((i + 1) * 1000 / FPS) - round(i * 1000 / FPS))
        finally:
            stop.set()
            await keeper
        for ev in pending:
            self.warnings.append(f"not fired before the chapter ended: {ev.kind} at {ev.at} {ev.args.get('target', '')}")
        return n

    async def keep_present(self, stop: asyncio.Event):
        while not stop.is_set():
            try:
                await self.page.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
            except Exception:  # noqa: BLE001 - the page closing ends it
                return
            try:
                await asyncio.wait_for(stop.wait(), PRESENCE_EVERY_SEC)
            except asyncio.TimeoutError:
                pass


async def capture_chapter(pw, chapter, bounds: tuple, out_root: Path, lang: str, jui_root: Path, demo_shop: Path,
                          theme: str = "dark", sky_time: str | None = "14:00", keep: bool = False) -> dict:
    """Capture one chapter into out_root/<lang>/<id>/%05d.png; returns its manifest (also written beside the frames)."""
    start, end = bounds
    out = Path(out_root) / lang / chapter.id
    res = {"chapter": chapter.id, "lang": lang, "start": start, "end": end, "frames": 0, "ok": False, "jui_root": str(jui_root)}
    missing = missing_features(jui_root, chapter.needs, lang)
    if missing:
        res["error"] = "the tree lacks: " + "; ".join(missing)
        return res
    stage = browser = drv = None
    try:
        stage = Stage(lang, jui_root, demo_shop, keep=keep, name=chapter.id)
        stage.start()
        browser = await pw.chromium.launch(args=LAUNCH_ARGS)
        viewport = chapter.viewport or VIEWPORT
        ctx = await browser.new_context(viewport=viewport, device_scale_factor=1, color_scheme=theme, reduced_motion="no-preference")
        page = await ctx.new_page()
        watch = Watch(origin=stage.url)
        watch.attach(page, chapter.id)
        # install() alone keeps time flowing at the wall clock's pace; paused, it moves only when run_for() moves it.
        # The Python API takes seconds (a number in ms put the page's Date ~1000x into the future: a question's
        # countdown read 0 s at once)
        t0 = time.time()
        await page.clock.install(time=t0)
        await page.add_init_script(SEEDED_RANDOM_JS)
        await page.clock.pause_at(t0 + 1)
        drv = Driver(page, stage, lang, watch, sky_time)
        if chapter.viewport:   # a board has no press: the cursor waits off the page
            drv.cursor = [viewport["width"] + 60.0, viewport["height"] + 60.0]
        await drv.boot(chapter.needs)
        await drv.prelude(chapter.prelude)
        res["frames"] = await drv.capture(chapter.events, start, end, out)
        res["ok"] = res["frames"] == frame_count(start, end)
        res["events"] = drv.log
        res["warnings"] = drv.warnings
        res["console"] = watch.console
        res["foreign"] = watch.foreign
    except Exception as e:  # noqa: BLE001 - the chapter fails with its reason; the next one is still captured
        res["error"] = f"{type(e).__name__}: {e}" if not isinstance(e, PromoError) else str(e)
        if drv is not None:
            res.update(frames=drv.frames_done, events=drv.log, warnings=drv.warnings)
    finally:
        if browser:
            await browser.close()
        if stage:
            stage.stop()
    if res["frames"]:
        (out / "manifest.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return res


# ---- --measure-fps: the floor with every robot, on the page's own clock ----

# every frame's time (the robots' update calls it at the end of each frame: 80-dbg.js afterFrame, the hook
# frame_gaps.py and waits.frame_log_js record with), kept for one window of sampling
FRAME_TIMES_JS = """() => { window.__promoFrames = []; window.__dbg.afterFrame(() => { window.__promoFrames.push(performance.now()); }); return true; }"""
FRAME_STOP_JS = """() => { window.__dbg.afterFrame(null); const t = window.__promoFrames || []; return t.slice(1).map((v, i) => v - t[i]); }"""
MEASURE_SEC = 10.0
# --gpu: a headed Chromium drawing through the machine's GPU (ANGLE on Metal), not the e2e's software GL
GPU_ARGS = ["--use-gl=angle", "--use-angle=metal", "--ignore-gpu-blocklist", "--enable-gpu-rasterization"]
RENDERER_JS = """() => { const gl = document.createElement('canvas').getContext('webgl'); if (!gl) return null;
  const x = gl.getExtension('WEBGL_debug_renderer_info');
  return x ? { vendor: gl.getParameter(x.UNMASKED_VENDOR_WEBGL), renderer: gl.getParameter(x.UNMASKED_RENDERER_WEBGL) } : null; }"""


def percentiles(gaps: list) -> dict:
    """p50 / p90 / max of frame intervals (ms), nearest rank."""
    if not gaps:
        return {"frames": 0, "p50": None, "p90": None, "max": None}
    s = sorted(gaps)
    rank = lambda q: s[min(len(s) - 1, max(0, int(round(q * len(s))) - 1))]  # noqa: E731
    return {"frames": len(s) + 1, "p50": round(rank(0.5), 1), "p90": round(rank(0.9), 1), "max": round(s[-1], 1)}


async def measure_fps(pw, lang: str, jui_root: Path, demo_shop: Path, out: Path, theme: str = "dark", sec: float = MEASURE_SEC,
                      gpu: bool = False) -> dict:
    """The floor with all SESSIONS in real time (no fake clock), at 1920x1080: frame intervals for `sec` seconds far
    (the whole floor) and near (demo-shop up close). Headless under the e2e's software GL, or with gpu a headed window
    through the GPU (the renderer WebGL reports is kept; a software one stops the measurement). Written to
    out/fps-<lang>[-gpu].json."""
    from viz_promo.timeline import chapters, up_close
    script = chapters(lang)["hook"]
    res = {"lang": lang, "jui_root": str(jui_root), "robots": len(SESSIONS), "sec": sec, "viewport": VIEWPORT, "gpu": gpu}
    stage = browser = None
    try:
        stage = Stage(lang, jui_root, demo_shop, name="fps")
        stage.start()
        browser = await (pw.chromium.launch(headless=False, args=GPU_ARGS) if gpu else pw.chromium.launch(args=LAUNCH_ARGS))
        ctx = await browser.new_context(viewport=VIEWPORT, device_scale_factor=1, color_scheme=theme, reduced_motion="no-preference")
        page = await ctx.new_page()
        watch = Watch(origin=stage.url)
        watch.attach(page, "fps")
        res["webgl"] = await page.evaluate(RENDERER_JS)
        if gpu and not (res["webgl"] and "swiftshader" not in str(res["webgl"]).lower() and "llvmpipe" not in str(res["webgl"]).lower()):
            raise PromoError(f"no GPU rendering: WebGL reports {res['webgl']}")
        drv = Driver(page, stage, lang, watch, None, fake_clock=False)
        await drv.boot(())
        await drv.prelude(script.prelude)
        res["robotsShown"] = await page.evaluate("() => window.__dbg.robots.length")
        for view, events in (("far", []), ("near", up_close("demo-shop"))):
            for ev in events:
                await drv.fire(ev, advance=True)
            if events:
                await drv.settle()
            await page.evaluate(FRAME_TIMES_JS)
            await asyncio.sleep(sec)
            res[view] = percentiles(await page.evaluate(FRAME_STOP_JS))
        res["console"] = watch.console
        res["warnings"] = drv.warnings
    except Exception as e:  # noqa: BLE001 - reported, as a chapter's failure is
        res["error"] = f"{type(e).__name__}: {e}"
    finally:
        if browser:
            await browser.close()
        if stage:
            stage.stop()
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / f"fps-{lang}{'-gpu' if gpu else ''}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return res
