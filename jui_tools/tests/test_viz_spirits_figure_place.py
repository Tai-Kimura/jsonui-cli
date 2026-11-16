"""Where the page puts a model's figure: spirit.json's spirit.at, offset and rotate, and its scale once
(45-spirits.js spiritWear → spiritPut, run in node on the vendored three.js; ticket
2026-10-24-jui-viz-spirit-figure-ignores-offset-rotate).

Until 2.3.22 the figure was put with no spec: offset and rotate passed the checks (spirits.SPIRIT_FIELDS) and the
figure stood at its anchor, unturned. A part (parts[]) was given its spec and moved; the figure now is, the same way.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

from tests.test_viz_bundle import WEB, _match, web_text


def _defs(src: str, *names: str) -> str:
    """Each const object / function of 45-spirits.js by name, as written (a function's body opens after its ``)``)."""
    out = []
    for name in names:
        start = re.search(rf"\n(?:async )?function {name}\(|\nconst {name} = ", src).start() + 1
        if src.startswith("const", start):
            out.append(src[start:_match(src, src.index("{", start)) + 1] + ";")
        else:
            out.append(src[start:_match(src, src.index("{", src.index(")", start))) + 1])
    return "\n".join(out)


def _place(spirit: dict, parts: list | None = None):
    """The figure (and parts) as spiritWear leaves them: position, rotation (degrees), scale, and the holder's place."""
    node = shutil.which("node")
    assert node, "node is needed (the jui_tools job has it; a skip would hide the arm)"
    src = web_text("js", "45-spirits.js")
    three = WEB.joinpath("vendor", "three-0.160.0", "three.module.min.js")
    code = _defs(src, "SPIRIT", "SPIRIT_ANCHORS", "spiritDefaultAt", "spiritPut", "spiritWear")
    files = ["spirit.glb"] + [p["file"] for p in parts or []]
    script = f"""
import * as THREE from {json.dumps(str(three))};
const HEAD = {{ d: 1 }}, BAND = {{ y: 0.3 }};
const SkeletonUtils = {{ clone: (o) => o.clone() }};
const spiritRoom = () => true, spiritGhost = () => {{}}, spiritGhostShader = () => null, spiritOutline = () => {{}};
const spiritFxStart = () => {{}}, spiritClip = () => {{}}, vizNow = () => 0, reduceMotion = false;
const files = {json.dumps(files)};
const spiritLoad = async () => Object.fromEntries(files.map((f) => {{
  const scene = new THREE.Group(); scene.name = f; return [f, {{ scene, animations: [] }}];
}}));
{code}
const r = {{ root: new THREE.Group(), head: new THREE.Group(), armL: new THREE.Group(), armR: new THREE.Group() }};
const S = {{ model: {{ spec: {{ spirit: {json.dumps(spirit)}, parts: {json.dumps(parts or [])} }} }}, holders: [], hidden: [] }};
const R = {{ robot: r, spirit: S }};
const robots = [R];
await spiritWear(R, S);
const deg = (x) => Math.round(THREE.MathUtils.radToDeg(x) * 1000) / 1000;
const one = (o) => ({{ name: o.name, position: o.position.toArray(), rotate: o.rotation.toArray().slice(0, 3).map(deg),
  scale: o.scale.toArray(), holder: o.parent.position.toArray(),
  world: o.getWorldPosition(new THREE.Vector3()).toArray().map((v) => Math.round(v * 1000) / 1000) }});
process.stdout.write(JSON.stringify({{ figure: S.figure ? one(S.figure) : null,
  parts: S.holders.map((h) => one(h.children[0])).filter((p) => p.name !== 'spirit.glb') }}));
"""
    out = subprocess.run([node, "--input-type=module", "-"], input=script, capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_figure_takes_its_offset_and_rotate():
    got = _place({"file": "spirit.glb", "at": "back", "offset": [0, 1, 0], "rotate": [0, 90, 0]})["figure"]
    assert got["position"] == [0, 1, 0]
    assert got["rotate"] == [0, 90, 0]
    assert got["holder"] == [0, 0, -0.9]   # SPIRIT.back: the anchor, the offset on top of it
    assert got["world"] == [0, 1, -0.9]


def test_without_them_the_figure_stands_at_its_anchor_unturned():
    got = _place({"file": "spirit.glb", "at": "back"})["figure"]
    assert got["position"] == [0, 0, 0] and got["rotate"] == [0, 0, 0] and got["world"] == [0, 0, -0.9]


def test_its_scale_is_applied_once_and_does_not_scale_the_offset():
    got = _place({"file": "spirit.glb", "at": "root", "offset": [0, 1, 0], "scale": 2})["figure"]
    assert got["scale"] == [2, 2, 2]
    assert got["world"] == [0, 1, 0]


def test_the_figure_is_placed_as_a_part_with_the_same_spec_is():
    spec = {"at": "root", "offset": [0.2, 0.4, -0.3], "rotate": [10, 45, -5]}
    got = _place({"file": "spirit.glb", **spec}, parts=[{"file": "prop-x.glb", **spec}])
    part = got["parts"][0]
    for key in ("position", "rotate", "holder", "world"):
        assert got["figure"][key] == part[key], key
