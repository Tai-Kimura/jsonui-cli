"""The talk view's data (viz/talk.py, viz/sources/talk_records.py; ticket 2026-10-20-jui-viz-talk-view).

Transcripts here are written in the shapes measured on 10-20 (the plan's research, and the keys of this machine's
records): the sender's tool_use ``SendMessage`` and its ``toolUseResult.msg_id``; the receiver's ``isMeta`` user record
or ``queued_command`` attachment with ``origin`` {kind peer, msg_id, from, verifiedPeerPid, name, body}; a subagent's
send to ``main`` (``senderTaskId``) and the parent's send to a subagent (``origin.kind`` coordinator).

Arms: matching by msg_id (two sends from one sender, the second read: only the second is read), duplicates dropped
(tool_use and receiver records written twice), undelivered shown and never matched, subagent talks in both directions,
the 1 h grace (kept within it, removed after, never at once), a comeback rebuilt, unread and badges, every frame
checked against talk_contract.json, nothing on the event loop, no path in a frame, the database under the state home.
"""
from __future__ import annotations

import asyncio
import json
import os
import stat
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from jui_cli.viz import talk as T
from jui_cli.viz import talk_contract as C

A = "0a0a0a0a-1111-4111-8111-aaaaaaaaaaaa"
B = "0b0b0b0b-2222-4222-8222-bbbbbbbbbbbb"
D = "0d0d0d0d-4444-4444-8444-dddddddddddd"
CHILD = "a1b2c3d4e5f6a7b8c"
NAMES = {A: "shop-app-a1", B: "shop-app-b2", D: "admin-web-d4"}
PIDS = {A: 101, B: 102, D: 104}
T0 = 1_792_300_000_000
GRACE = 3_600_000


def iso(at):
    return datetime.fromtimestamp(at / 1000, timezone.utc).isoformat().replace("+00:00", "Z")


class Box:
    """A projects folder, a registry and an index over them."""

    def __init__(self, tmp_path: Path, grace=GRACE):
        self.projects = tmp_path / "projects"
        self.folder = self.projects / "-work-shop"
        self.folder.mkdir(parents=True)
        self.alive = {A, B, D}
        self.files = {sid: self.folder / f"{sid}.jsonl" for sid in (A, B, D)}
        for f in self.files.values():
            f.write_text("")
        self.db = tmp_path / "state" / "talk.db"
        self.index = T.TalkIndex(self.db, self.projects, tmp_path / "sessions", grace, registry=self.rows)
        self.n = 0

    def rows(self):
        return [{"sessionId": s, "pid": PIDS[s], "name": NAMES[s], "messagingSocketPath": f"/tmp/socks/{PIDS[s]}.sock"}
                for s in sorted(self.alive)]

    def child_file(self, sid=A, aid=CHILD):
        p = self.folder / sid / "subagents" / f"agent-{aid}.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text("")
        return p

    def write(self, path: Path, *recs):
        with path.open("a", encoding="utf-8") as fh:
            for r in recs:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    def uid(self):
        self.n += 1
        return f"u-{self.n:04d}-0000-4000-8000-000000000000"

    # ---- the shapes
    def send(self, sid, use_id, to, text, at, summary="要約", sub=None):
        rec = {"type": "assistant", "timestamp": iso(at), "sessionId": sid, "uuid": self.uid(),
               "message": {"id": f"msg_{use_id}", "role": "assistant", "content": [
                   {"type": "tool_use", "id": use_id, "name": "SendMessage",
                    "input": {"to": to, "message": text, "summary": summary}}]}}
        if sub:
            rec["agentId"] = sub
        return rec

    def result(self, sid, use_id, at, msg_id=None, text=None, error=False):
        tur = {"success": True, "message": "ok", "display": "x"}
        if msg_id:
            tur["msg_id"] = msg_id
        body = text or json.dumps(tur)
        return {"type": "user", "timestamp": iso(at), "sessionId": sid, "uuid": self.uid(),
                "toolUseResult": tur if not text else {"success": True, "message": text},
                "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": use_id, "content": body,
                                                         **({"is_error": True} if error else {})}]}}

    def read_meta(self, sid, at, msg_id, sender, text, uuid=None, members=None):
        origin = {"kind": "peer", "from": f"uds:/tmp/socks/{PIDS[sender]}.sock", "verifiedPeerPid": PIDS[sender],
                  "msg_id": msg_id, "name": NAMES[sender], "fromMode": "prompting", "body": text}
        if members:
            origin["members"] = [{"body": m} for m in members]
            del origin["body"]
        return {"type": "user", "isMeta": True, "timestamp": iso(at), "sessionId": sid, "uuid": uuid or self.uid(),
                "origin": origin, "message": {"role": "user", "content": f"<cross-session-message>\n{text}\n</cross-session-message>"}}

    def read_queued(self, sid, at, msg_id, sender, text):
        return {"type": "attachment", "timestamp": iso(at), "sessionId": sid, "uuid": self.uid(),
                "attachment": {"type": "queued_command", "prompt": "wrapped", "source_uuid": self.uid(), "isMeta": True,
                               "origin": {"kind": "peer", "from": f"uds:/tmp/socks/{PIDS[sender]}.sock",
                                          "verifiedPeerPid": PIDS[sender], "msg_id": msg_id, "name": NAMES[sender],
                                          "body": text}}}

    def enqueue(self, sid, at, sender, text):
        return {"type": "queue-operation", "operation": "enqueue", "timestamp": iso(at), "sessionId": sid,
                "content": f'<cross-session-message from="uds:/tmp/socks/{PIDS[sender]}.sock" from-name="{NAMES[sender]}">\n{text}\n</cross-session-message>'}

    def step(self, at):
        got = self.index.step(at)
        for owner, ops in got["ops"].items():
            frame = {"type": "talk.update", "agentId": owner, "ops": ops[:100]}
            assert C.validate(frame) == [], C.validate(frame)
        return got

    def messages(self, owner, other):
        cid = T.conv_id(owner, other)
        got = self.index.messages(owner, cid)
        if got is None:
            return None
        frame = {"type": "talk.messages", "reqId": 1, "agentId": owner, "convId": cid, "items": got[0], "more": got[1]}
        assert C.validate(frame) == [], C.validate(frame)
        return got[0]

    def convs(self, owner, now=T0):
        items, more = self.index.conversations(owner, now)
        frame = {"type": "talk.list", "reqId": 1, "agentId": owner, "items": items, "more": more}
        assert C.validate(frame) == [], C.validate(frame)
        return items


