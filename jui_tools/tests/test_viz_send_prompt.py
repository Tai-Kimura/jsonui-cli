"""A prompt typed in the page's 応答の履歴 tab, sent to one session (requester, 10-19).

"やっぱりプロンプトをロボットの会話の履歴から打てないと不便だから打てるようにしよう" — with "別端末からは送れなくていいよ": POST
/api/prompt is taken only from the page itself (server.prompt_checks), queued for the target session's channel only,
and channel.py (jui-viz 1.2.0) hands it to the session as notifications/claude/channel.

The safety arms run against a real `jui viz start` in a temporary HOME on a free port, with raw HTTP requests whose
headers are set by hand (a browser cannot forge Host or Origin; another site's page or a DNS-rebinding name is what
these stand for). The delivery arm runs channel.py itself over stdio, twice, as two sessions. Nothing here starts
claude, and nothing reaches the real viz server.
"""
from __future__ import annotations

import http.client
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from jui_cli.viz import paths
from jui_cli.viz.ingest import PROMPT_HEAD, World

from jui_cli.viz.state import VizState

REPO = Path(__file__).resolve().parents[2]
JUI = REPO / "jui_tools" / "bin" / "jui"
CHANNEL = REPO / "jui_tools" / "jui_cli" / "viz" / "channel.py"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")

S_NEW = "e2e00000-0000-4000-8000-00000000a001"    # relay, jui-viz 1.2.0: can receive
S_NEW2 = "e2e00000-0000-4000-8000-00000000a004"   # relay, jui-viz 1.2.0: a second one (the delivery arm)
S_OLD = "e2e00000-0000-4000-8000-00000000a002"    # relay, jui-viz 1.1.0: cannot receive
S_NONE = "e2e00000-0000-4000-8000-00000000a003"   # relay: false
S_PLAIN = "e2e00000-0000-4000-8000-00000000a005"  # relay, 1.2.0, started without the channels flag (2.3.4)
S_IDE = "e2e00000-0000-4000-8000-00000000a006"    # relay, 1.2.0, the VS Code extension's session (2.3.4)
DEV = "--dangerously-load-development-channels"
#: The cap the requester named (10-19: "例: 8 KB"), written out here so a change of the constant shows.
PROMPT_MAX_BODY = 8192
TEXT = "一行目のプロンプト\n  二行目 \"quoted\" <b>not html</b> \\ 終わり  \n"


