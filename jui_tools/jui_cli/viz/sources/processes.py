"""Processes under a Claude Code session, for "waiting on background work" (requester, 10-18).

Measured on a live machine (lane 4d, 10-18 14:1x): a background Bash runs as a child of the session's
process, ``/bin/zsh -c source ~/.claude/shell-snapshots/snapshot-zsh-….sh …``, with the work (xcodebuild,
gradle, a sleep loop …) under it. The only child that lives as long as the session is the MCP server, which
is not such a shell. So "a shell-snapshot shell is still under the session" means its background work runs.
"""
from __future__ import annotations

import subprocess

SHELL_MARK = "shell-snapshots/snapshot-"


def snapshot(timeout: float = 5.0) -> list[tuple[int, int, str]] | None:
    """(pid, ppid, command) of every process, or None when ps cannot be run."""
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,command="], capture_output=True, text=True,
                             timeout=timeout, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    rows = []
    for line in out.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            rows.append((int(parts[0]), int(parts[1]), parts[2] if len(parts) > 2 else ""))
    return rows


def background_shells(rows: list[tuple[int, int, str]], pid: int) -> int | None:
    """How many shell-snapshot shells run under ``pid`` (any depth); None when ``pid`` itself is gone."""
    if not any(p == pid for p, _, _ in rows):
        return None
    children: dict[int, list[tuple[int, str]]] = {}
    for p, pp, cmd in rows:
        children.setdefault(pp, []).append((p, cmd))
    count, seen, stack = 0, {pid}, [pid]
    while stack:
        for child, cmd in children.get(stack.pop(), []):
            if child in seen:
                continue
            seen.add(child)
            stack.append(child)
            if SHELL_MARK in cmd:
                count += 1
    return count
