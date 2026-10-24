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
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from children import children, stop_children_since

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


def desk_pins_js(pins) -> str:
    """An init script that puts robots' desks where an arm needs them (ticket
    2026-10-20-jui-viz-e2e-callbell-dialog-wait-flaky): a desk is drawn from a seed of the robot's server id and the
    room's id, and the room's id is the sha1 of the project's root, which lies under --out. So the --out of a run
    decided where a desk stood, and one --out put a robot in front of the call bell: the press opened the robot's card.
    This writes the page's own desk memory (30-source-live.js DESK_MEM: localStorage agent-view:desks,
    "<project id>|<server id>" -> [dx, dz] in the floor-view room's coordinates; takeSeat keeps a remembered desk that is
    still clear) before the page loads. pins: (cwd as the hooks send it, the robot's server id, [dx, dz]). The arm
    then checks the desk is there (window.__dbg.seats()), so a pin that did not take is a failure, not a quiet draw."""
    desks = {f"{project_id(cwd)}|{rid}": list(spot) for cwd, rid, spot in pins}
    return f"try {{ localStorage.setItem('agent-view:desks', {json.dumps(json.dumps(desks))}); }} catch (e) {{}}"


def project_id(cwd) -> str:
    """The room's id the server gives a cwd (rooms.py: the sha1 of find_root's root, 12 hex)."""
    import hashlib
    import sys
    jt = str(Path(__file__).resolve().parents[2])
    if jt not in sys.path:
        sys.path.insert(0, jt)
    from jui_cli.viz.rooms import find_root
    return hashlib.sha1(find_root(str(cwd))[0].encode("utf-8")).hexdigest()[:12]


# Taken out of every environment a suite gives its server and its hooks: each would point the throwaway server at the
# real one's state (its folder, the progress a runner writes, the saved results) — 10-18.
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
# The real server's progress folder (the orchestrator's gate, 10-18: driver web's jest once wrote 480 files there from a test).
# Every suite runs in a throwaway HOME; after each, no file of this run may have appeared there. The folder is a
# parameter so a pytest arm can show the gate turns red on a temporary one (tests/test_viz_e2e_gate.py) without
# writing to the real.
REAL_PROGRESS = Path.home() / ".local" / "state" / "jui-viz" / "test-progress"
# What marks a file as this run's: the run ids its suites write records under (e2e_run_id) and its output folder,
# which holds every throwaway HOME. A file without one is another lane's test run on the real HOME, which the
# folder's count alone took for a leak (2.3.21: 405 -> 412 from a web run of another lane at the same time).
E2E_MARKS: set[str] = set()


def e2e_run_id() -> str:
    """A progress run id for a suite's records, kept as one of this run's marks."""
    run = str(uuid.uuid4())
    E2E_MARKS.add(run)
    return run


def progress_count(folder: Path = REAL_PROGRESS) -> dict[str, int]:
    """The folder's progress files and their sizes (what progress_grew compares against)."""
    return {f.name: f.stat().st_size for f in folder.glob("*.jsonl")} if folder.is_dir() else {}


def progress_grew(suite: str, before: dict[str, int], folder: Path = REAL_PROGRESS) -> str | None:
    """The files new or grown since before that carry one of this run's marks, in their name or their text."""
    ours = []
    for name, size in sorted(progress_count(folder).items()):
        if before.get(name) == size:
            continue
        try:
            text = name + "\n" + (folder / name).read_text(errors="replace")
        except OSError:
            continue
        if any(m in text for m in E2E_MARKS):
            ours.append(name)
    return f"{suite}: this run wrote to the real test-progress folder ({len(ours)}: {', '.join(ours[:3])})" if ours else None


#: how long a suite's leftover process has after INT before KILL (the arms make it short)
STOP_WAIT_S = 10.0


@contextlib.contextmanager
def suite_guard(name: str, failures: list, out: Path | None = None):
    """Run one suite's block in run.py: an exception out of it (a wait's WaitTimeout, a crash) becomes one FAIL line
    and the run goes on to the next suite (ticket 2026-10-20-jui-viz-e2e-one-suite-exception-stops-the-run: one
    timeout in props ended the whole run with a traceback, no FAIL line, and no later suite ran). The traceback is
    kept in <out>/<name>-traceback.txt. KeyboardInterrupt still stops the run. However it ends, the processes the suite
    started and left running are stopped (stop_children_since)."""
    before = children()
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
    finally:
        left = stop_children_since(before, STOP_WAIT_S)
        if left:
            print(f"  {name}: stopped {len(left)} process(es) the suite left: {', '.join(map(str, left))}", flush=True)



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
    await page.add_init_script(CANVAS_TEXT_JS)   # the canvas's words, for screen_check (defined below)
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


def expect_demo_file(language: str) -> Path:
    """The demo's expected results in the run's language: expect_demo.json (Japanese, recorded from the prototype), or
    expect_demo.<language>.json — the same results in that language's words, taken from a run of the port
    (<out>/demo-results.json) and held to the Japanese one's shape, numbers and order by
    tests/test_viz_demo_expect_languages.py (ticket 2026-10-21-viz-english-screen-checks §11: the demo's 140 checks
    compared the page with the Japanese words)."""
    here = Path(__file__).resolve().parent
    return here / ("expect_demo.json" if language in ("", "ja") else f"expect_demo.{language}.json")


