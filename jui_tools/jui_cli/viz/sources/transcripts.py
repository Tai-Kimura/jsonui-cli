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

from ..calls import record_event

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


# ---------------------------------------------------------------- what a session is doing now: its output tokens
# "Heavy" work (requester, 10-18) includes more than 2,000 output tokens a minute over the last two minutes. The
# transcript's assistant records carry message.usage.output_tokens; one message is written twice with the same
# usage (measured 10-18), so a message counts once — by its id, the largest value seen. A transcript can be
# hundreds of MB (251 MB measured) with single lines of several MB: only what was added since the last read is
# read, from where the file ended when it was first seen (the past is never read), at most READ_MAX a read, and a
# line longer than LINE_MAX is skipped to its end. The shape is Claude Code's own: unreadable lines are counted
# (the server shows the source as unreadable), never fatal.
LINE_MAX = 1_048_576
READ_MAX = 524_288


def usage_of(rec) -> tuple[str, int, int | None] | None:
    """(message id, output tokens, epoch ms or None) of an assistant record, else None."""
    if not isinstance(rec, dict) or rec.get("type") != "assistant":
        return None
    msg = rec.get("message")
    usage = msg.get("usage") if isinstance(msg, dict) else None
    mid = msg.get("id") if isinstance(msg, dict) else None
    out = usage.get("output_tokens") if isinstance(usage, dict) else None
    if not isinstance(mid, str) or not isinstance(out, int) or isinstance(out, bool) or out < 0:
        return None
    ts = rec.get("timestamp")
    at = None
    if isinstance(ts, str):
        try:
            at = int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
        except ValueError:
            at = None
    return mid, out, at


def _epoch_ms(ts) -> int | None:
    if not isinstance(ts, str):
        return None
    try:
        return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None


class UsageTail:
    """The new complete lines of one transcript, from the end it had when first seen."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.offset: int | None = None
        self.buf = b""
        self.skipping = False

    def read(self) -> dict:
        """{'usage': [(id, tokens, at)], 'calls': [(kind, sender name, at)], 'bytes': n, 'assistant': n, 'bad': n}
        for what was added. ``calls``: the receiver's records of a cross-session message (calls.record_event)."""
        out = {"usage": [], "calls": [], "bytes": 0, "assistant": 0, "bad": 0}
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError:
            return out
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                return out
            if self.offset is None or st.st_size < self.offset:       # first sight, or a new file in its place
                self.offset, self.buf, self.skipping = st.st_size, b"", False
                return out
            os.lseek(fd, self.offset, os.SEEK_SET)
            chunk = os.read(fd, READ_MAX)
        except OSError:
            return out
        finally:
            os.close(fd)
        self.offset += len(chunk)
        out["bytes"] = len(chunk)
        data = self.buf + chunk
        lines = data.split(b"\n")
        self.buf = lines.pop()                                         # an unfinished line waits for the rest
        if len(self.buf) > LINE_MAX:
            self.buf, self.skipping = b"", True
        for i, line in enumerate(lines):
            if self.skipping:
                self.skipping = False                                  # the end of a skipped line
                continue
            if not line or len(line) > LINE_MAX:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                out["bad"] += 1
                continue
            if isinstance(rec, dict) and rec.get("type") == "assistant":
                out["assistant"] += 1
            u = usage_of(rec)
            if u:
                out["usage"].append(u)
            c = record_event(rec)
            if c:
                out["calls"].append((c[0], c[1], _epoch_ms(rec.get("timestamp"))))
        return out


def transcript_path(projects: Path) -> Callable[[str, str | None, str | None], Path | None]:
    def find(session_id: str, cwd: str | None, given: str | None = None) -> Path | None:
        for path in candidates(projects, session_id, cwd, given):
            try:
                if path.is_file() and not path.is_symlink():
                    return path
            except OSError:
                continue
        return None
    return find
