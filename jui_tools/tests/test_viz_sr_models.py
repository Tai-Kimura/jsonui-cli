"""The server room's models up close (56-sr-models.js; ticket 2026-10-22-viz-server-room-palette-and-light-flow §3), run
under node with a stand-in for THREE: every category the infra model has gives a model that is in the table, every
model the table has is made of parts, and each has a part in the cloud's own colour (tone 0) — the e2e rooms hold only
some kinds, so a model with no part of its cloud's colour (the envelope was all lighter and deeper tones) is caught here.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

from jui_cli.core.document_tools_import import load_document_tools_module
from tests.test_viz_bundle import web_text

model = load_document_tools_module("infra.model")[0]

STAND_IN = """
const made = (type) => class { constructor(...args) { this.type = type; this.args = args; } translate() { return this; } rotateY() { return this; } };
const THREE = new Proxy({}, { get: (_t, name) => made(String(name)) });
"""


def _run(cases: str):
    node = shutil.which("node")
    assert node, "node is needed (the jui_tools job has it; a skip would hide the arm)"
    src = web_text("js", "56-sr-models.js")
    out = subprocess.run([node, "-"], input=STAND_IN + src + f"\nprocess.stdout.write(JSON.stringify({cases}));",
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_every_category_gives_a_model_with_a_part_in_its_clouds_colour():
    cats = sorted(model.vocabulary("category"))
    got = _run(f"""(() => {{ const parts = srModelParts();
      const kinds = Object.fromEntries({json.dumps(cats)}.map((c) => [c, srModelKind({{ category: c }})]));
      const tones = Object.fromEntries(Object.entries(parts).map(([k, ps]) => [k, ps.map((p) => p[4])]));
      return {{ kinds, tones, broadcast: srModelKind({{ category: 'queue', service: 'sns' }}) }}; }})()""")
    kinds, tones = got["kinds"], got["tones"]
    assert {c: k for c, k in kinds.items() if k not in tones} == {}
    assert {k: t for k, t in tones.items() if not t or 0 not in t} == {}
    assert got["broadcast"] == "broadcast" and kinds["queue"] == "queue"
    # the kinds the ticket names each have a model of their own, not the plinth
    named = ["database.relational", "storage.object", "queue", "load_balancer", "edge.cdn", "compute.function", "cache", "gateway.api",
             "compute.vm", "compute.container", "client", "edge.dns", "auth", "scheduler"]
    assert {c: kinds[c] for c in named if kinds[c] == "plinth"} == {}


def test_every_kind_the_code_names_is_in_the_table():
    src = web_text("js", "56-sr-models.js")
    body = src[src.index("function srModelKind("):src.index("\n}\n", src.index("function srModelKind(")) + 3]
    named = set(re.findall(r"return '(\w+)'", body))
    tones = _run("Object.fromEntries(Object.entries(srModelParts()).map(([k, ps]) => [k, ps.length]))")
    assert named and named <= set(tones) and set(tones) <= named
