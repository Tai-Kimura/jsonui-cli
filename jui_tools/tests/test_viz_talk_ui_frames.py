"""The talk view's page side against its contract (jui_cli/viz/talk_contract.json): what the page builds and what the demo
stand-in hands it are run under node and checked with ``talk_contract.validate``.

- 58-talk.js's ``talkFrame`` (the one place the page builds a request; it refuses what would not conform): every request
  it builds from good input conforms, and bad input (an id that does not match, a limit over pageMax, a key the
  contract does not have, a request the contract does not have — a send) is refused, not sent.
- Its rules are the contract's (patterns, lengths, pageMax), so the two cannot drift apart silently.
- 30-source-demo.js's ``talkStandIn`` (the demo's stand-in for the server), fed 31-talk-demo-data.js: every frame it
  emits through a session — open, get, get before, seen, the data's script (a new message, a read, a removal), the
  badges — conforms.
The blocks are cut out of the files by their markers (talk-frames / talk-demo), so the code tested is the code served.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from importlib import resources

import pytest

from jui_cli.viz import talk_contract as C

JS = resources.files("jui_cli.viz").joinpath("web", "js")
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def block(name: str, marker: str) -> str:
    text = JS.joinpath(name).read_text(encoding="utf-8")
    m = re.search(rf"/\* {marker}:begin \*/\n(.*?)/\* {marker}:end \*/", text, re.S)
    assert m, f"{name}: no {marker} block"
    return m.group(1)


HARNESS = r"""
const out = { built: [], refused: [], server: [], rules: TALK_RULES };
const CONV = 't-0123456789abcdef';
const good = [
  ['talk.open', { reqId: 'tk1', agentId: 'a07c09fe-2f17-530c-add4-737ff77c3934' }],
  ['talk.open', { reqId: 7, agentId: 'a3f19c2e8b7d4a601' }],
  ['talk.close', {}],
  ['talk.close', { reqId: 'tk2' }],
  ['talk.get', { reqId: 'tk3', agentId: 's-owner', convId: CONV }],
  ['talk.get', { reqId: 'tk4', agentId: 's-owner', convId: CONV, before: 'm-0b7c1f2a-1111-4222-8333-444455556666', limit: 30 }],
  ['talk.get', { reqId: 'tk5', agentId: 's-owner', convId: CONV, before: 'r-sid:uuid', limit: 100 }],
  ['talk.get', { reqId: 'tk6', agentId: 's-owner', convId: CONV, before: undefined, limit: 1 }],
  ['talk.seen', { reqId: 'tk7', agentId: 's-owner', convId: CONV, upTo: 0 }],
  ['talk.seen', { reqId: 'tk8', agentId: 's-owner', convId: CONV, upTo: 1760900000000 }],
];
const bad = [
  ['talk.open', { reqId: 'tk1', agentId: '' }],
  ['talk.open', { reqId: 'tk1', agentId: 'a/../b' }],
  ['talk.open', { reqId: 'tk1', agentId: 'x'.repeat(129) }],
  ['talk.open', { agentId: 's-owner' }],
  ['talk.open', { reqId: true, agentId: 's-owner' }],
  ['talk.get', { reqId: 'tk', agentId: 's-owner', convId: 't-XYZ' }],
  ['talk.get', { reqId: 'tk', agentId: 's-owner', convId: CONV, limit: 101 }],
  ['talk.get', { reqId: 'tk', agentId: 's-owner', convId: CONV, limit: 0 }],
  ['talk.get', { reqId: 'tk', agentId: 's-owner', convId: CONV, limit: 2.5 }],
  ['talk.get', { reqId: 'tk', agentId: 's-owner', convId: CONV, before: 'x-1' }],
  ['talk.get', { reqId: 'tk', agentId: 's-owner', convId: CONV, before: 'm-' + 'a'.repeat(199) }],
  ['talk.seen', { reqId: 'tk', agentId: 's-owner', convId: CONV, upTo: -1 }],
  ['talk.seen', { reqId: 'tk', agentId: 's-owner', convId: CONV }],
  ['talk.seen', { reqId: 'tk', agentId: 's-owner', convId: CONV, upTo: 1, text: 'hi' }],
  ['talk.send', { reqId: 'tk', agentId: 's-owner', convId: CONV, text: 'hi' }],
  ['talk.post', { reqId: 'tk', text: 'hi' }],
];
for (const [t, f] of good) out.built.push(talkFrame(t, f));
for (const [t, f] of bad) out.refused.push([t, f, talkFrame(t, f)]);

