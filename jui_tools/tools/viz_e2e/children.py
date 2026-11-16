"""The processes a suite started, and stopping the ones it left (common.suite_guard). Chosen by id only — this
process's own children born since a moment, and the process group each heads when started with a session of its
own — never by a name or an argument (a name once matched another lane's watcher's sleep, 10-22). Imported by
common.py and by pytest (no Playwright here)."""
from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time


def _rows() -> list[tuple[int, int, int, str]]:
    """(pid, ppid, pgid, stat) of every process; [] when ps cannot be run."""
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,pgid=,stat="], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4 and all(p.isdigit() for p in parts[:3]):
            rows.append((int(parts[0]), int(parts[1]), int(parts[2]), parts[3]))
    return rows


def children() -> set[int]:
    """This process's own children now, a zombie too (one that ended and is not reaped yet): their pids."""
    me = os.getpid()
    return {pid for pid, ppid, _g, _s in _rows() if ppid == me}


def _alive(pids: set[int], groups: set[int]) -> set[int]:
    """Of ``pids`` and of the members of ``groups`` (a group a child heads: its pid is the group's id), the ones
    still running (a zombie is not)."""
    return {pid for pid, _p, pgid, stat in _rows() if not stat.startswith("Z") and (pid in pids or pgid in groups)}


def stop_children_since(before: set[int], wait_s: float = 10.0) -> list[int]:
    """Stop the children born since ``before`` that still run, and every process in a group one of them heads (a
    serve or stand-in started with start_new_session, and what it started — still there when it has gone and they
    have the init process as their parent): INT first, KILL after ``wait_s``; the children reaped. Returns the pids
    stopped."""
    me, me_group = os.getpid(), os.getpgid(0)
    rows = _rows()
    born = {pid for pid, ppid, _g, _s in rows if ppid == me} - set(before)
    if not born:
        return []
    # a child that heads a group of its own (start_new_session): the group's id is its pid, read from ps — a zombie
    # child too, whose group may still hold what it started (now the init process's)
    groups = {pid for pid, _p, pgid, _s in rows if pid in born and pgid == pid and pid != me_group}
    targets = _alive(born, groups)

    def send(sig):
        for g in groups:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(g, sig)
        for pid in born - groups:
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, sig)
    send(signal.SIGINT)
    end = time.monotonic() + wait_s
    while time.monotonic() < end and _alive(born, groups):
        time.sleep(0.2)
    if _alive(born, groups):
        send(signal.SIGKILL)
    left, end = set(born), time.monotonic() + 2.0   # reap: no zombie left (a Popen that waits later gets ECHILD)
    while left and time.monotonic() < end:
        for pid in list(left):
            try:
                if os.waitpid(pid, os.WNOHANG)[0] == pid:
                    left.discard(pid)
            except ChildProcessError:   # reaped already (its Popen waited)
                left.discard(pid)
        if left:
            time.sleep(0.05)
    return sorted(targets)
