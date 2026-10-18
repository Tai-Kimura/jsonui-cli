"""AskUserQuestion is a question, not a permission (requester, 10-18: "選択肢なのに許可のボードが出る").

Measured on the requester's orchestrator (Claude Code 2.1.301, VS Code extension, the real server's snapshot): the
question card was made at 18:04:14.756 and a permission card for AskUserQuestion at 18:04:34.791 — 20.0 s later,
askWaitSec, when the --ask hook had given up — with sentBy "hook": the --decide hook was the way in, and the board's
allow went to it. These arms send that PermissionRequest through every way a permission card is born (the async
forward, the --decide hook, the channel relay) and check it never is one; each has a Bash request beside it, the
same way in, that does make a card, so an arm cannot pass because its way in is dead.

Everything runs in a throwaway HOME on a free port; JUI_VIZ_HOME / XDG_STATE_HOME are taken out of the environment.
"""
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
from jui_cli.viz.permissions import HOOK_WAIT_MS
from jui_cli.viz.server import ServerContext, make_app
from jui_cli.viz.state import VizState, now_ms

FORWARD = Path(__file__).resolve().parents[1] / "jui_cli" / "viz" / "forward.py"
TOKEN = "t" * 43
QUESTION = {"questions": [{"question": "どこに入れますか？", "header": "直す場所", "multiSelect": False,
                           "options": [{"label": "driver＋viz が読む", "description": "a"}, {"label": "viz だけ", "description": "b"}]}]}
BASH = {"command": "ls -la"}


def _hook(kind, sid="s1", **fields):
    return {"hook_event_name": kind, "session_id": sid, "cwd": "/work/app", **fields}


def _ask_permission():
    return _hook("PermissionRequest", tool_name="AskUserQuestion", tool_input=QUESTION)


def _bash_permission():
    return _hook("PermissionRequest", tool_name="Bash", tool_input=BASH)


class _Future:
    def __init__(self):
        self.result = None

    def done(self):
        return self.result is not None

    def set_result(self, value):
        self.result = value


# ---------------------------------------------------------------- the async forward


def test_the_forwarded_permission_request_of_a_question_makes_no_card_and_the_robot_still_waits_for_an_answer():
    world = World(VizState())
    world.apply_hook(_hook("PreToolUse", tool_name="AskUserQuestion", tool_use_id="q1", tool_input=QUESTION), 1)
    world.apply_hook(_ask_permission(), 2)
    world.publish()
    assert world.perms.items() == []
    agent = world.agents["s1"]
    assert agent["state"] == "waiting" and agent["act"].startswith("質問に回答待ち"), agent
    assert world.questions.items()[0]["status"] == "pending"          # the question card is still the one to answer
    # the same way in, a Bash request: a card (the way in is alive)
    world.apply_hook(_hook("PreToolUse", tool_name="Bash", tool_use_id="b1", tool_input=BASH), 3)
    world.apply_hook(_bash_permission(), 4)
    assert [c["toolName"] for c in world.perms.items()] == ["Bash"]
    assert world.agents["s1"]["act"].startswith("許可待ち")


def test_the_waiting_hook_gets_no_card_for_a_question():
    world = World(VizState())
    assert world.hook_decide(_ask_permission(), 1) is None
    assert world.perms.items() == []
    assert world.hook_decide(_bash_permission(), 2)["toolName"] == "Bash"


# ---------------------------------------------------------------- the channel relay


def test_the_relay_takes_a_question_and_never_makes_a_card_of_it():
    world = World(VizState())
    world.apply_hook(_hook("SessionStart"), 0)
    channel_id = world.channel_hello(None, None, "s1", 0)
    assert world.channel_request(channel_id, {"request_id": "rq", "tool_name": "AskUserQuestion", "input_preview": "{}"}, 1)
    assert world.channel_request(channel_id, {"request_id": "rb", "tool_name": "Bash", "input_preview": "ls -la"}, 1)
    world.perms.tick(1 + HOOK_WAIT_MS)     # unmatched requests become relay-only cards: the Bash one only
    cards = world.perms.items()
    assert [c["toolName"] for c in cards] == ["Bash"] and cards[0]["can"]["allowDeny"] is True
    assert "rq" not in world.perms.channels[channel_id].open    # nothing for the browser to answer it with


