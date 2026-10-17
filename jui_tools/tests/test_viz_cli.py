"""``jui viz`` serve / status / stop / open / doctor (jui_cli/commands/viz_cmd.py).

HOME points at a temporary folder in every test, so nothing here reads or
writes the real ~/.jsonui-cli or ~/.claude.
"""
from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from jui_cli.cli import main
from jui_cli.viz import paths

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


def _dead_pid() -> int:
    """A pid that existed and has exited (our own reaped child)."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def _start_serve(home: Path, port: int) -> subprocess.Popen:
    env = dict(os.environ, HOME=str(home), PYTHONUNBUFFERED="1")
    proc = subprocess.Popen(
        [sys.executable, str(JUI), "viz", "serve", "--port", str(port)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if (home / ".jsonui-cli" / "viz" / "server.json").exists():
            return proc
        if proc.poll() is not None:
            break
        time.sleep(0.05)
    proc.kill()
    out, err = proc.communicate()
    raise AssertionError(f"serve did not start: rc={proc.returncode}\n{out}\n{err}")


def _get(url: str, headers: dict | None = None) -> int:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.status
    except urllib.error.HTTPError as exc:
        exc.close()
        return exc.code


def test_paths_follow_home_at_call_time(home):
    assert paths.pid_file() == home / ".jsonui-cli" / "viz" / "viz.pid"
    assert paths.server_json().parent == paths.viz_home()
    assert paths.claude_settings() == home / ".claude" / "settings.json"


def test_status_when_nothing_runs(home, capsys):
    assert main(["viz", "status"]) == 0
    assert "停止中" in capsys.readouterr().out
    assert main(["viz", "status", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"running": False}


def test_status_and_stop_clear_files_left_by_a_dead_server(home, capsys):
    for command in (["viz", "status"], ["viz", "stop"]):
        paths.viz_home().mkdir(parents=True, exist_ok=True)
        paths.pid_file().write_text(str(_dead_pid()))
        paths.server_json().write_text(json.dumps({"pid": 1, "port": 1, "token": "x"}))
        assert main(command) == 0
        assert not paths.pid_file().exists() and not paths.server_json().exists(), command
    capsys.readouterr()


def test_stop_refuses_when_the_pid_files_disagree(home, capsys):
    paths.viz_home().mkdir(parents=True, exist_ok=True)
    paths.pid_file().write_text(str(os.getpid()))  # alive: this test process
    paths.server_json().write_text(json.dumps({"pid": os.getpid() + 1, "port": 1}))
    assert main(["viz", "stop"]) == 1
    assert "食い違う" in capsys.readouterr().err
    assert paths.pid_file().exists()  # nothing was signalled or removed


def test_open_without_a_server_is_a_usage_error(home, capsys):
    assert main(["viz", "open"]) == 1
    assert "起動していません" in capsys.readouterr().err


@pytest.mark.parametrize("sub", ["hooks", "relay"])
def test_later_phase_commands_say_so_and_exit_1(home, capsys, sub):
    assert main(["viz", sub]) == 1
    assert "実装予定" in capsys.readouterr().err


def test_broken_config_warns_and_falls_back_to_defaults(home, capsys):
    from jui_cli.viz.config import load_config

    paths.viz_home().mkdir(parents=True, exist_ok=True)
    paths.config_json().write_text("{broken")
    assert load_config().port == 7788
    assert "既定値" in capsys.readouterr().err
    paths.config_json().write_text(json.dumps({"port": 9100, "pushIntervalMs": True, "x": 1}))
    config = load_config()
    assert config.port == 9100
    assert config.pushIntervalMs == 200  # a bool is not a number here
    assert "pushIntervalMs" in capsys.readouterr().err


def test_serve_stays_off_a_port_in_use_and_leaves_its_owner_alone(home, capsys):
    holder = socket.socket()
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    port = holder.getsockname()[1]
    try:
        assert main(["viz", "serve", "--port", str(port)]) == 1
        assert f"ポート {port} は使用中です" in capsys.readouterr().err
        assert holder.fileno() != -1
        holder.getsockname()  # still open and listening
        assert not paths.pid_file().exists() and not paths.server_json().exists()
    finally:
        holder.close()


def test_serve_end_to_end(home):
    port = _free_port()
    proc = _start_serve(home, port)
    try:
        info = json.loads(paths.server_json().read_text())
        token = info["token"]
        assert info["pid"] == proc.pid and info["port"] == port
        assert stat.S_IMODE(paths.server_json().stat().st_mode) == 0o600
        assert int(paths.pid_file().read_text()) == proc.pid

        base = f"http://127.0.0.1:{port}"
        assert _get(base + "/") == 200
        assert _get(base + "/", {"Host": "example.com"}) == 421
        assert _get(base + "/health") == 200

        # A second serve refuses and leaves the first one running.
        second = subprocess.run(
            [sys.executable, str(JUI), "viz", "serve", "--port", str(_free_port())],
            env=dict(os.environ, HOME=str(home)), capture_output=True, text=True, timeout=30,
        )
        assert second.returncode == 1
        assert "起動中です（jui viz stop で止める）" in second.stderr
        assert proc.poll() is None

        status = subprocess.run(
            [sys.executable, str(JUI), "viz", "status", "--json"],
            env=dict(os.environ, HOME=str(home)), capture_output=True, text=True, timeout=30,
        )
        assert json.loads(status.stdout) == {"running": True, "pid": proc.pid, "url": base + "/"}

        # serve is this test's child: until we reap it, it lingers as a zombie
        # that `stop` would still see as alive. A shell reaps it at once, so
        # reap here while stop is waiting, as the shell would.
        stop_proc = subprocess.Popen(
            [sys.executable, str(JUI), "viz", "stop"],
            env=dict(os.environ, HOME=str(home)), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        assert proc.wait(timeout=10) == 0
        stop_out, stop_err = stop_proc.communicate(timeout=30)
        stop = subprocess.CompletedProcess(stop_proc.args, stop_proc.returncode, stop_out, stop_err)
        assert stop.returncode == 0, stop.stderr
        assert not paths.server_json().exists() and not paths.pid_file().exists()
    finally:
        if proc.poll() is None:
            proc.terminate()  # our own child
            proc.wait(timeout=10)
    out, err = proc.communicate()
    assert f"http://127.0.0.1:{port}/ で待ち受けています" in out
    for text in (out, err, second.stdout, second.stderr, status.stdout, stop.stdout, stop.stderr):
        assert token not in text


def test_serve_restarts_on_the_same_port_right_after_stop(home):
    """The last run's closed connections sit in TIME_WAIT on the server's
    port; a restart must not be refused for them (it was, for about a
    minute, while SO_REUSEADDR was off)."""
    port = _free_port()
    proc = _start_serve(home, port)
    token = json.loads(paths.server_json().read_text())["token"]
    for _ in range(3):  # connections the server closes first -> TIME_WAIT on its side
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/hook", data=b"{}", method="POST",
            headers={"X-Jui-Viz-Token": token, "Connection": "close"},
        )
        with urllib.request.urlopen(req, timeout=5) as res:
            assert res.status == 204
    proc.terminate()  # our own child
    assert proc.wait(timeout=10) == 0
    proc.communicate()
    again = _start_serve(home, port)
    try:
        assert _get(f"http://127.0.0.1:{port}/health") == 200
    finally:
        again.terminate()
        again.wait(timeout=10)
        again.communicate()


def test_serve_refuses_a_port_another_process_listens_on_all_addresses(home):
    """0.0.0.0:<port> held elsewhere: with SO_REUSEADDR macOS would let us
    bind 127.0.0.1:<port> beside it, so serve must notice and stop."""
    holder = socket.socket()
    holder.bind(("0.0.0.0", 0))
    holder.listen(1)
    port = holder.getsockname()[1]
    try:
        # A subprocess with a deadline: if serve wrongly binds, it runs on
        # instead of returning, and that must read as a failure, not a hang.
        try:
            done = subprocess.run(
                [sys.executable, str(JUI), "viz", "serve", "--port", str(port)],
                env=dict(os.environ, HOME=str(home)), capture_output=True, text=True, timeout=15,
            )
        except subprocess.TimeoutExpired:
            raise AssertionError("serve bound beside a 0.0.0.0 listener and kept running")
        assert done.returncode == 1
        assert f"ポート {port} は使用中です" in done.stderr
    finally:
        holder.close()


def test_doctor_reports_each_check(home, capsys, monkeypatch):
    monkeypatch.setenv("PATH", "")  # no claude: reported, not a crash
    rc = main(["viz", "doctor", "--json"])
    data = json.loads(capsys.readouterr().out)
    names = {c["name"] for c in data["checks"]}
    assert {"python", "aiohttp", "watchdog", "claude", "server"} <= names
    claude = next(c for c in data["checks"] if c["name"] == "claude")
    assert claude["ok"] is False and "PATH" in claude["detail"]
    assert rc == 1 and data["ok"] is False
