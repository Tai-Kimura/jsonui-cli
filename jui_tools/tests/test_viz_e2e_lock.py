"""One viz e2e at a time on the machine, in the order asked (tools/viz_e2e/e2e_lock.py; 2.3.5 ruling, 10-20; the line:
ticket 2026-10-21-viz-e2e-lock-has-no-queue).

The arms run the lock in child processes on a lock file of their own (JUI_VIZ_E2E_LOCK), never the machine's:
two started together run one after the other, the second says how many are ahead and who holds it, the runs waiting
take it in the order they asked, a priority ticket goes first, and a holder or a waiter that died (kill -9) does not
block the next.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

E2E = Path(__file__).resolve().parents[1] / "tools" / "viz_e2e"
sys.path.insert(0, str(E2E))
import e2e_lock  # noqa: E402

CHILD = """
import json, sys, time
sys.path.insert(0, sys.argv[1])
import e2e_lock
fd = e2e_lock.hold(say_every=float(sys.argv[3]), poll=0.05, only=json.loads(sys.argv[4]),
                   priority=True if sys.argv[5] == "1" else None)
t0 = time.time(); print("start", t0, flush=True)
time.sleep(float(sys.argv[2]))
print("end", time.time(), flush=True)
"""


def child(lock, hold_sec, say_every=30.0, only=(), priority=False, env=None):
    # the session's own mark never reaches a child: only an arm's env= marks one
    full = {k: v for k, v in os.environ.items() if k != e2e_lock.PRIORITY_ENV}
    full.update({e2e_lock.LOCK_ENV: str(lock)}, **(env or {}))
    return subprocess.Popen([sys.executable, "-c", CHILD, str(E2E), str(hold_sec), str(say_every), json.dumps(list(only)),
                             "1" if priority else "0"], env=full, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def times(out):
    return {k: float(v) for k, v in re.findall(r"^(start|end) ([0-9.]+)$", out, re.M)}


def queued(lock, n, timeout=10.0):
    """Wait until n tickets are in the line (each child has asked)."""
    q = Path(str(lock) + ".queue")
    t = time.monotonic()
    while time.monotonic() - t < timeout:
        if q.is_dir() and len([p for p in q.iterdir() if p.suffix == ".json"]) >= n:
            return
        time.sleep(0.02)
    raise AssertionError(f"{n} tickets never in the line: {sorted(p.name for p in q.iterdir()) if q.is_dir() else None}")


def started(proc):
    line = proc.stdout.readline()
    assert line.startswith("start"), line
    return float(line.split()[1])


def test_two_runs_started_together_run_one_after_the_other(tmp_path):
    lock = tmp_path / "e2e.lock"
    a = child(lock, 1.5, say_every=0.4, only=["gitbox"])
    started(a)
    b = child(lock, 0.2, say_every=0.4)
    out_a, out_b = a.communicate(timeout=30)[0], b.communicate(timeout=30)[0]
    ta, tb = times(out_a), times(out_b)
    assert tb["start"] >= ta["end"], (out_a, out_b)
    waits = re.findall(r"^waiting for a viz e2e: (\d+) ahead; holding it: (.*)$", out_b, re.M)
    assert len(waits) >= 2, out_b                                        # at once, then again every say_every
    assert json.loads(lock.read_text())["pid"] == b.pid                  # the last holder wrote who it is


def test_three_waiting_run_in_the_order_they_asked(tmp_path):
    """① The line: a holds it; b, c, d ask in that order (each after the last is in the line) and run b, c, d."""
    lock = tmp_path / "e2e.lock"
    a = child(lock, 1.5)
    started(a)
    rest = []
    for i in range(3):
        rest.append(child(lock, 0.1))
        queued(lock, i + 1)
    outs = [p.communicate(timeout=60)[0] for p in [a, *rest]]
    starts = [times(o)["start"] for o in outs[1:]]
    assert starts == sorted(starts), outs
    assert all(times(outs[i])["end"] <= times(outs[i + 1])["start"] for i in range(1, 3)), outs


def test_a_priority_ticket_goes_before_the_ones_waiting(tmp_path):
    """② b and c wait; p asks last with the integration's mark (--priority, or the environment's): p runs first, then
    b, c. The holder a is never stopped."""
    lock = tmp_path / "e2e.lock"
    a = child(lock, 1.5)
    started(a)
    b = child(lock, 0.1)
    queued(lock, 1)
    c = child(lock, 0.1)
    queued(lock, 2)
    p = child(lock, 0.1, env={e2e_lock.PRIORITY_ENV: "1"})
    queued(lock, 3)
    out = {k: v.communicate(timeout=60)[0] for k, v in (("a", a), ("b", b), ("c", c), ("p", p))}
    t = {k: times(v) for k, v in out.items()}
    assert t["a"]["end"] <= t["p"]["start"] <= t["b"]["start"] <= t["c"]["start"], out
    assert t["p"]["end"] <= t["b"]["start"], out


def test_a_waiter_that_died_is_taken_out_of_the_line(tmp_path):
    """③ b waits first, c behind it; b is killed hard while it waits: c runs as soon as a lets go, and b's ticket is
    gone from the line."""
    lock = tmp_path / "e2e.lock"
    a = child(lock, 1.0)
    started(a)
    b = child(lock, 0.1)
    queued(lock, 1)
    c = child(lock, 0.1)
    queued(lock, 2)
    os.kill(b.pid, signal.SIGKILL)
    b.wait(timeout=10)
    out_a, out_c = a.communicate(timeout=30)[0], c.communicate(timeout=30)[0]
    assert "start" in out_c and times(out_c)["start"] - times(out_a)["end"] < 5, out_c
    assert [p.name for p in Path(str(lock) + ".queue").iterdir() if p.suffix == ".json"] == []


def test_a_holder_killed_hard_does_not_block_the_next(tmp_path):
    lock = tmp_path / "e2e.lock"
    a = child(lock, 600)
    started(a)
    os.kill(a.pid, signal.SIGKILL)
    a.wait(timeout=10)
    t = time.monotonic()
    b = child(lock, 0)
    out_b = b.communicate(timeout=30)[0]
    assert "start" in out_b and time.monotonic() - t < 10, out_b


def test_the_wait_says_how_many_are_ahead_and_who_holds_it(tmp_path):
    """④ c waits behind b while a (--only gitbox, data-server) holds it: c says 1 ahead, and a's pid, --only and
    folder."""
    lock = tmp_path / "e2e.lock"
    a = child(lock, 1.5, only=["gitbox", "data-server"])
    started(a)
    b = child(lock, 0.1)
    queued(lock, 1)
    c = child(lock, 0.1, say_every=0.3)
    queued(lock, 2)
    out_c = c.communicate(timeout=30)[0]
    a.communicate(timeout=30), b.communicate(timeout=30)
    first = re.search(r"^waiting for a viz e2e: (\d+) ahead; holding it: (.*)$", out_c, re.M)
    assert first and first.group(1) == "1", out_c
    assert first.group(2) == f"pid {a.pid} (--only gitbox, data-server; in {os.getcwd()})", out_c


def test_a_lock_written_by_an_older_run_still_names_its_pid():
    assert e2e_lock.describe({"pid": "4242"}) == "pid 4242"
    assert e2e_lock.describe({"pid": 7, "only": [], "cwd": "/w"}) == "pid 7 (everything; in /w)"


def test_the_lock_file_is_one_fixed_place_outside_home_and_tmpdir(monkeypatch):
    monkeypatch.delenv(e2e_lock.LOCK_ENV, raising=False)
    assert e2e_lock.lock_path() == f"/tmp/jui-viz-e2e-{os.getuid()}.lock"


def test_run_py_takes_the_lock_before_the_browser_with_its_only_and_mark():
    src = (E2E / "run.py").read_text()
    assert src.index("e2e_lock.hold(") < src.index("asyncio.run(go())")
    assert "e2e_lock.hold(only=a.only or [], priority=True if a.priority else None)" in src and '"--priority"' in src
