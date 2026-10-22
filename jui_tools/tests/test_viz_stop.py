"""The page's 停止 (2.3.20, jui-viz 1.3.0): POST /api/stop raises a stop request for one session, and its synchronous
--stop hook (forward.py --stop, PreToolUse / PostToolUse) hands it out as {"continue": false} at the next tool
boundary, and at every later one of that turn; the same hook on the next UserPromptSubmit takes it away. Ticket
2026-10-22-viz-no-way-to-stop-a-session-from-the-page.

Measured 10-22 (Claude Code 2.1.307, isolated): from PreToolUse the call still runs, then the turn ends
(terminal_reason hook_stopped) and no Stop hook comes; from PostToolUse no further model call is made, but the next
call of the same response still ran (its PreToolUse and PostToolUse too); the next prompt is taken as usual. So the
turn stays stopped until the next prompt, and the server ends it at each such call's PostToolUse.
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

from jui_cli.viz import i18n
from jui_cli.viz.config import VizConfig
from jui_cli.viz.ingest import World
from jui_cli.viz.server import ServerContext, make_app
from jui_cli.viz.state import VizState, now_ms

FORWARD = Path(__file__).resolve().parents[1] / "jui_cli" / "viz" / "forward.py"
TOKEN = "s" * 43
STOP = {"continue": False, "stopReason": i18n.tl("stop.reason")}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _tool(kind: str, use_id: str = "b1", sid: str = "s1", **extra) -> dict:
    return {"hook_event_name": kind, "session_id": sid, "cwd": "/work/app", "tool_name": "Bash", "tool_use_id": use_id,
            "tool_input": {"command": "echo one"}, **extra}


def _busy_world() -> World:
    world = World(VizState())
    world.apply_hook({"hook_event_name": "UserPromptSubmit", "session_id": "s1", "cwd": "/work/app", "prompt": "go"}, now_ms())
    return world


def _env(home: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("JUI_VIZ_HOME", "XDG_STATE_HOME")}
    return dict(env, HOME=str(home))


def _hook(home: Path, payload: dict) -> tuple[int, bytes, bytes, float]:
    """forward.py --stop as Claude Code runs it: the payload on stdin; (exit, stdout, stderr, seconds)."""
    t0 = time.monotonic()
    p = subprocess.run([sys.executable, "-I", "-S", str(FORWARD), "--stop"], input=json.dumps(payload).encode(),
                       capture_output=True, env=_env(home), timeout=10)
    return p.returncode, p.stdout, p.stderr, time.monotonic() - t0


class Rig:
    def __init__(self, tmp_path: Path, world: World):
        self.home, self.world, self.port = tmp_path, world, _free_port()
        viz = tmp_path / ".local" / "state" / "jui-viz"
        viz.mkdir(parents=True, exist_ok=True)
        (viz / "server.json").write_text(json.dumps({"pid": 1, "port": self.port, "token": TOKEN}))
        self.ctx = ServerContext(config=VizConfig(pushIntervalMs=20), port=self.port, token=TOKEN, state=world.state,
                                 world=world, publish=world.publish)
        self.client = TestClient(TestServer(make_app(self.ctx), host="127.0.0.1", port=self.port))
        self.own = f"127.0.0.1:{self.port}"

    def page(self, **over) -> dict:
        h = {"Host": self.own, "Origin": f"http://{self.own}", "X-Jui-Viz-Token": TOKEN, "Content-Type": "application/json"}
        h.update(over)
        return {k: v for k, v in h.items() if v is not None}

    async def press(self, body: dict, **over):
        r = await self.client.post("/api/stop", headers=self.page(**over), data=json.dumps(body))
        return r.status, await r.text()

    async def hook(self, payload: dict) -> tuple[int, bytes, bytes, float]:
        return await asyncio.get_running_loop().run_in_executor(None, _hook, self.home, payload)


def _run(tmp_path, body, world=None):
    async def main():
        rig = Rig(tmp_path, world or _busy_world())
        await rig.client.start_server()
        try:
            return await body(rig)
        finally:
            await rig.client.close()
    return asyncio.run(main())


def _session(world: World) -> dict:
    world.publish()
    return next(s for s in world.state.snapshot()["slices"]["sessions"] if s["id"] == "s1")


# ---------------------------------------------------------------- the three arms the orchestrator asked for


def test_a_stop_asked_from_the_page_is_handed_out_as_continue_false_by_the_hook(tmp_path):
    async def body(rig):
        assert (await rig.hook(_tool("PreToolUse", "b0")))[1] == b""   # nothing asked: the call goes on
        assert (await rig.press({"sessionId": "s1"}))[0] == 200
        assert _session(rig.world)["stopAt"] > 0
        rc, out, err, _ = await rig.hook(_tool("PreToolUse", "b1"))
        return rc, json.loads(out), err
    rc, out, err = _run(tmp_path, body)
    assert rc == 0 and err == b"" and out == STOP


def test_no_request_or_no_viz_prints_nothing_and_lets_the_call_go_on(tmp_path):
    async def body(rig):
        quiet = [await rig.hook(_tool(kind, f"b-{kind}")) for kind in ("PreToolUse", "PostToolUse")]
        return quiet, _session(rig.world)
    quiet, session = _run(tmp_path, body)
    assert all(rc == 0 and out == b"" and err == b"" for rc, out, err, _ in quiet)
    assert session["stopHook"] is True and "stopAt" not in session   # heard: the page can say it will stop
    # viz down: the server.json left behind names a port nobody listens on, then no server.json at all
    for _ in range(2):
        rc, out, err, sec = _hook(tmp_path, _tool("PreToolUse"))
        assert rc == 0 and out == b"" and err == b"" and sec < 2.5
        (tmp_path / ".local" / "state" / "jui-viz" / "server.json").unlink(missing_ok=True)


def test_a_slow_viz_prints_nothing_within_about_a_second(tmp_path):
    """A server that takes the connection and never answers: the hook gives up (forward.STOP_READ_SEC) and prints
    nothing, so a hung viz costs each call about a second, never the hook's timeout."""
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(4)
        viz = tmp_path / ".local" / "state" / "jui-viz"
        viz.mkdir(parents=True)
        (viz / "server.json").write_text(json.dumps({"pid": 1, "port": srv.getsockname()[1], "token": TOKEN}))
        rc, out, err, sec = _hook(tmp_path, _tool("PreToolUse"))
    assert rc == 0 and out == b"" and err == b"" and 0.6 < sec < 2.0


