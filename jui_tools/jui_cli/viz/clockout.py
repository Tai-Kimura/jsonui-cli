"""退勤 (clock out): end one terminal session from its robot card (ticket 2026-10-19-jui-viz-clock-out-button).

Measured with the requester (10-19 11:10–11:15, throwaway sessions only): one SIGTERM ends claude in about 1.5 s in
the terminal, the VS Code extension and the desktop app — its children go, SessionEnd fires (reason "other") and
its ~/.claude/sessions/<pid>.json goes. Afterwards the terminal is back at its shell, but the VS Code tab stays with
an error and the desktop app shows no change. The ruling: the button works for terminal sessions only (the
registry's ``entrypoint`` is ``cli``); VS Code and the desktop app are refused, here and on the page. The signal is
SIGTERM, sent once. Nothing here ever sends SIGKILL: a session that does not end is reported as not ended.

Before the one signal every check below must hold, and all of them are made twice — once to decide, and again
immediately before ``os.kill`` (a pid that exited in between can be another process by then):

  * the pid is above 1 and is not this server's;
  * ``~/.claude/sessions/<pid>.json`` (a regular file, never through a symlink) names this sessionId, its ``pid`` is
    that pid, its ``kind`` is ``interactive`` and its ``entrypoint`` is ``cli`` (a terminal);
  * ``ps``: the process exists, is not a zombie, its argv[0] is a claude CLI (``…/claude`` or a native install's
    ``…/claude/versions/<version>``), and it started at the file's ``procStart`` — a reused pid started later.

What the server checks before this (server.api_session_end): the request checks of POST /api/prompt
(server.prompt_checks), the session in this server's list and not ended, and the robot asked for being the
session's main robot, never a subagent.

session-recovery's ledger (~/.claude/session-recovery/active.json, another lane's tool): a clocked-out session's
entry gets ``ended_reason: "clocked-out"``, under the lock its hook.sh / restore.sh take (common.sh lock_acquire: a
``mkdir`` of ``.lock`` next to the file, 50 tries 0.1 s apart, a lock older than 30 s removed; the file replaced by a
rename of ``active.json.tmp.<pid>``). No file, no entry: nothing is written.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import i18n
from .sources import session_files

SIGNAL = signal.SIGTERM
WAIT_SEC = 6.0
POLL_SEC = 0.1

#: The registry's ``entrypoint`` -> the client the page names. Only "terminal" may be clocked out.
CLIENTS = {"cli": "terminal", "claude-vscode": "vscode", "claude-desktop": "desktop"}
#: Why each other client is refused (the page says the same: 50-panel.js CLOCK_WHY): a key, said when refused.
REFUSED_CLIENT = {
    "vscode": "srv.clockout.vscode", "desktop": "srv.clockout.desktop", "other": "srv.clockout.other",
    "unknown": "srv.clockout.unknown",
}

LEDGER_LOCK_TRIES = 50
LEDGER_LOCK_STALE_SEC = 30

_LSTART = re.compile(r"^\s*(\S+)\s+([A-Z][a-z]{2} [A-Z][a-z]{2} [ 0-9][0-9] [0-9]{2}:[0-9]{2}:[0-9]{2} [0-9]{4})\s+(.*)$")
_NATIVE = re.compile(r"/claude/versions/[0-9][0-9A-Za-z.+-]*$")


def _kill(pid: int, sig: int) -> None:
    """The one place a signal is sent (tests replace it to record, and to refuse any pid they did not start)."""
    os.kill(pid, sig)


def client_of(entrypoint) -> str:
    if not isinstance(entrypoint, str) or not entrypoint:
        return "unknown"
    return CLIENTS.get(entrypoint, "other")


def is_claude_cli(command: str) -> bool:
    """argv[0] is a claude CLI: ``claude`` / ``…/claude``, or a native install's ``…/claude/versions/<version>``."""
    argv0 = command.split(" ", 1)[0] if command else ""
    return argv0.rsplit("/", 1)[-1] == "claude" or bool(_NATIVE.search(argv0))


def _norm(text: str) -> str:
    return " ".join(str(text).split())


def proc_info(pid: int) -> tuple[str, str, str] | None:
    """(state, start, command) of a process from ps, the start as ``procStart`` writes it (C locale, UTC), or None."""
    try:
        out = subprocess.run(["ps", "-o", "stat=,lstart=,command=", "-p", str(int(pid))], capture_output=True, text=True,
                             timeout=3, env=dict(os.environ, LC_ALL="C", LANG="C", TZ="UTC"))
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    m = _LSTART.match(out.stdout.strip().splitlines()[0] if out.stdout.strip() else "")
    return (m.group(1), m.group(2), m.group(3)) if m else None


def registry_pids(folder: Path, sid: str) -> list[int]:
    """The pids whose ~/.claude/sessions/<pid>.json names this sessionId (only <digits>.json is read)."""
    found = []
    if not folder.is_dir():
        return found
    for path in sorted(folder.iterdir()):
        data = session_files.read_session_file(path)
        if data is not None and data.get("sessionId") == sid:
            found.append(int(path.stem))
    return found