@pytest.fixture
def box(tmp_path):
    b = Box(tmp_path)
    b.step(T0)                     # caught up on empty files
    yield b
    b.index.close()


# ------------------------------------------------------------------ list and detail
def test_a_message_between_two_sessions_is_one_row_in_both_lists(box):
    box.write(box.files[A], box.send(A, "toolu_1", NAMES[B], "こんにちは\n2 行目", T0 + 1_000),
              box.result(A, "toolu_1", T0 + 1_400, msg_id="m1"))
    box.write(box.files[B], box.enqueue(B, T0 + 1_200, A, "こんにちは\n2 行目"),
              box.read_meta(B, T0 + 2_000, "m1", A, "こんにちは\n2 行目"))
    box.step(T0 + 3_000)
    for owner, other, d in ((A, B, "out"), (B, A, "in")):
        [conv] = box.convs(owner)
        assert conv["peer"]["key"] == other and conv["peer"]["name"] == NAMES[other] and conv["peer"]["alive"]
        assert conv["preview"] == "こんにちは" and conv["count"] == 1 and conv["lastDir"] == d
        [m] = box.messages(owner, other)
        assert (m["id"], m["dir"], m["state"], m["seen"]) == ("m-m1", d, "read", "both")
        assert (m["at"], m["deliveredAt"], m["readAt"]) == (T0 + 1_000, T0 + 1_200, T0 + 2_000)
        assert m["summary"] == "要約" and m["text"] == "こんにちは\n2 行目"


def test_matching_is_by_msg_id_not_by_sender_name_or_body(box):
    """Two sends from A to B, the same words; B read only the second: only the second is read. Matching by the
    sender's name (the first open one) or by the body would mark the first."""
    box.write(box.files[A], box.send(A, "toolu_1", NAMES[B], "同じ文", T0 + 1_000),
              box.result(A, "toolu_1", T0 + 1_100, msg_id="m1"),
              box.send(A, "toolu_2", NAMES[B], "同じ文", T0 + 2_000),
              box.result(A, "toolu_2", T0 + 2_100, msg_id="m2"))
    box.write(box.files[B], box.read_queued(B, T0 + 5_000, "m2", A, "同じ文"))
    box.step(T0 + 6_000)
    got = {m["id"]: m["state"] for m in box.messages(A, B)}
    assert got == {"m-m1": "delivered", "m-m2": "read"}


def test_the_receivers_side_first_lands_on_the_same_row(box):
    box.write(box.files[B], box.read_meta(B, T0 + 2_000, "m9", A, "先に読まれた"))
    box.step(T0 + 3_000)
    [m] = box.messages(B, A)
    assert (m["id"], m["seen"], m["dir"]) == ("m-m9", "receiver", "in")
    box.write(box.files[A], box.send(A, "toolu_9", NAMES[B], "先に読まれた", T0 + 1_000),
              box.result(A, "toolu_9", T0 + 1_100, msg_id="m9"))
    box.step(T0 + 4_000)
    [m] = box.messages(B, A)
    assert (m["id"], m["seen"], m["at"], m["readAt"]) == ("m-m9", "both", T0 + 1_000, T0 + 2_000)


