"""The skill spirit in the page (ticket 2026-10-21-jui-viz-skill-spirit). Runs with `--only spirits`.

The real `jui viz serve` in a throwaway HOME on a free port and the real forward.py. The HOME holds two models of the
person's own (copies of the bundled originals, each naming one skill, so the choice is known): "scholar" for
code-review (a bubble with ruby, glasses on the head), "gears" for band-test (it hides the band), and "textured" for
tex-test (a quad with an embedded PNG). Checked:
  * a Skill call: the robot's spirit loads, appears and stands (the figure and its parts on the robot), the badge says
    the skill, the bubble shows the model's words and ruby aimed at the spirit, the tag moves to the cheek
  * the scholar's ghost look, narrow eyes and the book's pose, its sparks; the gears' three afterimages, shouts and
    sparks, sharp eyes, typing
  * another session's skill hides its robot's band; the turn's Stop takes the spirit, the parts, the effects and the
    badge off and gives the band, the eyes and the pose back
  * an embedded texture is read (GLTFLoader's blob: URL under the page's CSP) and its picture loaded
  * five robots with a skill: four spirits stand at most
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


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


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


def _own_models(home: pathlib.Path, jt: pathlib.Path):
    """Three models of the person's own: the bundled originals, copied, each naming one skill, and a textured quad."""
    bundled = jt / "jui_cli" / "viz" / "web" / "spirits"
    own = home / ".local" / "state" / "jui-viz" / "spirits"
    for name, src, skill in (("scholar", "ink-scholar", "code-review"), ("gears", "gear-giant", "band-test")):
        shutil.copytree(bundled / src, own / name)
        spec = json.loads((own / name / "spirit.json").read_text(encoding="utf-8"))
        spec["skills"] = [skill]
        (own / name / "spirit.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    (own / "textured").mkdir()
    (own / "textured" / "spirit.glb").write_bytes(_textured_glb())
    (own / "textured" / "spirit.json").write_text(json.dumps({"version": 1, "skills": ["tex-test"],
                                                               "spirit": {"file": "spirit.glb", "opacity": 0.8}}), encoding="utf-8")


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

        # five skills at once: four spirits stand
        for i, k in enumerate(SIDS):
            skill(k, "code-review", f"v{i}")
        await wait(page, "(ls) => ls.every((l) => { const s = window.__dbg.spirit(l); return s && s.phase === 'shown'; })",
                   arg=list(who.values()), timeout=40000, label="five skills worn")
        standing = await page.evaluate("() => window.__dbg.spiritsStanding()")
        res["standing"] = standing
        check(standing == 4, f"four spirits stand at most: {standing}")
        await page.screenshot(path=str(out / "five.png"))
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
