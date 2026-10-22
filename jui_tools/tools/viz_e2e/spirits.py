"""The skill spirit in the page (ticket 2026-10-21-jui-viz-skill-spirit). Runs with `--only spirits`.

The real `jui viz serve` in a throwaway HOME on a free port and the real forward.py. The HOME holds four models of the
person's own (copies of the bundled originals, each naming one skill, so the choice is known): "scholar" for
code-review (a bubble with ruby, glasses on the head), "gears" for band-test (it hides the band; a glow, a flame aura,
sparks at rate 40 and three bolts added), "textured" for tex-test (a quad with an embedded PNG) and "skinned" for
glow-test (a skinned strip, a turning square and an fx_ card, with an outline and a glow). Checked:
  * a Skill call: the robot's spirit loads, appears and stands (the figure and its parts on the robot), the badge says
    the skill, the bubble shows the model's words and ruby aimed at the spirit, the tag moves to the cheek
  * the scholar's ghost look, narrow eyes and the book's pose, its sparks; the gears' three afterimages, shouts and
    sparks, sharp eyes, typing
  * another session's skill hides its robot's band; the turn's Stop takes the spirit, the parts, the effects and the
    badge off and gives the band, the eyes and the pose back
  * an embedded texture is read (GLTFLoader's blob: URL under the page's CSP) and its picture loaded
  * the outline and effects.glow are posed as the figure, frame by frame: on the gears' turning gears and on "skinned"
    (glow-test: a strip whose bones its loop clip swings, a square whose own node turns), and never on an fx_ node;
    the glow's rim the same on a mesh scaled 2; none in the afterimages; hidden on a third spirit (past fullFx)
  * the gears' effects: a flame aura (an envelope and rising tongues), rate 40's 64 sparks, three bolts with width
  * five robots with a skill: four spirits stand at most, and their bubbles cross neither each other nor the tags
  * the frames' cost with 0 to 4 spirits (measured on a third page and written to the results, not judged)
  * reduced motion (a second page): the spirit stands still, no sparks, afterimages or shouts
  * seen from far (the robots drawn smaller than SPIRIT.minPx): no spirit and no effects; the parts stay on
  * no console error (the .glb are read through POST /api/spirit-file and GLTFLoader.parse, under the page's CSP)
No network outside the server.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

from common import DESKTOP, ISOLATE, LAUNCH_ARGS, Watch, dump, new_page, ready

SIDS = {f"r{i}": f"e2e00000-0000-4000-8000-00000000c0{i}0" for i in range(1, 6)}
CWD = "/work/spirits"


FRAME_COST_JS = """(() => {
  const raf = window.requestAnimationFrame.bind(window);
  const work = [], gaps = []; let last = 0, on = false;
  window.requestAnimationFrame = (cb) => raf((ts) => {
    const t0 = performance.now(); cb(ts); const t1 = performance.now();
    if (on) { work.push(t1 - t0); if (last) gaps.push(t0 - last); }
    last = t0;
  });
  const stat = (xs) => { const s = [...xs].sort((a, b) => a - b); const mean = s.reduce((a, b) => a + b, 0) / (s.length || 1);
    return [+mean.toFixed(2), +(s[Math.floor(s.length * 0.95)] || 0).toFixed(2), s.length]; };
  window.__frameCost = { sample: (ms) => new Promise((ok) => { work.length = 0; gaps.length = 0; last = 0; on = true;
    setTimeout(() => { on = false; const [workMean, workP95, frames] = stat(work), [gapMean] = stat(gaps);
      ok({ workMean, workP95, gapMean, frames }); }, ms); }) };
})()"""


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def seen(page, js, arg, timeout=10000) -> bool:
    """Whether js comes true within timeout (a check, not a stop: the arms after it still run)."""
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
        return True
    except Exception:  # noqa: BLE001
        return False


def _textured_glb() -> bytes:
    """A quad with an embedded PNG texture (a 4x4 picture), written by hand: the bundled originals hold no texture, and
    GLTFLoader reads an embedded one through a blob: URL the page's CSP must let it read."""
    import struct
    import zlib
    raw = b"".join(b"\x00" + bytes([200, 40, 40, 255]) * 4 for _ in range(4))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))  # noqa: E731
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    pos = struct.pack("<12f", -0.5, 0, 0, 0.5, 0, 0, 0.5, 1, 0, -0.5, 1, 0)
    uv = struct.pack("<8f", 0, 1, 1, 1, 1, 0, 0, 0)
    idx = struct.pack("<6H", 0, 1, 2, 0, 2, 3)   # 12 bytes: the image starts at 92
    img = png + b"\x00" * (-len(png) % 4)
    blob = pos + uv + idx + img
    views = [{"buffer": 0, "byteOffset": 0, "byteLength": 48}, {"buffer": 0, "byteOffset": 48, "byteLength": 32},
             {"buffer": 0, "byteOffset": 80, "byteLength": 12}, {"buffer": 0, "byteOffset": 92, "byteLength": len(png)}]
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0, "name": "quad"}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2, "material": 0}]}],
           "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
           "textures": [{"source": 0}], "images": [{"bufferView": 3, "mimeType": "image/png"}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 4, "type": "VEC3", "min": [-0.5, 0, 0], "max": [0.5, 1, 0]},
                         {"bufferView": 1, "componentType": 5126, "count": 4, "type": "VEC2"},
                         {"bufferView": 2, "componentType": 5123, "count": 6, "type": "SCALAR"}],
           "bufferViews": views, "buffers": [{"byteLength": len(blob)}]}
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    body = struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(blob), 0x004E4942) + blob
    return struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body


