"""Permission cards, matching hooks to the channel, and the relay end to end (jui viz P5)."""
from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import aiohttp
from aiohttp.test_utils import TestClient, TestServer

from jui_cli.viz.config import VizConfig
from jui_cli.viz.ingest import World
from jui_cli.viz.permissions import HOOK_WAIT_MS, PermissionBook
from jui_cli.viz.server import ServerContext, make_app
from jui_cli.viz.state import VizState

CHANNEL = Path(__file__).resolve().parents[1] / "jui_cli" / "viz" / "channel.py"


def _hook(kind, sid="s1", **fields):
    return {"hook_event_name": kind, "session_id": sid, "cwd": "/work/app", **fields}


def _world():
    state = VizState()
    return World(state), state


def _perm(state, i=0):
    return state.slices["perms"][i]


def test_a_card_without_a_relay_shows_and_is_settled_by_the_terminal():
    world, state = _world()
    world.apply_hook(_hook("PreToolUse", tool_name="Write", tool_use_id="w1", tool_input={"file_path": "/work/app/a"}), 1)
    world.apply_hook(_hook("PermissionRequest", tool_name="Write", tool_input={"file_path": "/work/app/a"},
                           permission_suggestions=[{"type": "addRules"}]), 2)
    world.publish()
    card = _perm(state)
    assert card["status"] == "pending" and card["can"]["allowDeny"] is False
    assert card["summary"] == "Write /work/app/a" and card["suggestions"] == [{"type": "addRules"}]
    assert not any(k.startswith("_") for k in card)  # server-side links stay on the server
    world.apply_hook(_hook("PostToolUse", tool_name="Write", tool_use_id="w1", tool_input={}), 3)
    world.publish()
    card = _perm(state)
    assert card["status"] == "answered_in_terminal" and card["terminalBehavior"] == "allow" and card["decidedBy"] == "terminal"


def test_a_linked_card_is_answered_from_the_browser_and_confirmed_by_the_tool():
    world, state = _world()
    world.apply_hook(_hook("SessionStart"), 0)
    channel_id = world.channel_hello(None, None, "s1", 0)
    world.apply_hook(_hook("PreToolUse", tool_name="Bash", tool_use_id="b1", tool_input={"command": "ls -la"}), 1)
    world.apply_hook(_hook("PermissionRequest", tool_name="Bash", tool_input={"command": "ls -la"}), 2)
    assert world.channel_request(channel_id, {"request_id": "r1", "tool_name": "Bash", "input_preview": "ls -la"}, 3)
    world.publish()
    card = _perm(state)
    assert card["can"]["allowDeny"] is True and state.slices["sessions"][0]["relay"] is True
    assert world.decide(card["id"], "allow", 4) is None
    assert world.perms.take_verdicts(channel_id, 5) == [{"request_id": "r1", "behavior": "allow"}]
    assert world.decide(card["id"], "allow", 6) == "already sent"  # once only
    world.apply_hook(_hook("PostToolUse", tool_name="Bash", tool_use_id="b1", tool_input={}), 7)
    world.publish()
    card = _perm(state)
    assert card["status"] == "allow" and card["decidedBy"] == "browser"
    assert any(e["kind"] == "PermissionAnswered" for e in state.events)


def test_the_terminal_answering_first_means_no_verdict_is_sent():
    world, _ = _world()
    world.apply_hook(_hook("SessionStart"), 0)
    channel_id = world.channel_hello(None, None, "s1", 0)
    world.apply_hook(_hook("PreToolUse", tool_name="Bash", tool_use_id="b1", tool_input={"command": "rm x"}), 1)
    world.apply_hook(_hook("PermissionRequest", tool_name="Bash", tool_input={"command": "rm x"}), 2)
    world.channel_request(channel_id, {"request_id": "r1", "tool_name": "Bash", "input_preview": "rm x"}, 2)
    world.apply_hook(_hook("PermissionDenied", tool_name="Bash", tool_input={"command": "rm x"}), 3)
    card = next(iter(world.perms.perms.values()))
    assert card["status"] == "answered_in_terminal" and card["terminalBehavior"] == "deny"
    assert world.decide(card["id"], "allow", 4) == "already answered_in_terminal"
    assert world.perms.take_verdicts(channel_id, 5) == []
    assert "r1" not in world.perms.channels[channel_id].open  # the channel forgot it


