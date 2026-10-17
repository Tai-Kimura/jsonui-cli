"""Is this project's `jsonui-test mock serve` running? Design: P7 §A3.

The port is the one `mock serve` binds by default: jui.config.json's
mock.server.port, else 8790 (test_tools/jsonui_test_cli/cli.py,
cmd_mock_serve). The answer comes from GET /__jsonui__/identity, which needs
no token and names the server's projectRoot — so a mock of ANOTHER project
on the same port is reported as that, not as ours. A raw socket, so no
proxy variable applies.
"""
from __future__ import annotations

import json
import os
import socket
from pathlib import Path

DEFAULT_PORT = 8790
TIMEOUT_SEC = 1.0
INTERVAL_SEC = 5.0


def mock_port(config: dict) -> int:
    mock = config.get("mock") if isinstance(config.get("mock"), dict) else {}
    server = mock.get("server") if isinstance(mock.get("server"), dict) else {}
    port = server.get("port")
    ok = isinstance(port, int) and not isinstance(port, bool) and 0 < port < 65536
    return port if ok else DEFAULT_PORT


def identity(port: int, timeout: float = TIMEOUT_SEC) -> dict | None:
    try:
        sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    except OSError:
        return None
    try:
        sock.settimeout(timeout)
        sock.sendall(f"GET /__jsonui__/identity HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n".encode("ascii"))
        raw = b""
        while len(raw) < 65536:
            chunk = sock.recv(4096)
            if not chunk:
                break
            raw += chunk
    except OSError:
        return None
    finally:
        sock.close()
    head, _, body = raw.partition(b"\r\n\r\n")
    if not head.startswith(b"HTTP/1.") or b" 200 " not in head.split(b"\r\n", 1)[0] + b" ":
        return None
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def status(root: Path, config: dict) -> dict:
    """{running, port, pid?, other?}: other = a mock of another project answers there."""
    port = mock_port(config)
    ident = identity(port)
    if ident is None:
        return {"running": False, "port": port}
    theirs = ident.get("projectRoot")
    try:
        ours = os.path.realpath(root) == os.path.realpath(str(theirs))
    except (TypeError, ValueError):
        ours = False
    if not ours:
        return {"running": False, "port": port, "other": True}
    out = {"running": True, "port": port}
    if isinstance(ident.get("pid"), int):
        out["pid"] = ident["pid"]
    return out
