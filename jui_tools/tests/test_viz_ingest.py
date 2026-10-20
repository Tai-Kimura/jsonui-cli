"""Hook payloads → projects / sessions / agents / events (jui_cli/viz/ingest.py, robots.py, rooms.py)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jui_cli.viz import robots
from jui_cli.viz.ingest import World
from jui_cli.viz.rooms import Rooms, find_root
from jui_cli.viz.state import VizState

PROBE = sorted((Path(__file__).parent / "fixtures" / "viz" / "probe").glob("*.json"))


def _world() -> tuple[World, VizState]:
    state = VizState()
    return World(state, tool_input_max=50), state


def _hook(kind, sid="s-aaaa", at=0, **fields):
    return {"hook_event_name": kind, "session_id": sid, "cwd": "/work/shop-app", **fields}


def _agent(state, aid):
    return next(a for a in state.slices["agents"] if a["id"] == aid)


def test_the_probe_recording_walks_a_robot_through_its_states():
    world, state = _world()
    seen = []
    for i, path in enumerate(PROBE):
        world.apply_hook(json.loads(path.read_text()), i * 500)
        world.publish()
        main = state.slices["agents"][0]
        seen.append(main["state"])
    assert len(PROBE) == 22
    assert {"idle", "reading", "typing", "waiting", "command", "carry", "done"} <= set(seen)
    # The Explore subagent appeared, and leaves 5 s after SubagentStop.
    world.tick(len(PROBE) * 500 + 5_000)
    world.publish()
    assert [a["kind"] for a in state.slices["agents"]] == ["main"]
    assert [s["status"] for s in state.slices["sessions"]] == ["ended"]


def test_a_refused_tool_that_never_reports_back_does_not_keep_the_robot_busy():
    """In -p a refused Write sent PermissionRequest and then nothing (no Post,
    no PermissionDenied): the next PreToolUse settles it."""
    world, state = _world()
    world.apply_hook(_hook("PreToolUse", tool_name="Write", tool_use_id="w1", tool_input={"file_path": "/work/shop-app/a.txt"}), 1)
    world.apply_hook(_hook("PermissionRequest", tool_name="Write", tool_input={"file_path": "/work/shop-app/a.txt"}), 2)
    world.publish()
    assert _agent(state, "s-aaaa")["state"] == "waiting"
    world.apply_hook(_hook("PreToolUse", tool_name="Bash", tool_use_id="b1", tool_input={"command": "ls"}), 3)
    world.apply_hook(_hook("PostToolUse", tool_name="Bash", tool_use_id="b1", tool_input={"command": "ls"}), 4)
    world.publish()
    assert _agent(state, "s-aaaa")["state"] == "idle"


def test_parallel_tools_keep_the_robot_busy_until_the_last_one_ends():
    world, state = _world()
    for use_id, tool in (("r1", "Read"), ("r2", "Grep")):
        world.apply_hook(_hook("PreToolUse", tool_name=tool, tool_use_id=use_id, tool_input={"file_path": "/work/shop-app/x"}), 1)
    world.apply_hook(_hook("PostToolUse", tool_name="Read", tool_use_id="r1", tool_input={}), 2)
    world.publish()
    assert _agent(state, "s-aaaa")["state"] == "reading"
    world.apply_hook(_hook("PostToolUse", tool_name="Grep", tool_use_id="r2", tool_input={}), 3)
    world.publish()
    assert _agent(state, "s-aaaa")["state"] == "idle"


def test_unknown_events_and_payloads_without_a_session_are_dropped():
    world, state = _world()
    assert world.apply_hook(_hook("MessageDisplay"), 1) is None
    assert world.apply_hook({"hook_event_name": "PreToolUse"}, 1) is None
    assert world.apply_hook(_hook("SessionStart", sid=""), 1) is None
    assert len(state.events) == 0


def test_tool_input_strings_are_cut_and_paths_are_relative_to_the_project():
    world, state = _world()
    event = world.apply_hook(_hook("PreToolUse", tool_name="Write", tool_use_id="w",
                                   tool_input={"file_path": "/work/shop-app/docs/a.json", "content": "x" * 500}), 1)
    assert event["detail"]["content"] == "x" * 50 + "…"
    assert event["text"] == "Write docs/a.json"  # relative to the project root


def test_labels_are_unique_across_all_robots():
    world, state = _world()
    for sid in ("abc111", "abc222", "abd333"):
        world.apply_hook(_hook("SessionStart", sid=sid), 1)
    world.publish()
    labels = [a["label"] for a in state.slices["agents"]]
    assert labels == ["ab", "abc", "abd"]


def test_a_session_seen_only_by_the_agents_list_gets_a_room_and_a_robot():
    world, state = _world()
    world.apply_agents_list([{"sessionId": "x1", "cwd": "/work/other", "status": "busy", "pid": 42, "name": "n"},
                             {"no": "id"}, "junk"], 5)
    world.publish()
    (session,) = state.slices["sessions"]
    assert session["status"] == "busy" and session["title"] == "n"
    assert world.pid_to_session == {42: "x1"}
    assert [a["id"] for a in state.slices["agents"]] == ["x1"]
    assert [p["name"] for p in state.slices["projects"]] == ["other/"]


def test_a_rename_in_the_agents_list_renames_the_session():
    """/rename (or `claude -n`) changes the row's name: the robot's tag and the panels follow the newest one (10-19)."""
    world, state = _world()
    world.apply_hook(_hook("SessionStart", sid="r1"), 1)
    world.apply_agents_list([{"sessionId": "r1", "cwd": "/work/app", "status": "idle", "name": "最初の名前"}], 2)
    world.publish()
    assert state.slices["sessions"][0]["title"] == "最初の名前"
    world.apply_agents_list([{"sessionId": "r1", "cwd": "/work/app", "status": "idle", "name": "  新しい\n名前  "}], 3)
    world.publish()
    assert state.slices["sessions"][0]["title"] == "新しい 名前"   # one line
    world.apply_agents_list([{"sessionId": "r1", "cwd": "/work/app", "status": "idle"}], 4)   # a row without a name keeps it
    world.publish()
    assert state.slices["sessions"][0]["title"] == "新しい 名前"


def test_stop_with_background_tasks_keeps_the_session_busy():
    world, state = _world()
    world.apply_hook(_hook("UserPromptSubmit", prompt="p" * 300), 1)
    world.apply_hook(_hook("Stop", background_tasks=[{"id": "b"}]), 2)
    world.publish()
    session = state.slices["sessions"][0]
    assert session["status"] == "busy" and len(session["lastPrompt"]) == 200
    world.apply_hook(_hook("Stop", background_tasks=[]), 3)
    world.publish()
    assert state.slices["sessions"][0]["status"] == "idle"


@pytest.mark.parametrize("command,state", [
    ("xcodebuild test -scheme App", "phone"),
    ("./gradlew connectedDebugAndroidTest", "phone"),
    ("adb -s emulator-5554 shell ls", "phone"),
    ("npx playwright test", "phone"),
    ("xcrun simctl io booted screenshot x.png", "phone"),
    ("jsonui-test validate tests", "command"),   # jsonui-test has no subcommand that runs tests (10-18)
    ("find ~/.local/state/jsonui-test -maxdepth 3", "command"),
    ("git status", "command"),
    ("readb file", "command"),
])
def test_bash_commands_that_drive_a_device_are_phone(command, state):
    assert robots.state_for_tool("Bash", {"command": command}) == state


def test_roles_follow_the_agent_type():
    assert robots.role_for("jsonui-navigation-ios", False) == "navigation"
    assert robots.role_for("jsonui-test", False) == "test"
    assert robots.role_for("Explore", False) == "other"
    assert robots.role_for(None, True) == "main"


def test_rooms_prefer_jui_config_then_git_then_the_cwd(tmp_path):
    app = tmp_path / "repo" / "apps" / "shop"
    (app / "src").mkdir(parents=True)
    (tmp_path / "repo" / ".git").mkdir()
    assert find_root(str(app / "src")) == (str(tmp_path / "repo"), False)
    (app / "jui.config.json").write_text("{}")
    assert find_root(str(app / "src")) == (str(app), True)
    lone = tmp_path / "lone"
    lone.mkdir()
    assert find_root(str(lone)) == (str(lone), False)
    rooms = Rooms()
    p1 = rooms.project_for(str(app / "src"))
    p2 = rooms.project_for(str(app))
    assert p1["id"] == p2["id"] and p1["jsonui"] is True and p1["name"] == "shop/"
    assert str(tmp_path) not in json.dumps({k: v for k, v in p1.items() if k != "displayRoot"})


def _states(state):
    return {a["id"]: a["state"] for a in state.slices["agents"]}


def test_permission_for_one_of_two_parallel_tools_settles_the_right_one():
    """F1: PermissionRequest has no tool_use_id; "the newest open id" picked
    the wrong one when two calls were open (review, 10-18)."""
    world, state = _world()
    world.apply_hook(_hook("PreToolUse", tool_name="Bash", tool_use_id="A", tool_input={"command": "rm x"}), 1)
    world.apply_hook(_hook("PreToolUse", tool_name="Read", tool_use_id="B", tool_input={"file_path": "/work/shop-app/a"}), 2)
    world.apply_hook(_hook("PermissionRequest", tool_name="Bash", tool_input={"command": "rm x"}), 3)
    world.apply_hook(_hook("PostToolUse", tool_name="Read", tool_use_id="B", tool_input={}), 4)  # A refused: no Post
    world.apply_hook(_hook("PreToolUse", tool_name="Grep", tool_use_id="C", tool_input={"pattern": "x"}), 5)
    world.apply_hook(_hook("PostToolUse", tool_name="Grep", tool_use_id="C", tool_input={}), 6)
    world.publish()
    assert _states(state)["s-aaaa"] == "idle"


def test_a_new_prompt_clears_what_an_interrupted_turn_left_open():
    """F2: Esc — no Post, no Stop — then the next prompt."""
    world, state = _world()
    world.apply_hook(_hook("PreToolUse", tool_name="Bash", tool_use_id="A", tool_input={"command": "sleep 99"}), 1)
    world.apply_hook(_hook("UserPromptSubmit", prompt="next"), 2)
    world.apply_hook(_hook("PreToolUse", tool_name="Read", tool_use_id="B", tool_input={}), 3)
    world.apply_hook(_hook("PostToolUse", tool_name="Read", tool_use_id="B", tool_input={}), 4)
    world.publish()
    assert _states(state)["s-aaaa"] == "idle"


def test_a_subagent_that_never_sends_subagentstop_leaves_after_a_quiet_stop():
    """F3: an interrupted subagent; the main Stop has nothing in the background."""
    world, state = _world()
    world.apply_hook(_hook("SubagentStart", agent_id="sub1", agent_type="Explore"), 1)
    world.apply_hook(_hook("PreToolUse", agent_id="sub1", agent_type="Explore", tool_name="Read", tool_use_id="X", tool_input={}), 2)
    world.apply_hook(_hook("Stop", background_tasks=[]), 3)
    world.tick(3 + 5_000)
    world.publish()
    assert "sub1" not in _states(state)
    # ...but not while background work is running.
    world.apply_hook(_hook("SubagentStart", agent_id="sub2", agent_type="Explore"), 10_000)
    world.apply_hook(_hook("Stop", background_tasks=[{"id": "sub2"}]), 10_001)
    world.tick(20_000)
    world.publish()
    assert "sub2" in _states(state)


def test_idle_prompt_after_a_permission_prompt_idles_the_robot():
    """F4"""
    world, state = _world()
    world.apply_hook(_hook("PreToolUse", tool_name="Write", tool_use_id="w", tool_input={}), 1)
    world.apply_hook(_hook("PermissionRequest", tool_name="Write", tool_input={}), 2)
    world.apply_hook(_hook("Notification", notification_type="idle_prompt", message="waiting"), 3)
    world.publish()
    assert _states(state)["s-aaaa"] == "idle"
    assert state.slices["sessions"][0]["status"] == "idle"


def test_a_notifications_event_carries_its_type_for_the_page():
    """The page rings 入力待ち on idle_prompt (2.3.7, ticket 2026-10-20-jui-viz-notify-waiting-for-input): the event says
    which notification it was; other events carry no such field."""
    world, state = _world()
    world.apply_hook(_hook("Notification", notification_type="idle_prompt", message="Claude is waiting for your input"), 1)
    world.apply_hook(_hook("Stop"), 2)
    world.publish()
    by_kind = {e["kind"]: e for e in state.events}
    assert by_kind["Notification"]["ntype"] == "idle_prompt"
    assert "ntype" not in by_kind["Stop"]



def test_a_busy_session_quiet_for_30_s_is_thinking_then_works_then_stops():
    """10-18 live check: thinking was idle with another act, so the page drew it asleep."""
    from jui_cli.viz.ingest import THINKING_AFTER_MS
    world, state = _world()
    world.apply_hook(_hook("UserPromptSubmit", prompt="go"), 1_000)
    world.tick(1_000 + THINKING_AFTER_MS - 1)
    world.publish()
    assert _states(state)["s-aaaa"] == "idle"                    # not yet
    world.tick(1_000 + THINKING_AFTER_MS)
    world.publish()
    assert _states(state)["s-aaaa"] == "thinking" and _agent(state, "s-aaaa")["act"] == "考え中"
    world.apply_hook(_hook("PreToolUse", tool_name="Bash", tool_use_id="b", tool_input={"command": "npm run build"}), 40_000)
    world.publish()
    assert _states(state)["s-aaaa"] == "command"                 # a tool: thinking gives way to the work
    world.apply_hook(_hook("PostToolUse", tool_name="Bash", tool_use_id="b", tool_input={}), 41_000)
    world.tick(41_000 + THINKING_AFTER_MS)
    world.publish()
    assert _states(state)["s-aaaa"] == "thinking"                # quiet again after the tool
    world.apply_hook(_hook("Stop", background_tasks=[]), 80_000)
    world.publish()
    assert _states(state)["s-aaaa"] == "done"                    # Stop: the turn is done (a moment's cheer) ...
    world.tick(80_000 + 10_000)
    world.publish()
    assert _states(state)["s-aaaa"] == "idle"                    # ... then idle, not thinking
    world.tick(80_000 + 2 * THINKING_AFTER_MS)
    world.publish()
    assert _states(state)["s-aaaa"] == "idle"                    # an idle session does not think


def test_a_hookless_session_thinks_while_the_cli_says_busy_and_stops_when_it_does_not():
    from jui_cli.viz.ingest import THINKING_AFTER_MS
    world, state = _world()
    row = {"sessionId": "s-bbbb", "cwd": "/work/shop-app", "status": "busy"}
    world.apply_agents_list([row], 1_000)
    world.tick(1_000 + THINKING_AFTER_MS)
    world.publish()
    assert _states(state)["s-bbbb"] == "thinking"
    world.apply_agents_list([dict(row, status="idle")], 40_000)
    world.tick(40_001)
    world.publish()
    assert _states(state)["s-bbbb"] == "idle"