def _env(home: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env.update(HOME=str(home), PYTHONUNBUFFERED="1")
    return env


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


class Viz:
    """`jui viz start` in a temporary HOME; raw requests with every header chosen by the test."""

    def __init__(self, home: Path):
        self.home = home
        self.state = home / ".local" / "state" / "jui-viz"
        self.state.mkdir(parents=True, exist_ok=True)
        self.sessions_dir = home / ".claude" / "sessions"   # watched by the server from its start
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.procs: list[subprocess.Popen] = []
        (self.state / "config.json").write_text(json.dumps({"port": _free_port()}))
        started = subprocess.run([sys.executable, str(JUI), "viz", "start", "--json"], env=_env(home), capture_output=True, text=True, timeout=40)
        assert started.returncode == 0, started.stderr
        self.pid = json.loads(started.stdout)["pid"]
        info = json.loads((self.state / "server.json").read_text())
        self.port, self.token = info["port"], info["token"]
        self.own = f"127.0.0.1:{self.port}"

    def session_process(self, sid: str, *args: str, entrypoint: str = "cli") -> int:
        """A stand-in for a session's process: a sleeping python whose argv carries ``args`` (as a terminal session's
        carries its flags), named by a session file as the CLI writes one."""
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)", *args],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.procs.append(proc)
        (self.sessions_dir / f"{proc.pid}.json").write_text(json.dumps({
            "pid": proc.pid, "sessionId": sid, "cwd": f"/work/{sid[-4:]}", "kind": "interactive", "entrypoint": entrypoint,
            "status": "idle", "procStart": f"t{proc.pid}", "startedAt": int(time.time() * 1000)}))
        return proc.pid

    def stop(self):
        for proc in self.procs:   # the stand-ins this test started
            proc.kill()
            proc.wait()
        subprocess.run([sys.executable, str(JUI), "viz", "stop"], env=_env(self.home), capture_output=True, timeout=40)
        if _alive(self.pid):
            os.kill(self.pid, signal.SIGTERM)   # the server this test started

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
                    for i in range(0, len(body), 1000):
                        part = body[i:i + 1000]
                        conn.send(f"{len(part):x}\r\n".encode() + part + b"\r\n")
                    conn.send(b"0\r\n\r\n")
                else:
                    conn.send(body)
            res = conn.getresponse()
            return res.status, res.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def page_headers(self, **over) -> dict:
        """What the page's fetch sends: its own Host and Origin (set by the browser), the token, JSON."""
        h = {"Host": self.own, "Origin": f"http://{self.own}", "X-Jui-Viz-Token": self.token, "Content-Type": "application/json"}
        h.update(over)
        return {k: v for k, v in h.items() if v is not None}

    def prompt(self, sid=S_NEW, text=TEXT, method="POST", body: bytes | None = None, chunked=False, **over):
        data = body if body is not None else json.dumps({"sessionId": sid, "text": text}, ensure_ascii=False).encode("utf-8")
        return self.raw(method, "/api/prompt", self.page_headers(**over), data, chunked)

    def local(self, method: str, path: str, body: dict | None = None):
        """A local process (forward.py, channel.py): token, no Origin."""
        data = json.dumps(body).encode() if body is not None else None
        h = {"Host": self.own, "X-Jui-Viz-Token": self.token}
        if data is not None:
            h["Content-Type"] = "application/json"
        status, text = self.raw(method, path, h, data)
        return status, (json.loads(text) if text.strip().startswith(("{", "[")) else text)

    def sessions(self) -> dict:
        _, snap = self.local("GET", "/api/snapshot")
        return {s["id"]: s for s in snap["slices"]["sessions"]}

    def wait(self, cond, what: str, timeout: float = 10):
        end = time.time() + timeout
        while time.time() < end:
            if cond():
                return
            time.sleep(0.1)
        raise AssertionError(f"timed out: {what}")


@pytest.fixture()
def viz(tmp_path, monkeypatch):
    home = tmp_path / "home"
    for k in ISOLATE:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HOME", str(home))
    v = Viz(home)
    assert paths.viz_home() == home / ".local" / "state" / "jui-viz"
    try:
        for sid in (S_NEW, S_OLD, S_NONE, S_PLAIN, S_IDE):
            assert v.local("POST", "/hook", {"hook_event_name": "SessionStart", "session_id": sid, "cwd": f"/work/{sid[-4:]}", "source": "startup"})[0] == 204
        v.session_process(S_NEW, DEV, "plugin:jui-viz@jsonui", "server:jui-viz")
        v.session_process(S_OLD, DEV, "plugin:jui-viz@jsonui")
        v.session_process(S_PLAIN)                                   # `claude` as typed: no flag
        v.session_process(S_IDE, "--output-format", "stream-json", entrypoint="claude-vscode")
        v.wait(lambda: {S_NEW, S_OLD, S_NONE, S_PLAIN, S_IDE} <= set(v.sessions()), "the sessions")
        ok, new = v.local("POST", "/channel/hello", {"ppid": 1, "cwd": "/", "sessionId": S_NEW, "version": "2", "accepts": ["prompt"]})
        assert ok == 200
        ok, old = v.local("POST", "/channel/hello", {"ppid": 1, "cwd": "/", "sessionId": S_OLD})   # what 1.1.0 says
        assert ok == 200
        for sid in (S_PLAIN, S_IDE):
            assert v.local("POST", "/channel/hello", {"ppid": 1, "cwd": "/", "sessionId": sid, "version": "2", "accepts": ["prompt"], "via": "plugin"})[0] == 200
        v.channels = {"new": new["channelId"], "old": old["channelId"]}
        v.wait(lambda: v.sessions()[S_NEW]["relay"] and v.sessions()[S_OLD]["relay"], "relay on")
        v.wait(lambda: v.sessions()[S_NEW].get("launch") == "dev" and v.sessions()[S_PLAIN].get("launch") == "no-flag"
               and v.sessions()[S_IDE].get("launch") == "vscode", "the launches")
        yield v
    finally:
        v.stop()


