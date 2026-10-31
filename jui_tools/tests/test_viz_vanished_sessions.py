"""A claude session killed without its SessionEnd leaves the page (ticket 2026-10-29-viz-claude-session-killed-without-sessionend-stays).

On 10-28 22 sessions died with no SessionEnd; their ~/.claude/sessions entries went, and the page kept them idle until
viz restarted, and 退勤 on one was refused 409 ("no ~/.claude/sessions entry names this session"). Now:

* a session whose process the server knew, gone from a ``claude agents --json`` list that was read AND from every
  ~/.claude/sessions entry, ends as its SessionEnd would (World.end_vanished, from the agents poll);
* while the list cannot be read it stays (an unread list is unknown, never "gone");
* 退勤 on a session with no entry left and its known process gone ends it without a signal, and says so in clock-out.log.

The live arms run a real ``jui viz start`` in a TEMPORARY HOME with PATH holding only a stand-in ``claude`` written by
this file (it prints this test's list, or exits 1 while the test says the list is unreadable). The sessions are
stand-ins of test_viz_clock_out (a symlink called claude to /bin/bash); each kill -9 goes to one of them only.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from jui_cli.viz import clockout
from jui_cli.viz.ingest import World
from jui_cli.viz.state import VizState

from tests.test_viz_clock_out import DROP, JUI, StandIns, Viz, _env, _free_port, _lstart, write_registry

SID = "c2000000-0000-4000-8000-{:012d}"


# ---------------------------------------------------------------- the World on its own


def _world_with(*sids_pids) -> World:
    w = World(VizState(100))
    for sid, pid in sids_pids:
        w.apply_session_file({"pid": pid, "sessionId": sid, "cwd": "/work/x", "entrypoint": "cli", "status": "idle",
                              "procStart": "Thu Oct 29 00:00:00 2026"}, 1000)
    return w


def test_only_a_session_gone_from_both_the_list_and_the_registry_ends():
    w = _world_with(("s-both", 11), ("s-listed", 12), ("s-registered", 13), ("s-alive", 14))
    gone = w.end_vanished({"s-listed", "s-alive"}, {"s-registered", "s-alive"}, 2000)
    assert gone == ["s-both"]
    status = {sid: s["status"] for sid, s in w.sessions.items()}
    assert status == {"s-both": "ended", "s-listed": "idle", "s-registered": "idle", "s-alive": "idle"}
    assert w.agents["s-both"]["leftAt"] == 2000
    ends = [e for e in w.state.recent_events() if e["kind"] == "SessionEnd"]
    assert [e["sessionId"] for e in ends] == ["s-both"]


def test_an_ended_session_is_not_ended_again_and_one_without_a_known_process_is_left_alone():
    w = _world_with(("s-1", 21))
    w._session("s-hooks-only", "/work/h", 1000)   # named by a hook (or Codex): no claude pid known
    assert w.end_vanished(set(), set(), 2000) == ["s-1"]
    assert w.end_vanished(set(), set(), 3000) == []
    assert w.sessions["s-hooks-only"]["status"] != "ended"
    assert len([e for e in w.state.recent_events() if e["kind"] == "SessionEnd"]) == 1


# ---------------------------------------------------------------- 退勤 with no entry left


def test_clock_out_with_no_entry_and_its_process_gone_ends_it_without_a_signal(tmp_path, monkeypatch):
    standins = StandIns(tmp_path / "standins")
    try:
        p = standins.start("sleep")
        start = _lstart(p.pid)
        p.send_signal(signal.SIGKILL)   # our own stand-in
        p.wait(timeout=5)
        sent: list = []
        monkeypatch.setattr(clockout, "_kill", standins.guarded_kill(sent))
        folder = tmp_path / "sessions"
        folder.mkdir()
        out = clockout.end_session(folder, "s-gone", os.getpid(), known=(p.pid, start))
        assert (out.result, out.status, out.signalled, out.pid) == ("ended", 200, False, p.pid), out
        assert "process is gone" in out.reason and sent == []
        # without what the server knew, it is refused as before
        out = clockout.end_session(folder, "s-gone", os.getpid())
        assert (out.result, out.status) == ("refused", 409), out
    finally:
        standins.cleanup()


def test_clock_out_with_no_entry_but_its_process_alive_is_refused(tmp_path, monkeypatch):
    standins = StandIns(tmp_path / "standins")
    try:
        p = standins.start("sleep")
        sent: list = []
        monkeypatch.setattr(clockout, "_kill", standins.guarded_kill(sent))
        folder = tmp_path / "sessions"
        folder.mkdir()
        out = clockout.end_session(folder, "s-alive", os.getpid(), known=(p.pid, _lstart(p.pid)))
        assert (out.result, out.status) == ("refused", 409) and sent == [] and standins.alive(p), out
        out = clockout.end_session(folder, "s-alive", os.getpid(), known=(p.pid, None))   # no procStart: cannot tell
        assert (out.result, out.status) == ("refused", 409), out
    finally:
        standins.cleanup()


# ---------------------------------------------------------------- the live server


CLAUDE = """#!/bin/sh
[ -e "{fail}" ] && exit 1
cat "{rows}"
"""


class ListedViz(Viz):
    """Viz with a stand-in ``claude`` on PATH: ``claude agents --json`` prints rows.json, or fails while fail exists."""

    def __init__(self, home: Path, bin_dir: Path):
        self.home = home
        self.rows = home / "rows.json"
        self.fail = home / "agents-fail"
        bin_dir.mkdir(parents=True)
        (bin_dir / "claude").write_text(CLAUDE.format(fail=self.fail, rows=self.rows))
        (bin_dir / "claude").chmod(0o755)
        self.path = f"{bin_dir}:/usr/bin:/bin"
        self.state = home / ".local" / "state" / "jui-viz"
        self.state.mkdir(parents=True, exist_ok=True)
        self.sessions_dir = home / ".claude" / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.list_rows([])
        # agentsPollSec is an int: the loader casts to the default's type (0.3 would read as 0, no poll)
        (self.state / "config.json").write_text(json.dumps({"port": _free_port(), "agentsPollSec": 1}))
        started = subprocess.run([sys.executable, str(JUI), "viz", "start", "--json"], env=self.env(),
                                 capture_output=True, text=True, timeout=40)
        assert started.returncode == 0, started.stderr
        self.pid = json.loads(started.stdout)["pid"]
        info = json.loads((self.state / "server.json").read_text())
        self.port, self.token = info["port"], info["token"]
        self.own = f"127.0.0.1:{self.port}"

    def env(self) -> dict:
        return dict(_env(self.home), PATH=self.path)

    def stop(self):
        subprocess.run([sys.executable, str(JUI), "viz", "stop"], env=self.env(), capture_output=True, timeout=40)
        if self.alive():
            os.kill(self.pid, signal.SIGTERM)   # the server this test started
        end = time.time() + 10
        while self.alive() and time.time() < end:
            time.sleep(0.1)

    def list_rows(self, rows: list):
        tmp = self.rows.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows))
        os.replace(tmp, self.rows)


@pytest.fixture()
def listed(tmp_path, monkeypatch):
    standins = StandIns(tmp_path / "standins")
    home = tmp_path / "home"
    for k in DROP:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HOME", str(home))
    try:
        v = ListedViz(home, tmp_path / "bin")
    except BaseException:
        standins.cleanup()
        raise
    try:
        yield v, standins
    finally:
        v.stop()          # the server stops before any stand-in is reaped
        standins.cleanup()


def _row(sid: str, p) -> dict:
    return {"pid": p.pid, "sessionId": sid, "cwd": f"/work/{sid[-4:]}", "kind": "interactive", "status": "idle",
            "startedAt": int(time.time() * 1000)}


def test_a_session_killed_without_sessionend_leaves_the_page_but_not_while_the_list_is_unreadable(listed):
    viz, standins = listed
    sid, keep = SID.format(1), SID.format(2)
    p = standins.start("sleep")
    q = standins.start("sleep")
    write_registry(viz.sessions_dir, p.pid, sid)
    write_registry(viz.sessions_dir, q.pid, keep)
    viz.list_rows([_row(sid, p), _row(keep, q)])
    viz.wait(lambda: {sid, keep} <= set(viz.sessions()), "both sessions listed")

    viz.fail.touch()                       # the list cannot be read from here
    time.sleep(1.5)                        # a poll or more fails before the session dies
    p.send_signal(signal.SIGKILL)          # our own stand-in: no SessionEnd
    p.wait(timeout=5)
    (viz.sessions_dir / f"{p.pid}.json").unlink()
    time.sleep(3.5)                        # three failing polls (1 s apart)
    assert viz.sessions()[sid]["status"] != "ended", "ended while the list was unreadable"

    viz.list_rows([_row(keep, q)])         # the list reads again, without the dead session
    viz.fail.unlink()
    viz.wait(lambda: viz.sessions()[sid]["status"] == "ended", "the dead session ended")
    assert viz.agents()[sid].get("leftAt"), viz.agents()[sid]
    assert viz.sessions()[keep]["status"] != "ended" and standins.alive(q)


def test_a_session_still_registered_stays_though_the_list_drops_it(listed):
    viz, standins = listed
    sid = SID.format(3)
    p = standins.start("sleep")
    write_registry(viz.sessions_dir, p.pid, sid)
    viz.list_rows([_row(sid, p)])
    viz.wait(lambda: sid in viz.sessions(), "the session listed")
    viz.list_rows([])                      # a list that dropped it, its entry still there
    time.sleep(3.5)                        # three polls
    assert viz.sessions()[sid]["status"] != "ended"


def test_clock_out_on_a_session_whose_entry_and_process_are_gone_takes_it_out(listed):
    viz, standins = listed
    viz.fail.touch()                       # no list: only 退勤 can end it here
    sid = SID.format(4)
    p = standins.start("sleep")
    write_registry(viz.sessions_dir, p.pid, sid)
    viz.wait(lambda: sid in viz.sessions(), "the session from its entry")
    p.send_signal(signal.SIGKILL)          # our own stand-in
    p.wait(timeout=5)
    (viz.sessions_dir / f"{p.pid}.json").unlink()
    status, text = viz.end(sid)
    assert status == 200, text
    assert json.loads(text) == {"ok": True, "ended": True, "pid": p.pid}
    assert viz.sessions()[sid]["status"] == "ended"
    last = viz.log()[-1]
    assert (last["result"], last["signalled"], last["pid"]) == ("ended", False, p.pid)
    assert "process is gone" in last["detail"]
