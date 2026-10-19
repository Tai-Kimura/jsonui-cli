"""The talk view's demo data (jui_cli/viz/web/js/31-talk-demo-data.js), what the demo page shows without a server.

Every frame conforms to talk_contract.json; the file is what tools/viz_e2e/talk_demo_gen.py writes (so it is changed
there, not by hand); the ids, unread counts and badges agree with each other; the robots are the demo's own; it is
in the demo bundle only, never the live one; it holds no code.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from jui_cli.viz import bundle
from jui_cli.viz import talk_contract as C
from jui_cli.viz.talk import conv_id

JT = Path(__file__).resolve().parents[1]
FILE = JT / "jui_cli" / "viz" / "web" / "js" / "31-talk-demo-data.js"
DEMO_ROBOTS = {"a0", "a3", "a5", "a2", "a7", "b4", "e6", "f2", "d8", "4f", "7c", "c9", "e1"}


def data() -> dict:
    text = FILE.read_text(encoding="utf-8")
    m = re.search(r"^const TALK_DEMO = (\{.*\});\n\Z", text, re.S | re.M)
    assert m, "the file is one const of JSON"
    return json.loads(m.group(1))


def frames(d):
    yield d["badges"]
    yield from d["lists"].values()
    yield from d["messages"].values()
    yield from (s["frame"] for s in d["script"])


def test_every_frame_conforms_to_the_contract():
    d = data()
    assert d["contractVersion"] == C.load()["version"]
    for f in frames(d):
        assert C.validate(f) == [], (f["type"], C.validate(f)[:3])


def test_the_file_is_what_the_generator_writes(tmp_path):
    out = tmp_path / "gen.js"
    subprocess.run([sys.executable, str(JT / "tools" / "viz_e2e" / "talk_demo_gen.py"), str(out)], check=True)
    assert out.read_text(encoding="utf-8") == FILE.read_text(encoding="utf-8")


def test_ids_unread_and_badges_agree():
    d = data()
    for owner, listing in d["lists"].items():
        assert listing["agentId"] == owner
        for conv in listing["items"]:
            assert conv["id"] == conv_id(owner, conv["peer"]["key"]) and conv["owner"] == owner
            detail = d["messages"][f"{owner} {conv['id']}"]
            assert len(detail["items"]) == conv["count"]
            assert all(m["convId"] == conv["id"] for m in detail["items"])
            assert detail["items"][-1]["at"] == conv["lastAt"]
    totals = {o: sum(c["unread"] for c in l["items"]) for o, l in d["lists"].items()}
    assert d["badges"]["counts"] == {o: n for o, n in totals.items() if n}


def test_it_shows_every_case_the_ui_draws():
    d = data()
    msgs = [m for f in d["messages"].values() for m in f["items"]]
    peers = [c["peer"] for c in d["lists"]["a0"]["items"]]
    assert {m["state"] for m in msgs} >= {"read", "delivered", "undelivered"}
    assert {m["via"] for m in msgs} >= {"session", "subagent", "parent", "external"}
    assert any(not p["alive"] and p["kind"] == "session" for p in peers)          # a peer that ended, in its grace
    assert any(p["kind"] == "external" and p["agentId"] is None for p in peers)   # outside this machine
    assert any(len(p["name"]) > 40 for p in peers)                                 # a name cut to one line
    assert any(len(m["text"]) > 250 and "\n" in m["text"] for m in msgs)           # folded
    assert any("<script>" in m["text"] for m in msgs)                              # drawn as text
    ops = {op["op"] for s in d["script"] if s["frame"]["type"] == "talk.update" for op in s["frame"]["ops"]}
    assert ops == {"message", "conv", "remove"}


def test_the_robots_are_the_demos_own():
    d = data()
    keys = {c["peer"]["key"] for l in d["lists"].values() for c in l["items"]} | set(d["lists"])
    assert {k for k in keys if not k.startswith("x:")} <= DEMO_ROBOTS


def test_in_the_demo_bundle_only_and_data_only():
    assert "31-talk-demo-data.js" in bundle.parts("demo", e2e=False)
    assert "31-talk-demo-data.js" not in bundle.parts("live", e2e=False)
    code = "\n".join(l for l in FILE.read_text(encoding="utf-8").splitlines() if not l.startswith("//"))
    assert code.startswith("const TALK_DEMO = {") and "function" not in code.split("\n", 1)[0]
    assert "__dbg" not in FILE.read_text(encoding="utf-8")
