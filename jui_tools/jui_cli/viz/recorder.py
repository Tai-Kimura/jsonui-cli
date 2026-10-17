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


async def replay(path: Path, apply: Callable[[dict, int], None], speed: float = 1.0) -> int:
    """Apply each recorded body at its recorded time (``t``), sleeping the gaps / speed.

    The recorded time is passed on as the event time, so the state a replay
    builds does not depend on how fast it ran.
    """
    count = 0
    previous: int | None = None
    for t, body in read_recording(path):
        if previous is not None and t > previous and speed > 0:
            await asyncio.sleep(min((t - previous) / 1000 / speed, 10))
        previous = t
        apply(body, t)
        count += 1
    return count