def test_two_subagents_asking_for_the_same_tool_are_not_mixed_up():
    world, state = _world()
    world.apply_hook(_hook("SessionStart"), 0)
    channel_id = world.channel_hello(None, None, "s1", 0)
    for aid, cmd in (("a1", "npm test"), ("a2", "npm run lint")):
        world.apply_hook(_hook("PreToolUse", agent_id=aid, tool_name="Bash", tool_use_id=f"u-{aid}", tool_input={"command": cmd}), 1)
        world.apply_hook(_hook("PermissionRequest", agent_id=aid, tool_name="Bash", tool_input={"command": cmd}), 2)
    # Told apart by the preview: each links to its own card.
    world.channel_request(channel_id, {"request_id": "rB", "tool_name": "Bash", "input_preview": "npm run lint"}, 3)
    world.channel_request(channel_id, {"request_id": "rA", "tool_name": "Bash", "input_preview": "npm test"}, 3)
    links = {c["agentId"]: c.get("_requestId") for c in world.perms.perms.values()}
    assert links == {"a1": "rA", "a2": "rB"}


def test_an_ambiguous_match_makes_a_separate_relay_only_card():
    world, state = _world()
    world.apply_hook(_hook("SessionStart"), 0)
    channel_id = world.channel_hello(None, None, "s1", 0)
    for aid in ("a1", "a2"):
        world.apply_hook(_hook("PreToolUse", agent_id=aid, tool_name="Bash", tool_use_id=f"u-{aid}", tool_input={"command": "make"}), 1)
        world.apply_hook(_hook("PermissionRequest", agent_id=aid, tool_name="Bash", tool_input={"command": "make"}), 2)
    world.channel_request(channel_id, {"request_id": "r?", "tool_name": "Bash", "input_preview": "make"}, 3)
    assert all("_requestId" not in c for c in world.perms.perms.values())  # no guess
    world.tick(3 + HOOK_WAIT_MS)
    world.publish()
    relay_only = [c for c in state.slices["perms"] if c.get("relayOnly")]
    assert len(relay_only) == 1 and relay_only[0]["can"]["allowDeny"] is True
    hooked = [c for c in state.slices["perms"] if not c.get("relayOnly")]
    assert len(hooked) == 2 and all(c["can"]["allowDeny"] is False for c in hooked)


def test_a_channel_request_before_its_hook_waits_and_then_links():
    world, _ = _world()
    world.apply_hook(_hook("SessionStart"), 0)
    channel_id = world.channel_hello(None, None, "s1", 0)
    world.channel_request(channel_id, {"request_id": "r1", "tool_name": "Write", "input_preview": "/work/app/a"}, 1)
    world.apply_hook(_hook("PreToolUse", tool_name="Write", tool_use_id="w1", tool_input={"file_path": "/work/app/a"}), 2)
    world.apply_hook(_hook("PermissionRequest", tool_name="Write", tool_input={"file_path": "/work/app/a"}), 3)
    (card,) = world.perms.perms.values()
    assert card["_requestId"] == "r1" and card["can"]["allowDeny"] is True
    world.tick(10_000)
    assert len(world.perms.perms) == 1  # no relay-only duplicate


def test_stop_expires_open_cards_and_a_silent_channel_goes_away():
    book = PermissionBook()
    card = book.from_hook("s1", "s1", "Bash", {"command": "x"}, "u", None, 0)
    book.session_stopped("s1", 5)
    assert card["status"] == "expired"
    channel = book.hello("s1", 0)
    assert book.relay_sessions() == {"s1"}
    book.tick(60_000)
    assert channel.id not in book.channels and book.relay_sessions() == set()


# ---------------------------------------------------------------- end to end


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _rpc_lines(proc, n, timeout=10):
    out = []
    deadline = time.monotonic() + timeout
    while len(out) < n and time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        out.append(json.loads(line))  # anything that is not JSON fails here
    return out


