"""Messages that came while the session was working show in the 応答の履歴 (ticket
2026-10-20-jui-viz-history-misses-mid-turn-deliveries; requester: "届いてるのに応答の履歴に表示されない").

While a session works, what reaches it is written as an ``attachment`` of type ``queued_command`` (measured 10-20 on
273 transcripts: channel 4, peer 1,029, coordinator 100, human 318, task-notification 1,010), never as the ``user``
record a waiting session writes. The records here are written in those shapes, with times relative to the run.

Arms: a page prompt (channel), another session's message (peer), a subagent's to main (peer, senderTaskId), the
parent's to a subagent (coordinator), the requester's own words (human) and a task notification, each one row of the
kind its waiting form makes; a queued_command written twice is one row; the same message as a queued_command and then
as a user record (one msg_id) is one row; a waiting delivery is the row it was before; talk_records.delivery is the
one parse of origin both the history and the talk view use.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from jui_cli.viz.sources import history as H
from jui_cli.viz.sources import talk_records as R

NOW = int(time.time() * 1000)
SOCK = "uds:/tmp/cc-socks/4242.sock"


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat().replace("+00:00", "Z")


def queued(kind_origin: dict, prompt, at, uuid, delivery_id=None, ts_on_attachment=True):
    att = {"type": "queued_command", "prompt": prompt, "source_uuid": f"src-{uuid}", "isMeta": True, "origin": kind_origin}
    if delivery_id:
        att["delivery_id"] = delivery_id
    if ts_on_attachment:
        att["timestamp"] = iso(at)
    return {"type": "attachment", "timestamp": iso(at), "uuid": uuid, "attachment": att}


def user(content, at, uuid, **extra):
    return {"type": "user", "timestamp": iso(at), "uuid": uuid, "message": {"role": "user", "content": content}, **extra}


def asst(text, at, mid):
    return {"type": "assistant", "timestamp": iso(at), "message": {"id": mid, "role": "assistant", "content": [{"type": "text", "text": text}]}}


def read(tmp_path, *recs):
    path = tmp_path / "s.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs))
    fd = os.open(path, os.O_RDONLY)
    try:
        return H.read_tail(fd)["items"]
    finally:
        os.close(fd)


def rows(items):
    return [{k: v for k, v in i.items() if k in ("kind", "from", "label", "server", "text", "at", "fromAddr")} for i in items]


CHANNEL_ORIGIN = {"kind": "channel", "server": "plugin:jui-viz:jui-viz"}
PEER_ORIGIN = {"kind": "peer", "from": SOCK, "verifiedPeerPid": 4242, "msg_id": "mid-0001", "name": "shop-app-b2",
               "fromMode": "prompting", "body": "票を振りました"}
WRAPPED_PEER = f'<cross-session-message from="{SOCK}" from-name="shop-app-b2" from-mode="prompting">\n票を振りました\n</cross-session-message>'


def test_a_page_prompt_that_came_while_working_is_one_channel_row(tmp_path):
    items = read(tmp_path, asst("作業中", NOW - 5_000, "m1"),
                 queued(CHANNEL_ORIGIN, '<channel source="plugin:jui-viz:jui-viz" sender="jui_viz_page">\nFirebase の作業を教えて\n</channel>',
                        NOW - 4_000, "q-ch-1", delivery_id="d-ch-1"),
                 asst("続き", NOW - 3_000, "m2"))
    assert rows(items) == [{"kind": "assistant", "text": "作業中", "at": NOW - 5_000},
                           {"kind": "channel", "server": "plugin:jui-viz:jui-viz", "text": "Firebase の作業を教えて", "at": NOW - 4_000},
                           {"kind": "assistant", "text": "続き", "at": NOW - 3_000}]


def test_another_sessions_message_while_working_is_one_peer_row_like_the_waiting_one(tmp_path):
    working = read(tmp_path, queued(PEER_ORIGIN, WRAPPED_PEER, NOW - 4_000, "q-peer-1", delivery_id="d-peer-1"))
    waiting = read(tmp_path, user(f"Another Claude session sent a message:\n{WRAPPED_PEER}", NOW - 4_000, "u-peer-1", isMeta=True,
                                  origin=PEER_ORIGIN))
    assert rows(working) == rows(waiting) == [{"kind": "peer", "from": "shop-app-b2", "text": "票を振りました", "at": NOW - 4_000,
                                               "fromAddr": SOCK}]


def test_a_subagents_message_to_main_while_working_is_one_peer_row(tmp_path):
    origin = {"kind": "peer", "from": "a1b2c3d4e5f6a7b8", "senderTaskId": "a1b2c3d4e5f6a7b8", "name": "worker", "body": "調べ終わりました"}
    items = read(tmp_path, queued(origin, '<agent-message from="a1b2c3d4e5f6a7b8">\n調べ終わりました\n</agent-message>', NOW - 2_000, "q-sub-1"))
    assert rows(items) == [{"kind": "peer", "from": "worker", "text": "調べ終わりました", "at": NOW - 2_000}]


def test_the_parents_message_to_a_subagent_is_one_harness_row_like_the_waiting_one(tmp_path):
    """The coordinator's queued_command has no time on the attachment (measured: 100 of 100): the record's time."""
    items = read(tmp_path, queued({"kind": "coordinator"}, "途中の指示です", NOW - 2_000, "q-co-1", ts_on_attachment=False))
    waiting = read(tmp_path, user("The coordinator sent a message while you were working:\n途中の指示です\n\nAddress this before completing your current task.",
                                  NOW - 2_000, "u-co-1", isMeta=True, origin={"kind": "coordinator"}))
    assert [(i["kind"], i["label"]) for i in items] == [(i["kind"], i["label"]) for i in waiting] == [("harness", "ハーネスの文")]
    assert items[0]["text"] == "途中の指示です" and items[0]["at"] == NOW - 2_000


def test_the_requesters_words_and_a_task_notification_while_working_show_as_they_would_waiting(tmp_path):
    items = read(tmp_path, queued({"kind": "human"}, [{"type": "text", "text": "それも直して"}], NOW - 3_000, "q-h-1", delivery_id="d-h-1"),
                 queued({"kind": "task-notification", "producer": "bash"}, "<task-notification>\n<status>completed</status>\n</task-notification>",
                        NOW - 2_000, "q-t-1", delivery_id="d-t-1"))
    assert [(i["kind"], i.get("label"), i["text"][:6]) for i in items] == [("user", None, "それも直して"), ("harness", "タスクの通知", "<task-")]


def test_a_queued_command_written_twice_is_one_row(tmp_path):
    rec = queued(PEER_ORIGIN, WRAPPED_PEER, NOW - 4_000, "q-peer-1", delivery_id="d-peer-1")
    items = read(tmp_path, rec, asst("読んだ", NOW - 3_000, "m1"), rec)
    assert [i["kind"] for i in items] == ["peer", "assistant"]                   # in the first copy's place


def test_the_same_message_as_a_queued_command_and_then_a_user_record_is_one_row(tmp_path):
    items = read(tmp_path, queued(PEER_ORIGIN, WRAPPED_PEER, NOW - 4_000, "q-peer-1", delivery_id="d-peer-1"),
                 user(f"Another Claude session sent a message:\n{WRAPPED_PEER}", NOW - 1_000, "u-peer-1", isMeta=True, origin=PEER_ORIGIN))
    assert [(i["kind"], i["at"]) for i in items] == [("peer", NOW - 4_000)]      # the first record: when it came


def test_a_delivery_while_waiting_is_the_row_it_was(tmp_path):
    channel = user('<channel source="plugin:jui-viz:jui-viz" sender="jui_viz_page">\nページから\n</channel>', NOW - 2_000, "u-ch-1",
                   isMeta=True, origin=CHANNEL_ORIGIN, promptSource="system")
    items = read(tmp_path, user("ふつうの依頼", NOW - 3_000, "u-1"), channel)
    assert rows(items) == [{"kind": "user", "text": "ふつうの依頼", "at": NOW - 3_000},
                           {"kind": "channel", "server": "plugin:jui-viz:jui-viz", "text": "ページから", "at": NOW - 2_000}]


def test_other_attachments_are_not_rows(tmp_path):
    other = {"type": "attachment", "timestamp": iso(NOW), "uuid": "a-1", "attachment": {"type": "hook_success", "content": "x"}}
    assert read(tmp_path, user("依頼", NOW - 1_000, "u-1"), other) == read(tmp_path, user("依頼", NOW - 1_000, "u-1"))


def test_one_parse_of_origin_for_the_history_and_the_talk_view():
    """talk_records.delivery is what both read: the talk's observation of a queued peer message carries the same
    msg_id, body and name the history's row shows."""
    rec = queued(PEER_ORIGIN, WRAPPED_PEER, NOW - 4_000, "q-peer-1", delivery_id="d-peer-1")
    d = R.delivery(rec)
    assert (d["kind"], d["queued"], d["msg_id"], d["body"], d["name"]) == ("peer", True, "mid-0001", "票を振りました", "shop-app-b2")
    assert R.delivery_key(d) == ("msg", "mid-0001")
    [(_k, info)] = R.observations(rec)
    assert (info["msg_id"], info["body"], info["name"]) == (d["msg_id"], d["body"], d["name"])
    assert "_origin_info(origin" not in open(H.__file__, encoding="utf-8").read() and "origin.get(\"body\")" not in open(H.__file__, encoding="utf-8").read()
