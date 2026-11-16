"""One suite's exception never ends the browser run (tools/viz_e2e/common.py suite_guard; ticket
2026-10-20-jui-viz-e2e-one-suite-exception-stops-the-run).

A timeout in props once went up to run.py as a WaitTimeout: the run ended with a traceback, no FAIL line, and no later
suite ran. Every suite block in run.py is now inside suite_guard, which turns any exception into one FAIL line and lets
the next block run. These arms need no browser: the guard itself, the forced timeout of waits.until, and that every
suite block of run.py is guarded (the family: a block added later without the guard is red here).
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

import pytest

E2E = Path(__file__).resolve().parents[1] / "tools" / "viz_e2e"
sys.path.insert(0, str(E2E))
import common  # noqa: E402
import waits  # noqa: E402


def test_a_timeout_in_one_suite_is_a_fail_line_and_the_next_suite_runs(tmp_path):
    failures, ran = [], []

    async def go():
        with common.suite_guard("props", failures, tmp_path):
            ran.append("props")
            raise waits.WaitTimeout("waiting for ten again: Timeout 30000ms exceeded.\nmore")
        with common.suite_guard("breaks", failures, tmp_path):
            await asyncio.sleep(0)
            ran.append("breaks")
        with common.suite_guard("weather", failures, tmp_path):
            raise KeyError("x")

    asyncio.run(go())
    assert ran == ["props", "breaks"]
    assert failures == ["props: the suite stopped: WaitTimeout: waiting for ten again: Timeout 30000ms exceeded.",
                        "weather: the suite stopped: KeyError: 'x'"]
    assert "WaitTimeout" in (tmp_path / "props-traceback.txt").read_text()
    assert not (tmp_path / "breaks-traceback.txt").exists()


def test_an_interrupt_still_stops_the_run():
    with pytest.raises(KeyboardInterrupt):
        with common.suite_guard("props", []):
            raise KeyboardInterrupt


def test_the_forced_timeout_names_one_wait(monkeypatch):
    monkeypatch.setenv(waits.FORCE_TIMEOUT, "the robot at its desk")

    class Page:   # the forced timeout comes before the page is touched
        async def wait_for_function(self, *a, **k):
            raise AssertionError("not reached")

    with pytest.raises(waits.WaitTimeout, match="forced"):
        asyncio.run(waits.until(Page(), "() => true", "the robot at its desk (settled)"))


def test_every_suite_block_of_run_py_is_guarded():
    lines = (E2E / "run.py").read_text().splitlines()
    blocks = [i for i, l in enumerate(lines) if re.match(r"\s*if want\(", l)]
    assert len(blocks) >= 25
    unguarded = [lines[i].strip() for i in blocks if "with suite_guard(" not in lines[i + 1]]
    assert unguarded == []
    assert not [l for l in lines if "a.only in (" in l]   # no block chosen the old way, outside the guard's pattern


def test_every_suite_call_in_run_py_is_inside_a_guard():
    """Not only the `if want(` blocks: any `await <suite>.run_...(` in go() sits, by indentation, under a `with
    suite_guard(` line (a suite added later as a bare call, or under another kind of `if`, is red here)."""
    lines = (E2E / "run.py").read_text().splitlines()
    go = next(i for i, l in enumerate(lines) if l.strip() == "async def go():")
    end = next(i for i, l in enumerate(lines) if "asyncio.run(go())" in l)
    bare = []
    for i in range(go, end):
        if not re.search(r"await \w+\.run_\w+\(", lines[i]):
            continue
        ind = len(lines[i]) - len(lines[i].lstrip())
        guarded = False
        for j in range(i - 1, go, -1):
            lj = lines[j]
            if not lj.strip():
                continue
            k = len(lj) - len(lj.lstrip())
            if k < ind and "with suite_guard(" in lj:
                guarded = True
                break
            if k < ind:
                ind = k
        if not guarded:
            bare.append(lines[i].strip())
    assert bare == []


# ---------------------------------------------------------------- what a suite started and left (children.py)
# Each arm follows its processes by the pids Popen gave, never by a name (ps -p <pid>); the marks in the sleeps are
# only to tell them apart in a listing by eye.

import os  # noqa: E402
import signal  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402


def _state(pid: int) -> str:
    """ps's state of ``pid``: '' when there is no such process (gone and reaped)."""
    return subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()


def _gone(pid: int, within: float = 3.0) -> bool:
    end = time.monotonic() + within
    while time.monotonic() < end:
        if _state(pid) == "":
            return True
        time.sleep(0.05)
    return False


def _sleeper(*pre: str, **kw) -> subprocess.Popen:
    code = "; ".join([*pre, "import time", "time.sleep(30.7171)"])
    return subprocess.Popen([sys.executable, "-c", code], **kw)


def test_a_child_the_suite_left_is_stopped_and_reaped_when_the_suite_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "STOP_WAIT_S", 3.0)
    failures, kid = [], {}
    with common.suite_guard("leaky", failures, tmp_path):
        kid["p"] = _sleeper()
        raise RuntimeError("a failure after the serve started")
    pid = kid["p"].pid
    assert failures and _state(pid) == "", (pid, _state(pid))   # not running, and not a zombie: reaped
    assert kid["p"].wait(timeout=1) is not None or True        # the Popen still waits without an error


def test_a_child_from_before_the_suite_is_left_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "STOP_WAIT_S", 1.0)
    earlier = _sleeper()
    try:
        with common.suite_guard("other", [], tmp_path):
            raise RuntimeError("fails")
        assert _state(earlier.pid) and not _state(earlier.pid).startswith("Z")
    finally:
        earlier.kill()   # our own, by its pid
        earlier.wait(timeout=5)


def test_a_child_that_ignores_int_is_killed_after_the_wait(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "STOP_WAIT_S", 1.0)
    kid = {}
    t0 = time.monotonic()
    with common.suite_guard("stubborn", [], tmp_path):
        kid["p"] = _sleeper("import signal", "signal.signal(signal.SIGINT, signal.SIG_IGN)")
        time.sleep(0.5)   # its handler is set
        raise RuntimeError("fails")
    assert _state(kid["p"].pid) == "" and 0.9 <= time.monotonic() - t0 < 8


def test_what_a_session_of_its_own_started_is_stopped_after_its_parent_has_gone(tmp_path, monkeypatch):
    """A child with a session of its own (start_new_session) starts a grandchild and ends: the grandchild's parent is
    the init process (as a serve whose parent went), and it is still stopped — by the group the child's pid heads."""
    monkeypatch.setattr(common, "STOP_WAIT_S", 2.0)
    mark = tmp_path / "grandchild.pid"
    code = ("import os, subprocess, sys; "
            f"g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30.7171)']); "
            f"open({str(mark)!r}, 'w').write(str(g.pid)); os._exit(0)")
    with common.suite_guard("detached", [], tmp_path):
        child = subprocess.Popen([sys.executable, "-c", code], start_new_session=True)
        end = time.monotonic() + 10
        while not (mark.exists() and mark.read_text()) and time.monotonic() < end:
            time.sleep(0.05)
        gpid = int(mark.read_text())
        while time.monotonic() < end and not _state(child.pid).startswith("Z"):
            time.sleep(0.05)
        ppid = subprocess.run(["ps", "-o", "ppid=", "-p", str(gpid)], capture_output=True, text=True).stdout.strip()
        assert ppid == "1", ppid   # the form: its parent gone
        raise RuntimeError("fails")
    try:
        assert _gone(gpid), _state(gpid)
    finally:
        if _state(gpid):
            os.kill(gpid, signal.SIGKILL)   # the arm's own grandchild, by its pid
