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
from concurrent.futures import Future, ThreadPoolExecutor
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

    The stop, the join and the start run on one thread of their own (WORKER), never on the loop's: FSEvents' stop took
    20 to 68 s when a room's worktrees changed, and the loop answered nothing for that long; the server's TERM waited on
    the same stop (ticket 2026-11-12-viz-loop-stalls-on-watcher-stop). One thread, in the order asked, keeps the old
    order: a replaced watcher has let go of its folders before the next one asks for them.
    """

    WORKER = "jui-viz-watchers"

    def __init__(self, folders_of: Callable[[object], list], start: Callable[[object], object | None],
                 started: list | None = None, join_sec: float = 1.0):
        """``folders_of(project)`` gives the folders a watcher of it would watch; ``start(project)`` starts one (an
        observer with stop / join, or None when nothing is there to watch); ``started`` is kept up to date with the
        running observers, from the worker's thread under ``lock``."""
        self._folders_of = folders_of
        self._start = start
        self.started = started if started is not None else []
        self.lock = threading.Lock()
        self._join_sec = join_sec
        self._by_room: dict[str, tuple[Future, list]] = {}
        self._pool: ThreadPoolExecutor | None = None
        self._closed = False

    def watch(self, project) -> bool:
        """Watch the room's folders; True when a watcher is to be started again (the worker does it), False when the
        one it has stands. Never waits for a watcher."""
        folders = self._folders_of(project)
        old = self._by_room.get(project.project_id)
        if old is not None and old[1] == folders and not _failed(old[0]):
            return False
        if self._closed:
            return False
        self._by_room.pop(project.project_id, None)
        if self._pool is None:
            self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=self.WORKER)
        previous = old[0] if old is not None else None
        self._by_room[project.project_id] = (self._pool.submit(self._swap, previous, project), folders)
        return True

    def _swap(self, previous: Future | None, project):
        """On the worker: the room's old watcher stopped and joined, then the new one started."""
        if previous is not None and not _failed(previous):
            self._retire(previous.result())         # done: the one worker ran it before this one
        observer = self._start(project)
        if observer is None:
            return None
        with self.lock:
            closed = self._closed
            if not closed:
                self.started.append(observer)
        if closed:                                  # the server stopped while it started
            _stop(observer, self._join_sec)
        return observer

    def _retire(self, observer) -> None:
        if observer is None:
            return
        with self.lock:
            if observer in self.started:
                self.started.remove(observer)
        _stop(observer, self._join_sec)             # let go of its folders before a new one asks for them

    def settle(self, timeout: float | None = None) -> None:
        """Wait for the worker's jobs asked so far (tests)."""
        if self._pool is not None:
            self._pool.submit(lambda: None).result(timeout)

    def close(self) -> list:
        """No more starts; the jobs not begun are dropped. The running observers are returned for the caller to stop
        (off the loop); one the worker starts after this stops itself."""
        with self.lock:
            self._closed = True
            running, self.started[:] = list(self.started), []
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
        return running


def _failed(job: Future) -> bool:
    return job.done() and (job.cancelled() or job.exception() is not None)


def _stop(observer, join_sec: float) -> None:
    try:
        observer.stop()
        observer.join(timeout=join_sec)
    except Exception as exc:  # noqa: BLE001 — one watcher that fails to stop must not stop the others
        import sys
        print(f"jui viz: stopping a file watcher failed: {type(exc).__name__}: {exc}"[:300], file=sys.stderr, flush=True)


def stop_observers(observers: list, join_sec: float = 2.0) -> None:
    """Stop and join each (the server's way out), on the caller's thread."""
    for observer in observers:
        if observer is not None:
            _stop(observer, join_sec)
