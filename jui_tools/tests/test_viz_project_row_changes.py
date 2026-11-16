"""jui viz: a change to a room's row after it was first published reaches the page (ticket
docs/bugs/2026-10-19-jui-viz-project-row-changes-never-pushed.md). World.publish handed set_slice the rooms' own dicts;
a row changed in place (apply_mock) then compared equal to the slice already published, and nothing was sent."""
from __future__ import annotations

from jui_cli.viz.ingest import World
from jui_cli.viz.state import VizState


def test_a_mock_that_starts_after_the_room_appeared_is_published():
    state = VizState()
    world = World(state)
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/work/mock-app"}, 1)
    world.publish()
    (row,) = state.slices["projects"]
    rev = state.rev
    world.apply_mock(row["id"], {"running": True, "port": 8790})
    world.publish()
    assert state.rev > rev
    assert state.slices["projects"][0]["mock"] == {"running": True, "port": 8790}
    rev = state.rev
    world.apply_mock(row["id"], {"running": False, "port": 8790})
    world.publish()
    assert state.rev > rev and state.slices["projects"][0]["mock"]["running"] is False
