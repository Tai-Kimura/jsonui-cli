"""File watcher that bridges watchdog events into an asyncio.Queue."""
from __future__ import annotations

import asyncio
import fnmatch
from dataclasses import dataclass
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer


@dataclass
class FileChange:
    kind: str  # "modified" | "created" | "deleted"
    path: Path


class _QueueHandler(FileSystemEventHandler):
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue[FileChange],
        ignored: list[str],
    ):
        self._loop = loop
        self._queue = queue
        self._ignored = ignored

    def on_modified(self, event: FileSystemEvent) -> None:
        self._enqueue("modified", event)

    def on_created(self, event: FileSystemEvent) -> None:
        self._enqueue("created", event)

    def on_deleted(self, event: FileSystemEvent) -> None:
        self._enqueue("deleted", event)

    def on_moved(self, event: FileSystemEvent) -> None:
        # Treat as delete + create on the destination
        src = getattr(event, "src_path", None)
        dst = getattr(event, "dest_path", None)
        if src:
            self._emit(FileChange("deleted", Path(src)))
        if dst:
            self._emit(FileChange("created", Path(dst)))

    def _enqueue(self, kind: str, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        self._emit(FileChange(kind, path))

    def _emit(self, change: FileChange) -> None:
        if change.path.suffix.lower() != ".json":
            return
        if self._is_ignored(change.path):
            return
        self._loop.call_soon_threadsafe(self._queue.put_nowait, change)

    def _is_ignored(self, path: Path) -> bool:
        s = str(path)
        return any(fnmatch.fnmatch(s, pattern) for pattern in self._ignored)


class LayoutWatcher:
    """Wraps a ``watchdog.Observer`` to publish file changes onto an
    ``asyncio.Queue`` owned by the caller's event loop.
    """

    def __init__(
        self,
        paths: list[Path],
        ignored: list[str],
        loop: asyncio.AbstractEventLoop,
    ):
        self._paths = paths
        self._ignored = ignored
        self._loop = loop
        self._queue: asyncio.Queue[FileChange] = asyncio.Queue()
        self._observer: Observer | None = None

    @property
    def queue(self) -> asyncio.Queue[FileChange]:
        return self._queue

    def start(self) -> None:
        if self._observer is not None:
            return
        observer = Observer()
        handler = _QueueHandler(self._loop, self._queue, self._ignored)
        for p in self._paths:
            if p.exists():
                observer.schedule(handler, str(p), recursive=True)
        observer.start()
        self._observer = observer

    def stop(self) -> None:
        if self._observer is None:
            return
        self._observer.stop()
        self._observer.join(timeout=2)
        self._observer = None
