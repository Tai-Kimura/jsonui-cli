"""The rooms' file changes handed to the loop in batches (ticket 2026-11-06-viz-e2e-full-run-red-under-load, the ENOSPC
night of 2026-11-09).

The watcher's thread gives one path per file event. Each used to be one call on the loop (file_changed and a publish),
so a storm of changes (a build writing thousands of .json files under a watched folder) was thousands of publishes
queued behind each other. Here the paths are kept, each once per room and in the order they first came, and the loop
is asked once for all of them: ``apply(project_id, path)`` for each, then ``done()`` once. Changes that come while a
batch is being applied wait for the next one.
"""
from __future__ import annotations

import threading
from typing import Callable


class ChangeBatch:
    def __init__(self, call_soon: Callable[[Callable[[], None]], object], apply: Callable[[str, str], None],
                 done: Callable[[], None]):
        """``call_soon(fn)`` runs fn on the loop (loop.call_soon_threadsafe); ``apply(project_id, path)`` takes one
        change there and ``done()`` follows a batch."""
        self._call_soon = call_soon
        self._apply = apply
        self._done = done
        self._lock = threading.Lock()
        self._pending: dict[str, dict[str, None]] = {}
        self._asked = False

    def add(self, project_id: str, path: str) -> None:
        """A change, from any thread."""
        with self._lock:
            self._pending.setdefault(project_id, {})[path] = None
            if self._asked:
                return
            self._asked = True
        self._call_soon(self.flush)

    def flush(self) -> int:
        """On the loop: the changes kept so far, applied; how many."""
        with self._lock:
            batch, self._pending, self._asked = self._pending, {}, False
        n = 0
        for project_id, paths in batch.items():
            for path in paths:
                self._apply(project_id, path)
                n += 1
        if n:
            self._done()
        return n


class Watchers:
    """The rooms' file watchers, one per room, started again only when the folders it watches changed.

    The room's apps are read again often (a worktree shown or gone, the session list flapping), and each time a new
    watcher started on the same folders while the old one still held them: watchdog's FSEvents emitter said "Cannot
    add watch ... it is already scheduled", and changes were told again (the ENOSPC night's log, 2026-11-09). Now the
    same folders keep their watcher, and a watcher replaced is stopped and joined before the new one starts.
    """

    def __init__(self, folders_of: Callable[[object], list], start: Callable[[object], object | None],
                 started: list | None = None, join_sec: float = 1.0):
        """``folders_of(project)`` gives the folders a watcher of it would watch; ``start(project)`` starts one (an
        observer with stop / join, or None when nothing is there to watch); ``started`` is kept up to date with the
        running observers (the server stops them on its way out)."""
        self._folders_of = folders_of
        self._start = start
        self.started = started if started is not None else []
        self._join_sec = join_sec
        self._by_room: dict[str, tuple[object, list]] = {}

    def watch(self, project) -> bool:
        """Watch the room's folders; True when a watcher was started (or stopped), False when the one it has stands."""
        folders = self._folders_of(project)
        old = self._by_room.get(project.project_id)
        if old is not None and old[1] == folders:
            return False
        self._by_room.pop(project.project_id, None)
        if old is not None:
            old[0].stop()
            old[0].join(timeout=self._join_sec)   # let go of its folders before a new one asks for them
            if old[0] in self.started:
                self.started.remove(old[0])
        observer = self._start(project)
        if observer is not None:
            self.started.append(observer)
            self._by_room[project.project_id] = (observer, folders)
        return True