def _skinned_glb() -> bytes:
    """A strip two units tall, skinned to two bones (its top row to the second); a square beside it whose own node turns
    and is scaled 2 ("spinner"); and a flat card under a node named fx_card. The loop clip swings the second bone and turns the spinner
    (written by hand: the bundled originals move their nodes, not bones, and have no fx_ node)."""
    import math
    import struct
    rows = (0.0, 1.0, 2.0)
    square = lambda: struct.pack("<12f", -0.2, -0.2, 0, 0.2, -0.2, 0, 0.2, 0.2, 0, -0.2, 0.2, 0)  # noqa: E731
    flat = lambda: struct.pack("<12f", *[0, 0, 1] * 4)  # noqa: E731
    quat = lambda axis, a: tuple(math.sin(a / 2) * c for c in axis) + (math.cos(a / 2),)  # noqa: E731
    parts = [
        struct.pack("<18f", *[c for y in rows for c in (-0.3, y, 0, 0.3, y, 0)]),                          # 0 strip pos
        struct.pack("<18f", *[0, 0, 1] * 6),                                                                # 1 strip nrm
        struct.pack("<24H", *[c for y in rows for c in ((0, 0, 0, 0) if y < 2 else (1, 0, 0, 0)) * 2]),     # 2 joints
        struct.pack("<24f", *[1, 0, 0, 0] * 6),                                                             # 3 weights
        struct.pack("<12H", 0, 1, 3, 0, 3, 2, 2, 3, 5, 2, 5, 4),                                            # 4 strip idx
        struct.pack("<32f", *(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1), *(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, -1, 0, 1)),  # 5 ibm
        struct.pack("<3f", 0, 0.5, 1),                                                                      # 6 times
        struct.pack("<12f", *quat((0, 0, 1), -0.6), *quat((0, 0, 1), 0.6), *quat((0, 0, 1), -0.6)),         # 7 bone1 turns
        struct.pack("<12f", *quat((0, 1, 0), 0), *quat((0, 1, 0), 1.5), *quat((0, 1, 0), 3.0)),             # 8 spinner turns
        square(), flat(), struct.pack("<6H", 0, 1, 2, 0, 2, 3),                                             # 9-11 spinner
        square(), flat(), struct.pack("<6H", 0, 1, 2, 0, 2, 3),                                             # 12-14 the fx_ card
    ]
    views, at = [], 0
    for b in parts:
        views.append({"buffer": 0, "byteOffset": at, "byteLength": len(b)})
        at += len(b)
    acc = lambda v, ct, n, t, **k: {"bufferView": v, "componentType": ct, "count": n, "type": t, **k}  # noqa: E731
    sq = lambda v: acc(v, 5126, 4, "VEC3", min=[-0.2, -0.2, 0], max=[0.2, 0.2, 0])  # noqa: E731
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0, 2, 3, 4]}],
           "nodes": [{"name": "bone0", "children": [1]}, {"name": "bone1", "translation": [0, 1, 0]},
                     {"name": "strip", "mesh": 0, "skin": 0},
                     {"name": "spinner", "mesh": 1, "translation": [0.8, 1, 0], "scale": [2, 2, 2]},
                     {"name": "fx_card", "mesh": 2, "translation": [-0.8, 1, 0]}],
           "skins": [{"joints": [0, 1], "inverseBindMatrices": 5}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1, "JOINTS_0": 2, "WEIGHTS_0": 3}, "indices": 4}]},
                      {"primitives": [{"attributes": {"POSITION": 9, "NORMAL": 10}, "indices": 11}]},
                      {"primitives": [{"attributes": {"POSITION": 12, "NORMAL": 13}, "indices": 14}]}],
           "accessors": [acc(0, 5126, 6, "VEC3", min=[-0.3, 0, 0], max=[0.3, 2, 0]), acc(1, 5126, 6, "VEC3"),
                         acc(2, 5123, 6, "VEC4"), acc(3, 5126, 6, "VEC4"), acc(4, 5123, 12, "SCALAR"),
                         acc(5, 5126, 2, "MAT4"), acc(6, 5126, 3, "SCALAR", min=[0], max=[1]), acc(7, 5126, 3, "VEC4"),
                         acc(8, 5126, 3, "VEC4"), sq(9), acc(10, 5126, 4, "VEC3"), acc(11, 5123, 6, "SCALAR"),
                         sq(12), acc(13, 5126, 4, "VEC3"), acc(14, 5123, 6, "SCALAR")],
           "animations": [{"name": "loop", "samplers": [{"input": 6, "output": 7}, {"input": 6, "output": 8}],
                           "channels": [{"sampler": 0, "target": {"node": 1, "path": "rotation"}},
                                        {"sampler": 1, "target": {"node": 3, "path": "rotation"}}]}],
           "bufferViews": views, "buffers": [{"byteLength": at}]}
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    blob = b"".join(parts)
    body = struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(blob), 0x004E4942) + blob
    return struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body


