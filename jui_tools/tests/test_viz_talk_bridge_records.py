"""A message that came through Remote Control's bridge, and the watch's reading of it (ticket
2026-11-09-cc-dependency-watch-red).

Measured on this machine's transcripts (11-05..11-09): 35 receiver records whose origin is
``{"kind": "peer", "from": "bridge:session_…", "fromMode", "name", "body"(, "hopChain")}`` — no msg_id, no
verifiedPeerPid — 31 as an isMeta user record and 4 as a queued_command, each message in one form only; every body is
exactly the sender's SendMessage text, and the sender's result has a msg_id. 7 of the senders wrote
``to: "bridge:session_…"``; ~/.claude/sessions/<pid>.json names that id as ``bridgeSessionId``.

Arms (talk.py): a bridge record and the sender's send are one row, read, whichever is seen first; a send to
``bridge:session_…`` lands on that session; a bridge record whose sender names another session is not matched to it;
one nobody's send matches is still a receiver-only row from the bridge's session.
Arms (cc_watch probes): a bridge record does not make the uds form's msg_id "some"; a coordinator record in a subagent
file past the byte budget is seen. Arm (session_files): a file with a stray "}" after the object is read.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

from jui_cli.viz import talk as T
from jui_cli.viz.sources import session_files as SF

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
from cc_watch import probes as P  # noqa: E402


from tests.test_viz_talk import A, B, D, NAMES, T0, Box, iso  # noqa: E402

BRIDGE = {A: "session_01AAAAAAAAAAAAAAAAAAAAAAAA", B: "session_01BBBBBBBBBBBBBBBBBBBBBBBB",
          D: "session_01DDDDDDDDDDDDDDDDDDDDDDDD"}


class BridgeBox(Box):
    def rows(self):
        return [dict(r, bridgeSessionId=BRIDGE[r["sessionId"]]) for r in super().rows()]

    def read_bridge(self, sid, at, sender, text, queued=False):
        origin = {"kind": "peer", "from": f"bridge:{BRIDGE[sender]}", "fromMode": "prompting", "name": NAMES[sender],
                  "body": text, "hopChain": [BRIDGE[sender]]}
        if queued:
            return {"type": "attachment", "timestamp": iso(at), "sessionId": sid, "uuid": self.uid(),
                    "attachment": {"type": "queued_command", "prompt": text, "source_uuid": self.uid(), "isMeta": True,
                                   "origin": origin}}
        return {"type": "user", "isMeta": True, "timestamp": iso(at), "sessionId": sid, "uuid": self.uid(),
                "origin": origin, "message": {"role": "user", "content": f"<cross-session-message>\n{text}\n</cross-session-message>"}}


@pytest.fixture
def box(tmp_path):
    b = BridgeBox(tmp_path)
    b.step(T0)
    yield b
    b.index.close()


@pytest.mark.parametrize("queued", [False, True])
def test_a_bridge_record_and_the_send_are_one_read_row(box, queued):
    box.write(box.files[A], box.send(A, "toolu_1", NAMES[B], "橋を渡った", T0 + 1_000),
              box.result(A, "toolu_1", T0 + 1_100, msg_id="m1"))
    box.write(box.files[B], box.read_bridge(B, T0 + 2_000, A, "橋を渡った", queued=queued))
    box.step(T0 + 3_000)
    box.step(T0 + 4_000 + T.HOLD_MS)            # past the hold: nothing left to settle into a second row
    for owner, other in ((A, B), (B, A)):
        [m] = box.messages(owner, other)
        assert (m["id"], m["state"], m["seen"], m["readAt"]) == ("m-m1", "read", "both", T0 + 2_000)


def test_the_bridge_record_first_is_matched_when_the_send_comes(box):
    box.write(box.files[B], box.read_bridge(B, T0 + 2_000, A, "先に届いた"))
    box.step(T0 + 3_000)
    box.write(box.files[A], box.send(A, "toolu_1", NAMES[B], "先に届いた", T0 + 1_000),
              box.result(A, "toolu_1", T0 + 1_100, msg_id="m1"))
    box.step(T0 + 4_000)
    box.step(T0 + 5_000 + T.HOLD_MS)
    [m] = box.messages(B, A)
    assert (m["id"], m["state"], m["seen"], m["readAt"]) == ("m-m1", "read", "both", T0 + 2_000)


def test_a_send_to_a_bridge_id_lands_on_that_session(box):
    box.write(box.files[A], box.send(A, "toolu_1", f"bridge:{BRIDGE[B]}", "宛先は橋", T0 + 1_000),
              box.result(A, "toolu_1", T0 + 1_100, msg_id="m1"))
    box.write(box.files[B], box.read_bridge(B, T0 + 2_000, A, "宛先は橋"))
    box.step(T0 + 3_000)
    box.step(T0 + 4_000 + T.HOLD_MS)
    [m] = box.messages(A, B)
    assert (m["id"], m["state"]) == ("m-m1", "read")
    assert [c["peer"]["key"] for c in box.convs(A)] == [B]


def test_a_bridge_record_from_another_session_is_not_matched(box):
    """D sent the same words to B over the bridge; A's send to B stays unread."""
    box.write(box.files[A], box.send(A, "toolu_1", NAMES[B], "同じ文", T0 + 1_000),
              box.result(A, "toolu_1", T0 + 1_100, msg_id="m1"))
    box.write(box.files[B], box.read_bridge(B, T0 + 2_000, D, "同じ文"))
    box.step(T0 + 3_000)
    box.step(T0 + 4_000 + T.HOLD_MS)
    [m] = box.messages(A, B)
    assert (m["id"], m["state"]) == ("m-m1", "delivered")
    [r] = box.messages(B, D)                    # the unmatched record: a row from D's session, not an external name
    assert r["dir"] == "in" and r["state"] == "read"