# ---- the English screen (ticket 2026-10-21-viz-english-screen-checks) ---------------------------------------------
# The page's words come from the language's table; a key it lacks or a slot left unfilled is a console warning (tl in
# 05-i18n.js), which every suite already fails on. What a console cannot say is what the reader sees: a key drawn as
# itself, Japanese left on an English page, a button or a sign whose words do not fit. screen_check reads them from
# the page; shot keeps a picture of it with that report, for lang_sheet.py's side-by-side sheet (en and ja).

#: Every text a canvas draws, recorded before the page's own code runs (textures drawn at load too): its words, where
#: it starts and ends in the canvas, the canvas's width. An approximation — a canvas transform is not followed.
CANVAS_TEXT_JS = """(() => {
  if (window.__canvasText) return;
  const rec = window.__canvasText = [];
  const P = CanvasRenderingContext2D.prototype, fill = P.fillText;
  P.fillText = function (text, x, y, maxWidth) {
    try {
      if (rec.length < 20000) {
        const s = String(text), w = this.measureText(s).width, a = this.textAlign;
        const left = a === 'center' ? x - w / 2 : (a === 'right' || a === 'end') ? x - w : x;
        rec.push({ text: s, left: Math.round(left), right: Math.round(left + w), canvas: this.canvas.width,
                   font: this.font, maxWidth: maxWidth === undefined ? null : maxWidth });
      }
    } catch (err) { /* never in the page's way */ }
    return fill.apply(this, arguments);
  };
})();"""

#: The page as read: keys drawn as themselves (a failure), Japanese on an English page, elements whose words do not
#: fit, canvas words past the canvas or cut with "…" (reported, for eyes). Hidden elements are not read.
SCREEN_REPORT_JS = r"""() => {
  const out = { lang: document.documentElement.lang || '', keys: [], japanese: [], overflow: [], overlap: [], canvas: [] };
  let strings = {};
  try { strings = JSON.parse(document.getElementById('jui-viz-strings').textContent).strings || {}; } catch (err) { /* none */ }
  const KEY = /^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$/, JA = /[぀-ヿ㐀-鿿！-｠]/;
  const en = out.lang === 'en';
  const away = (el) => !el || el.closest('script, style, template, #jui-viz-strings') || !el.getClientRects().length;
  const where = (el) => el.id ? `#${el.id}` : `${el.tagName.toLowerCase()}${el.classList.length ? '.' + [...el.classList].join('.') : ''}`;
  const seen = new Set();
  const note = (list, v) => { if (!seen.has(v) && list.length < 200) { seen.add(v); list.push(v); } };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const t = n.nodeValue.trim();
    if (!t || away(n.parentElement)) continue;
    if (KEY.test(t) && t in strings) note(out.keys, `${where(n.parentElement)}: ${t}`);
    if (en && JA.test(t)) note(out.japanese, `${where(n.parentElement)}: ${t.slice(0, 80)}`);
  }
  for (const el of document.querySelectorAll('[title], [aria-label], [placeholder], [alt]')) {
    if (away(el)) continue;
    for (const a of ['title', 'aria-label', 'placeholder', 'alt']) {
      const v = el.getAttribute(a);
      if (!v) continue;
      if (KEY.test(v) && v in strings) note(out.keys, `${where(el)}[${a}]: ${v}`);
      if (en && JA.test(v)) note(out.japanese, `${where(el)}[${a}]: ${v.slice(0, 80)}`);
    }
  }
  for (const el of document.querySelectorAll('button, .chip, [role=tab], h1, h2, h3, h4, label, th, .wb-btn, .pill')) {
    if (away(el)) continue;
    const over = el.scrollWidth - el.clientWidth;
    if (over > 1) out.overflow.push({ at: where(el), text: el.textContent.trim().slice(0, 60), over });
  }
  // two boxes of words in one parent that cover each other (a line wrapped longer in one language runs into its
  // neighbour: the scene's hint and the demo clock on a phone in English). A box of words holds words of its own (a
  // text node of its own), is not inline (an inline's box spans its wrapped lines) and is not one of the 3D's tags
  // (#tags: they follow their robots and may cross); a layer over the scene (the card, the tags' layer) has none.
  const own = (el) => [...el.childNodes].some((n) => n.nodeType === 3 && n.nodeValue.trim());
  const worded = (el) => !away(el) && own(el) && !el.closest('#tags') && getComputedStyle(el).display !== 'inline'
    && getComputedStyle(el).visibility !== 'hidden';
  for (const parent of document.querySelectorAll('body, body *')) {
    const kids = [...parent.children].filter(worded);
    for (let i = 0; i < kids.length; i++) {
      const a = kids[i].getBoundingClientRect();
      for (let j = i + 1; j < kids.length; j++) {
        const b = kids[j].getBoundingClientRect();
        const w = Math.min(a.right, b.right) - Math.max(a.left, b.left), h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        if (w > 2 && h > 2 && out.overlap.length < 100) {
          out.overlap.push({ a: where(kids[i]), b: where(kids[j]), text: [kids[i].textContent.trim().slice(0, 40), kids[j].textContent.trim().slice(0, 40)], w: Math.round(w), h: Math.round(h) });
        }
      }
    }
  }
  const drawn = new Set();   // a texture is drawn again and again: one line for each words on each canvas width
  for (const c of window.__canvasText || []) {
    const id = `${c.text}\u0000${c.canvas}`;
    if (drawn.has(id)) continue;
    if (c.right > c.canvas + 1 || c.left < -1 || /…$/.test(c.text)) { drawn.add(id); out.canvas.push(c); }
  }
  return out;
}"""


