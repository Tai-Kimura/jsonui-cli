"""forward.py: hands one hook payload to the server, silently, always exit 0."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

FORWARD = Path(__file__).resolve().parents[1] / "jui_cli" / "viz" / "forward.py"
BODY = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Read", "note": "日本語"}).encode("utf-8")


class _Server:
    def __init__(self, delay: float = 0.0, status: int = 204):
        self.received: list[tuple[dict, bytes]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                outer.received.append((dict(self.headers), body))
                time.sleep(delay)
                self.send_response(status)
                self.end_headers()

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def _server_json(home: Path, port: int, token: str = "tok") -> None:
    folder = home / ".jsonui-cli" / "viz"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "server.json").write_text(json.dumps({"pid": 1, "port": port, "token": token}))


def _run(home: Path, body: bytes = BODY, extra_env: dict | None = None):
    env = dict(os.environ, HOME=str(home), **(extra_env or {}))
    start = time.monotonic()
    done = subprocess.run([sys.executable, "-I", "-S", str(FORWARD)], input=body,
                          capture_output=True, env=env, timeout=20)
    return done, time.monotonic() - start


@pytest.fixture()
def home(tmp_path):
    return tmp_path


def test_no_server_json_exits_quietly(home):
    done, _ = _run(home)
    assert (done.returncode, done.stdout, done.stderr) == (0, b"", b"")


def test_a_running_server_gets_the_body_and_token_unchanged(home):
    server = _Server()
    try:
        _server_json(home, server.port, token="secret-token")
        done, _ = _run(home)
        assert (done.returncode, done.stdout, done.stderr) == (0, b"", b"")
        (headers, body), = server.received
        assert body == BODY
        assert headers["X-Jui-Viz-Token"] == "secret-token"
        assert headers["Host"] == f"127.0.0.1:{server.port}"
        assert int(headers["X-Jui-Viz-Sent-At"]) > 0
    finally:
        server.close()


def test_a_proxy_in_the_environment_is_not_used(home):
    server = _Server()
    try:
        _server_json(home, server.port)
        done, _ = _run(home, extra_env={"HTTP_PROXY": "http://127.0.0.1:9", "http_proxy": "http://127.0.0.1:9"})
        assert done.returncode == 0 and len(server.received) == 1
    finally:
        server.close()


def test_a_slow_server_is_given_up_on_after_about_a_second(home):
    server = _Server(delay=5)
    try:
        _server_json(home, server.port)
        done, took = _run(home)
        assert (done.returncode, done.stdout, done.stderr) == (0, b"", b"")
        assert took < 3.5, took
    finally:
        server.close()


def test_a_refused_token_or_a_dead_port_is_still_silent(home):
    server = _Server(status=401)
    try:
        _server_json(home, server.port, token="wrong")
        done, _ = _run(home)
        assert (done.returncode, done.stdout, done.stderr) == (0, b"", b"")
    finally:
        server.close()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        dead = s.getsockname()[1]
    _server_json(home, dead)
    done, _ = _run(home)
    assert (done.returncode, done.stdout, done.stderr) == (0, b"", b"")


def test_a_broken_server_json_or_an_oversized_body_is_silent(home):
    folder = home / ".jsonui-cli" / "viz"
    folder.mkdir(parents=True)
    (folder / "server.json").write_text("{not json")
    done, _ = _run(home)
    assert (done.returncode, done.stdout, done.stderr) == (0, b"", b"")
    server = _Server()
    try:
        _server_json(home, server.port)
        done, _ = _run(home, body=b"x" * 2_000_001)
        assert done.returncode == 0 and server.received == []
    finally:
        server.close()
