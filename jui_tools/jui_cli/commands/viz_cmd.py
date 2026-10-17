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
from pathlib import Path


def register_viz_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "viz",
        help="Show the Claude Code sessions on this machine in the browser",
    )
    sub = parser.add_subparsers(dest="viz_cmd")

    serve = sub.add_parser("serve", help="Start the viz server in the foreground")
    serve.add_argument("--port", type=int, help="Port on 127.0.0.1 (default 7788)")
    serve.add_argument("--open", action="store_true", help="Open the page in the browser")
    serve.add_argument("--record", metavar="FILE", help="Append every received hook body to FILE (JSONL; holds tool input)")
    serve.add_argument("--replay", metavar="FILE", help="Feed a --record file instead of live hooks")
    serve.add_argument("--speed", type=float, default=1.0, help="Replay speed (default 1.0)")
    serve.add_argument("--no-agents-poll", dest="no_agents_poll", action="store_true",
                       help="Do not run `claude agents --json`")

    status = sub.add_parser("status", help="Print whether a viz server is running")
    status.add_argument("--json", action="store_true", help="Machine-readable output")

    sub.add_parser("stop", help="Stop the running viz server")
    sub.add_parser("open", help="Open the running server's page in the browser")

    doctor = sub.add_parser("doctor", help="Check the environment for jui viz")
    doctor.add_argument("--json", action="store_true", help="Machine-readable output")

    hooks = sub.add_parser("hooks", help="Install or remove the Claude Code hooks in ~/.claude/settings.json")
    hooks.add_argument("hooks_action", nargs="?", choices=["install", "uninstall", "status"])
    hooks.add_argument("--dry-run", dest="dry_run", action="store_true", help="Show the change, write nothing")
    hooks.add_argument("--json", action="store_true", help="Machine-readable status")
    relay = sub.add_parser("relay", help="Register the permission relay (P5)")
    relay.add_argument("relay_action", nargs="?", choices=["install", "uninstall"])


