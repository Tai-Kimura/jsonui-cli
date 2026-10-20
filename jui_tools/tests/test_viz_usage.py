"""The plan's usage limits (requester, 10-18): statusline.py → POST /usage → the usage slice → the header.

HOME is a temporary folder in every test that touches settings.json or the server, with a config.json naming a
free port; JUI_VIZ_HOME / XDG_STATE_HOME / JSONUI_TEST_PROGRESS_DIR / JSONUI_TEST_RESULTS_DIR are removed. The
input JSON is made up in the shape Claude Code 2.1.302 gives a statusLine command (read in its binary, 10-18):
nothing here runs claude.
"""
from __future__ import annotations

import base64
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from jui_cli.viz import paths
from jui_cli.viz import statusline_installer as sl
from jui_cli.viz import usage

REPO = Path(__file__).resolve().parents[2]
JUI = REPO / "jui_tools" / "bin" / "jui"
SCRIPT = REPO / "jui_tools" / "jui_cli" / "viz" / "statusline.py"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
RESET = 1_792_400_000   # epoch seconds, a time in the future of every fixture here


def _status(five=None, week=None, model="Opus") -> dict:
    out = {"session_id": "s", "model": {"id": "m", "display_name": model}}
    limits = {}
    if five is not None:
        limits["five_hour"] = {"used_percentage": five, "resets_at": RESET}
    if week is not None:
        limits["seven_day"] = {"used_percentage": week, "resets_at": RESET + 86400 * 3}
    if limits:
        out["rate_limits"] = limits
    return out


@pytest.fixture()
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True)
    for k in ISOLATE:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HOME", str(home))
    assert paths.viz_home() == home / ".local" / "state" / "jui-viz"
    return home


