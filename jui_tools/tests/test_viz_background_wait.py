"""Waiting on background work (requester, 10-18): the light stays on while a session's background work runs.

Signals, as lane 4d measured them on a live machine (10-18 14:1x): Stop's background_tasks arrives filled for the
sessions that have background work (4 of 4, no false positive in 20); the work runs in a shell-snapshot shell
under the session's process; the sessions file and `claude agents` report idle all the while.
"""
from __future__ import annotations

from jui_cli.viz import ingest
from jui_cli.viz.ingest import World
from jui_cli.viz.sources import processes
from jui_cli.viz.state import VizState

SID = "s-aaaa"
PID = 4242
SHELL = "/bin/zsh -c source ~/.claude/shell-snapshots/snapshot-zsh-1760000000-abcd.sh && eval 'sleep 60'"


def _world() -> tuple[World, VizState]:
    state = VizState()
    return World(state, tool_input_max=50), state


def _hook(kind, **fields):
    return {"hook_event_name": kind, "session_id": SID, "cwd": "/work/shop-app", **fields}


def _main(world):
    return world.agents[SID]


def _lit(world) -> bool:
    return _main(world)["state"] == "background"


def _start(world, pid=PID):
    world.apply_hook(_hook("UserPromptSubmit", prompt="テストを流して"), 1_000)
    if pid is not None:
        world.apply_agents_list([{"sessionId": SID, "cwd": "/work/shop-app", "status": "busy", "pid": pid}], 1_100)
    world.apply_hook(_hook("Stop", background_tasks=[{"id": "bash_1", "type": "bash"}]), 2_000)


def _ps(*shells, pid=PID, mcp=True):
    rows = [(1, 0, "launchd"), (PID - 1, 1, "zsh"), (pid, PID - 1, "claude")]
    if mcp:
        rows.append((pid + 1, pid, "python3 -m jui_cli.mcp"))
    for i, cmd in enumerate(shells):
        rows.append((pid + 10 + i, pid, cmd))
        rows.append((pid + 20 + i, pid + 10 + i, "xcodebuild test"))
    return rows


def test_a_stop_with_background_work_stays_lit_past_the_done_timer_and_an_idle_status_row():
    world, _ = _world()
    _start(world)
    assert _lit(world)
    world.tick(2_000 + ingest.DONE_TO_IDLE_MS + 1)            # the done → idle timer of an ordinary Stop
    world.apply_agents_list([{"sessionId": SID, "cwd": "/work/shop-app", "status": "idle", "pid": PID}], 6_000)
    world.tick(6_000 + ingest.THINKING_AFTER_MS + 1)
    world.check_background(_ps(SHELL), 40_000)                 # the shell still runs
    assert _lit(world)


def test_the_last_background_shell_gone_turns_the_light_off():
    world, _ = _world()
    _start(world)
    world.check_background(_ps(SHELL), 10_000)
    assert _lit(world)
    world.check_background(_ps(), 15_000)                      # the MCP server alone is left under the session
    assert _main(world)["state"] == "idle" and "background" not in world.sessions[SID]


def test_the_session_process_gone_turns_the_light_off():
    world, _ = _world()
    _start(world)
    world.check_background(_ps(SHELL, pid=PID + 500), 10_000)   # no process with the session's pid
    assert not _lit(world)


def test_a_stop_without_background_work_turns_the_light_off():
    world, _ = _world()
    _start(world)
    world.apply_hook(_hook("UserPromptSubmit", prompt="次"), 5_000)
    world.apply_hook(_hook("Stop", background_tasks=[]), 6_000)
    world.tick(6_000 + ingest.DONE_TO_IDLE_MS + 1)
    assert _main(world)["state"] == "idle" and "background" not in world.sessions[SID]


def test_session_end_turns_the_light_off():
    world, _ = _world()
    _start(world)
    world.apply_hook(_hook("SessionEnd", reason="exit"), 5_000)
    assert "background" not in world.sessions[SID]


def test_without_a_pid_the_light_goes_off_at_the_cap_and_not_before():
    world, _ = _world()
    _start(world, pid=None)
    world.tick(2_000 + ingest.BACKGROUND_CAP_MS - 1)
    assert _lit(world)
    world.tick(2_000 + ingest.BACKGROUND_CAP_MS)
    assert not _lit(world)


def test_a_watched_session_is_not_capped_but_one_whose_ps_went_quiet_is():
    world, _ = _world()
    _start(world)
    at = 2_000 + ingest.BACKGROUND_CAP_MS + 10_000
    world.check_background(_ps(SHELL), at - 5_000)            # watched a moment ago: the cap does not apply
    world.tick(at)
    assert _lit(world)
    world.tick(at + ingest.BACKGROUND_UNWATCHED_MS + 1)         # ps has not answered since: the cap applies
    assert not _lit(world)


def test_a_subagent_still_at_work_keeps_it_lit_without_a_shell():
    world, _ = _world()
    world.apply_hook(_hook("UserPromptSubmit", prompt="調べて"), 1_000)
    world.apply_agents_list([{"sessionId": SID, "cwd": "/work/shop-app", "status": "busy", "pid": PID}], 1_100)
    world.apply_hook(_hook("SubagentStart", agent_id="ag1", agent_type="Explore"), 1_200)
    world.apply_hook(_hook("Stop", background_tasks=[{"id": "ag1", "type": "agent"}]), 2_000)
    world.check_background(_ps(), 10_000)
    assert _lit(world)
    world.apply_hook(_hook("SubagentStop", agent_id="ag1", agent_type="Explore"), 11_000)
    world.check_background(_ps(), 15_000)
    assert not _lit(world)


def test_background_shells_counts_shell_snapshot_shells_at_any_depth_only():
    rows = [(10, 1, "claude"), (11, 10, "python3 mcp"), (12, 10, SHELL), (13, 12, "sleep 60"),
            (14, 13, SHELL.replace("sleep 60", "nested")), (20, 1, SHELL)]   # pid 20 is another session's
    assert processes.background_shells(rows, 10) == 2
    assert processes.background_shells(rows, 11) == 0
    assert processes.background_shells(rows, 99) is None


def _turn(world):
    return next(t for t in world.tasks.tasks.values() if t["sessionId"] == SID and t.get("source") == "turn")


def test_when_the_light_goes_off_the_turn_card_is_done_too():
    """The lamp and the card agree: the work ending (ps), the cap or SessionEnd closes the turn left working."""
    for end in ("ps", "cap", "end"):
        world, _ = _world()
        _start(world, pid=None if end == "cap" else PID)
        assert _turn(world)["status"] == "in_progress" and _turn(world).get("background") is True
        if end == "ps":
            world.check_background(_ps(SHELL), 10_000)
            world.check_background(_ps(), 15_000)
        elif end == "cap":
            world.tick(2_000 + ingest.BACKGROUND_CAP_MS)
        else:
            world.apply_hook(_hook("SessionEnd", reason="exit"), 5_000)
        card = _turn(world)
        assert (end, card["status"], "background" in card, "background" in world.sessions[SID]) == (end, "completed", False, False)
