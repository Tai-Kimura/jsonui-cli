"""``jui viz start`` (serve in the background) and ``status --json`` with hooks / relay.

The MCP tools (jsonui-mcp-server viz_*) call these, so the round trip is what they rely on: start returns once
the server answers /health with the pid it launched, a second start reports the running one instead of starting
another, and a start that cannot come up stops only the child it launched.

HOME points at a temporary folder in every test, so nothing here reads or writes the real ~/.jsonui-cli or
~/.claude.
"""
from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from jui_cli.commands import viz_cmd

JUI = Path(__file__).resolve().parents[1] / "bin" / "jui"


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert Path.home() == tmp_path
    return tmp_path


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _jui(home: Path, *args: str, env: dict | None = None, timeout: float = 40) -> subprocess.CompletedProcess:
    full = dict(os.environ, HOME=str(home), PYTHONUNBUFFERED="1", **(env or {}))
    return subprocess.run([sys.executable, str(JUI), *args], env=full, capture_output=True, text=True, timeout=timeout)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.fixture()
def stop_after(home):
    """Stops whatever server the test left running in its HOME (by `jui viz stop`, which checks it is ours)."""
    yield
    _jui(home, "viz", "stop")


def test_start_status_open_stop_round_trip(home, stop_after, tmp_path):
    port = _free_port()
    old = home / ".local" / "state" / "jui-viz" / "serve.log"   # a log left by an earlier start, readable by others
    old.parent.mkdir(parents=True)
    old.write_text("earlier run\n" * 700)   # longer than serve writes, so an untruncated log keeps some
    old.chmod(0o644)
    started = _jui(home, "viz", "start", "--port", str(port), "--json")
    assert started.returncode == 0, started.stderr
    info = json.loads(started.stdout)
    assert info["running"] is True and info["alreadyRunning"] is False
    assert info["url"] == f"http://127.0.0.1:{port}/"
    assert _alive(info["pid"])

    log = Path(info["log"])
    assert log == old and stat.S_IMODE(log.stat().st_mode) == 0o600   # recreated on each start, 0600
    assert "earlier run" not in log.read_text()
    token = json.loads((home / ".local" / "state" / "jui-viz" / "server.json").read_text())["token"]
    assert token not in log.read_text() and token not in started.stdout and token not in started.stderr

    status = json.loads(_jui(home, "viz", "status", "--json").stdout)
    assert status["running"] is True and status["pid"] == info["pid"] and status["url"] == info["url"]
    assert status["hooks"]["readable"] is True and status["hooks"]["total"] == 18
    assert "relay" not in status   # only with --with-relay

    # open: the browser is replaced by a script that records the URL it was asked to open.
    seen = tmp_path / "opened.txt"
    browser = tmp_path / "browser.sh"
    browser.write_text(f"#!/bin/sh\necho \"$1\" >> {seen}\n")
    browser.chmod(0o755)
    opened = _jui(home, "viz", "open", env={"BROWSER": f"{browser} %s"})
    assert opened.returncode == 0, opened.stderr
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not seen.exists():
        time.sleep(0.05)
    assert seen.read_text().split() == [info["url"]]

    stopped = _jui(home, "viz", "stop")
    assert stopped.returncode == 0, stopped.stderr
    assert not _alive(info["pid"])
    assert json.loads(_jui(home, "viz", "status", "--json").stdout)["running"] is False
    assert not (home / ".local" / "state" / "jui-viz" / "server.json").exists()


def test_a_second_start_reports_the_running_server(home, stop_after):
    port = _free_port()
    first = json.loads(_jui(home, "viz", "start", "--port", str(port), "--json").stdout)
    log = Path(first["log"])
    log.write_text(log.read_text() + "marker: the running server's log\n")
    second = _jui(home, "viz", "start", "--port", str(port), "--json")
    assert second.returncode == 0, second.stderr
    info = json.loads(second.stdout)
    assert info["alreadyRunning"] is True and info["pid"] == first["pid"] and info["url"] == first["url"]
    # Another port asked for while one runs: still the running one, not a second server.
    third = json.loads(_jui(home, "viz", "start", "--port", str(_free_port()), "--json").stdout)
    assert third["alreadyRunning"] is True and third["pid"] == first["pid"]
    # Reported before anything is launched: the running server's log is not truncated by a second serve.
    assert "marker: the running server's log" in log.read_text()