def _prompt(sid: str = "s1") -> dict:
    return {"hook_event_name": "UserPromptSubmit", "session_id": sid, "cwd": "/work/app", "prompt": "next"}


def test_handed_out_at_the_first_boundary_and_answered_the_same_until_the_next_prompt(tmp_path):
    async def body(rig):
        await rig.press({"sessionId": "s1"})
        first = (await rig.hook(_tool("PreToolUse", "b1")))[1]
        rig.world.apply_hook(_tool("PreToolUse", "b1"), now_ms())    # the async forward of the same call
        rig.world.apply_hook(_tool("PostToolUse", "b1"), now_ms())   # the call ran: the turn ended there
        after = _session(rig.world)
        second = (await rig.hook(_tool("PostToolUse", "b1")))[1]
        third = (await rig.hook(_tool("PreToolUse", "b2")))[1]
        again = await rig.press({"sessionId": "s1"})                  # pressed again while it stops: nothing new
        prompt = (await rig.hook(_prompt()))[1]                        # the next prompt's synchronous --stop
        fourth = (await rig.hook(_tool("PreToolUse", "b3")))[1]
        return first, after, second, third, again, prompt, fourth, _session(rig.world), rig.world
    first, after, second, third, again, prompt, fourth, last, world = _run(tmp_path, body)
    assert json.loads(first) == STOP and json.loads(second) == STOP and json.loads(third) == STOP
    assert "stopAt" not in after and after["stopTurn"] is True and after["stoppedAt"] > 0
    assert after["status"] == "idle"   # no Stop hook comes after hook_stopped: the server ends the turn
    assert prompt == b"" and fourth == b"" and "stopTurn" not in last and "haltOn" not in last
    kinds = [e["kind"] for e in world.state.recent_events(50)]
    assert kinds.count("StopAsked") == 1 and kinds.count("Stopped") == 1


