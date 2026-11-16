"""A whole run's suite does not start on a machine too busy to run it (ticket 2026-11-06-viz-e2e-full-run-red-under-load).

Under load over 100 a state took longer than its wait's cap, in a different suite each run. The cap is not the fix
(waits.py), so no check changes here: before each suite, while the one-minute load is over three times the cores, the
run waits for it, ten minutes at most, and then starts whatever the load is and says so. Thirty minutes of waiting in
all, and every later suite starts as it is: the machine's line of runs is behind this one. Only a whole run does this
(no --only, no --suite; --priority or not); --no-load-hold turns it off. A load that cannot be read never holds anything.
"""
from __future__ import annotations

import math
import os
import time

FACTOR = 3
MAX_WAIT_S = 600.0
TOTAL_WAIT_S = 1800.0
BUDGET_USED = "load hold budget used, every later suite starts as it is"
POLL_S = 15.0

_on = False
_waited = 0.0
_budget_used = False
_over: list[str] = []


def read_load() -> float:
    return os.getloadavg()[0]


def configure(a) -> bool:
    """On for a whole run only: `a` is run.py's parsed arguments."""
    global _on, _waited, _budget_used
    _on = not (a.only or a.suite or a.record_demo or a.no_load_hold)
    _waited = 0.0
    _budget_used = False
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
         max_wait: float = MAX_WAIT_S, poll: float = POLL_S, total_wait: float = TOTAL_WAIT_S) -> None:
    """Return when suite `name` may start: the load is at the limit or under it, unreadable, `max_wait` has passed, or
    the run has spent `total_wait` on waiting."""
    limit = FACTOR * (cores or os.cpu_count() or 1)
    allowed = min(max_wait, total_wait - _waited)
    if allowed <= 0:
        load = _read(read)
        if load is not None and load > limit:
            _over.append(f"{name} ({load:.1f})")
        return
    start = now()
    slept = False

    def done(spent):
        global _waited, _budget_used
        if slept:
            _waited += spent
            if _waited >= total_wait:   # and no suite waits after this (`allowed` above), so it is said once
                _budget_used = True
                say(f"  {BUDGET_USED}")

    while True:
        load = _read(read)
        spent = now() - start
        if load is None:
            say(f"  {name}: the load cannot be read, started after {spent:.0f}s of waiting")
            done(spent)
            return
        if load <= limit:
            if slept:
                say(f"  {name}: waited {spent:.0f}s for the load, started at {load:.1f} (limit {limit})")
            done(spent)
            return
        if spent >= allowed:
            _over.append(f"{name} ({load:.1f})")
            say(f"  {name}: started at load {load:.1f}, still over {limit} after {spent:.0f}s (every check as it is)")
            done(spent)
            return
        if not slept:
            say(f"  {name}: load {load:.1f} is over {limit}, waiting up to {allowed:.0f}s")
        sleep(min(poll, allowed - spent))
        slept = True


def summary() -> list[str]:
    """For the end of the log, where the FAIL lines are: what a red there should be read beside."""
    lines = []
    if _waited > 0:
        lines.append(f"load hold: waited {_waited:.0f}s in all")
    if _budget_used:
        lines.append(f"{BUDGET_USED}")
    if _over:
        lines.append(f"load hold: started over the limit: {', '.join(_over)}")
    return lines
