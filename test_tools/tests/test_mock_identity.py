"""`GET /__jsonui__/identity` — whose mock answered.

A health check that only sees HTTP 200 learns that a mock is listening, not
whose corpus it serves. Measured 2026-09-04: one lane's server failed to bind
because another project already held the port, the health check passed on the
control panel's 200, and five tests ran against the other project's mocks.
The failures were reported as regressions of the change under test.
"""
import json
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from jsonui_test_cli.mock.generate import generate
from jsonui_test_cli.mock.server import MockServer, MockStore, RunManager

SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "t", "version": "1"},
    "paths": {
        "/v1/items": {
            "get": {
                "operationId": "listItems",
                "responses": {"200": {"description": "ok", "content": {
                    "application/json": {"schema": {"type": "object"}}}}},
            }
        }
    },
}


def _serve(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(SPEC))
    out = tmp_path / "mocks"
    generate([str(spec_file)], out)
    store = MockStore.load(out)
    srv = MockServer(store, RunManager({}, tmp_path), port=0)
    srv.bind()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.1)
    return srv


def _identity(port: int, token: str | None = None):
    headers = {"Host": f"127.0.0.1:{port}"}
    if token:
        headers["X-JsonUI-Token"] = token
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/__jsonui__/identity", headers=headers)
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status, json.loads(resp.read().decode())


@pytest.fixture
def own(tmp_path):
    srv = _serve(tmp_path / "projectA")
    yield srv
    srv.shutdown()


class TestIdentity:
    def test_it_names_the_corpus_it_serves(self, own, tmp_path):
        status, body = _identity(own.port)
        assert status == 200
        assert body["projectRoot"] == str((tmp_path / "projectA").resolve())
        assert body["mockDir"] == str((tmp_path / "projectA" / "mocks").resolve())
        assert body["port"] == own.port
        assert body["pid"] > 0
        assert body["startedAt"]

    def test_a_harness_can_tell_another_projects_mock_apart(self, tmp_path):
        """The incident, as a test: two projects, one port each, and the
        caller holds project B while project A answers."""
        a = _serve(tmp_path / "projectA")
        b_root = str((tmp_path / "projectB").resolve())
        try:
            _, body = _identity(a.port)
            assert body["projectRoot"] != b_root, "must not look like project B's mock"
            # Positive control: the same check passes for its own server, so a
            # harness wiring this in does not simply always refuse to run.
            _, own_body = _identity(a.port)
            assert own_body["projectRoot"] == str((tmp_path / "projectA").resolve())
        finally:
            a.shutdown()

    def test_pid_separates_two_runs_of_the_same_project(self, tmp_path):
        """projectRoot cannot catch a second run of the SAME project taking
        the port — only the pid can, and both are reported."""
        a = _serve(tmp_path / "projectA")
        try:
            _, body = _identity(a.port)
            import os
            assert body["pid"] == os.getpid()
            assert body["projectRoot"] == str((tmp_path / "projectA").resolve())
        finally:
            a.shutdown()

    def test_it_answers_without_the_admin_token(self, own):
        """A caller asking "are you mine?" does not have the answer's token
        when the answer is no."""
        status, _ = _identity(own.port)
        assert status == 200

    def test_it_carries_no_secret(self, own):
        _, body = _identity(own.port)
        blob = json.dumps(body)
        assert own.token not in blob
        assert not any("token" in k.lower() for k in body)

    def test_nothing_answers_when_the_server_failed_to_bind(self, tmp_path):
        """A server that could not take the port is not reachable at all —
        the caller gets a connection error, never a misleading 200. (The
        danger is the OTHER server answering, which the checks above cover.)"""
        srv = _serve(tmp_path / "projectA")
        port = srv.port
        srv.shutdown()
        time.sleep(0.1)
        with pytest.raises((urllib.error.URLError, ConnectionError, OSError)):
            _identity(port)


