"""Heavy work (requester, 10-18): output tokens over two minutes, a long tool call, three subagents.

Tokens come from the transcript's assistant records (message.usage.output_tokens, a message written twice counts
once); only what is added after the server first sees the file is read; unreadable or huge lines are skipped.
"""
from __future__ import annotations

import json

from jui_cli.viz.ingest import HEAVY_TOOL_MS, World
from jui_cli.viz.sources import transcripts
from jui_cli.viz.state import VizState

SID = "0b1c2d3e-4f50-4617-8899-aabbccddeeff"
T = 1_792_300_000_000                                     # epoch ms the records are written at


def _setup(tmp_path, past=()):
    projects = tmp_path / "projects"
    d = projects / transcripts.project_dir_name("/work/shop")
    d.mkdir(parents=True)
    f = d / f"{SID}.jsonl"
    f.write_text("".join(json.dumps(x) + "\n" for x in past))
    world = World(VizState(), session_start=transcripts.session_start(projects))
    world.transcript_path = transcripts.transcript_path(projects)
    world.apply_agents_list([{"sessionId": SID, "cwd": "/work/shop", "status": "busy"}], T)
    world.poll_usage(T)                                    # first sight: from the end
    return world, f


def _assistant(mid, tokens, at=T):
    iso = __import__("datetime").datetime.fromtimestamp(at / 1000, __import__("datetime").timezone.utc).isoformat()
    return {"type": "assistant", "timestamp": iso, "message": {"id": mid, "usage": {"input_tokens": 9, "output_tokens": tokens}}}


def _append(f, *recs, raw=b""):
    with open(f, "ab") as h:
        h.write(raw)
        for r in recs:
            h.write((json.dumps(r) + "\n").encode())


def _heavy(world, at):
    world.poll_usage(at)
    world.tick(at)
    return world.sessions[SID].get("heavy", [])


def test_tokens_heavy_from_2000_a_minute_over_two_minutes(tmp_path):
    world, f = _setup(tmp_path)
    _append(f, _assistant("m1", 2000), _assistant("m2", 1999))
    assert _heavy(world, T + 1_000) == []                  # 3,999 in two minutes: 1,999.5 a minute
    _append(f, _assistant("m3", 1))
    assert _heavy(world, T + 2_000) == ["tokens"]          # 4,000: 2,000 a minute
    assert world.sessions[SID]["heavyInfo"] == {"tokensPerMin": 2000, "toolSec": 0, "subagents": 0}   # what the card says
    assert _heavy(world, T + 120_001) == []                # they left the window


def test_a_message_written_twice_counts_once(tmp_path):
    world, f = _setup(tmp_path)
    _append(f, _assistant("m1", 3000), _assistant("m1", 3000))
    assert _heavy(world, T + 1_000) == []                  # 3,000, not 6,000
    _append(f, _assistant("m1", 4000))                     # the same message, more tokens: the larger counts
    assert _heavy(world, T + 2_000) == ["tokens"]


def test_the_past_is_never_read(tmp_path):
    world, f = _setup(tmp_path, past=[_assistant(f"old{i}", 5000) for i in range(5)])
    assert _heavy(world, T + 1_000) == []


def test_unreadable_and_huge_lines_are_skipped(tmp_path):
    world, f = _setup(tmp_path)
    huge = b'{"type":"user","message":"' + b"x" * (transcripts.LINE_MAX + 10) + b'"}\n'
    _append(f, raw=b"not json\n[1,2]\n" + huge)
    _append(f, {"type": "assistant", "message": {"id": "m0"}}, _assistant("m1", 4000))
    got = {"bytes": 1, "bad": 0, "assistant": 0, "usage": 0}
    total = dict.fromkeys(got, 0)
    while got["bytes"]:                                    # a line over READ_MAX takes more than one read
        got = world.poll_usage(T + 1_000)
        for k in total:
            total[k] += got[k]
    world.tick(T + 1_000)
    assert world.sessions[SID]["heavy"] == ["tokens"] and total["bad"] == 1 and total["assistant"] == 2 and total["usage"] == 1


def test_a_tool_running_for_60_s(tmp_path):
    world, _ = _setup(tmp_path)
    hook = {"hook_event_name": "PreToolUse", "session_id": SID, "cwd": "/work/shop", "tool_name": "Bash", "tool_use_id": "b1", "tool_input": {"command": "make"}}
    world.apply_hook(hook, T)
    assert _heavy(world, T + HEAVY_TOOL_MS - 1) == []
    assert _heavy(world, T + HEAVY_TOOL_MS) == ["tool"]
    assert world.sessions[SID]["heavyInfo"]["toolSec"] == 60
    world.apply_hook(dict(hook, hook_event_name="PostToolUse"), T + HEAVY_TOOL_MS + 1)
    assert _heavy(world, T + HEAVY_TOOL_MS + 2) == []


def test_three_subagents_not_two(tmp_path):
    world, _ = _setup(tmp_path)
    for i in range(2):
        world.apply_hook({"hook_event_name": "SubagentStart", "session_id": SID, "cwd": "/work/shop", "agent_id": f"s{i}", "agent_type": "Explore"}, T + i)
    assert _heavy(world, T + 10) == []
    world.apply_hook({"hook_event_name": "SubagentStart", "session_id": SID, "cwd": "/work/shop", "agent_id": "s2", "agent_type": "Explore"}, T + 11)
    assert _heavy(world, T + 12) == ["subagents"]
