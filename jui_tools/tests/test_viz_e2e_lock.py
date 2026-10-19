"""One viz e2e at a time on the machine (tools/viz_e2e/e2e_lock.py; 2.3.5 ruling, 10-20).

The arms run the lock in child processes on a lock file of their own (JUI_VIZ_E2E_LOCK), never the machine's:
two started together run one after the other, the second says whom it waits for, and a holder that died (kill -9)
does not block the next.
"""
from __future__ import annotations

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
import sys, time
sys.path.insert(0, sys.argv[1])
import e2e_lock
fd = e2e_lock.hold(say_every=float(sys.argv[3]), poll=0.05)
t0 = time.time(); print("start", t0, flush=True)
time.sleep(float(sys.argv[2]))
print("end", time.time(), flush=True)
"""


def child(lock, hold_sec, say_every=30.0):
    env = dict(os.environ, **{e2e_lock.LOCK_ENV: str(lock)})
    return subprocess.Popen([sys.executable, "-c", CHILD, str(E2E), str(hold_sec), str(say_every)], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def times(out):
    return {k: float(v) for k, v in re.findall(r"^(start|end) ([0-9.]+)$", out, re.M)}


def test_two_runs_started_together_run_one_after_the_other(tmp_path):
    lock = tmp_path / "e2e.lock"
    a = child(lock, 1.5, say_every=0.4)
    time.sleep(0.5)
    b = child(lock, 0.2, say_every=0.4)
    out_a, out_b = a.communicate(timeout=30)[0], b.communicate(timeout=30)[0]
    ta, tb = times(out_a), times(out_b)
    assert tb["start"] >= ta["end"], (out_a, out_b)
    waits = re.findall(r"^waiting for another viz e2e \(pid (\d+)\)$", out_b, re.M)
    assert len(waits) >= 2 and set(waits) == {str(a.pid)}, out_b       # at once, then again every say_every
    assert lock.read_text() == str(b.pid)                                # the last holder wrote its pid


def test_a_holder_killed_hard_does_not_block_the_next(tmp_path):
    lock = tmp_path / "e2e.lock"
    a = child(lock, 600)
    assert a.stdout.readline().startswith("start")
    os.kill(a.pid, signal.SIGKILL)
    a.wait(timeout=10)
    t = time.monotonic()
    b = child(lock, 0)
    out_b = b.communicate(timeout=30)[0]
    assert "start" in out_b and time.monotonic() - t < 10, out_b


def test_the_lock_file_is_one_fixed_place_outside_home_and_tmpdir(monkeypatch):
    monkeypatch.delenv(e2e_lock.LOCK_ENV, raising=False)
    assert e2e_lock.lock_path() == f"/tmp/jui-viz-e2e-{os.getuid()}.lock"


def test_run_py_takes_the_lock_before_the_browser():
    src = (E2E / "run.py").read_text()
    assert src.index("e2e_lock.hold(") < src.index("asyncio.run(go())")
