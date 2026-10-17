"""The jui-viz MCP channel: relays Claude Code's permission prompts to the local
jui viz server, and the browser's answers back. Design: 08 §2.

Claude Code starts this per session (``claude mcp add --scope user jui-viz --
<python> -I <this file>``; the session runs with
``--dangerously-load-development-channels server:jui-viz``). Standard library
only, and it must not import jui_cli.

Rules:
  * stdout carries JSON-RPC and nothing else, one message per line, under a
    lock. Logs go to stderr.
  * It never sends ``notifications/claude/channel`` (that would put text in
    Claude's context): only permission verdicts, and only for request_ids it
    received and that are still open (forgotten after 10 minutes).
  * The server is reached over http.client on 127.0.0.1 (no proxy variables
    apply); when it is not running, retry quietly every 5 s.
"""
from __future__ import annotations

import http.client
import json
import os
import queue
import stat
import sys
import threading
import time

VERSION = "1"
FORGET_SEC = 600
RETRY_SEC = 5
POLL_TIMEOUT_SEC = 35  # the server holds a poll up to 25 s
INSTRUCTIONS = (
    "This server only relays permission prompts to the local jui viz page and "
    "returns the answers given there. It sends no messages."
)

_out_lock = threading.Lock()


def log(message: str) -> None:
    print(f"jui-viz channel: {message}", file=sys.stderr, flush=True)


def send(message: dict) -> None:
    line = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
    with _out_lock:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def _home() -> str:
    return os.path.expanduser("~")


def read_server() -> dict | None:
    try:
        with open(os.path.join(_home(), ".jsonui-cli", "viz", "server.json"), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) and isinstance(data.get("port"), int) else None
    except (OSError, ValueError):
        return None


def session_id_of(pid: int) -> str | None:
    """sessionId from ~/.claude/sessions/<pid>.json — never a .key, never through a symlink."""
    path = os.path.join(_home(), ".claude", "sessions", f"{int(pid)}.json")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > 256_000:
            return None
        data = json.loads(os.read(fd, 256_001).decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    finally:
        os.close(fd)
    sid = data.get("sessionId") if isinstance(data, dict) else None
    return sid if isinstance(sid, str) else None


class Bridge:
    """The link to the viz server: hello, forward requests, long-poll verdicts."""

    def __init__(self) -> None:
        self.channel_id: str | None = None
        self.server: dict | None = None
        self.open: dict[str, float] = {}
        self.outbox: "queue.Queue[dict]" = queue.Queue()
        self.lock = threading.Lock()
        self.stopping = threading.Event()

    def _call(self, method: str, path: str, body: dict | None = None, timeout: float = 5):
        server = self.server
        if server is None:
            raise OSError("no server")
        conn = http.client.HTTPConnection("127.0.0.1", server["port"], timeout=timeout)
        try:
            headers = {"X-Jui-Viz-Token": str(server.get("token", "")), "Host": f"127.0.0.1:{server['port']}"}
            payload = None
            if body is not None:
                payload = json.dumps(body).encode("utf-8")
                headers["Content-Type"] = "application/json"
            conn.request(method, path, body=payload, headers=headers)
            res = conn.getresponse()
            data = res.read()
            return res.status, data
        finally:
            conn.close()

    def _connect(self) -> bool:
        self.server = read_server()
        if self.server is None:
            return False
        ppid = os.getppid()
        body = {"ppid": ppid, "cwd": os.getcwd(), "sessionId": session_id_of(ppid)}
        try:
            status, data = self._call("POST", "/channel/hello", body)
        except OSError:
            return False
        if status != 200:
            return False
        try:
            self.channel_id = json.loads(data.decode("utf-8"))["channelId"]
        except (ValueError, KeyError, UnicodeDecodeError):
            return False
        log("connected")
        return True

    def remember(self, request_id: str) -> None:
        with self.lock:
            now = time.time()
            self.open[request_id] = now
            for rid, at in list(self.open.items()):
                if now - at > FORGET_SEC:
                    del self.open[rid]

    def take(self, request_id: str) -> bool:
        with self.lock:
            return self.open.pop(request_id, None) is not None

    def run(self) -> None:
        while not self.stopping.is_set():
            if self.channel_id is None and not self._connect():
                self.stopping.wait(RETRY_SEC)
                continue
            try:
                self._flush_outbox()
                status, data = self._call("GET", f"/channel/poll?channelId={self.channel_id}", timeout=POLL_TIMEOUT_SEC)
            except OSError:
                self.channel_id = None
                self.stopping.wait(RETRY_SEC)
                continue
            if status in (401, 404):
                self.channel_id = None  # the server restarted: new token, no such channel
                continue
            if status != 200:
                self.stopping.wait(RETRY_SEC)
                continue
            try:
                verdicts = json.loads(data.decode("utf-8")).get("verdicts") or []
            except (ValueError, UnicodeDecodeError, AttributeError):
                continue
            for verdict in verdicts:
                rid = verdict.get("request_id") if isinstance(verdict, dict) else None
                behavior = verdict.get("behavior") if isinstance(verdict, dict) else None
                if isinstance(rid, str) and behavior in ("allow", "deny") and self.take(rid):
                    send({"jsonrpc": "2.0", "method": "notifications/claude/channel/permission",
                          "params": {"request_id": rid, "behavior": behavior}})

    def _flush_outbox(self) -> None:
        while True:
            try:
                item = self.outbox.get_nowait()
            except queue.Empty:
                return
            try:
                self._call("POST", "/channel/request", dict(item, channelId=self.channel_id))
            except OSError:
                self.outbox.put(item)
                raise

    def forward(self, params: dict) -> None:
        rid = params.get("request_id")
        if not isinstance(rid, str) or not rid:
            return
        self.remember(rid)
        item = {k: params.get(k) for k in ("request_id", "tool_name", "description", "input_preview")}
        if self.channel_id is not None:
            try:
                self._call("POST", "/channel/request", dict(item, channelId=self.channel_id), timeout=2)
                return
            except OSError:
                pass
        self.outbox.put(item)


def handle(message: dict, bridge: Bridge, started: list) -> None:
    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": msg_id, "result": {
            "protocolVersion": params.get("protocolVersion", "2025-06-18"),
            "capabilities": {"experimental": {"claude/channel": {}, "claude/channel/permission": {}}},
            "serverInfo": {"name": "jui-viz", "version": VERSION},
            "instructions": INSTRUCTIONS,
        }})
    elif method == "notifications/initialized":
        if not started:
            threading.Thread(target=bridge.run, daemon=True).start()
            started.append(True)
    elif method == "notifications/claude/channel/permission_request":
        bridge.forward(params)
    elif method == "ping":
        send({"jsonrpc": "2.0", "id": msg_id, "result": {}})
    elif method in ("tools/list", "resources/list", "prompts/list", "resources/templates/list"):
        key = method.split("/")[0] if method != "resources/templates/list" else "resourceTemplates"
        send({"jsonrpc": "2.0", "id": msg_id, "result": {key: []}})
    elif msg_id is not None:
        send({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"method not found: {method}"}})
    # other notifications: ignored


def main() -> int:
    bridge = Bridge()
    started: list = []
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        if isinstance(message, dict):
            try:
                handle(message, bridge, started)
            except Exception as exc:  # noqa: BLE001 - one bad message must not end the session's channel
                log(f"error handling {message.get('method')}: {type(exc).__name__}")
    bridge.stopping.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
