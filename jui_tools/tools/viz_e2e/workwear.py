"""A subagent's work clothes and size (2.3.5, requester 10-19: "サブエージェントは格好を作業着っぽい感じにできる？",
"さいずも0.8くらいにして", "作業着の服装の感じはアメリカの囚人服っぽいオレンジがいいな").

The real `jui viz serve` in a throwaway HOME on a free port, the real forward.py: one main session and two of its
subagents (jsonui-implement, jsonui-test). Measured from the page's own objects (window.__dbg.wear / wearFit):

  - the subagents wear the orange coverall, a patch of their role's colour and a work cap; the main robot none of it;
  - a subagent is 0.75–0.85 of the main robot's height as drawn; every name tag sits just above its robot's head on screen;
  - the coverall's orange stays apart from the main robot's colour (ΔE2000 ≥ DE_MIN) and the patch's edge reads on it
    (contrast ≥ EDGE_CONTRAST);
  - typing at its desk, a subagent's hands are on the desk, not in it (as the main robot's);
  - in the headset (background work), the band goes over the cap and the cups clear its sides;
  - a click on a subagent opens its card.
Screenshots (light and dark): the room up close (the main robot next to its subagents), a subagent with the headset.
"""

from __future__ import annotations

import json
import math
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, dump, new_page, ready

MAIN = "e2e00000-0000-4000-8000-0000000003a1"
SUBS = [("a3sub000000000000impl", "jsonui-implement"), ("a3sub000000000000test", "jsonui-test")]
CWD = "/work/wear-app"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
DE_MIN = 10.0
EDGE_CONTRAST = 3.0
WEAR = "() => window.__dbg.wear()"


def check(failures, cond, text):
    if not cond:
        failures.append(f"workwear: {text}")


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=100)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _rgb(h):
    return [_lin(int(h[i:i + 2], 16)) for i in (1, 3, 5)]


def lab(h):
    r, g, b = _rgb(h)
    x, y, z = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047, 0.2126 * r + 0.7152 * g + 0.0722 * b, (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116   # noqa: E731
    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def de2000(c1, c2):
    L1, a1, b1 = lab(c1)
    L2, a2, b2 = lab(c2)
    C1, C2 = math.hypot(a1, b1), math.hypot(a2, b2)
    Cb = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cb ** 7 / (Cb ** 7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1, h2 = math.degrees(math.atan2(b1, a1p)) % 360, math.degrees(math.atan2(b2, a2p)) % 360
    dL, dC = L2 - L1, C2p - C1p
    dh = 0 if C1p * C2p == 0 else (h2 - h1 - 360 if h2 - h1 > 180 else h2 - h1 + 360 if h2 - h1 < -180 else h2 - h1)
    dH = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dh / 2))
    Lb, Cbp = (L1 + L2) / 2, (C1p + C2p) / 2
    hb = (h1 + h2) / 2 if abs(h1 - h2) <= 180 else (h1 + h2 + 360) / 2
    T = 1 - 0.17 * math.cos(math.radians(hb - 30)) + 0.24 * math.cos(math.radians(2 * hb)) + 0.32 * math.cos(math.radians(3 * hb + 6)) - 0.2 * math.cos(math.radians(4 * hb - 63))
    SL, SC, SH = 1 + 0.015 * (Lb - 50) ** 2 / math.sqrt(20 + (Lb - 50) ** 2), 1 + 0.045 * Cbp, 1 + 0.015 * Cbp * T
    RT = -2 * math.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7)) * math.sin(math.radians(60 * math.exp(-((hb - 275) / 25) ** 2)))
    return math.sqrt((dL / SL) ** 2 + (dC / SC) ** 2 + (dH / SH) ** 2 + RT * (dC / SC) * (dH / SH))


def contrast(c1, c2):
    lum = lambda h: 0.2126 * _rgb(h)[0] + 0.7152 * _rgb(h)[1] + 0.0722 * _rgb(h)[2]   # noqa: E731
    a, b = sorted([lum(c1), lum(c2)])
    return (b + 0.05) / (a + 0.05)