def _taken(v: Viz, which: str) -> list:
    """What that channel's next poll gets (a poll with something queued answers at once; else it waits 25 s)."""
    status, got = v.local("GET", f"/channel/poll?channelId={v.channels[which]}")
    assert status == 200
    return got["prompts"]


# ---------------------------------------------------------------- the page's request goes through


def test_the_pages_own_request_is_taken_and_queued_for_that_session_only(viz):
    s = viz.sessions()
    assert (s[S_NEW]["relay"], s[S_NEW]["prompt"]) == (True, True)
    assert (s[S_OLD]["relay"], s[S_OLD]["prompt"]) == (True, False)    # an old plugin: shown so in the page and doctor
    assert (s[S_NONE]["relay"], s[S_NONE]["prompt"]) == (False, False)
    status, text = viz.prompt()
    assert status == 200, text
    assert _taken(viz, "new") == [{"text": TEXT}]                       # exactly as typed
    # the old channel was given nothing (its poll answers after 25 s with nothing; queue checked on the server below)


# ---------------------------------------------------------------- each refusal, everything else valid


def test_no_token_or_a_wrong_one_is_refused(viz):
    assert viz.prompt(**{"X-Jui-Viz-Token": None})[0] == 401
    assert viz.prompt(**{"X-Jui-Viz-Token": "x" * 43})[0] == 401


def test_an_origin_that_is_not_the_page_is_refused(viz):
    for origin in ("http://evil.example", f"http://localhost:{viz.port}", f"http://127.0.0.1:{viz.port + 1}",
                   f"https://127.0.0.1:{viz.port}", "null", None,
                   # shapes that start with the page's origin: equal, not a prefix (the independent check's attack script, 10-19)
                   f"http://127.0.0.1:{viz.port}/", f"http://127.0.0.1:{viz.port}1", f"http://127.0.0.1:{viz.port}.evil.example",
                   f"HTTP://127.0.0.1:{viz.port}"):
        assert viz.prompt(Origin=origin)[0] == 403, origin


def test_a_host_that_is_not_the_pages_own_is_refused(viz):
    """A DNS-rebinding name gets the middleware's 421; localhost:<port> passes the middleware (other routes take it)
    but not this route: the page is served as http://127.0.0.1:<port>/ (jui viz open / start), its only origin."""
    assert viz.prompt(Host=f"rebind.example:{viz.port}")[0] == 421
    assert viz.prompt(Host=f"127.0.0.1:{viz.port + 1}")[0] == 421
    assert viz.prompt(Host=f"localhost:{viz.port}", Origin=f"http://localhost:{viz.port}")[0] == 403
    assert viz.prompt(Host=f"localhost:{viz.port}")[0] == 403
    # shapes that start with the page's own host: equal, not a prefix
    for host in (f"127.0.0.1:{viz.port}0", f"127.0.0.1:{viz.port}.evil.example"):
        assert viz.prompt(Host=host, Origin=f"http://{host}")[0] in (403, 421), host
        assert viz.prompt(Host=host)[0] in (403, 421), host