def test_duplicates_are_dropped_by_tool_use_id_and_msg_id(box):
    """A tool_use written twice and a read record written again later (Remote Control's copy, same uuid): one row,
    and the read time is the first record's."""
    send = box.send(A, "toolu_1", NAMES[B], "一度だけ", T0 + 1_000)
    box.write(box.files[A], send, box.result(A, "toolu_1", T0 + 1_100, msg_id="m1"), send)
    first = box.read_meta(B, T0 + 2_000, "m1", A, "一度だけ", uuid="rc-0001")
    box.write(box.files[B], first)
    box.step(T0 + 3_000)
    again = dict(first, timestamp=iso(T0 + 50_000))
    box.write(box.files[B], again, box.read_queued(B, T0 + 60_000, "m1", A, "一度だけ"))
    box.write(box.files[A], send)
    got = box.step(T0 + 61_000)
    assert [m["id"] for m in box.messages(A, B)] == ["m-m1"]
    assert box.messages(A, B)[0]["readAt"] == T0 + 2_000
    assert not any(op["op"] == "message" for ops in got["ops"].values() for op in ops)   # nothing changed


def test_a_bundled_read_marks_both_sends(box):
    box.write(box.files[A], box.send(A, "toolu_1", NAMES[B], "一つ目", T0 + 1_000),
              box.result(A, "toolu_1", T0 + 1_100, msg_id="m1"),
              box.send(A, "toolu_2", NAMES[B], "二つ目", T0 + 1_500),
              box.result(A, "toolu_2", T0 + 1_600, msg_id="m2"))
    box.write(box.files[B], box.read_meta(B, T0 + 3_000, "m1", A, None, members=["一つ目", "二つ目"]))
    box.step(T0 + 4_000)
    got = {m["id"]: (m["state"], m["merged"]) for m in box.messages(A, B)}
    assert got == {"m-m1": ("read", True), "m-m2": ("read", True)}


# ------------------------------------------------------------------ undelivered
def test_an_undelivered_send_is_shown_marked_and_never_matched(box):
    """"No agent named … is reachable" (not is_error) and an is_error result: both undelivered, to an external peer
    that cannot be switched to. The same body read by B from another send stays on that send only."""
    box.write(box.files[A], box.send(A, "toolu_1", "nobody-here", "一斉送信", T0 + 1_000),
              box.result(A, "toolu_1", T0 + 1_100, text="No agent named \"nobody-here\" is reachable."),
              box.send(A, "toolu_2", "gone-too", "別の文", T0 + 1_200),
              box.result(A, "toolu_2", T0 + 1_300, text="Error", error=True),
              box.send(A, "toolu_3", NAMES[B], "一斉送信", T0 + 1_400),
              box.result(A, "toolu_3", T0 + 1_500, msg_id="m3"))
    box.write(box.files[B], box.read_meta(B, T0 + 2_000, "m3", A, "一斉送信"))
    box.step(T0 + 3_000)
    peers = {c["peer"]["key"]: c for c in box.convs(A)}
    nobody = peers[T.external_key("nobody-here")]
    assert nobody["peer"]["kind"] == "external" and nobody["peer"]["agentId"] is None
    [u] = box.messages(A, T.external_key("nobody-here"))
    assert (u["id"], u["state"], u["readAt"], u["deliveredAt"], u["via"]) == ("u-toolu_1", "undelivered", None, None, "external")
    [e] = box.messages(A, T.external_key("gone-too"))
    assert e["state"] == "undelivered"
    [b] = box.messages(A, B)
    assert (b["id"], b["state"]) == ("m-m3", "read")


# ------------------------------------------------------------------ subagents
def test_subagent_talks_both_ways_are_included(box):
    """The parent's send to its subagent (to: the agent id; the child reads a coordinator queued_command) and the
    subagent's send to main (the parent reads origin.senderTaskId). The hand-back is not a talk."""
    child = box.child_file()
    box.write(box.files[A], box.send(A, "toolu_p", CHILD, "子への指示", T0 + 1_000),
              box.result(A, "toolu_p", T0 + 1_050, text="Message queued for delivery to " + CHILD))
    box.write(child, {"type": "attachment", "timestamp": iso(T0 + 1_500), "uuid": box.uid(), "agentId": CHILD,
                      "attachment": {"type": "queued_command", "prompt": "子への指示", "source_uuid": box.uid(),
                                     "isMeta": True, "origin": {"kind": "coordinator"}}},
              box.send(A, "toolu_c", "main", "親への報告", T0 + 2_000, sub=CHILD),
              box.result(A, "toolu_c", T0 + 2_050))
    box.write(box.files[A], {"type": "user", "isMeta": True, "timestamp": iso(T0 + 2_500), "uuid": box.uid(),
                             "origin": {"kind": "peer", "from": CHILD, "senderTaskId": CHILD, "name": "worker", "body": "親への報告"},
                             "message": {"role": "user", "content": "<agent-message>親への報告</agent-message>"}},
              {"type": "user", "isMeta": True, "timestamp": iso(T0 + 9_000), "uuid": box.uid(),
               "origin": {"kind": "peer", "from": CHILD, "senderTaskId": CHILD, "handback": True, "body": "最後の返事"},
               "message": {"role": "user", "content": "[Subagent hand-back] 最後の返事"}})
    box.step(T0 + 10_000)
    [conv] = box.convs(A)
    assert conv["peer"]["key"] == CHILD and conv["peer"]["kind"] == "subagent" and conv["peer"]["sessionId"] == A
    got = [(m["dir"], m["text"], m["state"], m["via"]) for m in box.messages(A, CHILD)]
    assert got == [("out", "子への指示", "read", "subagent"), ("in", "親への報告", "read", "parent")]
    [mine] = box.convs(CHILD)
    assert mine["peer"]["key"] == A


