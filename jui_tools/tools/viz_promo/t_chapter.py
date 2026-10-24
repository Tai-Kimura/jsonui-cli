"""Chapter T of the promo (2.3.23, requester 10-25): the mock server and the test runner, in two halves.

T-a, automated e2e (``Ta`` + ``Ta-app``): the real web runner (t_runner.mjs, npm's jsonui-test-runner-web) runs two of
the stage's screen tests against its web app and its ``jsonui-test mock serve``, in a browser that records a video.
Left: the test file, the step being run lit, a step done ticked. Right: the run's own video, a phone's width in the
middle of the half. The responses change by the tests' own ``setMocks`` steps (requester: 「自動e2eはsetmock」).

T-b, checked by hand (``Tb`` + ``Tb-app``): left, the mock server's control panel; right, the store map. A pin is the map
widget's, not a JsonUI element, so no test step can point at it (requester: 「Googleマップが自動テストできないのは
マップのピン指定とかの機能が提供されてないから」): the panel switches listStores' scenario (one, none, a 503, many) and the
cursor taps the pins. At the end the left half is a terminal: a request the contract refuses, then the server's list of
contract violations.

Everything is the stage's own (``--stage``: a demo-shop with a web shell, its pages, scenarios and tests; promo
plan 2026-10-25): its web app under ``next dev``, its mock server, real clicks. The cursor is an overlay drawn into the
page it points at (as capture.py's #promo-cursor), the only thing the app did not draw.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from PIL import Image

FPS = 30
HALF = (1125, 1012)                  # SPLIT_VIEWPORT: each half of the split (900 x 810 in the video)
PHONE = (430, 932)                   # the app's viewport (t_runner.mjs VIEW)
PANEL_ZOOM = 1.5                     # the control panel is drawn for a wide window; larger, so it reads at 900 px
HOLD_MS = 1600                       # each runner step held this long after it ends (t_runner.mjs T_HOLD_MS)
INTRO = 1.2                          # T-a: the test file in view before its run starts
GAP = 0.8                            # between the two runs

WORDS = {
    "ja": {"runner": "jsonui-test-runner-web（web のテストランナー）· mock serve", "passed": "通過", "running": "実行中",
           "panel": "mock の管理画面", "term": "端末"},
    "en": {"runner": "jsonui-test-runner-web (the web test runner) · mock serve", "passed": "passed", "running": "running",
           "panel": "the mock's control panel", "term": "terminal"},
}

PAGING = "tests/screens/product_list/product_list_paging.test.json"
CART_429 = "tests/screens/cart/cart_rate_limited.test.json"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_http(url: str, sec: float = 120) -> None:
    end = time.monotonic() + sec
    while time.monotonic() < end:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                if r.status < 500:
                    return
        except Exception:  # noqa: BLE001 — not up yet
            time.sleep(0.5)
    raise RuntimeError(f"{url} did not answer in {sec} s")


class Servers:
    """The stage's mock server and its web app (next dev), started here and stopped by stop()."""

    def __init__(self, stage: Path, jui_root: Path, work: Path):
        self.stage, self.work = stage, work
        self.mock_port, self.app_port = free_port(), free_port()
        self.mock = f"http://127.0.0.1:{self.mock_port}"
        self.app = f"http://127.0.0.1:{self.app_port}"
        log = open(work / "mock.log", "w")
        self.procs = [subprocess.Popen([str(jui_root / "test_tools" / "jsonui-test"), "mock", "serve", "--port", str(self.mock_port)],
                                       cwd=stage, stdout=log, stderr=subprocess.STDOUT, env={**os.environ, "HOME": str(work)},
                                       start_new_session=True)]
        app_log = open(work / "next.log", "w")
        self.procs.append(subprocess.Popen(["npx", "next", "dev", "--port", str(self.app_port)], cwd=stage / "web",
                                           stdout=app_log, stderr=subprocess.STDOUT, start_new_session=True,
                                           env={**os.environ, "NEXT_PUBLIC_API_BASE_URL": self.mock}))
        try:
            wait_http(f"{self.mock}/__jsonui__/identity")
            wait_http(f"{self.app}/?lang=ja", 180)
        except RuntimeError:
            self.stop()   # one that did start is not left behind
            raise
        self.token = next(line.split()[-1] for line in (work / "mock.log").read_text().splitlines() if "admin token" in line)

    def admin(self, path: str, body: dict | None = None):
        req = urllib.request.Request(self.mock + "/__jsonui__" + path, method="POST" if body is not None else "GET",
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"X-JsonUI-Token": self.token, "Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read() or b"null")

    def stop(self) -> None:
        import signal
        for p in self.procs:
            try:
                os.killpg(p.pid, signal.SIGINT)
            except ProcessLookupError:
                continue
        for p in self.procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)


