"""Is a terminal still attached to this Codex home? Read-only OS evidence, not loaded daemon threads.

Codex's TUI and daemon both hold that home's logs_2.sqlite open. A loaded thread alone is inconclusive because
viz's subscription keeps it loaded after the TUI exits. Match the open-file owners to a fresh process snapshot,
excluding the shared app-server daemon and noninteractive commands. No process is signalled and no DB is changed.
If another TUI is still in the same home, its thread cannot be inferred: keep the robots rather than guess.
Missing lsof/ps, inaccessible files or an unreadable snapshot mean unknown, never proof of an exit.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


def processes() -> dict[int, str] | None:
    try:
        got = subprocess.run(['ps', '-Ao', 'pid=,command='], capture_output=True, text=True, timeout=3)
        if got.returncode:
            return None
        out = {}
        for line in got.stdout.splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2 and parts[0].isdigit():
                out[int(parts[0])] = parts[1]
        return out or None
    except (OSError, subprocess.SubprocessError):
        return None


def owners(path: Path) -> set[int] | None:
    try:
        got = subprocess.run(['lsof', '-t', '--', str(path)], capture_output=True, text=True, timeout=3)
        lines = got.stdout.splitlines()
        if got.returncode or not lines or not all(line.isdigit() for line in lines):
            return None
        return {int(line) for line in lines}
    except (OSError, subprocess.SubprocessError):
        return None


def alive(home: Path, snapshot=processes, opened=owners) -> bool | None:
    path = home / 'logs_2.sqlite'
    try:
        if not path.is_file():
            return None
        pids = opened(path)
        procs = snapshot() if pids is not None else None
        if pids is None or procs is None:
            return None
        for pid in pids:
            command = procs.get(pid, '')
            argv0 = command.split(' ', 1)[0]
            if Path(argv0).name != 'codex':
                continue
            if not re.match(r'^\S+\s+(?:app-server|exec|mcp-server|login|logout|features|completion|sandbox)(?:\s|$)', command):
                return True
        return False
    except OSError:
        return None