# ---------------------------------------------------------------- end to end: the --decide hook and a visible page


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _env(home) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("JUI_VIZ_HOME", "XDG_STATE_HOME")}
    return dict(env, HOME=str(home))


async def _setup(tmp_path):
    port = _free_port()
    viz = tmp_path / ".local" / "state" / "jui-viz"
    viz.mkdir(parents=True, exist_ok=True)
    (viz / "server.json").write_text(json.dumps({"pid": 1, "port": port, "token": TOKEN, "decideWaitSec": 4}))
    world = World(VizState())
    ctx = ServerContext(config=VizConfig(decideWaitSec=4, pushIntervalMs=20), port=port, token=TOKEN,
                        state=world.state, world=world, publish=world.publish)
    client = TestClient(TestServer(make_app(ctx), host="127.0.0.1", port=port))
    await client.start_server()
    return port, world, client


async def _page(client, port):
    ws = await client.ws_connect("/ws", headers={"Host": f"127.0.0.1:{port}", "Origin": f"http://127.0.0.1:{port}"})
    await ws.receive_json()
    await ws.send_json({"type": "auth", "token": TOKEN})
    await ws.receive_json()
    await ws.receive_json()
    await ws.send_json({"type": "presence", "visible": True})
    await asyncio.sleep(0.1)
    return ws


async def _decide(tmp_path, payload):
    loop = asyncio.get_running_loop()

    def run():
        t0 = time.monotonic()
        p = subprocess.run([sys.executable, "-I", "-S", str(FORWARD), "--decide"], input=json.dumps(payload).encode(),
                           capture_output=True, env=_env(tmp_path), timeout=30)
        return p.stdout.decode(), time.monotonic() - t0
    return await loop.run_in_executor(None, run)


def test_the_decide_hook_lets_a_question_through_at_once_with_a_page_watching(tmp_path):
    async def run():
        port, world, client = await _setup(tmp_path)
        try:
            ws = await _page(client, port)
            ask = await _decide(tmp_path, _ask_permission())
            ask_cards = world.perms.items()
            bash = await _decide(tmp_path, _bash_permission())     # nobody answers: it waits decideWaitSec
            await ws.close()
            return ask, ask_cards, bash
        finally:
            await client.close()
    (ask_out, ask_sec), ask_cards, (bash_out, bash_sec) = asyncio.run(run())
    assert ask_out == "" and ask_sec < 2 and ask_cards == [], (ask_out, ask_sec, ask_cards)
    assert bash_out == "" and bash_sec >= 3.5, (bash_out, bash_sec)  # the way in is alive: the same hook waited


# ---------------------------------------------------------------- the question card says why it cannot be answered


def test_a_wait_that_ran_out_is_on_the_card_and_a_release_or_an_answer_is_not_that():
    world = World(VizState())
    card = world.hook_ask(_hook("PreToolUse", tool_name="AskUserQuestion", tool_use_id="q1", tool_input=QUESTION), now_ms())
    world.question_waiting(card, _Future(), now_ms() + 20_000, now_ms() + 300_000)
    world.question_gave_up(card)                                     # what /hook/ask does when the wait runs out
    item = world.questions.items()[0]
    assert item["status"] == "pending" and item["hookWaiting"] is False and item["waitEnded"] is True

    released = world.hook_ask(_hook("PreToolUse", tool_name="AskUserQuestion", tool_use_id="q2", tool_input=QUESTION), now_ms())
    world.question_waiting(released, _Future(), now_ms() + 20_000, now_ms() + 300_000)
    assert world.release_question(released["id"], now_ms()) is None
    assert "waitEnded" not in released and released["released"] is True
