"""jui viz keeps its runtime files outside the install folder, which every bootstrap replaces.

Up to 2.1.0 they lived in ~/.jsonui-cli/viz: the bootstrap's ``rm -rf`` + clone
took server.json and viz.pid from under a running server (an orphan status /
stop / start could not see) and took backups/ (the only copy of settings.json
from before ``hooks install``) and test-progress/ with it.

HOME points at a temporary folder in every test, and every HOME here has a
config.json naming a free port: nothing here reaches the real ~/.jsonui-cli,
~/.claude, or a server on the default port (an earlier draft's
``jui viz stop`` in a temporary HOME looked at 7788 and, with the home check
mutated away, stopped the real server there).
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from jui_cli.cli import main
from jui_cli.viz import hooks_installer as hi
from jui_cli.viz import paths

REPO = Path(__file__).resolve().parents[2]
JUI = REPO / "jui_tools" / "bin" / "jui"
BOOTSTRAP = REPO / "installer" / "bootstrap.sh"
SESSION_ENV = REPO / "plugins" / "jui-viz" / "scripts" / "session_env.sh"
SCRIPTS = {name: REPO / "jui_tools" / "jui_cli" / "viz" / name for name in ("forward.py", "channel.py")}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _own_port(home: Path) -> int:
    """A config.json in this HOME's runtime folder naming a free port, so no command here looks at the default one."""
    folder = home / ".local" / "state" / "jui-viz"
    folder.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    (folder / "config.json").write_text(json.dumps({"port": port}))
    return port


@pytest.fixture()
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    assert Path.home() == home
    _own_port(home)
    return home


def _env(home: Path, **extra) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("JUI_VIZ_HOME", "XDG_STATE_HOME")}
    env.update(HOME=str(home), PYTHONUNBUFFERED="1", **extra)
    return env


def _jui(home: Path, *args: str, timeout: float = 40) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(JUI), *args], env=_env(home), capture_output=True, text=True, timeout=timeout)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _bootstrap_block() -> str:
    """bootstrap.sh between its viz-state markers: the folder rule and the move, nothing else."""
    text = BOOTSTRAP.read_text()
    m = re.search(r"^# >>> viz-state.*?\n(.*?)^# <<< viz-state$", text, re.S | re.M)
    assert m, "the viz-state markers are gone from bootstrap.sh"
    block = m.group(1)
    assert not re.search(r"\brm\b", block), "the extracted block runs here; it must not delete anything"
    return block


