"""The main robot's colour (2.3.5, requester 10-19: 「むしろメインのロボットの色を変えればいいんじゃないの？」→「スカイブルーにしようか」).

The real `jui viz serve` in a throwaway HOME on a free port, the real forward.py: a main session with a jsonui-implement
subagent (the two blues side by side in the panel), and a second main session in another room. Measured from the page:

  - the main robot's accent (ears, hands, feet, antenna) is MAIN (#0ea5e9); a subagent's is its role's colour;
  - the main pill in the panel and over the robot: its background MAIN, its text dark enough (contrast ≥ 4.5:1);
  - the robot card of a main robot: its head's colour MAIN;
  - nothing on the page is drawn in the old orange (#ff7a3d) any more (every element's colour, background and border);
  - the main blue and implement's blue stay apart (ΔE2000 ≥ DE_IMPLEMENT).
Screenshots (light and dark): the whole floor, the room up close (the main robot next to its subagent), the card.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, dump, new_page, ready
from workwear import contrast, de2000

MAIN = "#0ea5e9"
OLD = "rgb(255, 122, 61)"
DE_IMPLEMENT = 20.0
INK_CONTRAST = 4.5
S1 = "e2e00000-0000-4000-8000-0000000004a1"
S2 = "e2e00000-0000-4000-8000-0000000004a2"
SUB = ("a4sub00000000000impl", "jsonui-implement")
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")


def check(failures, cond, text):
    if not cond:
        failures.append(f"main-color: {text}")


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=100)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


def rgb_hex(css: str) -> str:
    nums = [int(float(x)) for x in css[css.index("(") + 1:css.index(")")].split(",")[:3]]
    return "#" + "".join(f"{n:02x}" for n in nums)


PAGE = """() => {
  const D = window.__dbg, out = { robots: D.robots.map((R) => ({ id: R.def.id, kind: R.def.kind, role: R.def.role, accent: '#' + R.robot.accent.color.getHexString() })) };
  const pills = [...document.querySelectorAll('#sessions .pill')];
  out.pills = pills.map((p) => ({ text: p.textContent, bg: getComputedStyle(p).backgroundColor, fg: getComputedStyle(p).color }));
  out.tagPills = [...document.querySelectorAll('.tag .pill')].map((p) => ({ text: p.textContent, bg: getComputedStyle(p).backgroundColor, fg: getComputedStyle(p).color }));
  const old = [];
  for (const el of document.querySelectorAll('body *')) {
    const s = getComputedStyle(el);
    for (const k of ['color', 'backgroundColor', 'borderTopColor', 'borderLeftColor', 'outlineColor']) if (s[k] === '%s') old.push(`${el.tagName.toLowerCase()}.${el.className}:${k}`);
  }
  out.old = old.slice(0, 20);
  return out;
}""" % OLD


async def run_main_color(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "main-color"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT,
                           env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def hook(sid, cwd, **payload):
        body = {"session_id": sid, "cwd": cwd, "permission_mode": "default", **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(),
                       capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)

    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    t0 = time.monotonic()
    try:
        import urllib.request
        for _ in range(400):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError(f"the server did not answer /health in 40 s: {(out / 'serve.log').read_text()[-400:]}")
        watch = Watch(origin=url)
        page = await new_page(browser, watch, "main-color", **DESKTOP)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", label="connected")
        hook(S1, "/work/sky-one", hook_event_name="SessionStart", source="startup")
        hook(S1, "/work/sky-one", hook_event_name="UserPromptSubmit", prompt="頼む")
        hook(S1, "/work/sky-one", hook_event_name="SubagentStart", agent_id=SUB[0], agent_type=SUB[1])
        hook(S2, "/work/sky-two", hook_event_name="SessionStart", source="startup")
        await wait(page, "() => window.__dbg.robots.length >= 3", label="three robots")
        await wait(page, "() => window.__dbg.play().robots.every((x) => x.path === 0)", timeout=30000, label="seated")
        await page.evaluate("() => { window.__dbg.play({ p: 0, solo: { p: 0 } }); window.__dbg.brk({ p: { smoke: 0, vend: 0 } }); }")
        await page.wait_for_timeout(800)
        got = res["page"] = await page.evaluate(PAGE)
        for r in got["robots"]:
            want = MAIN if r["role"] == "main" else None
            if want:
                check(failures, r["accent"] == want, f"a main robot's accent is {MAIN}: {r}")
        mains = [p for p in got["pills"] if rgb_hex(p["bg"]) == MAIN]
        check(failures, len(mains) >= 2, f"the main sessions' pills are {MAIN}: {got['pills']}")
        for p in mains + [t for t in got["tagPills"] if rgb_hex(t["bg"]) == MAIN]:
            c = contrast(rgb_hex(p["fg"]), rgb_hex(p["bg"]))
            check(failures, c >= INK_CONTRAST, f"the main pill's text reads on {MAIN}: {c:.2f}:1 {p}")
        res["inkContrast"] = round(contrast(rgb_hex(mains[0]["fg"]), MAIN), 2) if mains else None
        check(failures, not got["old"], f"nothing drawn in the old orange: {got['old']}")
        colors = await page.evaluate("() => window.__dbg.wearColors()")
        res["deImplement"] = round(de2000(colors["roles"]["main"], colors["roles"]["implement"]), 2)
        res["roles"] = colors["roles"]
        check(failures, colors["roles"]["main"] == MAIN and res["deImplement"] >= DE_IMPLEMENT,
              f"the main blue {colors['roles']['main']} and implement's {colors['roles']['implement']} stay apart: ΔE2000 {res['deImplement']}")

        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await page.wait_for_timeout(700)
            await page.screenshot(path=str(out / f"floor-{scheme}.png"))
        await page.emulate_media(color_scheme="light")
        room = await page.evaluate("(s) => window.__dbg.robots.find((R) => R.def.sessionId === s && R.def.kind === 'main').def.room", S1)
        await page.click(f".tag.room[data-set-project='{room}']")
        await wait(page, f"() => window.__dbg.solo() === '{room}'", label="the room up close")
        await page.wait_for_timeout(1500)
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await page.wait_for_timeout(700)
            await page.screenshot(path=str(out / f"room-{scheme}.png"))
        await page.emulate_media(color_scheme="light")
        main_id = await page.evaluate("(s) => window.__dbg.robots.find((R) => R.def.sessionId === s && R.def.kind === 'main').def.id", S1)
        await page.evaluate("(i) => window.__dbg.openRobot(i)", main_id)
        await wait(page, "() => { const f = window.__dbg.focus(); return f.zoomed && !f.tween; }", label="the camera on the main robot")
        await page.wait_for_timeout(2500)
        head = res["cardHead"] = await page.evaluate("() => getComputedStyle(document.querySelector('#rb .rb-head')).getPropertyValue('--c').trim()")
        check(failures, head.lower() == MAIN, f"the main robot's card is {MAIN}: {head}")
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await page.wait_for_timeout(700)
            await page.screenshot(path=str(out / f"card-{scheme}.png"))
        await page.close()
        for line in watch.console:
            failures.append(f"main-color: console: {line}")
        for u in watch.foreign:
            failures.append(f"main-color: request outside the server: {u}")
    except Exception as e:
        failures.append(f"main-color: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  main-color: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "main-color-results.json").write_text(dump(res) + "\n")
