"""Calling a subagent blows a whistle (ticket 2026-10-20-jui-viz-agent-launch-whistle; requester 10-20: "サブエージェント
呼ぶのは笛鳴らそうか").

The moment an Agent (or Task) call starts, the robot gets agent["whistle"] = {"at", "until"}: a short signal of a
fixed length (robots.LAUNCH_WHISTLE_MS), not the call's length. A background Agent ends in about 0.5 s and the whistle
stays its full length; a foreground Agent runs on (p50 74 s) and the whistle ends at its fixed length all the same, the
robot back to the look it had (carry, then idle while it waits). No other tool whistles.
"""
from __future__ import annotations

import pytest

from jui_cli.viz import robots
from jui_cli.viz.ingest import World
from jui_cli.viz.state import VizState

S, CWD = "s-whistle", "/work/whistle"
LEN = robots.LAUNCH_WHISTLE_MS
CALL = {"description": "画面を作る", "prompt": "作って", "subagent_type": "jsonui-implement"}


def _world() -> World:
    w = World(VizState(100))
    w.apply_hook({"hook_event_name": "SessionStart", "session_id": S, "cwd": CWD, "source": "startup"}, 1)
    w.apply_hook({"hook_event_name": "UserPromptSubmit", "session_id": S, "cwd": CWD, "prompt": "頼む"}, 2)
    return w


def _h(w: World, at: int, **payload) -> None:
    w.apply_hook({"session_id": S, "cwd": CWD, **payload}, at)


def _robot(w: World) -> dict:
    w.publish()
    return next(a for a in w.state.snapshot()["slices"]["agents"] if a["sessionId"] == S)


def test_the_fixed_length_is_a_short_signal():
    assert 2_000 <= LEN <= 3_000
    assert robots.LAUNCH_TOOLS == {"Agent", "Task"}


@pytest.mark.parametrize("tool", ["Agent", "Task"])
def test_a_background_agent_whistles_its_fixed_length_though_the_call_ends_at_once(tool):
    w = _world()
    _h(w, 1_000, hook_event_name="PreToolUse", tool_name=tool, tool_input={**CALL, "run_in_background": True}, tool_use_id="a1")
    assert _robot(w)["whistle"] == {"at": 1_000, "until": 1_000 + LEN}
    _h(w, 1_500, hook_event_name="PostToolUse", tool_name=tool, tool_input={**CALL, "run_in_background": True}, tool_use_id="a1",
       tool_response={"status": "async_launched"})
    w.tick(1_500)
    assert _robot(w)["whistle"]["until"] == 1_000 + LEN   # the call is over; the whistle is not
    w.tick(1_000 + LEN - 1)
    assert "whistle" in _robot(w)
    w.tick(1_000 + LEN)
    assert "whistle" not in _robot(w)


@pytest.mark.parametrize("tool", ["Agent", "Task"])
def test_a_foreground_agent_whistles_only_at_the_start_and_then_waits_as_before(tool):
    w = _world()
    _h(w, 1_000, hook_event_name="PreToolUse", tool_name=tool, tool_input=CALL, tool_use_id="a1")
    a = _robot(w)
    assert a["whistle"] == {"at": 1_000, "until": 1_000 + LEN} and a["state"] == "carry"
    w.tick(1_000 + LEN - 1)
    assert "whistle" in _robot(w)
    w.tick(1_000 + LEN)
    a = _robot(w)
    assert "whistle" not in a, a                       # the call still runs (p50 74 s): no more whistle
    w.tick(60_000)
    a = _robot(w)
    assert "whistle" not in a and a["state"] in ("idle", "thinking"), a   # waiting for the subagent, as before
    _h(w, 74_000, hook_event_name="PostToolUse", tool_name=tool, tool_input=CALL, tool_use_id="a1", tool_response="done")
    assert "whistle" not in _robot(w)


def test_a_second_call_starts_the_whistle_again():
    w = _world()
    _h(w, 1_000, hook_event_name="PreToolUse", tool_name="Agent", tool_input=CALL, tool_use_id="a1")
    _h(w, 2_000, hook_event_name="PreToolUse", tool_name="Agent", tool_input={**CALL, "run_in_background": True}, tool_use_id="a2")
    assert _robot(w)["whistle"] == {"at": 2_000, "until": 2_000 + LEN}
    w.tick(1_000 + LEN)
    assert "whistle" in _robot(w)
    w.tick(2_000 + LEN)
    assert "whistle" not in _robot(w)


@pytest.mark.parametrize("tool,tool_input", [
    ("Read", {"file_path": f"{CWD}/a.txt"}), ("Edit", {"file_path": f"{CWD}/a.py"}), ("Bash", {"command": "ls"}),
    ("WebFetch", {"url": "https://example.com"}), ("SendMessage", {"to": "x", "message": "y"}), ("TodoWrite", {"todos": []}),
    ("mcp__jui-tools__jui_build", {}),
])
def test_no_other_tool_whistles(tool, tool_input):
    w = _world()
    _h(w, 1_000, hook_event_name="PreToolUse", tool_name=tool, tool_input=tool_input, tool_use_id="t1")
    assert "whistle" not in _robot(w)


def test_the_demo_whistles_as_long_as_the_live_view():
    import pathlib
    import re

    demo = (pathlib.Path(robots.__file__).parent / "web" / "js" / "30-source-demo.js").read_text()
    m = re.search(r"launchSec: ([0-9.]+)", demo)
    assert m and float(m.group(1)) * 1000 == LEN
