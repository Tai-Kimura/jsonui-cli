"""When a session really started: the time of the first record in its transcript.

``sessions[].startedAt`` is when the server first saw a session, so every session already running when
``jui viz serve`` started had the server's start time (10-18 live check: 26 sessions, one value). The
robot's tiredness after 8 hours needs the session's own start, so it comes from
``~/.claude/projects/<cwd with every non-alphanumeric character as '-'>/<session id>.jsonl`` (or the
hook's ``transcript_path``): the first record that carries a ``timestamp``. Only the first
``HEAD_BYTES`` are read, only regular ``.jsonl`` files under the projects folder, never through a
symlink. A session whose transcript cannot be read gets no start time — the page does not guess.
"""
from __future__ import annotations

import json
import os
import re
import stat
from datetime import datetime
from pathlib import Path
from typing import Callable

HEAD_BYTES = 65_536


def project_dir_name(cwd: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", cwd)


def candidates(projects: Path, session_id: str, cwd: str | None, given: str | None = None) -> list[Path]:
    """The transcript paths to try: the hook's own (when it is under the projects folder), then cwd's."""
    out = []
    root = projects.resolve()
    if given and given.endswith(".jsonl"):
        p = Path(given).expanduser()
        try:
            if p.parent.resolve().is_relative_to(root):
                out.append(p)
        except OSError:
            pass
    if cwd and cwd.startswith("/") and re.fullmatch(r"[0-9a-fA-F-]{8,}", session_id or ""):
        out.append(projects / project_dir_name(cwd) / f"{session_id}.jsonl")
    return out


def first_timestamp(path: Path) -> int | None:
    """Epoch ms of the first record with a ``timestamp`` in the first HEAD_BYTES of path, or None."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        raw = os.read(fd, HEAD_BYTES)
    except OSError:
        return None
    finally:
        os.close(fd)
    lines = raw.split(b"\n")
    if len(raw) == HEAD_BYTES:
        lines = lines[:-1]                     # the last line may be cut
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        ts = rec.get("timestamp") if isinstance(rec, dict) else None
        if isinstance(ts, str):
            try:
                return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
            except ValueError:
                continue
    return None


def session_start(projects: Path) -> Callable[[str, str | None, str | None], int | None]:
    def start(session_id: str, cwd: str | None, given: str | None = None) -> int | None:
        for path in candidates(projects, session_id, cwd, given):
            ts = first_timestamp(path)
            if ts is not None:
                return ts
        return None
    return start
