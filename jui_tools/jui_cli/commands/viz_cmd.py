"""``jui viz`` — a local browser view of the Claude Code sessions on this machine.

Subcommands:
    jui viz serve    Start the server in the foreground (127.0.0.1 only)
    jui viz start    Start it in the background, wait until it answers, print the URL
    jui viz status   Whether a server is running, and its URL
    jui viz stop     SIGTERM the pid this tool wrote to its own pid file
    jui viz open     Open the running server's page in the browser
    jui viz doctor   Check the environment
    jui viz hooks    (P2) install / uninstall / status of the Claude Code hooks
    jui viz relay    (P5) the permission relay

Exit codes: 0 success, 1 usage error or a missing precondition, 2 internal error.
Runtime files live in paths.viz_home() — ``$JUI_VIZ_HOME``, else
``$XDG_STATE_HOME/jui-viz``, else ``~/.local/state/jui-viz`` — outside the
install folder, which every bootstrap replaces (``viz.pid``, ``server.json``
0600, ``serve.log`` 0600 for a server ``start`` launched). What 2.1.0 and
earlier left in ~/.jsonui-cli/viz is moved there by the first viz command.
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

    start = sub.add_parser("start", help="Start the viz server in the background and print its URL")
    start.add_argument("--port", type=int, help="Port on 127.0.0.1 (default 7788)")
    start.add_argument("--json", action="store_true", help="Machine-readable output")

    status = sub.add_parser("status", help="Print whether a viz server is running")
    status.add_argument("--json", action="store_true", help="Machine-readable output")
    status.add_argument("--with-relay", dest="with_relay", action="store_true",
                        help="Also ask claude whether the permission relay is registered (runs claude mcp get; slower)")

    stop = sub.add_parser("stop", help="Stop the running viz server")
    stop.add_argument("--port", type=int, help="Also look for a viz server without its files on this port (default: the configured port)")
    sub.add_parser("open", help="Open the running server's page in the browser")

    doctor = sub.add_parser("doctor", help="Check the environment for jui viz")
    doctor.add_argument("--json", action="store_true", help="Machine-readable output")

    hooks = sub.add_parser("hooks", help="Install or remove the Claude Code hooks in ~/.claude/settings.json")
    hooks.add_argument("hooks_action", nargs="?", choices=["install", "uninstall", "status"])
    hooks.add_argument("--dry-run", dest="dry_run", action="store_true", help="Show the change, write nothing")
    hooks.add_argument("--json", action="store_true", help="Machine-readable status")
    statusline = sub.add_parser("statusline", help="Install or remove the statusLine that hands the usage limits to jui viz")
    statusline.add_argument("statusline_action", nargs="?", choices=["install", "uninstall", "status"])
    statusline.add_argument("--dry-run", dest="dry_run", action="store_true", help="Show the change, write nothing")
    statusline.add_argument("--json", action="store_true", help="Machine-readable status")
    export = sub.add_parser("export-demo", help="Write the demo page as a static folder (for a docs site)")
    export.add_argument("--out", required=True, help="An empty or new folder")

    pr = sub.add_parser("prices", help="Show or change the prices behind the estimated cost over each robot")
    pr.add_argument("prices_action", nargs="?", choices=["list", "set", "remove", "reset"], default="list")
    pr.add_argument("model", nargs="?", help="The model ID as the transcript writes it (message.model)")
    for flag, key in (("--input", "input"), ("--cache-write-5m", "cache_write_5m"), ("--cache-write-1h", "cache_write_1h"),
                      ("--cache-read", "cache_read"), ("--output", "output")):
        pr.add_argument(flag, dest=key, type=float, help="USD per million tokens (set: all five are required)")
    pr.add_argument("--json", action="store_true", help="Machine-readable list")

    relay = sub.add_parser("relay", help="Register the permission relay (an MCP channel) with Claude Code")
    relay.add_argument("relay_action", nargs="?", choices=["install", "uninstall", "status"])
    relay.add_argument("--dry-run", dest="dry_run", action="store_true", help="Show the command, run nothing")
    relay.add_argument("--yes", action="store_true", help="Do not ask before running claude mcp")


def cmd_viz(args: argparse.Namespace) -> int:
    handlers = {
        "serve": _cmd_serve,
        "start": _cmd_start,
        "status": _cmd_status,
        "stop": _cmd_stop,
        "open": _cmd_open,
        "doctor": _cmd_doctor,
        "hooks": _cmd_hooks,
        "statusline": _cmd_statusline,
        "relay": _cmd_relay,
        "export-demo": _cmd_export_demo,
        "prices": _cmd_prices,
    }
    handler = handlers.get(getattr(args, "viz_cmd", None))
    if handler is None:
        _err("使い方: jui viz {serve,start,status,stop,open,doctor,hooks,statusline,relay,export-demo,prices}")
        return 1
    try:
        # Every command that reads or writes the runtime folder moves the old one first; export-demo uses none.
        moved = paths.migrate_legacy() if args.viz_cmd != "export-demo" else []
        if moved:
            _err(f"状態を {paths.legacy_viz_home()} から {paths.viz_home()} へ移しました（{', '.join(moved)}）")
        return handler(args)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:  # noqa: BLE001 - report, don't dump a traceback
        _err(f"内部エラー: {type(exc).__name__}: {exc}")
        return 2


# ---------------------------------------------------------------- prices (the bill over a robot, 2.3.6)


def _cmd_prices(args: argparse.Namespace) -> int:
    """list: the table in use (shipped, then the user's), where each price comes from, and the user's rows left out
    with the reason. set / remove / reset: change the user's table (<viz home>/prices.json); a running server uses it
    from its next response, with no restart."""
    from ..viz import prices
    action = args.prices_action
    path = prices.user_path()
    if action == "list":
        book = prices.PriceBook(user=path)
        book.read_now()
        rows = book.rows()
        if args.json:
            print(json.dumps({"rows": rows, "errors": book.errors, "source": book.default["source"],
                              "checked": book.default["checked"], "userPath": str(path)}, ensure_ascii=False, indent=1))
            return 0
        print(f"単価（USD / 100 万トークン）。出典: {book.default['source']}（{book.default['checked']} に確認）")
        print(f"利用者の表: {path}")
        names = {"default": "既定", "user": "追加", "changed": "変更", "removed": "削除"}
        for r in rows:
            if r["origin"] == "removed":
                print(f"  {r['model']:<30} 削除（金額を出さない）")
                continue
            print(f"  {r['model']:<30} 入力 {r['input']:g} / 書込5分 {r['cache_write_5m']:g} / 書込1時間 {r['cache_write_1h']:g}"
                  f" / 読込 {r['cache_read']:g} / 出力 {r['output']:g}  [{names[r['origin']]}]")
        for e in book.errors:
            print(f"  使わない行: {e}")
        return 0
    if not args.model:
        _err(f"jui viz prices {action} にはモデル名が要ります")
        return 1
    row = None
    if action == "set":
        row = {k: getattr(args, k) for k in prices.KINDS}
        missing = [k for k, v in row.items() if v is None]
        if missing:
            _err("set には 5 つの単価が要ります: " + ", ".join("--" + k.replace("_", "-") for k in missing))
            return 1
    ok, msg = prices.apply_op(path, action, args.model, row)
    if not ok:
        _err(msg)
        return 1
    print(f"{msg}（{path}）")
    return 0


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


# ---------------------------------------------------------------- the jui-viz plugin 1.0.0
#
# ⏳ COMPATIBILITY, TO REMOVE IN jsonui-cli 3.0.0 (the next major), together with
# LEGACY_MIRROR_SEC, the mirror task in _serve and its clear in _cmd_serve.
#
# The plugin 1.0.0's forward.py / channel.py read ~/.jsonui-cli/viz/server.json
# and nothing else; a plugin is updated by hand, so it outlives the CLI that
# moved the runtime folder. Without this, a new server and an old plugin meet
# silently: no robot moves and the permission relay is gone. So a running
# server also writes a copy of server.json there, marked with "mirrorOf" (the
# real one's path). Only when the install folder (~/.jsonui-cli) exists, so a
# machine without one gets no folder of ours; never over a server.json that is
# not a mirror (a 2.1.0 server's own). The bootstrap deletes that folder, so
# the server rewrites a missing copy every LEGACY_MIRROR_SEC. Stopping removes
# it. The plugin 1.0.1 and later read the new folder only.

LEGACY_MIRROR_SEC = 2.0
LEGACY_MIRROR_KEY = "mirrorOf"


def _legacy_server_json() -> Path:
    return paths.legacy_viz_home() / "server.json"


def _read_legacy_server_json() -> dict | None:
    """The old folder's server.json; {} when it exists but is not a JSON object; None when absent."""
    try:
        data = json.loads(_legacy_server_json().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _legacy_mirror_write(info: dict) -> bool:
    """Write the copy for old plugins when it is missing or stale. True when written."""
    if not paths.legacy_viz_home().parent.is_dir():
        return False
    current = _read_legacy_server_json()
    if current is not None and not current.get(LEGACY_MIRROR_KEY):
        return False  # a server.json that is not a mirror: an old server's, not ours to replace
    wanted = dict(info, **{LEGACY_MIRROR_KEY: str(paths.server_json())})
    if current == wanted:
        return False
    paths.legacy_viz_home().mkdir(mode=0o700, exist_ok=True)
    _write_private_json(_legacy_server_json(), wanted)
    return True


def _legacy_mirror_clear(pid: int) -> None:
    """Remove the copy this server wrote (only a mirror naming ``pid``), and the old folder when that leaves it empty."""
    current = _read_legacy_server_json()
    if current and current.get(LEGACY_MIRROR_KEY) and current.get("pid") == pid:
        try:
            _legacy_server_json().unlink()
        except FileNotFoundError:
            pass
        try:
            paths.legacy_viz_home().rmdir()
        except OSError:
            pass


def _legacy_in_use() -> list[str]:
    """What the old folder holds besides our mirror: something still written by an old plugin or hook."""
    folder = paths.legacy_viz_home()
    if not folder.is_dir():
        return []
    mirror = _read_legacy_server_json()
    return sorted(p.name for p in folder.iterdir()
                  if not (p.name == "server.json" and mirror and mirror.get(LEGACY_MIRROR_KEY)))


#: _health_pid's answers besides a pid.
REFUSED = "refused"  # nothing listens there: certainly not our server
UNKNOWN = "unknown"  # no answer in time / not a viz answer: cannot tell


def _health_body(port: int, timeout: float = 1.0):
    """The JSON body of /health on 127.0.0.1:<port> (a dict), REFUSED or UNKNOWN.

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
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return UNKNOWN
    return data if isinstance(data, dict) else UNKNOWN


def _health_pid(port: int, timeout: float = 1.0):
    """The pid the server on 127.0.0.1:<port> reports, REFUSED or UNKNOWN."""
    body = _health_body(port, timeout)
    if not isinstance(body, dict):
        return body
    pid = body.get("pid")
    return pid if isinstance(pid, int) else UNKNOWN


def _health_info(port: int, timeout: float = 1.0) -> tuple[int, str | None] | None:
    """(pid, home) from /health on 127.0.0.1:<port>; home is None for a server that does not report one."""
    body = _health_body(port, timeout)
    if not isinstance(body, dict) or not isinstance(body.get("pid"), int):
        return None
    home = body.get("home")
    return body["pid"], home if isinstance(home, str) else None


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


def _command_line(pid: int) -> str:
    try:
        out = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def _process_home(pid: int) -> str | None:
    """The HOME a process runs with: /proc on Linux, ``ps -E`` (BSD/macOS) else. None when unreadable."""
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
        for item in raw.split(b"\0"):
            if item.startswith(b"HOME="):
                return item[5:].decode("utf-8", "replace")
        return None
    except OSError:
        pass
    try:
        out = subprocess.run(["ps", "-E", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return None
    homes = [w[5:] for w in out.stdout.split() if w.startswith("HOME=")]
    return homes[-1] if out.returncode == 0 and len(set(homes)) == 1 else None


def _orphan(port: int) -> int | None:
    """The pid of OUR viz server on 127.0.0.1:<port> that this tool has no files for, else None.

    An orphan is what an install that deleted the runtime files left behind:
    alive, answering, unreachable by status / stop. Before it is named, let
    alone signalled, all of these must hold:
      * /health on that port reports the pid, and that pid's command line is ``… viz serve …``;
      * it is ours: its /health ``home`` is this viz_home() — or, for a server
        from before /health named its home (2.1.0 and earlier), it runs with
        this HOME. A viz server of another HOME or another JUI_VIZ_HOME on the
        same port is not ours to stop (a test in a temporary HOME once
        stopped the user's real server on the default port).
    """
    answer = _health_info(port)
    if answer is None:
        return None
    pid, home = answer
    if pid < 2 or pid == os.getpid():
        return None
    # Ours first: nothing — not even signal 0 — reaches a server that is not.
    if (home if home is not None else _process_home(pid)) != str(paths.viz_home() if home is not None else Path.home()):
        return None
    argv = _command_line(pid).split()
    if not any(a == "viz" and b == "serve" for a, b in zip(argv, argv[1:])):
        return None
    return pid if _pid_alive(pid) else None


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


def _rewrite_server_json(info: dict, config) -> None:
    """The page chose another question window: forward.py --ask reads askHookWaitSec from server.json (ticket
    2026-10-20 question-window-over-5-min), so it is rewritten — whole, then moved into place, so a hook never reads
    half of it — and the old plugins' mirror with it."""
    from ..viz.config import ask_server_info

    info.update(ask_server_info(config))
    tmp = paths.server_json().with_name(paths.server_json().name + ".tmp")
    _write_private_json(tmp, info)
    os.replace(tmp, paths.server_json())
    try:
        _legacy_mirror_write(info)
    except OSError:
        pass


def _write_private_json(path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)  # O_CREAT keeps the mode of a file that already existed
        os.write(fd, json.dumps(data).encode("utf-8"))
    finally:
        os.close(fd)


# ---------------------------------------------------------------- serve


def _leave_the_launch_folder() -> None:
    """The server lives in its own folder, not where it was launched: the folder it was started from can be
    deleted (a git worktree removed, 10-18), and every child it starts inherits the cwd — `claude agents --json`
    exits 1 in a deleted folder, so the agents source stayed broken until a restart."""
    for target in (paths.viz_home(), Path.home()):
        try:
            os.chdir(target)
            return
        except OSError:
            continue


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
    _leave_the_launch_folder()
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
        _legacy_mirror_clear(os.getpid())


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
    from ..viz.paths import claude_home
    from ..viz.sources import history, transcripts
    world = World(ctx.state, config.toolInputMaxChars, session_start=transcripts.session_start(claude_home() / "projects"))
    world.transcript_path = transcripts.transcript_path(claude_home() / "projects")
    world.history_reader = history.reader(claude_home() / "projects")
    from ..viz import prices as prices_mod
    world.prices = prices_mod.PriceBook()
    from ..viz.attachments import Attachments
    world.attachments = Attachments()
    for gone in world.attachments.sweep_private(time.time()):   # left by a server that stopped before its hour was up
        log(f"添付の掃除: uploads/{gone}")
    world._dirty.add("prices")
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
    ctx.world = world
    ctx.publish = world.publish

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

    # The near weather (10-18): off by default, and then no connection is made at all. A replay never asks.
    from ..viz.sources import weather as weather_src

    weather = None if replay else weather_src.WeatherBook()

    def publish_weather() -> None:
        ctx.state.set_slice("weather", weather.view() if weather else {"on": False})
        status, error = weather.source() if weather else ("off", None)
        if sources.get("weather") != {"status": status, **({"error": error} if error else {})}:
            set_source("weather", status, error)

    ctx.weather, ctx.on_weather = weather, publish_weather
    publish_weather()
    # The plan's usage limits (statusline.py → POST /usage): the last value kept survives a restart.
    from ..viz import usage as usage_mod

    ctx.state.set_slice("usage", usage_mod.load())
    # the page's settings (2.3.6): how long a question waits for the page, its choices
    from ..viz.server import settings_slice

    ctx.state.set_slice("settings", settings_slice(ctx.config))

    def on_usage(payload: dict) -> None:
        value = usage_mod.accept(payload, now_ms())
        if value is not None:
            ctx.state.set_slice("usage", value)

    ctx.on_usage = None if replay else on_usage

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
    reader_cleanup: list = []
    observer = None
    from ..viz.config import ask_server_info

    try:
        info = {
            "pid": pid, "port": port, "token": ctx.token,
            "startedAt": started_at, "version": ctx.version, "decideWaitSec": config.decideWaitSec,
            **ask_server_info(config),
        }
        _write_private_json(paths.server_json(), info)

        ctx.on_settings = lambda: _rewrite_server_json(info, config)
        hooks_installer.progress_dir().mkdir(parents=True, exist_ok=True)

        _legacy_mirror_write(info)  # ⏳ for the plugin 1.0.0 (see _legacy_mirror_write); remove in 3.0.0

        async def legacy_mirror_loop() -> None:
            while True:
                await asyncio.sleep(LEGACY_MIRROR_SEC)
                try:
                    _legacy_mirror_write(info)
                except OSError:
                    pass

        tasks.append(asyncio.create_task(legacy_mirror_loop()))

        # the talk view (talk.py): its index is read and written in its own thread; this loop only starts a step and
        # takes a finished one (TalkHub.tick never waits), in a replay too (its HOME's transcripts)
        from ..viz import talk as talk_mod
        ctx.talk = talk_mod.TalkHub(
            lambda: talk_mod.TalkIndex(paths.viz_home() / "talk.db", claude_home() / "projects", paths.claude_sessions_dir(),
                                       int(config.talkGraceSec * 1000)),
            agents=lambda: world.agents, sessions=lambda: world.sessions)
        reader_cleanup.append(lambda: loop.run_in_executor(None, ctx.talk.close))

        async def talk_loop() -> None:
            while True:
                await asyncio.sleep(0.5)
                ctx.talk.tick(now_ms())

        tasks.append(asyncio.create_task(talk_loop()))

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

            from ..viz.sources import devices as devices_src
            from ..viz.sources import processes
            from ..viz.sources import test_progress
            from ..viz.sources import test_results

            shelf = test_results.ResultShelf(test_results.results_base())
            for folder in test_results.app_folders(shelf.base):
                test_results.prune(folder)
            world.apply_saved_results(shelf.scan())
            pulls: dict[str, asyncio.Task] = {}

            def pull_results(serial: str) -> None:
                """adb pull one device's saved results, then read the shelf again. Two moments only (10-18):
                once per device at start, and when a run_end comes from it. One pull per device at a time."""
                if not adb or (serial in pulls and not pulls[serial].done()):
                    return

                async def go() -> None:
                    await test_results.pull(adb, serial, shelf.base)
                    world.apply_saved_results(shelf.scan())
                    world.publish()

                pulls[serial] = asyncio.create_task(go())

            async def background_loop() -> None:
                # Sessions waiting on background work: is a background shell still under their process? (10-18)
                while True:
                    await asyncio.sleep(5)
                    if not world.background_pids():
                        continue
                    rows = await loop.run_in_executor(None, processes.snapshot)
                    world.check_background(rows, now_ms())
                    world.publish()

            tasks.append(asyncio.create_task(background_loop()))

            first_scan = {"done": False}

            def on_devices(found: list[dict]) -> None:
                world.apply_devices(found)
                world.publish()
                if not first_scan["done"]:  # the start-up pull rides the first device scan; no watcher of its own
                    first_scan["done"] = True
                    for dev in found:
                        if dev["platform"] == "android" and dev["state"] == "device":
                            pull_results(dev["id"])

            tasks.append(asyncio.create_task(devices_src.run(on_devices, lambda st, err: set_source("devices", st, err))))

            # The progress folder, and while a session still has the old one (a plugin or a settings.json
            # env written before the move: the web runner recreates it), that one too.
            tails = [test_progress.FolderTail(hooks_installer.progress_dir()),
                     test_progress.FolderTail(paths.legacy_progress_dir())]
            for tail in tails:
                tail.prune()
            readers: dict[tuple[str, str], asyncio.Task] = {}
            reader_idle: dict[tuple[str, str], int] = {}
            adb = devices_src.find_adb()
            xcrun = shutil.which("xcrun")

            def on_record(source: str, device_id: str | None):
                def handle(rec) -> None:
                    if world.apply_progress(rec, source, device_id, now_ms()):
                        world.publish()
                        if source == "android" and device_id and rec.get("event") == "run_end":
                            pull_results(device_id)
                return handle

            def manage_readers(at: int) -> None:
                """Follow the device logs only while a test of that platform runs."""
                wanted: set[tuple[str, str]] = set()
                for platform in ("android", "ios"):
                    if not world.running_tests(platform):
                        continue
                    for dev in world.devices:
                        if dev["platform"] == platform and dev["state"] in ("device", "booted"):
                            wanted.add((platform, dev["id"]))
                for key in wanted - readers.keys():
                    platform, dev_id = key
                    if platform == "android" and adb:
                        argv = test_progress.logcat_argv(adb, dev_id)
                        parse = test_progress.parse_logcat_line
                    elif platform == "ios" and xcrun:
                        argv = test_progress.simctl_log_argv(xcrun, dev_id)
                        parse = test_progress.parse_ndjson_line
                    else:
                        continue
                    readers[key] = asyncio.create_task(test_progress.follow(argv, parse, on_record(platform, dev_id)))
                for key in list(readers):
                    if key in wanted:
                        reader_idle.pop(key, None)
                        continue
                    reader_idle.setdefault(key, at)
                    if at - reader_idle[key] >= 30_000 or readers[key].done():
                        readers.pop(key).cancel()
                        reader_idle.pop(key, None)

            usage_ticks = {"n": 0, "dry": 0}

            def poll_usage(at: int) -> None:
                """Every 2 s: the transcripts' new usage (heavy work). Assistant lines without a readable usage for a
                while mean Claude Code changed the shape: the source says so; nothing else depends on it."""
                got = world.poll_usage(at)
                usage_ticks["dry"] = usage_ticks["dry"] + 1 if got["assistant"] and not got["usage"] else 0 if got["usage"] else usage_ticks["dry"]
                if usage_ticks["dry"] >= 5:
                    set_source("transcripts", "error", "記録の usage が読めない（形が変わった可能性）")
                elif sources.get("transcripts", {}).get("status") != "running":
                    set_source("transcripts", "running")

            async def tick_loop() -> None:
                while True:
                    await asyncio.sleep(0.5)
                    at = now_ms()
                    for tail in tails:
                        for rec in tail.read_new():
                            world.apply_progress(rec, "web", None, at)
                    usage_ticks["n"] += 1
                    if world.poll_prices():
                        log(f"単価の表を読み直しました（{world.prices.path()}）")
                        for e in world.prices.errors:
                            log(f"単価の表: 使わない行: {e}")
                    if usage_ticks["n"] % 4 == 0:
                        poll_usage(at)
                    if usage_ticks["n"] % 10 == 0:  # every 5 s: new files from iOS / Web runs
                        rows = await loop.run_in_executor(None, shelf.scan)
                        world.apply_saved_results(rows)
                    manage_readers(at)
                    world.tick(at)
                    world.publish()

            async def stop_readers() -> None:
                for task in [*readers.values(), *pulls.values()]:
                    task.cancel()
                for task in [*readers.values(), *pulls.values()]:
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):  # noqa: BLE001
                        pass

            async def mock_loop() -> None:
                from ..viz.sources import mock_status

                while True:
                    for project in list(world.jsonui.values()):
                        info = await loop.run_in_executor(None, mock_status.status, project.root, project.config)
                        world.apply_mock(project.project_id, info)
                    world.publish()
                    await asyncio.sleep(mock_status.INTERVAL_SEC)

            async def weather_loop() -> None:
                """While on: one query when due (at once when turned on, then every 30 min), in an executor so a
                slow answer never holds the server; once a minute the slice again, since an answer goes stale."""
                n = 0
                while True:
                    if weather.due():
                        await loop.run_in_executor(None, weather.ask)
                        publish_weather()
                    elif n % 60 == 0:
                        publish_weather()
                    n += 1
                    await asyncio.sleep(1)

            async def git_loop() -> None:
                """The box (2.3.4): count each push / pull's range in an executor (git, read-only, a short timeout), so
                a slow repository never holds the server; the trip's amount follows a moment after the trip."""
                from ..viz import gitbox

                while True:
                    for agent_id, trip_id, job in world.take_git_jobs():
                        counted = await loop.run_in_executor(None, gitbox.count_range, job["folder"], job["old"], job["new"])
                        world.git_counted(agent_id, trip_id, counted, now_ms())
                        world.publish()
                    await asyncio.sleep(0.3)

            tasks.append(asyncio.create_task(tick_loop()))
            tasks.append(asyncio.create_task(mock_loop()))
            tasks.append(asyncio.create_task(git_loop()))
            tasks.append(asyncio.create_task(weather_loop()))
            reader_cleanup.append(stop_readers)

        stop = asyncio.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        hook_state = hooks_installer.status()
        print(f"jui viz: {_url(port)} で待ち受けています（Ctrl+C で終了）", flush=True)
        if replay:
            print(f"  再生: {replay}（{speed} 倍速）。フックの受信とセッション一覧の取得は止めています", flush=True)
        elif hook_state.get("plugin"):
            print(f"  フック: プラグイン {hook_state['plugin']} で入っています", flush=True)
        elif hook_state.get("installed"):
            print(f"  フック: 入っています（{hook_state['installed']} イベント）", flush=True)
        else:
            print("  フック: 入っていません（/plugin install jui-viz@jsonui、または jui viz hooks install）", flush=True)
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
        for cleanup in reader_cleanup:
            await cleanup()
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


# ---------------------------------------------------------------- export-demo (P8)


def _cmd_export_demo(args: argparse.Namespace) -> int:
    from ..viz.export_demo import ExportError, export

    try:
        result = export(Path(args.out))
    except ExportError as exc:
        _err(str(exc))
        return 1
    print(f"jui viz: デモを書き出しました: {result['out']}（{result['files']} ファイル、{result['bytes'] / 1_000_000:.1f} MB）")
    print("  静的なサーバーやサイトの中で index.html を開いてください（file:// ではモジュールが読み込めません）")
    return 0


# ---------------------------------------------------------------- relay (08 §2)

RELAY_NAME = "jui-viz"
RELAY_ALIAS = "alias claude-viz='claude --dangerously-load-development-channels server:jui-viz'"


def _relay_argv(action: str, claude: str) -> list[str]:
    if action == "install":
        channel = Path(__file__).resolve().parents[1] / "viz" / "channel.py"
        return [claude, "mcp", "add", "--scope", "user", RELAY_NAME, "--", sys.executable, "-I", str(channel)]
    return [claude, "mcp", "remove", "--scope", "user", RELAY_NAME]


def _relay_registered(claude: str) -> bool | None:
    try:
        done = subprocess.run([claude, "mcp", "get", RELAY_NAME], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.returncode == 0


def _cmd_relay(args: argparse.Namespace) -> int:
    import shlex

    action = getattr(args, "relay_action", None)
    if action is None:
        _err("使い方: jui viz relay {install,uninstall,status} [--dry-run] [--yes]")
        return 1
    claude = shutil.which("claude")
    if claude is None:
        _err("claude が PATH にありません")
        return 1
    if action == "status":
        registered = _relay_registered(claude)
        print(f"jui viz: 許可の中継は{'登録済み' if registered else '未登録' if registered is False else '確かめられません'}")
        return 0
    argv = _relay_argv(action, claude)
    print("実行するコマンド:")
    print("  " + shlex.join(argv))
    if getattr(args, "dry_run", False):
        return 0
    if not getattr(args, "yes", False):
        try:
            answer = input("実行しますか？ [y/N] ")
        except EOFError:
            answer = ""
        if answer.strip().lower() not in ("y", "yes"):
            print("jui viz: 中止しました")
            return 1
    done = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    if done.returncode != 0:
        _err(f"claude mcp が失敗しました（{done.returncode}）: {(done.stderr or done.stdout).strip()[:300]}")
        return 1
    if action == "install":
        print("jui viz: 許可の中継を登録しました。ブラウザから答えるセッションは、次のように起動してください:")
        print("  claude --dangerously-load-development-channels server:jui-viz")
        print("  （起動時の警告では「I am using this for local development」を選びます。対話モードだけで有効です）")
        print(f"  エイリアスの例: {RELAY_ALIAS}")
    else:
        print("jui viz: 許可の中継の登録を外しました")
    return 0


# ---------------------------------------------------------------- hooks


STATUSLINE_NOTE = ("上限の値は、ターミナルの claude（の statusLine）からだけ届きます。VS Code 拡張とデスクトップアプリのセッションからは更新されません。"
                   "ターミナルの claude が 1 つ動いていれば更新されます")


def _cmd_statusline(args: argparse.Namespace) -> int:
    from ..viz import hooks_installer as hi
    from ..viz import statusline_installer as sl

    action = getattr(args, "statusline_action", None)
    if action is None:
        _err("使い方: jui viz statusline {install,uninstall,status} [--dry-run]")
        return 1
    if action == "status":
        info = sl.status()
        if getattr(args, "json", False):
            print(json.dumps(info, ensure_ascii=False))
            return 0
        if not info.get("readable"):
            _err(info.get("error", "settings.json を読めません"))
            return 1
        if info["installed"]:
            print(f"jui viz: statusLine を入れています（{info['path']}）" + (f"。元の statusLine を包んでいます: {info['wraps']}" if info["wraps"] else ""))
        else:
            print("jui viz: statusLine は入っていません" + ("（別の statusLine があります。install すると包みます）" if info["other"] else ""))
        print(f"  {STATUSLINE_NOTE}")
        return 0
    try:
        result = sl.install(dry_run=args.dry_run) if action == "install" else sl.uninstall(dry_run=args.dry_run)
    except hi.SettingsError as exc:
        _err(str(exc))
        return 1
    if args.dry_run:
        print(result.diff or "変更はありません")
        return 0
    if not result.changed:
        print("jui viz: 変更はありません")
        return 0
    print("jui viz: statusLine を入れました" if action == "install" else "jui viz: statusLine を外しました（包んでいたものは元に戻しました）")
    if result.backup is not None:
        print(f"  元の settings.json の控え: {result.backup}")
    if action == "install":
        print(f"  {STATUSLINE_NOTE}")
    return 0


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
        if info.get("plugin"):
            print(f"jui viz: プラグイン {info['plugin']} で入っています")
        print(f"jui viz: フック {info['installed']}/{len(hi.EVENTS)} イベント（{info['path']}）")
        missing = [e for e, ok in info["events"].items() if not ok]
        if missing and info["installed"]:
            print(f"  入っていないイベント: {', '.join(missing)}")
        for command in info["broken"]:
            print(f"  NG  python か forward.py が見つかりません: {command}（jui viz hooks install で入れ直す）")
        if info.get("askTimeout") is not None and info["askTimeout"] < hi.ASK_TIMEOUT_SEC:
            print(f"  NG  質問のフックの timeout が {info['askTimeout']:g} 秒のままです。長い待ち時間（30 分・答えるまで）が途中で切れます"
                  "（jui viz hooks install で入れ直す）")
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
        from ..viz.config import load_config

        port = load_config().port
        orphan = _orphan(port)
        info = {"running": False} if orphan is None else {"running": True, "orphan": True, "pid": orphan, "url": _url(port)}
    elif found[0] == "starting":
        info = {"running": False, "starting": True, "pid": found[1]}
    elif found[0] == "unresponsive":
        info = {"running": True, "unresponsive": True, "pid": found[1], "url": None}
    else:
        _, pid, data = found
        port = (data or {}).get("port")
        info = {"running": True, "pid": pid, "url": _url(port) if isinstance(port, int) else None}
    info["hooks"] = _hooks_summary()
    if getattr(args, "with_relay", False):
        info["relay"] = _relay_summary()
    if getattr(args, "json", False):
        print(json.dumps(info, ensure_ascii=False))
    elif info.get("orphan"):
        print(f"jui viz: 状態ファイルの無い viz サーバーが動いています（pid {info['pid']}） {info['url']}（jui viz stop で止められます）")
    elif info.get("unresponsive"):
        print(f"jui viz: 起動中ですが /health に応答しません（pid {info['pid']}）")
    elif info.get("starting"):
        print(f"jui viz: 起動の途中（pid {info['pid']}）")
    elif info["running"]:
        print(f"jui viz: 起動中（pid {info['pid']}） {info['url'] or 'URL 不明（server.json が読めません）'}")
    else:
        print("jui viz: 停止中")
    return 0


def _hooks_summary() -> dict:
    """What `status` says about the hooks: read from settings.json, no process started."""
    from ..viz import hooks_installer

    state = hooks_installer.status()
    if not state.get("readable"):
        return {"readable": False, "error": state.get("error")}
    return {
        "readable": True,
        "installed": state.get("installed", 0),
        "total": len(hooks_installer.EVENTS),
        "broken": len(state.get("broken") or []),
        "plugin": state.get("plugin"),
        "disableAllHooks": bool(state.get("disableAllHooks")),
    }


def _relay_summary() -> dict:
    """Whether the permission relay is registered: asks `claude mcp get`, so only with --with-relay."""
    claude = shutil.which("claude")
    if claude is None:
        return {"registered": None, "reason": "claude が PATH にありません"}
    registered = _relay_registered(claude)
    return {"registered": registered} if registered is not None else {"registered": None, "reason": "claude mcp get が答えませんでした"}


# ---------------------------------------------------------------- start

#: How long `start` waits for the server it launched to answer /health with its own pid.
START_WAIT_SEC = 15.0


def serve_log() -> Path:
    return paths.viz_home() / "serve.log"


def _serve_child_argv(port: int) -> list[str]:
    """This same jui_cli running `viz serve` — not whatever `jui` is first on PATH."""
    root = str(Path(__file__).resolve().parents[2])
    boot = f"import sys; sys.path.insert(0, {root!r}); from jui_cli.cli import main; sys.exit(main(sys.argv[1:]))"
    return [sys.executable, "-c", boot, "viz", "serve", "--port", str(port)]


def _log_tail(lines: int = 8) -> str:
    try:
        text = serve_log().read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(text.strip().splitlines()[-lines:])


def _start_report(args, info: dict, code: int) -> int:
    if getattr(args, "json", False):
        print(json.dumps(info, ensure_ascii=False))
    elif code == 0:
        verb = "起動済みです" if info.get("alreadyRunning") else "起動しました"
        print(f"jui viz: {verb}（pid {info['pid']}） {info['url']}")
        if not info.get("alreadyRunning"):
            print(f"  ログ: {info['log']}（止めるときは jui viz stop）")
    else:
        _err(info.get("error", "起動できませんでした"))
        if info.get("logTail"):
            print(info["logTail"], file=sys.stderr)
    return code


def _cmd_start(args: argparse.Namespace) -> int:
    """`serve` detached: launch it in its own session, wait until it answers /health with its own pid, print
    the URL and return. A server already running is reported, not started again (two `start`s at once: one
    serve takes the pid lock, the other start reports that one). On failure, only the child this call launched
    is signalled."""
    from ..viz.config import load_config

    config = load_config()
    port = int(args.port) if getattr(args, "port", None) else config.port
    if not 1 <= port <= 65535:
        return _start_report(args, {"running": False, "error": f"ポート {port} は使えません（1〜65535）"}, 1)

    def already(found) -> int:
        _, pid, data = found
        p = (data or {}).get("port")
        return _start_report(args, {"running": True, "alreadyRunning": True, "pid": pid,
                                    "url": _url(p) if isinstance(p, int) else None}, 0)

    deadline = time.monotonic() + START_WAIT_SEC
    found = _identify()
    while found is not None and found[0] == "starting" and time.monotonic() < deadline:
        time.sleep(0.2)          # another start/serve is coming up: report it once it answers
        found = _identify()
    if found is not None:
        if found[0] == "running":
            return already(found)
        return _start_report(args, {"running": False, "pid": found[1], "error":
                                    f"pid {found[1]} が起動中ですが /health に応答しません（jui viz status で確かめてください）"}, 1)

    orphan = _orphan(port)
    if orphan is not None:
        return _start_report(args, {"running": False, "orphan": True, "pid": orphan, "error":
                                    f"ポート {port} では viz サーバー（pid {orphan}）が状態ファイル無しで動いています。"
                                    f"jui viz stop{'' if port == config.port else f' --port {port}'} で止めてから起動してください"}, 1)

    log = serve_log()
    log.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        child = subprocess.Popen(_serve_child_argv(port), stdin=subprocess.DEVNULL, stdout=fd, stderr=fd,
                                 start_new_session=True, close_fds=True, cwd=str(paths.viz_home()))
    finally:
        os.close(fd)

    while time.monotonic() < deadline:
        found = _identify()
        if found is not None and found[0] == "running":
            if found[1] == child.pid:
                data = found[2] or {}
                return _start_report(args, {"running": True, "alreadyRunning": False, "pid": child.pid,
                                            "url": _url(data.get("port")), "log": str(log)}, 0)
            return already(found)   # another start won the lock; ours exits on its own
        if child.poll() is not None:
            found = _identify()
            if found is not None and found[0] == "running":
                return already(found)
            if found is not None and found[0] == "starting" and found[1] != child.pid:
                time.sleep(0.1)      # ours lost the pid lock to a serve still binding: report that one once it answers
                continue
            return _start_report(args, {"running": False, "error": f"jui viz serve が終了しました（終了コード {child.returncode}）",
                                        "log": str(log), "logTail": _log_tail()}, 1)
        time.sleep(0.1)

    # Not up in time: stop the child this call launched, and nothing else. terminate() does nothing once the
    # child has been reaped, so a pid reused after it exited is never signalled.
    if child.poll() is not None:
        return _start_report(args, {"running": False, "error": f"{int(START_WAIT_SEC)} 秒で /health に応答するサーバーがありませんでした",
                                    "log": str(log), "logTail": _log_tail()}, 1)
    try:
        child.terminate()
        child.wait(5)
    except subprocess.TimeoutExpired:
        pass
    return _start_report(args, {"running": False, "error": f"{int(START_WAIT_SEC)} 秒で /health に応答しませんでした。起動した pid {child.pid} を止めました",
                                "log": str(log), "logTail": _log_tail()}, 1)


def _cmd_stop(args: argparse.Namespace) -> int:
    found = _identify()
    if found is None:
        return _stop_orphan(args)
    state, pid, _ = found
    if state == "starting":
        _err("起動の途中です。少し待ってから jui viz stop を再実行してください")
        return 1
    if state == "unresponsive" and not _our_viz_serve(pid):
        # No /health answer, and the pid is not our `viz serve` (its command line or its HOME): not ours to signal.
        _err(f"pid {pid} が /health に応答しないうえ、この HOME の viz サーバーとも確かめられないため止めません")
        return 1
    # the pid this tool wrote to its own pid file; when it does not answer /health, also its command line and HOME
    how = _terminate(pid)
    if how is None:
        _clear_runtime_files(pid)
        print("jui viz: 起動していません")
        return 0
    if how == "alive":
        _err(f"pid {pid} を止められませんでした（TERM の {STOP_TERM_SEC} 秒後に KILL しても残っています）")
        return 1
    _clear_runtime_files(pid)
    note = "（/health に応答しないため、pid とコマンド行で確かめて止めました）" if state == "unresponsive" else ""
    note += f"（TERM の {STOP_TERM_SEC} 秒後に KILL しました）" if how == "killed" else ""
    print(f"jui viz: 停止しました（pid {pid}）{note}")
    return 0


#: `stop` sends TERM, waits this long, then KILL to a pid it verified as ours (10-18: an old server held on past 5 s
#: three times and was killed by hand; the cause did not reproduce on 2.3.0, so stop no longer depends on it).
STOP_TERM_SEC = 5
STOP_KILL_SEC = 3


def _our_viz_serve(pid: int) -> bool:
    """The pid runs `… viz serve …` with this HOME (the same rule as an orphan from before /health named its home)."""
    argv = _command_line(pid).split()
    if not any(a == "viz" and b == "serve" for a, b in zip(argv, argv[1:])):
        return False
    return _process_home(pid) == str(Path.home())


def _terminate(pid: int):
    """TERM, then KILL after STOP_TERM_SEC. None: it was already gone; "stopped" / "killed"; "alive": still there."""
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return None
    except PermissionError:
        return "alive"
    deadline = time.monotonic() + STOP_TERM_SEC
    while time.monotonic() < deadline and _pid_alive(pid):
        time.sleep(0.05)
    if not _pid_alive(pid):
        return "stopped"
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return "stopped"
    except PermissionError:
        return "alive"
    deadline = time.monotonic() + STOP_KILL_SEC
    while time.monotonic() < deadline and _pid_alive(pid):
        time.sleep(0.05)
    return "alive" if _pid_alive(pid) else "killed"


def _stop_orphan(args: argparse.Namespace) -> int:
    """No files name a server: stop a viz server on the port (--port, else the configured one) if there is one."""
    from ..viz.config import load_config

    port = int(args.port) if getattr(args, "port", None) else load_config().port
    pid = _orphan(port)
    if pid is None:
        print("jui viz: 起動していません")
        return 0
    how = _terminate(pid)   # /health on the port named it AND its command line is `viz serve` AND it is ours
    if how is None:
        print("jui viz: 起動していません")
        return 0
    if how == "alive":
        _err(f"pid {pid} を止められませんでした（TERM の {STOP_TERM_SEC} 秒後に KILL しても残っています）")
        return 1
    note = f"（TERM の {STOP_TERM_SEC} 秒後に KILL しました）" if how == "killed" else ""
    print(f"jui viz: 状態ファイルの無い viz サーバーを停止しました（pid {pid}、ポート {port}）{note}")
    return 0


def _cmd_open(args: argparse.Namespace) -> int:
    running = _running()
    port = (running[1] or {}).get("port") if running else None
    if not isinstance(port, int):
        _err("起動していません（jui viz start で裏で起動、または jui viz serve で前面で起動）")
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
        if hooks.get("plugin"):
            add("hooks", hooks["installed"] == 0, f"プラグイン {hooks['plugin']}" +
                ("" if hooks["installed"] == 0 else f"、加えて settings.json にも {hooks['installed']} イベント（二重。jui viz hooks uninstall で外す）"))
        else:
            ok = hooks["installed"] == total and not hooks["broken"]
            add("hooks", ok, f"{hooks['installed']}/{total} イベント" + ("" if ok else "（/plugin install jui-viz@jsonui、または jui viz hooks install）"))
            if hooks.get("askTimeout") is not None and hooks["askTimeout"] < hooks_installer.ASK_TIMEOUT_SEC:
                add("askTimeout", False, f"質問のフックの timeout が {hooks['askTimeout']:g} 秒のままです。長い待ち時間（30 分・答えるまで）が"
                    "途中で切れます。jui viz hooks install を撃ち直してください（Claude Code のセッションの再起動が要ります）")
        if hooks.get("progressEnv") in hooks_installer.legacy_progress_values():
            add("progressEnv", False, f"settings.json の {hooks_installer.PROGRESS_ENV} が古い場所（{hooks['progressEnv']}）のままです。"
                "jui viz hooks install を撃ち直すと新しい場所に書き換わります")
    legacy, in_use = paths.legacy_viz_home(), _legacy_in_use()
    add("state", not in_use, f"{paths.viz_home()}" + ("" if not in_use else
        f"（古い場所 {legacy} がまだ使われています: {', '.join(in_use)}。プラグインなら /plugin で jui-viz を更新し、"
        "settings.json のフックなら jui viz hooks install を撃ち直してください。どちらも Claude Code のセッションの再起動が要ります）"))

    from ..viz.sources import devices as devices_src
    from ..viz.sources import test_results

    base = test_results.results_base()
    override = os.environ.get(test_results.BASE_ENV, "")
    add("results", True, f"テストの結果を読む場所: {base}"
        + (f"（{test_results.BASE_ENV} で指定。driver 側にも同じ値が要ります）" if os.path.isabs(override) else "")
        + ("" if devices_src.find_adb() else "。adb が無いので Android の結果は取りません"))

    from ..viz.sources import weather as weather_src

    w_on, w_status = weather_src.load_setting()["on"], weather_src.read_status()
    if not w_on:
        add("weather", True, "近所の天気: オフ（外への通信はしません。ビルの全景のスイッチでオンにできます）")
    else:
        ok_at, err = w_status.get("lastOkAt"), w_status.get("lastError")
        when = time.strftime("%m-%d %H:%M", time.localtime(ok_at / 1000)) if isinstance(ok_at, (int, float)) else "まだ取れていない"
        add("weather", not err, f"近所の天気: オン（最後に取れた時刻 {when}）" + (f"。失敗: {err}" if err else ""))

    # the box (2.3.4): what it can see — nothing to check, so always ok; it says where the line is
    add("git-box", True, "git の箱: Claude のセッションが Bash で撃った git push / pull だけが見えます"
                         "（自分のターミナル、エディタの git、GitHub での merge は見えません）")
    from ..viz import statusline_installer as sl
    from ..viz import usage as usage_mod

    line = sl.status()
    last = usage_mod.load()
    when = time.strftime("%m-%d %H:%M", time.localtime(last["receivedAt"] / 1000)) if last else None
    add("usage", True, ("statusLine: 入っています" if line.get("installed") else "statusLine: 入っていません（jui viz statusline install）")
        + (f"。最後の値 {when}" if when else "。値はまだありません") + f"。{STATUSLINE_NOTE}")

    add("shredder", True, "削除の見分け: Bash の rm・rmdir・unlink・trash・git rm・git worktree remove・find -delete / -exec rm だけ。"
        "スクリプトの中の削除（Python の os.remove など）と、利用者自身の削除は見えません")

    if claude is not None:
        registered = _relay_registered(claude)
        add("relay", True, "許可の中継: " + ("登録済み" if registered else "未登録（jui viz relay install）" if registered is False else "確かめられません"))

    running = _running()
    if running is not None:
        port = (running[1] or {}).get("port")
        add("server", True, f"起動中（pid {running[0]}、{_url(port) if isinstance(port, int) else 'URL 不明'}）")
        sessions = _server_sessions(port, (running[1] or {}).get("token")) if isinstance(port, int) else None
        if sessions is not None:
            add("prompt", True, _prompt_reach(sessions))
    else:
        from ..viz.config import load_config

        port = load_config().port
        add("server", True, "停止中")
        add("port", _port_free(port), f"{port} は{'空いています' if _port_free(port) else '使用中です'}")
    return checks


def _server_sessions(port: int, token) -> list | None:
    """The running server's sessions slice (http.client: no proxy variable applies), or None."""
    import http.client

    if not isinstance(token, str) or not token:
        return None
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        conn.request("GET", "/api/snapshot", headers={"Host": f"127.0.0.1:{port}", "X-Jui-Viz-Token": token})
        res = conn.getresponse()
        data = json.loads(res.read().decode("utf-8")) if res.status == 200 else None
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    finally:
        conn.close()
    sessions = (data or {}).get("slices", {}).get("sessions") if isinstance(data, dict) else None
    return sessions if isinstance(sessions, list) else None


def _prompt_reach(sessions: list) -> str:
    """Which sessions a prompt typed in the page reaches (the robot card's 応答の履歴 tab): jui-viz 1.2.0+ connected,
    and the session started naming the channel (2.3.4: the CLI drops a channel's text otherwise; sources/launch.py)."""
    from ..viz.sources import launch

    live = [s for s in sessions if isinstance(s, dict) and s.get("status") != "ended"]
    relay = [s for s in live if s.get("relay")]
    able = [s for s in relay if s.get("prompt") and launch.REASONS.get(s.get("launch"), (False,))[0]]
    old = [s for s in relay if not s.get("prompt")]
    text = f"ページからのプロンプト送信: 届くセッション {len(able)}（中継あり {len(relay)} / 全 {len(live)}）"
    blocked: dict[str, list[str]] = {}
    for s in relay:
        if s.get("prompt") and s not in able:
            blocked.setdefault(str(s.get("launch") or "unreadable"), []).append(str(s.get("label") or s.get("id")))
    for key, names in blocked.items():
        text += f"。届かない {len(names)}（{', '.join(names)}）: {launch.REASONS.get(key, launch.REASONS['unreadable'])[1]}"
    if old:
        names = ", ".join(str(s.get("label") or s.get("id")) for s in old)
        text += (f"。jui-viz プラグインが 1.2.0 より古いセッション {len(old)}（{names}）には送れません"
                 "（/plugin で jui-viz を更新し、そのセッションを起動し直す）")
    if any(s.get("launch") == "channels" for s in able):
        text += "。--channels で起動したセッションは、managed settings の allowedChannelPlugins に jui-viz が無ければ届きません"
    text += f"。届く起動: {launch.HOW_TO_START}"
    return text


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
