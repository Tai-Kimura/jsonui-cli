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
        else:
            assert len(groups) == 1
    assert hi.status()["decide"] is True
    assert data["env"][hi.PROGRESS_ENV] == str(paths.viz_home() / "test-progress")
    hi.uninstall()
    assert _read() == {}


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
    assert any("上書きしません" in w for w in result.warnings)
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