def check_pid(folder: Path, pid: int, sid: str, own_pid: int,
              procs: Callable[[int], tuple[str, str, str] | None] = proc_info) -> tuple[int, str] | None:
    """None when every check on the pid holds, else (HTTP status, why). Made before the signal, and again just before."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 1:
        return 403, "no such pid"
    if pid == own_pid:
        return 403, "that pid is this viz server"
    data = session_files.read_session_file(folder / f"{pid}.json")
    if data is None:
        return 409, "the session's ~/.claude/sessions entry is gone (it has ended?)"
    if data.get("sessionId") != sid:
        return 409, "the pid's sessionId does not match"
    if data.get("pid") != pid or isinstance(data.get("pid"), bool):
        return 409, "the entry's pid is not its file's"
    if data.get("kind") != "interactive":
        return 409, "not an interactive session"
    client = client_of(data.get("entrypoint"))
    if client != "terminal":
        return 409, i18n.tl(REFUSED_CLIENT[client])
    start = data.get("procStart")
    if not isinstance(start, str) or not start.strip():
        return 409, "the entry has no procStart: the process cannot be told from a reused pid"
    info = procs(pid)
    if info is None or "Z" in info[0]:
        return 409, "no such process (it has ended?)"
    if not is_claude_cli(info[2]):
        return 409, "the pid's command line is not a claude CLI"
    if _norm(info[1]) != _norm(start):
        return 409, "the process started at another time than the session (the pid was reused)"
    return None


@dataclass
class Outcome:
    result: str            # "ended" / "refused" / "not-ended"
    status: int            # HTTP status for the page
    reason: str
    pid: int | None = None
    signalled: bool = False


def _gone(pid: int, start: str, procs) -> bool:
    info = procs(pid)
    return info is None or "Z" in info[0] or _norm(info[1]) != _norm(start)


def end_session(folder: Path, sid: str, own_pid: int, *, procs=proc_info, before_signal: Callable[[int], None] | None = None,
                wait_sec: float = WAIT_SEC, poll_sec: float = POLL_SEC, known: tuple | None = None) -> Outcome:
    """Find the session's pid, check it, check it again, send SIGTERM once, wait for it to go. Blocking (run it in an
    executor). ``before_signal`` is for the race arm only: it runs between the two checks. ``known`` is the
    (pid, procStart) the server last saw for the session: with no entry left and that process gone, the session
    had already ended (killed without its SessionEnd) and nothing is sent."""
    pids = registry_pids(folder, sid)
    if not pids:
        if known and isinstance(known[0], int) and isinstance(known[1], str) and known[1].strip() \
                and _gone(known[0], known[1], procs) and not registry_pids(folder, sid):
            return Outcome("ended", 200, "no ~/.claude/sessions entry and its process is gone (it had already ended)", known[0])
        return Outcome("refused", 409, "no ~/.claude/sessions entry names this session (not running?)")
    if len(pids) > 1:
        return Outcome("refused", 409, "more than one ~/.claude/sessions entry names this session", None)
    pid = pids[0]
    refused = check_pid(folder, pid, sid, own_pid, procs)
    if refused is not None:
        return Outcome("refused", refused[0], refused[1], pid)
    start = (session_files.read_session_file(folder / f"{pid}.json") or {}).get("procStart", "")
    if before_signal is not None:
        before_signal(pid)
    refused = check_pid(folder, pid, sid, own_pid, procs)   # immediately before the signal
    if refused is not None:
        return Outcome("refused", refused[0], refused[1], pid)
    try:
        _kill(pid, SIGNAL)
    except ProcessLookupError:
        return Outcome("ended", 200, "it had already ended", pid)
    except PermissionError:
        return Outcome("refused", 403, "not allowed to signal that process", pid)
    deadline = time.monotonic() + wait_sec
    while time.monotonic() < deadline:
        if _gone(pid, start, procs):
            return Outcome("ended", 200, "ended after SIGTERM", pid, True)
        time.sleep(poll_sec)
    if _gone(pid, start, procs):
        return Outcome("ended", 200, "ended after SIGTERM", pid, True)
    return Outcome("not-ended", 504, f"SIGTERM was sent once and it has not ended within {wait_sec:g} s (nothing more is sent)", pid, True)


# ---------------------------------------------------------------- session-recovery's ledger


def _lock_acquire(lock: Path, tries: int = LEDGER_LOCK_TRIES, stale_sec: float = LEDGER_LOCK_STALE_SEC) -> bool:
    """common.sh lock_acquire, as it is: mkdir; a lock older than stale_sec is removed and tried again at once."""
    i = 0
    while True:
        try:
            os.mkdir(lock)
            return True
        except FileExistsError:
            pass
        try:
            age = time.time() - lock.stat().st_mtime
        except FileNotFoundError:
            continue
        if age > stale_sec:
            try:
                os.rmdir(lock)
                continue
            except OSError:
                pass
        i += 1
        if i >= tries:
            return False
        time.sleep(0.1)


def mark_ledger(sr_dir: Path, sid: str, at_epoch: float | None = None) -> str:
    """ended_reason "clocked-out" on this session's entry of active.json. Returns what happened, for the log:
    "absent" (no file: nothing done), "no entry", "marked", "lock timeout", "unreadable"."""
    active = sr_dir / "active.json"
    if not active.is_file():
        return "absent"
    lock = sr_dir / ".lock"
    try:
        if not _lock_acquire(lock):
            return "lock timeout"
    except OSError:
        return "lock error"
    try:
        try:
            data = json.loads(active.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            return "unreadable"
        if not isinstance(data, list):
            return "unreadable"
        hit = [e for e in data if isinstance(e, dict) and e.get("session_id") == sid]
        if not hit:
            return "no entry"
        when = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if at_epoch is None else at_epoch))
        for entry in hit:
            entry["ended_reason"] = "clocked-out"
            entry["ended_at"] = when
        tmp = sr_dir / f"active.json.tmp.{os.getpid()}"
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, active)
        return "marked"
    finally:
        try:
            os.rmdir(lock)
        except OSError:
            pass


# ---------------------------------------------------------------- the log of every attempt


def write_log(path: Path, record: dict) -> None:
    """One JSON line per attempt, in a 0600 file. A failure to write never changes the outcome."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"))
        finally:
            os.close(fd)
    except OSError:
        pass
