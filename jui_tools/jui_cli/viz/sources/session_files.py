"""Watch ~/.claude/sessions/<pid>.json for session status and the pid → session id map.

The same folder holds ``<pid>.<hash>.key`` files: peer tokens. They are
excluded by NAME before any read, and never opened. Only ``<digits>.json``
is read — the allow-list is the guard, so a new kind of file there stays
unread too.
"""
from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path
from typing import Callable
from .. import quiet_fs

SESSION_FILE = re.compile(r"^[0-9]+\.json$")  # ASCII digits only (\d matches other scripts)
MAX_BYTES = 256_000


def is_session_file(name: str) -> bool:
    return bool(SESSION_FILE.match(name))


def read_session_file(path: Path) -> dict | None:
    if not is_session_file(path.name):
        return None  # never open anything else in this folder
    # O_NOFOLLOW + a regular-file check: a "<n>.json" that is a symlink (to a
    # .key, say) is never followed.
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_BYTES:
            return None
        raw = os.read(fd, MAX_BYTES + 1)
    except OSError:
        return None
    finally:
        os.close(fd)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def scan(folder: Path) -> list[dict]:
    if not quiet_fs.is_dir(folder):
        return []
    out = []
    for path in sorted(folder.iterdir()):
        data = read_session_file(path)
        if data is not None:
            out.append(data)
    return out


def watch(folder: Path, on_data: Callable[[dict], None]):
    """Start a watchdog observer; returns it (call .stop() and .join()). None if the folder is missing."""
    if not quiet_fs.is_dir(folder):
        return None
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    class Handler(FileSystemEventHandler):
        def _handle(self, raw_path) -> None:
            path = Path(raw_path if isinstance(raw_path, str) else raw_path.decode())
            if not is_session_file(path.name):
                return
            data = read_session_file(path)
            if data is not None:
                on_data(data)

        def on_created(self, event):
            if not event.is_directory:
                self._handle(event.src_path)

        def on_modified(self, event):
            if not event.is_directory:
                self._handle(event.src_path)

        def on_moved(self, event):
            if not event.is_directory:
                self._handle(event.dest_path)

    observer = Observer()
    observer.schedule(Handler(), str(folder), recursive=False)
    observer.daemon = True
    observer.start()
    return observer
