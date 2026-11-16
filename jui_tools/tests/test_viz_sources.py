"""claude agents --json and ~/.claude/sessions/*.json (jui_cli/viz/sources/)."""
from __future__ import annotations

import asyncio
import builtins
import sys
import io
import json
import os
import stat
import time
from pathlib import Path

import pytest

from jui_cli.viz.sources import agents_cli, devices, session_files


def test_parse_reads_the_measured_shape_and_refuses_others():
    rows = [{"pid": 1, "cwd": "/work/a", "kind": "interactive", "startedAt": 1, "sessionId": "s", "name": "n", "status": "idle"}]
    assert agents_cli.parse(json.dumps(rows).encode()) == rows
    assert agents_cli.parse(json.dumps({"agents": rows}).encode()) == rows
    assert agents_cli.parse(b"not json") is None
    assert agents_cli.parse(b'"text"') is None
    assert agents_cli.parse(json.dumps([1, rows[0]]).encode()) == rows


def _fake_claude(tmp_path: Path, script: str) -> str:
    exe = tmp_path / "claude"
    exe.write_text("#!/bin/sh\n" + script)
    exe.chmod(0o755)
    return str(exe)


def test_poll_once_runs_the_command_and_gives_up_after_the_timeout(tmp_path, monkeypatch):
    ok = _fake_claude(tmp_path, 'echo \'[{"sessionId":"s1"}]\'\n')
    assert asyncio.run(agents_cli.poll_once(ok)) == [{"sessionId": "s1"}]
    monkeypatch.setattr(agents_cli, "TIMEOUT_SEC", 0.3)
    slow = _fake_claude(tmp_path, "sleep 5\n")
    start = time.monotonic()
    assert asyncio.run(agents_cli.poll_once(slow)) is None
    assert time.monotonic() - start < 3
    failing = _fake_claude(tmp_path, "exit 3\n")
    assert asyncio.run(agents_cli.poll_once(failing)) is None


def test_run_stops_and_says_why_without_claude():
    statuses = []
    asyncio.run(agents_cli.run(3, lambda rows: None, lambda st, err: statuses.append((st, err)), which=lambda name: None))
    assert statuses and statuses[0][0] == "stopped" and "PATH" in statuses[0][1]


# The stop's cancel landing as a poll's answer comes in: on 3.11 asyncio.wait_for returned the answer and dropped the
# cancel, so the reader went on to its next sleep, the stop waited on it, and serve did not end within its bound (Linux
# CI, the TERM-while-it-still-starts arm and the held-stop arm; the task dumped as "run (agents_cli.py:85) > sleep",
# state cancelling). Here the stand-in's communicate() cancels the reader as it answers, every time.
@pytest.mark.parametrize("reader", ["agents", "devices"])
def test_a_stop_landing_as_a_poll_answers_ends_the_reader(monkeypatch, reader):
    box: list = [None]

    class Proc:
        pid, returncode = 0, 0

        async def communicate(self):
            box[0].cancel()
            return b"[]", b""

        async def wait(self):
            return 0

    async def spawn(*args, **kwargs):
        return Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)

    async def go() -> bool:
        if reader == "agents":
            coro = agents_cli.run(3.0, lambda rows: None, lambda st, err: None, which=lambda name: "/stand-in/claude")
        else:
            coro = devices.run(lambda found: None, lambda st, err: None, which=lambda name: None, adb="/stand-in/adb",
                               interval=3.0)
        box[0] = asyncio.create_task(coro)
        done, _ = await asyncio.wait({box[0]}, timeout=1.0)   # well inside its 3 s sleep
        return bool(done) and box[0].cancelled()

    assert asyncio.run(go()), f"the {reader} reader went on to its next poll though it was cancelled"


def test_no_asyncio_wait_for_in_jui_cli():
    """asyncio.timeout in its place: on 3.11 wait_for drops a cancel that lands as what it waits on finishes (above)."""
    import ast

    root = Path(agents_cli.__file__).resolve().parents[2]
    found, read = [], 0
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        read += 1
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "wait_for" and isinstance(node.value, ast.Name) \
                    and node.value.id == "asyncio":
                found.append(f"{path.relative_to(root)}:{node.lineno}")
    assert read > 100 and found == [], found


