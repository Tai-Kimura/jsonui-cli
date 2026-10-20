"""Heavy work in three looks, one per cause (2.3.6; ticket 2026-10-19-jui-viz-heavy-work-three-looks).

The demo page on the fake server, the script frozen at HOLD s (e1 and 4f, both main, typing; e6, a subagent, typing;
b4, main, idle). The causes are set on a robot through window.__dbg.force (the server's _heavy decides them in the
live view; here only the look is under test), and everything is read from the robot itself (window.__dbg.looks):
the look now, the screen's colour (a pixel of the face canvas), the face drawn, the whistle, the sweat, the arm.

  - no cause: no look, no tint, no whistle;
  - tokens -> 'fired': the screen red (R over B), the fired face, no whistle;
  - tool -> 'drained': the screen blue (B over R), the drained face;
  - subagents -> 'whistle' on a main robot: the whistle, 「ピッ！」, the arm raised to wave; on a subagent: no look at all;
  - drained is not the 8-hour tiredness: b4 forced tired shows the tired face on the plain dark screen with the
    antenna down; the drained screen is far from that colour, its face differs and its antenna stays up;
  - two causes take turns: fired, then drained, then fired again (waits.until on the page's state, every frame);
  - the look clears when the cause ends: no look, the tint gone, the whistle hidden;
  - reduced motion: all three causes give the blue look only, held across two whole periods, and the whistle alone
    shows without the arm waving;
  - the robot card names the looks (the legend) while the work is heavy, and not otherwise.

Screenshots (light and dark): each look up close, the 8-hour tiredness beside it, two causes, the card.
"""
from __future__ import annotations

import pathlib
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, freeze, new_page, ready
from waits import until

HOLD = 48
MAIN, OTHER, SUB, TIRED = "e1", "4f", "e6", "b4"
SCREEN = (15, 24, 48)     # COL.screen: the face's dark screen with no tint
FAR = 40                  # how far (sum of channel differences) a tinted screen is from the plain one, at least
RAISED = -1.8             # armR.rotation.z of the arm waving up beside the head (typing: about -0.2)

LOOKS = "(ids) => window.__dbg.looks(ids)"


def check(failures, cond, text):
    if not cond:
        failures.append(f"heavy-looks: {text}")
    return cond


def dist(a, b):
    return sum(abs(x - y) for x, y in zip(a, b))


async def look_of(page, rid):
    """The robot's look read on a frame outside a blink. A blink (0.12 s, every 2.4–5.6 s) redraws the face as 'blink'
    over fired and tired alike; read at one instant, the arm saw 'blink' instead of the look's own face (2.3.5's whole
    e2e at 443fa709, ticket 2026-10-20-jui-viz-heavy-looks-reads-face-mid-blink). Waiting for a frame that is not a
    blink reads the same record, the face the look sets, and checks no less."""
    return await until(page, "(id) => { const x = window.__dbg.looks([id])[0]; return x.face !== 'blink' && x; }",
                       f"{rid}'s look outside a blink", arg=rid, why=f"() => window.__dbg.looks(['{rid}'])")


async def force(page, rid, **o):
    await page.evaluate("([id, o]) => window.__dbg.force(id, o)", [rid, o or None])


async def wait_look(page, rid, look, name, tint_settled=True):
    """Until the robot shows `look` (None: none), its tint eased in (or out) and its face redrawn."""
    js = """([id, look, settled]) => { const x = window.__dbg.looks([id])[0];
      if (x.look !== look) return false;
      if (!settled) return true;
      return x.eased && (look === 'fired' || look === 'drained' || look === 'whistle' ? x.face === look : true); }"""
    return await until(page, js, name, arg=[rid, look, tint_settled], why=f"() => window.__dbg.looks(['{rid}'])")


async def shot(page, out, name, rid=None):
    if rid:
        await page.evaluate("(id) => window.__dbg.faceCam(id)", rid)
        await page.wait_for_timeout(500)
    await page.screenshot(path=str(out / f"{name}.png"))


