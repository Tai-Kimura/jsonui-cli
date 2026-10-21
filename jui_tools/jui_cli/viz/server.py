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
  POST /api/attach    one file for a prompt, kept in <viz home>/uploads/<session>/ (the same checks, octet-stream)
  POST /api/attach-remove  an attachment taken off before sending (the same checks)
  POST /api/denial    a card of a call stopped by auto mode: approve (its fixed words as a prompt) or dismiss (the same checks)
  POST /api/attach-image  one attached image for the history's thumbnail and large view, by session and id (the same checks)
  POST /api/history-image  one picture of a robot's 応答の履歴, named by the robot and its place (the same checks)
  POST /api/history-file  one picture a session sent with SendUserFile, named by the robot, the call and the file (the same checks)
  POST /api/reveal-file  show one file of the history in Finder (open -R): a SendUserFile file or an attachment, named as above (the same checks)
  POST /api/data-docs  a JsonUI room's API and DB specifications for its data server, named by the room (the same checks)
  POST /api/session/end  退勤: SIGTERM to one terminal session's claude (prompt_checks, then clockout.py's checks)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass, field
from importlib import resources
from typing import Awaitable, Callable

from aiohttp import WSMsgType, web

from . import attachments, callcmd, clockout, i18n, infra_cost, infra_docs, paths, security
from .config import ASK_UNTIL_ANSWERED_SEC, ASK_WAIT_CHOICES, VizConfig, ask_hook_wait_sec, save_setting
from .state import VizState, now_ms

MAX_HOOK_BODY = 2_000_000
USAGE_MAX_BODY = 64_000
#: POST /api/prompt: the whole request body, JSON included (the requester's ruling, 10-19: "例: 8 KB").
PROMPT_MAX_BODY = 8_192
#: POST /api/session/end: {"sessionId", "agentId"} and nothing more.
END_MAX_BODY = 1_024
NOTIFY_MAX_BODY = 256     # /api/notify-presence and /api/ask-wait: one small object
CALL_MAX_BODY = 32_768   # the call button: a role text of callcmd.ROLE_MAX characters, JSON-escaped
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
        log(f"refused: a bad request ({reason})")


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
    # The question window changed (POST /api/ask-wait): serve rewrites server.json's askHookWaitSec, which
    # forward.py --ask reads to know how long to wait (ticket 2026-10-20 question-window-over-5-min).
    on_settings: Callable[[], None] | None = None
    # Until when a page reported itself visible (presence), epoch ms.
    present_until: int = 0
    # Until when a page said its question notifications are on (POST /api/notify-presence, 2.3.6), epoch ms.
    notify_until: int = 0
    # The talk view (talk.TalkHub): talk.* requests, its increments and the chat icon's badges.
    talk: object | None = None

    def browser_present(self) -> bool:
        return self.present_until > now_ms()

    def notify_present(self) -> bool:
        return self.notify_until > now_ms()

    def page_can_answer(self) -> bool:
        """A page that can answer a question now: one visible, or one whose question notifications are on (it shows
        the question on screen even when hidden, and someone comes from it) — the orchestrator's ruling 10-19, both time-limited."""
        return self.browser_present() or self.notify_present()
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


#: "until answered" (askWaitSec 0): a time no hook reaches (the card's ターミナルで答える, every page gone and the session
#: ending still end the wait)
NEVER_MS = 2 ** 53 - 1


def ask_window(config: VizConfig, start: int) -> tuple[int, int]:
    """(until, latest) of a question's wait: askWaitSec from now, holds from the page up to askMaxSec in all — or up
    to askWaitSec when that is longer (a 10 or 30 minute choice is not cut at 5); 0: until answered."""
    wait = float(config.askWaitSec)
    if wait <= 0:
        return NEVER_MS, NEVER_MS
    return start + int(wait * 1000), start + int(max(config.askMaxSec, wait) * 1000)


def _hook_wait_sec(request: web.Request, config: VizConfig) -> float:
    """How long the --ask hook that sent this waits: its X-Jui-Viz-Wait-Sec, else askMaxSec (an older forward.py
    waits server.json's askMaxSec + 5)."""
    try:
        said = float(request.headers.get("X-Jui-Viz-Wait-Sec", ""))
    except ValueError:
        said = 0.0
    return said if said > 0 and said == said and said != float("inf") else float(config.askMaxSec)


def ask_wait_text(sec: float) -> str:
    """質問は viz で <これ> 待つ: 20 秒, 3 分, 答えるまで."""
    if sec <= 0:
        return i18n.tl("srv.ask.until_answered")
    return i18n.tl("srv.ask.sec", n=int(sec)) if sec < 60 else i18n.tl("srv.ask.min", n=f"{sec / 60:g}")


def settings_slice(config: VizConfig) -> dict:
    """What the page shows and changes (2.3.6): the question window, its choices, the notifications' presence."""
    return {"askWaitSec": config.askWaitSec, "askWaitText": ask_wait_text(config.askWaitSec), "askWaitChoices": list(ASK_WAIT_CHOICES),
            "askUntilAnsweredSec": ASK_UNTIL_ANSWERED_SEC,
            "notifyPresenceSec": config.notifyPresenceSec}


async def _send_all(ctx: "ServerContext", message: dict) -> None:
    """One message to every page that is connected (authed sockets only)."""
    for sock in list(ctx.sockets):
        try:
            await sock.send_json(message)
        except (ConnectionResetError, RuntimeError):
            ctx.sockets.pop(sock, None)


