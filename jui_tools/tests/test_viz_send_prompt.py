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
        (self.state / "config.json").write_text(json.dumps({"port": _free_port()}))
        started = subprocess.run([sys.executable, str(JUI), "viz", "start", "--json"], env=_env(home), capture_output=True, text=True, timeout=40)
        assert started.returncode == 0, started.stderr
        self.pid = json.loads(started.stdout)["pid"]
        info = json.loads((self.state / "server.json").read_text())
        self.port, self.token = info["port"], info["token"]
        self.own = f"127.0.0.1:{self.port}"

    def stop(self):
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
        for sid in (S_NEW, S_OLD, S_NONE):
            assert v.local("POST", "/hook", {"hook_event_name": "SessionStart", "session_id": sid, "cwd": f"/work/{sid[-4:]}", "source": "startup"})[0] == 204
        v.wait(lambda: {S_NEW, S_OLD, S_NONE} <= set(v.sessions()), "the sessions")
        ok, new = v.local("POST", "/channel/hello", {"ppid": 1, "cwd": "/", "sessionId": S_NEW, "version": "2", "accepts": ["prompt"]})
        assert ok == 200
        ok, old = v.local("POST", "/channel/hello", {"ppid": 1, "cwd": "/", "sessionId": S_OLD})   # what 1.1.0 says
        assert ok == 200
        v.channels = {"new": new["channelId"], "old": old["channelId"]}
        v.wait(lambda: v.sessions()[S_NEW]["relay"] and v.sessions()[S_OLD]["relay"], "relay on")
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
                   # shapes that start with the page's origin: equal, not a prefix (dd's attack script, 10-19)
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


def test_the_event_log_gets_the_time_the_target_and_the_head_only():
    state = VizState()
    world = World(state)
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/work/a"}, 1)
    channel_id = world.channel_hello(None, None, "s1", 2, ["prompt"])
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
    results = [world.send_prompt("s1", f"p{i}", 3) for i in range(7)]
    assert results[:5] == [None] * 5 and results[5][0] == 429


# ---------------------------------------------------------------- delivery: channel.py, two sessions


def _start_channel(home: Path, sid: str) -> subprocess.Popen:
    """channel.py as the session runs it, under a parent shell whose pid names the session (~/.claude/sessions/<pid>.json)."""
    proc = subprocess.Popen(["/bin/sh", "-c", f'"{sys.executable}" -I "{CHANNEL}"; status=$?; exit $status'],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=_env(home), cwd="/")
    sessions = home / ".claude" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / f"{proc.pid}.json").write_text(json.dumps({"pid": proc.pid, "sessionId": sid}))
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


def test_doctor_names_the_sessions_whose_plugin_cannot_receive(viz):
    out = subprocess.run([sys.executable, str(JUI), "viz", "doctor", "--json"], env=_env(viz.home), capture_output=True, text=True, timeout=60).stdout
    (check,) = [c for c in json.loads(out)["checks"] if c["name"] == "prompt"]
    old_label = viz.sessions()[S_OLD]["label"]
    assert "送れるセッション 1（中継あり 2 / 全 3）" in check["detail"]
    assert "1.2.0 より古いセッション 1" in check["detail"] and old_label in check["detail"]