async def screen_hooks(page):
    """For a page a suite opens itself (not through new_page): record the canvas's words from the start."""
    await page.add_init_script(CANVAS_TEXT_JS)


async def screen_check(page, tag: str, failures: list) -> dict:
    """Read the page as the reader sees it. A key drawn as itself is a failure in either language; the rest (Japanese
    on an English page, words that do not fit, canvas words past the canvas or cut) is returned for the sheet."""
    got = await page.evaluate(SCREEN_REPORT_JS)
    for k in got["keys"]:
        failures.append(f"{tag}: a key of the table on the page as itself: {k}")
    return got


async def shot(page, name: str, out, failures: list, clip: dict | None = None) -> dict:
    """A picture of the page for lang_sheet.py with screen_check's report: <out>/shots/<name>.png and its line in
    <out>/shots/shots.json (the language the run was in, the report). Returns the report."""
    import os
    folder = Path(out) / "shots"
    folder.mkdir(parents=True, exist_ok=True)
    report = await screen_check(page, f"shot {name}", failures)
    await page.screenshot(path=str(folder / f"{name}.png"), clip=clip)
    index = folder / "shots.json"
    data = json.loads(index.read_text(encoding="utf-8")) if index.exists() else {}
    data[name] = {"language": os.environ.get("JUI_VIZ_LANGUAGE", ""), "report": report}
    index.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


_STRINGS = None


def T(key: str, **params) -> str:
    """The page's words for ``key`` in the run's language (JUI_VIZ_LANGUAGE, as the server under test reads it), its
    slots filled: a suite compares the page with the table, not with the words of one language (ticket
    2026-10-21-viz-english-screen-checks §2c), so it reads the same in Japanese and in English. A key the table lacks
    raises — a suite never waits for words that cannot appear."""
    global _STRINGS
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from jui_cli.viz import i18n
    if _STRINGS is None:
        _STRINGS = i18n.load()
    if key not in _STRINGS.table:
        raise KeyError(f"no words for {key!r} in the {_STRINGS.language} table")
    return i18n.lookup(_STRINGS, key, params)


def T_pattern(key: str, **params) -> "re.Pattern":
    """T(key) as a regular expression: the slots given filled (escaped; a compiled pattern goes in as it is), every
    other slot any words — for a check that knows part of what the page says (a notification's tool, not the
    session's name; the time to a reset, not its last minute)."""
    import re as _re
    marker = "\x00"
    raw = {k: v.pattern for k, v in params.items() if isinstance(v, _re.Pattern)}
    filled = {k: v for k, v in params.items() if k not in raw}
    words = T(key, **{**{s: marker + s + marker for s in _re.findall(r"\{(\w+)\}", _template(key)) if s not in filled}, **filled})
    parts = words.split(marker)
    return _re.compile("".join(_re.escape(p) if i % 2 == 0 else raw.get(p, ".+?") for i, p in enumerate(parts)))


def _template(key: str) -> str:
    """The key's words as the table has them (its {slots} unfilled; a count's forms joined)."""
    T(key)   # loads the table, raises for a key it lacks
    value = _STRINGS.table[key]
    return " ".join(value.values()) if isinstance(value, dict) else value


def T_head(key: str, slot: str, **params) -> str:
    """T(key)'s words up to {slot} (the slot and what follows left out): for words whose end the suite cannot know (a
    time, a summary) and a check that reads their start."""
    return T(key, **{**params, slot: "\x00"}).split("\x00")[0]


_DEMO_TALK = None


def demo_talk(key):
    """The demo's talk words for ``key`` in the run's language (tools/viz_e2e/talk_demo_gen.py WORDS, English when the
    language has none — as 31-talk-demo-data.js picks its set). Read from the generator's source, never run: importing
    it writes the data file."""
    global _DEMO_TALK
    import ast
    import os
    if _DEMO_TALK is None:
        tree = ast.parse((Path(__file__).resolve().parent / "talk_demo_gen.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "WORDS" for t in n.targets))
        _DEMO_TALK = ast.literal_eval(node.value)
    lang = os.environ.get("JUI_VIZ_LANGUAGE", "") or "en"
    words = _DEMO_TALK.get(lang) or _DEMO_TALK.get(lang.split("-")[0]) or _DEMO_TALK["en"]   # ja-JP: ja, as the page
    return words[key]