def test_a_coordinator_user_record_matches_by_containment(box):
    child = box.child_file()
    box.write(box.files[A], box.send(A, "toolu_p", CHILD, "途中の指示", T0 + 1_000),
              box.result(A, "toolu_p", T0 + 1_050, text="Message queued"))
    box.write(child, {"type": "user", "isMeta": True, "timestamp": iso(T0 + 1_500), "uuid": box.uid(), "agentId": CHILD,
                      "origin": {"kind": "coordinator"},
                      "message": {"role": "user", "content": "The coordinator sent a message while you were working:\n途中の指示\n\nAddress this before completing your current task."}})
    box.step(T0 + 2_000)
    [m] = box.messages(A, CHILD)
    assert (m["state"], m["readAt"]) == ("read", T0 + 1_500)


def test_a_receivers_record_no_send_matches_becomes_its_own_row_once(box):
    """A cloud message (no msg_id, no sender here): held, then one receiver-only row once caught up and old enough;
    reading the file again never adds a second."""
    box.write(box.files[B], {"type": "user", "isMeta": True, "timestamp": iso(T0 + 1_000), "uuid": "cloud-0001",
                             "origin": {"kind": "peer", "from": "unknown", "name": "cloud-bot", "body": "雲から"},
                             "message": {"role": "user", "content": "x"}})
    box.step(T0 + 2_000)
    assert box.convs(B) == []
    box.step(T0 + 2_000 + T.HOLD_MS)
    [conv] = box.convs(B)
    [m] = box.messages(B, conv["peer"]["key"])
    assert m["id"].startswith("r-") and m["seen"] == "receiver" and conv["peer"]["kind"] == "external"
    box.index.db.execute("UPDATE files SET off=0")
    box.step(T0 + 3_000 + T.HOLD_MS)
    assert len(box.messages(B, conv["peer"]["key"])) == 1


# ------------------------------------------------------------------ the 1 h grace
def _talk(box, at=T0 + 1_000):
    box.write(box.files[A], box.send(A, "toolu_1", NAMES[B], "またね", at), box.result(A, "toolu_1", at + 100, msg_id="m1"))
    box.write(box.files[B], box.read_meta(B, at + 500, "m1", A, "またね"))
    box.step(at + 1_000)


def test_a_dead_peer_is_kept_for_the_grace_then_removed(box):
    _talk(box)
    box.alive.discard(B)
    died = T0 + 10_000
    got = box.step(died)
    [conv] = box.convs(A)
    assert conv["peer"]["alive"] is False and conv["peer"]["goneAt"] == died and conv["peer"]["removeAt"] == died + GRACE
    assert any(op["op"] == "conv" and not op["conv"]["peer"]["alive"] for op in got["ops"][A])
    box.step(died + GRACE - 1)
    assert len(box.convs(A)) == 1 and len(box.messages(A, B)) == 1           # kept within the grace
    got = box.step(died + GRACE)
    assert box.convs(A) == [] and box.convs(B) == [] and box.messages(A, B) is None
    assert {"op": "remove", "convId": T.conv_id(A, B), "reason": "peer-ended"} in got["ops"][A]
    assert {"op": "remove", "convId": T.conv_id(A, B), "reason": "owner-ended"} in got["ops"][B]


def test_a_session_back_within_the_grace_keeps_its_talks(box):
    _talk(box)
    box.alive.discard(B)
    box.step(T0 + 10_000)
    box.alive.add(B)
    box.step(T0 + 20_000)
    box.step(T0 + 10_000 + GRACE + 1)
    [conv] = box.convs(A)
    assert conv["peer"]["alive"] is True and conv["peer"]["goneAt"] is None


def test_a_session_back_after_removal_is_rebuilt_from_the_transcripts(box):
    _talk(box)
    box.alive.discard(B)
    box.step(T0 + 10_000)
    box.step(T0 + 10_000 + GRACE)
    assert box.convs(A) == []
    box.alive.add(B)
    box.step(T0 + 20_000 + GRACE)
    box.step(T0 + 21_000 + GRACE)
    [m] = box.messages(A, B)
    assert (m["id"], m["state"], m["seen"]) == ("m-m1", "read", "both")


