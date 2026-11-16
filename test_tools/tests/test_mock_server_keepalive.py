"""A kept-alive connection must not hold a thread and a descriptor forever.

The mock server speaks HTTP/1.1, so a connection stays open after its
response, and with it the thread serving it and the descriptor under it.
Nothing closed an idle one — `BaseHTTPRequestHandler.timeout` is None — so a
client that abandons connections instead of closing them (a browser
reloading between tests) left one of each behind every time.

Measured 2026-09-03 against the shipped 1.8.20 server, one abandoned
keep-alive connection at a time under a 64-descriptor limit:

    abandoned  25 -> threads 26   50 -> threads 51   59 -> threads 60
    at 59 the server stopped accepting: a new client got ECONNRESET while
    the server PROCESS WAS STILL ALIVE, and 35s later it was still wedged.

That is what a consumer reported as "the mock server dies mid-run": it had
not died, it had run out of descriptors and could no longer accept, which
from the client side reads the same. It appeared right after a scenario
switch (a reload opens a burst of connections) and only in the full chain
(a single spec never reached the ceiling). Nothing in the version it was
blamed on touched this file — the leak was as old as the keep-alive.

The same experiment against the fixed server saturates identically and then
RECOVERS: 35s later, threads 1, descriptors back to baseline, serving again.
That experiment needs a lowered descriptor limit and 35 seconds, so it lives
in the bug report; what is pinned here is the value, its effect, and the
diagnostic.
"""

from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.mock import server as server_mod
from jsonui_test_cli.mock.server import MockServer, MockStore, RunManager


def _serve(tmp_path) -> MockServer:
    store = MockStore.load(tmp_path)
    srv = MockServer(store, RunManager({}, Path(tmp_path)), port=0)
    srv.bind()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _read_one_response(sock) -> bytes:
    """Consume exactly one HTTP response: headers, then Content-Length bytes.

    A single recv() is not one response — headers and body arrive in
    separate segments often enough that leaving the body in the buffer made
    a later "did the server close this?" read return the leftover body
    instead of EOF, on two runs in five. The flake was in the client here,
    not in the server.
    """
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            return buf
        buf += chunk
    head, _, body = buf.partition(b"\r\n\r\n")
    length = 0
    for line in head.split(b"\r\n"):
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":")[1])
    while len(body) < length:
        chunk = sock.recv(4096)
        if not chunk:
            break
        body += chunk
    return head + b"\r\n\r\n" + body


def _get(port: int, keep_open: bool):
    """One request on a fresh connection; returns the socket, kept open."""
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    s.sendall(b"GET /nothing HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n\r\n" % port)
    _read_one_response(s)
    if not keep_open:
        s.close()
        return None
    return s