const S = talkStandIn(TALK_DEMO, 1800000000000);
const emit = (frames) => { for (const f of frames) out.server.push(f); return frames; };
emit([S.badges()]);
let req = 0;
const ask = (type, fields) => { const f = talkFrame(type, { reqId: `tk${++req}`, ...fields }); out.built.push(f); return emit(S.handle(f)); };
for (const owner of Object.keys(TALK_DEMO.lists)) {
  const list = ask('talk.open', { agentId: owner })[0];
  for (const c of list.items) {
    let page = ask('talk.get', { agentId: owner, convId: c.id, limit: 1 })[0];
    while (page.more) page = ask('talk.get', { agentId: owner, convId: c.id, before: page.items[0].id, limit: 1 })[0];
    ask('talk.seen', { agentId: owner, convId: c.id, upTo: c.lastAt });
  }
}
for (const x of S.script) emit(S.apply(x.frame));
const gone = TALK_DEMO.script.find((x) => x.frame.ops && x.frame.ops.some((o) => o.op === 'remove')).frame;
ask('talk.get', { agentId: gone.agentId, convId: gone.ops.find((o) => o.op === 'remove').convId });   // gone: a failed ack
ask('talk.close', {});
process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    data = JS.joinpath("31-talk-demo-data.js").read_text(encoding="utf-8")
    src = "\n".join([block("58-talk.js", "talk-frames"), data, block("30-source-demo.js", "talk-demo"), HARNESS])
    path = tmp_path_factory.mktemp("talk") / "harness.js"
    path.write_text(src, encoding="utf-8")
    done = subprocess.run([NODE, str(path)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_every_request_the_page_builds_conforms(run):
    assert run["built"] and all(f is not None for f in run["built"])
    problems = {json.dumps(f, ensure_ascii=False): C.validate(f) for f in run["built"]}
    assert {k: v for k, v in problems.items() if v} == {}
    assert {f["type"] for f in run["built"]} == {"talk.open", "talk.close", "talk.get", "talk.seen"}


def test_a_request_that_would_break_the_contract_is_refused(run):
    for kind, fields, built in run["refused"]:
        assert built is None, (kind, fields, built)
        # and the contract agrees it is broken (so the page refuses only what the server would refuse)
        assert C.validate({"type": kind, **{k: v for k, v in fields.items() if v is not None}}), (kind, fields)


def test_the_page_never_builds_a_send():
    """依頼者の確定（10-20）: トークから送らない。the page's request table has no send, and no request carries a text."""
    text = JS.joinpath("58-talk.js").read_text(encoding="utf-8")
    fields = re.search(r"const TALK_FIELDS = \{(.*?)\n\};", text, re.S).group(1)
    assert set(re.findall(r"'(talk\.[a-z]+)'", fields)) == set(C.load()["requests"])
    assert "text" not in fields and "send" not in fields.replace("talkSend", "")


def test_the_page_rules_are_the_contract(run):
    root, rules = C.load(), run["rules"]
    d = root["$defs"]
    assert rules["agentId"] == d["agentId"]["pattern"] and rules["agentIdMax"] == d["agentId"]["maxLength"]
    assert rules["convId"] == d["convId"]["pattern"]
    assert rules["messageId"] == d["messageId"]["pattern"]
    assert (rules["messageIdMin"], rules["messageIdMax"]) == (d["messageId"]["minLength"], d["messageId"]["maxLength"])
    assert rules["pageMax"] == C.limits()["pageMax"] == root["requests"]["talk.get"]["properties"]["limit"]["maximum"]


def test_every_frame_the_demo_stand_in_emits_conforms(run):
    frames = [f for f in run["server"] if f.get("type") != "ack"]
    kinds = {f["type"] for f in frames}
    assert kinds == {"talk.list", "talk.messages", "talk.update", "talk.badges"}, kinds
    ops = {op["op"] for f in frames if f["type"] == "talk.update" for op in f["ops"]}
    assert ops == {"message", "conv", "remove"}
    bad = [(f["type"], p) for f in frames for p in [C.validate(f)] if p]
    assert bad == []
    acks = [f for f in run["server"] if f.get("type") == "ack"]
    assert len(acks) == 1 and acks[0]["ok"] is False   # the get on the removed talk


def test_the_demo_has_what_the_view_shows(run):
    """The stand-in, fed the demo data, serves every case the e2e (talk-ui) and the screenshots rely on."""
    frames = run["server"]
    msgs = [m for f in frames if f["type"] == "talk.messages" for m in f["items"]]
    convs = [c for f in frames if f["type"] == "talk.list" for c in f["items"]]
    assert {m["state"] for m in msgs} == {"read", "delivered", "undelivered"}
    assert {m["via"] for m in msgs} >= {"session", "subagent", "parent", "external"}
    assert any(c["peer"]["agentId"] is None for c in convs) and any(not c["peer"]["alive"] for c in convs)
    assert any(len(c["peer"]["name"]) > 40 for c in convs)
    assert any(f["type"] == "talk.messages" and f["more"] for f in frames)
    assert any("<script>" in m["text"] for m in msgs)
    first = frames[0]
    assert first == {"type": "talk.badges", "counts": {"a0": 2}}
    # seen everything: the badges fall to nothing
    assert {"type": "talk.badges", "counts": {}} in frames
