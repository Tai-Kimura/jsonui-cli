"""P6: the synchronous PermissionRequest hook (forward.py --decide) and the browser's answer."""
from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from jui_cli.viz.config import VizConfig
from jui_cli.viz.ingest import World
from jui_cli.viz.server import ServerContext, make_app
from jui_cli.viz.state import VizState, now_ms

FORWARD = Path(__file__).resolve().parents[1] / "jui_cli" / "viz" / "forward.py"
TOKEN = "t" * 43
SUGGESTIONS = [{"type": "addRules", "rules": [{"toolName": "Bash", "ruleContent": "npm test"}], "behavior": "allow",
                "destination": "localSettings"},
               {"type": "addRules", "rules": [{"toolName": "Bash", "ruleContent": "npm run *"}], "behavior": "allow",
                "destination": "userSettings"}]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _payload(**extra) -> dict:
    return {"hook_event_name": "PermissionRequest", "session_id": "s1", "cwd": "/work/app", "tool_name": "Bash",
            "tool_input": {"command": "npm test"}, "permission_suggestions": SUGGESTIONS, **extra}


async def _setup(tmp_path, wait_sec: float = 5):
    port = _free_port()
    viz = tmp_path / ".jsonui-cli" / "viz"
    viz.mkdir(parents=True, exist_ok=True)
    (viz / "server.json").write_text(json.dumps({"pid": 1, "port": port, "token": TOKEN, "decideWaitSec": wait_sec}))
    world = World(VizState())
    world.apply_hook({"hook_event_name": "PreToolUse", "session_id": "s1", "cwd": "/work/app", "tool_name": "Bash",
                      "tool_use_id": "b1", "tool_input": {"command": "npm test"}}, now_ms())
    ctx = ServerContext(config=VizConfig(decideWaitSec=wait_sec, pushIntervalMs=20), port=port, token=TOKEN,
                        state=world.state, world=world, publish=world.publish)
    client = TestClient(TestServer(make_app(ctx), host="127.0.0.1", port=port))
    await client.start_server()
    return port, world, ctx, client


async def _page(client, port, visible=True):
    ws = await client.ws_connect("/ws", headers={"Host": f"127.0.0.1:{port}", "Origin": f"http://127.0.0.1:{port}"})
    await ws.receive_json()
    await ws.send_json({"type": "auth", "token": TOKEN})
    await ws.receive_json()
    await ws.receive_json()
    await ws.send_json({"type": "presence", "visible": visible})
    await asyncio.sleep(0.1)
    return ws


def _start_hook(tmp_path, payload):
    proc = subprocess.Popen([sys.executable, "-I", "-S", str(FORWARD), "--decide"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(os.environ, HOME=str(tmp_path)))
    proc.stdin.write(json.dumps(payload).encode())
    proc.stdin.close()
    return proc


async def _wait_card(world, cond, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for card in world.perms.perms.values():
            if cond(card):
                return card
        await asyncio.sleep(0.05)
    raise AssertionError("no such card")


async def _answer(ws, **msg):
    await ws.send_json({"type": "perm.decide", "reqId": 1, **msg})
    while True:
        reply = await ws.receive_json(timeout=3)
        if reply.get("type") == "ack":
            return reply


def _finish(proc, timeout=15):
    out, err = proc.communicate(timeout=timeout)
    assert proc.returncode == 0 and err == b""
    return json.loads(out) if out else None


def test_from_now_on_returns_only_the_requests_own_suggestions(tmp_path):
    async def main():
        port, world, ctx, client = await _setup(tmp_path)
        try:
            ws = await _page(client, port)
            # The async forward reports the same request first.
            world.apply_hook(_payload(), now_ms())
            proc = _start_hook(tmp_path, _payload())
            card = await _wait_card(world, lambda c: "_future" in c)
            assert card["can"] == {"allowDeny": True, "always": True, "reason": True}
            # Out of range, or "from now on" with deny: refused, the hook still waits.
            assert (await _answer(ws, permId=card["id"], behavior="allow", always=[5]))["ok"] is False
            assert (await _answer(ws, permId=card["id"], behavior="deny", always=True))["ok"] is False
            assert (await _answer(ws, permId=card["id"], behavior="allow", reason="no"))["ok"] is False
            assert (await _answer(ws, permId=card["id"], behavior="allow", always=[1]))["ok"] is True
            out = await asyncio.get_running_loop().run_in_executor(None, _finish, proc)
            assert out == {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {
                "behavior": "allow", "updatedPermissions": [SUGGESTIONS[1]]}}}
            assert card["status"] == "sent" and card["sentBy"] == "hook"
            assert len(world.perms.perms) == 1  # the async forward's card and this one are the same
            await ws.close()
        finally:
            await client.close()

    asyncio.run(main())


def test_a_reasoned_deny_reaches_the_hook(tmp_path):
    async def main():
        port, world, ctx, client = await _setup(tmp_path)
        try:
            ws = await _page(client, port)
            proc = _start_hook(tmp_path, _payload())
            card = await _wait_card(world, lambda c: "_future" in c)
            assert (await _answer(ws, permId=card["id"], behavior="deny", reason="  本番の DB には触らないで  "))["ok"]
            out = await asyncio.get_running_loop().run_in_executor(None, _finish, proc)
            assert out["hookSpecificOutput"]["decision"] == {"behavior": "deny", "message": "本番の DB には触らないで"}
            await ws.close()
        finally:
            await client.close()

    asyncio.run(main())


def test_no_visible_page_means_no_wait(tmp_path):
    async def main():
        port, world, ctx, client = await _setup(tmp_path, wait_sec=20)
        try:
            ws = await _page(client, port, visible=False)  # a tab in the background
            start = time.monotonic()
            proc = _start_hook(tmp_path, _payload())
            out = await asyncio.get_running_loop().run_in_executor(None, _finish, proc)
            assert out is None and time.monotonic() - start < 3
            await ws.close()
        finally:
            await client.close()

    asyncio.run(main())


def test_the_terminal_answering_first_releases_the_hook_with_nothing(tmp_path):
    async def main():
        port, world, ctx, client = await _setup(tmp_path, wait_sec=20)
        try:
            ws = await _page(client, port)
            start = time.monotonic()
            proc = _start_hook(tmp_path, _payload())
            card = await _wait_card(world, lambda c: "_future" in c)
            world.apply_hook({"hook_event_name": "PostToolUse", "session_id": "s1", "cwd": "/work/app", "tool_name": "Bash",
                              "tool_use_id": "b1", "tool_input": {"command": "npm test"}}, now_ms())
            out = await asyncio.get_running_loop().run_in_executor(None, _finish, proc)
            assert out is None and time.monotonic() - start < 5
            assert card["status"] == "answered_in_terminal"
            await ws.close()
        finally:
            await client.close()

    asyncio.run(main())


def test_no_answer_in_time_gives_back_the_dialog(tmp_path):
    async def main():
        port, world, ctx, client = await _setup(tmp_path, wait_sec=1)
        try:
            ws = await _page(client, port)
            proc = _start_hook(tmp_path, _payload())
            card = await _wait_card(world, lambda c: "_future" in c)
            out = await asyncio.get_running_loop().run_in_executor(None, _finish, proc)
            assert out is None
            assert card["status"] == "pending" and card["can"]["always"] is False  # back to the terminal
            await ws.close()
        finally:
            await client.close()

    asyncio.run(main())


def test_decide_without_a_server_prints_nothing(tmp_path):
    proc = _start_hook(tmp_path, _payload())
    assert _finish(proc) is None
