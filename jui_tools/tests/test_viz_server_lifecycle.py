"""The viz server's own folder and `jui viz stop` (10-18, 2.3.1).

- The server leaves the folder it was launched from: that folder can be deleted (a git worktree removed), and
  every child it starts — `claude agents --json` first — inherits the cwd and exits 1 in a deleted folder.
- `stop` stops a server of this HOME that no longer answers /health (its pid file, its command line `viz serve`
  and its HOME agree), and sends KILL when TERM has not ended it in STOP_TERM_SEC; it never signals a pid that is
  not our `viz serve`.

HOME points at a temporary folder in every test, the ports are free ones, and the real server is never touched.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from jui_cli.commands import viz_cmd

JUI = Path(__file__).resolve().parents[1] / "bin" / "jui"
FORWARD = Path(__file__).resolve().parents[1] / "jui_cli" / "viz" / "forward.py"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _env(home: Path, **extra) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env.update(HOME=str(home), PYTHONUNBUFFERED="1", **extra)
    return env


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _jui(home: Path, *args: str, cwd: Path | None = None, timeout: float = 40, **extra) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(JUI), *args], env=_env(home, **extra), cwd=str(cwd or home),
                          capture_output=True, text=True, timeout=timeout)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _cwd_of(pid: int) -> str:
    out = subprocess.run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"], capture_output=True, text=True).stdout
    names = [line[1:] for line in out.splitlines() if line.startswith("n")]
    return names[0] if names else ""


def _snapshot(port: int, home: Path) -> dict:
    url = f"http://127.0.0.1:{port}"
    token = re.search(r'name="jui-viz-token" content="([^"]+)"', urllib.request.urlopen(url + "/").read().decode()).group(1)
    return json.loads(urllib.request.urlopen(urllib.request.Request(url + "/api/snapshot", headers={"X-Jui-Viz-Token": token})).read())


def _fake_claude(folder: Path) -> Path:
    """`claude` that answers `agents --json` with [] — and exits 1 when its cwd was deleted, as the real one does."""
    folder.mkdir(parents=True, exist_ok=True)
    script = folder / "claude"
    script.write_text(f"#!{sys.executable}\nimport os, sys\ntry:\n    os.getcwd()\nexcept OSError:\n    sys.exit(1)\nprint('[]')\n")
    script.chmod(0o755)
    return folder


@pytest.fixture()
def stop_after(home):
    yield
    _jui(home, "viz", "stop")


# ---------------------------------------------------------------- the server's own folder

def test_a_started_server_lives_in_its_own_folder_and_keeps_its_agents_source_when_the_launch_folder_goes(home, stop_after):
    launch = home / "worktree"
    launch.mkdir()
    bin_dir = _fake_claude(home / "fakebin")
    port = _free_port()
    started = _jui(home, "viz", "start", "--port", str(port), "--json", cwd=launch, PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    assert started.returncode == 0, started.stderr
    pid = json.loads(started.stdout)["pid"]
    shutil.rmtree(launch)                                         # the worktree is removed
    assert Path(_cwd_of(pid)).resolve() == (home / ".local" / "state" / "jui-viz").resolve()
    time.sleep(7)                                                 # two polls of `claude agents` (every 3 s)
    agents = _snapshot(port, home)["slices"]["server"]["sources"]["agents"]
    assert agents["status"] == "running", agents


def test_serve_in_the_foreground_leaves_the_launch_folder_too(home):
    launch = home / "worktree"
    launch.mkdir()
    port = _free_port()
    p = subprocess.Popen([sys.executable, str(JUI), "viz", "serve", "--port", str(port), "--no-agents-poll"],
                         env=_env(home), cwd=str(launch), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        assert Path(_cwd_of(p.pid)).resolve() == (home / ".local" / "state" / "jui-viz").resolve()
    finally:
        p.terminate()
        p.wait(10)


# ---------------------------------------------------------------- stop

def test_stop_ends_a_server_holding_a_page_and_a_waiting_hook_without_kill(home):
    """The orchestrator's arm: a WebSocket from a visible page and a --decide hook waiting on it; stop ends it within TERM."""
    port = _free_port()
    started = _jui(home, "viz", "start", "--port", str(port), "--json")
    assert started.returncode == 0, started.stderr
    pid = json.loads(started.stdout)["pid"]
    url = f"http://127.0.0.1:{port}"
    token = re.search(r'name="jui-viz-token" content="([^"]+)"', urllib.request.urlopen(url + "/").read().decode()).group(1)

    async def hold_and_stop():
        import aiohttp
        async with aiohttp.ClientSession() as session:
            ws = await session.ws_connect(url + "/ws", headers={"Origin": url})
            await ws.send_json({"type": "auth", "token": token})
            await ws.receive(timeout=5)
            await ws.send_json({"type": "presence", "visible": True})
            await asyncio.sleep(0.3)
            body = {"hook_event_name": "PermissionRequest", "session_id": "0a0a0a0a-1111-4111-8111-aaaaaaaaaaaa",
                    "cwd": str(home), "tool_name": "Bash", "tool_input": {"command": "ls"}}
            threading.Thread(target=lambda: subprocess.run([sys.executable, "-I", "-S", str(FORWARD), "--decide"],
                             input=json.dumps(body).encode(), capture_output=True, env=_env(home), timeout=60), daemon=True).start()
            for _ in range(40):
                await asyncio.sleep(0.1)
                perms = _snapshot(port, home)["slices"]["perms"]
                if perms and perms[0]["can"]["allowDeny"]:
                    break
            assert perms and perms[0]["can"]["allowDeny"], perms             # the hook does wait (else this says nothing)
            t0 = time.monotonic()
            r = await asyncio.get_running_loop().run_in_executor(None, lambda: _jui(home, "viz", "stop"))
            return r, time.monotonic() - t0

    r, took = asyncio.run(hold_and_stop())
    assert r.returncode == 0, r.stderr
    assert "KILL" not in r.stdout and took < viz_cmd.STOP_TERM_SEC, (r.stdout, took)
    assert not _alive(pid)


