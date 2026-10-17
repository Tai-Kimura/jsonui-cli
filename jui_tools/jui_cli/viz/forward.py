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
