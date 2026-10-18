"""Phone calls (requester, 10-18): a SendMessage rings the receiver; the receiver's transcript picks up.

The receiver's records are the shapes measured on 10-18 (17 messages between two sessions): an ``enqueue`` when it
arrives, then an ``isMeta`` user record (idle) or a ``remove`` with ``absorbed_mid_turn`` (busy) when it is read.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from jui_cli.viz import calls as calls_mod
from jui_cli.viz.ingest import World
from jui_cli.viz.sources import transcripts
from jui_cli.viz.state import VizState

A = "0a0a0a0a-1111-4111-8111-aaaaaaaaaaaa"     # the sender
B = "0b0b0b0b-2222-4222-8222-bbbbbbbbbbbb"     # the receiver
C = "0c0c0c0c-3333-4333-8333-cccccccccccc"     # another sender
NAMES = {A: "shop-app-a1", B: "shop-app-b2", C: "admin-web-c3"}
T = 1_792_300_000_000
BODY = "SECRET-BODY-7f3a"                       # a message's text: it must never reach a slice


def _iso(at):
    return datetime.fromtimestamp(at / 1000, timezone.utc).isoformat().replace("+00:00", "Z")


def _setup(tmp_path, names=True):
    projects = tmp_path / "projects"
    files = {}
    for sid, cwd in ((A, "/work/shop"), (B, "/work/shop"), (C, "/work/admin")):
        d = projects / transcripts.project_dir_name(cwd)
        d.mkdir(parents=True, exist_ok=True)
        files[sid] = d / f"{sid}.jsonl"
        files[sid].write_text("")
    world = World(VizState(), session_start=transcripts.session_start(projects))
    world.transcript_path = transcripts.transcript_path(projects)
    rows = []
    for sid, cwd in ((A, "/work/shop"), (B, "/work/shop"), (C, "/work/admin")):
        row = {"sessionId": sid, "cwd": cwd, "status": "idle", "pid": 100 + len(rows)}
        if names:
            row.update(name=NAMES[sid], nameSource="derived", messagingSocketPath=f"/tmp/socks/{100 + len(rows)}.sock")
        rows.append(row)
    world.apply_agents_list(rows, T)
    world.poll_usage(T)                           # first sight: from the end
    return world, files


def _send(world, sender, to, use_id="tu1", at=T + 1_000, post=True):
    base = {"session_id": sender, "cwd": "/work/shop", "tool_name": "SendMessage", "tool_use_id": use_id,
            "tool_input": {"to": to, "summary": "x", "message": BODY}}
    world.apply_hook({**base, "hook_event_name": "PreToolUse"}, at)
    if post:
        world.apply_hook({**base, "hook_event_name": "PostToolUse", "tool_response": {"success": True}}, at + 100)


def _xmsg(sender):
    return (f'<cross-session-message from="uds:/tmp/socks/1.sock" from-name="{NAMES.get(sender, sender)}" '
            f'from-mode="prompting">\n{BODY}\n</cross-session-message>')


def _enqueue(sender, at):
    return {"type": "queue-operation", "operation": "enqueue", "timestamp": _iso(at), "sessionId": B, "content": _xmsg(sender)}


def _meta(sender, at):
    # the shape measured 10-18 (11 records): one line of the harness before the tag
    return {"type": "user", "isMeta": True, "timestamp": _iso(at),
            "message": {"role": "user", "content": "Another Claude session sent a message:\n" + _xmsg(sender)}}


def _absorbed(sender, at, reason="absorbed_mid_turn"):
    return {"type": "queue-operation", "operation": "remove", "reason": reason, "timestamp": _iso(at), "content": _xmsg(sender)}


def _append(f, *recs):
    with open(f, "a") as h:
        for r in recs:
            h.write(json.dumps(r) + "\n")


def _calls(world, at):
    world.poll_usage(at)
    world.tick(at)
    world.publish()
    return world.state.slices["calls"]


def test_a_named_receiver_rings_at_once_and_picks_up_when_it_reads_idle(tmp_path):
    world, f = _setup(tmp_path)
    _send(world, A, f"{NAMES[B]} [3fa9c1]")                    # a `[ref]` is not part of the name
    [c] = _calls(world, T + 1_200)
    assert (c["state"], c["from"], c["toSession"]) == ("ringing", A, B)
    _append(f[B], _enqueue(A, T + 2_000))
    [c] = _calls(world, T + 3_000)
    assert c["state"] == "ringing" and c["arrived"] == T + 2_000   # arrived, not read yet
    _append(f[B], _meta(A, T + 2_010))
    [c] = _calls(world, T + 4_000)
    assert c["state"] == "answered" and c["read"] == T + 2_010 and c["endedAt"] == T + 4_000   # moved when it was read here
    assert _calls(world, T + 4_000 + calls_mod.ANSWERED_SHOW_MS - 1)[0]["state"] == "answered"
    assert _calls(world, T + 4_000 + calls_mod.ANSWERED_SHOW_MS) == []   # both back to work


def test_a_busy_receiver_picks_up_at_its_next_tool_boundary(tmp_path):
    world, f = _setup(tmp_path)
    _send(world, A, NAMES[B])
    _append(f[B], _enqueue(A, T + 2_000))
    assert _calls(world, T + 60_000)[0]["state"] == "ringing"     # it keeps ringing while the receiver works
    _append(f[B], _absorbed(A, T + 194_000))                       # 3 min 14 s later (measured)
    assert _calls(world, T + 195_000)[0]["state"] == "answered"


def test_without_the_name_map_the_receiver_still_rings_from_its_enqueue(tmp_path):
    world, f = _setup(tmp_path, names=False)
    world._session_names[A] = NAMES[A]                            # the sender's own name is known, the receiver's not
    _send(world, A, NAMES[B])
    [c] = _calls(world, T + 1_200)
    assert c["state"] == "dialing" and c["toSession"] is None
    _append(f[B], _enqueue(A, T + 3_000))
    [c] = _calls(world, T + 4_000)
    assert (c["state"], c["toSession"]) == ("ringing", B)


def test_a_receiver_that_is_not_here_moves_only_the_sender(tmp_path):
    world, f = _setup(tmp_path)
    _send(world, A, "main")
    [c] = _calls(world, T + 2_000)
    assert c["state"] == "dialing" and c["toSession"] is None
    [c] = _calls(world, T + 1_100 + calls_mod.UNREACHABLE_GRACE_MS)
    assert c["state"] == "unreachable"


def test_a_message_from_another_sender_does_not_pick_up(tmp_path):
    world, f = _setup(tmp_path)
    _send(world, A, NAMES[B])
    _append(f[B], _enqueue(C, T + 2_000), _meta(C, T + 2_010))     # C's message, read
    calls = _calls(world, T + 3_000)
    mine = [c for c in calls if c["from"] == A]
    assert [c["state"] for c in mine] == ["ringing"]


def test_a_quoted_message_in_a_tool_result_or_a_prompt_does_not_pick_up(tmp_path):
    world, f = _setup(tmp_path)
    _send(world, A, NAMES[B])
    quoted = {"type": "user", "timestamp": _iso(T + 2_000),
              "message": {"role": "user", "content": [{"type": "tool_result", "content": "grep: " + _xmsg(A)}]}}
    prompt = {"type": "user", "isMeta": True, "timestamp": _iso(T + 2_000), "message": {"role": "user", "content": "see " + _xmsg(A)}}
    two = {"type": "user", "isMeta": True, "timestamp": _iso(T + 2_000),
           "message": {"role": "user", "content": "a line\nanother line\n" + _xmsg(A)}}     # more than one line before it
    tagged = {"type": "user", "isMeta": True, "timestamp": _iso(T + 2_000),
              "message": {"role": "user", "content": "<b>x</b>\n" + _xmsg(A)}}              # a first line with a tag
    _append(f[B], quoted, prompt, two, tagged)
    assert _calls(world, T + 3_000)[0]["state"] == "ringing"


def test_nobody_picks_up_and_it_stops_ringing(tmp_path):
    world, f = _setup(tmp_path)
    _send(world, A, NAMES[B])
    assert _calls(world, T + 1_000 + calls_mod.RING_MAX_MS - 1)[0]["state"] == "ringing"
    assert _calls(world, T + 1_000 + calls_mod.RING_MAX_MS)[0]["state"] == "missed"


def test_a_reply_to_a_uds_address_rings_that_session(tmp_path):
    world, f = _setup(tmp_path)
    _send(world, B, "uds:/tmp/socks/100.sock")                    # A's socket (pid 100)
    [c] = _calls(world, T + 1_200)
    assert (c["from"], c["toSession"], c["state"]) == (B, A, "ringing")


def test_another_remove_hangs_up(tmp_path):
    world, f = _setup(tmp_path)
    _send(world, A, NAMES[B])
    _append(f[B], _enqueue(A, T + 2_000), _absorbed(A, T + 5_000, reason="cleared"))
    assert _calls(world, T + 6_000)[0]["state"] == "hungUp"


def test_a_failed_send_ends_the_call(tmp_path):
    world, f = _setup(tmp_path)
    base = {"session_id": A, "cwd": "/work/shop", "tool_name": "SendMessage", "tool_use_id": "tu9", "tool_input": {"to": NAMES[B], "message": BODY}}
    world.apply_hook({**base, "hook_event_name": "PreToolUse"}, T + 1_000)
    world.apply_hook({**base, "hook_event_name": "PostToolUseFailure"}, T + 1_100)
    assert _calls(world, T + 1_200)[0]["state"] == "failed"


def test_the_message_text_never_reaches_the_calls_or_the_robots(tmp_path):
    world, f = _setup(tmp_path)
    _send(world, A, NAMES[B])
    _append(f[B], _enqueue(A, T + 2_000), _meta(A, T + 2_010))
    _calls(world, T + 3_000)
    for name in ("calls", "agents", "sessions"):
        assert BODY not in json.dumps(world.state.slices[name], ensure_ascii=False), name


def test_the_receivers_records_as_claude_code_writes_them(tmp_path):
    """One record of each shape, copied from a real transcript (10-18) with the text replaced."""
    enqueue = {"type": "queue-operation", "operation": "enqueue", "timestamp": "2026-10-18T09:30:49.212Z", "sessionId": B,
               "content": '<cross-session-message from="uds:/tmp/cc-socks/86453.sock" from-name="jsonui-agents-for-claude-cd" from-mode="prompting">\nx\n</cross-session-message>'}
    meta = {"type": "user", "isMeta": True, "timestamp": "2026-10-18T09:04:14.587Z",
            "message": {"role": "user", "content": 'Another Claude session sent a message:\n<cross-session-message from="uds:/tmp/cc-socks/86453.sock" from-name="jsonui-agents-for-claude-cd" from-mode="prompting">\nx\n</cross-session-message>'}}
    absorbed = {"type": "queue-operation", "operation": "remove", "reason": "absorbed_mid_turn", "timestamp": "2026-10-18T09:34:02.859Z",
                "content": enqueue["content"]}
    assert [calls_mod.record_event(r) for r in (enqueue, meta, absorbed)] == [
        ("ring", "jsonui-agents-for-claude-cd"), ("answer", "jsonui-agents-for-claude-cd"), ("answer", "jsonui-agents-for-claude-cd")]


def test_a_record_written_long_ago_still_rings_and_shows_the_pick_up(tmp_path):
    """The receiver's clock or a slow read: the record's time is behind the server's. The call moves at the read."""
    world, f = _setup(tmp_path)
    _send(world, A, NAMES[B])
    late = T + 1_000 + calls_mod.RING_MAX_MS + 60_000                # read long after the records were written
    _append(f[B], _enqueue(A, T + 2_000), _meta(A, T + 2_010))
    [c] = _calls(world, late)
    assert c["state"] == "answered" and c["endedAt"] == late         # not missed, not hidden at once