def test_the_rest_of_the_stopped_response_runs_and_the_turn_ends_after_it_again(tmp_path):
    """Measured 10-22: a PostToolUse continue:false lets the response's next call run; the page goes busy at its
    PreToolUse and must not stay so (no Stop hook comes): the server ends the turn after that call too."""
    async def body(rig):
        rig.world.apply_hook(_tool("PreToolUse", "b1"), now_ms())
        await rig.press({"sessionId": "s1"})
        rig.world.apply_hook(_tool("PostToolUse", "b1"), now_ms())
        first = (await rig.hook(_tool("PostToolUse", "b1")))[1]
        rig.world.apply_hook(_tool("PreToolUse", "b2"), now_ms())     # echo two, the same response
        busy = _session(rig.world)["status"]
        again = await rig.press({"sessionId": "s1"})                   # pressed again while it still works: no new ask
        second = (await rig.hook(_tool("PreToolUse", "b2")))[1]
        rig.world.apply_hook(_tool("PostToolUse", "b2"), now_ms())
        return first, busy, again, second, _session(rig.world), rig.world
    first, busy, again, second, session, world = _run(tmp_path, body)
    assert json.loads(first) == STOP and busy == "busy" and again[0] == 200 and json.loads(second) == STOP
    assert session["status"] == "idle" and "haltOn" not in session and "stopAt" not in session
    kinds = [e["kind"] for e in world.state.recent_events(50)]
    assert kinds.count("StopAsked") == 1 and kinds.count("Stopped") == 1


def test_a_late_async_prompt_never_lets_the_old_stop_stop_the_new_turn(tmp_path):
    """The prompt's async forward may come after the new turn's first tool asks: the synchronous --stop of the
    UserPromptSubmit has taken the stop away already, and the late forward changes nothing."""
    async def body(rig):
        await rig.press({"sessionId": "s1"})
        rig.world.apply_hook(_tool("PreToolUse", "b1"), now_ms())
        stopped = (await rig.hook(_tool("PostToolUse", "b1")))[1]
        prompt = (await rig.hook(_prompt()))[1]                        # its async forward is not here yet
        new = (await rig.hook(_tool("PreToolUse", "b2")))[1]          # the new turn's first tool
        rig.world.apply_hook(_tool("PreToolUse", "b2"), now_ms())
        rig.world.apply_hook(_prompt(), now_ms())                      # the late async forward of the prompt
        later = (await rig.hook(_tool("PostToolUse", "b2")))[1]
        return stopped, prompt, new, later, _session(rig.world)
    stopped, prompt, new, later, session = _run(tmp_path, body)
    assert json.loads(stopped) == STOP and prompt == b"" and new == b"" and later == b""
    assert session["status"] == "busy" and not ({"stopAt", "stopTurn", "haltOn"} & set(session))


# ---------------------------------------------------------------- where the request ends without a stop


def test_a_stop_at_post_tool_use_ends_the_turn_at_once(tmp_path):
    async def body(rig):
        rig.world.apply_hook(_tool("PreToolUse", "b1"), now_ms())
        rig.world.apply_hook(_tool("PostToolUse", "b1"), now_ms())   # the async forward came first
        await rig.press({"sessionId": "s1"})
        out = (await rig.hook(_tool("PostToolUse", "b1")))[1]
        return json.loads(out), _session(rig.world), rig.world
    out, session, world = _run(tmp_path, body)
    assert out == STOP and session["status"] == "idle" and "haltOn" not in session
    main = next(a for a in world.agents.values() if a["sessionId"] == "s1" and a["kind"] == "main")
    assert main["state"] == "done" and main["act"] == i18n.tl("act.stopped")