def cmd_viz(args: argparse.Namespace) -> int:
    handlers = {
        "serve": _cmd_serve,
        "status": _cmd_status,
        "stop": _cmd_stop,
        "open": _cmd_open,
        "doctor": _cmd_doctor,
        "hooks": _cmd_hooks,
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


#: A pid file younger than this with no matching server.json is a serve still
#: starting up (it takes the lock before it binds), not a leftover.
STARTING_GRACE_SEC = 30


def _read_pid() -> int | None:
    """The pid in viz.pid, or None. Anything but an integer >= 2 is a broken
    file: it is removed and never signalled (0 would be our own process group,
    -1 every process we may signal, 1 launchd)."""
    path = paths.pid_file()
    try:
        text = path.read_text().strip()
    except OSError:
        return None
    if text.isascii() and text.isdigit() and int(text) >= 2:
        return int(text)
    _clear_runtime_files()
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
        try:
            current = paths.pid_file().read_text().strip()
        except OSError:
            current = None
        if current not in (None, str(pid)):
            return
    for path in (paths.server_json(), paths.pid_file()):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


#: _health_pid's answers besides a pid.
REFUSED = "refused"  # nothing listens there: certainly not our server
UNKNOWN = "unknown"  # no answer in time / not a viz answer: cannot tell


def _health_pid(port: int, timeout: float = 1.0):
    """The pid the server on 127.0.0.1:<port> reports, REFUSED or UNKNOWN.

    A raw socket, like forward.py: urllib follows HTTP(S)_PROXY, and a proxy
    variable once turned a live server into "not answering" and its files
    were removed (independent review, 10-18).
    """
    try:
        sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    except ConnectionRefusedError:
        return REFUSED
    except OSError:
        return UNKNOWN
    try:
        sock.settimeout(timeout)
        sock.sendall(f"GET /health HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n".encode("ascii"))
        raw = b""
        while len(raw) < 65536:
            chunk = sock.recv(4096)
            if not chunk:
                break
            raw += chunk
    except OSError:
        return UNKNOWN
    finally:
        sock.close()
    head, _, body = raw.partition(b"\r\n\r\n")
    if not head.startswith(b"HTTP/1.1 200"):
        return UNKNOWN
    try:
        pid = json.loads(body.decode("utf-8")).get("pid")
    except (UnicodeDecodeError, ValueError, AttributeError):
        return UNKNOWN
    return pid if isinstance(pid, int) else UNKNOWN


def _identify() -> tuple[str, int, dict | None] | None:
    """("running", pid, server.json) / ("starting", pid, None) / None.

    A live pid is not enough: after a crash the pid can belong to another
    process. "running" needs server.json to name the same pid AND the server
    on its port to answer /health with it. Files that fail that are removed,
    and nothing is signalled.
    """
    pid = _read_pid()
    if pid is None:
        if paths.server_json().exists():
            _clear_runtime_files()
        return None
    if not _pid_alive(pid):
        _clear_runtime_files()
        return None
    data = _read_server_json()
    port = (data or {}).get("port")
    if data is not None and data.get("pid") == pid and isinstance(port, int):
        answer = _health_pid(port)
        if answer == pid:
            return "running", pid, data
        if answer == UNKNOWN:
            # Alive, files agree, but no clear answer (load, a hung loop):
            # keep the files and signal nothing.
            return "unresponsive", pid, data
        _clear_runtime_files(pid)  # refused, or another pid answers there
        return None
    try:
        age = time.time() - paths.pid_file().stat().st_mtime
    except OSError:
        return None
    if age < STARTING_GRACE_SEC:
        return "starting", pid, None
    _clear_runtime_files(pid)
    return None


def _running() -> tuple[int, dict | None] | None:
    """(pid, server.json) of a verified running server, else None."""
    found = _identify()
    if found is None or found[0] != "running":
        return None
    return found[1], found[2]


def _take_lock() -> bool:
    """Create viz.pid exclusively. False if a serve holds it (or is starting)."""
    folder = paths.pid_file().parent
    folder.mkdir(parents=True, exist_ok=True)
    # The pid file appears WITH its content: written to a private temp file,
    # then hard-linked into place (link fails if the name exists). Created
    # empty and filled afterwards, a second serve read it empty in between,
    # took it for a broken file, removed it, and both ran.
    tmp = folder / f".viz.pid.{os.getpid()}.tmp"
    tmp.write_text(str(os.getpid()))
    try:
        for _ in range(2):
            try:
                os.link(tmp, paths.pid_file())
                return True
            except FileExistsError:
                if _identify() is not None:
                    return False
                # a leftover, now removed: try once more
        return False
    finally:
        tmp.unlink(missing_ok=True)


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
    if getattr(args, "replay", None) and not os.path.isfile(args.replay):
        _err(f"{args.replay} がありません")
        return 1
    if getattr(args, "replay", None) and getattr(args, "record", None):
        _err("--record と --replay は同時に使えません")
        return 1
    if not _take_lock():
        _err("起動中です（jui viz stop で止める）")
        return 1
    try:
        return asyncio.run(_serve(
            config,
        open_browser=bool(getattr(args, "open", False)) or config.openBrowser,
        record=getattr(args, "record", None),
        replay=getattr(args, "replay", None),
        speed=float(getattr(args, "speed", 1.0) or 1.0),
            agents_poll=not getattr(args, "no_agents_poll", False) and config.agentsPollSec > 0,
        ))
    finally:
        _clear_runtime_files(os.getpid())


async def _serve(config, open_browser: bool, record: str | None = None, replay: str | None = None,
                 speed: float = 1.0, agents_poll: bool = True) -> int:
    from aiohttp import web

    from ..version import version_label
    from ..viz import hooks_installer, recorder, security
    from ..viz.ingest import World
    from ..viz.server import ServerContext, log, make_app, quiet_aiohttp_logs, server_slice
    from ..viz.sources import agents_cli, session_files
    from ..viz.state import VizState, now_ms

    quiet_aiohttp_logs()
    port = config.port
    ctx = ServerContext(
        config=config,
        port=port,
        token=security.make_token(),
        version=version_label(),
        state=VizState(config.eventsKeep),
    )
    world = World(ctx.state, config.toolInputMaxChars)
    started_at = now_ms()
    sources: dict[str, dict] = {}

    def set_source(name: str, status: str, error: str | None = None) -> None:
        sources[name] = {"status": status, **({"error": error} if error else {})}
        ctx.state.set_slice("server", server_slice(ctx, started_at, {k: dict(v) for k, v in sources.items()}))
        if error:
            log(f"{name}: {error}")

    rec = recorder.Recorder(Path(record)) if record else None
    observers: list = []
    loop = asyncio.get_running_loop()

    def sheet(spec_id: str):
        from ..viz.sheet import sheet_for

        for project in world.jsonui.values():
            if spec_id in project.specs:
                return sheet_for(project, spec_id)
        return None

    ctx.sheet = sheet

    def watch_project(project) -> None:
        from ..viz.sources import jsonui_project

        def on_change(path: str) -> None:
            loop.call_soon_threadsafe(lambda: (world.file_changed(project.project_id, path, now_ms()), world.publish()))

        observer = jsonui_project.watch(project, on_change)
        if observer is not None:
            observers.append(observer)

    if not replay:
        world.on_project_loaded = watch_project

    def on_hook(payload: dict) -> None:
        at = now_ms()
        if rec is not None:
            rec.write(at, payload)
        world.apply_hook(payload, at)
        world.publish()

    ctx.on_hook = None if replay else on_hook
    set_source("hooks", "replay" if replay else "running")

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
    tasks: list[asyncio.Task] = []
    observer = None
    try:
        _write_private_json(paths.server_json(), {
            "pid": pid, "port": port, "token": ctx.token,
            "startedAt": started_at, "version": ctx.version,
        })
        hooks_installer.progress_dir().mkdir(parents=True, exist_ok=True)

        if replay:
            set_source("agents", "stopped", None)

            async def run_replay() -> None:
                def apply(body: dict, t: int) -> None:
                    world.apply_hook(body, t)
                    world.publish()

                def tick(t: int) -> None:
                    world.tick(t)
                    world.publish()

                count = await recorder.replay(Path(replay), apply, speed, tick)
                log(f"再生が終わりました（{count} 件）")

            tasks.append(asyncio.create_task(run_replay()))
        else:
            for data in session_files.scan(paths.claude_sessions_dir()):
                world.apply_session_file(data, now_ms())
            world.publish()

            def on_session_file(data: dict) -> None:
                loop.call_soon_threadsafe(lambda: (world.apply_session_file(data, now_ms()), world.publish()))

            observer = session_files.watch(paths.claude_sessions_dir(), on_session_file)
            set_source("sessionFiles", "running" if observer else "stopped",
                       None if observer else "~/.claude/sessions がありません")
            if agents_poll:
                def on_rows(rows: list) -> None:
                    world.apply_agents_list(rows, now_ms())
                    world.publish()

                tasks.append(asyncio.create_task(agents_cli.run(
                    config.agentsPollSec, on_rows, lambda st, err: set_source("agents", st, err))))
            else:
                set_source("agents", "stopped", None)

            async def tick_loop() -> None:
                while True:
                    await asyncio.sleep(0.5)
                    world.tick(now_ms())
                    world.publish()

            tasks.append(asyncio.create_task(tick_loop()))

        stop = asyncio.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        hook_state = hooks_installer.status()
        print(f"jui viz: {_url(port)} で待ち受けています（Ctrl+C で終了）", flush=True)
        if replay:
            print(f"  再生: {replay}（{speed} 倍速）。フックの受信とセッション一覧の取得は止めています", flush=True)
        elif hook_state.get("installed"):
            print(f"  フック: 入っています（{hook_state['installed']} イベント）", flush=True)
        else:
            print("  フック: 入っていません（jui viz hooks install で入れます）", flush=True)
        if not replay:
            print(f"  セッション一覧: {'claude agents --json を ' + format(config.agentsPollSec, 'g') + ' 秒ごとに取得' if agents_poll else '取得しません'}", flush=True)
        if rec is not None:
            print(f"  {recorder.WARNING}: {record}", flush=True)
        log(f"起動しました（pid {pid}）")
        if open_browser:
            webbrowser.open(_url(port))
        await stop.wait()
        log("停止します")
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        for watcher in [observer, *observers]:
            if watcher is not None:
                watcher.stop()
                watcher.join(timeout=2)
        if rec is not None:
            rec.close()
        await runner.cleanup()
        _clear_runtime_files(pid)
    return 0


def _someone_listens(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------- hooks


def _cmd_hooks(args: argparse.Namespace) -> int:
    from ..viz import hooks_installer as hi

    action = getattr(args, "hooks_action", None)
    if action is None:
        _err("使い方: jui viz hooks {install,uninstall,status} [--dry-run]")
        return 1
    if action == "status":
        info = hi.status()
        if getattr(args, "json", False):
            print(json.dumps(info, ensure_ascii=False))
            return 0
        if not info.get("readable"):
            _err(info.get("error", "settings.json を読めません"))
            return 1
        print(f"jui viz: フック {info['installed']}/{len(hi.EVENTS)} イベント（{info['path']}）")
        missing = [e for e, ok in info["events"].items() if not ok]
        if missing and info["installed"]:
            print(f"  入っていないイベント: {', '.join(missing)}")
        for command in info["broken"]:
            print(f"  NG  python か forward.py が見つかりません: {command}（jui viz hooks install で入れ直す）")
        if info["disableAllHooks"]:
            print("  NG  フックが全体で無効になっています（disableAllHooks: true）")
        if info["otherHooks"]:
            print("  ほかのフックもあります")
        return 0
    try:
        result = hi.install(dry_run=args.dry_run) if action == "install" else hi.uninstall(dry_run=args.dry_run)
    except hi.SettingsError as exc:
        _err(str(exc))
        return 1
    for warning in result.warnings:
        _err(warning)
    if args.dry_run:
        print(result.diff or "変更はありません")
        return 0
    if not result.changed:
        print("jui viz: 変更はありません")
        return 0
    if action == "install":
        print(f"jui viz: フックを入れました（{len(result.events)} イベント: {', '.join(result.events)}）")
    else:
        print("jui viz: フックを外しました")
    if result.backup is not None:
        print(f"  バックアップ: {result.backup}")
    return 0


# ---------------------------------------------------------------- status / stop / open


def _cmd_status(args: argparse.Namespace) -> int:
    found = _identify()
    if found is None:
        info = {"running": False}
    elif found[0] == "starting":
        info = {"running": False, "starting": True, "pid": found[1]}
    elif found[0] == "unresponsive":
        info = {"running": True, "unresponsive": True, "pid": found[1], "url": None}
    else:
        _, pid, data = found
        port = (data or {}).get("port")
        info = {"running": True, "pid": pid, "url": _url(port) if isinstance(port, int) else None}
    if getattr(args, "json", False):
        print(json.dumps(info))
    elif info.get("unresponsive"):
        print(f"jui viz: 起動中ですが /health に応答しません（pid {info['pid']}）")
    elif info.get("starting"):
        print(f"jui viz: 起動の途中（pid {info['pid']}）")
    elif info["running"]:
        print(f"jui viz: 起動中（pid {info['pid']}） {info['url'] or 'URL 不明（server.json が読めません）'}")
    else:
        print("jui viz: 停止中")
    return 0


def _cmd_stop(args: argparse.Namespace) -> int:
    found = _identify()
    if found is None:
        print("jui viz: 起動していません")
        return 0
    state, pid, _ = found
    if state == "starting":
        _err("起動の途中です。少し待ってから jui viz stop を再実行してください")
        return 1
    if state == "unresponsive":
        _err(f"pid {pid} が /health に応答しないため止めません（viz か確かめられません）。少し待って再実行してください")
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

    from ..viz import hooks_installer

    hooks = hooks_installer.status()
    if hooks.get("readable"):
        total = len(hooks_installer.EVENTS)
        ok = hooks["installed"] == total and not hooks["broken"]
        add("hooks", ok, f"{hooks['installed']}/{total} イベント" + ("" if ok else "（jui viz hooks install で入れる）"))

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
