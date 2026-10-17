"""--record FILE: every accepted hook body as one JSONL line ``{"t": ms, "body": {...}}``.
--replay FILE: feed those lines back with their original spacing (``speed`` times faster).

A recording holds tool input — file contents, commands, prompts — so serve
warns when it starts one, and the file is created 0600.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Callable, Iterator

WARNING = "記録を取ります。ツールの入力（ファイルの中身やコマンド）とプロンプトが含まれます。確認が終わったら消してください"


class Recorder:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        self._file = os.fdopen(fd, "a", encoding="utf-8")

    def write(self, at: int, body: dict) -> None:
        self._file.write(json.dumps({"t": at, "body": body}, ensure_ascii=False) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()


def read_recording(path: Path) -> Iterator[tuple[int, dict]]:
    """(t, body) per valid line; malformed lines are skipped."""
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict) and isinstance(item.get("t"), int) and isinstance(item.get("body"), dict):
                yield item["t"], item["body"]


TICK_MS = 500
TAIL_MS = 70_000
MAX_GAP_SEC = 10.0


async def replay(path: Path, apply: Callable[[dict, int], None], speed: float = 1.0,
                 tick: Callable[[int], None] | None = None) -> int:
    """Apply each recorded body at its recorded time (``t``) on a virtual clock.

    The live server ticks every 500 ms of wall time, so timers (a subagent
    leaving 5 s after SubagentStop, done -> idle, an ended session's 60 s)
    fire between events and after the last one. A replay that ticked only at
    event times left those timers unfired and ended in a different state
    (independent review, 10-18). So ``tick`` is called every TICK_MS of
    virtual time between events and for TAIL_MS after the last one. Real
    sleeping is the gap / speed, capped at MAX_GAP_SEC per gap.
    """
    count = 0
    previous: int | None = None

    async def advance(start: int, end: int) -> None:
        span = end - start
        if span <= 0:
            return
        steps = max(1, -(-span // TICK_MS))
        pause = (min(span / 1000 / speed, MAX_GAP_SEC) / steps) if speed > 0 else 0
        v = start
        for _ in range(steps):
            v = min(v + TICK_MS, end)
            if pause:
                await asyncio.sleep(pause)
            if tick is not None and v < end:
                tick(v)

    for t, body in read_recording(path):
        if previous is not None and t > previous:
            await advance(previous, t)
        previous = max(t, previous or t)
        apply(body, t)
        if tick is not None:
            tick(t)
        count += 1
    if previous is not None and tick is not None:
        await advance(previous, previous + TAIL_MS + 1)
        tick(previous + TAIL_MS)
    return count
