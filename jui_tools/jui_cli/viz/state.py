"""The server's state: named slices, a revision counter, and a ring of events.

A slice is replaced whole when it changes and sent whole to the page (no
patches). ``rev`` grows by one per change; the push loop sends the slices
marked dirty since its last send.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Any

SLICE_NAMES = ("projects", "sessions", "agents", "tasks", "specs", "tests", "perms", "questions", "devices", "server")


def now_ms() -> int:
    return int(time.time() * 1000)


class VizState:
    def __init__(self, events_keep: int = 2000) -> None:
        self.rev = 0
        self.slices: dict[str, Any] = {name: [] for name in SLICE_NAMES}
        self.slices["server"] = {}
        self._dirty: set[str] = set()
        self.events: deque[dict] = deque(maxlen=events_keep)
        self._new_events: list[dict] = []
        self._seq = 0

    def set_slice(self, name: str, value: Any) -> None:
        if name not in self.slices:
            raise KeyError(name)
        if self.slices[name] == value:
            return
        self.slices[name] = value
        self._dirty.add(name)
        self.rev += 1

    def add_event(self, event: dict) -> dict:
        self._seq += 1
        item = dict(event, seq=self._seq)
        item.setdefault("at", now_ms())
        self.events.append(item)
        self._new_events.append(item)
        return item

    @property
    def last_seq(self) -> int:
        return self._seq

    def snapshot(self) -> dict:
        return {"rev": self.rev, "slices": dict(self.slices)}

    def take_changes(self) -> tuple[dict | None, list[dict]]:
        """What to push since the last call: ({rev, changed} or None, new events)."""
        changed = None
        if self._dirty:
            changed = {"rev": self.rev, "changed": {name: self.slices[name] for name in sorted(self._dirty)}}
            self._dirty.clear()
        events, self._new_events = self._new_events, []
        return changed, events

    def recent_events(self, limit: int = 200) -> list[dict]:
        return list(self.events)[-limit:]
