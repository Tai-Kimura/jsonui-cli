"""The ``jui viz`` HTTP + WebSocket server (aiohttp, 127.0.0.1 only).

Routes (design: dev-guide, 05 §3):
  GET  /            the page, with the per-start token in <meta name="jui-viz-token">
  GET  /debug       the plain check page (P1–P2)
  GET  /health      {ok, version, pid, home}; no token, nothing secret (home: the runtime folder, so
                    `jui viz stop` can tell a server whose files were lost from one that is someone else's)
  GET  /app.js      the page's script, concatenated by ``bundle.build`` (P3)
  GET  /<static>    files under web/ (read with importlib.resources)
  GET  /ws          browser WebSocket: hello → auth (within 2 s) → snapshot → pushes
  POST /hook        hook payloads from forward.py (token; no Origin; 2 MB)
  GET  /api/snapshot  the whole state (token)
  POST /api/prompt    a prompt typed in the page for one session (prompt_checks: the page's own origin only)
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

from . import paths, security
from .config import VizConfig
from .state import VizState, now_ms

MAX_HOOK_BODY = 2_000_000
USAGE_MAX_BODY = 64_000
#: POST /api/prompt: the whole request body, JSON included (the requester's ruling, 10-19: "例: 8 KB").
PROMPT_MAX_BODY = 8_192
AUTH_TIMEOUT_SEC = 2.0
POLL_SEC = 25.0
PRESENCE_MS = 12_000
PRESENCE_POLL_SEC = 0.5
PROTOCOL = 1
TOKEN_PLACEHOLDER = "__JUI_VIZ_TOKEN__"
_PUSH_TASK = web.AppKey("push_task", asyncio.Task)

# Static files the page may ask for, in folders whose names may hold a dot
# after the first character (vendor/three-0.160.0/). A name starting with a
# dot — "..", ".hidden" — or other characters is refused before it reaches
# the resource reader.
_STATIC_PATH = re.compile(r"^(?:[A-Za-z0-9_-][A-Za-z0-9_.-]*/)*[A-Za-z0-9_-][A-Za-z0-9_.-]*$")
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
    # The World (P5: channel_hello / channel_request / decide / perms), and
    # what to call after changing it.
    world: object | None = None
    publish: Callable[[], None] | None = None
    # The near weather (sources/weather.py: off by default, no connection then) and what republishes it.
    weather: object | None = None
    on_weather: Callable[[], None] | None = None
    # Called with each accepted POST /usage body (the statusLine's rate_limits, 10-18).
    on_usage: Callable[[dict], None] | None = None
    # Until when a page reported itself visible (presence), epoch ms.
    present_until: int = 0

    def browser_present(self) -> bool:
        return self.present_until > now_ms()
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
        return web.json_response({"ok": True, "version": ctx.version, "pid": os.getpid(), "home": str(paths.viz_home())})

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

    async def usage(request: web.Request) -> web.Response:
        """The plan's usage limits from statusline.py (local processes only, like /hook)."""
        refused = _check_token(request)
        if refused is not None:
            return refused
        if request.content_length is not None and request.content_length > USAGE_MAX_BODY:
            return web.Response(status=413, text="too large\n")
        try:
            payload = json.loads(await request.read())
        except (ValueError, web.HTTPRequestEntityTooLarge):
            return web.Response(status=400, text="not json\n")
        if ctx.on_usage is not None and isinstance(payload, dict):
            ctx.on_usage(payload)
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
            if not ctx.sockets:
                ctx.present_until = 0  # the last page went away: nobody answers in the browser
        return sock

    async def _json_body(request: web.Request) -> dict | None:
        try:
            data = await request.json()
        except (ValueError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None

    async def hook_decide(request: web.Request) -> web.Response:
        """The synchronous PermissionRequest hook (forward.py --decide): wait up to
        decideWaitSec for the browser's answer. No visible page: answer at once
        with nothing, so the terminal dialog is never delayed for no one."""
        refused = _check_token(request)
        if refused is not None:
            return refused
        body = await _json_body(request)
        if body is None or ctx.world is None:
            return web.Response(status=400, text="bad request\n")
        card = ctx.world.hook_decide(body, now_ms())
        if ctx.publish:
            ctx.publish()
        if card is None or card["status"] != "pending" or not ctx.browser_present():
            return web.json_response({})
        future = asyncio.get_running_loop().create_future()
        ctx.world.hook_waiting(card, future)  # through World: it marks the perms slice to send
        if ctx.publish:
            ctx.publish()
        # Wait for the answer, but give up as soon as no page is visible any
        # more: a page closed mid-wait left the hook (and the terminal's
        # answer) waiting the full decideWaitSec (independent review, 10-18).
        answer = {}
        deadline = asyncio.get_running_loop().time() + ctx.config.decideWaitSec
        try:
            while True:
                left = deadline - asyncio.get_running_loop().time()
                if left <= 0 or not ctx.browser_present():
                    break
                try:
                    answer = await asyncio.wait_for(asyncio.shield(future), min(left, PRESENCE_POLL_SEC))
                    break
                except asyncio.TimeoutError:
                    continue
        finally:
            if card.get("_future") is future:
                ctx.world.hook_gave_up(card)
                if ctx.publish:
                    ctx.publish()
        return web.json_response(answer)

    app.router.add_post("/hook/decide", hook_decide)

    async def hook_ask(request: web.Request) -> web.Response:
        """The synchronous PreToolUse hook of AskUserQuestion (forward.py --ask), as /hook/decide: wait up to
        askWaitSec for the browser's answer while a page is visible; no visible page, or a question that cannot
        be shown in full: answer at once with nothing, so the terminal's question is never held for no one.
        While this waits the terminal shows no question (measured 10-18): the wait is askWaitSec, renewed by the
        page's question.hold while someone answers, up to askMaxSec (questions.py)."""
        refused = _check_token(request)
        if refused is not None:
            return refused
        body = await _json_body(request)
        if body is None or ctx.world is None:
            return web.Response(status=400, text="bad request\n")
        card = ctx.world.hook_ask(body, now_ms())
        if ctx.publish:
            ctx.publish()
        if card is None or card["status"] != "pending" or card["tooLongToShow"] or not ctx.browser_present():
            return web.json_response({})
        future = asyncio.get_running_loop().create_future()
        start = now_ms()
        ctx.world.question_waiting(card, future, start + int(ctx.config.askWaitSec * 1000), start + int(ctx.config.askMaxSec * 1000))
        if ctx.publish:
            ctx.publish()
        answer = {}
        try:
            while True:
                left = (card.get("waitUntil", 0) - now_ms()) / 1000   # holds from the page move it
                if left <= 0 or not ctx.browser_present():
                    break
                try:
                    answer = await asyncio.wait_for(asyncio.shield(future), min(left, PRESENCE_POLL_SEC))
                    break
                except asyncio.TimeoutError:
                    continue
        finally:
            if card.get("_future") is future:
                ctx.world.question_gave_up(card)
                if ctx.publish:
                    ctx.publish()
        return web.json_response(answer)

    app.router.add_post("/hook/ask", hook_ask)

    async def channel_hello(request: web.Request) -> web.Response:
        refused = _check_token(request)
        if refused is not None:
            return refused
        body = await _json_body(request)
        if body is None or ctx.world is None:
            return web.Response(status=400, text="bad request\n")
        channel_id = ctx.world.channel_hello(body.get("ppid"), body.get("cwd"), body.get("sessionId"), now_ms(), body.get("accepts"))
        if ctx.publish:
            ctx.publish()
        return web.json_response({"channelId": channel_id})

    async def channel_request(request: web.Request) -> web.Response:
        refused = _check_token(request)
        if refused is not None:
            return refused
        body = await _json_body(request)
        if body is None or ctx.world is None or not isinstance(body.get("channelId"), str):
            return web.Response(status=400, text="bad request\n")
        fields = {k: body.get(k) for k in ("request_id", "tool_name", "description", "input_preview")}
        if not ctx.world.channel_request(body["channelId"], fields, now_ms()):
            return web.Response(status=404, text="unknown channel\n")
        if ctx.publish:
            ctx.publish()
        return web.Response(status=204)

    async def channel_poll(request: web.Request) -> web.Response:
        refused = _check_token(request)
        if refused is not None:
            return refused
        channel_id = request.query.get("channelId", "")
        if ctx.world is None:
            return web.Response(status=400, text="bad request\n")
        deadline = asyncio.get_running_loop().time() + POLL_SEC
        while True:
            verdicts = ctx.world.perms.take_verdicts(channel_id, now_ms())
            if verdicts is None:
                return web.Response(status=404, text="unknown channel\n")
            prompts = [{"text": p["text"]} for p in ctx.world.perms.take_prompts(channel_id)]
            if verdicts or prompts or asyncio.get_running_loop().time() >= deadline:
                return web.json_response({"verdicts": verdicts, "prompts": prompts})
            await asyncio.sleep(0.1)

    async def api_prompt(request: web.Request) -> web.Response:
        """A prompt typed in the page's 応答の履歴 tab, for one session (requester's ruling, 10-19: "別端末からは送れなくて
        いいよ"). Every check in prompt_checks must pass; then World.send_prompt queues it for that session's channel."""
        refused = prompt_checks(request, ctx)
        if refused is not None:
            log(f"拒否: /api/prompt（{refused.text.strip()}）")
            return refused
        raw = b""
        while len(raw) <= PROMPT_MAX_BODY:   # a chunked body has no Content-Length: stop reading past the cap
            chunk = await request.content.read(PROMPT_MAX_BODY + 1 - len(raw))
            if not chunk:
                break
            raw += chunk
        if len(raw) > PROMPT_MAX_BODY:
            return web.Response(status=413, text="too large\n")
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return web.Response(status=400, text="not json\n")
        sid = body.get("sessionId") if isinstance(body, dict) else None
        text = body.get("text") if isinstance(body, dict) else None
        if not isinstance(sid, str) or not sid or not isinstance(text, str) or not text.strip():
            return web.Response(status=400, text="sessionId and text are required\n")
        if ctx.world is None:
            return web.Response(status=503, text="no world\n")
        refused_by = ctx.world.send_prompt(sid, text, now_ms())
        if refused_by is not None:
            return web.Response(status=refused_by[0], text=refused_by[1] + "\n")
        if ctx.publish:
            ctx.publish()
        return web.json_response({"ok": True})

    # Before the static catch-all: every method reaches the handler, which answers 405 to all but POST.
    app.router.add_route("*", "/api/prompt", api_prompt)
    app.router.add_post("/channel/hello", channel_hello)
    app.router.add_post("/channel/request", channel_request)
    app.router.add_get("/channel/poll", channel_poll)
    app.router.add_get("/", index)
    app.router.add_get("/debug", debug)
    app.router.add_get("/health", health)
    app.router.add_get("/app.js", app_js)
    app.router.add_get("/ws", ws)
    app.router.add_post("/hook", hook)
    app.router.add_post("/usage", usage)
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


def prompt_checks(request: web.Request, ctx: ServerContext) -> web.Response | None:
    """The checks of POST /api/prompt, each on its own (the requester's ruling, 10-19; none may be dropped):

      * POST only (405). The page has no other way to send, and a GET could be made by an <img> on any site.
      * Host exactly ``127.0.0.1:<port>`` (403). The middleware already refuses foreign names (DNS rebinding) with
        421; this route also refuses ``localhost:<port>``: ``jui viz open`` / ``start`` give the page as
        http://127.0.0.1:<port>/, so that is the only origin the page has, and one spelling is one thing to check.
      * Origin exactly ``http://127.0.0.1:<port>`` (403), and present: a browser sends it on every POST, so a
        request without one is not the page (CSRF from another site carries that site's origin).
      * X-Jui-Viz-Token, the per-start token from the served page (401).
      * Content-Type application/json (415): another site's form can only post the three "simple" types without a
        preflight, which this route never answers with CORS headers.
      * a declared body over PROMPT_MAX_BODY (413); the read in the handler stops at PROMPT_MAX_BODY + 1 bytes too.
    The server binds 127.0.0.1 only and has no option to bind anything else (viz_cmd._serve), so no other machine
    reaches it. What it does not stop: another process of this user (security.py says why)."""
    if request.method != "POST":
        return web.Response(status=405, text="POST only\n", headers={"Allow": "POST"})
    own = f"127.0.0.1:{ctx.port}"
    if request.headers.get("Host") != own:
        return web.Response(status=403, text="host must be the page's own\n")
    if request.headers.get("Origin") != f"http://{own}":
        return web.Response(status=403, text="origin must be the page's own\n")
    if not security.token_ok(request.headers.get(security.TOKEN_HEADER), ctx.token):
        return web.Response(status=401, text="unauthorized\n")
    if request.content_type != "application/json":
        return web.Response(status=415, text="application/json only\n")
    if request.content_length is not None and request.content_length > PROMPT_MAX_BODY:
        return web.Response(status=413, text="too large\n")
    return None


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
    elif kind == "history.get":
        # Only the robot whose 応答の履歴 tab is open, only when asked: never a slice, so never in a snapshot,
        # the event log or an export (sources/history.py).
        agent_id = message.get("agentId")
        got = ctx.world.history(agent_id) if ctx.world is not None and isinstance(agent_id, str) else None
        if got is None:
            await sock.send_json({"type": "ack", "reqId": req_id, "ok": False, "error": "no transcript for this robot"})
            return
        await sock.send_json({"type": "history", "reqId": req_id, "agentId": agent_id, "items": got["items"],
                              "bytes": got["bytes"], "more": got["more"]})
    elif kind == "perm.decide":
        perm_id, behavior = message.get("permId"), message.get("behavior")
        if ctx.world is None or not isinstance(perm_id, str) or not isinstance(behavior, str):
            await sock.send_json({"type": "ack", "reqId": req_id, "ok": False, "error": "permId and behavior are required"})
            return
        error = ctx.world.decide(perm_id, behavior, now_ms(), message.get("always"), message.get("reason"))
        if ctx.publish:
            ctx.publish()
        reply = {"type": "ack", "reqId": req_id, "ok": error is None}
        if error:
            reply["error"] = error
        await sock.send_json(reply)
    elif kind == "question.answer":
        card_id, picks = message.get("questionId"), message.get("answers")
        if ctx.world is None or not isinstance(card_id, str) or not isinstance(picks, dict):
            await sock.send_json({"type": "ack", "reqId": req_id, "ok": False, "error": "questionId and answers are required"})
            return
        error = ctx.world.answer_question(card_id, picks, now_ms())
        if ctx.publish:
            ctx.publish()
        reply = {"type": "ack", "reqId": req_id, "ok": error is None}
        if error:
            reply["error"] = error
        await sock.send_json(reply)
    elif kind in ("question.hold", "question.release"):
        card_id = message.get("questionId")
        if ctx.world is None or not isinstance(card_id, str):
            await sock.send_json({"type": "ack", "reqId": req_id, "ok": False, "error": "questionId is required"})
            return
        error = (ctx.world.hold_question(card_id, now_ms(), int(ctx.config.askWaitSec * 1000)) if kind == "question.hold"
                 else ctx.world.release_question(card_id, now_ms()))
        if ctx.publish:
            ctx.publish()
        reply = {"type": "ack", "reqId": req_id, "ok": error is None}
        if error:
            reply["error"] = error
        await sock.send_json(reply)
    elif kind == "weather.set":
        # The page's switch (10-18): on with the position it got from the browser (rounded there; rounded again in
        # sources/weather.py, so an unrounded one is never stored), or off (the position removed).
        if ctx.weather is None:
            await sock.send_json({"type": "ack", "reqId": req_id, "ok": False, "error": "天気はこのサーバーでは使えません"})
            return
        try:
            ctx.weather.set(message.get("on") is True, message.get("lat"), message.get("lon"))
        except (ValueError, OSError) as exc:
            await sock.send_json({"type": "ack", "reqId": req_id, "ok": False, "error": str(exc)})
            return
        if ctx.on_weather:
            ctx.on_weather()
        await sock.send_json({"type": "ack", "reqId": req_id, "ok": True})
    elif kind == "presence":
        # A visible page answers for 12 s (it reports every 5 s); hidden: at once not.
        ctx.present_until = now_ms() + PRESENCE_MS if message.get("visible") is True else 0
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