def test_a_peer_never_seen_alive_counts_from_its_transcripts_last_write(box):
    """At the first start, a peer that ended hours ago is not kept another hour: its transcript's last write is when
    it ended."""
    box.alive.discard(B)
    _talk(box)
    old = (T0 - 2 * GRACE) / 1000
    os.utime(box.files[B], (old, old))
    box.index._seen_alive.discard(B)
    box.step(T0 + 5_000)
    assert box.convs(A) == []


def test_a_peer_not_on_this_machine_is_kept_for_the_grace_after_its_last_message(box):
    """Its liveness cannot be known here: an hour after the last message it goes, and a new message brings it back
    (never shut out like an ended session)."""
    nobody = T.external_key("cloud-peer")
    box.write(box.files[A], box.send(A, "toolu_1", "cloud-peer", "雲へ", T0 + 1_000),
              box.result(A, "toolu_1", T0 + 1_100, text="No agent named cloud-peer is reachable"))
    box.step(T0 + 2_000)
    box.step(T0 + 3_000)
    [conv] = box.convs(A)
    assert conv["peer"]["kind"] == "external" and conv["peer"]["sessionId"] is None
    assert conv["peer"]["removeAt"] == T0 + 1_000 + GRACE
    box.step(T0 + 1_000 + GRACE - 1)
    assert len(box.convs(A)) == 1
    got = box.step(T0 + 1_000 + GRACE)
    assert box.convs(A) == [] and {"op": "remove", "convId": T.conv_id(A, nobody), "reason": "peer-ended"} in got["ops"][A]
    later = T0 + 2 * GRACE
    box.write(box.files[A], box.send(A, "toolu_2", "cloud-peer", "また", later), box.result(A, "toolu_2", later + 100, text="No agent named cloud-peer is reachable"))
    box.step(later + 1_000)
    assert [m["id"] for m in box.messages(A, nobody)] == ["u-toolu_2"]


def test_a_live_peer_on_this_machine_is_never_removed_for_an_old_last_message(box):
    """The 1 h since the last message is only for peers whose liveness cannot be known (x:): a session in the registry
    stays however old its talk is."""
    _talk(box, at=T0 - 5 * GRACE)
    ops = [op for at in (T0, T0 + 1_000, T0 + 3 * GRACE) for o in box.step(at)["ops"].values() for op in o]
    assert not [op for op in ops if op["op"] == "remove"], ops
    assert not any(op["op"] == "conv" and not op["conv"]["peer"]["alive"] for op in ops)
    [conv] = box.convs(A)
    assert conv["peer"]["key"] == B and conv["peer"]["alive"] is True and conv["peer"]["removeAt"] is None
    assert len(box.messages(A, B)) == 1


