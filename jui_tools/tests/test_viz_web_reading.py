"""Reading the web: WebFetch and WebSearch open a dictionary on the desk (ticket 2026-10-20-jui-viz-webfetch-dictionary).

The state stays 'reading' (the lamp, the tag's 読む and the card as they were); the robot carries the sub-kind
readKind = "web" while the tool runs, and loses it when the tool ends or another tool starts. The other reading tools
(Read, Grep, Glob, LS, ToolSearch, jui-tools' read_/lookup_/list_/search_/get_) carry no sub-kind: the book in the hands.
"""
from __future__ import annotations

import pytest

from jui_cli.viz import robots
from jui_cli.viz.ingest import World
from jui_cli.viz.state import VizState

S, CWD = "s-web", "/work/web"
WEB = {"WebFetch": {"url": "https://example.com/a", "prompt": "要約して"}, "WebSearch": {"query": "three.js dispose"}}
PLAIN = {"Read": {"file_path": f"{CWD}/a.txt"}, "Grep": {"pattern": "x"}, "Glob": {"pattern": "*.py"}, "LS": {"path": CWD},
         "ToolSearch": {"query": "x"}, "mcp__jui-tools__read_spec_file": {"path": f"{CWD}/a.spec.json"}}
Q = {"questions": [{"question": "どれ?", "header": "選択", "options": [{"label": "A"}, {"label": "B"}], "multiSelect": False}]}


def _world() -> World:
    w = World(VizState(100))
    w.apply_hook({"hook_event_name": "SessionStart", "session_id": S, "cwd": CWD, "source": "startup"}, 1)
    w.apply_hook({"hook_event_name": "UserPromptSubmit", "session_id": S, "cwd": CWD, "prompt": "調べて"}, 2)
    return w


def _h(w: World, at: int, **payload) -> None:
    w.apply_hook({"session_id": S, "cwd": CWD, **payload}, at)


def _robot(w: World) -> dict:
    w.publish()
    return next(a for a in w.state.snapshot()["slices"]["agents"] if a["sessionId"] == S)


def test_the_web_reading_tools_are_webfetch_and_websearch_only():
    assert robots.WEB_READING_TOOLS == {"WebFetch", "WebSearch"}
    assert robots.WEB_READING_TOOLS <= robots.READING_TOOLS   # still the state 'reading'
    for tool in WEB:
        assert robots.read_kind(tool) == "web"
    for tool in [*PLAIN, "Edit", "Bash", "Agent"]:
        assert robots.read_kind(tool) is None


@pytest.mark.parametrize("tool", sorted(WEB))
def test_pre_tool_use_reads_the_web_and_post_tool_use_puts_it_back(tool):
    w = _world()
    _h(w, 10, hook_event_name="PreToolUse", tool_name=tool, tool_input=WEB[tool], tool_use_id="w1")
    a = _robot(w)
    assert (a["state"], a.get("readKind")) == ("reading", "web"), a
    _h(w, 20, hook_event_name="PostToolUse", tool_name=tool, tool_input=WEB[tool], tool_use_id="w1", tool_response="ok")
    a = _robot(w)
    assert a["state"] == "idle" and "readKind" not in a, a


@pytest.mark.parametrize("tool", sorted(WEB))
def test_a_failed_web_tool_puts_it_back_too(tool):
    w = _world()
    _h(w, 10, hook_event_name="PreToolUse", tool_name=tool, tool_input=WEB[tool], tool_use_id="w1")
    _h(w, 20, hook_event_name="PostToolUseFailure", tool_name=tool, tool_input=WEB[tool], tool_use_id="w1", error="x")
    assert "readKind" not in _robot(w)


@pytest.mark.parametrize("tool", sorted(PLAIN))
def test_the_other_reading_tools_read_as_before(tool):
    w = _world()
    _h(w, 10, hook_event_name="PreToolUse", tool_name=tool, tool_input=PLAIN[tool], tool_use_id="r1")
    a = _robot(w)
    assert a["state"] == "reading" and "readKind" not in a, a


@pytest.mark.parametrize("tool", sorted(WEB))
def test_the_next_tool_takes_the_dictionary_away(tool):
    w = _world()
    _h(w, 10, hook_event_name="PreToolUse", tool_name=tool, tool_input=WEB[tool], tool_use_id="w1")
    _h(w, 11, hook_event_name="PreToolUse", tool_name="Read", tool_input=PLAIN["Read"], tool_use_id="r1")
    a = _robot(w)
    assert a["state"] == "reading" and "readKind" not in a, a
    _h(w, 12, hook_event_name="PreToolUse", tool_name="Edit", tool_input={"file_path": f"{CWD}/a.py"}, tool_use_id="e1")
    a = _robot(w)
    assert a["state"] == "typing" and "readKind" not in a, a


@pytest.mark.parametrize("tool", sorted(WEB))
def test_back_from_a_question_to_the_web_tool_still_open(tool):
    """A web tool runs, a question waits; the question answered, the robot is back at the web tool: the dictionary."""
    w = _world()
    _h(w, 10, hook_event_name="PreToolUse", tool_name=tool, tool_input=WEB[tool], tool_use_id="w1")
    _h(w, 11, hook_event_name="PreToolUse", tool_name="AskUserQuestion", tool_input=Q, tool_use_id="q1")
    a = _robot(w)
    assert a["state"] == "waiting" and "readKind" not in a, a
    _h(w, 20, hook_event_name="PostToolUse", tool_name="AskUserQuestion", tool_input={**Q, "answers": {"どれ?": "A"}}, tool_use_id="q1")
    a = _robot(w)
    assert (a["state"], a.get("readKind")) == ("reading", "web"), a
