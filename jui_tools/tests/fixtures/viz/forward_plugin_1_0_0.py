"""Forward one Claude Code hook payload to the local jui viz server.

Runs for every hook event, so it must be fast and must never fail loudly:
no output, exit 0 whatever happens. Imports are deferred until the server
is known to be running, and the request is written on a raw socket
(http.client and urllib.request cost tens of milliseconds to import, and
a socket ignores HTTP(S)_PROXY, which must never route 127.0.0.1).
"""
import os
import sys

MAX_BODY = 2_000_000


def decide(body: bytes, info: dict) -> None:
    """--decide: the synchronous PermissionRequest hook (P6).

    Posts the request to /hook/decide and prints the server's answer — a
    hookSpecificOutput JSON — when the browser gave one in time. No answer,
    no server, any error: print nothing, so the usual terminal dialog stays.
    Measured 2026-10-18 (Claude Code 2.1.302): the dialog shows at once while
    this waits, an answer in the terminal goes through without waiting for it,
    and an answer printed here closes the dialog.
    """
    import json
    import socket

    port = int(info["port"])
    wait = float(info.get("decideWaitSec", 30))
    head = (
        f"POST /hook/decide HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
        f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n"
        f"X-Jui-Viz-Token: {info['token']}\r\nConnection: close\r\n\r\n"
    )
    with socket.create_connection(("127.0.0.1", port), timeout=1.0) as s:
        s.sendall(head.encode("ascii") + body)
        s.settimeout(wait + 5)
        raw = b""
        while len(raw) < 1_000_000:
            chunk = s.recv(65536)
            if not chunk:
                break
            raw += chunk
    status, _, rest = raw.partition(b"\r\n")
    if b" 200 " not in status + b" ":
        return
    answer = rest.partition(b"\r\n\r\n")[2]
    data = json.loads(answer.decode("utf-8"))
    if isinstance(data, dict) and isinstance(data.get("hookSpecificOutput"), dict):
        sys.stdout.write(json.dumps(data))
        sys.stdout.flush()


def main() -> int:
    try:
        # Drain stdin first so Claude Code never writes into a closed pipe.
        body = sys.stdin.buffer.read()
        info_path = os.path.join(os.path.expanduser("~"), ".jsonui-cli", "viz", "server.json")
        if len(body) > MAX_BODY or not os.path.exists(info_path):
            return 0  # too large, or the server is not running
        import json
        import socket
        import time

        with open(info_path, encoding="utf-8") as f:
            info = json.load(f)
        if "--decide" in sys.argv[1:]:
            decide(body, info)
            return 0
        port = int(info["port"])
        head = (
            f"POST /hook HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
            f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n"
            f"X-Jui-Viz-Token: {info['token']}\r\n"
            f"X-Jui-Viz-Sent-At: {int(time.time() * 1000)}\r\nConnection: close\r\n\r\n"
        )
        with socket.create_connection(("127.0.0.1", port), timeout=1.0) as s:
            s.sendall(head.encode("ascii") + body)
            s.recv(64)  # wait for the status line so the server has the body
    except Exception:  # noqa: BLE001 - a hook must never break the session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
