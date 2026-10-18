"""A Claude Code statusLine command that hands the plan's usage limits to jui viz (requester, 10-18).

Claude Code runs it with the status JSON on stdin; the only place the 5-hour and weekly limits reach
anything outside Claude Code is that JSON's ``rate_limits``. This posts them to the running viz server
(the same raw-socket POST as forward.py: no proxy, short timeout, silent on any failure) and prints the
status line:
  * installed over an existing statusLine (``--wrap <base64 of it>``): runs that command with the same
    stdin and prints exactly what it printed, so the user's line stays theirs;
  * on its own: one short line, e.g. ``5h 42% · 週 18%``.
Installed only by `jui viz statusline install`, which also takes it out again.

⚠️ Only a terminal claude runs a statusLine; the VS Code extension does not (10-18).
"""
import os
import sys

MAX_BODY = 2_000_000
TIMEOUT = 0.5


def _post(body: bytes) -> None:
    import json
    import socket

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from forward import viz_home   # the one copy of where the server's files are

    info_path = os.path.join(viz_home(), "server.json")
    if not os.path.exists(info_path):
        return
    with open(info_path, encoding="utf-8") as f:
        info = json.load(f)
    port = int(info["port"])
    head = (
        f"POST /usage HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\nX-Jui-Viz-Token: {info['token']}\r\nConnection: close\r\n\r\n"
    )
    with socket.create_connection(("127.0.0.1", port), timeout=TIMEOUT) as s:
        s.sendall(head.encode("ascii") + body)
        s.recv(64)


def own_line(status: dict) -> str:
    """5h 42% · 週 18% (上限到達 when a window is at 100); the model's name when there are no limits."""
    limits = status.get("rate_limits") if isinstance(status.get("rate_limits"), dict) else {}
    parts = []
    for key, label in (("five_hour", "5h"), ("seven_day", "週")):
        w = limits.get(key)
        if isinstance(w, dict) and isinstance(w.get("used_percentage"), (int, float)):
            pct = float(w["used_percentage"])
            parts.append(f"{label} 上限到達" if pct >= 100 else f"{label} {pct:.0f}%")
    if parts:
        return " · ".join(parts)
    model = status.get("model") if isinstance(status.get("model"), dict) else {}
    return str(model.get("display_name") or "")


def wrapped(arg: str, body: bytes) -> bytes:
    """What the statusLine this one wraps prints for the same input."""
    import base64
    import json
    import subprocess

    original = json.loads(base64.b64decode(arg.encode("ascii")).decode("utf-8"))
    command = original.get("command") if isinstance(original, dict) else None
    if not isinstance(command, str) or not command:
        return b""
    done = subprocess.run(command, shell=True, input=body, capture_output=True, timeout=30)
    return done.stdout


def main() -> int:
    body = sys.stdin.buffer.read()
    out = b""
    argv = sys.argv[1:]
    try:
        if "--wrap" in argv and argv.index("--wrap") + 1 < len(argv):
            out = wrapped(argv[argv.index("--wrap") + 1], body)
    except Exception:  # noqa: BLE001 - the user's own line failing must not take this one down
        out = b""
    status = {}
    try:
        import json

        status = json.loads(body.decode("utf-8")) if body.strip() else {}
        if isinstance(status, dict) and isinstance(status.get("rate_limits"), dict) and len(body) <= MAX_BODY:
            _post(json.dumps({"rate_limits": status["rate_limits"]}).encode("utf-8"))
    except Exception:  # noqa: BLE001 - a status line must never fail loudly
        pass
    if "--wrap" not in argv:
        out = own_line(status if isinstance(status, dict) else {}).encode("utf-8")
    sys.stdout.buffer.write(out)
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
