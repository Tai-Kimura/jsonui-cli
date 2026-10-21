"""One viz e2e at a time on the machine (2.3.5 ruling, 10-20), taken in the order asked (2.3.16).

Several lanes' browser runs side by side drove the load to 140+ and made the suites time out in varying places. run.py
takes this lock before it starts a browser and keeps it until it exits:

  - the lock file is /tmp/jui-viz-e2e-<uid>.lock: a fixed place outside every worktree, and not under HOME or TMPDIR,
    which a run (or the session that starts it) may point somewhere of its own. JUI_VIZ_E2E_LOCK names another file
    (the arms use one of their own);
  - it is an flock: the kernel lets go of it when the holder exits, however it exits (a crash, kill -9), so a dead
    run never blocks the next;
  - the runs waiting take it in turn: each takes a ticket first, numbered in the order asked, in <lock>.queue/, and
    only the first ticket may take the lock. Before, whoever looked first when it came free took it, and a run that
    had waited two hours was passed again and again (ticket 2026-10-21-viz-e2e-lock-has-no-queue);
  - a ticket marked priority (--priority, or JUI_VIZ_E2E_PRIORITY=1: the integration's checks only) goes before every
    unmarked one, after the marked ones already waiting; it never stops the run that holds the lock;
  - a ticket is held with an flock of its own while its run waits: a run that died (a crash, kill -9) lets go of it,
    and the next one to look takes it out of the line;
  - while it waits, a run prints how many are ahead and who holds the lock (its pid, its --only, its folder) at once
    and again every minute.
"""

from __future__ import annotations

import fcntl
import json
import os
import time

LOCK_ENV = "JUI_VIZ_E2E_LOCK"
PRIORITY_ENV = "JUI_VIZ_E2E_PRIORITY"
WAIT_SAY_EVERY = 60.0


def lock_path() -> str:
    return os.environ.get(LOCK_ENV) or f"/tmp/jui-viz-e2e-{os.getuid()}.lock"


def priority_from_env() -> bool:
    return os.environ.get(PRIORITY_ENV, "").strip().lower() in ("1", "true", "yes")


def _read_json(fd: int) -> dict:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        raw = os.read(fd, 4096).decode(errors="replace").strip()
    except OSError:
        return {}
    if not raw:
        return {}
    try:
        got = json.loads(raw)
    except ValueError:
        return {"pid": raw}   # a run before 2.3.16 wrote its pid alone
    return got if isinstance(got, dict) else {"pid": raw}


def describe(who: dict) -> str:
    """pid N (--only a, b; in <folder>), from what a run wrote (a run before 2.3.16: its pid only)."""
    parts = [f"pid {who.get('pid', '?')}"]
    extra = []
    if who.get("only") is not None:
        extra.append("--only " + ", ".join(who["only"]) if who["only"] else "everything")
    if who.get("cwd"):
        extra.append(f"in {who['cwd']}")
    return parts[0] + (f" ({'; '.join(extra)})" if extra else "")


def _write(fd: int, data: dict) -> None:
    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, json.dumps(data).encode())


class Ticket:
    """This run's place in the line: <lock>.queue/<0 priority | 1>-<number>-<pid>.json, flocked while it waits."""

    def __init__(self, queue: str, me: dict, priority: bool):
        os.makedirs(queue, exist_ok=True)
        self.queue = queue
        with open(os.path.join(queue, ".number"), "a+") as counter:   # the next number, one taker at a time
            fcntl.flock(counter, fcntl.LOCK_EX)
            counter.seek(0)
            text = counter.read().strip()
            number = int(text) + 1 if text.isdigit() else 1
            counter.seek(0)
            counter.truncate()
            counter.write(str(number))
        self.name = f"{0 if priority else 1}-{number:012d}-{os.getpid()}.json"
        # flocked before it is in the line under its name: no one sees it unheld and takes it for a dead one's
        tmp = os.path.join(queue, f".new-{os.getpid()}-{number}")
        self.fd = os.open(tmp, os.O_RDWR | os.O_CREAT | os.O_TRUNC, 0o666)
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        _write(self.fd, dict(me, number=number, priority=priority))
        os.rename(tmp, os.path.join(queue, self.name))

    def ahead(self) -> list[dict]:
        """The live tickets before this one, in their order; a dead run's ticket is taken out of the line."""
        out = []
        for name in sorted(n for n in os.listdir(self.queue) if n.endswith(".json")):
            if name >= self.name:
                break
            path = os.path.join(self.queue, name)
            try:
                fd = os.open(path, os.O_RDWR)
            except FileNotFoundError:
                continue
            try:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:   # its run is alive and waiting
                    out.append(_read_json(fd))
                    continue
                try:   # no one holds it: its run died
                    os.unlink(path)
                except FileNotFoundError:
                    pass
            finally:
                os.close(fd)
        return out

    def leave(self) -> None:
        try:
            os.unlink(os.path.join(self.queue, self.name))
        except FileNotFoundError:
            pass
        os.close(self.fd)


def hold(path: str | None = None, say_every: float = WAIT_SAY_EVERY, poll: float = 0.5, say=print,
         only: list[str] | None = None, priority: bool | None = None) -> int:
    """Block until this process holds the lock, in its turn; returns its fd (keep it open: closing it, or exiting, lets
    go). only: the run's --only (None: not said; [] everything), shown to the runs waiting behind it."""
    path = path or lock_path()
    me = {"pid": os.getpid(), "only": only, "cwd": os.getcwd(), "since": int(time.time())}
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o666)
    ticket = Ticket(path + ".queue", me, priority_from_env() if priority is None else priority)
    last_said = None
    try:
        while True:
            ahead = ticket.ahead()
            if not ahead:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    pass
            now = time.monotonic()
            if last_said is None or now - last_said >= say_every:
                held = _read_json(fd)
                if ahead:   # free between two runs: the file still names the last one
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        fcntl.flock(fd, fcntl.LOCK_UN)
                        held = {}
                    except BlockingIOError:
                        pass
                say(f"waiting for a viz e2e: {len(ahead)} ahead; holding it: {describe(held) if held else '(none)'}",
                    flush=True)
                last_said = now
            time.sleep(poll)
    finally:
        ticket.leave()
    _write(fd, me)
    return fd