def _own_models(home: pathlib.Path, jt: pathlib.Path):
    """Three models of the person's own: the bundled originals, copied, each naming one skill, and a textured quad."""
    bundled = jt / "jui_cli" / "viz" / "web" / "spirits"
    own = home / ".local" / "state" / "jui-viz" / "spirits"
    for name, src, skill in (("scholar", "ink-scholar", "code-review"), ("gears", "gear-giant", "band-test")):
        shutil.copytree(bundled / src, own / name)
        spec = json.loads((own / name / "spirit.json").read_text(encoding="utf-8"))
        spec["skills"] = [skill]
        if name == "gears":   # a glow on its turning gears, a flame aura, sparks at their most, three bolts at a time
            spec["effects"]["glow"] = {"color": "#ffd060", "opacity": 0.3, "scale": 1.03}
            spec["effects"]["aura"] = {"color": "#ffd23a", "height": 2, "opacity": 0.4}
            spec["effects"]["sparks"] = {**spec["effects"]["sparks"], "rate": 40, "size": 0.18}
            spec["effects"]["lightning"] = {"count": 3, "everySec": 0.3}
        (own / name / "spirit.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    (own / "textured").mkdir()
    (own / "textured" / "spirit.glb").write_bytes(_textured_glb())
    (own / "textured" / "spirit.json").write_text(json.dumps({"version": 1, "skills": ["tex-test"],
                                                               "spirit": {"file": "spirit.glb", "opacity": 0.8}}), encoding="utf-8")
    (own / "skinned").mkdir()
    (own / "skinned" / "spirit.glb").write_bytes(_skinned_glb())
    (own / "skinned" / "spirit.json").write_text(json.dumps({"version": 1, "skills": ["glow-test"], "spirit": {"file": "spirit.glb", "outline": {"color": "#101010", "width": 0.02}},
                                                              "effects": {"glow": {"color": "#ff6a10", "opacity": 0.3, "scale": 1.03}}}),
                                                  encoding="utf-8")


async def run_spirits(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "spirits"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    _own_models(home, jt)
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log,
                           stderr=subprocess.STDOUT, env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"
    res: dict = {"steps": []}

    def check(cond, text):
        if not cond:
            failures.append(f"spirits: {text}")

    def hook(k, **payload):
        subprocess.run([sys.executable, "-I", "-S", str(forward)], timeout=10, capture_output=True, env=dict(base_env, HOME=str(home)),
                       input=json.dumps({"session_id": SIDS[k], "cwd": CWD, "transcript_path": "/work/none.jsonl",
                                         "permission_mode": "default", **payload}).encode())

    def skill(k, name, use):
        hook(k, hook_event_name="PreToolUse", tool_name="Skill", tool_input={"skill": name, "args": ""}, tool_use_id=use)

    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    t0 = time.monotonic()
    try:
        import urllib.request
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        for k in SIDS:
            hook(k, hook_event_name="SessionStart", source="startup")
        watch = Watch(origin=url)
        page = await new_page(browser, watch, "spirits", **DESKTOP)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelectorAll('#sessions [data-robot-open]').length >= 5", label="five sessions")
        who = await page.evaluate("(sids) => Object.fromEntries(Object.entries(sids).map(([k, sid]) => [k, window.__dbg.labelOfSession(sid)]))", SIDS)
        res["who"] = who
        state = "(l) => window.__dbg.spirit(l)"

        async def shells_follow(k, kind, what):
            """The outline's or the glow's shells are posed as the figure: twice, 0.5 s apart, each shell's world matrix
            (and its bones') is its mesh's, while the figure itself has moved; every mesh has one but those under an fx_
            node (tickets 2026-10-22-viz-spirit-glow-scales-about-root and -aura-too-weak)."""
            a = await page.evaluate("([l, k]) => window.__dbg.spiritShells(l, k)", [who[k], kind])
            await page.wait_for_timeout(500)
            b = await page.evaluate("([l, k]) => window.__dbg.spiritShells(l, k)", [who[k], kind])
            res["steps"].append({"step": f"{k} {kind}", "a": a, "b": b})
            check(a and b and a["shells"] > 0 and a["gap"] < 1e-3 and b["gap"] < 1e-3 and not a["lost"],
                  f"{what}: posed as the figure: {a} -> {b}")
            check(a and b and b["mixerTime"] > a["mixerTime"] and abs(b["pose"] - a["pose"]) > 1e-3,
                  f"{what}: the figure moved between the two looks: {a} -> {b}")
            check(a and a["bare"] == 0 and a["onFx"] == 0, f"{what}: one on each mesh, none under an fx_ node: {a}")
            return b

        # a skill: the spirit stands, the parts are on, the badge and the bubble say what the model says
        skill("r1", "code-review", "u1")
        await wait(page, "(l) => { const s = window.__dbg.spirit(l); return s && s.phase === 'shown'; }", arg=who["r1"],
                   timeout=30000, label="r1's spirit standing")
        await wait(page, "(l) => { const s = window.__dbg.spirit(l); return s && s.bubble; }", arg=who["r1"], label="r1's bubble")
        s1 = await page.evaluate(state, who["r1"])
        res["steps"].append({"step": "r1 code-review", **s1})
        check(s1["model"] == "own/scholar" and s1["figure"] and s1["holders"] == 4 and not s1["error"],
              f"r1 wears the scholar: its figure, the glasses, the scroll and its effects: {s1}")
        # the page's language (run.py pins ja unless JUI_VIZ_LANGUAGE says otherwise): the badge is the table's, the
        # bubble the model's own words in that language
        ja = (await page.evaluate("() => document.documentElement.lang")) == "ja"
        badge, words, ruby = (("スキル使用中: code-review", "筆を執る", "レビュー") if ja
                              else ("Using skill: code-review", "Taking up the brush", "review"))
        check(s1["badge"] == badge, f"the badge says the skill: {s1['badge']!r}")
        check(s1["bubble"] and s1["bubble"]["text"] == words + ruby and s1["bubble"]["ruby"] == ruby
              and s1["bubble"]["target"] == "spirit", f"the bubble is the model's, its ruby, at the spirit: {s1['bubble']}")
        check(s1["cheek"], "a part on the head moves the tag to the cheek")
        # the look and what the robot does: the ghost and its outline, the eyes and pose spirit.json names, the sparks
        await wait(page, "(l) => { const s = window.__dbg.spirit(l); return s.fx && s.fx.sparks > 0; }", arg=who["r1"],
                   timeout=10000, label="r1's sparks rising")
        s1 = await page.evaluate(state, who["r1"])
        check(s1["ghost"] and s1["eyes"] == "narrow" and (s1["face"] or "").startswith("spirit") and s1["pose"] == "book",
              f"the scholar: the ghost look, narrow eyes on the face, the book's pose: {s1}")
        await page.screenshot(path=str(out / "scholar.png"))

        # another session's skill hides its band; the turn's Stop takes everything off
        skill("r2", "band-test", "u2")
        await wait(page, "(l) => { const s = window.__dbg.spirit(l); return s && s.phase === 'shown'; }", arg=who["r2"],
                   timeout=30000, label="r2's spirit standing")
        s2 = await page.evaluate(state, who["r2"])
        res["steps"].append({"step": "r2 band-test", **s2})
        check(s2["model"] == "own/gears" and s2["band"] is False, f"the gears hide r2's band: {s2}")
        await wait(page, "(l) => { const s = window.__dbg.spirit(l); return s.fx && s.fx.shouts > 0 && s.fx.sparks > 0; }",
                   arg=who["r2"], timeout=10000, label="r2's shouts and sparks")
        s2 = await page.evaluate(state, who["r2"])
        check(s2["fx"]["clones"] == 3 and s2["eyes"] == "sharp" and s2["pose"] == "type",
              f"the gears: three afterimages, sharp eyes, typing: {s2}")
        check(s2["fx"]["cloneShells"] == 0, f"the gears' afterimages carry no outline and no glow: {s2['fx']}")
        await shells_follow("r2", "glow", "the gears' glow (turning gears)")
        await shells_follow("r2", "outline", "the gears' outline (turning gears)")
        # the flame aura: an envelope and 32 tongues that rise (their heights change) and show
        a = await page.evaluate(state, who["r2"])
        await page.wait_for_timeout(300)
        b = await page.evaluate(state, who["r2"])
        check(a["fx"]["auraStyle"] == "flame" and a["fx"]["tongues"] == 32 and a["fx"]["tongueY"] != b["fx"]["tongueY"]
              and b["fx"]["tongueTop"] > 0.1, f"the gears' aura is flames that rise: {a['fx']} -> {b['fx']}")
        # sparks at rate 40: a pool of 64, and more than the 24 of before alight at once
        check(b["fx"]["sparkPool"] == 64, f"rate 40's pool holds 64 sparks: {b['fx']}")
        check(await seen(page, "(l) => window.__dbg.spirit(l).fx.sparks > 24", who["r2"]),
              "more than 24 of the gears' sparks alight at once (rate 40)")
        # the lightning: three bolts, ribbons with width, shown in turn
        check(b["fx"]["bolts"] == 3 and b["fx"]["boltWidth"] >= 0.03, f"three bolts, each a ribbon with width: {b['fx']}")
        check(await seen(page, "(l) => window.__dbg.spirit(l).fx.boltShown", who["r2"]), "a bolt shown")
        bolt = (await page.evaluate(state, who["r2"]))["fx"]
        check(bolt["boltGap"] is not None and bolt["boltGap"] < 1e-3, f"each bolt is one unbroken zigzag: {bolt}")
        await page.screenshot(path=str(out / "gears-effects.png"))
        hook("r1", hook_event_name="Stop")
        hook("r2", hook_event_name="Stop")
        await wait(page, "(ls) => ls.every((l) => { const s = window.__dbg.spirit(l); return s && !s.phase && !s.badge && !s.skill; })",
                   arg=[who["r1"], who["r2"]], label="r1 and r2 back to themselves")
        after = [await page.evaluate(state, who[k]) for k in ("r1", "r2")]
        res["steps"].append({"step": "after Stop", "r1": after[0], "r2": after[1]})
        check(after[1]["band"] is True and after[0]["holders"] == 0 and not after[0]["eyes"] and not after[1]["pose"]
              and not (after[0]["face"] or "").startswith("spirit"), f"the band, the eyes and the pose are back; nothing is worn: {after}")

        # an embedded texture: GLTFLoader reads it through a blob: URL, under the page's CSP
        skill("r3", "tex-test", "u3")
        await wait(page, "(l) => { const s = window.__dbg.spirit(l); return s && s.phase === 'shown'; }", arg=who["r3"],
                   timeout=30000, label="r3's textured spirit standing")
        await wait(page, "(l) => window.__dbg.spirit(l).textures.loaded > 0 || window.__dbg.spirit(l).error", arg=who["r3"],
                   timeout=15000, label="the texture's picture")
        s3 = await page.evaluate(state, who["r3"])
        res["steps"].append({"step": "r3 tex-test", **s3})
        check(s3["model"] == "own/textured" and s3["textures"] == {"maps": 1, "loaded": 1} and not s3["error"],
              f"the embedded texture is read and drawn: {s3}")
        hook("r3", hook_event_name="Stop")
        await wait(page, "(l) => !window.__dbg.spirit(l).phase", arg=who["r3"], label="r3 back to itself")

        # a glow on a skinned figure: bound to the figure's own bones, it is posed as the figure is, frame by frame
        skill("r3", "glow-test", "u4")
        await wait(page, "(l) => { const s = window.__dbg.spirit(l); return s && s.phase === 'shown'; }", arg=who["r3"],
                   timeout=30000, label="r3's skinned spirit standing")
        for kind in ("glow", "outline"):
            g = await shells_follow("r3", kind, f"the skinned model's {kind}")
            check(g and g["bones"] > 0 and g["fxMeshes"] == 1 and g["shells"] == g["meshes"] - 1,
                  f"the skinned model's {kind}: on the skinned strip (its bones) and the spinner, not the fx_ card: {g}")
            if kind == "glow":
                check(g and g["reach"] < 0.01, f"the skinned model's glow: the same rim on the strip and on the spinner (scaled 2): {g}")
        await page.screenshot(path=str(out / "glow-skinned.png"))
        hook("r3", hook_event_name="Stop")
        await wait(page, "(l) => !window.__dbg.spirit(l).phase", arg=who["r3"], label="r3 back to itself")

        # three glows standing: the SPIRIT.fullFx (2) nearest the camera draw theirs, the third hides it
        trio = [who[k] for k in ("r1", "r2", "r3")]
        for i, k in enumerate(("r1", "r2", "r3")):
            skill(k, "glow-test", f"g{i}")
        await wait(page, "(ls) => ls.every((l) => { const s = window.__dbg.spirit(l); return s && s.phase === 'shown'; })",
                   arg=trio, timeout=40000, label="three skinned spirits standing")
        lod = "(ls) => ls.map((l) => window.__dbg.spiritShells(l, 'glow'))"
        lod_ok = f"(ls) => {{ const g = ({lod})(ls); return g.filter((x) => x.hidden === 0).length === 2 && g.filter((x) => x.hidden === x.shells).length === 1; }}"
        ok = await seen(page, lod_ok, trio)
        g = await page.evaluate(lod, trio)
        res["steps"].append({"step": "three glows", "glow": g})
        check(ok, f"three glows: two drawn, the farthest hidden: {g}")
        for k in ("r1", "r2", "r3"):
            hook(k, hook_event_name="Stop")
        await wait(page, "(ls) => ls.every((l) => !window.__dbg.spirit(l).phase)", arg=trio, label="r1-r3 back to themselves")

        # five skills at once: four spirits stand
        for i, k in enumerate(SIDS):
            skill(k, "code-review", f"v{i}")
        await wait(page, "(ls) => ls.every((l) => { const s = window.__dbg.spirit(l); return s && s.phase === 'shown'; })",
                   arg=list(who.values()), timeout=40000, label="five skills worn")
        standing = await page.evaluate("() => window.__dbg.spiritsStanding()")
        res["standing"] = standing
        check(standing == 4, f"four spirits stand at most: {standing}")
        await page.screenshot(path=str(out / "five.png"))

        # the bubbles aimed at spirits keep off each other (and the tags): no two shown boxes cross
        boxes = "(ls) => ls.map((l) => window.__dbg.spirit(l).bubbleBox).filter(Boolean)"
        await wait(page, f"(ls) => ({boxes})(ls).length >= 2", arg=list(who.values()), timeout=10000, label="two bubbles shown")
        shown = await page.evaluate(boxes, list(who.values()))
        crossed = [(i, j) for i in range(len(shown)) for j in range(i + 1, len(shown))
                   if shown[i]["left"] < shown[j]["right"] and shown[j]["left"] < shown[i]["right"]
                   and shown[i]["top"] < shown[j]["bottom"] and shown[j]["top"] < shown[i]["bottom"]]
        res["bubbles"] = shown
        check(not crossed, f"no two spirit bubbles cross: {crossed} of {shown}")

        # reduced motion: the spirits stand still, and no sparks, afterimages or shouts
        still = await new_page(browser, watch, "spirits-reduced", reduced_motion="reduce", **DESKTOP)
        await still.goto(url + "/")
        await ready(still)
        await wait(still, "(l) => { const s = window.__dbg.spirit(l); return s && s.phase === 'shown'; }", arg=who["r1"],
                   timeout=30000, label="r1's spirit standing, reduced motion")
        t_a = (await still.evaluate(state, who["r1"]))["mixerTime"]
        await still.wait_for_timeout(1500)
        r1 = await still.evaluate(state, who["r1"])
        res["reduced"] = r1
        check(r1["mixerTime"] == t_a and r1["fx"]["sparks"] == 0 and r1["fx"]["clones"] == 0 and r1["fx"]["shouts"] == 0,
              f"reduced motion: no clip runs, no sparks, afterimages or shouts: {t_a} -> {r1}")
        await still.close()

        # the frames' cost with 0 to 4 spirits standing (a measurement, written to the results; not a pass or a fail:
        # the machine is shared and its load moves it). Each requestAnimationFrame callback is timed on the main thread
        # (the page's whole frame, the WebGL calls it submits included, not the GPU's own time).
        for k in SIDS:
            hook(k, hook_event_name="Stop")
        frames = await new_page(browser, watch, "spirits-frames", **DESKTOP)
        await frames.add_init_script(FRAME_COST_JS)
        await frames.goto(url + "/")
        await ready(frames)
        await wait(frames, "(ls) => ls.every((l) => { const s = window.__dbg.spirit(l); return s && !s.phase; })",
                   arg=list(who.values()), label="no spirit before the frames are measured")
        cost = {}
        # the fair base: four robots busy with an ordinary tool, no skill (a Skill call is a tool call: its robot works)
        for i in range(1, 5):
            hook(f"r{i}", hook_event_name="PreToolUse", tool_name="Read", tool_input={"file_path": f"{CWD}/a.py"},
                 tool_use_id=f"busy{i}")
        await frames.wait_for_timeout(1500)
        cost["0, four busy"] = {**await frames.evaluate("() => window.__frameCost.sample(3000)"),
                                **await frames.evaluate("() => window.__dbg.mainDraw()")}
        for i in range(1, 5):
            hook(f"r{i}", hook_event_name="Stop")
        await frames.wait_for_timeout(1500)
        for n in range(0, 5):
            if n:
                skill(f"r{n}", "code-review", f"f{n}")
                await wait(frames, "(l) => { const s = window.__dbg.spirit(l); return s && s.phase === 'shown'; }",
                           arg=who[f"r{n}"], timeout=30000, label=f"{n} spirits standing")
            await frames.wait_for_timeout(500)
            cost[str(n)] = {**await frames.evaluate("() => window.__frameCost.sample(3000)"),
                       **await frames.evaluate("() => window.__dbg.mainDraw()")}
        # what the four cost: their figures hidden (parts and effects kept), then their effects hidden too
        for label, js in (("4, figures hidden", "() => window.__dbg.spiritHide('figure')"),
                          ("4, figures and effects hidden", "() => window.__dbg.spiritHide('all')"),
                          ("4, and the badges and bubbles hidden", "() => window.__dbg.spiritHide('dom')")):
            await frames.evaluate(js)
            await frames.wait_for_timeout(300)
            cost[label] = {**await frames.evaluate("() => window.__frameCost.sample(3000)"),
                           **await frames.evaluate("() => window.__dbg.mainDraw()")}
        await frames.evaluate("() => window.__dbg.spiritHide(null)")
        res["frameCost"] = cost
        print(f"  spirits frame cost (ms: work mean / p95, interval mean; draw calls): "
              + ", ".join(f"{n}: {c['workMean']} / {c['workP95']}, {c['gapMean']}; {c['calls']}" for n, c in cost.items()), flush=True)
        await frames.close()
        for k in ("r1", "r2", "r3", "r4"):
            hook(k, hook_event_name="Stop")
        for i, k in enumerate(SIDS):
            skill(k, "code-review", f"w{i}")
        await wait(page, "(ls) => ls.every((l) => { const s = window.__dbg.spirit(l); return s && s.phase === 'shown'; })",
                   arg=list(who.values()), timeout=40000, label="five skills worn again")

        # a floor seen from far (the robots drawn small): no spirit, no effects; the parts stay on
        await page.evaluate("() => { const c = window.__dbg.camera; c.position.multiplyScalar(8); }")
        await wait(page, "(l) => { const s = window.__dbg.spirit(l); return s.near === false && !s.figureShown; }",
                   arg=who["r1"], timeout=10000, label="r1's spirit resting, seen from far")
        far = await page.evaluate(state, who["r1"])
        res["far"] = far
        check(far["holders"] == 4 and far["phase"] == "shown", f"seen from far the parts stay on: {far}")
        await page.close()
        for line in watch.console:
            failures.append(f"spirits: console: {line}")
        for u in watch.foreign:
            failures.append(f"spirits: request outside the server: {u}")
    except Exception as e:
        failures.append(f"spirits: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  spirits: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "spirits-results.json").write_text(dump(res) + "\n")
