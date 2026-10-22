"""jui viz hooks install / uninstall / status against a temporary HOME."""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from jui_cli.viz import hooks_installer as hi
from jui_cli.viz import paths

PY = "/work/py/bin/python3"


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _settings() -> Path:
    return paths.claude_settings()


def _write(data) -> None:
    _settings().parent.mkdir(parents=True, exist_ok=True)
    _settings().write_text(json.dumps(data, indent=2))


def _read() -> dict:
    return json.loads(_settings().read_text())


USER_HOOK = {"type": "command", "command": "echo user"}


def test_install_into_no_file_then_uninstall_leaves_an_empty_object(home):
    result = hi.install(python=PY)
    assert result.changed and result.backup is None  # nothing to back up
    data = _read()
    assert sorted(data["hooks"]) == sorted(hi.EVENTS) and len(hi.EVENTS) == 18
    for event in hi.EVENTS:
        groups = data["hooks"][event]
        group = groups[0]
        assert ("matcher" in group) == (event in hi.TOOL_EVENTS)
        (handler,) = group["hooks"]
        assert hi.is_ours(handler) and handler["async"] is True and handler["timeout"] == 5
        assert handler["command"].startswith(PY + " -I -S ")
        if event == "PermissionRequest":
            # P6: a second, synchronous item that waits for the browser.
            (decide,) = groups[1]["hooks"]
            assert decide["command"].endswith(" --decide") and "async" not in decide
            assert decide["timeout"] == hi.DECIDE_TIMEOUT_SEC > 30
        elif event == "PreToolUse":
            # 10-18: a second, synchronous item for AskUserQuestion only, that waits for the browser's answer.
            assert len(groups) == 3 and groups[1]["matcher"] == "AskUserQuestion"
            (ask,) = groups[1]["hooks"]
            assert hi.is_ours(ask) and ask["command"].endswith(" --ask") and "async" not in ask
            assert ask["timeout"] == hi.ASK_TIMEOUT_SEC > 300
        elif event != "PostToolUse":
            assert len(groups) == 1
        if event in hi.STOP_EVENTS:
            # 2.3.20: the page's 停止 — a synchronous item on every tool call, cut short (forward.py gives up within 1 s)
            assert groups[-1]["matcher"] == "*" and len(groups) == (3 if event == "PreToolUse" else 2)
            (stop,) = groups[-1]["hooks"]
            assert hi.is_ours(stop) and stop["command"].endswith(" --stop") and "async" not in stop
            assert stop["timeout"] == hi.STOP_TIMEOUT_SEC <= 3
    assert hi.status()["decide"] is True and hi.status()["ask"] is True and hi.status()["stop"] is True
    assert data["env"][hi.PROGRESS_ENV] == str(paths.viz_home() / "test-progress")
    hi.uninstall()
    assert _read() == {}


@pytest.mark.parametrize("left", ["PreToolUse", "PostToolUse"])
def test_status_says_no_stop_when_the_stop_hook_is_on_one_of_its_two_events_only(home, left):
    """The --stop hook removed by hand from one event (or an install from a half-done version): status's stop is false."""
    hi.install(python=PY)
    data = _read()
    (gone,) = [e for e in hi.STOP_EVENTS if e != left]
    data["hooks"][gone] = [g for g in data["hooks"][gone]
                           if not any(str(h.get("command", "")).endswith(" --stop") for h in g["hooks"])]
    _write(data)
    assert any(str(h.get("command", "")).endswith(" --stop") for g in _read()["hooks"][left] for h in g["hooks"])
    assert hi.status()["stop"] is False


