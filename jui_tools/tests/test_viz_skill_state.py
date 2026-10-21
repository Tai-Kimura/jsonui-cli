"""A skill in use, as the server sees it (ticket 2026-10-21-jui-viz-skill-spirit): the robot that runs it carries
``skill`` {name, since[, useId, forked]} from Claude's Skill call until it ends.

- inline: the turn's Stop (or StopFailure), the next prompt, or the next skill;
- forked: the skill moves to the subagent that starts within SKILL_FORK_MS of the call, and ends with the call's result
  (status "forked") or the subagent's stop;
- never longer than SKILL_MAX_MS (no hook says a skill is over).
The shapes are the transcripts' of 10-21 (the call's input {skill, args}; a forked result {status: "forked", …}).
"""
from __future__ import annotations

import pytest

from jui_cli.viz import ingest as I
from jui_cli.viz.ingest import World
from jui_cli.viz.state import VizState

SID = "s-aaaa"


def _world() -> tuple[World, VizState]:
    state = VizState()
    return World(state, tool_input_max=50), state


def _hook(kind, at, sid=SID, **fields):
    return {"hook_event_name": kind, "session_id": sid, "cwd": "/work/shop-app", **fields}


def _skill_call(world, at, name="code-review", use="t1"):
    world.apply_hook(_hook("PreToolUse", at, tool_name="Skill", tool_input={"skill": name, "args": ""},
                           tool_use_id=use), at)


def _skills(world, state, at=None) -> dict:
    if at is not None:
        world.tick(at)
    world.publish()
    return {a["id"]: a["skill"] for a in state.slices["agents"] if a.get("skill")}


def test_an_inline_skill_is_held_by_the_main_robot_until_its_turn_stops():
    world, state = _world()
    world.apply_hook(_hook("UserPromptSubmit", 0, prompt="review this"), 0)
    _skill_call(world, 1000)
    got = _skills(world, state)
    assert got == {SID: {"name": "code-review", "since": 1000, "useId": "t1"}}
    # the inline result comes at once ("Launching skill: …"): the skill goes on
    world.apply_hook(_hook("PostToolUse", 1100, tool_name="Skill", tool_input={"skill": "code-review"}, tool_use_id="t1",
                           tool_response={"success": True, "commandName": "code-review"}), 1100)
    world.apply_hook(_hook("PreToolUse", 2000, tool_name="Read", tool_input={"file_path": "/work/shop-app/a.py"},
                           tool_use_id="t2"), 2000)
    assert _skills(world, state) == {SID: {"name": "code-review", "since": 1000, "useId": "t1"}}
    world.apply_hook(_hook("Stop", 9000), 9000)
    assert _skills(world, state) == {}


@pytest.mark.parametrize("end", ["UserPromptSubmit", "StopFailure", "next skill"])
def test_an_inline_skill_ends_with_the_next_prompt_a_failed_stop_or_the_next_skill(end):
    world, state = _world()
    _skill_call(world, 1000)
    if end == "next skill":
        _skill_call(world, 5000, name="claude-api", use="t9")
        assert _skills(world, state) == {SID: {"name": "claude-api", "since": 5000, "useId": "t9"}}
        return
    world.apply_hook(_hook(end, 5000, prompt="next"), 5000)
    assert _skills(world, state) == {}


def test_a_forked_skill_moves_to_its_subagent_and_ends_with_the_forked_result():
    world, state = _world()
    _skill_call(world, 1000)
    world.apply_hook(_hook("SubagentStart", 3000, agent_id="ag1", agent_type="general-purpose"), 3000)
    got = _skills(world, state)
    assert got == {"ag1": {"name": "code-review", "since": 1000, "useId": "t1", "forked": True}}
    world.apply_hook(_hook("PostToolUse", 150_000, tool_name="Skill", tool_input={"skill": "code-review"}, tool_use_id="t1",
                           tool_response={"status": "forked", "agentId": "ag1", "result": "…"}), 150_000)
    assert _skills(world, state) == {}


def test_a_subagent_started_later_or_by_another_session_does_not_take_the_skill():
    world, state = _world()
    _skill_call(world, 1000)
    world.apply_hook(_hook("SubagentStart", 1000 + I.SKILL_FORK_MS + 1, agent_id="late", agent_type="Explore"), 7000)
    world.apply_hook(_hook("SubagentStart", 2000, sid="s-bbbb", agent_id="other", agent_type="Explore"), 2000)
    assert set(_skills(world, state)) == {SID}


def test_a_forked_skill_s_subagent_stopping_ends_it():
    world, state = _world()
    _skill_call(world, 1000)
    world.apply_hook(_hook("SubagentStart", 2000, agent_id="ag1", agent_type="general-purpose"), 2000)
    world.apply_hook(_hook("SubagentStop", 90_000, agent_id="ag1", agent_type="general-purpose"), 90_000)
    assert _skills(world, state) == {}


def test_a_skill_whose_end_never_came_is_over_after_thirty_minutes():
    world, state = _world()
    _skill_call(world, 1000)
    assert _skills(world, state, at=1000 + I.SKILL_MAX_MS - 1)
    assert _skills(world, state, at=1000 + I.SKILL_MAX_MS) == {}


@pytest.mark.parametrize("tool_input", [{}, {"skill": ""}, {"skill": 3}, {"skill": "a b"}, {"skill": "x" * 129},
                                        {"name": "code-review"}])
def test_a_skill_call_without_a_skill_name_is_no_skill(tool_input):
    world, state = _world()
    world.apply_hook(_hook("PreToolUse", 1000, tool_name="Skill", tool_input=tool_input, tool_use_id="t1"), 1000)
    assert _skills(world, state) == {}


@pytest.mark.parametrize("response, forked", [({"status": "forked"}, True), ({"success": True}, False),
                                              ('Skill "code-review" completed (forked execution).', True),
                                              ("Launching skill: code-review", False), (None, False)])
def test_what_says_a_skill_ran_in_a_subagent(response, forked):
    assert I._skill_forked(response) is forked
