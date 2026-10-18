"""A session's real start for the 8-hour tiredness (jui_cli/viz/sources/transcripts.py, World.session_start).

10-18 live check: sessions[].startedAt was when the server first saw a session — one value for all 26.
"""
from __future__ import annotations

import json
import os

from jui_cli.viz.ingest import World
from jui_cli.viz.sources import transcripts
from jui_cli.viz.state import VizState

SID = "0b1c2d3e-4f50-4617-8899-aabbccddeeff"


def _transcript(projects, cwd, lines):
    d = projects / transcripts.project_dir_name(cwd)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{SID}.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    return p


def test_the_first_record_with_a_timestamp_is_the_start(tmp_path):
    projects = tmp_path / "projects"
    p = _transcript(projects, "/work/shop_app", [{"type": "summary"}, {"type": "user", "timestamp": "2026-10-18T00:00:00.000Z"},
                                                   {"type": "assistant", "timestamp": "2026-10-18T09:00:00.000Z"}])
    assert p.parent.name == "-work-shop-app"                       # every non-alphanumeric character is '-'
    assert transcripts.first_timestamp(p) == 1792281600000
    assert transcripts.session_start(projects)(SID, "/work/shop_app") == 1792281600000


def test_no_transcript_no_timestamp_or_a_link_is_no_start(tmp_path):
    projects = tmp_path / "projects"
    start = transcripts.session_start(projects)
    assert start(SID, "/work/none") is None                         # no file
    _transcript(projects, "/work/a", [{"type": "summary"}])
    assert start(SID, "/work/a") is None                            # no record with a time
    real = _transcript(projects, "/work/b", [{"timestamp": "2026-10-18T00:00:00Z"}])
    link = projects / transcripts.project_dir_name("/work/c")
    link.mkdir(parents=True)
    os.symlink(real, link / f"{SID}.jsonl")
    assert start(SID, "/work/c") is None                            # never through a symlink
    assert transcripts.candidates(projects, SID, None, "/etc/passwd.jsonl") == []   # outside the projects folder


def test_the_start_is_the_transcripts_not_the_servers(tmp_path):
    projects = tmp_path / "projects"
    _transcript(projects, "/work/shop", [{"timestamp": "2026-10-17T22:00:00Z"}])
    state = VizState()
    world = World(state, session_start=transcripts.session_start(projects))
    server_saw_it_at = 1792300000000                                # long after the session started
    world.apply_agents_list([{"sessionId": SID, "cwd": "/work/shop", "status": "busy"}], server_saw_it_at)
    world.publish()
    s = state.slices["sessions"][0]
    assert s["since"] == 1792274400000 and s["since"] != s["startedAt"] == server_saw_it_at


def test_a_session_without_a_readable_transcript_has_no_start(tmp_path):
    state = VizState()
    world = World(state, session_start=transcripts.session_start(tmp_path / "projects"))
    world.apply_agents_list([{"sessionId": SID, "cwd": "/work/none", "status": "busy"}], 1_000)
    world.publish()
    assert "since" not in state.slices["sessions"][0]               # not guessed from startedAt
    world2 = World(VizState())                                      # no reader at all (tests, replays)
    world2.apply_agents_list([{"sessionId": SID, "cwd": "/work/none"}], 1_000)
    assert "since" not in world2.sessions[SID]


def test_a_new_sessions_transcript_is_found_when_it_appears(tmp_path):
    projects = tmp_path / "projects"
    state = VizState()
    world = World(state, session_start=transcripts.session_start(projects))
    row = {"sessionId": SID, "cwd": "/work/new", "status": "idle"}
    world.apply_agents_list([row], 1_000)
    assert "since" not in world.sessions[SID]
    _transcript(projects, "/work/new", [{"timestamp": "2026-10-18T00:00:00Z"}])
    world.apply_agents_list([row], 2_000)
    assert world.sessions[SID]["since"] == 1792281600000