def test_install_twice_is_the_same_and_uninstall_restores_the_value(home):
    before = {
        "model": "x",
        "hooks": {
            "PreToolUse": [{"matcher": "Bash", "hooks": [USER_HOOK]}],
            "SessionStart": [{"hooks": [USER_HOOK]}],
            "Custom": [{"hooks": [USER_HOOK]}],
        },
        "env": {"OTHER": "1"},
        "permissions": {"allow": ["Read"]},
    }
    _write(before)
    hi.install(python=PY)
    once = _read()
    second = hi.install(python=PY)
    assert _read() == once and second.changed is False
    # The user's own groups stay first and untouched; ours are appended.
    assert once["hooks"]["PreToolUse"][0] == {"matcher": "Bash", "hooks": [USER_HOOK]}
    assert list(once)[:4] == ["model", "hooks", "env", "permissions"]
    hi.uninstall()
    assert _read() == before


def test_a_user_handler_in_the_same_group_as_ours_survives_uninstall(home):
    ours = hi.our_handler(PY)
    _write({"hooks": {"Stop": [{"hooks": [USER_HOOK, ours]}]}})
    hi.uninstall()
    assert _read() == {"hooks": {"Stop": [{"hooks": [USER_HOOK]}]}}


def test_uninstall_without_install_writes_nothing(home):
    before = {"hooks": {"Stop": [{"hooks": [USER_HOOK]}]}, "env": {}}
    _write(before)
    mtime = _settings().stat().st_mtime_ns
    result = hi.uninstall()
    assert result.changed is False and _settings().stat().st_mtime_ns == mtime
    assert _read() == before


def test_an_empty_env_present_before_install_is_gone_after_uninstall(home):
    """The one documented asymmetry: we cannot tell our emptied env from a pre-existing one."""
    _write({"env": {}})
    hi.install(python=PY)
    hi.uninstall()
    assert _read() == {}


def test_a_different_progress_env_is_kept_and_warned(home):
    _write({"env": {hi.PROGRESS_ENV: "/elsewhere"}})
    result = hi.install(python=PY)
    assert any("is not overwritten" in w for w in result.warnings)
    assert _read()["env"][hi.PROGRESS_ENV] == "/elsewhere"
    hi.uninstall()
    assert _read() == {"env": {hi.PROGRESS_ENV: "/elsewhere"}}


@pytest.mark.parametrize("text", ["{broken", "[1, 2]", "\xff\xfe"])
def test_a_file_that_is_not_a_json_object_is_never_written(home, text):
    _settings().parent.mkdir(parents=True, exist_ok=True)
    _settings().write_bytes(text.encode("latin-1"))
    with pytest.raises(hi.SettingsError):
        hi.install(python=PY)
    assert _settings().read_bytes() == text.encode("latin-1")
    assert not paths.backups_dir().exists()


def test_backup_holds_the_original_bytes_and_only_ten_are_kept(home):
    original = '{\n    "model": "x"\n}\n'  # 4-space indent: bytes differ from what we write
    _settings().parent.mkdir(parents=True, exist_ok=True)
    _settings().write_text(original)
    result = hi.install(python=PY)
    assert result.backup is not None and result.backup.read_text() == original
    assert stat.S_IMODE(result.backup.stat().st_mode) == 0o600
    for _ in range(12):
        hi.uninstall()
        hi.install(python=PY)
    assert len(list(paths.backups_dir().glob("settings.json.*.bak"))) == hi.BACKUPS_KEPT


def test_the_file_mode_is_kept(home):
    _write({})
    os.chmod(_settings(), 0o640)
    hi.install(python=PY)
    assert stat.S_IMODE(_settings().stat().st_mode) == 0o640


def test_a_symlinked_settings_file_is_written_through_to_its_target(home, tmp_path):
    real = tmp_path / "dotfiles" / "claude-settings.json"
    real.parent.mkdir()
    real.write_text("{}")
    _settings().parent.mkdir(parents=True, exist_ok=True)
    _settings().symlink_to(real)
    hi.install(python=PY)
    assert _settings().is_symlink()
    assert "hooks" in json.loads(real.read_text())


def test_dry_run_shows_a_diff_and_writes_nothing(home):
    _write({"model": "x"})
    before = _settings().read_bytes()
    result = hi.install(dry_run=True, python=PY)
    assert result.changed and "+  \"hooks\"" in result.diff
    assert _settings().read_bytes() == before and not paths.backups_dir().exists()