def test_two_starts_at_once_leave_one_server(home, stop_after):
    env = dict(os.environ, HOME=str(home), PYTHONUNBUFFERED="1")
    ports = [_free_port(), _free_port()]
    procs = [subprocess.Popen([sys.executable, str(JUI), "viz", "start", "--port", str(p), "--json"],
                              env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for p in ports]
    outs = [p.communicate(timeout=40) for p in procs]
    assert [p.returncode for p in procs] == [0, 0], outs
    infos = [json.loads(o[0]) for o in outs]
    assert infos[0]["pid"] == infos[1]["pid"] and infos[0]["url"] == infos[1]["url"], infos
    assert sorted(i["alreadyRunning"] for i in infos) == [False, True], infos
    status = json.loads(_jui(home, "viz", "status", "--json").stdout)
    assert status["pid"] == infos[0]["pid"]
    listening = [p for p in ports if _listening(p)]
    assert len(listening) == 1, f"servers listening on {listening}"


def _listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def test_a_start_on_a_busy_port_fails_and_leaves_the_holder_alone(home):
    holder = socket.socket()
    holder.bind(("127.0.0.1", 0))
    holder.listen()
    port = holder.getsockname()[1]
    try:
        began = time.monotonic()
        res = _jui(home, "viz", "start", "--port", str(port), "--json")
        elapsed = time.monotonic() - began
        assert res.returncode == 1
        # The child's exit is the answer: start does not sit out the whole wait before reporting it.
        assert elapsed < viz_cmd.START_WAIT_SEC, f"{elapsed:.1f}s"
        info = json.loads(res.stdout)
        assert info["running"] is False and "is in use" in info["logTail"], info
        assert not (home / ".local" / "state" / "jui-viz" / "viz.pid").exists()
        assert holder.fileno() != -1   # still ours, still listening
        assert _listening(port)
    finally:
        holder.close()


def test_a_start_that_never_answers_stops_only_its_own_child(home, monkeypatch, capsys):
    """The child never answers /health: after START_WAIT_SEC start signals that child — and only it."""
    bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    monkeypatch.setattr(viz_cmd, "START_WAIT_SEC", 1.5)
    launched = []
    real_popen = subprocess.Popen

    def fake_argv(port):
        return [sys.executable, "-c", "import time; time.sleep(60)"]

    def spy_popen(*a, **k):
        proc = real_popen(*a, **k)
        launched.append(proc)
        return proc

    monkeypatch.setattr(viz_cmd, "_serve_child_argv", fake_argv)
    monkeypatch.setattr(viz_cmd.subprocess, "Popen", spy_popen)
    try:
        code = viz_cmd._cmd_start(type("A", (), {"port": _free_port(), "json": True})())
        info = json.loads(capsys.readouterr().out)
        assert code == 1 and info["running"] is False and "no answer on /health" in info["error"], info
        assert len(launched) == 1 and launched[0].poll() is not None, "its own child was not stopped"
        assert bystander.poll() is None, "a process it did not launch was signalled"
    finally:
        for proc in launched:
            if proc.poll() is None:
                proc.kill()
        bystander.kill()
        bystander.wait()


def test_status_with_relay_asks_claude_only_when_asked(home, tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "claude-calls.txt"
    fake = bin_dir / "claude"
    fake.write_text(f"#!/bin/sh\necho \"$@\" >> {calls}\nexit 0\n")
    fake.chmod(0o755)
    env = {"PATH": f"{bin_dir}:{os.environ['PATH']}"}
    plain = json.loads(_jui(home, "viz", "status", "--json", env=env).stdout)
    assert "relay" not in plain and not calls.exists()
    asked = json.loads(_jui(home, "viz", "status", "--json", "--with-relay", env=env).stdout)
    assert asked["relay"] == {"registered": True}
    assert calls.read_text().split() == ["mcp", "get", "jui-viz"]
    no_claude = json.loads(_jui(home, "viz", "status", "--json", "--with-relay", env={"PATH": "/usr/bin:/bin"}).stdout)
    assert no_claude["relay"]["registered"] is None and "claude" in no_claude["relay"]["reason"]
