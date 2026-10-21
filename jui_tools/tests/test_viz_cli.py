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
        if (home / ".local" / "state" / "jui-viz" / "server.json").exists():
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
    assert paths.pid_file() == home / ".local" / "state" / "jui-viz" / "viz.pid"
    assert paths.server_json().parent == paths.viz_home()
    assert paths.claude_settings() == home / ".claude" / "settings.json"


def test_status_when_nothing_runs(home, capsys):
    assert main(["viz", "status"]) == 0
    assert "jui viz: stopped" in capsys.readouterr().out
    assert main(["viz", "status", "--json"]) == 0
    info = json.loads(capsys.readouterr().out)
    # hooks: the installer's state, so `status --json` alone tells a caller (the MCP viz_status) what is missing.
    assert info.pop("hooks") == {"readable": True, "installed": 0, "total": 18, "broken": 0, "plugin": None,
                                 "disableAllHooks": False}
    assert info == {"running": False}


def test_status_and_stop_clear_files_left_by_a_dead_server(home, capsys):
    for command in (["viz", "status"], ["viz", "stop"]):
        paths.viz_home().mkdir(parents=True, exist_ok=True)
        paths.pid_file().write_text(str(_dead_pid()))
        paths.server_json().write_text(json.dumps({"pid": 1, "port": 1, "token": "x"}))
        assert main(command) == 0
        assert not paths.pid_file().exists() and not paths.server_json().exists(), command
    capsys.readouterr()


def test_a_pid_that_now_belongs_to_another_process_is_never_signalled(home, capsys):
    """After a crash the pid in the files can be reused. stop must check that
    the process really is a viz server (its /health answers with that pid)."""
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        paths.viz_home().mkdir(parents=True, exist_ok=True)
        for with_server_json in (True, False):
            paths.pid_file().write_text(str(other.pid))
            if with_server_json:
                paths.server_json().write_text(json.dumps({"pid": other.pid, "port": _free_port(), "token": "t"}))
            else:
                old = time.time() - 3600  # a leftover, not a serve still starting
                os.utime(paths.pid_file(), (old, old))
            assert main(["viz", "stop"]) == 0
            assert "not running" in capsys.readouterr().out
            assert other.poll() is None, "stop signalled a process that is not viz"
            assert not paths.pid_file().exists() and not paths.server_json().exists()
    finally:
        other.terminate()  # our own child
        other.wait(timeout=10)


@pytest.mark.parametrize("text", ["0", "-1", " -1 ", "1", "+5", "abc", ""])
def test_a_broken_pid_file_is_cleared_and_nothing_is_signalled(home, capsys, monkeypatch, text):
    signalled = []
    real_kill = os.kill
    monkeypatch.setattr(os, "kill", lambda pid, sig: signalled.append((pid, sig)) or real_kill(os.getpid(), 0))
    paths.viz_home().mkdir(parents=True, exist_ok=True)
    paths.pid_file().write_text(text)
    paths.server_json().write_text(json.dumps({"pid": 0, "port": 1}))
    assert main(["viz", "stop"]) == 0
    assert signalled == []
    assert not paths.pid_file().exists() and not paths.server_json().exists()


def test_stop_waits_out_a_serve_that_is_still_starting(home, capsys):
    """viz.pid freshly taken by a live process, no server.json yet: starting."""
    paths.viz_home().mkdir(parents=True, exist_ok=True)
    paths.pid_file().write_text(str(os.getpid()))  # alive: this test process
    assert main(["viz", "stop"]) == 1
    assert "still starting" in capsys.readouterr().err
    assert paths.pid_file().exists()  # nothing was signalled or removed


def test_open_without_a_server_is_a_usage_error(home, capsys):
    assert main(["viz", "open"]) == 1
    assert "not running" in capsys.readouterr().err


def test_relay_without_an_action_prints_usage(home, capsys):
    assert main(["viz", "relay"]) == 1
    assert "usage: jui viz" in capsys.readouterr().err