def test_a_write_racing_ours_is_read_again(home, monkeypatch):
    _write({"model": "x"})
    real_read = hi._read
    calls = {"n": 0}

    def racing_read(path):
        out = real_read(path)
        calls["n"] += 1
        if calls["n"] == 1:
            # Another writer lands right after our first read.
            _write({"model": "x", "theirs": True})
            st = path.stat()
            os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))
        return out

    monkeypatch.setattr(hi, "_read", racing_read)
    hi.install(python=PY)
    data = _read()
    assert data["theirs"] is True and "hooks" in data  # their write kept, ours added
    assert calls["n"] == 2


def test_status_reports_events_broken_paths_and_other_hooks(home):
    _write({"hooks": {"Stop": [{"hooks": [USER_HOOK]}]}, "disableAllHooks": True})
    hi.install(python=PY)  # PY does not exist on this machine
    s = hi.status()
    assert s["installed"] == 18 and all(s["events"].values())
    assert s["broken"]  # /work/py/bin/python3 is not there
    assert s["otherHooks"] is True and s["disableAllHooks"] is True
    hi.uninstall()
    hi.install()  # this interpreter and this forward.py: both exist
    assert hi.status()["broken"] == []


def test_only_handlers_naming_forward_py_count_as_ours():
    assert hi.is_ours({"command": "python3 /x/jui_cli/viz/forward.py"})
    assert hi.is_ours({"command": "python3", "args": ["-I", "/x/jui_cli/viz/forward.py"]})
    assert not hi.is_ours({"command": "python3 /x/forward.py"})
    assert not hi.is_ours({"command": "echo jui viz"})
    assert not hi.is_ours("jui_cli/viz/forward.py")


def test_a_user_command_that_merely_mentions_forward_py_is_not_ours(home):
    """Substring matching removed this handler (review, 10-18)."""
    theirs = {"type": "command", "command": "/usr/local/bin/audit --watch /src/jui_cli/viz/forward.py"}
    before = {"hooks": {"Stop": [{"hooks": [theirs]}]}}
    _write(before)
    hi.install(python=PY)
    hi.uninstall()
    assert _read() == before
    assert not hi.is_ours(theirs)
    assert hi.is_ours({"command": "'/opt/py/bin/python3.14' -I -S '/x y/jui_cli/viz/forward.py'"})


def test_a_write_between_our_read_and_our_stat_is_not_lost(home, monkeypatch):
    """The stamp was taken after read_bytes: a write in that gap was kept
    neither by us nor by the re-read check (review, 10-18)."""
    _write({"model": "x"})
    real_read_bytes = Path.read_bytes
    calls = {"n": 0}

    def racing_read_bytes(self):
        out = real_read_bytes(self)
        if self == hi._target() and calls["n"] == 0:
            calls["n"] += 1
            _write({"model": "x", "permissions": {"allow": ["Bash(ls)"]}})
            st = self.stat()
            os.utime(self, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))
        return out

    monkeypatch.setattr(Path, "read_bytes", racing_read_bytes)
    hi.install(python=PY)
    data = _read()
    assert data["permissions"] == {"allow": ["Bash(ls)"]} and "hooks" in data



