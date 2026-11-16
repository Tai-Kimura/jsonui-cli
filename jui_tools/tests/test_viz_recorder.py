"""--record then --replay rebuilds the same final state (jui_cli/viz/recorder.py)."""
from __future__ import annotations

import asyncio
import json
import stat
from pathlib import Path

from jui_cli.viz import recorder
from jui_cli.viz.ingest import World
from jui_cli.viz.state import VizState

ALL = sorted((Path(__file__).parent / "fixtures" / "viz" / "probe").glob("*.json"))
# Up to Stop, without SessionEnd: the session stays, so the end state is not
# empty, and it depends on the timers (the subagent leaving 5 s after
# SubagentStop, the main robot going done -> idle).
PROBE = [p for p in ALL if not p.name.endswith("SessionEnd.json")]


def _live(path: Path) -> dict:
    """What the server builds live: each body at its time, plus a tick every
    500 ms of wall time (the server's tick_loop), and long enough afterwards
    for every timer to fire. Written without the recorder's own clock, so a
    replay that skips the ticks cannot agree with it by construction."""
    state = VizState()
    world = World(state)
    rec = recorder.Recorder(path)
    times = [1_000_000 + i * 700 for i in range(len(PROBE))]
    clock = times[0]
    for at, sample in zip(times, PROBE):
        while clock + 500 < at:
            clock += 500
            world.tick(clock)
            world.publish()
        body = json.loads(sample.read_text())
        rec.write(at, body)
        world.apply_hook(body, at)
        world.publish()
    rec.close()
    end = times[-1] + 70_000
    while clock < end:
        clock += 500
        world.tick(clock)
        world.publish()
    return {k: state.slices[k] for k in ("projects", "sessions", "agents")}


def test_replay_of_a_recording_reaches_the_same_final_state(tmp_path):
    path = tmp_path / "rec.jsonl"
    live = _live(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    # Timers resolved: one session, its main robot idle, the subagent gone.
    assert [s["status"] for s in live["sessions"]] == ["idle"]
    assert [(a["kind"], a["state"]) for a in live["agents"]] == [("main", "idle")]
    state = VizState()
    world = World(state)

    def apply(body, t):
        world.apply_hook(body, t)
        world.publish()

    def tick(t):
        world.tick(t)
        world.publish()

    count = asyncio.run(recorder.replay(path, apply, speed=100_000, tick=tick))
    assert count == len(PROBE) == 21
    assert {k: state.slices[k] for k in ("projects", "sessions", "agents")} == live
    assert [e["kind"] for e in state.events][:3] == ["SessionStart", "UserPromptSubmit", "PreToolUse"]


def test_a_replay_that_only_ticks_at_event_times_does_not_match(tmp_path):
    """The control: the shape the first replay had (no ticks between or after
    events) ends with the subagent still there."""
    path = tmp_path / "rec.jsonl"
    live = _live(path)
    state = VizState()
    world = World(state)

    def apply(body, t):
        world.apply_hook(body, t)
        world.tick(t)
        world.publish()

    asyncio.run(recorder.replay(path, apply, speed=100_000))
    assert {k: state.slices[k] for k in ("projects", "sessions", "agents")} != live


def test_replay_skips_malformed_lines_and_keeps_the_gaps(tmp_path):
    path = tmp_path / "rec.jsonl"
    path.write_text(
        json.dumps({"t": 0, "body": {"a": 1}}) + "\nnot json\n" + json.dumps({"t": "x", "body": {}}) + "\n"
        + json.dumps({"t": 400, "body": {"a": 2}}) + "\n"
    )
    seen = []
    loop_time = []

    async def main():
        start = asyncio.get_running_loop().time()
        await recorder.replay(path, lambda b, t: (seen.append((t, b)), loop_time.append(asyncio.get_running_loop().time() - start)), speed=2)

    asyncio.run(main())
    assert seen == [(0, {"a": 1}), (400, {"a": 2})]
    assert 0.15 <= loop_time[1] - loop_time[0] < 1.0  # 400 ms at 2x is ~200 ms
