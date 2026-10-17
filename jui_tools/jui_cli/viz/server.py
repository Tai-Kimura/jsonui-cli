"""The ``jui viz`` HTTP + WebSocket server (aiohttp, 127.0.0.1 only).

Routes (design: dev-guide, 05 §3):
  GET  /            the page, with the per-start token in <meta name="jui-viz-token">
  GET  /debug       the plain check page (P1–P2)
  GET  /health      {ok, version, pid}; no token, nothing secret
  GET  /app.js      the page's script, concatenated by ``bundle.build`` (P3)
  GET  /<static>    files under web/ (read with importlib.resources)
  GET  /ws          browser WebSocket: hello → auth (within 2 s) → snapshot → pushes
  POST /hook        hook payloads from forward.py (token; no Origin; 2 MB)
  GET  /api/snapshot  the whole state (token)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from importlib import resources
from typing import Awaitable, Callable

from aiohttp import WSMsgType, web

from . import security
from .config import VizConfig
from .state import VizState, now_ms

MAX_HOOK_BODY = 2_000_000
AUTH_TIMEOUT_SEC = 2.0
PROTOCOL = 1
TOKEN_PLACEHOLDER = "__JUI_VIZ_TOKEN__"
_PUSH_TASK = web.AppKey("push_task", asyncio.Task)

# Static files the page may ask for: a flat name or one folder level deep
# (fonts/, vendor/...). Anything with "..", a leading dot or other
# characters is refused before it reaches the resource reader.
_STATIC_PATH = re.compile(r"^(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+$")
_CONTENT_TYPES = {
    ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
    ".json": "application/json", ".woff2": "font/woff2", ".woff": "font/woff",
    ".svg": "image/svg+xml", ".png": "image/png", ".md": "text/plain", ".txt": "text/plain",
}


class _OneLine(logging.Handler):
    """aiohttp's own errors (a malformed request, a handler crash) as one line,
    without the traceback: any local process could otherwise grow the log at will."""

    def emit(self, record: logging.LogRecord) -> None:
        exc = record.exc_info[1] if record.exc_info else None
        reason = type(exc).__name__ if exc else record.getMessage().splitlines()[0][:120]
        log(f"拒否: 不正なリクエスト（{reason}）")


def quiet_aiohttp_logs() -> None:
    for name in ("aiohttp.server", "aiohttp.web", "aiohttp.access", "aiohttp.internal", "aiohttp.websocket"):
        logger = logging.getLogger(name)
        logger.handlers = [_OneLine()]
        logger.propagate = False
        logger.setLevel(logging.WARNING)


def log(message: str) -> None:
    """One line on stderr. Never pass hook bodies or the token here."""
    print(f"jui viz: {message}", file=sys.stderr, flush=True)


def web_root():
    return resources.files("jui_cli.viz") / "web"


def _read_web(name: str) -> bytes | None:
    node = web_root()
    for part in name.split("/"):
        node = node / part
    try:
        if not node.is_file():
            return None
        return node.read_bytes()
    except (OSError, ValueError):
        return None


def _importmap_hashes(html: str) -> list[str]:
    """CSP hashes for the inline importmap(s) the page embeds."""
    blocks = re.findall(r'<script type="importmap">(.*?)</script>', html, flags=re.S)
    return [security.script_hash(block) for block in blocks]


@dataclass
class ServerContext:
    config: VizConfig
    port: int
    token: str
    version: str = ""
    state: VizState = field(default_factory=VizState)
    # Called with each accepted hook payload (P2 plugs ingest in here).
    on_hook: Callable[[dict], Awaitable[None] | None] | None = None
    # spec id -> the sheet's doc (P4), or None when the spec is unknown.
    sheet: Callable[[str], dict | None] | None = None
    # Each authed socket and the (rev, seq) it has already been sent, so a
    # change made before it connected is not delivered twice.
    sockets: dict = field(default_factory=dict)


def _page_html(ctx: ServerContext) -> str | None:
    """index.html once the page exists (P3), the check page until then."""
    for name in ("index.html", "debug.html"):
        raw = _read_web(name)
        if raw is not None:
            return raw.decode("utf-8")
    return None


def make_app(ctx: ServerContext) -> web.Application:
    page = _page_html(ctx) or ""
    hashes = _importmap_hashes(page)
    app = web.Application(
        middlewares=[security.make_middleware(ctx.port, hashes)],
        client_max_size=MAX_HOOK_BODY,
    )
    security.install_headers(app, ctx.port, hashes)

    def _with_token(html: str) -> web.Response:
        body = html.replace(TOKEN_PLACEHOLDER, ctx.token)
        response = web.Response(text=body, content_type="text/html")
        response.headers["Cache-Control"] = "no-store"
        return response

    async def index(request: web.Request) -> web.Response:
        html = _page_html(ctx)
        if html is None:
            return web.Response(status=500, text="web/ is missing from this install\n")
        return _with_token(html)

    async def debug(request: web.Request) -> web.Response:
        raw = _read_web("debug.html")
        if raw is None:
            raise web.HTTPNotFound()
        return _with_token(raw.decode("utf-8"))

    async def health(request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "version": ctx.version, "pid": os.getpid()})

    async def app_js(request: web.Request) -> web.Response:
        from . import bundle  # concatenates web/js/ in a fixed order

        mode = request.query.get("mode", "live")
        if mode not in ("live", "demo"):
            raise web.HTTPBadRequest(text="mode must be live or demo\n")
        try:
            source = bundle.build(mode)
        except LookupError:
            raise web.HTTPNotFound()
        response = web.Response(text=source, content_type="text/javascript")
        response.headers["Cache-Control"] = "no-store"
        return response

    async def static(request: web.Request) -> web.Response:
        name = request.match_info["path"]
        if not _STATIC_PATH.match(name) or name.endswith(".html"):
            raise web.HTTPNotFound()
        if any(part.startswith(".") for part in name.split("/")):
            raise web.HTTPNotFound()
        raw = _read_web(name)
        if raw is None:
            raise web.HTTPNotFound()
        ext = os.path.splitext(name)[1].lower()
        return web.Response(body=raw, content_type=_CONTENT_TYPES.get(ext, "application/octet-stream"))

    def _check_token(request: web.Request) -> web.Response | None:
        if request.headers.get("Origin"):
            # These routes are for local processes, never a browser page.
            return web.Response(status=403, text="forbidden\n")
        if not security.token_ok(request.headers.get(security.TOKEN_HEADER), ctx.token):
            return web.Response(status=401, text="unauthorized\n")
        return None

    async def hook(request: web.Request) -> web.Response:
        refused = _check_token(request)
        if refused is not None:
            return refused
        if request.content_length is not None and request.content_length > MAX_HOOK_BODY:
            return web.Response(status=413, text="too large\n")
        try:
            raw = await request.read()
        except web.HTTPRequestEntityTooLarge:
            return web.Response(status=413, text="too large\n")
        try:
            payload = json.loads(raw)
        except ValueError:
            return web.Response(status=400, text="not json\n")
        if not isinstance(payload, dict):
            return web.Response(status=400, text="not an object\n")
        if ctx.on_hook is not None:
            asyncio.get_running_loop().call_soon(_dispatch_hook, ctx, payload)
        return web.Response(status=204)

    async def api_snapshot(request: web.Request) -> web.Response:
        refused = _check_token(request)
        if refused is not None:
            return refused
        return web.json_response(ctx.state.snapshot())

    async def ws(request: web.Request) -> web.StreamResponse:
        if not security.origin_ok(request.headers.get("Origin"), ctx.port):
            log("拒否: WebSocket の Origin が違います")
            return web.Response(status=403, text="forbidden\n")
        sock = web.WebSocketResponse(heartbeat=20)
        await sock.prepare(request)
        await sock.send_json({"type": "hello", "protocol": PROTOCOL, "serverVersion": ctx.version})
        try:
            first = await sock.receive(timeout=AUTH_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            await sock.close(code=4401, message=b"auth timeout")
            return sock
        message = _parse(first)
        if message is None or message.get("type") != "auth" or not security.token_ok(message.get("token"), ctx.token):
            log("拒否: WebSocket の認証に失敗しました")
            await sock.close(code=4401, message=b"auth failed")
            return sock
        snapshot = ctx.state.snapshot()
        recent = ctx.state.recent_events(200)
        ctx.sockets[sock] = {"rev": snapshot["rev"], "seq": ctx.state.last_seq}
        await sock.send_json({"type": "snapshot", **snapshot})
        await sock.send_json({"type": "events", "items": recent})
        try:
            async for msg in sock:
                request_message = _parse(msg)
                if request_message is None:
                    continue
                await _handle_browser_message(ctx, sock, request_message)
        finally:
            ctx.sockets.pop(sock, None)
        return sock

    app.router.add_get("/", index)
    app.router.add_get("/debug", debug)
    app.router.add_get("/health", health)
    app.router.add_get("/app.js", app_js)
    app.router.add_get("/ws", ws)
    app.router.add_post("/hook", hook)
    app.router.add_get("/api/snapshot", api_snapshot)
    app.router.add_get("/{path:.+}", static)

    async def start_push(app: web.Application) -> None:
        app[_PUSH_TASK] = asyncio.create_task(push_loop(ctx))

    async def stop_push(app: web.Application) -> None:
        task = app.get(_PUSH_TASK)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        for sock in list(ctx.sockets):
            await sock.close(code=1001, message=b"server stopping")

    app.on_startup.append(start_push)
    app.on_shutdown.append(stop_push)
    return app


def _dispatch_hook(ctx: ServerContext, payload: dict) -> None:
    try:
        result = ctx.on_hook(payload)  # type: ignore[misc]
        if asyncio.iscoroutine(result):
            asyncio.ensure_future(result)
    except Exception as exc:  # noqa: BLE001 - one bad payload must not stop the server
        log(f"フックの処理に失敗しました（{type(exc).__name__}）")


def _parse(msg) -> dict | None:
    if msg.type != WSMsgType.TEXT:
        return None
    try:
        data = json.loads(msg.data)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


async def _handle_browser_message(ctx: ServerContext, sock, message: dict) -> None:
    kind = message.get("type")
    req_id = message.get("reqId")
    if kind == "snapshot.get":
        await sock.send_json({"type": "snapshot", **ctx.state.snapshot()})
        await sock.send_json({"type": "ack", "reqId": req_id, "ok": True})
    elif kind == "events.more":
        before = message.get("beforeSeq")
        limit = message.get("limit")
        if not isinstance(before, int) or not isinstance(limit, int) or limit <= 0:
            await sock.send_json({"type": "ack", "reqId": req_id, "ok": False, "error": "beforeSeq and limit must be integers"})
            return
        older = [e for e in ctx.state.events if e["seq"] < before][-min(limit, 500):]
        await sock.send_json({"type": "events", "items": older, "older": True})
        await sock.send_json({"type": "ack", "reqId": req_id, "ok": True})
    elif kind == "spec.sheet":
        spec_id = message.get("specId")
        cards = ctx.sheet(spec_id) if isinstance(spec_id, str) and ctx.sheet is not None else None
        if cards is None:
            await sock.send_json({"type": "ack", "reqId": req_id, "ok": False, "error": "unknown spec"})
            return
        await sock.send_json({"type": "sheet", "reqId": req_id, "specId": spec_id, "cards": cards})
    elif kind == "presence":
        return  # used from P6
    elif req_id is not None:
        await sock.send_json({"type": "ack", "reqId": req_id, "ok": False, "error": f"unknown type {kind!r}"})


async def push_loop(ctx: ServerContext) -> None:
    """Every pushIntervalMs, send the slices and events that changed. Quiet otherwise."""
    interval = max(ctx.config.pushIntervalMs, 20) / 1000
    while True:
        await asyncio.sleep(interval)
        changed, events = ctx.state.take_changes()
        if changed is None and not events:
            continue
        for sock, sent in list(ctx.sockets.items()):
            try:
                if changed is not None and changed["rev"] > sent["rev"]:
                    await sock.send_json({"type": "slices", **changed})
                    sent["rev"] = changed["rev"]
                fresh = [e for e in events if e["seq"] > sent["seq"]]
                if fresh:
                    await sock.send_json({"type": "events", "items": fresh})
                    sent["seq"] = fresh[-1]["seq"]
            except (ConnectionResetError, RuntimeError):
                ctx.sockets.pop(sock, None)


def server_slice(ctx: ServerContext, started_at: int, sources: dict | None = None) -> dict:
    return {
        "version": ctx.version,
        "startedAt": started_at,
        "pid": os.getpid(),
        "port": ctx.port,
        "sources": sources or {},
        "at": now_ms(),
    }
