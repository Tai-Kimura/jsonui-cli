"""A whole browser run waits for a machine that has the time (tools/viz_e2e/load_hold.py; ticket
2026-11-06-viz-e2e-full-run-red-under-load). The reading and the clock are handed in, so none of this needs a busy
machine, and a wait that never ends is a failed arm here, not a run that hangs."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import pytest

E2E = Path(__file__).resolve().parents[1] / "tools" / "viz_e2e"
sys.path.insert(0, str(E2E))
import common  # noqa: E402
import load_hold  # noqa: E402

CORES = 18
LIMIT = 54


class Machine:
    """A load read from a list (the last one stays), an exception raised as it is read; a clock moved only by sleep."""

    def __init__(self, *loads):
        self.loads, self.t, self.lines, self.sleeps = list(loads), 0.0, [], []

    def read(self):
        v = self.loads.pop(0) if len(self.loads) > 1 else self.loads[0]
        if isinstance(v, Exception):
            raise v
        return v

    def sleep(self, s):
        assert len(self.sleeps) < 500, "a wait that does not end"
        assert s > 0
        self.sleeps.append(s)
        self.t += s

    def now(self):
        self.t += 0.001   # a real clock: never the same twice, with no wait at all
        return self.t

    def hold(self, name="props"):
        load_hold.hold(name, read=self.read, cores=CORES, sleep=self.sleep, now=self.now, say=self.lines.append)


@pytest.fixture(autouse=True)
def fresh():
    load_hold.configure(args())
    load_hold._on = False
    yield
    load_hold.configure(args())
    load_hold._on = False


def args(**kw):
    return argparse.Namespace(**{"only": None, "suite": None, "record_demo": None, "no_load_hold": False, "priority": False, **kw})


@pytest.mark.parametrize("load", [0.0, 20.0, LIMIT])
def test_at_the_limit_or_under_it_a_suite_starts_at_once_and_says_nothing(load):
    m = Machine(load)
    m.hold()
    assert m.sleeps == [] and m.lines == [] and load_hold.summary() == []


def test_over_the_limit_it_waits_and_the_line_says_how_long_and_the_load_it_started_at():
    m = Machine(90.0, 70.0, 55.0, 30.5)
    m.hold()
    assert m.sleeps == [15.0, 15.0, 15.0]
    assert m.lines == ["  props: load 90.0 is over 54, waiting up to 600s",
                       "  props: waited 45s for the load, started at 30.5 (limit 54)"]
    assert load_hold.summary() == ["load hold: waited 45s in all"]


def test_a_load_that_stays_up_starts_after_the_most_and_says_so_beside_the_reds():
    m = Machine(120.0)
    m.hold("breaks")
    assert 600.0 <= m.t < 601.0 and load_hold.MAX_WAIT_S == 600.0
    assert m.lines[-1] == "  breaks: started at load 120.0, still over 54 after 600s (every check as it is)"
    assert load_hold.summary() == ["load hold: waited 600s in all", "load hold: started over the limit: breaks (120.0)"]


def test_the_last_sleep_ends_at_the_most_and_not_past_it():
    m = Machine(120.0)
    load_hold.hold("x", read=m.read, cores=CORES, sleep=m.sleep, now=lambda: m.t, say=m.lines.append, max_wait=20.0, poll=15.0)
    assert m.sleeps == [15.0, 5.0] and m.t == 20.0   # the plain clock here: the sum is exact


@pytest.mark.parametrize("unreadable", [OSError("no load"), ValueError("x"), RuntimeError("x"), float("nan"), float("inf"), None, "?"])
def test_a_load_that_cannot_be_read_never_holds_a_suite(unreadable):
    m = Machine(unreadable)
    m.hold()
    assert m.sleeps == []
    assert m.lines == ["  props: the load cannot be read, started after 0s of waiting"]


def test_a_reading_that_stops_working_during_a_wait_ends_the_wait():
    m = Machine(90.0, OSError("gone"))
    m.hold()
    assert m.sleeps == [15.0] and m.lines[-1] == "  props: the load cannot be read, started after 15s of waiting"


def test_the_real_reading_is_a_number():
    assert load_hold.read_load() >= 0


@pytest.mark.parametrize("kw, on", [
    ({}, True),
    ({"priority": True}, True),
    ({"only": ["props"]}, False),
    ({"only": ["live"], "priority": True}, False),
    ({"suite": ["a"]}, False),
    ({"record_demo": "http://x"}, False),
    ({"no_load_hold": True}, False),
    ({"no_load_hold": True, "priority": True}, False),
])
def test_only_a_whole_run_holds(kw, on):
    assert load_hold.configure(args(**kw)) is on and load_hold.enabled() is on


def test_the_guard_holds_a_suite_only_when_the_run_holds(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(load_hold, "hold", lambda name, **kw: calls.append(name))
    with common.suite_guard("props", []):
        pass
    assert calls == []
    load_hold._on = True
    at_start = []
    with common.suite_guard("breaks", []):
        at_start.extend(calls)   # the guard takes an assert in its body for the suite's own failure: read outside it
    assert at_start == ["breaks"]   # before the suite, not after it


@pytest.mark.parametrize("argv, on", [
    ([], True),
    (["--priority"], True),
    (["--only", "props"], False),
    (["--no-load-hold"], False),
])
def test_run_py_turns_it_on_from_its_own_arguments(tmp_path, monkeypatch, argv, on):
    pytest.importorskip("playwright.async_api")
    import e2e_lock
    import run
    monkeypatch.setattr(e2e_lock, "hold", lambda **kw: None)
    seen = []

    def no_browsers(coro):
        coro.close()
        seen.append(load_hold.enabled())

    monkeypatch.setattr(asyncio, "run", no_browsers)
    assert run.main(["--out", str(tmp_path), *argv]) == 0
    assert seen == [on]