# ------------------------------------------------------------------ the watch's probe
def _line(path: Path, *recs):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")


def _peer(frm, msg_id=None):
    o = {"kind": "peer", "from": frm, "name": "x", "body": "b"}
    if msg_id:
        o.update(msg_id=msg_id, verifiedPeerPid=1)
    return {"type": "user", "isMeta": True, "timestamp": "2026-11-08T00:00:00Z", "origin": o}


def test_a_bridge_record_has_its_own_shape_and_leaves_the_uds_form_all(tmp_path):
    proj = tmp_path / "projects"
    _line(proj / "-w" / "s.jsonl", _peer("uds:/tmp/1.sock", "m1"), _peer("bridge:session_01X"))
    got = P.talk_origin(P.Context(run=None, session=None, transcripts=str(proj)))
    assert got["peer"]["msg_id"] == "all"
    assert got["bridge"] == {k: "all" for k in P.BRIDGE_ORIGIN_KEYS}


def test_a_coordinator_record_past_the_byte_budget_is_seen(tmp_path, monkeypatch):
    proj = tmp_path / "projects"
    big = proj / "-w" / "big.jsonl"
    _line(big, *[_peer("uds:/tmp/1.sock", f"m{i}") for i in range(200)])
    sub = proj / "-w" / "s" / "subagents" / "agent-a1.jsonl"
    _line(sub, {"type": "user", "timestamp": "2026-11-08T00:00:00Z", "origin": {"kind": "coordinator"},
                "message": {"role": "user", "content": "x"}})
    old = time.time() - 3_600
    os.utime(sub, (old, old))                   # older than the big file: read after it
    monkeypatch.setattr(P, "TALK_BYTES", big.stat().st_size)
    got = P.talk_origin(P.Context(run=None, session=None, transcripts=str(proj)))
    assert got["coordinator"] == "seen"


# ------------------------------------------------------------------ ~/.claude/sessions
@pytest.mark.parametrize("text, want", [
    ('{"sessionId": "s"}\n}', {"sessionId": "s"}),
    ('{"sessionId": "s"}}}\n', {"sessionId": "s"}),
    ('{"sessionId": "s"}x', None),
    ('{"sessionId": "s"}{"b": 1}', None),
    ('[1]', None),
])
def test_a_stray_brace_after_the_object_is_read(tmp_path, text, want):
    p = tmp_path / "123.json"
    p.write_text(text)
    assert SF.read_session_file(p) == want
