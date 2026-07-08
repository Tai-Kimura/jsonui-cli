"""Local API mock server + control-panel host.

Bound to 127.0.0.1 only. Serves mock responses under the swagger paths and an
admin API under /__jsonui__/. Because it can run shell commands (/__jsonui__/run),
it defends against DNS-rebinding / CSRF:
  - Host header must be 127.0.0.1:PORT or localhost:PORT.
  - Every /__jsonui__/ mutation requires the per-boot admin token.
  - CORS is wide-open for mock API paths only; admin is same-origin.
"""

from __future__ import annotations

import json
import re
import secrets
import subprocess
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ADMIN_PREFIX = "/__jsonui__"
_MAX_RECORDED = 200
_PARAM_RE = re.compile(r"\{[^/}]+\}")
_SAFE_OP_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass
class MockEndpoint:
    operation_id: str
    method: str
    path: str
    active_scenario: str
    scenarios: dict
    file_path: Path
    regex: "re.Pattern"
    is_static: bool


@dataclass
class MockStore:
    """In-memory mock state, loaded from <mockDir>/**/*.mock.json."""
    mock_dir: Path
    endpoints: list[MockEndpoint] = field(default_factory=list)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    @classmethod
    def load(cls, mock_dir: str | Path) -> "MockStore":
        store = cls(mock_dir=Path(mock_dir))
        store.reload()
        return store

    def reload(self):
        endpoints: list[MockEndpoint] = []
        for f in sorted(Path(self.mock_dir).rglob("*.mock.json")):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError):
                continue
            src = data.get("source", {})
            method = (src.get("method") or "GET").upper()
            path = src.get("path") or "/"
            op_id = src.get("operationId") or f.stem.replace(".mock", "")
            scenarios = data.get("scenarios", {})
            active = data.get("activeScenario", "default")
            endpoints.append(MockEndpoint(
                operation_id=op_id,
                method=method,
                path=path,
                active_scenario=active if active in scenarios else next(iter(scenarios), "default"),
                scenarios=scenarios,
                file_path=f,
                regex=_path_to_regex(path),
                is_static="{" not in path,
            ))
        # Static paths first so they win over parameterized ones.
        endpoints.sort(key=lambda e: (not e.is_static, e.path))
        with self._lock:
            self.endpoints = endpoints

    def match(self, method: str, path: str) -> MockEndpoint | None:
        with self._lock:
            for ep in self.endpoints:
                if ep.method == method.upper() and ep.regex.match(path):
                    return ep
        return None

    def list_summary(self) -> list[dict]:
        with self._lock:
            return [{
                "operationId": ep.operation_id,
                "method": ep.method,
                "path": ep.path,
                "activeScenario": ep.active_scenario,
                "scenarios": list(ep.scenarios.keys()),
            } for ep in self.endpoints]

    def by_id(self, op_id: str) -> MockEndpoint | None:
        with self._lock:
            for ep in self.endpoints:
                if ep.operation_id == op_id:
                    return ep
        return None

    def definition(self, op_id: str) -> dict | None:
        """Full definition (scenario bodies included) for the editor."""
        ep = self.by_id(op_id)
        if ep is None:
            return None
        with self._lock:
            return {
                "operationId": ep.operation_id,
                "method": ep.method,
                "path": ep.path,
                "activeScenario": ep.active_scenario,
                "scenarios": ep.scenarios,
            }

    def activate(self, op_id: str, scenario: str) -> bool:
        with self._lock:
            ep = next((e for e in self.endpoints if e.operation_id == op_id), None)
            if ep is None or scenario not in ep.scenarios:
                return False
            ep.active_scenario = scenario
            return True

    def scenario_set(self, mapping: dict) -> dict:
        applied, unknown = {}, []
        with self._lock:
            for op_id, scenario in mapping.items():
                ep = next((e for e in self.endpoints if e.operation_id == op_id), None)
                if ep is None or scenario not in ep.scenarios:
                    unknown.append(op_id)
                else:
                    ep.active_scenario = scenario
                    applied[op_id] = scenario
        return {"applied": applied, "unknown": unknown}

    def reset(self):
        with self._lock:
            for ep in self.endpoints:
                if "default" in ep.scenarios:
                    ep.active_scenario = "default"

    def write_scenario(self, op_id: str, scenario: str, payload: dict) -> bool:
        """Persist an edited scenario back to its file."""
        with self._lock:
            ep = next((e for e in self.endpoints if e.operation_id == op_id), None)
            if ep is None:
                return False
            ep.scenarios[scenario] = payload
            try:
                with open(ep.file_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                data.setdefault("scenarios", {})[scenario] = payload
                with open(ep.file_path, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False, indent=2)
                    fh.write("\n")
            except (OSError, json.JSONDecodeError):
                return False
            return True


def _path_to_regex(path: str) -> "re.Pattern":
    escaped = re.escape(path)
    # re.escape turns {id} into \{id\}; swap each param for a path segment match.
    pattern = re.sub(r"\\\{[^/}]+\\\}", r"[^/]+", escaped)
    return re.compile("^" + pattern + "/?$")


class RequestLog:
    def __init__(self, cap: int = _MAX_RECORDED):
        self._items: list[dict] = []
        self._cap = cap
        self._lock = threading.Lock()

    def record(self, entry: dict):
        with self._lock:
            self._items.append(entry)
            if len(self._items) > self._cap:
                self._items.pop(0)

    def all(self) -> list[dict]:
        with self._lock:
            return list(self._items)


class RunManager:
    """Runs a single configured test target at a time, streaming its output."""

    def __init__(self, run_targets: dict, project_root: Path):
        self._targets = run_targets or {}
        self._root = project_root
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._lines: list[str] = []
        self._returncode: int | None = None
        self._running = False
        self._last_target: str | None = None

    @property
    def targets(self) -> list[str]:
        return list(self._targets.keys())

    def read_results(self) -> dict | None:
        """Read the results JSON (results.schema.json) from the last run target."""
        with self._lock:
            target = self._last_target
        if not target:
            return None
        spec = self._targets.get(target, {})
        rel = spec.get("resultsPath", "jsonui-results.json")
        cwd = (self._root / spec.get("cwd", ".")).resolve()
        results_file = (cwd / rel).resolve()
        if not str(results_file).startswith(str(self._root.resolve())):
            return None
        try:
            with open(results_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    def status(self) -> dict:
        with self._lock:
            return {"running": self._running, "returncode": self._returncode,
                    "lineCount": len(self._lines)}

    def lines_since(self, index: int) -> tuple[list[str], int]:
        with self._lock:
            return self._lines[index:], len(self._lines)

    def start(self, target: str) -> tuple[bool, str]:
        if target not in self._targets:
            return False, f"unknown target '{target}' (allowed: {self.targets})"
        with self._lock:
            if self._running:
                return False, "a run is already in progress"
            self._running = True
            self._lines = []
            self._returncode = None
            self._last_target = target
        spec = self._targets[target]
        cwd = (self._root / spec.get("cwd", ".")).resolve()
        if not str(cwd).startswith(str(self._root.resolve())):
            with self._lock:
                self._running = False
            return False, "run cwd escapes project root"
        threading.Thread(target=self._run, args=(spec["command"], cwd), daemon=True).start()
        return True, "started"

    def _run(self, command: str, cwd: Path):
        try:
            proc = subprocess.Popen(
                command, shell=True, cwd=str(cwd),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            with self._lock:
                self._proc = proc
            for line in proc.stdout:
                with self._lock:
                    self._lines.append(line.rstrip("\n"))
            proc.wait()
            rc = proc.returncode
        except Exception as e:  # noqa: BLE001 - surface any launch failure to the panel
            with self._lock:
                self._lines.append(f"[run error] {e}")
            rc = 1
        with self._lock:
            self._running = False
            self._returncode = rc
            self._proc = None


def _panel_html(token: str) -> bytes:
    """Serve the packaged control panel, injecting the admin token.

    Phase 1 ships a placeholder; Phase 2 replaces static/panel.html.
    """
    try:
        from importlib.resources import files
        raw = (files("jsonui_test_cli") / "static" / "panel.html").read_text("utf-8")
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        raw = ("<!doctype html><title>JsonUI Mock</title>"
               "<h1>JsonUI Mock Server</h1>"
               "<p>Control panel not yet installed (Phase 2).</p>"
               "<p>Admin token: <code>__JSONUI_TOKEN__</code></p>")
    return raw.replace("__JSONUI_TOKEN__", token).encode("utf-8")


class MockServer:
    def __init__(self, store: MockStore, run_manager: RunManager, port: int = 8790):
        self.store = store
        self.run = run_manager
        self.port = port
        self.token = secrets.token_urlsafe(24)
        self.requests = RequestLog()
        self._httpd: ThreadingHTTPServer | None = None

    def bind(self):
        """Bind the listening socket now so the real port is known (port 0 = ephemeral)."""
        handler = _make_handler(self)
        self._httpd = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        self.port = self._httpd.server_address[1]
        return self.port

    def serve_forever(self):
        if self._httpd is None:
            self.bind()
        self._httpd.serve_forever()

    def shutdown(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None


def _host_ok(host: str, port: int) -> bool:
    if not host:
        return False
    allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
    # A bare host with the default port omitted is also acceptable.
    return host in allowed or host in {"127.0.0.1", "localhost"}


def _make_handler(server: "MockServer"):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass  # keep stdout clean; panel shows requests

        # -- helpers ----------------------------------------------------
        def _send(self, status, body=b"", content_type="application/json", cors=False):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            elif isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            if cors:
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,PATCH,OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "*")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _read_body(self):
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return None
            raw = self.rfile.read(length)
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                return raw.decode("utf-8", "replace")

        def _admin_authorized(self) -> bool:
            if self.headers.get("X-JsonUI-Token") == server.token:
                return True
            # EventSource (SSE) cannot set headers, so accept ?token= as a fallback.
            token_q = parse_qs(urlparse(self.path).query).get("token", [None])[0]
            return token_q == server.token

        # -- verbs ------------------------------------------------------
        def do_OPTIONS(self):
            self._send(204, cors=True)

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_PUT(self):
            self._dispatch("PUT")

        def do_DELETE(self):
            self._dispatch("DELETE")

        def do_PATCH(self):
            self._dispatch("PATCH")

        def _dispatch(self, method):
            parsed = urlparse(self.path)
            path = parsed.path
            if not _host_ok(self.headers.get("Host", ""), server.port):
                self._send(403, {"error": "bad host"})
                return
            if path == ADMIN_PREFIX + "/panel":
                self._send(200, _panel_html(server.token), content_type="text/html")
                return
            if path.startswith(ADMIN_PREFIX):
                self._admin(method, path, parsed)
                return
            self._mock(method, path, parsed)

        # -- admin API --------------------------------------------------
        def _admin(self, method, path, parsed):
            if not self._admin_authorized():
                self._send(401, {"error": "admin token required"})
                return
            sub = path[len(ADMIN_PREFIX):]

            if sub == "/mocks" and method == "GET":
                self._send(200, server.store.list_summary())
            elif sub == "/scenario-set" and method == "POST":
                body = self._read_body() or {}
                self._send(200, server.store.scenario_set(body.get("mocks", body)))
            elif sub == "/reset" and method == "POST":
                server.store.reset()
                self._send(200, {"ok": True})
            elif sub == "/reload" and method == "POST":
                server.store.reload()
                self._send(200, {"ok": True})
            elif sub == "/requests" and method == "GET":
                self._send(200, server.requests.all())
            elif sub == "/run/status" and method == "GET":
                self._send(200, {**server.run.status(), "targets": server.run.targets})
            elif sub == "/run/results" and method == "GET":
                results = server.run.read_results()
                self._send(200 if results is not None else 404, results or {"error": "no results"})
            elif sub == "/run/stream" and method == "GET":
                self._sse_run(parsed)
            elif sub == "/run" and method == "POST":
                body = self._read_body() or {}
                ok, msg = server.run.start(body.get("target", ""))
                self._send(200 if ok else 409, {"ok": ok, "message": msg})
            elif re.match(r"^/mocks/[^/]+/activate$", sub) and method == "POST":
                op_id = sub.split("/")[2]
                body = self._read_body() or {}
                ok = server.store.activate(op_id, body.get("scenario", ""))
                self._send(200 if ok else 404, {"ok": ok})
            elif re.match(r"^/mocks/[^/]+$", sub) and method == "GET":
                op_id = sub.split("/")[2]
                definition = server.store.definition(op_id)
                self._send(200 if definition else 404, definition or {"error": "not found"})
            elif re.match(r"^/mocks/[^/]+$", sub) and method == "PUT":
                op_id = sub.split("/")[2]
                if not _SAFE_OP_ID.match(op_id):
                    self._send(400, {"error": "invalid operationId"})
                    return
                body = self._read_body() or {}
                ok = server.store.write_scenario(
                    op_id, body.get("scenario", ""), body.get("payload", {}))
                self._send(200 if ok else 404, {"ok": ok})
            else:
                self._send(404, {"error": f"unknown admin route {method} {sub}"})

        def _sse_run(self, parsed):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            index = 0
            try:
                while True:
                    lines, index = server.run.lines_since(index)
                    for line in lines:
                        self.wfile.write(f"data: {line}\n\n".encode("utf-8"))
                        self.wfile.flush()
                    status = server.run.status()
                    if not status["running"] and index >= status["lineCount"]:
                        self.wfile.write(
                            f"event: done\ndata: {status['returncode']}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        break
                    time.sleep(0.2)
            except (BrokenPipeError, ConnectionResetError):
                pass

        # -- mock responses ---------------------------------------------
        def _mock(self, method, path, parsed):
            body = self._read_body()
            ep = server.store.match(method, path)
            server.requests.record({
                "method": method,
                "path": path,
                "query": parse_qs(parsed.query),
                "body": _mask(body),
                "matched": ep.operation_id if ep else None,
            })
            if ep is None:
                self._send(404, {"error": "no mock for this route", "path": path}, cors=True)
                return
            scenario = ep.scenarios.get(ep.active_scenario, {})
            delay = scenario.get("delayMs")
            if delay:
                time.sleep(min(delay, 30000) / 1000.0)
            status = scenario.get("status", 200)
            ctype = scenario.get("contentType", "application/json")
            payload = scenario.get("body")
            if payload is None:
                self._send(status, b"", content_type=ctype, cors=True)
            else:
                self._send(status, payload, content_type=ctype, cors=True)

    return Handler


def _mask(body):
    """Redact obvious secrets from recorded request bodies."""
    if isinstance(body, dict):
        return {k: ("***" if k.lower() in {"password", "token", "authorization", "secret"}
                    else _mask(v)) for k, v in body.items()}
    if isinstance(body, list):
        return [_mask(v) for v in body]
    return body
