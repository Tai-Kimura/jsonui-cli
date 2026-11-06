"""A whole run's suite does not start on a machine too busy to run it (ticket 2026-11-06-viz-e2e-full-run-red-under-load).

Under load over 100 a state took longer than its wait's cap, in a different suite each run. The cap is not the fix
(waits.py), so no check changes here: before each suite, while the one-minute load is over three times the cores, the
run waits for it, ten minutes at most, and then starts whatever the load is and says so. Only a whole run does this (no
--only, no --suite; --priority or not); --no-load-hold turns it off. A load that cannot be read never holds anything.
"""
from __future__ import annotations

import math
import os
import time

FACTOR = 3
MAX_WAIT_S = 600.0
POLL_S = 15.0

_on = False
_waited = 0.0
_over: list[str] = []


def read_load() -> float:
    return os.getloadavg()[0]


def configure(a) -> bool:
    """On for a whole run only: `a` is run.py's parsed arguments."""
    global _on, _waited
    _on = not (a.only or a.suite or a.record_demo or a.no_load_hold)
    _waited = 0.0
    _over.clear()
    return _on


def enabled() -> bool:
    return _on


def _read(read):
    try:
        load = float(read())
    except Exception:  # noqa: BLE001 - whatever the reading did, it is not a reason to wait
        return None
    return load if math.isfinite(load) else None


def hold(name: str, read=read_load, cores=None, sleep=time.sleep, now=time.monotonic, say=print,
         max_wait: float = MAX_WAIT_S, poll: float = POLL_S) -> None:
    """Return when suite `name` may start: the load is at the limit or under it, unreadable, or `max_wait` has passed."""
    global _waited
    limit = FACTOR * (cores or os.cpu_count() or 1)
    start = now()
    slept = False
    while True:
        load = _read(read)
        spent = now() - start
        if slept and (load is None or load <= limit or spent >= max_wait):
            _waited += spent
        if load is None:
            say(f"  {name}: the load cannot be read, started after {spent:.0f}s of waiting")
            return
        if load <= limit:
            if slept:
                say(f"  {name}: waited {spent:.0f}s for the load, started at {load:.1f} (limit {limit})")
            return
        if spent >= max_wait:
            _over.append(f"{name} ({load:.1f})")
            say(f"  {name}: started at load {load:.1f}, still over {limit} after {spent:.0f}s (every check as it is)")
            return
        if not slept:
            say(f"  {name}: load {load:.1f} is over {limit}, waiting up to {max_wait:.0f}s")
        sleep(min(poll, max_wait - spent))
        slept = True


def summary() -> list[str]:
    """For the end of the log, where the FAIL lines are: what a red there should be read beside."""
    lines = []
    if _waited > 0:
        lines.append(f"load hold: waited {_waited:.0f}s in all")
    if _over:
        lines.append(f"load hold: started over the limit: {', '.join(_over)}")
    return lines