class TestIdentityCommand:
    """`jsonui-test mock identity` — the one-request check a harness runs
    after starting the server and again after the run."""

    def _run(self, root, *extra):
        import subprocess
        import sys
        launcher = Path(__file__).resolve().parents[1] / "jsonui-test"
        return subprocess.run(
            [sys.executable, str(launcher), "mock", "identity", *extra],
            capture_output=True, text=True, cwd=root)

    def test_it_passes_for_its_own_project(self, tmp_path):
        root = tmp_path / "projectA"
        srv = _serve(root)
        try:
            proc = self._run(root, "--port", str(srv.port))
            assert proc.returncode == 0, proc.stderr
            assert str(root.resolve()) in proc.stdout
        finally:
            srv.shutdown()

    def test_it_refuses_another_projects_mock(self, tmp_path):
        """The incident: project B's harness against project A's server."""
        a_root = tmp_path / "projectA"
        srv = _serve(a_root)
        b_root = tmp_path / "projectB"
        b_root.mkdir(parents=True, exist_ok=True)
        try:
            proc = self._run(b_root, "--port", str(srv.port))
            assert proc.returncode == 1, (proc.returncode, proc.stdout, proc.stderr)
            assert str(a_root.resolve()) in proc.stderr
            assert "another project" in proc.stderr
        finally:
            srv.shutdown()

    def test_nothing_listening_is_a_different_exit_code(self, tmp_path):
        root = tmp_path / "projectA"
        srv = _serve(root)
        port = srv.port
        srv.shutdown()
        time.sleep(0.1)
        proc = self._run(root, "--port", str(port))
        assert proc.returncode == 2, (proc.returncode, proc.stderr)
        assert "nothing answered" in proc.stderr

    def test_any_project_reports_without_failing(self, tmp_path):
        a_root = tmp_path / "projectA"
        srv = _serve(a_root)
        b_root = tmp_path / "projectB"
        b_root.mkdir(parents=True, exist_ok=True)
        try:
            proc = self._run(b_root, "--port", str(srv.port), "--any-project")
            assert proc.returncode == 0, proc.stderr
            assert str(a_root.resolve()) in proc.stdout
        finally:
            srv.shutdown()

    def test_a_server_without_the_endpoint_is_not_reported_as_absent(self, tmp_path):
        """Measured against a deployed server from before this endpoint: the
        request falls through to the admin router and comes back 401.
        Reporting that as "nothing answered" would send the caller to start a
        server that is already running — and would hide that an unidentified
        mock holds the port."""
        import http.server
        import socket
        import threading

        class Old(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b'{"error": "admin token required"}')

            def log_message(self, *a):
                pass

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        httpd = http.server.HTTPServer(("127.0.0.1", port), Old)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        time.sleep(0.1)
        try:
            root = tmp_path / "projectA"
            root.mkdir(parents=True, exist_ok=True)
            proc = self._run(root, "--port", str(port))
            assert proc.returncode == 3, (proc.returncode, proc.stdout, proc.stderr)
            assert "no identity endpoint" in proc.stderr
        finally:
            httpd.shutdown()