def test_status_and_doctor_name_an_ask_hook_left_at_the_old_timeout(home, capsys, monkeypatch):
    """Ticket 2026-10-20 question-window-over-5-min: hooks installed before 2.3.7 cut the --ask hook at 600 s, under
    the 30 min and "until answered" windows; status says the timeout, doctor asks for hooks install again."""
    from jui_cli.cli import main
    hi.install(python=PY)
    assert hi.status()["askTimeout"] == hi.ASK_TIMEOUT_SEC
    data = _read()
    for g in data["hooks"]["PreToolUse"]:
        for h in g["hooks"]:
            if h.get("command", "").endswith(" --ask"):
                h["timeout"] = 600
    _write(data)
    assert hi.status()["askTimeout"] == 600
    monkeypatch.setenv("PATH", "")
    main(["viz", "doctor", "--json"])
    checks = {c["name"]: c for c in json.loads(capsys.readouterr().out)["checks"]}
    assert checks["askTimeout"]["ok"] is False and "600" in checks["askTimeout"]["detail"]
    # 600 s cuts 10 min too (600 + forward.py's 5 s), named from the rule, not a list (ticket doctor-misses-old-plugin)
    assert "10 min, 30 min, until answered" in checks["askTimeout"]["detail"] and "3 min" not in checks["askTimeout"]["detail"]
    hi.install(python=PY)
    assert hi.status()["askTimeout"] == hi.ASK_TIMEOUT_SEC
    main(["viz", "doctor", "--json"])
    assert "askTimeout" not in {c["name"] for c in json.loads(capsys.readouterr().out)["checks"]}


# ---- the enabled plugin's --ask hook (ticket 2026-10-20 doctor-misses-old-plugin-ask-timeout) ----

REPO_HOOKS = Path(__file__).resolve().parents[2] / "plugins" / "jui-viz" / "hooks" / "hooks.json"


def _fake_plugin(home: Path, version: str, ask_timeout, record=True) -> Path:
    """A plugin installed as Claude Code records it, under the temporary HOME: enabledPlugins in settings.json,
    plugins/installed_plugins.json, and the copy's hooks/hooks.json with this --ask timeout (None: no timeout key)."""
    _write({"enabledPlugins": {"jui-viz@jsonui": True}})
    root = home / ".claude" / "plugins" / "cache" / "jsonui" / "jui-viz" / version
    (root / "hooks").mkdir(parents=True)
    hooks = json.loads(REPO_HOOKS.read_text())
    for g in hooks["hooks"]["PreToolUse"]:
        for h in g["hooks"]:
            if h.get("args", [])[-1:] == ["--ask"]:
                if ask_timeout is None:
                    h.pop("timeout", None)
                else:
                    h["timeout"] = ask_timeout
    (root / "hooks" / "hooks.json").write_text(json.dumps(hooks))
    if record:
        (home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps(
            {"version": 2, "plugins": {"jui-viz@jsonui": [{"scope": "user", "installPath": str(root), "version": version}]}}))
    return root


def _doctor(capsys, monkeypatch) -> dict:
    from jui_cli.cli import main
    monkeypatch.setenv("PATH", "")
    main(["viz", "doctor", "--json"])
    return {c["name"]: c for c in json.loads(capsys.readouterr().out)["checks"]}