def on_canvas(phone: Image.Image) -> Image.Image:
    """The app at a phone's width in the middle of the right half."""
    canvas = Image.new("RGB", HALF, (232, 226, 216))
    k = (HALF[1] - 24) / phone.height   # as tall as the half allows
    phone = phone.convert("RGB").resize((round(phone.width * k), round(phone.height * k)), Image.LANCZOS)
    canvas.paste(phone, ((HALF[0] - phone.width) // 2, (HALF[1] - phone.height) // 2))
    return canvas


# ---------------------------------------------------------------------------------------------------------- T-a

EDITOR = """<!doctype html><meta charset="utf-8"><style>
html,body{margin:0;width:100vw;height:100vh;background:#0d1117;color:#e6edf3;overflow:hidden}
body{font:17px/1.55 Menlo,"SF Mono","Hiragino Sans",monospace}
#path{padding:14px 26px;color:#8b949e;font-size:18px;border-bottom:1px solid #30363d}
#code{padding:10px 0;white-space:pre}
.ln{display:flex;padding:0 18px}.ln i{width:46px;text-align:right;padding-right:18px;color:#484f58;font-style:normal;flex:none}
.ln.run{background:rgba(210,153,34,.22);box-shadow:inset 4px 0 0 #d29922}.ln.ok{background:rgba(63,185,80,.13)}
.ln b{width:28px;flex:none;font-weight:400}.ln.ok b{color:#3fb950}.ln.run b{color:#d29922}
#bar{position:absolute;left:0;right:0;bottom:0;padding:12px 26px;background:#161b22;border-top:1px solid #30363d;
color:#8b949e;font-size:18px;display:flex;justify-content:space-between}#res{color:#3fb950}
</style><div id="path"></div><div id="code"></div><div id="bar"><span id="who"></span><span id="res"></span></div>
<script>
function esc(s){return s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'})[c])}
window.show=(file,text,marks,who,res)=>{document.getElementById('path').textContent=file;
 document.getElementById('who').textContent=who;document.getElementById('res').textContent=res;
 document.getElementById('code').innerHTML=text.split('\\n').map((l,n)=>{const m=marks[n]||'';
 return `<div class="ln ${m}"><i>${n+1}</i><b>${m==='ok'?'✓':m==='run'?'▶':''}</b>${esc(l)||' '}</div>`}).join('')}
</script>"""


def step_lines(text: str) -> list[int]:
    """The line of each step (one step a line in the stage's test files), in order."""
    return [n for n, line in enumerate(text.splitlines()) if line.strip().startswith('{ "a')]


def run_tests(servers: Servers, jui_root: Path, lang: str, work: Path) -> list[dict]:
    out = work / "ta-runs"
    shutil.rmtree(out, ignore_errors=True)
    here = Path(__file__).resolve().parent
    stage = servers.stage
    p = subprocess.run(["node", str(here / "t_runner.mjs"), str(stage / "web"), str(out), servers.app, servers.mock,
                        servers.token, lang, f"/={stage / PAGING}", f"/cart={stage / CART_429}"],
                       capture_output=True, text=True, env={**os.environ, "T_HOLD_MS": str(HOLD_MS)})
    if p.returncode != 0:
        raise RuntimeError(f"the runner's run failed ({p.returncode}): {p.stdout[-800:]} {p.stderr[-800:]}")
    runs = json.loads((out / "runs.json").read_text())
    for r in runs:
        frames = out / (r["name"] + "-frames")
        frames.mkdir()
        subprocess.run(["ffmpeg", "-v", "error", "-i", r["video"], "-vf", f"fps={FPS}", str(frames / "%05d.png")], check=True)
        r["frames"] = sorted(frames.glob("*.png"))
    return runs


async def capture_ta(pw, out_root: Path, lang: str, bounds: tuple, servers: Servers, jui_root: Path, work: Path) -> dict:
    start, end = bounds
    total = round((end - start) * FPS)
    runs = run_tests(servers, jui_root, lang, work)
    left_dir, right_dir = out_root / lang / "Ta", out_root / lang / "Ta-app"
    for d in (left_dir, right_dir):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
    texts = {r["name"]: (servers.stage / (PAGING if "paging" in r["name"] else CART_429)).read_text(encoding="utf-8") for r in runs}
    # each run's place on the chapter's clock: the first after INTRO, the second after the first and GAP
    plan, at = [], INTRO
    for r in runs:
        plan.append((at, r))
        # its video up to the last step's end and its hold (the tail is the browser closing)
        at += min(len(r["frames"]) / FPS, (r["steps"][-1]["end"] + HOLD_MS + 500) / 1000) + GAP
    browser = await pw.chromium.launch()
    page = await browser.new_page(viewport={"width": HALF[0], "height": HALF[1]})
    await page.set_content(EDITOR)
    w = WORDS[lang]
    shown = None
    for i in range(total):
        t = i / FPS
        k = max((n for n, (s, _) in enumerate(plan) if t >= s - INTRO), default=0)
        s, r = plan[k]
        tau = max(0.0, t - s) * 1000   # ms into the run's video
        text = texts[r["name"]]
        lines = step_lines(text)
        marks, done = {}, 0
        for line, st in zip(lines, r["steps"]):
            if tau >= st["end"]:
                marks[line] = "ok"
                done += 1
            elif tau >= st["start"]:
                marks[line] = "run"
        finished = tau >= r["steps"][-1]["end"] + 200
        res = (f"✓ 1 {w['passed']}" if finished and all(x["passed"] for x in r["results"]) else
               (w["running"] if tau > 0 else ""))
        state = (r["name"], tuple(sorted(marks.items())), res)
        if state != shown:
            await page.evaluate("([f,t,m,w,r]) => show(f,t,m,w,r)",
                                [PAGING if "paging" in r["name"] else CART_429, text, {str(a): b for a, b in marks.items()}, w["runner"], res])
            await page.screenshot(path=str(work / "ta-left.png"))
            shown = state
        shutil.copyfile(work / "ta-left.png", left_dir / f"{i:05d}.png")
        frame = r["frames"][min(len(r["frames"]) - 1, int(tau / 1000 * FPS))]
        on_canvas(Image.open(frame)).save(right_dir / f"{i:05d}.png")
    await browser.close()
    return {"runs": [{"name": r["name"], "results": r["results"], "steps": len(r["steps"])} for r in runs], "frames": total}


# ---------------------------------------------------------------------------------------------------------- T-b

CURSOR_JS = """(([x, y]) => { let c = document.getElementById('promo-cursor');
 if (!c) { c = document.createElement('div'); c.id = 'promo-cursor';
  c.innerHTML = '<svg width="28" height="34" viewBox="0 0 28 34"><path d="M2 2 L2 28 L9 21 L14 32 L19 30 L14 19 L24 19 Z" fill="#111" stroke="#fff" stroke-width="2"/></svg>';
  Object.assign(c.style, {position: 'fixed', zIndex: 2147483647, pointerEvents: 'none', left: '0px', top: '0px'});
  document.documentElement.appendChild(c); }
 c.style.display = x < 0 ? 'none' : 'block'; c.style.left = x + 'px'; c.style.top = y + 'px'; })"""

TERM = """<!doctype html><meta charset="utf-8"><style>
html,body{margin:0;width:100vw;height:100vh;background:#0d1117;color:#c9d1d9;overflow:hidden}
#t{padding:26px 30px;white-space:pre-wrap;word-break:break-all;font:20px/1.45 Menlo,"SF Mono","Hiragino Sans",monospace}
.p{color:#3fb950}.c{color:#e6edf3}</style><div id="t"></div>
<script>function esc(s){return s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'})[c])}
window.show=(blocks)=>{document.getElementById('t').innerHTML=blocks.map(b=>`<span class="p">demo-shop $ </span><span class="c">${esc(b[0])}</span>\\n${esc(b[1])}`).join('\\n')}</script>"""


async def capture_tb(pw, out_root: Path, lang: str, bounds: tuple, servers: Servers, work: Path) -> dict:
    """The script on the chapter's clock: (second, what). The pages are driven for real between frames."""
    start, end = bounds
    total = round((end - start) * FPS)
    left_dir, right_dir = out_root / lang / "Tb", out_root / lang / "Tb-app"
    for d in (left_dir, right_dir):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
    servers.admin("/reset", {})
    browser = await pw.chromium.launch()
    panel = await browser.new_page(viewport={"width": round(HALF[0] / PANEL_ZOOM), "height": round(HALF[1] / PANEL_ZOOM)},
                                   device_scale_factor=PANEL_ZOOM)
    app = await browser.new_page(viewport={"width": PHONE[0], "height": PHONE[1]})
    term = await browser.new_page(viewport={"width": HALF[0], "height": HALF[1]})
    await term.set_content(TERM)
    await panel.goto(f"{servers.mock}/__jsonui__/panel")
    await app.goto(f"{servers.app}/stores?lang={lang}")
    await app.wait_for_timeout(1500)

    async def pin_xy(n: int):
        box = await app.locator("#map_area button").nth(n).bounding_box()
        return (box["x"] + box["width"] / 2, box["y"] + box["height"] * 0.35) if box else None

    async def select_xy():
        box = await panel.locator("tr", has_text="/stores").locator("select").bounding_box()
        return (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

    async def pick(scenario: str):
        await panel.locator("tr", has_text="/stores").locator("select").select_option(scenario)
        await panel.wait_for_timeout(300)
        await app.reload()
        await app.wait_for_timeout(1200)

    async def tap_pin(n: int):
        await app.locator("#map_area button").nth(n).click()
        await app.wait_for_timeout(200)

    async def requests_tab():
        await panel.get_by_text("Requests", exact=True).click()
        await panel.wait_for_timeout(500)

    term_blocks: list = []

    def run_term():
        bad = urllib.request.Request(servers.mock + "/orders", data=b'{"items": []}', method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(bad) as r:
                said = f"{r.status} {r.read().decode()}"
        except urllib.error.HTTPError as e:
            said = f"{e.code} {e.read().decode()}"
        term_blocks.append([f"curl -X POST {servers.mock}/orders -d '{{\"items\": []}}'", said])
        violations = servers.admin("/contract-violations")
        term_blocks.append([f"curl {servers.mock}/__jsonui__/contract-violations",
                            json.dumps(violations[-1:], ensure_ascii=False, indent=1)])

    # (second, side, target for the cursor or None, the action at that second)
    script = [
        (1.0, "app", ("pin", 0), lambda: tap_pin(0)),
        (6.0, "panel", ("select",), lambda: pick("one")),
        (7.6, "app", ("pin", 0), lambda: tap_pin(0)),
        (10.0, "panel", ("select",), lambda: pick("empty")),
        (12.6, "panel", ("select",), lambda: pick("error_503")),
        (15.0, "panel", ("select",), lambda: pick("default")),
        (16.6, "app", ("pin", 4), lambda: tap_pin(4)),
        (18.4, "panel", ("tab",), requests_tab),
        (21.0, "term", None, None),
    ]
    cursor = {"panel": (-1, -1), "app": (-1, -1)}
    left_mode, done = "panel", set()
    for i in range(total):
        t = i / FPS
        for n, (sec, side, target, act) in enumerate(script):
            # the cursor glides to its target over the 0.8 s before the second, then the action
            if n not in done and target and sec - 0.8 <= t:
                if target[0] == "pin":
                    goal = await pin_xy(target[1])
                elif target[0] == "select":
                    goal = await select_xy()
                else:
                    box = await panel.get_by_text("Requests", exact=True).bounding_box()
                    goal = (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                if goal:
                    other = "app" if side == "panel" else "panel"
                    cursor[other] = (-1, -1)
                    x0, y0 = cursor[side] if cursor[side][0] >= 0 else (goal[0] + 120, goal[1] + 160)
                    k = min(1.0, (t - (sec - 0.8)) / 0.8)
                    e = k * k * (3 - 2 * k)
                    cursor[side] = (x0 + (goal[0] - x0) * e, y0 + (goal[1] - y0) * e)
            if n not in done and t >= sec:
                done.add(n)
                if side == "term":
                    run_term()
                    left_mode = "term"
                    await term.evaluate("(b) => show(b)", term_blocks)
                elif act:
                    await act()
        await panel.evaluate(CURSOR_JS, list(cursor["panel"]))
        await app.evaluate(CURSOR_JS, list(cursor["app"]))
        if left_mode == "panel":
            await panel.screenshot(path=str(left_dir / f"{i:05d}.png"))
        else:
            await term.screenshot(path=str(left_dir / f"{i:05d}.png"))
        await app.screenshot(path=str(work / "tb-app.png"))
        on_canvas(Image.open(work / "tb-app.png")).save(right_dir / f"{i:05d}.png")
    await browser.close()
    return {"frames": total, "term": term_blocks}


async def capture_t(pw, out_root: Path, lang: str, bounds: dict, stage: Path, jui_root: Path, keep: bool = False) -> dict:
    """T-a and T-b on one start of the stage's servers. bounds: {"Ta": (s, e), "Tb": (s, e)} (the promo's seconds)."""
    work = Path(tempfile.mkdtemp(prefix="promo-t-"))
    servers = Servers(stage, jui_root, work)
    try:
        out = {"Ta": await capture_ta(pw, out_root, lang, bounds["Ta"], servers, jui_root, work),
               "Tb": await capture_tb(pw, out_root, lang, bounds["Tb"], servers, work)}
        (out_root / lang / "Ta" / "manifest.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
        return out
    finally:
        servers.stop()
        if not keep:
            shutil.rmtree(work, ignore_errors=True)
