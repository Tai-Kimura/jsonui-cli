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