async def run_heavy_looks(pw, out, failures, Server):
    out = pathlib.Path(out) / "heavy-looks"
    out.mkdir(parents=True, exist_ok=True)
    srv = Server()
    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    watch = Watch(origin=srv.url)
    t0 = time.monotonic()
    res: dict = {}
    try:
        for scheme in ("light", "dark"):
            r = res[scheme] = {}
            page = await new_page(browser, watch, f"heavy-looks-{scheme}", color_scheme=scheme, **DESKTOP)
            await page.goto(f"{srv.url}/?demo=1")
            await ready(page)
            await freeze(page, HOLD)
            states = {x["id"]: (x["role"], x["state"]) for x in await page.evaluate(LOOKS, None)}
            r["states"] = {k: states.get(k) for k in (MAIN, OTHER, SUB, TIRED)}
            check(failures, states.get(MAIN) == ("main", "typing") and states.get(OTHER) == ("main", "typing")
                  and states.get(SUB, ("", ""))[0] != "main" and states.get(SUB, ("", ""))[1] == "typing"
                  and states.get(TIRED) == ("main", "idle"), f"{scheme}: the demo at {HOLD}s as the arms expect: {r['states']}")

            # no cause: nothing
            base = r["none"] = await look_of(page, MAIN)
            check(failures, base["look"] is None and not base["whistle"] and (not base["tint"] or base["tint"][3] < 0.02)
                  and dist(base["screen"], SCREEN) < 12, f"{scheme}: no cause, no look: {base}")
            await shot(page, out, f"none-{scheme}", MAIN)

            # each cause, its own look
            seen = {}
            for cause, look in (("tokens", "fired"), ("tool", "drained"), ("subagents", "whistle")):
                await force(page, MAIN, heavy=[cause])
                await wait_look(page, MAIN, look, f"{scheme}: {cause} shows {look}")
                if look == "whistle":
                    await until(page, f"(id) => window.__dbg.looks([id])[0].armRz < {RAISED}", f"{scheme}: the whistle's arm up",
                                arg=MAIN, why=f"() => window.__dbg.looks(['{MAIN}'])")
                x = seen[look] = await look_of(page, MAIN)
                await shot(page, out, f"{look}-{scheme}", MAIN)
            r["looks"] = seen
            f, d, w = seen["fired"], seen["drained"], seen["whistle"]
            check(failures, f["face"] == "fired" and f["screen"][0] > f["screen"][2] + 20 and dist(f["screen"], SCREEN) > FAR
                  and not f["whistle"] and f["sweat"], f"{scheme}: tokens: a red screen, the fired face, sweat, no whistle: {f}")
            check(failures, d["face"] == "drained" and d["screen"][2] > d["screen"][0] + 20 and dist(d["screen"], SCREEN) > FAR
                  and not d["whistle"] and d["sweat"], f"{scheme}: tool: a blue screen, the drained face, sweat: {d}")
            check(failures, w["face"] == "whistle" and w["whistle"] and w["pipi"] and w["armRz"] < RAISED,
                  f"{scheme}: subagents: the whistle, the face, ピッ, the waving arm: {w}")
            check(failures, len({f["face"], d["face"], w["face"]}) == 3 and dist(f["screen"], d["screen"]) > FAR,
                  f"{scheme}: three looks, not one: {[f['face'], d['face'], w['face']]} {f['screen']} {d['screen']}")

            # a subagent has no team: no whistle
            await force(page, SUB, heavy=["subagents"])
            await page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
            sub = r["subWhistle"] = await look_of(page, SUB)
            check(failures, sub["look"] is None and not sub["whistle"] and not sub["pipi"], f"{scheme}: a subagent never blows the whistle: {sub}")
            await force(page, SUB)

            # drained is not the 8-hour tiredness
            await force(page, MAIN, heavy=["tool"])
            await wait_look(page, MAIN, "drained", f"{scheme}: drained again")
            await force(page, TIRED, tired=True)
            await until(page, f"(id) => {{ const x = window.__dbg.looks([id])[0]; return x.tired && x.antenna > 0.9 && (x.face === 'tired' || x.face === 'blink'); }}",
                        f"{scheme}: b4 tired", arg=TIRED, why=f"() => window.__dbg.looks(['{TIRED}'])")
            tired, drained = await look_of(page, TIRED), await look_of(page, MAIN)
            r["tiredVsDrained"] = {"tired": tired, "drained": drained}
            check(failures, tired["face"] == "tired" and drained["face"] == "drained" and dist(tired["screen"], SCREEN) < 12
                  and dist(drained["screen"], tired["screen"]) > FAR and tired["antenna"] > 0.9 and drained["antenna"] < 0.2,
                  f"{scheme}: drained differs from 8 hours tired (face, screen colour, antenna): tired {tired} drained {drained}")
            await shot(page, out, f"tired-8h-{scheme}", TIRED)
            await force(page, TIRED)

            # two causes take turns
            await force(page, MAIN, heavy=["tokens", "tool"])
            turns = []
            for want in ("fired", "drained", "fired"):
                await wait_look(page, MAIN, want, f"{scheme}: two causes, turn to {want}", tint_settled=False)
                turns.append(want)
            r["turns"] = turns
            check(failures, turns == ["fired", "drained", "fired"], f"{scheme}: two causes alternate: {turns}")
            await wait_look(page, MAIN, "drained", f"{scheme}: two causes, drained for the picture")
            await shot(page, out, f"two-causes-{scheme}", MAIN)

            # the card names the looks while heavy
            await page.evaluate(f"() => window.__dbg.openRobot('{MAIN}')")
            await until(page, "() => { const el = document.querySelector('[data-rb-looks]'); return el && !el.hidden; }",
                        f"{scheme}: the card's legend shows", why="() => document.querySelector('[data-rb-looks]') && document.querySelector('[data-rb-looks]').outerHTML")
            legend = r["legend"] = await page.evaluate("() => document.querySelector('[data-rb-looks]').textContent")
            check(failures, all(w_ in legend for w_ in ("赤い顔", "青い顔", "笛")), f"{scheme}: the legend names the three looks: {legend!r}")
            check(failures, "裏で作業中でも、サブエージェント 3 体以上なら笛" in legend, f"{scheme}: the legend says the whistle shows in background work too: {legend!r}")
            await page.screenshot(path=str(out / f"card-{scheme}.png"))

            # the look clears when the cause ends
            await force(page, MAIN, heavy=[])
            await wait_look(page, MAIN, None, f"{scheme}: no cause again, no look")
            gone = r["cleared"] = await look_of(page, MAIN)
            check(failures, not gone["whistle"] and not gone["pipi"] and gone["face"] not in ("fired", "drained", "whistle") and dist(gone["screen"], SCREEN) < 12,
                  f"{scheme}: the look clears: {gone}")
            await until(page, "() => { const el = document.querySelector('[data-rb-looks]'); return el && el.hidden; }",
                        f"{scheme}: the legend hides once the work is not heavy")
            await page.close()

        # reduced motion: one look (blue > whistle > red), no turns, no waving
        page = await new_page(browser, watch, "heavy-looks-reduced", color_scheme="light", reduced_motion="reduce", **DESKTOP)
        await page.goto(f"{srv.url}/?demo=1")
        await ready(page)
        await freeze(page, HOLD)
        await force(page, MAIN, heavy=["tokens", "tool", "subagents"])
        await wait_look(page, MAIN, "drained", "reduced: all three causes, the blue look")
        period = (await look_of(page, MAIN))["period"]
        held = await page.evaluate("""([id, ms]) => new Promise((done) => { const t0 = performance.now(), seen = new Set();
          const step = () => { seen.add(window.__dbg.looks([id])[0].look); if (performance.now() - t0 < ms) requestAnimationFrame(step); else done([...seen]); };
          requestAnimationFrame(step); })""", [MAIN, int(period * 2200)])
        res["reduced"] = {"heldLooks": held}
        check(failures, held == ["drained"], f"reduced: no turns, blue held over two periods: {held}")
        await force(page, MAIN, heavy=["subagents"])
        await until(page, "(id) => window.__dbg.looks([id])[0].whistle", "reduced: the whistle", arg=MAIN)
        arms = await page.evaluate("""(id) => new Promise((done) => { const t0 = performance.now(), xs = [];
          const step = () => { xs.push(window.__dbg.looks([id])[0].armRz); if (performance.now() - t0 < 1500) requestAnimationFrame(step); else done(xs); };
          requestAnimationFrame(step); })""", MAIN)
        res["reduced"]["armMin"] = min(arms)
        check(failures, min(arms) > RAISED, f"reduced: the whistle without the waving arm (min armRz {min(arms)})")
        await shot(page, out, "whistle-reduced", MAIN)
        await page.close()
        for line in watch.console:
            failures.append(f"heavy-looks: console: {line}")
        for u in watch.foreign:
            failures.append(f"heavy-looks: request outside the server: {u}")
    finally:
        await browser.close()
        srv.stop()
    (out / "results.json").write_text(__import__("json").dumps(res, ensure_ascii=False, indent=1))
    print(f"  heavy-looks: {time.monotonic() - t0:.0f}s", flush=True)
    return res
