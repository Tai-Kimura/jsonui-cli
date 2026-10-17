"""--record then --replay rebuilds the same final state (jui_cli/viz/recorder.py)."""
from __future__ import annotations

import asyncio
import json
import stat
from pathlib import Path

from jui_cli.viz import recorder
from jui_cli.viz.ingest import World
from jui_cli.viz.state import VizState

PROBE = sorted((Path(__file__).parent / "fixtures" / "viz" / "probe").glob("*.json"))


def _live(path: Path) -> dict:
    state = VizState()
    world = World(state)
    rec = recorder.Recorder(path)
    for i, sample in enumerate(PROBE):
        at = 1_000_000 + i * 700
        body = json.loads(sample.read_text())
        rec.write(at, body)
        world.apply_hook(body, at)
        world.tick(at)
        world.publish()
    rec.close()
    return {k: state.slices[k] for k in ("projects", "sessions", "agents")}


def test_replay_of_a_recording_reaches_the_same_final_state(tmp_path):
    path = tmp_path / "rec.jsonl"
    live = _live(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    state = VizState()
    world = World(state)

    def apply(body, t):
        world.apply_hook(body, t)
        world.tick(t)
        world.publish()

    count = asyncio.run(recorder.replay(path, apply, speed=1000))
    assert count == len(PROBE) == 22
    assert {k: state.slices[k] for k in ("projects", "sessions", "agents")} == live
    assert [e["kind"] for e in state.events][:3] == ["SessionStart", "UserPromptSubmit", "PreToolUse"]


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