def test_the_channel_speaks_only_json_rpc_and_relays_a_browser_answer(tmp_path):
    """channel.py as Claude Code runs it, against the real server: a permission
    prompt reaches a card, the browser answers, the channel emits the verdict."""
    port = _free_port()
    token = "t" * 43
    viz = tmp_path / ".jsonui-cli" / "viz"
    viz.mkdir(parents=True)
    (viz / "server.json").write_text(json.dumps({"pid": 1, "port": port, "token": token}))

    async def main():
        state = VizState()
        world = World(state)
        from jui_cli.viz.state import now_ms

        t = now_ms()  # the server matches on its own clock
        world.apply_hook(_hook("SessionStart", sid="sess-1"), t)
        world.apply_hook(_hook("PreToolUse", sid="sess-1", tool_name="Bash", tool_use_id="b1", tool_input={"command": "touch /work/app/x"}), t)
        world.apply_hook(_hook("PermissionRequest", sid="sess-1", tool_name="Bash", tool_input={"command": "touch /work/app/x"}), t)
        world.publish()
        ctx = ServerContext(config=VizConfig(pushIntervalMs=20), port=port, token=token, state=state,
                            world=world, publish=world.publish)
        client = TestClient(TestServer(make_app(ctx), host="127.0.0.1", port=port))
        await client.start_server()
        proc = subprocess.Popen([sys.executable, "-I", str(CHANNEL)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=dict(os.environ, HOME=str(tmp_path)), cwd="/")
        loop = asyncio.get_running_loop()
        try:
            def rpc(msg):
                proc.stdin.write(json.dumps(msg) + "\n")
                proc.stdin.flush()

            rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2099-01-01"}})
            (init,) = await loop.run_in_executor(None, _rpc_lines, proc, 1)
            assert init["result"]["protocolVersion"] == "2099-01-01"
            assert init["result"]["capabilities"]["experimental"] == {"claude/channel": {}, "claude/channel/permission": {}}
            rpc({"jsonrpc": "2.0", "method": "notifications/initialized"})
            rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            rpc({"jsonrpc": "2.0", "id": 3, "method": "nope"})
            got = await loop.run_in_executor(None, _rpc_lines, proc, 2)
            assert got[0] == {"jsonrpc": "2.0", "id": 2, "result": {"tools": []}}
            assert got[1]["error"]["code"] == -32601

            # The channel says hello; no session id to read in this HOME, so link the channel by hand.
            for _ in range(100):
                if world.perms.channels:
                    break
                await asyncio.sleep(0.05)
            (channel,) = world.perms.channels.values()
            channel.session_id = "sess-1"
            rpc({"jsonrpc": "2.0", "method": "notifications/claude/channel/permission_request",
                 "params": {"request_id": "abcde", "tool_name": "Bash", "description": "touch", "input_preview": "touch /work/app/x"}})
            for _ in range(100):
                card = next(iter(world.perms.perms.values()))
                if card.get("_requestId") == "abcde":
                    break
                await asyncio.sleep(0.05)
            assert card["can"]["allowDeny"] is True

            ws = await client.ws_connect("/ws", headers={"Host": f"127.0.0.1:{port}", "Origin": f"http://127.0.0.1:{port}"})
            await ws.receive_json()
            await ws.send_json({"type": "auth", "token": token})
            await ws.receive_json()
            await ws.receive_json()
            await ws.send_json({"type": "perm.decide", "reqId": 9, "permId": card["id"], "behavior": "deny"})
            while True:
                reply = await ws.receive_json(timeout=3)
                if reply.get("type") == "ack":
                    break
            assert reply == {"type": "ack", "reqId": 9, "ok": True}
            (verdict,) = await loop.run_in_executor(None, _rpc_lines, proc, 1, 30)
            assert verdict == {"jsonrpc": "2.0", "method": "notifications/claude/channel/permission",
                               "params": {"request_id": "abcde", "behavior": "deny"}}
            await ws.close()
        finally:
            proc.stdin.close()
            proc.wait(timeout=10)
            await client.close()
        assert proc.returncode == 0
        assert proc.stdout.read() == ""  # nothing but JSON-RPC, and nothing after the end

    asyncio.run(main())


def test_channel_routes_refuse_without_token_or_with_an_origin(tmp_path):
    async def main():
        port = _free_port()
        world = World(VizState())
        ctx = ServerContext(config=VizConfig(), port=port, token="t" * 43, state=world.state, world=world, publish=world.publish)
        client = TestClient(TestServer(make_app(ctx), host="127.0.0.1", port=port))
        await client.start_server()
        host = {"Host": f"127.0.0.1:{port}"}
        try:
            for method, path in (("POST", "/channel/hello"), ("POST", "/channel/request"), ("GET", "/channel/poll?channelId=x")):
                assert (await client.request(method, path, headers=host, json={})).status == 401
                bad = {**host, "X-Jui-Viz-Token": "t" * 43, "Origin": f"http://127.0.0.1:{port}"}
                assert (await client.request(method, path, headers=bad, json={})).status == 403
            ok = {**host, "X-Jui-Viz-Token": "t" * 43}
            assert (await client.get("/channel/poll?channelId=nope", headers=ok)).status == 404
            ws = await client.ws_connect("/ws", headers={**host, "Origin": f"http://127.0.0.1:{port}"})
            await ws.receive_json()
            await ws.send_json({"type": "perm.decide", "reqId": 1, "permId": "p1", "behavior": "allow"})
            msg = await ws.receive(timeout=2)
            assert msg.type == aiohttp.WSMsgType.CLOSE and ws.close_code == 4401  # no auth: no decisions
        finally:
            await client.close()

    asyncio.run(main())


def test_the_channel_never_writes_into_claudes_context():
    """Only permission verdicts go out; notifications/claude/channel (a message
    into Claude's context) has no sender in channel.py."""
    import re

    methods = set(re.findall(r'"method":\s*"([^"]+)"', CHANNEL.read_text()))
    assert methods == {"notifications/claude/channel/permission"}, methods


def test_the_channel_answers_only_request_ids_it_received():
    sys.path.insert(0, str(CHANNEL.parent))
    try:
        import channel as ch
    finally:
        sys.path.pop(0)
    bridge = ch.Bridge()
    bridge.remember("r1")
    assert bridge.take("never-seen") is False
    assert bridge.take("r1") is True and bridge.take("r1") is False  # once


def test_a_lone_card_is_not_linked_to_a_different_request():
    """P-a (review, 10-18): one "ls" card, a channel request for "rm -rf x"."""
    world, _ = _world()
    world.apply_hook(_hook("SessionStart"), 0)
    channel_id = world.channel_hello(None, None, "s1", 0)
    world.apply_hook(_hook("PreToolUse", tool_name="Bash", tool_use_id="b1", tool_input={"command": "ls"}), 1)
    world.apply_hook(_hook("PermissionRequest", tool_name="Bash", tool_input={"command": "ls"}), 2)
    world.channel_request(channel_id, {"request_id": "R-rm", "tool_name": "Bash", "input_preview": "rm -rf x"}, 3)
    (card,) = [c for c in world.perms.perms.values()]
    assert "_requestId" not in card and card["can"]["allowDeny"] is False


def test_requests_that_came_first_link_by_content_not_by_arrival_order():
    """P-a': rm then ls reach the channel before the ls hook; allowing "ls" must not allow rm."""
    world, _ = _world()
    world.apply_hook(_hook("SessionStart"), 0)
    channel_id = world.channel_hello(None, None, "s1", 0)
    world.channel_request(channel_id, {"request_id": "R-rm", "tool_name": "Bash", "input_preview": "rm -rf x"}, 1)
    world.channel_request(channel_id, {"request_id": "R-ls", "tool_name": "Bash", "input_preview": "ls"}, 1)
    world.apply_hook(_hook("PreToolUse", tool_name="Bash", tool_use_id="b1", tool_input={"command": "ls"}), 2)
    world.apply_hook(_hook("PermissionRequest", tool_name="Bash", tool_input={"command": "ls"}), 2)
    card = next(c for c in world.perms.perms.values() if c["toolName"] == "Bash" and not c.get("relayOnly"))
    assert card["_requestId"] == "R-ls"
    assert world.decide(card["id"], "allow", 3) is None
    assert world.perms.take_verdicts(channel_id, 4) == [{"request_id": "R-ls", "behavior": "allow"}]


def test_after_the_asked_tool_runs_nothing_still_says_waiting():
    world, state = _world()
    world.apply_hook(_hook("PreToolUse", tool_name="Write", tool_use_id="w", tool_input={"file_path": "/work/app/a"}), 1)
    world.apply_hook(_hook("PermissionRequest", tool_name="Write", tool_input={"file_path": "/work/app/a"}), 2)
    world.apply_hook(_hook("PostToolUse", tool_name="Write", tool_use_id="w", tool_input={"file_path": "/work/app/a"}), 3)
    world.publish()
    assert state.slices["sessions"][0]["status"] == "busy"
    agent = state.slices["agents"][0]
    assert agent["state"] == "idle" and not agent["act"].startswith("許可待ち")


def test_a_command_card_shows_the_command_not_only_the_models_description():
    """The summary was the description ("run"): the page asked for a decision
    without showing what would run (d2, 10-18)."""
    book = PermissionBook()
    card = book.from_hook("s1", "s1", "Bash", {"command": "rm -rf build", "description": "run"}, "u", None, 0)
    assert card["summary"] == "rm -rf build" and card["description"] == "run"
    plain = book.from_hook("s1", "s1", "Bash", {"command": "ls"}, "v", None, 0)
    assert plain["summary"] == "ls" and "description" not in plain

