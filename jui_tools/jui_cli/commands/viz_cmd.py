"""``jui viz`` — a local browser view of the Claude Code sessions on this machine.

Subcommands:
    jui viz serve    Start the server in the foreground (127.0.0.1 only)
    jui viz status   Whether a server is running, and its URL
    jui viz stop     SIGTERM the pid this tool wrote to its own pid file
    jui viz open     Open the running server's page in the browser
    jui viz doctor   Check the environment
    jui viz hooks    (P2) install / uninstall / status of the Claude Code hooks
    jui viz relay    (P5) the permission relay

Exit codes: 0 success, 1 usage error or a missing precondition, 2 internal error.
Runtime files live in ~/.jsonui-cli/viz/ (``viz.pid``, ``server.json`` 0600).
"""
from __future__ import annotations

import argparse
import asyncio
import errno
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import webbrowser

from ..viz import paths


def register_viz_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "viz",
        help="Show the Claude Code sessions on this machine in the browser",
    )
    sub = parser.add_subparsers(dest="viz_cmd")

    serve = sub.add_parser("serve", help="Start the viz server in the foreground")
    serve.add_argument("--port", type=int, help="Port on 127.0.0.1 (default 7788)")
    serve.add_argument("--open", action="store_true", help="Open the page in the browser")

    status = sub.add_parser("status", help="Print whether a viz server is running")
    status.add_argument("--json", action="store_true", help="Machine-readable output")

    sub.add_parser("stop", help="Stop the running viz server")
    sub.add_parser("open", help="Open the running server's page in the browser")

    doctor = sub.add_parser("doctor", help="Check the environment for jui viz")
    doctor.add_argument("--json", action="store_true", help="Machine-readable output")

    hooks = sub.add_parser("hooks", help="Install or remove the Claude Code hooks (P2)")
    hooks.add_argument("hooks_action", nargs="?", choices=["install", "uninstall", "status"])
    relay = sub.add_parser("relay", help="Register the permission relay (P5)")
    relay.add_argument("relay_action", nargs="?", choices=["install", "uninstall"])


def cmd_viz(args: argparse.Namespace) -> int:
    handlers = {
        "serve": _cmd_serve,
        "status": _cmd_status,
        "stop": _cmd_stop,
        "open": _cmd_open,
        "doctor": _cmd_doctor,
        "hooks": lambda a: _not_yet("jui viz hooks", "P2"),
        "relay": lambda a: _not_yet("jui viz relay", "P5"),
    }
    handler = handlers.get(getattr(args, "viz_cmd", None))
    if handler is None:
        _err("使い方: jui viz {serve,status,stop,open,doctor,hooks,relay}")
        return 1
    try:
        return handler(args)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:  # noqa: BLE001 - report, don't dump a traceback
        _err(f"内部エラー: {type(exc).__name__}: {exc}")
        return 2


# ---------------------------------------------------------------- helpers


def _err(message: str) -> None:
    print(f"jui viz: {message}", file=sys.stderr)


def _not_yet(name: str, phase: str) -> int:
    _err(f"{name} はまだありません（{phase} で実装予定）")
    return 1


def _read_pid() -> int | None:
    try:
        return int(paths.pid_file().read_text().strip())
    except (OSError, ValueError):
        return None


def _read_server_json() -> dict | None:
    try:
        data = json.loads(paths.server_json().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)  # signal 0: existence check only
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _clear_runtime_files(pid: int | None = None) -> None:
    """Remove viz.pid and server.json — only if they still name ``pid`` when given."""
    if pid is not None:
        if _read_pid() not in (None, pid):
            return
    for path in (paths.server_json(), paths.pid_file()):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _running() -> tuple[int, dict | None] | None:
    """(pid, server.json) of a live server; clears files left by a dead one."""
    pid = _read_pid()
    if pid is None:
        if paths.server_json().exists():
            _clear_runtime_files()
        return None
    if not _pid_alive(pid):
        _clear_runtime_files()
        return None
    return pid, _read_server_json()