def test_relay_install_shows_the_command_and_asks_first(home, capsys, monkeypatch, tmp_path):
    calls = tmp_path / "calls"
    fake = tmp_path / "bin" / "claude"
    fake.parent.mkdir()
    fake.write_text(f"#!/bin/sh\necho \"$@\" >> {calls}\nexit 0\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake.parent))
    assert main(["viz", "relay", "install", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "mcp add --scope user jui-viz --" in out and "channel.py" in out
    assert not calls.exists()  # dry-run ran nothing
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert main(["viz", "relay", "install"]) == 1 and not calls.exists()
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    assert main(["viz", "relay", "install"]) == 0
    assert "mcp add --scope user jui-viz -- " in calls.read_text()
    assert "--dangerously-load-development-channels server:jui-viz" in capsys.readouterr().out
    assert main(["viz", "relay", "uninstall", "--yes"]) == 0
    assert "mcp remove --scope user jui-viz" in calls.read_text()


def test_hooks_without_an_action_prints_usage(home, capsys):
    assert main(["viz", "hooks"]) == 1
    assert "usage: jui viz" in capsys.readouterr().err


def test_hooks_install_status_uninstall_through_the_cli(home, capsys):
    assert main(["viz", "hooks", "install", "--dry-run"]) == 0
    assert not paths.claude_settings().exists()
    assert main(["viz", "hooks", "install"]) == 0
    assert "(18 events:" in capsys.readouterr().out
    assert main(["viz", "hooks", "status", "--json"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["installed"] == 18 and info["broken"] == []
    assert main(["viz", "hooks", "uninstall"]) == 0
    assert json.loads(paths.claude_settings().read_text()) == {}
    paths.claude_settings().write_text("{broken")
    assert main(["viz", "hooks", "install"]) == 1
    assert "cannot be read as JSON" in capsys.readouterr().err


def test_broken_config_warns_and_falls_back_to_defaults(home, capsys):
    from jui_cli.viz.config import load_config

    paths.viz_home().mkdir(parents=True, exist_ok=True)
    paths.config_json().write_text("{broken")
    assert load_config().port == 7788
    assert "the defaults are used" in capsys.readouterr().err
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
        assert f"port {port} is in use" in capsys.readouterr().err
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
        assert "it is running (jui viz stop stops it)" in second.stderr
        assert proc.poll() is None

        status = subprocess.run(
            [sys.executable, str(JUI), "viz", "status", "--json"],
            env=dict(os.environ, HOME=str(home)), capture_output=True, text=True, timeout=30,
        )
        info = json.loads(status.stdout)
        assert info.pop("hooks")["total"] == 18
        assert info == {"running": True, "pid": proc.pid, "url": base + "/"}

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
    assert f"listening on http://127.0.0.1:{port}/" in out
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


# ---- TERM ends the server within 3 s, with code 0 (ticket 2026-10-21-jui-viz-serve-does-not-exit-on-term) ----------
# A stop that waited for the slowest thing in the process: aiohttp's 60 s for a request still being handled, asyncio.run's
# join of every executor job, a pool's job at the interpreter's exit, the talk index's step. Each case below holds one.

TERM_WITHIN_SEC = 3
#: nothing busy in the process: it ends without the helpers' grace (measured 0.05 s; the grace is 1 s)
IDLE_WITHIN_SEC = 0.9
#: a job that takes 20 s, put on one pool before serve starts (the code under test is not changed)
SLOW_JOB = {   # name: (the patch, seconds until it runs, the thread left busy, named in the log)
    "the loop's executor (a shelf rescan)": (
        "import time; from jui_cli.viz.sources import test_results as T; o = T.ResultShelf.scan; n = [0]\n"
        "def slow(self):\n    n[0] += 1\n    if n[0] > 1: time.sleep(20)\n    return o(self)\nT.ResultShelf.scan = slow", 6, "jui-viz-serve_"),
    "the talk index's step": (
        "import time; from jui_cli.viz import talk as T; o = T.TalkHub._step\n"
        "def slow(self, now):\n    time.sleep(20); return o(self, now)\nT.TalkHub._step = slow", 4, "jui-viz-talk_"),
    "the price table's read": (
        "import time; from jui_cli.viz import prices as P; o = P.PriceBook._load\n"
        "def slow(self):\n    time.sleep(20); return o(self)\nP.PriceBook._load = slow", 2, "jui-viz-prices_"),
}


def _serve_as(home: Path, port: int, patch: str = "", claude_sleep: float = 0) -> subprocess.Popen:
    """serve in a child with a stand-in `claude` first on PATH (its `agents --json` answers after claude_sleep s) and
    patch run first; started once server.json is there."""
    bin_dir = home / "stand-in-bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "claude").write_text(f"#!/bin/sh\nsleep {claude_sleep}\necho '[]'\n")
    (bin_dir / "claude").chmod(0o755)
    code = (f"import sys; sys.argv = ['jui', 'viz', 'serve', '--port', '{port}']; sys.path.insert(0, {str(JUI.parents[1])!r}); "
            + (f"exec({patch!r}); " if patch else "") + "from jui_cli.cli import main; sys.exit(main())")
    env = dict(os.environ, HOME=str(home), PYTHONUNBUFFERED="1", PATH=f"{bin_dir}:{os.environ['PATH']}")
    proc = subprocess.Popen([sys.executable, "-c", code], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if paths.server_json().exists():
            return proc
        if proc.poll() is not None:
            break
        time.sleep(0.05)
    proc.kill()
    out, err = proc.communicate()
    raise AssertionError(f"serve did not start: rc={proc.returncode}\n{out}\n{err}")


def _term_ends_it(proc: subprocess.Popen, err_out: list | None = None) -> float:
    """TERM; it must end with 0 within TERM_WITHIN_SEC, its files cleared. How long it took (its stderr into err_out)."""
    start = time.monotonic()
    proc.terminate()  # our own child
    try:
        rc = proc.wait(timeout=TERM_WITHIN_SEC)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise AssertionError(f"TERM did not end serve within {TERM_WITHIN_SEC} s")
    took = time.monotonic() - start
    out, err = proc.communicate()
    assert rc == 0, err
    assert not paths.server_json().exists() and not paths.pid_file().exists()
    if err_out is not None:
        err_out.append(err)
    return took


def test_term_right_after_closed_connections_ends_it(home):
    port = _free_port()
    proc = _serve_as(home, port)
    token = json.loads(paths.server_json().read_text())["token"]
    for _ in range(3):
        req = urllib.request.Request(f"http://127.0.0.1:{port}/hook", data=b"{}", method="POST",
                                     headers={"X-Jui-Viz-Token": token, "Connection": "close"})
        with urllib.request.urlopen(req, timeout=5) as res:
            assert res.status == 204
    assert _term_ends_it(proc) < IDLE_WITHIN_SEC   # nothing busy: nothing waited for (the pools' idle threads go at once)


def test_term_while_the_session_list_is_being_read_ends_it(home):
    """`claude agents --json` still running (the stand-in answers after 30 s)."""
    proc = _serve_as(home, _free_port(), claude_sleep=30)
    time.sleep(1.5)
    assert _term_ends_it(proc) < IDLE_WITHIN_SEC


def test_term_while_a_hook_is_being_read_ends_it(home):
    """A hook whose body is promised and not all sent: the request is still being handled."""
    port = _free_port()
    proc = _serve_as(home, port)
    token = json.loads(paths.server_json().read_text())["token"]
    with socket.create_connection(("127.0.0.1", port)) as held:
        held.sendall((f"POST /hook HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nX-Jui-Viz-Token: {token}\r\n"
                      "Content-Type: application/json\r\nContent-Length: 1000\r\n\r\n{").encode())
        time.sleep(0.5)
        _term_ends_it(proc)


@pytest.mark.parametrize("where", list(SLOW_JOB))
def test_term_while_a_pool_job_runs_ends_it(home, where):
    patch, settle, thread = SLOW_JOB[where]
    proc = _serve_as(home, _free_port(), patch=patch)
    time.sleep(settle)   # the slow job is under way
    err: list = []
    _term_ends_it(proc, err)
    # the thread not waited for is named on stderr (what `jui viz start` keeps in serve.log)
    left = [line for line in err[0].splitlines() if "stopped; not waited for:" in line]
    assert len(left) == 1 and thread in left[0], err[0][-2000:]


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
        assert f"port {port} is in use" in done.stderr
    finally:
        holder.close()


def test_two_serves_started_together_leave_exactly_one_running(home):
    """Each checked "not running" and then bound its own port: both ran, and
    one was left with no files naming it. The lock is taken before binding."""
    env = dict(os.environ, HOME=str(home))
    procs = [subprocess.Popen([sys.executable, str(JUI), "viz", "serve", "--port", str(_free_port()), "--no-agents-poll"],
                              env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not (paths.server_json().exists() and any(p.poll() is not None for p in procs)):
            time.sleep(0.05)
        running = [p for p in procs if p.poll() is None]
        assert len(running) == 1, [p.poll() for p in procs]
        refused = next(p for p in procs if p.poll() is not None)
        assert refused.returncode == 1 and "it is running" in refused.communicate()[1]
        assert json.loads(paths.server_json().read_text())["pid"] == running[0].pid
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()  # our own children
                p.wait(timeout=10)


def test_malformed_requests_are_one_line_each_on_stderr(home):
    port = _free_port()
    proc = _start_serve(home, port)
    try:
        for raw in (b"GET / HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nHost: example.com\r\n\r\n" % port,
                    b"POST /hook HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nX-Jui-Viz-Token: \xff\xfe\r\nContent-Length: 2\r\n\r\n{}" % port):
            with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
                s.sendall(raw)
                status = s.recv(64).split(b" ")[1]
                assert status in (b"400", b"401"), status
    finally:
        proc.terminate()  # our own child
        proc.wait(timeout=10)
    _, err = proc.communicate()
    assert "Traceback" not in err
    # Count the request lines, not the whole stderr: how many startup notes serve prints depends on the
    # machine (CI has no ~/.claude/sessions, no adb and no xcrun — one note each), and a total of <= 5
    # went red there for 2.0.0 while the requests themselves logged one line each.
    lines = err.strip().splitlines()
    assert all(line.startswith("jui viz: ") for line in lines), err
    assert len([line for line in lines if "拒否" in line]) <= 2, err


def test_a_proxy_variable_does_not_make_a_live_server_look_dead(home):
    """/health went through urllib, which follows HTTP_PROXY: status then
    removed a live server's files (review, 10-18)."""
    port = _free_port()
    proc = _start_serve(home, port)
    try:
        env = dict(os.environ, HOME=str(home), HTTP_PROXY="http://127.0.0.1:9", http_proxy="http://127.0.0.1:9")
        env.pop("NO_PROXY", None)
        env.pop("no_proxy", None)
        done = subprocess.run([sys.executable, str(JUI), "viz", "status", "--json"], env=env,
                              capture_output=True, text=True, timeout=30)
        assert json.loads(done.stdout)["running"] is True
        assert paths.server_json().exists() and paths.pid_file().exists()
    finally:
        proc.terminate()  # our own child
        proc.wait(timeout=10)
        proc.communicate()


def test_a_server_that_does_not_answer_is_neither_signalled_nor_forgotten(home, capsys):
    """Something listens on the port but never answers /health: cannot tell,
    so keep the files and send nothing."""
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    mute = socket.socket()
    mute.bind(("127.0.0.1", 0))
    mute.listen(5)
    try:
        paths.viz_home().mkdir(parents=True, exist_ok=True)
        paths.pid_file().write_text(str(other.pid))
        paths.server_json().write_text(json.dumps({"pid": other.pid, "port": mute.getsockname()[1], "token": "t"}))
        assert main(["viz", "stop"]) == 1
        assert "does not answer /health" in capsys.readouterr().err
        assert other.poll() is None
        assert paths.pid_file().exists() and paths.server_json().exists()
    finally:
        mute.close()
        other.terminate()  # our own child
        other.wait(timeout=10)


def test_doctor_reports_each_check(home, capsys, monkeypatch):
    monkeypatch.setenv("PATH", "")  # no claude: reported, not a crash
    rc = main(["viz", "doctor", "--json"])
    data = json.loads(capsys.readouterr().out)
    names = {c["name"] for c in data["checks"]}
    assert {"python", "aiohttp", "watchdog", "claude", "server"} <= names
    claude = next(c for c in data["checks"] if c["name"] == "claude")
    assert claude["ok"] is False and "PATH" in claude["detail"]
    assert rc == 1 and data["ok"] is False
