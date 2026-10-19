"""退勤: end one terminal session from its robot card (ticket 2026-10-19-jui-viz-clock-out-button).

Every process that could ever be signalled here is one this file started: stand-ins named like a claude CLI (a
symlink called ``claude`` to /bin/sleep or /bin/bash) or not (``notclaude``), each written into a TEMPORARY HOME's
~/.claude/sessions as a session. The server is a real ``jui viz start`` in that HOME on a free port, with PATH cut
to /usr/bin:/bin (no ``claude agents`` poll), so the only pids it can read are these. The stand-ins are reaped only
after the server has stopped, so none of their pids can be reused by another process while a server could still
signal it. The in-process arms replace clockout._kill with a recorder that sends nothing to any pid but a live
stand-in of this file.

The ledger arms use a temporary session-recovery folder; the interop arm runs a COPY of session-recovery's own
common.sh (read from ~/.claude/session-recovery, never changed) against it, and is skipped where it is absent.
"""
from __future__ import annotations

import http.client
import json
import os
import pwd
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from jui_cli.viz import clockout

REPO = Path(__file__).resolve().parents[2]
JUI = REPO / "jui_tools" / "bin" / "jui"
DROP = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR", "PYTHONPATH", "CLAUDE_CONFIG_DIR")
#: Read only (copied), from the user's real home: pytest may itself run with HOME set to a temporary folder.
REAL_COMMON = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".claude" / "session-recovery" / "common.sh"
#: The cap of POST /api/session/end, written out so a change of the constant shows.
END_MAX_BODY = 1024


def _env(home: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in DROP}
    env.update(HOME=str(home), PYTHONUNBUFFERED="1", PATH="/usr/bin:/bin")
    return env


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _lstart(pid: int) -> str:
    out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                         env=dict(os.environ, LC_ALL="C", LANG="C", TZ="UTC"))
    return " ".join(out.stdout.split())


class StandIns:
    """Processes this test starts, and only these may ever get a signal."""

    def __init__(self, root: Path):
        self.root = root
        self.procs: dict[int, subprocess.Popen] = {}
        for name, target in (("sleep/claude", "/bin/sleep"), ("bash/claude", "/bin/bash"), ("other/notclaude", "/bin/sleep")):
            link = root / name
            link.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(target, link)

    def start(self, kind: str = "sleep", script: str | None = None) -> subprocess.Popen:
        if kind == "sleep":
            argv = [str(self.root / "sleep" / "claude"), "600"]
        elif kind == "notclaude":
            argv = [str(self.root / "other" / "notclaude"), "600"]
        else:   # a bash called claude running a script (traps)
            path = self.root / f"script-{len(self.procs)}.sh"
            path.write_text(script or "")
            argv = [str(self.root / "bash" / "claude"), str(path)]
        p = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.procs[p.pid] = p
        return p

    def alive(self, p: subprocess.Popen) -> bool:
        return p.poll() is None

    def guarded_kill(self, sent: list):
        """clockout._kill for the in-process arms: records, and sends only to a live stand-in of this test."""
        def kill(pid: int, sig: int) -> None:
            sent.append((pid, sig))
            p = self.procs.get(pid)
            if p is not None and p.poll() is None:
                os.kill(pid, sig)
        return kill

    def cleanup(self):
        for p in self.procs.values():
            if p.poll() is None:
                p.kill()   # our own stand-in
            p.wait(timeout=10)


def write_registry(folder: Path, pid: int, sid: str, entrypoint="cli", kind="interactive", proc_start: str | None = None,
                   pid_field: int | None = None, **extra):
    folder.mkdir(parents=True, exist_ok=True)
    data = {"pid": pid if pid_field is None else pid_field, "sessionId": sid, "cwd": f"/work/{sid[-4:]}", "kind": kind, "entrypoint": entrypoint,
            "procStart": _lstart(pid) if proc_start is None else proc_start, "status": "idle", "startedAt": int(time.time() * 1000)}
    data.update(extra)
    data = {k: v for k, v in data.items() if v is not None}
    path = folder / f"{pid}.json"
    tmp = folder / f".{pid}.tmp"
    tmp.write_text(json.dumps(data))
    os.replace(tmp, path)
    return path