def _url(port: int) -> str:
    return f"http://127.0.0.1:{port}/"


def _write_private_json(path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)  # O_CREAT keeps the mode of a file that already existed
        os.write(fd, json.dumps(data).encode("utf-8"))
    finally:
        os.close(fd)


# ---------------------------------------------------------------- serve


def _cmd_serve(args: argparse.Namespace) -> int:
    from ..viz.config import load_config

    config = load_config()
    if getattr(args, "port", None):
        config.port = int(args.port)
    if not 1 <= config.port <= 65535:
        _err(f"ポート {config.port} は使えません（1〜65535）")
        return 1
    running = _running()
    if running is not None:
        _err("起動中です（jui viz stop で止める）")
        return 1
    return asyncio.run(_serve(config, open_browser=bool(getattr(args, "open", False)) or config.openBrowser))


async def _serve(config, open_browser: bool) -> int:
    from aiohttp import web

    from ..version import version_label
    from ..viz import security
    from ..viz.server import ServerContext, log, make_app, server_slice
    from ..viz.state import VizState, now_ms

    port = config.port
    ctx = ServerContext(
        config=config,
        port=port,
        token=security.make_token(),
        version=version_label(),
        state=VizState(config.eventsKeep),
    )
    ctx.on_hook = lambda payload: _record_raw_hook(ctx, payload)
    started_at = now_ms()
    ctx.state.set_slice("server", server_slice(ctx, started_at))

    in_use = f"ポート {port} は使用中です。--port で変えるか、使っているプロセスを止めてください"
    # SO_REUSEADDR stays on so a restart is not refused for a minute by the
    # last run's TIME_WAIT connections. On macOS it would also let us bind
    # 127.0.0.1:<port> beside another process listening on 0.0.0.0:<port>
    # and take its local traffic, so ask first whether anyone answers there.
    if _someone_listens(port):
        _err(in_use)
        return 1
    runner = web.AppRunner(make_app(ctx), access_log=None, handle_signals=False)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port, reuse_address=True)
    try:
        await site.start()
    except OSError as exc:
        await runner.cleanup()
        if exc.errno == errno.EADDRINUSE:
            _err(in_use)
            return 1
        raise

    pid = os.getpid()
    try:
        paths.pid_file().parent.mkdir(parents=True, exist_ok=True)
        paths.pid_file().write_text(str(pid))
        _write_private_json(paths.server_json(), {
            "pid": pid, "port": port, "token": ctx.token,
            "startedAt": started_at, "version": ctx.version,
        })
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        print(f"jui viz: {_url(port)} で待ち受けています（Ctrl+C で終了）", flush=True)
        print("  フック: 未対応（P2 で jui viz hooks install を追加します）", flush=True)
        log(f"起動しました（pid {pid}）")
        if open_browser:
            webbrowser.open(_url(port))
        await stop.wait()
        log("停止します")
    finally:
        await runner.cleanup()
        _clear_runtime_files(pid)
    return 0


