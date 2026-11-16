"""Who a SendMessage went to, and who a received message came from, in the 応答の履歴 (2.3.6; ticket
2026-10-20-jui-viz-history-sendmessage-recipient).

The folded SendMessage row carries input.to and input.summary (else the message's first line). World.history links
`to` (and a received message's sender) to a session here, by the same rule a phone call uses: a name from the agents
list (`name [ref]` loses its ref), a `uds:` socket address that a row named, or the pid in the socket's file name.
Anything else stays unlinked: another machine, a session that ended, `main`, the session itself.
"""
from __future__ import annotations

import json

from jui_cli.viz.ingest import World
from jui_cli.viz.sources import history as H
from jui_cli.viz.sources.transcripts import project_dir_name
from jui_cli.viz.state import VizState

A = "0a0a0a0a-1111-4111-8111-aaaaaaaaaaaa"     # whose history is read
B = "0b0b0b0b-2222-4222-8222-bbbbbbbbbbbb"     # named in the agents list, with its socket
C = "0c0c0c0c-3333-4333-8333-cccccccccccc"     # a pid but no name and no socket row (a session file read before)
GONE = "0d0d0d0d-4444-4444-8444-dddddddddddd"  # ended
CWD = "/work/peers"
T = 1_792_300_000_000


def _send(use_id, to, summary=None, message="1 行目\n2 行目"):
    inp = {"to": to, "message": message}
    if summary is not None:
        inp["summary"] = summary
    return {"type": "assistant", "timestamp": "2026-10-20T01:00:00Z",
            "message": {"id": use_id, "role": "assistant", "content": [{"type": "tool_use", "id": use_id, "name": "SendMessage", "input": inp}]}}


def _received(addr, name):
    name_attr = f' from-name="{name}"' if name else ""
    return {"type": "user", "timestamp": "2026-10-20T01:00:05Z", "message": {"role": "user", "content":
            f'Another Claude session sent a message:\n<cross-session-message from="{addr}"{name_attr}>\n本文\n</cross-session-message>'}}


def _world(tmp_path, records):
    projects = tmp_path / ".claude" / "projects"
    path = projects / project_dir_name(CWD) / f"{A}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    world = World(VizState())
    world.history_reader = H.reader(projects)
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": A, "cwd": CWD, "transcript_path": str(path)}, T)
    world.apply_agents_list([
        {"sessionId": A, "cwd": CWD, "status": "idle", "pid": 100, "name": "peers-a", "messagingSocketPath": "/tmp/cc-socks/100.sock"},
        {"sessionId": B, "cwd": CWD, "status": "idle", "pid": 101, "name": "peers-b", "messagingSocketPath": "/tmp/cc-socks/101.sock"},
        {"sessionId": C, "cwd": CWD, "status": "idle", "pid": 102},
        {"sessionId": GONE, "cwd": CWD, "status": "idle", "pid": 103, "name": "peers-gone"},
    ], T)
    world.apply_hook({"hook_event_name": "SessionEnd", "session_id": GONE, "cwd": CWD, "reason": "other"}, T + 1)
    return world


def _tools(world):
    return [i for i in world.history(A)["items"] if i["kind"] == "tool"]


def test_the_folded_row_carries_to_and_summary(tmp_path):
    world = _world(tmp_path, [_send("u1", "peers-b", "請求の件"), _send("u2", "peers-b"), {"type": "assistant", "timestamp": "2026-10-20T01:00:00Z",
        "message": {"id": "u3", "role": "assistant", "content": [{"type": "tool_use", "id": "u3", "name": "Bash", "input": {"command": "ls"}}]}}])
    t = _tools(world)
    assert (t[0]["to"], t[0]["summary"]) == ("peers-b", "請求の件")
    assert t[1]["summary"] == "1 行目"                      # no summary: the message's first line
    assert "to" not in t[2] and "toSession" not in t[2]     # only SendMessage


def test_to_resolves_by_name_by_name_with_ref_by_socket_and_by_the_pid_in_the_socket(tmp_path):
    world = _world(tmp_path, [_send("u1", "peers-b"), _send("u2", "peers-b [3fa9c1]"), _send("u3", "uds:/tmp/cc-socks/101.sock"),
                              _send("u4", "uds:/tmp/other-dir/102.sock")])
    assert [x.get("toSession") for x in _tools(world)] == [B, B, B, C]


def test_unmatched_recipients_stay_unlinked(tmp_path):
    world = _world(tmp_path, [_send("u1", "elsewhere-z9"), _send("u2", "main"), _send("u3", "peers-gone"), _send("u4", "peers-a"),
                              _send("u5", "uds:/tmp/cc-socks/999.sock")])
    assert [x.get("toSession") for x in _tools(world)] == [None] * 5   # another machine, main, ended, itself, no such pid


def test_a_received_message_links_its_sender_by_name_or_by_its_address(tmp_path):
    world = _world(tmp_path, [_received("uds:/tmp/cc-socks/101.sock", "peers-b"), _received("uds:/tmp/cc-socks/102.sock", None),
                              _received("uds:/tmp/cc-socks/998.sock", "far-away")])
    peers = [i for i in world.history(A)["items"] if i["kind"] == "peer"]
    assert [(p["from"], p.get("fromSession")) for p in peers] == [("peers-b", B), ("uds:/tmp/cc-socks/102.sock", C), ("far-away", None)]   # no from-name: the address is the name
    assert peers[1]["fromAddr"] == "uds:/tmp/cc-socks/102.sock"


def test_a_phone_call_resolves_the_same_way():
    world = World(VizState())
    world.apply_agents_list([{"sessionId": C, "cwd": CWD, "status": "idle", "pid": 102}], T)
    assert world._resolve_peer("uds:/tmp/cc-socks/102.sock") == C   # the pid, no socket row (the calls' family)