def test_a_subagents_call_is_answered_but_leaves_the_request_for_the_main(tmp_path):
    async def body(rig):
        await rig.press({"sessionId": "s1"})
        sub = json.loads((await rig.hook(_tool("PreToolUse", "c1", agent_id="a1", agent_type="Explore")))[1])
        waiting = _session(rig.world).get("stopAt")
        main = json.loads((await rig.hook(_tool("PostToolUse", "t1")))[1])
        return sub, waiting, main, _session(rig.world)
    sub, waiting, main, session = _run(tmp_path, body)
    assert sub == STOP and waiting and main == STOP and "stopAt" not in session


def test_a_turn_that_ends_or_a_new_prompt_takes_a_waiting_request_away(tmp_path):
    for kind in ("Stop", "UserPromptSubmit", "SessionEnd"):
        world = _busy_world()

        async def body(rig, kind=kind):
            await rig.press({"sessionId": "s1"})
            rig.world.apply_hook({"hook_event_name": kind, "session_id": "s1", "cwd": "/work/app", "prompt": "next"}, now_ms())
            return (await rig.hook(_tool("PreToolUse", "b9")))[1], _session(rig.world)
        out, session = _run(tmp_path, body, world)
        assert out == b"" and "stopAt" not in session, kind
        if kind == "Stop":
            assert [e["kind"] for e in world.state.recent_events(50)].count("StopMissed") == 1


# ---------------------------------------------------------------- the page's request


def test_the_page_can_take_a_waiting_stop_back(tmp_path):
    async def body(rig):
        await rig.press({"sessionId": "s1"})
        back = await rig.press({"sessionId": "s1", "cancel": True})
        again = await rig.press({"sessionId": "s1", "cancel": True})
        return back[0], again[0], (await rig.hook(_tool("PreToolUse")))[1]
    back, again, out = _run(tmp_path, body)
    assert back == 200 and again == 409 and out == b""


def test_a_session_that_is_not_working_or_unknown_is_refused(tmp_path):
    world = World(VizState())
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/work/app"}, now_ms())

    async def body(rig):
        return [(await rig.press(b))[0] for b in ({"sessionId": "s1"}, {"sessionId": "nobody"}, {"sessionId": ""},
                                                     {"sessionId": "s1", "cancel": "yes"})]
    assert _run(tmp_path, body, world) == [409, 404, 400, 400]


def test_api_stop_has_the_page_only_checks_of_api_prompt(tmp_path):
    async def body(rig):
        data = json.dumps({"sessionId": "s1"})
        out = {
            "token": (await rig.client.post("/api/stop", headers=rig.page(**{"X-Jui-Viz-Token": "x" * 43}), data=data)).status,
            "origin": (await rig.client.post("/api/stop", headers=rig.page(Origin="http://evil.example"), data=data)).status,
            "no-origin": (await rig.client.post("/api/stop", headers=rig.page(Origin=None), data=data)).status,
            "type": (await rig.client.post("/api/stop", headers=rig.page(**{"Content-Type": "text/plain"}), data=data)).status,
            "get": (await rig.client.get("/api/stop", headers=rig.page())).status,
            "big": (await rig.client.post("/api/stop", headers=rig.page(), data=json.dumps({"sessionId": "s" * 2000}))).status,
        }
        return out, _session(rig.world)
    out, session = _run(tmp_path, body)
    assert out == {"token": 401, "origin": 403, "no-origin": 403, "type": 415, "get": 405, "big": 413}
    assert "stopAt" not in session


def test_hook_stop_takes_only_a_local_process_with_the_token(tmp_path):
    async def body(rig):
        await rig.press({"sessionId": "s1"})
        data = json.dumps(_tool("PreToolUse"))
        page = await rig.client.post("/hook/stop", headers=rig.page(), data=data)       # a browser (Origin): refused
        bad = await rig.client.post("/hook/stop", headers={"X-Jui-Viz-Token": "x" * 43}, data=data)
        return page.status, bad.status, _session(rig.world).get("stopAt")
    page, bad, waiting = _run(tmp_path, body)
    assert page == 403 and bad == 401 and waiting