def _bash(block: str, call: str, env: dict) -> str:
    out = subprocess.run(["bash", "-c", f"{block}\n{call}"], env=env, capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(f"_state_home_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


# ---------------------------------------------------------------- one rule, five places


ENVIRONMENTS = {
    "nothing set": {},
    "XDG_STATE_HOME": {"XDG_STATE_HOME": "{tmp}/state"},
    "a relative XDG_STATE_HOME is ignored": {"XDG_STATE_HOME": "state"},
    "JUI_VIZ_HOME": {"JUI_VIZ_HOME": "{tmp}/viz", "XDG_STATE_HOME": "{tmp}/state"},
    "a relative JUI_VIZ_HOME is ignored": {"JUI_VIZ_HOME": "viz", "XDG_STATE_HOME": "{tmp}/state"},
}


@pytest.mark.parametrize("case", list(ENVIRONMENTS))
def test_every_place_that_names_the_folder_follows_one_rule(case, home, tmp_path, monkeypatch):
    extra = {k: v.format(tmp=tmp_path) for k, v in ENVIRONMENTS[case].items()}
    for k, v in extra.items():
        monkeypatch.setenv(k, v)
    expected = str(paths.viz_home())
    assert expected != str(paths.legacy_viz_home())

    answers = {name: _load(path).viz_home() for name, path in SCRIPTS.items()}
    env_file = tmp_path / "env"
    subprocess.run(["sh", str(SESSION_ENV)], env=_env(home, CLAUDE_ENV_FILE=str(env_file), **extra), check=True, timeout=10)
    exported = re.fullmatch(r'export JSONUI_TEST_PROGRESS_DIR="(.*)"\n', env_file.read_text())
    answers["session_env.sh"] = str(Path(exported.group(1)).parent)
    answers["bootstrap.sh"] = _bash(_bootstrap_block(), "viz_state_home", _env(home, **extra))

    assert answers == {name: expected for name in answers}
    assert str(paths.progress_dir()) == exported.group(1)


def test_the_plugins_copies_are_the_packages():
    for name, path in SCRIPTS.items():
        assert (REPO / "plugins" / "jui-viz" / "scripts" / name).read_bytes() == path.read_bytes(), name


# ---------------------------------------------------------------- the bootstrap replaces the install folder


def test_state_survives_the_install_folder_being_replaced(home):
    """What the bootstrap does to ~/.jsonui-cli (rm -rf, then a fresh clone) leaves the runtime files alone."""
    install = home / ".jsonui-cli"
    (install / "jui_tools").mkdir(parents=True)
    paths.backups_dir().mkdir(parents=True)
    (paths.backups_dir() / "settings.json.1").write_text("{}")
    paths.progress_dir().mkdir(parents=True)
    (paths.progress_dir() / "run.jsonl").write_text("{}\n")
    config = paths.config_json().read_text()

    shutil.rmtree(install)
    (install / "jui_tools").mkdir(parents=True)

    assert (paths.backups_dir() / "settings.json.1").read_text() == "{}"
    assert (paths.progress_dir() / "run.jsonl").exists()
    assert paths.config_json().read_text() == config


def test_a_running_server_is_still_reachable_after_the_install_folder_is_replaced(home):
    started = _jui(home, "viz", "start", "--json")
    assert started.returncode == 0, started.stderr
    pid = json.loads(started.stdout)["pid"]
    try:
        install = home / ".jsonui-cli"
        (install / "jui_tools").mkdir(parents=True, exist_ok=True)
        shutil.rmtree(install)                                 # the bootstrap's rm -rf
        (install / "jui_tools").mkdir(parents=True)            # and its clone

        status = json.loads(_jui(home, "viz", "status", "--json").stdout)
        assert status["running"] is True and status["pid"] == pid and not status.get("orphan")
        again = _jui(home, "viz", "start", "--json")
        assert again.returncode == 0 and json.loads(again.stdout)["alreadyRunning"] is True
        stopped = _jui(home, "viz", "stop")
        assert stopped.returncode == 0 and "stopped (pid" in stopped.stdout
        assert not _alive(pid)
        restarted = _jui(home, "viz", "start", "--json")
        assert restarted.returncode == 0, restarted.stderr
        pid = json.loads(restarted.stdout)["pid"]
    finally:
        _jui(home, "viz", "stop")
        if _alive(pid):
            os.kill(pid, signal.SIGTERM)  # the server this test started


# ---------------------------------------------------------------- moving what 2.1.0 left behind


def _legacy(home: Path) -> Path:
    old = home / ".jsonui-cli" / "viz"
    (old / "backups").mkdir(parents=True)
    (old / "backups" / "settings.json.1").write_text("backup")
    (old / "test-progress").mkdir()
    (old / "test-progress" / "run.jsonl").write_text("{}\n")
    (old / "config.json").write_text('{"port": 7799}')
    return old


def test_the_bootstrap_moves_the_old_folder_before_it_deletes_the_install_folder(home):
    old = _legacy(home)
    new = paths.viz_home()
    kept = (new / "config.json").read_text()               # already there: never overwritten

    _bash(_bootstrap_block(), f'migrate_viz_state "{home / ".jsonui-cli"}"', _env(home))

    assert (new / "backups" / "settings.json.1").read_text() == "backup"
    assert (new / "test-progress" / "run.jsonl").exists()
    assert (new / "config.json").read_text() == kept
    assert (old / "config.json").exists() and not (old / "backups").exists()


def test_the_bootstrap_calls_the_move_before_it_swaps_the_install_folder_out():
    # Since 2.3.8 the install folder is renamed aside and deleted after a fresh clone is swapped in
    # (test_bootstrap_swaps_in_a_fresh_clone.py); the move still has to come first.
    lines = [line.strip() for line in BOOTSTRAP.read_text().splitlines()]
    assert 'rm -rf "$INSTALL_DIR"' not in lines, "the live install folder is never emptied in place"
    aside = [i for i, line in enumerate(lines) if line.startswith('mv "$INSTALL_DIR" ')]
    assert len(aside) == 1, "one place moves the install folder out; a new one needs the move too"
    moves = [i for i, line in enumerate(lines) if line == 'migrate_viz_state "$INSTALL_DIR"']
    assert len(moves) == 1 and moves[0] < aside[0]


def test_the_first_viz_command_moves_the_old_folder(home, capsys):
    old = _legacy(home)
    new = paths.viz_home()
    kept = (new / "config.json").read_text()

    assert main(["viz", "status"]) == 0

    assert (new / "backups" / "settings.json.1").read_text() == "backup"
    assert (new / "test-progress" / "run.jsonl").exists()
    assert (new / "config.json").read_text() == kept
    assert (old / "config.json").exists()
    assert "moved the state from" in capsys.readouterr().err


def test_hooks_install_rewrites_the_old_progress_folder_and_uninstall_removes_it(home):
    paths.claude_settings().parent.mkdir(parents=True)
    old_value = str(paths.legacy_progress_dir())
    paths.claude_settings().write_text(json.dumps({"env": {hi.PROGRESS_ENV: old_value}}))

    hi.install(python="/work/py")
    assert json.loads(paths.claude_settings().read_text())["env"][hi.PROGRESS_ENV] == str(paths.progress_dir())

    paths.claude_settings().write_text(json.dumps({"env": {hi.PROGRESS_ENV: old_value, "OTHER": "1"}}))
    hi.uninstall()
    assert json.loads(paths.claude_settings().read_text())["env"] == {"OTHER": "1"}


# ---------------------------------------------------------------- a server whose files are gone


def test_a_server_whose_files_were_lost_is_named_by_start_and_stopped_by_stop(home):
    started = _jui(home, "viz", "start", "--json")   # on the configured port, which status / start / stop look at
    assert started.returncode == 0, started.stderr
    pid = json.loads(started.stdout)["pid"]
    try:
        for name in ("server.json", "viz.pid"):
            (paths.viz_home() / name).unlink()                # what the old bootstrap did

        status = json.loads(_jui(home, "viz", "status", "--json").stdout)
        assert status == {**status, "running": True, "orphan": True, "pid": pid}
        blocked = _jui(home, "viz", "start")
        assert blocked.returncode == 1 and f"pid {pid}" in blocked.stderr and "jui viz stop" in blocked.stderr
        stopped = _jui(home, "viz", "stop")
        assert stopped.returncode == 0 and f"pid {pid}" in stopped.stdout
        deadline = time.monotonic() + 5
        while _alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not _alive(pid)
    finally:
        if _alive(pid):
            os.kill(pid, signal.SIGTERM)  # the server this test started


def test_a_server_of_another_home_is_not_stopped(home, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    port = _own_port(other)
    started = _jui(other, "viz", "start", "--json")
    assert started.returncode == 0, started.stderr
    pid = json.loads(started.stdout)["pid"]
    try:
        stopped = _jui(home, "viz", "stop", "--port", str(port))
        assert stopped.returncode == 0 and "not running" in stopped.stdout
        assert _alive(pid)
        assert json.loads(_jui(home, "viz", "status", "--json").stdout)["running"] is False
    finally:
        _jui(other, "viz", "stop")
        if _alive(pid):
            os.kill(pid, signal.SIGTERM)  # the server this test started


# ---------------------------------------------------------------- ⏳ the jui-viz plugin 1.0.0 (remove in 3.0.0)
#
# tests/fixtures/viz/forward_plugin_1_0_0.py is plugins/jui-viz/scripts/forward.py
# of 8ccee0a2 (jsonui-cli 2.1.0, plugin 1.0.0) byte for byte: it reads
# ~/.jsonui-cli/viz/server.json and nothing else.

OLD_FORWARD = Path(__file__).resolve().parent / "fixtures" / "viz" / "forward_plugin_1_0_0.py"


def _wait_for(predicate, seconds: float = 10.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return predicate()


def _mirror(home: Path) -> dict | None:
    try:
        return json.loads((home / ".jsonui-cli" / "viz" / "server.json").read_text())
    except (OSError, ValueError):
        return None


def _snapshot(port: int, token: str) -> dict:
    import urllib.request

    request = urllib.request.Request(f"http://127.0.0.1:{port}/api/snapshot", headers={"X-Jui-Viz-Token": token})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return json.loads(opener.open(request, timeout=5).read())


@pytest.fixture()
def server(home):
    """A server started in this HOME (with an install folder there, as on a real machine)."""
    (home / ".jsonui-cli" / "jui_tools").mkdir(parents=True)
    started = _jui(home, "viz", "start", "--json")
    assert started.returncode == 0, started.stderr
    pid = json.loads(started.stdout)["pid"]
    yield pid
    _jui(home, "viz", "stop")
    if _alive(pid):
        os.kill(pid, signal.SIGTERM)  # the server this test started


def test_an_old_plugin_reaches_a_new_server_through_the_copy(home, server):
    assert OLD_FORWARD.read_text().count('".jsonui-cli", "viz", "server.json"') == 1
    info = json.loads(paths.server_json().read_text())
    assert _wait_for(lambda: _mirror(home) is not None)
    mirror = _mirror(home)
    assert {k: mirror[k] for k in info} == info and mirror["mirrorOf"] == str(paths.server_json())
    assert (home / ".jsonui-cli" / "viz" / "server.json").stat().st_mode & 0o777 == 0o600

    body = {"session_id": "0ld-p1ug-1n00", "hook_event_name": "SessionStart", "cwd": str(home), "source": "startup"}
    done = subprocess.run([sys.executable, "-I", "-S", str(OLD_FORWARD)], input=json.dumps(body).encode(),
                          env=_env(home), capture_output=True, timeout=10)
    assert done.returncode == 0

    def arrived() -> bool:
        sessions = _snapshot(info["port"], info["token"])["slices"].get("sessions") or []
        return any(s.get("id", "").startswith("0ld") or "0ld-p1ug-1n00" in json.dumps(s) for s in sessions)

    assert _wait_for(arrived), "the 1.0.0 forward.py did not reach the server"


def test_the_copy_comes_back_after_the_bootstrap_deletes_it(home, server):
    assert _wait_for(lambda: _mirror(home) is not None)
    shutil.rmtree(home / ".jsonui-cli")                      # the bootstrap's rm -rf
    (home / ".jsonui-cli" / "jui_tools").mkdir(parents=True)  # and its clone
    assert _mirror(home) is None
    assert _wait_for(lambda: _mirror(home) is not None, seconds=10), "the server did not write the copy again"
    assert _mirror(home)["pid"] == server


def test_stopping_removes_the_copy_and_the_real_file(home, server):
    assert _wait_for(lambda: _mirror(home) is not None)
    assert _jui(home, "viz", "stop").returncode == 0
    assert not paths.server_json().exists()
    assert not (home / ".jsonui-cli" / "viz").exists()


def test_no_install_folder_means_no_copy(home):
    started = _jui(home, "viz", "start", "--json")
    assert started.returncode == 0, started.stderr
    pid = json.loads(started.stdout)["pid"]
    try:
        time.sleep(2.5)  # past one rewrite
        assert not (home / ".jsonui-cli").exists()
    finally:
        _jui(home, "viz", "stop")
        if _alive(pid):
            os.kill(pid, signal.SIGTERM)  # the server this test started


def test_an_old_servers_own_file_is_not_replaced(home, server):
    """A server.json without mirrorOf appearing while ours runs (an old CLI's server) is left as it is."""
    assert _wait_for(lambda: _mirror(home) is not None)
    own = json.dumps({"pid": 999999, "port": 1, "token": "old"})
    (home / ".jsonui-cli" / "viz" / "server.json").write_text(own)
    time.sleep(2.5)  # past one rewrite
    assert (home / ".jsonui-cli" / "viz" / "server.json").read_text() == own


def test_the_copy_is_never_moved_into_the_new_folder(home):
    old = home / ".jsonui-cli" / "viz"
    old.mkdir(parents=True)
    (old / "server.json").write_text(json.dumps({"pid": 999999, "port": 1, "token": "t", "mirrorOf": "x"}))
    assert main(["viz", "status"]) == 0
    assert not paths.server_json().exists() and (old / "server.json").exists()


def test_a_server_removes_only_the_copy_that_names_it(home):
    """The copy another server wrote (another pid) outlives this one's stop; this one's own copy does not.

    Called directly: a running server rewrites a copy that names someone else within LEGACY_MIRROR_SEC, so a stop
    could not be timed to meet one. This is the function _cmd_serve's last step calls.
    """
    from jui_cli.commands import viz_cmd

    old = home / ".jsonui-cli" / "viz"
    old.mkdir(parents=True)
    other = {"pid": 999999, "port": 1, "token": "t", "mirrorOf": str(paths.server_json())}
    (old / "server.json").write_text(json.dumps(other))

    viz_cmd._legacy_mirror_clear(os.getpid())
    assert json.loads((old / "server.json").read_text()) == other

    (old / "server.json").write_text(json.dumps(dict(other, pid=os.getpid())))
    viz_cmd._legacy_mirror_clear(os.getpid())
    assert not old.exists()