async def run_workwear(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "workwear"
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

    def hook(**payload):
        body = {"session_id": MAIN, "cwd": CWD, "permission_mode": "default", **payload}
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
        page = await new_page(browser, watch, "workwear", **DESKTOP)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", label="connected")
        hook(hook_event_name="SessionStart", source="startup")
        hook(hook_event_name="UserPromptSubmit", prompt="二人に頼む")
        for aid, atype in SUBS:
            hook(hook_event_name="SubagentStart", agent_id=aid, agent_type=atype)
        await wait(page, "() => window.__dbg.wear().length >= 3", label="three robots")
        await wait(page, "() => window.__dbg.play().robots.every((x) => x.path === 0)", timeout=30000, label="seated")
        await page.evaluate("() => { window.__dbg.play({ p: 0, solo: { p: 0 } }); window.__dbg.brk({ p: { smoke: 0, vend: 0 } }); }")
        await page.wait_for_timeout(800)
        wear = res["wear"] = await page.evaluate(WEAR)
        main = next(x for x in wear if x["kind"] == "main")
        subs = [x for x in wear if x["kind"] == "sub"]
        check(failures, len(subs) == 2, f"two subagents: {wear}")
        check(failures, not main["cap"] and main["patch"] is None and main["size"] == 1 and main["body"] != subs[0]["body"],
              f"the main robot wears none of it, at full size: {main}")
        colors = res["colors"] = await page.evaluate("() => window.__dbg.wearColors()")
        for s in subs:
            check(failures, s["cap"] and s["patch"] == s["roleColor"] and s["body"] == colors["overall"] and s["patchEdge"] == colors["edge"],
                  f"a subagent wears the coverall, the cap and a patch of its role's colour: {s}")
            ratio = s["height"] / main["height"]
            check(failures, 0.75 <= ratio <= 0.85, f"a subagent is 0.75–0.85 of the main robot's height: {s['height']} / {main['height']} = {ratio:.3f}")
        de, edge = de2000(colors["overall"], colors["main"]), contrast(colors["edge"], colors["overall"])
        res["measure"] = {"deOverallMain": round(de, 2), "edgeOnOverall": round(edge, 2), "rimOnEdge": round(contrast(colors["rim"], colors["edge"]), 2),
                          "patchOnRim": {k: round(contrast(v, colors["rim"]), 2) for k, v in colors["roles"].items()}}
        check(failures, de >= DE_MIN, f"the coverall's orange stays apart from the main robot's colour: ΔE2000 {de:.2f} < {DE_MIN}")
        check(failures, edge >= EDGE_CONTRAST, f"the patch's edge reads on the coverall: contrast {edge:.2f} < {EDGE_CONTRAST}")

        # at the desk, typing: the hands on the desk, not in it (main and subagent alike)
        hook(hook_event_name="PreToolUse", tool_name="Edit", tool_use_id="toolu_w_main", tool_input={"file_path": f"{CWD}/m.py", "old_string": "a", "new_string": "b"})
        for aid, atype in SUBS:
            hook(hook_event_name="PreToolUse", agent_id=aid, agent_type=atype, tool_name="Edit", tool_use_id=f"toolu_w_{aid}",
                 tool_input={"file_path": f"{CWD}/{aid}.py", "old_string": "a", "new_string": "b"})
        await wait(page, "() => window.__dbg.bgLook().every((x) => x.state === 'typing')", label="all three typing")
        await page.wait_for_timeout(1200)
        typing = res["typing"] = await page.evaluate(WEAR)
        for x in typing:
            size = x["size"]
            check(failures, x["deskY"] is not None and 0 <= (x["handY"] - x["deskY"]) / size <= 0.3 and x["bottom"] >= -0.02,
                  f"typing at its desk, the hands are on it ({x['id']}): hand {x['handY']}, desk {x['deskY']}, size {size}, feet {x['bottom']}")

        # the room up close: the main robot next to its subagents
        room = await page.evaluate("() => window.__dbg.robots[0].def.room")
        await page.click(f".tag.room[data-set-project='{room}']")
        await wait(page, f"() => window.__dbg.solo() === '{room}'", label="the room up close")
        await page.wait_for_timeout(1500)
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await page.wait_for_timeout(700)
            await page.screenshot(path=str(out / f"room-{scheme}.png"))
        await page.emulate_media(color_scheme="light")
        # each name tag as placed on the screen: its bottom just above the robot's head (the top of its drawn body)
        tags = res["tags"] = await page.evaluate("""() => { const D = window.__dbg, c = document.getElementById('scene-canvas').getBoundingClientRect();
          const W = Object.fromEntries(D.wear().map((x) => [x.id, x]));
          return D.robots.map((R) => { const p = R.robot.root.position, top = new D.THREE.Vector3(p.x, W[R.def.id].top, p.z).project(D.camera);
            const feet = new D.THREE.Vector3(p.x, W[R.def.id].bottom, p.z).project(D.camera);
            // the tag's own spot: where it is drawn, less how far it was moved up to clear another tag (R.tagDy)
            return { id: R.def.id, kind: R.def.kind, tagBottom: +(R.tag.getBoundingClientRect().bottom + (R.tagDy || 0)).toFixed(1),
              headTop: +(c.top + (1 - top.y) / 2 * c.height).toFixed(1), feet: +(c.top + (1 - feet.y) / 2 * c.height).toFixed(1) }; }); }""")
        for t in tags:
            gap = (t["headTop"] - t["tagBottom"]) / max(1.0, t["feet"] - t["headTop"])   # in the robot's own height on screen
            t["gapShare"] = round(gap, 3)
            check(failures, 0 <= gap <= 0.3, f"the name tag sits just above the head on screen ({t['id']}, {t['kind']}): gap {gap:.3f} of its height {t}")

        # a click on a subagent opens its card
        sub_id = subs[0]["id"]
        xy = await page.evaluate("""(id) => { const D = window.__dbg, R = D.robots.find((x) => x.def.id === id), c = document.getElementById('scene-canvas').getBoundingClientRect();
          const p = R.robot.torso.children[0].getWorldPosition(new D.THREE.Vector3()).project(D.camera);
          return [c.left + (p.x + 1) / 2 * c.width, c.top + (1 - p.y) / 2 * c.height]; }""", sub_id)
        await page.mouse.click(xy[0], xy[1])
        await wait(page, "(id) => window.__dbg.focus().id === id", arg=sub_id, label="the subagent's card from a click")
        res["clicked"] = sub_id

        # the headset over the cap (background work: a subagent never gets it from the hooks, so the page's state is set)
        await page.evaluate("(id) => window.__dbg.setVisState(id, 'background')", sub_id)
        await wait(page, "(id) => window.__dbg.bgLook().find((x) => x.id === id).headset", arg=sub_id, label="the subagent in the headset")
        fit = res["fit"] = await page.evaluate("(id) => window.__dbg.wearFit(id)", sub_id)
        check(failures, fit and fit["arcTop"] - fit["crownTop"] >= 0.03 and fit["cupInnerX"] - fit["crownHalfW"] >= 0.03 and not fit["overlapCrownCups"],
              f"the headset's band goes over the cap and its cups clear the cap's sides: {fit}")
        await wait(page, "() => { const f = window.__dbg.focus(); return f.zoomed && !f.tween; }", label="the camera on the subagent")
        await page.wait_for_timeout(2500)
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await page.wait_for_timeout(700)
            await page.screenshot(path=str(out / f"sub-headset-{scheme}.png"))
        await page.emulate_media(color_scheme="light")
        await page.close()
        for line in watch.console:
            failures.append(f"workwear: console: {line}")
        for u in watch.foreign:
            failures.append(f"workwear: request outside the server: {u}")
    except Exception as e:
        failures.append(f"workwear: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  workwear: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "workwear-results.json").write_text(dump(res) + "\n")
