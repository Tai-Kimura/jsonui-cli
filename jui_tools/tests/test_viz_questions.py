"""AskUserQuestion answered from the browser (jui_cli/viz/questions.py, server /hook/ask, forward.py --ask; 10-18).

The answer is PreToolUse's documented one: allow, and updatedInput = the input as it came plus ``answers`` keyed by
the question's text. How a multiple choice and a free answer are written (questions.MULTI_SEP) is what
ask-check.sh measures on a real session; these arms take the module's choice and check everything around it.
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

from jui_cli.viz import questions as qmod
from jui_cli.viz.config import VizConfig
from jui_cli.viz.ingest import World
from jui_cli.viz.server import ServerContext, make_app
from jui_cli.viz.state import VizState, now_ms

FORWARD = Path(__file__).resolve().parents[1] / "jui_cli" / "viz" / "forward.py"
TOKEN = "t" * 43
FRUIT = {"question": "好きな果物は？", "header": "果物", "multiSelect": False,
         "options": [{"label": "りんご", "description": "赤い"}, {"label": "みかん", "description": "冬", "preview": "## みかん\n- 甘い"}]}
COLOR = {"question": "好きな色は？", "header": "色", "multiSelect": True,
         "options": [{"label": "赤", "description": "r"}, {"label": "青", "description": "b"}, {"label": "緑", "description": "g"}]}
INPUT = {"questions": [FRUIT, COLOR]}


def _pre(use_id="u1", tool_input=None, sid="s1"):
    return {"hook_event_name": "PreToolUse", "session_id": sid, "cwd": "/work/app", "tool_name": "AskUserQuestion",
            "tool_use_id": use_id, "tool_input": tool_input or INPUT}


def _post(answers, use_id="u1", sid="s1"):
    return {"hook_event_name": "PostToolUse", "session_id": sid, "cwd": "/work/app", "tool_name": "AskUserQuestion",
            "tool_use_id": use_id, "tool_input": {**INPUT, "answers": answers}, "tool_response": {"answers": answers}}


class _Future:
    """Enough of an asyncio future for the book (set_result / done)."""
    def __init__(self):
        self.result = None

    def done(self):
        return self.result is not None

    def set_result(self, value):
        self.result = value


def _waiting_card(world):
    card = world.hook_ask(_pre(), now_ms())
    fut = _Future()
    world.question_waiting(card, fut, now_ms() + 20_000, now_ms() + 300_000)
    return card, fut


# ---------------------------------------------------------------- the answer's shape


def test_a_single_and_a_multiple_choice_make_the_documented_answer():
    world = World(VizState())
    card, fut = _waiting_card(world)
    err = world.answer_question(card["id"], {FRUIT["question"]: {"labels": ["みかん"]}, COLOR["question"]: {"labels": ["緑", "赤"]}}, now_ms())
    assert err is None
    out = fut.result["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse" and out["permissionDecision"] == "allow"
    assert out["updatedInput"]["questions"] == INPUT["questions"]          # the questions as they came, untouched
    assert out["updatedInput"]["answers"] == {FRUIT["question"]: "みかん", COLOR["question"]: qmod.MULTI_SEP.join(["赤", "緑"])}


def test_a_free_answer_goes_in_as_written_alone_or_after_the_labels():
    answers, err = qmod.answer_strings(INPUT["questions"], {FRUIT["question"]: {"other": "  ぶどう  "},
                                                           COLOR["question"]: {"labels": ["青"], "other": "金"}})
    assert err is None and answers == {FRUIT["question"]: "ぶどう", COLOR["question"]: qmod.MULTI_SEP.join(["青", "金"])}


def test_every_question_must_be_answered_and_only_with_its_options():
    qs = INPUT["questions"]
    assert qmod.answer_strings(qs, {FRUIT["question"]: {"labels": ["りんご"]}})[1]                              # the second is missing
    assert qmod.answer_strings(qs, {FRUIT["question"]: {"labels": ["りんご", "みかん"]}, COLOR["question"]: {"labels": ["赤"]}})[1]  # two for one
    assert qmod.answer_strings(qs, {FRUIT["question"]: {"labels": ["りんご"], "other": "梨"}, COLOR["question"]: {"labels": ["赤"]}})[1]
    assert qmod.answer_strings(qs, {FRUIT["question"]: {"labels": ["バナナ"]}, COLOR["question"]: {"labels": ["赤"]}})[1]  # not an option
    assert qmod.answer_strings(qs, {FRUIT["question"]: {"labels": ["りんご"]}, COLOR["question"]: {"labels": []}})[1]   # none chosen
    # a label the question does not have is refused, not dropped (a multiple choice would otherwise go through)
    assert qmod.answer_strings(qs, {FRUIT["question"]: {"labels": ["りんご"]}, COLOR["question"]: {"labels": ["赤", "紫"]}})[1]


def test_a_question_not_shown_in_full_cannot_be_answered_from_the_browser():
    long = {**FRUIT, "options": [{"label": "りんご", "description": "x" * (qmod.TEXT_MAX + 1)}, FRUIT["options"][1]]}
    world = World(VizState())
    card = world.hook_ask(_pre(tool_input={"questions": [long]}), now_ms())
    fut = _Future()
    world.question_waiting(card, fut, now_ms() + 20_000, now_ms() + 300_000)
    assert card["tooLongToShow"] and card["hookWaiting"] is False
    assert world.answer_question(card["id"], {FRUIT["question"]: {"labels": ["りんご"]}}, now_ms())
    assert fut.result is None
    same_text = {"questions": [FRUIT, {**COLOR, "question": FRUIT["question"]}]}   # answers are keyed by the text
    assert World(VizState()).hook_ask(_pre(tool_input=same_text), now_ms())["tooLongToShow"]


# ---------------------------------------------------------------- the card's life


def test_the_async_forward_and_the_waiting_hook_share_one_card():
    world = World(VizState())
    world.apply_hook(_pre(), now_ms())
    card = world.hook_ask(_pre(), now_ms())
    world.publish()
    assert len(world.state.slices["questions"]) == 1 and world.state.slices["questions"][0]["id"] == card["id"]


def test_the_terminal_answering_first_releases_the_hook_and_refuses_the_browser():
    world = World(VizState())
    card, fut = _waiting_card(world)
    world.apply_hook(_post({FRUIT["question"]: "りんご", COLOR["question"]: "青"}), now_ms())
    assert card["status"] == "answered_in_terminal" and fut.result == {}      # the hook prints nothing
    assert card["gotAnswers"] == {FRUIT["question"]: "りんご", COLOR["question"]: "青"}
    assert world.answer_question(card["id"], {FRUIT["question"]: {"labels": ["みかん"]}, COLOR["question"]: {"labels": ["赤"]}}, now_ms())
    assert any("ターミナルで質問に回答" in e["text"] for e in world.state.events)


def test_the_browsers_answer_is_logged_and_confirmed_by_post_tool_use():
    world = World(VizState())
    card, _ = _waiting_card(world)
    world.answer_question(card["id"], {FRUIT["question"]: {"labels": ["りんご"]}, COLOR["question"]: {"labels": ["赤"]}}, now_ms())
    assert card["status"] == "sent"
    world.apply_hook(_post({FRUIT["question"]: "りんご", COLOR["question"]: "赤"}), now_ms())
    assert card["status"] == "answered"
    assert any(e["text"].startswith("ブラウザで質問に回答 果物: りんご / 色: 赤") for e in world.state.events)


def test_stop_expires_a_question_left_open_and_releases_its_hook():
    world = World(VizState())
    card, fut = _waiting_card(world)
    world.apply_hook({"hook_event_name": "Stop", "session_id": "s1", "cwd": "/work/app"}, now_ms())
    assert card["status"] == "expired" and fut.result == {}


# ---------------------------------------------------------------- end to end: forward.py --ask and the server


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _setup(tmp_path, wait_sec: float = 5, max_sec: float = 30):
    port = _free_port()
    viz = tmp_path / ".local" / "state" / "jui-viz"   # paths.viz_home() under the fake HOME
    viz.mkdir(parents=True, exist_ok=True)
    (viz / "server.json").write_text(json.dumps({"pid": 1, "port": port, "token": TOKEN, "askMaxSec": max_sec}))
    world = World(VizState())
    ctx = ServerContext(config=VizConfig(askWaitSec=wait_sec, askMaxSec=max_sec, pushIntervalMs=20), port=port, token=TOKEN,
                        state=world.state, world=world, publish=world.publish)
    client = TestClient(TestServer(make_app(ctx), host="127.0.0.1", port=port))
    await client.start_server()
    return port, world, client


async def _page(client, port, visible=True):
    ws = await client.ws_connect("/ws", headers={"Host": f"127.0.0.1:{port}", "Origin": f"http://127.0.0.1:{port}"})
    await ws.receive_json()
    await ws.send_json({"type": "auth", "token": TOKEN})
    await ws.receive_json()
    await ws.receive_json()
    await ws.send_json({"type": "presence", "visible": visible})
    await asyncio.sleep(0.1)
    return ws


def _env(home) -> dict:
    """The fake HOME, and nothing that would point viz_home() elsewhere (the real server's files)."""
    env = {k: v for k, v in os.environ.items() if k not in ("JUI_VIZ_HOME", "XDG_STATE_HOME")}
    return dict(env, HOME=str(home))


def _hook(tmp_path, payload):
    proc = subprocess.Popen([sys.executable, "-I", "-S", str(FORWARD), "--ask"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_env(tmp_path))
    proc.stdin.write(json.dumps(payload).encode())
    proc.stdin.close()
    proc.stdin = None
    return proc


async def _finish(proc, timeout=15):
    loop = asyncio.get_running_loop()
    out, _ = await loop.run_in_executor(None, lambda: proc.communicate(timeout=timeout))
    return out.decode()


async def _wait(cond, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = cond()
        if found:
            return found
        await asyncio.sleep(0.05)
    raise AssertionError("timed out")


def test_the_page_answers_and_the_hook_prints_the_contract(tmp_path):
    async def run():
        port, world, client = await _setup(tmp_path)
        try:
            ws = await _page(client, port)
            proc = _hook(tmp_path, _pre())
            card = await _wait(lambda: next((c for c in world.questions.cards.values() if c["hookWaiting"]), None))
            await ws.send_json({"type": "question.answer", "reqId": 1, "questionId": card["id"],
                                "answers": {FRUIT["question"]: {"labels": ["りんご"]}, COLOR["question"]: {"labels": ["青", "赤"], "other": "金"}}})
            out = json.loads(await _finish(proc))
            await ws.close()
            return out
        finally:
            await client.close()
    out = asyncio.run(run())["hookSpecificOutput"]
    assert out["permissionDecision"] == "allow" and out["updatedInput"]["questions"] == INPUT["questions"]
    assert out["updatedInput"]["answers"] == {FRUIT["question"]: "りんご", COLOR["question"]: qmod.MULTI_SEP.join(["赤", "青", "金"])}


def test_no_page_watching_lets_the_question_through_at_once(tmp_path):
    async def run():
        port, world, client = await _setup(tmp_path, wait_sec=20)
        try:
            ws = await _page(client, port, visible=False)
            t0 = time.monotonic()
            out = await _finish(_hook(tmp_path, _pre()))
            await ws.close()
            return out, time.monotonic() - t0, world.questions.items()
        finally:
            await client.close()
    out, took, items = asyncio.run(run())
    assert out == "" and took < 5 and items and items[0]["hookWaiting"] is False


def test_the_terminal_answering_first_makes_the_waiting_hook_print_nothing(tmp_path):
    async def run():
        port, world, client = await _setup(tmp_path, wait_sec=20)
        try:
            ws = await _page(client, port)
            proc = _hook(tmp_path, _pre())
            await _wait(lambda: any(c["hookWaiting"] for c in world.questions.cards.values()))
            t0 = time.monotonic()
            world.apply_hook(_post({FRUIT["question"]: "みかん", COLOR["question"]: "緑"}), now_ms())
            out = await _finish(proc)
            await ws.close()
            return out, time.monotonic() - t0
        finally:
            await client.close()
    out, took = asyncio.run(run())
    assert out == "" and took < 5


def test_the_asking_robot_waits_with_its_hand_up_and_goes_back_after_the_answer():
    world = World(VizState())
    world.apply_hook(_pre(), now_ms())
    agent = world.agents["s1"]
    assert agent["state"] == "waiting" and agent["act"] == "質問に回答待ち 果物 / 色"
    world.apply_hook(_post({FRUIT["question"]: "りんご", COLOR["question"]: "赤"}), now_ms())
    assert agent["state"] == "idle"


# ---------------------------------------------------------------- the wait: short unless someone answers (measured 10-18)
# While the hook waits the terminal shows no question, so it must not wait long for nobody.


def test_a_hold_moves_the_wait_but_never_past_the_latest():
    world = World(VizState())
    card = world.hook_ask(_pre(), 1_000)
    world.question_waiting(card, _Future(), 21_000, 301_000)
    assert world.hold_question(card["id"], 15_000, 20_000) is None and card["waitUntil"] == 35_000
    world.hold_question(card["id"], 10_000, 20_000)                 # an older hold never shortens it
    assert card["waitUntil"] == 35_000
    world.hold_question(card["id"], 290_000, 20_000)
    assert card["waitUntil"] == 301_000


def test_release_hands_the_question_to_the_terminal_at_once():
    world = World(VizState())
    card, fut = _waiting_card(world)
    assert world.release_question(card["id"], now_ms()) is None
    assert fut.result == {} and card["status"] == "pending" and card["hookWaiting"] is False and card["released"]
    assert world.answer_question(card["id"], {FRUIT["question"]: {"labels": ["りんご"]}, COLOR["question"]: {"labels": ["赤"]}}, now_ms())
    assert world.release_question(card["id"], now_ms())            # nothing waits any more


def test_nobody_answering_gives_the_question_back_after_the_short_wait(tmp_path):
    async def run():
        port, world, client = await _setup(tmp_path, wait_sec=1.5, max_sec=30)
        try:
            ws = await _page(client, port)
            t0 = time.monotonic()
            out = await _finish(_hook(tmp_path, _pre()))
            await ws.close()
            return out, time.monotonic() - t0
        finally:
            await client.close()
    out, took = asyncio.run(run())
    assert out == "" and 1.2 < took < 6


def test_holds_from_the_page_keep_the_hook_waiting_for_the_answer(tmp_path):
    async def run():
        port, world, client = await _setup(tmp_path, wait_sec=1.5, max_sec=30)
        try:
            ws = await _page(client, port)
            proc = _hook(tmp_path, _pre())
            card = await _wait(lambda: next((c for c in world.questions.cards.values() if c["hookWaiting"]), None))
            for _ in range(4):                       # 4 s of answering: past the 1.5 s wait, held each second
                await ws.send_json({"type": "question.hold", "reqId": 2, "questionId": card["id"]})
                await asyncio.sleep(1)
            await ws.send_json({"type": "question.answer", "reqId": 3, "questionId": card["id"],
                                "answers": {FRUIT["question"]: {"labels": ["りんご"]}, COLOR["question"]: {"labels": ["赤"]}}})
            out = await _finish(proc)
            await ws.close()
            return out
        finally:
            await client.close()
    out = json.loads(asyncio.run(run()))
    assert out["hookSpecificOutput"]["updatedInput"]["answers"] == {FRUIT["question"]: "りんご", COLOR["question"]: "赤"}


def test_the_terminal_button_ends_the_hooks_wait_with_nothing(tmp_path):
    async def run():
        port, world, client = await _setup(tmp_path, wait_sec=20, max_sec=30)
        try:
            ws = await _page(client, port)
            proc = _hook(tmp_path, _pre())
            card = await _wait(lambda: next((c for c in world.questions.cards.values() if c["hookWaiting"]), None))
            t0 = time.monotonic()
            await ws.send_json({"type": "question.release", "reqId": 4, "questionId": card["id"]})
            out = await _finish(proc)
            await ws.close()
            return out, time.monotonic() - t0
        finally:
            await client.close()
    out, took = asyncio.run(run())
    assert out == "" and took < 5


# The person declined in the terminal ("User declined to answer questions", measured 10-18): no PostToolUse and no
# PostToolUseFailure follows that PreToolUse, so what comes next in the session closes the card.


def test_a_question_declined_in_the_terminal_is_closed_by_the_sessions_next_question():
    world = World(VizState())
    old, fut = _waiting_card(world)
    new = world.hook_ask(_pre(use_id="u2"), now_ms())
    assert old["status"] == "expired" and fut.result == {} and new["status"] == "pending"
    other = world.hook_ask(_pre(use_id="u3", sid="s2"), now_ms())           # another session's question stays
    assert new["status"] == "pending" and other["status"] == "pending"
    assert world.hook_ask(_pre(use_id="u2"), now_ms()) is new and new["status"] == "pending"   # the same ask again


def test_a_question_declined_in_the_terminal_is_closed_by_the_sessions_next_prompt():
    world = World(VizState())
    card, fut = _waiting_card(world)
    world.apply_hook({"hook_event_name": "UserPromptSubmit", "session_id": "s1", "cwd": "/work/app", "prompt": "次"}, now_ms())
    assert card["status"] == "expired" and fut.result == {}
