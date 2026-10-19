"""Shared helpers for the browser tests (Playwright, async). Not imported by pytest.

The headless renderer draws 1–3 frames a second (plan 10 §6), so the helpers wait for states, never for time,
except `settle`, which only lets a camera tween finish before the next click.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import re
import traceback
from dataclasses import dataclass, field
from pathlib import Path

# ---- the times a fixture writes (2.3.5; ticket 2026-10-20-jui-viz-hist-wide-robot-margin-red-on-integrate) ----
# A session's start is its transcript's first record, and the page draws a robot tired 8 hours after that (20-core.js
# isTired, a wider pose). A fixture dated on a fixed day made the robots turn tired at a fixed hour of the clock, and
# what a suite checked depended on when it ran. Fixtures write their times through stamp() (or ago()), never as a
# fixed date: tests/test_viz_e2e_fixture_times.py fails on a fixed one outside its allowlist.
RUN_BASE = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0) - datetime.timedelta(hours=1)


def stamp(ts: str) -> str:
    """A fixture time written as 09:00 plus an offset on any day ("2026-10-19T09:47:10Z") → that offset after
    RUN_BASE (an hour before the run): the order and the gaps are kept, the day and the hour are the run's."""
    t = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
    offset = t - t.replace(hour=9, minute=0, second=0)
    assert offset >= datetime.timedelta(0), f"a fixture time is written as 09:00 plus an offset: {ts}"
    return (RUN_BASE + offset).strftime("%Y-%m-%dT%H:%M:%SZ")


def ago(hours: float = 0, minutes: float = 0) -> str:
    """A time this long before now, for a fixture that means it (a session 9 hours old is meant to be tired)."""
    t = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0) - datetime.timedelta(hours=hours, minutes=minutes)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")

# Taken out of every environment a suite gives its server and its hooks: each would point the throwaway server at the
# real one's state (its folder, the progress a runner writes, the saved results) — 10-18.
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
# The real server's progress folder (cd's gate, 10-18: driver web's jest once wrote 480 files there from a test).
# Every suite runs in a throwaway HOME; after each, this folder must not have grown. The folder is a parameter so a
# pytest arm can show the gate turns red on a temporary one (tests/test_viz_e2e_gate.py) without writing to the real.
REAL_PROGRESS = Path.home() / ".local" / "state" / "jui-viz" / "test-progress"


def progress_count(folder: Path = REAL_PROGRESS) -> int:
    return len(list(folder.glob("*.jsonl"))) if folder.is_dir() else 0


def progress_grew(suite: str, before: int, folder: Path = REAL_PROGRESS) -> str | None:
    now = progress_count(folder)
    return f"{suite}: the real test-progress folder grew ({before} -> {now})" if now > before else None


@contextlib.contextmanager
def suite_guard(name: str, failures: list, out: Path | None = None):
    """Run one suite's block in run.py: an exception out of it (a wait's WaitTimeout, a crash) becomes one FAIL line
    and the run goes on to the next suite (ticket 2026-10-20-jui-viz-e2e-one-suite-exception-stops-the-run: one
    timeout in props ended the whole run with a traceback, no FAIL line, and no later suite ran). The traceback is
    kept in <out>/<name>-traceback.txt. KeyboardInterrupt still stops the run."""
    try:
        yield
    except Exception as e:  # noqa: BLE001 - every exception, so the next suite runs
        first = (str(e).splitlines() or [""])[0][:2000]
        failures.append(f"{name}: the suite stopped: {type(e).__name__}: {first}")
        if out is not None:
            try:
                Path(out).mkdir(parents=True, exist_ok=True)
                (Path(out) / f"{name}-traceback.txt").write_text(traceback.format_exc())
            except OSError:
                pass


LAUNCH_ARGS = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
DESKTOP = {"viewport": {"width": 1440, "height": 900}, "device_scale_factor": 1}
PHONE = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 2, "is_mobile": True, "has_touch": True}

# Console lines that are not the page's: the software GL renderer's performance notes.
NOISE = re.compile(r"GL Driver Message|GPU stall due to ReadPixels|Automatic fallback to software WebGL")