def test_stop_ends_our_server_that_no_longer_answers_health(home):
    port = _free_port()
    started = _jui(home, "viz", "start", "--port", str(port), "--json")
    assert started.returncode == 0, started.stderr
    pid = json.loads(started.stdout)["pid"]
    os.kill(pid, signal.SIGSTOP)                                  # alive, listening, never answers
    try:
        r = _jui(home, "viz", "stop", timeout=60)
        assert r.returncode == 0, r.stderr
        assert "/health に応答しない" in r.stdout and "KILL" in r.stdout, r.stdout   # a stopped process takes no TERM
        for _ in range(40):
            if not _alive(pid):
                break
            time.sleep(0.05)
        assert not _alive(pid)
        assert not (home / ".local" / "state" / "jui-viz" / "viz.pid").exists()
    finally:
        if _alive(pid):
            os.kill(pid, signal.SIGKILL)


def test_stop_never_signals_a_pid_that_is_not_our_viz_serve(home):
    """The pid file names a process that is not `viz serve`, on a port that accepts but never answers."""
    holder = socket.socket()
    holder.bind(("127.0.0.1", 0))
    holder.listen(8)                                              # accepts the connect, never answers /health
    port = holder.getsockname()[1]
    other = subprocess.Popen(["sleep", "60"])
    try:
        state = home / ".local" / "state" / "jui-viz"
        state.mkdir(parents=True)
        (state / "viz.pid").write_text(str(other.pid))
        (state / "server.json").write_text(json.dumps({"pid": other.pid, "port": port, "token": "x"}))
        r = _jui(home, "viz", "stop", timeout=60)
        assert r.returncode == 1 and "止めません" in r.stderr, (r.stdout, r.stderr)
        assert other.poll() is None                               # still alive: never signalled
    finally:
        other.kill()
        other.wait(5)
        holder.close()