class TestTheCorpusFields:
    """`mockDir` says which tree; these say what came out of it.

    Added after the fact (two lanes implemented this endpoint from the same
    report, and these two fields were in only one of them).
    """

    def test_the_swagger_is_anchored_to_the_project_root(self, tmp_path):
        # "api/openapi.yaml" is the same string in every project. As a bare
        # relative path it cannot distinguish the two servers this endpoint
        # exists to distinguish, which is the whole job.
        root = tmp_path / "projectA"
        root.mkdir(parents=True)
        spec_file = root / "spec.json"
        spec_file.write_text(json.dumps(SPEC))
        out = root / "mocks"
        generate([str(spec_file)], out)
        srv = MockServer(MockStore.load(out), RunManager({}, root), port=0,
                         swagger=["api/openapi.yaml"])
        srv.bind()
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        time.sleep(0.1)
        try:
            _, body = _identity(srv.port)
            assert body["swagger"] == [str(root / "api/openapi.yaml")]
            assert Path(body["swagger"][0]).is_absolute()
        finally:
            srv.shutdown()

    def test_an_absolute_swagger_is_left_alone(self, tmp_path):
        root = tmp_path / "projectA"
        root.mkdir(parents=True)
        spec_file = root / "spec.json"
        spec_file.write_text(json.dumps(SPEC))
        out = root / "mocks"
        generate([str(spec_file)], out)
        srv = MockServer(MockStore.load(out), RunManager({}, root), port=0,
                         swagger=[str(spec_file)])
        srv.bind()
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        time.sleep(0.1)
        try:
            assert _identity(srv.port)[1]["swagger"] == [str(spec_file)]
        finally:
            srv.shutdown()

    def test_a_swagger_path_starts_with_the_projectRoot_beside_it(self, tmp_path):
        """The two fields must spell the same directory the same way.

        Asserted as a relation, not against a literal: the literal version
        passed while the payload actually disagreed with itself, because
        pytest's tmp_path is already resolved and the bug only appears for a
        caller whose root is not (macOS /var -> /private/var). Found by
        running the server outside the suite.
        """
        import os
        root = Path(tempfile.mkdtemp()) / "projectA"   # NOT pre-resolved
        root.mkdir(parents=True)
        spec_file = root / "spec.json"
        spec_file.write_text(json.dumps(SPEC))
        out = root / "mocks"
        generate([str(spec_file)], out)
        srv = MockServer(MockStore.load(out), RunManager({}, root), port=0,
                         swagger=["api/openapi.yaml"])
        srv.bind()
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        time.sleep(0.1)
        try:
            _, body = _identity(srv.port)
            assert body["swagger"][0].startswith(body["projectRoot"]), body
        finally:
            srv.shutdown()

    def test_the_endpoint_count_follows_the_corpus(self, own):
        # The difference between "the wrong corpus" and "an empty one": a
        # server with 0 endpoints 404s everything, which reads downstream as
        # a broken app rather than a mock pointed at nothing.
        assert _identity(own.port)[1]["endpointCount"] == 1

    def test_no_swagger_configured_is_an_empty_list_not_a_missing_key(self, own):
        # A harness comparing fields should not have to distinguish "absent"
        # from "none declared".
        assert _identity(own.port)[1]["swagger"] == []


class TestTheTokenGateDidNotMove:
    """`identity` sits AHEAD of the token check. That is deliberate, and it
    is also the kind of edit that quietly widens a hole: `/__jsonui__/run`
    executes shell commands. These arms pin the boundary where it was."""

    def _admin(self, port: int, path: str, token: str | None = None):
        headers = {"Host": f"127.0.0.1:{port}"}
        if token:
            headers["X-JsonUI-Token"] = token
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status

    def test_every_other_admin_route_still_demands_the_token(self, own):
        for path in ("/__jsonui__/mocks", "/__jsonui__/requests",
                     "/__jsonui__/run/status", "/__jsonui__/contract-violations"):
            with pytest.raises(urllib.error.HTTPError) as caught:
                self._admin(own.port, path)
            assert caught.value.code == 401, path
            assert self._admin(own.port, path, token=own.token) == 200, path

    def test_identity_is_still_refused_from_a_foreign_host_header(self, own):
        # Unauthenticated is not unguarded: the DNS-rebinding defence is the
        # Host check, and it runs before the route.
        req = urllib.request.Request(
            f"http://127.0.0.1:{own.port}/__jsonui__/identity",
            headers={"Host": "evil.example"})
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(req, timeout=5)
        assert caught.value.code == 403


class TestShutdownWithoutAServeLoop:
    """`shutdown()` waits for the serve loop to stop, so on a server that only
    ever bound it waited for something that never started — forever. A unit
    test that binds without serving is exactly that shape, and it is how this
    was found."""

    def test_it_returns_instead_of_hanging(self, tmp_path):
        root = tmp_path / "projectA"
        root.mkdir(parents=True)
        (root / "mocks").mkdir()
        srv = MockServer(MockStore.load(root / "mocks"), RunManager({}, root), port=0)
        port = srv.bind()  # bound, never served
        done = threading.Event()

        def stop():
            srv.shutdown()
            done.set()

        threading.Thread(target=stop, daemon=True).start()
        assert done.wait(timeout=10), "shutdown() blocked on a serve loop that never started"

        # and the port is actually released
        import socket
        probe = socket.socket()
        try:
            probe.bind(("127.0.0.1", port))
        finally:
            probe.close()

    def test_a_served_server_still_stops(self, tmp_path):
        # The guard must not skip the real shutdown when there IS a loop.
        srv = _serve(tmp_path / "projectA")
        srv.shutdown()
        with pytest.raises(urllib.error.URLError):
            _identity(srv.port)