def _env(home: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env.update(HOME=str(home), PYTHONUNBUFFERED="1")
    return env


def _line(home: Path, status, *extra: str) -> subprocess.CompletedProcess:
    body = json.dumps(status).encode() if not isinstance(status, bytes) else status
    return subprocess.run([sys.executable, "-I", "-S", str(SCRIPT), *extra], input=body, capture_output=True, env=_env(home), timeout=20)


# ---------------------------------------------------------------- the value


def test_the_windows_are_read_checked_and_kept(home):
    assert usage.parse(None) is None and usage.parse({}) is None and usage.parse({"five_hour": None}) is None
    assert usage.parse({"five_hour": {"used_percentage": "42", "resets_at": RESET}}) is None      # not a number
    assert usage.parse({"five_hour": {"used_percentage": 42.0, "resets_at": RESET}}) == {"fiveHour": {"pct": 42.0, "resetsAt": RESET * 1000}}
    both = usage.parse(_status(42.5, 18)["rate_limits"])
    assert both == {"fiveHour": {"pct": 42.5, "resetsAt": RESET * 1000}, "sevenDay": {"pct": 18.0, "resetsAt": (RESET + 86400 * 3) * 1000}}
    assert usage.parse({"five_hour": {"used_percentage": 130, "resets_at": RESET}})["fiveHour"]["pct"] == 100.0
    assert usage.parse({"five_hour": {"used_percentage": -3, "resets_at": RESET}})["fiveHour"]["pct"] == 0.0
    assert usage.load() == {}
    assert usage.accept({"rate_limits": {}}, 1) is None and usage.load() == {}                        # nothing usable: kept as it was
    value = usage.accept({"rate_limits": _status(42, 18)["rate_limits"]}, 1234)
    assert value == {"windows": both | {"fiveHour": {"pct": 42.0, "resetsAt": RESET * 1000}}, "receivedAt": 1234}
    assert usage.load() == value                                                                       # what a restart reads
    assert (usage.store_path().stat().st_mode & 0o777) == 0o600


# ---------------------------------------------------------------- the status line


def test_on_its_own_it_prints_a_short_line(home):
    assert _line(home, _status(42.4, 18)).stdout.decode() == "5h 42% · 7d 18%"
    assert _line(home, _status(100, 18)).stdout.decode() == "5h limit · 7d 18%"
    assert _line(home, _status(99.7, 18)).stdout.decode() == "5h 99% · 7d 18%"            # floored: only 100 is the limit
    assert _line(home, _status()).stdout.decode() == "Opus"                    # no limits (API key, or before the first call)
    done = _line(home, b"{not json")
    assert done.returncode == 0 and done.stderr == b""                         # never loud


def test_wrapping_prints_exactly_what_the_users_line_printed(home, tmp_path):
    script = tmp_path / "mine.sh"
    script.write_text("#!/bin/sh\nread x\nprintf '\\033[32mmy line\\033[0m %s' \"$(printf '%s' \"$x\" | wc -c | tr -d ' ')\"\n")
    script.chmod(0o755)
    original = {"type": "command", "command": str(script), "padding": 2}
    arg = base64.b64encode(json.dumps(original).encode()).decode()
    body = json.dumps(_status(42, 18)).encode()
    mine = subprocess.run([str(script)], input=body, capture_output=True).stdout
    out = _line(home, body, "--wrap", arg).stdout
    assert out == mine and b"my line" in out                                   # byte for byte, colours included
    broken = base64.b64encode(json.dumps({"type": "command", "command": "exit 3"}).encode()).decode()
    assert _line(home, body, "--wrap", broken).returncode == 3                # the user's command's own exit status


# ---------------------------------------------------------------- install / uninstall


def _settings(home: Path) -> dict:
    p = home / ".claude" / "settings.json"
    return json.loads(p.read_text()) if p.exists() else {}


def test_install_writes_ours_and_uninstall_takes_it_out(home):
    (home / ".claude").mkdir()
    (home / ".claude" / "settings.json").write_text(json.dumps({"model": "opus"}))
    assert sl.install(dry_run=True).changed and _settings(home) == {"model": "opus"}              # dry run writes nothing
    r = sl.install()
    assert r.changed and r.backup is not None and sl.is_ours(_settings(home)["statusLine"])
    assert sl.status()["installed"] and sl.status()["wraps"] is None
    assert not sl.install().changed                                                               # twice is once
    assert sl.uninstall().changed and _settings(home) == {"model": "opus"}


def test_an_existing_status_line_is_wrapped_and_put_back_exactly(home):
    (home / ".claude").mkdir()
    original = {"type": "command", "command": "~/bin/my-line --short", "padding": 1, "refreshInterval": 5}
    (home / ".claude" / "settings.json").write_text(json.dumps({"statusLine": original, "theme": "dark"}))
    sl.install()
    line = _settings(home)["statusLine"]
    assert sl.is_ours(line) and sl.wrapped_of(line) == original and line["padding"] == 1 and line["refreshInterval"] == 5
    assert sl.status()["wraps"] == "~/bin/my-line --short"
    sl.uninstall()
    assert _settings(home) == {"statusLine": original, "theme": "dark"}


def test_install_and_status_say_the_vs_code_extension_and_the_desktop_app_never_update_it(home):
    """Neither runs a statusLine (the desktop app measured 10-19: one turn, statusline.py ran 0 times)."""
    for action in ("install", "status"):
        out = subprocess.run([sys.executable, str(JUI), "viz", "statusline", action], env=_env(home), capture_output=True,
                             text=True, timeout=60).stdout
        assert "sessions in the VS Code extension and the desktop app do not update them" in out, (action, out)


def test_doctor_says_where_the_value_comes_from(home):
    out = subprocess.run([sys.executable, str(JUI), "viz", "doctor"], env=_env(home), capture_output=True, text=True, timeout=60).stdout
    assert "usage: statusLine: not installed" in out and "sessions in the VS Code extension and the desktop app do not update them" in out


# ---------------------------------------------------------------- a real server


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _usage_slice(state: Path) -> dict:
    info = json.loads((state / "server.json").read_text())
    req = urllib.request.Request(f"http://127.0.0.1:{info['port']}/api/snapshot", headers={"X-Jui-Viz-Token": info["token"]})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return json.loads(opener.open(req, timeout=5).read())["slices"]["usage"]


def test_the_status_line_reaches_the_server_and_a_restart_keeps_it(home):
    state = home / ".local" / "state" / "jui-viz"
    port = _free_port()
    (state / "config.json").write_text(json.dumps({"port": port}))
    pids = []
    try:
        started = subprocess.run([sys.executable, str(JUI), "viz", "start", "--json"], env=_env(home), capture_output=True, text=True, timeout=40)
        assert started.returncode == 0, started.stderr
        pids.append(json.loads(started.stdout)["pid"])
        assert f":{port}" in started.stdout
        assert _usage_slice(state) in ({}, [])
        t0 = time.time()
        assert _line(home, _status(42, 18)).returncode == 0
        got = _usage_slice(state)
        assert got["windows"]["fiveHour"] == {"pct": 42.0, "resetsAt": RESET * 1000} and abs(got["receivedAt"] / 1000 - t0) < 10
        _line(home, _status())                                                  # no limits in this one: the last value stays
        assert _usage_slice(state)["windows"]["sevenDay"]["pct"] == 18.0
        subprocess.run([sys.executable, str(JUI), "viz", "stop"], env=_env(home), capture_output=True, timeout=40)
        started = subprocess.run([sys.executable, str(JUI), "viz", "start", "--json"], env=_env(home), capture_output=True, text=True, timeout=40)
        pids.append(json.loads(started.stdout)["pid"])
        assert _usage_slice(state) == got                                       # after the restart, with when it came
    finally:
        subprocess.run([sys.executable, str(JUI), "viz", "stop"], env=_env(home), capture_output=True, timeout=40)
        for pid in pids:
            if _alive(pid):
                os.kill(pid, signal.SIGTERM)   # a server this test started
