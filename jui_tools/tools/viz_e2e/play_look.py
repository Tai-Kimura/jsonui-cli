"""What a game looks like, end to end (2.3.3, requester 10-19: "ずっと二人で向き合ってるだけで何やってるかわからない").

The real `jui viz serve` in a throwaway HOME on a free port, the real forward.py for two sessions in one room, the
times shortened through window.__dbg.play (as play.py does). For each game (ball, highfive, rps) the page is sampled
on every frame for a few seconds and the arms read what a person would see:

  - the name tag says 遊びに行く on the way, the game's name while it plays (キャッチボール中 / ハイタッチ中 / じゃんけん中),
    and nothing once both are back at their desks; the robot's card and the building's window say it too;
  - ball: the ball's on-screen diameter in the default view is 10 px or more, and the catcher holds both hands out;
  - highfive: the two walk toward each other (their distance changes by 0.8 or more) and two hands come within
    HAND_TOUCH of each other, with the パチン mark up at that moment;
  - rps: the bubble is up for half the time or more and never missing between the reveal and the next pump; a
    decided round shows a winner with both arms up and a loser; a tie (あいこ) starts the next round at once.

Everything is measured from the page's own objects (window.__dbg.robots, the camera, the scene), so the same file
runs against an older page and says what it lacks. Screenshots (light and dark; the whole floor, the room up close,
the building) are for the eye.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, T, Watch, dump, new_page, ready

A = "e2e00000-0000-4000-8000-0000000000ea"
B = "e2e00000-0000-4000-8000-0000000000eb"
CWD = "/work/look-app"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
BALL_PX = 10        # the ticket: the ball 10 px or more in the default view
HAND_TOUCH = 0.25   # two hand spheres of radius 0.095 touch at 0.19
APPROACH = 0.8      # how much nearer the two get at highfive
BUBBLE_SHARE = 0.5  # the rps bubble up for at least this share of the time
UP_Y = 1.0          # a hand this high above the robot's feet is raised (hanging: about 0.47)

# One sample per frame for `dur` ms: tags, the two players' hands, the ball's size on screen, the mark, the bubbles.
SAMPLER = """async (dur) => {
  const D = window.__dbg, T = D.THREE, cam = D.camera, canvas = document.getElementById('scene-canvas'), out = [];
  const hand = (r, s) => (s === 'L' ? r.armL : r.armR).localToWorld(new T.Vector3(0, -0.38, 0));
  const local = (r, s) => r.root.worldToLocal(hand(r, s));
  const px = (o, rad) => {
    const c = o.getWorldPosition(new T.Vector3()), right = new T.Vector3().setFromMatrixColumn(cam.matrixWorld, 0).multiplyScalar(rad);
    const a = c.clone().project(cam), b = c.clone().add(right).project(cam);
    return 2 * Math.hypot((b.x - a.x) * canvas.clientWidth / 2, (b.y - a.y) * canvas.clientHeight / 2);
  };
  const t0 = performance.now();
  while (performance.now() - t0 < dur) {
    await new Promise((r) => requestAnimationFrame(r));
    const scene = D.robots.length ? D.robots[0].robot.root.parent : null;
    const P = D.play(), G = P.list[0];
    const s = { t: Math.round(performance.now() - t0), started: !!(G && G.started), going: P.robots.filter((x) => x.play === 'going').map((x) => x.id),
      tags: Object.fromEntries(D.robots.map((R) => [R.def.id, R.callText || ''])) };
    const rs = G ? G.players.map((id) => D.robots.find((x) => x.def.id === id)).filter(Boolean) : [];
    if (rs.length === 2 && s.started) {
      const [a, b] = rs.map((R) => R.robot);
      let m = Infinity;
      for (const x of ['L', 'R']) for (const y of ['L', 'R']) m = Math.min(m, hand(a, x).distanceTo(hand(b, y)));
      s.hand = +m.toFixed(3);
      s.center = +Math.hypot(a.root.position.x - b.root.position.x, a.root.position.z - b.root.position.z).toFixed(3);
      s.bots = [a, b].map((r) => { const l = local(r, 'L'), rr = local(r, 'R');
        return { vis: !!(r.rps && r.rps.visible), st: r.rpsState || null, l: [l.x, l.y, l.z].map((v) => +v.toFixed(3)), r: [rr.x, rr.y, rr.z].map((v) => +v.toFixed(3)) }; });
    }
    if (scene) {
      const ball = scene.children.find((o) => o.isMesh && o.geometry && o.geometry.type === 'SphereGeometry' && o.material && o.material.color && o.material.color.getHex() === 0xff7a3d);
      if (ball) { s.ballPx = +px(ball, ball.geometry.parameters.radius * ball.scale.x).toFixed(2); s.ballY = +ball.position.y.toFixed(3); }
      s.mark = scene.children.some((o) => o.isSprite && o.visible && o.userData.playMark);
    }
    out.push(s);
  }
  return out;
}"""

MOMENT = {   # when to take the picture; an older page that never gets there is pictured anyway after the timeout
    "ball": "() => { const G = window.__dbg.play().list[0]; return !!(G && G.ball && G.ball[1] >= 1.55); }",
    "highfive": "() => { const D = window.__dbg, s = D.robots.length && D.robots[0].robot.root.parent; return !!(s && s.children.some((o) => o.isSprite && o.visible && o.userData.playMark)); }",
    "rps": "() => window.__dbg.robots.some((R) => R.robot.rpsState && R.robot.rpsState.res && R.robot.rpsState.res !== 'tie')",
}
RPS_TIE = """() => {
  const X = window.__dbg.rps;
  if (!X) return { missing: true };
  const rpsRound = X.round, RPS_T = X.T;
  for (let seed = 1; seed < 400; seed++) {
    const r0 = rpsRound(seed, 0.1);
    if (r0.res[0] !== 'tie') continue;
    const next = rpsRound(seed, r0.len + 0.1);
    return { seed, hands: r0.hands, len: r0.len, decided: RPS_T.len, nextK: next.k, nextW: +next.w.toFixed(2), shake: RPS_T.shake };
  }
  return { none: true };
}"""


def check(failures, cond, text):
    if not cond:
        failures.append(f"play-look: {text}")


async def wait(page, js, timeout=20000, label=""):
    try:
        await page.wait_for_function(js, timeout=timeout, polling=100)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def moment(page, kind, timeout=8000):
    try:
        await page.wait_for_function(MOMENT[kind], timeout=timeout, polling="raf")
        return True
    except Exception:
        return False


async def run_play_look(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "play-look"
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

    def hook(sid, **payload):
        body = {"session_id": sid, "cwd": CWD, "permission_mode": "default", **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(),
                       capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)

    play = "() => window.__dbg.play()"
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
        page = await new_page(browser, watch, "play-look", **DESKTOP)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').dataset.net === 'connected'", label="connected")
        for sid in (A, B):
            hook(sid, hook_event_name="SessionStart", source="startup")
        await wait(page, "() => window.__dbg.play().robots.length >= 2", label="two robots")
        await wait(page, "() => window.__dbg.play().robots.every((x) => x.path === 0 && x.x === x.seat[0] && x.z === x.seat[1])", label="both seated")
        await page.evaluate("() => window.__dbg.play({ p: 0, solo: { p: 0 } })")
        res["has"] = await page.evaluate("() => ({ towerPlay: typeof window.__dbg.towerPlay === 'function' })")

        async def start(kind, label):
            await page.evaluate("() => window.__dbg.play({ p: 0, endAll: true, solo: { p: 0 } })")
            await wait(page, "() => window.__dbg.play().list.length === 0 && window.__dbg.play().robots.every((x) => !x.back && x.path === 0)",
                       timeout=60000, label=f"everyone at a desk before {label}")
            await page.evaluate(f"() => window.__dbg.play({{ idleMs: 1000, p: 1, kinds: ['{kind}'], minSec: 120, maxSec: 120, restMinSec: 0, restMaxSec: 0, solo: {{ p: 0 }} }})")
            await wait(page, "() => window.__dbg.play().robots.some((x) => x.play === 'going')", timeout=20000, label=f"{label}: on the way")
            way = await page.evaluate(SAMPLER, 1200)
            await page.evaluate("() => window.__dbg.play({ p: 0 })")   # this one game only
            await wait(page, "() => window.__dbg.play().list.some((g) => g.started)", timeout=30000, label=f"{label}: the game starts")
            return way, (await page.evaluate(play))["list"][0]

        async def stop(kind, r):
            await page.evaluate("() => window.__dbg.play({ p: 0, endAll: true })")
            await wait(page, "() => window.__dbg.play().list.length === 0 && window.__dbg.play().robots.every((x) => !x.back && x.path === 0)",
                       timeout=60000, label=f"{kind}: both back")
            await page.wait_for_timeout(300)
            after = await page.evaluate("() => window.__dbg.robots.map((R) => R.callText || '')")
            r["tagsAfter"] = after
            check(failures, all(t == "" for t in after), f"{kind}: the name tag is back to normal at the desk: {after}")

        async def pictures(kind, views, r):
            moments = r.setdefault("moments", {})
            for view in views:
                if view == "room":
                    await page.click(f".tag.room[data-set-project='{r['room']}']")
                    await wait(page, f"() => window.__dbg.solo() === '{r['room']}'", label="the room up close")
                    await page.wait_for_timeout(1500)
                for scheme in ("light", "dark"):
                    await page.emulate_media(color_scheme=scheme)
                    await page.wait_for_timeout(600)
                    moments[f"{view}-{scheme}"] = await moment(page, kind)
                    await page.screenshot(path=str(out / f"{kind}-{view}-{scheme}.png"))
                await page.emulate_media(color_scheme="light")
                if view == "room":
                    await page.click("#room-back")
                    await wait(page, "() => window.__dbg.solo() === null", label="back to the floor")
                    await page.wait_for_timeout(1500)

        # One room on the floor (the default view frames it): every arm, the card, pictures of the floor and the room.
        for kind in ("ball", "highfive", "rps"):
            r = res[kind] = {}
            way, G = await start(kind, kind)
            going_tags = sorted({s["tags"].get(i, "") for s in way for i in s["going"]})
            r["goingTags"] = going_tags
            check(failures, going_tags == [T("scene.play.going")], f"{kind}: the name tag says {T('scene.play.going')} on the way: {going_tags}")
            room, players = G["room"], G["players"]
            r["room"], r["players"] = room, players
            samples = await page.evaluate(SAMPLER, 9000 if kind == "rps" else 6000)
            on = [s for s in samples if s["started"] and s.get("bots")]
            r["n"] = len(on)
            tags = sorted({s["tags"].get(i, "") for s in on for i in players})
            r["tags"] = tags
            check(failures, len(on) > 30 and tags == [T(f"scene.play.{kind}")], f"{kind}: the name tag says {T(f'scene.play.{kind}')} while they play: {tags} ({len(on)} frames)")
            if kind == "ball":
                pxs = [s["ballPx"] for s in on if "ballPx" in s]
                r["ballPx"] = {"min": min(pxs) if pxs else None, "max": max(pxs) if pxs else None, "n": len(pxs)}
                check(failures, len(pxs) > 30 and min(pxs) >= BALL_PX, f"ball: {BALL_PX} px or more in the default view (one room): {r['ballPx']}")
                ys = [s["ballY"] for s in on if "ballY" in s]
                check(failures, ys and max(ys) - min(ys) > 0.3, f"ball: it flies: {min(ys) if ys else None}..{max(ys) if ys else None}")
                # the catcher: both hands out in front (forward of the body, near each other)
                both = [b for s in on for b in s["bots"] if b["l"][2] >= 0.38 and b["r"][2] >= 0.38 and abs(b["l"][0] - b["r"][0]) <= 0.7]
                r["catchFrames"] = len(both)
                check(failures, len(both) > 5, f"ball: the catcher holds both hands out ({len(both)} frames)")
            elif kind == "highfive":
                hands = [s["hand"] for s in on]
                centers = [s["center"] for s in on]
                touch = [s for s in on if s["hand"] <= HAND_TOUCH]
                r["hand"] = {"min": min(hands) if hands else None, "max": max(hands) if hands else None}
                r["center"] = {"min": min(centers) if centers else None, "max": max(centers) if centers else None}
                r["touchFrames"] = len(touch)
                r["markAtTouch"] = sum(1 for s in touch if s.get("mark"))
                r["markFrames"] = sum(1 for s in on if s.get("mark"))
                check(failures, hands and min(hands) <= HAND_TOUCH, f"highfive: two hands within {HAND_TOUCH} at some moment: {r['hand']}")
                check(failures, centers and max(centers) - min(centers) >= APPROACH, f"highfive: they walk toward each other ({APPROACH} or more): {r['center']}")
                check(failures, r["markAtTouch"] > 0, f"highfive: the パチン mark is up when the hands meet: {r['markAtTouch']} of {len(touch)}")
            else:
                vis = [all(b["vis"] for b in s["bots"]) for s in on]
                share = sum(vis) / len(vis) if vis else 0
                r["bubbleShare"] = round(share, 3)
                check(failures, share >= BUBBLE_SHARE, f"rps: the bubble is up {BUBBLE_SHARE:.0%} of the time or more: {share:.1%}")
                gaps = [s["t"] for s in on if any(b["st"] and not b["st"].get("shaking") and not b["vis"] for b in s["bots"])]
                known = [s for s in on if all(b["st"] for b in s["bots"])]
                r["bubbleGaps"] = len(gaps)
                check(failures, known and not gaps, f"rps: the bubble stays up from the reveal to the next pump: {len(gaps)} frames missing, {len(known)} with a phase")
                res_of = lambda b: (b["st"] or {}).get("res") or ""   # noqa: E731
                won = [s for s in on if sorted(res_of(b) for b in s["bots"]) == ["lose", "win"]]
                up = [s for s in won if all((b["l"][1] >= UP_Y and b["r"][1] >= UP_Y) == (res_of(b) == "win") for b in s["bots"])]
                r["winFrames"], r["winArmsUp"] = len(won), len(up)
                r["results"] = sorted({res_of(b) for s in on for b in s["bots"]})
                r["rounds"] = sorted({b["st"]["k"] for s in on for b in s["bots"] if b["st"]})
                check(failures, len(won) > 5 and len(up) >= len(won) * 0.8, f"rps: a winner and a loser are shown, the winner's both arms up: {len(up)} of {len(won)} frames")
                tie = r["tie"] = await page.evaluate(RPS_TIE)
                check(failures, tie.get("len") is not None and tie["len"] < tie["decided"] and tie["nextK"] == 1 and tie["nextW"] < tie["shake"],
                      f"rps: あいこ plays again at once (the next round's pumps follow the tie): {tie}")
            # the robot's card, the same words
            await page.evaluate("(id) => window.__dbg.openRobot(id)", players[0])
            try:
                await wait(page, "() => { const el = document.getElementById('rb'); return !el.hidden && getComputedStyle(el).opacity === '1'; }", timeout=8000, label="the card")
            except RuntimeError:
                pass
            await page.wait_for_timeout(700)
            card = await page.evaluate("() => { const el = document.querySelector('#rb [data-rb-state]'); return el ? el.textContent : null; }")
            r["card"] = card
            check(failures, card is not None and T(f"scene.play.{kind}") in card, f"{kind}: the robot's card says {T(f'scene.play.{kind}')}: {card!r}")
            await page.click("#rb-close")
            await wait(page, "() => document.getElementById('rb').hidden", label="the card closed")
            await page.wait_for_timeout(1500)                     # the camera back to the floor
            await pictures(kind, ("floor", "room"), r)
            await stop(kind, r)

        # Seven rooms (six more sessions, one robot each): two floors, so there is a building, and the floor's default
        # view frames six rooms — the far view. The page is opened again so the camera is the one it picks itself.
        for k in range(6):
            hook(f"e2e00000-0000-4000-8000-0000000000f{k}", hook_event_name="SessionStart", source="startup", cwd=f"/work/look-other-{k}")
        await page.evaluate("() => window.__dbg.play({ p: 0, endAll: true, solo: { p: 0 } })")
        await page.reload()
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').dataset.net === 'connected'", label="connected again")
        await wait(page, "() => window.__dbg.floors().floors.length >= 2 && window.__dbg.floors().floors.flat().length >= 7", timeout=30000, label="two floors")
        room = res["ball"].get("room")
        fl = await page.evaluate("() => window.__dbg.floors()")
        k = next((i for i, f in enumerate(fl["floors"]) if room in f), 0)
        if k != fl["floor"]:
            await page.evaluate(f"() => window.__dbg.goFloor({k - fl['floor']})")
        await wait(page, f"() => window.__dbg.floors().floor === {k}", label="the game's floor")
        await page.wait_for_timeout(2500)
        await wait(page, "() => window.__dbg.play().robots.every((x) => x.path === 0)", timeout=60000, label="everyone seated")
        res["far"] = {"floors": [len(f) for f in fl["floors"]], "floor": k}
        await page.evaluate("() => window.__dbg.play({ p: 0, solo: { p: 0 } })")
        for kind in ("ball", "highfive", "rps"):
            r = res["far"][kind] = {}
            way, G = await start(kind, f"{kind} (far)")
            r["room"], r["players"] = G["room"], G["players"]
            check(failures, G["room"] == room, f"{kind} (far): the game is in the same room: {G['room']} vs {room}")
            samples = await page.evaluate(SAMPLER, 3000)
            on = [s for s in samples if s["started"] and s.get("bots")]
            tags = sorted({s["tags"].get(i, "") for s in on for i in G["players"]})
            r["tags"] = tags
            check(failures, tags == [T(f"scene.play.{kind}")], f"{kind} (far): the name tag says {T(f'scene.play.{kind}')}: {tags}")
            if kind == "ball":
                pxs = [s["ballPx"] for s in on if "ballPx" in s]
                r["ballPx"] = {"min": min(pxs) if pxs else None, "max": max(pxs) if pxs else None, "n": len(pxs)}
                check(failures, len(pxs) > 15 and min(pxs) >= BALL_PX, f"ball: {BALL_PX} px or more in the default view (six rooms): {r['ballPx']}")
            await pictures(kind, ("floor6",), r)
            # the building: the window says the game
            if res["has"]["towerPlay"]:
                await page.evaluate("() => window.__dbg.tower(true)")
                await wait(page, "() => window.__dbg.floors().tower === true", label="in the building")
                await page.wait_for_timeout(2500)
                tp = r["tower"] = await page.evaluate("() => window.__dbg.towerPlay()")
                check(failures, any(T(f"scene.play.{kind}") in b for f in tp for b in f), f"{kind}: the building's window says {T(f'scene.play.{kind}')}: {tp}")
            else:
                await page.evaluate("() => window.__dbg.tower(true)")
                await page.wait_for_timeout(2500)
                check(failures, False, f"{kind}: the building's window says the game (no towerPlay on this page)")
            for scheme in ("light", "dark"):
                await page.emulate_media(color_scheme=scheme)
                await page.wait_for_timeout(1500)
                await page.screenshot(path=str(out / f"{kind}-building-{scheme}.png"))
            await page.emulate_media(color_scheme="light")
            await page.evaluate("() => window.__dbg.goFloor(0)")   # out of the building, to the floor it was entered from
            await wait(page, f"() => window.__dbg.floors().tower === false && window.__dbg.floors().floor === {k}", label="out of the building")
            await page.wait_for_timeout(2000)
            await stop(kind, r)
        await page.close()
        for line in watch.console:
            failures.append(f"play-look: console: {line}")
        for u in watch.foreign:
            failures.append(f"play-look: request outside the server: {u}")
        res["console"] = len(watch.console)
    except Exception as e:
        failures.append(f"play-look: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  play/look: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "play-look-results.json").write_text(dump(res) + "\n")