class Viz:
    """`jui viz start` in a temporary HOME; raw requests with every header chosen by the test."""

    def __init__(self, home: Path):
        self.home = home
        self.state = home / ".local" / "state" / "jui-viz"
        self.state.mkdir(parents=True, exist_ok=True)
        self.sessions_dir = home / ".claude" / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        (self.state / "config.json").write_text(json.dumps({"port": _free_port()}))
        started = subprocess.run([sys.executable, str(JUI), "viz", "start", "--json"], env=_env(home), capture_output=True, text=True, timeout=40)
        assert started.returncode == 0, started.stderr
        self.pid = json.loads(started.stdout)["pid"]
        info = json.loads((self.state / "server.json").read_text())
        self.port, self.token = info["port"], info["token"]
        self.own = f"127.0.0.1:{self.port}"

    def alive(self) -> bool:
        try:
            os.kill(self.pid, 0)   # signal 0 to the server this test started: nothing is delivered
        except ProcessLookupError:
            return False
        return True

    def stop(self):
        subprocess.run([sys.executable, str(JUI), "viz", "stop"], env=_env(self.home), capture_output=True, timeout=40)
        if self.alive():
            os.kill(self.pid, signal.SIGTERM)   # the server this test started
        end = time.time() + 10
        while self.alive() and time.time() < end:
            time.sleep(0.1)

    def raw(self, method: str, path: str, headers: dict, body: bytes | None = None, chunked: bool = False):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=40)
        try:
            conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            for k, v in headers.items():
                conn.putheader(k, v)
            if body is not None and not chunked:
                conn.putheader("Content-Length", str(len(body)))
            if chunked:
                conn.putheader("Transfer-Encoding", "chunked")
            conn.endheaders()
            if body is not None:
                if chunked:
                    for i in range(0, len(body), 300):
                        part = body[i:i + 300]
                        conn.send(f"{len(part):x}\r\n".encode() + part + b"\r\n")
                    conn.send(b"0\r\n\r\n")
                else:
                    conn.send(body)
            res = conn.getresponse()
            return res.status, res.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def page_headers(self, **over) -> dict:
        h = {"Host": self.own, "Origin": f"http://{self.own}", "X-Jui-Viz-Token": self.token, "Content-Type": "application/json"}
        h.update(over)
        return {k: v for k, v in h.items() if v is not None}

    def end(self, sid, agent_id=None, method="POST", body: bytes | None = None, chunked=False, **over):
        payload = {"sessionId": sid} if agent_id is None else {"sessionId": sid, "agentId": agent_id}
        data = body if body is not None else json.dumps(payload).encode()
        return self.raw(method, "/api/session/end", self.page_headers(**over), data, chunked)

    def local(self, method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        h = {"Host": self.own, "X-Jui-Viz-Token": self.token}
        if data is not None:
            h["Content-Type"] = "application/json"
        status, text = self.raw(method, path, h, data)
        return status, (json.loads(text) if text.strip().startswith(("{", "[")) else text)

    def snapshot(self) -> dict:
        return self.local("GET", "/api/snapshot")[1]

    def sessions(self) -> dict:
        return {s["id"]: s for s in self.snapshot()["slices"]["sessions"]}

    def agents(self) -> dict:
        return {a["id"]: a for a in self.snapshot()["slices"]["agents"]}

    def log(self) -> list[dict]:
        path = self.state / "clock-out.log"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def wait(self, cond, what: str, timeout: float = 10):
        end = time.time() + timeout
        while time.time() < end:
            if cond():
                return
            time.sleep(0.1)
        raise AssertionError(f"timed out: {what}")

    def session(self, standins: StandIns, n: int, kind="sleep", script=None, **registry):
        """A stand-in process and its ~/.claude/sessions entry; waits until the server lists the session."""
        sid = f"c1000000-0000-4000-8000-{n:012d}"
        p = standins.start(kind, script)
        write_registry(self.sessions_dir, p.pid, sid, **registry)
        self.wait(lambda: sid in self.sessions(), f"the session {sid}")
        return sid, p


@pytest.fixture()
def standins(tmp_path):
    s = StandIns(tmp_path / "standins")
    try:
        yield s
    finally:
        s.cleanup()


@pytest.fixture()
def viz(tmp_path, standins, monkeypatch):
    """Torn down before `standins` (it depends on it): the server stops before any stand-in is reaped."""
    home = tmp_path / "home"
    for k in DROP:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HOME", str(home))
    sr = home / ".claude" / "session-recovery"
    sr.mkdir(parents=True)
    v = Viz(home)
    v.sr = sr
    try:
        yield v
    finally:
        v.stop()


def _refused_untouched(viz: Viz, standins: StandIns, p, sid: str, status: int, response):
    """A refusal: the status, the process alive and untouched, the session not ended, and the attempt in the log."""
    assert response[0] == status, response
    time.sleep(0.3)
    assert standins.alive(p)
    assert viz.sessions()[sid]["status"] != "ended"
    assert viz.log()[-1]["result"] == "refused" and viz.log()[-1]["status"] == status


# ---------------------------------------------------------------- the path that ends a session


def test_a_terminal_session_is_ended_with_one_sigterm_marked_logged_and_its_robot_leaves(viz, standins):
    sid, p = viz.session(standins, 1)
    other, q = viz.session(standins, 2)
    (viz.sr / "active.json").write_text(json.dumps([{"session_id": sid, "name": "a"}, {"session_id": other, "name": "b"}], indent=2))
    assert viz.sessions()[sid]["client"] == "terminal"
    status, text = viz.end(sid)
    assert status == 200, text
    assert json.loads(text) == {"ok": True, "ended": True, "pid": p.pid}
    assert p.wait(timeout=5) == -signal.SIGTERM          # the signal it died of: SIGTERM
    assert standins.alive(q)                              # the other session's process: untouched
    s, a = viz.sessions()[sid], viz.agents()[sid]
    assert s["status"] == "ended" and s["clockedOut"] and a["leftAt"] and a["act"] == "退勤"   # the page walks it out
    ledger = json.loads((viz.sr / "active.json").read_text())
    assert ledger[0]["ended_reason"] == "clocked-out" and ledger[0]["ended_at"].endswith("Z")
    assert "ended_reason" not in ledger[1]
    rec = viz.log()[-1]
    assert (rec["sessionId"], rec["pid"], rec["result"], rec["status"], rec["signalled"], rec["ledger"]) == (sid, p.pid, "ended", 200, True, "marked")
    assert (viz.state / "clock-out.log").stat().st_mode & 0o777 == 0o600


def test_without_a_ledger_nothing_is_written_there(viz, standins):
    sid, p = viz.session(standins, 3)
    assert viz.end(sid)[0] == 200
    assert p.wait(timeout=5) == -signal.SIGTERM
    assert not (viz.sr / "active.json").exists() and list(viz.sr.iterdir()) == []
    assert viz.log()[-1]["ledger"] == "absent"


# ---------------------------------------------------------------- the request checks (server.prompt_checks)


def test_no_token_or_a_wrong_one_is_refused(viz, standins):
    sid, p = viz.session(standins, 10)
    _refused_untouched(viz, standins, p, sid, 401, viz.end(sid, **{"X-Jui-Viz-Token": None}))
    _refused_untouched(viz, standins, p, sid, 401, viz.end(sid, **{"X-Jui-Viz-Token": "x" * 43}))


def test_an_origin_that_is_not_the_page_is_refused_prefixes_included(viz, standins):
    sid, p = viz.session(standins, 11)
    for origin in ("http://evil.example", f"http://localhost:{viz.port}", f"http://127.0.0.1:{viz.port + 1}", "null", None,
                   f"http://127.0.0.1:{viz.port}/", f"http://127.0.0.1:{viz.port}1", f"http://127.0.0.1:{viz.port}.evil.example"):
        _refused_untouched(viz, standins, p, sid, 403, viz.end(sid, Origin=origin))


def test_a_host_that_is_not_the_page_is_refused_prefixes_included(viz, standins):
    sid, p = viz.session(standins, 12)
    # localhost passes the middleware's name check; prompt_checks takes the page's one spelling only
    _refused_untouched(viz, standins, p, sid, 403, viz.end(sid, Host=f"localhost:{viz.port}"))
    # foreign names and prefixed shapes: the middleware (DNS rebinding) answers 421 before the route
    for host in ("evil.example", f"evil.example:{viz.port}", f"127.0.0.1:{viz.port}.evil.example", f"127.0.0.1:{viz.port}1"):
        _refused_untouched(viz, standins, p, sid, 421, viz.end(sid, Host=host))


def test_only_post(viz, standins):
    sid, p = viz.session(standins, 13)
    for method in ("GET", "PUT", "DELETE"):
        _refused_untouched(viz, standins, p, sid, 405, viz.end(sid, method=method))


def test_json_only(viz, standins):
    sid, p = viz.session(standins, 14)
    for ctype in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x", None):
        _refused_untouched(viz, standins, p, sid, 415, viz.end(sid, **{"Content-Type": ctype}))
    _refused_untouched(viz, standins, p, sid, 400, viz.end(sid, body=b"sessionId=" + sid.encode()))
    _refused_untouched(viz, standins, p, sid, 400, viz.end(sid, body=json.dumps([sid]).encode()))


def test_a_body_over_the_cap_is_refused_declared_or_chunked(viz, standins):
    sid, p = viz.session(standins, 15)
    body = json.dumps({"sessionId": sid, "pad": "x" * END_MAX_BODY}).encode()
    assert END_MAX_BODY < len(body) < 8192   # over this route's cap, under /api/prompt's
    _refused_untouched(viz, standins, p, sid, 413, viz.end(sid, body=body))
    _refused_untouched(viz, standins, p, sid, 413, viz.end(sid, body=body, chunked=True))


# ---------------------------------------------------------------- which session and which robot


def test_a_session_not_in_this_servers_list_is_refused(viz, standins):
    sid, p = viz.session(standins, 20)
    status, _ = viz.end("c1000000-0000-4000-8000-999999999999")
    assert status == 404
    # an ended session whose process still runs (SessionEnd came, the process did not go): not in the list to end
    assert viz.local("POST", "/hook", {"hook_event_name": "SessionEnd", "session_id": sid, "reason": "other"})[0] == 204
    viz.wait(lambda: viz.sessions()[sid]["status"] == "ended", "ended by its hook")
    assert viz.end(sid)[0] == 404
    time.sleep(0.3)
    assert standins.alive(p)
    assert viz.log()[-1]["result"] == "refused"


def test_a_subagent_is_refused_and_its_main_session_is_not_ended_for_it(viz, standins):
    sid, p = viz.session(standins, 21)
    sub = "sub-agent-0021"
    assert viz.local("POST", "/hook", {"hook_event_name": "PreToolUse", "session_id": sid, "agent_id": sub, "agent_type": "Explore",
                                       "tool_name": "Read", "tool_input": {"file_path": "/x"}, "tool_use_id": "t1"})[0] == 204
    viz.wait(lambda: sub in viz.agents(), "the subagent")
    _refused_untouched(viz, standins, p, sid, 403, viz.end(sid, agent_id=sub))
    assert viz.end(sub)[0] == 404   # a subagent's id is no session


def test_the_viz_servers_own_pid_is_refused(viz, standins):
    sid = "c1000000-0000-4000-8000-000000000022"
    write_registry(viz.sessions_dir, viz.pid, sid)   # the server's real start time: only the pid check stops it here
    viz.wait(lambda: sid in viz.sessions(), "the session")
    status, text = viz.end(sid)
    assert status == 403 and "this viz server" in text, text
    assert viz.alive()


def test_the_own_pid_check_on_its_own(tmp_path):
    """In-process, with a ps answer that would pass every other check: only the own-pid check refuses."""
    folder = tmp_path / "sessions"
    me = os.getpid()
    write_registry(folder, me, "s-own", proc_start="Mon Oct 19 00:00:00 2026")
    fake = lambda pid: ("S", "Mon Oct 19 00:00:00 2026", "/usr/local/bin/claude --resume x")   # noqa: E731
    assert clockout.check_pid(folder, me, "s-own", own_pid=me, procs=fake) == (403, "that pid is this viz server")
    assert clockout.check_pid(folder, me, "s-own", own_pid=me + 100000, procs=fake) is None   # the arm can be green


def test_a_pid_whose_command_line_is_not_claude_is_refused(viz, standins):
    sid, p = viz.session(standins, 23, kind="notclaude")
    status, text = viz.end(sid)
    assert "not a claude CLI" in text
    _refused_untouched(viz, standins, p, sid, 409, (status, text))


@pytest.mark.parametrize("entrypoint,client,words", [("claude-vscode", "vscode", "VS Code"), ("claude-desktop", "desktop", "デスクトップアプリ"),
                                                     ("sdk-py", "other", "ターミナル"), (None, "unknown", "起動元")])
def test_a_session_not_started_in_a_terminal_is_refused(viz, standins, entrypoint, client, words):
    sid, p = viz.session(standins, 24, entrypoint=entrypoint)
    if entrypoint:
        assert viz.sessions()[sid]["client"] == client
    status, text = viz.end(sid)
    assert words in text, text
    _refused_untouched(viz, standins, p, sid, 409, (status, text))


def test_a_reused_pid_started_at_another_time_is_refused(viz, standins):
    sid, p = viz.session(standins, 25, proc_start="Thu Jan  1 00:00:00 2026")
    status, text = viz.end(sid)
    assert "reused" in text, text
    _refused_untouched(viz, standins, p, sid, 409, (status, text))


def test_an_entry_whose_pid_is_not_its_files_is_refused(viz, standins):
    sid, p = viz.session(standins, 26, pid_field=1)
    status, text = viz.end(sid)
    _refused_untouched(viz, standins, p, sid, 409, (status, text))


# ---------------------------------------------------------------- the race: checked again immediately before the signal


def _race(tmp_path, standins, monkeypatch, between):
    folder = tmp_path / "race-sessions"
    p = standins.start("sleep")
    write_registry(folder, p.pid, "s-race")
    sent: list = []
    monkeypatch.setattr(clockout, "_kill", standins.guarded_kill(sent))
    out = clockout.end_session(folder, "s-race", os.getpid(), before_signal=lambda pid: between(p, folder), wait_sec=2)
    return p, out, sent


def test_a_process_that_exits_between_the_check_and_the_signal_gets_none(tmp_path, standins, monkeypatch):
    def exits(p, folder):
        p.terminate()      # our stand-in ends (as a session ending by itself would) …
        p.wait(timeout=5)  # … and is reaped: from here its pid could be anyone's
    p, out, sent = _race(tmp_path, standins, monkeypatch, exits)
    assert out.result == "refused" and out.status == 409, out
    assert sent == []


def test_a_pid_taken_by_another_session_between_the_checks_gets_none(tmp_path, standins, monkeypatch):
    def rewritten(p, folder):
        write_registry(folder, p.pid, "s-someone-else")
    p, out, sent = _race(tmp_path, standins, monkeypatch, rewritten)
    assert (out.result, out.reason) == ("refused", "the pid's sessionId does not match"), out
    assert sent == [] and standins.alive(p)


def test_a_pid_restarted_between_the_checks_gets_none(tmp_path, standins, monkeypatch):
    def restarted(p, folder):
        write_registry(folder, p.pid, "s-race", proc_start="Thu Jan  1 00:00:00 2026")
    p, out, sent = _race(tmp_path, standins, monkeypatch, restarted)
    assert out.result == "refused" and "reused" in out.reason, out
    assert sent == [] and standins.alive(p)


def test_nothing_between_the_checks_and_it_is_sigterm_once(tmp_path, standins, monkeypatch):
    p, out, sent = _race(tmp_path, standins, monkeypatch, lambda p, folder: None)
    assert out.result == "ended" and sent == [(p.pid, signal.SIGTERM)]


# ---------------------------------------------------------------- the signal: SIGTERM, once, never SIGKILL

RECORD = """for s in TERM INT HUP QUIT USR1 USR2 ALRM; do trap "echo $s >> '{log}'; exit 0" $s; done
while :; do sleep 0.1; done
"""
IGNORE = """trap '' TERM
while :; do sleep 0.1; done
"""


def test_the_signal_is_sigterm(viz, standins, tmp_path):
    log = tmp_path / "signals.txt"
    sid, p = viz.session(standins, 30, kind="bash", script=RECORD.format(log=log))
    assert viz.end(sid)[0] == 200
    p.wait(timeout=5)
    assert log.read_text().split() == ["TERM"]


def test_a_session_that_does_not_end_is_reported_and_never_sigkilled(viz, standins):
    sid, p = viz.session(standins, 31, kind="bash", script=IGNORE)
    time.sleep(0.3)   # the trap is set
    status, text = viz.end(sid)
    assert status == 504 and "nothing more is sent" in text, text
    time.sleep(1.5)
    assert standins.alive(p)                        # no SIGKILL (nor anything else) after the one SIGTERM
    assert viz.sessions()[sid]["status"] != "ended"
    rec = viz.log()[-1]
    assert (rec["result"], rec["signalled"]) == ("not-ended", True)


def test_sigkill_is_not_in_the_code_that_signals():
    import inspect
    code = inspect.getsource(clockout.end_session) + inspect.getsource(clockout._kill)
    assert "SIGKILL" not in code and clockout.SIGNAL == signal.SIGTERM


# ---------------------------------------------------------------- session-recovery's ledger and its lock


def _ledger(tmp_path, entries=None):
    sr = tmp_path / "session-recovery"
    sr.mkdir()
    (sr / "active.json").write_text(json.dumps(entries if entries is not None else [{"session_id": "s1", "name": "a"}], indent=2))
    return sr


def test_the_ledger_waits_for_the_lock_and_writes_after_it_is_released(tmp_path):
    sr = _ledger(tmp_path)
    (sr / ".lock").mkdir()                       # held, as hook.sh holds it
    released = {}

    def release():
        time.sleep(1.0)
        before = (sr / "active.json").read_text()
        released["unchanged_while_held"] = "clocked-out" not in before
        os.rmdir(sr / ".lock")
    t = threading.Thread(target=release)
    t.start()
    t0 = time.monotonic()
    assert clockout.mark_ledger(sr, "s1") == "marked"
    t.join()
    assert time.monotonic() - t0 >= 0.9 and released["unchanged_while_held"]
    assert json.loads((sr / "active.json").read_text())[0]["ended_reason"] == "clocked-out"
    assert not (sr / ".lock").exists()           # released after


def test_a_lock_held_too_long_leaves_the_ledger_alone(tmp_path):
    sr = _ledger(tmp_path)
    (sr / ".lock").mkdir()
    before = (sr / "active.json").read_text()
    assert clockout.mark_ledger(sr, "s1") == "lock timeout"
    assert (sr / "active.json").read_text() == before and (sr / ".lock").is_dir()   # someone else's lock: kept


def test_a_stale_lock_is_taken_over_as_common_sh_does(tmp_path):
    sr = _ledger(tmp_path)
    (sr / ".lock").mkdir()
    old = time.time() - 40
    os.utime(sr / ".lock", (old, old))
    assert clockout.mark_ledger(sr, "s1") == "marked"


def test_no_file_or_no_entry_writes_nothing(tmp_path):
    sr = tmp_path / "sr"
    sr.mkdir()
    assert clockout.mark_ledger(sr, "s1") == "absent" and list(sr.iterdir()) == []
    sr = _ledger(tmp_path, [{"session_id": "other"}])
    before = (sr / "active.json").read_text()
    assert clockout.mark_ledger(sr, "s1") == "no entry" and (sr / "active.json").read_text() == before


@pytest.mark.skipif(not REAL_COMMON.is_file() or not shutil.which("jq"), reason="session-recovery's common.sh (or jq) is not on this machine")
def test_the_lock_is_the_one_common_sh_takes(tmp_path):
    """A copy of session-recovery's own common.sh, in a temporary HOME, holds its lock_acquire across a read, a second's
    wait and a write of the ledger (a hook's read-modify-write, stretched) while mark_ledger runs: both edits survive.
    Without the shared lock mark_ledger writes inside that window and the hook's write puts the old content back."""
    home = tmp_path / "h"
    sr = home / ".claude" / "session-recovery"
    sr.mkdir(parents=True)
    shutil.copy(REAL_COMMON, sr / "common.sh")
    (sr / "active.json").write_text(json.dumps([{"session_id": "s1"}, {"session_id": "s2"}], indent=2))
    script = (f". '{sr}/common.sh'\nlock_acquire || exit 3\nsnap=$(cat \"$ACTIVE\")\necho locked\nsleep 1\n"
              "printf '%s' \"$snap\" | jq 'map(if .session_id == \"s2\" then . + {ended_reason:\"other\"} else . end)' > \"$ACTIVE.tmp.$$\" "
              "&& mv -f \"$ACTIVE.tmp.$$\" \"$ACTIVE\"\nlock_release\n")
    env = {k: v for k, v in os.environ.items() if k not in DROP}
    env["HOME"] = str(home)
    hook = subprocess.Popen(["/bin/bash", "-c", script], env=env, stdout=subprocess.PIPE, text=True)
    assert hook.stdout.readline().strip() == "locked"
    assert clockout.mark_ledger(sr, "s1") == "marked"
    assert hook.wait(timeout=10) == 0
    got = {e["session_id"]: e.get("ended_reason") for e in json.loads((sr / "active.json").read_text())}
    assert got == {"s1": "clocked-out", "s2": "other"}


# ---------------------------------------------------------------- small parts


def test_the_world_ends_a_clocked_out_session_and_logs_each_attempt():
    from jui_cli.viz.ingest import World
    from jui_cli.viz.state import VizState
    w = World(VizState(100))
    w.apply_session_file({"pid": 4242, "sessionId": "s-w", "cwd": "/work/w", "entrypoint": "cli", "status": "idle"}, 1000)
    assert w.sessions["s-w"]["client"] == "terminal"
    w.clock_out_event("s-w", 1500, {"result": "refused", "pid": 4242, "reason": "the pid's command line is not a claude CLI"})
    w.clock_out("s-w", 2000)
    w.clock_out_event("s-w", 2000, {"result": "ended", "pid": 4242})
    s, a = w.sessions["s-w"], w.agents["s-w"]
    assert (s["status"], s["clockedOut"], a["leftAt"], a["act"]) == ("ended", 2000, 2000, "退勤")
    texts = [e["text"] for e in w.state.recent_events()]
    assert texts == [f"退勤の合図 → {s['label']}（pid 4242） 断った: the pid's command line is not a claude CLI",
                     f"退勤の合図 → {s['label']}（pid 4242） 終わった"]



def test_which_command_lines_are_a_claude_cli():
    yes = ["claude", "claude --resume x", "/home/a/.local/bin/claude --channels plugin:jui-viz@jsonui",
           "/home/a/.local/share/claude/versions/2.1.303 --resume x"]
    no = ["", "python3 -m claude", "/usr/bin/claude-helper", "sleep 600", "/x/notclaude", "/x/claude.sh", "/x/claude/versions/latest",
          "/opt/python /x/bin/jui viz serve --port 7788"]
    assert [c for c in yes if not clockout.is_claude_cli(c)] == []
    assert [c for c in no if clockout.is_claude_cli(c)] == []


def test_clients():
    assert [clockout.client_of(e) for e in ("cli", "claude-vscode", "claude-desktop", "sdk-ts", "", None)] == \
        ["terminal", "vscode", "desktop", "other", "unknown", "unknown"]