def make_app(ctx: ServerContext) -> web.Application:
    page = _page_html(ctx) or ""
    hashes = _importmap_hashes(page)
    app = web.Application(
        middlewares=[security.make_middleware(ctx.port, hashes, on_refused=lambda request, response: (
            _clock_log(ctx, {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "remote": request.remote}, response)
            if request.path == "/api/session/end" else None))],
        client_max_size=MAX_HOOK_BODY,
    )
    security.install_headers(app, ctx.port, hashes)

    def _with_token(html: str) -> web.Response:
        body = i18n.page_html(html.replace(TOKEN_PLACEHOLDER, ctx.token), i18n.active())
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
            log("refused: the WebSocket's Origin is not this page's")
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
            log("refused: the WebSocket's authentication failed")
            await sock.close(code=4401, message=b"auth failed")
            return sock
        snapshot = ctx.state.snapshot()
        recent = ctx.state.recent_events(200)
        ctx.sockets[sock] = {"rev": snapshot["rev"], "seq": ctx.state.last_seq}
        await sock.send_json({"type": "snapshot", **snapshot})
        await sock.send_json({"type": "events", "items": recent})
        if ctx.talk is not None:
            await sock.send_json(ctx.talk.badges_frame())
        try:
            async for msg in sock:
                request_message = _parse(msg)
                if request_message is None:
                    continue
                await _handle_browser_message(ctx, sock, request_message)
        finally:
            ctx.sockets.pop(sock, None)
            if ctx.talk is not None:
                ctx.talk.forget(sock)
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
        if card is None or card["status"] != "pending" or card["tooLongToShow"] or not ctx.page_can_answer():
            return web.json_response({})
        future = asyncio.get_running_loop().create_future()
        start = now_ms()
        until, latest = ask_window(ctx.config, start)
        # Never wait past the hook (ticket 2026-10-20 question-window-over-5-min): forward.py says how long it waits
        # (X-Jui-Viz-Wait-Sec, from server.json askHookWaitSec); a forward.py that does not say (the plugin 1.2.1 and
        # before) waits askMaxSec + 5. Past that the terminal has the question, so the card must not still wait.
        hard = start + int(min(_hook_wait_sec(request, ctx.config), ask_hook_wait_sec(ctx.config)) * 1000)
        if until != NEVER_MS or hard < start + ASK_UNTIL_ANSWERED_SEC * 1000:
            until, latest = min(until, hard), min(latest, hard)
        ctx.world.question_waiting(card, future, until, latest)
        if ctx.publish:
            ctx.publish()
        answer, reason, pinged = {}, None, 0
        try:
            while True:
                now = now_ms()
                left = min(card.get("waitUntil", 0) - now, hard - now) / 1000   # holds from the page move it
                if left <= 0:
                    reason = "timeout"
                    break
                if not ctx.page_can_answer():
                    reason = "hidden"
                    break
                if not ctx.browser_present() and now - pinged >= ctx.config.askPingSec * 1000:
                    pinged = now   # waiting on a hidden page: it says again that its notifications are on
                    await _send_all(ctx, {"type": "notify.ping"})
                try:
                    answer = await asyncio.wait_for(asyncio.shield(future), min(left, PRESENCE_POLL_SEC))
                    break
                except asyncio.TimeoutError:
                    continue
        finally:
            if card.get("_future") is future:
                ctx.world.question_gave_up(card, reason, now_ms())
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
        channel_id = ctx.world.channel_hello(body.get("ppid"), body.get("cwd"), body.get("sessionId"), now_ms(), body.get("accepts"),
                                             body.get("via"))
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

    async def api_denial(request: web.Request) -> web.Response:
        """A card of a tool call stopped by auto mode (denials.py): {"id", "do": "approve" | "dismiss"}. The checks of
        /api/prompt (prompt_checks). approve sends the card's fixed words (denials.prompt_text) to its session as a
        prompt from the page (World.approve_denial → send_prompt); the page only names the card, never the words."""
        refused = prompt_checks(request, ctx)
        if refused is not None:
            log(f"refused: /api/denial ({refused.text.strip()})")
            return refused
        body = await _capped_json(request, PROMPT_MAX_BODY)
        if isinstance(body, web.Response):
            return body
        card_id, do = body.get("id"), body.get("do")
        if not isinstance(card_id, str) or do not in ("approve", "dismiss"):
            return web.Response(status=400, text="id and do (approve or dismiss) are required\n")
        if ctx.world is None:
            return web.Response(status=503, text="no world\n")
        world_do = ctx.world.approve_denial if do == "approve" else ctx.world.dismiss_denial
        refused_by = world_do(card_id, now_ms())
        if refused_by is not None:
            return web.Response(status=refused_by[0], text=refused_by[1] + "\n")
        if ctx.publish:
            ctx.publish()
        return web.json_response({"ok": True})

    async def api_prompt(request: web.Request) -> web.Response:
        """A prompt typed in the page's 応答の履歴 tab, for one session (requester's ruling, 10-19: "別端末からは送れなくて
        いいよ"). Every check in prompt_checks must pass; then World.send_prompt queues it for that session's channel."""
        refused = prompt_checks(request, ctx)
        if refused is not None:
            log(f"refused: /api/prompt ({refused.text.strip()})")
            return refused
        body = await _capped_json(request, PROMPT_MAX_BODY)
        if isinstance(body, web.Response):
            return body
        sid = body.get("sessionId") if isinstance(body, dict) else None
        text = body.get("text") if isinstance(body, dict) else None
        ids = body.get("attachments", []) if isinstance(body, dict) else []
        if not isinstance(sid, str) or not sid or not isinstance(text, str) or (not text.strip() and not ids):
            return web.Response(status=400, text="sessionId and text are required\n")
        if ctx.world is None:
            return web.Response(status=503, text="no world\n")
        try:
            attached = ctx.world.attachments.take(sid, ids) if ids else []
        except attachments.Refused as exc:
            return web.Response(status=exc.status, text=f"{exc}\n")
        except OSError:
            return web.Response(status=404, text="no such attachment\n")
        refused_by = ctx.world.send_prompt(sid, text, now_ms(), attached)
        if refused_by is not None:
            return web.Response(status=refused_by[0], text=refused_by[1] + "\n")
        if ctx.publish:
            ctx.publish()
        return web.json_response({"ok": True})

    async def api_attach(request: web.Request) -> web.Response:
        """One file attached to a prompt (ticket 2026-10-20 prompt-attach): the bytes as application/octet-stream, the
        session in X-Jui-Viz-Session, the shown name (percent-encoded) in X-Jui-Viz-Name, a pasted image's media type
        in X-Jui-Viz-Media. The checks of /api/prompt (prompt_checks) with this route's size and type; then the
        session must be one a prompt can go to now (World.prompt_refusal). attachments.Attachments.save keeps it in
        the private folder off the event loop. Answers {id, name, media, size}; the path goes only into the prompt."""
        refused = prompt_checks(request, ctx, attachments.FILE_MAX, "application/octet-stream")
        if refused is not None:
            log(f"refused: /api/attach ({refused.text.strip()})")
            return refused
        sid = request.headers.get("X-Jui-Viz-Session", "")
        name = urllib.parse.unquote(request.headers.get("X-Jui-Viz-Name", ""), errors="replace")
        media = request.headers.get("X-Jui-Viz-Media", "")
        raw = b""
        while len(raw) <= attachments.FILE_MAX:   # a chunked body has no Content-Length: stop reading past the cap
            chunk = await request.content.read(attachments.FILE_MAX + 1 - len(raw))
            if not chunk:
                break
            raw += chunk
        if len(raw) > attachments.FILE_MAX:
            return web.Response(status=413, text="file too large\n")
        if ctx.world is None:
            return web.Response(status=503, text="no world\n")
        refused_by = ctx.world.prompt_refusal(sid)
        if refused_by is not None:
            return web.Response(status=refused_by[0], text=refused_by[1] + "\n")
        try:
            record = await asyncio.get_running_loop().run_in_executor(
                None, ctx.world.attachments.save, sid, name, media, raw)
        except attachments.Refused as exc:
            return web.Response(status=exc.status, text=f"{exc}\n")
        except OSError as exc:
            log(f"an attachment cannot be saved: {type(exc).__name__}")
            return web.Response(status=409, text="the attachment could not be kept\n")
        return web.json_response({k: record[k] for k in ("id", "name", "media", "size")})

    async def api_attach_image(request: web.Request) -> web.Response:
        """One attached image, for the history's thumbnail and its large view (ticket 2026-10-20-jui-viz-attachment-thumb-
        opens-large): {"sessionId", "id", "ext"} from the prompt's line, never a path. The checks of /api/prompt;
        attachments.Attachments.read_image reads it off the event loop. A file that is gone is not an error of the
        request: {"gone": true} with 200 (a 404 is logged by the browser as a console error on every look). The bytes
        go back with their own media type, nosniff and no-store, as /api/history-image's."""
        refused = prompt_checks(request, ctx)
        if refused is not None:
            log(f"refused: /api/attach-image ({refused.text.strip()})")
            return refused
        body = await _capped_json(request, PROMPT_MAX_BODY)
        if isinstance(body, web.Response):
            return body
        sid, fid, ext = body.get("sessionId"), body.get("id"), body.get("ext")
        if not isinstance(sid, str) or not isinstance(fid, str) or not isinstance(ext, str):
            return web.Response(status=400, text="sessionId, id and ext are required\n")
        if ctx.world is None:
            return web.Response(status=503, text="no world\n")
        try:
            media, data = await asyncio.get_running_loop().run_in_executor(None, ctx.world.attachments.read_image, sid, fid, ext)
        except attachments.Refused as exc:
            if exc.status == 404:
                return web.json_response({"gone": True}, headers={"Cache-Control": "no-store"})
            return web.Response(status=exc.status, text=f"{exc}\n")
        return web.Response(body=data, content_type=media,
                            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Content-Disposition": "inline"})

    async def api_attach_remove(request: web.Request) -> web.Response:
        """× on an attachment not sent yet: {sessionId, id}; the checks of /api/prompt."""
        refused = prompt_checks(request, ctx)
        if refused is not None:
            return refused
        body = await _capped_json(request, PROMPT_MAX_BODY)
        if isinstance(body, web.Response):
            return body
        if ctx.world is None:
            return web.Response(status=503, text="no world\n")
        sid, fid = body.get("sessionId"), body.get("id")
        if not isinstance(sid, str) or not isinstance(fid, str):
            return web.Response(status=400, text="sessionId and id are required\n")
        gone = await asyncio.get_running_loop().run_in_executor(None, ctx.world.attachments.remove, sid, fid)
        return web.json_response({"ok": gone})

    async def api_call_command(request: web.Request) -> web.Response:
        """The call button's command (2.3.5, callcmd.py): {"projectId", "name", "role"} -> {"command", "flag", "root"}.
        Nothing is run and nothing is written: the line is made here so its quoting is one piece of Python with its own
        arms (tests/test_viz_callcmd.py: zsh and bash, run and pasted). The checks of /api/prompt (prompt_checks: POST,
        the page's own Host and Origin, the token, JSON, a capped body); the folder is the server's own record of the
        project (rooms.root_of), never a path from the client; the channels flag is read from the managed settings."""
        refused = prompt_checks(request, ctx, CALL_MAX_BODY)
        if refused is not None:
            log(f"refused: /api/call-command ({refused.text.strip()})")
            return refused
        body = await _capped_json(request, CALL_MAX_BODY)
        if isinstance(body, web.Response):
            return body
        if not isinstance(body, dict) or not isinstance(body.get("projectId"), str):
            return web.Response(status=400, text="projectId is required\n")
        if ctx.world is None:
            return web.Response(status=503, text="no world\n")
        root = ctx.world.rooms.root_of(body["projectId"])
        if not root:
            return web.Response(status=404, text="no such project\n")
        name, role = body.get("name", ""), body.get("role", "")
        why = callcmd.check(name, role)
        if why:
            return web.json_response({"ok": False, "why": why}, status=400)
        flag = callcmd.channels_flag()
        return web.json_response({"ok": True, "command": callcmd.command(root, name, role, flag), "flag": flag, "root": root},
                                 headers={"Cache-Control": "no-store"})

    async def api_notify_presence(request: web.Request) -> web.Response:
        """A page whose question notifications are on says so (2.3.6, the orchestrator's ruling 10-19): {"ask": true} — the page
        sends it only when Notification.permission is granted and the question kind is on — holds for
        notifyPresenceSec; {"ask": false} ends it at once. The checks of /api/prompt (prompt_checks)."""
        refused = prompt_checks(request, ctx, NOTIFY_MAX_BODY)
        if refused is not None:
            log(f"refused: /api/notify-presence ({refused.text.strip()})")
            return refused
        body = await _capped_json(request, NOTIFY_MAX_BODY)
        if isinstance(body, web.Response):
            return body
        if not isinstance(body, dict) or not isinstance(body.get("ask"), bool):
            return web.Response(status=400, text="ask (true or false) is required\n")
        ctx.notify_until = now_ms() + int(ctx.config.notifyPresenceSec * 1000) if body["ask"] else 0
        return web.json_response({"ok": True, "forSec": ctx.config.notifyPresenceSec if body["ask"] else 0})

    async def api_ask_wait(request: web.Request) -> web.Response:
        """How long a question waits for the page (2.3.6, requester 10-19): {"sec": one of ASK_WAIT_CHOICES}, 0 =
        until answered. Saved in config.json (kept after a restart) and used from the next question on. The checks of
        /api/prompt (prompt_checks)."""
        refused = prompt_checks(request, ctx, NOTIFY_MAX_BODY)
        if refused is not None:
            log(f"refused: /api/ask-wait ({refused.text.strip()})")
            return refused
        body = await _capped_json(request, NOTIFY_MAX_BODY)
        if isinstance(body, web.Response):
            return body
        sec = body.get("sec") if isinstance(body, dict) else None
        if isinstance(sec, bool) or not isinstance(sec, (int, float)) or sec not in ASK_WAIT_CHOICES:
            return web.Response(status=400, text=f"sec must be one of {list(ASK_WAIT_CHOICES)}\n")
        try:
            save_setting("askWaitSec", sec)
        except (OSError, ValueError) as exc:
            return web.json_response({"ok": False, "why": i18n.tl("srv.config.not_saved", error=exc)}, status=500)
        ctx.config.askWaitSec = float(sec)
        if ctx.on_settings:
            ctx.on_settings()   # server.json's askHookWaitSec: forward.py --ask waits that long from the next question on
        ctx.state.set_slice("settings", settings_slice(ctx.config))
        if ctx.publish:
            ctx.publish()
        log(f"question wait: {'until answered' if ctx.config.askWaitSec <= 0 else f'{ctx.config.askWaitSec} s'}")
        return web.json_response({"ok": True, "askWaitSec": ctx.config.askWaitSec})

    async def api_history_file(request: web.Request) -> web.Response:
        """One picture a session sent with SendUserFile, for the 応答の履歴 (ticket 2026-10-20-jui-viz-history-
        senduserfile-image-no-thumb): {"agentId", "off", "n"} names the robot, the call's record and the file in it —
        never a path; the server reads only the path that call holds (sources/history.sent_file_at). The checks of
        /api/prompt. A file no longer there is {"gone": true} with 200 (a 404 is a console error on every look)."""
        refused = prompt_checks(request, ctx)
        if refused is not None:
            log(f"refused: /api/history-file ({refused.text.strip()})")
            return refused
        body = await _capped_json(request, PROMPT_MAX_BODY)
        if isinstance(body, web.Response):
            return body
        agent_id, off, n = body.get("agentId"), body.get("off"), body.get("n")
        if not isinstance(agent_id, str) or not agent_id or type(off) is not int or type(n) is not int:
            return web.Response(status=400, text="agentId, off and n are required\n")
        if ctx.world is None:
            return web.Response(status=503, text="no world\n")
        status, got = await asyncio.get_running_loop().run_in_executor(None, ctx.world.history_file, agent_id, off, n)
        if status == 404 and got == "gone":
            return web.json_response({"gone": True}, headers={"Cache-Control": "no-store"})
        if status != 200:
            return web.Response(status=status, text=f"{got}\n")
        media, data = got
        return web.Response(body=data, content_type=media,
                            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Content-Disposition": "inline"})

    async def api_reveal_file(request: web.Request) -> web.Response:
        """A file of the 応答の履歴 shown in Finder, selected in its folder's window (2.3.12, requester 10-21: 「画像以外は
        ファイル名出してリンクっぽくして、押したらfinderでそのファイル選択してウィンドウ開く」; ticket 2026-10-21-jui-viz-hist-
        tool-row-shows-no-image-when-closed). {"sent": {"agentId", "off", "n"}} — a file a SendUserFile call sent, the
        path that call holds (sources/history.sent_reveal_at) —, {"tool": {"agentId", "off", "id"}} — the file a Read /
        Edit / Write / NotebookEdit call names (sources/history.tool_file_reveal_at) — or {"attach": {"sessionId", "id",
        "ext"}} — a file sent from this page (attachments.reveal_path); never a path. The checks of /api/prompt. `open -R <path>` (no shell,
        an absolute path). A file no longer there is {"gone": true} with 200; not on macOS, 501."""
        refused = prompt_checks(request, ctx)
        if refused is not None:
            log(f"refused: /api/reveal-file ({refused.text.strip()})")
            return refused
        body = await _capped_json(request, PROMPT_MAX_BODY)
        if isinstance(body, web.Response):
            return body
        if ctx.world is None:
            return web.Response(status=503, text="no world\n")
        loop = asyncio.get_running_loop()
        sent, att = body.get("sent"), body.get("attach")
        if isinstance(sent, dict):
            agent_id, off, n = sent.get("agentId"), sent.get("off"), sent.get("n")
            if not isinstance(agent_id, str) or not agent_id or type(off) is not int or type(n) is not int:
                return web.Response(status=400, text="agentId, off and n are required\n")
            status, path = await loop.run_in_executor(None, ctx.world.history_reveal, agent_id, off, n)
        elif isinstance(body.get("tool"), dict):
            tool = body["tool"]
            agent_id, off, use_id = tool.get("agentId"), tool.get("off"), tool.get("id")
            if not isinstance(agent_id, str) or not agent_id or type(off) is not int or not isinstance(use_id, str) or not use_id:
                return web.Response(status=400, text="agentId, off and id are required\n")
            status, path = await loop.run_in_executor(None, ctx.world.history_tool_reveal, agent_id, off, use_id)
        elif isinstance(att, dict):
            sid, fid, ext = att.get("sessionId"), att.get("id"), att.get("ext")
            if not isinstance(sid, str) or not isinstance(fid, str) or not isinstance(ext, str):
                return web.Response(status=400, text="sessionId, id and ext are required\n")
            try:
                status, path = 200, await loop.run_in_executor(None, ctx.world.attachments.reveal_path, sid, fid, ext)
            except attachments.Refused as exc:
                status, path = exc.status, ("gone" if exc.status == 404 else str(exc))
        else:
            return web.Response(status=400, text="sent or attach is required\n")
        if status == 404 and path == "gone":
            return web.json_response({"gone": True}, headers={"Cache-Control": "no-store"})
        if status != 200:
            return web.Response(status=status, text=f"{path}\n")
        if sys.platform != "darwin":
            return web.Response(status=501, text="Finder is macOS's\n")
        if not os.path.isabs(path):
            return web.Response(status=403, text="not this path\n")
        ok = await _reveal(path)
        return web.json_response({"ok": ok}, headers={"Cache-Control": "no-store"})

    async def api_history_image(request: web.Request) -> web.Response:
        """One picture of the 応答の履歴 (2.3.4): {"agentId", "off", "n"} names the robot (so its transcript) and the
        picture in it (sources/history.image_at). The same checks as /api/prompt (prompt_checks: POST, the page's own
        Host and Origin, the token, JSON, a small body), and never a path from the client. Asked by the page only
        while the tab shows the picture; nothing is kept. The bytes go back with their own media type, nosniff and
        no-store; a refusal carries no picture."""
        refused = prompt_checks(request, ctx)
        if refused is not None:
            log(f"refused: /api/history-image ({refused.text.strip()})")
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
        agent_id = body.get("agentId") if isinstance(body, dict) else None
        off = body.get("off") if isinstance(body, dict) else None
        n = body.get("n") if isinstance(body, dict) else None
        if not isinstance(agent_id, str) or not agent_id or type(off) is not int or type(n) is not int:
            return web.Response(status=400, text="agentId, off and n are required\n")
        if ctx.world is None:
            return web.Response(status=503, text="no world\n")
        status, got = ctx.world.history_image(agent_id, off, n)
        if status != 200:
            return web.Response(status=status, text=f"{got}\n")
        media, data = got
        return web.Response(body=data, content_type=media,
                            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                     "Content-Disposition": "inline"})

    async def api_data_docs(request: web.Request) -> web.Response:
        """The data server's documents (2.3.5): {"projectId"} names a JsonUI room; data_docs.read gives its API and DB
        specifications, read now from the room's docs/api and docs/db (data_docs.doc_dirs: inside the room, no
        symlink or .. out of it, capped). The same checks as /api/prompt (prompt_checks), never a path from the client,
        asked only when the rack is pressed, nothing kept; JSON, no-store."""
        refused = prompt_checks(request, ctx)
        if refused is not None:
            log(f"refused: /api/data-docs ({refused.text.strip()})")
            return refused
        body = await _capped_json(request, PROMPT_MAX_BODY)
        if isinstance(body, web.Response):
            return body
        project_id = body.get("projectId") if isinstance(body, dict) else None
        if not isinstance(project_id, str) or not project_id or len(project_id) > 64:
            return web.Response(status=400, text="projectId is required\n")
        if ctx.world is None:
            return web.Response(status=503, text="no world\n")
        if ctx.world.data_docs_room(project_id) is None:
            return web.Response(status=404, text="no such JsonUI room\n")
        # read off the event loop (up to 8 MB of JSON): the page, the hooks and /health go on meanwhile. In an executor of
        # its own, two threads: a read that is held up (the independent review 2: a FIFO swapped in) never takes the default one,
        # which processes, 退勤, the mock and the git box share
        status, got = await asyncio.get_running_loop().run_in_executor(_data_docs_pool(), ctx.world.data_docs, project_id)
        if status != 200:
            return web.Response(status=status, text=f"{got}\n")
        return web.Response(body=got, content_type="application/json",
                            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    async def _infra_room(request: web.Request, route: str):
        """The checks of /api/prompt, then {"projectId", …}: (body, the room's root) or a refusal."""
        refused = prompt_checks(request, ctx)
        if refused is not None:
            log(f"refused: {route} ({refused.text.strip()})")
            return refused, None
        body = await _capped_json(request, PROMPT_MAX_BODY)
        if isinstance(body, web.Response):
            return body, None
        project_id = body.get("projectId") if isinstance(body, dict) else None
        if not isinstance(project_id, str) or not project_id or len(project_id) > 64:
            return web.Response(status=400, text="projectId is required\n"), None
        if ctx.world is None:
            return web.Response(status=503, text="no world\n"), None
        root = ctx.world.infra_root(project_id)
        if root is None:
            return web.Response(status=404, text="no such room\n"), None
        return body, root

    async def api_infra_docs(request: web.Request) -> web.Response:
        """The server room's model (infra_docs.read → document_tools' infra.room, the boundary's §5.2): {"projectId",
        "seq"} names a room; its declared infrastructure is read now from its infra folder (inside the room, no symlink,
        capped, merged and validated), when the room's door is pressed and never before. The reply carries the page's
        seq back; a refusal is {ok: false, seq, reason, message} with the boundary's HTTP status. The checks of
        /api/prompt; never a path from the client; off the event loop; JSON, no-store."""
        body, root = await _infra_room(request, "/api/infra-docs")
        if root is None:
            return body
        seq = body.get("seq") if isinstance(body.get("seq"), int) and not isinstance(body.get("seq"), bool) else None
        status, model = await asyncio.get_running_loop().run_in_executor(_data_docs_pool(), infra_docs.read, root, seq)
        return web.json_response(model, status=status, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    async def api_infra_icon(request: web.Request) -> web.Response:
        """One icon the room's settings name ({"projectId", "key": "category:…" | "service:<provider>/<service>"}): an
        image file in the room, read as the model is (infra_docs.icon), its own media type, nosniff, no-store. A key
        that is not configured, or a file that cannot be read: 404 (the page draws the neutral shape)."""
        body, root = await _infra_room(request, "/api/infra-icon")
        if root is None:
            return body
        key = body.get("key")
        if not isinstance(key, str) or not key or len(key) > 200:
            return web.Response(status=400, text="key is required\n")
        got = await asyncio.get_running_loop().run_in_executor(_data_docs_pool(), infra_docs.icon, root, key)
        if got is None:
            return web.Response(status=404, text="no such icon\n")
        data, media = got
        # POST only (no link opens it as a page); the page shows it through <img>, where an SVG runs no script
        return web.Response(body=data, content_type=media, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    async def api_infra_cost(request: web.Request) -> web.Response:
        """The cost simulator (infra_cost.read → document_tools' infra.load, infra.cost): {"projectId", "seq",
        "scenario"?, "date"?, "by"?, "account"?} names a room and a scenario of its load definitions (the first when none); no date:
        the month and the scenarios, a date: that day. The checks of /api/prompt; never a path from the client; off the
        event loop; JSON, no-store."""
        body, root = await _infra_room(request, "/api/infra-cost")
        if root is None:
            return body
        seq = body.get("seq") if isinstance(body.get("seq"), int) and not isinstance(body.get("seq"), bool) else None
        status, got = await asyncio.get_running_loop().run_in_executor(
            _data_docs_pool(), lambda: infra_cost.read(root, seq, body.get("scenario"), body.get("date"),
                                                       body.get("by", "provider"), body.get("account")))
        return web.json_response(got, status=status, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    async def api_prices(request: web.Request) -> web.Response:
        """The page's 単価 sheet (2.3.6): {"op": set | remove | reset, "model", "row"?} changes the user's price
        table (prices.apply_op) — the checks of /api/prompt (prompt_checks) first. Written in the price table's own
        worker (never on the event loop), then read again at once: the next response is priced by it."""
        refused = prompt_checks(request, ctx)
        if refused is not None:
            log(f"refused: /api/prices ({refused.text.strip()})")
            return refused
        body = await _capped_json(request, PROMPT_MAX_BODY)
        if isinstance(body, web.Response):
            return body
        op, model, row = body.get("op"), body.get("model"), body.get("row")
        world = ctx.world
        if world is None or world.prices is None:
            return web.Response(status=503, text="no world\n")
        from . import prices
        book = world.prices
        if world._prices_pool is None:
            world.poll_prices()
        ok, msg = await asyncio.get_running_loop().run_in_executor(
            world._prices_pool, lambda: prices.apply_op(book.path(), op, model, row, book.default))
        if not ok:
            return web.json_response({"ok": False, "error": msg}, status=400, headers={"Cache-Control": "no-store"})
        log(f"prices: {msg}")
        book.recheck()
        return web.json_response({"ok": True, "message": msg}, headers={"Cache-Control": "no-store"})

    async def api_session_end(request: web.Request) -> web.Response:
        """退勤 from a robot card (ticket 2026-10-19-jui-viz-clock-out-button): the checks of /api/prompt
        (prompt_checks, with this route's cap), then the session in this server's list and not ended, the robot asked
        for its main robot (never a subagent), then clockout.end_session's checks of the pid, made twice, and one
        SIGTERM. Every attempt goes to clock-out.log in the runtime folder and to stderr; one naming a session this
        server knows, to the event log too."""
        at = now_ms()
        record = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "remote": request.remote}
        refused = prompt_checks(request, ctx, END_MAX_BODY)
        if refused is None:
            body = await _capped_json(request, END_MAX_BODY)
            refused = body if isinstance(body, web.Response) else None
        if refused is not None:
            return _clock_log(ctx, record, refused)
        sid, agent_id = body.get("sessionId"), body.get("agentId", body.get("sessionId"))
        record.update(sessionId=sid if isinstance(sid, str) else None, agentId=agent_id if isinstance(agent_id, str) else None)
        if not isinstance(sid, str) or not sid or not isinstance(agent_id, str) or not agent_id:
            return _clock_log(ctx, record, web.Response(status=400, text="sessionId is required\n"))
        world = ctx.world
        session = world.sessions.get(sid) if world is not None else None
        if session is None or session["status"] == "ended":
            return _clock_log(ctx, record, web.Response(status=404, text="no such session in this server's list\n"))
        agent = world.agents.get(agent_id)
        if agent is None or agent.get("sessionId") != sid:
            return _clock_log(ctx, record, web.Response(status=404, text="no such robot in this session\n"), world, sid)
        if agent.get("kind") != "main" or agent_id != sid:
            return _clock_log(ctx, record, web.Response(status=403, text="a subagent cannot be clocked out; only its session's main robot\n"), world, sid)
        loop = asyncio.get_running_loop()
        outcome = await loop.run_in_executor(None, lambda: clockout.end_session(paths.claude_sessions_dir(), sid, os.getpid()))
        record.update(pid=outcome.pid, signalled=outcome.signalled)
        if outcome.result == "ended":
            world.clock_out(sid, now_ms())
            record["ledger"] = await loop.run_in_executor(None, lambda: clockout.mark_ledger(paths.claude_home() / "session-recovery", sid))
            if ctx.publish:
                ctx.publish()
            return _clock_log(ctx, record, web.json_response({"ok": True, "ended": True, "pid": outcome.pid}), world, sid, outcome)
        return _clock_log(ctx, record, web.Response(status=outcome.status, text=outcome.reason + "\n"), world, sid, outcome)

    # Before the static catch-all: every method reaches the handler, which answers 405 to all but POST.
    app.router.add_route("*", "/api/prompt", api_prompt)
    app.router.add_route("*", "/api/attach", api_attach)
    app.router.add_route("*", "/api/attach-remove", api_attach_remove)
    app.router.add_route("*", "/api/denial", api_denial)
    app.router.add_route("*", "/api/attach-image", api_attach_image)
    app.router.add_route("*", "/api/history-image", api_history_image)
    app.router.add_route("*", "/api/history-file", api_history_file)
    app.router.add_route("*", "/api/reveal-file", api_reveal_file)
    app.router.add_route("*", "/api/data-docs", api_data_docs)
    app.router.add_route("*", "/api/infra-docs", api_infra_docs)
    app.router.add_route("*", "/api/infra-icon", api_infra_icon)
    app.router.add_route("*", "/api/infra-cost", api_infra_cost)
    app.router.add_route("*", "/api/prices", api_prices)
    app.router.add_route("*", "/api/session/end", api_session_end)
    app.router.add_route("*", "/api/call-command", api_call_command)
    app.router.add_route("*", "/api/notify-presence", api_notify_presence)
    app.router.add_route("*", "/api/ask-wait", api_ask_wait)
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


_DATA_DOCS_POOL: list = []


def close_pools() -> None:
    """The server stopping: the data reads' pool lets its idle threads go, a read still running is not waited for."""
    for pool in _DATA_DOCS_POOL:
        pool.shutdown(wait=False, cancel_futures=True)


def _data_docs_pool():
    """The data server's reads' own executor (2 threads), made on first use."""
    if not _DATA_DOCS_POOL:
        from concurrent.futures import ThreadPoolExecutor
        _DATA_DOCS_POOL.append(ThreadPoolExecutor(max_workers=2, thread_name_prefix="jui-viz-data-docs-read"))
    return _DATA_DOCS_POOL[0]


def prompt_checks(request: web.Request, ctx: ServerContext, max_body: int = PROMPT_MAX_BODY,
                  content_type: str = "application/json") -> web.Response | None:
    """The checks of POST /api/prompt — and of POST /api/session/end, with its own ``max_body`` — each on its own
    (the requester's ruling, 10-19; none may be dropped):

      * POST only (405). The page has no other way to send, and a GET could be made by an <img> on any site.
      * Host exactly ``127.0.0.1:<port>`` (403). The middleware already refuses foreign names (DNS rebinding) with
        421; this route also refuses ``localhost:<port>``: ``jui viz open`` / ``start`` give the page as
        http://127.0.0.1:<port>/, so that is the only origin the page has, and one spelling is one thing to check.
      * Origin exactly ``http://127.0.0.1:<port>`` (403), and present: a browser sends it on every POST, so a
        request without one is not the page (CSRF from another site carries that site's origin).
      * X-Jui-Viz-Token, the per-start token from the served page (401).
      * Content-Type application/json (415): another site's form can only post the three "simple" types without a
        preflight, which this route never answers with CORS headers. POST /api/attach takes
        application/octet-stream instead (``content_type``), which is not a "simple" type either.
      * a declared body over ``max_body`` (413); the read in the handler (_capped_json) stops at max_body + 1 bytes too.
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
    # aiohttp reads a missing Content-Type as application/octet-stream: the header itself must be there
    if "Content-Type" not in request.headers or request.content_type != content_type:
        return web.Response(status=415, text=f"{content_type} only\n")
    if request.content_length is not None and request.content_length > max_body:
        return web.Response(status=413, text="too large\n")
    return None


async def _capped_json(request: web.Request, cap: int):
    """The body as a JSON object, read up to cap + 1 bytes (a chunked body has no Content-Length), or the refusal."""
    raw = b""
    while len(raw) <= cap:
        chunk = await request.content.read(cap + 1 - len(raw))
        if not chunk:
            break
        raw += chunk
    if len(raw) > cap:
        return web.Response(status=413, text="too large\n")
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return web.Response(status=400, text="not json\n")
    return body if isinstance(body, dict) else web.Response(status=400, text="not a JSON object\n")


def _clock_log(ctx: ServerContext, record: dict, response: web.Response, world=None, sid: str | None = None, outcome=None) -> web.Response:
    """Every 退勤 attempt and its outcome: clock-out.log (0600, one JSON line), stderr, and for a session this server
    knows the event log."""
    text = response.text.strip() if response.text and not response.content_type.endswith("json") else "ended"
    result = outcome.result if outcome is not None else "refused"
    record.update(status=response.status, result=result, reason=text)
    clockout.write_log(paths.viz_home() / "clock-out.log", record)
    log(f"clock-out: {record.get('sessionId') or '?'} pid={record.get('pid')} -> {result} {response.status} ({text})")
    if world is not None and sid is not None:
        world.clock_out_event(sid, now_ms(), record)
        if ctx.publish:
            ctx.publish()
    return response


async def _reveal(path: str) -> bool:
    """`open -R path`: Finder shows the file selected in its folder's window. The path is an argument (no shell) and
    absolute (never read as an option). Our own child, waited for up to 10 s. Under the e2e (JUI_VIZ_E2E=1, a server
    of tools/viz_e2e in a throwaway HOME) nothing is opened: the path goes to <viz home>/reveal.log for the arm to read,
    so no Finder window comes up on the screen of whoever runs it."""
    if os.environ.get("JUI_VIZ_E2E") == "1":
        with open(os.path.join(paths.viz_home(), "reveal.log"), "a", encoding="utf-8") as f:
            f.write(path + "\n")
        return True
    try:
        proc = await asyncio.create_subprocess_exec("open", "-R", path, stdin=asyncio.subprocess.DEVNULL,
                                                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    except OSError:
        return False
    try:
        return await asyncio.wait_for(proc.wait(), 10) == 0
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return False



def _dispatch_hook(ctx: ServerContext, payload: dict) -> None:
    try:
        result = ctx.on_hook(payload)  # type: ignore[misc]
        if asyncio.iscoroutine(result):
            asyncio.ensure_future(result)
    except Exception as exc:  # noqa: BLE001 - one bad payload must not stop the server
        log(f"a hook could not be handled ({type(exc).__name__})")


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
        # further back (2.3.12): `before` reads the items before that byte (「もっと前を読む」), `stop` reads from that byte
        # to the end (the newest part, joined to what was read before it); both are offsets the server itself gave
        num = lambda v: v if type(v) is int and v >= 0 else None   # noqa: E731
        got = (ctx.world.history(agent_id, end=num(message.get("before")), stop=num(message.get("stop")))
               if ctx.world is not None and isinstance(agent_id, str) else None)
        if got is None:
            await sock.send_json({"type": "ack", "reqId": req_id, "ok": False, "error": "no transcript for this robot"})
            return
        await sock.send_json({"type": "history", "reqId": req_id, "agentId": agent_id, "items": got["items"],
                              "bytes": got["bytes"], "more": got["more"], "from": got.get("from"), "results": got.get("results") or {}})
    elif isinstance(kind, str) and kind.startswith("talk."):
        # The talk view (talk_contract.json): read only; there is no request that sends a message.
        if ctx.talk is None:
            await sock.send_json({"type": "ack", "reqId": req_id, "ok": False, "error": i18n.tl("srv.talk.unavailable")})
            return
        await ctx.talk.handle(sock, message)
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
            await sock.send_json({"type": "ack", "reqId": req_id, "ok": False, "error": i18n.tl("srv.weather.unavailable")})
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
        if ctx.talk is not None and ctx.talk.frames:
            await ctx.talk.flush(ctx.sockets)
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