def _someone_listens(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def _record_raw_hook(ctx, payload: dict) -> None:
    """P1 stand-in for ingest: one line per hook so the check page shows traffic.

    Keeps only names (event, tool, agent type), never tool input or prompts.
    """
    kind = payload.get("hook_event_name")
    tool = payload.get("tool_name")
    agent = payload.get("agent_type")
    session = payload.get("session_id")
    parts = [str(x) for x in (tool, agent) if isinstance(x, str) and x]
    ctx.state.add_event({
        "sessionId": session if isinstance(session, str) else "",
        "agentId": payload.get("agent_id") if isinstance(payload.get("agent_id"), str) else "",
        "kind": kind if isinstance(kind, str) else "?",
        "cat": "session",
        "text": " ".join(parts)[:200],
    })


# ---------------------------------------------------------------- status / stop / open


def _cmd_status(args: argparse.Namespace) -> int:
    running = _running()
    if running is None:
        info = {"running": False}
    else:
        pid, data = running
        port = (data or {}).get("port")
        info = {"running": True, "pid": pid, "url": _url(port) if isinstance(port, int) else None}
    if getattr(args, "json", False):
        print(json.dumps(info))
    elif info["running"]:
        print(f"jui viz: 起動中（pid {info['pid']}） {info['url'] or 'URL 不明（server.json が読めません）'}")
    else:
        print("jui viz: 停止中")
    return 0


def _cmd_stop(args: argparse.Namespace) -> int:
    running = _running()
    if running is None:
        print("jui viz: 起動していません")
        return 0
    pid, data = running
    if data is not None and data.get("pid") not in (None, pid):
        _err("viz.pid と server.json の pid が食い違うため止めません。jui viz status で確かめてください")
        return 1
    try:
        os.kill(pid, signal.SIGTERM)  # the pid this tool wrote to its own pid file
    except ProcessLookupError:
        _clear_runtime_files(pid)
        print("jui viz: 起動していません")
        return 0
    except PermissionError as exc:
        _err(f"pid {pid} を止められません: {exc}")
        return 1
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and _pid_alive(pid):
        time.sleep(0.05)
    if _pid_alive(pid):
        _err(f"pid {pid} が 5 秒で止まりませんでした")
        return 1
    _clear_runtime_files(pid)
    print(f"jui viz: 停止しました（pid {pid}）")
    return 0


def _cmd_open(args: argparse.Namespace) -> int:
    running = _running()
    port = (running[1] or {}).get("port") if running else None
    if not isinstance(port, int):
        _err("起動していません（jui viz serve で起動）")
        return 1
    webbrowser.open(_url(port))
    print(f"jui viz: {_url(port)} を開きました")
    return 0


# ---------------------------------------------------------------- doctor


def _doctor_checks() -> list[dict]:
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    version = sys.version_info
    add("python", version >= (3, 11), f"{version.major}.{version.minor}.{version.micro}（3.11 以上が必要）")
    for module in ("aiohttp", "watchdog"):
        try:
            __import__(module)
            add(module, True, "import できます")
        except ImportError:
            add(module, False, f"import できません（pip install {module}）")

    claude = shutil.which("claude")
    if claude is None:
        add("claude", False, "PATH にありません（セッション一覧の取得は無効になります）")
    else:
        try:
            out = subprocess.run([claude, "--version"], capture_output=True, text=True, timeout=5)
            add("claude", out.returncode == 0, (out.stdout or out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr).strip() else "版を読めません")
        except (OSError, subprocess.TimeoutExpired) as exc:
            add("claude", False, f"起動できません（{type(exc).__name__}）")

    settings = paths.claude_settings()
    try:
        data = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}
        disabled = isinstance(data, dict) and data.get("disableAllHooks") is True
        add("disableAllHooks", not disabled, "有効（フックは動きません）" if disabled else "設定されていません")
    except (OSError, ValueError):
        add("settings.json", False, f"{settings} を JSON として読めません")

    running = _running()
    if running is not None:
        port = (running[1] or {}).get("port")
        add("server", True, f"起動中（pid {running[0]}、{_url(port) if isinstance(port, int) else 'URL 不明'}）")
    else:
        from ..viz.config import load_config

        port = load_config().port
        add("server", True, "停止中")
        add("port", _port_free(port), f"{port} は{'空いています' if _port_free(port) else '使用中です'}")
    return checks


def _port_free(port: int) -> bool:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def _cmd_doctor(args: argparse.Namespace) -> int:
    checks = _doctor_checks()
    if getattr(args, "json", False):
        print(json.dumps({"ok": all(c["ok"] for c in checks), "checks": checks}, ensure_ascii=False))
    else:
        for c in checks:
            print(f"  {'OK' if c['ok'] else 'NG'}  {c['name']}: {c['detail']}")
    return 0 if all(c["ok"] for c in checks) else 1
