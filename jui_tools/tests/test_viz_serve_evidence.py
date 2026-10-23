"""What a stuck viz server leaves behind (tickets 2026-10-24-viz-serve-stops-answering-after-setsockopt-einval and
2026-10-24-viz-start-overwrites-serve-log).

On 10-24 the real server stopped answering /health and was killed; its serve.log ended in aiohttp's keep-alive
setsockopt raising EINVAL (measured: the effect of clients that gave up while the loop stood still, the same on
2.3.20 and 2.3.21, never the cause), and the start that followed wrote over the log. Now:

- connections the client already reset leave no traceback, and the server answers after them;
- `start` keeps the last run's serve.log as serve.log.1 (up to SERVE_LOG_KEEP), and `stop` keeps the log of a
  server it had to force;
- USR1 writes every thread's stack to the log and the server goes on; `stop` sends it before a KILL;
- a watch thread writes one line (the connections open, the last request, the ones being handled) and the stacks
  when the loop has not run for a while, once each time it stands still.

HOME points at a temporary folder in every test, the ports are free ones, and the real server is never touched.
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import socket
import struct
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from jui_cli.commands import viz_cmd
from jui_cli.viz import loop_watch
from tests.test_viz_server_lifecycle import _alive, _free_port, _jui, home  # noqa: F401 - the fixture


def _log_dir(home: Path) -> Path:
    return home / ".local" / "state" / "jui-viz"


def _start(home: Path) -> tuple[int, int]:
    port = _free_port()
    r = _jui(home, "viz", "start", "--port", str(port), "--json")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["pid"], port


def _health(port: int) -> int:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as response:
        return response.status


def _stop(home: Path, pid: int) -> None:
    _jui(home, "viz", "stop", timeout=60)
    if _alive(pid):
        os.kill(pid, signal.SIGKILL)


# ---------------------------------------------------------------- the log of the run before


def test_keep_serve_log_moves_each_older_log_up_and_drops_the_oldest(home):
    folder = _log_dir(home)
    folder.mkdir(parents=True)
    (folder / "serve.log").write_text("run 0\n")
    for n in range(1, viz_cmd.SERVE_LOG_KEEP + 1):
        (folder / f"serve.log.{n}").write_text(f"run {n}\n")
    assert viz_cmd._keep_serve_log() == folder / "serve.log.1"
    assert not (folder / "serve.log").exists()
    assert [(folder / f"serve.log.{n}").read_text() for n in range(1, viz_cmd.SERVE_LOG_KEEP + 1)] == \
        [f"run {n - 1}\n" for n in range(1, viz_cmd.SERVE_LOG_KEEP + 1)]
    assert not (folder / f"serve.log.{viz_cmd.SERVE_LOG_KEEP + 1}").exists()
    (folder / "serve.log").write_text("")   # an empty log is not worth a place
    assert viz_cmd._keep_serve_log() is None and (folder / "serve.log.1").read_text() == "run 0\n"


def test_a_start_keeps_the_last_runs_log(home):
    first, _ = _start(home)
    _stop(home, first)
    second, _ = _start(home)
    try:
        kept = (_log_dir(home) / "serve.log.1").read_text()
        assert f"started (pid {first})" in kept, kept
        assert f"started (pid {first})" not in (_log_dir(home) / "serve.log").read_text()
    finally:
        _stop(home, second)


def test_stop_keeps_the_log_of_a_server_it_had_to_force(home):
    pid, _ = _start(home)
    os.kill(pid, signal.SIGSTOP)                                  # alive, listening, never answers
    try:
        r = _jui(home, "viz", "stop", timeout=60)
        assert r.returncode == 0, r.stderr
        kept = _log_dir(home) / "serve.log.1"
        assert str(kept) in r.stdout, r.stdout
        assert f"started (pid {pid})" in kept.read_text()
        assert not (_log_dir(home) / "serve.log").exists()
    finally:
        if _alive(pid):
            os.kill(pid, signal.SIGKILL)


# ---------------------------------------------------------------- connections reset before they were taken


def test_connections_reset_before_they_were_taken_leave_no_traceback(home):
    pid, port = _start(home)
    try:
        os.kill(pid, signal.SIGSTOP)                              # the loop stands still, as on 10-24
        reset = 0
        try:
            for _ in range(60):
                s = socket.socket()
                s.settimeout(1)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                try:
                    s.connect(("127.0.0.1", port))
                    reset += 1
                except OSError:
                    pass
                s.close()
        finally:
            os.kill(pid, signal.SIGCONT)
        assert reset >= 20
        time.sleep(1)
        assert _health(port) == 200
        log = (_log_dir(home) / "serve.log").read_text()
        assert "Errno 22" not in log and "Exception in callback" not in log, log[-2000:]
    finally:
        _stop(home, pid)


# ---------------------------------------------------------------- the stacks


def test_usr1_writes_every_threads_stack_and_the_server_goes_on(home):
    pid, port = _start(home)
    try:
        os.kill(pid, signal.SIGUSR1)
        log = _log_dir(home) / "serve.log"
        for _ in range(50):
            if "run_forever" in log.read_text():                   # the loop's own stack is among them
                break
            time.sleep(0.1)
        text = log.read_text()
        assert "run_forever" in text and "jui-viz-loop-watch" in text, text[-2000:]
        assert _health(port) == 200 and _alive(pid)
    finally:
        _stop(home, pid)


def test_the_watch_writes_a_line_and_the_stacks_once_while_the_loop_stands_still_and_a_line_when_the_loop_runs_again(tmp_path):
    out_path = tmp_path / "out.log"

    async def main(out) -> None:
        loop = asyncio.get_running_loop()
        watch = loop_watch.LoopWatch(loop, lambda now: "2 connections open; last request: GET /api/x", after_sec=0.3,
                                 beat_sec=0.05, out=out)
        watch.start()
        await asyncio.sleep(0.2)
        time.sleep(1.0)            # the loop stands still
        await asyncio.sleep(0.4)
        watch.stop()

    with out_path.open("w") as out:
        asyncio.run(main(out))
    text = out_path.read_text()
    assert text.count("the loop has not run for") == 1, text
    assert "2 connections open; last request: GET /api/x; every thread's stack:" in text
    assert "time.sleep" in text or "in main" in text, text           # the stuck loop's own frame
    assert text.count("the loop runs again, after") == 1, text


def test_request_notes_say_the_last_request_and_the_ones_being_handled():
    notes = loop_watch.RequestNotes()
    middleware = notes.middleware()
    assert notes.describe(time.monotonic()) == "last request: no request yet; being handled: 0"
    seen = {}

    async def handler(request):
        seen["during"] = notes.describe(time.monotonic())
        return "ok"

    asyncio.run(middleware(SimpleNamespace(method="GET", path="/api/snapshot"), handler))
    assert "last request: GET /api/snapshot" in seen["during"] and "(not answered)" in seen["during"]
    assert "being handled: 1 (GET /api/snapshot for" in seen["during"]
    after = notes.describe(time.monotonic())
    assert "GET /api/snapshot" in after and "(answered)" in after and after.endswith("being handled: 0"), after