@pytest.fixture()
def plain_home(home, monkeypatch):
    monkeypatch.delenv("JUI_VIZ_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    return home


def test_a_plugin_left_at_600_seconds_is_named_with_the_choices_it_cuts(plain_home, capsys, monkeypatch):
    _fake_plugin(plain_home, "1.2.1", 600)
    assert hi.status()["pluginAsk"] == {"state": "found", "plugin": "jui-viz@jsonui", "version": "1.2.1", "askTimeout": 600}
    check = _doctor(capsys, monkeypatch)["pluginAskTimeout"]
    assert check["ok"] is False and "1.2.1" in check["detail"] and "Update jui-viz with /plugin" in check["detail"]
    assert "10 min, 30 min, until answered" in check["detail"] and "3 min" not in check["detail"]
    from jui_cli.cli import main
    main(["viz", "hooks", "status"])
    out = capsys.readouterr().out
    assert "NG" in out and "10 min, 30 min, until answered" in out


def test_a_plugin_hook_without_a_timeout_is_claude_codes_default_600(plain_home, capsys, monkeypatch):
    _fake_plugin(plain_home, "1.2.0", None)
    assert hi.status()["pluginAsk"]["askTimeout"] == hi.COMMAND_HOOK_DEFAULT_TIMEOUT_SEC == 600
    assert _doctor(capsys, monkeypatch)["pluginAskTimeout"]["ok"] is False


def test_a_plugin_at_86400_seconds_is_ok(plain_home, capsys, monkeypatch):
    _fake_plugin(plain_home, "1.2.2", 86400)
    check = _doctor(capsys, monkeypatch)["pluginAskTimeout"]
    assert check["ok"] is True and "1.2.2" in check["detail"]


def test_the_boundary_is_the_longest_wait_plus_five_seconds(plain_home, capsys, monkeypatch):
    from jui_cli.viz.config import ASK_UNTIL_ANSWERED_SEC, VizConfig, ask_choices_cut_short
    edge = ASK_UNTIL_ANSWERED_SEC + 5
    assert ask_choices_cut_short(edge, VizConfig()) == []
    assert ask_choices_cut_short(edge - 1, VizConfig()) == [0]
    assert ask_choices_cut_short(605, VizConfig()) == [1800, 0] and ask_choices_cut_short(604, VizConfig()) == [600, 1800, 0]
    _fake_plugin(plain_home, "1.2.2", edge)
    assert _doctor(capsys, monkeypatch)["pluginAskTimeout"]["ok"] is True


def test_no_plugin_installed_is_a_clear_state_not_a_crash(plain_home, capsys, monkeypatch):
    assert hi.status()["pluginAsk"] == {"state": "not-enabled"}     # no settings.json at all
    _write({"enabledPlugins": {"jui-viz@jsonui": True}})              # enabled, but Claude Code records no copy
    got = hi.status()["pluginAsk"]
    assert got["state"] == "not-found" and got["record"].endswith("installed_plugins.json")
    check = _doctor(capsys, monkeypatch)["pluginAskTimeout"]
    assert check["ok"] is False and "is not in" in check["detail"]


def test_a_plugin_whose_hooks_json_is_broken_is_unreadable(plain_home):
    root = _fake_plugin(plain_home, "1.2.2", 86400)
    (root / "hooks" / "hooks.json").write_text("{not json")
    assert hi.status()["pluginAsk"]["state"] == "unreadable"


def test_the_check_only_reads(plain_home, capsys, monkeypatch):
    root = _fake_plugin(plain_home, "1.2.1", 600)
    files = [root / "hooks" / "hooks.json", plain_home / ".claude" / "plugins" / "installed_plugins.json", _settings()]
    before = [(f.read_bytes(), f.stat().st_mtime_ns) for f in files]
    _doctor(capsys, monkeypatch)
    hi.status()
    assert [(f.read_bytes(), f.stat().st_mtime_ns) for f in files] == before


def test_a_disabled_plugin_is_not_checked(plain_home, capsys, monkeypatch):
    """/plugin can turn the plugin off: enabledPlugins then says false. Its old copy (600 s) is not in use, so no
    NG for it (the same lookup guards hooks install against forwarding twice: the next arm)."""
    _fake_plugin(plain_home, "1.2.1", 600)
    _write({"enabledPlugins": {"jui-viz@jsonui": False}})
    assert hi.plugin_enabled() is None
    assert hi.status()["pluginAsk"] == {"state": "not-enabled"}
    checks = _doctor(capsys, monkeypatch)
    assert "pluginAskTimeout" not in checks
    from jui_cli.cli import main
    main(["viz", "hooks", "status"])
    out = capsys.readouterr().out
    assert "プラグイン" not in out and "NG" not in out


def test_a_disabled_plugin_does_not_block_hooks_install(plain_home):
    """The same settings: hooks install puts the hooks in; it does not take the plugin as on."""
    _fake_plugin(plain_home, "1.2.1", 600)
    _write({"enabledPlugins": {"jui-viz@jsonui": False}})
    result = hi.install(python=PY)
    assert result.changed and hi.status()["installed"] == len(hi.EVENTS) and hi.status()["ask"] is True
    assert _read()["enabledPlugins"] == {"jui-viz@jsonui": False}      # the person's setting is kept as it was