def test_only_post_is_taken(viz):
    for method in ("GET", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"):
        status, _ = viz.prompt(method=method)
        assert status == 405, method


def test_only_json_is_taken(viz):
    """The three types another site's form may post without a preflight, and others."""
    for ctype in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x", "application/jsonx", None):
        assert viz.prompt(**{"Content-Type": ctype})[0] == 415, ctype


def test_a_body_over_the_cap_is_refused_declared_or_chunked(viz):
    def body_of(n):   # a JSON body of exactly n bytes
        base = json.dumps({"sessionId": S_NEW, "text": ""}).encode()
        return json.dumps({"sessionId": S_NEW, "text": "a" * (n - len(base))}).encode()

    assert len(body_of(PROMPT_MAX_BODY)) == PROMPT_MAX_BODY
    assert viz.prompt(body=body_of(PROMPT_MAX_BODY + 1))[0] == 413
    assert viz.prompt(body=body_of(PROMPT_MAX_BODY + 1), chunked=True)[0] == 413
    assert viz.prompt(body=body_of(PROMPT_MAX_BODY))[0] == 200            # the cap itself is taken
    assert _taken(viz, "new") == [{"text": "a" * (PROMPT_MAX_BODY - len(json.dumps({"sessionId": S_NEW, "text": ""})))}]


def test_a_session_without_relay_or_with_an_old_plugin_or_unknown_is_refused(viz):
    status, why = viz.prompt(sid=S_NONE)
    assert status == 409 and "relay" in why
    status, why = viz.prompt(sid=S_OLD)
    assert status == 409 and "1.2.0" in why
    assert viz.prompt(sid="e2e00000-0000-4000-8000-0000000000ff")[0] == 404
    assert viz.prompt(body=b'{"sessionId": "' + S_NEW.encode() + b'", "text": "   "}')[0] == 400
    assert viz.prompt(body=b"not json")[0] == 400


def test_nothing_refused_was_queued(viz):
    viz.prompt(**{"X-Jui-Viz-Token": None})
    viz.prompt(Origin="http://evil.example")
    viz.prompt(Host=f"localhost:{viz.port}")
    viz.prompt(method="GET")
    viz.prompt(**{"Content-Type": "text/plain"})
    viz.prompt(sid=S_OLD)
    status, _ = viz.prompt(text="the only one taken")
    assert status == 200
    assert _taken(viz, "new") == [{"text": "the only one taken"}]


def test_the_server_listens_on_loopback_only_and_has_no_way_to_change_it(viz):
    out = subprocess.run(["lsof", "-nP", "-a", "-p", str(viz.pid), "-iTCP", "-sTCP:LISTEN"], capture_output=True, text=True, timeout=20).stdout
    names = [line.split()[8] for line in out.splitlines()[1:] if len(line.split()) > 8]
    assert names == [f"127.0.0.1:{viz.port}"], out
    # no address of this machine but loopback answers on the port
    addrs = set()
    try:
        addrs |= {ai[4][0] for ai in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        pass
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as u:   # the address of the default route (a UDP connect sends nothing)
        try:
            u.connect(("192.0.2.1", 9))
            addrs.add(u.getsockname()[0])
        except OSError:
            pass
    lan = sorted(a for a in addrs if not a.startswith("127.") and a != "0.0.0.0")
    print("non-loopback addresses tried:", lan)
    for addr in lan:
        with socket.socket() as s:
            s.settimeout(2)
            assert s.connect_ex((addr, viz.port)) != 0, addr
    # no option and no config key to bind elsewhere
    for flag in ("--host", "--bind", "--address", "--listen"):
        rc = subprocess.run([sys.executable, str(JUI), "viz", "serve", flag, "0.0.0.0"], env=_env(viz.home), capture_output=True, timeout=30).returncode
        assert rc == 2, flag   # argparse: unrecognized argument
    from jui_cli.viz.config import VizConfig
    from dataclasses import fields
    assert not {f.name.lower() for f in fields(VizConfig)} & {"host", "bind", "address", "listen"}


# ---------------------------------------------------------------- the event log and what is kept


def _started_right(world, sid):
    """The session's process as a terminal session started with the flag (sources/launch.py)."""
    world.read_argv = lambda pid: ["claude", DEV, "plugin:jui-viz@jsonui"]
    world.apply_agents_list([{"sessionId": sid, "pid": 4242, "cwd": "/work/a", "entrypoint": "cli"}], 2)


def test_the_event_log_gets_the_time_the_target_and_the_head_only():
    state = VizState()
    world = World(state)
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/work/a"}, 1)
    channel_id = world.channel_hello(None, None, "s1", 2, ["prompt"])
    _started_right(world, "s1")
    world.publish()
    long = "先頭の文 " + "x" * 300 + " TAIL-SECRET"
    assert world.send_prompt("s1", long, 3) is None
    world.publish()
    (event,) = [e for e in state.events if e["kind"] == "PromptSent"]
    assert event["at"] == 3 and event["sessionId"] == "s1" and event["cat"] == "perm"
    assert "先頭の文" in event["text"] and "TAIL-SECRET" not in event["text"] and len(event["text"]) < PROMPT_HEAD + 40
    # nowhere in the state the page, a snapshot or an export is made from
    assert "TAIL-SECRET" not in json.dumps(state.snapshot(), ensure_ascii=False)
    assert "TAIL-SECRET" not in json.dumps(list(state.events), ensure_ascii=False)
    # handed to the channel once, then gone from the server
    assert world.perms.take_prompts(channel_id) == [{"text": long, "at": 3}]
    assert world.perms.take_prompts(channel_id) == []


def test_a_channel_that_does_not_take_its_prompts_is_not_flooded():
    world = World(VizState())
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/work/a"}, 1)
    world.channel_hello(None, None, "s1", 2, ["prompt"])
    _started_right(world, "s1")
    results = [world.send_prompt("s1", f"p{i}", 3) for i in range(7)]
    assert results[:5] == [None] * 5 and results[5][0] == 429


# ---------------------------------------------------------------- delivery: channel.py, two sessions


def _start_channel(home: Path, sid: str) -> subprocess.Popen:
    """channel.py as the session runs it, under a parent shell whose pid names the session (~/.claude/sessions/<pid>.json)."""
    # The shell stands for the session's process, so its argv carries the launch flag (sh -c's own $0 $1 …): the
    # session file below names it, and the server reads that argv (2.3.4). channel.py here is the package's copy,
    # connected as "mcp", so the flag names server:jui-viz.
    proc = subprocess.Popen(["/bin/sh", "-c", f'"{sys.executable}" -I "{CHANNEL}"; status=$?; exit $status',
                             "sh", DEV, "server:jui-viz"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=_env(home), cwd="/")
    sessions = home / ".claude" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / f"{proc.pid}.json").write_text(json.dumps({"pid": proc.pid, "sessionId": sid, "entrypoint": "cli", "procStart": f"c{proc.pid}"}))
    for msg in ({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"}):
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()
    init = json.loads(proc.stdout.readline())
    assert init["id"] == 1 and init["result"]["serverInfo"] == {"name": "jui-viz", "version": "2"}
    return proc


def _lines(proc: subprocess.Popen, seconds: float) -> list:
    import selectors

    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ)
    out, end = [], time.time() + seconds
    while time.time() < end:
        if sel.select(timeout=max(0.0, end - time.time())):
            line = proc.stdout.readline()
            if not line:
                break
            out.append(json.loads(line))
            end = min(end, time.time() + 1.5)   # after one arrives, a short tail for anything else
    sel.close()
    return out


def test_a_prompt_reaches_only_the_target_sessions_channel_with_the_exact_text(viz):
    viz.local("POST", "/hook", {"hook_event_name": "SessionStart", "session_id": S_NEW2, "cwd": "/work/a004", "source": "startup"})
    viz.wait(lambda: S_NEW2 in viz.sessions(), "the second session")
    one, two = _start_channel(viz.home, S_NEW), _start_channel(viz.home, S_NEW2)
    try:
        viz.wait(lambda: viz.sessions()[S_NEW2]["prompt"], "the second channel")
        # its session file is read by the server's watcher, in its own time: wait for the launch it gives
        viz.wait(lambda: viz.sessions()[S_NEW2].get("launch") == "dev" and viz.sessions()[S_NEW].get("launch") == "dev", "the launches")
        # S_NEW has two channels now (the fixture's hello and channel.py's): the prompt goes to the one seen last,
        # which is channel.py's — it polls; the fixture's never does.
        time.sleep(1.0)
        status, why = viz.prompt(sid=S_NEW2, text=TEXT)
        assert status == 200, why
        got_two, got_one = _lines(two, 10), _lines(one, 3)
        assert got_two == [{"jsonrpc": "2.0", "method": "notifications/claude/channel",
                            "params": {"content": TEXT, "meta": {"sender": "jui_viz_page"}}}]
        assert got_one == []
        status, why = viz.prompt(sid=S_NEW, text="to the first")
        assert status == 200, why
        got_one, got_two = _lines(one, 10), _lines(two, 3)
        assert [m["params"]["content"] for m in got_one] == ["to the first"] and got_two == []
    finally:
        for proc in (one, two):
            proc.stdin.close()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    assert one.returncode == 0 and two.returncode == 0


# ---------------------------------------------------------------- doctor


def test_doctor_names_the_sessions_whose_plugin_cannot_receive_and_those_started_without_the_flag(viz):
    out = subprocess.run([sys.executable, str(JUI), "viz", "doctor", "--json"], env=_env(viz.home), capture_output=True, text=True, timeout=60).stdout
    (check,) = [c for c in json.loads(out)["checks"] if c["name"] == "prompt"]
    s = viz.sessions()
    assert "1 session(s) reached (4 with the relay / 5 in all)" in check["detail"], check
    assert "1 session(s) with a jui-viz plugin older than 1.2.0" in check["detail"] and s[S_OLD]["label"] in check["detail"]
    assert f"1 not reached ({s[S_PLAIN]['label']}): started naming no channel" in check["detail"]
    assert f"1 not reached ({s[S_IDE]['label']}): a VS Code extension session" in check["detail"]
    assert "claude --dangerously-load-development-channels plugin:jui-viz@jsonui" in check["detail"]
    assert "claude --channels plugin:jui-viz@jsonui (no warning)" in check["detail"]
    assert '"allowedChannelPlugins": [{"plugin": "jui-viz", "marketplace": "jsonui"}]' in check["detail"] and "channelsEnabled" in check["detail"]


# ---------------------------------------------------------------- 2.3.4: the CLI drops a channel's text unless it was named at launch


def test_a_session_started_without_the_flag_or_in_the_extension_is_refused(viz):
    status, why = viz.prompt(sid=S_PLAIN)
    assert status == 409 and "no-flag" in why and "--dangerously-load-development-channels plugin:jui-viz@jsonui" in why
    status, why = viz.prompt(sid=S_IDE)
    assert status == 409 and "vscode" in why
    assert viz.prompt(sid=S_NEW)[0] == 200


def test_a_session_whose_process_is_gone_or_unnamed_is_refused(tmp_path):
    world = World(VizState())
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/w"}, 1)
    world.channel_hello(None, None, "s1", 2, ["prompt"], "plugin")
    assert world.send_prompt("s1", "x", 3)[0] == 409                    # no session file: no pid to read
    world.read_argv = lambda pid: None                                   # a pid whose argv cannot be read
    world.apply_agents_list([{"sessionId": "s1", "pid": 4242, "cwd": "/w", "entrypoint": "cli"}], 4)
    status, why = world.send_prompt("s1", "x", 5)
    assert status == 409 and "unreadable" in why
    world.read_argv = lambda pid: ["claude", DEV, "plugin:jui-viz@jsonui"]
    world.apply_agents_list([{"sessionId": "s1", "pid": 4243, "procStart": "b", "cwd": "/w", "entrypoint": "cli"}], 6)
    assert world.send_prompt("s1", "x", 7) is None                       # a new process of the session, started right
    world.publish()
    assert world.state.slices["sessions"][0]["launch"] == "dev"
    assert "plugin:jui-viz" not in json.dumps(world.state.snapshot())    # the classification only, never the argv


from jui_cli.viz.sources import launch  # noqa: E402


def test_the_launch_flags_are_read_as_the_cli_reads_them():
    c = launch.classify
    assert c(["claude", DEV, "plugin:jui-viz@jsonui"]) == "dev"
    assert c(["claude", DEV, "plugin:jui-viz@jsonui"], via="plugin") == "dev"
    assert c(["claude", DEV, "server:jui-viz"], via="mcp") == "dev"
    assert c(["claude", f"{DEV}=plugin:jui-viz@jsonui"]) == "dev"                                    # one value after =
    assert c(["claude", DEV, "server:other", "plugin:jui-viz@jsonui", "--model", "x"]) == "dev"      # variadic
    assert c(["claude", DEV, "server:jui-viz"], via="plugin") == "form"                              # names the other form
    assert c(["claude", DEV, "plugin:jui-viz@jsonui"], via="mcp") == "form"
    assert c(["claude", DEV, "plugin:jui-viz@elsewhere"]) == "form"                                  # another marketplace
    assert c(["claude", "--channels", "plugin:jui-viz@jsonui"]) == "channels"
    assert c(["claude", "--channels=plugin:jui-viz@jsonui"]) == "channels"
    assert c(["claude", "--channels", "plugin:x@y", "--channels", "plugin:jui-viz@jsonui"]) == "channels"     # repeated
    assert c(["claude", "--channels", "plugin:x@y,plugin:jui-viz@jsonui"]) == "other"                        # no comma lists
    assert c(["claude", "--channels", "server:jui-viz"]) == "server-channels"
    assert c(["claude", DEV, "server:other"]) == "other"
    assert c(["claude", "--channels", "plugin:x@y"]) == "other"
    assert c(["claude", "--model", "x", "plugin:jui-viz@jsonui"]) == "no-flag"                     # not after the flag
    assert c(["claude", DEV, "--model", "plugin:jui-viz@jsonui"]) == "no-flag"                     # the flag got no value
    assert c(["claude"]) == "no-flag"
    assert c(None) == "unreadable"
    assert c(["claude", DEV, "plugin:jui-viz@jsonui"], entrypoint="claude-vscode") == "vscode"
    assert c(["claude"], entrypoint="claude-desktop") == "desktop"
    assert c(["/x/native-binary/claude", "--output-format", "stream-json"]) == "desktop"
    assert c(["/x/.vscode/extensions/a/native-binary/claude", "--output-format", "stream-json"]) == "vscode"
    assert [k for k, (ok, _) in launch.REASONS.items() if ok] == ["dev", "channels"]


def test_the_argv_of_a_process_is_read_exactly():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", DEV, "plugin:jui-viz@jsonui", "a b"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        argv = None
        for _ in range(50):
            argv = launch.read_argv(proc.pid)
            if argv and argv[-1] == "a b":
                break
            time.sleep(0.05)
        assert argv is not None and argv[-3:] == [DEV, "plugin:jui-viz@jsonui", "a b"], argv     # a space stays inside
    finally:
        proc.kill()
        proc.wait()
    assert launch.read_argv(proc.pid) is None                                                     # gone
    assert launch.read_argv(1) is None and launch.read_argv(None) is None


def test_the_channel_says_how_it_is_connected():
    sys.path.insert(0, str(CHANNEL.parent))
    try:
        import channel as ch
        assert ch.via() == "mcp"
    finally:
        sys.path.pop(0)
    plugin_copy = REPO / "plugins" / "jui-viz" / "scripts" / "channel.py"
    out = subprocess.run([sys.executable, "-I", "-c", "import runpy,sys; m=runpy.run_path(sys.argv[1]); print(m['via']())", str(plugin_copy)],
                         capture_output=True, text=True, timeout=20).stdout.strip()
    assert out == "plugin"


def test_a_channel_record_of_the_receivers_transcript_is_a_channel_item():
    """The record the CLI wrote on a real receiver (10-19 09:20, a terminal session started with --channels
    plugin:jui-viz@jsonui; the shape copied, the text replaced)."""
    from jui_cli.viz.sources import history

    rec = {"type": "user", "isMeta": True, "promptSource": "system", "timestamp": "2026-10-19T00:20:50.811Z",
           "origin": {"kind": "channel", "server": "plugin:jui-viz:jui-viz"}, "userType": "external", "entrypoint": "cli",
           "message": {"role": "user", "content": '<channel source="plugin:jui-viz:jui-viz" sender="jui_viz_page">\n一行目\n  二行目 \n</channel>'}}
    assert history.items_of(rec, {}) == [{"kind": "channel", "server": "plugin:jui-viz:jui-viz", "text": "一行目\n  二行目 ",
                                          "cut": False, "at": 1792369250811}]
    plain = dict(rec, origin=None, isMeta=False, message={"role": "user", "content": "一行目"})
    assert history.items_of(plain, {})[0]["kind"] == "user"     # the same words typed by hand are not a channel item


# Real command lines read on this machine (10-19 09:2x, ps / sysctl, read only; nothing sent to those sessions),
# anonymised: the home folder is /home/user, session ids are zeros, the desktop app's tool list is cut short.
REAL_TERMINAL = ["claude"]                                   # pids 37357, 37799, 48134 (entrypoint cli), started as typed
REAL_VSCODE = ["/opt/u/.vscode/extensions/anthropic.claude-code-2.1.301-darwin-arm64/resources/native-binary/claude",
               "--output-format", "stream-json", "--verbose", "--input-format", "stream-json", "--max-thinking-tokens=31999",
               "--permission-prompt-tool=stdio", "--resume=00000000-0000-0000-0000-000000000000",
               "--setting-sources=user,project,local", "--permission-mode=auto", "--include-partial-messages",
               "--add-dir=/opt/u/resource/a", "--debug", "--debug-to-stderr", "--enable-auth-status", "--no-chrome",
               "--replay-user-messages"]                       # pids 35927, 36312 (entrypoint claude-vscode)
REAL_DESKTOP = ["/opt/u/Library/Application Support/Claude/claude-code/2.1.299/4fa9694b7975/claude.app/Contents/MacOS/claude",
                "--output-format", "stream-json", "--verbose", "--input-format", "stream-json", "--model=m",
                "--permission-prompt-tool=stdio", "--allowedTools=mcp__computer-use,mcp__ccd_session__spawn_task"]   # pid 92944


def test_the_launch_is_told_from_the_command_line_alone():
    """No entrypoint given: the argv decides. The three shapes that reach a session are the terminal's argv with the
    flag the shell passes (no such process was running to read; the CLI's parser takes one argument per entry)."""
    c = launch.classify
    assert c(REAL_TERMINAL + ["--channels", "plugin:jui-viz@jsonui"]) == "channels"
    assert c(REAL_TERMINAL + [DEV, "plugin:jui-viz@jsonui"]) == "dev"
    assert c(REAL_TERMINAL + [DEV, "server:jui-viz"], via="mcp") == "dev"
    assert all(launch.REASONS[k][0] for k in ("channels", "dev"))
    assert c(REAL_TERMINAL) == "no-flag"
    assert c(REAL_VSCODE) == "vscode"
    assert c(REAL_DESKTOP) == "desktop"
    assert not any(launch.REASONS[k][0] for k in ("no-flag", "vscode", "desktop"))


def test_a_failed_read_of_the_argv_is_tried_again_and_a_good_one_kept():
    """The independent check's repro (10-19): a reader that fails once and then reads. The failure is not kept — the session was
    "unreadable" (prompts refused) until viz restarted — the next read comes after a wait (never every frame), and the
    argv read is kept for the process."""
    world = World(VizState())
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/w"}, 1)
    world.channel_hello(None, None, "s1", 2, ["prompt"], "plugin")
    calls = []

    def reader(pid):
        calls.append(pid)
        return None if len(calls) == 1 else ["claude", DEV, "plugin:jui-viz@jsonui"]

    now = [100.0]
    world.read_argv, world.clock = reader, (lambda: now[0])
    world.apply_agents_list([{"sessionId": "s1", "pid": 4242, "procStart": "a", "cwd": "/w", "entrypoint": "cli"}], 3)
    assert world.launch_of("s1") == "unreadable" and len(calls) == 1          # the first read fails
    now[0] += 0.2
    assert world.launch_of("s1") == "unreadable" and len(calls) == 1          # not again at once
    now[0] += 1.0
    assert world.launch_of("s1") == "dev" and len(calls) == 2                 # read again after the wait: dev
    now[0] += 100
    assert world.launch_of("s1") == "dev" and world.send_prompt("s1", "x", 4) is None and len(calls) == 2   # kept
    # a process that keeps failing is read at most with the wait doubling (1, 2, 4 … 30 s), not on every call
    world.read_argv = lambda pid: (calls.append(pid), None)[1]
    world.apply_agents_list([{"sessionId": "s1", "pid": 4243, "procStart": "b", "cwd": "/w", "entrypoint": "cli"}], 5)
    before, t0 = len(calls), now[0]
    while now[0] < t0 + 60:
        world.launch_of("s1")
        now[0] += 0.5
    assert len(calls) - before == 6, len(calls) - before                      # read at 0, 1, 3, 7, 15 and 31 s: 6 in a minute