def test_session_files_read_only_pid_json_and_never_open_key_files(tmp_path, monkeypatch):
    folder = tmp_path / "sessions"
    folder.mkdir()
    (folder / "123.json").write_text(json.dumps({"pid": 123, "sessionId": "s1", "status": "idle"}))
    (folder / "123.0b53b6ba.key").write_text("peer-token")
    (folder / "notes.json").write_text("{}")
    (folder / "999.json").write_text("{broken")

    opened = []
    real_open = builtins.open
    real_read_text = Path.read_text
    real_read_bytes = Path.read_bytes
    real_io_open = io.open
    real_os_open = os.open

    def spy_open(file, *a, **kw):
        opened.append(str(file))
        return real_open(file, *a, **kw)

    def spy_read_text(self, *a, **kw):
        opened.append(str(self))
        return real_read_text(self, *a, **kw)

    def spy_read_bytes(self, *a, **kw):
        opened.append(str(self))
        return real_read_bytes(self, *a, **kw)

    def spy_os_open(path, *a, **kw):
        opened.append(str(path))
        return real_os_open(path, *a, **kw)

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(io, "open", spy_open)
    monkeypatch.setattr(Path, "read_text", spy_read_text)
    monkeypatch.setattr(Path, "read_bytes", spy_read_bytes)
    monkeypatch.setattr(os, "open", spy_os_open)

    rows = session_files.scan(folder)
    assert rows == [{"pid": 123, "sessionId": "s1", "status": "idle"}]
    assert session_files.read_session_file(folder / "123.0b53b6ba.key") is None
    # The positive control: the spy does see reads (the .json was opened)...
    assert any(p.endswith("123.json") for p in opened)
    # ...and the key file never was.
    assert not any(p.endswith(".key") for p in opened), opened
    monkeypatch.setattr(io, "open", real_io_open)


def test_session_files_watch_reports_changes_and_ignores_keys(tmp_path):
    folder = tmp_path / "sessions"
    folder.mkdir()
    got = []
    observer = session_files.watch(folder, got.append)
    try:
        time.sleep(0.3)
        (folder / "77.0abc.key").write_text("token")
        (folder / "77.json").write_text(json.dumps({"pid": 77, "sessionId": "s77", "status": "busy"}))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not got:
            time.sleep(0.05)
    finally:
        observer.stop()
        observer.join(timeout=2)
    assert got and all(row.get("sessionId") == "s77" for row in got)
    assert session_files.watch(tmp_path / "missing", got.append) is None


def test_a_grandchild_that_leaves_the_group_cannot_hold_the_poll_open(tmp_path, monkeypatch):
    """setsid + holding stdout kept poll_once waiting 13.6 s with a 2 s limit (review, 10-18).

    The fake claude waits until the grandchild has left the group, so the
    timeout cannot land before the situation exists (it did, at first: the
    arm passed against the unfixed code).
    """
    monkeypatch.setattr(agents_cli, "TIMEOUT_SEC", 1.0)
    ready = tmp_path / "ready"
    holder = tmp_path / "hold.py"
    holder.write_text(f"import os, time\nos.setsid()\nopen({str(ready)!r}, 'w').close()\ntime.sleep(8)\n")
    exe = _fake_claude(tmp_path, f'{sys.executable} {holder} &\nwhile [ ! -f {ready} ]; do sleep 0.02; done\nsleep 8\n')
    start = time.monotonic()
    assert asyncio.run(agents_cli.poll_once(exe)) is None
    assert ready.exists()  # the situation existed
    assert time.monotonic() - start < 3.5


def test_session_files_do_not_follow_symlinks_or_take_other_digits(tmp_path):
    folder = tmp_path / "sessions"
    folder.mkdir()
    key = folder / "222.abc.key"
    key.write_text('{"sessionId": "from-key"}')
    (folder / "222.json").symlink_to(key)
    (folder / "٣.json").write_text('{"sessionId": "arabic-digit"}')
    assert session_files.scan(folder) == []
    assert session_files.read_session_file(folder / "222.json") is None