@dataclass
class Watch:
    """What a page said and asked for while a suite ran."""
    origin: str
    console: list = field(default_factory=list)
    foreign: list = field(default_factory=list)
    csp: list = field(default_factory=list)

    def attach(self, page, label: str):
        def on_console(m):
            if m.type in ("error", "warning") and not NOISE.search(m.text):
                self.console.append(f"[{label} {m.type}] {m.text}")
                if "Content Security Policy" in m.text or "Content-Security-Policy" in m.text:
                    self.csp.append(m.text)
        page.on("console", on_console)
        page.on("pageerror", lambda e: self.console.append(
            f"[{label} pageerror] {e} @ " + " | ".join(l.strip() for l in (getattr(e, "stack", "") or "").splitlines()[1:4])))

        def on_request(r):
            url = r.url
            if not (url.startswith(self.origin) or url.startswith("data:") or url.startswith("blob:")
                    or url.startswith(self.origin.replace("http://", "ws://"))):
                self.foreign.append(url)
        page.on("request", on_request)
        page.on("websocket", lambda ws: on_request(type("R", (), {"url": ws.url})()))


async def new_page(browser, watch: Watch, label: str, **opts):
    page = await browser.new_page(**opts)
    watch.attach(page, label)
    return page


async def ready(page):
    """The view is up: the e2e hook exists and the robots are built (or 3D is off)."""
    await page.wait_for_function(
        "() => !!(window.__dbg && window.__dbg.robots && (window.__dbg.robots.length || document.body.dataset.mode === 'live' || document.querySelector('.nogl')))",
        timeout=30000)


async def freeze(page, t: float):
    """Demo only: jump the script to t seconds and pause it there."""
    await page.evaluate("(t) => window.__dbg.setSim(t)", t)
    if (await page.get_attribute("#btn-play", "aria-pressed")) != "true":
        await page.click("#btn-play")
    await page.wait_for_function("() => document.querySelector('#btn-play').getAttribute('aria-pressed') === 'true'")
    await page.evaluate("(t) => window.__dbg.setSim(t)", t)
    await page.wait_for_timeout(700)  # one panel pass (250 ms) and one board pass (200 ms), with room


async def shown(page, el_id: str, timeout=20000):
    await page.wait_for_function(
        "(x) => { const el = document.getElementById(x); return !el.hidden && el.classList.contains('show') && getComputedStyle(el).opacity === '1'; }",
        arg=el_id, timeout=timeout)


async def gone(page, el_id: str, timeout=20000):
    await page.wait_for_function("(x) => document.getElementById(x).hidden", arg=el_id, timeout=timeout)


async def settle(page):
    await page.wait_for_timeout(2600)


async def board_point(page, which):
    """Screen point of the shop spec board's header ('board'), the cork board ('tasks') or spec tile number n."""
    return await page.evaluate("""(w) => {
      const d = window.__dbg, c = document.getElementById('scene-canvas').getBoundingClientRect();
      let v;
      if (w === 'board') v = d.sbPoint(d.SB.W / 2, 40);
      else if (w === 'tasks') v = new d.THREE.Vector3(d.KB.cx, d.KB.cy, d.KB.z);
      else { const t = d.sbTile(w); v = d.sbPoint(t.x + d.SB.tw / 2, t.y + d.SB.th / 2); }
      v.project(d.camera);
      return [c.left + ((v.x + 1) / 2) * c.width, c.top + ((1 - v.y) / 2) * c.height];
    }""", which)


async def robot_point(page, rid: str):
    return await page.evaluate("""(rid) => {
      const d = window.__dbg, c = document.getElementById('scene-canvas').getBoundingClientRect();
      const R = d.robots.find((x) => x.def.id === rid);
      const v = R.robot.root.position.clone().add(new d.THREE.Vector3(0, 1.0, 0)).project(d.camera);
      return [c.left + ((v.x + 1) / 2) * c.width, c.top + ((1 - v.y) / 2) * c.height];
    }""", rid)


def squash(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True)