def test_the_grace_comes_from_the_config(tmp_path, monkeypatch):
    from jui_cli.viz import config as config_mod
    monkeypatch.setenv("JUI_VIZ_HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    (tmp_path / "home" / "config.json").write_text(json.dumps({"talkGraceSec": 2}))
    assert config_mod.load_config().talkGraceSec == 2
    assert config_mod.VizConfig().talkGraceSec == 3600


# ------------------------------------------------------------------ unread and badges
def test_the_past_is_read_and_a_new_message_is_unread_until_seen(tmp_path):
    b = Box(tmp_path)
    b.write(b.files[A], b.send(A, "toolu_0", NAMES[B], "昔の話", T0 - 100_000),
            b.result(A, "toolu_0", T0 - 99_000, msg_id="m0"))
    b.step(T0)                                                    # the first reading: catching up
    assert b.convs(B)[0]["unread"] == 0 and b.index.badges() == {}
    b.write(b.files[A], b.send(A, "toolu_1", NAMES[B], "新しい話", T0 + 1_000),
            b.result(A, "toolu_1", T0 + 1_100, msg_id="m1"))
    got = b.step(T0 + 2_000)
    assert got["badges"] == {B: 1}
    assert b.convs(B)[0]["unread"] == 1 and b.convs(A)[0]["unread"] == 0
    conv = b.index.seen(B, T.conv_id(A, B), T0 + 1_000, T0 + 3_000)
    assert conv["unread"] == 0 and b.index.badges() == {}
    assert b.index.seen(B, T.conv_id(A, B), T0, T0 + 3_000)["unread"] == 0     # never moves back
    b.index.close()


def test_a_new_conversation_after_catching_up_starts_unread(box):
    box.write(box.files[D], box.send(D, "toolu_d", NAMES[B], "はじめまして", T0 + 1_000),
              box.result(D, "toolu_d", T0 + 1_100, msg_id="md"))
    box.step(T0 + 5_000)
    [conv] = box.convs(B)
    assert conv["unread"] == 1


# ------------------------------------------------------------------ what leaves the module
def test_no_path_reaches_a_frame(box, tmp_path):
    _talk(box)
    blob = json.dumps([box.convs(A), box.messages(A, B), box.step(T0 + 9_000)], ensure_ascii=False)
    assert str(tmp_path) not in blob and "/projects/" not in blob and ".jsonl" not in blob


def test_the_database_is_under_the_state_home_and_private(tmp_path):
    b = Box(tmp_path)
    mode = stat.S_IMODE(os.stat(b.db).st_mode)
    assert mode == 0o600 and b.db.parent == tmp_path / "state"
    b.index.close()


def test_an_older_schema_is_dropped_and_rebuilt(tmp_path):
    b = Box(tmp_path)
    b.index.db.execute("UPDATE meta SET v='0' WHERE k='schema'")
    b.index.close()
    db = T.open_db(b.db)
    assert db.execute("SELECT v FROM meta WHERE k='schema'").fetchone()[0] == str(T.SCHEMA)
    db.close()


def test_a_symlinked_transcript_is_not_read(tmp_path):
    b = Box(tmp_path)
    outside = tmp_path / "outside.jsonl"
    b.write(outside, b.send(A, "toolu_x", NAMES[B], "外", T0), b.result(A, "toolu_x", T0 + 1, msg_id="mx"))
    b.files[A].unlink()
    b.files[A].symlink_to(outside)
    b.step(T0 + 1_000)
    assert b.convs(A) == []
    b.index.close()


# ------------------------------------------------------------------ the hub: the event loop is never held
class FakeSock:
    def __init__(self):
        self.sent = []

    async def send_json(self, frame):
        self.sent.append(frame)


def test_the_hub_steps_off_the_event_loop_and_answers_requests(tmp_path):
    b = Box(tmp_path)
    _talk(b, at=T0 - 50_000)
    slow = threading.Event()

    def slow_rows():
        slow.wait(0.5)
        return b.rows()

    index = T.TalkIndex(tmp_path / "state2" / "talk.db", b.projects, tmp_path / "sessions", GRACE, registry=slow_rows)
    agents = {A: {"id": A}, B: {"id": B}, CHILD: {"id": CHILD}}
    hub = T.TalkHub(lambda: index, agents=lambda: agents, sessions=lambda: {B: {"title": "B の名前"}})

    async def go():
        t = time.monotonic()
        hub.tick(T0)                       # starts the (slow) step
        assert time.monotonic() - t < 0.05
        while hub._job is not None and not hub._job.done():
            await asyncio.sleep(0.02)
        hub.tick(T0 + 100)
        sock = FakeSock()
        await hub.handle(sock, {"type": "talk.open", "reqId": 1, "agentId": A})
        listing = sock.sent[-1]
        assert C.validate(listing) == [] and listing["items"][0]["peer"]["agentId"] == B
        assert listing["items"][0]["peer"]["name"] == "B の名前"
        cid = listing["items"][0]["id"]
        await hub.handle(sock, {"type": "talk.get", "reqId": 2, "agentId": A, "convId": cid})
        assert C.validate(sock.sent[-1]) == [] and sock.sent[-1]["items"][0]["id"] == "m-m1"
        await hub.handle(sock, {"type": "talk.seen", "reqId": 3, "agentId": B, "convId": cid, "upTo": T0})
        assert sock.sent[-1] == {"type": "ack", "reqId": 3, "ok": True}
        await hub.handle(sock, {"type": "talk.send", "reqId": 4, "agentId": A, "convId": cid, "text": "hi"})
        assert sock.sent[-1]["ok"] is False                       # no sending from the talk view
        await hub.handle(sock, {"type": "talk.open", "reqId": 5, "agentId": "a-robot-not-here"})
        assert sock.sent[-1] == {"type": "ack", "reqId": 5, "ok": False, "error": "no such robot"}
        # a new message: an increment for the socket that opened A, and the badge for every socket
        b.write(b.files[A], b.send(A, "toolu_n", NAMES[B], "新着", T0 + 200_000), b.result(A, "toolu_n", T0 + 200_100, msg_id="mn"))
        hub._last = -10**12
        hub.tick(T0 + 200_500)
        while hub._job is not None and not hub._job.done():
            await asyncio.sleep(0.02)
        hub.tick(T0 + 200_600)
        other = FakeSock()
        await hub.flush({sock: {}, other: {}})
        updates = [f for f in sock.sent if f["type"] == "talk.update"]
        assert updates and all(C.validate(f) == [] for f in updates)
        assert any(op["op"] == "message" and op["message"]["id"] == "m-mn" for f in updates for op in f["ops"])
        badges = [f for f in other.sent if f["type"] == "talk.badges"]
        assert badges and C.validate(badges[-1]) == [] and badges[-1]["counts"] == {B: 1}
        assert not [f for f in other.sent if f["type"] == "talk.update"]      # only the socket that opened A
        # talk.seen: the badge goes out at once, not only at the next step (no tick between)
        hub._last = 10**15
        await hub.handle(sock, {"type": "talk.seen", "reqId": 6, "agentId": B, "convId": cid, "upTo": T0 + 200_000})
        assert sock.sent[-1] == {"type": "ack", "reqId": 6, "ok": True}
        await hub.flush({sock: {}, other: {}})
        assert other.sent[-1] == {"type": "talk.badges", "counts": {}}

    try:
        asyncio.run(go())
    finally:
        hub.close()
        b.index.close()


def test_the_peer_can_be_switched_to_only_when_its_robot_is_on_the_page(tmp_path):
    b = Box(tmp_path)
    _talk(b)
    hub = T.TalkHub(lambda: b.index, agents=lambda: {A: {}, B: {}})
    [conv] = b.convs(A)
    assert hub._decorate(conv)["peer"]["agentId"] == B
    hub2 = T.TalkHub(lambda: b.index, agents=lambda: {A: {}})
    [conv] = b.convs(A)
    assert hub2._decorate(conv)["peer"]["agentId"] is None
    hub.pool.shutdown()
    hub2.pool.shutdown()
    b.index.close()


# ------------------------------------------------------------------ through the real server's WebSocket
def test_the_server_sends_badges_on_connect_and_talk_frames_over_the_websocket(tmp_path):
    import aiohttp
    from aiohttp.test_utils import TestClient, TestServer

    from jui_cli.viz.config import VizConfig
    from jui_cli.viz.server import ServerContext, make_app
    from jui_cli.viz.state import VizState

    b = Box(tmp_path)
    b.write(b.files[A], b.send(A, "toolu_0", NAMES[B], "昔", T0 - 100_000), b.result(A, "toolu_0", T0 - 99_000, msg_id="m0"))
    agents = {A: {}, B: {}}
    hub = T.TalkHub(lambda: b.index, agents=lambda: agents)
    ctx = ServerContext(config=VizConfig(pushIntervalMs=20), port=0, token="t" * 43, version="test", state=VizState(50))
    ctx.talk = hub

    async def settle():
        hub._last = -10**12
        hub.tick(T.time.time() * 1000)
        while hub._job is not None and not hub._job.done():
            await asyncio.sleep(0.01)
        hub.tick(T.time.time() * 1000)

    async def main():
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            ctx.port = s.getsockname()[1]
        client = TestClient(TestServer(make_app(ctx), host="127.0.0.1", port=ctx.port))
        await client.start_server()
        try:
            await settle()
            headers = {"Host": f"127.0.0.1:{ctx.port}", "Origin": f"http://127.0.0.1:{ctx.port}"}
            ws = await client.ws_connect("/ws", headers=headers)
            await ws.receive_json(timeout=2)
            await ws.send_json({"type": "auth", "token": "t" * 43})
            kinds = [(await ws.receive_json(timeout=2))["type"] for _ in range(3)]
            assert kinds == ["snapshot", "events", "talk.badges"]
            await ws.send_json({"type": "talk.open", "reqId": 1, "agentId": B})
            listing = await ws.receive_json(timeout=2)
            assert listing["type"] == "talk.list" and C.validate(listing) == [] and listing["items"][0]["unread"] == 0
            now = int(T.time.time() * 1000)
            b.write(b.files[A], b.send(A, "toolu_1", NAMES[B], "今", now), b.result(A, "toolu_1", now + 10, msg_id="m1"))
            await settle()
            got = {}
            while set(got) != {"talk.update", "talk.badges"}:
                frame = await ws.receive_json(timeout=2)
                got[frame["type"]] = frame
            assert C.validate(got["talk.update"]) == [] and got["talk.badges"]["counts"] == {B: 1}
            assert "m-m1" in json.dumps(got["talk.update"])
            # the snapshot never carries a body
            snap = await client.get("/api/snapshot", headers={"Host": f"127.0.0.1:{ctx.port}", "X-Jui-Viz-Token": "t" * 43})
            assert "今" not in await snap.text() and "昔" not in await snap.text()
            # no HTTP route for talks: there is nothing to post to and no file to name
            r = await client.post("/api/talk", headers=headers, json={"text": "x"})
            assert r.status in (404, 405)
            await ws.close()
        finally:
            await client.close()

    try:
        asyncio.run(main())
    finally:
        hub.close()


def test_a_server_without_talks_refuses_talk_requests():
    from jui_cli.viz.config import VizConfig
    from jui_cli.viz.server import ServerContext, _handle_browser_message
    from jui_cli.viz.state import VizState

    ctx = ServerContext(config=VizConfig(), port=0, token="t" * 43, version="test", state=VizState(50))
    sock = FakeSock()
    asyncio.run(_handle_browser_message(ctx, sock, {"type": "talk.open", "reqId": 1, "agentId": A}))
    assert sock.sent[-1]["ok"] is False


# ------------------------------------------------------------------ the independent review's findings (10-20)
def test_a_matched_receivers_record_read_again_stays_one_row(box):
    """A subagent's send to main, matched by sender and body (no msg_id), its file read again from the start and the
    hold passed: still one row (the receiver's (receiver, uuid) is remembered; without it a second r- row appears)."""
    child = box.child_file()
    box.write(child, box.send(A, "toolu_c", "main", "親への報告", T0 + 1_000, sub=CHILD), box.result(A, "toolu_c", T0 + 1_050))
    box.write(box.files[A], {"type": "user", "isMeta": True, "timestamp": iso(T0 + 1_500), "uuid": "child-read-0001",
                             "origin": {"kind": "peer", "from": CHILD, "senderTaskId": CHILD, "name": "worker", "body": "親への報告"},
                             "message": {"role": "user", "content": "x"}})
    box.step(T0 + 2_000)
    assert [(m["id"], m["state"]) for m in box.messages(A, CHILD)] == [("u-toolu_c", "read")]
    box.index.db.execute("UPDATE files SET off=0")
    box.step(T0 + 3_000)
    box.step(T0 + 3_000 + T.HOLD_MS)
    assert [m["id"] for m in box.messages(A, CHILD)] == ["u-toolu_c"]
    assert [c["peer"]["key"] for c in box.convs(A)] == [CHILD]


def test_a_body_over_text_max_is_cut_before_it_is_sent(box):
    long = "あ" * (T.TEXT_MAX + 5_000)
    box.write(box.files[A], box.send(A, "toolu_l", NAMES[B], long, T0 + 1_000), box.result(A, "toolu_l", T0 + 1_100, msg_id="ml"))
    got = box.step(T0 + 2_000)
    [m] = box.messages(A, B)                     # messages() checks the talk.messages frame against the contract
    assert len(m["text"]) == T.TEXT_MAX and m["cut"] is True
    ops = [op for op in got["ops"][B] if op["op"] == "message"]
    assert ops and len(ops[0]["message"]["text"]) == T.TEXT_MAX


def test_the_database_folder_is_made_0700(tmp_path):
    b = Box(tmp_path)
    assert stat.S_IMODE(os.stat(b.db.parent).st_mode) == 0o700
    b.index.close()


def test_a_line_nested_too_deep_is_skipped_and_the_reading_goes_on(tmp_path):
    """A line with a needle and a million brackets (json.loads raises RecursionError, not ValueError): skipped; the
    send and read after it are indexed and the place read is kept."""
    b = Box(tmp_path)
    with b.files[A].open("a") as fh:
        fh.write('{"type":"assistant","x":"SendMessage","y":' + "[" * 1_000_000 + "\n")
    b.write(b.files[A], b.send(A, "toolu_1", NAMES[B], "毒の後", T0 + 1_000), b.result(A, "toolu_1", T0 + 1_100, msg_id="m1"))
    b.write(b.files[B], b.read_meta(B, T0 + 2_000, "m1", A, "毒の後"))
    b.step(T0 + 3_000)
    assert [(m["id"], m["state"]) for m in b.messages(A, B)] == [("m-m1", "read")]
    assert b.index.db.execute("SELECT MIN(off) FROM files WHERE agent IS NULL AND sid IN (?, ?)", (A, B)).fetchone()[0] > 0
    b.index.close()


def test_a_server_frames_type_sent_by_a_page_is_refused_not_fatal(tmp_path):
    """talk.badges / talk.list / talk.update from a page are not requests: an ack with ok false, the socket stays (a
    KeyError there closed the page's socket; a talk.list passed and was never answered)."""
    b = Box(tmp_path)
    hub = T.TalkHub(lambda: b.index, agents=lambda: {A: {}, B: {}})
    sock = FakeSock()

    async def go():
        for i, frame in enumerate([{"type": "talk.badges", "counts": {}},
                                   {"type": "talk.list", "agentId": A, "items": [], "more": False},
                                   {"type": "talk.update", "agentId": A, "ops": [{"op": "remove", "convId": "t-0123456789abcdef", "reason": "peer-ended"}]},
                                   {"type": "talk.messages", "reqId": 9, "agentId": A, "convId": "t-0123456789abcdef", "items": [], "more": False}]):
            await hub.handle(sock, {**frame, "reqId": i})
            assert sock.sent[-1]["type"] == "ack" and sock.sent[-1]["ok"] is False and sock.sent[-1]["reqId"] == i
            assert "not a talk request" in sock.sent[-1]["error"]

    try:
        asyncio.run(go())
        assert C.validate_request({"type": "talk.open", "reqId": 1, "agentId": A}) == []
    finally:
        hub.close()
