"""``jui hotload`` — centralized hotload server.

Subcommands:
    jui hotload listen   Start the HTTP + WebSocket server in foreground
    jui hotload status   Print whether a server is running (reads PID file)
    jui hotload stop     Stop a running server via its PID file
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
from pathlib import Path

from ..core.config_manager import ConfigManager
from ..hotloader.config_loader import (
    HotloadConfig,
    load_config,
    write_default_config,
)


PID_FILE = Path.home() / ".jsonui-cli" / "hotload.pid"


def register_hotload_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "hotload",
        help="Start the centralized hotload server (iOS + Android)",
    )
    hotload_sub = parser.add_subparsers(dest="hotload_cmd")

    listen = hotload_sub.add_parser(
        "listen",
        help="Start the hotload server in the foreground",
    )
    listen.add_argument("--host", help="Override server.host from config")
    listen.add_argument("--port", type=int, help="Override server.port from config")
    listen.add_argument(
        "--ws-path",
        dest="ws_path",
        help="Override server.wsPath from config (default /ws)",
    )

    hotload_sub.add_parser("status", help="Print whether a hotload server is running")
    hotload_sub.add_parser("stop", help="Stop the running hotload server")


def cmd_hotload(args: argparse.Namespace) -> int:
    sub = getattr(args, "hotload_cmd", None)
    if sub == "listen":
        return _cmd_listen(args)
    if sub == "status":
        return _cmd_status(args)
    if sub == "stop":
        return _cmd_stop(args)
    print("usage: jui hotload {listen,status,stop}", file=sys.stderr)
    return 1


def _cmd_listen(args: argparse.Namespace) -> int:
    project_root = _project_root()
    if project_root is None:
        print("error: jui.config.json not found (run inside a JsonUI project)", file=sys.stderr)
        return 1

    write_default_config(project_root)
    config = load_config(project_root)
    _apply_overrides(config, args)

    existing_pid = _read_pid()
    if existing_pid and _pid_alive(existing_pid):
        print(
            f"error: hotload server already running (pid {existing_pid}). "
            f"Run 'jui hotload stop' first.",
            file=sys.stderr,
        )
        return 1

    _write_pid(os.getpid())
    try:
        from ..hotloader.server import run_server
        run_server(config)
    finally:
        _clear_pid()
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    pid = _read_pid()
    if pid is None:
        print("hotload: not running")
        return 0
    if _pid_alive(pid):
        print(f"hotload: running (pid {pid})")
        return 0
    print(f"hotload: stale pid file ({pid}) — process not alive. Removing.")
    _clear_pid()
    return 0


def _cmd_stop(args: argparse.Namespace) -> int:
    pid = _read_pid()
    if pid is None:
        print("hotload: no pid file, nothing to stop")
        return 0
    if not _pid_alive(pid):
        print(f"hotload: pid {pid} not alive, clearing pid file")
        _clear_pid()
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        print(f"error: failed to signal pid {pid}: {exc}", file=sys.stderr)
        return 1
    _clear_pid()
    print(f"hotload: sent SIGTERM to pid {pid}")
    return 0


def _apply_overrides(config: HotloadConfig, args: argparse.Namespace) -> None:
    if getattr(args, "host", None):
        config.host = args.host
    if getattr(args, "port", None):
        config.port = int(args.port)
    if getattr(args, "ws_path", None):
        config.ws_path = args.ws_path


def _project_root() -> Path | None:
    try:
        mgr = ConfigManager()
    except Exception:  # noqa: BLE001
        return None
    if not mgr.exists():
        return None
    return mgr.project_root


def _read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except (OSError, ValueError):
        return None


def _write_pid(pid: int) -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(pid))


def _clear_pid() -> None:
    try:
        PID_FILE.unlink()
    except FileNotFoundError:
        pass


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