# ---- Remote Control re-appends past isMeta records (same uuid, old times) when it attaches again: measured and
# ---- armed by jsonuidocument-96 in its independent check (10-18), taken in here.
HOUR = 3_600_000


def _replay(sender_msgs):
    recs = [{"type": "bridge-session", "timestamp": "2026-10-18T00:00:00Z"}]
    for sender, at in sender_msgs:
        m = _meta(sender, at + 10)                 # only the isMeta user records are re-written; queue-operation never
        m["uuid"] = f"u-m-{sender}-{at}"
        recs.append(m)
    return recs


def test_replayed_history_does_not_pick_up_an_unread_call(tmp_path):
    world, f = _setup(tmp_path)
    _send(world, A, NAMES[B])
    _append(f[B], _enqueue(A, T + 2_000))
    assert _calls(world, T + 3_000)[0]["state"] == "ringing"
    _append(f[B], *_replay([(A, T - HOUR), (C, T - HOUR + 5_000)]))   # B has NOT read the new message
    [real] = [c for c in _calls(world, T + 5_000) if c["id"] == "call-tu1"]
    assert real["state"] == "ringing"
    _append(f[B], _meta(A, T + 6_000))                                 # now it reads it
    [real] = [c for c in _calls(world, T + 7_000) if c["id"] == "call-tu1"]
    assert real["state"] == "answered"


def test_replayed_history_before_the_enqueue_is_seen_does_not_pick_up(tmp_path):
    world, f = _setup(tmp_path)
    _send(world, A, NAMES[B])                                          # rings by name; no enqueue read yet
    _append(f[B], *_replay([(A, T - HOUR)]))
    assert _calls(world, T + 3_000)[0]["state"] == "ringing"


def test_replayed_history_makes_no_calls(tmp_path):
    world, f = _setup(tmp_path)
    _append(f[B], *_replay([(A if i % 2 else C, T - HOUR + i * 60_000) for i in range(30)]))
    assert _calls(world, T + 5_000) == []