def _wait_until(predicate, timeout=6.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _quiet_thread_count() -> int:
    """A baseline that has stopped moving.

    `threading.active_count()` is process-global: a serving thread from an
    earlier test in the same session may still be exiting, so a baseline read
    once can drift under the test that reads it. Wait for two identical
    readings, and compare with >= / <= rather than == so a stale thread
    finishing mid-test cannot decide the verdict. (Measured: the first
    version used == and failed on two of five runs for exactly that.)
    """
    last = threading.active_count()
    for _ in range(100):
        time.sleep(0.05)
        now = threading.active_count()
        if now == last:
            return now
        last = now
    return last


class TestTheIdleTimeoutShips:
    """Arm 1: the VALUE. Fails if the attribute is dropped or set to None —
    which is the state the leak was found in."""

    def test_the_constant_is_finite_and_positive(self):
        assert isinstance(server_mod.IDLE_KEEPALIVE_TIMEOUT, (int, float))
        assert 0 < server_mod.IDLE_KEEPALIVE_TIMEOUT <= 120

    def test_the_handler_actually_carries_it(self, tmp_path):
        # The constant is not the contract; what the handler class carries
        # is. A constant nobody reads would satisfy the test above alone.
        srv = _serve(tmp_path)
        handler = srv._httpd.RequestHandlerClass
        assert handler.timeout == server_mod.IDLE_KEEPALIVE_TIMEOUT
        assert handler.timeout is not None
        srv.shutdown()


class TestTheTimeoutHasTheEffect:
    """Arm 2: the EFFECT — that a timeout, in THIS configuration (HTTP/1.1 +
    ThreadingHTTPServer), does close an idle keep-alive and release its
    thread.

    This arm shortens the timeout so the suite stays fast, which means it
    CANNOT fail for a missing shipped value: supplying 0.5 is exactly what
    the fix supplies. Arm 1 above is what fails in that case. Neither arm
    alone is the guard.
    """

    def test_an_idle_connection_is_closed_and_its_thread_released(self, tmp_path, monkeypatch):
        monkeypatch.setattr(server_mod, "IDLE_KEEPALIVE_TIMEOUT", 0.5)
        srv = _serve(tmp_path)
        base = _quiet_thread_count()
        sock = _get(srv.port, keep_open=True)
        # served, then deliberately abandoned: still open, holding a thread
        assert _wait_until(lambda: threading.active_count() >= base + 1), \
            "the connection held no thread — this arm is not measuring the leak"

        # the server closes it on its own; the client sees EOF
        sock.settimeout(5)
        assert sock.recv(4096) == b"", "the server did not close the idle keep-alive connection"
        assert _wait_until(lambda: threading.active_count() <= base), \
            "the serving thread was not released"
        sock.close()
        srv.shutdown()

    def test_several_abandoned_connections_are_all_reclaimed_and_service_continues(
            self, tmp_path, monkeypatch):
        # The leak's shape is cumulative, so the arm is too: five abandoned
        # connections, all five threads back afterwards, and the next client
        # still served (a closed keep-alive is the ordinary end of a
        # connection — the client opens another).
        #
        # The thread-count assertion is what makes this arm fail without the
        # fix. Without it the arm passed either way: with no descriptor
        # pressure a new client is served whether or not anything is ever
        # reclaimed, which measures nothing. (Registered as a 3-failure
        # prediction, measured 2 — this was the arm that did not fire.)
        monkeypatch.setattr(server_mod, "IDLE_KEEPALIVE_TIMEOUT", 0.5)
        srv = _serve(tmp_path)
        base = _quiet_thread_count()
        abandoned = [_get(srv.port, keep_open=True) for _ in range(5)]
        assert _wait_until(lambda: threading.active_count() >= base + 5), \
            "five connections did not hold five threads"
        assert _wait_until(lambda: threading.active_count() <= base), \
            "abandoned connections were not reclaimed"

        s = socket.create_connection(("127.0.0.1", srv.port), timeout=5)
        s.sendall(b"GET /nothing HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nConnection: close\r\n\r\n" % srv.port)
        assert b"404" in _read_one_response(s)  # served (no mocks loaded), not refused
        s.close()
        for sock in abandoned:
            sock.close()
        srv.shutdown()


class TestDescriptorExhaustionIsNotSilent:
    """socketserver swallows an accept() failure, so a wedged server printed
    nothing at all and read, from outside, as a dead one. The report cost two
    full suite runs and a version accusation before anyone asked whether the
    process was still alive."""

    class _Accept:
        def __init__(self, err):
            self.err = err

        def accept(self):
            raise self.err

    def _server_that_cannot_accept(self, err):
        srv = server_mod._MockHTTPServer.__new__(server_mod._MockHTTPServer)
        srv.socket = self._Accept(err)
        srv.address_family = socket.AF_INET
        return srv

    def test_it_says_so_once_per_server(self, capsys):
        import errno as errno_mod
        srv = self._server_that_cannot_accept(OSError(errno_mod.EMFILE, "Too many open files"))
        for _ in range(3):
            try:
                srv.get_request()
            except OSError:
                pass
        err = capsys.readouterr().err
        assert err.count("out of file descriptors") == 1, err
        # the sentence has to carry the diagnosis, not just the errno
        assert "still running" in err

    def test_other_accept_errors_are_not_dressed_up_as_exhaustion(self, capsys):
        import errno as errno_mod
        srv = self._server_that_cannot_accept(OSError(errno_mod.ECONNABORTED, "aborted"))
        try:
            srv.get_request()
        except OSError:
            pass
        assert "out of file descriptors" not in capsys.readouterr().err
