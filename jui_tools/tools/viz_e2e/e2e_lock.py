"""One viz e2e at a time on the machine (2.3.5 ruling, 10-20).

Several lanes' browser runs side by side drove the load to 140+ and made the suites time out in varying places. run.py
takes this lock before it starts a browser and keeps it until it exits:

  - the lock file is /tmp/jui-viz-e2e-<uid>.lock: a fixed place outside every worktree, and not under HOME or TMPDIR,
    which a run (or the session that starts it) may point somewhere of its own. JUI_VIZ_E2E_LOCK names another file
    (the arms use one of their own);
  - it is an flock: the kernel lets go of it when the holder exits, however it exits (a crash, kill -9), so a dead
    run never blocks the next;
  - while another run holds it, "waiting for another viz e2e (pid N)" is printed at once and again every 30 s.
"""

from __future__ import annotations

import fcntl
import os
import time

LOCK_ENV = "JUI_VIZ_E2E_LOCK"
WAIT_SAY_EVERY = 30.0


def lock_path() -> str:
    return os.environ.get(LOCK_ENV) or f"/tmp/jui-viz-e2e-{os.getuid()}.lock"


def _holder(fd: int) -> str:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        return os.read(fd, 64).decode(errors="replace").strip() or "?"
    except OSError:
        return "?"


def hold(path: str | None = None, say_every: float = WAIT_SAY_EVERY, poll: float = 0.5, say=print) -> int:
    """Block until this process holds the lock; returns its fd (keep it open: closing it, or exiting, lets go)."""
    path = path or lock_path()
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o666)
    last_said = None
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            now = time.monotonic()
            if last_said is None or now - last_said >= say_every:
                say(f"waiting for another viz e2e (pid {_holder(fd)})", flush=True)
                last_said = now
            time.sleep(poll)
    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, str(os.getpid()).encode())
    return fd
