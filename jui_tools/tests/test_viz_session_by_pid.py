"""A session with no ~/.claude/sessions entry is still known by its claude pid (ticket
2026-11-06-viz-e2e-full-run-red-under-load, its section 「起動し直しの後に名乗りと relay が戻らない件の読み」).

After the ENOSPC night of 2026-11-09 a session's registry entry was gone, and so was its row in `claude agents`: the
server knew it only from its hooks, by id. `jui viz message` from it said "cannot identify this session", and its
channel, reconnected after the restart, was tied to no session ("this session has no relay").

Now forward.py sends the claude pid it runs under (X-Jui-Viz-Claude-Pid, jui-viz 1.4.0), the server keeps pid ->
session from the hooks (World.hook_pids), a channel not tied yet is tied once a hook names its pid or its id, and the
message client asks the server (/api/messages/whoami) when the registry names none of its processes.

Where the registry (or the agents list) and the hooks name a pid differently, the registry wins: it is what the
server went by before, and the hooks fill only what it does not name. An older plugin (no header) and an older
server (no whoami) behave as before.
"""
from __future__ import annotations

import http.server
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from jui_cli.viz import message_client
from jui_cli.viz.ingest import World
from jui_cli.viz.messaging import Refused, Router
from jui_cli.viz.state import VizState

SID = "d3000000-0000-4000-8000-000000000001"
OTHER = "d3000000-0000-4000-8000-000000000002"
THIRD = "d3000000-0000-4000-8000-000000000003"
PID = 4242


def _hook(world: World, sid: str, pid: int | None, at: int, cwd: str = "/work/shared") -> None:
    payload = {"session_id": sid, "cwd": cwd, "hook_event_name": "PreToolUse", "tool_name": "Read",
               "tool_input": {"file_path": f"{cwd}/a"}}
    if pid is not None:
        payload["_claudePid"] = pid   # what the server's /hook adds from X-Jui-Viz-Claude-Pid
    world.apply_hook(payload, at)


def test_after_a_restart_a_channel_ahead_of_the_hooks_is_tied_once_a_hook_names_its_pid():
    world = World(VizState(100))                     # a server just started: nothing known yet
    _hook(world, OTHER, None, 900)                   # two other sessions in the same folder: the cwd names no one
    _hook(world, THIRD, None, 900)
    channel = world.channel_hello(PID, "/work/shared", None, 1000)   # no registry entry: no id to send
    assert SID not in world.perms.relay_sessions()
    _hook(world, SID, PID, 2000)                     # its first hook after the restart names its pid
    assert world.perms.channels[channel].session_id == SID
    assert SID in world.perms.relay_sessions()
    assert (world.prompt_refusal(SID) or (0, ""))[1] != "this session has no relay (relay: false)"
    assert world.pid_session(PID) == SID


def test_a_channel_that_named_its_session_before_the_server_knew_it_is_tied_by_its_hook():
    world = World(VizState(100))
    _hook(world, OTHER, None, 900)
    _hook(world, THIRD, None, 900)
    channel = world.channel_hello(PID, "/work/shared", SID, 1000)   # its id, but no session of that id yet
    assert world.perms.channels[channel].session_id is None
    _hook(world, SID, None, 2000)                     # an older plugin's hook: no pid, the id alone
    assert world.perms.channels[channel].session_id is None   # the id alone ties nothing the pid does not confirm
    _hook(world, SID, PID, 3000)
    assert world.perms.channels[channel].session_id == SID


def test_the_sender_is_known_by_its_pid_through_whoami():
    world = World(VizState(100))
    _hook(world, SID, PID, 1000)
    router = Router(world, talk=None)
    assert router.whoami({"pids": [9999, PID]}) == {"sessionId": SID}
    with pytest.raises(Refused) as no:
        router.whoami({"pids": [9999]})
    assert no.value.status == 404
    for bad in ({}, {"pids": []}, {"pids": ["1"]}, {"pids": [True]}, {"pids": list(range(2, 40))}, {"pids": [5], "x": 1}):
        with pytest.raises(Refused) as e:
            router.whoami(bad)
        assert e.value.status == 400, bad


def test_the_registry_wins_where_it_and_the_hooks_disagree():
    world = World(VizState(100))
    world.apply_session_file({"pid": PID, "sessionId": OTHER, "cwd": "/work/x", "entrypoint": "cli", "status": "idle",
                              "procStart": "Thu Oct 29 00:00:00 2026"}, 1000)
    _hook(world, SID, PID, 2000)                     # a hook says the pid is another session's
    assert world.pid_session(PID) == OTHER           # the registry's word stands
    channel = world.channel_hello(PID, "/work/x", None, 3000)
    assert world.perms.channels[channel].session_id == OTHER


def test_an_older_plugin_sends_no_pid_and_nothing_changes():
    world = World(VizState(100))
    _hook(world, OTHER, None, 900)
    _hook(world, THIRD, None, 900)
    channel = world.channel_hello(PID, "/work/shared", None, 1000)
    _hook(world, SID, None, 2000)
    assert world.hook_pids == {} and world.pid_session(PID) is None
    assert world.perms.channels[channel].session_id is None   # as before: untied, the cwd shared


# ---------------------------------------------------------------- the server's /hook and the client


def test_the_hook_endpoint_adds_the_pid_from_the_header_and_only_a_valid_one(tmp_path, monkeypatch):
    """The header becomes the payload's _claudePid; none, or one that is no pid, adds nothing (an older plugin)."""
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from jui_cli.viz.config import VizConfig
    from jui_cli.viz.server import ServerContext, make_app

    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    got: list = []
    ctx = ServerContext(config=VizConfig(), port=port, token="t" * 24, state=VizState(10))
    ctx.on_hook = got.append

    async def go():
        client = TestClient(TestServer(make_app(ctx), host="127.0.0.1", port=port))
        await client.start_server()
        try:
            for header in ({"X-Jui-Viz-Claude-Pid": "4242"}, {}, {"X-Jui-Viz-Claude-Pid": "1"},
                           {"X-Jui-Viz-Claude-Pid": "-5"}, {"X-Jui-Viz-Claude-Pid": "abc"}):
                r = await client.post("/hook", data=json.dumps({"session_id": SID}),
                                      headers={"Host": f"127.0.0.1:{port}", "X-Jui-Viz-Token": "t" * 24, **header})
                assert r.status == 204
            await asyncio.sleep(0.05)
        finally:
            await client.close()

    asyncio.run(go())
    assert [p.get("_claudePid") for p in got] == [4242, None, None, None, None]


class _Old(http.server.BaseHTTPRequestHandler):
    """A server older than whoami: /api/messages/whoami is not there (404)."""

    def do_POST(self):
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not Found")

    def log_message(self, *a):
        pass


def test_against_an_older_server_the_client_says_what_it_said(tmp_path, monkeypatch, capsys):
    httpd = http.server.HTTPServer(("127.0.0.1", 0), _Old)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        home = tmp_path / "viz"
        home.mkdir()
        (home / "server.json").write_text(json.dumps({"port": httpd.server_address[1], "token": "t" * 24}))
        monkeypatch.setenv("JUI_VIZ_HOME", str(home))
        monkeypatch.setenv("HOME", str(tmp_path))          # no ~/.claude/sessions entry for any process
        monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
        monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
        rc = message_client.command(SimpleNamespace(viz_cmd="message", sender=None, recipient="x", text="hi",
                                                    message_id=None))
    finally:
        httpd.shutdown()
    assert rc == 1
    assert "cannot identify this session; use --from <session-id>" in capsys.readouterr().err
